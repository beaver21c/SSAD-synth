import sys; sys.path.insert(0,'/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r3/work_w1')
import pandas as pd, numpy as np
from lib import load, compute, wquantile
pd.set_option('display.width',250); pd.set_option('display.max_rows',300)
df=load()
print('hnum==가구 행수?', (df.groupby('hid')['pid'].transform('size')==df['hnum']).mean())
print('hh_dinc==h_dinc?', np.isclose(df['hh_dinc'],df['h_dinc']).mean())
print('poverty rate all', 100*(df.poor*df.indwgt).sum()/df.indwgt.sum())
print('inc5 share', df.groupby('inc5').indwgt.sum()/df.indwgt.sum())
# 동일 내용 변수 비교
pairs=[('p_dainc','dainc_sum'),('p_pripeninc','pripen_inc'),('p_privschp_premium_amt','privschp_premium_amt'),('p_milp_premium_amt','milp_premium_amt'),
       ('p_disp_bn_amt','disp_bn_amt'),('p_nbls_edu_amt1','nbls_edu_amt1'),('p_govp_pension_amt','govp_pension_amt'),('p_ee_deposit_amt_ptot','ee_deposit_amt_ptot'),
       ('p_ptax_building','ptax_building'),('p_othinc','othinc_sum_inc'),('p_single_rear_amt','single_rear_amt'),('p_aid_live_amt','aid_live_amt'),('p_bp_amt','bp_amt'),('p_privschp_pension_amt','privschp_pension_amt')]
for a,b in pairs:
    x=df[a]; y=df[b].fillna(0)
    print(a,b,'same set>0:', ((x>0)==(y>0)).all(), 'identical:', np.isclose(x,y).all(), 'maxabsdiff', float((x-y).abs().max()), 'sum ratio', float((x*df.indwgt).sum()/(y*df.indwgt).sum()))
# 표본 규모
print(df.groupby('sido').size().to_dict())
print((df[df['head']==1]).groupby('sido').size().to_dict())
print('age>=65', (df.age>=65).sum(), 'age<=5', (df.age<=5).sum(), '7~18', df.age.between(7,18).sum())
for v in ['nhi_out_clinic_dur','nhi_out_tehospital_dur','nhi_in_gehospital_dur','nhi_in_emergency_dur','nhi_in_tehospital_dur']:
    a=v.replace('_dur','_amt')
    print(v, 'min', df[v].min(), 'dur>=1 n', (df[v]>=1).sum(), 'notna', df[v].notna().sum(), ('amt notna same' , (df[v].notna()==df[a].notna()).all()) if a in df else '')
