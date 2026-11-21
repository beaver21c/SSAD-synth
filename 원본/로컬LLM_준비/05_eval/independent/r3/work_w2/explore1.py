import pandas as pd, numpy as np
P='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
df=pd.read_parquet(P)
print(df.shape)
print('wsum', df.indwgt.sum(), 'hh', df.loc[df['head']==1,'hhwgt'].sum(), df.hid.nunique())
yn=[c for c in df.columns if c.endswith('_yn') or c.endswith('_yn1') or c.endswith('_yn2')]
rows=[]
for c in yn:
    s=df[c]
    rows.append((c, int((s==1).sum()), int((s==0).sum()), int(s.isna().sum())))
pd.set_option('display.width',200); pd.set_option('display.max_rows',500)
print(pd.DataFrame(rows,columns=['var','n1','n0','nna']).to_string())
