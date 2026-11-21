#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""5차(제도·현안 과제형) 과제 묶기 — 작성자별 과제 파일을 점검하고 평가 실행용 문항 파일과 참값 계산용 파일로 만든다.

  INDEP_DIR=05_eval/independent/r5 python 05_eval/independent/build_cases.py
입력  <차수 폴더>/work/W*/cases.jsonl          작성자별 과제(양식은 r5/inputs/과제_양식.md)
      <차수 폴더>/work/fixes.json (선택)        이중 입력·사실 대조 뒤의 정정: {"drop_cases": [...], "drop_turns": {"과제 id": [차례…]}, "add_specs": {"과제 id": [정의…]}, "set": {"과제 id": {"차례": {항목: 값}}}}
출력  <차수 폴더>/items/P.jsonl, items/all.jsonl  과제 1개 = 한 줄(turns 는 질문 문장의 목록, specs 는 차례 번호를 붙여 편 것)
      <차수 폴더>/items/구성.json                 유형·표현·영역별 수와 점검 결과
참값은 이 파일을 만든 뒤 truth_engine.py 로 계산한다. 산출 정의가 있는 차례를 뺀 경우(drop_turns)에는 그 차례를 평가에서 제외한다(대화에는 남김: 뒤 차례의 맥락이므로).
"""
import collections
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = Path(os.environ.get('INDEP_DIR') or HERE / 'r5')
KINDS = set('SGPNVTXCI')


def main():
    fixes = json.loads((BASE / 'work' / 'fixes.json').read_text(encoding='utf-8')) if (BASE / 'work' / 'fixes.json').exists() else {}
    cases, errors = [], []
    for f in sorted((BASE / 'work').glob('W*/cases.jsonl')):
        for ln, line in enumerate(f.read_text(encoding='utf-8').splitlines(), 1):
            if not line.strip():
                continue
            try:
                c = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f'{f.parent.name}:{ln} JSON 오류 {e}'); continue
            c['author'] = f.parent.name
            cases.append(c)
    out = []
    for c in cases:
        cid = c.get('id')
        if cid in (fixes.get('drop_cases') or []):
            continue
        ts = c.get('turns') or []
        if len(ts) != 4:
            errors.append(f'{cid}: 차례 {len(ts)}개')
        drop = set((fixes.get('drop_turns') or {}).get(cid, []))
        specs, kinds, regs, rub = [], [], [], {}
        for k, t in enumerate(ts, 1):
            t = {**t, **((fixes.get('set') or {}).get(cid, {}).get(str(k), {}))}
            kind = t.get('kind')
            if kind not in KINDS:
                errors.append(f'{cid} 차례 {k}: kind {kind}')
            kinds.append(kind); regs.append(t.get('register'))
            if k in drop:
                kinds[-1] = 'D'                      # 제외한 차례(대화에는 남김)
                continue
            if kind in 'SGP' and not t.get('specs'):
                errors.append(f'{cid} 차례 {k}: {kind} 인데 산출 정의 없음')
            for s in t.get('specs') or []:
                specs.append({**s, 'turn': k, 'part': s.get('part', 1), 'alt': s.get('alt', 1)})
            rub[str(k)] = {x: t[x] for x in ('rubric', 'absent', 'premise', 'param', 'note') if t.get(x)}
        specs += [{**s, 'part': s.get('part', 1), 'alt': s.get('alt', 1)} for s in (fixes.get('add_specs') or {}).get(cid, [])]
        out.append({'id': cid, 'stratum': 'P', 'author': c['author'], 'domain': c.get('domain'), 'issue': c.get('issue'), 'facts': c.get('facts') or [], 'persona': c.get('persona'), 'setting': c.get('setting'),
                    'turns': [t['q'] for t in ts], 'kinds': kinds, 'registers': regs, 'expect': 'compute', 'specs': specs, 'rubrics': rub, 'relations': c.get('relations') or []})
    ids = [c['id'] for c in out]
    for i in {i for i in ids if ids.count(i) > 1}:
        errors.append(f'과제 id 중복: {i}')
    (BASE / 'items').mkdir(exist_ok=True)
    text = '\n'.join(json.dumps(c, ensure_ascii=False) for c in out) + '\n'
    (BASE / 'items' / 'P.jsonl').write_text(text, encoding='utf-8'); (BASE / 'items' / 'all.jsonl').write_text(text, encoding='utf-8')
    kc = collections.Counter(k for c in out for k in c['kinds'])
    rc = collections.Counter(r for c in out for k, r in zip(c['kinds'], c['registers']) if k in 'SGPX')
    comp = {'cases': len(out), 'turns': sum(len(c['turns']) for c in out), 'kinds': dict(kc), 'registers': dict(rc), 'by_author': dict(collections.Counter(c['author'] for c in out)),
            'by_author_kind': {a: dict(collections.Counter(k for c in out if c['author'] == a for k in c['kinds'])) for a in sorted({c['author'] for c in out})},
            'specs': sum(len(c['specs']) for c in out), 'relations': sum(len(c['relations']) for c in out), 'errors': errors}
    (BASE / 'items' / '구성.json').write_text(json.dumps(comp, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(comp, ensure_ascii=False, indent=1))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
