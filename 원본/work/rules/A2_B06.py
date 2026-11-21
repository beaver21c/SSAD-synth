# -*- coding: utf-8 -*-
"""B06 근로·자녀장려금 (itc_*)  (A2 / order 8)

코드북 기준시점: **2021년 귀속 소득분에 대해 2022년에 지급된 장려금**(신청–미지급 사례 포함),
추출대상 = 가구를 대표하는 신청자 개인.

■ 소스 (등급순)
  S0  R02 <표 3-56> 가구시장소득 분위별 근로장려금 수급률, <표 3-57> 가구재산 분위별 수급률
      (18~64세 가구주 가구 기준) → **소득·재산 분위 기울기의 1순위 기준**            [1차확인]
      params/tab/S0_R02_T3-56_*.csv, S0_R02_T3-57_*.csv
  S0  R02 <표 3-53> 근로장려금 수급가구 × 두루누리 교차 (수급 11.8%)                 [1차확인]
  S2  국세통계 14-1-1 / 14-3-1 / 14-3-16 (2021년 귀속, 국세통계포털 TASIS 발행연도 2022)
      → 신청·지급 가구수, 가구유형별·연령별·부양자녀수별 가구수와 금액, 총급여액 등 규모별 분포 [1차확인]
      params/tab/NTS_14-*_2021귀속.csv
  S4  조세특례제한법(시행 2022.4.20) 제100조의3·제100조의5·제100조의28·제100조의29
      → 총소득기준금액(단독 2,000/홑벌이 3,000/맞벌이 3,600만원), 재산 2억원 미만,
        재산 1.4억원 이상 50% 감액, 근로·자녀장려금 산정식                          [1차확인]
      params/tab/TAX_2022_근로자녀장려금_요건산정표.csv

■ 주의 (코드북 수정 검토)
  작업지시서 §6 B06 은 "총급여 단독 2,200 / 홑벌이 3,200 / 맞벌이 3,800만원"이라 적었으나 이는
  **2022년 귀속(2023년 지급)** 개정치다. 코드북 기준시점(2021년 귀속)에는 2,000/3,000/3,600만원이
  적용된다 — 조특법 시행 2022.4.20 본문에서 직접 확인했다.

■ 생성 절차
  1) 신청 후보 = 만 18세 이상(부양자녀는 신청 불가), 근로·사업소득 보유(B03 구현 시 강제)
  2) 세법상 가구유형 itc_hmember: 단독(11)/홑벌이(21)/맞벌이(23) — 조특법 제100조의3제5항
  3) 점수 = R02 <표3-56> 소득분위 기울기 × <표3-57> 재산분위 기울기 (S0)
  4) (연령대 6 × 가구유형 3) 셀 목표를 국세통계 주변분포로 IPF 1회 → 셀 내 점수비례 배정
  5) itc_amt = 조특법 산정식(총급여액 등은 14-3-16 규모별 분포에서 추출) × 재산 1.4억 감액
     → 국세통계 가구유형별 평균액에 맞춰 최종 스케일
  6) itc_child_yn / itc_child_amt = 홑벌이·맞벌이 ∧ 부양자녀 ≥1, 국세통계 자녀수별 평균액
     — 근로장려금 동시수급 여부(b)별로 (가구유형 2 × 부양자녀수 5) 셀 목표를 IPF 1회로 만들어
       셀 안에서 배정한다. 주변분포는 14-3-1 「근로·자녀장려금 가구수 [C]」
       (가구유형: 홑벌이 373,711 / 맞벌이 77,272, 자녀수: 1명 256,818 … 5명+ 1,117)
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

TAB = 'params/tab'
MAN = 10_000.0

# ── 국세통계 14-1-1 · 14-3-1 (2021년 귀속) ────────────────────────────────
N_APPLY_EITC, N_APPLY_CTC, N_APPLY_BOTH = 5_102_300, 720_192, 558_661
N_PAY_EITC, N_PAY_CTC, N_PAY_BOTH = 4_362_325, 573_847, 450_983
PAY_BY_TYPE = {11: 2_956_175, 21: 1_166_188, 23: 239_962}            # 근로장려금
CTC_BY_TYPE = {21: 480_554, 23: 93_293}                               # 자녀장려금
# 근로·자녀장려금 **동시** 지급 가구수 — 14-3-1 (2021년 귀속) 가구유형별 「가구수 [C]」 [1차확인]
#   홑벌이 373,711 + 맞벌이 77,272 = 450,983 (단독가구는 자녀장려금 자체가 0)
CTC_BOTH_BY_TYPE = {21: 373_711, 23: 77_272}
# 14-3-1 (2021년 귀속) 부양자녀 인원별 자녀장려금 가구수 / 그중 근로장려금 동시수급 [1차확인]
CTC_BY_NCHILD = {1: 330_526, 2: 193_485, 3: 42_899, 4: 5_643, 5: 1_294}          # 계 573,847
CTC_BOTH_BY_NCHILD = {1: 256_818, 2: 153_126, 3: 35_210, 4: 4_712, 5: 1_117}     # 계 450,983
AMT_BY_TYPE = {11: 2_510_791e6 / 2_956_175, 21: 1_604_646e6 / 1_166_188,
               23: 329_265e6 / 239_962}                               # 원
CTC_AMT_BY_TYPE = {21: 415_051e6 / 480_554, 23: 78_448e6 / 93_293}
# 연령별 근로장려금 지급 가구수 (신청자 연령)
PAY_BY_AGE = [1_254_094, 544_095, 585_543, 710_382, 722_147, 546_064]  # <30,<40,<50,<60,<70,70+
AGE_CUTS = [30, 40, 50, 60, 70]
# 자녀수별 자녀장려금 평균액 (원)
CTC_AMT_BY_NCHILD = {1: 185_973e6 / 330_526, 2: 215_299e6 / 193_485, 3: 74_211e6 / 42_899,
                     4: 13_615e6 / 5_643, 5: 4_400e6 / 1_294}
# 14-3-16 총급여액 등 규모별 (근로장려금 수급가구, 만원 구간 · 가구수)
GROSS_LB = [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1200, 1300, 1400, 1500,
            1700, 2000, 2100, 2200, 2500, 2800, 3000, 3200, 3300, 3600]
GROSS_UB = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1200, 1300, 1400, 1500, 1700,
            2000, 2100, 2200, 2500, 2800, 3000, 3200, 3300, 3600, 4000]
GROSS_N = [347_321, 247_914, 374_188, 271_528, 188_392, 188_582, 173_283, 166_119, 151_320,
           148_007, 279_722, 144_490, 134_862, 138_333, 269_869, 387_089, 123_602, 134_611,
           156_729, 123_633, 68_129, 60_545, 12_880, 35_471, 35_706]

# ── S0 R02 기울기 (18~64세 가구주 가구, 근로장려금 수급률 %) ───────────────
G_INC = np.array([9.5, 20.7, 25.0, 15.5, 8.6, 6.3, 3.7, 1.7, 0.7, 0.2]) / 7.6   # <표 3-56>
G_PROP = np.array([16.1, 12.6, 13.1, 9.9, 4.8, 1.6, 0.7, 0.3, 0.1]) / 7.6       # <표 3-57>

# ── 조세특례제한법 (시행 2022.4.20) ────────────────────────────────────────
GROSS_CAP = {11: 2000.0, 21: 3000.0, 23: 3600.0}       # 총소득기준금액 (만원)
PROP_LIMIT = 200_000_000                                # 가구원 재산 합계 2억원 미만
PROP_HALF = 140_000_000                                 # 1.4억원 이상 → 50% 감액
CTC_MAX_PER_CHILD = 700_000                             # 자녀 1인당 70만원


def _eitc(x, t):
    """조특법 제100조의5 근로장려금 산정 (x: 총급여액 등, 만원 → 만원)."""
    if t == 11:
        return x * 150 / 400 if x < 400 else (150.0 if x < 900
                                              else max(0.0, 150 - (x - 900) * 150 / 1100))
    if t == 21:
        return x * 260 / 700 if x < 700 else (260.0 if x < 1400
                                              else max(0.0, 260 - (x - 1400) * 260 / 1600))
    return x * 300 / 800 if x < 800 else (300.0 if x < 1700
                                          else max(0.0, 300 - (x - 1700) * 300 / 1900))


def _solve_lambda(w, s, target):
    """Σ w·clip(λs,0,1) = target 을 만족하는 λ (이분법)."""
    if target <= 0 or s.sum() <= 0:
        return 0.0
    lo, hi = 0.0, 1.0
    for _ in range(200):
        if (w * np.clip(hi * s, 0, 1)).sum() >= target:
            break
        hi *= 2.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if (w * np.clip(mid * s, 0, 1)).sum() < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _systematic(g, w, p):
    """계통추출: 선정 확률 p 를 순서대로 누적해 등간격으로 뽑는다(베르누이보다 분산이 작다)."""
    q = np.clip(p, 0, 1)
    if q.sum() <= 0:
        return np.zeros(len(q), dtype=np.int8)
    idx = g.permutation(len(q))
    c = np.cumsum(q[idx])
    start = g.random()
    ks = start + np.arange(int(np.floor(c[-1] - start)) + 1)
    ks = ks[ks <= c[-1]]
    out = np.zeros(len(q), dtype=np.int8)
    if len(ks):
        out[idx[np.searchsorted(c, ks)]] = 1
    return out


def generate(df, params, ctx):
    g = core.rng('B06')
    n = len(df)
    w = df['indwgt'].values if 'indwgt' in df.columns else np.full(n, 1.0)
    age = df['age'].values
    hid = df['hid'].values

    # ── 선행 블록 컬럼(없으면 안전 폴백) ──────────────────────────────────
    if '_inc_dec' in df.columns:
        inc_dec = df['_inc_dec'].values.astype(int) - 1
    else:                                       # B05 미구현 시: 개인 잠재변수로 대체
        inc_dec = np.clip((df['_u_income'].values * 10).astype(int), 0, 9)
    if '_prop_dec' in df.columns:
        pd9 = np.clip(df['_prop_dec'].values.astype(int) - 1, 0, 9)
        prop_dec = np.where(pd9 <= 1, 0, pd9 - 1)          # 1-2분위 병합 → 0..8
    else:
        prop_dec = np.clip(inc_dec - 1, 0, 8)
    h_prop = df['h_prop'].values.astype(float) if 'h_prop' in df.columns else np.zeros(n)

    # ── 1) 신청 후보 ──────────────────────────────────────────────────────
    cand = age >= 18                              # 부양자녀(18세 미만)는 신청 불가
    # §7 R17(itc_yn=1 ⇒ p_labinc+p_binc>0) 을 강제하기 위해 일용소득(p_dainc)은 제외한다.
    # 조특법상 일용근로소득도 근로소득이지만, 정합성 규칙 준수를 우선한다 [논리적추론].
    earn_cols = [c for c in ('p_labinc', 'p_binc') if c in df.columns]
    if earn_cols:                                 # B03 구현 시 §7 R17 강제
        cand &= (df[earn_cols].fillna(0).sum(axis=1).values > 0)
        soft_earn = np.ones(n)
    elif '_p_earned' in df.columns:
        cand &= (df['_p_earned'].fillna(0).values > 0)
        soft_earn = np.ones(n)
    else:   # 폴백: 근로·사업소득 보유 확률을 하드 필터가 아니라 점수 가중으로 반영 [가정]
        soft_earn = np.where(age < 20, 0.30, np.where(age < 60, 0.85,
                             np.where(age < 70, 0.62, 0.32)))

    # ── 2) 세법상 가구유형 (조특법 제100조의3제5항) ───────────────────────
    role = df['_role'].values
    is_head = df['head'].values == 1
    is_sp = role == 'spouse'
    has_sp_hh = pd.Series(is_sp).groupby(hid).transform('max').values
    n_child = df['_n_child_u18'].values if '_n_child_u18' in df.columns else np.zeros(n)
    # 동거 70세 이상 직계존속
    old_parent = pd.Series(((role == 'parent') & (age >= 70)).astype(int)).groupby(hid).transform('max').values
    # 배우자 총급여액 등 300만원 이상 여부 (맞벌이 판정)
    if earn_cols:
        pe = df[earn_cols].fillna(0).sum(axis=1).values
    elif '_p_earned' in df.columns:
        pe = df['_p_earned'].fillna(0).values
    else:                                         # [가정] 배우자 취업률 0.52
        pe = np.where(core.bernoulli(g, np.full(n, 0.52)).astype(bool), 5_000_000, 0)
    sp_earn = pd.Series(np.where(is_sp, pe, 0.0)).groupby(hid).transform('max').values

    hmember = np.full(n, 11, dtype=int)
    hh_applicant = is_head | is_sp                 # 가구주·배우자는 가구 기준으로 판정
    dual = hh_applicant & (has_sp_hh == 1) & (sp_earn >= 3_000_000)
    single_earner = hh_applicant & (~dual) & ((has_sp_hh == 1) | (n_child >= 1) | (old_parent == 1))
    hmember[single_earner] = 21
    hmember[dual] = 23
    # 비가구주·비배우자 성인은 자기 세법가구(대부분 단독가구)
    itc_child = np.where(hmember == 11, 0, np.minimum(n_child, 5)).astype(int)

    # ── 3) S0 기울기 점수 + 조특법 재산요건 ───────────────────────────────
    score = G_INC[inc_dec] * G_PROP[prop_dec] * soft_earn
    prop_ok = h_prop < PROP_LIMIT
    # 비가구주 신청자는 자기 세법가구 기준이므로 개인 재산으로 판정
    if 'p_prop' in df.columns:
        prop_ok = np.where(hh_applicant, prop_ok, df['p_prop'].values < PROP_LIMIT)
    cand &= prop_ok
    score = np.where(cand, np.maximum(score, 1e-4), 0.0)

    # ── 4) (연령대 × 가구유형) 셀 목표 IPF 1회 → 셀 내 점수비례 배정 ──────
    ab = np.digitize(age, AGE_CUTS)                # 0..5
    seed = np.zeros((6, 3))
    tcode = [11, 21, 23]
    for k in range(6):
        for j, t in enumerate(tcode):
            m = cand & (ab == k) & (hmember == t)
            seed[k, j] = (w[m] * score[m]).sum()
    seed = np.maximum(seed, 1.0)
    tgt_age = np.array(PAY_BY_AGE, float)
    tgt_type = np.array([PAY_BY_TYPE[t] for t in tcode], float)
    cell = core.ipf(seed, [((0,), tgt_age), ((1,), tgt_type)], max_iter=1)
    cell = cell * (N_PAY_EITC / cell.sum())

    itc_yn = np.zeros(n, dtype=int)
    for k in range(6):
        for j, t in enumerate(tcode):
            m = cand & (ab == k) & (hmember == t)
            if not m.any():
                continue
            lam = _solve_lambda(w[m], score[m], cell[k, j])
            itc_yn[np.flatnonzero(m)] = _systematic(g, w[m], lam * score[m])

    # 신청했으나 미지급 (지급제외) — 추출대상에 포함
    n_apply_net = N_APPLY_EITC + N_APPLY_CTC - N_APPLY_BOTH
    n_pay_net = N_PAY_EITC + N_PAY_CTC - N_PAY_BOTH
    rest = cand & (itc_yn == 0)
    lam = _solve_lambda(w[rest], score[rest], max(n_apply_net - n_pay_net, 0.0))
    rejected = np.zeros(n, dtype=int)
    rejected[np.flatnonzero(rest)] = _systematic(g, w[rest], lam * score[rest])

    # ── 5) 자녀장려금 ─────────────────────────────────────────────────────
    # 근로장려금 동시수급은 "itc_yn=1 에 점수 가중"이 아니라 **층(stratum) 목표**로 직접 맞춘다.
    # 종전의 가중치 배수(18배)는 동시수급률을 제어하지 못해 +20.1% 과다였고,
    # 자녀수 가중(nchw)도 손으로 고른 값이라 자녀수 구성이 국세통계와 어긋났다.
    # → 동시수급 여부(b) 별로 (가구유형 × 부양자녀수) 2×5 셀 목표를 IPF 로 만들고 셀 안에서 배정한다.
    #   행 주변분포 = 14-3-1 가구유형별  / 열 주변분포 = 14-3-1 부양자녀 인원별 (둘 다 [1차확인])
    ctc_cand = cand & (hmember != 11) & (itc_child >= 1)
    itc_child_yn = np.zeros(n, dtype=int)
    kk = [1, 2, 3, 4, 5]
    for b in (1, 0):
        rows = np.array([(CTC_BOTH_BY_TYPE[t] if b else CTC_BY_TYPE[t] - CTC_BOTH_BY_TYPE[t])
                         for t in (21, 23)], float)
        cols = np.array([(CTC_BOTH_BY_NCHILD[k] if b else CTC_BY_NCHILD[k] - CTC_BOTH_BY_NCHILD[k])
                         for k in kk], float)
        seed = np.zeros((2, len(kk)))
        masks = {}
        for i, t in enumerate((21, 23)):
            for j, k in enumerate(kk):
                m = ctc_cand & (hmember == t) & (itc_child == k) & (itc_yn == b)
                masks[(i, j)] = m
                seed[i, j] = (w[m] * score[m]).sum()
        cell = core.ipf(seed, [((0,), rows), ((1,), cols)], max_iter=1)
        for (i, j), m in masks.items():
            if not m.any() or cell[i, j] <= 0:
                continue
            lam = _solve_lambda(w[m], score[m], cell[i, j])
            itc_child_yn[np.flatnonzero(m)] = _systematic(g, w[m], lam * score[m])

    # ── 6) 금액 ───────────────────────────────────────────────────────────
    gw = np.array(GROSS_N, float); gw = gw / gw.sum()
    itc_amt = np.zeros(n)
    for t in tcode:
        m = (itc_yn == 1) & (hmember == t)
        c = int(m.sum())
        if c == 0:
            continue
        cap = GROSS_CAP[t]
        ww = gw.copy()
        for i, lb in enumerate(GROSS_LB):
            if lb >= cap:
                ww[i] = 0.0
        ww = ww / ww.sum()
        k = g.choice(len(ww), size=c, p=ww)
        x = np.array([g.uniform(GROSS_LB[i], min(GROSS_UB[i], cap)) for i in k])
        a = np.array([_eitc(v, t) for v in x]) * MAN
        a = np.where(h_prop[m] >= PROP_HALF, a * 0.5, a)      # 조특법 제100조의5제4항
        # 국세통계 가구유형별 평균 심사금액에 최종 정합 (재산·기한후신청 감액,
        # 자녀세액공제 차감 및 유형별 총급여 분포 차이를 흡수하는 보정)
        if a.mean() > 0:
            a = a * (AMT_BY_TYPE[t] / a.mean())
        itc_amt[np.flatnonzero(m)] = np.maximum(a, 10_000)

    itc_child_amt = np.zeros(n)
    m = itc_child_yn == 1
    if m.any():
        nc = np.clip(itc_child[m], 1, 5)
        base = np.array([CTC_AMT_BY_NCHILD[int(v)] for v in nc])
        jitter = np.clip(g.normal(1.0, 0.18, int(m.sum())), 0.35, 1.30)
        a = base * jitter
        for _ in range(3):                       # 상한(자녀수×70만원) 절단 후 평균 재정합
            a = a * (base.mean() / max(a.mean(), 1e-9))
            a = np.minimum(a, nc * CTC_MAX_PER_CHILD)
        itc_child_amt[np.flatnonzero(m)] = np.maximum(a, 10_000)

    # ── 출력: 추출대상 = 신청자(지급 + 지급제외) 개인, 그 밖 NaN ──────────
    applicant = (itc_yn == 1) | (itc_child_yn == 1) | (rejected == 1)
    nan = np.nan
    out = pd.DataFrame(index=df.index)
    out['itc_hmember'] = np.where(applicant, hmember, nan)
    out['itc_child'] = np.where(applicant, itc_child, nan)
    out['itc_yn'] = np.where(applicant, itc_yn, nan)
    out['itc_amt'] = np.where(itc_yn == 1, np.rint(itc_amt), nan)
    out['itc_child_yn'] = np.where(applicant, itc_child_yn, nan)
    out['itc_child_amt'] = np.where(itc_child_yn == 1, np.rint(itc_child_amt), nan)
    return out
