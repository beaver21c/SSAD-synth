# 집계 확인 전용(개인 단위 행 출력 없음)
import csv
import pandas as pd, numpy as np
CB='/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/inputs/codebook.tsv'
PQ='/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
rows=list(csv.DictReader(open(CB,encoding='utf-8'),delimiter='\t'))
for k in ['재난적','장학','이용권','바우처','돌봄','월세','입원','응급','산정특례']:
    print(k,[r['var'] for r in rows if k in (r['name_ko']+r['program']+(r['content'] or ''))][:15])
df=pd.read_parquet(PQ)
def n(q): return int(df.query(q).shape[0])
print('--- value sets')
for v in ['nhi_special1_yn','nhi_special4_yn','nhi_disentitle_yn','ltcare_bn_yn','ltcare_yn','nhi_pregnant_yn','nbls_live_yn2','disp_yn2','bp_yn2','nbls_medi_yn2','dis_yn','dis_grade_1','head']:
    print(v, df[v].value_counts(dropna=False).to_dict())
print('--- dis_type_1', df['dis_type_1'].value_counts(dropna=False).to_dict())
print('--- 시도별 관측 수')
for q in ['disp_yn1 == 1','disp_yn2 == 1','nbls_live_yn2 == 1','dis_yn == 1','dis_yn == 1 and dis_type_1 == 11','disp_bn_yn1 == 1','single_rear_yn1 == 1','milip_pension_yn == 1','frm_yn == 1','rm_yn == 1','nhi_special4_yn == 1','nhi_special1_yn == 1']:
    try: print(q, df.query(q).groupby('sido').size().to_dict())
    except Exception as e: print(q,'ERR',e)
print('--- 좁힌 집단')
for q in ['sido == 8 and dis_yn == 1','sido == 8 and dis_yn == 1 and disp_yn1 == 1','sido == 8 and dis_yn == 1 and disp_yn1 != 1',
          'sido == 17 and dis_yn == 1','sido == 17 and dis_yn == 1 and disp_yn1 == 1','sido == 17 and disp_yn1 == 1 and gender == 2',
          'sido == 7 and age >= 90 and gender == 1','sido == 7 and age >= 90 and gender == 1 and dis_yn == 1','sido == 7 and age >= 85 and gender == 1 and dis_yn == 1 and hnum == 1',
          'sido == 17 and age >= 85 and gender == 2 and hnum == 1 and bp_yn1 == 1 and nbls_live_yn1 == 1',
          'sido == 17 and age >= 80 and gender == 2 and hnum == 1 and bp_yn1 == 1 and nbls_live_yn1 == 1',
          'sido == 8 and milip_pension_yn == 1','sido == 8 and govp_pension_yn == 1','sido == 8 and govp_pension_yn == 1 and age >= 80','sido == 8 and govp_pension_yn == 1 and age >= 80 and gender == 2',
          'sido == 8 and age >= 80','sido == 8 and age >= 80 and dis_yn == 1','sido == 8 and age >= 80 and dis_yn == 1 and gender == 2','sido == 8 and age >= 80 and dis_yn == 1 and gender == 2 and hnum == 1',
          'sido == 10 and dis_type_1 == 9','dis_type_1 == 9 and age >= 40','dis_type_1 == 7','sido == 6 and dis_type_1 == 5 and gender == 2 and age < 40',
          'sido == 17 and nhi_special2_yn == 1','sido == 17 and nhi_special2_yn == 1 and age < 18',
          'year == 1930 and sido == 17 and gender == 2','year == 1930 and sido == 17 and gender == 2 and hnum == 1','year == 1938 and sido == 17 and gender == 2 and hnum == 1 and bp_yn1 == 1',
          'rm_yn == 1 and sido == 13','rm_yn == 1 and sido == 13 and gender == 2','frm_yn == 1 and sido == 14',
          'sido == 5 and disvou_act_yn1 == 1','sido == 5 and disvou_act_yn1 == 1 and age < 18']:
    try: print(q,'=>',n(q))
    except Exception as e: print(q,'ERR',e)
