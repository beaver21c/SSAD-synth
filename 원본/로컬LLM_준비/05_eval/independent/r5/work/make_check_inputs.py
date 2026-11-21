#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""검산자 입력(요청 문장과 유형만. 산출 정의·판정 기준은 넣지 않음)과 사실 재대조 목록을 만든다.
  python 05_eval/independent/r5/work/make_check_inputs.py
산출  r5/truth/check_input_1.jsonl(W1·W3), check_input_2.jsonl(W2·W4), r5/facts/used_numbers.jsonl(G·P·X 차례의 기준값·전제와 사실 id)"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
items = [json.loads(l) for l in (BASE / 'items' / 'all.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
(BASE / 'truth').mkdir(exist_ok=True)
for n, authors in ((1, ('W1', 'W3')), (2, ('W2', 'W4'))):
    rows = []
    for b in items:
        if b['author'] in authors:
            comp = {s['turn'] for s in b['specs']}
            rows.append({'id': b['id'], 'issue': b['issue'], 'facts': b['facts'], 'turns': [{'n': k, 'kind': kind, 'q': q, 'compute': k in comp} for k, (kind, q) in enumerate(zip(b['kinds'], b['turns']), 1)]})
    (BASE / 'truth' / f'check_input_{n}.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n', encoding='utf-8')
    print(n, len(rows), '과제', sum(t['compute'] for r in rows for t in r['turns']), '산출 차례')
used = []
for b in items:
    for k, kind in enumerate(b['kinds'], 1):
        rb = (b['rubrics'] or {}).get(str(k)) or {}
        if kind in 'GPX':
            used.append({'case': b['id'], 'turn': k, 'kind': kind, 'facts': b['facts'], 'q': b['turns'][k - 1], 'param': rb.get('param'), 'premise': rb.get('premise')})
(BASE / 'facts' / 'used_numbers.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in used) + '\n', encoding='utf-8')
print('기준값·전제 차례', len(used), '· 쓰인 사실 id', len({f for b in items for f in b['facts']}))
