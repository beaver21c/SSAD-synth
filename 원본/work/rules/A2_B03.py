# -*- coding: utf-8 -*-
"""B03 개인 일차소득 (p_labinc … p_othinc) — 7개 변수  (A2 / order 4)

코드북상 "추출 정보 가공" 변수다. 추출대상 = 2022.11.1. 기준 일반가구원 **전원**이며
무정보 사례는 0원 처리(NaN 아님). 15세 미만은 0.

원칙 (AGENT_BRIEF ★S0 기준연도 정정):
  · **조건부 구조(보유율·구간 형태)** = S0 R01 <표 2-30>~<표 2-33> (2020년 소득연도)
  · **총량·수준(2022년)**            = S1/S2 원기관 집계(국세통계 2022년 귀속)
  두 축을 결합해, R01 의 분포 형태를 유지한 채 전국 총액을 2022년 값에 맞춘다.

1순위 소스 (S0, [1차확인] 2026-09-02, params/raw/R01_…최종보고서.pdf):
  <표 2-30> 개인근로소득 분포 p86  → 근로(일용 포함) 0원 이하 53.0%, 평균 1,499만원
  <표 2-31> 개인사업소득 분포 p87  → 0원 이하 80.8%, 평균 233만원
  <표 2-32> 개인부동산소득 분포 p88 → 0원 이하 97.3%, 평균 41만원
  <표 2-33> 개인일차소득 분포 p89  → 0원 이하 40.6%, 평균 1,789만원 (검증 기준)
  전사본: params/tab/S0_R01_T2-30~33_*.csv (+ .meta.json)
2순위 소스 (S2 국세통계 2022년 귀속, params/tab/B03_NTS_*.csv):
  4-2-3 성·연령별 근로소득 연말정산 인원·총급여 / 4-2-4 총급여 금액구간
  4-4-10 일용근로소득 금액구간 / 4-4-6·4-4-8 원천징수 사업·기타소득 총량
  4-4-7 연금계좌(사적연금) 연령별 / 4-4-12·4-4-13 이자·배당 분위별
  3-2-3 종합소득 사업·부동산임대 소득금액 (B07 경유)

생성 방식 (§6 B03):
  원천 DB 블록(B07 inc_*, B08 labinc_*, B09 dainc/binc/othinc_*, B10 fainc_sum,
  B11 pripen_inc)이 있으면 **그 값을 재조합**한다. 아직 없는 항목만 위 소스로 폴백
  생성하며, 폴백 시에도 B07 이 이미 부여한 소득 보유자는 반드시 포함한다(모순 방지).

재조합 규칙 (2026-09-02 재작업 — 자료원 간 이중계상 제거):
  · p_binc  = 종합소득세 신고자는 B07 inc_binc(결손은 음수 그대로), 미신고자만
              B09 binc_sum_inc + ybinc_sum_inc.  신고서의 사업소득금액은 원천징수 대상
              인적용역 사업소득을 이미 포함하므로 max·합산은 같은 소득을 두 번 센다.
  · p_othinc= 기타소득은 지급 단계에서 전액 원천징수되므로(소득세법 §127①6호)
              지급명세서(B09 othinc_sum_inc)가 그 사람의 기타소득 전부이고,
              B07 inc_other(종합과세분)는 그 부분집합이다 → B09 우선.
  · p_labinc= B08 총급여(labinc_sum_taxy − labinc_sum_taxn) 그대로.

헬퍼 산출: `_p_earned` = p_labinc + p_binc + p_dainc  (B06·B13·B16·B24 사용)
"""
from __future__ import annotations
import os, re, sys
import numpy as np, pandas as pd
from scipy.stats import norm

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

TAB = 'params/tab'
RAW = 'params/raw'
BANDS = ['15-29', '30-39', '40-49', '50-59', '60-69', '70+']
MAN = 10_000.0
MIN_AGE = 15                      # 15세 미만은 전 항목 0 (코드북 "추출 정보 가공")

# R01 <표 2-30>~<표 2-33> 구간 상한 (만원). 마지막은 개방구간.
R01_EDGES = [0, 100, 300, 500, 1000, 2000, 3000, 4000, 6000, 8000, 10000, None]
R01_BANDS = ['~100만원', '~300만원', '~500만원', '~1000만원', '~2000만원', '~3000만원',
             '~4000만원', '~6000만원', '~8000만원', '~10000만원', '10000만원 초과']

# 상관 파라미터 [가정 A2-B03-1] — 저소득 잠재변수와 소득 보유·크기의 순위상관
RHO_HOLD = 0.55
RHO_AMT = 0.70
RHO_FIN = 0.80                    # 금융소득은 자산과 함께 상위에 집중


def _T(name):
    return pd.read_csv(os.path.join(TAB, name + '.csv'))


_CANON = ['ZERO', '100', '300', '500', '1000', '2000', '3000', '4000', '6000', '8000',
          '10000', 'TOP']


def _norm(k):
    """'~1000만원/년 이하' → '1000', '0원 이하' → 'ZERO', '10000만원/년 초과' → 'TOP'."""
    k = str(k).replace(' ', '').replace('/년', '')
    if k.startswith('0원'):
        return 'ZERO'
    if '초과' in k:
        return 'TOP'
    m = re.search(r'(\d+)만원', k)
    return m.group(1) if m else k


def _r01(name):
    """R01 <표 2-3x> 전사본 → {'zero': 0원 이하 %, 'shares': 11구간 %, 'mean': 만원}.
    params/tab 의 전사본은 (metric,band,value) 형식과 (구분,행정데이터_A,…) 형식이
    공존하므로 둘 다 읽는다 — 두 형식의 수치는 동일함을 확인했다."""
    d = _T(name)
    if 'metric' in d.columns:
        lab = list(d.loc[d.metric == 'share', 'band'])
        val = list(d.loc[d.metric == 'share', 'value'].astype(float))
        mean = float(d.loc[d.metric == 'mean', 'value'].iloc[0])
    else:
        key = d.columns[0]
        vcol = '행정데이터_A' if '행정데이터_A' in d.columns else d.columns[1]
        dd = d.set_index(key)[vcol]
        lab = [k for k in dd.index if _norm(k) in _CANON]
        val = [float(dd[k]) for k in lab]
        mean = float(dd[[k for k in dd.index if str(k).strip() == '평균'][0]])
    mp = {}
    for k, v in zip(lab, val):
        mp[_norm(k)] = v
    zero = mp['ZERO']
    shares = np.array([mp[c] for c in _CANON[1:]], float)
    return {'zero': zero, 'shares': shares, 'mean': mean}


def _band(age):
    a = np.asarray(age)
    out = np.full(len(a), '', dtype=object)
    out[(a >= 15) & (a < 30)] = '15-29'
    out[(a >= 30) & (a < 40)] = '30-39'
    out[(a >= 40) & (a < 50)] = '40-49'
    out[(a >= 50) & (a < 60)] = '50-59'
    out[(a >= 60) & (a < 70)] = '60-69'
    out[a >= 70] = '70+'
    return out


def _copula(g, r, rho):
    r = np.clip(np.asarray(r, float), 1e-6, 1 - 1e-6)
    return norm.cdf(rho * norm.ppf(r) + np.sqrt(max(1e-9, 1 - rho ** 2)) * g.standard_normal(len(r)))


def _rank01(x):
    x = np.asarray(x, float)
    if len(x) == 0:
        return x
    return (np.argsort(np.argsort(x)) + 0.5) / len(x)


def _quota_w(order, w, frac):
    """order(우선순위)를 따라 누적 가중치가 전체의 frac 이 되는 지점까지 선택."""
    if len(order) == 0 or frac <= 0:
        return np.array([], dtype=int)
    cw = np.cumsum(w[order]); tgt = frac * cw[-1]
    k = int(np.searchsorted(cw, tgt))
    if not (k > 0 and abs(cw[k - 1] - tgt) <= abs((cw[k] if k < len(cw) else cw[-1]) - tgt)):
        k += 1
    return order[:min(max(k, 0), len(order))]


def _hist_draw(g, edges, weights, rankq, alpha=1.6):
    """구간 히스토그램에서 rankq(0~1 균등) 위치에 대응하는 금액을 뽑는다.
    core.hist_loguniform 로 형태를 생성한 뒤 rankq 순서에 정렬해 소득 잠재변수와 연결."""
    n = len(rankq)
    if n == 0:
        return np.zeros(0)
    v = np.sort(core.hist_loguniform(g, edges, weights, n, pareto_alpha=alpha))
    return v[np.clip((rankq * n).astype(int), 0, n - 1)]


def _scale_to_mean(x, w, target_mean, lo=0.2, hi=5.0):
    """가중 평균이 target_mean 이 되도록 배율 조정 (배율은 절단)."""
    if len(x) == 0:
        return x
    cur = float((x * w).sum() / max(w.sum(), 1e-9))
    if cur <= 0:
        return x
    return x * float(np.clip(target_mean / cur, lo, hi))


def _col(df, *names):
    """상위 블록이 만든 컬럼 값(원). 없으면 None."""
    vals = []
    for nm in names:
        if nm not in df.columns:
            return None
        vals.append(pd.to_numeric(df[nm], errors='coerce').fillna(0.0).values)
    return vals


def generate(df, params, ctx):
    g = core.rng('B03')
    n = len(df)
    age = df['age'].values.astype(int)
    sex = df['gender'].values.astype(int)
    band = _band(age)
    ui = df['_u_income'].values
    ue = df['_u_emp'].values if '_u_emp' in df.columns else g.random(n)
    wt = (df['indwgt'].values.astype(float) if 'indwgt' in df.columns else np.ones(n))
    adult = age >= MIN_AGE
    W15 = float(wt[adult].sum())                      # 15세 이상 가중 인구
    WALL = float(wt.sum())

    lab = np.zeros(n); dai = np.zeros(n); biz = np.zeros(n)
    fin = np.zeros(n); ren = np.zeros(n); pri = np.zeros(n); oth = np.zeros(n)
    src = {}                                          # 항목별 출처 기록(진단용)

    t423 = _T('B03_NTS_4-2-3_근로소득연말정산_성연령_2022')
    t424 = _T('B03_NTS_4-2-4_총급여_금액구간_2022')
    t4410 = _T('B03_NTS_4-4-10_일용근로소득_금액구간_2022')
    t447 = _T('B03_NTS_4-4-7_사적연금_연금계좌_연령별_2022')
    t446 = _T('B03_NTS_4-4-6_4-4-8_원천징수_사업_기타소득_총량_2022')
    r30 = _r01('S0_R01_T2-30_개인근로소득분포')
    r31 = _r01('S0_R01_T2-31_개인사업소득분포')
    r32 = _r01('S0_R01_T2-32_개인부동산소득분포')

    # ── 1) 근로소득 p_labinc (= 총급여) ────────────────────────────────────
    b08 = _col(df, 'labinc_sum_taxy', 'labinc_sum_taxn')
    if b08 is not None:
        lab = np.maximum(b08[0] - b08[1], 0.0)
        src['p_labinc'] = 'B08 labinc_sum_taxy − labinc_sum_taxn'
    else:
        src['p_labinc'] = 'S2 NTS 4-2-3(성·연령 보유율·평균) + 4-2-4(금액구간) 폴백'
        seed = _col(df, 'inc_labinc_sum')             # B07 종합소득 신고 근로소득
        seed = seed[0] if seed is not None else np.zeros(n)
        e424 = [0, 1000, 1500, 2000, 3000, 4000, 4500, 5000, 6000, 8000, 10000,
                20000, 30000, 50000, 100000, None]
        w424 = t424.sort_values('ord').n.values.astype(float)
        tt = t423.set_index(['sex', 'band'])
        for s in (1, 2):
            for b in BANDS:
                if (s, b) not in tt.index:
                    continue
                m = np.flatnonzero(adult & (sex == s) & (band == b))
                if len(m) == 0:
                    continue
                rate = float(tt.loc[(s, b), 'rate_holder'])
                sc = _copula(g, _rank01(0.6 * ui[m] + 0.4 * (1 - ue[m])), RHO_HOLD)
                # B07 종합소득세 근로소득 신고자를 우선순위 맨 앞에 배치(모순 방지)하고
                # 나머지를 소득성향 순으로 채워 보유율 총량을 보존한다.
                sc = sc + 2.0 * (seed[m] > 0)
                pick = _quota_w(m[np.argsort(-sc)], wt, min(1.0, rate))
                if len(pick) == 0:
                    continue
                q = _copula(g, _rank01(ui[pick]), RHO_AMT)
                v = _hist_draw(g, e424, w424, q, alpha=1.7) * MAN
                fix = seed[pick] > 0
                v = np.where(fix, seed[pick], v)          # B07 값은 그대로 고정
                # 셀 총량(= 4-2-3 성·연령 평균×인원)을 맞춘다. 우선 비(非)B07 보유자를
                # 조정하고, 그것만으로 부족하면 B07 값도 0.5~1.5배 범위에서 재조정한다
                # (B08 이 구현되면 B07·B03 모두 B08 총급여를 쓰므로 이 보정은 사라진다).
                T = float(tt.loc[(s, b), 'mean_taxable_manwon']) * MAN * wt[pick].sum()
                ws = wt[pick]
                S = float((v[fix] * ws[fix]).sum())
                B = float((v[~fix] * ws[~fix]).sum())
                f = float(np.clip((T - S) / B, 0.2, 5.0)) if B > 0 else 0.0
                if B > 0:
                    v[~fix] = v[~fix] * f
                    B = float((v[~fix] * ws[~fix]).sum())
                if S > 0 and abs(S + B - T) > 0.05 * T:
                    v[fix] = v[fix] * float(np.clip((T - B) / S, 0.5, 1.5))
                lab[pick] = v

    # ── 2) 일용소득 p_dainc ────────────────────────────────────────────────
    b09d = _col(df, 'dainc_sum')
    if b09d is not None:
        dai = b09d[0]
        src['p_dainc'] = 'B09 dainc_sum'
    else:
        src['p_dainc'] = 'S2 NTS 4-4-10(인원·금액구간) + S0 R01 표2-30 합집합 47.0% 제약 폴백'
        n_dai = float(t4410.n.sum()); amt_dai = float(t4410.amt_mil.sum())
        pop = float(pd.read_csv(os.path.join(RAW, 'POPUL_MOIS01_2022_11_sigungu_age1_sex.csv')
                                ).query("level=='sigungu' and sex in ['male','female']")['pop'].sum())
        n_lab = float(t423.n.sum())
        union = (100.0 - r30['zero']) / 100.0 * pop    # R01 표2-30 근로(일용 포함) 보유자
        # 근로(연말정산)와 일용의 합집합이 R01 표2-30 의 근로소득 보유율과 일치하도록
        # 중복(양쪽 모두 보유) 규모를 역산한다.
        overlap = float(np.clip(n_lab + n_dai - union, 0.0, min(n_lab, n_dai)))
        p_in = overlap / n_lab                        # 근로소득자 중 일용 병행 비율
        w_lab = float(wt[(lab > 0)].sum())
        p_out = (n_dai - overlap) / max(W15 - w_lab, 1.0)   # 비보유 성인 실제 규모 기준
        e10 = [0, 100, 300, 600, 900, 1000, 1200, 1500, 1800, 2000, 2100, 2500,
               3000, 4000, 5000, None]
        w10 = t4410.sort_values('ord').n.values.astype(float)
        mean_dai = amt_dai * 100.0 / n_dai
        has_lab = lab > 0
        for grp, rate in ((adult & has_lab, p_in), (adult & ~has_lab, p_out)):
            m = np.flatnonzero(grp)
            if len(m) == 0:
                continue
            sc = _copula(g, _rank01(0.7 * (1 - ui[m]) + 0.3 * (1 - ue[m])), RHO_HOLD)
            pick = _quota_w(m[np.argsort(-sc)], wt, min(1.0, rate))
            if len(pick) == 0:
                continue
            q = _copula(g, _rank01(ui[pick]), 0.45)
            v = _hist_draw(g, e10, w10, q, alpha=1.9)
            dai[pick] = _scale_to_mean(v, wt[pick], mean_dai) * MAN

    # ── 3) 사업소득 p_binc ────────────────────────────────────────────────
    # 종합소득세 확정신고서의 **사업소득금액**(B07 inc_binc)은 그 사람의 사업소득 전부
    # (원천징수 대상 인적용역 사업소득 포함)를 필요경비 공제 후로 적은 값이다. 따라서
    # 신고자에게는 B07 값이 유일한 정답이고, 원천징수 지급명세서(B09)를 더하거나 max 를
    # 취하면 같은 소득을 두 번 세게 된다(이전 판 +24.6% 과대의 원인).
    #   · 신고자(사업소득금액 기재)          → inc_binc  (결손이면 음수 그대로: R01 표2-31 주1)
    #   · 미신고자(지급명세서만 있는 사람)    → binc_sum_inc + ybinc_sum_inc
    b07b = _col(df, 'inc_binc')
    b09b = _col(df, 'binc_sum_inc', 'ybinc_sum_inc')
    seed_b = np.zeros(n)
    b09v = (b09b[0] + b09b[1]) if b09b is not None else np.zeros(n)
    if b07b is not None:
        rep = df['inc_binc'].notna().to_numpy() & (b07b[0] != 0.0)
        seed_b = np.where(rep, b07b[0], b09v)
        src['p_binc'] = 'B07 inc_binc (신고자) / B09 binc_sum_inc+ybinc_sum_inc (미신고자)'
    elif b09b is not None:
        seed_b = b09v
        src['p_binc'] = 'B09 binc_sum_inc + ybinc_sum_inc'
    else:
        src['p_binc'] = 'S0 R01 표2-31(보유율·구간) + S2 NTS 3-2-3(2022 총액) 폴백'
    biz = seed_b.copy()
    hold_rate_b = (100.0 - r31['zero']) / 100.0                  # 19.2%
    sh_b = r31['shares']
    tgt_amt_b = 140158005.0 * 1e6                     # NTS 3-2-3 사업소득금액(원)
    have = biz > 0
    need = hold_rate_b * WALL - float(wt[have].sum())
    if need > 0:
        m = np.flatnonzero(adult & ~have)
        sc = _copula(g, _rank01(0.75 * ui[m] + 0.25 * (1 - ue[m])), RHO_HOLD)
        pick = _quota_w(m[np.argsort(-sc)], wt, min(1.0, need / max(wt[m].sum(), 1e-9)))
        if len(pick):
            q = _copula(g, _rank01(ui[pick]), RHO_AMT)
            v = _hist_draw(g, R01_EDGES, sh_b, q, alpha=1.6)
            rest = max(tgt_amt_b - float((np.maximum(biz, 0) * wt).sum()), 0.0)
            biz[pick] = _scale_to_mean(v, wt[pick], rest / max(wt[pick].sum(), 1e-9) / MAN) * MAN

    # ── 4) 임대소득 p_reinc ───────────────────────────────────────────────
    b07r = _col(df, 'inc_reinc', 'inc_hou', 'inc_sehou')
    if b07r is not None:
        ren = b07r[0] + b07r[1] + b07r[2]
        src['p_reinc'] = 'B07 inc_reinc + inc_hou + inc_sehou'
    else:
        src['p_reinc'] = 'S0 R01 표2-32(보유율·구간) + S2 NTS 3-2-3·3-2-3-2(2022 총액) 폴백'
        hold_r = (100.0 - r32['zero']) / 100.0                   # 2.7%
        sh_r = r32['shares']
        m = np.flatnonzero(adult)
        sc = _copula(g, _rank01(ui[m]), 0.8)
        pick = _quota_w(m[np.argsort(-sc)], wt, min(1.0, hold_r * WALL / max(wt[m].sum(), 1e-9)))
        if len(pick):
            q = _copula(g, _rank01(ui[pick]), RHO_AMT)
            v = _hist_draw(g, R01_EDGES, np.maximum(sh_r, 1e-6), q, alpha=1.6)
            tgt = (22038964.0 + 773863.0) * 1e6       # 종합과세 + 분리과세 주택임대
            ren[pick] = _scale_to_mean(v, wt[pick], tgt / max(wt[pick].sum(), 1e-9) / MAN) * MAN

    # ── 5) 기타소득 p_othinc ──────────────────────────────────────────────
    # 기타소득은 지급 단계에서 전액 원천징수되고(소득세법 §127①6호) 그중 기타소득금액
    # 연 300만원 초과분만 종합과세로 넘어온다(§14③8호). 즉 B07 inc_other 는 B09
    # othinc_sum_inc 의 **부분집합**이므로 둘을 더하거나 max 를 취하면 이중계상이 된다.
    #   · 지급명세서 보유자 → othinc_sum_inc (원천 자료)
    #   · 지급명세서 없는 종합과세 신고자 → inc_other
    b09o = _col(df, 'othinc_sum_inc')
    seed_o = np.zeros(n)
    b07o = _col(df, 'inc_other')
    if b07o is not None:
        seed_o = b07o[0]
    if b09o is not None:
        # 기타소득은 지급 단계에서 전액 원천징수되므로(소득세법 §127①6호) 지급명세서(B09)가
        # 그 사람의 기타소득 전부를 담는다. B07 inc_other(종합과세 기타소득금액)는 그중
        # '기타소득금액 300만원 초과' 부분이 넘어온 **부분집합**이다(§14③8호).
        # 따라서 지급명세서가 있으면 B09 값을 쓰고, 없는 신고자만 B07 값을 쓴다.
        oth = np.where(b09o[0] > 0, b09o[0], seed_o)
        src['p_othinc'] = 'B09 othinc_sum_inc (지급명세서 우선) / B07 inc_other (명세서 없는 신고자)'
    else:
        src['p_othinc'] = 'S2 NTS 4-4-8 원천징수 기타소득(인원·소득금액) 폴백 + B07 inc_other'
        oth = seed_o.copy()
        row = t446[t446.item == '기타소득(원천징수)'].iloc[0]
        n_o = float(row.n); amt_o = float(row.income_mil)
        have = oth > 0
        need = n_o - float(wt[have].sum())
        m = np.flatnonzero(adult & ~have)
        if need > 0 and len(m):
            sc = _copula(g, _rank01(0.5 * ui[m] + 0.5 * g.random(len(m))), 0.35)
            pick = _quota_w(m[np.argsort(-sc)], wt, min(1.0, need / max(wt[m].sum(), 1e-9)))
            if len(pick):
                mu = amt_o * 100.0 / n_o              # 보유자 평균 224.7만원
                v = core.lognormal_mean(g, np.full(len(pick), mu), 1.35, len(pick))
                rest = max(amt_o * 1e6 - float((oth * wt).sum()), 0.0)
                oth[pick] = _scale_to_mean(v, wt[pick],
                                           rest / max(wt[pick].sum(), 1e-9) / MAN) * MAN

    # ── 6) 금융소득 p_fininc ──────────────────────────────────────────────
    b10 = _col(df, 'fainc_sum')
    if b10 is not None:
        fin = b10[0]
        src['p_fininc'] = 'B10 fainc_sum'
    else:
        src['p_fininc'] = ('S2 NTS 4-4-12·4-4-13(이자·배당 분위별 총액) + '
                           'S0 R02 표2-13(가구 금융소득 보유율) 폴백')
        d12 = pd.read_csv(os.path.join(RAW, 'NTS_4-4-12_이자소득분위별신고.csv'))
        d13 = pd.read_csv(os.path.join(RAW, 'NTS_4-4-13_배당소득분위별신고.csv'))
        def dec(d):
            q = d[d.ROW_L2 != '소계'].sort_values('ROW_ORD')
            a = q[q.COL_L2 == '소득금액'].VALUE.values.astype(float)
            return a
        a12, a13 = dec(d12), dec(d13)
        share = (a12 / a12.sum())                     # 이자소득 분위 구성 (상위10%…)
        tgt_fin = (float(a12.sum()) + float(a13.sum())) * 1e6
        hold_r = 0.62                                 # [가정] 성인 보유율
        m = np.flatnonzero(age >= 19)
        sc = _copula(g, _rank01(ui[m]), RHO_FIN)
        pick = _quota_w(m[np.argsort(-sc)], wt, hold_r)
        if len(pick):
            q = 1.0 - _rank01(ui[pick])               # 0 = 상위분위
            dcut = np.clip((q * 10).astype(int), 0, 9)
            nh = float(wt[pick].sum())                # 보유자 가중 인원
            mu_d = share * (tgt_fin / MAN) / max(0.1 * nh, 1e-9)   # 분위별 1인 평균(만원)
            v = core.lognormal_mean(g, mu_d[dcut], 0.8, len(pick))
            fin[pick] = _scale_to_mean(v, wt[pick], tgt_fin / nh / MAN) * MAN

    # ── 7) 사적연금소득 p_pripeninc ───────────────────────────────────────
    b11 = _col(df, 'pripen_inc')
    if b11 is not None:
        pri = b11[0]
        src['p_pripeninc'] = 'B11 pripen_inc'
    else:
        src['p_pripeninc'] = 'S2 NTS 4-4-7 연금계좌 원천징수(연령별 인원·지급액) 폴백'
        BMAP = {'30세 미만': ['15-29'], '30세 이상': ['30-39'], '40세 이상': ['40-49'],
                '50세 이상': ['50-59'], '60세 이상': ['60-69', '70+']}
        pop = pd.read_csv(os.path.join(RAW, 'POPUL_MOIS01_2022_11_sigungu_age1_sex.csv'))
        pop = pop[(pop.level == 'sigungu') & (pop.sex.isin(['male', 'female']))]
        pb = _band(pop.age.values)
        for _, r in t447.iterrows():
            bs = BMAP.get(r.age_band)
            if not bs:
                continue
            denom = float(pop['pop'].values[np.isin(pb, bs)].sum())
            if denom <= 0:
                continue
            m = np.flatnonzero(np.isin(band, bs))
            if len(m) == 0:
                continue
            sc = _copula(g, _rank01(ui[m]), 0.6)
            pick = _quota_w(m[np.argsort(-sc)], wt, min(1.0, float(r.n) / denom))
            if len(pick) == 0:
                continue
            mu = float(r.amt_mil) * 100.0 / float(r.n)
            v = core.lognormal_mean(g, np.full(len(pick), mu), 0.9, len(pick))
            pri[pick] = _scale_to_mean(v, wt[pick], mu) * MAN

    # ── 8) 마무리: 15세 미만 0, 무정보 0, 천원 라운딩 ───────────────────────
    def fin_col(x):
        x = np.nan_to_num(np.asarray(x, float), nan=0.0)
        x = np.where(adult, x, 0.0)
        return np.round(x / 1000.0) * 1000.0

    out = pd.DataFrame(index=df.index)
    out['p_labinc'] = fin_col(lab)
    out['p_dainc'] = fin_col(dai)
    out['p_binc'] = fin_col(biz)
    out['p_fininc'] = fin_col(fin)
    out['p_reinc'] = fin_col(ren)
    out['p_pripeninc'] = fin_col(pri)
    out['p_othinc'] = fin_col(oth)
    # ── 9) §7 R16: 직장피부양자(nhi_type=6)는 무소득 ───────────────────────
    #  건강보험 피부양자는 자격요건상 소득이 없는 자다. B31(A5, order3)이 NHIS
    #  적용인구 통계(Ⅰ-3-2)에 맞춰 배정한 뒤 헬퍼 `_no_p_minc==1` 로 넘겨주며,
    #  B31 docstring 대로 **B03 이** 그 개인의 일차소득 7성분을 0 으로 만든다.
    #
    #  주의: 단순히 0 으로 지우면 전국 일차소득 총액이 17.8% 사라져
    #  targets/A2_B04.yaml 의 균등화 가구일차소득 중윗값·지니·상대빈곤율이
    #  전부 무너진다(이 지표들은 가구합 h_minc 기반). 그래서 지운 금액을
    #  **같은 가구의 직장가입자(nhi_type==5)** 에게 성분별로 이관한다.
    #  → 가구 일차소득·전국 총액 보존, §7 R16 과 R22 를 동시에 만족.
    #  (건강보험은 피부양자의 소득을 가입자 세대 단위로 귀속시키므로 정의상으로도 일관)
    # [T3] 소득 이관 중지 — p_* 는 본인의 원천 DB 값을 그대로 재조합한다(코드북 '추출 정보 가공').
    #      피부양자 자격과 소득의 정합은 B31 의 배정 단계와 §7 R16(개정)이 담당한다.
    if False and '_no_p_minc' in df.columns:
        COMP = ['p_labinc', 'p_dainc', 'p_binc', 'p_fininc',
                'p_reinc', 'p_pripeninc', 'p_othinc']
        PRIM = ['p_labinc', 'p_dainc', 'p_binc', 'p_reinc', 'p_othinc']
        hidv = df['hid'].to_numpy()
        dep = df['_no_p_minc'].fillna(0).to_numpy() == 1
        nd = (~dep) & adult                                # 비피부양 성인 = 수취 후보
        nhi5 = ((df['nhi_type'].fillna(0).to_numpy() == 5) & adult
                if 'nhi_type' in df.columns else nd)
        gsum = lambda v: pd.Series(v).groupby(hidv).transform('sum').to_numpy()
        gmax = lambda v: pd.Series(v).groupby(hidv).transform('max').to_numpy()
        # 이관 전 일차소득 보유 여부 (수취 우선순위 계산의 기준으로 고정)
        earned0 = np.sum([out[c].to_numpy(float) for c in PRIM], axis=0) <= 0
        idle = nd & earned0                                # 일차소득이 전혀 없는 비피부양 성인
        got = np.zeros(n, dtype=bool)                      # 이번 이관에서 이미 받은 사람
        moved, dropped = 0.0, 0.0
        for c in COMP:
            v = out[c].to_numpy(float).copy()
            take = np.where(dep, v, 0.0)
            pot = gsum(take)
            if not (pot > 0).any():
                continue
            # 배분 원칙: **개인 단위 성분 보유율(S0 표2-30·2-33)의 훼손을 최소화**한다.
            #   피부양자에게서 거둔 금액은 같은 가구에서 **그 성분을 갖고 있지 않은
            #   비피부양 성인 전원**에게 균등 배분한다 → 가구 일차소득 총액을 보존하면서
            #   성분 보유자 수 감소를 최소화한다. 그런 사람이 없으면 직장가입자(5),
            #   그마저 없으면 아무 비피부양 성인에게 기존 보유액 비례로 넘긴다.
            tiers = [nd & (v <= 0), nhi5, nd]
            sel = np.zeros(n, dtype=bool)
            done = np.zeros(n, dtype=bool)
            for t in tiers:
                has = gmax(t.astype(np.int8)) == 1
                use = has & ~done
                sel |= (t & use)
                done |= use
            base = np.where(sel, v, 0.0)
            bsum = gsum(base)
            rcnt = gsum(sel.astype(float))
            share = np.zeros(n)
            m1 = sel & (bsum > 0)
            share[m1] = base[m1] / bsum[m1]                # 기존 보유액 비례
            m2 = sel & (bsum <= 0) & (rcnt > 0)
            share[m2] = 1.0 / rcnt[m2]                     # 전원 0 이면 균등 분배
            v = np.maximum(v - take + pot * share, 0.0)
            out[c] = np.round(v / 1000.0) * 1000.0
            got |= (sel & (pot > 0))
            moved += float(take.sum())
            dropped += float(take[rcnt <= 0].sum())
        src['_R16'] = ('피부양자 %d명 일차소득 %.0f원 → 가구 내 비피부양 성인 이관 (미이관 %.0f원)'
                       % (int(dep.sum()), moved, dropped))

    # 계약 헬퍼: 개인 근로+사업+일용 소득 합 (B06·B13·B16·B24 사용)
    out['_p_earned'] = out['p_labinc'] + out['p_binc'] + out['p_dainc']
    globals()['LAST_SRC'] = src
    return out
