import numpy as np, pandas as pd
from truthlib import load, show, wquantile
df = load()
# 가구 변수 일관성
print('hnum==가구 행수:', (df.groupby('hid')['hid'].transform('size') == df['hnum']).mean())
print('h_dinc==hh_dinc:', np.isclose(df['h_dinc'], df['hh_dinc']).mean(), ' h_prop 가구내 동일:', (df.groupby('hid')['h_prop'].transform('nunique') == 1).mean())
print('head per hid ==1:', (df.groupby('hid')['head'].apply(lambda s: (s == 1).sum()) == 1).mean())
for c in ['nhi_out_fee', 'nhi_out_dur', 'nhi_in_dur', 'oldcare_dur', 'childcare_dur', 'nbls_edu_dur', 'empins_parentleave_dur', 'unempbn_jobseekbn_dur', 'self_amt', 'aid_live_amt', 'govp_pension_amt', 'privschp_pension_amt', 'oldwork_type1_amt', 'np_pension_amt', 'itc_child', 'h_prop', 'p_prop', 'privschp_premium_amt', 'empins_matleave_amt', 'nbls_live_amt']:
    s = df[c]
    print(c, 'notna', int(s.notna().sum()), 'zeros', int((s == 0).sum()), 'neg', int((s < 0).sum()), 'q10/50/90', s.quantile([.1, .5, .9]).round(0).tolist())
for c in ['oldcare_dur', 'nbls_edu_dur', 'childcare_dur', 'empins_parentleave_dur', 'itc_child', 'hnum', 'ltcare_grade', 'dis_grade_1', 'unempbn_jobseekbn_type', 'nhi_type', 'np_type', 'kua_type', 'self_type2', 'bp_type']:
    print(c, df[c].value_counts(dropna=False).sort_index().to_dict())
print('nhi_in_dur 분포', df['nhi_in_dur'].describe().round(1).to_dict())
print((df['nhi_in_dur'] < 7).sum(), (df['nhi_in_dur'] <= 7).sum(), (df['nhi_out_dur'] >= 12).sum(), (df['nhi_out_dur'] > 12).sum())
# 의료급여자의 진료실적 값 유무
print('의료급여(nhi_type 7,8) 외래일수 값 있음:', df.loc[df['nhi_type'].isin([7, 8]), 'nhi_out_dur'].notna().sum(), '/', df['nhi_type'].isin([7, 8]).sum())
# 교차
def ct(a, b):
    return int(((df[a] == 1) & (df[b] == 1)).sum())
print('live&house', ct('nbls_live_yn1', 'nbls_house_yn1'), 'aftsch&pclot', ct('pubedu_aftsch_yn', 'pubedu_pclot_yn'), 'disp&dispbn', ct('disp_yn1', 'disp_bn_yn1'), 'edu&aftsch', ct('nbls_edu_yn1', 'pubedu_aftsch_yn'))
print('disp_yn2 & dis_yn', ct('disp_yn2', 'dis_yn'), 'disp_yn2', int((df['disp_yn2'] == 1).sum()))
print('aftsch age', df.loc[df['pubedu_aftsch_yn'] == 1, 'age'].describe()[['min', 'max']].tolist(), 'pclot age', df.loc[df['pubedu_pclot_yn'] == 1, 'age'].describe()[['min', 'max']].tolist(), 'edu age', df.loc[df['nbls_edu_yn1'] == 1, 'age'].describe()[['min', 'max']].tolist())
print('childcare age', df.loc[df['childcare_yn1'] == 1, 'age'].value_counts().sort_index().to_dict())
print('childbn age', df.loc[df['childbn_yn1'] == 1, 'age'].value_counts().sort_index().to_dict())
print('oldcare age min', df.loc[df['oldcare_yn1'] == 1, 'age'].min(), 'ltcare_bn age<65', int(((df['ltcare_bn_yn'] == 1) & (df['age'] < 65)).sum()))
print('parentleave by gender yn1', df.loc[df['empins_parentleave_yn1'] == 1, 'gender'].value_counts().to_dict(), 'yn2', df.loc[df['empins_parentleave_yn2'] == 1, 'gender'].value_counts().to_dict())
print('sido n', df['sido'].value_counts().sort_index().to_dict())
