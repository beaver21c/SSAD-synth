import pandas as pd, numpy as np
P='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
df=pd.read_parquet(P)
g=df.groupby('hid')
print('hnum==size', (g['hid'].transform('size')==df['hnum']).all())
print('h_dinc==sum p_dinc', (g['p_dinc'].transform('sum')==df['h_dinc']).all(), (g['p_dinc'].transform('sum')-df['h_dinc']).abs().max())
print('h_prop==sum p_prop', (g['p_prop'].transform('sum')==df['h_prop']).all(), (g['p_prop'].transform('sum')-df['h_prop']).abs().max())
print('h_prop const in hh', (g['h_prop'].transform('nunique')==1).all())
print('one head per hh', (g['head'].transform(lambda s:(s==1).sum())==1).all())
print('hhwgt const in hh', (g['hhwgt'].transform('nunique')==1).all())
lab=df['labinc_sum_taxy'].fillna(0)
print('p_labinc==labinc_sum_taxy', (df['p_labinc']==lab).all(), int((df['p_labinc']!=lab).sum()), 'both>0 same set', ((df['p_labinc']>0)==(lab>0)).all())
print('p_labinc dtype', df['p_labinc'].dtype, 'p_dinc dtype', df['p_dinc'].dtype)
# medi vs nhi_type
print(pd.crosstab(df['nhi_type'].isin([7,8]), df['nbls_medi_yn2'].fillna(0)))
# childcare recipients age distribution (aggregate)
print(df.loc[df['childcare_yn1']==1,'age'].value_counts().sort_index().to_dict())
print('oldcare age<65', int(((df['oldcare_yn1']==1)&(df['age']<65)).sum()))
print('ltcare_bn age<65', int(((df['ltcare_bn_yn']==1)&(df['age']<65)).sum()))
print('disp_yn2 & not dis', int(((df['disp_yn2']==1)&(df['dis_yn']!=1)).sum()))
print('disvou & not sev', int(((df['disvou_act_yn1']==1)&~((df['dis_yn']==1)&(df['dis_grade_1']==1))).sum()))
print('aftsch age range', df.loc[df['pubedu_aftsch_yn']==1,'age'].agg(['min','max']).tolist())
print('govp_yn2==1 premium notna', int(((df['govp_yn2']==1)&df['govp_premium_amt'].notna()).sum()))
# independent recheck of weighted quantile via alternative implementation
def wq2(x,w,q):
    s=pd.DataFrame({'x':x,'w':w}).dropna().groupby('x')['w'].sum().sort_index()
    c=s.cumsum(); return float(c.index[(c>=q*c.iloc[-1]).to_numpy().argmax()])
eq=(g['p_dinc'].transform('sum')/np.sqrt(df['hnum']))
print('eq quantiles alt', [wq2(eq,df['indwgt'],q) for q in (.2,.4,.5,.6,.8)])
mk=df['p_labinc']>0
print('E18 alt', wq2(df.loc[mk,'p_labinc'],df.loc[mk,'indwgt'],.9))
mk=df['govp_pension_yn']==1
print('C05b alt', wq2(df.loc[mk,'govp_pension_amt'],df.loc[mk,'indwgt'],.5))
