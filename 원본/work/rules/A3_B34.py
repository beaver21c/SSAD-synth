# -*- coding: utf-8 -*-
"""B34 노인일자리·주택연금·농지연금·에너지바우처·문화누리  (A3 / order 7 / 38개 변수)

────────────────────────────────────────────────────────────────────────────
소스 (등급순, 모두 params/raw 에 원본 보존 · 접근일 2026-09-02)
  S1 M02 한국노인인력개발원 「2022년 노인일자리 및 사회활동 지원사업 통계동향」(2023.12, 284p)
       <표 2-1-3> 세부 창출실적 / <표 2-1-6> 월평균 활동시간·활동비 /
       <표 2-1-8·9·11> 공익활동·사회서비스형·시장형 사업운영추이(연령·성별) /
       <표 2-1-22·24·26·28> 공익활동 세부유형별 창출실적 /
       <표 2-1-43~48> 시장형사업단 세부유형별 창출실적(보수·참여개월) /
       <표 2-3-26> 중도포기 현황(사업유형별·중도포기사유별)
       → params/raw/M02_KORDI_2022노인일자리통계동향.pdf  [1차확인]
  S1/S4 M02 보건복지부 「2022년 노인일자리 및 사회활동 지원사업 운영안내」(299p)
       p.10 예산지원 기준(활동비·부대경비·참여기간) / p.48~49 공익활동 운영개요 /
       p.66 사회서비스형 운영개요 → params/raw/M02_MOHW2022_노인일자리_운영안내.pdf  [1차확인]
  S1 M02 data.go.kr 15127867 보건복지부_노인일자리 시도별(2022) → 시도 상대참여율
  S1 M03 주택금융통계시스템(HOUSTAT) T184773126728137(지급방식별 잔액) ·
       T181173126693676(지급유형별 잔액) · T189973126573724(보증잔액=신규/해지/잔액) ·
       T216423127661823(연령구간별 공급현황 2007~2022)  [1차확인]
  S2 R17 통계청 「2022년 연금통계 결과」(2024.8.22) <표16> 연금종류별 수급현황
       — 주택연금 78천명·월평균 1,216천원·중위 981천원·금액구간 5분위,
         농지연금 11천명·월평균 1,306천원  → params/raw/R17_표16_*.csv  [1차확인]
       ※ 주택연금 월지급금 금액구간 분포는 S1(HF·HOUSTAT/data.go.kr)에 2022년 표가
         없음을 확인(registry/acq_misc.md (3)절 "미확보")한 뒤 S2로 내려온 것이다.
  S1 M04 data.go.kr 15116651·15116649·15127646·15128622 한국농어촌공사 농지연금
  S1 M05 data.go.kr 15132477 에너지바우처 연도별 발급가구수 +
       산업통상자원부 2022-06-30 브리핑(가구원수별 지원단가)
  S3 M05 한국에너지공단 국회 제출자료(2024 국정감사, 오세희 의원실) 2022 미사용률 33.6%
       — 언론보도 경유(2차출처) → status:논리적추론
  S1 M06 한국문화예술위원회 「2023 통합문화이용권 사업 현장 업무보고」
       p.11·15 발급자수·지원금, p.21 세대별 합산카드 381,725매(16.5%),
       p.25 "이용자별 평균 지원금액의 90% 소진"  [1차확인(원문 열람)]

선행 블록 의존 (없으면 안전 폴백 — params note 에 명시)
  bp_yn1(B26) · ptax_housing(B05) · _is_nbls(B24) · _recog_rank(B05) · _p_earned(B03)

§7 정합성
  R19 rm_yn=1 ⇒ ptax_housing>0 ∧ age≥55   (코드에서 강제)
  R20 oldwork_type1_yn1=1 ⇒ bp_yn1=1 ∧ age≥65 (코드에서 강제)
  R24 dur : rm_dur·frm_dur 는 개월[1,12]. oldwork_type*_dur 는 코드북 단위가 **일**이므로
       [1,365] 로 생성한다(tools/consistency.py R24 는 코드북 단위를 참조하도록 수정).
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'params/raw')

MIN_EXPECTED = 3        # §4 규모 미달 기준: 기대 표본 수급자 < 3명이면 전량 NaN
DAYS_PER_MONTH = 30.44  # 참여기간(개월) → 일 환산 (365.25/12)

# ══════════════════════════════════════════════════════════════════════════
# 1. 노인일자리 (M02 KORDI 통계동향 + MOHW 운영안내) — 전부 [1차확인]
# ══════════════════════════════════════════════════════════════════════════
# <표 2-1-8·9·11> 누적참여자수
OW_TOTAL = {'type1': 716331, 'type2': 75012, 'type3': 42803}
# <표 2-1-8·9·11> 중도포기자수
OW_DROP = {'type1': 89940, 'type2': 8091, 'type3': 7381}
# <표 2-1-8·9·11> 참여자 연령 분포 (5세 구간, 명)
OW_AGE = {
    'type1': {(60, 64): 402, (65, 69): 69303, (70, 74): 177718,
              (75, 79): 222509, (80, 84): 187695, (85, 120): 58704},
    'type2': {(60, 64): 5475, (65, 69): 25737, (70, 74): 27195,
              (75, 79): 12805, (80, 84): 3374, (85, 120): 426},
    'type3': {(60, 64): 6388, (65, 69): 12241, (70, 74): 11783,
              (75, 79): 7943, (80, 84): 3651, (85, 120): 797},
}
# <표 2-1-8·9·11> 참여자 성별 (남, 여)
OW_SEX = {'type1': (208826, 507505), 'type2': (20085, 54927), 'type3': (11078, 31725)}
# <표 2-1-6> 월평균 활동비(임금), 천원 → 원.  운영안내 p.10·49·66 과 일치
OW_WAGE_M = {'type1': 270000, 'type2': 713000}      # type3 은 세부유형별 (아래)
# 운영안내 p.10 참여기간 / p.48 "평균 11개월" / p.66 사회서비스형 "10개월"
OW_RUN_MONTHS = {'type1': ([10, 11, 12], [0.30, 0.40, 0.30]), 'type2': ([10], [1.0])}
# 늦은 참여 개시(중도포기자 결원 충원 등)로 인한 개월 손실 [가정 A3-B34-1]
OW_LATE_START = ([0, 1, 2, 3, 4], [0.55, 0.20, 0.12, 0.08, 0.05])

# <표 2-1-43~48> 시장형사업단 세부유형: (누적참여인원, 중도포기, 1인당 월평균보수(원), 평균참여기간(개월))
OW3_SUB = {
    '식품제조 및 판매': (5266, 1050, 369249, 9.0),
    '공산품제작 및 판매': (7718, 1381, 346210, 9.3),
    '매장운영': (11511, 1986, 369256, 9.3),
    '지역영농': (3088, 351, 307607, 9.5),
    '운송': (2573, 650, 604410, 8.5),
    '기타': (12647, 1963, 405901, 9.5),
}
# 코드북 oldwork_type3_type 값 ← 시장형 세부유형 대분류 매핑 (그룹 내 균등배분은 [가정])
OW3_CODE = {
    '식품제조 및 판매': ['간식류(E-01)', '참기름 및 장류(E-02)', '도시락 및 반찬류(E-03)', '기타(E-04)'],
    '공산품제작 및 판매': ['비누류(E-05)', '봉제제품(E-06)', '기타(E-07)'],
    '매장운영': ['카페(E-08)', '음식점(E-09)', '매점(편의점)(E-10)', '기타(E-11)'],
    '지역영농': ['지역영농(E-12)'],
    '운송': ['아파트 택배(E-13)', '지하철 택배(E-14)', '기타(E-15)'],
    '기타': ['기타(E-19)', '기타'],
}
# <표 2-1-20·22·24·26·28> 공익활동 세부유형 누적참여인원 → 코드북 값 (합 716,331)
OW1_TYPE = {
    '노노케어(A-01)': 69270,
    '장애인 봉사(A-02)': 738, '다문화가정 봉사(A-03)': 412,
    '청소년선도 봉사(A-05)': 5530, '생활시설이용자 지원봉사(A-06)': 2761,
    '학교급식 지원봉사(A-07)': 29765, '스쿨존교통지원 봉사(A-08)': 43286,
    '보육시설 봉사(A-10)': 18030, '지역아동센터 봉사(A-11)': 6827,
    '도서관 봉사(A-12)': 6127, '공원 놀이터 등 공공시설 봉사(A-13)': 133537,
    '문화재시설 봉사(A-14)': 8963, '공공의료 및 복지시설 봉사(A-15)': 122520,
    '지역사회 환경개선 봉사(A-16)': 187699, '주정차질서 계도 봉사(A-17)': 6496,
    '지역사회안전망 구축 지원(A-18)': 20307, '기타(A-19)': 32554,
    '건강체조 취미생활 지도(A-20)': 6551, '문화공연 활동(A-21)': 1312,
    '체험활동 지원(A-22)': 1481, '경륜전수 활동(A-23)': 5005,
    '지역상생 활동작업장(A-24)': 1867, '지역 재생환경 활동(A-25)': 490,
    '지역상생활동 기타(A-26)': 4053, '시범사업(A-27))': 331,
    # 코드북에 대응 코드가 없는 3개 사업(한부모가정봉사 213 · CCTV상시관제 166 · 직접사업 40)
    '기타': 419,
}
# <표 2-3-26> 중도포기사유 (명). type2·type3 는 코드북 값 4개로 집계
OW_REASON = {
    'type1': {'전출': 2264, '사망': 2484, '수행기관 참여제한': 530, '적성·근무조건 불일치': 2261,
              '높은 노동강도': 430, '희망근로사업 참여': 391, '취업·기타일자리사업 참여': 6292,
              '동료관계': 392, '수요처·수혜자 관계': 933, '가족반대': 1294,
              '건강악화': 44518, '기타': 28151},
    'type2': {'건강악화': 3232, '적성·근무조건 불일치': 505,
              '취업·기타일자리사업 참여': 814, '기타': 3540},
    'type3': {'건강악화': 2375, '적성·근무조건 불일치': 607,
              '취업·기타일자리사업 참여': 946, '기타': 3453},
}
OW_HMEMBER_MISS_P = 0.02   # 코드북 "결측 존재" — 비율 미공표 [가정 A3-B34-2]

# ══════════════════════════════════════════════════════════════════════════
# 2. 주택연금 (HOUSTAT 2022 + R17 표16)
# ══════════════════════════════════════════════════════════════════════════
RM_STOCK_2022 = 82941     # T189973126573724 보증잔액 건수 2022
RM_STOCK_2021 = 71791     # 2021년말 잔액
RM_NEW_2022 = 14580       # 2022 보증공급(신규)
RM_TERM_DEATH = 1118      # 2022 사망해지
RM_TERM_MID = 2191        # 2022 중도해지
RM_TERM_NOEXEC = 121      # 미실행해지·약정철회 (지급 이력 없음 → 대상 제외)
RM_ELIG = RM_STOCK_2022 + RM_TERM_DEATH + RM_TERM_MID   # 86,250건 = 1일 이상 가입
# T184773126728137 지급방식별 잔액 2022 (건수)
RM_T1_MAIN = {1: 49981, 2: 21197}          # 1 종신지급 / 2 종신혼합
RM_T1_OTHER_N = 11763                      # 기타 (확정혼합·대출상환·우대지급·우대혼합·사전가입)
# data.go.kr 15134275 주택연금 월별통계(2024-06 전국 잔액 기준) 지급방식 선택비율(%)
#   → 기타 11,763건의 내부 구성비로만 사용 [가정: 2022년 세분표 미공표, 2024-06 값 원용]
RM_T1_OTHER_MIX = {3: 1.07, 4: 1.08, 5: 7.51, 6: 1.87, 7: 0.50}   # 확정혼합/대출상환/우대지급/우대혼합/사전가입
# T181173126693676 지급유형별 잔액 2022 (건수) → 코드북 rm_type2 값
RM_T2 = {4: 57597,          # 정액형
         3: 98 + 35,        # 증가형 = 증가형 + 정기증가형
         1: 1996,           # 감소형
         2: 17146,          # 전후후박형
         5: 6069}           # 증액형 = 초기증액형
# R17 <표16> 주택연금 월평균 수급금액 구간 구성비(%) · 월평균 1,216천원 · 중위 981천원
RM_AMT_EDGES = [0, 250000, 500000, 1000000, 2000000, None]
RM_AMT_W = [3.1, 12.8, 35.1, 32.7, 16.2]
RM_AMT_MEAN = 1216000
# 월지급금 상한 [가정 A3-B34-12] — R17 <표16> 최상위 구간(200만원 이상 16.2%) 내부 분포는 미공표.
# 2022년 가입주택 공시가격 상한 9억원 기준 최고령 가입자의 월지급금 개략 상한으로 절단한다.
RM_AMT_CAP = 4000000
RM_AGE_MIN = 55           # R19

# ══════════════════════════════════════════════════════════════════════════
# 3. 농지연금 (R17 표16 · M04) — 기대 표본 <3명 → 전량 NaN (§4 규모 미달)
# ══════════════════════════════════════════════════════════════════════════
FRM_TOTAL = 11000         # R17 <표16>·<표15> 2022 농지연금 수급자 11천명(65세 이상)
FRM_AMT_EDGES = [0, 250000, 500000, 1000000, 2000000, None]
FRM_AMT_W = [8.8, 11.6, 24.8, 31.2, 23.6]     # R17 <표16> 농지 구간 구성비(%)
FRM_AMT_MEAN = 1306000                         # R17 <표16> 월평균 1,306천원

# ══════════════════════════════════════════════════════════════════════════
# 4. 에너지바우처 (M05)
# ══════════════════════════════════════════════════════════════════════════
EVOU_HH_2022 = 1132911    # data.go.kr 15132477 발급 가구수(세대)
EVOU_UNIT = {1: 137200, 2: 189500, 3: 258900, 4: 347000}   # 산업부 2022.6.30 브리핑 연간 단가
EVOU_UNUSED = 0.336       # 2022 미사용률 (한국에너지공단 국회 제출자료, 언론보도 경유)
EVOU_FULLUSE_P = 0.40     # 전액 소진 가구 비율 [가정 A3-B34-3]

# ══════════════════════════════════════════════════════════════════════════
# 5. 통합문화이용권 (M06 ARKO)
# ══════════════════════════════════════════════════════════════════════════
CUL_N_2022 = 2319973      # 발급자수(명)
CUL_GRANT = 110000        # 1인당 지원금(원)
CUL_USE_RATE = 0.90       # "이용자별 평균 지원금액의 90% 소진" (ARKO 2023 업무보고 p.25)
CUL_MERGE_CARDS = 381725  # 세대별 합산 카드 매수(16.5%)
CUL_CARDS_PER_MERGE = 2   # 합산 1건당 카드 수 [가정 A3-B34-4] → 대표:부속 = 1:1
CUL_AGE_MIN = 6           # 지원대상 만 6세 이상


# ──────────────────────────────────────────────────────────────────────────
def _band_key(age, bands):
    a = int(age)
    for (lo, hi) in bands:
        if lo <= a <= hi:
            return (lo, hi)
    return None


def _alloc_exact(g, codes, weights, n):
    """소표본 범주 배정: 최대잉여법(largest remainder)으로 각 범주 인원을 확정한 뒤 무작위 배치.

    주택연금처럼 기대 표본이 10여 명뿐인 변수에서 다항추출(core.choice_p)을 쓰면
    구성비의 이산화 오차가 ±2σ ≈ ±25%p 까지 벌어진다(실제 종신지급 83.3% vs 원문 60.26%).
    비복원 정확배분은 기대값을 그대로 두면서 이 오차만 1/n 이하로 줄인다.
    """
    p = np.asarray(weights, float)
    p = p / p.sum()
    exact = p * n
    cnt = np.floor(exact).astype(int)
    rem = int(n - cnt.sum())
    if rem > 0:                              # 잔여 인원은 소수부가 큰 범주부터
        cnt[np.argsort(-(exact - cnt), kind='stable')[:rem]] += 1
    arr = np.repeat(np.asarray(codes), cnt)
    return arr[g.permutation(n)]


def _select_to_target(g, elig, score, w, target, tol=0.02, max_step=None):
    """가중 총량이 target 에 맞도록 elig 안에서 확률적으로 선택 (순차 PPS / order sampling).

    score : 상대 선택성향(>=0). 지수경쟁키 e_i = Exp(1)/score_i 를 오름차순 정렬하면
            score 에 비례하는 무작위 순서가 된다. 그 순서로 가중치를 누적해
            |누적 - target| 이 최소가 되는 지점에서 끊는다.
    → 선택확률은 score 에 비례하고, 가중 총량 오차는 최대 (가장 큰 개인가중치)/2 수준.
      특정 가중치 구간(고가중치/저가중치)에 치우치지 않는다.
    """
    idx = np.flatnonzero(elig)
    if len(idx) == 0 or target <= 0:
        return np.zeros(len(elig), dtype=bool)
    s = np.asarray(score, float)[idx]
    s = np.where(np.isfinite(s) & (s > 0), s, 0.0)
    if s.sum() <= 0:
        s = np.ones(len(idx))
    ww = np.asarray(w, float)[idx]
    e = g.exponential(size=len(idx)) / np.maximum(s, 1e-12)
    e = np.where(s > 0, e, np.inf)
    order = np.argsort(e)
    ww_o = ww[order]
    cw = np.concatenate([[0.0], np.cumsum(ww_o)])
    k = int(np.argmin(np.abs(cw - target)))
    sel_local = order[:k]
    out = np.zeros(len(elig), dtype=bool)
    out[idx[sel_local]] = True
    return out


def _rm_age_profile():
    """HOUSTAT 연령구간별 주택연금 공급현황(2007~2022 신규)을 코호트로 쌓아
    2022년말 잔액의 연령 분포를 구성한다 [논리적추론].
    가입연도 y·연령구간 b 의 신규 n(y,b) → 2022년 연령 = 구간중앙 + (2022-y)."""
    f = os.path.join(RAW, 'M03_T216423127661823_연령구간별_주택연금_공급현황.csv')
    d = pd.read_csv(f)
    d = d[(d['항목'] == '건수') & (d['분류'] != '합계')].copy()
    d['값'] = d['값'].astype(str).str.replace(',', '').astype(float)
    mid = {'60세 미만': 57, '60세 ~ 64세': 62, '65세 ~ 69세': 67,
           '70세 ~ 74세': 72, '75세 ~ 79세': 77, '80세 이상': 83}
    prof = np.zeros(101)
    for _, r in d.iterrows():
        y = int(r['연도'])
        if y > 2022:
            continue
        m = mid.get(str(r['분류']).strip())
        if m is None:
            continue
        a = int(min(100, m + (2022 - y)))
        prof[a] += float(r['값'])
    if prof.sum() <= 0:
        prof[65:90] = 1.0
    return prof / prof.sum()


def _sido_rel_oldwork():
    """15127867 시도별 참여자수 → 시도 상대참여 배율(전국 1.0 기준, 인구 미보정 근사)."""
    f = os.path.join(RAW, 'M02_15127867_2022_노인일자리_시도별_유형별.csv')
    try:
        d = pd.read_csv(f)
    except Exception:
        return None
    return d


# ══════════════════════════════════════════════════════════════════════════
def generate(df, params, ctx):
    g = core.rng('B34')
    n = len(df)
    idx = df.index
    out = pd.DataFrame(index=idx)

    age = df['age'].to_numpy()
    sex = df['gender'].to_numpy()
    hid = df['hid'].to_numpy()
    hnum = df['hnum'].to_numpy()
    ui = df['_u_income'].to_numpy() if '_u_income' in df.columns else g.random(n)
    uw = df['_u_welfare'].to_numpy() if '_u_welfare' in df.columns else g.random(n)
    uh = df['_u_health'].to_numpy() if '_u_health' in df.columns else g.random(n)
    w = df['indwgt'].to_numpy(float) if 'indwgt' in df.columns else np.full(n, 5400.0)
    hw = df['hhwgt'].to_numpy(float) if 'hhwgt' in df.columns else w
    head = df['head'].to_numpy()

    fallbacks = []

    # ── 선행 블록 의존 컬럼 (없으면 폴백) ─────────────────────────────────
    if 'bp_yn1' in df.columns:
        bp = (df['bp_yn1'].fillna(0).to_numpy() == 1)
    else:
        # [폴백] B26 미구현. S1 목표 "65세 이상 기초연금 수급률 67.4%"(R04 <2-1>)로 대체
        bp = (age >= 65) & (ui < 0.674)
        fallbacks.append('bp_yn1←(age≥65 ∧ _u_income<0.674, 수급률 67.4% R04<2-1>)')

    if 'ptax_housing' in df.columns:
        own_p = df['ptax_housing'].fillna(0).to_numpy() > 0
    elif '_h_prop' in df.columns:
        own_p = df['_h_prop'].fillna(0).to_numpy() > 0
        fallbacks.append('ptax_housing←_h_prop>0')
    else:
        # [폴백] B05 미구현 시 소득잠재변수 상위 60%를 주택소유 대리지표로 사용
        own_p = (ui >= 0.40)
        fallbacks.append('ptax_housing←_u_income≥0.40 (자가 대리지표, [가정])')
    # 주택소유는 가구 속성 → 가구 내 1명이라도 보유하면 가구 전체 True
    own_hh = pd.Series(own_p, index=idx).groupby(hid).transform('max').to_numpy().astype(bool)
    # §7 R19 는 **개인** ptax_housing>0 을 본다. B05 가 개인별 ptax_housing 을 만들었다면
    # 가구 브로드캐스트(own_hh)가 아니라 소유자 본인(own_p)만 주택연금 후보가 되어야 한다.
    # (폴백 경로에서는 개인별 소유 정보가 없으므로 own_hh 를 그대로 쓴다.)
    own_self = own_p if 'ptax_housing' in df.columns else own_hh

    if '_is_nbls' in df.columns:
        nbls = (df['_is_nbls'].fillna(0).to_numpy() == 1)
    elif '_recog_rank' in df.columns:
        nbls = (df['_recog_rank'].fillna(1).to_numpy() <= 0.078)
        fallbacks.append('_is_nbls←_recog_rank≤0.078')
    else:
        # [폴백] 기초생활 수급가구 1,699,497 / 일반가구 21,773,507 = 7.8% (targets/S1)
        nbls = (ui <= 0.078)
        fallbacks.append('_is_nbls←_u_income≤0.078 (수급가구 7.8%)')
    rank = df['_recog_rank'].fillna(1).to_numpy() if '_recog_rank' in df.columns else ui

    earn = df['_p_earned'].fillna(0).to_numpy() if '_p_earned' in df.columns else None
    if earn is None:
        fallbacks.append('_p_earned 미존재 → hmember 경제력 판정은 _u_income·연령 대리')

    # 표본 1명이 대표하는 모집단 규모 (규모 미달 판정용)
    w_mean = float(np.mean(w))
    hw_head = hw[head == 1]
    hw_mean = float(np.mean(hw_head)) if len(hw_head) else w_mean

    # ══════════════════════════════════════════════════════════════════
    # 1. 노인일자리 — type1(공익활동) → type2(사회서비스형) → type3(시장형)
    #    이중참여 금지(코드북 중도포기사유 '노인일자리사업 이중참여') → 상호배타
    # ══════════════════════════════════════════════════════════════════
    taken = np.zeros(n, dtype=bool)
    ow_sel = {}

    for t in ('type1', 'type2', 'type3'):
        tot = OW_TOTAL[t]
        bands = list(OW_AGE[t].keys())
        # R20: 공익활동은 기초연금 수급 ∧ 65+ 강제.
        #      KORDI <표 2-1-8> 의 60~64세 402명(0.06%, 지역상생활동 예외)은 R20 준수를 위해 제외하고
        #      그 인원을 65+ 구간에 비례 배분해 총량 716,331 을 보존한다 [논리적추론]
        if t == 'type1':
            elig0 = bp & (age >= 65) & (~taken)
            use_bands = [b_ for b_ in bands if b_[0] >= 65]
        else:
            elig0 = (age >= 60) & (~taken)
            use_bands = bands
        base = {b_: float(OW_AGE[t][b_]) for b_ in use_bands}
        ssum = sum(base.values())
        btgt = {b_: base[b_] * tot / ssum for b_ in use_bands}

        # 성별 배율 (참여자 성비 / 대상 성비)
        m_share = OW_SEX[t][0] / (OW_SEX[t][0] + OW_SEX[t][1])
        pm = float(w[elig0 & (sex == 1)].sum()); pf = float(w[elig0 & (sex == 2)].sum())
        base_m = pm / max(pm + pf, 1e-9)
        fac_m = (m_share / max(base_m, 1e-6)) if base_m > 0 else 1.0
        fac_f = ((1 - m_share) / max(1 - base_m, 1e-6)) if base_m < 1 else 1.0
        # 저소득·복지접촉 성향 기울기 [가정 A3-B34-5]: 노인일자리는 저소득 노인 집중
        tilt = np.where(sex == 1, fac_m, fac_f) * (1.0 + 0.6 * (0.5 - ui)) * (1.0 + 0.4 * (uw - 0.5))
        # (연령구간 × 성) 셀 층화 — 연령·성 주변분포를 동시에 재현
        tilt = np.clip(tilt, 1e-6, None)

        if tot / w_mean < MIN_EXPECTED:
            ow_sel[t] = np.zeros(n, dtype=bool)
            continue
        # 연령구간별 층화 추출 — 연령 주변분포(KORDI 원표)를 그대로 재현
        sel_all = np.zeros(n, dtype=bool)
        for b_ in use_bands:
            for sx, sh in ((1, m_share), (2, 1.0 - m_share)):
                m = elig0 & (~sel_all) & (age >= b_[0]) & (age <= b_[1]) & (sex == sx)
                sel_all |= _select_to_target(g, m, tilt, w, btgt[b_] * sh)
        # 구간 목표가 개인가중치보다 작은 소구간(예: 사회서비스형 85세+ 426명)에서
        # 0명으로 절사되어 총량이 부족해질 수 있다 → 전국 총량 기준으로 1회 보정
        got = float(w[sel_all].sum())
        if abs(got - tot) > 0.03 * tot:
            if got < tot:
                rem = elig0 & (~sel_all)
                sc = np.zeros(n)
                for b_ in use_bands:
                    m = rem & (age >= b_[0]) & (age <= b_[1])
                    pw = float(w[m].sum())
                    if pw > 0:
                        sc[m] = btgt[b_] / pw
                sel_all |= _select_to_target(g, rem, sc * tilt, w, tot - got)
            else:
                drop = _select_to_target(g, sel_all, 1.0 / np.maximum(tilt, 1e-6), w, got - tot)
                sel_all &= ~drop
        ow_sel[t] = sel_all
        taken |= sel_all

    # ── 세대구성형태(hmember) 공통 계산 ─────────────────────────────────
    # 1 가족(경제력무)동거 / 2 가족(경제력유)동거 / 3 노인부부가구 / 4 노인독신가구 / 5 기타
    sp_age = df['_spouse_age'].to_numpy(float) if '_spouse_age' in df.columns else np.full(n, np.nan)
    hhtype = df['_hhtype'].to_numpy() if '_hhtype' in df.columns else np.array(['']*n, dtype=object)
    if earn is not None:
        oth_earn = (pd.Series(np.where(earn > 0, 1, 0), index=idx).groupby(hid).transform('sum').to_numpy()
                    - np.where(earn > 0, 1, 0)) > 0
    else:
        # [폴백] 18~64세 가구원 존재 & 그 가구원의 소득성향 상위 → 경제력 있음
        wk = ((age >= 18) & (age <= 64)).astype(int)
        oth_earn = (pd.Series(wk, index=idx).groupby(hid).transform('sum').to_numpy() - wk) > 0

    hmem = np.full(n, np.nan)
    single = (hnum == 1)
    couple = (hnum == 2) & (hhtype == 'couple') & (sp_age >= 65)
    nonrel = (hhtype == 'nonrel')
    hmem = np.where(single, 4.0, np.where(couple, 3.0, np.where(nonrel, 5.0,
                    np.where(oth_earn, 2.0, 1.0))))

    # ── 유형별 변수 생성 ────────────────────────────────────────────────
    for t in ('type1', 'type2', 'type3'):
        s = ow_sel[t]
        ns = int(s.sum())
        yn = np.full(n, np.nan); dur = np.full(n, np.nan); amt = np.full(n, np.nan)
        hm = np.full(n, np.nan); endy = np.full(n, np.nan); endr = np.empty(n, dtype=object); endr[:] = None
        sub = np.empty(n, dtype=object); sub[:] = None
        if ns > 0:
            yn[s] = 1.0
            # 중도포기
            pdrop = OW_DROP[t] / OW_TOTAL[t]
            d_ = core.bernoulli(g, np.full(ns, pdrop)).astype(bool)
            endy[s] = d_.astype(float)
            # 참여개월
            if t in OW_RUN_MONTHS:
                ms, ps = OW_RUN_MONTHS[t]
                M = core.choice_p(g, ms, ps, ns).astype(float)
                lateS, lateP = OW_LATE_START
                late = core.choice_p(g, lateS, lateP, ns).astype(float)
                base = np.maximum(M - late, 1.0)
                mon = np.where(d_, np.maximum(np.round(base * g.uniform(0.10, 0.90, ns)), 1.0), base)
                wage = np.full(ns, float(OW_WAGE_M[t]))
                sig = 0.0 if t == 'type1' else 0.10
            else:
                # type3: 세부유형 배정 후 유형별 평균 참여기간·보수 적용
                names = list(OW3_SUB)
                cnt = np.array([OW3_SUB[k][0] for k in names], float)
                pick = core.choice_p(g, np.arange(len(names)), cnt, ns)
                mu_all, wage = np.empty(ns), np.empty(ns)
                for j, k in enumerate(names):
                    cn, dn, wg, mm = OW3_SUB[k]
                    m_ = (pick == j)
                    if not m_.any():
                        continue
                    dd = dn / cn
                    mu_c = (mm - dd / 2.0) / max(1.0 - dd / 2.0, 1e-6)   # 완주자 평균개월
                    mu_all[m_] = mu_c
                    wage[m_] = wg
                    # 세부유형별 중도포기율로 end_yn 재배정
                    d_[m_] = core.bernoulli(g, np.full(int(m_.sum()), dd)).astype(bool)
                endy[s] = d_.astype(float)
                mon = np.where(d_,
                               np.maximum(np.round(g.uniform(1.0, np.maximum(mu_all, 1.5), ns)), 1.0),
                               np.clip(np.round(g.normal(mu_all, 1.5, ns)), 1.0, 12.0))
                codes = []
                for j, k in enumerate(names):
                    codes.append(OW3_CODE[k])
                sv = np.empty(ns, dtype=object)
                for j, k in enumerate(names):
                    m_ = (pick == j)
                    if m_.any():
                        cc = OW3_CODE[k]
                        sv[m_] = np.asarray(cc)[g.integers(0, len(cc), int(m_.sum()))]
                sub[s] = sv
                sig = 0.45
            mon = np.clip(mon, 1.0, 12.0)
            dur[s] = np.clip(np.round(mon * DAYS_PER_MONTH), 1, 365)
            a = wage * mon
            if sig > 0:
                a = a * core.lognormal_mean(g, np.ones(ns), sig, ns)
            amt[s] = np.round(a / 1000.0) * 1000.0          # 코드북 "천원 단위 라운딩"
            amt[s] = np.maximum(amt[s], 1000.0)
            # 세대구성형태 (결측 -99999999 포함)
            hh = hmem[s].copy()
            miss = g.random(ns) < OW_HMEMBER_MISS_P
            hh[miss] = -99999999.0
            hm[s] = hh
            # 중도포기사유
            rr = OW_REASON[t]
            keys = list(rr); wts = np.array([rr[k] for k in keys], float)
            di = np.flatnonzero(s)[d_]
            if len(di) > 0:
                endr[di] = core.choice_p(g, np.asarray(keys, dtype=object), wts, len(di))
            # 공익활동 세부유형
            if t == 'type1':
                keys1 = list(OW1_TYPE); w1 = np.array([OW1_TYPE[k] for k in keys1], float)
                sub[s] = core.choice_p(g, np.asarray(keys1, dtype=object), w1, ns)

        out[f'oldwork_{t}_yn1'] = yn
        out[f'oldwork_{t}_dur'] = dur
        out[f'oldwork_{t}_amt'] = amt
        out[f'oldwork_{t}_hmember'] = hm
        if t in ('type1', 'type3'):
            out[f'oldwork_{t}_type'] = pd.Series(sub, index=idx)
        out[f'oldwork_{t}_end_yn'] = endy
        out[f'oldwork_{t}_end_reason'] = pd.Series(endr, index=idx)

    # ══════════════════════════════════════════════════════════════════
    # 2. 주택연금 (rm_*)  — R19: 주택소유 ∧ 55+ , 가구당 1명
    # ══════════════════════════════════════════════════════════════════
    rm_yn = np.full(n, np.nan); rm_t1 = np.full(n, np.nan); rm_t2 = np.full(n, np.nan)
    rm_dur = np.full(n, np.nan); rm_amt = np.full(n, np.nan)
    if RM_ELIG / w_mean >= MIN_EXPECTED:
        prof = _rm_age_profile()
        cand = own_self & (age >= RM_AGE_MIN)
        # 가구당 최고령자 1명만 후보 (주택연금 가입자 = 주택소유자 본인)
        s_age = pd.Series(np.where(cand, age, -1), index=idx)
        mx = s_age.groupby(hid).transform('max').to_numpy()
        first = cand & (age == mx)
        # 동률이면 가구주 우선, 그래도 동률이면 앞선 행
        ord_ = pd.Series(np.arange(n), index=idx)
        key = np.where(first, ord_ - 1000000 * (head == 1), 10 ** 9)
        kmin = pd.Series(key, index=idx).groupby(hid).transform('min').to_numpy()
        elig = first & (key == kmin)
        score = prof[np.clip(age, 0, 100).astype(int)] * np.ones(n)
        score = score * (1.0 + 0.5 * (ui - 0.5))        # 자산·소득 상위 편향 [가정 A3-B34-6]
        sel = _select_to_target(g, elig, score, w, RM_ELIG)
        ns = int(sel.sum())
        if ns > 0:
            rm_yn[sel] = 1.0
            # 지급방식: 2022 잔액 3분류 + 기타 내부구성비
            t1k = [1, 2] + list(RM_T1_OTHER_MIX)
            om = np.array(list(RM_T1_OTHER_MIX.values()), float)
            om = om / om.sum() * RM_T1_OTHER_N
            t1w = np.array([RM_T1_MAIN[1], RM_T1_MAIN[2]] + list(om), float)
            # 기대 표본 16명 규모라 다항추출은 이산화 오차가 커진다 → 정확배분(_alloc_exact)
            rm_t1[sel] = _alloc_exact(g, t1k, t1w, ns).astype(float)
            t2k = list(RM_T2); t2w = np.array([RM_T2[k] for k in t2k], float)
            rm_t2[sel] = _alloc_exact(g, t2k, t2w, ns).astype(float)
            # 지급기간: 2021년말 잔액 중 존속 → 12개월, 당해 신규·해지 → 1~12 균등
            p_new = RM_NEW_2022 / RM_ELIG
            p_term = (RM_TERM_DEATH + RM_TERM_MID) / RM_ELIG
            u = g.random(ns)
            part = (u < p_new + p_term)
            mon = np.where(part, g.integers(1, 13, ns), 12).astype(float)
            rm_dur[sel] = mon
            # 월지급금 → 연 지급액
            mv = core.hist_loguniform(g, RM_AMT_EDGES, RM_AMT_W, ns, pareto_alpha=2.2)
            mv = mv * (RM_AMT_MEAN / max(float(np.mean(mv)), 1e-9))
            mv = np.minimum(mv, RM_AMT_CAP)
            a = np.round(mv * mon / 1000.0) * 1000.0
            rm_amt[sel] = np.maximum(a, 1000.0)
    out['rm_yn'] = rm_yn
    out['rm_type1'] = rm_t1
    out['rm_type2'] = rm_t2
    out['rm_dur'] = rm_dur
    out['rm_amt'] = rm_amt

    # ══════════════════════════════════════════════════════════════════
    # 3. 농지연금 (frm_*) — 기대 표본 = 11,000/평균가중치 ≈ 2명 < 3 → 전량 NaN
    # ══════════════════════════════════════════════════════════════════
    for c in ('frm_yn', 'frm_start', 'frm_end', 'frm_type', 'frm_dur', 'frm_amt'):
        out[c] = np.nan
    if FRM_TOTAL / w_mean >= MIN_EXPECTED:
        # (규모 조건을 만족하는 더 큰 표본에서만 생성 — 파라미터는 params yaml 에 기록)
        elig = (age >= 65) & own_hh
        score = np.where(age >= 65, 1.0, 0.0) * (1.0 + 0.4 * (0.5 - ui))
        sel = _select_to_target(g, elig, score, w, FRM_TOTAL)
        ns = int(sel.sum())
        if ns > 0:
            out.loc[sel, 'frm_yn'] = 1.0
            yj = g.integers(2011, 2023, ns); mj = g.integers(1, 13, ns)
            out.loc[sel, 'frm_start'] = yj * 100 + mj
            out.loc[sel, 'frm_type'] = core.choice_p(g, [1, 2, 3, 4, 5],
                                                     [0.70, 0.18, 0.05, 0.05, 0.02], ns).astype(float)
            mon = np.where(yj == 2022, g.integers(1, 13, ns), 12).astype(float)
            out.loc[sel, 'frm_dur'] = mon
            mv = core.hist_loguniform(g, FRM_AMT_EDGES, FRM_AMT_W, ns, pareto_alpha=2.2)
            mv = mv * (FRM_AMT_MEAN / max(float(np.mean(mv)), 1e-9))
            out.loc[sel, 'frm_amt'] = np.maximum(np.round(mv * mon / 1000.0) * 1000.0, 0.0)

    # ══════════════════════════════════════════════════════════════════
    # 4. 에너지바우처 (evou_*) — 가구 단위, 가구주 행에 기록
    # ══════════════════════════════════════════════════════════════════
    evou_yn = np.full(n, np.nan); evou_amt = np.full(n, np.nan); evou_bal = np.full(n, np.nan)
    if EVOU_HH_2022 / hw_mean >= MIN_EXPECTED:
        # 대상: 기초생활 수급세대(생계·의료·주거·교육) 중 노인·장애인·영유아·임산부 등 포함가구
        old_hh = pd.Series((age >= 65).astype(int), index=idx).groupby(hid).transform('max').to_numpy() == 1
        kid_hh = pd.Series((age <= 6).astype(int), index=idx).groupby(hid).transform('max').to_numpy() == 1
        # 산업부 2022-06-30 브리핑 원문: 대상은 "국민기초생활보장법상 생계·의료급여 수급세대 중
        # 노인·장애인·질환자 등 더위·추위 민감계층"에 2022년 한시적으로 "주거·교육급여 수급세대 중
        # 민감계층"을 더한 범위다 → 원칙적으로 **기초생활 수급세대(_is_nbls)로 한정**한다.
        # 다만 선행 블록(B24)의 수급가구 규모가 발급 목표에 미달하면 배정이 불가능하므로
        # 그때만 차상위(하위 12%)까지 후보를 넓힌다(폴백은 ctx 에 기록).
        nbls_hh = (head == 1) & nbls
        if float(hw[nbls_hh].sum()) >= EVOU_HH_2022 * 1.02:
            elig = nbls_hh
        else:
            elig = (head == 1) & (nbls | (rank <= 0.12))
            fallbacks.append(
                f'evou_elig: 기초생활 수급가구 가중 {float(hw[nbls_hh].sum()):,.0f} < 목표 {EVOU_HH_2022:,} → 차상위 12% 포함')
        score = np.where(elig, 1.0, 0.0) * (1.0 + 0.9 * (old_hh | kid_hh)) * (1.0 + 0.5 * (0.5 - rank))
        sel = _select_to_target(g, elig, score, hw, EVOU_HH_2022)
        ns = int(sel.sum())
        if ns > 0:
            evou_yn[sel] = 1.0
            hs = np.clip(hnum[sel], 1, 4)
            unit = np.array([EVOU_UNIT[int(x)] for x in hs], float)
            evou_amt[sel] = np.round(unit / 1000.0) * 1000.0
            full = g.random(ns) < EVOU_FULLUSE_P
            m_rest = EVOU_UNUSED / max(1.0 - EVOU_FULLUSE_P, 1e-9)   # 잔여군 평균 미사용률
            m_rest = min(max(m_rest, 0.01), 0.99)
            a_ = 4.0 * m_rest; b_ = 4.0 * (1 - m_rest)
            r = g.beta(a_, b_, ns)
            r = np.where(full, 0.0, r)
            evou_bal[sel] = np.round(evou_amt[sel] * r / 1000.0) * 1000.0
    out['evou_yn'] = evou_yn
    out['evou_amt'] = evou_amt
    out['evou_bal'] = evou_bal

    # ══════════════════════════════════════════════════════════════════
    # 5. 문화누리카드 (culvou_*) — 개인 단위
    # ══════════════════════════════════════════════════════════════════
    cv_yn = np.full(n, np.nan); cv_bn = np.full(n, np.nan)
    cv_amt = np.full(n, np.nan); cv_tot = np.full(n, np.nan)
    if CUL_N_2022 / w_mean >= MIN_EXPECTED:
        elig = (age >= CUL_AGE_MIN) & (nbls | (rank <= 0.115))
        score = np.where(elig, 1.0, 0.0) * (1.0 + 0.6 * (0.5 - rank)) * (1.0 + 0.3 * (uw - 0.5))
        sel = _select_to_target(g, elig, score, w, CUL_N_2022)
        ns = int(sel.sum())
        if ns > 0:
            cv_yn[sel] = 1.0
            # 합산카드 여부: 발급카드의 16.5%가 합산 참여, 대표:부속 = 1:1 [가정]
            p_merge = CUL_MERGE_CARDS / CUL_N_2022
            u = g.random(ns)
            is_sub = u < p_merge / CUL_CARDS_PER_MERGE
            is_rep = (u >= p_merge / CUL_CARDS_PER_MERGE) & (u < p_merge)
            # 소진율: 평균 90% 소진 (ARKO p.25). 완전소진 55% + Beta(3.5,1) 혼합 [가정]
            fu = g.random(ns) < 0.55
            rr = np.where(fu, 1.0, g.beta(3.5, 1.0, ns))
            total = np.full(ns, float(CUL_GRANT))
            # 부속카드: 합산 시점까지 사용한 금액만 남음 (잔액 0, total < 11만원)
            sub_use = np.round(CUL_GRANT * g.uniform(0.05, 0.95, ns) / 1000.0) * 1000.0
            total = np.where(is_sub, sub_use, total)
            # 대표카드: 부속의 잔액을 이전받음 (total > 11만원)
            xfer = np.round((CUL_GRANT - sub_use) / 1000.0) * 1000.0
            total = np.where(is_rep, CUL_GRANT + np.maximum(xfer, 1000.0), total)
            bn = np.where(is_sub, total, np.round(total * rr / 1000.0) * 1000.0)
            bn = np.minimum(bn, total)
            cv_tot[sel] = total
            cv_bn[sel] = bn
            cv_amt[sel] = total - bn
    out['culvou_yn'] = cv_yn
    out['culvou_bn'] = cv_bn
    out['culvou_amt'] = cv_amt
    out['culvou_total'] = cv_tot

    # ── 정수화 (_amt·_dur) ─────────────────────────────────────────────
    for c in out.columns:
        if c.endswith(('_amt', '_bn', '_bal', '_total', '_dur', '_start', '_end')):
            if out[c].dtype.kind in 'fc':
                out[c] = out[c].astype('float64')

    ctx.setdefault('B34_fallbacks', fallbacks)
    return out
