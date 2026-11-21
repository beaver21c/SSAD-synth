import pandas as pd, numpy as np
P="/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet"
df=pd.read_parquet(P)
print(df.shape)
print("indwgt sum",df.indwgt.sum(),"hh sum",df.loc[df['head']==1,'hhwgt'].sum(), "n head",(df['head']==1).sum(), "n hid", df.hid.nunique() if 'hid' in df else None)
vars_=["head","gender","age","hnum","sido","nhi_type",
"nhi_out_tehospital_dur","nhi_out_tehospital_amt","nbls_live_yn1","nbls_live_yn2","nbls_house_yn1","nbls_house_yn2","disp_bn_yn1","disp_bn_amt","nbls_live_amt",
"childcare_yn1","childcare_yn2","h_ee_deposit_amt_ptot","ee_deposit_amt_ptot","p_ee_deposit_amt_ptot","dis_yn","dis_type_1","bp_yn1","bp_yn2","youthemp_amt1","youthemp_yn1",
"nhi_in_gehospital_amt","nhi_in_gehospital_dur","self_yn1","self_yn2","h_pubinc","nhi_in_emergency_dur","empins_yn1","np_yn","dainc_sum","p_dainc",
"ltcare_daynight_yn","ltcare_daynight_freq","aid_live_yn1","aid_live_yn2","aid_live_amt","empins_parentleave_yn1","nbls_medi_yn1","nbls_medi_yn2","nhi_in_tehospital_amt","nhi_in_tehospital_dur",
"h_ptax_building","ptax_building","p_ptax_building","childcare_time_yn1","childcare_time_subsidy","unempbn_jobseekbn_yn","nhi_out_clinic_amt","nhi_out_clinic_dur","nhi_highbp_yn",
"ltcare_visit_yn","ltcare_visit_freq","ltcare_grade","ltcare_bn_yn","h_prop","pubedu_aftsch_yn","pubedu_aftsch_amt","pripen_inc","p_pripeninc","privschp_yn1","privschp_premium_amt",
"dis_disp_yn","disp_yn1","disp_yn2","unempbn_bnextended_yn","unempbn_bnextended_reason","empins_matleave_yn1","empins_matleave_amt","oldcare_yn1","govp_pension_yn","privschp_pension_yn","milip_pension_yn",
"privschp_pension_amt","oldwork_type2_yn1","oldwork_type2_end_yn","nbls_edu_yn1","nbls_edu_amt1","itc_yn","itc_hmember","itc_amt","empins_spouseleave_yn1","empins_spouseleave_dur",
"ltcare_institute_yn","ltcare_institute_freq","kua_yn1","kua_type","disvou_act_yn1","disvou_act_amt","p_dinc","h_dinc","indwgt","hhwgt"]
for v in vars_:
    if v not in df.columns:
        print(v,"** NOT IN DATA"); continue
    s=df[v]
    nn=s.notna().sum()
    nun=s.nunique(dropna=True)
    line=f"{v:28s} dtype={str(s.dtype):10s} notna={nn:6d} nuniq={nun:6d}"
    if nun<=20:
        vc=s.value_counts(dropna=False).sort_index()
        line+=" vc="+str({(k if pd.notna(k) else 'NA'):int(c) for k,c in vc.items()})
    else:
        sn=pd.to_numeric(s,errors='coerce')
        line+=f" n0={(sn==0).sum()} nneg={(sn<0).sum()} npos={(sn>0).sum()}"
    print(line)
