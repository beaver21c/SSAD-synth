# -*- coding: utf-8 -*-
"""2022 노인장기요양보험통계연보 표2편 2-4/2-6/2-7/2-8 (자격 '계' 블록) -> tidy long.
   표가 여러 시트로 분할되어 있어(열블록 3개 × 시도 2개씩) '계 Total' 열블록 시트만 모아 병합."""
import openpyxl, csv, re, os
SRC="/mnt/share/행정데이터_set/work/params/raw/_ext/b33/표2편_신청_및_인정_현황_2022_복호화.xlsx"
OUT="/mnt/share/행정데이터_set/work/params/raw"
SPEC=[('2-4','시도별_등급별_등급판정현황','92(2-4표)','100(2-4-1표)',4,True),
      ('2-6','시도별_등급별_주거상태현황','134(2-6표)','188(2-7표)',5,False),
      ('2-7','시도별_등급별_주요질병및증상현황','188(2-7표)','260(2-8표)',5,False),
      ('2-8','시도별_등급별_주수발자현황','260(2-8표)',None,5,False)]
def n(v): return re.sub(r'\s+','',str(v)).strip() if v is not None else ''
def num(v):
    if v is None: return None
    if isinstance(v,str):
        s=v.replace(',','').strip()
        if s in ('','-'): return None
        return float(s) if re.fullmatch(r'-?\d+(\.\d+)?',s) else None
    return v
wb=openpyxl.load_workbook(SRC,data_only=True)
names=wb.sheetnames
for tno,desc,start,end,c0,flat in SPEC:
    i0=names.index(start); i1=names.index(end) if end else len(names)
    rows=[]; cats=None
    for sname in names[i0:i1]:
        ws=wb[sname]
        # '계 Total' 로 시작하는 열블록 시트만 채택
        top=None
        for m in ws.merged_cells.ranges:
            if m.min_row==5 and m.min_col==c0: top=n(ws.cell(5,c0).value)
        if not top or not top.startswith('계'): continue
        span=[m for m in ws.merged_cells.ranges if m.min_row==5 and m.min_col==c0][0]
        # '계 Total' 헤더가 두 조각으로 쪼개진 경우가 있어 r6 라벨이 이어지는 끝까지 확장
        cend=span.max_col
        while cend+1<=ws.max_column and n(ws.cell(5,cend+1).value) in ('','계Total') and n(ws.cell(6,cend+1).value) \
              and n(ws.cell(5,cend+1).value)!='일반General':
            nxt=[m for m in ws.merged_cells.ranges if m.min_row==5 and m.min_col==cend+1]
            if nxt and n(ws.cell(5,cend+1).value).startswith('계'): cend=nxt[0].max_col
            else: break
        c=[n(ws.cell(6,j).value) for j in range(c0,cend+1)]
        if cats is None: cats=c
        elif c!=cats: continue
        sido=None; grade='전체'
        for r in ws.iter_rows(min_row=9,max_row=ws.max_row,values_only=True):
            a=n(r[0]); b=n(r[1]) if len(r)>1 else ''
            if a.startswith('주:') or a.startswith('Note'): break
            if a and not re.fullmatch(r'[A-Za-z.\s]+',a): sido=a
            if flat:
                sx=b
            else:
                if b and b not in ('합계','남자','여자') and not re.fullmatch(r'[A-Za-z0-9.\s]+',b): grade=b
                sx=n(r[2]) if len(r)>2 else ''
            if sx not in ('합계','남자','여자') or sido is None: continue
            for k,cat in enumerate(cats):
                v=num(r[c0-1+k]) if c0-1+k<len(r) else None
                if v is None: continue
                rows.append([tno,sido,grade,('계' if sx=='합계' else sx),cat,v])
    p=os.path.join(OUT,f"B33_{tno}_{desc}.csv")
    with open(p,'w',newline='',encoding='utf-8') as f:
        w=csv.writer(f); w.writerow(['표번호','시도','장기요양등급','성별','구분','인원_명']); w.writerows(rows)
    sid=sorted({r[1] for r in rows})
    print(p,len(rows),'| 시도수',len(sid),'| cats',len(cats or []))
