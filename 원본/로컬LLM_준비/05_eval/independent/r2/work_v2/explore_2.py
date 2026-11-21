import pandas as pd, numpy as np
P='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
df=pd.read_parquet(P)
print(df.shape, df['indwgt'].sum(), df.loc[df['head']==1,'hhwgt'].sum(), df['hid'].nunique(), (df['head']==1).sum())
vars_=['ltcare_bn_yn','empins_parentleave_yn1','aid_live_yn1','aid_live_yn2','disp_yn1','disp_yn2','evou_yn','nbls_live_yn1','nbls_live_yn2',
'unempbn_jobseekbn_yn','childcare_yn1','childcare_yn2','pubedu_aftsch_yn','pubedu_pclot_yn','govp_pension_yn','privschp_pension_yn','milip_pension_yn',
'nbls_house_yn1','nbls_house_yn2','itc_yn','itc_hmember','np_pension_yn','nbls_medi_yn1','nbls_medi_yn2','nbls_medi_type','nhi_type','empins_yn1','empins_yn2',
'dis_yn','dis_grade_1','ltcare_visit_yn','ltcare_daynight_yn','oldwork_type1_yn1','kua_yn1','kua_yn2','kua_type','oldcare_yn1','oldcare_yn2','culvou_yn',
'disvou_act_yn1','np_yn','nhi_special1_yn','bp_yn1','bp_yn2','gender','head','sido','hnum']
for v in vars_:
    print(v, df[v].dtype, df[v].value_counts(dropna=False).sort_index().to_dict())
num=['nhi_out_fee','nhi_out_dur','nhi_in_dur','disp_amt','unempbn_jobseekbn_dur','childcare_dur','childcare_amt','govp_pension_amt','privschp_pension_amt','itc_amt',
'h_prop','h_dinc','p_dinc','p_prop','pubedu_aftsch_amt','empins_parentleave_dur','culvou_bn','nbls_live_amt','age']
for v in num:
    s=df[v]
    print(v, s.dtype, 'nonmiss',s.notna().sum(),'zeros',(s==0).sum(),'neg',(s<0).sum(),'min',s.min(),'max',s.max())
