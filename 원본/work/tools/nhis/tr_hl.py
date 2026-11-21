# -*- coding: utf-8 -*-
"""2022 건강검진통계연보 Ⅰ-6 연령별 성별 일반건강검진 판정 현황(전체) -> tidy long."""
import openpyxl, csv, re, os, warnings
warnings.filterwarnings('ignore')
SRC="/mnt/share/행정데이터_set/work/params/raw/_ext/hl/2022 제1편_일반건강검진.xlsx"
OUT="/mnt/share/행정데이터_set/work/params/raw/nhi_healthlevel_I-6_연령별성별_일반건강검진_판정현황.csv"
COLS={4:'계',5:'정상A',6:'정상B(경계)',7:'질환의심_실인원',8:'일반질환의심',9:'고혈압당뇨병질환의심',10:'유질환자'}
def n(v): return re.sub(r'\s+','',str(v)).strip() if v is not None else ''
def num(v):
    if v is None: return None
    if isinstance(v,str):
        s=v.replace(',','').strip()
        if s in ('','-'): return None
        return float(s) if re.fullmatch(r'-?\d+(\.\d+)?',s) else None
    return v
wb=openpyxl.load_workbook(SRC,data_only=True); ws=wb['(I-6) p66']
rows=[]; age=None
for r in range(8,ws.max_row+1):
    c1,c2=n(ws.cell(r,1).value),n(ws.cell(r,2).value)
    if c1.startswith('주') or c1.startswith('Note'): break
    if c1 and not re.fullmatch(r'[A-Za-z0-9\s.]+',c1): age=re.sub(r'\s+','',c1)
    if c2 not in ('합계','남자','여자') or age is None: continue
    sex='계' if c2=='합계' else c2
    for j,lab in COLS.items():
        v=num(ws.cell(r,j).value)
        if v is None: continue
        rows.append([age,sex,lab,v])
with open(OUT,'w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['연령군','성별','종합판정','인원_명']); w.writerows(rows)
print(OUT,len(rows))
