#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""조립기 — 질문 하나를 「검색 → 프롬프트 조립 → 모형 호출 → 코드 점검·격리 실행 → 결과 회신」으로 처리한다.

  처리 순서  ① 검색·프롬프트 조립  ② 모형이 「분석 계획」과 코드 작성  ③ 실행 전 점검(금지 표현, 없는 변수·값이 없는 변수)
            ④ 격리 실행  ⑤ 산출 자동 점검(분모·분류 누락·억제·전체 값·그림)과 「[검증 결과]」 회신  ⑥ 모형이 「결과」「유의 사항」 작성
            ⑦ 응답 수치 대조(실행 결과에 없는 수치가 있으면 1회 다시 작성)  ⑧ 「검증 요약」을 하네스가 만들어 붙임
  보완 동작(2026-11-17, 설정 verify 절에서 켬. 모형의 흐름이 막힌 경우에만 작동하고 그 밖의 대화는 바꾸지 않음)
            user_code       질문에 분석 코드가 들어 있는데 모형이 코드 없이 「확인 필요」로 답하면, 제시된 코드를 같은 점검·격리 실행에 넣어 결과와 「[검증 결과]」를 모형에 돌려줌
            repeat_guard    실패한 코드와 같은 코드를 다시 내면 실행하지 않고, 고친 부분이 없다는 안내와 앞선 오류를 돌려줌
            var_candidates  한 질문에서 없는 변수 오류가 두 번째 나면, 질문의 낱말로 변수 사전을 찾은 후보를 오류 문구에 덧붙임
            unexecuted_results  실행에 성공한 코드가 없는데 응답에 결과 표가 적혀 있으면 받아들이지 않음. 질문에 코드가 있으면 그 코드를 실행해 결과를 돌려주고, 없으면 코드를 실행해 다시 쓰게 함(질문당 1회)
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
HOOKS = ('user_code', 'repeat_guard', 'var_candidates', 'unexecuted_results', 'ask_gate', 'review', 'name_cards')
USER_CODE_NOTE = ('안내: 위는 이용자가 질문에 제시한 코드를 그대로 실행한 결과임. 확인을 요청하지 말 것. 검증 결과에 경고·주의가 있거나 오류가 났으면 그 내용대로 고친 코드를 작성해 실행하고, '
                  '고칠 점이 없으면 코드를 다시 쓰지 말고 이 결과로 「결과」와 「유의 사항」을 작성할 것')
EMPTY_OUT = {'ok': False, 'violations': [], 'stdout': '', 'results': {}, 'figures': [], 'checks': {}, 'figure_checks': []}


def norm_code(code):
    return re.sub(r'\s+', ' ', code or '').strip()
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
    cfg['verify'] = {'result_checks': True, 'ground_variables': True, 'ground_numbers': True, 'answer_retries': 1, 'footer': True,
                     'user_code': False, 'repeat_guard': False, 'var_candidates': False, 'unexecuted_results': False, **(cfg.get('verify') or {})}
    for kv in filter(None, os.environ.get('SSDA_HOOKS', '').split(',')):      # 평가에서 보완 동작만 바꿔 볼 때: SSDA_HOOKS=user_code=replace,repeat_guard=1,var_candidates=1
        k, _, v = kv.partition('=')
        if k.strip() in HOOKS:
            cfg['verify'][k.strip()] = {'0': False, 'off': False, 'false': False, '': True, '1': True, 'on': True, 'true': True}.get(v.strip().lower(), v.strip())
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
        self.qhist = []                                 # 이 대화의 앞선 질문(이어 묻는 질문의 용어 해석·조건 대조·검토에 쓴다)
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
        self.tr = tr = self.terms.resolve(question, self.pending, self.qhist)   # 제도명·약어 풀이와 내역이 정해지지 않은 용어(앞선 질문의 제도를 이어받음)
        tcards = [c for c in tr['cards'] if c['id'] not in self.shown][:p.get('n_term_cards', 2)]
        self.shown.update(c['id'] for c in tcards)
        query = (question + ' ' + tr['expansion']).strip()                  # 정식 명칭·구성 급여 이름을 덧붙여 변수 카드를 찾음
        followup = len(self.messages) > 1                                   # 후속 질문에는 새로 나온 제도 설명 카드와 용어 확인만 붙임
        docs = [] if followup else (self.rt.search(query, k=p['n_variable_cards'], kinds=['variable']) + self.rt.search(question, k=p['n_doc_cards'], kinds=['doc'])
                                    + self.rt.search(question, k=p['n_rule_cards'], kinds=['rule']))
        if self.cfg['verify'].get('name_cards') and not followup:           # 질문의 낱말이 한글 이름에 그대로 든 변수의 카드를 덧붙임(검색 순위에서 밀린 변수 보완)
            have = {d['id'] for d in docs}
            for c in verify.var_candidates(question, {i[4:] for i in have if i.startswith('var:')}, top=3):
                d = self.rt.get('var:' + c['name'])
                if d and d['id'] not in have:
                    docs.append(d); have.add(d['id'])
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
        hooks = {'user_code': False, 'repeat': 0, 'var_candidates': 0, 'unexecuted': 0, 'ask_gate': 0, 'review': 0}       # 보완 동작이 작동한 내역(기록·채점용)
        hist = list(self.qhist); self.qhist.append(question)
        budget, review = self.cfg['run']['max_steps'], None
        ucode = CODE.search(question)                                       # 이용자가 질문에 제시한 코드
        ucode = ucode.group(1).strip() if ucode and 'ssda.' in ucode.group(1) else None
        no_pre = {'used': [], 'unknown': {}, 'empty': [], 'unseen': []}
        while True:
            for _ in range(budget + 3):
                self.trim()
                reply = self.client.chat(self.messages)
                self.messages.append({'role': 'assistant', 'content': reply})
                m = CODE.search(reply)
                n_model = sum(1 for s in steps if s.get('origin') != 'user')    # 모형이 작성한 코드의 수(실행 횟수 한도는 이것으로 셈)
                usr = [x['content'] for x in self.messages[:-1] if x['role'] == 'user']
                fake = (not m and V['unexecuted_results'] and not hooks['unexecuted'] and not any(s.get('ok') for s in steps) and '요청 처리 불가' not in reply
                        and (verify.claims_results(reply, usr) or verify.claims_values(reply, usr)))      # 실행에 성공한 코드가 없는데 결과 표나 수치를 적은 응답
                if fake:
                    hooks['unexecuted'] += 1
                if (not m and ucode and V['user_code'] and not steps and not hooks['user_code'] and ('확인 필요' in reply or fake) and '요청 처리 불가' not in reply
                        and not [u for u in self.tr['unresolved'] if u['policy'] in ('ask', 'absent')]):
                    # 제시된 코드의 확인 요청에 되물은 경우: 그 코드를 모형의 코드와 같은 점검·격리 실행에 넣고 결과를 돌려줌(용어 확인이 필요한 질문과 거절한 요청은 그대로 둠)
                    hooks['user_code'] = True
                    pre = verify.lint_code(ucode, self.seen) if V['ground_variables'] else no_pre
                    out = {**EMPTY_OUT, 'error': verify.lint_error(pre)} if pre['unknown'] or pre['empty'] else self.execute(ucode)
                    req = (verify.check_request(question, ucode, hist) + Glossary.check(self.tr['unresolved'], pre['used'])) if V['result_checks'] else []
                    steps.append({'assistant': reply, 'code': ucode, 'pre': pre, 'req': req, 'origin': 'user', **out})
                    self.seen |= verify.names_in(out['stdout'])
                    if V['user_code'] == 'reply':               # 되물은 응답은 두고 실행 결과를 답으로 돌려줌
                        self.messages.append({'role': 'user', 'content': self.tool_message(out, pre, req) + '\n\n' + USER_CODE_NOTE})
                    else:                                       # 기본(replace): 되물은 응답을 「제시된 코드를 실행함」으로 바꿔 학습된 대화 형태(코드 → 실행 결과)에 맞춤
                        self.messages[-1] = {'role': 'assistant', 'content': f'이용자가 제시한 코드를 그대로 실행해 확인함\n\n```python\n{ucode}\n```'}
                        self.messages.append({'role': 'user', 'content': self.tool_message(out, pre, req) + '\n\n' + USER_CODE_NOTE})
                    continue
                if fake:                                        # 제시 코드가 없는 경우: 응답을 받아들이지 않고 코드를 실행해 다시 쓰게 함
                    self.messages.append({'role': 'user', 'content': verify.UNEXECUTED_NOTE})
                    continue
                if (not m and V.get('ask_gate') and not hooks['ask_gate'] and not ucode and '확인 필요' in reply[:300] and '요청 처리 불가' not in reply and not any(s.get('ok') for s in steps)
                        and not [u for u in self.tr['unresolved'] if u['policy'] in ('ask', 'absent')]):
                    # 되묻기 전 점검: 용어 사전이 되물으라고 한 경우가 아닌데 코드 없이 되물으면 한 번 돌려보냄(질문의 낱말로 찾은 변수 후보를 덧붙임)
                    hooks['ask_gate'] += 1
                    cand = verify.var_candidates(question, self.seen)
                    self.seen |= {c['name'] for c in cand}
                    self.messages.append({'role': 'user', 'content': verify.ask_gate_note(cand)})
                    continue
                if not m or n_model >= budget:
                    final = reply
                    break
                code = m.group(1).strip()
                pre = verify.lint_code(code, self.seen) if V['ground_variables'] else no_pre
                prev = next((s for s in reversed(steps) if norm_code(s['code']) == norm_code(code)), None)
                if V['repeat_guard'] and prev is not None and not prev.get('ok'):      # 실패한 코드를 그대로 다시 냄 → 실행하지 않음
                    hooks['repeat'] += 1
                    orig = next((s for s in steps if norm_code(s['code']) == norm_code(code) and not s.get('repeat')), prev)      # 처음 실패한 실행(그 오류를 다시 알림)
                    out = {**EMPTY_OUT, 'error': verify.repeat_error(orig.get('error', ''), code), 'repeat': True}
                    if orig.get('hint'):
                        out['hint'] = orig['hint']
                elif pre['unknown'] or pre['empty']:            # 없는 변수·값이 없는 변수는 실행하지 않고 비슷한 이름과 함께 돌려보냄
                    err = verify.lint_error(pre)
                    if V['var_candidates'] and pre['unknown'] and any((s.get('pre') or {}).get('unknown') for s in steps):      # 두 번째부터는 변수 사전에서 찾은 후보를 덧붙임
                        tried = {v for s in steps for v in (s.get('pre') or {}).get('unknown', {})} | set(pre['unknown'])
                        cand = verify.var_candidates(question, self.seen, tried)
                        if cand:
                            hooks['var_candidates'] += 1
                            err += ' / ' + verify.candidates_note(cand)
                            self.seen |= {c['name'] for c in cand}
                    out = {**EMPTY_OUT, 'error': err}
                else:
                    out = self.execute(code)
                req = (verify.check_request(question, code, hist) + Glossary.check(self.tr['unresolved'], pre['used'])) if V['result_checks'] else []
                # ↑ 질문에 적힌 조건이 코드에 반영됐는지, 내역이 정해지지 않은 용어를 어떻게 해석했는지
                steps.append({'assistant': reply, 'code': code, 'pre': pre, 'req': req, **out})
                self.seen |= verify.names_in(out['stdout'])
                self.messages.append({'role': 'user', 'content': self.tool_message(out, pre, req)})
            last = next((s for s in reversed(steps) if s.get('ok') and s.get('results')), None)
            if not (V.get('review') and review is None and last and final and '확인 필요' not in final[:200] and '요청 처리 불가' not in final[:200]):
                break
            # 검토 단계: 실행한 산출이 질문과 일치하는지 대화와 분리된 요청으로 다시 물음. 불일치이면 사유를 돌려주고 한 번 고칠 기회를 줌
            unused = [i[4:] for i in ids if i.startswith('var:')]
            text = self.client.chat([{'role': 'system', 'content': self.system}, {'role': 'user', 'content': verify.review_request(hist + [question], last, unused)}])
            review = {'flag': verify.review_verdict(text), 'text': text[:800], 'n_steps': len(steps)}
            if not review['flag']:
                break
            hooks['review'] += 1
            review['before'] = final
            self.messages.append({'role': 'user', 'content': verify.review_note(text)})
            budget += 1
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
        usr = [x['content'] for x in self.messages if x['role'] == 'user']
        if (V['unexecuted_results'] and not ok_steps and '요청 처리 불가' not in final
                and (verify.claims_results(final, usr) or verify.claims_values(final, usr))):      # 다시 쓰게 한 뒤에도 실행 없이 결과 표나 수치가 남은 응답
            ver['unexecuted_claim'] = True
            if V['footer']:
                foot = (foot + '\n' if foot else '검증 요약(자동 점검)\n') + verify.UNEXECUTED_FOOT
        rec = {'question': question, 'context_ids': ids, 'steps': steps, 'final': final, 'verification': ver, 'footer': foot, 'n_calls': len(steps) + 1 + int(retried),
               'elapsed_sec': round(time.time() - t0, 2)}
        rec['n_calls'] += hooks['ask_gate'] + (1 if review is not None else 0)
        if any(hooks.values()):
            rec['hooks'] = hooks
        if review is not None:
            rec['review'] = review
        with open(self.cfg['paths']['transcripts'], 'a', encoding='utf-8') as fp:      # 재현에 필요한 산출 조건을 함께 기록(집계 결과의 값은 기록하지 않음)
            fp.write(json.dumps({'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'question': question, 'context_ids': ids, 'n_calls': rec['n_calls'], 'elapsed_sec': rec['elapsed_sec'],
                                 'data': self.data_id, 'ssda': SSDA_VERSION, 'verification': ver, 'hooks': hooks if any(hooks.values()) else None,
                                 'steps': [{'code': s['code'], 'code_sha256': hashlib.sha256(s['code'].encode()).hexdigest()[:16], 'ok': s['ok'], 'violations': s['violations'],
                                            'error': s['error'], 'figures': s['figures'], 'origin': s.get('origin', 'model')} for s in steps]}, ensure_ascii=False) + '\n')
        return rec


def show(rec):
    for s in rec['steps']:
        print('─' * 60); print(s['assistant'] if s.get('origin') != 'user' else '(하네스) 질문에 제시된 코드를 그대로 실행해 확인함\n\n```python\n' + s['code'] + '\n```')
        print('─' * 60); print('[실행]', '성공' if s['ok'] else '실패: ' + s['error'].splitlines()[0])
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
