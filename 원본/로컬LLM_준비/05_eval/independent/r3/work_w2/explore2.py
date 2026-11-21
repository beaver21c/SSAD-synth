import pandas as pd, numpy as np
P='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
df=pd.read_parquet(P)
pd.set_option('display.width',250); pd.set_option('display.max_rows',500); pd.set_option('display.max_columns',50)
def vc(c, top=25):
    s=df[c]; v=s.value_counts(dropna=False).sort_index()
    print('==',c, 'nuniq',s.nunique()); print(v.head(top).to_string())
print(df.age.describe())
print(pd.cut(df.age,[-1,5,7,17,34,49,64,69,74,79,84,200]).value_counts().sort_index())
for c in ['hnum','gender','head','sido','nhi_type','np_type','np_status','ltcare_grade','dis_grade_1','itc_hmember','itc_child','kua_type','bp_type','unempbn_jobseekbn_type','youthemp_type','nbls_medi_type','childcare_type','self_type2','disp_extra_type']:
    vc(c)
for c in ['nhi_out_dur','nhi_in_dur','nhi_out_fee','nhi_in_fee','nhi_out_amt','bp_dur','nbls_live_dur','childcare_dur','empins_parentleave_dur','unempbn_jobseekbn_dur','np_dur','govp_dur','oldcare_dur','h_prop','p_prop','h_dinc','p_dinc','p_labinc','ee_deposit_amt_ptot','ee_monthly_rent_amt_ptot','unempbn_jobseekbn_amt','childcare_amt','govp_pension_amt','govp_premium_amt','np_pension_amt','empins_parentleave_amt','vocaedu_amt','oldwork_type1_amt','nhi_ceiling_subsidy_amt','ltcare_visit_amt','ltcare_hbn_fee','culvou_bn','evou_amt','aid_live_amt','self_amt','nbls_edu_amt1','pubedu_aftsch_amt','disp_amt','disp_bn_amt','disvou_act_dur','nbls_live_amt','nbls_house_amt','itc_amt','ptax_sum','np_inc_amt','labinc_sum_taxy','dainc_sum']:
    s=df[c]
    print(c, 'n_notna',int(s.notna().sum()), 'n_pos',int((s>0).sum()),'n_zero',int((s==0).sum()), 'neg',int((s<0).sum()), 'q', s.quantile([.1,.25,.5,.75,.9]).round(0).tolist(), 'mean', round(s.mean(),1))
