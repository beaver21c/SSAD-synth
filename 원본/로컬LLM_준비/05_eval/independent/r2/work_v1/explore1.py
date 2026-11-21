import pandas as pd, numpy as np
P='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
df=pd.read_parquet(P)
print(df.shape)
print(df['indwgt'].sum(), df.loc[df['head']==1,'hhwgt'].sum(), (df['head']==1).sum(), df['hid'].nunique())
vars_=['bp_yn1','bp_yn2','bp_type','nhi_highbp_yn','childcare_yn1','childcare_yn2','childcare_type','ee_deposit_amt_ptot','p_ee_deposit_amt_ptot','h_ee_deposit_amt_ptot','nhi_in_emergency_dur','kua_yn1','kua_yn2','kua_type','disp_bn_yn1','disp_bn_amt','p_disp_bn_amt','ltcare_yn','ltcare_bn_yn','ltcare_grade','ltcare_visit_yn','ltcare_visit_freq','ltcare_institute_yn','ltcare_institute_freq','dainc_sum','p_dainc','self_yn1','self_yn2','pubedu_aftsch_yn','pubedu_aftsch_amt','govp_yn1','govp_yn2','privschp_yn1','privschp_yn2','milp_yn1','milp_yn2','milp_premium_amt','p_milp_premium_amt','empins_matleave_yn1','empins_matleave_dur','empins_matleave_amt','empins_spouseleave_yn1','empins_spouseleave_dur','empins_parentleave_yn1','empins_postleave_yn','dis_yn','dis_grade_1','dis_disp_yn','disp_yn1','disp_yn2','pubpen_inc','unempbn_bnextended_yn','unempbn_bnextended_reason','unempbn_jobseekbn_yn','carebn_yn1','carebn_yn2','nhi_out_gehospital_dur','nhi_out_gehospital_subsidy','nhi_out_tehospital_dur','aid_live_yn1','aid_live_yn2','evou_yn','nbls_live_yn1','nbls_live_yn2','fainc_tax','fainc_sum','p_prop','h_prop','oldcare_yn1','oldcare_yn2','oldwork_type2_yn1','oldwork_type2_end_yn','childbn_yn1','childbn_yn2','nbls_edu_yn1','nbls_edu_amt1','p_nbls_edu_amt1','nhi_in_gehospital_dur','nhi_in_gehospital_amt','nhi_in_tehospital_dur','empins_yn1','empins_yn2','privschp_pension_yn','privschp_pension_amt','p_privschp_pension_amt','nhi_type','hnum','head','age','gender','sido','p_dinc','h_dinc']
for v in vars_:
    if v not in df.columns:
        print(v,'NOT IN DATA'); continue
    s=df[v]
    nn=s.notna().sum()
    nu=s.nunique(dropna=True)
    info=f"{v}: dtype={s.dtype} nonnull={nn} nunique={nu}"
    if nu<=20:
        info+=" vc="+str(s.value_counts(dropna=False).sort_index().to_dict())
    else:
        info+=f" n_zero={(s==0).sum()} n_pos={(s>0).sum()} n_neg={(s<0).sum()} q=[{s.quantile(0.01):.1f},{s.quantile(.5):.1f},{s.quantile(.99):.1f}]"
    print(info)
