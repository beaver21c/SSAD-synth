import pandas as pd, numpy as np
P='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
df=pd.read_parquet(P)
pd.set_option('display.width',250); pd.set_option('display.max_rows',500)
def agedist(cond,label):
    s=df.loc[df.eval(cond,engine='python'),'age']
    print(label,'n',len(s),'age q',s.quantile([0,.05,.25,.5,.75,.95,1]).tolist())
for c,l in [('childcare_yn1==1','childcare'),('nbls_edu_yn1==1','edu'),('pubedu_aftsch_yn==1','aftsch'),('pubedu_pclot_yn==1','pclot'),('oldcare_yn1==1','oldcare'),('oldwork_type1_yn1==1','oldwork1'),('childbn_yn1==1','childbn'),('ltcare_bn_yn==1','ltc'),('disp_yn1==1','disp'),('disp_bn_yn1==1','dispbn'),('disvou_act_yn1==1','disvou'),('culvou_yn==1','culvou'),('evou_yn==1','evou'),('aid_live_yn1==1','aidlive'),('self_yn1==1','self'),('unempbn_jobseekbn_yn==1','jobseek'),('empins_parentleave_yn1==1','parentleave'),('govp_yn2==1','govp'),('govp_pension_yn==1','govpen'),('np_pension_yn==1','nppen'),('kua_yn1==1','kua'),('vocaedu_yn==1','voca'),('single_rear_yn1==1','single'),('empins_matleave_yn1==1','mat'),('carebn_yn1==1','carebn'),('infantbn_yn1==1','infant'),('nhi_pregnant_yn==1','preg'),('bp_yn1==1','bp'),('nbls_live_yn2==1','live'),('nbls_house_yn2==1','house'),('nbls_medi_yn2==1','medi'),('rm_yn==1','rm'),('itc_yn==1','itc')]:
    agedist(c,l)
print('h_dinc==sum p_dinc', np.allclose(df.groupby('hid').p_dinc.transform('sum'), df.h_dinc))
print('h_prop==sum p_prop', np.allclose(df.groupby('hid').p_prop.transform('sum'), df.h_prop))
print(pd.crosstab(df.dis_disp_yn.fillna(-1), df.disp_yn2.fillna(-1)))
print(pd.crosstab(df.dis_yn.fillna(-1), df.disp_bn_yn2.fillna(-1)))
print(pd.crosstab(df.dis_grade_1.fillna(-1), df.disvou_act_yn1.fillna(-1)))
print(pd.crosstab(df.gender, df.disvou_act_yn1.fillna(-1)))
print('edu & aftsch', pd.crosstab(df.nbls_edu_yn1.fillna(-1), df.pubedu_aftsch_yn.fillna(-1)))
print('live & house', pd.crosstab(df.nbls_live_yn2.fillna(-1), df.nbls_house_yn2.fillna(-1)))
print('itc', pd.crosstab(df.itc_yn.fillna(-1), df.itc_child_yn.fillna(-1)))
print('medi nhi_out', df.loc[df.nbls_medi_yn2==1,'nhi_out_dur'].notna().mean(), df.loc[df.nbls_live_yn2==1,'nhi_out_dur'].notna().mean())
o=df[df.age>=65]
print('out_dur 65+ n', o.nhi_out_dur.notna().sum()); print(o.nhi_out_dur.value_counts().sort_index().loc[20:40].to_string())
print('in_dur'); print(df.nhi_in_dur.value_counts().sort_index().head(35).to_string())
print('jobseek dur'); v=df.unempbn_jobseekbn_dur.value_counts().sort_index(); print(v[v>40].to_string())
print('np_dur at 120', (df.np_dur==120).sum(), (df.np_dur<120).sum(), (df.np_dur<=120).sum())
for c in ['empins_parentleave_dur','childcare_dur','oldcare_dur','nbls_live_dur','empins_support_dur','np_support_dur','self_dur','aid_live_dur','disp_bn_dur','nbls_edu_dur','unempbn_npcredit_dur','rm_dur','oldwork_type1_dur']:
    print(c); print(df[c].value_counts().sort_index().to_dict())
# eval syntax tests
for e in ['sido in [1, 4, 9]','sido not in [1, 4, 9]','np_pension_yn.isna()','not (nbls_medi_yn2 == 1)','nbls_medi_yn2 != 1','age >= 65 and oldwork_type1_yn1.isna()','np_pension_yn.notna()']:
    try:
        r=df.eval(e,engine='python'); print(e,'OK',int(r.sum()))
    except Exception as ex: print(e,'ERR',repr(ex)[:200])
