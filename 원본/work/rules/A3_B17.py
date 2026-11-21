# -*- coding: utf-8 -*-
"""B17 실업급여 6종 (A3 / order 5) — 20변수

생성 변수
  unempbn_jobseekbn_yn/_type/_dur/_amt          구직급여      (생성)
  unempbn_sicknessbn_yn/_type/_dur/_amt         상병급여      (규모 미달 → 전량 NaN)
  unempbn_indivbn_yn/_type/_dur/_amt            개별연장급여  (규모 미달 → 전량 NaN)
  unempbn_early_yn/_type/_amt                   조기재취업수당(생성)
  unempbn_bnextended_yn/_type/_reason           수급기간연기  (생성, [가정] 규모)
  unempbn_etc_yn/_amt                           기타(훈련연장·광역구직활동비·이주비) (규모 미달 → NaN)

소스 (등급순)
  S1 R14 고용보험통계연보 2022 시트 7-10 산업별 성별 실업급여 지급현황 (산업=전 체) [1차확인]
       계 종합인원 1,761,467 / 순인원 1,730,533 / 건수 7,953,273 / 금액 11,390,905,017,620원
       구직급여 종합인원 1,660,012 / 금액 10,910,097,027,810원
       조기재취직촉진수당 종합인원 97,461 / 금액 467,849,515,450원
  S1 R14 시트 7-4 수급자격인정자 기초임금일액 14구간 (계 1,198,612명) [1차확인]
  S1 R14 시트 4-11 연령별 근속년수별 상실사유별 상실자 [1차확인] → 피보험기간 대리분포
  S1 R27 EIS 실업급여 지급현황(년) 2022 — 성×연령10세, 성×근로자유형 [1차확인]
  S1 R24 고용보험백서 표3-3-2~3-3-5 급여종류별 수급자·지급액 [1차확인]
       (상병 3,523명 · 개별연장 719명 · 훈련연장 19명 · 광역구직활동비 2명 · 이주비 118명)
  S4 R24 고용보험백서 표3-3-1 소정급여일수 기준표(120~270일) / p.221·223 구직급여일액
       상한 66,000원 · 하한 30,060~60,120원 · 산정률 60% [1차확인]

조건부 규칙 (§7 R13):  unempbn_* ⇒ _empins_hist=1 ∧ age ≥ 15
  조기재취업수당 ⊂ 구직급여 수급자, 수급기간연기 ⊂ 구직급여 수급자
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'params/raw')
TAB = os.path.join(ROOT, 'params/tab')

# ── 전국 총량 [1차확인] ──────────────────────────────────────────────────────
JS_N = 1_660_012                     # 구직급여 수급자(종합인원) R14 7-10
JS_AMT = 10_910_097_027_810.0        # 구직급여 지급액(원)
EARLY_N = 97_461                     # 조기재취직 촉진수당 종합인원
EARLY_AMT = 467_849_515_450.0
SICK_N = 3_567                       # 상병급여 종합인원 (백서 표3-3-3 3,523명)
INDIV_N = 719                        # 개별연장급여 (백서 표3-3-4)
ETC_N = 19 + 2 + 118                 # 훈련연장 + 광역구직활동비 + 이주비 (백서 표3-3-4·3-3-5)
BNEXT_RATE = 0.020                   # 수급기간연기 신고처리자 / 구직급여 수급자 [가정 A3-17-1]

MIN_EXPECTED = 3.0                   # §7 규모 미달 기준 (기대 수급자 3명 미만 → 전량 NaN)

# ── 구직급여일액 (R24 백서 p.221·223) [1차확인] ──────────────────────────────
DAILY_RATE = 0.60
DAILY_CAP = 66_000
DAILY_FLOOR_8H = 60_120
DAILY_FLOOR_MIN = 30_060
SHORT_TIME_P = 0.10                  # 단시간(소정근로시간<8h) 비중 [가정 A3-17-2]

# ── 소정급여일수 기준표 (R24 표3-3-1) [1차확인] ─────────────────────────────
SGD = {False: [120, 150, 180, 210, 240],     # 50세 미만
       True:  [120, 180, 210, 240, 270]}     # 50세 이상 및 장애인
# 피보험기간 대리분포 = 수급자격 인정 가능 이직사유(계약만료·공사종료, 경영상 필요, 폐업·도산,
# 정년, 근로조건변동 등 자진퇴사) 상실자의 근속기간 분포 (R14 4-11) [논리적추론]
SGD_W = np.array([1_536_236, 703_116, 192_563, 144_600, 111_164], float)
SGD_W = SGD_W / SGD_W.sum()

# ── 기초임금일액 14구간 (R14 7-4, 계) [1차확인] ─────────────────────────────
WAGE_EDGES = [0, 20080, 22720, 24800, 27840, 30160, 32000, 32880, 34560, 36640,
              40000, 60000, 70000, 80000, None]
WAGE_W = [52, 5, 2, 34, 36, 16, 10, 78, 14289, 43201, 85883, 113051, 391416, 550539]

# ── 수급자유형 (R27 EIS 근로자유형별 지급자수) [1차확인 + 상용/일용 분할 가정] ──
TYPE_WAGE = (1_724_845, 2_575, 2_275 + 817)      # 임금근로자 / 자영업자 / 예술인·노무제공자
DAILY_WORKER_SHARE = 0.10                        # 임금근로자 중 일용 비중 [가정 A3-17-3]

AGE_BANDS = [(0, 19, '19세 이하'), (20, 29, '20~29세'), (30, 39, '30~39세'), (40, 49, '40~49세'),
             (50, 59, '50~59세'), (60, 69, '60~69세'), (70, 200, '70세 이상')]


def _band(age):
    a = np.asarray(age)
    out = np.empty(len(a), dtype=object)
    for lo, hi, nm in AGE_BANDS:
        out[(a >= lo) & (a <= hi)] = nm
    return out


def _pick_w(g, score, wgt, target_W, pool=None):
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
        j = int(np.searchsorted(cum, target_W)); j = min(j, len(cum) - 1)
        k = j + 1 if (j == 0 or abs(cum[j] - target_W) <= abs(cum[j - 1] - target_W)) else j
    out[order[:k]] = True
    return out


def _load_js_profile():
    """R27 EIS 실업급여 지급현황(년) 2022 — 성×연령10세별 지급자수 [1차확인]"""
    p = os.path.join(RAW, 'R27_EIS_실업급여지급현황2022_연령10세별성별.csv')
    d = pd.read_csv(p)
    d = d[(d['측정값'] == '실업급여지급자수(년)') & (~d['연령_10세'].isin(['총계', '분류불능']))]
    return {(r['성별'], r['연령_10세']): float(r['value']) for _, r in d.iterrows()}


def _load_pop_band():
    p = os.path.join(RAW, 'POPUL_MOIS01_2022_11_sigungu_age1_sex.csv')
    d = pd.read_csv(p)
    d = d[(d.level == 'sigungu') & (d.sex.isin(['male', 'female']))].copy()
    d['g'] = np.where(d.sex == 'male', 1, 2)
    d['band'] = _band(d.age.astype(int).values)
    return d.groupby(['g', 'band'])['pop'].sum().to_dict()


def _nan_block(out, index, cols):
    for c in cols:
        out[c] = np.asarray(np.full(len(index), np.nan), float)


def generate(df, params, ctx):
    g = core.rng('B17')
    n = len(df)
    age = df['age'].astype(int).values
    sex = df['gender'].astype(int).values
    wgt = df['indwgt'].values if 'indwgt' in df.columns else np.full(n, 1.0)
    Npop = float(wgt.sum())
    frac = n / Npop                     # 표본률 (기대 수급자 산정용)
    ui = df['_u_income'].values
    ue = df['_u_emp'].values
    uh = df['_u_health'].values
    out = pd.DataFrame(index=df.index)

    # ── 고용보험 이력 (B16 헬퍼). 미구현 시 폴백 ────────────────────────────
    if '_empins_hist' in df.columns:
        hist = df['_empins_hist'].fillna(0).values.astype(bool)
    elif 'empins_yn1' in df.columns:
        hist = (df['empins_yn1'].fillna(0).values == 1)
    else:   # B16 미구현 폴백: 15~64세 ∧ 고용 잠재변수 상위 (가입률 40.5% 근사)
        hist = (age >= 15) & (age <= 64) & (ue > 0.30)
    pool = hist & (age >= 15)

    # ══════════════════════════════ 1) 구직급여 ═══════════════════════════════
    prof = _load_js_profile()
    pop = _load_pop_band()
    bnd = _band(age)
    rate = np.zeros(n)
    for s_c, s_k in ((1, '남'), (2, '여')):
        for _, _, nm in AGE_BANDS:
            P = pop.get((s_c, nm), 0.0)
            if P > 0:
                rate[(sex == s_c) & (bnd == nm)] = prof.get((s_k, nm), 0.0) / P
    # 고용 불안정(_u_emp 낮음)·저소득일수록 수급확률↑ (§4.1 블록 간 상관)
    score = rate * np.exp(1.0 * (0.5 - ue)) * np.exp(0.3 * (0.5 - ui))
    js = _pick_w(g, score, wgt, float(JS_N), pool)
    njs = int(js.sum())

    # 수급자유형
    tw = np.array(TYPE_WAGE, float); tw = tw / tw.sum()
    p_type = np.array([tw[0] * (1 - DAILY_WORKER_SHARE), tw[0] * DAILY_WORKER_SHARE, tw[1], tw[2]])
    jtype = core.choice_p(g, [1, 2, 3, 4], p_type, n)

    # 구직급여일액 = 기초임금일액 × 60%, 상·하한 적용
    base = core.hist_loguniform(g, WAGE_EDGES, WAGE_W, n, pareto_alpha=3.0)
    # 소득 잠재변수와 순위 결합
    base = np.sort(base)[np.argsort(np.argsort(ui))]
    short = core.bernoulli(g, np.full(n, SHORT_TIME_P)).astype(bool)
    floor = np.where(short, g.uniform(DAILY_FLOOR_MIN, DAILY_FLOOR_8H, n), DAILY_FLOOR_8H)
    daily = np.clip(np.rint(base * DAILY_RATE), floor, DAILY_CAP)

    # 소정급여일수 (피보험기간 × 연령)
    k_ins = core.choice_p(g, [0, 1, 2, 3, 4], SGD_W, n)
    sgd = np.where(age >= 50, np.array(SGD[True])[k_ins], np.array(SGD[False])[k_ins])

    # 2022년 중 실제 수급일수: 소정급여일수 × U(0.35,1.0) → 전국 1인당 지급액에 맞춰 스케일
    dur = sgd * g.uniform(0.35, 1.0, n)
    tgt_amt = JS_AMT / JS_N
    for _ in range(3):
        if njs:
            cur = float((daily[js] * dur[js] * wgt[js]).sum() / wgt[js].sum())
            dur = np.clip(dur * (tgt_amt / max(cur, 1.0)), 1, sgd)
    dur = np.clip(np.rint(dur), 1, sgd).astype(float)
    amt = np.rint(daily * dur)

    out['unempbn_jobseekbn_yn'] = np.asarray(np.where(js, 1, np.nan), float)
    out['unempbn_jobseekbn_type'] = np.asarray(np.where(js, jtype, np.nan), float)
    out['unempbn_jobseekbn_dur'] = np.asarray(np.where(js, dur, np.nan), float)
    out['unempbn_jobseekbn_amt'] = np.asarray(np.where(js, amt, np.nan), float)

    # ══════════════════════ 2) 상병급여 · 개별연장급여 · 기타 ═════════════════
    #   기대 수급자 = 전국 수급자 × 표본률.  3명 미만 → 전량 NaN (규모 미달)
    for cols, N in ((['unempbn_sicknessbn_yn', 'unempbn_sicknessbn_type',
                      'unempbn_sicknessbn_dur', 'unempbn_sicknessbn_amt'], SICK_N),
                    (['unempbn_indivbn_yn', 'unempbn_indivbn_type',
                      'unempbn_indivbn_dur', 'unempbn_indivbn_amt'], INDIV_N),
                    (['unempbn_etc_yn', 'unempbn_etc_amt'], ETC_N)):
        assert N * frac < MIN_EXPECTED, f'규모 미달 판정 재검토 필요: {cols[0]} 기대 {N*frac:.2f}명'
        _nan_block(out, df.index, cols)

    # ══════════════════════════════ 3) 조기재취업수당 ═════════════════════════
    #   소정급여일수의 1/2 이상을 남기고 재취업 → 수급일수가 짧은 자에 집중 [논리적추론]
    esc = np.where(js, np.exp(2.0 * (1.0 - dur / np.maximum(sgd, 1))) * np.exp(0.8 * ue), 0.0)
    early = _pick_w(g, esc, wgt, float(EARLY_N), js)
    # 유형: 상용/일용/결측 [가정 A3-17-4]
    etype = core.choice_p(g, [1, 2, -99999999], [0.86, 0.04, 0.10], n)
    eamt = core.lognormal_mean(g, np.full(n, EARLY_AMT / EARLY_N), 0.45, n)
    if early.any():
        cur = float((eamt[early] * wgt[early]).sum() / wgt[early].sum())
        eamt = eamt * ((EARLY_AMT / EARLY_N) / max(cur, 1.0))
    out['unempbn_early_yn'] = np.asarray(np.where(early, 1, np.nan), float)
    out['unempbn_early_type'] = np.asarray(np.where(early, etype, np.nan), float)
    out['unempbn_early_amt'] = np.asarray(np.where(early, np.rint(eamt), np.nan), float)

    # ══════════════════════════════ 4) 수급기간 연기 ══════════════════════════
    #   임신·출산·육아 사유가 다수 → 가임기 여성 가중 [가정 A3-17-5]
    bsc = np.where(js, np.exp(0.9 * uh) * np.where((sex == 2) & (age >= 25) & (age <= 42), 2.2, 1.0), 0.0)
    bx = _pick_w(g, bsc, wgt, float(JS_N * BNEXT_RATE), js)
    btype = np.where(jtype == 4, 1, np.clip(jtype, 1, 3))       # 예술인·노무제공자 → 상용으로 코딩
    reason = core.choice_p(g, [1, 2, 5, 6, 8], [0.55, 0.30, 0.03, 0.02, 0.10], n)
    reason = np.where((sex == 2) & (age >= 25) & (age <= 42) & (g.random(n) < 0.35), 1, reason)
    reason = np.where((sex == 1) & (age > 30) & (reason == 1), 2, reason)
    out['unempbn_bnextended_yn'] = np.asarray(np.where(bx, 1, np.nan), float)
    out['unempbn_bnextended_type'] = np.asarray(np.where(bx, btype, np.nan), float)
    out['unempbn_bnextended_reason'] = np.asarray(np.where(bx, reason, np.nan), float)

    return out
