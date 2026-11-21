import sys; sys.path.insert(0, '.')
from common import *
df = load()
w = df['indwgt']
def n(cond): 
    m = df.eval(cond, engine='python'); return int(m.fillna(False).sum())
print('age groups n:', {a: n(f'age >= {a}') for a in (60, 65, 70, 75, 80, 85)}, 'n<6', n('age < 6'), 'n<8', n('age < 8'), '6~17', n('age >= 6 and age <= 17'), '18~64', n('age >= 18 and age <= 64'), '18~34', n('age>=18 and age<=34'))
print('sido 65+ n:', df[df.age >= 65].groupby('sido').size().to_dict())
print('hnum dist(head):', df[df['head'] == 1].groupby('hs4').size().to_dict())
# 금액·기간 변수 요약(집계)
vars_ = ['nhi_out_dur','nhi_out_fee','nhi_out_amt','nhi_in_dur','nhi_in_fee','nhi_in_amt','nhi_out_clinic_dur','nhi_in_emergency_dur','nhi_ceiling_subsidy_amt','nhi_pregnant_amt',
 'p_labinc','p_binc','p_dinc','p_prop','h_prop','h_dinc','p_pubinc','p_minc','p_fininc','p_reinc','ptax_sum','ptax_housing','ee_deposit_amt_ptot','ee_monthly_rent_amt_ptot',
 'unempbn_jobseekbn_dur','unempbn_jobseekbn_amt','empins_parentleave_dur','empins_parentleave_amt','empins_matleave_amt','empins_matleave_dur','np_dur','np_inc_amt','np_pension_amt','govp_pension_amt','privschp_pension_amt','milip_pension_amt',
 'itc_amt','itc_child','itc_child_amt','nbls_live_dur','nbls_live_amt','nbls_house_amt','nbls_house_dur','aid_live_amt','aid_live_dur','self_amt','self_dur','bp_amt','bp_dur','disp_amt','disp_bn_amt','disvou_act_dur','disvou_act_subsidy','disvou_act_fee',
 'childbn_amt','childbn_dur','carebn_amt','infantbn_amt','childcare_amt','childcare_dur','oldcare_dur','pubedu_aftsch_amt','pubedu_pclot_amt','nbls_edu_amt1','nbls_edu_amt2','ltcare_visit_freq','ltcare_visit_amt','ltcare_hbn_fee','ltcare_ibn_fee','ltcare_recog_score','ltcare_institute_amt',
 'evou_amt','culvou_bn','rm_amt','vetbn_r_amt','vocaedu_amt','oldwork_type1_dur','oldwork_type1_amt','empins_premium_amt','nhi_premium_amt1_y','nhi_premium_amt3_y','nhi_premium_cal','np_premium_amt2','govp_premium_amt','kua_jobseekbn_amt','youthemp_cnt3','single_rear_amt','nhi_highmedi_num','nhi_healthlevel','dainc_sum','fainc_sum','pubpen_inc']
for v in vars_:
    x = df[v].astype(float)
    ok = x.notna()
    pos = (x > 0)
    print(f"{v:28s} n={int(ok.sum()):6d} n>0={int(pos.sum()):6d} n==0={int((x==0).sum()):6d} neg={int((x<0).sum())} wmean={ (x[ok]*w[ok]).sum()/w[ok].sum():,.1f} p25={wquant(x,w,.25):,.0f} med={wquant(x,w,.5):,.0f} p75={wquant(x,w,.75):,.0f}")
