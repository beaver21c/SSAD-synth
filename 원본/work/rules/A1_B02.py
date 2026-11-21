# -*- coding: utf-8 -*-
"""B02 지역·가중치 — city, sido, hhwgt, indwgt  (A1 / order 1)

소스:
  S2 행정안전부 행정표준코드 시군구코드(2022) — params/raw/CODE_sigungu_2022.csv  [1차확인]
     ※ 코드북 붙임 "시군구코드" 시트 부재 [1차확인] → 행안부 5자리 코드로 대체하고 매핑표를 산출한다.
  S2 주민등록 인구통계 2022.11 (시군구×1세×성) / 2022 등록센서스 일반가구수 — 모집단(가중치 분모)
  S0 R01 제2장 제2절 가중치 부여 방식 — 20~30% 표본설계, 시군구 단위 가구·가구원 비율 보존

가중치 (§6 B02, §7 R25):
  기본 hhwgt = 모집단 일반가구수 / 표본가구수, indwgt = 모집단 인구 / 표본인구
  → 성×5세연령대×시도 셀에 대해 IPF(raking) 1회로 개인가중치 보정 (§4.1 "반복 금지")
  → hhwgt 는 가구원 indwgt 평균으로 재계산 후 Σhhwgt 가 모집단 가구수와 일치하도록 스케일
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

RAW = 'params/raw'
AGE_BANDS = list(range(0, 101, 5))          # 0-4, 5-9, ... 100+


def _band(a):
    return np.minimum((np.asarray(a) // 5) * 5, 100)


def generate(df, params, ctx):
    g = core.rng('B02')
    code = pd.read_csv(os.path.join(RAW, 'CODE_sigungu_2022.csv'))
    code = code[code.level == 'sigungu'][['sigungu_code', 'sigungu_name', 'sido', 'sido_name', 'name_full']]

    out = pd.DataFrame(index=df.index)
    out['city'] = df['_sigungu_code'].astype(int)      # 행안부 5자리 시군구코드
    out['sido'] = df['_sido'].astype(int)              # 코드북 sido 코드(서울1 … 제주17)

    # ── 모집단 ─────────────────────────────────────────────────────────────
    pop = pd.read_csv(os.path.join(RAW, 'POPUL_MOIS01_2022_11_sigungu_age1_sex.csv'))
    pop = pop[(pop.level == 'sigungu') & (pop.sex.isin(['male', 'female']))].copy()
    pop['sido'] = pop['sido'].astype(int)
    pop['sex_c'] = np.where(pop.sex == 'male', 1, 2)
    pop['band'] = _band(pop.age.values)
    tgt = pop.groupby(['sex_c', 'band', 'sido'])['pop'].sum()
    N_pop_person = float(pop['pop'].sum())
    N_pop_hh = float(df['_hh_pop_total'].iloc[0])

    n_person = len(df)
    n_hh = int(df['hid'].nunique())

    # ── 초기 가중치 ────────────────────────────────────────────────────────
    w = np.full(n_person, N_pop_person / n_person, dtype=float)

    # ── IPF(raking) 1회: 성×5세×시도 ────────────────────────────────────────
    key = pd.MultiIndex.from_arrays([df['gender'].astype(int).values, _band(df['age'].values),
                                     out['sido'].astype(int).values])
    cur = pd.Series(w).groupby(key).sum()
    tg = tgt.reindex(cur.index)
    # 표본에 없는 셀은 조정 불가; 목표가 없는 셀(모집단 0)은 그대로 둠
    factor = (tg / cur).replace([np.inf, -np.inf], np.nan)
    # 극단 가중치 방지: 상·하한 [가정 A1-6] — 표본 9.8천으로 3,400여 셀을 채울 수 없어 필요
    factor = factor.clip(lower=0.2, upper=5.0).fillna(1.0)
    w = w * factor.reindex(key).values
    w = w * (N_pop_person / w.sum())      # 총량 재조정 (R25: Σindwgt ≈ 모집단 인구)

    out['indwgt'] = np.round(w, 4)

    # ── 가구가중치: 가구원 개인가중치 평균 → 총량 스케일 ─────────────────────
    hw = pd.Series(w, index=df['hid'].values).groupby(level=0).mean()
    hhw = df['hid'].map(hw).values
    scale = N_pop_hh / pd.Series(hhw, index=df['hid'].values).groupby(level=0).first().sum()
    out['hhwgt'] = np.round(hhw * scale, 4)

    # 진단용 (최종 export 시 제외)
    out['_sigungu_name'] = df['_sigungu_name'].values
    out['_N_pop_person'] = N_pop_person
    out['_N_pop_hh'] = N_pop_hh
    return out
