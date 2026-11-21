#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""전체·구성 변수 관계 — 변수 사전에서 「전체」 변수와 그 유형별(구성) 변수의 관계를 뽑아 분석 함수 묶음이 읽는 파일로 만든다.

  python 01_knowledge/build_relations.py            # 02_library/ssda/data/relations.json, 01_knowledge/relations.json
관계의 정의(둘 다 충족)
  ① 전체 변수의 한글 이름에 「전체」가 있음
  ② 구성 변수의 변수명에서 가운데 토막 하나를 빼면 전체 변수의 변수명이 되고, 한글 이름의 끝말(내원일수·재원일수·요양급여비용 총액·본인부담금·공단부담금 등)이 같음
  ③ 구성 변수의 한글 이름이 전체 변수의 이름에서 「전체 … 의료기관」 자리를 유형 이름 한 낱말로 바꾼 꼴임(낱말 수가 하나 적음)
  ②만 맞고 ③이 맞지 않는 변수(예: 응급실 재원일수)는 전체에 더하지 않는 별도 항목(not_parts)으로 적는다. 가상데이터에서 유형별 변수 4개의 합은 전체와 같고, 응급실 변수를 더하면 달라진다.
이름 규칙만 쓰면(①을 빼면) 전체·구성 관계가 아닌 묶음(가입 여부 변수 등)이 섞이므로 ①을 함께 둔다(2026-11-18 독립 검증 4차 검토).
분석 자료가 있으면(SSDA_DATA) 전체 변수의 값과 구성 변수의 합이 같은 사람의 비율을 함께 적는다(값이 있는 구성 변수만으로는 합이 전체보다 작을 수 있음).
"""
import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = HERE.parent / '02_library' / 'ssda' / 'data'


def main():
    meta = {}
    for line in (HERE / 'variables.jsonl').read_text(encoding='utf-8').splitlines():
        if line.strip():
            r = json.loads(line); meta[r['var']] = r
    tail = lambda v: re.sub(r'^\(.*?\)\s*', '', meta[v]['name_ko']).split(' ')[-1]
    totals = []
    for t, m in meta.items():
        if '전체' not in (m.get('name_ko') or '') or not m.get('available', True):
            continue
        tp = t.split('_')
        parts, others = [], []
        nwords = lambda v: len(re.sub(r'^\(.*?\)\s*', '', meta[v]['name_ko']).split(' '))
        for v, x in meta.items():
            vp = v.split('_')
            if len(vp) == len(tp) + 1 and x.get('available', True) and any(vp[:i] + vp[i + 1:] == tp for i in range(1, len(vp) - 1)) and tail(v) == tail(t) and '전체' not in x['name_ko']:
                (parts if nwords(v) == nwords(t) - 1 else others).append(v)
        if len(parts) >= 2:
            head = re.sub(r'^\(.*?\)\s*', '', m['name_ko'])
            words = []
            for v in parts:                               # 구성 변수를 가리키는 낱말(전체 변수의 이름에 없는 낱말)
                for w in re.sub(r'^\(.*?\)\s*', '', meta[v]['name_ko']).split(' '):
                    if w not in head.split(' ') and len(w) >= 2 and w not in words and not re.fullmatch(r'연간|방문한', w):
                        words.append(w)
            totals.append({'total': t, 'name_ko': m['name_ko'], 'parts': parts, 'part_words': words, 'not_parts': others})
    data = os.environ.get('SSDA_DATA')
    if data and Path(data).exists():
        import numpy as np
        import pandas as pd
        cols = sorted({c for r in totals for c in [r['total']] + r['parts']})
        d = pd.read_parquet(data, columns=cols)
        for r in totals:
            tv = d[r['total']].astype(float); s = d[r['parts']].astype(float).sum(axis=1, min_count=1)
            has = tv.notna()
            r['check'] = {'n_total': int(has.sum()), 'equal_pct': round(100 * float(np.isclose(tv[has], s[has].fillna(0)).mean()), 1) if has.any() else None,
                          'parts_sum_over_total_pct': round(100 * float(s[has].fillna(0).sum() / max(tv[has].sum(), 1e-9)), 1) if has.any() else None}
    out = {'rule': '한글 이름에 「전체」가 있는 변수와, 변수명에서 가운데 토막 하나를 뺀 것이 그 변수명과 같고 이름의 끝말이 같은 변수', 'totals': totals}
    for p in (HERE / 'relations.json', LIB / 'relations.json'):
        p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'전체·구성 관계 {len(totals)}묶음')
    for r in totals:
        print(' ', r['total'], '←', ', '.join(r['parts']), '| 낱말', r['part_words'], '|', r.get('check'))


if __name__ == '__main__':
    main()
