import pandas as pd, numpy as np
P='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
df=pd.read_parquet(P)
print(df.shape)
cb=pd.read_csv('/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/inputs/codebook.tsv',sep='\t')
print(len(cb), 'codebook vars;', sum(c in df.columns for c in cb['var']), 'in data')
print('not in data:', [c for c in cb['var'] if c not in df.columns])
print('in data not in codebook (first 100):', [c for c in df.columns if c not in set(cb['var'])][:100])
print(df['indwgt'].sum(), df.loc[df['head']==1,'hhwgt'].sum(), (df['head']==1).sum(), df['hid'].nunique())
print(df.dtypes.value_counts())
