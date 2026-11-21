# -*- coding: utf-8 -*-
"""B16 고용보험·산재보험·청년내일채움공제 (A3 / order 4) — 20변수

생성 변수
  empins_yn1 empins_yn2 empins_premium_amt
  empins_support_yn1 empins_support_yn2 empins_support_dur empins_support_amt
  occupins_pension_yn occupins_pension_amt occupins_lump_yn occupins_lump_amt
  youthemp_yn1 youthemp_yn2 youthemp_type youthemp_dur
  youthemp_cnt1 youthemp_cnt2 youthemp_cnt3 youthemp_amt1 youthemp_amt2
헬퍼
  _empins_hist  (당해연도 고용보험 이력 0/1) — column_contract 계약. B17 §7 R13 이 사용.

소스 (등급순)
  S0 R02 <표 7-1> 개인의 건강보험 가입유형별 사회보험 가입률 (2021.10.31 기준)
        → 고용보험 가입률 40.5%  [1차확인]  params/tab/S0_R02_T7-1_*.csv
  S0 R02 <표 7-2> 제도별 균등화 가처분소득 10분위 분포 → 고용보험 소득 기울기 [1차확인]
  S0 R02 <표 3-39>/<표 3-40> 산재보험급여 수급 비중·평균 수급액(가구시장소득 분위별) [1차확인]
  S1 R23 근로복지공단 2022년도 산재보험 사업연보 <표 2-3-2·3·5·6·8·11·12·14>, <4-1>, <4-18> [1차확인]
  S1 R14 고용보험통계연보 2022 / 2022.12 월보 시트 2-3(연령·성별 순수피보험자), 5-4(취득·상실) [1차확인]
  S1 data.go.kr 15119758·15120307 근로복지공단 두루누리(고용보험) 2022 + R24 <표 2-6-2> [1차확인]
  S1 R25 고용노동백서 p.80 청년내일채움공제 실적, <표 9-⑤-4>·<9-⑤-5> 정부지출액 [1차확인]
  S1 고용노동부 보도자료 2022.1.3 청년내일채움공제 2년형 적립구조 [1차확인]
  S4 R24 고용보험백서 <표 2-4-1> 고용보험료율 (근로자 0.8%→0.9%, 2022.7.1.) [1차확인]

선행 블록 폴백 (rules 미구현 시)
  _p_earned(B03) → 없으면 R14 <7-4> 기초임금일액 분포 × 365일 로 보수총액 대리 생성
  np_support_yn1(B13) → 없으면 저소득·저임금 지표만으로 두루누리 대상 배정
  govp_yn1 등 직역연금(B14) → 없으면 공무원 제외 조건을 적용하지 않음(가입률이 소폭 과대)
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'params/raw')
TAB = os.path.join(ROOT, 'params/tab')

# ── 고용보험 ─────────────────────────────────────────────────────────────────
EMPINS_YN2_RATE = 0.405        # S0 R02 <표 7-1> 합계 고용보험 가입률 (2021.10.31) [1차확인]
EMPINS_YN1_OVER_YN2 = 1.111    # 연간이력/시점 비 [가정 A3-16-1] (하한 1.039 · 상한 1.511, R14 5-4)
# S0 R02 <표 7-2> 고용보험 적용자의 균등화 가처분소득 10분위 분포(%) → /10 = 상대 가입지수
EMPINS_INC_IDX = np.array([6.3, 5.4, 6.8, 9.8, 11.3, 12.0, 12.3, 12.6, 12.3, 11.1]) / 10.0
# 근로자 부담 실업급여 보험료율: 0.8%(~2022.6.30) · 0.9%(2022.7.1~)  [1차확인 R24 표2-4-1]
EMPINS_RATE_H1, EMPINS_RATE_H2 = 0.008, 0.009
EMPINS_RATE_Y = (EMPINS_RATE_H1 + EMPINS_RATE_H2) / 2.0   # 연간 보수 균등 가정 → 0.85%

# ── 두루누리(고용보험) ───────────────────────────────────────────────────────
DN_N_YEAR = 1_065_526          # 2022 연간 누적 지원 근로자 [1차확인 data.go.kr 15120307/15119758]
DN_N_MONTHAVG = 381_329        # 2022 월평균 지원자(고용) [1차확인 R24 표2-6-2]
DN_SUPPORT_RATE = 0.80         # 근로자 지원율 (코드북 정의: 보수×요율×80%) [1차확인 코드북]

# ── 산재보험 (R23 2022) ──────────────────────────────────────────────────────
# 정기연금 = 장해연금 + 진폐보상연금 + 유족연금 + 진폐유족연금
OI_PENSION_N = 54_831 + 11_353 + 32_612 + 1_879                     # 100,675명 [1차확인]
OI_PENSION_AMT = (1_463_616 + 222_319 + 703_661 + 40_216) * 1e6     # 2,429,812백만원 [1차확인]
OI_ANY_N = 390_475                                                  # 전체 보험급여 순수급자 [1차확인 표4-1]
OI_LUMP_N = OI_ANY_N - OI_PENSION_N                                 # 289,800 [논리적추론: 연금·일시금 배타 가정]
# 수시·일시금 = 요양+휴업+상병보상연금+장해일시금+유족일시금+간병+직업재활
OI_LUMP_AMT = (1_316_460 + 1_693_399 + 137_078 + 858_890 + 141_165 + 50_618 + 20_300) * 1e6
OI_PENSION_MALE = 0.647   # 장해·진폐보상 66,184명 남 88% + 유족연금 34,491명 남 20% [가정 A3-16-3]
OI_LUMP_MALE = 0.765      # 요양+휴업 남 346,554 / 452,735 [1차확인 R23 4-18]
# S0 R02 <표 3-39> 가구시장소득 분위별 산재급여 수급 비중(전체 열) ÷ 전체 1.50 = 상대지수
OI_INC_IDX = np.array([1.47, 1.85, 1.78, 1.77, 1.89, 1.81, 1.64, 1.44, 1.13, 0.62]) / 1.50

# ── 청년내일채움공제 ─────────────────────────────────────────────────────────
YE_N = 373_000                 # 2022 중 계약상태 '정상' 이력자 [논리적추론] (상한 396,380)
YE_YN2_RATIO = 0.70            # 12.31 기준 정상 유지 비율 [가정 A3-16-4]
YE_MATURE_SHARE = 0.72         # 2022년 해지자 중 만기해지 비중 [논리적추론] 249,968:96,380
YE_YOUTH_MONTHLY = 125_000     # 2년형 청년 본인적립 300만원/24개월 [1차확인 보도자료 2022.1.3]
YE_FIRM_MONTHLY = 125_000      # 2년형 기업기여금 300만원/24개월 [1차확인]
YE_GOV_MONTHLY = 250_000       # 2년형 정부지원금 600만원/24개월 [1차확인]
YE_MATURITY = 12_000_000       # 2년형 만기공제금 [1차확인]
YE_INTEREST = 0.015            # 만기 이자율(누적) [가정 A3-16-5]
YE_TAXRATE = 0.154             # 이자소득세 15.4% [S4 소득세법 원천징수세율]
# 기업규모별 기업자부담률 [1차확인 R25 p.80 / 보도자료 2022.1.3]
YE_FIRM_BURDEN = [(0.00, 0.498), (0.20, 0.130), (0.50, 0.237), (1.00, 0.135)]
# 규모 비중은 R14 <2-1> 5~299인 순수피보험자 분포에서 산출 [논리적추론]

AGE_BANDS_EI = [(0, 17, '18세 미만'), (18, 19, '18~20세 미만'), (20, 24, '20~24세 이하'),
                (25, 29, '25~29세 이하'), (30, 34, '30~34세 이하'), (35, 39, '35~39세 이하'),
                (40, 44, '40~44세 이하'), (45, 49, '45~49세 이하'), (50, 54, '50~54세 이하'),
                (55, 59, '55~59세 이하'), (60, 200, '60세 이상')]
AGE_BANDS_OI = [(0, 19, '20세미만'), (20, 29, '20~29세'), (30, 39, '30~39세'), (40, 49, '40~49세'),
                (50, 59, '50~59세'), (60, 69, '60~69세'), (70, 79, '70~79세'), (80, 89, '80~89세'),
                (90, 99, '90~99세'), (100, 200, '100세이상')]

# R14 <7-4> 수급자격인정자 기초임금일액 14구간 (계) [1차확인] — 보수 대리분포·B17 일액에 사용
WAGE_EDGES = [0, 20080, 22720, 24800, 27840, 30160, 32000, 32880, 34560, 36640,
              40000, 60000, 70000, 80000, None]
WAGE_W = [52, 5, 2, 34, 36, 16, 10, 78, 14289, 43201, 85883, 113051, 391416, 550539]


# ── 유틸 ─────────────────────────────────────────────────────────────────────
def _band(age, bands):
    a = np.asarray(age)
    out = np.empty(len(a), dtype=object)
    for lo, hi, nm in bands:
        out[(a >= lo) & (a <= hi)] = nm
    return out


def _pick_w(g, score, wgt, target_W, pool=None):
    """score 비례 무복원추출(Gumbel top-k). 선택된 개인의 가중치 합이 target_W 에 가장 가깝게 k 결정."""
    s = np.asarray(score, float)
    s = np.where(np.isfinite(s) & (s > 0), s, 0.0)
    if pool is not None:
        s = np.where(np.asarray(pool, bool), s, 0.0)
    out = np.zeros(len(s), bool)
    m = s > 0
    if not m.any() or target_W <= 0:
        return out
    u = np.clip(g.random(len(s)), 1e-12, 1 - 1e-12)
    key = np.full(len(s), -np.inf)
    key[m] = np.log(s[m]) - np.log(-np.log(u[m]))
    order = np.argsort(-key)
    order = order[np.isfinite(key[order])]
    w = np.asarray(wgt, float)[order]
    cum = np.cumsum(w)
    if cum[-1] <= target_W:
        k = len(order)
    else:
        j = int(np.searchsorted(cum, target_W))
        j = min(j, len(cum) - 1)
        k = j + 1 if (j == 0 or abs(cum[j] - target_W) <= abs(cum[j - 1] - target_W)) else j
    out[order[:k]] = True
    return out


def _load_insured_band():
    """R14M 2-3 (2022.12.31 순수피보험자) 총계 행 → {(성별, 연령대): 인원}"""
    p = os.path.join(RAW, 'R14M_T2-3_피보험자202212_산업별연령별성별.csv')
    d = pd.read_csv(p)
    d = d[d['산업'].astype(str).str.replace(' ', '') == '총계']
    d = d[(d['성별'].isin(['남', '여'])) & (d['연령'] != '계')]
    return {(r['성별'], r['연령']): float(r['value']) for _, r in d.iterrows()}


def _load_pop_band(bands):
    """주민등록 2022.11 시군구×1세×성 → {(성별코드, 밴드): 인구}"""
    p = os.path.join(RAW, 'POPUL_MOIS01_2022_11_sigungu_age1_sex.csv')
    d = pd.read_csv(p)
    d = d[(d.level == 'sigungu') & (d.sex.isin(['male', 'female']))].copy()
    d['g'] = np.where(d.sex == 'male', 1, 2)
    d['band'] = _band(d.age.astype(int).values, bands)
    return d.groupby(['g', 'band'])['pop'].sum().to_dict()


def _load_oi_band():
    """R23 4-18 급여종류별 성별 연령별 수급자 (params/tab 전사본)"""
    p = os.path.join(TAB, 'S1_R23_T4-18_산재_급여종류별_성별연령별_수급자_2022.csv')
    d = pd.read_csv(p)
    d = d[(d['성별'] == '계') & (d['연령'] != '계')]
    return d.pivot_table(index='연령', columns='급여종류', values='수급자_명', aggfunc='sum')


def _fallback_wage(g, n, u_income, age):
    """B03 미구현 시 보수총액 대리: R14 7-4 기초임금일액 분포 × 365일 [논리적추론]."""
    d = core.hist_loguniform(g, WAGE_EDGES, WAGE_W, n, pareto_alpha=3.0)
    # 소득 잠재변수와 순위 결합 (블록 간 상관 유지, §4.1)
    o = np.argsort(np.argsort(u_income + 0.35 * (np.clip(age, 20, 55) - 20) / 35.0))
    return np.sort(d)[o] * 365.0


# ── 생성 ─────────────────────────────────────────────────────────────────────
def generate(df, params, ctx):
    g = core.rng('B16')
    n = len(df)
    age = df['age'].astype(int).values
    sex = df['gender'].astype(int).values
    wgt = df['indwgt'].values if 'indwgt' in df.columns else np.full(n, 1.0)
    Npop = float(wgt.sum())
    ui = df['_u_income'].values
    ue = df['_u_emp'].values
    uh = df['_u_health'].values
    uw = df['_u_welfare'].values
    out = pd.DataFrame(index=df.index)

    # 보수총액(원/년)
    if '_p_earned' in df.columns:
        pay = pd.to_numeric(df['_p_earned'], errors='coerce').fillna(0.0).values
        pay_src = '_p_earned(B03)'
    elif 'p_labinc' in df.columns:
        pay = pd.to_numeric(df['p_labinc'], errors='coerce').fillna(0.0).values
        pay_src = 'p_labinc(B03)'
    else:
        pay = _fallback_wage(g, n, ui, age)
        pay_src = 'fallback(R14 7-4 기초임금일액×365)'

    # 직역연금(공무원 등) 배제
    occ_cols = [c for c in ('govp_yn1', 'privschp_yn1', 'milp_yn1', 'postp_yn1') if c in df.columns]
    occ = (df[occ_cols].fillna(0).max(axis=1).values == 1) if occ_cols else np.zeros(n, bool)

    # ══════════════════════════════ 1) 고용보험 가입 ══════════════════════════
    ins = _load_insured_band()
    pop_ei = _load_pop_band(AGE_BANDS_EI)
    bnd = _band(age, AGE_BANDS_EI)
    cov = np.full(n, 0.02)
    for s_c, s_k in ((1, '남'), (2, '여')):
        for _, _, nm in AGE_BANDS_EI:
            P = pop_ei.get((s_c, nm), 0.0)
            if P > 0:
                cov[(sex == s_c) & (bnd == nm)] = min(ins.get((s_k, nm), 0.0) / P, 0.95)
    odds = np.clip(cov, 1e-4, 0.95)
    odds = odds / (1 - odds)
    odds = odds * EMPINS_INC_IDX[np.clip((ui * 10).astype(int), 0, 9)]
    odds = odds * np.exp(0.7 * (ue - 0.5))                       # 고용 안정성 잠재변수 (§4.1 상관)

    pool = (age >= 15) & (~occ)
    if '_p_earned' in df.columns or 'p_labinc' in df.columns:
        pool &= (pay > 0)                                         # 조건부 규칙: empins ⇒ 근로소득
    if 'labinc_sum_taxy' in df.columns and 'dainc_sum' in df.columns:   # [T2-f] 원천 DB 근로·일용소득 보유자만
        pool &= ((df['labinc_sum_taxy'].fillna(0).to_numpy() > 0) | (df['dainc_sum'].fillna(0).to_numpy() > 0))
    target_W1 = EMPINS_YN2_RATE * EMPINS_YN1_OVER_YN2 * Npop
    yn1 = _pick_w(g, odds, wgt, target_W1, pool)
    yn2 = _pick_w(g, odds * np.exp(0.5 * (ue - 0.5)), wgt, EMPINS_YN2_RATE * Npop, yn1)

    out['empins_yn1'] = np.asarray(np.where(yn1, 1, np.nan), float)
    out['empins_yn2'] = np.asarray(np.where(yn1, np.where(yn2, 1, 0), np.nan), float)
    out['_empins_hist'] = yn1.astype(np.int8)                     # column_contract 헬퍼 (B17 R13)

    # 가입 개월수(보험료 안분용) — yn2=1 은 연중 계속, yn2=0 은 부분가입 [논리적추론]
    mon = np.where(yn2, np.where(g.random(n) < 0.85, 12, g.integers(9, 12, n)), g.integers(1, 10, n))
    prem = np.where(yn1, np.rint(pay * EMPINS_RATE_Y * mon / 12.0), np.nan)
    out['empins_premium_amt'] = np.asarray(np.where(np.isfinite(prem), np.nan_to_num(prem), np.nan), float)

    # ══════════════════════════════ 2) 두루누리 고용보험료 지원 ═══════════════
    # 요건: 10인 미만 사업장·월보수 260만원 미만 → 저임금 지표로 대리. B13(np_support)과 동일 개인.
    low = 1.0 / (1.0 + np.exp((pay - 31_200_000) / 6_000_000.0))  # 월 260만원 근처 로지스틱
    sc = low * np.exp(1.2 * (0.5 - ui))
    if 'np_support_yn1' in df.columns:
        # 두루누리는 국민연금·고용보험을 같은 근로자에게 함께 지원 → B13 수급자를 사실상 우선 배정
        sc = sc * np.where(df['np_support_yn1'].fillna(0).values == 1, 150.0, 1.0)
    # 목표는 전국 인원. 선택 개인의 indwgt 합이 목표에 맞도록 _pick_w 가 k 를 정한다.
    sup1 = _pick_w(g, sc, wgt, float(DN_N_YEAR), yn1)
    sup2 = _pick_w(g, sc * np.exp(0.6 * (1 - ui)), wgt, float(DN_N_MONTHAVG), sup1)

    # 평균 4.29개월 = 12 × 381,329 / 1,065,526 인월/인 [논리적추론]
    d2 = np.clip(np.rint(g.uniform(5, 11.49, n)), 1, 12)
    d1 = np.clip(np.rint(g.uniform(1, 3.49, n)), 1, 12)
    dur = np.where(sup2, d2, d1)
    out['empins_support_yn1'] = np.asarray(np.where(sup1, 1, np.nan), float)
    out['empins_support_yn2'] = np.asarray(np.where(sup1, np.where(sup2, 1, 0), np.nan), float)
    out['empins_support_dur'] = np.asarray(np.where(sup1, dur, np.nan), float)
    samt = np.where(sup1, np.rint(pay * EMPINS_RATE_Y * DN_SUPPORT_RATE * dur / 12.0), np.nan)
    out['empins_support_amt'] = np.asarray(samt, float)

    # ══════════════════════════════ 3) 산재보험 급여 ══════════════════════════
    oi = _load_oi_band()
    pop_oi = _load_pop_band(AGE_BANDS_OI)
    bo = _band(age, AGE_BANDS_OI)
    pop_oi_b = {}
    for _, _, nm in AGE_BANDS_OI:
        pop_oi_b[nm] = pop_oi.get((1, nm), 0.0) + pop_oi.get((2, nm), 0.0)

    def _oi_score(cols, male_share):
        prof = oi[cols].sum(axis=1)
        r = np.zeros(n)
        for _, _, nm in AGE_BANDS_OI:
            P = pop_oi_b.get(nm, 0.0)
            if P > 0 and nm in prof.index:
                r[bo == nm] = float(prof.loc[nm]) / P
        r = r * OI_INC_IDX[np.clip((ui * 10).astype(int), 0, 9)]
        r = r * np.where(sex == 1, male_share / 0.5, (1 - male_share) / 0.5)
        r = r * np.exp(0.6 * (uh - 0.5))                          # 건강 위험 잠재변수 (§4.1 상관)
        return np.where(age >= 15, r, 0.0)

    pen = _pick_w(g, _oi_score(['장해급여', '유족급여'], OI_PENSION_MALE), wgt, float(OI_PENSION_N))
    lmp = _pick_w(g, _oi_score(['요양급여', '휴업급여'], OI_LUMP_MALE), wgt, float(OI_LUMP_N),
                  pool=~pen)                                       # 연금·일시금 배타 [논리적추론]

    out['occupins_pension_yn'] = np.asarray(np.where(pen, 1, np.nan), float)
    out['occupins_lump_yn'] = np.asarray(np.where(lmp, 1, np.nan), float)
    def _amt(mask, mean, sigma):
        """로그정규 추출 후 가중평균이 원문 1인당 평균과 일치하도록 스케일 보정."""
        v = core.lognormal_mean(g, np.full(n, mean), sigma, n)
        k = int(mask.sum())
        if k:
            cur = float((v[mask] * wgt[mask]).sum() / wgt[mask].sum())
            v = v * (mean / max(cur, 1.0))
        return np.asarray(np.where(mask, np.rint(v), np.nan), float)

    out['occupins_pension_amt'] = _amt(pen, OI_PENSION_AMT / OI_PENSION_N, 0.75)
    out['occupins_lump_amt'] = _amt(lmp, OI_LUMP_AMT / OI_LUMP_N, 1.10)

    # ══════════════════════════════ 4) 청년내일채움공제 ═══════════════════════
    ypool = yn1 & (age >= 15) & (age <= 39)
    ysc = np.where((age >= 19) & (age <= 34), 1.0, 0.12) * np.exp(0.8 * (0.5 - ui)) * np.exp(0.5 * (ue - 0.5))
    y1 = _pick_w(g, np.where(ypool, ysc, 0.0), wgt, float(YE_N), ypool)
    y2 = _pick_w(g, ysc * np.exp(0.4 * ue), wgt, float(YE_N * YE_YN2_RATIO), y1)

    ydur = np.where(y2, np.where(g.random(n) < 0.72, 12, g.integers(7, 12, n)),
                    g.integers(1, 12, n))
    ydur = np.clip(ydur, 1, 12)
    # 기업규모별 자부담률
    br = np.array([x[0] for x in YE_FIRM_BURDEN]); bw = np.array([x[1] for x in YE_FIRM_BURDEN])
    burden = core.choice_p(g, br, bw, n)

    out['youthemp_yn1'] = np.asarray(np.where(y1, 1, np.nan), float)
    out['youthemp_yn2'] = np.asarray(np.where(y1, np.where(y2, 1, 0), np.nan), float)
    out['youthemp_type'] = np.asarray(np.where(y1, 1, np.nan), float)   # 2022 재적계약 = 2년형
    out['youthemp_dur'] = np.asarray(np.where(y1, ydur, np.nan), float)
    out['youthemp_cnt1'] = np.asarray(np.where(y1, YE_YOUTH_MONTHLY * ydur, np.nan), float)
    out['youthemp_cnt2'] = np.asarray(np.where(y1, np.rint(YE_FIRM_MONTHLY * burden * ydur), np.nan), float)
    out['youthemp_cnt3'] = np.asarray(np.where(y1, np.rint((YE_GOV_MONTHLY + YE_FIRM_MONTHLY * (1 - burden)) * ydur), np.nan), float)

    # 지급액: 2022년 중 해지(만기·중도)로 지원금을 받은 자 = yn1=1 ∧ yn2=0
    exit_m = y1 & (~y2)
    mature = exit_m & (g.random(n) < YE_MATURE_SHARE)
    elapsed = np.clip(np.rint(g.uniform(3, 23, n)), 1, 23)       # 중도해지 시 경과 납입월
    gross = np.where(mature, YE_MATURITY * (1 + YE_INTEREST),
                     YE_YOUTH_MONTHLY * elapsed * (1 + YE_INTEREST))
    interest = np.where(mature, YE_MATURITY * YE_INTEREST, YE_YOUTH_MONTHLY * elapsed * YE_INTEREST)
    out['youthemp_amt1'] = np.asarray(np.where(exit_m, np.rint(gross), np.nan), float)
    out['youthemp_amt2'] = np.asarray(np.where(exit_m, np.rint(gross - interest * YE_TAXRATE), np.nan), float)

    out.attrs['pay_src'] = pay_src
    return out
