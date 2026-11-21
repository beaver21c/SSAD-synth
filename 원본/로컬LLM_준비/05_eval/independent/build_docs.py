#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""6차(문서형 요청) 과제 묶기 — 작성자별 문서 파일을 점검하고 평가 실행용 문항 파일과 참값 계산용 정의로 만든다.

  INDEP_DIR=05_eval/independent/r6 python 05_eval/independent/build_docs.py
입력  <차수 폴더>/work/W*/docs.jsonl     작성자별 문서(양식은 r6/inputs/문서_양식.md)
      <차수 폴더>/work/fixes.json (선택)  이중 입력·사실 대조 뒤의 정정 {"drop_docs": [...], "drop_items": {"문서 id": [항목 번호…]}, "add_specs": {"문서 id": [정의(item 포함)…]}}
출력  <차수 폴더>/items/P.jsonl, items/all.jsonl  문서 1개 = 한 줄. turns 는 요청 문장의 목록, context 는 붙임 문서(1차례에 참고 자료로 전달),
      specs 는 항목·하위 요청 번호를 붙여 편 것(item, sub, part = 항목×10 + 하위 요청, turn)
      <차수 폴더>/items/구성.json
"""
import collections
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = Path(os.environ.get('INDEP_DIR') or HERE / 'r6')
KINDS = set('SFGPNVXCI')


def main():
    fixes = json.loads((BASE / 'work' / 'fixes.json').read_text(encoding='utf-8')) if (BASE / 'work' / 'fixes.json').exists() else {}
    docs, errors = [], []
    for f in sorted((BASE / 'work').glob('W*/docs.jsonl')):
        for ln, line in enumerate(f.read_text(encoding='utf-8').splitlines(), 1):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f'{f.parent.name}:{ln} JSON 오류 {e}'); continue
            d['author'] = f.parent.name
            docs.append(d)
    byid = {d.get('id'): d for d in docs}
    out = []
    for d in docs:
        did = d.get('id')
        if did in (fixes.get('drop_docs') or []):
            continue
        turns = d.get('turns') or []
        items = d.get('items') or []
        if len(turns) != 2:
            errors.append(f'{did}: 차례 {len(turns)}개')
        if len(items) != 5:
            errors.append(f'{did}: 항목 {len(items)}개')
        drop = set((fixes.get('drop_items') or {}).get(did, []))
        specs, meta = [], []
        for it in items:
            no, kind = it.get('no'), it.get('kind')
            if kind not in KINDS:
                errors.append(f'{did} 항목 {no}: kind {kind}')
            turn = it.get('turn') or next((t['n'] for t in turns if no in (t.get('items') or [])), None)
            if turn is None:
                errors.append(f'{did} 항목 {no}: 차례 없음')
            m = {'no': no, 'turn': turn, 'kind': 'D' if no in drop else kind, 'register': it.get('register'), 'text': it.get('text', ''),
                 **{x: it[x] for x in ('rubric', 'absent', 'premise', 'param', 'claim', 'note') if it.get(x) is not None}}
            meta.append(m)
            if no in drop:
                continue
            if kind in 'SFGP' and not it.get('specs'):
                errors.append(f'{did} 항목 {no}: {kind} 인데 산출 정의 없음')
            if kind == 'F' and not isinstance(it.get('claim'), dict):
                errors.append(f'{did} 항목 {no}: F 인데 claim 없음')
            for s in it.get('specs') or []:
                sub = s.get('sub', 1)
                specs.append({**s, 'item': no, 'sub': sub, 'part': no * 10 + sub, 'alt': s.get('alt', 1), 'turn': turn})
        specs += [{**s, 'part': s['item'] * 10 + s.get('sub', 1), 'alt': s.get('alt', 1)} for s in (fixes.get('add_specs') or {}).get(did, [])]
        var = d.get('variant_of')
        if var and var not in byid:
            errors.append(f'{did}: 원판 {var} 없음')
        out.append({'id': did, 'stratum': 'P', 'author': d['author'], 'doc_type': d.get('doc_type'), 'issue': d.get('issue'), 'facts': d.get('facts') or [],
                    'persona': d.get('persona'), 'setting': d.get('setting'), 'variant_of': var,
                    'context': '■ 붙임 문서\n' + (d.get('document') or '').strip(), 'turns': [t['q'] for t in turns], 'turn_items': [t.get('items') or [] for t in turns],
                    'items': meta, 'expect': 'compute', 'specs': specs})
    ids = [d['id'] for d in out]
    for i in {i for i in ids if ids.count(i) > 1}:
        errors.append(f'id 중복: {i}')
    (BASE / 'items').mkdir(exist_ok=True)
    text = '\n'.join(json.dumps(d, ensure_ascii=False) for d in out) + '\n'
    (BASE / 'items' / 'P.jsonl').write_text(text, encoding='utf-8'); (BASE / 'items' / 'all.jsonl').write_text(text, encoding='utf-8')
    orig = [d for d in out if not d['variant_of']]
    kc = collections.Counter(m['kind'] for d in orig for m in d['items'])
    rc = collections.Counter(m['register'] for d in orig for m in d['items'] if m['kind'] in 'SFGPX')
    fc = collections.Counter(bool((m.get('claim') or {}).get('true')) for d in orig for m in d['items'] if m['kind'] == 'F')
    comp = {'docs': len(orig), 'variants': len(out) - len(orig), 'conversations': len(out), 'items': sum(len(d['items']) for d in orig),
            'items_with_variants': sum(len(d['items']) for d in out), 'kinds': dict(kc), 'registers': dict(rc), 'claims_true_false': {'맞는 주장': fc[True], '틀린 주장': fc[False]},
            'doc_types': dict(collections.Counter(d['doc_type'] for d in orig)), 'by_author': dict(collections.Counter(d['author'] for d in out)),
            'specs': sum(len(d['specs']) for d in out), 'context_chars_median': sorted(len(d['context']) for d in out)[len(out) // 2] if out else 0, 'errors': errors}
    (BASE / 'items' / '구성.json').write_text(json.dumps(comp, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(comp, ensure_ascii=False, indent=1))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
