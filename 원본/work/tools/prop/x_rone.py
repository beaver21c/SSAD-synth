"""부동산원 전국주택가격동향조사 월간 시계열 → 2022년 시도별 tidy CSV"""
import zipfile, io, csv, re, openpyxl, warnings
warnings.filterwarnings('ignore')

ZIP = 'params/raw/PROP_부동산원_전국주택가격동향조사_월간시계열.zip'
SIDO = ['전국','서울','부산','대구','인천','광주','대전','울산','세종','경기','강원',
        '충북','충남','전북','전남','경북','경남','제주','수도권','지방권','5대광역시','8개도']
TARGETS = [
    ('01.주택_월간_종합/06.전세가격/(월) 평균전세가격_주택종합.xlsx', '주택종합', '평균전세가격', '천원'),
    ('01.주택_월간_종합/07.월세가격/(월) 평균월세보증금_주택종합.xlsx', '주택종합', '평균월세보증금', '천원'),
    ('01.주택_월간_종합/07.월세가격/(월) 평균월세가격_주택종합.xlsx', '주택종합', '평균월세가격', '천원'),
    ('02.주택_월간_아파트/06.전세가격/(월) 평균전세가격_아파트.xlsx', '아파트', '평균전세가격', '천원'),
    ('02.주택_월간_아파트/07.월세가격/(월) 평균월세보증금_아파트.xlsx', '아파트', '평균월세보증금', '천원'),
    ('02.주택_월간_아파트/07.월세가격/(월) 평균월세가격_아파트.xlsx', '아파트', '평균월세가격', '천원'),
]

z = zipfile.ZipFile(ZIP)
rows = []
for name, kind, item, unit in TARGETS:
    wb = openpyxl.load_workbook(io.BytesIO(z.read(name)), data_only=True)
    ws = wb.worksheets[0]
    hdr = [ws.cell(4, c).value for c in range(1, ws.max_column+1)]
    u_row = [ws.cell(6, c).value for c in range(1, ws.max_column+1)]
    cols22 = [(c, hdr[c-1]) for c in range(4, ws.max_column+1)
              if hdr[c-1] and str(hdr[c-1]).startswith('2022년')]
    assert cols22, name
    for r in range(8, ws.max_row+1):
        b, cc = ws.cell(r,2).value, ws.cell(r,3).value
        if b is None or cc is None: continue
        b, cc = str(b).strip(), str(cc).strip()
        if b != cc: continue                # 시도(또는 권역) 레벨 행만
        a = b
        if a not in SIDO: continue
        for c, h in cols22:
            v = ws.cell(r, c).value
            if v is None or str(v).strip() == '': continue
            m = re.match(r'2022년\s*(\d+)월', str(h))
            rows.append([kind, item, a, f"2022-{int(m.group(1)):02d}", str(u_row[c-1] or unit), v])
out = 'params/raw/PROP_REB_주택가격동향_평균전세월세_2022.csv'
with open(out, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['주택유형','항목','지역','연월','단위','값']); w.writerows(rows)
print(out, len(rows))
# 연평균 요약
import collections
agg = collections.defaultdict(list)
for k, it, a, ym, u, v in rows:
    try: agg[(k, it, a, u)].append(float(v))
    except (TypeError, ValueError): pass
out2 = 'params/raw/PROP_REB_주택가격동향_평균전세월세_2022연평균.csv'
with open(out2, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['주택유형','항목','지역','단위','2022년_월평균','관측월수'])
    for (k, it, a, u), vs in agg.items():
        w.writerow([k, it, a, u, round(sum(vs)/len(vs), 1), len(vs)])
print(out2, len(agg))
