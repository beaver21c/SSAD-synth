from common import *
df, cb = load()
print('h_dinc == hh_dinc:', (df.h_dinc == df.hh_dinc).mean())
print('poor share (w):', (df.poor*df.indwgt).sum()/df.indwgt.sum(), 'inc5 n:', df.inc5.value_counts().sort_index().to_dict())
pairs = [('p_disp_bn_amt','disp_bn_amt'),('p_privschp_premium_amt','privschp_premium_amt'),('p_milp_premium_amt','milp_premium_amt'),
 ('p_ptax_building','ptax_building'),('p_ee_deposit_amt_ptot','ee_deposit_amt_ptot'),('p_dainc','dainc_sum'),('p_pripeninc','pripen_inc'),
 ('p_empins_matleave_amt','empins_matleave_amt'),('p_nbls_edu_amt1','nbls_edu_amt1'),('p_single_rear_amt','single_rear_amt'),('p_aid_live_amt','aid_live_amt'),
 ('p_privschp_pension_amt','privschp_pension_amt'),('p_bp_amt','bp_amt'),('p_othinc','othinc_sum_inc'),('p_fininc','fainc_sum'),('p_labinc','labinc_sum_taxy'),
 ('nhi_premium_cal','nhi_premium_set'),('youthemp_amt1','youthemp_amt2'),('p_aid_house_amt','aid_house_amt'),('p_aid_edu_amt','aid_edu_amt'),('p_single_edu_amt','single_edu_amt'),
 ('h_ee_deposit_amt_ptot','h_ee_deposit_amt_ptot'),('pubpen_inc','p_np_pension_amt')]
for a,b in pairs:
    x = df[a].fillna(0); y = df[b].fillna(0)
    print(f'{a} vs {b}: equal share={ (x==y).mean():.5f}, both>0 n={int(((x>0)&(y>0)).sum())}, a>0 only={int(((x>0)&(y<=0)).sum())}, b>0 only={int(((y>0)&(x<=0)).sum())}, mean abs rel diff(both>0)={ (abs(x-y)/y.where(y>0))[(x>0)&(y>0)].mean():.6f}')
# 가구 변수의 가구 내 일정성
for v in ['h_prop','h_ee_deposit_amt_ptot','h_ptax_building','h_dinc','h_pubinc','sido','hnum','hhwgt']:
    print(v, 'const within hh:', (df.groupby('hid')[v].nunique() == 1).mean())
# 연령 분포(집계): 제도별 5%/50%/95%
def agesumm(cond, label):
    s = df.query(cond, engine='python')
    q = s.age.quantile([.02,.5,.98]).tolist()
    print(f'{label}: n={len(s)} age p2/p50/p98={q}')
for cond,label in [('bp_yn1 == 1','기초연금'),('childbn_yn1 == 1','아동수당'),('carebn_yn1 == 1','양육수당'),('infantbn_yn1 == 1','영아수당'),('childcare_yn1 == 1','보육료'),
 ('childcare_time_yn1 == 1','시간제보육'),('childcare_longtime_yn1 == 1','시간연장'),('oldcare_yn1 == 1','노인맞춤돌봄'),('ltcare_bn_yn == 1','장기요양수급'),('ltcare_yn == 1','장기요양신청'),
 ('pubedu_aftsch_yn == 1','방과후'),('pubedu_pclot_yn == 1','교육정보화'),('nbls_edu_yn1 == 1','교육급여'),('youthemp_yn1 == 1','청년내일'),('np_pension_yn == 1','국민연금수급'),
 ('govp_pension_yn == 1','공무원연금수급'),('pubpen_inc > 0','공적연금DB'),('pripen_inc > 0','사적연금'),('empins_matleave_yn1 == 1','출산전후'),('empins_parentleave_yn1 == 1','육아휴직'),
 ('oldwork_type1_yn1 == 1','노인일자리공익'),('oldwork_type2_yn1 == 1','노인일자리사회서비스'),('disp_yn1 == 1','장애인연금'),('disp_bn_yn1 == 1','장애수당'),('dis_yn == 1','등록장애'),
 ('disvou_act_yn1 == 1','활동지원'),('aid_live_yn1 == 1','긴급생계'),('self_yn1 == 1','자활'),('kua_yn1 == 1','국취'),('unempbn_jobseekbn_yn == 1','구직급여'),('single_rear_yn1 == 1','한부모양육비'),
 ('nhi_highbp_yn == 1','고혈압입원'),('nhi_copd_yn == 1','COPD입원'),('nhi_cardiac_yn == 1','심부전입원'),('nhi_highbp_yn.notna()','만성질환변수 비결측'),('nhi_in_dur > 0','입원'),
 ('nhi_in_emergency_dur > 0','응급실'),('rm_yn == 1','주택연금'),('evou_yn == 1','에너지바우처'),('culvou_yn == 1','문화누리'),('itc_yn == 1','근로장려'),('nbls_live_yn1 == 1','생계급여'),('nbls_medi_yn1 == 1','의료급여'),
 ('milp_yn1 == 1','군인연금가입'),('privschp_yn1 == 1','사학가입'),('govp_yn1 == 1','공무원가입'),('nhi_special4_yn == 1','치매산정특례'),('nhi_pregnant_yn == 1','임신출산진료비')]:
    agesumm(cond,label)
# 성별 분포
for cond in ['empins_matleave_yn1 == 1','empins_parentleave_yn1 == 1','empins_spouseleave_yn1 == 1','milp_yn1 == 1','nhi_pregnant_yn == 1']:
    print(cond, df.query(cond, engine='python').gender.value_counts().to_dict())
# 교차
print('nhi_in_dur>0 & highbp notna', int(((df.nhi_in_dur>0)&df.nhi_highbp_yn.notna()).sum()), 'highbp notna only', int((~(df.nhi_in_dur>0)&df.nhi_highbp_yn.notna()).sum()))
print('nhi_type by medi_yn2', pd.crosstab(df.nhi_type, df.nbls_medi_yn2.fillna(-1)).to_dict())
print('ltcare_bn_yn x grade', pd.crosstab(df.ltcare_grade.fillna(-1), df.ltcare_bn_yn).to_dict())
print('visit_yn x grade', pd.crosstab(df.ltcare_grade.fillna(-1), df.ltcare_visit_yn.fillna(-1)).to_dict())
