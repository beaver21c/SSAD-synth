import csv, re, sys
import pandas as pd
CB='/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/inputs/codebook.tsv'
PQ='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
rows=list(csv.DictReader(open(CB,encoding='utf-8'),delimiter='\t'))
cbvars=[r['var'] for r in rows]
text=open(CB,encoding='utf-8').read()
kws=['학력','교육수준','산업','직종','직업','종사상','혼인','배우자 유무','국적','다문화','외국인','흡연','음주','검진','비만','부모급여','첫만남','장학','사망','읍면동','행정동','출산','실손','민간보험','주거형태','점유','자가','만족','근로시간','사업체','기업규모','암','치매','자살','우울','정신','한부모','차상위','기준중위','청년','월세','농어','도시','수도권','이주','북한','노숙','시설','주택연금','에너지','문화','통신','요금','감면','국가유공','보훈','체납','연체','부채','대출','금융자산','자동차','근로능력','취업','실업','구직','경제활동']
for k in kws:
    hits=[r['var'] for r in rows if k in r['name_ko'] or k in r['program'] or k in r['content'] or k in r['codes']]
    print(k, len(hits), hits[:8])
df=pd.read_parquet(PQ)
print(df.shape)
extra=[c for c in df.columns if c not in cbvars]
print('not in codebook:',extra)
missing=[c for c in cbvars if c not in df.columns]
print('codebook vars missing in data:',missing)
