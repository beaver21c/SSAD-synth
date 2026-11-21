# 지방세통계연감 2023(2022년 실적) 재산세 표 전사
import sys, csv, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import pymupdf, pdftab

PDF = 'params/raw/PROP_지방세통계연감2023.pdf'
REG = ['합계','시 계','군 계','구 계','서울','부산','대구','인천','광주','대전','울산','세종',
       '경기','강원','충북','충남','전북','전남','경북','경남','제주']

def grid(p, y0, y1):
    rows = pdftab.numrows(d[p], y0, y1)
    c, g = pdftab.to_grid(rows)
    return c, g

def num(s):
    s = s.replace(',', '').strip()
    return s if s else ''

d = pymupdf.open(PDF)

# ---- 9-1-1 재산세 과세현황(총괄) : p219 상단 + p220 상단 ----
c1, g1 = grid(219, 110, 400)
c2, g2 = grid(220, 110, 400)
assert len(g1) == 21 and len(g2) == 21, (len(g1), len(g2))
COL1 = ['총_건수','총_과표_천원','총_세액_천원','과세분_건수']
COL2 = ['과세분_과표_천원','과세분_세액_천원','비과세분_건수','비과세분_과표_천원','비과세분_세액_천원']
assert len(g1[0]) == len(COL1) and len(g2[0]) == len(COL2), (len(g1[0]), len(g2[0]))
rows = []
for i, r in enumerate(REG):
    vals = dict(zip(COL1, g1[i])); vals.update(dict(zip(COL2, g2[i])))
    for k, v in vals.items():
        rows.append([r, k, num(v)])
with open('params/raw/PROP_9-1-1_재산세과세현황총괄_2022.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['지역', '항목', '값'])
    w.writerows(rows)
print('9-1-1 rows', len(rows))

# ---- 9-1-2 과세물건별 과세현황(총괄) : p219 하단 + p220 하단 ----
c3, g3 = grid(219, 410, 700)
c4, g4 = grid(220, 410, 700)
assert len(g3) == 21 and len(g4) == 21
COL3 = ['합계_건수','합계_과표_천원','합계_세액_천원','토지_건수','토지_과표_천원','토지_세액_천원','건축물_건수','건축물_과표_천원']
COL4 = ['건축물_세액_천원','주택_건수','주택_과표_천원','주택_세액_천원','선박_건수','선박_과표_천원','선박_세액_천원','항공기_건수','항공기_과표_천원','항공기_세액_천원']
assert len(g3[0]) == len(COL3) and len(g4[0]) == len(COL4), (len(g3[0]), len(g4[0]))
rows = []
for i, r in enumerate(REG):
    vals = dict(zip(COL3, g3[i])); vals.update(dict(zip(COL4, g4[i])))
    for k, v in vals.items():
        obj, item = k.split('_', 1)
        rows.append([r, obj, item, num(v)])
with open('params/raw/PROP_9-1-2_과세물건별과세현황총괄_2022.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['지역', '과세물건', '항목', '값'])
    w.writerows(rows)
print('9-1-2 rows', len(rows))

# 검증: 물건별 세액 합 = 합계 세액
tot = {}
for r, obj, item, v in rows:
    if item == '세액_천원':
        tot.setdefault(r, {})[obj] = int(v) if v else 0
for r, dd in tot.items():
    s = sum(v for k, v in dd.items() if k != '합계')
    ok = (s == dd['합계'])
    if not ok:
        print('MISMATCH', r, s, dd['합계'])
print('세액 합산 검증 완료')

# ---- 9-2-3-3 주택 과표단계별 과세현황 : p255/p256 상단 ----
c5, g5 = grid(255, 170, 395)
c6, g6 = grid(256, 170, 395)
assert len(g5) == 21 and len(g6) == 21, (len(g5), len(g6))
A = ['합계_건수','합계_면적_부속토지_천m2','합계_면적_건물_천m2','합계_과표_천원','합계_세액_천원',
     '6천만원이하_건수','6천만원이하_면적_부속토지_천m2','6천만원이하_면적_건물_천m2','6천만원이하_과표_천원','6천만원이하_세액_천원',
     '6천만초과1.5억이하_건수']
B = ['6천만초과1.5억이하_면적_부속토지_천m2','6천만초과1.5억이하_면적_건물_천m2','6천만초과1.5억이하_과표_천원','6천만초과1.5억이하_세액_천원',
     '1.5억초과3억이하_건수','1.5억초과3억이하_면적_부속토지_천m2','1.5억초과3억이하_면적_건물_천m2','1.5억초과3억이하_과표_천원','1.5억초과3억이하_세액_천원',
     '3억초과_건수','3억초과_면적_부속토지_천m2','3억초과_면적_건물_천m2','3억초과_과표_천원','3억초과_세액_천원']
assert len(g5[0]) == len(A) and len(g6[0]) == len(B), (len(g5[0]), len(g6[0]))
# 원문 인쇄 오류 보정 (셀 폭 초과로 앞자리 '2'가 덧붙어 인쇄됨; 행 합계와 대조로 판독)
FIX = {('부산', '6천만초과1.5억이하', '건수'): ('2522,368', '522368',
        "원문 p.218 인쇄 '2522,368' — 구간별 건수 합(605,032+522,368+234,992+73,769)=합계 1,436,161과 일치하여 522,368으로 판독")}
rows = []
for i, r in enumerate(REG):
    v = dict(zip(A, g5[i])); v.update(dict(zip(B, g6[i])))
    for k, val in v.items():
        seg, item = k.split('_', 1)
        key = (r, seg, item); note = ''
        val_n = num(val)
        if key in FIX and val.strip() == FIX[key][0]:
            val_n, note = FIX[key][1], FIX[key][2]
        rows.append([r, seg, item, val_n, note])
with open('params/raw/PROP_9-2-3-3_주택과표단계별과세현황_2022.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['지역', '과표구간', '항목', '값', '비고']); w.writerows(rows)
print('9-2-3-3 rows', len(rows))
chk = {}
for r, seg, item, v, _n in rows:
    if item == '건수': chk.setdefault(r, {})[seg] = int(v) if v else 0
bad = [r for r, dd in chk.items() if sum(x for k, x in dd.items() if k != '합계') != dd['합계']]
print('9-2-3-3 건수 합산 불일치:', bad)

# ---- 9-2-3-4 주택 세액단계별 과세현황(건수) : p255/p256 하단 ----
c7, g7 = grid(255, 470, 700)
c8, g8 = grid(256, 470, 700)
assert len(g7) == 21 and len(g8) == 21, (len(g7), len(g8))
S = ['합계','5천원이하','5만원이하','10만원이하','50만원이하'] + \
    ['100만원이하','5백만원이하','1천만원이하','5천만원이하','1억원이하','1억원초과']
assert len(g7[0]) == 5 and len(g8[0]) == 6, (len(g7[0]), len(g8[0]))
rows = []
for i, r in enumerate(REG):
    vals = list(g7[i]) + list(g8[i])
    for k, val in zip(S, vals):
        rows.append([r, k, num(val)])
with open('params/raw/PROP_9-2-3-4_주택세액단계별건수_2022.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['지역', '세액구간', '건수']); w.writerows(rows)
print('9-2-3-4 rows', len(rows))
chk = {}
for r, seg, v in rows: chk.setdefault(r, {})[seg] = int(v) if v else 0
bad = [(r, sum(x for k, x in dd.items() if k != '합계'), dd['합계']) for r, dd in chk.items()
       if sum(x for k, x in dd.items() if k != '합계') != dd['합계']]
print('9-2-3-4 건수 합산 불일치:', bad)
