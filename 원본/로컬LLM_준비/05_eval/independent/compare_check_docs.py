#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""6차(문서형)의 이중 입력 대조 — 작성자의 산출 정의로 계산한 참값(truth/truth.json)과, 문서·요청만 본 검산자의 계산(truth/check_*.jsonl)을 항목·하위 요청별로 대조한다.

  INDEP_DIR=05_eval/independent/r6 python 05_eval/independent/compare_check_docs.py
검산자 파일의 한 줄  {"id": "W1-D01", "item": 2, "sub": 1, "reading_no": 1, "reading": "…", "pct": true, "cells": [{"labels": [...], "value": 값, "n": 관측 수}], "ambiguous": false, "note": ""}
                     산출이 아닌 항목·F 주장의 점검 {"id": …, "item": 3, "check": "ok|issue", "claim_true": true|false|null, "note": "…"}
일치의 기준  검산자의 칸 값이 작성자의 그 항목 어느 하위 요청·해석의 칸 값과 모두 대응함(compare_check.same)
산출  truth/double_entry.json
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = Path(os.environ.get('INDEP_DIR') or HERE / 'r6')
sys.path.insert(0, str(HERE))
from compare_check import same as _same  # noqa: E402
import re  # noqa: E402

TOTAL = re.compile(r'(^|\s)(계|합계|전체|총계)$|\s계$')


def same(check, alt):
    """검산자가 표에 덧붙인 합계 칸(「계」「전체」)은 작성자의 정의에 없으면 빼고 대조함(6차 이중 입력: 칸별 값은 같고 합계 칸만 더한 경우가 많았음)."""
    alabs = {' '.join(map(str, c.get('labels') or [])) for c in alt.get('cells') or []}
    cells = [c for c in check.get('cells') or [] if not (TOTAL.search(' '.join(map(str, c.get('labels') or []))) and ' '.join(map(str, c.get('labels') or [])) not in alabs)]
    if cells and len(cells) < len(check.get('cells') or []):
        if _same({**check, 'cells': cells}, alt):
            return True
    return _same(check, alt)


def main():
    truth = json.loads((BASE / 'truth' / 'truth.json').read_text(encoding='utf-8'))
    items = [json.loads(l) for l in (BASE / 'items' / 'all.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    checks, notes = {}, {}
    for f in sorted((BASE / 'truth').glob('check_[0-9]*.jsonl')):
        for line in f.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if 'cells' in r:
                checks.setdefault((r['id'], r['item']), []).append(r)
            else:
                notes.setdefault((r['id'], r['item']), []).append({**r, 'file': f.name})
    rows, claim_rows = [], []
    for b in items:
        specs = truth.get(b['id']) or []
        for m in b['items']:
            alts = [s for s in specs if (s.get('spec') or {}).get('item') == m['no']]
            if m['kind'] == 'F':
                ns = notes.get((b['id'], m['no']), [])
                ct = [n.get('claim_true') for n in ns if n.get('claim_true') is not None]
                claim_rows.append({'id': b['id'], 'item': m['no'], 'author_true': (m.get('claim') or {}).get('true'), 'checker_true': ct, 'agree': bool(ct) and all(x == (m.get('claim') or {}).get('true') for x in ct)})
            if not alts:
                continue
            subs = sorted({(s.get('spec') or {}).get('sub', 1) for s in alts})
            cs = checks.get((b['id'], m['no']), [])
            row = {'id': b['id'], 'item': m['no'], 'kind': m['kind'], 'subs': len(subs), 'n_check': len(cs), 'ambiguous': any(c.get('ambiguous') for c in cs)}
            if not cs:
                row.update(status='not_checked')
            else:
                sub_ok = {u: any(same(c, a) for c in cs for a in alts if (a.get('spec') or {}).get('sub', 1) == u) for u in subs}
                ck_ok = [any(same(c, a) for a in alts) for c in cs]
                row.update(sub_agree=sub_ok, status='agree' if all(sub_ok.values()) and all(ck_ok) else 'author_only_extra_reading' if all(sub_ok.values()) else 'disagree',
                           check_unmatched=[c.get('reading', '')[:200] for c, ok in zip(cs, ck_ok) if not ok])
            rows.append(row)
    issues = [n for v in notes.values() for n in v if n.get('check') == 'issue']
    out = {'n': len(rows), 'agree': sum(r['status'] == 'agree' for r in rows), 'extra_reading': [f"{r['id']}#{r['item']}" for r in rows if r['status'] == 'author_only_extra_reading'],
           'disagree': [f"{r['id']}#{r['item']}" for r in rows if r['status'] == 'disagree'], 'not_checked': [f"{r['id']}#{r['item']}" for r in rows if r['status'] == 'not_checked'],
           'flag_ambiguous': [f"{r['id']}#{r['item']}" for r in rows if r['ambiguous']], 'claims': {'n': len(claim_rows), 'agree': sum(c['agree'] for c in claim_rows), 'disagree': [c for c in claim_rows if not c['agree']]},
           'issues': issues, 'rows': rows}
    (BASE / 'truth' / 'double_entry.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print({k: v for k, v in out.items() if k not in ('rows',)})


if __name__ == '__main__':
    main()
