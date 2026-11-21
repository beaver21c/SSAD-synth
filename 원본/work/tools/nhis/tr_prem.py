# -*- coding: utf-8 -*-
"""II-3 / II-6 / II-7 보험료 부과 현황 -> tidy CSV."""
import openpyxl, csv, re, os
SRC="/mnt/share/행정데이터_set/work/params/raw/_ext/r10/02-2(건강공단) 2022년_제2편 건강보험 재정현황.xlsx"
OUT="/mnt/share/행정데이터_set/work/params/raw"
def num(v):
    if v is None: return ''
    if isinstance(v,str):
        s=v.replace(',','').strip()
        if s in ('','-'): return ''
        return float(s) if re.fullmatch(r'-?\d+(\.\d+)?',s) else ''
    return v
def lab(v):
    return re.sub(r'\s+','',str(v).replace('　',' ')).strip() if v is not None else ''
wb=openpyxl.load_workbook(SRC,data_only=True)

# ---- II-3 : 보수월액 구간별 (좌 1-9 / 우 10-18 두 패널) ----
ws=wb['II-3']; rows=[]
H=['인원_계_명','인원_근로자_명','인원_공교_명','보험료_계_천원','보험료_근로자_천원','보험료_공교_천원','구성비_인원_pct','구성비_보험료_pct']
for r in ws.iter_rows(min_row=8,max_row=ws.max_row,values_only=True):
    for off in (0,9):
        L=lab(r[off]) if off<len(r) else ''
        if not L or L.startswith('주') or L.startswith('Note') or re.match(r'^\d\)',L): continue
        vals=[num(r[off+1+k]) if off+1+k<len(r) else '' for k in range(8)]
        if all(v=='' for v in vals): continue
        rows.append([L.replace('Total','').strip()]+vals)
p=os.path.join(OUT,'R10_II-3_보수월액구간별_가입자_보험료부담_직장.csv')
open(p,'w',newline='',encoding='utf-8').close()
with open(p,'w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['보수월액구간_원']+H); w.writerows(rows)
print(p,len(rows))

# ---- II-6 : 산정보험료 점수 구간별 (지역) ----
rows=[]
H2=['세대수','세대구성비_pct','보험료_천원','보험료구성비_pct','소득등급_세대수','소득등급_점수','재산등급_세대수','재산등급_점수','자동차등급_세대수','자동차등급_점수']
for sh in ['II-6 (1)','II-6 (2)']:
    ws=wb[sh]
    for r in ws.iter_rows(min_row=8,max_row=ws.max_row,values_only=True):
        L=lab(r[0])
        if not L or L.startswith('주') or L.startswith('Note') or re.match(r'^\d\)',L): continue
        vals=[num(r[k]) if k<len(r) else '' for k in range(1,11)]
        if all(v=='' for v in vals): continue
        rows.append([sh,L.replace('Total','').strip()]+vals)
p=os.path.join(OUT,'R10_II-6_산정보험료_점수구간별_현황_지역.csv')
with open(p,'w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['표번호','점수구간']+H2); w.writerows(rows)
print(p,len(rows))

# ---- II-7 : 보험료분위별 ----
ws=wb['II-7']; rows=[]
GRP=[(2,'계'),(6,'직장계'),(10,'직장_근로자'),(14,'직장_공교'),(18,'지역')]
FLD={'계':['세대수','최대보험료_원','평균보험료_원','적용인구_명'],
     '직장계':['가입자_명','최대보험료_원','평균보험료_원','적용인구_명'],
     '직장_근로자':['가입자_명','최대보험료_원','평균보험료_원','적용인구_명'],
     '직장_공교':['가입자_명','최대보험료_원','평균보험료_원','적용인구_명'],
     '지역':['세대수','최대보험료_원','평균보험료_원','적용인구_명']}
for r in ws.iter_rows(min_row=10,max_row=ws.max_row,values_only=True):
    L=lab(r[0])
    if not L or L.startswith('주') or re.match(r'^\d\)',L): continue
    for c0,g in GRP:
        for k,fld in enumerate(FLD[g]):
            v=num(r[c0-1+k]) if c0-1+k<len(r) else ''
            if v=='': continue
            rows.append([L,g,fld,v])
p=os.path.join(OUT,'R10_II-7_보험료분위별_보험료현황.csv')
with open(p,'w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['보험료분위','자격구분','지표','값']); w.writerows(rows)
print(p,len(rows))
