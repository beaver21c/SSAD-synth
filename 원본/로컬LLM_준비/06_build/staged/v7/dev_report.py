#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""개발 실행의 대조 — 기준 실행(2차)과 개발 실행(조치 반영)의 문항별 판정을 견주고, 보완 동작(ask_gate, review)이 작동한 문항의 전후를 본다.

  INDEP_DIR=<차수 폴더> python 06_build/staged/v7/dev_report.py <기준 실행> <개발 실행>
- 채점은 05_eval/independent/score_outcome.py 를 그대로 씀. 검토(review) 전의 판정은 검토가 작동한 문항의 기록을 검토 전 상태로 잘라 따로 채점함(<개발 실행>_prerev)
- 개발 묶음(이미 결과를 본 문항)에서의 대조이며 판정에 쓰지 않음
"""
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path('/mnt/share/행정데이터_set/로컬LLM_준비')
RD = ROOT / '05_eval' / 'runs'
base, dev = sys.argv[1:3]
PY = '/mnt/share/행정데이터_set/.venv/bin/python'


def read_jsonl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding='utf-8').splitlines() if l.strip()]


T = read_jsonl(RD / dev / 'transcripts.jsonl')
pre = []
for t in T:
    turns = []
    for tr in t['turns']:
        rv = tr.get('review')
        if rv and rv.get('flag'):
            tr = dict(tr, steps=tr['steps'][:rv.get('n_steps', len(tr['steps']))], final=rv.get('before', tr['final']))
        turns.append(tr)
    pre.append({'id': t['id'], 'turns': turns})
(RD / f'{dev}_prerev').mkdir(exist_ok=True)
(RD / f'{dev}_prerev' / 'transcripts.jsonl').write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in pre), encoding='utf-8')
subprocess.run([PY, str(ROOT / '05_eval/independent/score_outcome.py'), dev, f'{dev}_prerev'], check=True, stdout=subprocess.DEVNULL, env=os.environ)


def classes(run):
    sc = json.loads((RD / run / 'indep_score.json').read_text(encoding='utf-8'))
    return {(r['id'], t['turn']): (t['class'], r['stratum']) for r in sc['rows'] for t in r['turns']}, {r['id']: r for r in sc['rows']}


B, _ = classes(base); D, Drows = classes(dev); P, _ = classes(f'{dev}_prerev')
keys = [k for k in D if k in B]
tr = Counter((B[k][0], D[k][0]) for k in keys)
print(f'산출 차례 {len(keys)}개 · 기준 실행 정답 {sum(B[k][0] == "correct" for k in keys)} → 개발 실행 정답 {sum(D[k][0] == "correct" for k in keys)}')
print('판정 변화(기준 → 개발):', {f'{a}→{b}': n for (a, b), n in sorted(tr.items(), key=lambda x: -x[1])})
print('정답 → 정답 아님:', [f'{k[0]}#{k[1]}({D[k][0]})' for k in keys if B[k][0] == 'correct' and D[k][0] != 'correct'])
print('오답 유지:', [f'{k[0]}#{k[1]}' for k in keys if B[k][0] == 'wrong' and D[k][0] == 'wrong'])
print('새 오답(값 없음·실행 없음 → 오답):', [f'{k[0]}#{k[1]}' for k in keys if B[k][0] not in ('correct', 'wrong') and D[k][0] == 'wrong'])
hk = {'ask_gate': [], 'review': [], 'review_flag': []}
for t in T:
    for i, x in enumerate(t['turns'], 1):
        h = x.get('hooks') or {}
        if h.get('ask_gate'):
            hk['ask_gate'].append((t['id'], i))
        if x.get('review') is not None:
            hk['review'].append((t['id'], i))
            if x['review'].get('flag'):
                hk['review_flag'].append((t['id'], i))
print(f"되묻기 전 점검 작동 {len(hk['ask_gate'])}차례:", [f'{k[0]}#{k[1]}: {B.get(k, ("-",))[0]}→{D.get(k, ("판정 묶음",))[0]}' for k in hk['ask_gate']])
print(f"검토 수행 {len(hk['review'])}차례, 불일치 판정 {len(hk['review_flag'])}차례:", [f'{k[0]}#{k[1]}: 검토 전 {P.get(k, ("-",))[0]}→검토 뒤 {D.get(k, ("판정 묶음",))[0]}' for k in hk['review_flag']])
rc = Counter((P[k][0], D[k][0]) for k in hk['review_flag'] if k in P and k in D)
print('검토 전후:', {f'{a}→{b}': n for (a, b), n in rc.items()})
nf = [k for k in hk['review'] if k not in hk['review_flag'] and k in D]
print('검토가 일치로 본 차례의 판정:', dict(Counter(D[k][0] for k in nf)))
