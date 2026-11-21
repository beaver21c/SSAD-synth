# -*- coding: utf-8 -*-
"""국세청 국세통계(TASIS, 2023년 발행 = 2022년 귀속) tidy CSV 로더·파생표 (A2 소득·국세 블록 공용).

원자료는 registry/acq_tax.md 의 규약대로 params/raw/NTS_{표번호}_{설명}.csv 에 전사되어 있다.
여기서는 **원표 수치를 그대로 읽어** 블록이 쓰는 파생표(보유율·금액구간·유효세율)만 만든다.
숫자를 새로 만들지 않는다. 모든 반환값의 출처는 함수 docstring 의 표번호로 추적된다.
"""
from __future__ import annotations
import os, glob
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'params', 'raw')

# NTS 표의 연령 라벨 → (하한, 상한)
AGE_LABEL = {'30세 미만': (0, 29), '30세 이상': (30, 39), '40세 이상': (40, 49),
             '50세 이상': (50, 59), '60세 이상': (60, 69), '70세 이상': (70, 200)}


def nts(stt_no: str) -> pd.DataFrame:
    """params/raw/NTS_{표번호}_*.csv 로드 (VALUE 는 float)."""
    hits = sorted(glob.glob(os.path.join(RAW, f'NTS_{stt_no}_*.csv')))
    if not hits:
        raise FileNotFoundError(f'NTS 표 {stt_no} 전사본 없음')
    d = pd.read_csv(hits[0])
    d['VALUE'] = pd.to_numeric(d['VALUE'], errors='coerce')
    for c in d.columns:
        if c.startswith(('ROW_', 'COL_')):
            d[c] = d[c].astype('object')
    return d


# ── 인구 (분모) ──────────────────────────────────────────────────────────────
def pop_sex_age(band_edges=(30, 40, 50, 60, 70)):
    """주민등록 인구통계 2022.11 (params/raw/POPUL_MOIS01_*.csv) → 성×연령대 인구.
    반환 DataFrame index=['남성','여성'], columns=밴드 라벨."""
    p = pd.read_csv(os.path.join(RAW, 'POPUL_MOIS01_2022_11_sigungu_age1_sex.csv'))
    p = p[(p.level == 'sigungu') & (p.sex.isin(['male', 'female']))].copy()
    p['age'] = p['age'].astype(int)
    labs = band_labels(band_edges)
    p['b'] = age_band(p['age'].values, band_edges)
    g = p.groupby(['sex', 'b'])['pop'].sum().unstack().reindex(columns=labs).fillna(0.0)
    g.index = ['여성' if i == 'female' else '남성' for i in g.index]
    return g.loc[['남성', '여성']]


def band_labels(edges=(30, 40, 50, 60, 70)):
    labs = ['30세 미만'] if edges[0] == 30 else [f'{edges[0]}세 미만']
    for e in edges:
        labs.append(f'{e}세 이상')
    return labs[:1] + labs[1:]


def age_band(age, edges=(30, 40, 50, 60, 70)):
    age = np.asarray(age)
    labs = band_labels(edges)
    conds = [age < edges[0]] + [age < e for e in edges[1:]]
    return np.select(conds, labs[:-1], labs[-1])


# ── 성×연령 결합표 복원 (주변합만 있는 표) ────────────────────────────────────
def joint_from_margins(sex_n: dict, age_n: dict, pop: pd.DataFrame, max_iter=4):
    """성 주변합·연령 주변합만 있는 NTS 표에서 성×연령 셀 인원을 복원.
    seed = 주민등록 인구(성×연령), margins = (성, 연령). IPF 반복 max_iter.
    ※ §4.1 의 'IPF 1회' 원칙은 B02 가중치 보정에 대한 규정이며, 여기는 원표 셀 복원이다."""
    cols = [c for c in pop.columns if c in age_n]
    seed = pop.loc[['남성', '여성'], cols].values.astype(float)
    tr = np.array([sex_n['남성'], sex_n['여성']], float)
    tc = np.array([age_n[c] for c in cols], float)
    # 두 주변합의 총계를 일치시킨다(원표의 '기타'(성·연령 미상) 제외분 차이 보정)
    tc = tc * (tr.sum() / tc.sum())
    t = seed.copy()
    for _ in range(max_iter):
        t *= (tr / t.sum(axis=1))[:, None]
        t *= (tc / t.sum(axis=0))[None, :]
    return pd.DataFrame(t, index=['남성', '여성'], columns=cols)


def rate_sex_age(sex_n, age_n, pop, cap=0.98):
    """성×연령 보유율 = 복원 인원 / 인구 (상한 cap)."""
    j = joint_from_margins(sex_n, age_n, pop)
    r = (j / pop.loc[j.index, j.columns]).clip(upper=cap)
    return r


# ── 금액 구간 → 개인 금액 추출 ───────────────────────────────────────────────
def band_table(lo, hi, n, amt):
    """구간표 정리. lo/hi 는 원 단위(hi=None 이면 개방구간), n=인원, amt=금액(원).
    반환 dict(lo, hi, w(구성비), mean(구간평균, 원))."""
    lo = np.asarray(lo, float)
    hi = np.array([np.inf if h is None else float(h) for h in hi])
    n = np.asarray(n, float); amt = np.asarray(amt, float)
    m = np.where(n > 0, amt / np.maximum(n, 1), (lo + np.where(np.isfinite(hi), hi, lo * 2)) / 2)
    return {'lo': lo, 'hi': hi, 'w': n / n.sum(), 'mean': m, 'n': n, 'amt': amt}


def draw_by_rank(g, rank, bt, alpha=1.3):
    """구간 히스토그램을 **순위 보존**으로 추출한다 (rank∈[0,1) 오름차순 = 금액 오름차순).
    구간 내부는 Beta(alpha, alpha(1-t)/t) 로 구간평균을 정확히 재현.
    최상단 개방구간은 파레토(구간평균 일치 α)."""
    rank = np.clip(np.asarray(rank, float), 0.0, 1.0 - 1e-12)
    cw = np.cumsum(bt['w'])
    k = np.searchsorted(cw, rank, side='right')
    k = np.clip(k, 0, len(bt['w']) - 1)
    lo0 = np.concatenate([[0.0], cw[:-1]])
    inner = (rank - lo0[k]) / np.maximum(bt['w'][k], 1e-12)      # 구간 내 상대순위
    inner = np.clip(inner, 1e-9, 1 - 1e-9)
    out = np.empty(len(rank))
    for i in range(len(bt['w'])):
        m = (k == i)
        c = int(m.sum())
        if c == 0:
            continue
        lo, hi, mu = bt['lo'][i], bt['hi'][i], bt['mean'][i]
        if not np.isfinite(hi):
            a = max(mu / max(mu - lo, 1.0), 1.05)               # 파레토: 평균 일치
            out[m] = lo * (1.0 - inner[m] * (1 - 1e-9)) ** (-1.0 / a)
        else:
            t = np.clip((mu - lo) / max(hi - lo, 1.0), 0.02, 0.98)
            b = alpha * (1 - t) / t
            from scipy.stats import beta as _beta
            out[m] = lo + (hi - lo) * _beta.ppf(inner[m], alpha, b)
    return out


def interp_rate(x, bt, rate):
    """구간별 비율(유효세율·보유율 등)을 구간평균 기준 로그선형 보간."""
    xs = np.log(np.maximum(bt['mean'], 1.0))
    ys = np.asarray(rate, float)
    o = np.argsort(xs)
    return np.interp(np.log(np.maximum(np.asarray(x, float), 1.0)), xs[o], ys[o])


# ── 개인 잠재변수 기반 상관 점수 ──────────────────────────────────────────────
def score(g, u, rho, n=None):
    """z = rho·Φ⁻¹(u) + √(1-rho²)·Φ⁻¹(v) → 균등순위 반환. rho<0 이면 역상관."""
    from scipy.stats import norm
    u = np.asarray(u, float)
    n = len(u) if n is None else n
    z = rho * norm.ppf(np.clip(u, 1e-9, 1 - 1e-9)) + np.sqrt(1 - rho ** 2) * norm.ppf(
        np.clip(g.random(n), 1e-9, 1 - 1e-9))
    return norm.cdf(z)


def pop_sex_age1():
    """주민등록 인구통계 2022.11 → 성×1세 인구 (index=['남성','여성'], columns=0..100)."""
    p = pd.read_csv(os.path.join(RAW, 'POPUL_MOIS01_2022_11_sigungu_age1_sex.csv'))
    p = p[(p.level == 'sigungu') & (p.sex.isin(['male', 'female']))].copy()
    p['age'] = p['age'].astype(int)
    g = p.groupby(['sex', 'age'])['pop'].sum().unstack().fillna(0.0)
    g.index = ['여성' if i == 'female' else '남성' for i in g.index]
    return g.loc[['남성', '여성']]


def pop_weight_mean(wfun, band_edges=(30, 40, 50, 60, 70)):
    """성×연령대별 인구가중 평균 w(age). 구간 내부 연령가중을 원표 보유율에 맞춰
    정규화할 때 쓴다 (표본이 아니라 **모집단** 연령분포로 정규화해야 편의가 없다)."""
    p1 = pop_sex_age1()
    ages = np.array(p1.columns, int)
    w = wfun(ages)
    b = age_band(ages, band_edges)
    out = {}
    for s in p1.index:
        n = p1.loc[s].values
        for lab in band_labels(band_edges):
            m = (b == lab)
            out[(s, lab)] = float((w[m] * n[m]).sum() / max(n[m].sum(), 1))
    return out


def match_band_means(x, w, bt, iters=3):
    """구간별 가중평균을 원표 구간평균에 정확히 맞춘다(순서 보존, 구간 경계 유지).
    개방구간(파레토)은 표본 수가 적어 실현평균이 이론평균에 못 미치므로 이 보정이 필요하다."""
    x = np.array(x, float); w = np.asarray(w, float)
    edges = np.append(bt['lo'], np.inf)
    k = np.clip(np.searchsorted(edges, x, side='right') - 1, 0, len(bt['lo']) - 1)
    for _ in range(iters):
        for i in range(len(bt['lo'])):
            m = (k == i)
            if not m.any() or bt['w'][i] <= 0:
                continue
            cur = float((x[m] * w[m]).sum() / max(w[m].sum(), 1e-12))
            if cur <= 0:
                continue
            x[m] = x[m] * (bt['mean'][i] / cur)
            hi = bt['hi'][i]
            lo = bt['lo'][i]
            x[m] = np.clip(x[m], max(lo, 1.0), hi if np.isfinite(hi) else np.inf)
    return x
