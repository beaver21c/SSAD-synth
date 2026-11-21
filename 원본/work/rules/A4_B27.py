# -*- coding: utf-8 -*-
"""B27 장애 정보·장애인연금·장애수당·장애아동수당·보조기기·자립자금  (A4 / order 3)

생성 변수 27개
  장애 정보(7) : dis_yn dis_type_1 dis_type_2 dis_grade_1 dis_grade_2 dis_grade_3 dis_disp_yn
  장애인연금(8): disp_yn1 disp_yn2 disp_type disp_extra_type disp_dur disp_amt
                 disp_basic_amt disp_extra_amt
  장애수당(4)  : disp_bn_yn1 disp_bn_yn2 disp_bn_dur disp_bn_amt
  장애아동수당(4): disp_bn_child_yn1 disp_bn_child_yn2 disp_bn_child_dur disp_bn_child_amt
  보조기기(3)  : dis_device_yn dis_device_amt dis_device_type
  자립자금(1)  : diswork_loan_yn

■ 소스 (등급순)
  S1  R05 2023 보건복지통계연보 <표 4-2-2> 등록장애인 수 - 장애정도별·연령별 : 2022
      params/raw/R05_4-2-2_등록장애인수_장애정도별연령별.csv  [1차확인 2026-09-02]
      → 성×연령대×주장애유형 등록장애인 수, 성×유형×장애정도 등록장애인 수
  S1  R05 <표 4-2-15> 장애인 거주시설 유형별 입소현황 2022 = 27,946명 (인쇄 p.322)
      → 일반가구 표본에서 시설 거주자 제외 보정
  S1  R05 <표 5-3-1/5-3-2/5-3-3> 장애수당·장애아동수당·장애인연금 수급자 현황(시도별) 2022
      params/raw/R05_5-3-1·2·3_*.csv  [1차확인]  → 부가급여 구분별 수급자 총량
  S1  한국사회보장정보원 data.go.kr 15009571 복지사업 월별 급여지급 현황 2022
      → 장애인연금 월별 지급건수·지급금액 (연 4,380,987건 / 1,215,971백만원, 건당 월 277,556원)
  S1  한국사회보장정보원 data.go.kr 15062448 복지사업 시군구별 수급권자 현황 2022.12
      → 장애인연금 수급권자 362,127 / 수급가구 356,181 → 부부2인 수급 비율
  S1  한국사회보장정보원 2022 차상위 및 한부모가족 수급자 현황 통계표 <표3.5/3.7/3.9>
      → 차상위 장애급여 수급자의 월별·연령대별 구조
  S1  국민건강보험공단 data.go.kr 3073131 현금급여비(장애인보조기기) 지급현황
      → 2022년 124,110건 / 91,919,752,540원
  S1  보건복지부 사전정보공표 2022년도 장애인자립자금 융자 대출실적(시도별) = 전국 34건
      params/tab/S1_장애인자립자금_융자대출실적_시도별_2022.csv  [1차확인]
  S0  R01 <표 6-13> 장애급여 수급률 / <표 6-14> 등록장애인 비율 / <표 6-15> 중복수급
      → 조건부 구조 검증 기준 (2020년 기준)
  S0  R02 <표 6-4> 장애인·비장애인 소득·재산 분위 분포 → _u_income 기울기
  S4  2022년 장애인연금 사업안내 / 2022년 장애인복지 사업안내(Ⅰ) → 법정 단가·선정기준액
      params/raw/S4_2022_사업별_법정단가_welfare.csv  [1차확인]

■ order 3 제약
  B05(재산, order5)보다 먼저 실행되므로 `_recog_rank`·`_h_prop`·`_h_eq_inc` 를 쓸 수 없다.
  소득인정액은 개인 잠재변수 `_u_income`(+`_u_welfare` 신청성향, 가구 특성)으로 대리한다.

■ §7 정합성
  R10 disp_yn1=1 ⇒ dis_yn=1 ∧ dis_grade_1=1 ∧ age≥18   (코드에서 강제)
  R11 disp_bn_yn1=1 ⇒ dis_grade_1=2 ∧ age≥18            (코드에서 강제)
  R24 yn2⇒yn1, dur∈[1,12], amt>0 ⇔ yn1=1                (코드에서 강제)
  65+ 장애인연금–기초연금 정합은 B26(order5)에서 처리 — 여기서는 65세 이상 수급자의
  기초급여를 0원으로 두어(제도상 기초연금 전환) B26이 참조할 수 있게 한다.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

RAW = 'params/raw'
TAB = 'params/tab'
DIAG = {}          # 마지막 실행 진단값 (검증 스크립트에서 참조)

# ── 코드북 장애유형 코드 (dis_type_1/2) ─────────────────────────────────────
TYPE_CODE = {'간': 1, '뇌병변': 2, '뇌전증': 3, '시각': 4, '신장': 5, '심장': 6, '안면': 7,
             '언어': 8, '자폐성': 9, '장루요루': 10, '정신': 11, '지적': 12, '지체': 13,
             '청각': 14, '호흡기': 15}
AGE_BANDS = ['0-4', '5-9', '10-14', '15-19', '20-24', '25-29', '30-34', '35-39', '40-44',
             '45-49', '50-54', '55-59', '60-64', '65+']
MISSING = -99999999          # 코드북 결측코드

# ── [1차확인] 2022 법정 단가 (S4 2022년 장애인연금 사업안내) ────────────────
DISP_BASIC_MAX      = 307_500    # 기초급여 월 최고 (18~64세, 단독·부부1인)
DISP_BASIC_COUPLE2  = 246_000    # 부부 2인 모두 수급 시 1인당 (20% 부부감액)
# 부가급여 (만18세 이상) : {disp_extra_type: (65세 미만, 65세 이상)}
DISP_EXTRA = {5: (80_000, 387_500),    # 기초생활보장수급자(생계·의료, 일반재가)
              4: (70_000,  70_000),    # 기초생활보장수급자(주거·교육) → 차상위 단가 적용
              2: (70_000,  70_000),    # 차상위계층
              1: (20_000,  40_000)}    # 차상위초과
# 초과분 감액 계단 (2022 사업안내 <장애인연금 수급자 중 차상위계층·차상위초과자 급여액>
# 1인 수급시 기초급여액, 특례자 값 제외) [1차확인]
DISP_REDUCE_LADDER = [300_000, 280_000, 260_000, 240_000, 220_000, 200_000, 180_000,
                      160_000, 140_000, 120_000, 100_000, 80_000, 60_000, 40_000, 20_000]
# 2022 선정기준액(월 소득인정액) — 소득인정액 자체는 B05(order5) 이후에나 산출 가능하므로
# 본 블록에서는 선정 기준의 서열(저소득 우선)만 사용하고 절대액은 참조값으로 둔다.
DISP_SEL_SINGLE = 1_220_000      # 단독가구
DISP_SEL_COUPLE = 1_952_000      # 부부가구
BN_AMT_M        = 40_000         # 장애수당 월 (재가 생계·의료 / 주거·교육·차상위 동일)
BN_CHILD_AMT_M  = {(1, 'basic'): 220_000, (1, 'near'): 170_000,   # 중증 생계·의료 / 주거·교육·차상위
                   (2, 'basic'): 110_000, (2, 'near'): 110_000}   # 경증

# ── [1차확인] 2022 총량 (모두 전국·시설 포함) ───────────────────────────────
N_REG_TOTAL      = 2_652_860     # 등록장애인 (R05 4-2-2)
N_INST_RESIDENT  =    27_946     # 장애인 거주시설 입소인원 (R05 4-2-15)
DISP_BY_EXTRA    = {5: 169_705,  # 일반(기초생활 생계·의료)   R05 5-3-3 2022
                    3:  27_608,  # 시설(보장시설수급자)  → 일반가구 표본에서 제외
                    'near': 18_099,   # 차상위 및 교육·주거급여 (코드북 2와 4의 합)
                    1: 146_715}  # 차상위초과
DISP_PAY_CNT_YR  = 4_380_987     # 장애인연금 연간 지급건수 (15009571)
DISP_PAY_AMT_YR  = 1_215_971     # 장애인연금 연간 지급금액 (백만원)
DISP_HOLDER      =   362_127     # 2022.12.31 수급권자 (15062448 · R05 5-3-3 일치)
DISP_HOUSEHOLD   =   356_181     # 2022.12.31 수급가구 (15062448)
BN_2022          = {'general': 277_458, 'inst': 13_875, 'near': 105_300}   # R05 5-3-1
BNC_2022         = {'general_sev': 3_728, 'general_mild': 4_668,           # R05 5-3-2
                    'inst_sev': 1_172, 'inst_mild': 1_065,
                    'near_sev': 3_066, 'near_mild': 3_060}
BNC_AGE_U18_SHARE = 5_600 / 6_122        # S1 표3.5 연령대별 (18세 미만 91.5%; 18~20세 8.5%)
BN_MONTH_FACTOR   = 1_284_796 / 12 / 105_273   # S1 표3.7 Σ월별/12/12월
BNC_MONTH_FACTOR  =    72_061 / 12 /   6_122   # S1 표3.5
DEVICE_CNT_2022  =   124_110     # 건강보험 장애인보조기기 지급건수 (3073131)
DEVICE_AMT_2022  = 91_919_752_540   # 건강보험 장애인보조기기 지급금액(원)

# ── [가정] 파라미터 (params/A4_B27.yaml note 에 근거·한계 기록) ─────────────
PI12_DISP   = 0.93     # 장애인연금 12개월 수급 비율 → 평균 수급개월 11.58
PI12_BN     = 0.93     # 장애수당
PI12_BNC    = 0.93     # 장애아동수당
INC_TILT    = 0.39     # 등록장애 로짓의 _u_income 기울기 (R02 표6-4 기울기의 1/2 감쇠)
NEAR_SPLIT  = 0.50     # 차상위및교육주거급여 18,099 중 '차상위계층(2)' 비중
TAKEUP_SD   = 0.50     # 수급 선정 순위에 섞는 _u_welfare(신청성향) 가중
DEVICE_SIGMA = 0.70    # 보조기기 지원액 로그정규 σ
BN_AGE_TILT = 0.70     # 장애수당 선정 선호의 age≥65 항 (차상위분 65+ 82.2% [1차확인] 반영)
# 보조기기 유형 분포 [가정] — 전국 품목별 통계 미확보. 수동휠체어:전동휠체어:전동스쿠터의
# 상호 비율만 [1차확인](2022 의료급여 시도별 지급건수 3,720:1,628:2,662)을 따른다.
DEVICE_TYPE_W = {
    '수동휠체어': 0.30 * 3720 / 8010, '전동 휠체어': 0.30 * 1628 / 8010,
    '전동 스쿠터': 0.30 * 2662 / 8010,
    '보청기': 0.30, '기타': 0.28,
    '맞춤형 교정용 신발(19세 이상)': 0.015, '발목 - 발 보조기': 0.015,
    '욕창예방매트리스': 0.015, '욕창예방방석': 0.015, '이동식전동리프트': 0.015,
    '전동휠체어 및 전동스쿠터용 전지(2개 1세트)': 0.015, '종아리 의지': 0.015,
}
# 보조기기 급여 대상 장애유형 상대가중 [가정] — 코드북 12개 품목이 이동·청각 보조기기임에 근거
DEVICE_TYPE_PREF = {13: 1.0, 2: 1.0, 14: 1.0, 4: 1.0}   # 지체·뇌병변·청각·시각
DEVICE_TYPE_BASE = 0.15                                  # 그 밖의 유형


# ── 입력 로드 ────────────────────────────────────────────────────────────────
def _load_reg():
    """R05 <표 4-2-2> → (age_band × type × sex) 및 (grade × type × sex) 등록장애인 수."""
    d = pd.read_csv(os.path.join(RAW, 'R05_4-2-2_등록장애인수_장애정도별연령별.csv'))
    d.columns = ['g', 'k', 'item', 'v', 'unit', 'note']
    d['type_ko'] = d['item'].str.rsplit('_', n=1).str[0]
    d['sex_ko'] = d['item'].str.rsplit('_', n=1).str[1]
    d = d[d['sex_ko'].isin(['남', '여'])].copy()
    d['sex'] = np.where(d['sex_ko'] == '남', 1, 2)
    d['v'] = d['v'].astype(float)
    age = d[(d.g == '연령') & (d.type_ko != '계')].copy()
    age['type'] = age['type_ko'].map(TYPE_CODE)
    grade = d[(d.g == '장애정도') & (d.type_ko != '계')].copy()
    grade['type'] = grade['type_ko'].map(TYPE_CODE)
    tot = d[(d.g == '연령') & (d.type_ko == '계')]
    return age, grade, tot


def _load_pop():
    p = pd.read_csv(os.path.join(RAW, 'POPUL_MOIS01_2022_11_sigungu_age1_sex.csv'))
    p = p[(p.level == 'sigungu') & (p.sex.isin(['male', 'female']))].copy()
    p['sex'] = np.where(p.sex == 'male', 1, 2)
    p['age'] = p['age'].astype(int)
    p['band'] = _band_of(p['age'].values)
    return p.groupby(['sex', 'band'])['pop'].sum()


def _band_of(a):
    a = np.asarray(a)
    idx = np.minimum(a // 5, 13)
    idx = np.where(a >= 65, 13, idx)
    return np.asarray(AGE_BANDS, dtype=object)[idx.astype(int)]


# ── 도구 ─────────────────────────────────────────────────────────────────────
def _z(u):
    """U(0,1) → 표준정규 분위 (근사 없이 scipy 없이)."""
    u = np.clip(np.asarray(u, float), 1e-9, 1 - 1e-9)
    # Acklam 근사
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    dd = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
          3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    out = np.empty_like(u)
    lo, hi = u < pl, u > ph
    mid = ~(lo | hi)
    q = np.sqrt(-2 * np.log(u[lo])) if lo.any() else np.array([])
    if lo.any():
        out[lo] = (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((dd[0]*q+dd[1])*q+dd[2])*q+dd[3])*q+1)
    q = np.sqrt(-2 * np.log(1 - u[hi])) if hi.any() else np.array([])
    if hi.any():
        out[hi] = -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((dd[0]*q+dd[1])*q+dd[2])*q+dd[3])*q+1)
    if mid.any():
        q = u[mid] - 0.5; r = q * q
        out[mid] = (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
                   (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    return out


def _wsample_to_target(g, pref, w, target, elig):
    """Efraimidis–Spirakis: 포함확률 ∝ pref 로 비복원 추출하되, 선택된 개체의
    가중치 합(w)이 target(모집단 수급자 수)에 도달하면 멈춘다 → 총량 정확 재현."""
    sel = np.zeros(len(w), bool)
    idx = np.flatnonzero(elig)
    if len(idx) == 0 or target <= 0:
        return sel
    p = np.maximum(np.asarray(pref, float)[idx], 1e-12)
    key = g.random(len(idx)) ** (1.0 / p)          # 큰 key 우선
    order = idx[np.argsort(-key)]
    cw = np.cumsum(w[order])
    k = int(np.searchsorted(cw, target)) + 1
    k = min(k, len(order))
    if k > 1 and abs(cw[k - 2] - target) < abs(cw[k - 1] - target):
        k -= 1                                    # 총량 오차 최소화 (과다/과소 중 근접 쪽)
    sel[order[:k]] = True
    return sel


def _grade_ipf(age_tab, grade_tab, n_iter=30):
    """(성,연령대,유형) 등록장애인 수 A 와 (성,유형,정도) 수 S 를 두 주변분포로 하는
    3원표 T[band, type, grade] 를 IPF 로 추정 → P(심한 | 성, 연령대, 유형)."""
    out = {}
    for sx in (1, 2):
        A = (age_tab[age_tab.sex == sx].groupby(['k', 'type'])['v'].sum()
             .unstack(fill_value=0.0).reindex(index=AGE_BANDS).fillna(0.0))
        S = (grade_tab[grade_tab.sex == sx].groupby(['type', 'k'])['v'].sum()
             .unstack(fill_value=0.0))
        types = [t for t in A.columns if t in S.index]
        A = A[types].values                                   # (band, type)
        Ssev = S.loc[types, '심한 장애'].values.astype(float)
        Smil = S.loc[types, '심하지 않은 장애'].values.astype(float)
        tot = Ssev + Smil
        with np.errstate(invalid='ignore', divide='ignore'):
            r0 = np.where(tot > 0, Ssev / tot, 0.0)
        T = np.stack([A * r0, A * (1 - r0)], axis=2)           # (band, type, 2)
        for _ in range(n_iter):
            m1 = T.sum(axis=2)                                 # (band, type)
            with np.errstate(invalid='ignore', divide='ignore'):
                f1 = np.where(m1 > 0, A / m1, 1.0)
            T = T * f1[:, :, None]
            m2 = T.sum(axis=0)                                 # (type, 2)
            tgt = np.stack([Ssev, Smil], axis=1)
            with np.errstate(invalid='ignore', divide='ignore'):
                f2 = np.where(m2 > 0, tgt / m2, 1.0)
            T = T * f2[None, :, :]
        den = T.sum(axis=2)
        with np.errstate(invalid='ignore', divide='ignore'):
            P = np.where(den > 0, T[:, :, 0] / den, 0.0)
        for bi, bd in enumerate(AGE_BANDS):
            for ti, tc in enumerate(types):
                out[(sx, bd, int(tc))] = float(P[bi, ti])
    return out


def _alloc_by_shares(g, idx, w, codes, probs):
    """셀 구성원 idx 를 무작위 순서로 늘어놓고 누적 가중치 경계로 codes 를 비례배분.
    다항추출 대비 구성비 재현오차가 훨씬 작다(표본 442명 수준에서 필요)."""
    idx = np.asarray(idx)
    if len(idx) == 0:
        return np.array([], dtype=float)
    pr = np.asarray(probs, float); pr = pr / pr.sum()
    order = idx[g.permutation(len(idx))]
    cw = np.cumsum(w[order]); tot = cw[-1]
    bounds = np.cumsum(pr) * tot
    mid = cw - w[order] / 2.0
    k = np.searchsorted(bounds, mid)
    k = np.clip(k, 0, len(codes) - 1)
    res = np.full(len(w), np.nan)
    res[order] = np.asarray(codes, float)[k]
    return res


def _cond_dist(tbl, keys, val='v'):
    s = tbl.groupby(keys)[val].sum()
    return s


# ── 생성 ─────────────────────────────────────────────────────────────────────
def generate(df, params, ctx):
    DIAG.clear()
    g = core.rng('B27')
    n = len(df)
    idx = df.index
    age = df['age'].astype(int).values
    sex = df['gender'].astype(int).values
    band = _band_of(age)
    w = df['indwgt'].astype(float).values if 'indwgt' in df.columns else np.full(n, 1.0)
    ui = df['_u_income'].values if '_u_income' in df.columns else g.random(n)
    uw = df['_u_welfare'].values if '_u_welfare' in df.columns else g.random(n)
    hnum = df['hnum'].astype(int).values if 'hnum' in df.columns else np.ones(n, int)
    has_spouse = (df['_spouse_age'].notna().values if '_spouse_age' in df.columns
                  else np.zeros(n, bool))
    hid = df['hid'].values

    out = pd.DataFrame(index=idx)

    # ══ 1. dis_yn — 등록장애인 (성×연령대 유병률, 시설거주자 제외 보정) ══════
    age_tab, grade_tab, tot_tab = _load_reg()
    pop = _load_pop()
    reg = tot_tab.groupby(['sex', 'k'])['v'].sum()          # 등록장애인 (성×연령대)
    inst_adj = (N_REG_TOTAL - N_INST_RESIDENT) / N_REG_TOTAL   # 일반가구 보정 0.98947

    tgt_cell = {}
    for (sx, bd), v in reg.items():
        tgt_cell[(int(sx), bd)] = float(v) * inst_adj

    # _u_income 기울기 (R02 표6-4 시장소득 분위 D/ND 비의 로그기울기 × 0.5 감쇠)
    pref = np.exp(-INC_TILT * _z(ui))                        # 저소득일수록 큰 값
    dis = np.zeros(n, bool)
    for (sx, bd), tgt in tgt_cell.items():
        m = (sex == sx) & (band == bd)
        if not m.any():
            continue
        dis |= _wsample_to_target(g, pref, w, tgt, m)

    out['dis_yn'] = np.where(dis, 1.0, np.nan)

    # ══ 2. dis_type_1 — 주장애유형 : P(type | 성, 연령대) ════════════════════
    at = _cond_dist(age_tab, ['sex', 'k', 'type'])
    dtype = np.full(n, np.nan)
    for (sx, bd) in sorted(set(zip(sex[dis].tolist(), band[dis].tolist()))):
        m = dis & (sex == sx) & (band == bd)
        try:
            ss = at.loc[(sx, bd)]
        except KeyError:
            continue
        codes = ss.index.values.astype(int); pr = ss.values.astype(float)
        if pr.sum() <= 0:
            continue
        r = _alloc_by_shares(g, np.flatnonzero(m), w, codes, pr)
        dtype[m] = r[m]
    out['dis_type_1'] = dtype

    # ══ 3. dis_grade_1 — 종합장애정도 : P(심한 | 성, 연령대, 유형) ══════════
    # R05 4-2-2 에는 (연령×정도) 교차가 없다. (성×연령대×유형)과 (성×유형×정도)
    # 두 주변분포를 IPF 로 화해시켜 P(정도 | 성,연령대,유형)을 얻는다(최대엔트로피).
    p_sev_tbl = _grade_ipf(age_tab, grade_tab)
    p_sev = np.full(n, np.nan)
    for (sx, bd, tc), v in p_sev_tbl.items():
        m = dis & (sex == sx) & (band == bd) & (dtype == tc)
        if m.any():
            p_sev[m] = v
    grade1 = np.full(n, np.nan)
    di = np.flatnonzero(dis & ~np.isnan(p_sev))
    if len(di):
        per = di[g.permutation(len(di))]
        pv = np.clip(p_sev[per], 0.0, 1.0)
        c = np.cumsum(pv); u = g.random()
        # 계통추출: 포함확률 = p_sev 를 정확히 유지하면서 합계 반올림 편의를 제거
        pick = np.floor(c - pv + u).astype(int) < np.floor(c + u).astype(int)
        grade1[per] = np.where(pick, 1.0, 2.0)
    grade1[dis & np.isnan(grade1)] = 2.0
    out['dis_grade_1'] = grade1
    severe = dis & (grade1 == 1)
    mild = dis & (grade1 == 2)

    # ══ 4. 부장애 (dis_type_2 / dis_grade_3) · 주장애정도(dis_grade_2) ═══════
    # 중복장애(부장애 보유) 비율에 대한 2022 원문 통계를 확보하지 못했다 [미확인].
    # → 코드북이 명시한 결측코드(-99999999)로 전량 처리. 주장애정도는 부장애가
    #   기록되지 않으므로 종합장애정도와 동일 [논리적추론].
    out['dis_type_2'] = np.where(dis, float(MISSING), np.nan)
    out['dis_grade_2'] = grade1
    out['dis_grade_3'] = np.where(dis, float(MISSING), np.nan)

    # ══ 5. dis_disp_yn — 장애인연금법상 중증장애인 여부 ══════════════════════
    # 법상 중증 = 종전 1급·2급·3급중복 ⊊ '정도가 심한'(종전 1~3급). 등급별 등록장애인
    # 수 통계 미확보 [미확인] + §7 R10(disp⇒심한)·R11(disp_bn⇒심하지않은)이 두 집합의
    # 동일시를 요구 → dis_disp_yn = (dis_grade_1==1) [논리적추론]
    out['dis_disp_yn'] = np.where(dis, np.where(grade1 == 1, 1.0, 0.0), np.nan)

    # ══ 6. 장애인연금 ════════════════════════════════════════════════════════
    disp_nonint = DISP_BY_EXTRA[5] + DISP_BY_EXTRA['near'] + DISP_BY_EXTRA[1]   # 334,519
    share_nonint = disp_nonint / DISP_HOLDER
    pay_cnt_nonint = DISP_PAY_CNT_YR * share_nonint          # 비시설 연간 지급건수
    mean_dur_disp = 6.0 + 6.0 * PI12_DISP
    n1_disp = pay_cnt_nonint / mean_dur_disp                 # 연간 1회 이상 수급자(비시설)

    # 소득인정액 대리지표(작을수록 저소득) : _u_income 주효과 + 가구 특성
    z_inc = _z(ui) + 0.30 * np.clip(hnum - 1, 0, 4) / 4.0 - 0.35 * (age >= 65)
    z_sel = z_inc - TAKEUP_SD * _z(uw)                       # 신청·수급 성향 혼합

    # 65세 이상 비중 s* : 총 지급금액/지급건수(=월 평균 277,556원, 1차확인)와 2022 단가표로
    # 해석적으로 결정한다.  DISP_HOLDER·meanpay = 비시설·((1-s)A<65 + s·A65+) + 시설·((1-s)·기초급여)
    a5 = DISP_BY_EXTRA[5] / disp_nonint
    aN = DISP_BY_EXTRA['near'] / disp_nonint
    a1 = DISP_BY_EXTRA[1] / disp_nonint
    A_lo = (a5 * (DISP_BASIC_MAX + DISP_EXTRA[5][0]) + aN * (DISP_BASIC_MAX + DISP_EXTRA[2][0])
            + a1 * (DISP_BASIC_MAX + DISP_EXTRA[1][0]))
    A_hi = a5 * DISP_EXTRA[5][1] + aN * DISP_EXTRA[2][1] + a1 * DISP_EXTRA[1][1]
    meanpay = DISP_PAY_AMT_YR * 1e6 / DISP_PAY_CNT_YR                 # 277,556원/건·월
    const = disp_nonint * A_lo + DISP_BY_EXTRA[3] * DISP_BASIC_MAX
    coef = disp_nonint * (A_lo - A_hi) + DISP_BY_EXTRA[3] * DISP_BASIC_MAX
    s_star = float(np.clip((const - DISP_HOLDER * meanpay) / coef, 0.0, 1.0))
    DIAG['disp_s_star'] = s_star

    elig_disp = severe & (age >= 18)
    pref_disp = np.exp(-1.5 * z_sel)                         # 저소득·고신청성향 우선
    disp1 = (_wsample_to_target(g, pref_disp, w, n1_disp * s_star, elig_disp & (age >= 65)) |
             _wsample_to_target(g, pref_disp, w, n1_disp * (1 - s_star), elig_disp & (age < 65)))

    # ══ 6-1. disp_type — 단독 / 부부1인 / 부부2인 ════════════════════════════
    # (부부2인 수급자 = (수급권자 362,127 − 수급가구 356,181) × 2 = 11,892명, 3.28%)
    #
    # ★ 2026-09-02 정정 — 이 블록은 종전에 dur·yn2·disp_extra_type 배정이 **끝난 뒤**에
    #   놓여 있었다. 그런데 아래 승격·강등 루프는 `disp1` 을 바꾼다:
    #     · 승격자 → disp_yn1=1 인데 dur=NaN·extra=NaN 이라 disp_amt=0  ⇒ §7 R24
    #       (`amt>0 ⇔ yn1`) 위반, 블록 말미 assert 가 터진다.
    #     · 강등자 → disp1=False 라 출력은 NaN 으로 마스킹되지만 dur·yn2 배정이 낭비되고
    #       총량 캘리브레이션(disp_nonint)이 어긋난다.
    #   지금까지 드러나지 않은 이유는 B01 `_spouse_age` 결함으로 부부 짝이 성립하지 않아
    #   루프가 한 번도 돌지 않았기 때문이다(cand=0). 짝이 하나만 생겨도 확실히 터진다
    #   (반사실 재현 확인: 수급자 1명에게 중증 배우자를 붙이면 종전 코드는 즉시 assert).
    #   → **disp1 을 여기서 확정하고**, dur·yn2·extra_type·amt 는 그 뒤에만 배정한다.
    #     루프 자체는 난수를 전혀 쓰지 않는다. 다만 강등 인원이 승격 인원과 다를 수 있어
    #     `disp1.sum()` 이 바뀌면 뒤이은 core.dur_months 추출 개수가 달라진다 —
    #     영향은 **B27 전용 generator `core.rng('B27')` 안에서만** 발생하고 다른 블록의
    #     난수열은 건드리지 않는다(seed 재현성 True 유지, 실측 확인).
    p_couple2 = 2.0 * (DISP_HOLDER - DISP_HOUSEHOLD) / DISP_HOLDER      # 0.0328
    partner = np.full(n, -1, dtype=int)
    bh = {}
    for i in np.flatnonzero(has_spouse):
        bh.setdefault(hid[i], []).append(i)
    for v in bh.values():
        if len(v) == 2:
            partner[v[0]], partner[v[1]] = v[1], v[0]
    pm = partner >= 0
    ipos = np.arange(n)

    def _both_mask(sel):
        """부부 양쪽이 모두 수급 중인 사람 마스크 (partner=-1 은 np.where 로 차단)."""
        return sel & pm & np.where(pm, sel[partner], False)

    def _demote(need_w):
        """단독 수급자를 z_sel 큰(=덜 절박한) 순으로 강등해 승격분 need_w 를 되돌린다.
        [S1] 장애인연금 수급권자수(362,127)는 **가중 총량** 목표이므로 강등 인원 수가 아니라
        가중치 합이 승격분에 가장 가까워지는 지점에서 끊는다 (관측치 수로 맞추면 강등자·
        승격자의 indwgt 차이만큼 총량이 흔들린다 — column_contract C3 와 같은 취지)."""
        dr = np.flatnonzero(disp1 & ~pm)
        if len(dr) == 0:
            return None
        dr = dr[np.argsort(-z_sel[dr], kind='stable')]
        k = int(np.argmin(np.abs(np.cumsum(w[dr]) - need_w))) + 1
        return dr[:k]

    tgt_both = p_couple2 * float(w[disp1].sum())
    both = _both_mask(disp1)
    # 목표 미달 시 부부 수급 짝을 만든다.
    #   (A) 수급자의 배우자(수급요건 충족·미선정)를 1명 승격
    #   (B) (A) 후보가 없으면 부부 **양쪽이** 수급요건을 충족하는 미선정 짝을 2명 승격
    #       ← 소표본에서 (A) 가 성립하지 않아 disp_type=3 이 한 명도 생기지 않던 문제
    #         (deviation_analysis §2-1 "남은 한계")를 여기서 해소한다.
    #   승격분만큼 단독 수급자를 강등해 가중 총량을 되돌린다(_demote).
    # 승격 대상은 elig_disp(dis_yn=1 ∧ 중증 ∧ 18세 이상)로만 한정 → §7 R10 항상 유지.
    # 강등 대상은 배우자 짝이 없는 단독 수급자로만 한정 → 기존 부부 짝을 깨지 않는다.
    guard = 0
    while guard < 20:
        guard += 1
        cur = float(w[both].sum())
        if cur >= tgt_both:
            break
        cand = np.flatnonzero(disp1 & pm & ~both &
                              np.where(pm, elig_disp[partner] & ~disp1[partner], False))
        if len(cand):
            up = np.array([partner[int(cand[np.argmin(z_sel[partner[cand]])])]])
        else:
            # 짝당 대표 1개(인덱스가 작은 쪽)만 세어 중복 제거
            pair = np.flatnonzero(elig_disp & pm & ~disp1 &
                                  np.where(pm, elig_disp[partner] & ~disp1[partner], False) &
                                  (ipos < np.where(pm, partner, n)))
            if len(pair) == 0:
                break
            i0 = int(pair[np.argmin(np.minimum(z_sel[pair], z_sel[partner[pair]]))])
            up = np.array([i0, partner[i0]])
        dn = _demote(float(w[up].sum()))
        if dn is None:
            break
        prev = disp1.copy()
        disp1[up] = True
        disp1[dn] = False
        nb = _both_mask(disp1)
        # 표본 1행의 indwgt 가 6천명대라 한 짝(2행)의 최소 증분이 목표(11,431명)와 같은 자릿수다.
        # 미달 상태에서 무조건 한 짝을 더 얹으면 오히려 목표에서 멀어지므로, 더 가까워질 때만 채택한다.
        if abs(float(w[nb].sum()) - tgt_both) > abs(cur - tgt_both):
            disp1[:] = prev
            break
        both = nb
    dtp = np.full(n, np.nan)
    dtp[disp1] = np.where(both[disp1], 3.0, np.where(has_spouse[disp1], 2.0, 1.0))
    out_disp_type = dtp
    DIAG['disp_couple2_rows'] = int(both.sum())
    DIAG['disp_couple2_w'] = float(w[both].sum())
    DIAG['disp_couple2_tgt_w'] = float(tgt_both)
    DIAG['disp_couple2_iter'] = guard
    DIAG['disp_type_rows'] = {int(k): int((dtp == k).sum()) for k in (1, 2, 3)}
    # 이 지점 이후로 disp1 을 바꾸면 안 된다 — 아래에서 dur·extra_type·amt 를 배정한다.
    _disp1_frozen = disp1.copy()

    dur = np.full(n, np.nan)
    dur[disp1] = core.dur_months(g, int(disp1.sum()), PI12_DISP, 1, 11)
    # yn2 : dur=12 는 전원 12월 수급, 나머지에서 부족분 보충 → 총 334,519 재현
    yn2 = np.zeros(n, bool)
    yn2[disp1 & (dur == 12)] = True
    got = float(w[yn2].sum())
    rest = disp1 & (dur < 12)
    if rest.any() and got < disp_nonint:
        add = _wsample_to_target(g, np.ones(n), w, disp_nonint - got, rest)
        yn2 |= add
    elif got > disp_nonint:                                   # 과다 시 dur=12 중 일부 해제
        drop = _wsample_to_target(g, np.ones(n), w, got - disp_nonint, yn2)
        yn2 &= ~drop

    # disp_extra_type — 소득인정액 순위 기준 (기초 → 차상위 → 차상위초과)
    extra = np.full(n, np.nan)
    sel_idx = np.flatnonzero(disp1)
    if len(sel_idx):
        order = sel_idx[np.argsort(z_inc[sel_idx])]
        cw = np.cumsum(w[order]); mid = cw - w[order] / 2.0
        scale = float(w[disp1].sum()) / disp_nonint           # yn1 기준으로 총량 환산
        c5 = DISP_BY_EXTRA[5] * scale
        cn = c5 + DISP_BY_EXTRA['near'] * scale
        extra[order] = np.where(mid <= c5, 5.0, np.where(mid <= cn, 0.0, 1.0))
        near_m = order[(mid > c5) & (mid <= cn)]
        if len(near_m):
            extra[near_m] = np.where(core.bernoulli(g, np.full(len(near_m), NEAR_SPLIT)) == 1,
                                     2.0, 4.0)

    # disp_type 은 6-1 에서 disp1 확정과 함께 이미 정해졌다 (out_disp_type).
    assert np.array_equal(disp1, _disp1_frozen), \
        'disp1 이 disp_type 확정 후에 변경되었다 — dur·extra·amt 배정과 어긋난다'

    # 급여액 (원/월) — 2022 단가표 [1차확인]
    basic_m = np.zeros(n)
    u65 = age < 65
    b18 = disp1 & u65
    basic_m[b18] = np.where(out_disp_type[b18] == 3, DISP_BASIC_COUPLE2, DISP_BASIC_MAX)
    extra_m = np.zeros(n)
    for k, (lo, hi) in DISP_EXTRA.items():
        m = disp1 & (extra == k)
        extra_m[m] = np.where(age[m] < 65, lo, hi)

    # 초과분 감액 (차상위계층·차상위초과 수급자, 18~64세) — 계단표는 [1차확인],
    # 계단 내 분포는 [가정](균등), 감액 비대상 비율 q 는 총 지급금액 [1차확인] 캘리브레이션
    red_m = disp1 & u65 & np.isin(extra, [1.0, 2.0])
    inst_mean_m = (1.0 - s_star) * DISP_BASIC_MAX                  # 보장시설: 부가급여 0원
    m_target = (DISP_HOLDER * DISP_PAY_AMT_YR * 1e6 / DISP_PAY_CNT_YR
                - DISP_BY_EXTRA[3] * inst_mean_m) / disp_nonint
    ww = w[disp1]
    m_now = float(((basic_m + extra_m)[disp1] * ww).sum() / ww.sum())
    q = 1.0
    if red_m.any() and m_now > m_target:
        need = (m_now - m_target) * ww.sum()                        # 줄여야 할 총 월지급액
        base_red = float((basic_m[red_m] * w[red_m]).sum())
        lad_mean = float(np.mean(DISP_REDUCE_LADDER)) / DISP_BASIC_MAX
        q = 1.0 - need / max(base_red * (1.0 - lad_mean), 1e-9)
        q = float(np.clip(q, 0.0, 1.0))
    if red_m.any() and q < 1.0:
        # 소득인정액이 선정기준액에 가까운(=z_inc 큰) 수급자가 감액 대상이 되도록 선호를 준다
        hit = _wsample_to_target(g, np.exp(1.0 * z_inc), w,
                                 (1.0 - q) * float(w[red_m].sum()), red_m)
        hi = np.flatnonzero(hit)
        if len(hi):
            st = _alloc_by_shares(g, hi, w, DISP_REDUCE_LADDER,
                                  np.ones(len(DISP_REDUCE_LADDER)))
            basic_m[hi] = np.round(basic_m[hi] * st[hi] / DISP_BASIC_MAX / 10.0) * 10.0
    DIAG['disp_reduce_q'] = q

    out['disp_yn1'] = np.where(disp1, 1.0, np.nan)
    out['disp_yn2'] = np.where(disp1, np.where(yn2, 1.0, 0.0), np.nan)
    out['disp_type'] = np.where(disp1, out_disp_type, np.nan)
    out['disp_extra_type'] = np.where(disp1, extra, np.nan)
    out['disp_dur'] = np.where(disp1, dur, np.nan)
    out['disp_basic_amt'] = np.where(disp1, np.round(basic_m * np.nan_to_num(dur)), np.nan)
    out['disp_extra_amt'] = np.where(disp1, np.round(extra_m * np.nan_to_num(dur)), np.nan)
    out['disp_amt'] = out['disp_basic_amt'] + out['disp_extra_amt']

    # ══ 7. 장애수당 (18세 이상 · 경증 · 기초생활 또는 차상위) ════════════════
    bn_nonint = BN_2022['general'] + BN_2022['near']            # 382,758
    n1_bn = bn_nonint * BN_MONTH_FACTOR * 12.0 / (6.0 + 6.0 * PI12_BN)
    elig_bn = mild & (age >= 18)
    pref_bn = np.exp(-1.5 * z_sel + BN_AGE_TILT * (age >= 65))
    bn1 = _wsample_to_target(g, pref_bn, w, n1_bn, elig_bn)
    bdur = np.full(n, np.nan)
    bdur[bn1] = core.dur_months(g, int(bn1.sum()), PI12_BN, 1, 11)
    byn2 = np.zeros(n, bool)
    byn2[bn1 & (bdur == 12)] = True
    got = float(w[byn2].sum())
    rest = bn1 & (bdur < 12)
    if rest.any() and got < bn_nonint:
        byn2 |= _wsample_to_target(g, np.ones(n), w, bn_nonint - got, rest)
    elif got > bn_nonint:
        byn2 &= ~_wsample_to_target(g, np.ones(n), w, got - bn_nonint, byn2)
    out['disp_bn_yn1'] = np.where(bn1, 1.0, np.nan)
    out['disp_bn_yn2'] = np.where(bn1, np.where(byn2, 1.0, 0.0), np.nan)
    out['disp_bn_dur'] = np.where(bn1, bdur, np.nan)
    out['disp_bn_amt'] = np.where(bn1, np.round(BN_AMT_M * np.nan_to_num(bdur)), np.nan)

    # ══ 8. 장애아동수당 ══════════════════════════════════════════════════════
    bnc_sev = BNC_2022['general_sev'] + BNC_2022['near_sev']
    bnc_mild = BNC_2022['general_mild'] + BNC_2022['near_mild']
    bnc_nonint = bnc_sev + bnc_mild                               # 14,522
    n1_bnc = bnc_nonint * BNC_MONTH_FACTOR * 12.0 / (6.0 + 6.0 * PI12_BNC)
    elig_bnc = dis & (age <= 20) & ~disp1 & ~bn1
    # §4 규모 미달 판정 : 기대 수급자(행 수) = target / 표본 대표 인구비
    exp_rows_bnc = n1_bnc * len(df) / float(w.sum())
    DIAG['exp_rows_bnc'] = exp_rows_bnc
    if exp_rows_bnc >= 3.0:
        s_sev = elig_bnc & (grade1 == 1)
        s_mild = elig_bnc & (grade1 == 2)
        # 연령구조 : 18세 미만 91.5% / 18~20세 8.5% (S1 표3.5 [1차확인])
        pref_c = np.exp(-1.5 * z_sel) * np.where(age < 18, BNC_AGE_U18_SHARE,
                                                 1.0 - BNC_AGE_U18_SHARE)
        bnc1 = (_wsample_to_target(g, pref_c, w, n1_bnc * bnc_sev / bnc_nonint, s_sev) |
                _wsample_to_target(g, pref_c, w, n1_bnc * bnc_mild / bnc_nonint, s_mild))
        cdur = np.full(n, np.nan)
        cdur[bnc1] = core.dur_months(g, int(bnc1.sum()), PI12_BNC, 1, 11)
        cyn2 = np.zeros(n, bool)
        cyn2[bnc1 & (cdur == 12)] = True
        got = float(w[cyn2].sum())
        rest = bnc1 & (cdur < 12)
        if rest.any() and got < bnc_nonint:
            cyn2 |= _wsample_to_target(g, np.ones(n), w, bnc_nonint - got, rest)
        elif got > bnc_nonint:
            cyn2 &= ~_wsample_to_target(g, np.ones(n), w, got - bnc_nonint, cyn2)
        # 단가 : 기초생활(생계·의료) vs 주거·교육·차상위 — 소득 순위로 배분
        basic_share = ((BNC_2022['general_sev'] + BNC_2022['general_mild']) /
                       float(bnc_nonint))
        camt_m = np.zeros(n)
        ci = np.flatnonzero(bnc1)
        if len(ci):
            order = ci[np.argsort(z_inc[ci])]
            cw = np.cumsum(w[order])
            is_basic = cw <= basic_share * float(w[bnc1].sum())
            for j, i in enumerate(order):
                gkey = 1 if grade1[i] == 1 else 2
                camt_m[i] = BN_CHILD_AMT_M[(gkey, 'basic' if is_basic[j] else 'near')]
        out['disp_bn_child_yn1'] = np.where(bnc1, 1.0, np.nan)
        out['disp_bn_child_yn2'] = np.where(bnc1, np.where(cyn2, 1.0, 0.0), np.nan)
        out['disp_bn_child_dur'] = np.where(bnc1, cdur, np.nan)
        out['disp_bn_child_amt'] = np.where(bnc1, np.round(camt_m * np.nan_to_num(cdur)), np.nan)
    else:
        # 규모 미달 (§4) — 전량 NaN
        for c in ('disp_bn_child_yn1', 'disp_bn_child_yn2',
                  'disp_bn_child_dur', 'disp_bn_child_amt'):
            out[c] = np.nan

    # ══ 9. 건강보험(의료급여) 장애인 보조기기 ════════════════════════════════
    pref_dev = np.where(np.isin(dtype, list(DEVICE_TYPE_PREF)), 1.0, DEVICE_TYPE_BASE)
    pref_dev = pref_dev * np.where(grade1 == 1, 1.0, 1.0)
    dev = _wsample_to_target(g, pref_dev, w, DEVICE_CNT_2022, dis)
    out['dis_device_yn'] = np.where(dev, 1.0, np.nan)
    dev_mean = DEVICE_AMT_2022 / DEVICE_CNT_2022
    amt = np.full(n, np.nan)
    if dev.any():
        raw_amt = core.lognormal_mean(g, np.full(int(dev.sum()), dev_mean),
                                      DEVICE_SIGMA, int(dev.sum()))
        tot = float((raw_amt * w[dev]).sum())
        if tot > 0:                       # 총 지급금액 [1차확인] 일치 보정
            raw_amt = raw_amt * (DEVICE_AMT_2022 / tot)
        amt[dev] = np.round(raw_amt)
    out['dis_device_amt'] = amt
    dnames = list(DEVICE_TYPE_W); dw = np.array([DEVICE_TYPE_W[k] for k in dnames], float)
    dt = np.full(n, np.nan, dtype=object)
    if dev.any():
        dt[dev] = core.choice_p(g, np.array(dnames, dtype=object), dw, int(dev.sum()))
    out['dis_device_type'] = pd.Series(dt, index=idx).astype('object')

    # ══ 10. 장애인 자립자금 대여 — §4 규모 미달 ══════════════════════════════
    # 2022 신규 대출실적 전국 34건(보건복지부 사전정보공표 [1차확인]). 12.31 기준 잔액
    # 건수는 미공표이나 신규 flow 34건 규모에서 표본(9,535명·모집단 51.45백만) 기대
    # 수급자는 1명에 크게 못 미친다 → 전량 NaN
    out['diswork_loan_yn'] = np.nan

    # ══ §7 강제 검증 (위반 시 즉시 실패) ═════════════════════════════════════
    assert not ((out.disp_yn1 == 1) & ((out.dis_yn != 1) | (out.dis_grade_1 != 1) |
                                       (df['age'] < 18))).any(), 'R10 위반'
    assert not ((out.disp_bn_yn1 == 1) & ((out.dis_grade_1 != 2) | (df['age'] < 18))).any(), 'R11 위반'
    for a, b in (('disp_yn2', 'disp_yn1'), ('disp_bn_yn2', 'disp_bn_yn1'),
                 ('disp_bn_child_yn2', 'disp_bn_child_yn1')):
        assert not ((out[a] == 1) & (out[b] != 1)).any(), f'R24 위반 {a}'
    for c in ('disp_dur', 'disp_bn_dur', 'disp_bn_child_dur'):
        s = out[c]
        assert not (s.notna() & ((s < 1) | (s > 12))).any(), f'R24 dur 위반 {c}'
    for a, y in (('disp_amt', 'disp_yn1'), ('disp_bn_amt', 'disp_bn_yn1'),
                 ('disp_bn_child_amt', 'disp_bn_child_yn1'), ('dis_device_amt', 'dis_device_yn')):
        assert not (out[a].notna() & (out[y] != 1)).any(), f'amt⇔yn 위반 {a}'
        assert not ((out[y] == 1) & (out[a].fillna(0) <= 0)).any(), f'amt>0⇔yn 위반 {a}'
    # 수급자에게 부속 변수가 빠짐없이 배정됐는지 — disp1 을 배정 뒤에 바꾸면 여기서 잡힌다
    for y, cs in (('disp_yn1', ('disp_type', 'disp_extra_type', 'disp_dur',
                                'disp_basic_amt', 'disp_extra_amt', 'disp_yn2')),
                  ('disp_bn_yn1', ('disp_bn_dur', 'disp_bn_yn2')),
                  ('disp_bn_child_yn1', ('disp_bn_child_dur', 'disp_bn_child_yn2'))):
        for c in cs:
            assert not ((out[y] == 1) & out[c].isna()).any(), f'수급자 {c} 미배정'
            assert not ((out[y] != 1) & out[c].notna()).any(), f'비수급자 {c} 잔존'

    if os.environ.get('B27_DIAG'):
        print('[B27 DIAG]', {k: (round(v, 4) if isinstance(v, float) else v)
                             for k, v in DIAG.items()}, flush=True)

    # amt 는 원 단위 정수
    for c in ('disp_amt', 'disp_basic_amt', 'disp_extra_amt', 'disp_bn_amt',
              'disp_bn_child_amt', 'dis_device_amt'):
        out[c] = out[c].astype('float64').round(0)

    return out[['dis_yn', 'dis_type_1', 'dis_type_2', 'dis_grade_1', 'dis_grade_2',
                'dis_grade_3', 'dis_disp_yn',
                'disp_yn1', 'disp_yn2', 'disp_type', 'disp_extra_type', 'disp_dur',
                'disp_amt', 'disp_basic_amt', 'disp_extra_amt',
                'disp_bn_yn1', 'disp_bn_yn2', 'disp_bn_dur', 'disp_bn_amt',
                'disp_bn_child_yn1', 'disp_bn_child_yn2', 'disp_bn_child_dur',
                'disp_bn_child_amt',
                'dis_device_yn', 'dis_device_amt', 'dis_device_type',
                'diswork_loan_yn']]
