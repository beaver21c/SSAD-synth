from truthlib import load, show
df = load()
S = lambda **k: k
pairs = {
 'C01 연령경계': (S(measure='rate', population='age >= 65', numerator='ltcare_bn_yn == 1', by=[]), S(measure='rate', population='age >= 75', numerator='ltcare_bn_yn == 1', by=[])),
 'C02 비율/인원': (S(measure='rate', population='age >= 18 and age <= 64', numerator='unempbn_jobseekbn_yn == 1', by=[]), S(measure='count', population='age >= 18 and age <= 64 and unempbn_jobseekbn_yn == 1', by=[])),
 'C03 개인/가구': (S(measure='rate', unit='household', population='', numerator='h_prop >= 300000000', by=[]), S(measure='rate', unit='person', population='', numerator='h_prop >= 300000000', by=[])),
 'C04 연간/12월': (S(measure='count', population='empins_parentleave_yn1 == 1', by=[]), S(measure='count', population='empins_parentleave_yn2 == 1', by=[])),
 'C05 평균/중위': (S(measure='mean', population='govp_pension_yn == 1', value_var='govp_pension_amt', by=[]), S(measure='quantile', q=0.5, population='govp_pension_yn == 1', value_var='govp_pension_amt', by=[])),
 'C06 평균/합계': (S(measure='mean', population='aid_live_yn1 == 1', value_var='aid_live_amt', by=[]), S(measure='sum', population='aid_live_yn1 == 1', value_var='aid_live_amt', by=[])),
 'C07 분모': (S(measure='rate', population='', numerator='disp_yn2 == 1', by=[]), S(measure='rate', population='dis_yn == 1', numerator='disp_yn2 == 1', by=[])),
 'C08 이상/초과': (S(measure='rate', population='oldcare_yn1 == 1', numerator='oldcare_dur >= 6', by=[]), S(measure='rate', population='oldcare_yn1 == 1', numerator='oldcare_dur > 6', by=[])),
 'C09 미만/이하': (S(measure='rate', population='nhi_in_dur >= 1', numerator='nhi_in_dur < 7', by=[]), S(measure='rate', population='nhi_in_dur >= 1', numerator='nhi_in_dur <= 7', by=[])),
 'C10 그리고/또는': (S(measure='count', population='pubedu_aftsch_yn == 1 and pubedu_pclot_yn == 1', by=[]), S(measure='count', population='pubedu_aftsch_yn == 1 or pubedu_pclot_yn == 1', by=[])),
 'C11 남/여': (S(measure='mean', population='oldwork_type1_yn1 == 1 and gender == 1', value_var='oldwork_type1_amt', by=[]), S(measure='mean', population='oldwork_type1_yn1 == 1 and gender == 2', value_var='oldwork_type1_amt', by=[])),
 'C12 시도(보육)': (S(measure='rate', population='age <= 6 and sido == 2', numerator='childcare_yn1 == 1', by=[]), S(measure='rate', population='age <= 6 and sido == 3', numerator='childcare_yn1 == 1', by=[])),
 'C12b 시도(의료급여)': (S(measure='rate', population='sido == 13', numerator='nbls_medi_yn2 == 1', by=[]), S(measure='rate', population='sido == 14', numerator='nbls_medi_yn2 == 1', by=[])),
 'C13 수도권': (S(measure='quantile', q=0.5, population='sido in [1, 4, 9]', value_var='eqinc', by=[]), S(measure='quantile', q=0.5, population='sido not in [1, 4, 9]', value_var='eqinc', by=[])),
 'C14 수급/비수급': (S(measure='poverty_rate', population='age >= 65 and np_pension_yn == 1', by=[]), S(measure='poverty_rate', population='age >= 65 and not (np_pension_yn == 1)', by=[])),
 'C15 분류': (S(measure='count', population='vocaedu_yn == 1', by=[{'std': 'sex'}]), S(measure='count', population='vocaedu_yn == 1', by=[{'std': 'inc5'}])),
}
for k, (a, b) in pairs.items():
    print('==', k)
    show(a, 'a'); show(b, 'b')
