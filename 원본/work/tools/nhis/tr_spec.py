# -*- coding: utf-8 -*-
"""6-22 중증질환 산정특례적용 연령별 성별 진료현황 -> tidy long (3개 연속시트 병합)."""
import openpyxl, csv, re, os
SRC="/mnt/share/행정데이터_set/work/params/raw/_ext/r10/06-2(건강공단) 2022년_제6편 질병통계.xlsx"
OUT="/mnt/share/행정데이터_set/work/params/raw/R10_6-22_산정특례_연령성별_진료현황.csv"
MEAS=['진료실인원수_명','입내원일수_일','요양급여일수_일','진료비_천원','급여비_천원']
BLOCKS={'6-22':[(3,'계'),(8,'암질환'),(13,'뇌혈관질환')],
        '6-22(계속)':[(3,'심장질환'),(8,'희귀난치성질환'),(13,'중증화상')],
        '6-22(계속2)':[(3,'중증외상'),(8,'중증치매'),(13,'결핵'),(18,'잠복결핵')]}
def n(s): return re.sub(r'\s+','',str(s)).strip() if s is not None else ''
wb=openpyxl.load_workbook(SRC,data_only=True); rows=[]
for sh,blocks in BLOCKS.items():
    ws=wb[sh]; grp=None
    for r in ws.iter_rows(min_row=8,max_row=ws.max_row,values_only=True):
        a=n(r[0])
        if not a or a.startswith('주'): continue
        if a in ('남자','여자'):
            sex=a
            if grp is None: continue
        else:
            grp=a.replace('세이상','세 이상'); sex='계'
        for c0,dis in blocks:
            for k,m in enumerate(MEAS):
                j=c0+k; v=r[j-1] if j-1<len(r) else None
                if v is None or (isinstance(v,str) and v.strip() in ('','-')): continue
                if isinstance(v,str):
                    vs=v.replace(',','').strip()
                    if not re.fullmatch(r'-?\d+(\.\d+)?',vs): continue
                    v=float(vs)
                rows.append([sh,dis,grp,sex,m,v])
with open(OUT,'w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['표번호','산정특례질환','연령군','성별','지표','값']); w.writerows(rows)
print(OUT,len(rows))
