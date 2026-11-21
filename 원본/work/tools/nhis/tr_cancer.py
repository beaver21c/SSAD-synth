# -*- coding: utf-8 -*-
"""6-18 / 6-21 연령별 성별 중증(암)등록환자 진료현황 -> tidy long."""
import openpyxl, csv, re, os
SRC="/mnt/share/행정데이터_set/work/params/raw/_ext/r10/06-2(건강공단) 2022년_제6편 질병통계.xlsx"
OUT="/mnt/share/행정데이터_set/work/params/raw"
COLS={3:'진료실인원수_명',4:'입내원일수_일',5:'요양급여일수_일',6:'진료비_천원',7:'급여비_천원',
      8:'1인당진료비_원',9:'1인당급여비_원',10:'1인당입내원일수_일'}
SH={'6-18':'신규중증(암)등록환자','6-21':'전체중증(암)등록환자'}
def n(v): return re.sub(r'\s+','',str(v)).strip() if v is not None else ''
def num(v):
    if v is None: return None
    if isinstance(v,str):
        s=v.replace(',','').strip()
        if s in ('','-'): return None
        return float(s) if re.fullmatch(r'-?\d+(\.\d+)?',s) else None
    return v
wb=openpyxl.load_workbook(SRC,data_only=True)
for sh,scope in SH.items():
    ws=wb[sh]; rows=[]; grp=None
    for r in range(8,ws.max_row+1):
        a=n(ws.cell(r,1).value)
        if not a or a.startswith('주'): continue
        if a in ('남자','여자'):
            sex=a
            if grp is None: continue
        else:
            grp=a.replace('세이상','세 이상'); sex='계'
        for j,m in COLS.items():
            v=num(ws.cell(r,j).value)
            if v is None: continue
            rows.append([sh,scope,grp,sex,m,v])
    p=os.path.join(OUT,f"R10_{sh}_연령성별_{scope}_진료현황.csv")
    with open(p,'w',newline='',encoding='utf-8') as f:
        w=csv.writer(f); w.writerow(['표번호','대상','연령군','성별','지표','값']); w.writerows(rows)
    print(p,len(rows))
