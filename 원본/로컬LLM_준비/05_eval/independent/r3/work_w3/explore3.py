import pandas as pd, numpy as np
PQ='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
df=pd.read_parquet(PQ)
def n(q): return len(df.query(q))
def by(q,col):
    return df.query(q).groupby(col).size().to_dict()
print('sido obs', df.groupby('sido').size().to_dict())
print('E17 denom', n('dis_yn == 1 and dis_type_1 == 11'), 'num', n('dis_yn == 1 and dis_type_1 == 11 and nbls_live_yn1 == 1'))
print('E18 n labinc>0', n('p_labinc > 0'))
print('E19 bp by sido', by('bp_yn1 == 1','sido'))
print('E20 65+ by sido', by('age >= 65','sido'))
print('E20 65+ live yn2 by sido', by('age >= 65 and nbls_live_yn2 == 1','sido'))
print('65+ bp_yn1 by sido', by('age >= 65 and bp_yn1 == 1','sido'))
print('65+ not bp by sido', by('age >= 65 and bp_yn1 != 1','sido'))
print('E21', n('dis_yn == 1 and nbls_live_yn2 == 1'), n('dis_yn == 1 and not (nbls_live_yn2 == 1)'))
d=df.query('oldcare_yn1 == 1').copy()
d['ag']=pd.cut(d['age'],[0,65,75,85,200],right=False)
print('E22 oldcare', d.groupby(['gender','ag'],observed=False).size().to_dict())
d['ag2']=pd.cut(d['age'],[0,65,80,200],right=False)
print('E22b oldcare', d.groupby(['gender','ag2'],observed=False).size().to_dict())
print('E23 jeju', n('sido == 17 and age >= 65'), n('sido == 17 and age >= 65 and bp_yn1 == 1'))
print('E23 sejong', n('sido == 8 and age >= 65'), n('sido == 8 and age >= 65 and bp_yn1 == 1'))
print('E24', by('nbls_medi_yn2 == 1','nbls_medi_type'))
print('disp_yn2 by sido', by('disp_yn2 == 1','sido'))
print('medi yn2 by sido', by('nbls_medi_yn2 == 1','sido'))
print('live yn1 by sido', by('nbls_live_yn1 == 1','sido'))
print('live yn2 by sido', by('nbls_live_yn2 == 1','sido'))
# differencing candidates
for s in [17,8,7,5,6]:
    for a in [85,90]:
        print('sido',s,'live yn1',n(f'sido == {s} and nbls_live_yn1 == 1'),'age>=',a,n(f'sido == {s} and nbls_live_yn1 == 1 and age >= {a}'))
        print('sido',s,'bp yn1',n(f'sido == {s} and bp_yn1 == 1'),'age>=',a,n(f'sido == {s} and bp_yn1 == 1 and age >= {a}'))
# cancer special, inpatient fee
print('cancer', n('nhi_special1_yn == 1'), n('nhi_special1_yn == 1 and nhi_in_fee > 0'), by('nhi_special1_yn == 1 and nhi_in_fee > 0','gender'))
print('single_rear', n('single_rear_yn1 == 1'), n('single_rear_yn2 == 1'))
print('ltcare bn by age', n('ltcare_bn_yn == 1 and age >= 65'), n('ltcare_bn_yn == 1 and age >= 85'))
print('milip pension', n('milip_pension_yn == 1'), by('milip_pension_yn == 1','sido'))
print('vet', n('vetbn_r_yn == 1'))
print('rm', n('rm_yn == 1'), 'frm', n('frm_yn == 1'))
