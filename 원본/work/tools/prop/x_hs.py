"""주거실태조사 2022 일반가구 연구보고서 표 전사"""
import pymupdf, csv, re, warnings
warnings.filterwarnings('ignore')
PDF = 'params/raw/PROP_주거실태조사2022_일반가구연구보고서.pdf'
d = pymupdf.open(PDF)
YEARS = ['2006','2010','2014','2016','2017','2018','2019','2020','2021','2022']

def lines(p):
    return [l.strip() for l in d[p].get_text().split('\n') if l.strip()]

def isnum(s):
    return bool(re.fullmatch(r'-?[\d,]+(\.\d+)?', s))

def wide_table(p, start_marker, row_labels):
    """구분 / 2006..2022 헤더 뒤에 (라벨 + 10개 값) 반복되는 표"""
    L = lines(p)
    i = L.index(start_marker)
    j = i
    # 연도 헤더 확인
    assert L[j+1:j+11] == YEARS, L[j+1:j+13]
    j += 11
    out = {}
    k = j
    while k < len(L) and len(out) < len(row_labels):
        if L[k] in row_labels and all(isnum(x) for x in L[k+1:k+11]):
            out[L[k]] = [x.replace(',', '') for x in L[k+1:k+11]]
            k += 11
        else:
            k += 1
    return out

def block_table(p, regions, ncol):
    """지역 라벨 뒤에 (연도 + ncol개 값) 반복"""
    L = lines(p)
    out = {}
    k = 0
    cur = None
    while k < len(L):
        if L[k] in regions:
            cur = L[k]; out.setdefault(cur, {}); k += 1; continue
        if cur and L[k] in YEARS and all(isnum(x) for x in L[k+1:k+1+ncol]):
            out[cur][L[k]] = [x.replace(',', '') for x in L[k+1:k+1+ncol]]
            k += 1 + ncol; continue
        k += 1
    return out

rows = []
# 표 Ⅲ-12 자가보유율 / 표 Ⅲ-14 자가점유율 (지역별·소득별)
for p, ind, tbl in [(72, '자가보유율', '표 Ⅲ-12'), (73, '자가점유율', '표 Ⅲ-14')]:
    g = wide_table(p, '구분', ['전체','수도권','광역시 등','도지역','하위','중위','상위'])
    for lab, vs in g.items():
        for y, v in zip(YEARS, vs):
            rows.append([tbl, ind, lab, y, v])
# 표 Ⅲ-13 / 표 Ⅲ-15 (가구주 연령별·가구원수별)
AGE = ['40세 미만','40세~49세','50세~59세','60세 이상',
       '1인가구','2인가구','3인가구','4인가구','5인가구','6인 이상 가구']
for p, ind, tbl in [(73, '자가보유율', '표 Ⅲ-13'), (74, '자가점유율', '표 Ⅲ-15')]:
    g = wide_table(p, '구분', AGE)
    for lab, vs in g.items():
        for y, v in zip(YEARS, vs):
            rows.append([tbl, ind, lab, y, v])
with open('params/raw/PROP_HS2022_자가보유율_자가점유율.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['표', '지표', '구분', '연도', '비율_pct']); w.writerows(rows)
print('자가보유/점유율', len(rows))

# 표 Ⅲ-16 지역별 점유형태
REG = ['전국','수도권','광역시 등','도지역']
g = block_table(76, REG, 4)
rows = []
for r, yy in g.items():
    for y, vs in yy.items():
        for k, v in zip(['자가','임차','무상','계'], vs):
            rows.append([r, y, k, v])
with open('params/raw/PROP_HS2022_표3-16_지역별점유형태.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['지역', '연도', '점유형태', '비율_pct']); w.writerows(rows)
print('표Ⅲ-16', len(rows))

# 표 Ⅲ-46 지역별 평균 주택가격 및 임대료 / 표 Ⅲ-47 소득별
COLS = ['주택가격_만원','전세보증금_만원','보증금있는월세_보증금_만원',
        '보증금있는월세_월세_만원','보증금없는월세_월세_만원']
for p, keys, out, dim in [(106, REG, 'params/raw/PROP_HS2022_표3-46_지역별평균주택가격임대료.csv', '지역'),
                          (107, ['하위','중위','상위'], 'params/raw/PROP_HS2022_표3-47_소득별평균주택가격임대료.csv', '소득계층')]:
    g = block_table(p, keys, 5)
    rows = []
    for r, yy in g.items():
        for y, vs in yy.items():
            for k, v in zip(COLS, vs):
                rows.append([r, y, k, v])
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow([dim, '연도', '항목', '값']); w.writerows(rows)
    print(out, len(rows))
