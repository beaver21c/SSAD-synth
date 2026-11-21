import pandas as pd, numpy as np
P='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
df=pd.read_parquet(P)
for raw,p in [('milp_premium_amt','p_milp_premium_amt'),('privschp_pension_amt','p_privschp_pension_amt'),('empins_matleave_amt','p_empins_matleave_amt'),('disp_bn_amt','p_disp_bn_amt'),('nbls_edu_amt1','p_nbls_edu_amt1')]:
    m=df[raw].notna()
    print(raw, 'max abs diff', (df.loc[m,raw]-df.loc[m,p]).abs().max(), 'p>0 outside', ((df[p]>0)&~m).sum())
print('gehosp out dur notna == subsidy notna', (df['nhi_out_gehospital_dur'].notna()==df['nhi_out_gehospital_subsidy'].notna()).mean())
print('gehosp in dur notna == amt notna', (df['nhi_in_gehospital_dur'].notna()==df['nhi_in_gehospital_amt'].notna()).mean())
print('fainc_tax min', df['fainc_tax'].min(), 'pubpen min', df['pubpen_inc'].min())
print('indwgt/hhwgt null', df['indwgt'].isna().sum(), df['hhwgt'].isna().sum(), 'hhwgt const within hid', df.groupby('hid')['hhwgt'].nunique().max())
print('fractional values? dur', (df['empins_matleave_dur']%1!=0).sum(), (df['nhi_in_gehospital_dur']%1!=0).sum(), (df['nhi_in_tehospital_dur']%1!=0).sum())
print('spouse by sido', df.loc[df['empins_spouseleave_yn1'].eq(1),'sido'].value_counts().sort_index().to_dict())
