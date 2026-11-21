# -*- coding: utf-8 -*-
"""B05 재산 — 재산세(ptax_*), 임대차 보증금·월차임, 재산 합계  (A2 / order 5)

이 블록은 order 5 의 첫 블록이며 공공부조·기초연금·장애인연금·한부모(B24·B26·B27·B29)가
쓰는 소득인정액 순위(`_recog_rank`)를 만든다. column_contract.md 의 헬퍼 계약을 따른다.

■ 소스 (등급순)
  S0  R02 <표 2-14> 분위별 가구 평균 소득 및 재산 (2021년 기준 행정데이터, 원문 p.80)
      → `_h_eq_inc` 10분위 평균, `_h_prop` 10분위 평균의 **목표분포**            [1차확인]
      params/tab/S0_R02_T2-14_분위별_가구평균_균등화일차소득_재산.csv
  S0  R02 <표 2-15>(소득분위×가구주연령), <표 2-16>(재산분위×가구주연령) 원문 p.80-81 [1차확인]
      params/tab/S0_R02_T2-15_*.csv, S0_R02_T2-16_*.csv
  S0  R01 <표 2-23> 소득분위별 재산분위별 가구비율 → 소득×재산 코퓰러          [1차확인]
      params/raw/R01_표2-23_소득분위별_재산분위별_가구비율.csv
  S1  R04 3-3 기초연금 수급자 재산유형별 평균보유액(2022) → 주택:토지:건물:보증금 구성비 [1차확인]
      params/tab/S1_R04_3-3_*.csv
  S1  2022 국민기초생활보장 사업안내(교육급여 운영방안, 교육부) + R03
      → 기본재산액·주거용재산 한도액·소득환산율(주거용 1.04%/일반 4.17%/금융 6.26%/자동차 100%) [1차확인]
      params/tab/NBLS_2022_소득인정액_산정규칙.csv
  S2b 지방세통계연감 2023(2022년 실적) 표9-1-2 + '지방세 개요' p.27
      → 과세물건별 건수·과표·세액, 공정시장가액비율(토지·건축물 70%, 주택 60%, 1세대1주택 45%) [1차확인]
      params/tab/PROP_2022_재산세_공정시장가액비율_실효세율.csv
  S2  주거실태조사 2022 : 시도별 점유형태(MLTM6909), 소득계층별 점유형태(MLTM6908),
      권역·소득계층별 평균 주택가격·전세보증금·월세(표Ⅲ-46·Ⅲ-47)                 [1차확인]
  S2  주거실태조사 2019 : 시도별 세부 점유형태(전세/보증부월세/무보증월세) — 2022년 계열 종료 [논리적추론]
  S2  가계금융복지조사 2022 : 전·월세보증금 보유가구 34.22%, 임대보증금(부채) 보유 15.36%·
      평균 2,366.7만원·중앙값 6,000만원                                            [1차확인]

■ 생성 순서
  1) 지역등급(대도시/중소도시/농어촌)·권역(수도권/광역시등/도지역)
  2) 가구 균등화 일차소득 분위 ← R02 표2-15 P(소득분위|가구주 연령대), 개인잠재변수 `_u_income`
  3) `_h_eq_inc` 값 ← R02 표2-14 분위 평균에 맞춘 구간 로그균등 + 분위평균 재조정
  4) 점유형태 ← MLTM6909(시도) × MLTM6908(소득계층), 임차 세부는 2019 계열
  5) 재산분위 ← R01 표2-23 코퓰러 × R02 표2-16(연령) × 점유형태 기울기 → IPF 1회로 주변분포 복원
  6) `_h_prop` 값 ← R02 표2-14 재산 분위 평균 (1~2분위 = 0원, 재산 0 가구 20.01%)
  7) 임차보증금·월차임 ← 주거실태 권역×소득계층 평균, 확정일자·임대차신고 포착률 0.883
  8) 재산세 시가표준액 3종 분해 → 개인 배분(가구주 0.75/배우자 0.20/기타 0.05, 지시서 §6 B05)
  9) ptax_sum = Σ 시가표준액 × 공정시장가액비율 × 물건별 실효세율
 10) `_recog_inc` = 소득평가액 + 재산의 소득환산액 (2022 사업안내 산식) → `_recog_rank`
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

RAW, TAB = 'params/raw', 'params/tab'
MAN = 10_000.0            # 만원 → 원

# ── S0 R02 <표 2-14> (만원) ────────────────────────────────────────────────
EQINC_DEC = [-133, 65, 359, 911, 1636, 2395, 3224, 4231, 5726, 12540]   # 균등화 일차소득
PROP_DEC  = [-63, 0, 1108, 5254, 10331, 16211, 24330, 37569, 63310, 206115]  # 가구 재산
PROP_ZERO_SHARE = 0.2001   # R02 원문 p.79 "재산이 0인 가구비율 20.01%"

# ── S0 R02 <표 2-15> 소득분위 × 가구주 연령대 (전체 가구 대비 %) ───────────
AGE_BANDS = [(0, 17), (18, 25), (26, 39), (40, 49), (50, 64), (65, 74), (75, 200)]
T215 = np.array([
    [0.01, 0.49, 0.98, 1.18, 2.95, 2.08, 2.32],
    [0.00, 0.59, 0.84, 1.04, 2.49, 2.56, 2.46],
    [0.00, 0.57, 1.12, 1.32, 2.72, 2.30, 1.96],
    [0.00, 0.51, 1.62, 1.80, 3.27, 1.71, 1.09],
    [0.00, 0.40, 1.79, 1.99, 3.67, 1.58, 0.58],
    [0.00, 0.40, 2.14, 2.08, 3.76, 1.22, 0.39],
    [0.00, 0.39, 2.74, 2.29, 3.45, 0.85, 0.27],
    [0.00, 0.26, 3.00, 2.58, 3.35, 0.60, 0.21],
    [0.00, 0.17, 2.95, 2.72, 3.57, 0.42, 0.18],
    [0.00, 0.08, 2.28, 2.76, 4.29, 0.43, 0.17]])
# ── S0 R02 <표 2-16> 재산분위(1-2,3..10) × 가구주 연령대 ───────────────────
T216 = np.array([
    [0.02, 2.44, 5.40, 3.52, 5.34, 1.71, 1.58],
    [0.00, 0.53, 2.34, 1.61, 3.05, 1.28, 1.18],
    [0.00, 0.37, 1.75, 1.65, 3.27, 1.62, 1.35],
    [0.00, 0.25, 2.01, 1.90, 3.37, 1.53, 1.10],
    [0.00, 0.11, 2.00, 2.07, 3.34, 1.41, 0.92],
    [0.00, 0.07, 1.96, 2.19, 3.47, 1.41, 0.87],
    [0.00, 0.04, 1.70, 2.32, 3.63, 1.46, 0.85],
    [0.00, 0.03, 1.35, 2.31, 3.90, 1.56, 0.85],
    [0.00, 0.02, 0.95, 2.18, 4.16, 1.75, 0.94]])
PROP_MARG = np.array([20.01, 10.00, 10.00, 10.16, 9.86, 9.98, 10.00, 10.00, 10.00]) / 100.0

# ── S0 R01 <표 2-23> 소득분위(행) × 재산분위(열: 1-2,3..10) 가구비율(%) ────
T223 = np.array([
    [5.87, 1.30, 1.79, 1.56, 1.29, 1.19, 1.15, 1.21, 0.84],
    [1.50, 0.22, 0.35, 0.33, 0.29, 0.27, 0.27, 0.31, 0.26],
    [3.37, 0.57, 1.08, 1.08, 0.90, 0.77, 0.67, 0.70, 0.84],
    [2.92, 0.67, 1.05, 1.10, 0.97, 0.83, 0.73, 0.71, 1.01],
    [2.32, 0.82, 1.03, 1.15, 1.11, 0.97, 0.84, 0.77, 0.99],
    [2.03, 0.99, 1.08, 1.18, 1.18, 1.04, 0.88, 0.73, 0.90],
    [1.66, 1.03, 1.07, 1.12, 1.23, 1.18, 1.02, 0.80, 0.88],
    [1.35, 0.90, 1.03, 1.04, 1.23, 1.31, 1.24, 0.98, 0.91],
    [1.01, 0.66, 0.95, 0.88, 1.11, 1.39, 1.53, 1.38, 1.10],
    [0.52, 0.30, 0.56, 0.57, 0.68, 1.06, 1.65, 2.40, 2.26]])

# ── 점유형태 (주거실태조사 2022) ───────────────────────────────────────────
# MLTM6908 전국 소득계층별 (자가/임차/무상)
TEN_BY_CLASS = {'low': (45.8, 48.5, 5.7), 'mid': (60.9, 36.2, 2.9), 'high': (74.2, 24.4, 1.4)}
TEN_ALL = (57.49, 38.78, 3.73)
# 권역별 평균 (표 Ⅲ-46, 2022, 만원)
REGION_RENT = {
    'capital':   {'price': 65557.4, 'jeonse': 24327.9, 'wdep': 3577.9, 'wrent': 38.2, 'nodep': 32.3},
    'metro_etc': {'price': 38078.0, 'jeonse': 15168.8, 'wdep': 1847.6, 'wrent': 30.8, 'nodep': 26.1},
    'province':  {'price': 20898.3, 'jeonse': 12398.9, 'wdep': 1232.2, 'wrent': 30.3, 'nodep': 26.6}}
NAT_RENT = {'price': 43804.8, 'jeonse': 20650.1, 'wdep': 2600.1, 'wrent': 34.5, 'nodep': 28.8}
# 소득계층별 평균 (표 Ⅲ-47, 2022, 만원)
CLASS_RENT = {'low':  {'jeonse': 10513.8, 'wdep': 1514.9, 'wrent': 30.0, 'nodep': 27.6},
              'mid':  {'jeonse': 19816.9, 'wdep': 3614.9, 'wrent': 39.4, 'nodep': 35.3},
              'high': {'jeonse': 34575.9, 'wdep': 8806.3, 'wrent': 57.0, 'nodep': 42.0}}

# ── 2022 국민기초생활보장 사업안내 (기본재산액·주거용재산 한도액·소득환산율) ──
BASIC_PROP = {'metro': 69_000_000, 'city': 42_000_000, 'rural': 35_000_000}
HOUSE_CAP  = {'metro': 120_000_000, 'city': 90_000_000, 'rural': 52_000_000}
R_HOUSE, R_GENERAL = 0.0104, 0.0417          # 월 소득환산율
DEPOSIT_RATE = 0.95                          # 주택임차보증금 적용률

# ── 재산세 (지방세통계연감 2023) ───────────────────────────────────────────
FMV = {'land': 0.70, 'building': 0.70, 'house': 0.60, 'house1': 0.45}
EFF = {'land': 0.00331, 'building': 0.003439, 'house': 0.002563}

LABOR_SHARE = 3694.0 / 4844.0      # R02 <표 2-13> 근로소득 평균 / 일차소득 평균
EARN_DEDUCT = 0.30                 # 근로소득공제 30% (2022 사업안내)
DEPOSIT_COVER = 34.22 / 38.78      # GFS 전월세보증금 보유가구 / 주거실태 임차가구 = 0.883
LANDLORD_SHARE = 0.1536            # GFS 2022 임대보증금(부채) 보유가구 비율
LANDLORD_MEAN, LANDLORD_MED = 15408.0, 6000.0   # 만원 (2366.7/0.1536, 중앙값)

CAPITAL, METRO_ETC = {1, 4, 9}, {2, 3, 5, 6, 7, 8}
SPECIAL_CITY = ('수원시', '고양시', '용인시', '창원시')     # 특례시 → 대도시


# ── 보조 함수 ──────────────────────────────────────────────────────────────
def _band_idx(age):
    a = np.asarray(age)
    out = np.full(len(a), 6, dtype=int)
    for i, (lo, hi) in enumerate(AGE_BANDS):
        out[(a >= lo) & (a <= hi)] = i
    return out


def _region_class(sido, name):
    """대도시 / 중소도시 / 농어촌 (2022 사업안내 지역구분)."""
    out = np.empty(len(sido), dtype=object)
    for i, (s, n) in enumerate(zip(sido, name)):
        n = str(n)
        if s in (1, 2, 3, 4, 5, 6, 7) or n in SPECIAL_CITY:
            out[i] = 'metro'
        elif s in (8, 17):
            out[i] = 'city'
        else:
            out[i] = 'rural' if n.endswith('군') else 'city'
    return out


def _zone(sido):
    return np.where(np.isin(sido, list(CAPITAL)), 'capital',
                    np.where(np.isin(sido, list(METRO_ETC)), 'metro_etc', 'province'))


def _decile_values(g, dec, means, edges, floor=0.0):
    """분위 dec(0-base) 별로 구간 로그균등 추출 후 분위 평균을 means 에 정확히 맞춘다."""
    v = np.zeros(len(dec))
    for k in range(len(means)):
        m = (dec == k)
        c = int(m.sum())
        if c == 0:
            continue
        if means[k] <= floor:
            v[m] = max(means[k], 0.0)
            continue
        lo, hi = edges[k], edges[k + 1]
        x = np.exp(g.uniform(np.log(lo), np.log(hi), c))
        v[m] = x * (means[k] / x.mean())
    return v


def _ln1(g, mean, sigma):
    """평균이 mean 인 로그정규 1개 (스칼라)."""
    if mean <= 0:
        return 0.0
    mu = np.log(mean) - sigma ** 2 / 2.0
    return float(g.lognormal(mu, sigma))


def _edges_from_means(means, lo_mult=0.45, hi_mult=4.0):
    """분위 평균 사이 기하평균을 경계로. 첫/마지막 구간은 배수로 연장."""
    m = np.asarray(means, float)
    inner = np.sqrt(m[:-1] * m[1:])
    return np.concatenate([[m[0] * lo_mult], inner, [m[-1] * hi_mult]])


def _tenure_prob(sido_code, cls, sido_table):
    """시도 주변분포(MLTM6909) × 소득계층 조정(MLTM6908) → (자가, 임차, 무상)."""
    base = np.array(sido_table[sido_code], float)
    adj = np.array(TEN_BY_CLASS[cls], float) / np.array(TEN_ALL, float)
    p = base * adj
    return p / p.sum()


def generate(df, params, ctx):
    g = core.rng('B05')
    n = len(df)

    # ── 가구 프레임 ────────────────────────────────────────────────────────
    hh = (df[df['head'] == 1][['hid', 'age', '_sido', '_sigungu_name', 'hnum', '_u_income']]
          .rename(columns={'age': 'h_age'}).reset_index(drop=True))
    hh['hnum'] = df.groupby('hid')['hid'].size().reindex(hh['hid']).values
    nh = len(hh)
    hidx = pd.Series(np.arange(nh), index=hh['hid'].values)
    row_h = hidx.reindex(df['hid'].values).values          # 개인 → 가구 index

    hh['rclass'] = _region_class(hh['_sido'].values, hh['_sigungu_name'].values)
    rc = hh['rclass'].values
    hh['zone'] = _zone(hh['_sido'].values)
    band = _band_idx(hh['h_age'].values)

    # ── 1) 균등화 일차소득 분위 (R02 표2-15 조건부) ─────────────────────────
    p_inc = T215 / T215.sum(axis=0, keepdims=True)          # P(소득분위 | 연령대)
    cdf = np.cumsum(p_inc, axis=0)
    u = hh['_u_income'].values
    d_inc = np.array([int(np.searchsorted(cdf[:, band[i]], u[i])) for i in range(nh)])
    d_inc = np.clip(d_inc, 0, 9)

    # ── 2) `_h_eq_inc` 값 (R02 표2-14 분위 평균) ───────────────────────────
    pos_means = np.array(EQINC_DEC, float)
    edges = _edges_from_means(np.maximum(pos_means, 1.0))
    eq = _decile_values(g, d_inc, pos_means, edges)
    m1 = (d_inc == 0)                                        # 1분위 평균 -133만원(결손)
    if m1.sum():
        x = g.gamma(1.4, 1.0, int(m1.sum()))
        eq[m1] = -x * (133.0 / max(x.mean(), 1e-9))
    m2 = (d_inc == 1)
    if m2.sum():
        x = g.uniform(0, 1, int(m2.sum()))
        eq[m2] = x * (65.0 / max(x.mean(), 1e-9))
    h_eq_inc = eq * MAN
    h_minc = h_eq_inc * np.sqrt(hh['hnum'].values)

    # 선행 블록(B03)의 실제 개인 일차소득이 있으면 그것을 우선한다.
    inc_cols = [c for c in ('p_labinc', 'p_dainc', 'p_binc', 'p_fininc',
                            'p_reinc', 'p_pripeninc', 'p_othinc') if c in df.columns]
    if '_p_earned' in df.columns or len(inc_cols) >= 4:
        s = (df[inc_cols].fillna(0).sum(axis=1) if len(inc_cols) >= 4
             else df['_p_earned'].fillna(0))
        hsum = s.groupby(df['hid']).sum().reindex(hh['hid']).values
        h_minc = hsum.astype(float)
        h_eq_inc = h_minc / np.sqrt(hh['hnum'].values)
        d_inc = np.clip((pd.Series(h_eq_inc).rank(pct=True).values * 10).astype(int), 0, 9)

    # ── 3) 점유형태 ────────────────────────────────────────────────────────
    ten = pd.read_csv(os.path.join(RAW, 'PROP_MLTM6909_행정구역별점유형태_2022.csv'))
    sido_name2code = {'서울': 1, '부산': 2, '대구': 3, '인천': 4, '광주': 5, '대전': 6, '울산': 7,
                      '세종': 8, '경기': 9, '강원': 10, '충북': 11, '충남': 12, '전북': 13,
                      '전남': 14, '경북': 15, '경남': 16, '제주': 17}
    tt = {}
    for nm, code in sido_name2code.items():
        sub = ten[(ten['시도구분'] == nm) & (ten['년(Annual)'] == 2022)]
        d = dict(zip(sub['점유형태'], sub['비율_pct']))
        tt[code] = (d.get('자가', TEN_ALL[0]), d.get('임차', TEN_ALL[1]), d.get('무상', TEN_ALL[2]))
    det = pd.read_csv(os.path.join(RAW, 'PROP_MLTM5402_행정구역별세부점유형태_2019.csv'))
    dsplit = {}
    for nm, code in sido_name2code.items():
        s = det[(det['시도'] == nm)]
        d = dict(zip(s['점유형태'], s['비율_pct']))
        v = np.array([d.get('전세', 0.0), d.get('보증금 있는 월세', 0.0),
                      d.get('보증금 없는 월세', 0.0) + d.get('사글세', 0.0)], float)
        dsplit[code] = v / v.sum() if v.sum() > 0 else np.array([.40, .52, .08])

    # 주거실태조사 소득계층: 저소득층 1~4분위 / 중소득층 5~8분위 / 고소득층 9~10분위
    cls = np.where(d_inc <= 3, 'low', np.where(d_inc <= 7, 'mid', 'high'))
    # 주택연금(rm_yn) 가입자는 주택 소유자여야 한다 (§7 R19).
    # 단 rm_yn 을 만드는 B34 는 order 7 로 B05(order 5)보다 **뒤**에 실행되므로 평시에는 이 분기가
    # 작동하지 않는다. R19 준수는 B34 쪽에서 ptax_housing>0 ∧ age≥55 인 개인만 고르는 방식으로
    # 이루어져야 한다(실행순서상 B34 가 ptax_housing 을 볼 수 있다). 아래는 순서가 바뀔 경우의 안전장치.
    rm_p = (df['rm_yn'].fillna(0).values == 1) if 'rm_yn' in df.columns else np.zeros(n, bool)
    rm_hh = np.zeros(nh, bool)
    if rm_p.any():
        idx_hh = pd.Series(rm_p.astype(int), index=df['hid'].values).groupby(level=0).max()
        rm_hh = idx_hh.reindex(hh['hid']).fillna(0).values.astype(bool)
    tenure = np.empty(nh, dtype=object)
    for i in range(nh):
        p = _tenure_prob(int(hh['_sido'].values[i]), cls[i], tt)
        k = g.choice(3, p=p)
        if k == 0:
            tenure[i] = 'own'
        elif k == 2:
            tenure[i] = 'free'
        else:
            sp = dsplit[int(hh['_sido'].values[i])]
            tenure[i] = ['jeonse', 'wolse_dep', 'wolse_nodep'][int(g.choice(3, p=sp))]
    tenure[rm_hh] = 'own'

    # ── 4) 재산분위 (코퓰러 × 연령 × 점유형태) ─────────────────────────────
    p_pi = T223 / T223.sum(axis=1, keepdims=True)            # P(재산분위 | 소득분위) R01 표2-23
    p_pa = T216 / T216.sum(axis=0, keepdims=True)            # P(재산분위 | 연령대)  R02 표2-16
    # 점유형태 기울기 [논리적추론] — 자가 가구는 부동산(시가표준액)을 보유하므로 상위
    # 재산분위, 임차·무상 가구는 부동산 보유가 적어 하위 재산분위에 몰린다.
    TILT = {'own':          np.array([0.00, 0.45, 1.20, 1.55, 1.75, 1.90, 2.00, 2.05, 2.10]),
            'jeonse':       np.array([2.05, 1.35, 1.00, 0.78, 0.60, 0.46, 0.36, 0.28, 0.22]),
            'wolse_dep':    np.array([2.45, 1.45, 1.00, 0.70, 0.46, 0.32, 0.24, 0.18, 0.14]),
            'wolse_nodep':  np.array([3.10, 1.05, 0.60, 0.38, 0.26, 0.18, 0.13, 0.10, 0.08]),
            'free':         np.array([2.70, 1.15, 0.80, 0.58, 0.44, 0.34, 0.28, 0.24, 0.20])}
    W = np.zeros((nh, 9))
    for i in range(nh):
        w = p_pi[d_inc[i]] * (p_pa[:, band[i]] / PROP_MARG) * TILT[tenure[i]]
        W[i] = w / w.sum()
    # 주변분포 정합: 기대 분위 점수로 순위를 매겨 R02 <표 2-16> 전체 비율대로 절단
    # (§4.1 'IPF 1회' 원칙 준수 — 반복 조정 없이 1회 순위절단으로 주변분포를 정확히 복원)
    score = (W * np.arange(9)).sum(axis=1) + g.normal(0, 0.28, nh)
    ordr = np.argsort(score, kind='stable')
    cutp = np.cumsum(PROP_MARG) / PROP_MARG.sum()
    cuts = np.searchsorted(np.arange(1, nh + 1) / nh, cutp)
    d_prop = np.zeros(nh, dtype=int)
    prev = 0
    for k in range(9):
        d_prop[ordr[prev:cuts[k]]] = k
        prev = cuts[k]
    d_prop[ordr[prev:]] = 8
    d_prop[rm_hh] = np.maximum(d_prop[rm_hh], 2)      # 주택연금 가구는 재산 4분위 이상

    # ── 5) `_h_prop` 값 ────────────────────────────────────────────────────
    pm = np.array(PROP_DEC[2:], float)                       # 3~10분위 평균(만원)
    pedges = _edges_from_means(pm, lo_mult=0.42, hi_mult=5.0)
    prop = np.zeros(nh)
    hi_mask = d_prop >= 1
    dd = (d_prop[hi_mask] - 1)
    prop[hi_mask] = _decile_values(g, dd, pm, pedges)
    # 재산 분위 목표값(만원). 임차보증금이 이 위에 더해지므로 부동산(시가표준액) 몫은
    # PTAX_SCALE 로 축소해 h_prop 전체 평균이 R02 <표 2-14> 전체 평균(36,423만원)에 맞도록 한다.
    PTAX_SCALE = 1.00
    h_ptax_target = prop * PTAX_SCALE * MAN                   # 1-2분위 = 0원

    # ── 6) 임차보증금·월차임 ───────────────────────────────────────────────
    ee_dep = np.zeros(nh)
    ee_rent = np.zeros(nh)
    zr = hh['zone'].values
    for i in range(nh):
        t = tenure[i]
        if t in ('own', 'free'):
            continue
        z, c = REGION_RENT[zr[i]], cls[i]
        if t == 'jeonse':
            mu = z['jeonse'] * (CLASS_RENT[c]['jeonse'] / NAT_RENT['jeonse'])
            ee_dep[i] = _ln1(g, mu, 0.55)
        elif t == 'wolse_dep':
            mu = z['wdep'] * (CLASS_RENT[c]['wdep'] / NAT_RENT['wdep'])
            ee_dep[i] = _ln1(g, mu, 0.75)
            mr = z['wrent'] * (CLASS_RENT[c]['wrent'] / NAT_RENT['wrent'])
            ee_rent[i] = _ln1(g, mr, 0.45)
        else:
            mr = z['nodep'] * (CLASS_RENT[c]['nodep'] / NAT_RENT['nodep'])
            ee_rent[i] = _ln1(g, mr, 0.45)
    ee_dep *= MAN
    ee_rent *= MAN
    # 확정일자DB + 임대차신고DB 포착 규칙
    #   「부동산 거래신고 등에 관한 법률 시행령」 제4조의3 : 보증금 6천만원 초과 또는
    #   월차임 30만원 초과인 주택임대차는 신고 대상(신고지역 = 특별자치시·도, 시, 광역시·경기도의 군, 구)
    #   → 신고대상 계약은 포착률 0.92, 그 밖의 소액계약은 확정일자 자발적 취득분만 0.50 [가정]
    is_rent = np.isin(tenure, ['jeonse', 'wolse_dep', 'wolse_nodep'])
    reportable_area = ~((np.isin(hh['_sido'].values, [10, 11, 12, 13, 14, 15, 16]))
                        & (rc == 'rural'))
    reportable = ((ee_dep > 6000 * MAN) | (ee_rent > 30 * MAN)) & reportable_area
    p_cap = np.where(reportable, 0.92, 0.35)
    miss = is_rent & (g.random(nh) > p_cap)
    ee_dep[miss] = 0.0
    ee_rent[miss] = 0.0
    # 코드북 h_prop = 시가표준액 3종 + 임차보증금 → 부동산 목표값에 보증금을 **가산**한다.
    # (R02 <표 2-14>는 2기 자료로 전월세 보증금 일부가 누락되어 있다고 원문 p.78이 명시하므로,
    #  보증금 수준은 S2 원기관(주거실태조사 2022)에 맞추고 부동산 몫만 S0 분위 구조를 따른다.)
    # 부동산 보유 여부: 가계금융복지조사 2022 부동산 보유가구 68.34%
    #   자가(58.4%) 전원 + 비자가 가구의 33% → 약 68%(추출 후 실현치 67%)  [1차확인 GFS 표1-10]
    is_own_arr = (tenure == 'own')
    has_re = is_own_arr | (core.bernoulli(g, np.full(nh, 0.33)).astype(bool)) | rm_hh
    # ── 7) 재산세 시가표준액 3종 분해 ──────────────────────────────────────
    ptax_tot = np.where(has_re, h_ptax_target, 0.0)
    h_prop = ptax_tot + ee_dep
    is_own = is_own_arr
    sh_own = np.array([0.80, 0.17, 0.03])       # 자가: 주택·토지·건축물
    sh_oth = np.array([0.35, 0.55, 0.10])       # 임차/무상 보유 부동산
    land = np.zeros(nh); house = np.zeros(nh); bld = np.zeros(nh)
    for i in range(nh):
        if ptax_tot[i] <= 0:
            continue
        base = sh_own if is_own[i] else sh_oth
        keep = np.array([1.0 if (is_own[i] or rm_hh[i]) else (1.0 if g.random() < 0.38 else 0.0),
                         1.0 if g.random() < (0.60 if is_own[i] else 0.62) else 0.0,
                         1.0 if g.random() < (0.24 if is_own[i] else 0.18) else 0.0])
        if keep.sum() == 0:
            keep[0] = 1.0
        w = g.dirichlet(base * 8.0) * keep
        if w.sum() <= 0:
            w = keep
        w = w / w.sum()
        house[i], land[i], bld[i] = ptax_tot[i] * w

    # ── 8) 임대인 (or_*) ───────────────────────────────────────────────────
    own_any = (ptax_tot > 0)
    score = np.where(own_any, (d_prop + 1) / 9.0, 0.0)
    p_ll = np.clip(score ** 2.2, 0, 1)
    p_ll = p_ll * (LANDLORD_SHARE / max(p_ll.mean(), 1e-9)) * 1.08
    is_ll = core.bernoulli(g, np.clip(p_ll, 0, 0.95)).astype(bool)
    sig = np.sqrt(2.0 * np.log(LANDLORD_MEAN / LANDLORD_MED))
    or_dep = np.zeros(nh); or_rent = np.zeros(nh)
    k = int(is_ll.sum())
    if k:
        or_dep[is_ll] = core.lognormal_mean(g, np.full(k, LANDLORD_MEAN), sig, k) * MAN
        has_m = g.random(k) < 0.60          # 임차계약 중 월세 비중(2019 계열 60.4%)
        amt = core.lognormal_mean(g, np.full(k, NAT_RENT['wrent'] * 1.3), 0.80, k) * MAN
        or_rent[is_ll] = np.where(has_m, amt, 0.0)

    # ── 9) 개인 배분 ───────────────────────────────────────────────────────
    role = df['_role'].values
    is_head = (df['head'].values == 1)
    is_sp = (role == 'spouse')
    has_sp = pd.Series(is_sp, index=df['hid'].values).groupby(level=0).max().reindex(hh['hid']).values

    order = np.argsort(row_h, kind='stable')
    bounds = np.searchsorted(row_h[order], np.arange(nh + 1))
    ROWS = [order[bounds[i]:bounds[i + 1]] for i in range(nh)]

    def _assign(hval, p_head, p_sp, joint=0.0, prefer=None):
        """가구값 → 개인. p_head/p_sp/나머지, joint 확률로 부부 공동명의(50:50)."""
        out = np.zeros(n)
        pick = g.random(nh); jr = g.random(nh)
        for i in range(nh):
            if hval[i] <= 0:
                continue
            rows = ROWS[i]
            if prefer is not None:
                pf = rows[prefer[rows]]
                if len(pf):
                    out[pf[0]] += hval[i]
                    continue
            hd = rows[is_head[rows]]
            sp = rows[is_sp[rows]]
            ot = rows[~is_head[rows] & ~is_sp[rows]]
            if len(sp) and jr[i] < joint:
                out[hd[0]] += hval[i] * 0.5
                out[sp[0]] += hval[i] * 0.5
                continue
            ph, ps = (p_head, p_sp) if len(sp) else (p_head + p_sp, 0.0)
            if len(ot) == 0:
                ph, ps = ph / (ph + ps), ps / (ph + ps)
            x = pick[i]
            if x < ph or len(rows) == 1:
                out[hd[0]] += hval[i]
            elif x < ph + ps and len(sp):
                out[sp[0]] += hval[i]
            elif len(ot):
                out[int(g.choice(ot))] += hval[i]
            else:
                out[hd[0]] += hval[i]
        return out

    p_land = _assign(land, 0.75, 0.20, joint=0.15)
    p_house = _assign(house, 0.75, 0.20, joint=0.15, prefer=rm_p if rm_p.any() else None)
    p_bld = _assign(bld, 0.75, 0.20, joint=0.15)
    p_eedep = _assign(ee_dep, 0.80, 0.15)
    p_eerent = _assign(ee_rent, 0.80, 0.15)
    p_ordep = _assign(or_dep, 0.80, 0.20)
    p_orrent = _assign(or_rent, 0.80, 0.20)

    # ── 10) ptax_sum (원) ──────────────────────────────────────────────────
    only_home = np.isin(row_h, np.flatnonzero(is_own)) & (p_land + p_bld <= 0)
    fmv_h = np.where(only_home, FMV['house1'], FMV['house'])
    ptax_sum = (p_house * fmv_h * EFF['house']
                + p_land * FMV['land'] * EFF['land']
                + p_bld * FMV['building'] * EFF['building'])

    has_ptax = (p_land + p_house + p_bld) > 0
    is_tenant = np.isin(row_h, np.flatnonzero(np.isin(tenure, ['jeonse', 'wolse_dep', 'wolse_nodep'])))
    has_lease = (p_eedep + p_eerent > 0) | (p_ordep + p_orrent > 0)

    out = pd.DataFrame(index=df.index)
    nan = np.nan
    out['ptax_yn'] = np.where(has_ptax, 1.0, nan)
    out['ptax_sum'] = np.where(has_ptax, np.rint(ptax_sum), nan)
    out['ptax_land'] = np.where(has_ptax, np.rint(p_land), nan)
    out['ptax_housing'] = np.where(has_ptax, np.rint(p_house), nan)
    out['ptax_building'] = np.where(has_ptax, np.rint(p_bld), nan)
    out['or_deposit_amt_ptot'] = np.where(has_lease, np.rint(p_ordep), nan)
    out['or_monthly_rent_amt_ptot'] = np.where(has_lease, np.rint(p_orrent), nan)
    out['ee_deposit_amt_ptot'] = np.where(has_lease, np.rint(p_eedep), nan)
    out['ee_monthly_rent_amt_ptot'] = np.where(has_lease, np.rint(p_eerent), nan)

    # p_* : 무정보 사례 0원 처리 (전 개인)
    out['p_ptax_land'] = np.rint(p_land)
    out['p_ptax_housing'] = np.rint(p_house)
    out['p_ptax_building'] = np.rint(p_bld)
    out['p_ee_deposit_amt_ptot'] = np.rint(p_eedep)
    out['p_prop'] = out[['p_ptax_land', 'p_ptax_housing',
                         'p_ptax_building', 'p_ee_deposit_amt_ptot']].sum(axis=1)

    hidv = df['hid'].values
    for src, dst in [('p_ptax_land', 'h_ptax_land'), ('p_ptax_housing', 'h_ptax_housing'),
                     ('p_ptax_building', 'h_ptax_building'),
                     ('p_ee_deposit_amt_ptot', 'h_ee_deposit_amt_ptot'), ('p_prop', 'h_prop')]:
        out[dst] = out[src].groupby(hidv).transform('sum').values
    for c in [c for c in out.columns if c.startswith(('p_', 'h_'))]:
        out[c] = out[c].astype('int64')

    # ── 11) 소득인정액 (2022 국민기초생활보장 사업안내 산식) ────────────────
    basic = np.array([BASIC_PROP[x] for x in rc], float)
    cap = np.array([HOUSE_CAP[x] for x in rc], float)
    h_house = pd.Series(out['p_ptax_housing'].values).groupby(hidv).sum().reindex(hh['hid']).values.astype(float)
    h_land = pd.Series(out['p_ptax_land'].values).groupby(hidv).sum().reindex(hh['hid']).values.astype(float)
    h_bld = pd.Series(out['p_ptax_building'].values).groupby(hidv).sum().reindex(hh['hid']).values.astype(float)
    h_dep = pd.Series(out['p_ee_deposit_amt_ptot'].values).groupby(hidv).sum().reindex(hh['hid']).values.astype(float)

    resid_home = np.where(is_own, h_house, 0.0)                     # 거주 주택
    housing_asset = resid_home + h_dep * DEPOSIT_RATE               # 주거용재산 후보
    res_house = np.minimum(housing_asset, cap)                      # 한도 내 = 주거용
    over = housing_asset - res_house                                # 한도 초과 → 일반재산
    general = h_land + h_bld + np.where(is_own, 0.0, h_house) + over

    ded = basic.copy()
    d1 = np.minimum(res_house, ded); res_house -= d1; ded -= d1
    d2 = np.minimum(general, ded); general -= d2
    conv = res_house * R_HOUSE + general * R_GENERAL                # 원/월

    eval_inc = np.maximum(h_minc, 0.0) / 12.0 * (1.0 - EARN_DEDUCT * LABOR_SHARE)
    recog = eval_inc + conv
    rank = pd.Series(recog).rank(pct=True, method='average').values

    out['_h_prop'] = out['h_prop'].values
    out['_h_minc_prelim'] = np.rint(h_minc)[row_h].astype('int64')
    out['_h_eq_inc'] = np.rint(h_eq_inc)[row_h].astype('int64')
    out['_recog_inc'] = np.rint(recog)[row_h]
    out['_recog_rank'] = rank[row_h]
    out['_tenure'] = np.asarray(tenure, dtype=object)[row_h]
    out['_region_class'] = rc[row_h]
    realized = pd.Series(h_prop)
    rk = realized.rank(pct=True, method='average').values
    dec_real = np.clip((rk * 10).astype(int) + 1, 1, 10)
    dec_real[h_prop <= 0] = 1
    out['_prop_dec'] = dec_real[row_h]
    out['_prop_dec_target'] = (d_prop + 1)[row_h]
    out['_inc_dec'] = (d_inc + 1)[row_h]
    return out
