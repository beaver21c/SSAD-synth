# -*- coding: utf-8 -*-
"""R11 본인부담상한제 + R13 주요통계 보험료 표 -> tidy CSV. 전사만 수행."""
import openpyxl, csv, re, os
RAW="/mnt/share/행정데이터_set/work/params/raw"
def n(v): return re.sub(r'\s+','',str(v)).strip() if v is not None else ''

# ---------- R11-1: 연도별 본인부담상한액 (참고자료.xlsx) ----------
wb=openpyxl.load_workbook(f"{RAW}/_ext/r11/국민건강보험공단_상한제년도월별기준보험료_참고자료.xlsx",data_only=True)
ws=wb.worksheets[0]
bands=[(3,'1구간(1분위)'),(4,'2구간(2~3분위)'),(5,'3구간(4~5분위)'),(6,'4구간(6~7분위)'),
       (7,'5구간(8분위)'),(8,'6구간(9분위)'),(9,'7구간(10분위)')]
rows=[]; year=None
for r in range(4,ws.max_row+1):
    a,b=n(ws.cell(r,1).value),n(ws.cell(r,2).value)
    m=re.match(r'^(20\d\d)년$',a) or re.match(r'^(20\d\d)년$',b)
    if m: year=int(m.group(1)); kind='일반'
    elif '요양병원' in b: kind='요양병원120일초과입원'
    else: continue
    for j,band in bands:
        v=n(ws.cell(r,j).value)
        mm=re.match(r'^(\d+)만원$',v)
        if not mm: continue
        rows.append([year,kind,band,int(mm.group(1))*10000])
p=f"{RAW}/R11_연도별_본인부담상한액_보험료분위구간별.csv"
with open(p,'w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['연도','입원유형','보험료분위구간','본인부담상한액_원']); w.writerows(rows)
print(p,len(rows))

# ---------- R11-2: 상한제 지급내역 (연도별) ----------
src=f"{RAW}/R11_15020230_본인부담금상한제_지급내역_20221231.csv"
raw=open(src,'rb').read().decode('cp949')
out=[]
for i,line in enumerate(raw.strip().splitlines()):
    cells=[c.strip() for c in line.split(',')]
    if i==0: continue
    if len(cells)<5 or not cells[0].isdigit(): continue
    out.append([int(cells[0])]+[int(c) for c in cells[1:5]])
p=f"{RAW}/R11_연도별_본인부담상한제_지급내역.csv"
with open(p,'w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['연도','사전지급건수','사전상한금_원','사후환급건수','사후환급금_원']); w.writerows(out)
print(p,len(out))

# ---------- R11-3: 기준보험료 개인단위 표본 (원자료 15행 = 공개 샘플) ----------
src=f"{RAW}/_ext/r11/국민건강보험공단_상한제년도월별기준보험료.csv"
raw=open(src,'rb').read().decode('cp949')
lines=[l for l in raw.strip().splitlines() if l.strip()]
p=f"{RAW}/R11_상한제_기준보험료_개인단위표본.csv"
with open(p,'w',newline='',encoding='utf-8') as f: f.write('\n'.join(lines)+'\n')
print(p,len(lines)-1,'rows (공개표본)')

# ---------- R13: 연도별 1인당 월평균 보험료 / 부과현황 ----------
wb2=openpyxl.load_workbook(f"{RAW}/_ext/r13/2. 2022년 주요통계___ _복호화.xlsx",data_only=True)
ws=wb2['28']
COL={2:('건강보험','적용인구 1인당 월평균보험료'),3:('직장 소계','가입자 1인당'),4:('직장 소계','적용인구 1인당'),
     5:('직장 보수월액 소계','가입자 1인당'),6:('직장 보수월액 소계','적용인구 1인당'),
     7:('직장 보수월액 일반사업장','가입자 1인당'),8:('직장 보수월액 일반사업장','적용인구 1인당'),
     9:('직장 보수월액 공ㆍ교','가입자 1인당'),10:('직장 보수월액 공ㆍ교','적용인구 1인당'),
     11:('직장 보수월액 임의계속','가입자 1인당'),12:('직장 보수월액 임의계속','적용인구 1인당'),
     13:('직장 소득월액','가입자 1인당'),14:('지역','월평균보험료')}
rows=[]
for r in range(8,ws.max_row+1):
    y=n(ws.cell(r,1).value)
    if not re.fullmatch(r'20\d\d',y): continue
    for j,(grp,ind) in COL.items():
        v=ws.cell(r,j).value
        if v is None or isinstance(v,str): continue
        rows.append([int(y),grp,ind,v])
p=f"{RAW}/R13_연도별_1인당_월평균보험료.csv"
with open(p,'w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['연도','구분','기준','월평균보험료_원']); w.writerows(rows)
print(p,len(rows))

ws=wb2['26']
C2={2:'계',3:'직장 소계',4:'직장 일반사업장',5:'직장 공ㆍ교',6:'직장 임의계속',7:'직장 소득월액',8:'지역'}
rows=[]
for r in range(6,ws.max_row+1):
    y=n(ws.cell(r,1).value)
    if not re.fullmatch(r'20\d\d',y): continue
    for j,lab in C2.items():
        v=ws.cell(r,j).value
        if v is None or isinstance(v,str): continue
        rows.append([int(y),lab,v])
p=f"{RAW}/R13_연도별_건강보험료_부과현황.csv"
with open(p,'w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['연도','구분','부과보험료_천원']); w.writerows(rows)
print(p,len(rows))
