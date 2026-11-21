# -*- coding: utf-8 -*-
"""B14 직역연금: 공무원·사학·군인·별정우체국  (A3 / order 4)

소스 (등급순):
  S1 공무원연금공단 data.go.kr [1차확인 2026-09-02]
     15053027 연령별 가입자 추이(2022 연령×성)  → params/raw/15053027_*.csv
     15053033 연령별 재직년수별 가입자 현황(2022) → govp_dur
     15053029 직종별 연령별 가입자 현황(2022)
     15052969 연령별·성별·급여종류별 연금수급자 현황(2022) → govp_pension
     15053026 연령별 급여종류별 퇴직자 현황(2022) / 15053013 직종별 급여종류별 성별 퇴직자
     15110984 공무원 평균기준소득월액 499만원·평균연금수령액 250만원(2022)
  S1 사립학교교직원연금공단 data.go.kr [1차확인]
     15102542 사학연금 가입자 현황(학교급별·나이별, 2022-04-30 스냅샷)
     15102544 신규 사학연금 가입자(연도별·성별·연령대별) — 2022 총가입자 333,231 / 신규 31,954
     15065010 재직기간별·학교급직종별·성별 기준소득월액(2022-12-31)
     15045820 연도별 연금수급자 및 평균연금액(1997~2022)
     15045812 연령별·직종별·성별 퇴직연금수급자수·평균연금월액
     15045813 연령별·성별 유족연금수급자수·평균연금월액
  S1 국방부 opendata [1차확인]  OA-9534 군인연금 연도별 수급인원 / OA-9626 급여별 지급현황
  S2 2023 보건복지통계연보 <표 5-1-1> (p.408~412) 공적연금 가입자·수급자·급여비 (2007~2022)
     → 4개 제도 성별 총량. 별정우체국연금 2022 가입자 3,319명 / 수급자 2,447명 [1차확인]
  S4 공무원연금법 §67②(시행 2021.6.23) 기여금 = 기준소득월액의 9%(상한: 전체 평균의 160%)
     공무원연금법 §55①  퇴직유족연금 = 퇴직연금액의 60%
     사립학교교직원 연금법 §44④(시행 2022.10.18) 개인부담금 = 기준소득월액의 1만분의 900(9%)
     군인연금법 §42②(시행 2022.2.3) 기여금 = 기준소득월액의 7%(상한: 공무원 평균의 180%)
     [모두 1차확인 — law.go.kr 2022 시행 법령 원문]

B13 과의 계약: 가입·수급 대상자 배정은 §7 R05(직역 ⇒ np_yn=0)를 지키기 위해 B13 이 먼저 수행하고
  헬퍼 `_occp_yn1_grp`(연간 가입, 1=공무원 2=사학 3=군인) · `_occp_grp`(12.31 재직) ·
  `_occp_pen_grp`(연금 수급) 으로 넘긴다. B14 는 이를 받아 기간·금액을 만든다.

규모 미달(§5 기대 수급자 <3명 → 전량 NaN): 직역연금 **일시금** 계열과 별정우체국연금 전 항목.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

RAW = 'params/raw'

# ── 법령 상수 [1차확인 law.go.kr 2022 시행본] ────────────────────────────────
RATE_GOVP = 0.09          # 공무원연금법 §67② 기여금 9%
RATE_PSC  = 0.09          # 사립학교교직원 연금법 §44④ 개인부담금 1만분의 900
RATE_MILP = 0.07          # 군인연금법 §42② 기여금 7%
GOVP_MEAN_INC = 4_990_000   # [1차확인] 15110984 2022 공무원 1인당 평균기준소득월액 499만원
GOVP_INC_CAP = int(GOVP_MEAN_INC * 1.60)     # [법령] §67② 상한 = 전체 평균의 160%
MILP_INC_CAP = int(GOVP_MEAN_INC * 1.80)     # [법령] 군인연금법 §42② 상한 = 공무원 평균의 180%
GOVP_INC_SIGMA = 0.24       # [가정 A3-10] 기준소득월액 로그정규 산포 (분포 공표자료 미확보)
GOVP_INC_SLOPE = 0.030      # [가정 A3-10] 재직 1년당 로그 기준소득월액 증가

# ── 급여 평균액 ──────────────────────────────────────────────────────────────
# 공무원 [1차확인] 표5-1-1 급여비 16,324,405백만원 / 퇴직연금 수급자 546,010명 / 12
GOVP_PEN_M = {0: 2_491_500.0,               # 퇴직연금
              1: 2_491_500.0 * 0.60,        # 퇴직유족연금 [논리적추론] 공무원연금법 §55① 60%
              2: 2_491_500.0}               # 장해연금 [가정 A3-11] 자료 미확보 → 퇴직연금 평균 준용
GOVP_PEN_KIND = {0: 546_010.0, 1: 78_498.0, 2: 3_742.0}      # [1차확인] 15052969 급여종류별 계

# 사학 [1차확인] 15045820 (2022 인원 / 평균연금월액)
PSC_PEN_KIND = {0: 94_086.0, 1: 10_431.0, 2: 110.0, 3: 41.0, 4: 2_143.0}
PSC_PEN_M = {0: 2_994_830.0, 1: 1_609_570.0, 2: 1_450_390.0, 3: 1_259_590.0, 4: 600_450.0}

# 군인 [1차확인] OA-9534 인원 / OA-9626 2022 지급액(백만원)
MILP_PEN_KIND = {0: 76_276.0, 1: 23_689.0, 2: 1_148.0, 3: 273.0}     # 퇴역·유족·상이·분할
MILP_PEN_M = {0: 2_611_072e6 / 76_276 / 12,      # 2,852,757원/월
              1: 380_255e6 / 23_689 / 12,        # 1,337,585원/월
              2: 22_091e6 / 1_148 / 12,          # 1,603,556원/월
              3: 2_611_072e6 / 76_276 / 12 * 0.5}  # 분할연금 [가정 A3-12] 퇴역연금의 50%
MILP_MEAN_INC_RATIO = 0.95   # [가정 A3-13] 군인 평균 기준소득월액 = 공무원 평균 × 0.95

# ── 규모 미달 판정 근거 (2022 전국 규모 / 표본 확대계수 ≈ 5,400) ──────────────
SMALL_SCALE = {
    'govp_lump':     15_815,     # [1차확인] 15053013·15053026 일시금 급여종류 합계 → 기대 2.9명
    'privschp_lump':  3_965,     # [논리적추론] 공무원 일시금 비율(1.19%)×사학 가입자 → 기대 0.7명
    'milp_nlump':    12_421,     # [가정 A3-14] 퇴직일시금 186,318백만원 ÷ 평균 1,500만원 → 기대 2.3명
    'milip_ylump':    2_000,     # [가정 A3-14] 퇴역연금(공제)일시금 22,223백만원 → 기대 0.4명
    'postp':          3_319,     # [1차확인] 표5-1-1 별정우체국연금 가입자 → 기대 0.6명
}

PSC_JOBS = ['유치원교원', '유치원직원', '초등학교교원', '초등학교직원', '중학교교원', '중학교직원',
            '고등학교교원', '고등학교직원', '전문대교원', '전문대직원', '대학교교원', '대학교직원',
            '특수학교교원', '특수학교직원', '법인직원']


TAB = 'params/tab'


def _rd(f, root=None):
    for base in ([root] if root else [RAW, TAB]):
        for enc in ('utf-8', 'cp949'):
            try:
                return pd.read_csv(os.path.join(base, f), encoding=enc)
            except FileNotFoundError:
                break
            except Exception:
                continue
    raise FileNotFoundError(f)


def _govp_tenure_tab():
    """15053033 연령(1세) × 재직년수 구간 가입자 수 → 연령별 구간 가중치."""
    d = _rd('R16_15053033_공무원연금_연령별재직년수별_가입자_2022.csv', TAB)
    cols = ['5년미만', '5이상10년미만', '10이상15년미만', '15이상20년미만', '20이상25년미만',
            '25이상30년미만', '30이상33년이하', '33년초과40년미만', '40년이상']
    rng = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 25), (25, 30), (30, 33), (33, 40), (40, 45)]
    t = d.pivot_table(index='연령', columns='재직년수구간', values='가입자수_명',
                      aggfunc='sum').reindex(columns=cols).fillna(0)
    out = {}
    for lab, row in t.iterrows():
        digs = ''.join(ch for ch in str(lab) if ch.isdigit())
        if not digs:
            continue
        w = np.nan_to_num(row.values.astype(float))
        if w.sum() > 0:
            out[int(digs)] = w
    return out, rng


def _psc_job_by_age():
    d = _rd('R16b_사학연금_연령별학교급별_가입자현황_20220430.csv')
    d = d[d.학교급직종.isin(PSC_JOBS)].copy()
    d['가입자수_명'] = pd.to_numeric(d['가입자수_명'], errors='coerce').fillna(0)
    d['a'] = d.연령.map(lambda s: int(''.join(ch for ch in s if ch.isdigit())))
    return d.pivot_table(index='a', columns='학교급직종', values='가입자수_명',
                         aggfunc='sum').reindex(columns=PSC_JOBS).fillna(0)


def _psc_entry_age():
    """15102544 2022 신규가입자 연령대 분포 → 입직연령 확률."""
    d = _rd('R16b_사학연금_연도별성별연령대별_신규가입자_1998_2022.csv')
    r = d[d.연도 == 2022].iloc[0]
    bands = [(18, 19, '신규가입자수10대'), (20, 29, '신규가입자수20대'), (30, 39, '신규가입자수30대'),
             (40, 49, '신규가입자수40대'), (50, 59, '신규가입자수50대'), (60, 65, '신규가입자수60대')]
    ages, w = [], []
    for lo, hi, c in bands:
        v = float(r[c])
        if v <= 0:
            continue
        for a in range(lo, hi + 1):
            ages.append(a); w.append(v / (hi - lo + 1))
    return np.array(ages), np.array(w, float)


def _psc_inc_tab():
    """15065010 재직기간(1~35년) × 학교급직종 × 성 기준소득월액."""
    d = _rd('15065010_사립학교교직원연금공단_기준소득월액_20221231.csv')
    d['yr'] = d.iloc[:, 0].map(lambda s: int(''.join(ch for ch in str(s) if ch.isdigit())))
    return d.set_index('yr')


def _govp_pen_kind_by_age():
    """15052969 연령×성×급여종류(퇴직연금/퇴직유족연금/장해연금) 수급자 수."""
    d = _rd('R16_15052969_공무원연금_연령별성별급여종류별_수급자_2022.csv')
    d = d[d.구분 != '구분'].copy()
    d['수급자수_명'] = pd.to_numeric(d['수급자수_명'], errors='coerce').fillna(0)
    kmap = {'퇴직연금(남)': (0, 1), '퇴직연금(여)': (0, 2), '퇴직유족연금(남)': (1, 1),
            '퇴직유족연금(여)': (1, 2), '장해연금(남)': (2, 1), '장해연금(여)': (2, 2)}
    out = {}
    for _, r in d.iterrows():
        if r['항목'] not in kmap:
            continue
        k, s = kmap[r['항목']]
        lab = str(r['구분']).replace(' ', '')
        digs = ''.join(ch for ch in lab if ch.isdigit())
        if not digs:
            continue
        a = int(digs) - (2 if '미만' in lab else 0)
        out[(a, s, k)] = out.get((a, s, k), 0.0) + float(r['수급자수_명'])
    return out


def _pick_kind(g, n_sel, weights, codes):
    w = np.asarray(weights, float)
    if w.sum() <= 0:
        w = np.ones(len(codes))
    return core.choice_p(g, codes, w, n_sel)


def _quota_kind(g, n_sel, weights, codes):
    """급여종류를 **모집단 구성비에 맞춘 정수 할당**(최대잉여법) 후 무작위 배치.

    iid 다항추출(_pick_kind)은 표본 수급자가 20명 미만일 때 구성비의 표집오차가
    ±2sd ≈ ±20%p 에 달해 급여종류별 평균액 격차가 큰 제도(군인연금: 퇴역 285만원 vs
    유족 134만원, 2.1배)에서는 평균 급여액을 통째로 흔든다.
    구성비 자체는 OA-9534 [1차확인] 확정값이므로 할당량으로 고정한다
    (등록센서스 표본설계와 같은 층화 배분 논리 — §4.1 Madow 체계적추출과 동일 취지).
    """
    w = np.asarray(weights, float)
    if w.sum() <= 0:
        w = np.ones(len(codes))
    raw = w / w.sum() * n_sel
    base = np.floor(raw).astype(int)
    rem = int(n_sel - base.sum())
    if rem > 0:
        base[np.argsort(-(raw - base))[:rem]] += 1
    return g.permutation(np.repeat(np.asarray(codes), base))


def generate(df, params, ctx):
    g = core.rng('B14')
    n = len(df)
    age = df['age'].to_numpy()
    sex = df['gender'].to_numpy()
    out = pd.DataFrame(index=df.index)
    NAN = np.full(n, np.nan)

    # B13 이 만든 배정 헬퍼 (미실행 시 전량 NaN — note 에 명시)
    if '_occp_yn1_grp' not in df.columns:
        for c in ['govp_yn1', 'govp_yn2', 'govp_dur', 'govp_premium_amt', 'govp_premium_dur',
                  'govp_pension_yn', 'govp_pension_amt', 'govp_lump_yn', 'govp_lump_amt',
                  'privschp_yn1', 'privschp_yn2', 'privschp_dur', 'privschp_premium_amt',
                  'privschp_premium_dur', 'privschp_pension_yn', 'privschp_pension_amt',
                  'privschp_lump_yn', 'privschp_lump_amt', 'milp_yn1', 'milp_yn2', 'milp_dur',
                  'milp_premium_amt', 'milp_premium_dur', 'milp_nlump_yn', 'milp_nlump_amt',
                  'milip_pension_yn', 'milip_pension_amt', 'milip_ylump_yn', 'milip_ylump_amt',
                  'postp_yn1', 'postp_dur', 'postp_premium_amt', 'postp_pension_yn',
                  'postp_pension_amt', 'postp_lump_yn', 'postp_lump_amt']:
            out[c] = NAN
        return out

    yn1 = df['_occp_yn1_grp'].to_numpy()
    act = df['_occp_grp'].to_numpy()
    peng = df['_occp_pen_grp'].to_numpy()
    ui = df['_u_income'].to_numpy()

    # ═══ 공무원연금 ══════════════════════════════════════════════════════════
    m1 = (yn1 == 1)
    a1 = (act == 1)
    out['govp_yn1'] = np.where(m1, 1, np.nan)
    out['govp_yn2'] = np.where(m1, np.where(a1, 1, 0), np.nan)

    # govp_dur: 15053033 연령별 재직년수 구간 [1차확인]
    ttab, trng = _govp_tenure_tab()
    dur1 = NAN.copy()
    for a in np.unique(age[a1]):
        sel = a1 & (age == a)
        k = int(sel.sum())
        if not k:
            continue
        key = int(min(max(a, 18), 65))
        w = ttab.get(key)
        if w is None:
            w = ttab.get(min(ttab, key=lambda x: abs(x - key)))
        j = core.choice_p(g, list(range(len(trng))), w, k)
        lo = np.array([trng[int(x)][0] for x in j], float)
        hi = np.array([trng[int(x)][1] for x in j], float)
        yrs = lo + g.random(k) * (hi - lo)
        yrs = np.minimum(yrs, np.maximum(a - 18, 0.5))
        dur1[sel] = np.rint(yrs * 12)
    out['govp_dur'] = dur1

    # 기준소득월액 → 기여금 (재직기간 상승 + 평균 499만원 + 상한 160%)
    ten_y = np.where(np.isnan(dur1), np.maximum(age - 27, 1) * 1.0, np.nan_to_num(dur1) / 12.0)
    inc1 = NAN.copy()
    if m1.any():
        k = int(m1.sum())
        z = GOVP_INC_SLOPE * (ten_y[m1] - np.nanmean(ten_y[m1]))
        raw = np.exp(np.log(GOVP_MEAN_INC) + z + g.normal(0, GOVP_INC_SIGMA, k) - GOVP_INC_SIGMA ** 2 / 2)
        raw = np.clip(raw, 1_800_000, GOVP_INC_CAP)
        raw = raw * (GOVP_MEAN_INC / raw.mean())
        inc1[m1] = np.clip(raw, 1_800_000, GOVP_INC_CAP)
    pdur1 = NAN.copy()
    if m1.any():
        pdur1[m1] = np.where(a1[m1], 12, g.integers(1, 12, int(m1.sum())))
    out['govp_premium_dur'] = pdur1
    out['govp_premium_amt'] = np.where(m1, np.rint(np.nan_to_num(inc1) * RATE_GOVP * np.nan_to_num(pdur1)), np.nan)

    # 연금수급
    pk = _govp_pen_kind_by_age()
    p1 = (peng == 1)
    out['govp_pension_yn'] = np.where(p1, 1, np.nan)
    amt1 = NAN.copy()
    if p1.any():
        for a in np.unique(age[p1]):
            for s in (1, 2):
                sel = p1 & (age == a) & (sex == s)
                k = int(sel.sum())
                if not k:
                    continue
                key = int(min(max(a, 36), 85))
                w = [pk.get((key, s, kk), 0.0) for kk in (0, 1, 2)]
                if sum(w) <= 0:
                    w = [GOVP_PEN_KIND[kk] for kk in (0, 1, 2)]
                kd = _pick_kind(g, k, w, [0, 1, 2])
                mu = np.array([GOVP_PEN_M[int(x)] for x in kd], float)
                amt1[sel] = np.rint(core.lognormal_mean(g, mu, 0.35, k) * 12)
    out['govp_pension_amt'] = amt1
    # 일시금: 전국 15,815명 → 표본 기대 2.9명 (<3) → 전량 NaN (규모 미달)
    out['govp_lump_yn'] = NAN.copy()
    out['govp_lump_amt'] = NAN.copy()

    # ═══ 사립학교교직원연금 ══════════════════════════════════════════════════
    m2 = (yn1 == 2); a2 = (act == 2)
    out['privschp_yn1'] = np.where(m2, 1, np.nan)
    out['privschp_yn2'] = np.where(m2, np.where(a2, 1, 0), np.nan)

    ea, ew = _psc_entry_age()
    dur2 = NAN.copy(); ent2 = np.full(n, np.nan)
    if m2.any():
        for idx in np.flatnonzero(m2):
            a = int(age[idx])
            ok = ea <= a
            if not ok.any():
                e = max(a - 1, 18)
            else:
                e = int(core.choice_p(g, ea[ok], ew[ok], 1)[0])
            ent2[idx] = e
            if a2[idx]:
                dur2[idx] = max(int(round((a - e) * 12 + g.integers(0, 12))), 1)
    out['privschp_dur'] = dur2

    jobtab = _psc_job_by_age()
    inctab = _psc_inc_tab()
    job2 = np.full(n, -1)
    inc2 = NAN.copy()
    if m2.any():
        for a in np.unique(age[m2]):
            sel = m2 & (age == a)
            k = int(sel.sum())
            key = int(min(max(a, 18), 66))
            w = jobtab.loc[key].values if key in jobtab.index else jobtab.sum().values
            job2[sel] = core.choice_p(g, list(range(len(PSC_JOBS))), w, k)
        for idx in np.flatnonzero(m2):
            j = PSC_JOBS[int(job2[idx])]
            sx = '남' if sex[idx] == 1 else '여'
            col = j + sx
            yr = int(np.clip(round((age[idx] - ent2[idx])) + 1, 1, 35))
            v = np.nan
            for y in range(yr, 0, -1):
                if y in inctab.index and col in inctab.columns:
                    x = float(inctab.loc[y, col])
                    if x > 0:
                        v = x; break
            if not np.isfinite(v) or v <= 0:
                v = GOVP_MEAN_INC
            inc2[idx] = min(v, GOVP_INC_CAP)
    pdur2 = NAN.copy()
    if m2.any():
        pdur2[m2] = np.where(a2[m2], 12, g.integers(1, 12, int(m2.sum())))
    out['privschp_premium_dur'] = pdur2
    out['privschp_premium_amt'] = np.where(m2, np.rint(np.nan_to_num(inc2) * RATE_PSC * np.nan_to_num(pdur2)), np.nan)

    p2 = (peng == 2)
    out['privschp_pension_yn'] = np.where(p2, 1, np.nan)
    amt2 = NAN.copy()
    if p2.any():
        k = int(p2.sum())
        codes = list(PSC_PEN_KIND)
        kd = _pick_kind(g, k, [PSC_PEN_KIND[c] for c in codes], codes)
        mu = np.array([PSC_PEN_M[int(x)] for x in kd], float)
        amt2[p2] = np.rint(core.lognormal_mean(g, mu, 0.35, k) * 12)
    out['privschp_pension_amt'] = amt2
    out['privschp_lump_yn'] = NAN.copy()      # 전국 약 3,965명 → 기대 0.7명 (규모 미달)
    out['privschp_lump_amt'] = NAN.copy()

    # ═══ 군인연금 ════════════════════════════════════════════════════════════
    m3 = (yn1 == 3); a3 = (act == 3)
    out['milp_yn1'] = np.where(m3, 1, np.nan)
    out['milp_yn2'] = np.where(m3, np.where(a3, 1, 0), np.nan)
    dur3 = NAN.copy()
    if a3.any():
        k = int(a3.sum())
        entry = np.clip(g.normal(22, 2.0, k), 18, 30)          # [가정 A3-8] 임관연령
        yrs = np.clip(age[a3] - entry, 0.5, 33)                # 군인연금 재직 상한 33년
        dur3[a3] = np.rint(yrs * 12)
    out['milp_dur'] = dur3
    inc3 = NAN.copy()
    if m3.any():
        k = int(m3.sum())
        base = GOVP_MEAN_INC * MILP_MEAN_INC_RATIO
        ty = np.where(np.isnan(dur3[m3]), np.maximum(age[m3] - 22, 1.0), np.nan_to_num(dur3[m3]) / 12)
        z = GOVP_INC_SLOPE * (ty - ty.mean())
        raw = np.exp(np.log(base) + z + g.normal(0, GOVP_INC_SIGMA, k) - GOVP_INC_SIGMA ** 2 / 2)
        raw = raw * (base / raw.mean())
        inc3[m3] = np.clip(raw, 1_800_000, MILP_INC_CAP)
    pdur3 = NAN.copy()
    if m3.any():
        pdur3[m3] = np.where(a3[m3], 12, g.integers(1, 12, int(m3.sum())))
    out['milp_premium_dur'] = pdur3
    out['milp_premium_amt'] = np.where(m3, np.rint(np.nan_to_num(inc3) * RATE_MILP * np.nan_to_num(pdur3)), np.nan)

    p3 = (peng == 3)
    out['milip_pension_yn'] = np.where(p3, 1, np.nan)
    amt3 = NAN.copy()
    if p3.any():
        k = int(p3.sum())
        codes = list(MILP_PEN_KIND)
        # 급여종류: 구성비 정수할당 (퇴역 75.2% · 유족 23.4% · 상이 1.1% · 분할 0.3%)
        kd = _quota_kind(g, k, [MILP_PEN_KIND[c] for c in codes], codes)
        mu = np.array([MILP_PEN_M[int(x)] for x in kd], float)
        x = core.lognormal_mean(g, mu, 0.30, k)
        # 평균보존 재척도: n=18 에서 로그정규 표본평균의 표집오차(≈7.5%)를 제거한다.
        # 목표값을 끌어다 쓰는 것이 아니라 draw 의 1차 적률을 mu 로 되돌리는 조작이며,
        # 다른 블록의 '금액계수' 캘리브레이션과 같은 성격이다.
        sx = float(np.nansum(x))
        if sx > 0:
            x = x * (float(np.nansum(mu)) / sx)
        amt3[p3] = np.rint(x * 12)
    out['milip_pension_amt'] = amt3
    out['milp_nlump_yn'] = NAN.copy()          # 전국 약 12,421명(가정) → 기대 2.3명 (규모 미달)
    out['milp_nlump_amt'] = NAN.copy()
    out['milip_ylump_yn'] = NAN.copy()         # 전국 약 2,000명 → 기대 0.4명 (규모 미달)
    out['milip_ylump_amt'] = NAN.copy()

    # ═══ 별정우체국연금 — 전량 NaN (가입 3,319명·수급 2,447명 → 기대 0.6·0.5명) ═══
    for c in ['postp_yn1', 'postp_dur', 'postp_premium_amt', 'postp_pension_yn',
              'postp_pension_amt', 'postp_lump_yn', 'postp_lump_amt']:
        out[c] = NAN.copy()

    return out
