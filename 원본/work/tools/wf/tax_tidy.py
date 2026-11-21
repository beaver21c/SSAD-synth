# -*- coding: utf-8 -*-
"""params/raw/NTS_*.json (TASIS 원본 응답) -> tidy long CSV.
행 계층 = dc_result.rows2 순서(외곽->내부), 열 계층 = dc_result.cols 순서(외곽->내부).
ROW_SECTION은 ROW2 블록 라벨이 표 안에서 비연속 반복되어 계층이 모호한 표에만 추가한다
(본 배치에서는 4-2-3 뿐: 남성/여성이 '결정세액이 있는자'와 '없는자' 아래 각각 반복).
복원 결과는 가산성(소계 = 하위 합)으로 검증했다.
"""
import json, glob, os, re, csv
from collections import Counter

RAW = '/mnt/share/행정데이터_set/work/params/raw'
ENT = re.compile(r'(&emsp;|&nbsp;)+')
clean = lambda s: ENT.sub('', str(s)).strip() if s is not None else ''

def build(fp):
    d = json.load(open(fp, encoding='utf-8'))
    res, L = d['dc_result'], d['dc_annRptList']
    rowk = [k for k in str(res.get('rows2','')).split(',') if k]
    colk = [k for k in str(res.get('cols','')).split(',') if k]
    unit = clean(res.get('STT_UNIT_NM'))
    title = res.get('sttsSbj') or ''
    stt_no = title.split('.')[0] if '.' in title else ''

    first = {}
    for r in L:
        o = int(r['ROW9'])
        if o not in first: first[o] = r
    order = sorted(first)
    depth = {o: (first[o].get('ROW8') or '').count('&emsp;')//2 for o in order}
    outer = rowk[0]                      # 최외곽 행 차원 (ROW3 또는 ROW2)

    # 최외곽 라벨 블록의 비연속 반복 여부
    seq, blocks = [first[o].get(outer) for o in order], []
    prev = object()
    for v in seq:
        if v != prev: blocks.append(v); prev = v
    ambiguous = [k for k, c in Counter(blocks).items() if c > 1]

    section = {o: '' for o in order}
    if ambiguous:
        cur = ''
        i = 0
        while i < len(order):
            o = order[i]
            nx = order[i+1] if i+1 < len(order) else None
            if depth[o] == 0 and nx is not None and depth[nx] == 0:
                cur = clean(first[o].get('ROW8')); section[o] = ''; i += 1; continue
            section[o] = cur
            i += 1

    fields = ['STT_NO','ATTR_YR']
    if ambiguous: fields.append('ROW_SECTION')
    fields += [f'ROW_L{i+1}' for i in range(len(rowk))]
    fields += [f'COL_L{i+1}' for i in range(len(colk))]
    fields += ['ROW_ORD','VALUE','UNIT']

    out = []
    for r in L:
        o = int(r['ROW9'])
        rec = {'STT_NO': stt_no, 'ATTR_YR': r.get('COL6','')}
        if ambiguous: rec['ROW_SECTION'] = section.get(o,'')
        for i,k in enumerate(rowk): rec[f'ROW_L{i+1}'] = clean(r.get(k))
        for i,k in enumerate(colk): rec[f'COL_L{i+1}'] = clean(r.get(k))
        rec.update(ROW_ORD=o, VALUE=r.get('VAL1',''), UNIT=unit)
        out.append(rec)
    return title, fields, out, ambiguous

for fp in sorted(glob.glob(os.path.join(RAW,'NTS_*.json'))):
    title, fields, rows, amb = build(fp)
    cp = fp[:-5] + '.csv'
    with open(cp,'w',encoding='utf-8',newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    print(f"{os.path.basename(cp)[:52]:54s} {len(rows):5d}  amb={amb}  {fields}")
