#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""시연용 자료 만들기 — 가상데이터 확대 생성본에서 주요 변수만 골라 OpenStat 화면용 CSV 를 만든다(식별자 pid·hid 제외).
  /mnt/share/행정데이터_set/.venv/bin/python make_data.py
자연어 창의 집계는 분석 함수(ssda)가 확대 생성본 전체(595개 변수)로 수행하고, 이 CSV 는 OpenStat 의 자료 화면과 메뉴 분석용이다."""
import numpy as np
import pandas as pd
from pathlib import Path

SRC = '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
OUT = Path(__file__).resolve().parent / 'openstat' / 'sample_data' / '사회보장행정데이터_가상_주요변수.csv'
SIDO = ['서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종', '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주']
d = pd.read_parquet(SRC)
w = d['indwgt'].astype(float).values
hh = d.groupby('hid')['p_dinc'].transform('sum').astype(float).values
eq = hh / np.sqrt(d['hnum'].astype(float).values)
o = np.argsort(eq, kind='stable'); cw = np.cumsum(w[o]); T = cw[-1]
wq = lambda q: eq[o][min(np.searchsorted(cw, T * q), len(eq) - 1)]
cuts = [wq(q) for q in (.2, .4, .6, .8)]; med = wq(.5)
age = d['age'].astype(int)
out = pd.DataFrame({
    '시도': [SIDO[i - 1] for i in d['sido'].astype(int)],
    '성별': np.where(d['gender'] == 1, '남', '여'),
    '연령': age,
    '연령대': pd.cut(age, [-1, 17, 34, 49, 64, 74, 200], labels=['0~17세', '18~34세', '35~49세', '50~64세', '65~74세', '75세 이상']).astype(str),
    '가구원수': np.where(d['hnum'] >= 4, '4인 이상', d['hnum'].astype(int).astype(str) + '인'),
    '가구주여부': np.where(d['head'] == 1, '가구주', '가구원'),
    '소득5분위': [f'{i + 1}분위' for i in np.digitize(eq, cuts)],
    '빈곤여부': np.where(eq < 0.5 * med, '빈곤', '비빈곤'),
    '균등화가처분소득_만원': np.round(eq / 1e4, 0),
    '개인가중치': d['indwgt'], '가구가중치': d['hhwgt'],
})
names = {'bp_yn1': '기초연금수급', 'bp_amt': '기초연금급여액', 'nbls_live_yn1': '생계급여수급', 'nbls_live_amt': '생계급여액', 'nbls_medi_yn1': '의료급여수급', 'nbls_house_yn1': '주거급여수급',
         'nbls_edu_yn1': '교육급여수급', 'np_yn': '국민연금가입', 'np_pension_yn': '국민연금수급', 'np_pension_amt': '국민연금급여액', 'empins_yn1': '고용보험가입', 'unempbn_jobseekbn_yn': '구직급여수급',
         'unempbn_jobseekbn_amt': '구직급여액', 'itc_yn': '근로장려금수급', 'itc_amt': '근로장려금액', 'childbn_yn1': '아동수당수급', 'childcare_yn1': '보육료지원', 'dis_yn': '등록장애인',
         'disp_yn1': '장애인연금수급', 'ltcare_bn_yn': '장기요양수급', 'oldwork_type1_yn1': '노인일자리공익활동', 'oldcare_yn1': '노인맞춤돌봄', 'evou_yn': '에너지바우처', 'culvou_yn': '문화누리카드',
         'aid_live_yn1': '긴급복지생계지원', 'nhi_type': '건강보험가입유형', 'p_labinc': '근로소득', 'p_businc': '사업소득', 'p_pubinc': '공적이전소득', 'p_dinc': '가처분소득', 'h_prop': '가구재산'}
for k, v in names.items():
    if k in d.columns:
        s = d[k]
        out[v] = np.where(s == 1, '예', '아니오') if k.endswith(('_yn', '_yn1', '_yn2')) else s
OUT.parent.mkdir(parents=True, exist_ok=True)
out.to_csv(OUT, index=False, encoding='utf-8-sig')
print(OUT, out.shape, f'{OUT.stat().st_size / 1e6:.1f}MB', [k for k in names if k not in d.columns])
