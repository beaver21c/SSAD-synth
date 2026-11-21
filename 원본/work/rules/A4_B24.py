# -*- coding: utf-8 -*-
"""B24 국민기초생활보장 생계·의료·주거·교육급여 (nbls_*)  — A4 / order 5 / 21변수

소스 (등급순, 전사본은 모두 params/raw 에 보존, 접근일 2026-09-02)
  S1 R03 보건복지부 「2022년 국민기초생활보장 수급자 현황」(국가승인통계 2023.7)  ← 1순위
       params/raw/R03_2022년국민기초생활보장수급자현황.pdf
       · PDF p5  <2022년도 급여별 수급자 선정기준>  → 기준중위소득 / 30·40·46·50%
       · PDF p13 <2022년 임차급여 지급기준: 기준 임대료>  (급지×가구원수)
       · PDF p14 <2022년도 교육급여액 기준>              (초 331,000·중 466,000·고 554,000)
       · 표1  수급자 종류별(일반/시설)   R03_표1_수급자현황_수급자종류별시도별.csv
       · 표5  급여종류별 수급자·가구     R03_표5_급여별수급자현황_급여유형별시도별.csv
       · 표9  가구원수별 수급가구        R03_표9_일반수급가구_가구원수별현황.csv
       · 표10 가구유형별 수급가구        R03_표10_*.csv
       · 표15/16 소득평가액 분포 · 표25 재산가액 분포 · 표33 소득인정액 평균
  S1 R05 보건복지부 「2023 보건복지통계연보」(2022 실적)
       · 표3-4-1 의료급여 대상자 유형별(1종/2종, 기초·시설·타법)
       · 표3-4-2/3/4 연령별·1종·2종
       · 표5-4-6 기초생활보장 급여집행실적(급여종류별)
  S1 R07 복지사업 월별 급여지급 현황 (data.go.kr 15009571)
       params/raw/R07_연간집계_서비스별_건당평균지급액_2022.csv
  S1 R08 복지사업 월별 시도별 수급권자 현황 (15009570)
       params/raw/R08_월별수급권자_연중변동지표_2022.csv       → dur 의 평균개월·탈락비중
  S1 R06 복지사업 시군구별 수급권자 현황 (15062448)             → 시도 조건부 수급률
  S1 국민건강보험공단 노인 의료급여수급권자 틀니·임플란트 급여 신청현황
       (data.go.kr 15112423) params/raw/R05b_15112423_*.csv
  S0 R02 <표 2-20> 정부공표 vs 행정데이터 생계급여 수급률(2021)
       → 행정데이터는 등록센서스 **일반가구** 표본이라 시설수급자가 빠진다는 근거.
         본 블록은 정부 총량에서 **시설수급자를 명시적으로 차감한 일반가구 총량**을 목표로 한다.

급여 간 포함관계 (2026-09-02 정정) — 원문 근거
  · R03 <표5> 주석: "총 수급자 수 및 가구 수는 시설 수급자 포함, **각 급여별 중복을 제외한 숫자임**"
      계 2,451,458 / 생계 1,566,570 / 의료 1,438,045 / 주거 2,260,783 / 교육 303,383
      ⇒ 주거급여 밖 수급자는 2,451,458 − 2,260,783 = 190,675명뿐이고, 그중 시설수급자가
        92,230명이므로 **일반가구에서 주거급여 밖은 98,445명**(= 교육급여 단독)이다.
  · R03 PDF p5 선정기준액: 생계 중위 30% < 의료 40% < 주거 46% < 교육 50%
      ⇒ 소득기준만으로는 생계 ⊂ 의료 ⊂ 주거 ⊂ 교육.
  · R03 PDF p4 부양의무자 기준: '15.7 교육급여 미적용 / '18.10 주거급여 폐지 /
      **'21.10 생계급여 전면 폐지**. 2022년에 부양의무자 기준이 남아 있는 급여는 **의료급여뿐**.
      ⇒ 소득요건(30%)을 충족해 생계급여를 받으면서도 의료급여 부양의무자 기준에서 탈락하는
        가구가 생겨 공표값이 생계 157만 > 의료 144만으로 역전된다(2019년 생계 123만 < 의료 140만
        → 2022년 역전, R05 표5-4-2 연도별). 따라서 **생계 ⊄ 의료** 이며 **의료 ⊄ 생계** 이다.
  · 결론(본 블록이 강제하는 구조): **생계 ⊂ 주거, 의료(기초법) ⊂ 주거,
      교육 단독 수급 98,445명만 주거 밖**. 의료급여의 타법·의료급여법 수급권자
      (85,370 + 686 = 86,056명, R05 표3-4-1)는 기초생활보장 수급자가 **아니다**.

생성 구조
  1) 가구단위 need 순위 (소득인정액비 r 기반 — B05 의 _recog_rank, 없으면 폴백)
  2) 의료급여 개인 마스크는 B31(order 3)의 nhi_type∈{7,8} 을 **그대로** 받는다 (§7 R08).
     그 가구 중 소득인정액 순위 상위 5.97% 를 타법·의료급여법(무자산조사)으로 갈라내고,
     나머지(기초법 의료급여 가구)를 수급가구·주거급여 가구에 **강제 편입**한다.
  3) 수급가구 = 기초의료급여 가구 ∪ 교육급여 가구(206,078) ∪ R03 표9 층화 충원
     → 주거급여 가구 = 수급가구 − 교육급여 단독가구(학생 98,445명분)
     → 생계급여 가구 ⊂ 주거급여 가구 (§7 R09 저소득·저재산 필터 안에서 need 순)
     → 수선유지급여 가구 ⊂ 주거급여 가구 (자가, 임차급여와 배타)
  4) 보장가구원 선정(비가구주 편입확률 캘리브레이션) → 개인 yn1
  5) dur: R07 지급건수·R08 연중변동으로 평균 개월수를 맞춘 π12 (core.dur_months)
  6) amt: 법정 산식(선정기준−소득인정액 / 기준임대료 / 교육급여 단가)
          → 가중 총액을 R07·R05 집행액에 맞추는 단일 계수 k 로 스케일
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'params/raw')

try:
    from scipy.special import ndtri as _ndtri
except Exception:                                    # scipy 부재 시 근사
    def _ndtri(p):
        p = np.clip(np.asarray(p, float), 1e-9, 1 - 1e-9)
        return np.sqrt(2) * np.vectorize(lambda x: _erfinv_scalar(2 * x - 1))(p)

    def _erfinv_scalar(x):
        from math import erf
        lo, hi = -6.0, 6.0
        for _ in range(50):
            m = (lo + hi) / 2
            if erf(m) < x: lo = m
            else: hi = m
        return (lo + hi) / 2

# ── [1차확인] R03 PDF p5 <2022년도 급여별 수급자 선정기준> (원/월) ────────────
MEDIAN_INC = {1: 1944812, 2: 3260085, 3: 4194701, 4: 5121080,
              5: 6024515, 6: 6907004, 7: 7780592}
SEL_LIVE  = {1: 583444, 2: 978026, 3: 1258410, 4: 1536324, 5: 1807355, 6: 2072101, 7: 2334178}
SEL_MEDI  = {1: 777925, 2: 1304034, 3: 1677880, 4: 2048432, 5: 2409806, 6: 2762802, 7: 3112237}
SEL_HOUSE = {1: 894614, 2: 1499639, 3: 1929562, 4: 2355697, 5: 2771277, 6: 3177222, 7: 3579072}
SEL_EDU   = {1: 972406, 2: 1630043, 3: 2097351, 4: 2560540, 5: 3012258, 6: 3453502, 7: 3890296}

# ── [1차확인] R03 PDF p13 기준임대료 (원/월) · 1급지 서울 / 2급지 경기·인천 /
#              3급지 광역시·세종 / 4급지 그 외 ───────────────────────────────
RENT_STD = {1: (327000, 253000, 201000, 163000),
            2: (367000, 283000, 224000, 183000),
            3: (437000, 338000, 268000, 218000),
            4: (506000, 391000, 310000, 254000),
            5: (524000, 404000, 320000, 262000),
            6: (621000, 478000, 379000, 310000),    # 6~7인
            8: (683000, 525000, 416000, 341000),    # 8~9인
            10: (751000, 577000, 457000, 375000)}   # 10~11인
GEUPJI = {1: 0, 4: 1, 9: 1, 2: 2, 3: 2, 5: 2, 6: 2, 7: 2, 8: 2}   # sido → 급지 idx (기본 3)

# ── [1차확인] R03 PDF p14 교육급여 교육활동지원비 (원/년, 연 1회) ────────────
EDU_ACT = (331000, 466000, 554000)          # 초 / 중 / 고

# ── [1차확인] 정부공표 2022 총량 — 일반가구 기준(시설수급자 차감) ────────────
T_HH_ALL    = 1699497            # R03 표1 일반수급자_가구
T_PER_ALL   = 2359228            # R03 표1 일반수급자_인원  (시설 92,230 별도)
T_HH_LIVE   = 1242549 - 92230    # 1,150,319
T_PER_LIVE  = 1566570 - 92230    # 1,474,340
T_HH_HOUSE  = 1628643            # 시설입소자는 주거급여 대상 아님 (R03 PDF p12)
T_PER_HOUSE = 2260783
T_HH_EDU    = 206078
T_PER_EDU   = 303383
T_HH_MEDI   = 1126712 - 92230    # 1,034,482  (기초의료급여 가구)
#  주거급여 밖 수급자 = 일반수급자 − 주거급여 수급자 = 교육급여 단독 수급자 [1차확인 유도]
T_PER_EDU_ONLY = T_PER_ALL - T_PER_HOUSE          # 98,445
# 의료급여 수급권자(국민기초+의료급여법+타법) — R05 표3-4-1 계 1,522,292 − 시설보호자 80,592
T_PER_MEDI = 1522292 - 80592     # 1,441,700
#  R05 표3-4-1 (2022, 시설보호자 80,592 제외한 1,441,700 기준)
#    국민기초생활보장법 = 1종 기초 998,019 + 2종 357,625 = 1,355,644   (0.94033)
#    의료급여법(행려 497 + 노숙 189)                    =       686   (0.00048)
#    타법 = 국가유공자 50,633 + 북한이탈주민 12,725 + 인간문화재 45 + 광주민주화 8,469
#           + 의사상자 1,259 + 국내입양아동 10,046 + 군입대자 2,193 =  85,370   (0.05922)
MEDI_LAW_SHARE = {1: (998019 + 357625) / 1441700,
                  2: (497 + 189) / 1441700,
                  3: (50633 + 12725 + 45 + 8469 + 1259 + 10046 + 2193) / 1441700}
MEDI_65PLUS = 170223 + 134671 + 112855 + 105478 + 102460    # R05 표3-4-2 65세+ 625,687

# ── [1차확인] R05 표3-4-3 / 3-4-4 연령대별 1종·2종 (2022) ────────────────────
MEDI_1J = {0: 956, 1: 7235, 5: 15338, 10: 26369, 15: 28340, 20: 13765, 25: 11801,
           30: 16106, 35: 22390, 40: 36454, 45: 51992, 50: 82779, 55: 103363,
           60: 138478, 65: 161898, 70: 131780, 75: 110737, 80: 103685, 85: 101263}
MEDI_2J = {0: 391, 1: 5107, 5: 14896, 10: 25565, 15: 37758, 20: 48686, 25: 18196,
           30: 8011, 35: 9660, 40: 18494, 45: 29157, 50: 43667, 55: 41314,
           60: 40399, 65: 8325, 70: 2891, 75: 2118, 80: 1793, 85: 1197}

# ── [1차확인] R07 연간 지급건수·금액 (2022) ─────────────────────────────────
R07_LIVE_CNT, R07_LIVE_AMT = 13424806, 6088198e6      # 생계급여(일반)
R07_HOUSE_CNT, R07_HOUSE_AMT = 25990980, 2538888e6    # 주거급여(임차)
R05_HOUSE_TOT, R05_EDU_TOT = 2720246e6, 150935e6      # R05 표5-4-6 집행 계
T_REPAIR_AMT = R05_HOUSE_TOT - R07_HOUSE_AMT          # 수선유지급여 총액 [논리적추론]

# ── [1차확인] R08 월별 수급권자 연중변동 (월1, 월12, 연평균, 양의변동합, 음의변동합)
R08 = {'live':  (1495706, 1566570, 1535775.2, 75197, 4333),
       'medi':  (1431787, 1438045, 1434529.8, 13207, 6949),
       'house': (2167116, 2260783, 2218523.6, 99416, 5749),
       'edu':   (309257,  303383,  300643.5,  22601, 28475)}

# ── [1차확인] data.go.kr 15112423 (2022): 틀니 48,846건 / 임플란트 52,637건 ──
DENT_CNT, IMPL_CNT, DENT_PERSON_RATIO = 48846, 52637, 0.75   # 0.75 = 건→인원 [가정]

# ── [1차확인] 국토교통부 2022년 주거급여 수선유지급여 단가 (경/중/대보수) ────
REPAIR_UNIT = np.array([4570000.0, 8490000.0, 12410000.0])
REPAIR_MIX = np.array([0.60, 0.25, 0.15])      # [가정] 보수유형 구성비

# ── [1차확인] R03 표9 일반수급가구 가구원수별 현황 (2022) ───────────────────
#   행정데이터에서 "수급가구"는 등록센서스 가구이고 수급자/수급가구 = 1.388 (표1)
#   → 표9 를 수급가구의 가구원수 분포 목표로 층화선정한다.
T9 = {1: 1234650, 2: 275663, 3: 110789, 4: 52134, 5: 19457, 6: 4963, 7: 1841}

# ── [1차확인] R03 표6 일반수급자 연령별 현황 (2022) → 연령 캘리브레이션 목표 ──
T6_65P = 232980 + 191775 + 174625 + 336685      # 936,065  (65세 이상)
T6_019 = 25829 + 75178 + 129601 + 145926        # 376,534  (0~19세)
#   0~6세 = 0-4 전부 + 5-9 의 2/5 (선형배분)  [논리적추론]
T6_006 = 25829 + 75178 * 2 / 5                  # 55,900

# ── [가정] 가구 선정 need 가점 (한부모·장애) — R03 표10 재현용 ───────────────
W_SINGLE_PARENT, W_DIS = 0.45, 0.40
JIT_LIVE, JIT_MEDI, JIT_HOUSE, JIT_EDU = 0.05, 0.14, 0.03, 0.06
BETA_A, BETA_B = 2.0, 1.267     # 생계급여율 f = 급여/선정기준 의 Beta 형상 [가정]
SIGMA_INC = 0.95                # 폴백 소득 로그정규 σ [가정]


# ══════════════════════════════════════════════════════════════════════════
def _scale8(tbl, n):
    """8인 이상 = 7인 + (7인−6인)×(n−7)  (R03 PDF p5 각주)"""
    n = int(n)
    if n <= 7:
        return float(tbl[max(n, 1)])
    return float(tbl[7] + (tbl[7] - tbl[6]) * (n - 7))


def _rent_std(k, j):
    k = int(k)
    key = 1 if k <= 1 else (k if k <= 5 else (6 if k <= 7 else (8 if k <= 9 else 10)))
    return float(RENT_STD[key][int(j)])


def _age_band_medi(a):
    a = int(a)
    if a == 0: return 0
    if a < 5: return 1
    return min((a // 5) * 5, 85)


def _p2jong(a):
    b = _age_band_medi(a)
    return MEDI_2J[b] / (MEDI_1J[b] + MEDI_2J[b])


def _income_capacity(age):
    """[가정] 연령별 월 소득능력(원) — B05(_recog_rank) 부재 시 폴백 산정용."""
    a = np.asarray(age, float)
    return np.where(a < 15, 0.0,
           np.where(a < 25, 900_000.0,
           np.where(a < 60, 2_600_000.0,
           np.where(a < 65, 1_500_000.0, 480_000.0))))


def _sido_factor():
    """R06(2022.12 시군구별 수급권자)을 시도 집계 → 주민등록 시도인구 대비 상대수급률."""
    try:
        r6 = pd.read_csv(os.path.join(RAW, 'R06_시군구별_수급권자_사업별_202212.csv'))
        r6 = r6[r6.사업명 == '기초생활보장(맞춤형급여)']
        pop = pd.read_csv(os.path.join(RAW, 'POPUL_MOIS01_2022_11_sigungu_age1_sex.csv'))
        pop = pop[(pop.level == 'sigungu') & (pop.sex.isin(['male', 'female']))]
        p = pop.groupby('sido')['pop'].sum()
        name2code = {'서울특별시': 1, '부산광역시': 2, '대구광역시': 3, '인천광역시': 4,
                     '광주광역시': 5, '대전광역시': 6, '울산광역시': 7, '세종특별자치시': 8,
                     '경기도': 9, '강원도': 10, '충청북도': 11, '충청남도': 12, '전라북도': 13,
                     '전라남도': 14, '경상북도': 15, '경상남도': 16, '제주특별자치도': 17}
        r6 = r6.assign(sido=r6.시도.map(name2code)).dropna(subset=['sido'])
        gsum = r6.groupby('sido')['수급권자수'].sum()
        p.index = p.index.astype(int)
        rate = (gsum / p.reindex(gsum.index.astype(int)).values).dropna()
        return {int(k): float(v) for k, v in (rate / rate.mean()).items()}
    except Exception:
        return {}


def _solve_threshold(key, weight, target_w, eligible=None):
    """key 오름차순 선택 시 Σweight 가 target_w 에 가장 가까워지는 마스크."""
    nn = len(key)
    m = np.ones(nn, bool) if eligible is None else np.asarray(eligible, bool)
    idx = np.flatnonzero(m)
    sel = np.zeros(nn, bool)
    if len(idx) == 0 or target_w <= 0:
        return sel
    o = idx[np.argsort(np.asarray(key)[idx], kind='stable')]
    cw = np.cumsum(np.asarray(weight, float)[o])
    k = int(np.searchsorted(cw, target_w)) + 1
    k = min(max(k, 1), len(o))
    if k > 1 and abs(cw[k - 2] - target_w) < abs(cw[k - 1] - target_w):
        k -= 1
    sel[o[:k]] = True
    return sel


def _alloc_weight(key, weight, target_w, eligible):
    """표본 셀이 5~6명뿐인 지표(노인 틀니·임플란트)용 가중총량 배정.
    _solve_threshold 는 무작위 순서의 누적합에서 자르므로 개인가중치(약 6~9천) 단위로
    ±20% 의 이산오차가 남는다. 여기서는 같은 무작위 순서를 훑되 |누적합−목표| 를
    줄이는 사람만 담아(그리디 부분합) 오차를 가중치 절반 수준까지 낮춘다."""
    nn = len(key)
    sel = np.zeros(nn, bool)
    idx = np.flatnonzero(np.asarray(eligible, bool))
    if len(idx) == 0 or target_w <= 0:
        return sel
    wv = np.asarray(weight, float)
    cur = 0.0
    for i in idx[np.argsort(np.asarray(key)[idx], kind='stable')]:
        if abs(cur + wv[i] - target_w) < abs(cur - target_w):
            sel[i] = True
            cur += wv[i]
    return sel


def _pi12(mean_dur):
    return float(np.clip((mean_dur - 6.0) / 6.0, 0.0, 1.0))


def _hh_table(df):
    sido = df['sido'] if 'sido' in df.columns else df['_sido']
    hw = df['hhwgt'] if 'hhwgt' in df.columns else pd.Series(1.0, index=df.index)
    t = pd.DataFrame({'hid': df['hid'].values, 'age': df['age'].values,
                      'head': df['head'].values, 'sido': np.asarray(sido),
                      'hhwgt': np.asarray(hw, float),
                      'ui': df['_u_income'].values, 'uw': df['_u_welfare'].values,
                      'sp': df['_is_single_parent'].values})
    gb = t.groupby('hid', sort=True)
    hh = pd.DataFrame({'hnum': gb.size(),
                       'sido': gb['sido'].first(),
                       'hhwgt': gb['hhwgt'].first(),
                       'n65': gb['age'].agg(lambda s: int((s >= 65).sum())),
                       'n_student': gb['age'].agg(lambda s: int(((s >= 7) & (s <= 18)).sum())),
                       'uw': gb['uw'].mean(),
                       'sp': gb['sp'].max()})
    ha = t.loc[t['head'] == 1].groupby('hid')['age'].first()
    hh['head_age'] = ha.reindex(hh.index).fillna(gb['age'].max())
    return hh


def _dis_flag(df, hids):
    if 'dis_yn' not in df.columns:
        return np.zeros(len(hids))
    s = pd.Series((df['dis_yn'].fillna(0) == 1).astype(float).values, index=df['hid'].values)
    return s.groupby(level=0).max().reindex(hids).fillna(0).values


# ══════════════════════════════════════════════════════════════════════════
def generate(df, params, ctx):
    g = core.rng('B24')
    n = len(df)
    out = pd.DataFrame(index=df.index)

    hh = _hh_table(df)
    hids = hh.index.values
    nh = len(hh)
    pos = pd.Series(np.arange(nh), index=hids).reindex(df['hid'].values).values
    w = hh['hhwgt'].values.astype(float)
    iw = (df['indwgt'].values if 'indwgt' in df.columns else np.ones(n)).astype(float)
    wp = np.bincount(pos, weights=iw, minlength=nh)          # 가구별 가중 인원

    hn = hh['hnum'].values
    hn_cat = np.minimum(hn, 7)
    med_std = np.array([_scale8(MEDIAN_INC, k) for k in hn])
    sl_live = np.array([_scale8(SEL_LIVE, k) for k in hn])
    sl_house = np.array([_scale8(SEL_HOUSE, k) for k in hn])
    sl_edu = np.array([_scale8(SEL_EDU, k) for k in hn])

    age_p = df['age'].values
    is_head = df['head'].values == 1
    isstu = (age_p >= 7) & (age_p <= 18)                     # 초·중·고 학령기
    is65 = age_p >= 65
    ispre = age_p <= 6
    wstu = np.bincount(pos[isstu], weights=iw[isstu], minlength=nh)
    has_stu = wstu > 0
    nstu = np.bincount(pos[isstu], minlength=nh).astype(float)   # 가구별 학령기 아동 수

    # ── 1) 가구 소득인정액비 순위 ────────────────────────────────────────────
    if '_recog_rank' in df.columns:                    # B05 (A2, order 5) 제공
        rr = pd.Series(np.asarray(df['_recog_rank'], float), index=df['hid'].values)
        rank0 = rr.groupby(level=0).first().reindex(hids).astype(float).values
        rank0 = np.where(np.isfinite(rank0), rank0, 0.5)
    else:                                              # 폴백 (B05 미구현)
        mult = np.exp(SIGMA_INC * _ndtri(np.clip(df['_u_income'].values, 1e-6, 1 - 1e-6)))
        pinc = _income_capacity(df['age'].values) * mult
        hinc = pd.Series(pinc, index=df['hid'].values).groupby(level=0).sum().reindex(hids).values
        rank0 = pd.Series(hinc / med_std).rank(pct=True).values

    sf = _sido_factor()
    sido_adj = np.array([-0.25 * np.log(max(sf.get(int(s), 1.0), 0.25)) for s in hh['sido'].values])
    n65 = hh['n65'].values
    npre = pd.Series((df['age'].values <= 6).astype(float), index=df['hid'].values
                     ).groupby(level=0).sum().reindex(hids).fillna(0).values
    need = (rank0
            - W_SINGLE_PARENT * (hh['sp'].values == 1)
            - W_DIS * _dis_flag(df, hids)
            + sido_adj
            + 0.10 * (hh['uw'].values - 0.5))
    jz = {k: g.normal(0, 1, nh) for k in ('house', 'live', 'edu', 'rep', 'all')}

    role_w = np.where(is_head, 1.0,
             np.where(age_p < 19, 0.90,
             np.where(is65, 0.85, 0.60)))
    u_mem = g.random(n)

    def members(mask_hh, target_per, base=None, force=None):
        """가구 마스크 → 보장가구원(개인) 마스크.
        비가구주 편입확률 p 를 이분탐색해 가중 총량(Σindwgt)을 목표에 맞춘다.
        base 가 주어지면 그 안에서만, force 는 반드시 포함한다(포함관계 강제)."""
        sel_hh = mask_hh[pos] if base is None else (mask_hh[pos] & base)
        f = np.zeros(n, bool) if force is None else (np.asarray(force, bool) & sel_hh)
        lo, hi = 0.0, 1.0
        for _ in range(40):
            p = (lo + hi) / 2
            m = f | (sel_hh & (is_head | (u_mem < np.clip(p * role_w, 0, 1))))
            if float((m * iw).sum()) < target_per: lo = p
            else: hi = p
        p = (lo + hi) / 2
        return f | (sel_hh & (is_head | (u_mem < np.clip(p * role_w, 0, 1))))

    # ── 2) 의료급여 — §7 R08: nbls_medi_yn1 ⇔ nhi_type∈{7,8} (B31 계약, order 3)
    #   B31 이 가구 단위로 배정한 의료급여 세대를 **그대로** 받는다. 개인 마스크는
    #   손대지 않고(R08 은 개인 XOR 검사), 가구 지표만 뽑아 포함관계의 기준으로 쓴다.
    if 'nhi_type' in df.columns:
        p_medi = df['nhi_type'].isin([7, 8]).to_numpy()
    else:                                              # 폴백 (B31 미구현)
        base_key = need + 0.14 * g.normal(0, 1, nh)
        mm = _solve_threshold(base_key, wp, T_PER_MEDI)
        p_medi = mm[pos]
    medi_hh = np.bincount(pos[p_medi], minlength=nh) > 0
    w_medi_p = float((iw * p_medi).sum())

    #   적용법 분리: 타법(국가유공자·북한이탈주민·입양아동 등 85,370명)·의료급여법
    #   (행려·노숙 686명)은 **소득·재산 조사 없이** 자격을 얻으므로 소득인정액 순위가
    #   높은 쪽에 분포한다 [논리적추론]. 이들은 기초생활보장 수급자가 아니다.
    sh_other = MEDI_LAW_SHARE[2] + MEDI_LAW_SHARE[3]
    medi_other_hh = _solve_threshold(-need, wp, sh_other * w_medi_p, eligible=medi_hh)
    medi_basic_hh = medi_hh & ~medi_other_hh           # 국민기초생활보장법 의료급여 가구
    p_medi_basic = p_medi & medi_basic_hh[pos]

    # ── 3) 수급가구 선정 — 포함관계를 구조로 강제한다 ────────────────────────
    #   R03 <표5> 주석 "각 급여별 중복을 제외한 숫자임" + 계 2,451,458 / 주거 2,260,783
    #   ⇒ 주거급여 밖 수급자는 190,675명뿐이고 그중 시설수급자가 92,230명이므로
    #     일반가구에서 주거급여 밖은 98,445명(=교육급여 단독)이다.
    #   선정기준액도 생계 30% < 의료 40% < 주거 46% < 교육 50% 이므로
    #     **생계 ⊂ 주거, 의료(기초) ⊂ 주거** 가 성립해야 한다.
    #   다만 부양의무자 기준은 2022년에도 **의료급여에만** 남아 있어(R03 PDF p4:
    #     '21.10 생계급여 부양의무자 기준 전면 폐지 / '18.10 주거 폐지 / '15.7 교육 미적용)
    #     생계(157만) > 의료(144만) 로 역전되고 **생계 ⊄ 의료** 가 된다.
    def build(a):
        """a = [65세+ 가점, 학생수 가점, 0~6세 가점] · 수급가구 집합을 만든다.

        a[1] 은 2026-09-02 에 '학령기 아동 보유(has_stu) 가점' → '**추가 학생 1인당** 가점'
        으로 바꿨다. 종전 has_stu 가점은 교육급여 가구 선정(ii)이 이미 가구수를
        T_HH_EDU(206,078)로 고정하고 충원(iii)이 has_stu 가구를 배제하므로
        **학생 수에 아무 영향이 없는 불용 손잡이**였고(모든 학생가구를 같은 크기만큼
        평행이동시킬 뿐 순위가 바뀌지 않는다), 그 결과 이분탐색이 상한 2.5 에 붙어
        교육급여 수급권자가 261,326명(-13.9%)에서 멈췄다.
        가구수가 고정된 이상 '가구당 학생 수'가 유일한 조절 손잡이이므로,
        R03 <표5> 의 두 값(가구 206,078 · 수급권자 303,383 ⇒ 가구당 1.472명)을 함께
        만족시키도록 다자녀 학생가구를 우선 선정한다.
        """
        sc = need - a[0] * (n65 > 0) - a[2] * (npre > 0) + 0.05 * jz['all']
        sc_edu = sc - a[1] * np.maximum(nstu - 1.0, 0.0)     # 학생 2명 이상 가구 우선
        m = medi_basic_hh.copy()                        # (i) 기초의료급여 가구는 강제 포함
        cap = {k: max(T9[k] - float(w[m & (hn_cat == k)].sum()), 0.0) for k in T9}
        #  (ii) 교육급여 가구 (R03 표5 206,078가구) — 가구원수 층화 상한 안에서 need 순
        tgt_edu = T_HH_EDU - float(w[m & has_stu].sum())
        pick = np.zeros(nh, bool)
        tot = 0.0
        for i in np.argsort(sc_edu):
            if tot >= tgt_edu: break
            k = int(hn_cat[i])
            if m[i] or medi_hh[i] or not has_stu[i] or cap[k] <= 0: continue
            pick[i] = True; cap[k] -= w[i]; tot += w[i]
        m |= pick
        #  (iii) 나머지는 R03 표9(가구원수별 수급가구)에 맞춰 층화 충원
        for k in T9:
            rest = T9[k] - float(w[m & (hn_cat == k)].sum())
            if rest <= 0: continue
            m |= _solve_threshold(sc, w, rest,
                                  eligible=(hn_cat == k) & ~m & ~medi_hh & ~has_stu)
        return sc, m

    #   연령가점 캘리브레이션 (좌표 이분탐색). 목표는 모두 [1차확인] R03 <표6>:
    #     65세+ 936,065 / 0~19세 376,534 / 0~6세 55,900.
    #   기초의료급여 가구가 강제 포함되므로 65세+ 가점은 대개 음수(감점)로 풀린다.
    #   교육급여(j=1)만 측정 기준이 다르다: 교육급여는 학생 개인에게 붙는 **수급권**이라
    #   보장가구원(members) 선정 여부와 무관하게 수급가구 안의 학령기 아동 전원이 대상이다.
    #   종전에는 members() 안의 학생 수로 재고 있어(=195,036) 목표 303,383 에 영원히
    #   닿지 못하고 a[1] 이 상한에 붙었다 — 목표식(측정식) 버그.
    A_TGT = [(is65, T6_65P, 'mem'), (isstu, float(T_PER_EDU), 'pool'), (ispre, T6_006, 'mem')]
    a = [0.0, 0.0, 0.0]
    for _ in range(4):
        for j in range(3):
            lo, hi = -2.5, 2.5
            for _ in range(18):
                mid = (lo + hi) / 2
                aa = list(a); aa[j] = mid
                _, mm = build(aa)
                if A_TGT[j][2] == 'pool':
                    v = float((iw * A_TGT[j][0] * mm[pos]).sum())
                else:
                    v = float((members(mm, T_PER_ALL) * iw * A_TGT[j][0]).sum())
                if v < A_TGT[j][1]: lo = mid
                else: hi = mid
            a[j] = (lo + hi) / 2
    sc_all, m_all = build(a)

    #  (iv) 교육급여 단독 수급가구 = 소득인정액이 주거 46% 선을 넘고 교육 50% 선 이하인
    #       학령기 아동 가구. 가중 학생수 합이 98,445명(=2,359,228−2,260,783)이 되게 뽑는다.
    m_eduonly = _solve_threshold(-sc_all, wstu, float(T_PER_EDU_ONLY),
                                 eligible=m_all & has_stu & ~medi_hh)
    m_house = m_all & ~m_eduonly                        # 주거급여 가구 (⊇ 기초의료급여 가구)

    #  (v) 생계급여 가구 ⊂ 주거급여 가구. §7 R09(생계 ⇒ 균등화소득 하위 ∧ 저재산) 강제.
    #      R09 가 실제로 검사하는 것은 _h_eq_inc ≤ 25분위뿐이므로, 후보가 목표 가구수에
    #      못 미치면 재산 조건(_h_prop ≤ 60분위)만 먼저 푼다 (B05 의 소득·재산 분포가
    #      바뀌어도 생계급여 총량이 무너지지 않게 하는 안전장치).
    def _hh_first(col):
        c = col if col in df.columns else col[1:]
        if c not in df.columns:
            return None
        return pd.Series(np.asarray(df[c], float), index=df['hid'].values
                         ).groupby(level=0).first().reindex(hids).values
    live_ok = m_house.copy()
    v_inc, v_prop = _hh_first('_h_eq_inc'), _hh_first('_h_prop')
    if v_inc is not None:
        live_ok &= (np.nan_to_num(v_inc, nan=-np.inf) <= np.nanquantile(v_inc, 0.25))
    live_ok_inc = live_ok.copy()
    if v_prop is not None:
        live_ok &= (np.nan_to_num(v_prop, nan=-np.inf) <= np.nanquantile(v_prop, 0.60))
    if float(w[live_ok].sum()) < T_HH_LIVE:
        live_ok = live_ok_inc
    m_live = _solve_threshold(need + JIT_LIVE * jz['live'], w, T_HH_LIVE, eligible=live_ok)

    #  (vi) 수선유지급여 가구 = 주거급여 가구 중 자가 거주자 (임차급여와 배타).
    #       주택을 소유한 수급가구이므로 소득인정액 순위가 상대적으로 높고(생계급여 밖),
    #       학령기 아동 가구를 제외해 교육급여 단독 수급자 총량(98,445)을 흐리지 않게 한다.
    t_rep_hh = T_REPAIR_AMT / float((REPAIR_UNIT * REPAIR_MIX).sum())
    m_rep = _solve_threshold(need + 0.5 * jz['rep'], w, t_rep_hh,
                             eligible=m_house & ~m_live & ~has_stu)
    if not m_rep.any():        # 학령기 조건만 풀고 생계급여 가구는 계속 제외한다
        m_rep = _solve_threshold(need + 0.5 * jz['rep'], w, t_rep_hh,
                                 eligible=m_house & ~m_live)

    # ── 4) 보장가구원 선정 → 개인 yn1 ───────────────────────────────────────
    #   주거급여 수급자에는 기초의료급여 가구원 전원과 **생계급여 보장가구원 전원**이
    #   포함된다(의료 ⊂ 주거, 생계 ⊂ 주거).
    #   ※ 2026-09-02 정정 — 종전에는 p_house_all 을 먼저 뽑고 그 안에서 생계급여
    #     보장가구원을 골랐다. 그런데 생계급여는 1,150,319가구에 1,474,340명(가구당 1.28명)
    #     으로 **가구원 편입률이 98%** 인 반면 주거급여는 1,628,643가구에 2,260,783명
    #     (편입률 92%)이라, 주거급여 편입률로 걸러진 뒤에는 생계급여 목표 인원에
    #     구조적으로 닿을 수 없었다(가능 최대 1,415,281명 < 1,474,340명).
    #     생계급여를 먼저 뽑고 주거급여가 그것을 force 로 흡수하면 두 총량이 모두 서고
    #     포함관계(생계 ⊂ 주거)도 그대로 유지된다.
    p_live = members(m_live, T_PER_LIVE)
    p_house_all = members(m_house, T_PER_HOUSE, force=(p_medi_basic | p_live))
    p_rep = p_house_all & m_rep[pos]
    p_house = p_house_all & ~m_rep[pos]                 # 임차급여 (nbls_house_yn1)

    #   교육급여 수급권자: 교육급여 단독가구의 학생 전원 + 주거급여 가구의 학생 일부
    #   교육급여는 **수급권**(nbls_edu_yn1 = 수급권 여부)이라 학생 개인에게 붙는다.
    #   임차급여 보장가구원(p_house_all)보다 넓게 잡아도 R03 <표5>의 급여별 인원과 어긋나지
    #   않는다(교육급여 수급권자 303,383 > 교육급여 가구 206,078 × 임차 보장가구원 몫).
    f_edu = isstu & m_eduonly[pos]
    rest_e = isstu & m_house[pos]
    p_edu = f_edu | _solve_threshold(need[pos] + 0.6 * g.normal(0, 1, n), iw,
                                     max(T_PER_EDU - float((f_edu * iw).sum()), 0.0),
                                     eligible=rest_e)

    #   기초생활보장 수급자 = 4개 급여의 합집합 (타법 의료급여는 제외)
    p_any = p_house_all | p_edu | p_medi_basic

    # ── 5) 수급기간 dur / 고정시점 yn2 ──────────────────────────────────────
    def dur_yn2(mask, mean_dur, exit_share):
        d = np.full(n, np.nan); y2 = np.full(n, np.nan)
        k = int(mask.sum())
        if k == 0:
            return d, y2
        d[mask] = core.dur_months(g, k, _pi12(mean_dur), 1, 11).astype(float)
        y2[mask] = 1.0
        short = mask & (d < 12)
        y2[short & (g.random(n) < exit_share)] = 0.0
        return d, y2

    mean_live = R07_LIVE_CNT / (T_HH_LIVE * (1 + R08['live'][4] / R08['live'][1]))
    mean_house = R07_HOUSE_CNT / (T_PER_HOUSE * (1 + R08['house'][4] / R08['house'][1]))
    mean_medi = (R08['medi'][2] * 12) / (R08['medi'][1] * (1 + R08['medi'][4] / R08['medi'][1]))
    mean_edu = (R08['edu'][2] * 12) / (R08['edu'][1] * (1 + R08['edu'][4] / R08['edu'][1]))
    ex = lambda k: R08[k][4] / (R08[k][3] + R08[k][4])

    d_live, y2_live = dur_yn2(p_live, mean_live, ex('live'))
    d_house, y2_house = dur_yn2(p_house, mean_house, ex('house'))
    d_edu, y2_edu = dur_yn2(p_edu, mean_edu, ex('edu'))
    d_medi, _ = dur_yn2(p_medi, mean_medi, 0.0)
    y2_medi = np.where(p_medi, 1.0, np.nan)   # nhi_type 이 12월 스냅숏 ⇒ 12.31 수급권 = 1

    # ── 6) 급여액 ───────────────────────────────────────────────────────────
    cnt_live = np.maximum(np.bincount(pos[p_live], minlength=nh), 1)
    sl_live_b = np.array([_scale8(SEL_LIVE, k) for k in cnt_live])
    f = g.beta(BETA_A, BETA_B, nh)
    if m_live.any():
        cur = float((sl_live_b[m_live] * f[m_live] * w[m_live]).sum() / w[m_live].sum())
        f = np.clip(f * ((R07_LIVE_AMT / R07_LIVE_CNT) / max(cur, 1.0)), 0.0, 1.0)
    live_hh_m = sl_live_b * f                                  # 가구 월 생계급여
    recog_inc = np.maximum(sl_live_b - live_hh_m, 0.0)         # 생계가구 소득인정액(원/월)

    amt_live = np.full(n, np.nan)
    v = (live_hh_m / cnt_live)[pos]
    amt_live[p_live] = v[p_live] * d_live[p_live]
    if p_live.any():                                           # 가중 총액 = R07 생계(일반)
        amt_live[p_live] *= R07_LIVE_AMT / max(float((amt_live[p_live] * iw[p_live]).sum()), 1.0)
    amt_live = np.where(p_live, np.round(amt_live), np.nan)

    cnt_house = np.maximum(np.bincount(pos[p_house], minlength=nh), 1)
    gj = np.array([GEUPJI.get(int(s), 3) for s in hh['sido'].values])
    rent = np.array([_rent_std(k, j) for k, j in zip(cnt_house, gj)])
    # 소득인정액: 생계수급가구는 위 산식, 그 밖의 수급가구는 (생계기준, 주거/교육기준] 사이
    upper = np.where(m_house, sl_house, sl_edu)
    ri = np.where(m_live, recog_inc, sl_live_b + (upper - sl_live_b) * g.random(nh))
    #  임차급여 최저 지급액 10,000원/월 (주거급여 실시에 관한 고시) → 0원 수급자 방지(§7 R24)
    house_hh_m = np.maximum(rent - 0.30 * np.maximum(ri - sl_live_b, 0.0), 10000.0)
    amt_house = np.full(n, np.nan)
    v = (house_hh_m / cnt_house)[pos]
    amt_house[p_house] = v[p_house] * d_house[p_house]
    if p_house.any():                                          # 가중 총액 = R07 주거(임차)
        amt_house[p_house] *= R07_HOUSE_AMT / max(float((amt_house[p_house] * iw[p_house]).sum()), 1.0)
    amt_house = np.where(p_house, np.round(amt_house), np.nan)

    # 수선유지급여 (자가 수급가구) — 총액 = R05 표5-4-6 주거급여 계 − R07 임차급여
    cnt_rep = np.maximum(np.bincount(pos[p_rep], minlength=nh), 1)
    rtype = g.choice(3, size=nh, p=REPAIR_MIX)
    amt_own = np.full(n, np.nan)
    amt_own[p_rep] = (REPAIR_UNIT[rtype] / cnt_rep)[pos][p_rep]
    if p_rep.any():
        amt_own[p_rep] *= T_REPAIR_AMT / max(float((amt_own[p_rep] * iw[p_rep]).sum()), 1.0)
    amt_own = np.where(p_rep, np.round(amt_own), np.nan)

    # 교육급여
    lvl = np.where(age_p <= 12, 0, np.where(age_p <= 15, 1, 2))
    amt_e1 = np.where(p_edu, np.asarray(EDU_ACT, float)[lvl], np.nan)
    amt_e2 = np.full(n, np.nan)
    amt_e2[p_edu] = 0.0
    hi_m = p_edu & (lvl == 2)
    resid = R05_EDU_TOT - float(np.nansum(np.where(p_edu, amt_e1, 0.0) * iw))
    if hi_m.any() and resid > 0:
        base2 = resid / max(float((hi_m * iw).sum()), 1.0)
        amt_e2[hi_m] = base2 * np.exp(g.normal(0, 0.35, n))[hi_m]
        amt_e2[hi_m] *= resid / max(float((amt_e2[hi_m] * iw[hi_m]).sum()), 1.0)
    amt_e1 = np.where(p_edu, np.round(amt_e1), np.nan)
    amt_e2 = np.where(p_edu, np.round(np.nan_to_num(amt_e2)), np.nan)

    # ── 7) 의료급여 적용법·종별 / 노인 틀니·임플란트 ────────────────────────
    #   적용법은 (3)에서 가른 가구 구분을 그대로 쓴다 — 기초 1 / 의료급여법 2 / 타법 3.
    law = np.full(n, np.nan)
    law[p_medi_basic] = 1.0
    oth = p_medi & ~p_medi_basic
    if oth.any():
        p2 = MEDI_LAW_SHARE[2] / max(MEDI_LAW_SHARE[2] + MEDI_LAW_SHARE[3], 1e-12)
        law[oth] = core.choice_p(g, [2, 3], [p2, 1 - p2], int(oth.sum())).astype(float)
    #  종별: 연령별 2종 비율(R05 표3-4-3/4)을 상대확률로 유지하되, 2종 **가중 총량**이
    #  R05 표3-4-1 의 357,625명이 되도록 배정한다. 표본 내 의료급여 수급권자가 240명
    #  수준이라 베르누이 표집오차(±5%p)가 커서, 확률 pp 에 지수경쟁 키
    #  (-log U / pp, 작을수록 우선)를 씌우고 _solve_threshold 로 총량을 맞춘다.
    p2raw = np.array([_p2jong(a) for a in age_p])
    od2 = p2raw / np.maximum(1 - p2raw, 1e-9)
    pp2 = np.clip(od2 / (1 + od2), 1e-6, 1 - 1e-6)
    key2 = -np.log(np.clip(g.random(n), 1e-12, 1.0)) / pp2
    sel2 = _solve_threshold(key2, iw, 357625.0, eligible=p_medi)
    mtype = np.full(n, np.nan)
    mtype[p_medi] = 1.0
    mtype[sel2] = 2.0

    #  노인 틀니·임플란트: 65세 이상 의료급여 수급권자만 대상.
    #  표본 내 기대 수급자가 5~6명 수준이라 베르누이 표집오차가 커, 무작위 키에
    #  가중총량 할당(_solve_threshold)을 써서 Σindwgt 를 원자료 건수에 맞춘다.
    med65 = p_medi & (age_p >= 65)
    dent = np.where(p_medi, 0.0, np.nan)
    impl = np.where(p_medi, 0.0, np.nan)
    dent[_alloc_weight(g.random(n), iw, DENT_CNT * DENT_PERSON_RATIO, med65)] = 1.0
    impl[_alloc_weight(g.random(n), iw, IMPL_CNT * DENT_PERSON_RATIO, med65)] = 1.0

    # ── 8) 출력 (yn1 = 1 / 추출대상 밖 NaN) ────────────────────────────────
    yn1 = lambda m: np.where(m, 1.0, np.nan)
    out['nbls_live_yn1'] = yn1(p_live)
    out['nbls_live_yn2'] = y2_live
    out['nbls_live_dur'] = d_live
    out['nbls_live_amt'] = amt_live
    out['nbls_house_yn1'] = yn1(p_house)
    out['nbls_house_yn2'] = y2_house
    out['nbls_house_dur'] = d_house
    out['nbls_house_amt'] = amt_house
    out['nbls_house_own_amt'] = amt_own
    out['nbls_edu_yn1'] = yn1(p_edu)
    out['nbls_edu_yn2'] = y2_edu
    out['nbls_edu_dur'] = d_edu
    out['nbls_edu_amt1'] = amt_e1
    out['nbls_edu_amt2'] = amt_e2
    out['nbls_medi_yn1'] = yn1(p_medi)
    out['nbls_medi_yn2'] = y2_medi
    out['nbls_medi_dur'] = d_medi
    out['nbls_medi_law'] = np.where(y2_medi == 1, law, np.nan)
    out['nbls_medi_type'] = np.where(y2_medi == 1, mtype, np.nan)
    out['nbls_medi_implant_yn'] = impl
    out['nbls_medi_dentures_yn'] = dent

    # ── 헬퍼 (column_contract) ─────────────────────────────────────────────
    out['_is_nbls'] = p_any.astype(np.int8)
    out['_nbls_recog_inc'] = np.where(m_all[pos], ri[pos], np.nan)   # 소득인정액(원/월)
    out['_nbls_rank'] = pd.Series(need).rank(pct=True).values[pos]
    if '_recog_rank' not in df.columns:
        out['_recog_rank_fb'] = rank0[pos]
    return out
