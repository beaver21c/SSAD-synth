import pandas as pd, numpy as np
P='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
df=pd.read_parquet(P)
print(df.shape, df['hid'].nunique(), df['indwgt'].sum(), df.loc[df['head']==1,'hhwgt'].sum(), (df['head']==1).sum())
vars_=['ltcare_bn_yn','unempbn_jobseekbn_yn','h_prop','empins_parentleave_yn1','empins_parentleave_yn2','govp_pension_yn','govp_pension_amt','aid_live_yn1','aid_live_amt','disp_yn1','disp_yn2','dis_yn','oldcare_yn1','oldcare_dur','nhi_in_dur','pubedu_aftsch_yn','pubedu_pclot_yn','oldwork_type1_yn1','childcare_yn1','nbls_house_yn2','np_pension_yn','vocaedu_yn','empins_yn2','empins_yn1','dis_grade_1','self_yn1','self_amt','privschp_pension_yn','privschp_pension_amt','empins_parentleave_amt','nbls_edu_yn1','privschp_yn2','privschp_premium_amt','empins_support_yn1','empins_support_yn2','nhi_out_dur','childbn_yn2','disvou_act_yn1','disvou_act_subsidy','p_dinc','h_dinc','empins_matleave_yn1','empins_matleave_amt','kua_yn1','nhi_ceiling_subsidy_yn','nbls_live_yn2','bp_yn1','nhi_special1_yn','nhi_out_fee','dis_type_1','age','gender','sido','hnum','head','hhwgt','indwgt']
for v in vars_:
    s=df[v]
    nn=s.notna().sum()
    desc=''
    if s.nunique(dropna=True)<=20:
        desc=str(s.value_counts(dropna=False).sort_index().to_dict())
    else:
        desc='min=%s p50=%s max=%s zeros=%d neg=%d'%(s.min(), s.median(), s.max(), (s==0).sum(), (s<0).sum())
    print(v, s.dtype, 'nonmiss',nn, desc)
