#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""이중 입력 대조 — 작성자의 산출 정의로 계산한 참값(truth/truth.json)과, 질문 문장만 본 검산자가 따로 계산한 값(truth/check_*.jsonl)을 대조한다.

  python 05_eval/independent/compare_check.py
검산자 파일의 한 줄  {"id": "A001", "turn": 1, "reading": "대상·분자·분류를 어떻게 읽었는지", "pct": true|false, "cells": [{"labels": [...], "value": 값, "n": 관측 수}], "ambiguous": false, "note": ""}
일치의 기준  검산자의 칸 값(값이 있는 칸)이 작성자의 어느 한 해석(alt)의 칸 값과 모두 대응함(비율 0.11%p, 그 밖 상대 1%)
산출  truth/double_entry.json (문항·차례별 일치 여부와 불일치 내역)
"""
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = Path(os.environ.get('INDEP_DIR') or HERE)


def close(a, b, pct):
    if a is None or b is None:
        return False
    return abs(a - b) <= 0.11 if pct else abs(a - b) <= 0.01 * abs(b) + 1e-9


def same(check, alt):
    pct = alt['measure'] in ('rate', 'share', 'poverty_rate', 'ratio')
    tc = [c['value'] for c in alt['cells'] if c.get('value') is not None and c['n'] > 0]
    cc = [c['value'] for c in check['cells'] if c.get('value') is not None]
    if len(tc) != len(cc):                                  # 칸 수가 다르면 값이 있는 칸끼리의 대응만 확인(관측 0건 칸의 표기 차이 허용)
        if not cc or not tc:
            return False
    used = set()
    for v in cc:
        j = next((i for i, t in enumerate(tc) if i not in used and close(v, t, pct)), None)
        if j is None:
            return False
        used.add(j)
    return len(used) == len(tc)


def main():
    truth = json.loads((BASE / 'truth' / 'truth.json').read_text(encoding='utf-8'))
    checks = []
    for f in sorted((BASE / 'truth').glob('check_[0-9].jsonl')):
        checks += [json.loads(l) for l in f.read_text(encoding='utf-8').splitlines() if l.strip()]
    rows = []
    seen = set()
    grouped = {}
    for c in checks:
        grouped.setdefault((c['id'], c.get('turn', 1)), []).append(c)
    for (iid, turn), cs in sorted(grouped.items()):
        cs.sort(key=lambda c: c.get('reading_no', 1))
        alts = [a for a in truth.get(iid, []) if a['turn'] == turn]
        hits = [any(same(c, a) for a in alts) for c in cs]
        seen.add((iid, turn))
        row = {'id': iid, 'turn': turn, 'agree': any(hits), 'primary_agree': hits[0], 'n_readings': len(cs), 'ambiguous': any(c.get('ambiguous') for c in cs),
               'reading': cs[0].get('reading', ''), 'note': ' / '.join(c.get('note', '') for c in cs if c.get('note'))}
        if not all(hits):
            row['check_cells'] = [[(x.get('labels'), x.get('value'), x.get('n')) for x in c['cells']][:12] for c in cs]
            row['readings'] = [c.get('reading', '') for c in cs]
            row['truth_cells'] = [[(x['labels'], x['value'], x['n']) for x in a['cells']][:12] for a in alts]
            row['specs'] = [a['spec'] for a in alts]
        rows.append(row)
    missing = sorted({(i, a['turn']) for i, alts in truth.items() for a in alts} - seen)
    out = {'n': len(rows), 'agree': sum(r['agree'] for r in rows), 'disagree': [r for r in rows if not r['agree']], 'flag_ambiguous': [r['id'] for r in rows if r['ambiguous']],
           'not_checked': [f'{i}#{t}' for i, t in missing], 'rows': rows}
    (BASE / 'truth' / 'double_entry.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"이중 입력: 대조 {out['n']}건, 일치 {out['agree']}건, 불일치 {len(out['disagree'])}건, 검산자가 모호하다고 본 문항 {len(out['flag_ambiguous'])}개, 검산 누락 {len(missing)}건")
    for r in out['disagree']:
        print(f"  {r['id']}#{r['turn']} | 검산자 해석: {r['reading'][:170]} | 검산 {str(r['check_cells'])[:230]} | 작성자 {str(r['truth_cells'])[:230]}")
    extra = [r for r in rows if r['agree'] and r['n_readings'] > 1]
    print(f"검산자가 다른 해석을 함께 낸 문항(일치) {len(extra)}개: {[r['id'] for r in extra]}")


if __name__ == '__main__':
    main()
