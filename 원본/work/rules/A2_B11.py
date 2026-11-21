# -*- coding: utf-8 -*-
"""B11 사적연금DB — pripen_inc, pripen_inctax, pripen_localtax  (A2 / order 3)

■ 소스 (등급순)
  S1 국세청 국세통계 2023년 발행(2022년 귀속) TASIS 직접 조회분  [1차확인 2026-09-02]
     <4-4-7> 거주자의 연금계좌 원천징수 신고 현황
       · 연금소득 인원 817,500명 / 지급액 4,381,038백만원 / 소득세(원천징수분) 246,751백만원
       · 성별 : 남 614,576(3,588,465백만원) / 여 202,909(792,427백만원)
       · 연령 : 30세미만 70 / 30대 392 / 40대 1,135 / 50대 191,806 / 60세이상 624,082
       · 연금소득 지급액 11구간 × 인원·지급액·소득세 → 금액 히스토그램 + **실측 유효세율 4.3~7.2%**
     ※ 코드북 pripen_inc = [별지 제24호서식(6)] (19)일반연금 = 연금계좌 연금수령액과 동일 정의.
        지시서의 S2(KOSIS 101/DT_1PEN_064·061, 통계청 연금통계)와 같은 사적연금 모집단이나,
        국세청 지급명세서 집계가 코드북 정의(지급명세서 서식 항목)와 정확히 일치하고 등급도 높다.
  S4 소득세법 시행령 제40조의2 제3항(연금수령 요건: 가입자가 55세 이후 연금계좌취급자에게 신청) →
     55세 미만 수급 배제. 지방세법상 개인지방소득세 = 소득세의 10%.

■ 생성 절차 (§6 B11)
  55세 이상 연령 조건부 수급확률(4-4-7 인원 / 주민등록 인구) → 지급액 구간 히스토그램(순위 보존,
  구간평균·구간비중 정확 재현) → 성×연령 셀 평균 보정 → 구간별 실측 유효세율 → 지방소득세 10%
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core, nts

MW = 1_000_000
E5 = (30, 40, 50, 60)
MIN_AGE = 55                    # 소득세법 시행령 §40의2 연금수령 요건
OLD_DECAY = 10.0                # 80세 이후 감쇠 스케일 [가정 A2-B11-1]
RHO_HOLD, RHO_AMT = 0.20, 0.55  # _u_income 상관 [가정 A2-B11-2]
BETA_ALPHA = 1.3
LOCAL = 0.10

BANDS = [('1백만 이하', 0, 1e6), ('2백만 이하', 1e6, 2e6), ('3백만 이하', 2e6, 3e6),
         ('4백만 이하', 3e6, 4e6), ('5백만 이하', 4e6, 5e6), ('7백만 이하', 5e6, 7e6),
         ('1천만 이하', 7e6, 10e6), ('1.2천만 이하', 10e6, 12e6), ('1.5천만 이하', 12e6, 15e6),
         ('2천만 이하', 15e6, 20e6), ('2천만 초과', 20e6, None)]


def src():
    d = nts.nts('4-4-7')
    sel = lambda r, c: d[(d.ROW_L1 == r) & (d.COL_L2 == '연금소득') & (d.COL_L3 == c)] \
        .set_index('ROW_L2')['VALUE']
    lab = [b[0] for b in BANDS]
    n = np.array([float(sel('연금소득 지급액  규모별', '인원').get(l, 0.0)) for l in lab])
    a = np.array([float(sel('연금소득 지급액  규모별', '지급액').get(l, 0.0)) for l in lab]) * MW
    t = np.array([float(sel('연금소득 지급액  규모별', '소득세 (원천징수분)').get(l, 0.0)) for l in lab]) * MW
    bt = nts.band_table([b[1] for b in BANDS], [b[2] for b in BANDS], n, a)
    return {'bt': bt, 'n': n, 'a': a, 'tax': t,
            'rate': np.divide(t, np.maximum(a, 1.0), out=np.zeros_like(t), where=a > 0),
            'sex_n': sel('성별 [c]', '인원'), 'age_n': sel('연령별 [c]', '인원'),
            'sex_a': sel('성별 [c]', '지급액'), 'age_a': sel('연령별 [c]', '지급액')}


def _age_w(age):
    """55세 미만 0(소득세법 시행령 §40의2), 80세 이후 완만한 감쇠 [가정 A2-B11-1]."""
    a = np.asarray(age, float)
    return np.where(a < MIN_AGE, 0.0, np.where(a <= 80, 1.0, np.exp(-(a - 80.0) / OLD_DECAY)))


def generate(df, params, ctx):
    g = core.rng('B11')
    n = len(df)
    S = src()
    labs = nts.band_labels(E5)
    pop = nts.pop_sex_age(E5)
    sn = {k: float(S['sex_n'].get(k, 0)) for k in ('남성', '여성')}
    an = {l: float(S['age_n'].get(l, 0.0)) for l in labs}
    jn = nts.joint_from_margins(sn, an, pop)
    sa = {k: float(S['sex_a'].get(k, 0)) * MW for k in ('남성', '여성')}
    aa = {l: float(S['age_a'].get(l, 0.0)) * MW for l in labs}
    ja = nts.joint_from_margins(sa, aa, jn)
    rate = (jn / pop.loc[jn.index, jn.columns]).clip(upper=0.9)
    cmean = ja / jn.replace(0, np.nan)

    sex = np.where(df['gender'].values == 1, '남성', '여성')
    band = nts.age_band(df['age'].values, E5)
    mw = nts.pop_weight_mean(_age_w, E5)
    wa = _age_w(df['age'].values)
    p = np.zeros(n)
    for s in ('남성', '여성'):
        for b in labs:
            m = (sex == s) & (band == b)
            if not m.any():
                continue
            d0 = mw.get((s, b), 0.0)
            p[m] = 0.0 if d0 <= 0 else np.clip(wa[m] / d0 * float(rate.loc[s, b]), 0.0, 0.9)

    hold = nts.score(g, df['_u_income'].values, RHO_HOLD) > (1.0 - p)
    r_amt = nts.score(g, df['_u_income'].values, RHO_AMT)

    x = np.full(n, np.nan)
    idx = np.flatnonzero(hold)
    if len(idx):
        key = np.array([f'{s}|{b}' for s, b in zip(sex, band)], dtype=object)
        rk = np.empty(len(idx))
        for k in np.unique(key[idx]):
            m = key[idx] == k
            rk[m] = (pd.Series(r_amt[idx][m]).rank(method='first').values - 0.5) / int(m.sum())
        base = nts.draw_by_rank(g, rk, S['bt'], alpha=BETA_ALPHA)
        natm = S['a'].sum() / max(S['n'].sum(), 1)
        tgt = {f'{s}|{b}': float(cmean.loc[s, b]) for s in ('남성', '여성') for b in labs
               if np.isfinite(cmean.loc[s, b])}
        fac = {k: max(v / natm, 1e-3) for k, v in tgt.items()}
        wt = df['indwgt'].values[idx] if 'indwgt' in df.columns else np.ones(len(idx))
        xx = base
        for _ in range(6):
            y = base * np.array([fac.get(k, 1.0) for k in key[idx]])
            o = np.argsort(y, kind='mergesort')
            cw = np.cumsum(wt[o]); rg = np.empty(len(idx)); rg[o] = (cw - 0.5 * wt[o]) / cw[-1]
            xx = nts.draw_by_rank(g, rg, S['bt'], alpha=BETA_ALPHA)
            ach = pd.Series(xx * wt).groupby(key[idx]).sum() / pd.Series(wt).groupby(key[idx]).sum()
            for k, v in ach.items():
                if k in fac and v > 0:
                    fac[k] = float(np.clip(fac[k] * tgt[k] / v, 1e-3, 50.0))
        xx = nts.match_band_means(xx, wt, S['bt'])
        x[idx] = np.maximum(xx, 10_000.0)

    er = nts.interp_rate(np.nan_to_num(x), S['bt'], S['rate'])
    tax = np.where(hold, np.round(x * er), np.nan)
    out = pd.DataFrame(index=df.index)
    out['pripen_inc'] = np.round(x)
    out['pripen_inctax'] = np.where(np.nan_to_num(tax) > 0, tax, np.nan)
    lt = np.round(out['pripen_inctax'] * LOCAL)
    out['pripen_localtax'] = lt.where(lt.fillna(0) > 0)
    return out
