# -*- coding: utf-8 -*-
"""B07 종합소득 (inc_*) — 21개 변수  (A2 / order 3)

추출대상: 2022년 귀속 종합소득세 확정신고자(분리과세 전용 신고자 포함). 그 밖은 NaN.
신고자 내부에서 해당 소득이 없으면 0 (코드북 비고 "0 초과/0 제외 유효 사례 …"가
0 사례의 존재를 전제하므로).

소스 (등급순) — 모두 [1차확인] 2026-09-02, 국세통계포털 TASIS 2023년 발행(2022년 귀속):
  S2 NTS 3-1-3  성·연령별 신고인원 → 신고확률          params/tab/B07_NTS_3-1-3_*.csv
  S2 NTS 3-2-2  성별×종합소득 규모별 인원 → 구간 배분   params/tab/B07_NTS_3-2-2_*.csv
  S2 NTS 3-2-3  종합소득 규모별×소득종류별 인원·금액    params/tab/B07_NTS_3-2-3_*.csv
  S2 NTS 3-1-4  종합소득 규모별 결정세액 → 유효세율     params/tab/B07_NTS_3-1-4_*.csv
  S2 NTS 3-1-2  소득종류별 총수입금액/소득금액 비율     params/tab/B07_NTS_3-1-2_*.csv
  S2 NTS 3-2-3-3 부동산임대소득 상가/주택/기타 분해     params/tab/B07_NTS_3-2-3-3_*.csv
  S2 NTS 3-2-3-2 분리과세 주택임대(성·연령)            params/tab/B07_NTS_3-2-3-2_*.csv
  S2 NTS 3-1-6  농어촌특별세                          params/tab/B07_NTS_3-1-6_*.csv
  S2 NTS 3-1-1-2 종합/분리 결정세액 총량               params/tab/B07_NTS_3-1-1-2_*.csv
  S2 행안부 주민등록 인구통계 2022.11 (신고확률 분모)   params/raw/POPUL_MOIS01_*.csv
  ※ S0(R01·R02) 제2장에는 '종합소득세 신고' 자체를 다룬 표가 없다(표 2-30~2-33 은 개인소득
     분포이며 B03 에서 사용). 따라서 B07 은 S2 국세통계가 최상위 사용가능 등급이다.

생성 절차 (§6 B07, 2026-09-02 재작업):
  1) 신고자 선정 — 3-1-3 성·연령 신고확률. 우선순위 = _u_income 코퓰러
       + B09 원천징수 사업소득 보유 가산(인적용역 3.3% 원천징수분 환급을 위해 확정신고)
       + B08 근로소득 보유 가산
  2) **근로소득 신고자 확정 후 구간 배정** — 3-2-3 의 구간별 근로소득금액 인원 L_k·평균 μ_k 에서
       총급여 목표 T_k = μ_k/소득률 을 역산하고, B08 총급여 분포에서 (인원 ΣL_k, 평균 T̄)를
       만족하도록 지수기울임 선택(_tilt_pick) → 총급여 오름차순으로 구간 슬라이스.
       나머지 신고자는 성별 3-2-2 잔여 정원을 _u_income 순위로 채운다.
       ※ 이전 판은 구간을 먼저 정하고 근로소득금액을 덮어써 구간 상한을 넘겼고, 그 보정 배율
         때문에 전국 총수입금액이 +29.8% 과대했다.
  3) 구간 내 종합소득금액(3-1-4 구간평균) → 4) 소득종류 배정(3-2-3 구간별 인원을 가중 쿼터로
     정확히 배분, 지급명세서(B09) 보유자 우선 + 무(無)종류 신고자 우선)
  5c) 구간평균(3-1-4) ↔ 종류별 전국총액(3-2-3) IPF 5회
  7) 총수입금액 = 3-1-2 소득률 역산 (근로는 B08 총급여 그대로)
  8) 결정세액 = 3-1-4 구간 유효세율, **가중** 순위·가중 총액 정렬
     ※ 이전 판은 비가중 합으로 정렬해 전국 결정세액이 −18.1% 어긋났다.
조건부 규칙:
  · inc_labinc_sum = B08(labinc_sum_taxy − labinc_sum_taxn, 총급여) 값과 개인 단위 일치
  · 사업소득금액 신고자 ⊇ B09 원천징수 사업소득 보유자 (B03 p_binc 이중계상 방지)
  · 기타소득금액 신고자 ⊂ B09 기타소득 지급명세서 보유자 중 금액 상위 (§14③8호 300만원 초과 요건)
"""
from __future__ import annotations
import os, sys, json
import numpy as np, pandas as pd
from scipy.stats import norm

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

TAB = 'params/tab'
RAW = 'params/raw'
BANDS = ['15-29', '30-39', '40-49', '50-59', '60-69', '70+']
# 종합소득금액 구간 경계 (만원). ord 0 = "0 이하" (별도 처리), ord 1..10
BEDGE = {1: (0, 1000), 2: (1000, 2000), 3: (2000, 4000), 4: (4000, 6000), 5: (6000, 8000),
         6: (8000, 10000), 7: (10000, 20000), 8: (20000, 30000), 9: (30000, 50000),
         10: (50000, None)}
TYPES = ['이자소득금액', '배당소득금액', '사업소득금액', '부동산임대소득금액',
         '근로소득금액', '연금소득금액', '기타소득금액']
DIR_KAPPA = 12.0          # 소득종류 배분 디리클레 집중도 [가정 A2-B07-1]
RHO_BRACKET = 0.75        # _u_income ↔ 소득구간 순위상관 [가정 A2-B07-2]
RHO_WITHIN = 0.55         # _u_income ↔ 구간 내 위치 순위상관 [가정 A2-B07-2]
RHO_FILE = 0.40           # _u_income ↔ 신고 여부 [가정 A2-B07-2]
RAS_ITER = 8              # 구간×소득종류 금액구성 RAS 반복 (가중치 IPF와 무관)
BONUS_BIZ = 1.20          # 신고자 선정 가산 — B09 원천징수 사업소득 보유 [논리적추론 A2-B07-3]
BONUS_LAB = 0.35          # 신고자 선정 가산 — B08 근로소득 보유 [논리적추론 A2-B07-3]
COVER = 1.60              # 소득종류 배정 — '아직 무(無)종류' 신고자 우선 가중
W_PREF = 1.10             # 소득종류 배정 — 지급명세서(B09) 보유자 우선 가중
W_OTH = 3.00              # 기타소득은 '기타소득금액 300만원 초과' 요건이 있어 금액 상위에 집중
# 구간 배정의 **연령대 보정** — NTS 3-1-3 의 성×연령별 종합소득금액 평균에 맞춘다.
#  3-1-3 은 성·연령별 신고인원뿐 아니라 **종합소득금액 합계**도 공표한다. 이전 판은
#  인원만 쓰고 금액을 쓰지 않아, 구간 배정이 연령과 무관하게 _u_income 순위로만
#  이루어졌다. 그 결과 5억 초과 구간(전국 43,379명, 평균 12.7억)의 표본 1행이
#  70대에 떨어지면 그 5세 계급의 사업소득이 28조 늘어나는 사고가 났다
#  (2026-09-02 실측: 75~79세 근로사업소득 per-capita 2,003만원 = S0 목표의 7배).
#  δ_{성,연령대} 를 정규점수에 더해 순서만 바꾸므로 **구간별 정원(3-2-2·3-1-4)은
#  그대로 보존**되고, 성×연령 평균만 원표에 맞춰진다.
CAL_ITER = 24             # δ 보정 반복 횟수
CAL_ETA = 0.45            # δ 갱신 감쇠
MAN = 10_000.0            # 만원 → 원
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
_POP1 = None


def _age_w(age):
    """15세 미만 0 · 15~29 로지스틱 · 60세 이상 2단 지수감쇠(위 주석)."""
    a = np.asarray(age, float)
    w = np.ones_like(a)
    w = np.where(a < 15, 0.0, w)
    m = (a >= 15) & (a < 30)
    w = np.where(m, 1.0 / (1.0 + np.exp(-(a - 21.0) / 2.5)), w)
    d1 = np.exp(-(np.clip(a, OLD_FROM, OLD_FROM + 10.0) - OLD_FROM) / TAU1)
    d2 = np.exp(-(np.maximum(a, OLD_FROM + 10.0) - (OLD_FROM + 10.0)) / TAU2)
    return np.where(a >= OLD_FROM, d1 * d2, w)


def _pop1():
    """성×1세 주민등록 인구 (2022.11). 구간 내부 정규화의 분모."""
    global _POP1
    if _POP1 is None:
        d = pd.read_csv(os.path.join(RAW, 'POPUL_MOIS01_2022_11_sigungu_age1_sex.csv'))
        d = d[(d.level == 'sigungu') & (d.sex.isin(['male', 'female']))].copy()
        d['age'] = d['age'].astype(int)
        t = d.groupby(['sex', 'age'])['pop'].sum().unstack().fillna(0.0)
        _POP1 = {1: t.loc['male'], 2: t.loc['female']}
    return _POP1


def _sub5(age):
    """5세 계급 하한 (100세 이상은 95 로 묶음)."""
    return (np.minimum(np.asarray(age, int), 99) // 5) * 5


def _age_norm():
    """(sex, band) → 모집단 가중 평균 φ, (sex, 5세계급) → 모집단 가중 평균 φ."""
    pop = _pop1()
    ages = np.arange(0, 101)
    w = _age_w(ages)
    bd = _band(ages)
    sb = _sub5(ages)
    nb, ns = {}, {}
    for s in (1, 2):
        npop = pop[s].reindex(ages).fillna(0.0).values
        for b in BANDS:
            m = bd == b
            nb[(s, b)] = float((w[m] * npop[m]).sum() / max(npop[m].sum(), 1.0))
        for u in np.unique(sb):
            m = sb == u
            ns[(s, int(u))] = float((w[m] * npop[m]).sum() / max(npop[m].sum(), 1.0))
    return nb, ns


# ── 유틸 ────────────────────────────────────────────────────────────────────
def _T(name):
    return pd.read_csv(os.path.join(TAB, name + '.csv'))


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
    """순위 r(0~1, 균등) 과 상관 rho 를 갖는 새 균등난수 (가우시안 코퓰러 — 주변분포 보존)."""
    r = np.clip(np.asarray(r, float), 1e-6, 1 - 1e-6)
    z = rho * norm.ppf(r) + np.sqrt(max(1e-9, 1 - rho ** 2)) * g.standard_normal(len(r))
    return norm.cdf(z)


def _rank01(x):
    """값 → (0,1) 균등 순위."""
    x = np.asarray(x, float)
    if len(x) == 0:
        return x
    o = np.argsort(np.argsort(x))
    return (o + 0.5) / len(x)


def _beta1_from_mean(lo, hi, mean):
    """구간 [lo,hi] 안에서 평균이 mean 이 되는 Beta(a,1) 의 a. (E[x]=lo+(hi-lo)a/(a+1))"""
    m = np.clip((mean - lo) / (hi - lo), 0.03, 0.97)
    return m / (1 - m)


def _syst(g, order, k):
    """정렬된 인덱스 order 에서 균등 간격 k 개를 뽑는 계통추출 (표본오차 축소)."""
    k = int(max(0, min(k, len(order))))
    if k == 0:
        return np.array([], dtype=int)
    step = len(order) / k
    pos = np.floor((np.arange(k) + g.random()) * step).astype(int)
    return order[np.clip(pos, 0, len(order) - 1)]


def _quota_w(order, w, frac):
    """order(우선순위) 를 따라 누적 가중치가 전체의 frac 이 될 때까지 선택.
    표본가중치가 개인마다 다르므로 '가중 인원' 기준으로 목표를 맞춘다."""
    if len(order) == 0 or frac <= 0:
        return np.array([], dtype=int)
    cw = np.cumsum(w[order])
    tgt = frac * cw[-1]
    k = int(np.searchsorted(cw, tgt))
    if k > 0 and abs(cw[k - 1] - tgt) <= abs((cw[k] if k < len(cw) else cw[-1]) - tgt):
        pass                                  # k개가 목표에 더 가까움
    else:
        k += 1
    return order[:min(max(k, 0), len(order))]


def _k1000(x):
    """천원 단위 라운딩 (코드북 비고)."""
    return np.round(np.asarray(x, float) / 1000.0) * 1000.0


def _tilt_pick(g, cand, x, w, n_tgt, mean_tgt, th_lo=-6.0, th_hi=6.0):
    """cand 중에서 **가중 인원 = n_tgt** 이고 **x 의 가중평균 = mean_tgt** 이 되도록 뽑는다.

    선택확률 p_i ∝ x_i^θ (지수기울임 = 평균 제약 아래 최대엔트로피 해)를 쓰고,
    θ 는 목표 평균에, 비례상수는 목표 인원에 각각 이분법으로 맞춘다.
    추출은 Efraimidis–Spirakis 가중 무복원추출(포함확률 ∝ p_i)로 한다.
    → 원표(NTS 3-2-3)가 주는 '구간별 근로소득금액 인원·평균'을 B08 총급여 분포에서
      **선택 편의만으로** 재현한다(금액을 손대지 않으므로 B08 과의 개인 단위 일치가 보존된다)."""
    cand = np.asarray(cand, int)
    if len(cand) == 0 or n_tgt <= 0:
        return np.array([], dtype=int)
    xx = np.maximum(np.asarray(x, float)[cand], 1.0)
    ww = np.asarray(w, float)[cand]
    Wt = float(ww.sum())
    if Wt <= 0:
        return np.array([], dtype=int)
    n_tgt = min(n_tgt, Wt)
    lx = np.log(xx); lx = lx - lx.mean()

    def _p(th):
        sc = np.exp(np.clip(th * lx, -50, 50))
        lo, hi = 1e-12, 1e12
        for _ in range(60):
            c = np.sqrt(lo * hi)
            if float((ww * np.minimum(1.0, c * sc)).sum()) < n_tgt:
                lo = c
            else:
                hi = c
        return np.minimum(1.0, np.sqrt(lo * hi) * sc)

    lo, hi = th_lo, th_hi
    for _ in range(40):
        th = 0.5 * (lo + hi)
        p = _p(th)
        den = float((ww * p).sum())
        m = float((ww * p * xx).sum()) / max(den, 1e-9)
        if m < mean_tgt:
            lo = th
        else:
            hi = th
    def _draw(aim):
        l2, h2 = th_lo, th_hi
        for _ in range(40):
            th2 = 0.5 * (l2 + h2)
            pp = _p(th2)
            dd = float((ww * pp).sum())
            mm = float((ww * pp * xx).sum()) / max(dd, 1e-9)
            if mm < aim:
                l2 = th2
            else:
                h2 = th2
        pp = _p(0.5 * (l2 + h2))
        u = np.clip(g.random(len(cand)), 1e-12, 1.0)
        key = np.where(pp >= 1.0, 0.0, np.log(u) / np.maximum(pp, 1e-12))
        return _quota_w(cand[np.argsort(-key)], w, n_tgt / Wt)

    # 유한표본에서는 포함확률대로 뽑아도 실현 평균이 흔들린다(상위 몇 행의 영향이 크다).
    # 목표를 실현치 비율로 되돌려 최대 6회 재추출하고 오차가 가장 작은 표본을 쓴다.
    aim, best, err = mean_tgt, None, np.inf
    for _ in range(6):
        pk = _draw(aim)
        if len(pk) == 0:
            return pk
        mm = float((w[pk] * np.maximum(np.asarray(x, float)[pk], 1.0)).sum()
                   / max(float(w[pk].sum()), 1e-9))
        e = abs(mm / mean_tgt - 1.0)
        if e < err:
            best, err = pk, e
        if e < 0.01:
            break
        aim = float(np.clip(aim * (mean_tgt / max(mm, 1e-9)) ** 0.9,
                            0.2 * mean_tgt, 5.0 * mean_tgt))
    return best


def _quota_idx(order, w, n_tgt):
    """order(우선순위) 를 따라 가중 인원이 n_tgt 가 될 때까지 선택."""
    order = np.asarray(order, int)
    if len(order) == 0 or n_tgt <= 0:
        return np.array([], dtype=int)
    tot = float(w[order].sum())
    if tot <= 0:
        return np.array([], dtype=int)
    return _quota_w(order, w, min(1.0, n_tgt / tot))


# ── 파라미터 로드 ────────────────────────────────────────────────────────────
def _load():
    P = {}
    P['filer'] = _T('B07_NTS_3-1-3_종합소득신고_성연령_2022')
    P['brk_sex'] = _T('B07_NTS_3-2-2_성별_종합소득규모별_신고인원_2022')
    P['brk_type'] = _T('B07_NTS_3-2-3_종합소득규모별_소득종류별_2022')
    P['brk_tax'] = _T('B07_NTS_3-1-4_종합소득규모별_결정세액_2022')
    P['ratio'] = _T('B07_NTS_3-1-2_소득종류별_총수입금액_소득금액_2022')
    P['rent'] = _T('B07_NTS_3-2-3-3_부동산임대소득_유형별_2022')
    P['sehou'] = _T('B07_NTS_3-2-3-2_분리과세주택임대_성연령_2022')
    P['rural'] = _T('B07_NTS_3-1-6_농어촌특별세_2022')
    P['setax'] = _T('B07_NTS_3-1-1-2_종합_분리과세_결정세액_2022')
    pop = pd.read_csv(os.path.join(RAW, 'POPUL_MOIS01_2022_11_sigungu_age1_sex.csv'))
    pop = pop[(pop.level == 'sigungu') & (pop.sex.isin(['male', 'female']))]
    P['N_pop'] = float(pop['pop'].sum())
    return P


def generate(df, params, ctx):
    g = core.rng('B07')
    P = _load()
    n = len(df)
    idx = np.arange(n)
    age = df['age'].values.astype(int)
    sex = df['gender'].values.astype(int)
    band = _band(age)
    ui = df['_u_income'].values
    wt = (df['indwgt'].values.astype(float) if 'indwgt' in df.columns
          else np.full(n, P['N_pop'] / n))            # 가중 인원 기준 배분에 사용

    out = pd.DataFrame(index=df.index)

    # ── 0) 상위 블록 연계 값 (B08 연말정산 근로소득 · B09 원천징수 지급명세서) ──
    #   B08(order2) 총급여 = labinc_sum_taxy − labinc_sum_taxn
    b08 = np.zeros(n)
    if 'labinc_sum_taxy' in df.columns:
        taxy = pd.to_numeric(df['labinc_sum_taxy'], errors='coerce').fillna(0).values
        taxn = (pd.to_numeric(df['labinc_sum_taxn'], errors='coerce').fillna(0).values
                if 'labinc_sum_taxn' in df.columns else np.zeros(n))
        b08 = np.maximum(taxy - taxn, 0.0)
    has_b08 = b08 > 0
    #   B09(order2) 원천징수 사업소득·연말정산 사업소득·기타소득 지급명세서 보유
    def _have(c):
        return df[c].notna().to_numpy() if c in df.columns else np.zeros(n, bool)
    b09_biz = _have('binc_sum') | _have('ybinc_sum')
    b09_oth = _have('othinc_sum')

    bt = P['brk_type']
    pt = bt.pivot_table(index='ord', columns='type', values='n', aggfunc='first')
    at = bt.pivot_table(index='ord', columns='type', values='amt_mil', aggfunc='first')
    ratio = P['ratio'].set_index('type')['income_ratio']
    lab_ratio = float(ratio['근로소득'])          # 근로소득금액/총급여 = 0.7746
    SCALE = float(wt.sum()) / P['N_pop']          # 전국 인원 → 표본 가중 인원 환산

    # ── 1) 종합과세 신고자 선정 (성·연령별 신고확률) ─────────────────────────
    #   우선순위 = _u_income 코퓰러
    #     + 원천징수 사업소득 지급명세서 보유 (3.3% 원천징수분을 환급받으려면 확정신고를
    #       해야 하므로 인적용역 사업소득자는 대부분 종합소득세 신고자다 [논리적추론])
    #     + 근로소득 보유 (근로 외 소득 합산신고)
    #   + 구간 **내부** 연령 프로파일 φ(a) (위 _age_w). 구간 신고인원은 보존한 채
    #     5세 계급별 신고확률 p_u = rate × φ̄_u / φ̄_band 로 나누어 배정한다.
    filer = np.zeros(n, dtype=bool)
    ft = P['filer'].set_index(['sex', 'band'])
    nb, ns = _age_norm()
    sub5 = _sub5(age)
    for s in (1, 2):
        for b in BANDS:
            m = np.flatnonzero((sex == s) & (band == b))
            if len(m) == 0 or (s, b) not in ft.index:
                continue
            rate = float(ft.loc[(s, b), 'rate_filer'])
            sc = np.zeros(n)
            sc[m] = (_copula(g, _rank01(ui[m]), RHO_FILE)
                     + BONUS_BIZ * b09_biz[m] + BONUS_LAB * has_b08[m])
            d = nb.get((s, b), 1.0)
            if d <= 0:
                continue
            for u in np.unique(sub5[m]):
                mm = m[sub5[m] == u]
                p_u = float(np.clip(rate * ns.get((s, int(u)), d) / d, 0.0, 0.95))
                filer[_quota_w(mm[np.argsort(-sc[mm])], wt, p_u)] = True

    # ── 2) 근로소득 신고자 확정 → 종합소득금액 구간 배정 ─────────────────────
    #   NTS 3-2-3 은 구간별 '근로소득금액' 인원 L_k 와 평균 μ_k 를 준다.
    #   총급여 목표 T_k = μ_k / 소득률. B08 총급여 분포에서 (인원 ΣL_k, 평균 T̄) 을
    #   만족하도록 신고자를 뽑고(_tilt_pick), 총급여 오름차순으로 T_k 순서에 맞춰
    #   구간을 부여한다 → 개인 단위 inc_labinc_sum = B08 총급여를 유지하면서
    #   전국 총수입금액(3-1-2 188,985,111백만원)과 구간별 근로소득금액을 동시에 맞춘다.
    n_b = bt[bt.type == '종합소득금액'].set_index('ord')['n']
    L_k = pt['근로소득금액'].reindex(range(0, 11)).fillna(0.0).to_numpy() * SCALE
    mu_k = np.array([float(at.loc[k, '근로소득금액']) * 100.0
                     / max(float(pt.loc[k, '근로소득금액']), 1.0) for k in range(0, 11)])
    T_k = mu_k / lab_ratio                          # 구간별 목표 총급여 (만원)
    N_lab = float(L_k.sum())
    T_bar = float((L_k * T_k).sum() / max(N_lab, 1e-9))
    cand_lab = np.flatnonzero(filer & has_b08)
    lab_sel = np.zeros(n, dtype=bool)
    pick = _tilt_pick(g, cand_lab, b08 / MAN, wt, N_lab, T_bar)
    lab_sel[pick] = True

    brk = np.full(n, -1, dtype=int)
    order_k = np.argsort(T_k)                       # 총급여 오름차순 구간 순서
    sel = np.flatnonzero(lab_sel)
    if len(sel):
        o = sel[np.argsort(b08[sel], kind='mergesort')]
        cw = np.cumsum(wt[o])
        cut = 0.0
        for k in order_k:
            cut2 = cut + L_k[k]
            i0 = int(np.searchsorted(cw, cut)); i1 = int(np.searchsorted(cw, cut2))
            if k == order_k[-1]:
                i1 = len(o)
            brk[o[i0:i1]] = int(k)
            cut = cut2
        brk[o[brk[o] < 0]] = int(order_k[-1])

    # 나머지 신고자 → 잔여 구간 정원을 _u_income 순위로 채운다 (성별 3-2-2 분포).
    #   순위에는 **연령대 오프셋 δ** 를 더해 NTS 3-1-3 의 성×연령별 종합소득금액
    #   평균(= sum_income / n_filer, 만원)에 맞춘다. 정원은 바뀌지 않는다.
    mu_brk = np.array([float(P['brk_tax'].set_index('ord').loc[k, 'mean_income_manwon'])
                       for k in range(11)])
    tmean = {(int(r.sex), r.band): float(r.sum_income_mil) * 100.0 / float(r.n_filer)
             for r in P['filer'].itertuples()}
    for s in (1, 2):
        m_s = np.flatnonzero(filer & (sex == s))
        if len(m_s) == 0:
            continue
        bs = P['brk_sex'][P['brk_sex'].sex == s].sort_values('ord')
        w_all = float(wt[m_s].sum())
        p0 = float(n_b.loc[0] / n_b.sum())
        cap = np.zeros(11)
        cap[0] = p0 * w_all
        bw = bs.n.values / bs.n.values.sum()
        cap[1:] = (1.0 - p0) * w_all * bw
        used = np.array([float(wt[(brk == k) & (sex == s)].sum()) for k in range(11)])
        resid = np.maximum(cap - used, 0.0)
        rest = np.flatnonzero(filer & (sex == s) & (brk < 0))
        if len(rest) == 0:
            continue
        tot_r = float(wt[rest].sum())
        if resid.sum() > 0:
            resid = resid * (tot_r / resid.sum())
        else:
            resid = np.full(11, tot_r / 11.0)
        # "0 이하" 구간은 무작위, 나머지는 소득순위 오름차순
        sel0 = _quota_idx(rest[g.permutation(len(rest))], wt, resid[0])
        brk[sel0] = 0
        rest = np.setdiff1d(rest, sel0)
        if len(rest):
            r = _copula(g, _rank01(ui[rest]), RHO_BRACKET)
            z = norm.ppf(np.clip(r, 1e-6, 1 - 1e-6))
            wr = wt[rest]
            bi_r = np.array([BANDS.index(b) for b in band[rest]], int)

            def _fill(zz):
                """정규점수 zz 오름차순으로 구간 정원(resid)을 채운다 (정원 불변)."""
                a = np.full(len(rest), -1, int)
                o = np.argsort(zz, kind='mergesort')
                cw = np.cumsum(wr[o]); cut = 0.0
                for k in range(1, 11):
                    cut2 = cut + resid[k]
                    i0 = int(np.searchsorted(cw, cut)); i1 = int(np.searchsorted(cw, cut2))
                    if k == 10:
                        i1 = len(o)
                    a[o[i0:i1]] = k
                    cut = cut2
                a[a < 0] = 10
                return a

            #  이미 확정된 부분(근로소득 신고자 + "0 이하")의 금액·정원
            fixed = np.zeros(len(BANDS)); cellw = np.zeros(len(BANDS))
            for bi, b in enumerate(BANDS):
                cm = np.flatnonzero(filer & (sex == s) & (band == b))
                cellw[bi] = float(wt[cm].sum())
                fx = cm[brk[cm] >= 0]
                fixed[bi] = float((wt[fx] * mu_brk[brk[fx]]).sum())
            tgtm = np.array([tmean.get((s, b), np.nan) for b in BANDS])

            delta = np.zeros(len(BANDS)); best, berr = _fill(z), np.inf
            for _ in range(CAL_ITER):
                a = _fill(z + delta[bi_r])
                got = fixed.copy()
                np.add.at(got, bi_r, wr * mu_brk[a])
                got = got / np.maximum(cellw, 1e-9)
                ok = np.isfinite(tgtm) & (cellw > 0)
                e = float(np.abs(np.log(np.maximum(got[ok], 1.0) /
                                        np.maximum(tgtm[ok], 1.0))).sum())
                if e < berr:
                    best, berr = a, e
                delta = np.clip(delta + CAL_ETA * np.where(
                    ok, np.log(np.maximum(tgtm, 1.0) / np.maximum(got, 1.0)), 0.0),
                    -4.0, 4.0)
            brk[rest] = best

    infiler = brk >= 0

    # ── 3) 구간 내 종합소득금액 (만원) ──────────────────────────────────────
    tax_tab = P['brk_tax'].set_index('ord')
    tot_man = np.zeros(n)
    for k, (lo, hi) in BEDGE.items():
        m = np.flatnonzero(brk == k)
        if len(m) == 0:
            continue
        mean = float(tax_tab.loc[k, 'mean_income_manwon'])
        v = _copula(g, _rank01(ui[m]), RHO_WITHIN)
        if hi is None:                                 # 개방구간 → 파레토
            alpha = mean / max(mean - lo, 1.0)
            x = lo * (1.0 - v * (1 - 1e-9)) ** (-1.0 / alpha)
            top = lo * 400.0
        else:
            a = _beta1_from_mean(lo, hi, mean)
            x = lo + (hi - lo) * v ** (1.0 / a)
            top = hi
        # 가중 표본 평균을 구간 평균에 정렬 (개방구간 파레토는 α<2 로 평균이 매우 불안정)
        ww = wt[m]
        for _ in range(6):
            cur = float((x * ww).sum() / ww.sum())
            x = np.clip(x * (mean / max(cur, 1e-9)), lo, top)
        # 근로소득 신고자는 총급여 순위와 종합소득금액 순위를 일치시킨다
        # (근로소득금액 ≤ 종합소득금액 이라는 정의상 제약을 위반하는 사례를 줄인다)
        loc = np.flatnonzero(lab_sel[m])
        if len(loc) > 1:
            xs = np.sort(x[loc])
            x[loc[np.argsort(np.argsort(b08[m[loc]]))]] = xs
        tot_man[m] = x

    # ── 4) 소득종류 배분 (3-2-3 구간별 인원·금액) ───────────────────────────
    #   · 근로소득 보유자는 2)에서 확정 (B08 보유자와 일치)
    #   · 나머지 종류는 **구간별 인원을 가중 쿼터로 정확히** 배정한다.
    #     선호점수: 사업소득 → B09 원천징수 사업소득 보유자, 기타소득 → B09 기타소득
    #     보유자 (지급명세서가 있는 소득이 종합과세로 넘어오는 것이 실제 경로다).
    #     동시에 '아직 아무 종류도 없는 신고자'를 우선해 무(無)소득 신고자를 없앤다.
    amt = {t: np.zeros(n) for t in TYPES}
    J = TYPES.index('근로소득금액')
    #   기타소득은 '기타소득금액 300만원 초과' 라야 종합과세로 넘어오므로(소득세법 §14③8호)
    #   B09 지급명세서 보유자 **중 금액이 큰 쪽**을 우선한다.
    oth_rk = np.zeros(n)
    if b09_oth.any():
        v = pd.to_numeric(df['othinc_sum'], errors='coerce').fillna(0).to_numpy()
        hh = np.flatnonzero(b09_oth)
        oth_rk[hh] = W_OTH * (0.10 + 0.90 * _rank01(v[hh]))   # 보유자 **내부** 금액순위
    PREF = {'사업소득금액': W_PREF * b09_biz.astype(float), '기타소득금액': oth_rk}
    for k in range(1, 11):
        m = np.flatnonzero(brk == k)
        if len(m) == 0:
            continue
        nb = float(pt.loc[k, '종합소득금액'])
        p = np.array([min(1.0, float(pt.loc[k, t]) / nb) for t in TYPES])
        mu = np.array([float(at.loc[k, t]) * 100.0 / max(float(pt.loc[k, t]), 1.0)
                       for t in TYPES])              # 보유자 평균(만원)
        ind = np.zeros((len(m), len(TYPES)))
        ind[:, J] = lab_sel[m].astype(float)
        wm = wt[m]
        tot_w = float(wm.sum())
        for ti in np.argsort(-p):
            if ti == J:
                continue
            ncnt = ind.sum(axis=1)
            pr = PREF.get(TYPES[ti], np.zeros(n))[m]
            sc = COVER * (ncnt == 0) + pr + g.random(len(m))
            free = np.flatnonzero(ind[:, ti] == 0)
            take = _quota_idx(free[np.argsort(-sc[free])], wm, p[ti] * tot_w)
            ind[take, ti] = 1.0
        # 어떤 종류도 없는 신고자 ↔ 2종 이상 보유자 사이에서 교환 (인원 총량 보존)
        no = np.flatnonzero(ind.sum(axis=1) == 0)
        if len(no):
            for i in no:
                cnt = ind.sum(axis=1)
                donors = np.flatnonzero((cnt >= 2))
                if len(donors) == 0:
                    break
                d = donors[int(np.argmax(wm[donors]))]
                tj = int(np.argmax(np.where(ind[d] > 0, mu, -1)))
                tj = int(np.flatnonzero(ind[d] > 0)[0]) if tj == J else tj
                if tj == J:
                    continue
                ind[d, tj] = 0.0
                ind[i, tj] = 1.0

        base = ind * mu[None, :]
        ssum = base.sum(axis=1, keepdims=True)
        w_ = np.where(ssum > 0, base / np.maximum(ssum, 1e-9), 0.0)
        gam = np.where(w_ > 0, g.gamma(np.maximum(DIR_KAPPA * w_, 1e-9)), 0.0)
        sh = gam / np.maximum(gam.sum(axis=1, keepdims=True), 1e-12)
        tm = tot_man[m]
        X = sh * tm[:, None]
        # 구간별 소득종류 금액구성을 3-2-3 에 정렬하는 RAS (행합=종합소득금액 고정)
        tgt = np.array([float(at.loc[k, t]) for t in TYPES]); tgt = tgt / tgt.sum()
        ww = wm[:, None]
        for _ in range(RAS_ITER):
            cs = (X * ww).sum(axis=0)
            f = np.where(cs > 0, tgt * cs.sum() / np.maximum(cs, 1e-9), 1.0)
            X = X * np.clip(f, 0.05, 20.0)[None, :]
            X = X * (tm[:, None] / np.maximum(X.sum(axis=1, keepdims=True), 1e-9))
        for ti, t in enumerate(TYPES):
            amt[t][m] = X[:, ti]

    # ── 5) "0 이하" 구간: 3-2-3 구간별 보유율·평균으로 직접 배정 + 결손 ────
    #     결손 근거: 3-1-1-2 결손소득 344,374명 · 7,583,586백만원 (1인 평균 2,202만원)
    m0 = np.flatnonzero(brk == 0)
    if len(m0):
        nb0 = float(pt.loc[0, '종합소득금액'])
        for t in TYPES:
            if t == '근로소득금액':
                continue
            p0 = min(1.0, float(pt.loc[0, t]) / nb0)
            mu0 = float(at.loc[0, t]) * 100.0 / max(float(pt.loc[0, t]), 1.0)
            hit = g.random(len(m0)) < p0
            v = core.lognormal_mean(g, np.full(len(m0), mu0), 1.0, len(m0))
            if hit.sum() > 0:
                v = v * (mu0 / max(v[hit].mean(), 1e-9))
            amt[t][m0] = np.where(hit, v, 0.0)
        neg = amt['사업소득금액'][m0] <= 0             # 사업소득 미보유자 → 결손 기록
        loss = core.lognormal_mean(g, np.full(len(m0), 2202.0), 1.0, len(m0))
        if neg.sum() > 0:
            loss = loss * (2202.0 / max(loss[neg].mean(), 1e-9))
        amt['사업소득금액'][m0] = np.where(neg, -loss, amt['사업소득금액'][m0])
        tot_man[m0] = 0.0

    # ── 5b) B08 연계: 근로소득금액 = 총급여 × 소득률 (개인 단위 일치) ────────
    ml = np.flatnonzero(lab_sel & infiler)
    amt['근로소득금액'][:] = 0.0
    amt['근로소득금액'][ml] = (b08[ml] / MAN) * lab_ratio

    # ── 5c) 구간 평균(3-1-4) ↔ 소득종류 전국 총액(3-2-3) 이원 정렬 ───────────
    #   근로소득금액은 B08 에 고정되어 있으므로 배율 대상에서 제외하고,
    #   나머지 6종류로 구간 평균과 종류별 총액을 번갈아 맞춘다(IPF 성격, 5회).
    OTHERS = [t for t in TYPES if t != '근로소득금액']
    for _ in range(5):
        for t in OTHERS:                             # (a) 종류별 전국 총액
            tgt_t = float(at[t].sum()) * 100.0       # 백만원 → 만원
            pmask = amt[t] > 0
            cur = float((amt[t][pmask] * wt[pmask]).sum()) / SCALE
            if cur <= 0 or tgt_t <= 0:
                continue
            amt[t] = np.where(pmask, amt[t] * float(np.clip(tgt_t / cur, 0.4, 2.5)), amt[t])
        for k in range(1, 11):                       # (b) 구간별 가중평균
            m = np.flatnonzero(brk == k)
            if len(m) == 0:
                continue
            ww = wt[m]
            lab = amt['근로소득금액'][m]
            oth = np.sum([np.maximum(amt[t][m], 0.0) for t in OTHERS], axis=0)
            cur = float(((lab + oth) * ww).sum() / ww.sum())
            need = float(tax_tab.loc[k, 'mean_income_manwon'])
            base = float((oth * ww).sum() / ww.sum())
            if base <= 0 or cur <= 0:
                continue
            f = float(np.clip((need - float((lab * ww).sum() / ww.sum())) / base, 0.25, 4.0))
            for t in OTHERS:
                amt[t][m] = np.where(amt[t][m] > 0, amt[t][m] * f, amt[t][m])
    tot_man = np.where(brk >= 1,
                       np.sum([np.maximum(amt[t], 0.0) for t in TYPES], axis=0), tot_man)


    # ── 6) 부동산임대 → 상가·기타(inc_reinc) / 주택(inc_hou) 분해 ────────────
    rt = P['rent'].set_index('type')
    n_house = float(rt.loc['주택 임대소득 [C]', 'n'])
    n_rent_uniq = float(pt.loc[:, '부동산임대소득금액'].sum())
    p_house = min(0.9, n_house / max(n_rent_uniq, 1.0))
    sh_house = float(rt.loc['주택 임대소득 [C]', 'income_mil']) / float(rt['income_mil'].sum())
    mean_house_share = min(0.95, sh_house / p_house)
    reinc = amt['부동산임대소득금액'].copy()
    hou = np.zeros(n)
    mr = np.flatnonzero(reinc > 0)
    if len(mr):
        # 금액 순위로 계통추출 → 주택임대 보유자 집합이 금액분포를 대표하게 한다
        sel = _syst(g, mr[np.argsort(reinc[mr])], round(len(mr) * p_house))
        if len(sel):
            s_ = g.beta(mean_house_share * 4.0, (1 - mean_house_share) * 4.0, len(sel))
            s_ = np.clip(s_ * (mean_house_share / max(s_.mean(), 1e-9)), 0.02, 1.0)
            hou[sel] = reinc[sel] * s_
            reinc[sel] = reinc[sel] - hou[sel]

    # ── 7) 총수입금액 (3-1-2·3-2-3-3 소득률의 역수, 개인별 잡음) ─────────────
    rr = P['ratio'].set_index('type')
    # 사업소득 소득률 = (사업·부동산 소득금액 − 부동산임대 소득금액) / (동 총수입금액 차)
    r_biz = ((float(rr.loc['사업·부동산소득', 'income_amt_mil']) - float(rt['income_mil'].sum()))
             / (float(rr.loc['사업·부동산소득', 'revenue_amt_mil']) - float(rt['revenue_mil'].sum())))
    r_rent = ((float(rt.loc['상가 임대소득', 'income_mil']) + float(rt.loc['기타부동산 임대소득 [D]', 'income_mil']))
              / (float(rt.loc['상가 임대소득', 'revenue_mil']) + float(rt.loc['기타부동산 임대소득 [D]', 'revenue_mil'])))
    r_hou = float(rt.loc['주택 임대소득 [C]', 'income_ratio'])
    r_pens = float(ratio['연금소득'])
    r_oth = float(ratio['기타소득'])
    r_div = float(ratio['배당소득'])

    def rev(income, r):
        """소득금액 → 총수입금액. 개인별 소득률에 Beta 잡음을 주되
        표본 전체의 Σ소득금액/Σ총수입금액 이 목표 소득률 r 과 일치하도록 정렬한다
        (1/z 의 Jensen 편향 제거)."""
        z = np.clip(g.beta(6.0, 6.0 * (1 - r) / max(r, 1e-6), n), 0.02, 0.98)
        v = np.where(income > 0, income / z, 0.0)
        tot_i, tot_v = income[income > 0].sum(), v.sum()
        if tot_v > 0 and tot_i > 0:
            v = v * (tot_i / r) / tot_v
        return v

    binc_sum = rev(amt['사업소득금액'], r_biz)
    # 결손(음수 사업소득) 신고자도 총수입금액은 존재한다. 3-1-4 "0 이하" 구간의 총수입금액
    # 56,848,200백만원 ÷ 3-1-1-2 결손소득 7,583,586백만원 = 7.50 배를 결손액에 곱해 부여하고
    # [논리적추론], 열 전체를 전국 총수입금액 목표(Σ양수소득/소득률)에 다시 정렬한다.
    negb = amt['사업소득금액'] < 0
    if negb.any():
        binc_sum[negb] = np.abs(amt['사업소득금액'][negb]) * 7.50
        tgt_rev = float((np.maximum(amt['사업소득금액'], 0.0) * wt).sum()) / r_biz
        cur_rev = float((binc_sum * wt).sum())
        if cur_rev > 0:
            binc_sum = binc_sum * (tgt_rev / cur_rev)
    reinc_sum = rev(reinc, r_rent)
    hou_sum = rev(hou, r_hou)
    lab_sum = rev(amt['근로소득금액'], lab_ratio)
    mb = np.flatnonzero(lab_sel & infiler & (b08 > 0))
    lab_sum[mb] = b08[mb] / MAN                        # 총급여 = B08 값 그대로 (개인 단위 일치)
    pens_sum = rev(amt['연금소득금액'], r_pens)
    oth_sum = rev(amt['기타소득금액'], r_oth)

    # ── 8) 결정세액 (구간별 유효세율·과세인원비) ────────────────────────────
    tax_man = np.zeros(n)
    for k in range(0, 11):
        m = np.flatnonzero(brk == k)
        if len(m) == 0:
            continue
        share = float(tax_tab.loc[k, 'share_with_tax'])
        r = tax_tab.loc[k, 'eff_tax_rate']
        r = 0.0 if not np.isfinite(r) else float(r)
        # 순위·정렬은 모두 **가중** 기준으로 한다. 표본가중치가 개인마다 다르므로
        # 비가중 합으로 맞추면 전국 총액이 어긋난다(이전 판 −18.1% 이탈의 원인).
        ww = wt[m]
        o = np.argsort(tot_man[m], kind='mergesort')
        cwp = np.empty(len(m)); cw_ = np.cumsum(ww[o])
        cwp[o] = (cw_ - 0.5 * ww[o]) / cw_[-1]
        pos = cwp
        has = pos >= (1.0 - share)                     # 구간 내 상위부터 과세
        if k == 0:                                     # 0 이하 구간: 결정세액 평균 132만원
            mean0 = (float(tax_tab.loc[0, 'sum_tax_mil']) * 100.0
                     / max(float(tax_tab.loc[0, 'n_tax']), 1.0))
            v = np.where(has, core.lognormal_mean(g, np.full(len(m), mean0), 0.9, len(m)), 0.0)
            sw = float((v * ww).sum())
            if sw > 0:
                v = v * (mean0 * float(ww[has].sum()) / sw)
            tax_man[m] = v
            continue
        eff = r / max(share, 1e-9)
        base = tot_man[m] * eff * (0.6 + 0.8 * pos)    # 구간 내 누진 반영
        v = np.where(has, base, 0.0)
        s = float((v * ww).sum())
        if s > 0:                                      # 구간 총액을 목표 유효세율에 정렬
            v = v * (float((tot_man[m] * ww).sum()) * r / s)
        tax_man[m] = v

    # ── 9) 분리과세 주택임대 (3-2-3-2) ─────────────────────────────────────
    seh_rev = np.zeros(n); seh_inc = np.zeros(n); seh_tax = np.zeros(n)
    st = P['sehou'].set_index(['sex', 'band'])
    popt = P['filer'].set_index(['sex', 'band'])['pop_2022_11']
    inc_ratio_seh = float(P['sehou'].income_mil.sum() / P['sehou'].revenue_mil.sum())
    p_pos_seh = float(P['sehou'].n_income.sum() / P['sehou'].n_revenue.sum())
    tax_ratio_seh = float(P['sehou'].tax_mil.sum() / P['sehou'].income_mil.sum())
    sehou_pick = np.zeros(n, dtype=bool)
    for s in (1, 2):
        for b in BANDS:
            if (s, b) not in st.index:
                continue
            m = np.flatnonzero((sex == s) & (band == b))
            if len(m) == 0:
                continue
            rate = float(st.loc[(s, b), 'n_revenue']) / float(popt.loc[(s, b)])
            # 부동산임대 보유자·고소득자 우선 (실제 신고자의 39%가 종합과세 동시신고)
            sc = (0.62 * _rank01(ui[m]) + 0.12 * (hou[m] + reinc[m] > 0)
                  + 0.26 * g.random(len(m)))
            sel = _quota_w(m[np.argsort(-sc)], wt, rate)
            if len(sel) == 0:
                continue
            sehou_pick[sel] = True
            mean_rev = float(st.loc[(s, b), 'revenue_mil']) * 100.0 / float(st.loc[(s, b), 'n_revenue'])
            v = core.lognormal_mean(g, np.full(len(sel), mean_rev), 0.75, len(sel))
            seh_rev[sel] = v * (mean_rev / max(v.mean(), 1e-9))
    msh = np.flatnonzero(sehou_pick)
    if len(msh):
        haspos = np.zeros(len(msh), dtype=bool)
        haspos[g.permutation(len(msh))[:int(round(len(msh) * p_pos_seh))]] = True
        seh_inc[msh] = np.where(haspos, seh_rev[msh] * inc_ratio_seh / p_pos_seh, 0.0)
        seh_tax[msh] = seh_inc[msh] * tax_ratio_seh

    indb = infiler | sehou_pick                        # B07 DB 수록 대상

    # ── 10) 농어촌특별세 (3-1-6: 189,439명, 1인 평균 143.4만원) ─────────────
    rural = np.zeros(n)
    n_ru = float(P['rural'].n.iloc[0]); amt_ru = float(P['rural'].tax_mil.iloc[0])
    rate_ru = n_ru / P['N_pop']
    cand = np.flatnonzero(infiler & (amt['사업소득금액'] > 0))
    if len(cand) > 0:
        frac = n_ru / max(float((wt[cand]).sum()), 1.0)
        sc = np.sqrt(np.maximum(amt['사업소득금액'][cand], 1.0)) * g.random(len(cand))
        sel = _quota_w(cand[np.argsort(-sc)], wt, min(1.0, frac))
        mu_ru = amt_ru * 100.0 / n_ru                  # 1인 평균 143.4만원
        v = core.lognormal_mean(g, np.full(len(sel), mu_ru), 0.9, len(sel))
        rural[sel] = v * (mu_ru / max(v.mean(), 1e-9))

    # ── 11) 조립 (만원 → 원, 천원 라운딩, 비신고자 NaN) ─────────────────────
    nan = np.full(n, np.nan)

    def col(v, mask=None):
        m = indb if mask is None else mask
        x = np.where(m, _k1000(np.asarray(v) * MAN), np.nan)
        return x

    out['inc_binc_sum'] = col(np.where(binc_sum > 0, binc_sum, 0.0))
    out['inc_reinc_sum'] = col(np.where(reinc_sum > 0, reinc_sum, 0.0))
    out['inc_hou_sum'] = col(np.where(hou_sum > 0, hou_sum, 0.0))
    out['inc_sehou_sum'] = col(seh_rev)
    out['inc_labinc_sum'] = col(np.maximum(lab_sum, 0.0))
    out['inc_other_sum'] = col(np.maximum(oth_sum, 0.0))
    out['inc_seother_sum'] = nan                      # 규모 미달 (전국 381명)
    out['inc_binc'] = col(amt['사업소득금액'])
    out['inc_reinc'] = col(reinc)
    out['inc_hou'] = col(hou)
    out['inc_sehou'] = col(seh_inc)
    out['inc_labinc'] = col(np.maximum(amt['근로소득금액'], 0.0))
    out['inc_other'] = col(np.maximum(amt['기타소득금액'], 0.0))
    out['inc_seothe'] = nan                           # 규모 미달 (전국 381명)
    out['inc_inter'] = col(np.maximum(amt['이자소득금액'], 0.0))
    out['inc_allo'] = col(np.maximum(amt['배당소득금액'], 0.0) / r_div)
    out['inc_pens_sum'] = col(np.maximum(pens_sum, 0.0))
    out['inc_pens'] = col(np.maximum(amt['연금소득금액'], 0.0))
    out['inc_total_tax'] = col(np.maximum(tax_man, 0.0))
    out['inc_total_ruraltax'] = col(rural)
    out['inc_total_setax'] = col(seh_tax)

    # 진단용 헬퍼 (최종 산출물에서 제외)
    out['_inc_filer'] = indb.astype(np.int8)
    out['_inc_total_man'] = np.where(indb, tot_man, np.nan)
    return out
