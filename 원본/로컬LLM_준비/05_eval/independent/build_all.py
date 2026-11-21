#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""독립 검증 문항 묶기 — 작성자별 파일(items/A.jsonl …)을 점검해 실행용 한 파일(items/all.jsonl)로 묶는다.

  python 05_eval/independent/build_all.py
- 형식 점검: id 중복, turns, expect, 산출 문항의 specs
- 제외: truth/excluded.json 에 적힌 문항(이중 입력 대조에서 참값을 정할 수 없던 문항. 사유와 함께 기록)
- 추가 해석: truth/added_alts.json 에 적힌 산출 정의(이중 입력 대조에서 질문이 두 가지로 읽힌 문항)를 specs 에 더함
- A 묶음의 변수 구분: 분자·대상 변수에 기존 자료(학습 자료·평가 문항·프롬프트)에 나오지 않은 변수가 있으면 'P' → truth/item_vars.json
산출  items/all.jsonl, truth/item_vars.json, items/구성.json(묶음별 문항 수)
"""
import json
import os
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = Path(os.environ.get('INDEP_DIR') or HERE)
ORDER = 'ABCFGHDE'


def read_jsonl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding='utf-8').splitlines() if l.strip()]


def jload(p, default):
    p = Path(p)
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default


def main():
    excluded = jload(BASE / 'truth' / 'excluded.json', {})
    added = jload(BASE / 'truth' / 'added_alts.json', {})
    unseen = set(jload(HERE / 'truth' / 'seen_vars.json', {'unseen': []})['unseen'])
    items, problems, ivars = [], [], {}
    for st in ORDER:
        f = BASE / 'items' / f'{st}.jsonl'
        if not f.exists():
            problems.append(f'{st}.jsonl 없음'); continue
        for b in read_jsonl(f):
            b.setdefault('stratum', st)
            if b['id'] in excluded:
                continue
            if not b.get('turns') or not all(isinstance(q, str) and q.strip() for q in b['turns']):
                problems.append(f"{b['id']}: turns 형식"); continue
            if b.get('expect') not in ('compute', 'ask_or_assume', 'infeasible', 'refuse', 'safe_compute'):
                problems.append(f"{b['id']}: expect {b.get('expect')}"); continue
            if b['expect'] in ('compute', 'safe_compute') and not b.get('specs'):
                problems.append(f"{b['id']}: 산출 정의 없음"); continue
            for s in added.get(b['id'], []):
                b['specs'].append(s)
            if st == 'A':
                text = ' '.join(str(s.get('numerator', '')) + ' ' + str(s.get('value_var', '')) for s in b['specs'])
                names = set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', text))
                ivars[b['id']] = 'P' if names & unseen else ''
            items.append(b)
    ids = Counter(b['id'] for b in items)
    problems += [f'id 중복: {i}' for i, n in ids.items() if n > 1]
    (BASE / 'items' / 'all.jsonl').write_text(''.join(json.dumps(b, ensure_ascii=False) + '\n' for b in items), encoding='utf-8')
    (BASE / 'truth' / 'item_vars.json').write_text(json.dumps(ivars, ensure_ascii=False, indent=1), encoding='utf-8')
    comp = {'n': len(items), 'by_stratum': dict(Counter(b['stratum'] for b in items)), 'by_expect': dict(Counter(b['expect'] for b in items)),
            'turns': sum(len(b['turns']) for b in items), 'excluded': excluded, 'added_alts': {k: len(v) for k, v in added.items()},
            'A_unseen_var': sum(v == 'P' for v in ivars.values()), 'problems': problems}
    (BASE / 'items' / '구성.json').write_text(json.dumps(comp, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: v for k, v in comp.items() if k != 'excluded'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
