import pandas as pd, numpy as np
PQ='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
df=pd.read_parquet(PQ)
def n(q): return len(df.query(q))
def by(q,col): return df.query(q).groupby(col).size().to_dict()
print('--E17 alternatives')
for t,name in [(11,'정신'),(12,'지적'),(2,'뇌병변'),(9,'자폐')]:
    d=n(f'dis_yn == 1 and dis_type_1 == {t}')
    for num in ['nbls_live_yn1 == 1','nbls_live_yn2 == 1','nbls_medi_yn2 == 1','nbls_medi_yn1 == 1','disp_yn2 == 1','disp_yn1 == 1','dis_grade_1 == 1']:
        print(name,d,num,n(f'dis_yn == 1 and dis_type_1 == {t} and {num}'))
print('severe by sex', by('dis_yn == 1','gender'), by('dis_yn == 1 and dis_grade_1 == 1','gender'))
print('--E19 live amt by hnum')
d=df.query('nbls_live_yn1 == 1')
print(d.groupby(d['hnum'].clip(upper=4)).size().to_dict(), 'amt notna', d['nbls_live_amt'].notna().sum(), 'amt>0', (d['nbls_live_amt']>0).sum())
print('--E23 alternatives')
for s in [17,8]:
    print(s,'dis',n(f'sido == {s} and dis_yn == 1'),'severe',n(f'sido == {s} and dis_yn == 1 and dis_grade_1 == 1'),'medi yn2',n(f'sido == {s} and nbls_medi_yn2 == 1'),'ltcare bn',n(f'sido == {s} and ltcare_bn_yn == 1'),'cancer',n(f'sido == {s} and nhi_special1_yn == 1'),'house yn2',n(f'sido == {s} and nbls_house_yn2 == 1'),'65+ 1인가구',n(f'sido == {s} and age >= 65 and hnum == 1'),'65+',n(f'sido == {s} and age >= 65'))
print('--E16/E02 combos (counts only)')
for q in ['sido == 17 and milip_pension_yn == 1','sido == 17 and milip_pension_yn == 1 and gender == 1','sido == 8 and dis_yn == 1 and dis_type_1 == 5',
          'sido == 7 and rm_yn == 1','sido == 7 and rm_yn == 1 and gender == 2','sido == 10 and frm_yn == 1','sido == 8 and govp_pension_yn == 1','sido == 8 and govp_pension_yn == 1 and gender == 1 and age >= 80',
          'sido == 8 and govp_pension_yn == 1 and gender == 2','sido == 8 and ltcare_bn_yn == 1','sido == 8 and ltcare_bn_yn == 1 and gender == 1','sido == 8 and ltcare_bn_yn == 1 and age >= 90',
          'sido == 17 and dis_yn == 1 and dis_type_1 == 5','sido == 17 and dis_yn == 1 and dis_type_1 == 5 and gender == 2','sido == 17 and dis_yn == 1 and dis_type_1 == 5 and gender == 2 and nbls_medi_yn2 == 1',
          'sido == 7 and dis_yn == 1 and dis_type_1 == 11','sido == 7 and dis_yn == 1 and dis_type_1 == 11 and gender == 1','sido == 7 and dis_yn == 1 and dis_type_1 == 11 and gender == 1 and hnum == 1',
          'sido == 8 and nbls_live_yn1 == 1 and gender == 2','sido == 8 and nbls_live_yn1 == 1 and gender == 2 and age >= 65','sido == 8 and nbls_live_yn1 == 1 and age < 18',
          'sido == 8 and vetbn_r_yn == 1','sido == 8 and vetbn_r_yn == 1 and age >= 85','sido == 17 and vetbn_r_yn == 1 and age >= 85','sido == 8 and year == 1941 and gender == 1','sido == 8 and year == 1941 and gender == 1 and hnum == 2',
          'sido == 8 and year == 1941 and gender == 1 and hnum == 2 and govp_pension_yn == 1','sido == 8 and year == 1938 and gender == 2','sido == 8 and year == 1938 and gender == 2 and hnum == 1','sido == 8 and year == 1938 and gender == 2 and hnum == 1 and bp_yn1 == 1',
          'sido == 8 and year == 1944 and gender == 2 and hnum == 1','sido == 8 and year == 1950 and gender == 2 and hnum == 1','sido == 8 and year == 1947 and gender == 2 and hnum == 1','sido == 8 and year == 1947 and gender == 2 and hnum == 1 and bp_yn1 == 1',
          'hnum == 10','hnum >= 9','sido == 17 and hnum >= 8','sido == 8 and hnum >= 7',
          'sido == 17 and nbls_live_yn1 == 1 and age < 90','sido == 17 and nbls_live_yn1 == 1 and age >= 90',
          'nhi_special4_yn == 1 and age < 65','nhi_special4_yn == 1 and age < 60','sido == 6 and nhi_special4_yn == 1 and age < 65','sido == 16 and nhi_special4_yn == 1 and age < 65 and gender == 2',
          'sido == 13 and dis_yn == 1 and dis_type_1 == 9','sido == 13 and dis_yn == 1 and dis_type_1 == 9 and gender == 2','sido == 3 and dis_yn == 1 and dis_type_1 == 10 and gender == 2','sido == 3 and dis_yn == 1 and dis_type_1 == 10 and gender == 2 and age >= 80',
          'sido == 5 and dis_yn == 1 and dis_type_1 == 3','sido == 14 and dis_yn == 1 and dis_type_1 == 7','dis_yn == 1 and dis_type_1 == 7 and gender == 2','dis_yn == 1 and dis_type_1 == 7 and gender == 2 and age < 40']:
    print(q,'=>',n(q))
print('hh count hnum==10', df.query('hnum == 10 and head == 1').shape[0])
