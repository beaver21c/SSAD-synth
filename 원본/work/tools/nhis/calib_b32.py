# -*- coding: utf-8 -*-
"""B32 재현 검증: 표본 1인당 값 vs Ⅲ-4/Ⅲ-11/Ⅲ-12 전국값."""
import sys, os
sys.path.insert(0, '/mnt/share/행정데이터_set/work/tools')
os.chdir('/mnt/share/행정데이터_set/work')
import numpy as np, pandas as pd, pipeline
import importlib
b32 = importlib.import_module('importlib').import_module

df, lg, raw = pipeline.run(only={'B01', 'B02', 'B32'}, verbose=False)
t4 = pd.read_csv('params/raw/R10_3-4_요양기관종별_진료형태별_진료현황_총계.csv')
t4 = t4[t4.자격구분 == '총계']
POP = 51409978.0
INST = {'clinic': '의원', 'hospital': '병원', 'gehospital': '종합병원', 'tehospital': '상급종합병원'}
FORM = {'out': '외래', 'in': '입원'}

rows = []
N = len(df)
# 연령(19군)×성 사후층화 가중 — B01 표본의 연령 구성 왜곡(0세 4.5배 과대)을 제거한 재현오차
import importlib.util as _iu
_sp=_iu.spec_from_file_location('b32','rules/A5_B32.py'); _m=_iu.module_from_spec(_sp); _sp.loader.exec_module(_m)
pop_hi,_=_m._load_pop()
ai=_m._grp_of_age(df['age'].to_numpy()); sj=(df['gender'].to_numpy()==2).astype(int)
cnt=np.zeros((19,2))
for i in range(19):
    for j in range(2): cnt[i,j]=((ai==i)&(sj==j)).sum()
share=pop_hi/pop_hi.sum()
WW=np.where(cnt[ai,sj]>0, share[ai,sj]/np.maximum(cnt[ai,sj],1), 0.0)   # Σ=1
print('사후층화 가중 합', round(WW.sum(),4))
for fk, form in FORM.items():
    for ik, inst in list(INST.items()) + [(None, None)]:
        if ik is None:
            tgt_p = np.nan
            tgt_d = sum(float(t4[(t4.요양기관종별 == v) & (t4.진료형태 == form)].입내원일수_일.iloc[0]) for v in INST.values())
            tgt_a = sum(float(t4[(t4.요양기관종별 == v) & (t4.진료형태 == form)].진료비_천원.iloc[0]) * 1000 for v in INST.values())
            tgt_f = sum((float(t4[(t4.요양기관종별 == v) & (t4.진료형태 == form)].진료비_천원.iloc[0])
                         - float(t4[(t4.요양기관종별 == v) & (t4.진료형태 == form)].급여비_천원.iloc[0])) * 1000 for v in INST.values())
            pre = f'nhi_{fk}'
            name = f'{form} 총괄(의과4종)'
        else:
            r = t4[(t4.요양기관종별 == inst) & (t4.진료형태 == form)].iloc[0]
            tgt_p = float(r.진료실인원수_명); tgt_d = float(r.입내원일수_일)
            tgt_a = float(r.진료비_천원) * 1000; tgt_f = (float(r.진료비_천원) - float(r.급여비_천원)) * 1000
            pre = f'nhi_{fk}_{ik}'; name = f'{form} {inst}'
        s_p = (df[pre + '_dur'].notna() * WW).sum() * POP
        s_d = (df[pre + '_dur'].fillna(0) * WW).sum() * POP
        s_a = (df[pre + '_amt'].fillna(0) * WW).sum() * POP
        s_f = (df[pre + '_fee'].fillna(0) * WW).sum() * POP
        rows.append({'항목': name,
                     '실인원_목표': tgt_p, '실인원_재현': s_p,
                     '오차_실인원%': np.nan if np.isnan(tgt_p) else (s_p / tgt_p - 1) * 100,
                     '일수_목표': tgt_d, '일수_재현': s_d, '오차_일수%': (s_d / tgt_d - 1) * 100,
                     '진료비_목표': tgt_a, '진료비_재현': s_a, '오차_진료비%': (s_a / tgt_a - 1) * 100,
                     '본인부담_목표': tgt_f, '본인부담_재현': s_f, '오차_본인부담%': (s_f / tgt_f - 1) * 100})
o = pd.DataFrame(rows)
pd.set_option('display.width', 250)
print(o[['항목', '오차_실인원%', '오차_일수%', '오차_진료비%', '오차_본인부담%']].round(1).to_string(index=False))
print()
for fk, form, tq in (('out', '외래', (544734, 1721325, 977563)), ('in', '입원', (1914755, 11158830, 5165572))):
    x = df[f'nhi_{fk}_amt'].dropna()
    print(f'{form} 연간진료비  중위 {x.median():,.0f} (목표 {tq[0]:,}) | P90 {x.quantile(.9):,.0f} (목표 {tq[1]:,}) | 평균 {x.mean():,.0f} (목표 {tq[2]:,})')
print()
sc = df[['nhi_out_dur', 'nhi_in_dur']].notna().any(axis=1).mean()
print('추출대상 비율', round(sc, 4))
print('응급실 이용률(1인당 건/년, 전체)', round(df['nhi_in_emergency_dur'].fillna(0).sum() / N, 4), ' 목표 0.1615')
# 건강보험 가입자만(의료급여 제외) → Ⅲ-4 는 건강보험 기준이므로 이것이 본래의 대조군
import importlib.util as _iu2
_u=df['_u_income'].to_numpy(); hi_only=_u>=(1522292/52932270)
W2=WW*hi_only; W2=W2/W2.sum()
print()
print('── 의료급여 제외(건강보험 가입자만) · 연령성 사후층화 재현오차 ──')
r2=[]
for fk, form in FORM.items():
    for ik, inst in list(INST.items())+[(None,None)]:
        if ik is None:
            tgt_d=sum(float(t4[(t4.요양기관종별==v)&(t4.진료형태==form)].입내원일수_일.iloc[0]) for v in INST.values())
            tgt_a=sum(float(t4[(t4.요양기관종별==v)&(t4.진료형태==form)].진료비_천원.iloc[0])*1000 for v in INST.values())
            tgt_f=sum((float(t4[(t4.요양기관종별==v)&(t4.진료형태==form)].진료비_천원.iloc[0])-float(t4[(t4.요양기관종별==v)&(t4.진료형태==form)].급여비_천원.iloc[0]))*1000 for v in INST.values())
            tgt_p=np.nan; pre=f'nhi_{fk}'; name=f'{form} 총괄(의과4종)'
        else:
            r=t4[(t4.요양기관종별==inst)&(t4.진료형태==form)].iloc[0]
            tgt_p=float(r.진료실인원수_명); tgt_d=float(r.입내원일수_일); tgt_a=float(r.진료비_천원)*1000
            tgt_f=(float(r.진료비_천원)-float(r.급여비_천원))*1000; pre=f'nhi_{fk}_{ik}'; name=f'{form} {inst}'
        sp=(df[pre+'_dur'].notna()*W2).sum()*POP; sd=(df[pre+'_dur'].fillna(0)*W2).sum()*POP
        sa=(df[pre+'_amt'].fillna(0)*W2).sum()*POP; sf=(df[pre+'_fee'].fillna(0)*W2).sum()*POP
        r2.append({'항목':name,'오차_실인원%':np.nan if np.isnan(tgt_p) else (sp/tgt_p-1)*100,
                   '오차_일수%':(sd/tgt_d-1)*100,'오차_진료비%':(sa/tgt_a-1)*100,'오차_본인부담%':(sf/tgt_f-1)*100})
print(pd.DataFrame(r2).round(1).to_string(index=False))
print()
print('총괄=Σ종별 위반', int((df[['nhi_out_clinic_dur','nhi_out_hospital_dur','nhi_out_gehospital_dur','nhi_out_tehospital_dur']].sum(axis=1, min_count=1).fillna(0)
                        - df['nhi_out_dur'].fillna(0)).abs().gt(1e-6).sum()))
