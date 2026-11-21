from truthlib import load, show
df = load()
S = lambda **k: k
SU = "sido in [1, 4, 9]"; NS = "sido not in [1, 4, 9]"
for name, mk in {
 '가구재산 평균(가구)': lambda p: S(measure='mean', unit='household', population=p, value_var='h_prop', by=[]),
 '가구재산 중위(가구)': lambda p: S(measure='quantile', q=0.5, unit='household', population=p, value_var='h_prop', by=[]),
 '재산세 부과 비율(18+)': lambda p: S(measure='rate', population='age >= 18 and ' + p, numerator='ptax_yn == 1', by=[]),
 '임차 보증금 평균': lambda p: S(measure='mean', population='ee_deposit_amt_ptot > 0 and ' + p, value_var='ee_deposit_amt_ptot', by=[]),
 '월차임 평균': lambda p: S(measure='mean', population='ee_monthly_rent_amt_ptot > 0 and ' + p, value_var='ee_monthly_rent_amt_ptot', by=[]),
 '근로소득 평균(18~64)': lambda p: S(measure='mean', population='age >= 18 and age <= 64 and p_labinc > 0 and ' + p, value_var='p_labinc', by=[]),
 '빈곤율65+': lambda p: S(measure='poverty_rate', population='age >= 65 and ' + p, by=[]),
 '양육수당 0~6': lambda p: S(measure='rate', population='age <= 6 and ' + p, numerator='carebn_yn2 == 1', by=[]),
 '에너지바우처': lambda p: S(measure='count', population='evou_yn == 1 and ' + p, by=[]),
 '주거급여 12월': lambda p: S(measure='rate', population=p, numerator='nbls_house_yn2 == 1', by=[]),
}.items():
    a = show(mk(SU), name + ' 수도권'); b = show(mk(NS), name + ' 비수도권')
print(df['ee_deposit_amt_ptot'].notna().sum(), (df['ee_deposit_amt_ptot'] > 0).sum(), (df['ee_monthly_rent_amt_ptot'] > 0).sum())
for name, mk in {
 '근로장려금 평균': lambda g: S(measure='mean', population='itc_yn == 1 and gender == %d' % g, value_var='itc_amt', by=[]),
 '노인일자리 인원': lambda g: S(measure='count', population='oldwork_type1_yn1 == 1 and gender == %d' % g, by=[]),
 '구직급여 일수': lambda g: S(measure='mean', population='unempbn_jobseekbn_yn == 1 and gender == %d' % g, value_var='unempbn_jobseekbn_dur', by=[]),
 '자활 인원': lambda g: S(measure='count', population='self_yn1 == 1 and gender == %d' % g, by=[]),
 '산재 일시금 인원': lambda g: S(measure='count', population='occupins_lump_yn == 1 and gender == %d' % g, by=[]),
}.items():
    show(mk(1), name + ' 남'); show(mk(2), name + ' 여')
print('itc_amt notna & itc_yn', df.loc[df['itc_yn'] == 1, 'itc_amt'].notna().sum(), (df['itc_yn'] == 1).sum(), df.loc[df['itc_yn'] == 0, 'itc_amt'].notna().sum())
