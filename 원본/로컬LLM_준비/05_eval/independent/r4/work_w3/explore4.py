# 집계 확인 전용(개인 단위 행 출력 없음)
import pandas as pd, numpy as np
PQ='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
df=pd.read_parquet(PQ)
def n(q): return int(df.query(q).shape[0])
qs=['sido == 17 and age >= 85 and gender == 2','sido == 17 and age >= 85 and gender == 2 and hnum == 1','sido == 17 and age >= 80 and gender == 2 and hnum == 1',
 'sido == 17 and age >= 85 and gender == 2 and hnum == 1 and bp_yn1 == 1','sido == 17 and age >= 85 and gender == 2 and hnum == 1 and bp_yn1 == 1 and nbls_live_yn1 == 1',
 'sido == 17 and age >= 75 and gender == 2 and hnum == 1','sido == 17 and age >= 75 and gender == 2 and hnum == 1 and bp_yn1 == 1 and nbls_live_yn1 == 1',
 'sido == 17 and age >= 65 and gender == 2 and hnum == 1','sido == 17 and age >= 65 and gender == 2 and hnum == 1 and nbls_live_yn1 == 1',
 'sido == 7 and age >= 90','sido == 7 and age >= 90 and gender == 1 and dis_yn == 1 and bp_yn1 == 1',
 'nhi_type in [5, 6] and nbls_medi_yn1 == 1','nhi_type in [1, 2] and nbls_medi_yn1 == 1','nhi_type in [7, 8]',
 'nbls_medi_yn1 == 1 and nhi_in_fee.notna()','nbls_medi_yn1 == 1 and nhi_out_fee.notna()','nhi_out_fee == 0','nhi_out_fee.notna()','nhi_in_fee == 0','nhi_in_fee.notna()',
 'dis_yn == 1 and nhi_out_fee.notna()','dis_yn == 1 and dis_grade_1 == 1 and nhi_out_fee.notna()','dis_yn == 1 and dis_grade_1 == 2 and nhi_out_fee.notna()',
 'dis_yn == 1 and nhi_out_fee == 0',
 'nhi_special1_yn == 1 and age < 18','nhi_special1_yn == 1 and age >= 18 and age < 65','nhi_special1_yn == 1 and age >= 65','nhi_special1_yn == 1 and nhi_out_fee.notna()',
 'disp_yn2 == 1 and gender == 1','disp_yn2 == 1 and gender == 2',
 'age >= 65','age >= 65 and bp_yn1 == 1','age >= 65 and dis_yn == 1','age >= 65 and dis_yn.isna()',
 'bp_yn1 == 1 and h_prop.notna()','bp_yn1 == 1 and h_prop == 0',
 'sido == 17 and dis_yn == 1 and disp_yn1.isna()','sido == 17 and dis_yn == 1 and p_dinc.notna()']
for q in qs:
    try: print(q,'=>',n(q))
    except Exception as e: print(q,'ERR',e)
print('65+ by sido: n, bp, non-bp')
g=df.query('age >= 65').assign(bp=lambda d:d.bp_yn1.eq(1)).groupby('sido').agg(n=('bp','size'),bp=('bp','sum'))
g['non']=g.n-g.bp; print(g.T.to_string())
print('hid per hnum consistency:', int((df.groupby('hid').size()!=df.groupby('hid')['hnum'].first()).sum()))
print('h_dinc vs sum p_dinc mismatch:', int((df.groupby('hid')['p_dinc'].transform('sum')-df['h_dinc']).abs().gt(1).sum()))
print('city n<30 count:', int((df.groupby('city').size()<30).sum()), 'of', df['city'].nunique())
print('nbls_live_yn2==1 by city: cities with 1..9 obs =', int(df.query('nbls_live_yn2 == 1').groupby('city').size().between(1,9).sum()))
print('dtypes', df[['dis_type_1','dis_grade_1','nhi_special1_yn','sido','gender','age','hnum','year']].dtypes.to_dict())
