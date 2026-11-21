import pandas as pd, numpy as np
P='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
df=pd.read_parquet(P)
print(df.shape, df['indwgt'].sum(), df.loc[df['head']==1,'hhwgt'].sum(), (df['head']==1).sum(), df['hid'].nunique())
yn=[c for c in df.columns if c.endswith('_yn') or c.endswith('_yn1') or c.endswith('_yn2')]
rows=[]
for c in yn:
    vc=df[c].value_counts(dropna=False).to_dict()
    rows.append((c, vc))
for c,vc in rows:
    print(c, {k:(int(v)) for k,v in vc.items()})
