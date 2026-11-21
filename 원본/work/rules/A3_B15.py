# -*- coding: utf-8 -*-
"""B15 보훈급여 (vetbn_r_*, vetbn_ir_*)  — A3 / order 6

소스 (등급순)
  S1 국가보훈부 · e-나라지표 통계표 242301 「보훈급여금 등 지급현황」(2018~2024)
     2022: 계 438천명 / 45,127억원, 대상구분별(독립유공자·국가유공자·고엽제후유의증·참전유공자)
     params/raw/M01_242301_보훈급여금등_지급현황.csv                      [1차확인 2026-09-02]
  S1 국가보훈부 · e-나라지표 통계표 248201 「국가유공자 평균 연령 현황」 2022 전체평균 74세
     params/raw/M01_248201_국가유공자_평균연령.csv                        [1차확인]
  S1 국가보훈부 · e-나라지표 통계표 156101 「보훈대상자현황」 2022 등록대상자 834,126명
     params/raw/M01_156101_보훈대상자현황_등록대상별.csv                   [1차확인]
  전사본: params/tab/A3_B15_보훈급여_2022.csv

확보 실패 (registry/acq_misc.md §(1) 참조) — 지어내지 않고 [미확인]으로 남김
  · 보훈대상자 **성·연령별 분포 2022** : data.go.kr 15072654 는 2025-12-31 이후 이력만 제공,
    mpva.go.kr 게시판은 2025-06 이후 게시물만 노출. 2022판 부재.
    → 연령 분포는 e-나라지표 248201 의 대상구분별 **평균연령**(2022)에 맞춘 정규가중으로 복원
      [논리적추론]. 2025 기준 성·연령표는 수치 전사에 사용하지 않았다.
  · **수시 보상금**(vetbn_ir_yn, vetbn_ir_amt) : 정기/수시 구분 공표표 미발견.
    KOSIS 109/DT_109006_D004(보훈대상자 생활실태조사)는 OpenAPI 인증키 없음으로 조회 불가.
    → **전량 NaN [미확인]**. 임의 수치를 생성하지 않는다.

검증 : 참전유공자 1인당 연 4,192,517원 = 월 349,376원 ≒ 2022년 참전명예수당 월 35만원 → 정합.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

# ── [1차확인] e-나라지표 242301 (2022) — 대상구분별 수급인원·지급금액 ──────────────
#   (이름, 수급인원, 연간지급액(원), 연령봉우리, 연령표준편차, 최저연령, 남성비율)
#   연령봉우리·표준편차·남성비율은 e-나라지표 248201 평균연령(2022)과 제도 성격
#   (참전·고엽제=월남/6·25 참전 본인, 국가유공자=전공상군경 본인+유족)에서 도출 [논리적추론]
COMPS = [
    ('참전유공자',     147000,  616300000000, 79.0,  6.0, 66, 0.99),
    ('국가유공자',     249000, 3484100000000, 71.0, 11.0, 40, 0.70),
    ('고엽제후유의증',  35000,  296100000000, 77.0,  5.0, 66, 0.99),
    ('독립유공자',       7000,  116200000000, 78.0, 10.0, 45, 0.50),
]
N_VET = 438000                  # 계 438천명
AMT_VET = 4512700000000         # 계 45,127억원
MEAN_AGE_TARGET = 74.0          # e-나라지표 248201 2022 전체평균
SIGMA_AMT = 0.45                # 대상구분 내 급여액 분산 [가정]
MIN_EXPECTED = 3.0


def _pps_select(g, p):
    p = np.clip(np.asarray(p, float), 0.0, 1.0)
    idx = np.flatnonzero(p > 0)
    out = np.zeros(len(p), dtype=np.int8)
    if idx.size == 0:
        return out
    order = idx[g.permutation(idx.size)]
    c = np.cumsum(p[order]); u = g.random()
    prev = np.floor(np.concatenate(([0.0], c[:-1])) - u)
    out[order[np.floor(c - u) > prev]] = 1
    return out


def _norm_target(score, elig, target_n):
    s = np.where(elig, np.maximum(score, 0.0), 0.0)
    p = np.zeros(len(s))
    if s.sum() <= 0 or target_n <= 0:
        return p
    p = s / s.sum() * target_n
    for _ in range(30):
        over = p > 0.95
        if not over.any():
            break
        exc = float((p[over] - 0.95).sum()); p[over] = 0.95
        rest = (s > 0) & ~over
        if not rest.any() or s[rest].sum() <= 0:
            break
        p[rest] += exc * s[rest] / s[rest].sum()
    return np.clip(p, 0, 1)


def _calib(vals, mask, target_nat, frac, lo=0.4, hi=2.5):
    cur = float(np.nansum(np.where(mask, vals, 0.0))) / frac
    if cur <= 0:
        return vals, 1.0
    k = float(np.clip(target_nat / cur, lo, hi))
    return vals * k, k


def _norm_target_w(score, elig, target_pop, w):
    """포함확률 p ∝ score, **가중 합계** Σ p_i·indwgt_i = 전국 목표인원 이 되도록 정규화.
    (표본 가중치가 셀마다 다르므로 단순 인원 목표로 맞추면 가중 추정 총량이 어긋난다.)"""
    s = np.where(elig, np.maximum(score, 0.0), 0.0)
    p = np.zeros(len(s))
    den = float((s * w).sum())
    if den <= 0 or target_pop <= 0:
        return p
    p = s * (target_pop / den)
    for _ in range(30):
        over = p > 0.95
        if not over.any():
            break
        exc = float(((p[over] - 0.95) * w[over]).sum())
        p[over] = 0.95
        rest = (s > 0) & ~over
        d2 = float((s[rest] * w[rest]).sum()) if rest.any() else 0.0
        if d2 <= 0:
            break
        p[rest] += exc * s[rest] / d2
    return np.clip(p, 0, 1)


def _calib_w(vals, mask, target_nat, w, lo=0.4, hi=2.5):
    """Σ(금액×indwgt) = 전국 목표 총액이 되도록 단일계수 스케일링."""
    cur = float(np.nansum(np.where(mask, vals * w, 0.0)))
    if cur <= 0:
        return vals, 1.0
    k = float(np.clip(target_nat / cur, lo, hi))
    return vals * k, k


def generate(df, params, ctx):
    g = core.rng('B15')
    n = len(df)
    N_pop = float(df['_N_pop_person'].iloc[0])
    frac = n / N_pop
    w = df['indwgt'].astype(float).values if 'indwgt' in df.columns else np.full(n, N_pop / n)
    age = df['age'].values.astype(float)
    sex = df['gender'].values
    u_wel = df['_u_welfare'].values

    out = pd.DataFrame(index=df.index)
    for c in ('vetbn_r_yn', 'vetbn_r_amt', 'vetbn_ir_yn', 'vetbn_ir_amt'):
        out[c] = np.nan
    trace = {'표본추출률': frac}

    # 대상구분별 가중 (연령 정규 × 성별)
    shares = np.array([c[1] for c in COMPS], float); shares = shares / shares.sum()
    # 대상구분별 "수급자 연령·성 구성비" W 를 만든 뒤, 표본의 (성×5세) 셀 인원으로 나누어
    # **1인당 수급확률**로 바꾼다. (그냥 W 를 확률로 쓰면 인구가 많은 젊은 층이 과다 선정된다.)
    band = np.clip((age // 5 * 5).astype(int), 0, 100)
    cell = pd.Series(1, index=pd.MultiIndex.from_arrays([sex, band])).groupby(level=[0, 1]).sum()
    base = np.array([float(cell.get((int(sx), int(bd)), 0.0)) for sx, bd in zip(sex, band)])
    base = np.maximum(base, 1.0)
    W = np.zeros((len(COMPS), n))
    for i, (nm, cn, ca, pk, sd, lo, pm) in enumerate(COMPS):
        cw = np.exp(-0.5 * ((age - pk) / sd) ** 2)
        cw = np.where(age >= lo, cw, 0.0)
        cw = cw * np.where(sex == 1, pm, 1.0 - pm)
        r = cw / base                                 # 1인당 상대 수급확률
        tot = r.sum()
        W[i] = r / tot if tot > 0 else r              # Σ_i W[i] = 1 → 대상구분 주변분포 보존
    score = (shares[:, None] * W).sum(axis=0) * (0.7 + 0.6 * u_wel)
    elig = score > 0
    tgt = N_VET / w.mean()
    trace['보훈급여_기대인원'] = tgt

    if tgt >= MIN_EXPECTED and elig.any():
        sel = _pps_select(g, _norm_target_w(score, elig, N_VET, w)) == 1
        out['vetbn_r_yn'] = np.where(sel, 1.0, np.nan)
        # 선정자별 대상구분 배정 (P(c|age,sex) ∝ share_c × w_c)
        comp = np.full(n, -1, int)
        idx = np.flatnonzero(sel)
        if idx.size:
            pw = (shares[:, None] * W[:, idx])
            colsum = pw.sum(axis=0)
            colsum[colsum <= 0] = 1.0
            pw = pw / colsum
            u = g.random(idx.size)
            comp[idx] = (np.cumsum(pw, axis=0) < u[None, :]).sum(axis=0).clip(0, len(COMPS) - 1)
        cmean = np.array([c[2] / c[1] for c in COMPS], float)
        base = np.where(comp >= 0, cmean[np.clip(comp, 0, len(COMPS) - 1)], 0.0)
        amt = core.lognormal_mean(g, np.maximum(base, 1.0), SIGMA_AMT, n)
        amt, k = _calib_w(amt, sel, AMT_VET, w)
        out.loc[sel, 'vetbn_r_amt'] = np.maximum(np.rint(amt[sel]), 1)
        trace['보훈급여_생성'] = int(sel.sum())
        trace['보훈급여_금액계수'] = k
        trace['보훈급여_총액_가중'] = float((out['vetbn_r_amt'].fillna(0) * w).sum())
        trace['수급자_평균연령'] = float(age[sel].mean()) if sel.any() else None
        trace['목표_평균연령'] = MEAN_AGE_TARGET
        trace['수급자_남성비율'] = float((sex[sel] == 1).mean()) if sel.any() else None
        trace['대상구분_분포'] = {COMPS[i][0]: int((comp == i).sum()) for i in range(len(COMPS))}
        trace['65세이상_비율'] = float((age[sel] >= 65).mean()) if sel.any() else None
    else:
        trace['보훈급여_규모미달'] = True

    # ── 수시 보상금: 공표 자료 확보 실패 → 전량 NaN [미확인] ──────────────────
    trace['수시보상금'] = '미확인(전량 NaN) — registry/acq_misc.md 시도기록'

    for c in out.columns:
        out[c] = np.rint(pd.to_numeric(out[c], errors='coerce').astype(float))

    ctx.setdefault('trace', {})['B15'] = trace
    print('  [B15]', {k: (round(v, 4) if isinstance(v, float) else v) for k, v in trace.items()})
    return out
