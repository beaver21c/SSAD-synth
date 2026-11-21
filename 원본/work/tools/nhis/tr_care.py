# -*- coding: utf-8 -*-
"""3-6~3-8 연령별·성별 진료현황 -> tidy long. 원표 셀 값을 그대로 전사."""
import openpyxl, csv, re, os
SRC="/mnt/share/행정데이터_set/work/params/raw/_ext/r10/03-1(건강공단) 2022년_제3편 건강보험 진료현황.xlsx"
OUT="/mnt/share/행정데이터_set/work/params/raw"
COLS={3:'진료실인원수_명',4:'입내원일수_일',5:'요양급여일수_일',6:'진료비_천원',7:'급여비_천원',
      8:'입내원1일당진료비_원',9:'입내원1일당급여비_원',10:'요양급여1일당진료비_원',11:'요양급여1일당급여비_원'}
SHEETS={'3-6':('총계','전체'),'3-6-1':('직장','전체'),'3-6-2':('지역','전체'),
        '3-7':('총계','의료기관소계'),'3-7-1':('총계','입원'),'3-7-2':('총계','외래'),'3-8':('총계','약국')}
def n(s): return re.sub(r'\s+','',str(s)).strip() if s is not None else ''
wb=openpyxl.load_workbook(SRC,data_only=True)
for sh,(자격,형태) in SHEETS.items():
    ws=wb[sh]; rows=[]; grp=None
    for r in ws.iter_rows(min_row=8,max_row=ws.max_row,values_only=True):
        a=n(r[0])
        if not a: continue
        if a in ('남자','여자'):
            sex=a
            if grp is None: continue
        else:
            grp=a.replace('세이상','세 이상'); sex='계'
        for j,name in COLS.items():
            v=r[j-1] if j-1<len(r) else None
            if v is None or (isinstance(v,str) and not v.strip()): continue
            if isinstance(v,str):
                vs=v.replace(',','').strip()
                if not re.fullmatch(r'-?\d+(\.\d+)?',vs): continue
                v=float(vs)
            rows.append([sh,자격,형태,grp,sex,name,v])
    p=os.path.join(OUT,f"R10_{sh}_연령성별_진료현황_{자격}_{형태}.csv")
    with open(p,'w',newline='',encoding='utf-8') as f:
        w=csv.writer(f); w.writerow(['표번호','자격구분','진료형태','연령군','성별','지표','값']); w.writerows(rows)
    print(p,len(rows))
