# -*- coding: utf-8 -*-
"""3-4/3-4-1/3-4-2 요양기관종별 진료형태별 진료현황 -> tidy long."""
import openpyxl, csv, re, os
SRC="/mnt/share/행정데이터_set/work/params/raw/_ext/r10/03-1(건강공단) 2022년_제3편 건강보험 진료현황.xlsx"
OUT="/mnt/share/행정데이터_set/work/params/raw"
COLS={4:'진료실인원수_명',5:'입내원일수_일',6:'요양급여일수_일',7:'진료비_천원',8:'급여비_천원',
      9:'입내원1일당진료비_원',10:'입내원1일당급여비_원',11:'요양급여1일당진료비_원',12:'요양급여1일당급여비_원'}
SHEETS={'3-4':'총계','3-4-1':'직장','3-4-2':'지역'}
def clean(s):
    if s is None: return ''
    t=str(s).replace('　',' ')
    t=re.sub(r'[A-Za-z().\'’,/&]+',' ',t)      # drop English gloss
    return re.sub(r'\s+','',t).strip()
wb=openpyxl.load_workbook(SRC,data_only=True)
for sh,자격 in SHEETS.items():
    ws=wb[sh]; rows=[]; big=''; kind=''
    for r in ws.iter_rows(min_row=8,max_row=ws.max_row,values_only=True):
        c1,c2,c3=clean(r[0]),clean(r[1]),clean(r[2])
        if c1.startswith('주') or c1.startswith('3)') or c1.startswith('4)'): break
        if c1: big=c1; kind=c1 if not c2 else c2
        if c2: kind=c2
        if not c3: continue
        rows.append([sh,자격,big,kind,c3]+[None]*0+[ (r[j-1] if j-1<len(r) else None) for j in COLS])
    p=os.path.join(OUT,f"R10_{sh}_요양기관종별_진료형태별_진료현황_{자격}.csv")
    with open(p,'w',newline='',encoding='utf-8') as f:
        w=csv.writer(f); w.writerow(['표번호','자격구분','대분류','요양기관종별','진료형태']+list(COLS.values()))
        for row in rows:
            head,vals=row[:5],row[5:]
            out=[]
            for v in vals:
                if v is None or (isinstance(v,str) and v.strip() in ('','-')): out.append('')
                else: out.append(v)
            w.writerow(head+out)
    print(p,len(rows))
