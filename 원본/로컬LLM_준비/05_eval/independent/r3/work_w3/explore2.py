import pandas as pd, numpy as np
PQ='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
df=pd.read_parquet(PQ)
def n(q): 
    try: return len(df.query(q))
    except Exception as e: return 'ERR '+str(e)[:80]
print('--- false premise candidates (obs counts)')
for q in ['nbls_medi_type == 3','bp_yn1 == 1 and age < 65','bp_yn1 == 1 and age >= 60 and age <= 64','bp_yn2 == 1 and age < 65',
          'childbn_yn1 == 1 and age >= 10','childbn_yn1 == 1 and age >= 13 and age <= 15','childbn_yn1 == 1 and age >= 9','hnum == 1 and head == 2',
          'empins_matleave_yn1 == 1 and gender == 1','ltcare_grade == 7','dis_grade_1 == 3','dis_grade_1 >= 3','dis_grade_2 == 3',
          'bp_type == 3 and hnum == 1','nbls_medi_yn2 == 1 and (nhi_type == 5 or nhi_type == 6)','ltcare_bn_yn == 1 and age < 40',
          'np_pension_yn == 1 and age < 18','itc_hmember == 22','infantbn_yn1 == 1 and age >= 3','carebn_yn1 == 1 and age >= 8',
          'oldwork_type1_yn1 == 1 and age < 60','oldwork_type1_yn1 == 1 and age < 65','oldcare_yn1 == 1 and age < 65','nhi_pregnant_yn == 1 and gender == 1',
          'disp_yn1 == 1 and age < 18','disp_yn1 == 1 and dis_grade_1 == 2','rm_yn == 1 and age < 55','rm_yn == 1 and age < 50','youthemp_yn1 == 1 and age >= 40','youthemp_yn1 == 1 and age >= 35',
          'evou_yn == 1','culvou_yn == 1','sido == 18','sido == 0']:
    print(q,'=>',n(q))
print('--- value sets')
for v in ['nbls_medi_type','dis_grade_1','ltcare_grade','bp_type','nhi_type','itc_hmember','np_type','nbls_live_yn2','bp_yn2','nbls_medi_yn2','dis_yn','nhi_special1_yn','nhi_special4_yn','disp_yn2','dis_type_1','ltcare_bn_yn','ltcare_yn','head','hnum','unempbn_jobseekbn_type','kua_type']:
    print(v, df[v].value_counts(dropna=False).sort_index().to_dict())
print(df['age'].describe())
print('city nunique', df['city'].nunique())
