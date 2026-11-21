# -*- coding: utf-8 -*-
"""B33 장기요양 (ltcare_*)  (A5 / order 5)

소스 (등급순)
  S0  R02 <표 4-33>/<표 4-34> 노인 돌봄서비스 수급률 — 사회보장행정데이터(2021) 65+ 장기요양
      수급률 6.5%, 가처분소득 10분위별 수급률.  params/raw/R02_표4-33*.csv, R02_표4-34*.csv [1차확인]
      ※ 본 가상데이터와 동일 자료원(행정데이터 일반가구 표본)의 관측치 → 수준·소득기울기의 1순위 기준
  S1  국민건강보험공단 2022 노인장기요양보험통계연보 (params/raw/_ext/b33/*.xlsx) [1차확인]
        <1-1표>  연도별 65세이상 의료보장 적용인구            → params/tab/B33_T1-1_*.csv
        <2-1표>  연도별 자격별 인정 신청 현황                 → params/tab/B33_T2-1_*.csv
        <2-6표>  시도별 등급별 자격별 주거상태 현황           → params/raw/B33_2-6_*.csv
        <2-7표>  시도별 등급별 자격별 주요질병 및 증상 현황   → params/raw/B33_2-7_*.csv
        <2-8표>  시도별 등급별 자격별 주수발자 현황           → params/raw/B33_2-8_*.csv
        <2-9표>  시도별 등급별 연령별 자격별 등급 판정 현황   → params/tab/B33_T2-9_*.csv
        <3-1표>  시군구별 등급별 급여종류별 급여실적(전국 계) → params/tab/B33_T3-1_*.csv
        <3-3표>  연령별 자격별 급여종류별 급여실적            → params/tab/B33_T3-3_*.csv
        <5-1표>  연도별 장기요양 재정현황(가족요양비)         → params/tab/B33_T5-1_*.csv
      제도소개(hwp) : 등급별 인정점수 구간, 본인부담 재가 15%/시설 20%, 기초 면제·40~60% 감경
  S1  R05 2023 보건복지통계연보 <표 4-5-9> 연도별 신청자·판정자·인정자
      params/raw/R05_4-5-9_장기요양신청및인정현황_시도별.csv [1차확인]
  S2  행안부 주민등록 2022.11 시군구×1세×성 인구 (연령·성별 이용률의 분모) [1차확인]

핵심 설계 (일반가구 표본 과소포착 보정)
  본 데이터는 등록센서스 **일반가구** 표본이라 인정조사 시점에 노인요양시설·요양병원에 있던
  수급자가 빠진다. <2-6표>상 인정자의 79.6%만 자택 거주.
  ① 구조 보정 : 등급별 표본포함 가중 ∝ 자택 거주 비율(<2-6표>)  → 등급구성이 4·5등급 쪽으로 이동
  ② 수준 보정 : 65+ 수급률을 S0 R02 6.5%(2021)에 2022 인정자 증가율(1,019,130/953,511)을 곱한
                6.95% 로 맞추는 상수 배율                     → 공표 이용률 10.50% 대비 0.66배
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

RAW = 'params/raw'
TAB = 'params/tab'

# ── 상수 (모두 원문 확인값) ───────────────────────────────────────────────────
# R05 <표 4-5-9> 연도별 인정자·신청자 [1차확인 2026-09-02]
N_RECOG_2021, N_RECOG_2022 = 953_511, 1_019_130
N_APPLY_2022 = 1_348_961
# S0 R02 <표 4-33> 2021년 65+ 장기요양 수급률 [1차확인]
S0_RATE_65P_2021 = 0.065
# S0 R02 <표 4-34> 가처분소득 10분위별 65+ 장기요양 수급률(%) [1차확인]
S0_DECILE_RATE = np.array([8.4, 10.4, 6.7, 5.6, 5.4, 4.8, 4.8, 5.0, 5.4, 5.1])
S0_RATE_ALL = 6.5
# 등급별 인정점수 구간 — 통계연보 제도소개 "장기요양 등급별 대표적 상태" [1차확인]
SCORE_BAND = {1: (95, 100), 2: (75, 95), 3: (60, 75), 4: (51, 60), 5: (45, 51), 6: (40, 45)}
# 자격별 실효 본인부담률 — <3-3표> (급여비용−공단부담금)/급여비용 [1차확인]
OWNPAY = {'일반': (0.1341, 0.1728), '감경': (0.0627, 0.0796),
          '의료급여': (0.0540, 0.0690), '기초': (0.0, 0.0)}
# 자격 구성비 — <3-3표> 급여이용수급자 (자격 변동에 따른 중복 포함, 정규화) [1차확인]
QUAL_N = {'일반': 515_325, '감경': 425_801, '의료급여': 10_963, '기초': 160_375}
# 개인 잠재변수 반영 강도 [가정]
BETA_HEALTH = 1.2
# 이용일수 분포 집중도 (Beta 분포) [가정]
KAPPA_DAYS = 2.5
SIGMA_AMT = 0.8            # 복지용구 금액 로그정규 σ [가정]
MIN_EXPECTED = 3.0         # 기대 수급자 3명 미만이면 전량 NaN (작업지시서 규모 미달 규칙)

AGE_BANDS = [(0, 64, '65세미만'), (65, 69, '65~69세'), (70, 74, '70~74세'),
             (75, 79, '75~79세'), (80, 84, '80~84세'), (85, 200, '85세이상')]
GRADE_KO = {'1등급': 1, '2등급': 2, '3등급': 3, '4등급': 4, '5등급': 5, '인지지원등급': 6, '인지지원': 6}
# 3-3표 연령 표기 → 공통 밴드
A33 = {'65세미만': '65세미만', '65세~69세': '65~69세', '70세~74세': '70~74세',
       '75세~79세': '75~79세', '80세~84세': '80~84세', '85세이상': '85세이상'}
# 코드북 주수발자 코드 ← <2-8표> 항목
CG_MAP = {'독거': 0, '배우자': 1, '부모': 2, '자녀(며느리,사위포함)': 4, '손자녀': 5,
          '친척': 6, '친구,이웃': 7, '간병인': 8, '자원봉사자': 9, '기타': 11}
# 코드북 노인성질환 코드 ← <2-7표> 항목
DIS_MAP = {'질병없음': 0, '치매': 1, '중풍(뇌졸증)': 2, '치매+중풍': 3, '고혈압': 4, '당뇨병': 5,
           '관절염': 6, '요통,좌골통': 7, '골절,탈골등사고로인한후유증': 9, '암': 10,
           '심부전': 11, '난청': 12, '백내장등시각장애': 13, '기타': 99}


def _band(age):
    a = np.asarray(age)
    out = np.empty(len(a), dtype=object)
    for lo, hi, nm in AGE_BANDS:
        out[(a >= lo) & (a <= hi)] = nm
    return out


# ── 원자료 로드 ──────────────────────────────────────────────────────────────
def _load():
    t33 = pd.read_csv(os.path.join(TAB, 'B33_T3-3_연령성자격급여종류별_급여실적.csv'))
    t31 = pd.read_csv(os.path.join(TAB, 'B33_T3-1_등급별급여종류별_급여실적_전국.csv'))
    t29 = pd.read_csv(os.path.join(TAB, 'B33_T2-9_연령별등급별_등급판정현황_전국.csv'))
    t26 = pd.read_csv(os.path.join(RAW, 'B33_2-6_시도별_등급별_주거상태현황.csv'))
    t27 = pd.read_csv(os.path.join(RAW, 'B33_2-7_시도별_등급별_주요질병및증상현황.csv'))
    t28 = pd.read_csv(os.path.join(RAW, 'B33_2-8_시도별_등급별_주수발자현황.csv'))
    pop = pd.read_csv(os.path.join(RAW, 'POPUL_MOIS01_2022_11_sigungu_age1_sex.csv'))
    pop = pop[(pop.level == 'sigungu') & (pop.sex.isin(['male', 'female']))].copy()
    pop['age'] = pop['age'].astype(int)
    pop['성별'] = np.where(pop.sex == 'male', '남', '여')
    pop['band'] = _band(pop['age'].values)
    return t33, t31, t29, t26, t27, t28, pop


def _rate_age_sex(t33, pop):
    """<3-3표> 급여이용수급자 / 주민등록 인구 → (연령밴드, 성)별 공표 이용률 [1차확인]."""
    u = t33[(t33.자격 == '계') & (t33.지표 == '급여이용수급자') & (t33.급여종류 == '계')
            & (t33.성별.isin(['남', '여'])) & (t33.연령 != '계')].copy()
    u['band'] = u['연령'].map(A33)
    P = pop.groupby(['band', '성별'])['pop'].sum()
    r = {}
    for _, row in u.iterrows():
        r[(row['band'], row['성별'])] = float(row['값']) / float(P.loc[(row['band'], row['성별'])])
    return r


def _home_share_by_grade(t26):
    """<2-6표> 등급별 자택 거주 비율 — 일반가구 표본 포함 구조보정 가중."""
    s = t26[(t26.시도 == '계') & (t26.성별 == '계')]
    p = s.pivot(index='장기요양등급', columns='구분', values='인원_명')
    return {GRADE_KO[k]: float(p.loc[k, '자택']) / float(p.loc[k, '계'])
            for k in p.index if k in GRADE_KO}, p


def _grade_dist_by_band(t29, home_share):
    """<2-9표> 연령밴드별 인정등급 분포 × 자택비율(<2-6표>) → 표본 등급분포."""
    s = t29[(t29.성별 == '계') & (t29.자격 == '계') & (t29.연령 != '계')]
    p = s.pivot(index='연령', columns='장기요양등급', values='인원_명')
    out, ext = {}, {}
    for band in p.index:
        w = {}
        for k, g in GRADE_KO.items():
            if k in p.columns:
                w[g] = float(p.loc[band, k]) * home_share[g]
        tot = sum(w.values())
        out[band] = {g: v / tot for g, v in w.items()}
        ext[band] = float(p.loc[band, '등급외'])
    return out, ext, p


def _benefit_probs(t31):
    """<3-1표> 등급별 급여종류별 이용자 → P(시설|등급), P(재가종류|재가·등급), 일수·단가."""
    u = t31.pivot_table(index='장기요양등급', columns=['급여종류', '지표'], values='값')
    res = {}
    for k, g in GRADE_KO.items():
        if k not in u.index: continue
        n_tot = float(u.loc[k, ('계', '급여이용수급자')])
        n_inst = float(u.loc[k, ('노인요양시설', '급여이용수급자')]) + \
                 float(u.loc[k, ('노인요양공동생활가정', '급여이용수급자')])
        pool = n_tot - n_inst
        d = {'p_inst': n_inst / n_tot, 'home_pool': pool, 'types': {}}
        for b in ('방문요양', '방문목욕', '방문간호', '주야간보호', '단기보호', '복지용구'):
            n = float(u.loc[k, (b, '급여이용수급자')])
            days = float(u.loc[k, (b, '급여제공일수')])
            cost = float(u.loc[k, (b, '급여비용')]) * 1000.0      # 천원 → 원
            d['types'][b] = {'p': (n / pool) if pool > 0 else 0.0,
                             'mean_days': (days / n) if n > 0 else 0.0,
                             'unit': (cost / days) if days > 0 else 0.0,
                             'per_cap': (cost / n) if n > 0 else 0.0}
        for b in ('노인요양시설', '노인요양공동생활가정'):
            n = float(u.loc[k, (b, '급여이용수급자')])
            days = float(u.loc[k, (b, '급여제공일수')])
            cost = float(u.loc[k, (b, '급여비용')]) * 1000.0
            d[b] = {'n': n, 'mean_days': (days / n) if n > 0 else 0.0,
                    'unit': (cost / days) if days > 0 else 0.0}
        res[g] = d
    return res


def _cat_dist(tbl, keys):
    """<2-7표>/<2-8표> 전국·성계 등급별 항목분포 → {등급: (codes, probs)}."""
    s = tbl[(tbl.시도 == '계') & (tbl.성별 == '계')]
    p = s.pivot(index='장기요양등급', columns='구분', values='인원_명')
    p.columns = [str(c).replace(' ', '') for c in p.columns]
    out = {}
    for k, g in GRADE_KO.items():
        if k not in p.index: continue
        codes, w = [], []
        for name, code in keys.items():
            if name in p.columns and pd.notna(p.loc[k, name]):
                codes.append(code); w.append(float(p.loc[k, name]))
        w = np.array(w, float)
        out[g] = (np.array(codes), w / w.sum())
    return out


def _madow(g, p):
    """Madow 계통추출: 포함확률 p 를 유지하면서 표본수를 round(Σp) 로 고정."""
    p = np.clip(np.asarray(p, float), 0.0, 1.0)
    n = len(p)
    if p.sum() <= 0: return np.zeros(n, bool)
    order = g.permutation(n)
    cs = np.cumsum(p[order])
    k = int(np.floor(cs[-1] + g.random()))
    sel = np.zeros(n, bool)
    if k <= 0: return sel
    u = g.random()
    pts = u + np.arange(k)
    pos = np.searchsorted(cs, pts, side='left')
    pos = np.clip(pos, 0, n - 1)
    sel[order[pos]] = True
    return sel


def _beta_days(g, mean_days, n, cap=365.0):
    """평균을 정확히 보존하는 Beta(κ) 이용일수 (하한 1일)."""
    if n == 0: return np.zeros(0)
    mu = float(np.clip(mean_days / cap, 1e-3, 0.999))
    kap = max(KAPPA_DAYS, 1.0 / mu)          # a=μκ≥1 → 저평균 항목의 과도한 왜도 방지
    a, b = mu * kap, (1 - mu) * kap
    x = g.beta(a, b, n) * cap
    return np.clip(np.rint(x), 1, cap)


# ── 생성 ─────────────────────────────────────────────────────────────────────
def generate(df, params, ctx):
    g = core.rng('B33')
    n = len(df)
    t33, t31, t29, t26, t27, t28, pop = _load()

    rate_as = _rate_age_sex(t33, pop)
    home_share, t26p = _home_share_by_grade(t26)
    gdist, ext_n, t29p = _grade_dist_by_band(t29, home_share)
    ben = _benefit_probs(t31)
    cg = _cat_dist(t28, CG_MAP)
    dis = _cat_dist(t27, DIS_MAP)

    band = _band(df['age'].values)
    sex = np.where(df['gender'].astype(int).values == 1, '남', '여')
    is65 = df['age'].values >= 65

    # ── 1) 수급 성향 ──────────────────────────────────────────────────────────
    base = np.array([rate_as.get((b, s), 0.0) for b, s in zip(band, sex)])
    # 등급구성 보정(자택비율) — 연령밴드별 평균 자택비율
    hc_band = {}
    for b in t29p.index:
        num = sum(float(t29p.loc[b, k]) * home_share[gg]
                  for k, gg in GRADE_KO.items() if k in t29p.columns)
        den = sum(float(t29p.loc[b, k]) for k in GRADE_KO if k in t29p.columns)
        hc_band[b] = num / den
    hcorr = np.array([hc_band[b] for b in band])
    # 소득분위 상대위험 (S0 R02 <표 4-34>)
    if '_recog_rank' in df.columns:
        rk = df['_recog_rank'].fillna(df['_u_income']).values
        inc_src = '_recog_rank'
    else:
        rk = df['_u_income'].values
        inc_src = '_u_income'
    dec = np.clip((rk * 10).astype(int), 0, 9)
    rr_inc = (S0_DECILE_RATE / S0_RATE_ALL)[dec]
    # 건강 잠재변수
    uh = df['_u_health'].values
    rr_h = np.exp(BETA_HEALTH * (uh - 0.5))
    rr_h = rr_h / rr_h.mean()

    prop = base * hcorr * rr_inc * rr_h
    # 수준 보정 : 65+ 평균 수급확률 = S0 6.5% × (2022/2021 인정자)
    target65 = S0_RATE_65P_2021 * (N_RECOG_2022 / N_RECOG_2021)
    k65 = target65 / prop[is65].mean()
    p = np.clip(prop * k65, 0, 0.95)
    # 65세 미만은 공표 구성비(30,320/999,451)에 맞춰 별도 스케일
    n65_exp = p[is65].sum()
    u65_share = 30_320 / 999_451
    if p[~is65].sum() > 0:
        p[~is65] *= (n65_exp * u65_share / (1 - u65_share)) / p[~is65].sum()

    bn = _madow(g, p)
    # §7 R14 : 65세 미만 수급자 비율 ≤ 5% 강제
    idx_u65 = np.flatnonzero(bn & ~is65)
    cap_u65 = int(np.floor(0.05 * bn.sum()))
    if len(idx_u65) > cap_u65:
        drop = g.choice(idx_u65, size=len(idx_u65) - cap_u65, replace=False)
        bn[drop] = False
    nb = int(bn.sum())

    # ── 2) 신청 (ltcare_yn) : 수급자 전원 + 비수급 신청자(등급외) ───────────────
    apply_ratio = N_APPLY_2022 / N_RECOG_2022 - 1.0        # 0.3236 [1차확인]
    n_extra = int(round(nb * apply_ratio))
    P = pop.groupby('band')['pop'].sum()
    w_ext = np.array([ext_n[b] / float(P.loc[b]) for b in band])
    w_ext[bn] = 0.0
    if w_ext.sum() > 0 and n_extra > 0:
        n_extra = min(n_extra, int((w_ext > 0).sum()))
        extra = g.choice(n, size=n_extra, replace=False, p=w_ext / w_ext.sum())
    else:
        extra = np.array([], dtype=int)
    applied = bn.copy(); applied[extra] = True
    # R14 는 ltcare_yn 기준 → 신청자에도 동일 상한 적용
    idx_u65a = np.flatnonzero(applied & ~is65)
    cap_u65a = int(np.floor(0.05 * applied.sum()))
    if len(idx_u65a) > cap_u65a:
        cand = np.array([i for i in idx_u65a if not bn[i]])
        k = len(idx_u65a) - cap_u65a
        if len(cand) >= k:
            applied[g.choice(cand, size=k, replace=False)] = False

    # ── 3) 등급 ──────────────────────────────────────────────────────────────
    grade = np.full(n, np.nan)
    for b in sorted(set(band[bn])):
        m = bn & (band == b)
        codes = np.array(sorted(gdist[b])); pr = np.array([gdist[b][c] for c in codes])
        grade[m] = core.choice_p(g, codes, pr, int(m.sum()))
    grade[applied & ~bn] = 9                                   # 등급외

    # ── 4) 인정점수 (등급 1~6) ────────────────────────────────────────────────
    score = np.full(n, np.nan)
    for gr, (lo, hi) in SCORE_BAND.items():
        m = grade == gr
        c = int(m.sum())
        if c: score[m] = np.rint(g.uniform(lo, hi, c))

    # ── 5) 노인성질환 · 주수발자 (수급자) ─────────────────────────────────────
    cgt = np.full(n, np.nan); dnum = np.full(n, np.nan)
    for gr in range(1, 7):
        m = bn & (grade == gr)
        c = int(m.sum())
        if not c: continue
        cd, pr = dis[gr]; dnum[m] = core.choice_p(g, cd, pr, c)
    # 가구 정합성 : 독거(0) ⇒ 1인가구, 배우자(1) ⇒ 배우자 존재 (주변분포 보존형 재배정)
    hnum = df['hnum'].values if 'hnum' in df.columns else np.ones(n)
    has_sp = df['_spouse_age'].notna().values if '_spouse_age' in df.columns else np.zeros(n, bool)
    alone = hnum == 1
    if bn.any():
        p0 = np.array([cg[int(x)][1][list(cg[int(x)][0]).index(0)] if 0 in cg[int(x)][0] else 0.0
                       for x in grade[bn]])
        p1 = np.array([cg[int(x)][1][list(cg[int(x)][0]).index(1)] if 1 in cg[int(x)][0] else 0.0
                       for x in grade[bn]])
        idx = np.flatnonzero(bn)
        # (a) 독거 : 1인가구에만, 전국 주변분포(Σp0)를 맞추도록 확률 상향
        al = alone[idx]
        if al.sum() > 0:
            q = np.clip(p0.sum() / al.sum(), 0, 1)
            pick = _madow(g, np.where(al, q, 0.0))
            cgt[idx[pick]] = 0
        # (b) 배우자 : 배우자 존재자에만, Σp1 을 맞추도록 확률 상향
        rest = np.isnan(cgt[idx])
        hs = has_sp[idx] & rest
        if hs.sum() > 0:
            q = np.clip(p1.sum() / hs.sum(), 0, 1)
            pick = _madow(g, np.where(hs, q, 0.0))
            cgt[idx[pick]] = 1
        # (c) 나머지 : 등급별 분포에서 0·1 제외 후 재정규화
        for gr in range(1, 7):
            m = bn & (grade == gr) & np.isnan(cgt)
            c = int(m.sum())
            if not c: continue
            cd, pr = cg[gr]
            keep = ~np.isin(cd, [0, 1])
            cgt[m] = core.choice_p(g, cd[keep], pr[keep], c)

    # ── 6) 급여종류 ──────────────────────────────────────────────────────────
    # 시설급여 : 인정조사 시점 시설 거주자는 일반가구 표본에서 제외되므로
    #            <2-6표> 시설거주자/<3-3표> 연간 시설급여 이용자 비율만큼 오즈를 낮춘다
    n_inst_year = 234_280 + 20_753                       # <3-3표> 연간 시설급여 이용자
    n_inst_point = 118_744 + 5_669                       # <2-6표> 인정조사 시점 시설 거주자
    f_inst = 1.0 - n_inst_point / n_inst_year            # 0.512 [논리적추론]

    inst = np.zeros(n, bool)
    for gr in range(1, 7):
        m = bn & (grade == gr)
        c = int(m.sum())
        if not c: continue
        p0 = ben[gr]['p_inst']
        ps = p0 * f_inst / (p0 * f_inst + (1 - p0))
        inst[m] = core.bernoulli(g, np.full(c, ps)).astype(bool)

    HOME_T = {'visit': '방문요양', 'bath': '방문목욕', 'daynight': '주야간보호', 'extrah': '복지용구'}
    yn = {k: np.zeros(n, np.int8) for k in HOME_T}
    for gr in range(1, 7):
        m = bn & (grade == gr) & ~inst
        c = int(m.sum())
        if not c: continue
        for k, b in HOME_T.items():
            yn[k][m] = core.bernoulli(g, np.full(c, ben[gr]['types'][b]['p']))
        none = m & (yn['visit'] + yn['bath'] + yn['daynight'] + yn['extrah'] == 0)
        if none.any():                                   # 최소 1종 이용 보장
            top = max(HOME_T, key=lambda k: ben[gr]['types'][HOME_T[k]]['p'])
            yn[top][none] = 1

    # ── 7) 이용일수 · 급여액 ──────────────────────────────────────────────────
    freq = {k: np.zeros(n) for k in HOME_T}
    amt = {k: np.zeros(n) for k in HOME_T}
    inst_freq = np.zeros(n); inst_amt = np.zeros(n)
    for gr in range(1, 7):
        for k, b in HOME_T.items():
            m = bn & (grade == gr) & (yn[k] == 1)
            c = int(m.sum())
            if not c: continue
            spec = ben[gr]['types'][b]
            if b == '복지용구':                          # 원표 급여제공일수 0 (일수 개념 없음)
                freq[k][m] = 0
                amt[k][m] = np.rint(core.lognormal_mean(g, np.full(c, spec['per_cap']), SIGMA_AMT, c))
            else:
                d = _beta_days(g, spec['mean_days'], c)
                freq[k][m] = d
                amt[k][m] = np.rint(d * spec['unit'])
        mi = bn & (grade == gr) & inst
        c = int(mi.sum())
        if c:
            spec = ben[gr]['노인요양시설']
            d = _beta_days(g, spec['mean_days'], c)
            inst_freq[mi] = d
            inst_amt[mi] = np.rint(d * spec['unit'])

    # ── 8) 자격 → 본인일부부담금 ──────────────────────────────────────────────
    qn = np.array([QUAL_N[q] for q in ('기초', '의료급여', '감경', '일반')], float)
    qsh = qn / qn.sum()                                   # 기초·의료급여·감경·일반
    qual = np.full(n, '일반', dtype=object)
    if 'nhi_type' in df.columns:
        medi = df['nhi_type'].isin([7, 8]).values
    else:
        medi = np.zeros(n, bool)
    rank = np.ones(n)
    if bn.any():
        rank[bn] = pd.Series(rk[bn]).rank(pct=True).values
    if medi.any():
        qual[bn & medi] = '기초'                          # 기초생활 의료급여 수급자 ⇒ 본인부담 면제
        rest = bn & ~medi
        thr = qsh[2] / (qsh[2] + qsh[3])
        qual[rest & (rank <= thr)] = '감경'
    else:                                                 # B31/B24 미실행 시 소득순위 폴백
        c0, c1, c2 = qsh[0], qsh[0] + qsh[1], qsh[0] + qsh[1] + qsh[2]
        qual[bn & (rank <= c0)] = '기초'
        qual[bn & (rank > c0) & (rank <= c1)] = '의료급여'
        qual[bn & (rank > c1) & (rank <= c2)] = '감경'
    r_home = np.array([OWNPAY[q][0] for q in qual])
    r_inst = np.array([OWNPAY[q][1] for q in qual])

    home_cost = sum(amt[k] for k in HOME_T)
    hbn = np.rint(home_cost * r_home)
    ibn = np.rint(inst_amt * r_inst)

    # ── 9) 출력 ──────────────────────────────────────────────────────────────
    out = pd.DataFrame(index=df.index)
    nan = np.full(n, np.nan)

    def put_scope(col, vals, scope):
        v = np.asarray(vals, float).copy()
        v[~scope] = np.nan
        out[col] = v

    out['ltcare_yn'] = applied.astype(np.int8)
    out['ltcare_bn_yn'] = bn.astype(np.int8)
    out['ltcare_grade'] = grade
    out['ltcare_recog_score'] = score
    out['ltcare_caregiver_type'] = cgt
    out['ltcare_disease_num'] = dnum
    put_scope('ltcare_carecenter_yn', inst.astype(float), bn)
    out['ltcare_carehome_yn'] = nan                       # 규모 미달 (기대 1.2명)

    for k, pre in (('visit', 'visit'), ('bath', 'bath'), ('daynight', 'daynight'), ('extrah', 'extrah')):
        put_scope(f'ltcare_{pre}_yn', yn[k].astype(float), bn)
        put_scope(f'ltcare_{pre}_freq', freq[k], bn)
        put_scope(f'ltcare_{pre}_amt', amt[k], bn)
    for pre in ('nursing', 'short', 'cash'):              # 규모 미달
        out[f'ltcare_{pre}_yn'] = nan
        out[f'ltcare_{pre}_freq'] = nan
        out[f'ltcare_{pre}_amt'] = nan

    put_scope('ltcare_institute_yn', inst.astype(float), bn)
    put_scope('ltcare_institute_freq', inst_freq, bn)
    put_scope('ltcare_institute_amt', inst_amt, bn)
    put_scope('ltcare_hbn_fee', hbn, bn)
    put_scope('ltcare_ibn_fee', ibn, bn)

    for c in out.columns:
        if c.endswith('_amt') or c.endswith('_fee') or c.endswith('_freq') \
           or c.endswith('_yn') or c in ('ltcare_grade', 'ltcare_recog_score',
                                         'ltcare_caregiver_type', 'ltcare_disease_num'):
            out[c] = out[c].astype('Int64')

    ctx.setdefault('_b33', {})
    ctx['_b33'].update({'n_recipient': nb, 'n_applied': int(applied.sum()),
                        'target65': target65, 'income_src': inc_src, 'f_inst': f_inst})
    return out
