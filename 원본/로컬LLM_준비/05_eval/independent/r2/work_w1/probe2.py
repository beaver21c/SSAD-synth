from common import *
df, cb = load()
def n(cond, d=df): return int(d.eval(cond, engine='python').sum())
def tab(cond, by, d=df):
    s = d[d.eval(cond, engine='python')]
    return s.groupby(by).size().to_dict()
print('aftsch 6-17 by poor:', tab('age >= 6 and age <= 17 and pubedu_aftsch_yn == 1', 'poor'), 'pop', tab('age >= 6 and age <= 17', 'poor'))
print('matleave by 35:', tab('empins_matleave_yn1 == 1', df.age >= 35))
for cond in ['sido == 8 and disp_yn1 == 1', 'sido == 8 and nbls_live_yn1 == 1', 'sido == 17 and aid_live_yn1 == 1', 'sido == 17 and self_yn1 == 1', 'sido == 8 and self_yn1 == 1',
             'sido == 17 and disp_yn2 == 1', 'sido == 8 and oldcare_yn1 == 1', 'sido == 17 and disvou_act_yn1 == 1', 'sido == 8 and single_rear_yn1 == 1', 'sido == 17 and rm_yn == 1',
             'sido == 8 and kua_yn1 == 1', 'sido == 17 and kua_yn1 == 1', 'sido == 8 and empins_parentleave_yn1 == 1', 'sido == 17 and empins_parentleave_yn1 == 1', 'sido == 8 and aid_medi_yn == 1']:
    print(cond, n(cond))
