# -*- coding: utf-8 -*-
"""1-3-x 시도별 연령별 성별 적용인구 -> tidy long CSV. 전사만 수행 (계산·추정 없음)."""
import openpyxl, csv, sys, re, os
SRC = "/mnt/share/행정데이터_set/work/params/raw/_ext/r10/01-1(건강공단) 2022년_제1편 건강보험 일반현황 제1장 적용인구.xlsx"
OUT = "/mnt/share/행정데이터_set/work/params/raw"
SHEETS = {"1-3":"의료보장(건강보험+의료급여)","1-3-1":"건강보험","1-3-2":"직장","1-3-3":"지역","1-3-4":"의료급여"}

def norm(s):
    return re.sub(r'\s+','',str(s)).strip() if s is not None else ''

wb = openpyxl.load_workbook(SRC, data_only=True)
for sh, scope in SHEETS.items():
    ws = wb[sh]
    # header ages from row 5
    hdr = [c for c in next(ws.iter_rows(min_row=5,max_row=5,values_only=True))]
    ages = {}
    for j,v in enumerate(hdr, start=1):
        if j < 3 or v is None: continue
        t = re.sub(r'\s+',' ',str(v)).strip()
        t = re.sub(r'\s*(T$|Age.*$|and over$)','',t).strip()
        t = t.replace('∼','~')
        if t: ages[j] = t
    rows=[]
    group=None   # 시도 or 자격구분
    for r in ws.iter_rows(min_row=8, max_row=ws.max_row, values_only=True):
        a, b = norm(r[0]), norm(r[1]) if len(r)>1 else ''
        if not a: continue
        if a in ('남','여'):
            sex = '남자' if a=='남' else '여자'
            if group is None: continue
        else:
            group = re.sub(r'\s+','',str(r[0])).strip()
            sex = '계'
        for j,age in ages.items():
            v = r[j-1] if j-1 < len(r) else None
            if v is None or str(v).strip()=='' : continue
            if isinstance(v,str):
                vs=v.replace(',','').strip()
                if not re.fullmatch(r'-?\d+(\.\d+)?', vs): continue
                v=float(vs) if '.' in vs else int(vs)
            rows.append([sh, scope, group, sex, age, v])
    p = os.path.join(OUT, f"R10_{sh}_시도연령성별_적용인구_{scope}.csv")
    with open(p,'w',newline='',encoding='utf-8') as f:
        w=csv.writer(f); w.writerow(['표번호','적용구분','구분','성별','연령군','적용인구_명']); w.writerows(rows)
    print(p, len(rows))
