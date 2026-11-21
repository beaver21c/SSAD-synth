# -*- coding: utf-8 -*-
"""II-8 연도별 건강보험 주요지표(총괄) -> tidy long (R13 대체·검증용)."""
import openpyxl, csv, re, os
SRC="/mnt/share/행정데이터_set/work/params/raw/_ext/r10/02-2(건강공단) 2022년_제2편 건강보험 재정현황.xlsx"
OUT="/mnt/share/행정데이터_set/work/params/raw/R10_II-8_연도별_건강보험_주요지표_총괄.csv"
def n(v): return re.sub(r'\s+','',str(v)).strip() if v is not None else ''
def num(v):
    if v is None: return None
    if isinstance(v,str):
        s=v.replace(',','').strip()
        if s in ('','-'): return None
        return float(s) if re.fullmatch(r'-?\d+(\.\d+)?',s) else None
    return v
wb=openpyxl.load_workbook(SRC,data_only=True); ws=wb['II-8']
years={j:int(n(ws.cell(5,j).value)) for j in range(9,ws.max_column+1)
       if n(ws.cell(5,j).value).isdigit()}
rows=[]; L1=''; L2=''
for r in range(7,ws.max_row+1):
    a,b,c,d=n(ws.cell(r,1).value),n(ws.cell(r,2).value),n(ws.cell(r,3).value),n(ws.cell(r,4).value)
    if a.startswith('주'): break
    if a and not re.fullmatch(r'[A-Za-z\s]+',a): L1=a
    if b and not re.fullmatch(r'[A-Za-z\s]+',b): L2=b
    if not d: continue
    unit=n(ws.cell(r,7).value)
    for j,y in years.items():
        v=num(ws.cell(r,j).value)
        if v is None: continue
        rows.append([L1,L2,d,unit,y,v])
with open(OUT,'w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['대분류','중분류','지표','단위','연도','값']); w.writerows(rows)
print(OUT,len(rows),'years',sorted(years.values()))
