# -*- coding: utf-8 -*-
"""B09 기타소득·원천징수사업소득·연말정산사업소득·일용소득 DB (18개)  (A2 / order 2)

  othinc_*  기타소득 지급명세서        ← NTS <4-4-8> 거주자의 기타소득 원천징수 신고 현황
  binc_*    원천징수사업소득 지급명세서 ← NTS <4-4-6> 거주자의 사업소득 원천징수 신고 현황
  ybinc_*   연말정산사업소득           ← NTS <4-3-1> 사업소득 연말정산Ⅰ(총괄) + <4-3-2>(성·연령)
  dainc_*   일용근로소득 지급명세서     ← NTS <4-4-10> 일용근로소득자별 지급명세서 제출 현황

■ 소스 (등급순)
  S1 국세청 국세통계 2023년 발행(2022년 귀속) TASIS 직접 조회분 [1차확인 2026-09-02]
     4-4-6 : 인원 8,473,541 / 연간지급금액 136,778,483백만원 / 소득세(원천징수분) 4,087,898백만원
             (성·연령·지급총액 10구간 × 인원·금액·소득세)
     4-4-8 : 인원 5,035,437 / 연간지급총액 17,529,946 / 소득금액 11,315,171 / 소득세 2,120,916
     4-3-1 : 인원 529,705 / 수입금액 8,960,951 / 소득금액 2,157,834 / 결정세액 76,265(179,411명)
     4-3-2 : 성·연령별 수입금액·소득금액·결정세액
     4-4-10: 인원 7,087,845 / 총소득금액(과세) 66,471,851 / 소득세 417,163 / 지방소득세 41,716
     3-1-2 : 단순경비율신고자 사업·부동산 총수입금액 59,155,019 → 소득금액 16,233,171 (소득률 27.44%)
             → binc_sum_inc(업종별 단순경비율 적용 소득금액)의 소득률 근거
  S2 행정안전부 주민등록 인구통계 2022.11 — 보유율 분모 [1차확인]
  S0 R01 <표 2-30>(개인근로소득: 일용 포함, 0원 53.0%) · <표 2-31>(개인사업소득 0원 80.8%)
     · <표 2-33>(개인일차소득 0원 40.6%)  params/tab/S0_R01_T2-3*.csv → 합성 결과 검증 목표

■ 생성 절차 (§6 B09)
  보유확률 = 원표 인원/주민등록 인구 (성·연령대 IPF 셀 복원, 15세 미만 0)
  → 금액은 원표 구간 히스토그램을 **셀 내부 순위 보존**으로 추출하고 전국 순위 재정렬로
    구간 분포를 정확히 복원(B08과 동일 절차) → 성×연령 셀 평균은 원표 값에 6회 반복 수렴
  → 세액은 구간별 **실측 유효세율**(법정률 아님)을 로그보간해 적용
     · 사업소득 원천징수 3%(소득세법 §129①3호)는 실측 2.99%로 확인됨
     · 일용근로소득 (일급−15만원)×6%×(1−55%) 구조는 실측 유효세율 0.63%로 확인됨
  → 지방소득세 = 소득세 × 10% (4-4-10 에서 41,716/417,163 = 0.100000 으로 실측)
  → 농어촌특별세(othinc_ruraltax, ybinc_ruraltax)는 조특법 감면세액이 있어야 성립하는데
    해당 지급명세서에는 감면 항목이 없다 → 규모 미달, 전량 NaN
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core, nts

MW = 1_000_000
E5 = (30, 40, 50, 60)            # 4-4-6 / 4-4-8 / 4-3-2 의 연령 구분 (60세 이상 통합)
E6 = (30, 40, 50, 60, 70)        # 4-4-10 의 연령 구분
LOCAL = 0.10                     # 지방소득세(특별징수) = 소득세의 10% [4-4-10 실측]
BETA_ALPHA = 1.3                 # 구간 내부 형상 [가정 A2-B09-1]
# 원천징수사업소득 소득률 — NTS <3-1-2> 단순경비율신고자: 소득금액 16,233,171 / 총수입금액 59,155,019
INC_RATIO_BINC = 16_233_171 / 59_155_019

# ── 60세 이후 연령 활동성 감쇠 (S0 2단 적합) ────────────────────────────────
#  NTS 원표는 '60세 이상'·'70세 이상'을 각각 한 칸으로 공표하므로 구간 **내부**의
#  연령 프로파일이 없다. 이전 판은 구간 내부를 평탄하게 두어 65~69세 보유율이
#  60~64세와 같아졌고, 그 결과 65세 이상 개인근로사업소득이 S0 대비 +88% 였다.
#
#  근거 [1차확인 2026-09-02] — 노인 개인근로사업소득(근로+사업+일용) 평균, 만원/년
#    S0 R01 <표 4-3> p.161 (2020): 65~69 884 / 70~74 542 / 75~79 292 / 80+ 141
#    S0 R02 <표 4-8> p.156 (2021): 65~69 862 / 70~74 482 / 75~79 281 / 80+ 143
#
#  프로파일 φ(a) = 1 (a<60) · exp(-(a-60)/τ1) (60≤a<70) · 그 뒤 exp(-(a-70)/τ2)
#    τ2 = 9.3년 : 주민등록 2022.11 단일연령 인구로 가중해 70~74 : 75~79 : 80+ 를
#                 1 : 0.587 : 0.275 로 만든다 (R01 1:0.330/0.160·R02 1:0.326/0.166
#                 대비 로그편차합 최소).
#    τ1 = TAU1  : 60~69 구간 **내부**의 배분. NTS 60~69 구간 총량(S2, 확정)과
#                 S0 의 65~69 평균(확정)을 동시에 만족시키는 값을 역산한 것으로,
#                 60~64 평균 = (구간총량 − 65~69 인구×S0값)/60~64 인구 라는 항등식이
#                 결정한다(작업지시 '연령×금액 이원 IPF'). 실측 캘리브레이션 결과.
#  구간 총 보유율은 모집단(주민등록 1세) 가중 평균으로 정규화하므로
#  **NTS 구간 총량(인원·금액)은 그대로 보존되고 구간 내부 배분만 바뀐다.**
OLD_FROM = 60.0
TAU1 = 5.5                  # 60~69 감쇠 시간상수(년)
TAU2 = 9.3                  # 70세 이상 감쇠 시간상수(년) — S0 연령비 적합

# 상관 파라미터 [가정 A2-B09-2] — _u_income 과의 상관(보유, 금액)
RHO = {'binc': (0.20, 0.45), 'othinc': (0.25, 0.50), 'ybinc': (0.10, 0.35), 'dainc': (-0.25, 0.20)}
# 근로소득(B08) 보유자에 대한 상대위험 [논리적추론 A2-B09-3] — note 참조
RR_LAB = {'binc': 0.80, 'othinc': 1.10, 'ybinc': 0.65, 'dainc': 1.15}

# 금액 구간 (원). (라벨, 하한, 상한)
BAND_BINC = [('1천만 이하', 0, 10e6), ('2천만 이하', 10e6, 20e6), ('4천만 이하', 20e6, 40e6),
             ('6천만 이하', 40e6, 60e6), ('8천만 이하', 60e6, 80e6), ('1억 이하', 80e6, 100e6),
             ('2억 이하', 100e6, 200e6), ('3억 이하', 200e6, 300e6), ('5억 이하', 300e6, 500e6),
             ('5억 초과', 500e6, None)]
BAND_OTH = [('1천만원 이하', 0, 10e6), ('2천만원 이하', 10e6, 20e6), ('4천만원 이하', 20e6, 40e6),
            ('6천만원 이하', 40e6, 60e6), ('8천만원 이하', 60e6, 80e6), ('1억 이하', 80e6, 100e6),
            ('2억 이하', 100e6, 200e6), ('3억 이하', 200e6, 300e6), ('5억 이하', 300e6, 500e6),
            ('5억 초과', 500e6, None)]
BAND_YB = [('5백만 이하', 0, 5e6), ('1천만 이하', 5e6, 10e6), ('2천만 이하', 10e6, 20e6),
           ('4천만 이하', 20e6, 40e6), ('6천만 이하', 40e6, 60e6), ('8천만 이하', 60e6, 80e6),
           ('1억 이하', 80e6, 100e6), ('2억 이하', 100e6, 200e6), ('2억 초과', 200e6, None)]
BAND_DA = [('1백만원 이하', 0, 1e6), ('3백만원 이하', 1e6, 3e6), ('6백만 이하', 3e6, 6e6),
           ('9백만 이하', 6e6, 9e6), ('10백만 이하', 9e6, 10e6), ('12백만 이하', 10e6, 12e6),
           ('15백만 이하', 12e6, 15e6), ('18백만 이하', 15e6, 18e6), ('20백만 이하', 18e6, 20e6),
           ('21백만 이하', 20e6, 21e6), ('25백만 이하', 21e6, 25e6), ('30백만 이하', 25e6, 30e6),
           ('40백만 이하', 30e6, 40e6), ('50백만 이하', 40e6, 50e6), ('50백만 초과', 50e6, None)]


# ── 원표 파싱 ────────────────────────────────────────────────────────────────
def _pick(d, row_l1, col_filter):
    s = d[d.ROW_L1 == row_l1]
    for k, v in col_filter.items():
        s = s[s[k] == v]
    return s.set_index('ROW_L2')['VALUE']


MIN_EXP_ROWS = 2.0        # 최상위 구간이 표본에서 기대되는 최소 행수 (미만이면 병합)


def _merge_tail(b, n_hold, min_exp=MIN_EXP_ROWS):
    """표본이 지지하지 못하는 **최상위 금액구간**을 아래 구간과 병합한다.

    원표의 최상위 구간이 전국 인원의 0.0x% 인데 금액의 10%대를 차지하는 경우
    (NTS 4-4-8 기타소득: 1,471명=0.03% 인원이 소득금액의 16.6%),
    표본 9,535명에서 그 구간에 배정되는 기대 행수가 0.3 미만이라 사실상 항상 비고
    전국 총액이 그만큼 구조적으로 결손된다. 기대 행수가 min_exp 이상이 될 때까지
    상위 구간을 하나로 합치면 구간 내부 형상만 잃고 **총액·인원은 원표대로 보존**된다.
    (합계는 병합 전후 동일하므로 원표 수치를 바꾸는 것이 아니다.)"""
    n = np.asarray(b['n'], float)
    if n.sum() <= 0 or len(n) < 3:
        return b
    share = n / n.sum()
    i = len(n) - 1
    while i > 0 and share[i:].sum() * n_hold < min_exp:
        i -= 1
    if i >= len(n) - 1:
        return b
    bt = b['bt']
    lo = np.append(bt['lo'][:i], bt['lo'][i])
    hi_all = bt['hi']
    hi = [None if not np.isfinite(h) else float(h) for h in hi_all[:i]] + \
         [None if not np.isfinite(hi_all[-1]) else float(hi_all[-1])]
    agg = lambda v: np.append(np.asarray(v, float)[:i], np.asarray(v, float)[i:].sum())
    nn, aa = agg(b['n']), agg(b['a'])
    out = {'bt': nts.band_table(lo, hi, nn, aa), 'n': nn, 'a': aa, 'merged_from': int(i)}
    for k in b:
        if k not in ('bt', 'n', 'a'):
            out[k] = agg(b[k])
    return out


def _bands(series_map, bands):
    lab = [b[0] for b in bands]
    n = np.array([float(series_map['n'].get(l, 0.0)) for l in lab])
    a = np.array([float(series_map['a'].get(l, 0.0)) for l in lab]) * MW
    bt = nts.band_table([b[1] for b in bands], [b[2] for b in bands], n, a)
    out = {'bt': bt, 'n': n, 'a': a}
    for k in series_map:
        if k not in ('n', 'a'):
            out[k] = np.array([float(series_map[k].get(l, 0.0)) for l in lab]) * MW
    return out


def src_binc():
    d = nts.nts('4-4-6')
    f = lambda c: {'COL_L2': c}
    b = _bands({'n': _pick(d, '지급총액 규모별', f('인원 [E]')),
                'a': _pick(d, '지급총액 규모별', f('연간지급금액')),
                'tax': _pick(d, '지급총액 규모별', f('소득세 (원천징수분)'))}, BAND_BINC)
    return {'band': b,
            'sex_n': _pick(d, '성별', f('인원 [E]')), 'age_n': _pick(d, '연령별', f('인원 [E]')),
            'sex_a': _pick(d, '성별', f('연간지급금액')), 'age_a': _pick(d, '연령별', f('연간지급금액'))}


def src_othinc():
    d = nts.nts('4-4-8')
    f = lambda c: {'COL_L2': c}
    b = _bands({'n': _pick(d, '연간지급액규모별', f('인원')),
                'a': _pick(d, '연간지급액규모별', f('연간지급총액')),
                'inc': _pick(d, '연간지급액규모별', f('소득금액')),
                'tax': _pick(d, '연간지급액규모별', f('소득세 (원천징수분)'))}, BAND_OTH)
    return {'band': b,
            'sex_n': _pick(d, '성별 [B]', f('인원')), 'age_n': _pick(d, '연령별', f('인원')),
            'sex_a': _pick(d, '성별 [B]', f('연간지급총액')), 'age_a': _pick(d, '연령별', f('연간지급총액'))}


def src_ybinc():
    d1, d2 = nts.nts('4-3-1'), nts.nts('4-3-2')
    s = d1[(d1.ROW_L1 == '수입금액 규모별') & (d1.COL_L2 == '2022년')]
    n = s[s.COL_L3 == '인원'].set_index('ROW_L2')['VALUE']
    a = s[s.COL_L3 == '금액'].set_index('ROW_L2')['VALUE']
    b = _bands({'n': n, 'a': a}, BAND_YB)
    tot = d1[(d1.ROW_L1.isin(['소득금액', '수입금액', '결정세액'])) & (d1.ROW_L2 == '소계') &
             (d1.COL_L2 == '2022년')]
    g = tot.set_index(['ROW_L1', 'COL_L3'])['VALUE']
    q = lambda k: d2[(d2.ROW_L1 == k) & (d2.COL_L2 == '수입금액') & (d2.COL_L3 == '인원')] \
        .set_index('ROW_L2')['VALUE']
    qa = lambda k: d2[(d2.ROW_L1 == k) & (d2.COL_L2 == '수입금액') & (d2.COL_L3 == '금액')] \
        .set_index('ROW_L2')['VALUE']
    return {'band': b, 'sex_n': q('성별'), 'age_n': q('연령별'), 'sex_a': qa('성별'), 'age_a': qa('연령별'),
            'inc_ratio': float(g[('소득금액', '금액')] / g[('수입금액', '금액')]),
            'tax_tot': float(g[('결정세액', '금액')]) * MW, 'tax_n': float(g[('결정세액', '인원')]),
            'n_tot': float(g[('수입금액', '인원')])}


def src_dainc():
    d = nts.nts('4-4-10')
    cn = {'COL_L2': '일용근로자', 'COL_L3': '소계'}
    ca = {'COL_L2': '총소득금액 (과세소득) [B]', 'COL_L3': '소계'}
    ct = {'COL_L2': '원천징수세액', 'COL_L3': '소득세'}
    b = _bands({'n': _pick(d, '총소득금액규모별 [C]', cn), 'a': _pick(d, '총소득금액규모별 [C]', ca),
                'tax': _pick(d, '총소득금액규모별 [C]', ct)}, BAND_DA)
    return {'band': b, 'sex_n': _pick(d, '성별', cn), 'age_n': _pick(d, '연령별', cn),
            'sex_a': _pick(d, '성별', ca), 'age_a': _pick(d, '연령별', ca)}


# ── 공통 생성기 ──────────────────────────────────────────────────────────────
def _age_w(age):
    """구간 내부 연령 프로파일 — 15세 미만 0, 15~29 로지스틱 [가정 A2-B09-4],
    60세 이상 2단 지수감쇠(위 주석, S0 R01<표4-3>·R02<표4-8> 적합)."""
    a = np.asarray(age, float)
    w = np.ones_like(a)
    w = np.where(a < 15, 0.0, w)
    m = (a >= 15) & (a < 30)
    w = np.where(m, 1.0 / (1.0 + np.exp(-(a - 21.0) / 2.5)), w)
    d1 = np.exp(-(np.clip(a, OLD_FROM, OLD_FROM + 10.0) - OLD_FROM) / TAU1)
    d2 = np.exp(-(np.maximum(a, OLD_FROM + 10.0) - (OLD_FROM + 10.0)) / TAU2)
    return np.where(a >= OLD_FROM, d1 * d2, w)


# ── 노인 가구유형별 상대위험 (S0) ───────────────────────────────────────────
#  S0 R01 <표 4-3> p.161 / R02 <표 4-8> p.156 [1차확인 2026-09-02] — 노인 개인
#  근로·사업소득 평균(만원/년)을 가구유형별로 공표한다.
#      R01(2020) 노인1인 379 / 노인2인이상 515 / 비노인동거 615  (전체 523)
#      R02(2021) 노인1인 350 / 노인2인이상 504 / 비노인동거 580  (전체 504)
#  전체 평균 대비 상대비의 두 해 평균이 아래 값이다. NTS 원표에는 가구유형 축이
#  없으므로 이 조건부 구조는 S0 에서만 얻을 수 있다(AGENT_BRIEF: S0 는 조건부
#  구조의 기준). 성×연령대 셀 안에서 65세 이상만 재정규화하므로
#  **원표 구간 보유율과 연령 프로파일은 그대로 보존된다.**
OLD_RR_ALONE = 0.71       # 노인 1인 가구
OLD_RR_ONLY = 0.99        # 노인만 2인 이상
OLD_RR_MIX = 1.16         # 비노인 동거 가구


def _old_hh_rr(df):
    """65세 이상에 대한 가구유형별 상대위험 (그 외 1.0)."""
    age = np.asarray(df['age'].values, float)
    hid = np.asarray(df['hid'].values)
    o = (age >= 65).astype(np.int8)
    n_old = pd.Series(o).groupby(hid).transform('sum').to_numpy()
    n_all = pd.Series(np.ones(len(age))).groupby(hid).transform('sum').to_numpy()
    rr = np.where(n_old == n_all,
                  np.where(n_all == 1, OLD_RR_ALONE, OLD_RR_ONLY), OLD_RR_MIX)
    return np.where(age >= 65, rr, 1.0)


def _apply_old_rr(p, df, sex, band, cols):
    """성×연령대 셀 안에서 65세 이상의 보유확률에 가구유형 상대위험을 적용하고
    65세 이상 부분집합의 평균 확률을 보존하도록 재정규화한다."""
    rr = _old_hh_rr(df)
    o65 = np.asarray(df['age'].values) >= 65
    p = np.asarray(p, float).copy()
    for s in np.unique(sex):
        for b in cols:
            m = o65 & (sex == s) & (band == b)
            if not m.any():
                continue
            base = p[m]
            if base.sum() <= 0:
                continue
            adj = base * rr[m]
            if adj.mean() <= 0:
                continue
            p[m] = np.clip(adj * (base.mean() / adj.mean()), 0.0, 0.98)
    return p


def _cells(src, edges):
    """성×연령대 인원·금액 셀 복원 → (rate, mean)."""
    labs = nts.band_labels(edges)
    pop = nts.pop_sex_age(edges)
    sn = {'남성': float(src['sex_n'].get('남성', 0)), '여성': float(src['sex_n'].get('여성', 0))}
    an = {l: float(src['age_n'].get(l, 0.0)) for l in labs}
    jn = nts.joint_from_margins(sn, an, pop)
    sa = {'남성': float(src['sex_a'].get('남성', 0)), '여성': float(src['sex_a'].get('여성', 0))}
    aa = {l: float(src['age_a'].get(l, 0.0)) for l in labs}
    ja = nts.joint_from_margins(sa, aa, jn)          # 금액은 인원 셀을 seed 로 IPF
    rate = (jn / pop.loc[jn.index, jn.columns]).clip(upper=0.9)
    mean = (ja * MW / jn.replace(0, np.nan))
    return rate, mean


def _make(g, df, src, edges, kind, lab_hold):
    """보유 판정 → 금액(구간 히스토그램 + 셀평균 보정) 반환. 미보유는 NaN."""
    n = len(df)
    rate, cmean = _cells(src, edges)
    sex = np.where(df['gender'].values == 1, '남성', '여성')
    band = nts.age_band(df['age'].values, edges)
    mw = nts.pop_weight_mean(_age_w, edges)
    w_age = _age_w(df['age'].values)
    p = np.zeros(n)
    for s in ('남성', '여성'):
        for b in rate.columns:
            m = (sex == s) & (band == b)
            if not m.any():
                continue
            d = mw.get((s, b), 1.0)
            p[m] = 0.0 if d <= 0 else np.clip(w_age[m] / d * float(rate.loc[s, b]), 0.0, 0.9)
    # 근로소득 보유 여부에 따른 상대위험 (셀 평균 보유율은 유지)
    rr = RR_LAB[kind]
    f = np.where(lab_hold, rr, 1.0)
    for s in ('남성', '여성'):
        for b in rate.columns:
            m = (sex == s) & (band == b)
            if not m.any() or p[m].sum() <= 0:
                continue
            adj = p[m] * f[m]
            p[m] = np.clip(adj * (p[m].mean() / max(adj.mean(), 1e-12)), 0.0, 0.95)

    # 노인 가구유형별 상대위험 (S0 R01<표4-3>·R02<표4-8>) — 65세 이상만, 셀 평균 보존
    p = _apply_old_rr(p, df, sex, band, list(rate.columns))

    rho_h, rho_a = RHO[kind]
    hold = nts.score(g, df['_u_income'].values, rho_h) > (1.0 - p)
    r_amt = nts.score(g, df['_u_income'].values, rho_a)

    x = np.full(n, np.nan)
    idx = np.flatnonzero(hold)
    if not len(idx):
        return hold, x
    key = np.array([f'{s}|{b}' for s, b in zip(sex, band)], dtype=object)
    rk = np.empty(len(idx))
    for k in np.unique(key[idx]):
        m = key[idx] == k
        c = int(m.sum())
        rk[m] = (pd.Series(r_amt[idx][m]).rank(method='first').values - 0.5) / c
    base = nts.draw_by_rank(g, rk, src['band']['bt'], alpha=BETA_ALPHA)
    natm = src['band']['a'].sum() / max(src['band']['n'].sum(), 1)
    tgt = {f'{s}|{b}': float(cmean.loc[s, b]) for s in ('남성', '여성') for b in rate.columns
           if np.isfinite(cmean.loc[s, b])}
    fac = {k: max(v / natm, 1e-3) for k, v in tgt.items()}
    wt = (df['indwgt'].values if 'indwgt' in df.columns else np.ones(n))[idx]
    xx = base
    for _ in range(6):
        y = base * np.array([fac.get(k, 1.0) for k in key[idx]])
        o = np.argsort(y, kind='mergesort')
        cw = np.cumsum(wt[o]); rg = np.empty(len(idx)); rg[o] = (cw - 0.5 * wt[o]) / cw[-1]
        xx = nts.draw_by_rank(g, rg, src['band']['bt'], alpha=BETA_ALPHA)
        ach = pd.Series(xx * wt).groupby(key[idx]).sum() / pd.Series(wt).groupby(key[idx]).sum()
        for k, v in ach.items():
            if k in fac and v > 0:
                fac[k] = float(np.clip(fac[k] * tgt[k] / v, 1e-3, 50.0))
    xx = nts.match_band_means(xx, wt, src['band']['bt'])
    x[idx] = np.maximum(xx, 1000.0)
    return hold, x


def _pos(v):
    """세액 0원은 '세금이 존재하는 집단' 추출대상 밖 → NaN (§7 추출대상 규약)."""
    v = pd.Series(v)
    return v.where(v.fillna(0) > 0)


def _rate_of(band, num_key):
    b = band
    return np.divide(b[num_key], np.maximum(b['a'], 1.0), out=np.zeros_like(b['a']), where=b['a'] > 0)


# ── 생성 ─────────────────────────────────────────────────────────────────────
def generate(df, params, ctx):
    g = core.rng('B09')
    n = len(df)
    lab_hold = df['labinc_sum_taxy'].notna().values if 'labinc_sum_taxy' in df.columns \
        else np.zeros(n, bool)

    S = {'binc': src_binc(), 'othinc': src_othinc(), 'ybinc': src_ybinc(), 'dainc': src_dainc()}
    # 표본이 지지하지 못하는 최상위 금액구간은 병합한다 (구간 기대 행수 < MIN_EXP_ROWS).
    # 4-4-8 기타소득처럼 최상위 구간이 인원의 0.03%·금액의 16.6% 를 차지하면 병합하지 않을 때
    # 전국 총액이 구조적으로 결손된다. 총액·인원은 병합 전후 동일하다.
    for _k in S:
        S[_k]['band'] = _merge_tail(
            S[_k]['band'], float(np.asarray(S[_k]['band']['n']).sum()) / 51_450_829.0 * len(df))
    out = pd.DataFrame(index=df.index)

    # ── 원천징수사업소득 ─────────────────────────────────────────────────────
    h, x = _make(g, df, S['binc'], E5, 'binc', lab_hold)
    er = nts.interp_rate(np.nan_to_num(x), S['binc']['band']['bt'], _rate_of(S['binc']['band'], 'tax'))
    tax = np.where(h, np.round(x * er), np.nan)
    out['binc_sum'] = np.round(x)
    out['binc_sum_inc'] = np.round(x * INC_RATIO_BINC)
    out['binc_inctax'] = np.where(np.nan_to_num(tax) > 0, tax, np.nan)
    out['binc_localtax'] = _pos(np.round(out['binc_inctax'] * LOCAL))

    # ── 기타소득 ─────────────────────────────────────────────────────────────
    #   4-4-8 최상위 구간(5억 초과 1,471명)은 표본 기대 행수 0.3 미만이라 항상 비어
    #   전국 소득금액의 16.6% 가 구조적으로 결손된다 → 위에서 상위 구간을 병합했다.
    h, x = _make(g, df, S['othinc'], E5, 'othinc', lab_hold)
    bb = S['othinc']['band']
    ir = nts.interp_rate(np.nan_to_num(x), bb['bt'], _rate_of(bb, 'inc'))
    tr = np.divide(bb['tax'], np.maximum(bb['inc'], 1.0), out=np.zeros_like(bb['tax']), where=bb['inc'] > 0)
    inc = np.where(h, np.round(x * ir), np.nan)
    tax = np.where(h, np.round(inc * nts.interp_rate(np.nan_to_num(x), bb['bt'], tr)), np.nan)
    out['othinc_sum'] = np.round(x)
    out['othinc_sum_inc'] = inc
    out['othinc_inctax'] = np.where(np.nan_to_num(tax) > 0, tax, np.nan)
    out['othinc_localtax'] = _pos(np.round(out['othinc_inctax'] * LOCAL))
    out['othinc_ruraltax'] = np.nan          # 지급명세서에 조특법 감면 항목 없음 → 규모 미달

    # ── 연말정산사업소득 ─────────────────────────────────────────────────────
    yb = S['ybinc']
    h, x = _make(g, df, yb, E5, 'ybinc', lab_hold)
    inc = np.where(h, np.round(x * yb['inc_ratio']), np.nan)
    # 결정세액: 소득금액 상위 (179,411/529,705) 만 과세, 총액 76,265백만원에 맞춘 유효세율
    share = yb['tax_n'] / max(yb['n_tot'], 1)
    idx = np.flatnonzero(h)
    taxed = np.zeros(n, bool)
    if len(idx):
        wt = df['indwgt'].values[idx]
        o = np.argsort(inc[idx], kind='mergesort')
        cw = np.cumsum(wt[o]); rg = np.empty(len(idx)); rg[o] = (cw - 0.5 * wt[o]) / cw[-1]
        taxed[idx] = rg > (1.0 - share)
    # 유효세율 = 원표 결정세액 총액 / (상위 share 과세자의 소득금액 총액) — 전국 기준으로 산출
    eff = yb['tax_tot'] / max(yb['inc_ratio'] * _taxed_income_share(yb, share), 1.0)
    tax = np.where(taxed, np.round(inc * eff), np.nan)
    out['ybinc_sum'] = np.round(x)
    out['ybinc_sum_inc'] = inc
    out['ybinc_inctax'] = np.where(np.nan_to_num(tax) > 0, tax, np.nan)
    out['ybinc_localtax'] = _pos(np.round(out['ybinc_inctax'] * LOCAL))
    out['ybinc_ruraltax'] = np.nan           # 조특법 감면 없음 → 규모 미달

    # ── 일용근로소득 ─────────────────────────────────────────────────────────
    h, x = _make(g, df, S['dainc'], E6, 'dainc', lab_hold)
    er = nts.interp_rate(np.nan_to_num(x), S['dainc']['band']['bt'], _rate_of(S['dainc']['band'], 'tax'))
    tax = np.where(h, np.round(x * er), np.nan)
    out['dainc_sum'] = np.round(x)
    out['dainc_taxfree'] = np.where(h, 0.0, np.nan)   # [가정] 원표 미공표 → 0
    out['dainc_tax1'] = np.where(np.nan_to_num(tax) > 0, tax, np.nan)
    out['dainc_tax2'] = _pos(np.round(out['dainc_tax1'] * LOCAL))
    return out


def _taxed_income_share(yb, share):
    """원표 수입금액 구간분포에서 상위 share 에 해당하는 수입금액 합(전국, 원)."""
    bt = yb['band']['bt']
    w = bt['w'][::-1]; m = bt['mean'][::-1]; n = yb['band']['n'][::-1]
    cum = np.cumsum(w)
    tot = 0.0
    for i in range(len(w)):
        take = min(w[i], max(share - (cum[i] - w[i]), 0.0))
        tot += take / max(w[i], 1e-12) * n[i] * m[i]
        if cum[i] >= share:
            break
    return tot

