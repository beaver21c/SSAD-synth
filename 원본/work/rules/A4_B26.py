# -*- coding: utf-8 -*-
"""B26 기초연금 (bp_yn1 · bp_yn2 · bp_type · bp_dur · bp_amt) — A4 / order 5 / 5변수

소스 (등급순, 접근일 2026-09-02)
  S1 R04 보건복지부 「통계로 본 2022년 기초연금」  ← 1순위
       params/raw/R04_통계로본2022년기초연금.pdf
       · 2.1 성별·연령별 수급자 현황 (원문 p24~27)  → 전사본 R04_2-1_성별연령별수급자현황.csv
         2022: 65세이상인구 9,250,116 / 수급자 6,238,798 / 수급률 67.4%
               남자 2,484,255 · 여자 3,754,543
         연령별 수급률 65세 50.7 / 66~69 58.7 / 70~74 65.4 / 75~79 71.9 /
                       80~84 79.2 / 85~89 82.8 / 90~94 86.3 / 95~99 89.4 / 100+ 86.9 (%)
       · 2.4 연금액별 수급자 현황 (원문 p34·p36)  [1차확인, 본 파일 상수로 전사]
         전액 5,574,659 (단독·부부1인 3,232,240 / 부부2인 2,342,419), 감액 664,139,
         평균연금액 271,852원
  S1 R05 표5-1-9 기초연금 수급자수(가구형태·연령·시도) 2022
       params/raw/R05_5-1-9_기초노령연금수급자수_가구형태연령시도별.csv  [1차확인]
       단독가구 3,029,979 / 부부1인 514,425 / 부부2인 2,694,394
  S1 R07 복지사업 월별 급여지급 현황 (data.go.kr 15009571)
       params/raw/R07_연간집계_서비스별_건당평균지급액_2022.csv  [1차확인]
       기초연금 지급건수 72,957,947건 · 지급액 20,095,039백만원 · 건당월액 275,433원
  S1 R08 복지사업 월별 수급권자 현황 (15009570) → 연중 진입·탈락
  S2 R17 통계청 2022년 연금통계 보도자료: 기초연금 616.8만명·월평균 27.9만원 (총량 검증)
  S0 R01 <표 2-36> 기초연금 수급률 10.8% · 수급자 평균 285만원 (2020년 기준, 구조 검증용)

조건부 규칙 (§7)
  R01 bp_yn1=1 ⇒ age≥65            — 65세 미만은 후보에서 제외
  R02 bp_type∈{2,3} ⇒ _spouse_age≥65 — 배우자가 없거나 65세 미만이면 단독(1)
  소득인정액 하위 70% — B05 의 _recog_rank(없으면 B24 의 _recog_rank_fb)로 저소득 우선 선정
  직역연금 수급자 제외 — govp/privschp/milip/postp _pension_yn 이 있으면 제외
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'params/raw')

# ── [1차확인] R04 <2.1 성별 및 연령별 수급자 현황> 2022 ──────────────────────
POP65 = 9250116
N_RECIP = 6238798
N_MALE, N_FEMALE = 2484255, 3754543
AGE_BANDS = [(65, 65, 0.507, 740924, 375370), (66, 69, 0.587, 2437065, 1430172),
             (70, 74, 0.654, 2203904, 1441612), (75, 79, 0.719, 1614581, 1161589),
             (80, 84, 0.792, 1301856, 1030452), (85, 89, 0.828, 666582, 552005),
             (90, 94, 0.863, 229095, 197632), (95, 99, 0.894, 48384, 43255),
             (100, 200, 0.869, 7725, 6711)]

# ── [1차확인] R05 표5-1-9 가구형태별 수급자 (2022) ───────────────────────────
T_ALONE, T_CPL1, T_CPL2 = 3029979, 514425, 2694394       # 단독 / 부부1인 / 부부2인

# ── [1차확인] R04 <2.4 연금액별 수급자 현황> 2022 (원문 p34·p36) ────────────
FULL_SINGLE = 307500      # 2022 기준연금액 (단독·부부1인)
FULL_COUPLE = 246000      # 부부2인 감액 20%
MIN_PENSION = 30750       # 최저연금액 = 기준연금액의 10%
N_FULL_S, N_FULL_C = 3232240, 2342419        # 전액수급자 (단독·부부1인 / 부부2인)
#   감액수급자 구간: (하한, 상한, 인원)  — 첫 구간(24.6만 초과~30.75만 미만)은 단독·부부1인 전용
CUT_TOP = (246000, 307500, 103612)
CUT_REST = [(200000, 250000, 199861), (180000, 200000, 75632), (160000, 180000, 71699),
            (140000, 160000, 89027), (120000, 140000, 57860), (100000, 120000, 14808),
            (80000, 100000, 12815), (60000, 80000, 10856), (40000, 60000, 10547),
            (30000, 40000, 5870), (MIN_PENSION, MIN_PENSION, 11552)]
MEAN_PENSION_R04 = 271852      # R04 2022 평균연금액(원/월)

# ── [1차확인] R07 기초연금 (2022) ────────────────────────────────────────────
R07_BP_CNT, R07_BP_AMT = 72957947, 20095039e6      # 지급건수(건), 지급액(원)

# ── [논리적추론] 연중 진입·탈락 (R04 + R07 항등식) ──────────────────────────
#   P = 12S + 6E + 6X,  D = S + E,  N = D + X   (S=연중 계속, E=신규, X=탈락)
#   E = 375,370 (2022년 중 65세 도달 = R04 '65세' 수급자)  →  X = E − (12D − P)/6
BP_E = 375370
BP_X = BP_E - (12 * N_RECIP - R07_BP_CNT) / 6.0        # ≈ 57,432
BP_N = N_RECIP + BP_X                                   # 연간 1회 이상 수급 ≈ 6,296,230


def _sex_pop65():
    """주민등록 2022.11 성별 65세 이상 인구 (B01 과 동일 원천)."""
    try:
        p = pd.read_csv(os.path.join(RAW, 'POPUL_MOIS01_2022_11_sigungu_age1_sex.csv'))
        p = p[(p.level == 'sigungu') & (p.sex.isin(['male', 'female'])) & (p.age.astype(int) >= 65)]
        s = p.groupby('sex')['pop'].sum()
        return float(s.get('male', np.nan)), float(s.get('female', np.nan))
    except Exception:
        return np.nan, np.nan


def _band_idx(age):
    a = np.asarray(age)
    out = np.full(len(a), -1)
    for i, (lo, hi, *_r) in enumerate(AGE_BANDS):
        out[(a >= lo) & (a <= hi)] = i
    return out


def _solve_threshold(key, weight, target_w, eligible=None):
    nn = len(key)
    m = np.ones(nn, bool) if eligible is None else np.asarray(eligible, bool)
    idx = np.flatnonzero(m)
    sel = np.zeros(nn, bool)
    if len(idx) == 0 or target_w <= 0:
        return sel
    o = idx[np.argsort(np.asarray(key)[idx], kind='stable')]
    cw = np.cumsum(np.asarray(weight, float)[o])
    k = int(np.searchsorted(cw, target_w)) + 1
    k = min(max(k, 1), len(o))
    if k > 1 and abs(cw[k - 2] - target_w) < abs(cw[k - 1] - target_w):
        k -= 1
    sel[o[:k]] = True
    return sel


def generate(df, params, ctx):
    g = core.rng('B26')
    n = len(df)
    out = pd.DataFrame(index=df.index)
    age = df['age'].values.astype(int)
    sex = df['gender'].values.astype(int)
    iw = (df['indwgt'].values if 'indwgt' in df.columns else np.ones(n)).astype(float)

    # ── 저소득 순위 (소득인정액 하위 70% 요건) ──────────────────────────────
    for c in ('_recog_rank', '_recog_rank_fb', '_nbls_rank'):
        if c in df.columns:
            rank = np.asarray(df[c], float)
            rank_src = c
            break
    else:                                    # B05·B24 모두 없을 때의 최종 폴백
        rank = np.asarray(df['_u_income'], float)
        rank_src = '_u_income'
    rank = np.where(np.isfinite(rank), rank, 0.5)

    # 직역연금 수급자 제외 (B13·B14 산출; 미구현 시 제외 없음 — note 참조)
    if '_occp_pen_grp' in df.columns:              # B13(A3, order4) 계약 컬럼
        occ = np.asarray(df['_occp_pen_grp'].fillna(0).values) > 0
    else:
        occ_cols = [c for c in ('govp_pension_yn', 'privschp_pension_yn', 'milip_pension_yn',
                                'postp_pension_yn', 'govp_yn1', 'privschp_yn1', 'milp_yn1',
                                'postp_yn1') if c in df.columns]
        occ = (df[occ_cols].fillna(0).max(axis=1).values == 1) if occ_cols else np.zeros(n, bool)

    bi = _band_idx(age)
    elig = (bi >= 0) & (~occ)

    # ── 1) bp_yn1 — 연령대별 수급률(R04) × 성별 로그오즈 보정 ───────────────
    #   각 연령대 안에서 저소득(rank 낮은 순)부터 선정 → 소득 조건부 구조 확보
    pm65, pf65 = _sex_pop65()
    if np.isfinite(pm65) and np.isfinite(pf65) and pm65 > 0 and pf65 > 0:
        rm, rf = N_MALE / pm65, N_FEMALE / pf65            # 성별 수급률
        delta = np.log(rm / (1 - rm)) - np.log(rf / (1 - rf))   # 남−여 로그오즈차
    else:
        delta = 0.0
    key = rank + 0.35 * g.random(n)          # 저소득 우선 + 잡음 [가정: 잡음폭 0.35]

    # 부부 판정 (§7 R02: 배우자 65세 이상)
    sp_age = df['_spouse_age'].values
    has_sp65 = np.isfinite(sp_age) & (sp_age >= 65)
    hid = df['hid'].values
    role = np.asarray(df['_role'].values)
    cpl_unit = np.isin(role, ['head', 'spouse']) & has_sp65 & (bi >= 0)

    def band_select(k):
        sv = np.zeros(n, bool)
        for i, (lo, hi, rate, _p, _r) in enumerate(AGE_BANDS):
            m = elig & (bi == i)
            if not m.any():
                continue
            wm = float((iw * (m & (sex == 1))).sum()); wf = float((iw * (m & (sex == 2))).sum())
            base = rate * (wm + wf)
            if wm > 0 and wf > 0:
                o = np.exp(delta)
                l, h = 0.0, 1.0
                for _ in range(40):
                    pf = (l + h) / 2
                    od = o * pf / max(1 - pf, 1e-12)
                    pm = od / (1 + od)
                    if wm * pm + wf * pf < base: l = pf
                    else: h = pf
                pf = (l + h) / 2
                od = o * pf / max(1 - pf, 1e-12); pm = od / (1 + od)
            else:
                pm = pf = rate
            sv |= _solve_threshold(k, iw, wm * pm, eligible=(m & (sex == 1)))
            sv |= _solve_threshold(k, iw, wf * pf, eligible=(m & (sex == 2)))
        return sv

    def both_mask(sv):
        t = pd.DataFrame({'hid': hid, 'ok': (cpl_unit & sv).astype(int)})
        c = t.groupby('hid')['ok'].sum()
        return cpl_unit & (c.reindex(hid).values == 2)

    ud = g.random(n)

    def build(delta_c):
        """부부가구 가점 delta_c → (수급 마스크, 부부2인 마스크).
        R05 표5-1-9 의 부부1인:부부2인 = 514,425:2,694,394 를 쌍 단위 불일치로 재현하고,
        탈락분은 같은 연령대 비부부 후보로 보충해 R04 연령별 수급률을 유지한다."""
        sv = band_select(key - delta_c * cpl_unit)
        bt = both_mask(sv)
        one_w = float((iw * (cpl_unit & sv & ~bt)).sum())
        both_w = float((iw * bt).sum())
        # 목표: type2 / (type2+type3) = 514,425/(514,425+2,694,394) = 0.1603
        r1 = T_CPL1 / (T_CPL1 + T_CPL2)
        X = (r1 * (one_w + both_w) - one_w) / (1.0 + r1)
        if X > 0:
            kk = pd.DataFrame({'hid': hid, 'k': np.where(bt, key, -np.inf)})
            worse = kk.groupby('hid')['k'].transform('max').values
            cand = bt & (kk['k'].values == worse)
            drop = _solve_threshold(ud, iw, X, eligible=cand)
            sv = sv & ~drop
            for i, (lo, hi, rate, _p, _r) in enumerate(AGE_BANDS):
                m = (bi == i)
                d0 = rate * float((iw * m).sum()) - float((iw * (m & sv)).sum())
                if d0 > 0:
                    sv |= _solve_threshold(key + 5.0 * cpl_unit, iw, d0,
                                           eligible=(m & elig & ~sv & ~drop))
            bt = both_mask(sv)
        return sv, bt

    # 부부가구 비중(= (부부1인+부부2인)/전체 = 51.43%, R05 표5-1-9) 을 맞추는 delta_c
    tgt_cpl = (T_CPL1 + T_CPL2) / (T_ALONE + T_CPL1 + T_CPL2)
    lo_d, hi_d = 0.0, 3.0
    for _ in range(16):
        dc = (lo_d + hi_d) / 2
        sv, bt = build(dc)
        share = float((iw * (cpl_unit & sv)).sum()) / max(float((iw * sv).sum()), 1.0)
        if share < tgt_cpl: lo_d = dc
        else: hi_d = dc
    sel, both = build((lo_d + hi_d) / 2)

    # ── 2) bp_type ─────────────────────────────────────────────────────────
    bp_type = np.full(n, np.nan)
    bp_type[sel] = 1.0
    bp_type[sel & cpl_unit] = 2.0
    bp_type[sel & both] = 3.0

    # ── 3) bp_dur / bp_yn2 (R04 65세 신규 + R07 지급건수 항등식) ────────────
    dur = np.full(n, np.nan)
    newly = sel & (age == 65)                       # 2022년 중 65세 도달 → 연중 진입
    cont = sel & (age > 65)
    dur[newly] = g.integers(1, 13, int(newly.sum())).astype(float)
    p12 = 1.0 - BP_X / max(BP_N - BP_E, 1.0)        # 계속수급자 중 연중 탈락 제외 비율
    dur[cont] = core.dur_months(g, int(cont.sum()), p12, 1, 11).astype(float)
    yn2 = np.where(sel, 1.0, np.nan)
    short = sel & (dur < 12)
    ex_share = BP_X / (BP_E + BP_X)                 # 연중 변동자 중 탈락 비중 ≈ 13.3%
    yn2[short & (g.random(n) < ex_share)] = 0.0

    # ── 4) bp_amt = 월 연금액 × 수급개월수 ─────────────────────────────────
    #   월 연금액: R04 2.4 전액/감액 구간 분포를 유형별로 배분
    n_cut_s = (T_ALONE + T_CPL1) - N_FULL_S       # 단독·부부1인 감액수급자 312,164
    rest_tot = float(sum(c[2] for c in CUT_REST))
    share_s = max(n_cut_s - CUT_TOP[2], 0) / rest_tot     # 하위구간 중 단독·부부1인 몫 0.372
    u = g.random(n)
    r2 = g.random(n)
    is3 = (bp_type == 3)
    is12 = sel & ~is3
    monthly = np.full(n, np.nan)

    def draw(mask, p_full, full_amt, buckets, probs):
        v = np.full(n, np.nan)
        cum = np.concatenate([[p_full], p_full + np.cumsum(probs)])
        v[mask & (u < cum[0])] = full_amt
        for j, (a, b, _c) in enumerate(buckets):
            mm = mask & (u >= cum[j]) & (u < cum[j + 1])
            v[mm] = a + (b - a) * r2[mm]
        v[mask & (u >= cum[-1])] = full_amt          # 잔차는 전액
        return v

    # 단독·부부1인: 전액 307,500 / 24.6만~30.75만 구간 / 하위구간(공유분의 share_s)
    p_full_s = N_FULL_S / (T_ALONE + T_CPL1)
    bs = [CUT_TOP] + CUT_REST
    ps = np.array([CUT_TOP[2]] + [c[2] * share_s for c in CUT_REST], float) / (T_ALONE + T_CPL1)
    monthly = np.where(is12, draw(is12, p_full_s, FULL_SINGLE, bs, ps), monthly)
    # 부부2인: 전액 246,000 / 하위구간(공유분의 1−share_s)
    p_full_c = N_FULL_C / T_CPL2
    pc = np.array([c[2] * (1 - share_s) for c in CUT_REST], float) / T_CPL2
    monthly = np.where(is3, draw(is3, p_full_c, FULL_COUPLE, CUT_REST, pc), monthly)

    # 월 평균연금액을 R04 2022 평균(271,852원)에 맞추는 단일 계수
    cur = float(np.nansum(np.where(sel, monthly, 0.0) * iw) / max(float((iw * sel).sum()), 1.0))
    monthly = monthly * (MEAN_PENSION_R04 / max(cur, 1.0))
    amt = np.where(sel, np.round(monthly * dur), np.nan)

    out['bp_yn1'] = np.where(sel, 1.0, np.nan)
    out['bp_yn2'] = yn2
    out['bp_type'] = np.where(sel, bp_type, np.nan)
    out['bp_dur'] = dur
    out['bp_amt'] = amt
    return out
