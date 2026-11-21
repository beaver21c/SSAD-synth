# -*- coding: utf-8 -*-
"""B10 금융소득DB·공적연금DB — fainc_sum, fainc_tax, pubpen_inc, pubpen_tax  (A2 / order 3)

■ 소스 (등급순)
  S0 R02 <표 2-13> 소득원천별 가구소득 (2기·2021년 기준)  params/raw/R02_표2-13_소득원천별_가구소득.csv
     → **금융소득 보유 가구 비율 95.6%**, 가구 평균 319만원/년, 중위 23만원  [1차확인 2026-09-02]
     → 보유율(구조)의 1순위 기준. 행정데이터와 동일 자료원의 기초분석이므로 S1 보다 우선.
  S1 국세청 국세통계 2023년 발행(2022년 귀속) TASIS 직접 조회분  [1차확인 2026-09-02]
     <4-4-12> 이자소득 분위별 신고 현황 : 소득금액 19,873,890백만원 / 소득세 2,739,571 / 10분위
     <4-4-13> 배당소득 분위별 신고 현황 : 소득금액 29,183,799백만원 / 소득세 3,991,452 / 10분위
     → **총량·분위 집중도·유효세율**의 기준 (AGENT_BRIEF: 총량·단가는 2022년 S1 로 맞춘다)
     <4-3-3> 거주자의 연금소득 연말정산 신고 현황 : 인원 6,822,344 / 총연금수령액 49,551,373백만원 /
             소득세 결정세액 132,404백만원  → **pubpen_inc/pubpen_tax 의 통제총계** (B04 가 사용)
  S4 지방세법상 개인지방소득세 = 소득세액의 10% (NTS 4-4-10 에서 41,716/417,163 = 0.100000 실측)

■ 생성 절차
  fainc : 보유확률(연령가중)을 **가구 단위 보유율 95.6%(R02)** 에 맞도록 이분탐색으로 캘리브레이션
          → _u_income 상관 순위로 10분위 배정 → 분위 평균(이자+배당 합산)·로그정규
          → 분위 평균 정확 보정 → 전체 가중평균이 전국 1인당 총액(953,585원)이 되도록 1회 스케일
  fainc_tax = 소득세(분위별 실측 유효세율) × 1.1 (지방소득세 10% 부가)
  pubpen_* : **B10 은 만들지 않는다**(PUBPEN_MODE_DEFAULT='skip') → B04(order 9)가 생성.
             B10 은 order 3 이라 B13~B15 의 연금급여를 볼 수 없기 때문. [2026-09-02 최종검증 정정]
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core, nts

MW = 1_000_000
HH_HOLD_TARGET = 0.956          # R02 <표 2-13> 금융소득 보유 가구 비율 [1차확인]
POP_2022 = 51_450_829           # 주민등록 2022.11 총인구 (fainc 1인당 총액 분모)
AGE_W = {'child': 0.30, 'teen': 0.60}   # 15세 미만·15~19세 상대 보유성향 [가정 A2-B10-1]
RHO_HOLD, RHO_AMT = 0.30, 0.65  # _u_income 상관 [가정 A2-B10-2]
SIG_TOP, SIG_REST = 1.6, 0.9    # 분위 내부 로그정규 σ [가정 A2-B10-3]
LOCAL = 0.10                    # 지방소득세 = 소득세의 10%
# B10 이 pubpen_inc/pubpen_tax 컬럼을 만들지 여부.
# ★2026-09-02 최종검증에서 'nan' → 'skip' 으로 변경 (오케스트레이터 조치, 근거 아래).
#   pubpen_inc = 국민연금(B13)·직역연금(B14~B15) 급여 합이므로 order 3 인 B10 은 값을 만들 수 없다.
#   'nan' 이면 러너의 "상위 컬럼 수정 금지" 때문에 B04(order 9)가 값을 채우지 못해
#   두 변수가 최종 산출물에서 전량 NaN 이 되고, 검증목표 2건이 평가불가가 된다.
#   'skip' 이면 컬럼 자체를 만들지 않아 B04 가 국세청 4-3-3(2022 귀속) 통제총계로 생성한다.
#   (params/A2_B04.yaml codebook_review ① · registry/orchestrator_findings.md §3 참조)
PUBPEN_MODE_DEFAULT = 'skip'


def decile_table():
    """4-4-12(이자) + 4-4-13(배당) → 10분위별 (금액, 소득세). 상위10%=index 0."""
    order = ['상위10%', '상위 20%', '상위 30%', '상위 40%', '상위 50%',
             '상위 60%', '상위 70%', '상위 80%', '상위 90%', '상위 100%']
    amt = np.zeros(10); tax = np.zeros(10); npr = np.zeros(10)
    for t, akey in (('4-4-12', '이자소득\n분위별'), ('4-4-13', '배당소득\n분위별')):
        d = nts.nts(t)
        s = d[d.ROW_L1.astype(str).str.replace('\n', '') == akey.replace('\n', '')]
        g = s.pivot_table(index='ROW_L2', columns='COL_L2', values='VALUE', aggfunc='sum')
        cols = {str(c).replace('\n', ''): c for c in g.columns}
        for i, lab in enumerate(order):
            if lab not in g.index:
                continue
            amt[i] += float(g.loc[lab, cols['소득금액']]) * MW
            tax[i] += float(g.loc[lab, cols['소득세']]) * MW
            if t == '4-4-12':
                npr[i] = float(g.loc[lab, cols['소득자인원']])
    return {'amt': amt, 'tax': tax, 'n': npr,
            'mean': amt / np.maximum(npr, 1), 'rate': tax / np.maximum(amt, 1),
            'total': amt.sum()}


def _age_w(age):
    a = np.asarray(age, float)
    return np.where(a < 15, AGE_W['child'], np.where(a < 20, AGE_W['teen'], 1.0))


def generate(df, params, ctx):
    g = core.rng('B10')
    n = len(df)
    D = decile_table()
    w = df['indwgt'].values if 'indwgt' in df.columns else np.ones(n)
    hid = df['hid'].values
    wa = _age_w(df['age'].values)
    r_hold = nts.score(g, df['_u_income'].values, RHO_HOLD)
    r_amt = nts.score(g, df['_u_income'].values, RHO_AMT)

    # 가구 단위 보유율 = 95.6% (R02) 가 되도록 개인 기저확률 이분탐색
    hw = pd.Series(w).groupby(hid).first()

    def hh_share(base):
        h = r_hold > (1.0 - np.clip(base * wa, 0, 0.999))
        any_h = pd.Series(h).groupby(hid).max()
        return float((any_h * hw).sum() / hw.sum())

    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if hh_share(mid) < HH_HOLD_TARGET:
            lo = mid
        else:
            hi = mid
    base = (lo + hi) / 2
    hold = r_hold > (1.0 - np.clip(base * wa, 0, 0.999))
    # [T5-a] 금융소득 종합과세 신고자(B07 inc_inter·inc_allo 보유)는 금융소득DB 보유자이고,
    #        지급액(fainc_sum)은 신고한 이자소득금액 + 배당액 이상이어야 한다(신고분은 지급액의 부분집합).
    _fl = np.zeros(n)
    if 'inc_inter' in df.columns and 'inc_allo' in df.columns:
        _fl = df['inc_inter'].fillna(0).to_numpy(float) + df['inc_allo'].fillna(0).to_numpy(float)
        hold = hold | (_fl > 0)
        r_amt = r_amt + 2.0 * (_fl > 0)                          # 신고자를 금액 순위 최상단에 둔다

    # 10분위 배정(_u_income 상관 순위) → 분위 평균 로그정규 → 분위 평균 정확 보정
    x = np.full(n, np.nan)
    idx = np.flatnonzero(hold)
    if len(idx):
        o = np.argsort(r_amt[idx], kind='mergesort')
        cw = np.cumsum(w[idx][o]); rg = np.empty(len(idx)); rg[o] = (cw - 0.5 * w[idx][o]) / cw[-1]
        dec = np.clip((9 - (rg * 10).astype(int)), 0, 9)          # 0=상위10%
        v = np.empty(len(idx))
        for i in range(10):
            m = (dec == i)
            c = int(m.sum())
            if c == 0:
                continue
            sig = SIG_TOP if i == 0 else SIG_REST
            v[m] = core.lognormal_mean(g, D['mean'][i], sig, c)
            cur = float((v[m] * w[idx][m]).sum() / w[idx][m].sum())
            if cur > 0:
                v[m] *= D['mean'][i] / cur                        # 분위 평균 정확 재현
        # 전국 1인당 총액(= 이자+배당 소득금액 / 총인구)에 맞춰 1회 스케일
        per_cap = D['total'] / POP_2022
        cur_pc = float((v * w[idx]).sum() / w.sum())
        v *= per_cap / max(cur_pc, 1e-9)
        if (_fl[idx] > 0).any():                                  # [T5-b] 상위 10% 안에서 큰 금액을 신고액 큰 사람에게
            _t = np.flatnonzero(dec == 0)
            _ord = _t[np.lexsort((-r_amt[idx][_t], -_fl[idx][_t]))]
            v[_ord] = np.sort(v[_t])[::-1]
            _short = float((np.maximum(_fl[idx] - v, 0.0) * w[idx]).sum())
            v = np.maximum(v, _fl[idx])                          # 하한 = 신고 금융소득
            _rest = (_fl[idx] <= 0) & (dec == 0)
            _den = float((v[_rest] * w[idx][_rest]).sum())
            if _short > 0 and _den > 0:
                v[_rest] *= max(0.05, 1.0 - _short / _den)       # 상위 10% 가중 총액 보존
        x[idx] = np.maximum(v, 1.0)
        rate = np.zeros(n); rate[idx] = D['rate'][dec]
    else:
        rate = np.zeros(n)

    tax = np.where(hold, np.round(x * rate * (1.0 + LOCAL)), np.nan)

    out = pd.DataFrame(index=df.index)
    out['fainc_sum'] = np.round(x)
    out['fainc_tax'] = np.where(np.nan_to_num(tax) > 0, tax, np.nan)

    # ── 공적연금DB ────────────────────────────────────────────────────────────
    # pubpen_inc = 국민연금(B13)·공무원/사학/군인/별정우체국연금(B14~B15) 급여의 합이다.
    # 실행순서상 B10(order 3) < B13(order 4) 이므로 여기서는 값을 만들 수 없다.
    # 지시서 지정에 따라 **컬럼만 만들고 전량 NaN** 으로 두고, B04(order 9)가 채운다.
    if str(ctx.get('b10_pubpen', PUBPEN_MODE_DEFAULT)).lower() != 'skip':
        out['pubpen_inc'] = np.nan
        out['pubpen_tax'] = np.nan
    return out
