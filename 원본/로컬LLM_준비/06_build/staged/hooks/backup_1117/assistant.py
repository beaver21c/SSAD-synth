#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""조립기 — 질문 하나를 「검색 → 프롬프트 조립 → 모형 호출 → 코드 점검·격리 실행 → 결과 회신」으로 처리한다.

  처리 순서  ① 검색·프롬프트 조립  ② 모형이 「분석 계획」과 코드 작성  ③ 실행 전 점검(금지 표현, 없는 변수·값이 없는 변수)
            ④ 격리 실행  ⑤ 산출 자동 점검(분모·분류 누락·억제·전체 값·그림)과 「[검증 결과]」 회신  ⑥ 모형이 「결과」「유의 사항」 작성
            ⑦ 응답 수치 대조(실행 결과에 없는 수치가 있으면 1회 다시 작성)  ⑧ 「검증 요약」을 하네스가 만들어 붙임
  모형이 할 수 있는 동작은 파이썬 코드 블록 1개 작성뿐이다(03_prompts/tool_protocol.json).
  코드는 ssda.guard 점검을 통과한 것만, 질의마다 새 프로세스(ssda.runner)에서 시간·메모리 한도를 걸어 실행한다.
  모형에는 개인 단위 자료가 전달되지 않는다. 전달되는 것은 질문, 참고 자료(변수 카드 등), 집계 결과의 표준 출력뿐이다.

사용
  python 06_build/assistant.py --ask "65세 이상 기초연금 수급률을 시도별로"      # 설정 파일의 추론 서버 사용
  python 06_build/assistant.py --chat                                         # 대화형
  python 06_build/assistant.py --ask "..." --mock oracle                      # 모형 없이 흐름 점검(평가 문항만 응답)
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '02_library')); sys.path.insert(0, str(ROOT / '06_build'))
from clients import MockClient, OpenAICompatClient  # noqa: E402
from retriever import EX, Retriever  # noqa: E402
from terms import Glossary  # noqa: E402
from ssda import verify  # noqa: E402 — 자료를 열지 않고 변수 사전만 읽는 점검 함수

CODE = re.compile(r'```python\n(.*?)```', re.S)
SSDA_VERSION = __import__('ssda').__version__


def load_config(path=None):
    import yaml
    p = Path(path or os.environ.get('SSDA_CONFIG') or ROOT / 'config' / 'assistant.yaml')      # SSDA_CONFIG: 다른 설정으로 일괄 실행할 때(예: 미세조정 모형 평가)
    cfg = yaml.safe_load(p.read_text(encoding='utf-8'))

    def expand(v):
        if isinstance(v, str):
            v = os.path.expandvars(v)
            return v
        if isinstance(v, dict):
            return {k: expand(x) for k, x in v.items()}
        return v
    cfg = expand(cfg)
    cfg['verify'] = {'result_checks': True, 'ground_variables': True, 'ground_numbers': True, 'answer_retries': 1, 'footer': True, **(cfg.get('verify') or {})}
    for k, v in cfg['paths'].items():                 # 상대 경로는 준비 폴더 기준
        if v and not os.path.isabs(v) and not v.startswith('$'):
            cfg['paths'][k] = str(ROOT / v)
    return cfg


def make_client(cfg, mock=None, bank=None):
    if mock:
        return MockClient(mock, bank)
    m = cfg['model']
    return OpenAICompatClient(m['base_url'], m['served_name'], os.environ.get(m.get('api_key_env') or '', ''), m.get('temperature', 0.0), m.get('max_tokens', 1500),
                              m.get('timeout_sec', 600), m.get('extra_body'))


class Assistant:
    def __init__(self, cfg, client, retriever=None):
        self.cfg, self.client = cfg, client
        self.rt = retriever or Retriever()
        self.system = Path(cfg['prompt']['system'] if os.path.isabs(cfg['prompt']['system']) else ROOT / cfg['prompt']['system']).read_text(encoding='utf-8').strip()
        self.messages = [{'role': 'system', 'content': self.system}]
        if (cfg.get('model') or {}).get('server') == 'llama.cpp' and cfg['prompt'].get('warmup', True) and hasattr(client, 'warmup'):
            client.warmup(self.system)                  # 서버에 시스템 프롬프트 구간의 상태 저장 지점을 남김(프로세스당 한 번, clients.py)
        self.shown = set()                              # 이미 보여 준 참고 자료
        self.seen = set()                               # 이 대화에서 정의를 본 변수(참고 자료·변수 찾기 결과에 나온 변수)
        self.terms = Glossary()                         # 제도 용어 사전(약어·통칭 풀이, 모호한 용어의 확인 규칙)
        self.pending = []                               # 앞선 질문에서 되물은 용어(이번 답에서 내역이 정해지는지 본다)
        self.tr = {'unresolved': []}
        self.ex = Retriever(EX) if cfg['prompt'].get('n_examples', 0) and EX.exists() else None   # 유사 예시(미세조정 없이 쓸 때)
        self.env = dict(os.environ, PYTHONPATH=str(ROOT / '02_library'), SSDA_DATA=cfg['paths']['data'], SSDA_EXPORT=cfg['paths']['export'], SSDA_LOG=cfg['paths']['log'])
        d = Path(cfg['paths']['data']) if cfg['paths'].get('data') else None
        self.data_id = {'file': d.name, 'bytes': d.stat().st_size, 'mtime': int(d.stat().st_mtime)} if d and d.exists() else None
        for k in ('export', 'log', 'transcripts'):
            Path(cfg['paths'][k]).parent.mkdir(parents=True, exist_ok=True) if k != 'export' else Path(cfg['paths'][k]).mkdir(parents=True, exist_ok=True)

    # ── 참고 자료 ──
    def context(self, question, extra=None):
        p = self.cfg['prompt']
        self.tr = tr = self.terms.resolve(question, self.pending)          # 제도명·약어 풀이와 내역이 정해지지 않은 용어
        tcards = [c for c in tr['cards'] if c['id'] not in self.shown][:p.get('n_term_cards', 2)]
        self.shown.update(c['id'] for c in tcards)
        query = (question + ' ' + tr['expansion']).strip()                  # 정식 명칭·구성 급여 이름을 덧붙여 변수 카드를 찾음
        followup = len(self.messages) > 1                                   # 후속 질문에는 새로 나온 제도 설명 카드와 용어 확인만 붙임
        docs = [] if followup else (self.rt.search(query, k=p['n_variable_cards'], kinds=['variable']) + self.rt.search(question, k=p['n_doc_cards'], kinds=['doc'])
                                    + self.rt.search(question, k=p['n_rule_cards'], kinds=['rule']))
        new = [d for d in docs if d['id'] not in self.shown]
        self.shown.update(d['id'] for d in new)
        cards = [f"■ {c['title']}\n{c['text'][:p.get('term_card_chars', 1000)]}" for c in tcards] + [f"■ {d['title']}\n{d['text'][:p['card_chars']]}" for d in new]
        new = tcards + new
        if self.ex and not followup:
            for d in self.ex.search(question, k=p['n_examples']):
                if d['id'] not in self.shown:
                    self.shown.add(d['id']); new.append(d)
                    cards.append(f"■ 비슷한 질문의 처리 예\n질문: {d['title']}\n응답:\n{d['text']}")
        if extra:
            cards.append(extra)
        cards += tr['notes']                                                # 「용어 확인」은 질문 바로 앞에 둠
        return '\n\n'.join(cards), [d['id'] for d in new]

    # ── 코드 실행 ──
    def execute(self, code):
        r = self.cfg['run']
        if not r.get('isolate', True):
            os.environ.update({k: self.env[k] for k in ('SSDA_DATA', 'SSDA_EXPORT', 'SSDA_LOG')})
            from ssda import runner
            return runner.run(code, limits=False)
        with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False, encoding='utf-8') as fp:
            fp.write(code); path = fp.name
        try:
            p = subprocess.run([sys.executable, '-m', 'ssda.runner', path, '--timeout', str(r['timeout_sec']), '--mem', str(r.get('mem_gb', 6))], capture_output=True, text=True, env=self.env,
                               timeout=r['timeout_sec'] + 30, cwd=str(ROOT))
            return json.loads(p.stdout.strip().splitlines()[-1])
        except subprocess.TimeoutExpired:
            return {'ok': False, 'violations': [], 'stdout': '', 'error': f"시간 한도({r['timeout_sec']}초) 초과", 'results': {}, 'figures': []}
        except Exception as e:                          # noqa: BLE001
            return {'ok': False, 'violations': [], 'stdout': '', 'error': f'실행기 오류: {e}', 'results': {}, 'figures': []}
        finally:
            os.unlink(path)

    def tool_message(self, out, pre=None, req=None):
        return verify.tool_message(out, pre, self.cfg['paths']['export'], self.cfg['run'].get('stdout_chars', 4000), self.cfg['verify']['result_checks'], req)

    def trim(self):
        """문맥 한도를 넘으면 오래된 대화부터 뺀다(시스템 프롬프트와 최근 대화는 유지). 글자 수 ÷ 1.5 를 토큰 수로 어림한다."""
        budget = (self.cfg['model'].get('context_tokens', 16384) - self.cfg['model'].get('max_tokens', 1500)) * 1.5
        while sum(len(m['content']) for m in self.messages) > budget and len(self.messages) > 3:
            del self.messages[1]
            while len(self.messages) > 2 and self.messages[1]['role'] != 'user':
                del self.messages[1]

    # ── 질문 1건 ──
    def ask(self, question, extra_context=None):
        t0 = time.time(); V = self.cfg['verify']
        ctx, ids = self.context(question, extra_context)
        self.seen |= verify.names_in(ctx)
        self.messages.append({'role': 'user', 'content': (f'[참고 자료]\n{ctx}\n\n' if ctx else '') + f'[질문]\n{question}'})
        steps, final = [], ''
        for _ in range(self.cfg['run']['max_steps'] + 1):
            self.trim()
            reply = self.client.chat(self.messages)
            self.messages.append({'role': 'assistant', 'content': reply})
            m = CODE.search(reply)
            if not m or len(steps) >= self.cfg['run']['max_steps']:
                final = reply
                break
            code = m.group(1).strip()
            pre = verify.lint_code(code, self.seen) if V['ground_variables'] else {'used': [], 'unknown': {}, 'empty': [], 'unseen': []}
            if pre['unknown'] or pre['empty']:              # 없는 변수·값이 없는 변수는 실행하지 않고 비슷한 이름과 함께 돌려보냄
                out = {'ok': False, 'violations': [], 'stdout': '', 'error': verify.lint_error(pre), 'results': {}, 'figures': [], 'checks': {}, 'figure_checks': []}
            else:
                out = self.execute(code)
            req = (verify.check_request(question, code) + Glossary.check(self.tr['unresolved'], pre['used'])) if V['result_checks'] else []
            # ↑ 질문에 적힌 조건이 코드에 반영됐는지, 내역이 정해지지 않은 용어를 어떻게 해석했는지
            steps.append({'assistant': reply, 'code': code, 'pre': pre, 'req': req, **out})
            self.seen |= verify.names_in(out['stdout'])
            self.messages.append({'role': 'user', 'content': self.tool_message(out, pre, req)})
        # 응답 점검: 「결과」의 수치가 실행 결과에 있는 값인지, 억제 안내가 있는지
        bad, n_num, retried = [], None, False
        ok_steps = [s for s in steps if s.get('ok')]
        if ok_steps and V['ground_numbers']:
            src = verify.answer_sources(self.messages, [s['code'] for s in steps])
            for attempt in range(V['answer_retries'] + 1):
                issues = verify.answer_issues(final, src, ok_steps[-1].get('checks'))
                bad = [n for i in issues if i['code'] == '수치 대조' for n in i['numbers']]
                if not issues or attempt == V['answer_retries']:
                    break
                self.messages.append({'role': 'user', 'content': '[검증 결과]\n' + '\n'.join(f"- {i['level']}({i['code']}): {i['msg']}" for i in issues)
                                      + '\n코드는 다시 쓰지 말고 「결과」와 「유의 사항」만 다시 작성할 것'})
                final = self.client.chat(self.messages); retried = True
                self.messages.append({'role': 'assistant', 'content': final})
            n_num = verify.count_numbers(verify.result_part(final))
        self.pending = [u for u in self.tr['unresolved'] if u['policy'] in ('ask', 'absent')] if not ok_steps else []   # 되물은 용어는 다음 질문에서 다시 확인
        ver = verify.summarize(steps, bad, n_num, retried)
        foot = verify.footer(ver) if V['footer'] else ''
        rec = {'question': question, 'context_ids': ids, 'steps': steps, 'final': final, 'verification': ver, 'footer': foot, 'n_calls': len(steps) + 1 + int(retried),
               'elapsed_sec': round(time.time() - t0, 2)}
        with open(self.cfg['paths']['transcripts'], 'a', encoding='utf-8') as fp:      # 재현에 필요한 산출 조건을 함께 기록(집계 결과의 값은 기록하지 않음)
            fp.write(json.dumps({'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'question': question, 'context_ids': ids, 'n_calls': rec['n_calls'], 'elapsed_sec': rec['elapsed_sec'],
                                 'data': self.data_id, 'ssda': SSDA_VERSION, 'verification': ver,
                                 'steps': [{'code': s['code'], 'code_sha256': hashlib.sha256(s['code'].encode()).hexdigest()[:16], 'ok': s['ok'], 'violations': s['violations'],
                                            'error': s['error'], 'figures': s['figures']} for s in steps]}, ensure_ascii=False) + '\n')
        return rec


def show(rec):
    for s in rec['steps']:
        print('─' * 60); print(s['assistant']); print('─' * 60); print('[실행]', '성공' if s['ok'] else '실패: ' + s['error'].splitlines()[0])
        print(s['stdout'].rstrip()[:3000])
    print('═' * 60); print(rec['final'])
    if rec.get('footer'):
        print('─' * 60); print(rec['footer'])
    print(f"(모형 호출 {rec['n_calls']}회, {rec['elapsed_sec']}초)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config'); ap.add_argument('--ask'); ap.add_argument('--chat', action='store_true'); ap.add_argument('--mock', choices=['oracle', 'naive', 'sloppy'])
    a = ap.parse_args()
    cfg = load_config(a.config)
    bank = None
    if a.mock in ('oracle', 'sloppy'):
        sys.path.insert(0, str(ROOT / '05_eval'))
        from score import load_bank
        bank = load_bank()
    ast = Assistant(cfg, make_client(cfg, a.mock, bank))
    if a.ask:
        show(ast.ask(a.ask))
    elif a.chat:
        print('질문을 입력(빈 줄이면 종료)')
        while True:
            q = input('> ').strip()
            if not q:
                break
            show(ast.ask(q))
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
