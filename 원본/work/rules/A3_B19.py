# -*- coding: utf-8 -*-
"""B19 국민취업지원제도·국민내일배움카드 (kua_*, vocaedu_*)  — A3 / order 6

소스 (등급순)
  S0 R02 <표3-42><표3-44><표3-45><표3-46> (2021 기준) — 가구시장소득 분위별·가구주 연령대별
     국민취업지원제도 수급 가구 비중, 평균 수급액   [1차확인 2026-09-02]
     전사본 params/tab/A3_B19_S0_R02_국민취업_소득분위별.csv
  S1 R27 EIS 고용행정통계 「국민취업지원제도 참여현황 2022」(유형별·성별·연령별)
     「수당 지급현황 2022」(구직촉진수당·취업성공수당 건수·지급액)   [1차확인]
     params/raw/R27_EIS_국민취업지원제도*.csv
  S1 R25 고용노동백서(2023년판) p.538 — 2022 실적(284,811명), 지원요건·단가   [1차확인]
  S1 고용노동부 민원상담(moel.go.kr) — 취업활동비용(훈련참여지원수당) 월 284,000원 [1차확인]
  S1 R24 고용보험백서(2023년판) <표3-2-18><표3-2-19><표3-2-20> — 국민내일배움카드
     계좌발급·훈련실시(순인원)·예산집행액                              [1차확인]
     전사본 params/tab/A3_B19_국민취업지원제도_2022.csv, A3_B19_국민내일배움카드_2022.csv

생성 원칙
  (1) 총량 우선: 전국 참여자·수급자 × 표본추출률을 목표로 PPS 계통추출.
  (2) 조건부 구조: EIS 연령별·성별 분포(2022, S1) × S0 R02 소득분위 기울기(역U자, 3~4분위 정점).
  (3) 지시서 조건부 규칙 — 1유형 ⇒ 실업급여 미수급 (B17 선행 시 하드 제약).
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

RAW = 'params/raw'

# ── [1차확인] EIS 국민취업지원제도 참여현황 2022 ────────────────────────────────
KUA_BANDS = [(15, 17), (18, 19), (20, 24), (25, 29), (30, 34), (35, 39),
             (40, 44), (45, 49), (50, 54), (55, 59), (60, 64), (65, 69)]
KUA_TOT = np.array([1238, 5382, 75469, 82385, 33589, 14589,
                    14418, 12871, 13640, 11718, 11740, 6703], float)
KUA_T1 = np.array([864, 3845, 57447, 65575, 28280, 10960,
                   10639, 9478, 10137, 8756, 8059, 4624], float)
N_KUA = 283742          # 참여자 총계 (EIS)
N_KUA1 = 218664         # 1유형
N_KUA2 = 65078          # 2유형
KUA_M, KUA_F = 119759, 163983

# ── [1차확인] EIS 수당 지급현황 2022 ───────────────────────────────────────────
JB_CNT, JB_AMT = 1182955, 586950348496      # 구직촉진수당 건수·지급액
EB_CNT, EB_AMT = 95208, 62898780000         # 취업성공수당 건수·지급액
JB_BASE, JB_DEP = 500_000, 100_000          # 구직촉진수당 월 기본액 / 부양가족 1인당 추가
JB_MAXFREQ = 6
EB_1ST, EB_2ND = 500_000, 1_000_000         # 취업성공수당 근속3개월/6개월분
ACT_MONTH = 284_000                         # 취업활동비용(훈련참여지원수당) 월 지원액

# ── [1차확인] 국민내일배움카드 2022 ────────────────────────────────────────────
N_VOCA = 739097                 # 훈련실시 순인원 (<표3-2-19>)
AMT_VOCA = 1062528000000        # 예산집행액 1,062,528백만원 (<표3-2-20>)
VOCA_CAP = 5_000_000            # 1인당 지원한도 5년간 300~500만원 (고용보험백서 p.221)
# [1차확인] 고용보험백서 <표3-2-7> 2022 훈련생 구성(실업자 계열 579,763명)
VOCA_SEX = (0.317, 0.683)                       # 남, 여
VOCA_AGE = [((15, 29), 0.371), ((30, 39), 0.167), ((40, 49), 0.170), ((50, 64), 0.292)]

# ── [1차확인] S0 R02 <표3-46> 1·2유형 수급가구 비중, 소득 10분위 (2021) ────────
S0_KUA_INC = np.array([1.9, 2.8, 3.0, 3.0, 2.9, 2.6, 2.1, 1.5, 1.1, 0.6])
# ── [1차확인] S0 R02 <표3-45> 가구주 연령대별 (18-25/26-39/40-49/50-64) ────────
S0_KUA_HEADAGE = {(15, 25): 3.0, (26, 39): 1.9, (40, 49): 1.0, (50, 69): 1.7}

# ── [가정] 파라미터 ────────────────────────────────────────────────────────────
A_DEP_P = np.array([0.75, 0.15, 0.07, 0.03])   # 구직촉진수당 부양가족 수 분포 [가정]
A_YN2 = 0.50            # 12.31 기준 참여 비율 [논리적추론] 취업지원서비스기간 1년·연중 균등진입
A_ACT_SHARE = 0.50      # 2유형 참여자 중 직업훈련(취업활동비용) 수급 비율 [가정]
A_ACT_FREQ = 3.5        # 취업활동비용 평균 지원 개월수 [가정] (최대 6개월)
MIN_EXPECTED = 3.0


def _pps_select(g, p):
    p = np.clip(np.asarray(p, float), 0.0, 1.0)
    idx = np.flatnonzero(p > 0)
    out = np.zeros(len(p), dtype=np.int8)
    if idx.size == 0:
        return out
    order = idx[g.permutation(idx.size)]
    c = np.cumsum(p[order]); u = g.random()
    prev = np.floor(np.concatenate(([0.0], c[:-1])) - u)
    out[order[np.floor(c - u) > prev]] = 1
    return out


def _norm_target(score, elig, target_n):
    s = np.where(elig, np.maximum(score, 0.0), 0.0)
    p = np.zeros(len(s))
    if s.sum() <= 0 or target_n <= 0:
        return p
    p = s / s.sum() * target_n
    for _ in range(30):
        over = p > 0.95
        if not over.any():
            break
        exc = float((p[over] - 0.95).sum()); p[over] = 0.95
        rest = (s > 0) & ~over
        if not rest.any() or s[rest].sum() <= 0:
            break
        p[rest] += exc * s[rest] / s[rest].sum()
    return np.clip(p, 0, 1)


def _calib(vals, mask, target_nat, frac, lo=0.4, hi=2.5):
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
    for c in ('_h_eq_inc', '_h_minc_prelim'):
        if c in df.columns:
            r = df[c].rank(pct=True).values
            if np.isfinite(r).all():
                return r
    if '_recog_rank' in df.columns:
        return df['_recog_rank'].values    # 소득인정액 백분위(0=최저 … 1=최고)
    return df['_u_income'].values          # [폴백] B03·B05 미구현 시


def _pop_band(band):
    """주민등록 2022.11 인구 (연령대 합계) — EIS 참여자수의 분모."""
    pop = pd.read_csv(os.path.join(RAW, 'POPUL_MOIS01_2022_11_sigungu_age1_sex.csv'))
    pop = pop[(pop.level == 'sigungu') & (pop.sex.isin(['male', 'female']))]
    pop['age'] = pop['age'].astype(int)
    return np.array([float(pop[(pop.age >= lo) & (pop.age <= hi)]['pop'].sum()) for lo, hi in band])


def _bandidx(age, bands):
    out = np.full(len(age), -1, int)
    for i, (lo, hi) in enumerate(bands):
        out[(age >= lo) & (age <= hi)] = i
    return out


def _headage_w(df):
    hd = df[df['head'] == 1].set_index('hid')['age']
    ha = df['hid'].map(hd).values
    w = np.ones(len(df))
    for (lo, hi), v in S0_KUA_HEADAGE.items():
        w[(ha >= lo) & (ha <= hi)] = v
    w[ha > 69] = S0_KUA_HEADAGE[(50, 69)]
    return w / w.mean()


def generate(df, params, ctx):
    g = core.rng('B19')
    n = len(df)
    N_pop = float(df['_N_pop_person'].iloc[0])
    frac = n / N_pop
    w = df['indwgt'].astype(float).values if 'indwgt' in df.columns else np.full(n, N_pop / n)
    out = pd.DataFrame(index=df.index)
    trace = {'표본추출률': frac}

    age = df['age'].values
    sex = df['gender'].values
    inc_r = _income_rank(df)
    inc_d = np.clip((inc_r * 10).astype(int), 0, 9)
    u_emp = df['_u_emp'].values
    u_wel = df['_u_welfare'].values

    # ════════════════════ 1. 국민취업지원제도 참여 (kua_yn1) ═══════════════════
    bi = _bandidx(age, KUA_BANDS)
    popb = _pop_band(KUA_BANDS)
    band_rate = np.zeros(len(KUA_BANDS))
    band_rate = KUA_TOT / popb                       # 전국 연령대별 참여율
    elig = bi >= 0
    sexw = np.where(sex == 2, KUA_F, KUA_M).astype(float)
    base_sex = np.array([max(1, int((elig & (sex == s)).sum())) for s in (1, 2)], float)
    sexw = np.where(sex == 2, KUA_F / base_sex[1], KUA_M / base_sex[0])
    # 미취업·취업취약 성향: _u_emp 낮을수록 ↑ (블록 간 상관, §4.1)
    empw = 1.6 - 1.2 * u_emp
    score = np.where(elig, band_rate[np.clip(bi, 0, len(KUA_BANDS) - 1)], 0.0) \
        * S0_KUA_INC[inc_d] * _headage_w(df) * sexw * empw * (0.7 + 0.6 * u_wel)

    tgt = N_KUA / w.mean()
    trace['국민취업_기대인원'] = tgt
    for c in ('kua_yn1', 'kua_yn2', 'kua_type', 'kua_jobseekbn_amt', 'kua_jobseekbn_freq',
              'kua_employmentbn_amt', 'kua_jobseekact_amt'):
        out[c] = np.nan
    kua = np.zeros(n, bool)
    if tgt >= MIN_EXPECTED and elig.any():
        kua = _pps_select(g, _norm_target_w(score, elig, N_KUA, w)) == 1
        out['kua_yn1'] = np.where(kua, 1.0, np.nan)
        out.loc[kua, 'kua_yn2'] = core.bernoulli(g, np.full(n, A_YN2))[kua]

        # ── 참여유형: EIS 연령대별 1유형 비율 ──────────────────────────────
        p1 = np.where(elig, (KUA_T1 / KUA_TOT)[np.clip(bi, 0, len(KUA_BANDS) - 1)], 0.0)
        # 1유형은 소득·재산 요건이 엄격 → 고소득 상위 분위는 2유형으로
        p1 = np.clip(p1 * (1.35 - 0.7 * inc_r), 0, 1)
        # 표본 내 1유형 비율이 전국 실적(218,664/283,742)과 일치하도록 단일계수 보정
        if kua.any() and p1[kua].mean() > 0:
            p1 = np.clip(p1 * (N_KUA1 / N_KUA) / p1[kua].mean(), 0, 1)
        typ = np.where(core.bernoulli(g, p1) == 1, 1, 2)
        # 지시서 조건부 규칙: 1유형 ⇒ 실업급여 미수급 (B17 선행 시)
        if 'unempbn_jobseekbn_yn' in df.columns:
            typ = np.where(df['unempbn_jobseekbn_yn'].fillna(0).values == 1, 2, typ)
        out.loc[kua, 'kua_type'] = typ[kua]
        n1 = int(((typ == 1) & kua).sum()); n2 = int(((typ == 2) & kua).sum())
        trace['국민취업_생성'] = int(kua.sum()); trace['1유형/2유형'] = (n1, n2)
        trace['목표_1유형비율'] = N_KUA1 / N_KUA

        # ── 구직촉진수당 (1유형) ──────────────────────────────────────────
        m1 = kua & (typ == 1)
        if m1.any():
            freq_mean = JB_CNT / N_KUA1                       # 5.41회 [논리적추론]
            ks = np.arange(1, JB_MAXFREQ + 1, dtype=float)
            p6 = (freq_mean - 3.0) / 3.0                      # 6회 확률 (나머지 1~5 균등)
            pw = np.full(JB_MAXFREQ, (1 - p6) / (JB_MAXFREQ - 1)); pw[-1] = p6
            pw = np.clip(pw, 1e-6, None); pw /= pw.sum()
            freq = g.choice(ks.astype(int), size=n, p=pw)
            dep = g.choice(np.arange(len(A_DEP_P)), size=n, p=A_DEP_P)
            unit = JB_BASE + JB_DEP * dep                     # 월 지급단가(기본+부양가족)
            # EIS 건당 평균 지급액(586,950,348,496 / 1,182,955 = 496,173원)이 월 기본액
            # 500,000원보다 작다 → 일부 회차가 일할계산(중도 중단·취업)된 것으로 본다.
            # E[pay] = unit×(1-q) + unit×q×0.55 = 496,173  →  q 를 역산 [논리적추론]
            per_pay = JB_AMT / JB_CNT
            q = float(np.clip((1 - per_pay / unit.mean()) / 0.45, 0.0, 0.6))
            R = g.random((n, JB_MAXFREQ))
            part = (R < q)
            fracpay = np.where(part, g.uniform(0.1, 1.0, (n, JB_MAXFREQ)), 1.0)
            keep = (np.arange(JB_MAXFREQ)[None, :] < freq[:, None])
            amt = (unit[:, None] * fracpay * keep).sum(axis=1)
            amt = np.rint(amt / 10.0) * 10.0
            out.loc[m1, 'kua_jobseekbn_freq'] = freq[m1]
            out.loc[m1, 'kua_jobseekbn_amt'] = np.maximum(amt[m1], 1)
            trace['구직촉진수당_생성'] = int(m1.sum())
            trace['구직촉진수당_일할계산비율_q'] = q
            trace['구직촉진수당_총액_가중'] = float((out['kua_jobseekbn_amt'].fillna(0) * w).sum())

        # ── 취업성공수당: 건수·지급액 연립으로 1차분만/1+2차 인원 분해 ────────
        #   n1건 + 2·n2건 = 95,208 ; 50만·n1 + 150만·n2 = 628.99억 → n1=34,029, n2=30,590
        _a = EB_CNT
        _b = EB_AMT / EB_1ST                    # = n1 + 3·n2  (150만/50만 = 3)
        n_full = (_b - _a)                      # n2
        n_part = _a - 2 * n_full                # n1
        n_eb = n_part + n_full
        tgt_eb = n_eb / w.mean()
        trace['취업성공수당_기대인원'] = tgt_eb
        if tgt_eb >= MIN_EXPECTED and kua.any():
            ww = np.where(kua, 0.4 + 1.2 * u_emp, 0.0)        # 취업 성공 → 고용안정 성향 높음
            eb = _pps_select(g, _norm_target_w(ww, kua, n_eb, w)) == 1
            # 근속 6개월까지 도달(50만+100만) vs 3개월분만(50만) — 인원 비율은 PPS 로 고정
            full = _pps_select(g, _norm_target(np.where(eb, 1.0, 0.0), eb,
                                               (n_full / n_eb) * int(eb.sum()))) == 1
            ea = np.where(full, EB_1ST + EB_2ND, EB_1ST).astype(float)
            out.loc[eb, 'kua_employmentbn_amt'] = ea[eb]
            trace['취업성공수당_생성'] = int(eb.sum())
            trace['취업성공수당_전액수급'] = int((eb & full).sum())
            trace['취업성공수당_총액_가중'] = float((out['kua_employmentbn_amt'].fillna(0) * w).sum())
        else:
            trace['취업성공수당_규모미달'] = True

        # ── 취업활동비용 (2유형 직업훈련 참여자) ─────────────────────────────
        m2 = kua & (typ == 2)
        tgt_act = N_KUA2 * A_ACT_SHARE / w.mean()
        trace['취업활동비용_기대인원'] = tgt_act
        if tgt_act >= MIN_EXPECTED and m2.any():
            act = _pps_select(g, _norm_target_w(np.where(m2, 1.0, 0.0), m2,
                                                 N_KUA2 * A_ACT_SHARE, w)) == 1
            fr = np.clip(np.rint(g.normal(A_ACT_FREQ, 1.6, n)), 1, 6)
            out.loc[act, 'kua_jobseekact_amt'] = fr[act] * ACT_MONTH
            trace['취업활동비용_생성'] = int(act.sum())
        else:
            trace['취업활동비용_규모미달'] = True
    else:
        trace['국민취업_규모미달'] = True

    # ════════════════════ 2. 국민내일배움카드 (vocaedu_*) ══════════════════════
    out['vocaedu_yn'] = np.nan
    out['vocaedu_amt'] = np.nan
    eligv = (age >= 15) & (age <= 64)
    tgtv = N_VOCA / w.mean()
    trace['내일배움카드_기대인원'] = tgtv
    if tgtv >= MIN_EXPECTED and eligv.any():
        # 훈련 참여 성향 [논리적추론]: 실업자 일반직종 50%·재직자 33%·청년 특화훈련 구성
        #   → 20~40대 집중, 고용보험 이력(재직자)·구직활동(실업자) 양쪽 포함
        aw = np.zeros(n)
        for (lo, hi), sh in VOCA_AGE:
            m = eligv & (age >= lo) & (age <= hi)
            aw[m] = sh / max(1, int(m.sum()))
        sw = np.where(sex == 2, VOCA_SEX[1], VOCA_SEX[0])
        base_sex = np.array([max(1, int((eligv & (sex == s)).sum())) for s in (1, 2)], float)
        sw = np.where(sex == 2, VOCA_SEX[1] / base_sex[1], VOCA_SEX[0] / base_sex[0])
        vw = aw * sw * (0.7 + 0.6 * (1 - u_emp)) * (0.8 + 0.4 * u_wel)
        if kua.any():
            vw = vw * np.where(kua, 2.0, 1.0)       # 국취 참여자는 직업훈련 연계 비중 높음
        vy = _pps_select(g, _norm_target_w(vw, eligv, N_VOCA, w)) == 1
        out['vocaedu_yn'] = np.where(vy, 1.0, np.nan)
        va = core.lognormal_mean(g, np.full(n, AMT_VOCA / N_VOCA), 0.75, n)
        k_v = 1.0
        for _ in range(6):                          # 상한(백서 p.221) 절단 ↔ 총량 캘리브 반복
            va = np.clip(va, 50_000, VOCA_CAP)
            va, k1 = _calib_w(va, vy, AMT_VOCA, w); k_v *= k1
            if abs(k1 - 1) < 1e-4:
                break
        va = np.clip(va, 50_000, VOCA_CAP)
        out.loc[vy, 'vocaedu_amt'] = np.maximum(np.rint(va[vy]), 1)
        trace['내일배움카드_생성'] = int(vy.sum()); trace['내일배움카드_금액계수'] = k_v
        trace['내일배움카드_총액_가중'] = float((out['vocaedu_amt'].fillna(0) * w).sum())
    else:
        trace['내일배움카드_규모미달'] = True

    # ══════════════════════════ 정합성 (§7 R24 · 지시서 조건부) ════════════════
    ok = out['kua_yn1'] == 1
    out.loc[~ok, ['kua_yn2', 'kua_type', 'kua_jobseekbn_amt', 'kua_jobseekbn_freq',
                  'kua_employmentbn_amt', 'kua_jobseekact_amt']] = np.nan
    out.loc[out['kua_type'] != 1, ['kua_jobseekbn_amt', 'kua_jobseekbn_freq']] = np.nan
    out.loc[out['kua_type'] != 2, 'kua_jobseekact_amt'] = np.nan
    out.loc[out['vocaedu_yn'] != 1, 'vocaedu_amt'] = np.nan
    for c in out.columns:
        out[c] = np.rint(pd.to_numeric(out[c], errors='coerce').astype(float))

    ctx.setdefault('trace', {})['B19'] = trace
    print('  [B19]', {k: (round(v, 4) if isinstance(v, float) else v) for k, v in trace.items()})
    return out
