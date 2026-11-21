#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""5차(과제형)의 이중 입력 대조 — 작성자의 산출 정의로 계산한 참값(truth/truth.json)과, 요청 문장만 본 검산자가 따로 계산한 값(truth/check_*.jsonl)을 차례·요청별로 대조한다.

  INDEP_DIR=05_eval/independent/r5 python 05_eval/independent/compare_check_cases.py
검산자 파일의 한 줄  {"id": "W1-01", "turn": 1, "part": 1, "reading": "…", "pct": true|false, "cells": [{"labels": [...], "value": 값, "n": 관측 수}], "ambiguous": false, "note": ""}
                     한 차례·요청에 해석이 여럿이면 줄을 나누고 "reading_no" 를 달리함
                     산출이 아닌 차례의 점검  {"id": …, "turn": 3, "check": "ok|issue", "note": "자료에 없음 확인 / 전제와 사실 대조 결과"}
일치의 기준  검산자의 칸 값이 작성자의 그 차례 어느 요청·해석의 칸 값과 모두 대응함(비율 0.11%p, 그 밖 상대 1%). 요청(part) 번호는 달라도 됨
산출  truth/double_entry.json
"""
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = Path(os.environ.get('INDEP_DIR') or HERE / 'r5')
import sys
sys.path.insert(0, str(HERE))
from compare_check import same  # noqa: E402 — 칸 값의 대응 규칙은 1~4차와 같은 것을 씀


def main():
    truth = json.loads((BASE / 'truth' / 'truth.json').read_text(encoding='utf-8'))
    items = [json.loads(l) for l in (BASE / 'items' / 'all.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    checks, notes = {}, []
    for f in sorted((BASE / 'truth').glob('check_[0-9]*.jsonl')):
        for line in f.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if 'cells' in r:
                checks.setdefault((r['id'], r['turn']), []).append(r)
            else:
                notes.append({**r, 'file': f.name})
    rows = []
    for b in items:
        specs = truth.get(b['id']) or []
        for k in sorted({s['turn'] for s in specs}):
            alts = [s for s in specs if s['turn'] == k]
            parts = sorted({(s.get('spec') or {}).get('part', 1) for s in alts})
            cs = checks.get((b['id'], k), [])
            row = {'id': b['id'], 'turn': k, 'kind': b['kinds'][k - 1], 'parts': len(parts), 'n_check': len(cs), 'ambiguous': any(c.get('ambiguous') for c in cs)}
            if not cs:
                row.update(agree=None, status='not_checked')
            else:
                # 작성자의 요청(part)마다 검산자의 어느 계산과 맞는지, 검산자의 계산마다 작성자의 어느 해석과 맞는지
                part_ok = {p: any(same(c, a) for c in cs for a in alts if (a.get('spec') or {}).get('part', 1) == p) for p in parts}
                check_ok = [any(same(c, a) for a in alts) for c in cs]
                row.update(agree=all(part_ok.values()), part_agree=part_ok, check_matched=sum(check_ok), check_unmatched=[c.get('reading', '')[:200] for c, ok in zip(cs, check_ok) if not ok],
                           status='agree' if all(part_ok.values()) and all(check_ok) else 'author_only_extra_reading' if all(part_ok.values()) else 'disagree', notes=[c.get('note') for c in cs if c.get('note')])
            rows.append(row)
    out = {'n': len(rows), 'agree': sum(1 for r in rows if r['status'] == 'agree'), 'extra_reading': [f"{r['id']}#{r['turn']}" for r in rows if r['status'] == 'author_only_extra_reading'],
           'disagree': [f"{r['id']}#{r['turn']}" for r in rows if r['status'] == 'disagree'], 'not_checked': [f"{r['id']}#{r['turn']}" for r in rows if r['status'] == 'not_checked'],
           'flag_ambiguous': [f"{r['id']}#{r['turn']}" for r in rows if r['ambiguous']], 'non_compute_issues': [n for n in notes if n.get('check') == 'issue'], 'non_compute_checked': len(notes), 'rows': rows}
    (BASE / 'truth' / 'double_entry.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print({k: (v if not isinstance(v, list) else v) for k, v in out.items() if k != 'rows'})


if __name__ == '__main__':
    main()
