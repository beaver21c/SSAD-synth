#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""규칙 묶음 12h ③ — 제도 기준값 카드 보강(공식 출처에서 새로 수집한 줄을 01_knowledge/programs/facts_2021_2022.jsonl 에 더함).

원인(12f·12g 개발 점검의 판정 기록): 기준값 카드에 없는 제도 사실을 모형이 기억으로 적거나 문서의 틀린 전제를 받아 적음
  - 6차 W4-D08#4 청년월세 한시 특별지원의 소득 기준(원가구 기준을 청년가구 기준으로 적용)
  - 6차 W3-D07#3·#4 산재보험 전속성 요건 폐지 시점(2023년 7월 시행을 2022년으로 적음)
  - 6차 W2-D05#4 의료급여 2종 입원 본인부담률(문서의 20%를 맞다고 확인)
  - 6차 W4-D04v#4 3+3 부모육아휴직제의 달별 상한(셋째 달 300만원만 카드에 있었음)
  - 6차 W3-D01v#4 조기취업성공수당 자리에 취업성공수당(별개 수당)을 냄
  - 6차 W4-D03#2 영아수당 대상 출생일
수집 원칙: 국가법령정보센터·정부 부처·정책브리핑·공공기관 공식 누리집에서 쪽을 열어 확인한 값만, 인용문과 함께 적음(평가 자료는 보지 않음)

  python3 facts_v12h.py <루트> <새 줄 JSONL>
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
NEW = Path(sys.argv[2])
F = ROOT / '01_knowledge' / 'programs' / 'facts_2021_2022.jsonl'
G = {e['id'] for e in json.loads((ROOT / '01_knowledge' / 'programs' / 'glossary.json').read_text(encoding='utf-8'))}
KEYS = ('glossary_id', 'program', 'item', 'value', 'unit', 'applies', 'effective_from', 'source_title', 'source_url', 'quote', 'note')
OFFICIAL = re.compile(r'https?://(?:[\w-]+\.)*(?:go\.kr|korea\.kr|or\.kr|law\.go\.kr|bokjiro\.go\.kr|work24\.go\.kr|comwel\.or\.kr|nid\.or\.kr|nhis\.or\.kr|hira\.or\.kr|nps\.or\.kr)(?:/|$)')

old = [json.loads(l) for l in F.read_text(encoding='utf-8').splitlines() if l.strip()]
have = {(r['glossary_id'], r['item'], r.get('applies')) for r in old}
add, skip = [], []
for l in NEW.read_text(encoding='utf-8').splitlines():
    if not l.strip():
        continue
    r = json.loads(l)
    why = ''
    if r.get('glossary_id') not in G:
        why = '용어 사전에 없는 id'
    elif not r.get('item') or r.get('value') in (None, ''):
        why = '항목·값 없음'
    elif not re.fullmatch(r'20\d\d-\d\d~20\d\d-\d\d', r.get('applies') or ''):
        why = '적용 기간 형식'
    elif not OFFICIAL.match(r.get('source_url') or ''):
        why = '공식 출처 아님'
    elif not (r.get('quote') or '').strip():
        why = '인용문 없음'
    elif (r['glossary_id'], r['item'], r.get('applies')) in have:
        why = '이미 있음'
    if why:
        skip.append((r.get('item'), why))
        continue
    r = {k: r.get(k, '') for k in KEYS}
    have.add((r['glossary_id'], r['item'], r['applies']))
    add.append(r)
if add:
    with F.open('a', encoding='utf-8') as f:
        for r in add:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
print(f'더한 줄 {len(add)}, 뺀 줄 {len(skip)} → 전체 {len(old) + len(add)}줄')
for it, why in skip:
    print('  뺌:', it, '—', why)
