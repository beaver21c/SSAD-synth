# 집계 확인 전용(개인 단위 행 출력 없음)
import csv, re, sys
import pandas as pd, numpy as np
CB='/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/inputs/codebook.tsv'
PQ='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
rows=list(csv.DictReader(open(CB,encoding='utf-8'),delimiter='\t'))
txt=lambda r:' '.join([r['var'],r['name_ko'],r['program'],r['block'],r['codes'] or '',r['content'] or ''])
kws=['학력','교육수준','직업','산업','종사상','혼인','배우자','국적','외국인','다문화','읍면동','읍','동 ','부모급여','첫만남','월세','실업률','만족','흡연','음주','BMI','검진','사망','치과','한방','약국','우울','정신','자살','출생','출산','근로시간','사업체','점유','자가','전세','아파트','차상위','재난지원','손실보전','희망적금','도약','이북','북한','아이돌봄','농어촌','수도권','도시','코로나','백신','응급','암','치매','진단','상병','질병','주민등록','식별','hid','pid','id']
for k in kws:
    hit=[r['var'] for r in rows if k in txt(r)]
    print(k,len(hit),hit[:12])
df=pd.read_parquet(PQ)
print('shape',df.shape)
cb=set(r['var'] for r in rows)
cols=set(df.columns)
print('in data not in codebook:',sorted(cols-cb)[:50])
print('in codebook not in data:',sorted(cb-cols)[:50])
