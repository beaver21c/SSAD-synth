# -*- coding: utf-8 -*-
"""3-3표 연령별 자격별 급여종류별 장기요양 급여실적 -> tidy long (15개 분할시트 전체 병합)."""
import openpyxl, csv, re, os
SRC="/mnt/share/행정데이터_set/work/params/raw/_ext/b33/표3편_장기요양_급여현황_2022_복호화.xlsx"
OUT="/mnt/share/행정데이터_set/work/params/raw/B33_3-3_연령별_자격별_급여종류별_급여실적.csv"
def n(v): return re.sub(r'\s+','',str(v)).strip() if v is not None else ''
def num(v):
    if v is None: return None
    if isinstance(v,str):
        s=v.replace(',','').strip()
        if s in ('','-'): return None
        return float(s) if re.fullmatch(r'-?\d+(\.\d+)?',s) else None
    return v
AGES={'계','65세미만','65세~69세','70세~74세','75세~79세','80세~84세','85세이상'}
SEX={'계':'계','S.T':'계','남자':'남자','여자':'여자'}
METR={'급여이용수급자','급여제공기관','급여제공일수','급여비용','공단부담금'}
wb=openpyxl.load_workbook(SRC,data_only=True)
names=wb.sheetnames; i=names.index('700(3-3표)'); j=names.index('730(3-4표)')
rows=[]
for sh in names[i:j]:
    ws=wb[sh]
    qual=n(ws.cell(5,5).value) or ''
    qual=re.sub(r'[A-Za-z.\s]+','',qual) or '계'
    cats=[n(ws.cell(6,c).value) for c in range(5,ws.max_column+1)]
    age=None; sex=None
    for r in range(8,ws.max_row+1):
        c1,c2,c3=n(ws.cell(r,1).value),n(ws.cell(r,2).value),n(ws.cell(r,3).value)
        if c1.startswith('주:'): break
        if c1 in AGES: age=c1
        if c2 in SEX: sex=SEX[c2]
        if c3 not in METR or age is None or sex is None: continue
        for k,cat in enumerate(cats):
            v=num(ws.cell(r,5+k).value)
            if v is None: continue
            rows.append([sh,qual,age,sex,cat,c3,v])
with open(OUT,'w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['원시트','자격구분','연령군','성별','급여종류','지표','값']); w.writerows(rows)
print(OUT,len(rows))
