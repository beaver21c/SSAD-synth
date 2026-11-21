#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""6차 검산자 입력(문서·요청·항목 문구와 유형만. 산출 정의·주장의 참거짓·판정 기준은 넣지 않음)과 기준값·전제 재대조 목록.
  python 05_eval/independent/r6/work/make_check_inputs.py
산출  r6/truth/check_input_1.jsonl(W1·W3), check_input_2.jsonl(W2·W4), r6/truth/used_numbers.jsonl"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
items = [json.loads(l) for l in (BASE / 'items' / 'all.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
(BASE / 'truth').mkdir(exist_ok=True)
for n, authors in ((1, ('W1', 'W3')), (2, ('W2', 'W4'))):
    rows = []
    for b in items:
        if b['author'] in authors and not b.get('variant_of'):
            comp = {(s['item']) for s in b['specs']}
            rows.append({'id': b['id'], 'issue': b['issue'], 'facts': b['facts'], 'document': b['context'].replace('■ 붙임 문서\n', ''), 'turns': b['turns'],
                         'items': [{'no': m['no'], 'turn': m['turn'], 'kind': m['kind'], 'text': m.get('text', ''), 'compute': m['no'] in comp} for m in b['items']]})
    (BASE / 'truth' / f'check_input_{n}.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n', encoding='utf-8')
    print(n, len(rows), '문서', sum(i['compute'] for r in rows for i in r['items']), '계산 항목')
used = []
for b in items:
    for m in b['items']:
        if m['kind'] in 'GPX' or (m['kind'] == 'F'):
            used.append({'case': b['id'], 'item': m['no'], 'kind': m['kind'], 'facts': b['facts'], 'q': m.get('text', ''), 'document': b['context'][:3000],
                         'param': m.get('param'), 'premise': m.get('premise')})
(BASE / 'truth' / 'used_numbers.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in used if r['kind'] != 'F') + '\n', encoding='utf-8')
print('기준값·전제 항목', sum(1 for r in used if r['kind'] != 'F'))
