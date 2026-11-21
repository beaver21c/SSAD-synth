import pandas as pd, numpy as np
P='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
df=pd.read_parquet(P)
print(df.shape, df['indwgt'].sum(), df.loc[df['head']==1,'hhwgt'].sum(), df['hid'].nunique(), (df['head']==1).sum())
vars_=['head','gender','age','hnum','sido','ltcare_bn_yn','dis_yn','dis_grade_1','dis_type_1','h_prop','p_prop','empins_parentleave_yn1','empins_parentleave_yn2',
'govp_pension_yn','govp_pension_amt','childcare_yn1','childcare_amt','pubedu_aftsch_yn','nbls_edu_yn1','nbls_edu_amt1','nhi_out_dur','unempbn_jobseekbn_yn','unempbn_jobseekbn_dur','unempbn_jobseekbn_amt',
'itc_yn','itc_child_yn','nhi_type','oldcare_yn1','ee_deposit_amt_ptot','p_ee_deposit_amt_ptot','np_pension_yn','nbls_house_yn2','nbls_live_yn2','nbls_live_yn1','nbls_live_amt','nhi_in_dur',
'ltcare_visit_yn','ltcare_daynight_yn','aid_live_yn1','aid_live_amt','govp_yn2','govp_yn1','govp_premium_amt','disvou_act_yn1','kua_yn1','kua_yn2','h_dinc','p_dinc','oldwork_type1_yn1','oldwork_type1_amt',
'vocaedu_yn','vocaedu_amt','nhi_ceiling_subsidy_yn','disp_yn2','disp_yn1','p_labinc','labinc_sum_taxy','bp_yn1','nbls_medi_yn1','nbls_medi_yn2','nbls_medi_type','indwgt','hhwgt']
for v in vars_:
    if v not in df.columns:
        print('MISSING', v); continue
    s=df[v]
    nn=s.notna().sum()
    nu=s.nunique(dropna=True)
    if nu<=20:
        print(v, s.dtype, 'nonnull',nn, dict(s.value_counts(dropna=False).sort_index()))
    else:
        print(v, s.dtype, 'nonnull',nn, 'zeros',int((s==0).sum()), 'neg',int((s<0).sum()), 'q', s.quantile([.1,.5,.9]).round(1).tolist())
