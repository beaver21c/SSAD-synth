import pandas as pd, numpy as np
P='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
df=pd.read_parquet(P, columns=['p_labinc','labinc_sum_taxy','labinc_sum_taxn','inc_labinc_sum','inc_labinc','p_ee_deposit_amt_ptot','ee_deposit_amt_ptot','indwgt','p_dainc','dainc_sum'])
mk=df['p_labinc']>0
d=df[mk]
r=(d['p_labinc']/d['labinc_sum_taxy'])
print('ratio p_labinc/labinc_sum_taxy quantiles', r.quantile([.01,.1,.5,.9,.99]).round(4).tolist())
print('p_labinc == taxy+taxn', int((d['p_labinc']==d['labinc_sum_taxy']+d['labinc_sum_taxn'].fillna(0)).sum()), len(d))
print('p_labinc == taxy-taxn', int((d['p_labinc']==d['labinc_sum_taxy']-d['labinc_sum_taxn'].fillna(0)).sum()))
print('diff quantiles', (d['p_labinc']-d['labinc_sum_taxy']).quantile([.01,.1,.5,.9,.99]).round(1).tolist())
print('inc_labinc_sum nonnull', int(df['inc_labinc_sum'].notna().sum()), 'pos', int((df['inc_labinc_sum']>0).sum()))
e=df['ee_deposit_amt_ptot'].fillna(0)
print('p_ee == ee', (df['p_ee_deposit_amt_ptot']==e).all(), int((df['p_ee_deposit_amt_ptot']!=e).sum()))
def wq(x,w,q):
    s=pd.DataFrame({'x':x,'w':w}).dropna().groupby('x')['w'].sum().sort_index()
    c=s.cumsum(); return float(c.index[(c>=q*c.iloc[-1]).to_numpy().argmax()])
m2=df['labinc_sum_taxy']>0
print('q90 labinc_sum_taxy', wq(df.loc[m2,'labinc_sum_taxy'],df.loc[m2,'indwgt'],.9), int(m2.sum()))
