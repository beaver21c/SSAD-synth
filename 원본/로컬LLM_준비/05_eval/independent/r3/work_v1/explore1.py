import pandas as pd, numpy as np
P="/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet"
df=pd.read_parquet(P)
print(df.shape)
print("indwgt sum",df.indwgt.sum(),"hh",df.loc[df['head']==1,'hhwgt'].sum(), "n head",(df['head']==1).sum(), "n hid", df.hid.nunique())
vars_=["head","gender","age","hnum","sido","hhwgt","indwgt","p_dinc","h_prop","h_ee_deposit_amt_ptot","p_ee_deposit_amt_ptot","ee_deposit_amt_ptot","h_ptax_building","p_ptax_building","ptax_building","h_pubinc",
"bp_yn1","bp_yn2","bp_type","bp_amt","nbls_live_yn1","nhi_out_clinic_dur","nhi_out_clinic_amt","nhi_in_emergency_dur","ltcare_visit_yn","ltcare_visit_freq","ltcare_grade","ltcare_bn_yn","ltcare_yn",
"self_yn1","self_yn2","nhi_in_tehospital_amt","nhi_in_tehospital_dur","empins_yn1","empins_parentleave_yn1","empins_parentleave_yn2","childcare_time_yn1","nhi_in_gehospital_dur","nhi_in_gehospital_amt","itc_yn","itc_amt",
"aid_live_yn1","aid_live_yn2","aid_live_dur","vocaedu_yn","vocaedu_amt","milp_yn1","milp_premium_amt","pubedu_aftsch_yn","pubedu_aftsch_amt","nbls_edu_yn1","nbls_edu_amt1","dainc_sum","p_dainc","nhi_type",
"oldwork_type2_yn1","oldwork_type2_end_yn","empins_matleave_yn1","empins_matleave_dur","dis_yn","dis_grade_1","disp_yn1","disp_yn2","ltcare_daynight_yn","ltcare_daynight_freq","kua_yn1","kua_yn2","kua_type",
"childcare_yn1","disp_bn_yn1","disp_bn_amt","nhi_copd_yn","pubpen_inc","childcare_longtime_yn1","childcare_longtime_yn2","disvou_act_yn1","disvou_act_amt","unempbn_bnextended_yn","unempbn_bnextended_reason",
"oldcare_yn1","privschp_yn1","privschp_premium_amt","govp_pension_yn","govp_pension_amt","fainc_tax","fainc_sum","unempbn_jobseekbn_yn","unempbn_jobseekbn_dur"]
for v in vars_:
    if v not in df.columns:
        print("MISSING",v); continue
    s=df[v]
    nn=s.notna().sum()
    nu=s.nunique(dropna=True)
    info=f"{v:28s} {str(s.dtype):10s} nonmiss={nn:6d} nuniq={nu:6d}"
    if nu<=12:
        info+=" vc="+str(s.value_counts(dropna=False).sort_index().to_dict())
    else:
        info+=f" n_zero={(s==0).sum()} n_neg={(s<0).sum()} n_pos={(s>0).sum()}"
    print(info)
