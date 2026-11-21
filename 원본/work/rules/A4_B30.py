# -*- coding: utf-8 -*-
"""B30 보육료 4종·노인맞춤돌봄·장애인활동지원  (A4 / order 6, 29변수)

소스 (등급순)
  S1 R05 2023 보건복지통계연보(2022 실적)  [1차확인 2026-09-02]
     <표 4-3-10> 영유아 보육료 수급 아동(반연령·성·시도) 전국 1,071,789명
     <표 4-5-8>  노인맞춤돌봄서비스(시도별) 2022 이용자 일반돌봄군 457,099 + 중점돌봄군 57,300 = 514,399명
  S1 R09 data.go.kr 3084474 보건복지부 장애인활동지원 통계(2022, 시도별)  [1차확인]
     수급자 139,509명 / 이용자 110,778명
  S0 R02 2023년 사회보장 행정데이터 기초분석(2021년 기준)  [1차확인]
     <표 4-34> 소득수준별 노인돌봄서비스 수급률(맞춤돌봄, 10분위)
     <표 4-33> 시도별 노인돌봄서비스 수급률
     <표 10-5> 바우처 사업별 가처분소득 분위별 수급률(2패널: 대상인구 대비) — 장애인활동지원
     <표 10-19> 이용자 1인당 서비스 지원금: 장애인활동지원 평균 22,596천원/년, 중위 19,186천원/년
     p.394 본문: 활동지원급여 16개 구간, 월 한도액 660,000~6,730,000원(2021년 단가 14,020원 기준)
  S4 2022년 보육사업안내 본문  [1차확인]
     인쇄 p.332(PDF p.338) 2022년 보육료 지원단가 — 부모보육료 0세반 499,000 / 1세반 439,000 /
       2세반 364,000 / 3~5세반 260,000(1.1~2.28)·280,000(3.1~) / 장애아 532,000
     인쇄 p.331 방과후 보육료 100,000, 장애아 방과후 266,000, 누리 장애아 532,000
     인쇄 p.332 각주 연장보육료 시간당 영아반 2,000·유아반 1,000·0세반/장애아 3,000
     인쇄 p.315(PDF p.321) 시간제보육 — 지원대상 영아수당(현금)·양육수당 수급자 6~36개월,
       지원시간 월 80시간, 이용단가 4,000원/시간(정부지원 3,000 + 부모부담 1,000)
     인쇄 p.371(PDF p.377) 그 밖의 연장형(야간연장) 보육료 — 일반아동 3,200원/시간·월 한도 192,000원,
       장애아동 4,200원/시간·월 한도 252,000원
  S4 2022년 장애인보건복지정책 이렇게 달라집니다 PDF p.7  [1차확인]
     활동지원 서비스 단가 (’21) 14,020 → (’22) 14,800원/시간, 예산 1조 7,405억, 이용자 107천명
  S1 R03 2022년 국민기초생활보장 수급자 현황 별첨표2(1세단위 연령별 일반수급자)  [1차확인]
     → childcare_type 의 '법정저소득' 비율(기초생활 수급 아동 비율)

정합성
  §7 R07 childcare ⊥ infantbn·carebn  → B28 이 만든 `_pre_prog` 배타 배정을 그대로 사용
  §7 R24 yn2⇒yn1 / dur∈[1,12](개월 단위) / amt>0 ⇔ yn1=1
  지시서 조건: oldcare ⇒ 65+ , disvou_act ⇒ 중증(dis_grade_1=1) ∧ 6~64세
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core, a4_child

RAW = 'params/raw'
SIDO = a4_child.SIDO_CODE

# ── [1차확인] 2022년 보육료 지원단가(부모보육료, 원/월) ─────────────────────
CC_FEE = {0: 499000, 1: 439000, 2: 364000, 3: 280000, 4: 280000, 5: 280000}
CC_FEE_NURI_JANFEB = 260000          # 3~5세반 2022.1.1~2.28
CC_FEE_DIS = 532000                  # 장애아 보육료(부모보육료) / 누리 장애아
TIME_UNIT_SUBSIDY = 3000             # 시간제보육 정부지원 단가(원/시간)
TIME_CAP_HOURS = 80                  # 시간제보육 월 지원한도(시간)
NIGHT_UNIT = 3200                    # 야간연장 보육료 일반아동(원/시간)
NIGHT_CAP_WON = 192000               # 야간연장 월 지원한도액(원)
ACT_UNIT_2022 = 14800                # 장애인활동지원 2022 단가(원/시간)
ACT_UNIT_2021 = 14020                # 2021 단가 — R02 표10-19 역산에 사용
ACT_MIN_H, ACT_MAX_H = 660000 / ACT_UNIT_2021, 6730000 / ACT_UNIT_2021   # 47.1 ~ 480.0시간/월

# ── R02 <표 4-34> 소득수준별 노인맞춤돌봄 수급률(%) [1차확인] ───────────────
OLDCARE_BY_DECILE = np.array([3.6, 11.7, 10.1, 5.3, 2.3, 1.8, 1.7, 1.6, 1.6, 1.2])
# ── R02 <표 10-5> 하단 패널: 장애인활동지원 가처분소득 분위별 수급률(%) [1차확인]
ACT_BY_DECILE = np.array([2.73, 1.94, 2.35, 7.42, 5.41, 4.60, 4.31, 4.58, 4.91, 5.44])

# ── [가정] 파라미터 (원문 미확보 — params/A4_B30.yaml note 참조) ────────────
A_OLDCARE_SOLO = 1.90       # 노인맞춤돌봄 1인가구 상대위험 [가정]
A_OLDCARE_OTHER = 0.75      # 그 외 가구 상대위험 [가정]
A_OLDCARE_PI12 = 0.72       # 12개월 계속이용 비율 [가정]
A_CC_PI12 = 0.80            # 보육료 12개월 계속지원 비율 [가정]
A_TYPE_EXT = 0.10           # 0~2세반 중 연장보육 자격 비율 [가정]
A_TYPE_MULTI = 0.05         # 다문화 자격 비율 [가정]
A_TIME_RATE = 0.06          # 시간제보육 연간 이용률(영아수당·양육수당 수급 6~36개월) [가정]
A_NIGHT_RATE = 0.03         # 야간연장(시간연장형) 보육료 이용률(보육료 수급아동) [가정]
A_ACT_SIGMA = 0.45          # 활동지원 월 급여량 로그정규 σ [가정]
A_ACT_PI12 = 0.85           # 활동지원 12개월 이용 비율 [가정]
A_ACT_USE = (0.93, 0.08)    # 생성액 대비 결제율 평균·표준편차 [가정]


# ────────────────────────────────────────────────────────────── 원자료 로드
def _r05(name):
    d = pd.read_csv(os.path.join(RAW, name))
    d['값'] = pd.to_numeric(d['값'], errors='coerce')
    return d


def _oldcare_targets():
    d = _r05('R05_4-5-8_노인맞춤돌봄서비스_시도별.csv')
    nat = d[(d['구분유형'] == '연도') & (d['구분'].astype(str) == '2022') &
            (d['항목'].isin(['이용자_일반돌봄군', '이용자_중점돌봄군']))]['값'].sum()
    sido = {}
    for s in SIDO:
        m = d[(d['구분유형'] == '시도') & (d['구분'] == s) &
              (d['항목'].isin(['이용자_일반돌봄군', '이용자_중점돌봄군']))]
        sido[SIDO[s]] = float(m['값'].sum())
    return float(nat), sido


def _act_targets():
    d = pd.read_csv(os.path.join(RAW, 'R09_장애인활동지원_시도별_수급자_이용자_기관_2022.csv'))
    d = d[d['시도'].isin(SIDO)]
    tot = float(d['수급자(명)'].sum())
    sido = {SIDO[r['시도']]: float(r['수급자(명)']) for _, r in d.iterrows()}
    return tot, sido


def _pop_sido_age():
    p = pd.read_csv(os.path.join(RAW, 'POPUL_MOIS01_2022_11_sigungu_age1_sex.csv'))
    p = p[(p.level == 'sigungu') & (p.sex.isin(['male', 'female']))].copy()
    p['age'] = p['age'].astype(int); p['sido'] = p['sido'].astype(int)
    return p


def _nbls_child_rate():
    """R03 별첨표2 — 1세단위 기초생활 일반수급자 / 주민등록 인구 (0~5세)."""
    d = pd.read_csv(os.path.join(RAW, 'R03_별첨표2_일반수급자_1세단위연령별_전국.csv'))
    d = d[(d['구분유형'] == '전국') & (d['구분'] == '합계')]
    d = d[d['연령'].astype(str).str.fullmatch(r'\d+')]
    r = {int(a): float(v) for a, v in zip(d['연령'], d['값'])}
    pop = a4_child.load_pop_by_age()
    return {a: (r.get(a, 0.0) / float(pop.loc[a])) for a in range(0, 13) if a in pop.index}


def _dis_severe_fallback(df, g):
    """B27 미구현 시 대체: R05 <표 4-2-2> 연령대별 등록장애인 수 / 주민등록 인구로
    등록률을 만들고, 전체 심한 장애 비율(983,928/2,652,860=37.09%)을 곱해
    _u_health 상위 개인에게 배정한다 [논리적추론]."""
    d = _r05('R05_4-2-2_등록장애인수_장애정도별연령별.csv')
    band = d[(d['구분유형'] == '연령') & (d['항목'] == '계_계')][['구분', '값']]
    sev = float(d[(d['구분유형'] == '장애정도') & (d['구분'] == '심한 장애') &
                  (d['항목'] == '계_계')]['값'].iloc[0])
    tot = float(d[(d['구분유형'] == '전체') & (d['구분'] == '계') &
                  (d['항목'] == '계_계')]['값'].iloc[0])
    sev_share = sev / tot
    pop = a4_child.load_pop_by_age()
    age = df['age'].to_numpy()
    p = np.zeros(len(df))
    for _, r in band.iterrows():
        lab = str(r['구분'])
        if lab.endswith('+'):
            lo, hi = int(lab[:-1]), 100
        else:
            lo, hi = (int(x) for x in lab.split('-'))
        denom = float(pop.loc[[a for a in range(lo, hi + 1) if a in pop.index]].sum())
        if denom <= 0:
            continue
        p[(age >= lo) & (age <= hi)] = float(r['값']) / denom
    p_sev = p * sev_share
    u = df['_u_health'].to_numpy()
    return (u > 1.0 - p_sev).astype(int)


def _income_decile(df):
    """가구 소득분위(1=최저). B05 `_recog_rank` 우선, 없으면 가구평균 `_u_income` 순위 [대체]."""
    if '_recog_rank' in df.columns:
        r = df['_recog_rank'].to_numpy(dtype=float)
    else:
        hm = df.groupby('hid')['_u_income'].transform('mean')
        r = hm.rank(pct=True).to_numpy()
    return np.clip((r * 10).astype(int), 0, 9)          # 0..9 → 1~10분위


def _calibrate(p, w, mask, target):
    """가중합 Σ w·p (mask 내) 가 target 이 되도록 비례 스케일(상한 1)."""
    cur = float((w[mask] * p[mask]).sum())
    if cur <= 0:
        return p
    for _ in range(12):
        k = target / max(cur, 1e-9)
        p = np.where(mask, np.clip(p * k, 0, 1), p)
        cur = float((w[mask] * p[mask]).sum())
        if abs(cur / target - 1) < 1e-4:
            break
    return p


# ─────────────────────────────────────────────────────────────────── 생성
def generate(df, params, ctx):
    g = core.rng('B30')
    n = len(df)
    out = pd.DataFrame(index=df.index)
    nan = np.full(n, np.nan)
    age = df['age'].to_numpy()
    yr = df['year'].to_numpy()
    w = df['indwgt'].to_numpy() if 'indwgt' in df.columns else np.ones(n)

    # 0) B28 산출물 (_pre_prog, _bmonth) — 없으면 동일 난수열로 재계산 -------
    if '_pre_prog' in df.columns and '_bmonth' in df.columns:
        prog = df['_pre_prog'].to_numpy()
        bmonth = df['_bmonth'].to_numpy()
    else:
        prog, bmonth, _, _, _ = a4_child.assign(df, core.rng('B28'))

    # 0b) 선행 블록 대체 지표 ------------------------------------------------
    if 'dis_grade_1' in df.columns and 'dis_yn' in df.columns:
        severe = ((df['dis_yn'] == 1) & (df['dis_grade_1'] == 1)).to_numpy().astype(int)
    else:
        severe = _dis_severe_fallback(df, g)          # B27 미구현 대체
    dec = _income_decile(df)
    nbls_rate = _nbls_child_rate()
    if '_is_nbls' in df.columns:
        low_inc = (df['_is_nbls'] == 1).to_numpy()
    else:
        pr = np.array([nbls_rate.get(int(a), 0.0) for a in age])
        low_inc = df['_u_income'].to_numpy() < pr      # 저소득 잠재변수 하위 = 기초생활 [대체]

    # ══════════════════════════ 1. 보육료 지원 (childcare) ══════════════════
    m_cc = (prog == 'childcare')
    cls = a4_child.class_age(yr)                       # 반연령 0~5 [1차확인 반편성 기준]
    dis_child = m_cc & (severe == 1)

    dur_cc = core.dur_months(g, n, A_CC_PI12, 3, 11).astype(float)
    dur_cc = np.where(yr >= 2022, np.clip(13 - bmonth - 2, 1, 12), dur_cc)   # 2022년생 늦은 입소
    dur_cc = np.clip(dur_cc, 1, 12)

    fee_m = np.array([CC_FEE[c] for c in cls], dtype=np.int64)
    fee_m = np.where(dis_child, CC_FEE_DIS, fee_m)
    # 3~5세반은 1~2월 260,000 → 3월 이후 280,000 [1차확인]
    nuri = (cls >= 3) & (~dis_child)
    amt_cc = fee_m * dur_cc
    adj = np.where(nuri, np.minimum(dur_cc, 2) * (CC_FEE_NURI_JANFEB - CC_FEE[3]), 0)
    amt_cc = amt_cc + adj

    out['childcare_yn1'] = np.where(m_cc, 1.0, np.nan)
    out['childcare_dur'] = np.where(m_cc, dur_cc, np.nan)
    yn2_cc = np.where(dur_cc >= 12, 1.0, core.bernoulli(g, np.full(n, 0.75)).astype(float))
    out['childcare_yn2'] = np.where(m_cc, yn2_cc, np.nan)
    out['childcare_amt'] = np.where(m_cc, np.round(amt_cc, -3), np.nan)

    # childcare_type — 코드북 9개 값, 2022.12 기준 지원자만 -------------------
    r1, r2 = g.random(n), g.random(n)
    is_low = low_inc
    is_multi = r2 < A_TYPE_MULTI
    ext = r1 < A_TYPE_EXT
    t = np.full(n, np.nan)
    young = cls <= 2
    t = np.where(young & ext & is_low, 8.0, t)          # 연장보육(만0-2세 법정)
    t = np.where(young & ext & (~is_low) & is_multi, 7.0, t)
    t = np.where(young & ext & (~is_low) & (~is_multi), 6.0, t)
    t = np.where(young & (~ext), 1.0, t)               # 기본보육
    t = np.where((~young) & is_low, 4.0, t)            # 누리(만3-5세 법정)
    t = np.where((~young) & (~is_low) & is_multi, 3.0, t)
    t = np.where((~young) & (~is_low) & (~is_multi), 2.0, t)
    t = np.where(dis_child & young, 9.0, t)            # 장애아보육료
    t = np.where(dis_child & (~young), 5.0, t)         # 누리(만3-5세 장애아)
    out['childcare_type'] = np.where(m_cc & (out['childcare_yn2'].to_numpy() == 1), t, np.nan)

    # ══════════════════ 2. 시간제보육 (childcare_time) ══════════════════════
    # [1차확인] 지원대상: 어린이집·유치원 미이용 + 영아수당(현금)·양육수당 수급 중 6~36개월
    mm_dec = (2022 - yr) * 12 + (12 - bmonth)
    mm_jan = (2022 - yr) * 12 + (1 - bmonth)
    elig_t = np.isin(prog, ['infant', 'care']) & (mm_dec >= 6) & (mm_jan < 36)
    hit_t = elig_t & (core.bernoulli(g, np.where(elig_t, A_TIME_RATE, 0.0)) == 1)
    dur_t = np.clip(g.integers(1, 7, n), 1, 12).astype(float)
    hrs_t = np.clip(np.round(g.uniform(4, 40, n)), 1, TIME_CAP_HOURS)
    out['childcare_time_yn1'] = np.where(hit_t, 1.0, np.nan)
    out['childcare_time_yn2'] = np.where(hit_t, core.bernoulli(g, np.full(n, 0.45)).astype(float), np.nan)
    out['childcare_time_dur'] = np.where(hit_t, dur_t, np.nan)
    out['childcare_time_subsidy'] = np.where(hit_t, np.round(hrs_t * dur_t * TIME_UNIT_SUBSIDY, -3), np.nan)

    # ══════════════════ 3. 시간연장형(야간연장) 보육료 ══════════════════════
    hit_l = m_cc & (core.bernoulli(g, np.where(m_cc, A_NIGHT_RATE, 0.0)) == 1)
    dur_l = np.minimum(dur_cc, np.clip(g.integers(2, 13, n), 1, 12)).astype(float)
    hrs_l = np.clip(np.round(g.uniform(5, 55, n)), 1, NIGHT_CAP_WON / NIGHT_UNIT)
    out['childcare_longtime_yn1'] = np.where(hit_l, 1.0, np.nan)
    out['childcare_longtime_yn2'] = np.where(hit_l, core.bernoulli(g, np.full(n, 0.7)).astype(float), np.nan)
    out['childcare_longtime_dur'] = np.where(hit_l, dur_l, np.nan)
    out['childcare_longtime_amt'] = np.where(hit_l, np.round(hrs_l * dur_l * NIGHT_UNIT, -3), np.nan)

    # ══════════════════ 4. 방과후 보육료 — 규모 미달 → 전량 NaN ════════════
    for s in ('yn1', 'yn2', 'dur', 'amt'):
        out[f'childcare_aftsch_{s}'] = nan

    # ══════════════════ 5. 노인맞춤돌봄 (oldcare) ═══════════════════════════
    tgt_old, sido_old = _oldcare_targets()
    pop = _pop_sido_age()
    p65 = pop[pop.age >= 65].groupby('sido')['pop'].sum()
    nat65 = float(p65.sum())
    base_old = tgt_old / nat65
    rr_sido_old = {s: (sido_old[s] / float(p65.get(s, np.nan)) / base_old) for s in sido_old}

    sido = df['_sido'].to_numpy().astype(int)
    hnum = df['hnum'].to_numpy()
    p_old = np.zeros(n)
    m65 = age >= 65
    p_old[m65] = (OLDCARE_BY_DECILE[dec[m65]] / 100.0) \
        * np.array([rr_sido_old.get(int(s), 1.0) for s in sido[m65]]) \
        * np.where(hnum[m65] == 1, A_OLDCARE_SOLO, A_OLDCARE_OTHER)
    p_old = _calibrate(p_old, w, m65, tgt_old)
    hit_o = m65 & (core.bernoulli(g, p_old) == 1)
    dur_o = core.dur_months(g, n, A_OLDCARE_PI12, 1, 11).astype(float)
    out['oldcare_yn1'] = np.where(hit_o, 1.0, np.nan)
    out['oldcare_dur'] = np.where(hit_o, dur_o, np.nan)
    out['oldcare_yn2'] = np.where(hit_o, np.where(dur_o >= 12, 1.0,
                                                  core.bernoulli(g, np.full(n, 0.6)).astype(float)), np.nan)

    # ══════════════════ 6. 장애인활동지원 (disvou_act) ══════════════════════
    tgt_act, sido_act = _act_targets()
    p664 = pop[(pop.age >= 6) & (pop.age <= 64)].groupby('sido')['pop'].sum()
    base_act = tgt_act / float(p664.sum())
    rr_sido_act = {s: (sido_act[s] / float(p664.get(s, np.nan)) / base_act) for s in sido_act}

    m_act = (age >= 6) & (age <= 64) & (severe == 1)
    p_act = np.zeros(n)
    p_act[m_act] = (ACT_BY_DECILE[dec[m_act]] / 100.0) \
        * np.array([rr_sido_act.get(int(s), 1.0) for s in sido[m_act]])
    p_act = _calibrate(p_act, w, m_act, tgt_act)
    hit_a = m_act & (core.bernoulli(g, p_act) == 1)

    # 월 급여량(시간): R02 <표 10-19> 활동지원 1인당 정부지원금 평균 22,596천원/년을
    # 2021년 단가 14,020원으로 나눈 월 134.3시간을 평균으로 하는 로그정규 [논리적추론],
    # 구간 하·상한 47.1~480.0시간(R02 p.394 월 한도액 660,000~6,730,000원)으로 절단
    mean_h = 22596000.0 / 12.0 / ACT_UNIT_2021           # 134.3시간/월
    hours_raw = core.lognormal_mean(g, np.full(n, mean_h), A_ACT_SIGMA, n)
    dur_a = core.dur_months(g, n, A_ACT_PI12, 2, 11).astype(float)
    # 사용률 — R09 [1차확인] 수급자 139,509명 대비 이용자 110,778명(79.4%) → 20.6%는
    # 자격만 보유하고 실제 결제가 거의 없다(코드북 주 "실제 이용이 아니라 자격 기준으로 추출").
    act_share = 110778.0 / 139509.0
    active = g.random(n) < act_share
    use = np.where(active,
                   np.clip(g.normal(A_ACT_USE[0], A_ACT_USE[1], n), 0.55, 1.0),
                   g.uniform(0.02, 0.15, n))
    fee_rate = np.where(dec == 0, 0.0, np.where(dec == 1, -1.0,
                        0.02 + 0.07 * (dec - 1) / 8.0))          # [가정] 소득분위별 본인부담률
                                                                 # (-1 = 차상위 정액 20,000원/월)

    def _build(h):
        h = np.clip(h, ACT_MIN_H, ACT_MAX_H)
        tot = h * ACT_UNIT_2022 * dur_a
        a = tot * use
        f = np.where(fee_rate < 0, 20000.0 * dur_a, a * np.maximum(fee_rate, 0.0))
        f = np.minimum(f, a * 0.15)
        return h, tot, a, f, a - f

    # 연간 정부지원금 평균을 R02 <표 10-19>(2021 평균 22,596천원)의 2022년 단가 환산치
    # 23,853천원에 맞춰 급여량 스케일 1회 보정 [논리적추론]
    tgt_sub = 22596000.0 * ACT_UNIT_2022 / ACT_UNIT_2021
    hours_m, total, amt, fee, subsidy = _build(hours_raw)
    sel = hit_a & active                       # 실제 이용자 기준으로 평균 맞춤
    if sel.any():
        k = tgt_sub / max(float(subsidy[sel].mean()), 1.0)
        hours_m, total, amt, fee, subsidy = _build(hours_raw * k)
    hours_y = np.round(hours_m * dur_a * use)

    start_m = (1 + np.floor(g.random(n) * (13 - dur_a))).astype(int)
    start_m = np.clip(start_m, 1, 12)
    end_m = np.clip(start_m + dur_a - 1, 1, 12).astype(int)

    out['disvou_act_yn1'] = np.where(hit_a, 1.0, np.nan)
    out['disvou_act_yn2'] = np.where(hit_a, (end_m >= 12).astype(float), np.nan)
    out['disvou_act_dur'] = np.where(hit_a, hours_y, np.nan)             # 단위: 시간/년
    out['disvou_act_total'] = np.where(hit_a, np.round(total, -3), np.nan)
    out['disvou_act_amt'] = np.where(hit_a, np.round(amt, -3), np.nan)
    out['disvou_act_fee'] = np.where(hit_a, np.round(fee, -3), np.nan)
    out['disvou_act_subsidy'] = np.where(hit_a, np.round(subsidy, -3), np.nan)
    out['disvou_act_dur2_a'] = np.where(hit_a, 202200 + start_m, np.nan)
    out['disvou_act_dur2_b'] = np.where(hit_a, 202200 + end_m, np.nan)

    # ══════════════════ 7. 정합성 강제 (§7 R24) ═════════════════════════════
    month_dur = ['childcare_dur', 'childcare_time_dur', 'childcare_longtime_dur',
                 'childcare_aftsch_dur', 'oldcare_dur']
    for c in month_dur:
        s = out[c]
        out.loc[s.notna(), c] = s[s.notna()].clip(1, 12)
    for pre in ('childcare', 'childcare_time', 'childcare_longtime', 'childcare_aftsch',
                'oldcare', 'disvou_act'):
        y1, y2 = f'{pre}_yn1', f'{pre}_yn2'
        if y1 in out.columns and y2 in out.columns:
            bad = (out[y2] == 1) & (out[y1] != 1)
            out.loc[bad, y2] = 0.0

    if 'indwgt' in df.columns:
        ctx['B30_report'] = {
            'childcare_N': float(np.nansum(w * (out['childcare_yn1'] == 1))),
            'childcare_amt_백만원': float(np.nansum(w * out['childcare_amt'].fillna(0)) / 1e6),
            'oldcare_N': float(np.nansum(w * (out['oldcare_yn1'] == 1))),
            'oldcare_target': tgt_old,
            'disvou_act_N': float(np.nansum(w * (out['disvou_act_yn1'] == 1))),
            'disvou_act_target': tgt_act,
        }
    return out
