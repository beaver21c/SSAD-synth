# 집계 확인 전용(개인 단위 행 출력 없음)
import csv
import pandas as pd, numpy as np
CB='/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/inputs/codebook.tsv'
PQ='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
rows=list(csv.DictReader(open(CB,encoding='utf-8'),delimiter='\t'))
cb=set(r['var'] for r in rows)
df=pd.read_parquet(PQ)
print(sorted(set(df.columns)-cb))
def n(q): return int(df.query(q).shape[0])
print('--- 틀린 전제 후보(관측 수)')
for q in ['bp_yn1 == 1 and age < 60','bp_yn1 == 1 and age < 65','bp_yn1 == 1 and age >= 50 and age <= 59',
          'childbn_yn1 == 1 and age >= 10','childbn_yn1 == 1 and age >= 13 and age <= 15','childbn_yn1 == 1',
          'nbls_medi_type == 3','nbls_medi_yn1 == 1','youthemp_type == 3','youthemp_yn1 == 1','ltcare_grade == 7','ltcare_grade == 8',
          'empins_parentleave_yn1 == 1 and age >= 70','empins_parentleave_yn1 == 1 and age < 18',
          'oldwork_type1_yn1 == 1 and age < 60','oldwork_type1_yn1 == 1 and age < 65','oldwork_type1_yn1 == 1',
          'oldcare_yn1 == 1 and age < 65','oldcare_yn1 == 1','disp_yn1 == 1 and age < 18','disp_yn1 == 1',
          'disp_bn_child_yn1 == 1 and age >= 18','disp_bn_child_yn1 == 1',
          'np_type == 2','np_type == 3','sido == 18','sido == 0','hnum == 0','gender == 3',
          'infantbn_yn1 == 1 and age >= 3','infantbn_yn1 == 1','carebn_yn1 == 1 and age >= 8','carebn_yn1 == 1',
          'youthemp_yn1 == 1 and age >= 40','youthemp_yn1 == 1 and age >= 35',
          'nbls_live_dur > 12','bp_dur > 12','np_dur > 12','rm_yn == 1 and age < 55','rm_yn == 1','frm_yn == 1','frm_yn == 1 and age < 60',
          'nhi_type in [7, 8] and nbls_medi_yn2 != 1','nhi_type in [5, 6] and nbls_medi_yn2 == 1','nhi_type == 3','nhi_type == 4',
          'itc_hmember == 22','itc_hmember == 12','bp_type == 4','disp_type == 4','kua_type == 3','dis_type_1 == 16','dis_grade_1 == 3',
          'nbls_edu_yn1 == 1 and age >= 25','nbls_edu_yn1 == 1','childcare_yn1 == 1 and age >= 8','childcare_yn1 == 1',
          'evou_yn == 1','culvou_yn == 1 and age < 6','culvou_yn == 1']:
    try: print(q,'=>',n(q))
    except Exception as e: print(q,'ERR',e)
print('year range bins', df['year'].min() if False else '', pd.cut(df['year'],[1900,1930,1950,1970,1990,2010,2023]).value_counts().to_dict())
print('age>=100', n('age >= 100'), 'age==0', n('age == 0'))
print('city nunique', df['city'].nunique())
