# -*- coding: utf-8 -*-
"""B18 모성보호급여 6종 (empins_*leave / shorthrs / uninsureleave)  — A3 / order 6

소스 (등급순)
  S1 R26 EIS 고용행정통계 「모성보호 지급자 현황 2022」 순지급자수(성별·연령10세별)
     params/raw/R26_EIS_모성보호지급자현황2022_{성별,연령10세별}.csv           [1차확인 2026-09-02]
     → 코드북 yn1 정의("2022년 중 한 번이라도 수급")와 정확히 일치하는 연간 실인원
  S1 R14 고용보험통계연보 2022 <표9-1><표9-2><표9-3> (규모별 수급금액, 통상임금 분포)
     params/raw/R14_T9-1_*.csv, R14_T9-2_*.csv, R14_T9-3_*.csv                [1차확인]
  S1 R14M 2022년 12월 고용보험통계 <표7-1><표7-3> (12월 수급자)  → yn2 비율     [1차확인]
  S1 R24 고용보험백서(2023년판) p.52~53·p.245·p.559 — 법정 급여수준·상한액      [1차확인]
  S1 R25 고용노동백서(2023년판) p.106~109·p.462 — 지원실적·평균 육아휴직일수     [1차확인]
  S1 R21 고용노동부 보도자료(2023.1.25) — 평균 사용기간, 자녀연령 분포, 3+3 이용자 [1차확인]
  S0 R02 <표3-27>~<표3-37> (2021 기준) — 가구시장소득 분위별 수급률 기울기        [1차확인]
     params/tab/A3_B18_S0_R02_모성보호_소득분위별.csv
  전사본: params/tab/A3_B18_모성보호급여_2022_총량.csv, *_법정단가.csv

생성 원칙
  (1) 총량 우선 — 전국 순지급자수 × 표본추출률(n/모집단)을 목표 인원으로 두고
      PPS 계통추출로 정확히 그 인원을 뽑는다(§4 총량 재현).
  (2) 조건부 구조 — S0 R02 소득분위 기울기 + EIS 성·연령 분포 + R21 자녀연령 분포로 score 구성.
  (3) 금액 — 법정 산식(통상임금×지급률, 상한/하한)에 R14 <표9-2> 통상임금 히스토그램을 결합.
  (4) §7 R12: 육아휴직 ⇒ 0~8세 자녀 ∧ 고용보험. 코드에서 하드 제약.
  (5) §4 규모 미달(기대 수급자 <3명) 변수는 전량 NaN.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

RAW = 'params/raw'
TAB = 'params/tab'

# ── [1차확인] 2022 전국 총량 (params/tab/A3_B18_모성보호급여_2022_총량.csv) ──────────
N_MAT      = 78045          # 출산전후휴가급여 연간 순지급자수 (EIS)
AMT_MAT    = 304849239710   # 출산전후휴가급여 연간 지급액 (고용보험통계연보 표9-1)
DEC_MAT    = 11700          # 2022.12 출산전후휴가급여 수급자 (2022.12 고용보험통계 표7-1)
N_PAR      = 282375         # 육아휴직급여 연간 순지급자수 (EIS)
N_PAR_M    = 67620
N_PAR_F    = 214755
AMT_PAR    = 1657230530120  # 육아휴직급여 연간 지급액 (표9-3) — 사후지급금 포함
DEC_PAR    = 99719          # 2022.12 육아휴직급여 수급자 (표7-3)
LEAVE_DAYS = 269.0          # 2022 평균 육아휴직일수 (고용노동백서 p.109)
N_SHT      = 36266          # 육아기 근로시간 단축급여 연간 순지급자수 (EIS)
N_SHT_M    = 3411
N_SHT_F    = 32855
AMT_SHT    = 107330000000   # 육아기 단축급여 연간 지급액 (고용보험백서 p.245)
SHT_MONTHS = 9.4            # 육아기 단축 평균 사용기간(개월) — R21
SHT_HOURS  = 12.2           # 육아기 단축 평균 주당 단축시간 — R21
N_SPS      = 16169          # 배우자출산휴가급여 연간 순지급자수 (EIS)
AMT_UNINS_TOT = 12775000000 # 고용보험 미적용자 출산급여 2022 지출액(고용노동백서 p.462)
AMT_UNINS     = 1500000     # 1인당 총 지급액(월 50만×3) — R02 p.114
N_DAD33    = 14830          # 3+3 부모육아휴직제 2022 이용자 (R21)

# ── [1차확인] 법정 단가 (고용보험백서 2023년판 p.52~53, p.559) ────────────────────
MAT_CAP_M   = 2_000_000     # 출산전후휴가급여 월 상한
PAR_RATE    = 0.80          # 육아휴직급여 통상임금 지급률(2022.1~ 전 기간 80%)
PAR_CAP_M   = 1_500_000     # 육아휴직급여 월 상한
PAR_FLOOR_M =   700_000     # 육아휴직급여 월 하한
POST_SHARE  = 0.25          # 사후지급금 비율(복귀 후 6개월 계속근무 시)
SHT_CAP1    = 2_000_000     # 육아기 단축: 최초 주5시간분 통상임금 상한(지급률 100%)
SHT_CAP2    = 1_500_000     # 육아기 단축: 나머지 단축분 통상임금 상한(지급률 80%)
SHT_RATE2   = 0.80
WEEK_HOURS  = 40.0          # 소정근로 주 40시간 기준

# ── [1차확인] R14 <표9-2> 출산전후휴가 초회수급자 통상임금 분포 (전체·계) ──────────
TW_EDGES = [0, 850_000, 1_100_000, 1_350_000, 1_600_000, 1_850_000,
            2_100_000, 2_350_000, 2_600_000, 3_000_000, None]
TW_W     = [260, 595, 494, 759, 1835, 12089, 11798, 10338, 11227, 23677]

# ── [1차확인] R14 <표9-1> 출산전후휴가급여 규모별 초회수급자·수급금액 ──────────────
#   (≤299인 = 우선지원대상기업 90일분 지원, 1,000인 이상 = 대규모기업 30일분)
MAT_SIZE   = ['le299', '300_999', 'ge1000']
MAT_SIZE_N = np.array([43340.0, 9208.0, 19638.0])
MAT_SIZE_A = np.array([233135175630.0, 27484189440.0, 40707688910.0])
MAT_SIZE_DAYS = np.array([90.0, 60.0, 30.0])   # 우선지원 90일 / 혼재 / 대규모 30일

# ── [1차확인] R26 EIS 연령10세별 순지급자수 ─────────────────────────────────────
EIS_AGE_BAND = [(0, 19), (20, 29), (30, 39), (40, 49), (50, 120)]
EIS_MAT = np.array([5, 12357, 62053, 3628, 1], float)
EIS_PAR = np.array([159, 52254, 217157, 12701, 102], float)
EIS_SHT = np.array([32, 9047, 26060, 1123, 4], float)

# ── [1차확인] S0 R02 소득분위별 수급률 (2021, 가구시장소득 10분위, 전체 재산분위) ──
S0_MAT = np.array([4.5, 8.1, 12.3, 15.5, 18.2, 21.3, 24.2, 29.6, 34.5, 35.3])   # 표3-27
S0_PAR = np.array([1.8, 3.1, 4.6, 5.4, 6.5, 7.6, 7.9, 8.8, 9.5, 9.6])           # 표3-30
S0_SHT = np.array([0.2, 0.2, 0.5, 0.8, 1.1, 1.1, 1.2, 1.5, 1.3, 0.9])           # 표3-32

# ── [1차확인] R21 육아휴직 자녀연령 분포 / 육아기단축 7~8세 비중 ─────────────────
PAR_KIDSHARE = {0: .3215, 1: .3215, 2: .0442, 3: .0442, 4: .0442,
                5: .0442, 6: .0442, 7: .0680, 8: .0680}     # 1세 이내 64.3%, 7~8세 13.6%
SHT_KIDSHARE = {0: .1200, 1: .1200, 2: .0940, 3: .0940, 4: .0940,
                5: .0940, 6: .0940, 7: .1450, 8: .1450}     # 7~8세 29.0%

SINGLE_SHARE = 0.04         # [가정] 육아휴직급여 수급자 중 한부모 근로자 특례 적용 비율
MIN_EXPECTED = 3.0          # §4 규모 미달 임계치 (기대 수급자 3명 미만 → 전량 NaN)


# ══════════════════════════════════════════════════════════════════ 공통 유틸
def _pps_select(g, p):
    """포함확률 p(합=목표인원)로 정확히 round(Σp)명을 뽑는 계통 PPS 추출."""
    p = np.clip(np.asarray(p, float), 0.0, 1.0)
    idx = np.flatnonzero(p > 0)
    out = np.zeros(len(p), dtype=np.int8)
    if idx.size == 0:
        return out
    order = idx[g.permutation(idx.size)]
    c = np.cumsum(p[order])
    u = g.random()
    prev = np.floor(np.concatenate(([0.0], c[:-1])) - u)
    cur = np.floor(c - u)
    out[order[cur > prev]] = 1
    return out


def _norm_target(score, elig, target_n):
    """score∝수급확률, Σp = target_n 이 되도록 정규화(상한 0.95, 초과분 재배분)."""
    s = np.where(elig, np.maximum(score, 0.0), 0.0)
    p = np.zeros(len(s))
    if s.sum() <= 0 or target_n <= 0:
        return p
    p = s / s.sum() * target_n
    for _ in range(30):
        over = p > 0.95
        if not over.any():
            break
        exc = float((p[over] - 0.95).sum())
        p[over] = 0.95
        rest = (s > 0) & ~over
        if not rest.any() or s[rest].sum() <= 0:
            break
        p[rest] += exc * s[rest] / s[rest].sum()
    return np.clip(p, 0, 1)


def _calib(vals, mask, target_nat, frac, lo=0.4, hi=2.5):
    """표본 금액 합 ÷ 추출률 = 전국 목표 총액이 되도록 1차원 스케일링(§4 총량 재현).
    법정 산식으로 그린 금액에 단일 계수만 곱한다(계수는 trace 에 기록)."""
    cur = float(np.nansum(np.where(mask, vals, 0.0))) / frac
    if cur <= 0:
        return vals, 1.0
    k = float(np.clip(target_nat / cur, lo, hi))
    return vals * k, k


def _norm_target_w(score, elig, target_pop, w):
    """포함확률 p ∝ score, **가중 합계** Σ p_i·indwgt_i = 전국 목표인원 이 되도록 정규화.
    (표본 가중치가 셀마다 다르므로 단순 인원 목표로 맞추면 가중 추정 총량이 어긋난다.)"""
    s = np.where(elig, np.maximum(score, 0.0), 0.0)
    p = np.zeros(len(s))
    den = float((s * w).sum())
    if den <= 0 or target_pop <= 0:
        return p
    p = s * (target_pop / den)
    for _ in range(30):
        over = p > 0.95
        if not over.any():
            break
        exc = float(((p[over] - 0.95) * w[over]).sum())
        p[over] = 0.95
        rest = (s > 0) & ~over
        d2 = float((s[rest] * w[rest]).sum()) if rest.any() else 0.0
        if d2 <= 0:
            break
        p[rest] += exc * s[rest] / d2
    return np.clip(p, 0, 1)


def _calib_w(vals, mask, target_nat, w, lo=0.4, hi=2.5):
    """Σ(금액×indwgt) = 전국 목표 총액이 되도록 단일계수 스케일링."""
    cur = float(np.nansum(np.where(mask, vals * w, 0.0)))
    if cur <= 0:
        return vals, 1.0
    k = float(np.clip(target_nat / cur, lo, hi))
    return vals * k, k


def _income_rank(df):
    """가구 소득 순위(0=최저 … 1=최고). B05 선행 없으면 _u_income 폴백."""
    for c in ('_h_eq_inc', '_h_minc_prelim'):
        if c in df.columns:
            r = df[c].rank(pct=True).values
            if np.isfinite(r).all():
                return r
    if '_recog_rank' in df.columns:
        return df['_recog_rank'].values            # 소득인정액 백분위(0=최저 … 1=최고)
    return df['_u_income'].values                  # [폴백] B03·B05 미구현 시


def _decile(rank):
    return np.clip((np.asarray(rank) * 10).astype(int), 0, 9)


def _ei_rate_table():
    """고용보험 피보험자(2022 연평균, R14 <표2-3>) ÷ 주민등록인구 → 성×연령대 가입률."""
    t = pd.read_csv(os.path.join(RAW, 'R14_T2-3_피보험자연평균_산업별연령별성별.csv'))
    t = t[(t['산업'].astype(str).str.replace(' ', '') == '전체')]
    t = t[t['연령'] != '계'].drop_duplicates(subset=['성별', '연령'])
    bands = {'18세 미만': (15, 17), '18~20세 미만': (18, 19), '20~24세 이하': (20, 24),
             '25~29세 이하': (25, 29), '30~34세 이하': (30, 34), '35~39세 이하': (35, 39),
             '40~44세 이하': (40, 44), '45~49세 이하': (45, 49), '50~54세 이하': (50, 54),
             '55~59세 이하': (55, 59), '60세 이상': (60, 74)}
    pop = pd.read_csv(os.path.join(RAW, 'POPUL_MOIS01_2022_11_sigungu_age1_sex.csv'))
    pop = pop[(pop.level == 'sigungu') & (pop.sex.isin(['male', 'female']))]
    pop['age'] = pop['age'].astype(int)
    rate = {}
    for sx, sname in ((1, '남'), (2, '여')):
        sub = t[t['성별'] == sname].set_index('연령')['value']
        psub = pop[pop.sex == ('male' if sx == 1 else 'female')]
        for k, (lo, hi) in bands.items():
            if k not in sub.index:
                continue
            P = float(psub[(psub.age >= lo) & (psub.age <= hi)]['pop'].sum())
            rate[(sx, lo, hi)] = min(0.97, float(sub[k]) / P) if P > 0 else 0.0
    return rate


def _empins_proxy(df):
    """고용보험 가입 여부. B16 이 만든 empins_yn1 이 있으면 그대로 사용.
    없으면 성×연령대 가입률(R14 표2-3 ÷ 주민등록)을 _u_emp 로 순위배정(폴백)."""
    if 'empins_yn1' in df.columns:
        return (df['empins_yn1'].fillna(0).values == 1).astype(np.int8), 'B16 empins_yn1'
    if '_empins_hist' in df.columns:
        return (df['_empins_hist'].fillna(0).values == 1).astype(np.int8), 'B16 _empins_hist'
    rate = _ei_rate_table()
    age = df['age'].values
    sex = df['gender'].values
    r = np.zeros(len(df))
    for (sx, lo, hi), v in rate.items():
        r[(sex == sx) & (age >= lo) & (age <= hi)] = v
    return (df['_u_emp'].values > (1.0 - r)).astype(np.int8), '폴백(R14 표2-3 성·연령별 가입률)'


def _band_idx(age, bands):
    out = np.zeros(len(age), dtype=int)
    for i, (lo, hi) in enumerate(bands):
        out[(age >= lo) & (age <= hi)] = i
    return out


def _rate_by_band(counts, age, mask, bands):
    """EIS 연령대별 수급자수 → 표본 내 연령대별 상대 수급성향(수급자수/해당 연령대 후보수)."""
    bi = _band_idx(age, bands)
    base = np.array([max(1, int(((bi == i) & mask).sum())) for i in range(len(bands))], float)
    rel = counts / base
    rel = rel / rel[rel > 0].mean() if (rel > 0).any() else np.ones_like(rel)
    return rel[bi]


def _discrete_mean(g, n, kmax, mean, kmin=1):
    """1..kmax 의 지수형 이산분포에서 평균이 mean 이 되도록 τ 를 풀어 추출."""
    ks = np.arange(kmin, kmax + 1, dtype=float)
    lo, hi = -6.0, 6.0
    for _ in range(60):
        mid = (lo + hi) / 2
        w = np.exp(mid * ks); w /= w.sum()
        m = float((w * ks).sum())
        if m < mean: lo = mid
        else: hi = mid
    w = np.exp(((lo + hi) / 2) * ks); w /= w.sum()
    return g.choice(ks.astype(int), size=n, p=w)


# ══════════════════════════════════════════════════════════════════ 생성
def generate(df, params, ctx):
    g = core.rng('B18')
    n = len(df)
    idx = df.index
    N_pop = float(df['_N_pop_person'].iloc[0])
    frac = n / N_pop                                   # 표본추출률(참고)
    w = df['indwgt'].astype(float).values if 'indwgt' in df.columns else np.full(n, N_pop / n)
    ei, ei_src = _empins_proxy(df)

    out = pd.DataFrame(index=idx)
    trace = {'표본추출률': frac, '고용보험_출처': ei_src}

    # ── 가구 내 최연소 0~8세 자녀 연령 ────────────────────────────────────────
    kid = df.loc[df['age'] <= 8, ['hid', 'age']]
    mink = kid.groupby('hid')['age'].min()
    minkid = df['hid'].map(mink).values                # NaN = 0~8세 자녀 없음
    has08 = np.isfinite(minkid)

    age = df['age'].values
    sex = df['gender'].values
    is_parent = df['_role'].isin(['head', 'spouse']).values & (age >= 19) & (age <= 54) & has08
    inc_d = _decile(_income_rank(df))

    # 통상임금 (R14 <표9-2> 히스토그램)
    tw = core.hist_loguniform(g, TW_EDGES, TW_W, n, pareto_alpha=3.0)
    tw = np.clip(tw, 600_000, 20_000_000)

    def kidw(share):
        w = np.ones(n)
        for a, s in share.items():
            m = (minkid == a) & is_parent
            b = max(1, int(m.sum()))
            w[m] = s / b
        return w / (w[is_parent].mean() if is_parent.any() else 1.0)

    # ══════════════════════════════ 1. 출산전후휴가급여 ═══════════════════════
    tgt_mat = N_MAT / w.mean()
    trace['출산전후휴가_기대인원'] = tgt_mat
    elig_mat = is_parent & (sex == 2) & (minkid == 0) & (ei == 1)
    for c in ('empins_matleave_yn1', 'empins_matleave_yn2',
              'empins_matleave_dur', 'empins_matleave_amt'):
        out[c] = np.nan
    if tgt_mat >= MIN_EXPECTED and elig_mat.any():
        sc = S0_MAT[inc_d] * _rate_by_band(EIS_MAT, age, elig_mat, EIS_AGE_BAND)
        yn1 = _pps_select(g, _norm_target_w(sc, elig_mat, N_MAT, w))
        m = yn1 == 1
        out['empins_matleave_yn1'] = np.where(m, 1.0, np.nan)
        # 사업장 규모 구분 → 지원일수·평균 수급금액 (R14 <표9-1>)
        ps = MAT_SIZE_N / MAT_SIZE_N.sum()
        cls = g.choice(len(MAT_SIZE), size=n, p=ps)
        cls_mean = (MAT_SIZE_A / MAT_SIZE_N)[cls]
        amt = core.lognormal_mean(g, cls_mean, 0.30, n)
        amt, k_mat = _calib_w(amt, m, AMT_MAT, w)
        trace['출산전후휴가_금액계수'] = k_mat
        daily = np.minimum(tw, MAT_CAP_M) / 30.0
        dur = np.clip(np.rint(amt / np.maximum(daily, 1)), 1, MAT_SIZE_DAYS[cls])
        out.loc[m, 'empins_matleave_dur'] = dur[m].astype(int)
        out.loc[m, 'empins_matleave_amt'] = np.rint(amt[m]).astype(np.int64)
        p2 = DEC_MAT / N_MAT
        yn2 = core.bernoulli(g, np.full(n, p2))
        out.loc[m, 'empins_matleave_yn2'] = yn2[m]
        trace['출산전후휴가_생성'] = int(m.sum())
        trace['출산전후휴가_총액_가중'] = float((out['empins_matleave_amt'].fillna(0) * w).sum())
    else:
        trace['출산전후휴가_규모미달'] = True

    # ══════════════════════════════ 2. 육아휴직급여 ═══════════════════════════
    tgt_par = N_PAR / w.mean()
    trace['육아휴직_기대인원'] = tgt_par
    elig_par = is_parent & (ei == 1)
    for c in ('empins_parentleave_yn1', 'empins_parentleave_yn2',
              'empins_parentleave_dur', 'empins_parentleave_amt',
              'empins_dadleave_yn', 'empins_singleleave_yn',
              'empins_postleave_yn', 'empins_postleave_amt'):
        out[c] = np.nan
    par_m = np.zeros(n, bool)
    monthly = np.clip(tw * PAR_RATE, PAR_FLOOR_M, PAR_CAP_M)
    if tgt_par >= MIN_EXPECTED and elig_par.any():
        sexw = np.where(sex == 2, N_PAR_F, N_PAR_M).astype(float)
        base_sex = np.array([max(1, int((elig_par & (sex == s)).sum())) for s in (1, 2)], float)
        sexw = np.where(sex == 2, N_PAR_F / base_sex[1], N_PAR_M / base_sex[0])
        sc = (S0_PAR[inc_d] * _rate_by_band(EIS_PAR, age, elig_par, EIS_AGE_BAND)
              * kidw(PAR_KIDSHARE) * sexw)
        yn1 = _pps_select(g, _norm_target_w(sc, elig_par, N_PAR, w))
        par_m = (yn1 == 1)
        out['empins_parentleave_yn1'] = np.where(par_m, 1.0, np.nan)
        # 수급 개월수: 12월 수급자×12 ÷ 연간 순지급자 = 4.24개월 [논리적추론]
        dur_mean = DEC_PAR * 12.0 / N_PAR
        dur = np.zeros(n, int)
        if par_m.any():
            dur[par_m] = _discrete_mean(g, int(par_m.sum()), 12, dur_mean)
        amt = monthly * dur * (1 - POST_SHARE)
        # 전국 총 지급액(1,657,231백만원)은 사후지급금을 포함한다. 월별 지급분 목표는
        # 총액 − 사후지급금(모형 추정) 이므로 두 단계로 나누어 캘리브레이션한다.
        post_each0 = POST_SHARE * monthly * (LEAVE_DAYS / 30.4)
        post_rate0 = 0.33
        post_nat0 = float(post_each0[par_m].mean()) * post_rate0 * N_PAR if par_m.any() else 0.0
        amt, k_par = _calib_w(amt, par_m, max(AMT_PAR - post_nat0, AMT_PAR * 0.5), w)
        amt = np.rint(amt)
        trace['육아휴직_금액계수'] = k_par
        out.loc[par_m, 'empins_parentleave_dur'] = dur[par_m]
        out.loc[par_m, 'empins_parentleave_amt'] = amt[par_m].astype(np.int64)
        p2 = np.clip((DEC_PAR / N_PAR) * dur / max(dur_mean, 1e-9), 0, 1)
        yn2 = core.bernoulli(g, p2)
        out.loc[par_m, 'empins_parentleave_yn2'] = yn2[par_m]
        trace['육아휴직_생성'] = int(par_m.sum())
        trace['육아휴직_dur평균'] = dur_mean

        # ── 사후지급금: 전국 지급액 잔여분(총액 − 월별지급분)으로 인원·금액 결정 ──
        paid_nat = float((amt * w)[par_m].sum())
        resid = max(AMT_PAR - paid_nat, 0.0)
        post_each = POST_SHARE * monthly * (LEAVE_DAYS / 30.4)     # 1인 사후지급금 추정
        mean_post = float(post_each[par_m].mean()) if par_m.any() else 1.0
        post_rate = float(np.clip((resid / max(mean_post, 1)) / N_PAR, 0.02, 0.90))
        ww = np.where(par_m, 13.0 - dur, 0.0)                       # 복귀자일수록(짧을수록) 높게
        pyn = _pps_select(g, _norm_target_w(ww, par_m, post_rate * N_PAR, w))
        pm = pyn == 1
        out.loc[pm, 'empins_postleave_yn'] = 1
        pa = post_each * g.lognormal(-0.5 * 0.35 ** 2, 0.35, n)
        pa, k_post = _calib_w(pa, pm, resid if resid > 0 else post_nat0, w)
        trace['사후지급금_금액계수'] = k_post
        out.loc[pm, 'empins_postleave_amt'] = np.maximum(np.rint(pa[pm]), 1).astype(np.int64)
        trace['사후지급금_비율'] = post_rate
        trace['사후지급금_생성'] = int(pm.sum())
        trace['육아휴직_총액_가중'] = float(((out['empins_parentleave_amt'].fillna(0) + out['empins_postleave_amt'].fillna(0)) * w).sum())

        # ── 3+3 부모육아휴직제(통상임금 100% 첫 3개월) 적용 여부 ──
        w33 = np.where(par_m & (minkid <= 1), 3.0, 0.3) * par_m
        d33 = _pps_select(g, _norm_target_w(w33, par_m, N_DAD33, w))
        out.loc[par_m, 'empins_dadleave_yn'] = 0
        out.loc[d33 == 1, 'empins_dadleave_yn'] = 1
        trace['3+3부모육아휴직_생성'] = int((d33 == 1).sum())

        # ── 한부모 근로자 육아휴직급여 특례 ──
        sp = df['_is_single_parent'].values == 1
        out.loc[par_m, 'empins_singleleave_yn'] = 0
        cand = par_m & sp
        if cand.any():
            sl = _pps_select(g, _norm_target_w(np.where(cand, 1.0, 0.0), cand,
                                               N_PAR * SINGLE_SHARE, w))
            out.loc[sl == 1, 'empins_singleleave_yn'] = 1
        trace['한부모특례_생성'] = int((out['empins_singleleave_yn'] == 1).sum())
    else:
        trace['육아휴직_규모미달'] = True

    # ══════════════════════════ 3. 육아기 근로시간 단축급여 ═══════════════════
    tgt_sht = N_SHT / w.mean()
    trace['육아기단축_기대인원'] = tgt_sht
    elig_sht = is_parent & (ei == 1)
    for c in ('empins_shorthrs_yn1', 'empins_shorthrs_yn2',
              'empins_shorthrs_dur', 'empins_shorthrs_amt'):
        out[c] = np.nan
    if tgt_sht >= MIN_EXPECTED and elig_sht.any():
        base_sex = np.array([max(1, int((elig_sht & (sex == s)).sum())) for s in (1, 2)], float)
        sexw = np.where(sex == 2, N_SHT_F / base_sex[1], N_SHT_M / base_sex[0])
        sc = (S0_SHT[inc_d] * _rate_by_band(EIS_SHT, age, elig_sht, EIS_AGE_BAND)
              * kidw(SHT_KIDSHARE) * sexw * np.where(par_m, 0.4, 1.0))
        # [T6] 표본 6~8행 규모이므로 포함확률 계통추출 대신, 점수 비례 Gumbel 순위로 정렬해
        #      Σindwgt 가 전국 수급자수(N_SHT)에 가장 가까워지는 지점까지 채운다(column_contract C3).
        _s = np.where(elig_sht, np.maximum(sc, 0.0), 0.0); _ok = _s > 0
        _key = np.full(len(_s), -np.inf)
        _key[_ok] = np.log(_s[_ok]) - np.log(-np.log(np.clip(g.random(int(_ok.sum())), 1e-12, 1 - 1e-12)))
        _o = np.argsort(-_key); _o = _o[np.isfinite(_key[_o])]; _cw = np.cumsum(w[_o])
        _j = min(int(np.searchsorted(_cw, N_SHT)), len(_cw) - 1)
        _k = _j + 1 if (_j == 0 or abs(_cw[_j] - N_SHT) <= abs(_cw[_j - 1] - N_SHT)) else _j
        yn1 = np.zeros(len(_s), dtype=np.int8); yn1[_o[:_k]] = 1
        m = yn1 == 1
        out['empins_shorthrs_yn1'] = np.where(m, 1.0, np.nan)
        # 월 급여 = 최초 주5시간분 100%(통상임금 상한 200만) + 나머지 80%(상한 150만)
        hours = np.clip(g.normal(SHT_HOURS, 3.5, n), 5.0, 25.0)
        mon = (np.minimum(tw, SHT_CAP1) * (5.0 / WEEK_HOURS)
               + np.minimum(tw, SHT_CAP2) * SHT_RATE2 * (hours - 5.0) / WEEK_HOURS)
        # 연내 수급개월: 전국 총 지급액에 맞춰 평균 개월수를 1차원 캘리브레이션
        base_mean = 12.0 * SHT_MONTHS / (12.0 + SHT_MONTHS)
        tgt_mean_amt = AMT_SHT / N_SHT
        mm = float(mon[m].mean()) if m.any() else 1.0
        dur_mean = float(np.clip(tgt_mean_amt / max(mm, 1.0), 1.2, 12.0))
        dur = np.zeros(n, int)
        if m.any():
            dur[m] = _discrete_mean(g, int(m.sum()), 12, dur_mean)
        out.loc[m, 'empins_shorthrs_dur'] = dur[m]
        sa, k_sht = _calib_w(mon * dur, m, AMT_SHT, w)
        trace['육아기단축_금액계수'] = k_sht
        out.loc[m, 'empins_shorthrs_amt'] = np.maximum(np.rint(sa[m]), 1).astype(np.int64)
        p2 = np.clip(dur / 12.0, 0, 1)
        yn2 = core.bernoulli(g, p2)
        out.loc[m, 'empins_shorthrs_yn2'] = yn2[m]
        trace['육아기단축_생성'] = int(m.sum())
        trace['육아기단축_dur평균_캘리브'] = (dur_mean, base_mean)
        trace['육아기단축_총액_가중'] = float((out['empins_shorthrs_amt'].fillna(0) * w).sum())
    else:
        trace['육아기단축_규모미달'] = True

    # ══════════════════════════ 4. 배우자출산휴가급여 (규모 판정) ═════════════
    for c in ('empins_spouseleave_yn1', 'empins_spouseleave_yn2',
              'empins_spouseleave_dur', 'empins_spouseleave_amt'):
        out[c] = np.nan
    elig_sps = is_parent & (sex == 1) & (minkid == 0) & (ei == 1)
    sc_sps = np.array([0.6, 0.7, 0.9, 2.6, 5.8, 9.4, 9.2, 7.7, 4.8, 2.4])[inc_d]   # S0 표3-28
    p_sps = _norm_target_w(sc_sps, elig_sps, N_SPS, w)
    tgt_sps = float(p_sps.sum())                      # 표본 내 기대 수급자(Σ포함확률)
    trace['배우자출산휴가_기대인원'] = tgt_sps
    if tgt_sps >= MIN_EXPECTED and elig_sps.any():
        yn1 = _pps_select(g, p_sps)
        m = yn1 == 1
        out['empins_spouseleave_yn1'] = np.where(m, 1.0, np.nan)
        amt = np.minimum(np.minimum(tw, MAT_CAP_M) / 209.0 * 8.0, 382770.0 / 5.0) * 5.0
        out.loc[m, 'empins_spouseleave_dur'] = 5
        out.loc[m, 'empins_spouseleave_amt'] = np.rint(amt[m]).astype(np.int64)
        out.loc[m, 'empins_spouseleave_yn2'] = core.bernoulli(g, np.full(n, 5 / 365.0 * 31))[m]
        trace['배우자출산휴가_생성'] = int(m.sum())
    else:
        trace['배우자출산휴가_규모미달'] = True

    # ══════════════════════ 5. 고용보험 미적용자 출산급여 (규모 판정) ═════════
    n_unins = AMT_UNINS_TOT / AMT_UNINS
    for c in ('empins_uninsureleave_yn1', 'empins_uninsureleave_yn2',
              'empins_uninsureleave_dur', 'empins_uninsureleave_amt'):
        out[c] = np.nan
    elig_uns = is_parent & (sex == 2) & (minkid == 0) & (ei == 0)
    sc_uns = np.array([3.3, 6.2, 6.3, 5.8, 4.7, 3.6, 3.1, 3.0, 2.1, 1.6])[inc_d]   # S0 표3-33
    p_uns = _norm_target_w(sc_uns, elig_uns, n_unins, w)
    tgt_uns = float(p_uns.sum())
    trace['미적용자출산급여_기대인원'] = tgt_uns
    if tgt_uns >= MIN_EXPECTED and elig_uns.any():
        yn1 = _pps_select(g, p_uns)
        m = yn1 == 1
        out['empins_uninsureleave_yn1'] = np.where(m, 1.0, np.nan)
        out.loc[m, 'empins_uninsureleave_dur'] = 90
        out.loc[m, 'empins_uninsureleave_amt'] = int(AMT_UNINS)
        out.loc[m, 'empins_uninsureleave_yn2'] = core.bernoulli(g, np.full(n, 0.25))[m]
        trace['미적용자출산급여_생성'] = int(m.sum())
    else:
        trace['미적용자출산급여_규모미달'] = True

    # ══════════════════════════════ 정합성 강제 (§7 R24) ══════════════════════
    for stem in ('empins_matleave', 'empins_spouseleave', 'empins_parentleave',
                 'empins_shorthrs', 'empins_uninsureleave'):
        y1, y2 = f'{stem}_yn1', f'{stem}_yn2'
        bad = (out[y2] == 1) & (out[y1] != 1)
        out.loc[bad, y2] = 0
        # amt>0 ⇔ yn1=1
        a, d = f'{stem}_amt', f'{stem}_dur'
        out.loc[out[y1] != 1, [a, d, y2]] = np.nan
        out.loc[out[y1] == 1, a] = np.maximum(out.loc[out[y1] == 1, a].fillna(1), 1)
    out.loc[out['empins_parentleave_yn1'] != 1,
            ['empins_dadleave_yn', 'empins_singleleave_yn', 'empins_postleave_yn']] = np.nan
    out.loc[out['empins_postleave_yn'] != 1, 'empins_postleave_amt'] = np.nan

    # dtype: NaN 을 보존해야 하므로 float64 로 두되 값은 모두 정수(원·일·개월).
    # 최종 산출(tools/export_final.py)에서 Int64 로 변환된다.
    for c in out.columns:
        out[c] = np.rint(pd.to_numeric(out[c], errors='coerce').astype(float))

    ctx.setdefault('trace', {})['B18'] = trace
    print('  [B18]', {k: (round(v, 4) if isinstance(v, float) else v) for k, v in trace.items()})
    return out
