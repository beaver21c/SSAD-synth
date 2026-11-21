import sys; sys.path.insert(0, '.')
from common import *
df = load()
def n(cond):
    return int(df.eval(cond, engine='python').fillna(False).sum())
def vc(v, cond=None, top=40):
    d = df if cond is None else df[df.eval(cond, engine='python').fillna(False)]
    s = d[v].value_counts(dropna=False).sort_index()
    out = {}
    for k, x in list(s.items())[:top]:
        try:
            kk = None if pd.isna(k) else (int(k) if float(k).is_integer() else k)
        except Exception:
            kk = k
        out[kk] = int(x)
    return out
print('oldwork1 age10', vc('age10', 'oldwork_type1_yn1 == 1'), 'min age band:', vc('age6', 'oldwork_type1_yn1 == 1'))
print('ltcare_bn age6', vc('age6', 'ltcare_bn_yn == 1'), 'by sex', vc('gender', 'ltcare_bn_yn == 1'))
print('ltcare 65+ n', n('ltcare_bn_yn == 1 and age >= 65'), '75+', n('ltcare_bn_yn == 1 and age >= 75'), '80+', n('ltcare_bn_yn == 1 and age >= 80'))
print('kua yn2 by type', vc('kua_type', 'kua_yn2 == 1'), 'yn1', vc('kua_type', 'kua_yn1 == 1'))
print('disvou yn1 by sex among dis', vc('gender', 'disvou_act_yn1 == 1 and dis_yn == 1'), 'not dis', n('disvou_act_yn1 == 1 and dis_yn.isna()'))
print('disvou age3', vc('age3', 'disvou_act_yn1 == 1'))
print('oldcare yn2 age: ==75', n('oldcare_yn2 == 1 and age == 75'), '>=75', n('oldcare_yn2 == 1 and age >= 75'), 'all', n('oldcare_yn2 == 1'), '<65', n('oldcare_yn2 == 1 and age < 65'), 'age==75 all', n('age == 75'))
print('aid_live yn1 hnum', vc('hnum', 'aid_live_yn1 == 1'), 'age3', vc('age3', 'aid_live_yn1 == 1'), 'sex', vc('gender', 'aid_live_yn1 == 1'), '& live yn2', n('aid_live_yn1 == 1 and nbls_live_yn2 == 1'))
print('self yn1 sex', vc('gender', 'self_yn1 == 1'), 'age3', vc('age3','self_yn1 == 1'))
print('live&house yn2', n('nbls_live_yn2 == 1 and nbls_house_yn2 == 1'), 'or', n('nbls_live_yn2 == 1 or nbls_house_yn2 == 1'))
print('evou among live yn2', n('evou_yn == 1 and nbls_live_yn2 == 1'), n('nbls_live_yn2 == 1'))
print('house yn2 by sido', vc('sido', 'nbls_house_yn2 == 1'))
print('medi yn2 by type', vc('nbls_medi_type', 'nbls_medi_yn2 == 1'), 'sex', vc('gender', 'nbls_medi_yn2 == 1'))
print('govp pension sex', vc('gender', 'govp_pension_yn == 1'), 'privsch', vc('gender', 'privschp_pension_yn == 1'), 'mil', vc('gender', 'milip_pension_yn == 1'))
print('pension any', n('govp_pension_yn == 1 or privschp_pension_yn == 1 or milip_pension_yn == 1'), 'all', n('govp_pension_yn == 1 and privschp_pension_yn == 1 and milip_pension_yn == 1'), 'govp&priv', n('govp_pension_yn == 1 and privschp_pension_yn == 1'))
print('np_pension 65+', n('np_pension_yn == 1 and age >= 65'), 'not', n('np_pension_yn.isna() and age >= 65'))
print('itc_yn==1 by hmember', vc('itc_hmember', 'itc_yn == 1'), 'sex', vc('gender', 'itc_yn == 1'), 'sudo', n('itc_yn == 1 and sido in [1,4,9]'))
print('dis by grade/sex/age3', vc('dis_grade_1','dis_yn == 1'), vc('gender','dis_yn == 1'), vc('age3','dis_yn == 1'))
print('dis severe by age3', vc('age3', 'dis_yn == 1 and dis_grade_1 == 1'))
print('ltcare visit/daynight by sex', vc('gender', 'ltcare_bn_yn == 1 and ltcare_visit_yn == 1'), vc('gender', 'ltcare_bn_yn == 1 and ltcare_daynight_yn == 1'), vc('gender','ltcare_bn_yn == 1'))
print('vocaedu sex', vc('gender','vocaedu_yn == 1'), 'age6', vc('age6','vocaedu_yn == 1'))
print('not test', int(df.eval('not (bp_yn2 == 1)', engine='python').sum()), int(df.eval('bp_yn2 != 1', engine='python').sum()))
print('nhi_in by 65+ women sido n', df[(df.age>=65)&(df.gender==2)&df.nhi_in_dur.notna()].groupby('sido').size().to_dict())
print('age at exactly 65', n('age == 65'), '18', n('age == 18'))
print('hnum', vc('hnum'))
print('itc_child', vc('itc_child'))
print('nhi_out_dur exact 12', n('nhi_out_dur == 12'), 'nhi_in_dur==7', n('nhi_in_dur == 7'), '<7', n('nhi_in_dur < 7'))
print('culvou sex', vc('gender','culvou_yn == 1'), 'evou', vc('gender','evou_yn == 1'), 'rm', vc('gender','rm_yn == 1'), 'vet', vc('gender','vetbn_r_yn == 1'))
