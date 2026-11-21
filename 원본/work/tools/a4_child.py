# -*- coding: utf-8 -*-
"""A4 영유아 급여 공통 모듈 — B28(수당)·B30(보육료)이 공유하는 배타 배분 로직.

§7 R07 (infantbn · carebn · childcare 배타)을 만족시키려면 두 블록이 **동일한**
프로그램 배정 결과를 써야 한다. B28(order 5)이 `_pre_prog`·`_bmonth` 를 만들어
B30(order 6)에 넘기고, B30 은 컬럼이 없을 때만 같은 난수열로 재계산한다.

소스 (모두 params/raw, [1차확인] 2026-09-02):
  R05 <표 4-3-10> 영유아 보육료 수급 아동 수 (연령·성·시도)   전국 1,071,789명
  R05 <표 4-3-11> 가정양육수당 수급 아동 수 (월령대·성·시도)  전국 280,267명
  R05 <표 4-3-12> 영아수당 수급 아동 수 (성·시도)              전국 219,524명
  2022년 보육사업안내 본문 인쇄 p.63 (PDF p.69) 반편성 기준:
     만0세반 ʼ21.1.1. 이후 출생 / 만1세반 ʼ20년생 / 만2세반 ʼ19년생 /
     만3세반 ʼ18년생 / 만4세반 ʼ17년생 / 만5세반 ʼ16년생
     → 표 4-3-10 의 "연령"은 만나이가 아니라 **반연령(출생연도)** 이다.
  2022년 보육사업안내 본문 인쇄 p.331 "영아수당 도입에 따라 ʼ22년 이후 출생아는
     만 2세부터 가정양육수당 지원" → 2022년생은 2022년 중 영아수당(현금)만 대상
  주민등록 인구통계 2022.11 (params/raw/POPUL_MOIS01_*) → 출생연도별 등록인구
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core

RAW = 'params/raw'
P_NOV_DEC = 0.17           # B01 과 동일: 만나이 a 인 자 중 (2022-a-1)년생 비율

SIDO_CODE = {'서울': 1, '부산': 2, '대구': 3, '인천': 4, '광주': 5, '대전': 6, '울산': 7,
             '세종': 8, '경기': 9, '강원': 10, '충북': 11, '충남': 12, '전북': 13,
             '전남': 14, '경북': 15, '경남': 16, '제주': 17}

# 반연령(=출생연도) ↔ R05 표4-3-10 "연령" 라벨   [1차확인 보육사업안내 p.63]
CC_CLASS_BY = {'0세': (2021, 2022), '1세': (2020,), '2세': (2019,),
               '3세': (2018,), '4세': (2017,), '5+세': (2016,)}
# 표4-3-11 월령대 ↔ 출생연도 (2022.12 기준 월령)  [1차확인]
CARE_BAND_BY = {'12-23개월': 2021, '24-35개월': 2020, '36-47개월': 2019,
                '48-59개월': 2018, '60-71개월': 2017, '72개월-취학전': 2016}


# ────────────────────────────────────────────────────────────── 원자료 로드
def _r05(name):
    d = pd.read_csv(os.path.join(RAW, name))
    d['값'] = pd.to_numeric(d['값'], errors='coerce')
    return d


def load_counts():
    """R05 표 4-3-10/11/12 전국·시도 수급아동 수 → dict."""
    cc = _r05('R05_4-3-10_영유아보육료수급아동_연령성별시도별.csv')
    ca = _r05('R05_4-3-11_가정양육수당수급아동_성별시도별.csv')
    inf = _r05('R05_4-3-12_영아수당수급아동_성별시도별.csv')

    def _sum(d, sel, key):                      # 항목 '<key>_남' + '<key>_여'
        m = d[(d['구분유형'] == sel[0]) & (d['구분'] == sel[1])]
        return float(m[m['항목'].isin([key + '_남', key + '_여'])]['값'].sum())

    cc_nat = {k: _sum(cc, ('전국', '계'), k) for k in CC_CLASS_BY}
    ca_nat = {k: _sum(ca, ('전국', '계'), k) for k in CARE_BAND_BY}
    inf_nat = float(inf[(inf['구분유형'] == '전국') & (inf['항목'] == '계_계')]['값'].iloc[0])

    cc_sido = {s: _sum(cc, ('시도', s), '계') for s in SIDO_CODE}
    ca_sido = {s: _sum(ca, ('시도', s), '계') for s in SIDO_CODE}
    return {'cc_nat': cc_nat, 'ca_nat': ca_nat, 'inf_nat': inf_nat,
            'cc_sido': cc_sido, 'ca_sido': ca_sido}


def load_pop_by_age():
    """주민등록 2022.11 전국 1세 인구 (만나이 0~100)."""
    p = pd.read_csv(os.path.join(RAW, 'POPUL_MOIS01_2022_11_sigungu_age1_sex.csv'))
    p = p[(p.level == 'sigungu') & (p.sex.isin(['male', 'female']))].copy()
    p['age'] = p['age'].astype(int)
    return p.groupby('age')['pop'].sum()


def birth_cohort_reg(pop_by_age, year):
    """2022.11.1 등록인구 기준 출생연도 `year` 코호트 크기.
    만나이 a 인 자의 (1-0.17)은 (2022-a)년생, 0.17은 (2022-a-1)년생 [B01 규약]."""
    a0 = 2022 - year                        # 해당 연도 1~11.1 출생 → 만나이 a0
    n = 0.0
    if a0 in pop_by_age.index:
        n += (1 - P_NOV_DEC) * float(pop_by_age.loc[a0])
    if (a0 - 1) in pop_by_age.index and a0 - 1 >= 0:
        n += P_NOV_DEC * float(pop_by_age.loc[a0 - 1])
    return n


# ────────────────────────────────────────────────── 출생연도별 배타 배분 확률
def program_rates():
    """출생연도 Y → {'infant','care','childcare'} 수급확률 (배타, 합≤1).

    보육료 0세반(124,107명)은 2021·2022년생이 공유하므로 각 코호트의
    '잔여 정원'(등록인구 − 타 프로그램 수급자)에 비례 배분한다 [논리적추론].
    합이 1을 넘으면 비례 축소(연간 자격중복·연중 이동으로 원자료 합이
    코호트 인구를 초과하는 구간이 있음) [논리적추론].
    """
    c = load_counts()
    pop = load_pop_by_age()
    reg = {y: birth_cohort_reg(pop, y) for y in range(2016, 2023)}

    cnt = {y: {'infant': 0.0, 'care': 0.0, 'childcare': 0.0} for y in reg}
    cnt[2022]['infant'] = c['inf_nat']
    for band, y in CARE_BAND_BY.items():
        cnt[y]['care'] = c['ca_nat'][band]
    for k, ys in CC_CLASS_BY.items():
        if len(ys) == 1:
            cnt[ys[0]]['childcare'] = c['cc_nat'][k]
        else:                                    # 0세반 = 2021·2022년생 공유
            room = {y: max(0.0, reg[y] - cnt[y]['infant'] - cnt[y]['care']) for y in ys}
            tot = sum(room.values())
            for y in ys:
                cnt[y]['childcare'] = c['cc_nat'][k] * (room[y] / tot if tot > 0 else 0.0)

    rates = {}
    for y, d in cnt.items():
        p = {k: (v / reg[y] if reg[y] > 0 else 0.0) for k, v in d.items()}
        s = sum(p.values())
        if s > 1.0:
            p = {k: v / s for k, v in p.items()}
        rates[y] = p
    return rates, reg, c


def sido_care_tilt(counts):
    """시도별 [양육수당 ÷ (양육수당+보육료)] 상대비 → 가정양육 성향 보정계수."""
    nat = counts['ca_nat']
    tot_ca = sum(nat.values())
    tot_cc = sum(counts['cc_nat'].values())
    base = tot_ca / (tot_ca + tot_cc)
    out = {}
    for s, code in SIDO_CODE.items():
        a, b = counts['ca_sido'][s], counts['cc_sido'][s]
        out[code] = ((a / (a + b)) / base) if (a + b) > 0 else 1.0
    return out


# ─────────────────────────────────────────────────────────────── 배정 실행
def assign(df, g):
    """(_pre_prog, _bmonth) 생성. g 는 core.rng('B28') 로 얻은 생성기(소비됨)."""
    rates, reg, counts = program_rates()
    tilt = sido_care_tilt(counts)

    n = len(df)
    age = df['age'].to_numpy()
    yr = df['year'].to_numpy()
    sido = df['_sido'].to_numpy()

    # 출생월: B01 의 year 규약과 정합 — year==2022-age 면 1~11월, 아니면 11~12월
    u = g.random(n)
    early = (yr == (2022 - age))
    bm = np.where(early, 1 + np.floor(u * 11).astype(int), 11 + (u < 0.5).astype(int))
    bm = np.clip(bm, 1, 12).astype(np.int16)

    prog = np.full(n, 'none', dtype=object)
    r = g.random(n)
    for y, p in rates.items():
        m = (yr == y) & (age <= 7)
        if not m.any():
            continue
        p_inf = np.full(int(m.sum()), p['infant'])
        p_car = np.full(int(m.sum()), p['care'])
        p_cc = np.full(int(m.sum()), p['childcare'])
        t = np.array([tilt.get(int(s), 1.0) for s in sido[m]])
        tot = p_car + p_cc
        p_car2 = np.minimum(p_car * t, tot)          # 배타 총량 보존, 구성만 이동
        p_cc2 = tot - p_car2
        rr = r[m]
        pick = np.where(rr < p_inf, 'infant',
                 np.where(rr < p_inf + p_car2, 'care',
                   np.where(rr < p_inf + p_car2 + p_cc2, 'childcare', 'none')))
        prog[np.flatnonzero(m)] = pick
    return prog, bm, rates, reg, counts


# ────────────────────────────────────────────────────────────── 단가 유틸
def care_monthly_won(year, bmonth, t):
    """가정양육수당 월 단가 (원). t=1..12 (2022년 달).
    [1차확인] 2022년 보육사업안내 본문 인쇄 p.374: 0~11개월 200,000 /
    12~23개월 150,000 / 24~35개월 100,000 / 36개월~86개월 미만 100,000."""
    mm = (2022 - year) * 12 + (t - bmonth)
    out = np.zeros_like(mm, dtype=np.int64)
    out = np.where((mm >= 0) & (mm < 12), 200000, out)
    out = np.where((mm >= 12) & (mm < 24), 150000, out)
    out = np.where((mm >= 24) & (mm < 86), 100000, out)
    return out


def rural_monthly_won(year, bmonth, t):
    """농어촌 양육수당 월 단가 (원) [1차확인 보육사업안내 인쇄 p.374]
    0~11 200,000 / 12~23 177,000 / 24~35 156,000 / 36~47 129,000 / 48~86미만 100,000"""
    mm = (2022 - year) * 12 + (t - bmonth)
    out = np.zeros_like(mm, dtype=np.int64)
    out = np.where((mm >= 0) & (mm < 12), 200000, out)
    out = np.where((mm >= 12) & (mm < 24), 177000, out)
    out = np.where((mm >= 24) & (mm < 36), 156000, out)
    out = np.where((mm >= 36) & (mm < 48), 129000, out)
    out = np.where((mm >= 48) & (mm < 86), 100000, out)
    return out


def class_age(year):
    """출생연도 → 2022년도 어린이집 반연령 (0~5). [1차확인 보육사업안내 p.63]"""
    y = np.asarray(year)
    return np.clip(2022 - np.where(y >= 2021, 2021, y), 0, 5).astype(int)
