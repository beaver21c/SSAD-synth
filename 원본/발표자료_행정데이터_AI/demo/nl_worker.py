#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""자연어 명령 창의 뒷단 작업자 — 질문을 분석 지원기(로컬LLM_준비/06_build/assistant.py)에 넘기고 결과(응답, 코드, 집계표, 그림)를 JSON 한 줄로 돌려준다.

  /mnt/share/행정데이터_set/.venv/bin/python nl_worker.py        # 표준 입력으로 {"question": "..."} 한 줄씩, 표준 출력으로 결과 한 줄씩
방식(환경변수 NL_MODE)
  replay  언어모형 서버를 쓰지 않고, 평가 실행에 기록된 실제 모형 응답을 같은 질문에 대해 다시 내보낸다(코드는 지금 다시 실행한다). 기록에 없는 질문은 처리하지 않는다
  live    설정 파일의 언어모형 서버(llama.cpp, OpenAI 호환 주소)에 질문을 보낸다
분석 함수(ssda)의 실행 전 점검·격리 실행·출력 통제는 두 방식 모두 그대로 적용된다.
"""
import base64
import json
import os
import sys
import tempfile
from pathlib import Path

LLM = Path('/mnt/share/행정데이터_set/로컬LLM_준비')
sys.path.insert(0, str(LLM / '06_build'))
os.environ.setdefault('SSDA_DATA', '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet')
os.environ.pop('SSDA_HOOKS', None)
_real_stdout = sys.stdout
sys.stdout = sys.stderr                                   # 다른 출력이 결과 줄에 섞이지 않게

from assistant import Assistant, load_config, make_client  # noqa: E402
from retriever import Retriever  # noqa: E402

MODE = os.environ.get('NL_MODE', 'replay')
TMP = Path(os.environ.get('NL_TMP') or tempfile.mkdtemp(prefix='nl_'))
RUNS = ('indep_c2', 'arete27b_lora_v3_r3_base')          # 현행 구성(미세조정 모형 + 개선판 3 + 보완 동작)의 평가 실행 기록


def norm(q):
    return ' '.join((q or '').split())


def load_bank():
    """질문 → 기록된 모형 응답의 순서(코드가 든 응답들, 마지막 응답)."""
    bank = {}
    for run in RUNS:
        p = LLM / '05_eval' / 'runs' / run / 'transcripts.jsonl'
        if not p.exists():
            continue
        for line in p.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            t = json.loads(line)
            if len(t['turns']) != 1:
                continue
            u = t['turns'][0]
            if (u.get('verification') or {}).get('answer_retried') or any(s.get('origin') == 'user' for s in u['steps']):
                continue
            bank.setdefault(norm(u['question']), {'replies': [s['assistant'] for s in u['steps']] + [u['final']], 'run': run, 'id': t['id']})
    return bank


class ReplayClient:
    """기록된 응답을 차례로 내는 연결부(언어모형 서버 없음)."""

    def __init__(self, bank):
        self.bank, self.queue, self.usage, self.src = bank, [], {'calls': 0}, None

    def chat(self, messages):
        self.usage['calls'] += 1
        last = messages[-1]['content']
        if '[질문]' in last:
            hit = self.bank.get(norm(last.split('[질문]')[-1]))
            self.queue = list(hit['replies']) if hit else []
            self.src = hit
        return self.queue.pop(0) if self.queue else '확인 필요\n- 시연용 기록에 없는 질문임(언어모형 서버가 연결되어 있지 않음)\n\n위 내용을 알려 주면 바로 산출함'

    def warmup(self, system):
        return None


def main():
    cfg = load_config()
    cfg['paths'].update(export=str(TMP / 'export'), log=str(TMP / 'ssda_log.jsonl'), transcripts=str(TMP / 'assistant_log.jsonl'))
    (TMP / 'export').mkdir(parents=True, exist_ok=True)
    bank = load_bank()
    client = make_client(cfg, None, None) if MODE == 'live' else ReplayClient(bank)
    rt = Retriever()
    print(json.dumps({'ready': True, 'mode': MODE, 'bank': len(bank), 'model': os.path.basename(str(cfg['model'].get('file', ''))), 'system': cfg['prompt']['system']}, ensure_ascii=False), file=_real_stdout, flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            q = req['question']
            if req.get('op') == 'known':
                out = {'known': norm(q) in bank}
            else:
                ast = Assistant(cfg, client, rt)
                ast.env = dict(ast.env, PYTHONPATH=str(Path(__file__).resolve().parent / 'termfix') + os.pathsep + ast.env['PYTHONPATH'])   # 그림 표기 「억제」→「마킹」(2026-11-21)
                rec = ast.ask(q)
                steps = []
                for s in rec['steps']:
                    figs = []
                    for f in s.get('figures') or []:
                        fp = TMP / 'export' / f
                        if fp.exists():
                            figs.append({'name': f, 'src': 'data:image/png;base64,' + base64.b64encode(fp.read_bytes()).decode()})
                    steps.append({'code': s['code'], 'ok': bool(s.get('ok')), 'origin': s.get('origin', 'model'), 'blocked': bool(s.get('violations')),
                                  'error': (s.get('error') or '').splitlines()[0][:400] if s.get('error') else '', 'stdout': (s.get('stdout') or '')[:4000],
                                  'results': s.get('results') or {}, 'figures': figs})
                src = getattr(client, 'src', None)
                out = {'ok': True, 'mode': MODE, 'question': q, 'final': rec['final'], 'footer': rec.get('footer') or '', 'n_calls': rec['n_calls'], 'elapsed_sec': rec['elapsed_sec'],
                       'hooks': rec.get('hooks'), 'steps': steps, 'replay_source': ({'run': src['run'], 'id': src['id']} if src else None)}
        except Exception as e:                           # noqa: BLE001
            out = {'ok': False, 'error': f'{type(e).__name__}: {e}'[:600]}
        print(json.dumps(out, ensure_ascii=False), file=_real_stdout, flush=True)


if __name__ == '__main__':
    main()
