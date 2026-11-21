# -*- coding: utf-8 -*-
"""B08 연말정산 근로소득DB — labinc_sum_taxy / labinc_sum_taxn / labinc_inc_taxamt /
   labinc_residence_taxamt / labinc_rural_taxamt   (A2 / order 2)

■ 소스 (등급순)
  S1  국세청 국세통계 2023년 발행(2022년 귀속) — TASIS 원기관 직접 조회분 [1차확인 2026-09-02]
      <4-2-3> 근로소득 연말정산 신고 현황Ⅲ(성, 연령)   params/raw/NTS_4-2-3_*.csv
              → 성×연령대 신고인원·급여총계·비과세소득·결정세액
      <4-2-4> 근로소득 연말정산 신고 현황Ⅳ(과세대상근로소득 규모)  params/raw/NTS_4-2-4_*.csv
              → 총급여 15구간 인원·금액, 결정세액 있는자/없는자, 구간별 결정세액·비과세소득
      <4-2-1> 근로소득 연말정산 신고 현황Ⅰ(총괄)  params/raw/NTS_4-2-1_*.csv
              → 통제총계(인원 20,534,714 / 급여총계 869,287,953백만원 / 결정세액 59,145,880백만원)
              → 세액감면 내역(조특법상 중소기업취업세액감면 1,066,580명·943,451백만원) = 농특세 판정 근거
      ※ 지시서의 S2 KOSIS DT_13301N_A423/A424/A425 와 동일 원천이며 등급이 한 단계 높다(§1).
  S2  행정안전부 주민등록 인구통계 2022.11 (성×1세×시군구) — 보유율의 분모  [1차확인]
  S4  농어촌특별세법 제4·5조 및 시행령 제4조  params/tab/S4_농어촌특별세_*.csv  [1차확인]
  S0  R01 <표 2-30> 개인근로소득 분포 / <표 2-33> 개인일차소득 분포
      params/tab/S0_R01_T2-30_*.csv, T2-33  → 검증 목표(2020년 기준)

■ 생성 절차 (§6 B08)
  1) 보유 판정 : p(성, 연령대) = 4-2-3 급여총계 인원 / 주민등록 인구 → _u_income 상관 점수 상위 p
  2) 과세대상근로소득 : 4-2-4 15구간 히스토그램을 **순위 보존**으로 추출(구간평균 정확 재현)
                       → 성×연령 셀 평균비(4-2-3)로 스케일
  3) 비과세소득(taxn) : 구간별 보유율·평균(4-2-4 비과세소득 소계)
  4) labinc_sum_taxy = 과세대상근로소득 + 비과세소득  (= 원표의 '급여총계' 정의)
  5) 결정세액 : 구간별 '결정세액이 있는자' 비율로 과세 여부 → 구간 유효세율(로그보간)×과세대상근로소득
  6) 지방소득세 = 소득세 × 10% ; 농어촌특별세 = 전량 NaN (법령상 비과세, 아래 참조)
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core, nts

MW = 1_000_000            # 원표 단위: 백만원 → 원
# 4-2-4 과세대상근로소득(총급여) 구간 라벨 → (하한, 상한) 원
BANDS = [
    ('1천만 이하',   0,            10_000_000),
    ('1.5천만 이하', 10_000_000,   15_000_000),
    ('2천만 이하',   15_000_000,   20_000_000),
    ('3천만 이하',   20_000_000,   30_000_000),
    ('4천만 이하',   30_000_000,   40_000_000),
    ('4.5천만 이하', 40_000_000,   45_000_000),
    ('5천만 이하',   45_000_000,   50_000_000),
    ('6천만 이하',   50_000_000,   60_000_000),
    ('8천만 이하',   60_000_000,   80_000_000),
    ('1억 이하',     80_000_000,  100_000_000),
    ('2억 이하',    100_000_000,  200_000_000),
    ('3억 이하',    200_000_000,  300_000_000),
    ('5억 이하',    300_000_000,  500_000_000),
    ('10억 이하',   500_000_000, 1000_000_000),
    ('10억 초과',  1000_000_000,        None),
]
MERGE = {'1억 초과': '2억 이하'}     # '결정세액이 없는자' 블록의 상위 개방구간 → 2억 이하로 합산
RHO_HOLD, RHO_AMT = 0.55, 0.70      # _u_income 과의 상관 [가정 A2-B08-1]
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
BETA_ALPHA = 1.3                     # 구간 내부 형상 [가정 A2-B08-2]
LOCAL_TAX = 0.10                     # 개인지방소득세 = 소득세액의 10%


# ── 원표 파싱 ────────────────────────────────────────────────────────────────
def _m24(d, col2, meas):
    """4-2-4 에서 (ROW_L1, ROW_L2) → 값. meas ∈ {'인원','금액'}."""
    s = d[d.COL_L2 == col2]
    s = s[(s.COL_L3 == meas) | ((s.COL_L3 == '소계') & (s.COL_L4 == meas))]
    return s.groupby(['ROW_L1', 'ROW_L2'])['VALUE'].sum()


def band_tables():
    """4-2-4 → 구간별 인원·금액·결정세액·비과세소득 (원 단위)."""
    d = nts.nts('4-2-4')
    YES, NO = '결정세액이 있는자 [C]', '결정세액이 없는자'
    lab = [b[0] for b in BANDS]
    idx = {l: i for i, l in enumerate(lab)}
    z = lambda: np.zeros(len(lab))
    n_y, n_n, a_y, a_n, tax, tf_n, tf_a = z(), z(), z(), z(), z(), z(), z()
    src = {'인원': _m24(d, '과세대상근로소득(총급여)', '인원'),
           '금액': _m24(d, '과세대상근로소득(총급여)', '금액'),
           '세액': _m24(d, '결정세액', '금액'),
           '비인': _m24(d, '비과세소득', '인원'),
           '비금': _m24(d, '비과세소득', '금액')}
    for (sec, row), v in src['인원'].items():
        if row == '소계' or sec not in (YES, NO):
            continue
        i = idx[MERGE.get(row, row)]
        (n_y if sec == YES else n_n)[i] += v
    for key, tgt in (('금액', None), ('세액', tax), ('비인', tf_n), ('비금', tf_a)):
        for (sec, row), v in src[key].items():
            if row == '소계' or sec not in (YES, NO):
                continue
            i = idx[MERGE.get(row, row)]
            if key == '금액':
                (a_y if sec == YES else a_n)[i] += v
            else:
                tgt[i] += v
    n, a = n_y + n_n, (a_y + a_n) * MW
    eff = np.divide(tax, np.maximum(a_y, 1), out=np.zeros_like(tax), where=a_y > 0)
    # 최저구간(결정세액 있는자 13명)의 유효세율은 표본이 극소해 불안정 → 단조 증가로 정리
    eff[0] = min(eff[0], eff[1])
    eff = np.maximum.accumulate(eff)
    bt = nts.band_table([b[1] for b in BANDS], [b[2] for b in BANDS], n, a)
    return {'bt': bt, 'n': n, 'n_taxed': n_y,
            'share_taxed': np.divide(n_y, n, out=np.zeros_like(n), where=n > 0),
            'eff_rate': eff,
            'tf_share': np.divide(tf_n, n, out=np.zeros_like(n), where=n > 0),
            'tf_mean': np.divide(tf_a * MW, np.maximum(tf_n, 1), out=np.zeros_like(tf_a), where=tf_n > 0),
            'tot_n': n.sum(), 'tot_amt': a.sum(), 'tot_tax': tax.sum() * MW}


def sex_age_tables():
    """4-2-3 → 성×연령대 신고인원·급여총계 평균(원)."""
    d = nts.nts('4-2-3')
    s = d[(d.ROW_L1.isin(['남성', '여성'])) & (d.ROW_L2 != '소계') & (d.COL_L2 == '급여총계')]
    n = s[s.COL_L4 == '인원'].pivot_table(index='ROW_L1', columns='ROW_L2', values='VALUE', aggfunc='sum')
    a = s[s.COL_L4 == '금액'].pivot_table(index='ROW_L1', columns='ROW_L2', values='VALUE', aggfunc='sum') * MW
    labs = nts.band_labels()
    n, a = n.reindex(index=['남성', '여성'], columns=labs), a.reindex(index=['남성', '여성'], columns=labs)
    return n, (a / n)


# ── 생성 ─────────────────────────────────────────────────────────────────────
def age_weight(age):
    """구간 내부 연령 프로파일 [가정 A2-B08-4].
    NTS 4-2-3 은 '30세 미만'·'70세 이상'을 한 칸으로 묶어 공표한다. 15세 미만은 근로소득이
    사실상 없고(근로기준법 제64조 취직인허증), 70대 이후 취업률은 급감하므로 구간 안에서
    가중치를 두고, 구간 전체 보유율은 원표 값과 일치하도록 정규화한다.
    60세 이상은 위 상수 주석의 2단 지수감쇠(S0 R01<표4-3>·R02<표4-8> 적합)를 쓴다."""
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


def old_hh_rr(df):
    """65세 이상에 대한 가구유형별 상대위험 (그 외 1.0)."""
    age = np.asarray(df['age'].values, float)
    hid = np.asarray(df['hid'].values)
    o = (age >= 65).astype(np.int8)
    n_old = pd.Series(o).groupby(hid).transform('sum').to_numpy()
    n_all = pd.Series(np.ones(len(age))).groupby(hid).transform('sum').to_numpy()
    rr = np.where(n_old == n_all,
                  np.where(n_all == 1, OLD_RR_ALONE, OLD_RR_ONLY), OLD_RR_MIX)
    return np.where(age >= 65, rr, 1.0)


def apply_old_rr(p, df, sex, band, cols):
    """성×연령대 셀 안에서 65세 이상의 보유확률에 가구유형 상대위험을 적용하고
    65세 이상 부분집합의 평균 확률을 보존하도록 재정규화한다."""
    rr = old_hh_rr(df)
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


def cell_prob(sex, band, age, rate, wfun=None):
    """성×연령대 보유율을 구간 내부 연령가중으로 배분.
    정규화 분모는 **모집단(주민등록 1세 인구) 가중 평균 w** 를 쓴다 → 구간 보유율이
    원표 값과 일치한다(표본 평균으로 정규화하면 표본 연령구성 편의가 남는다)."""
    wfun = wfun or age_weight
    mw = nts.pop_weight_mean(wfun)
    w = wfun(age)
    p = np.zeros(len(age), float)
    for s in ('남성', '여성'):
        for b in rate.columns:
            m = (sex == s) & (band == b)
            if not m.any():
                continue
            d = mw.get((s, b), 1.0)
            p[m] = 0.0 if d <= 0 else np.clip(w[m] / d * float(rate.loc[s, b]), 0.0, 0.98)
    return p


def generate(df, params, ctx):
    g = core.rng('B08')
    n = len(df)
    B = band_tables()
    cnt, cell_mean = sex_age_tables()
    pop = nts.pop_sex_age()
    rate = (cnt / pop).clip(upper=0.95)                 # 성×연령 보유율 (4-2-3 / 주민등록)
    nat_mean = float(B['tot_amt'] / B['tot_n'])         # 전국 평균 과세대상근로소득(원)

    sex = np.where(df['gender'].values == 1, '남성', '여성')
    band = nts.age_band(df['age'].values)
    p = cell_prob(sex, band, df['age'].values, rate)
    p = apply_old_rr(p, df, sex, band, rate.columns)

    u = df['_u_income'].values
    r_hold = nts.score(g, u, RHO_HOLD)
    r_amt = nts.score(g, u, RHO_AMT)
    hold = r_hold > (1.0 - p)

    # 과세대상근로소득 = 전국 구간 히스토그램(셀 내부 순위 보존) × 성×연령 셀 평균비
    #  · 셀 안에서 _u_income 이 높을수록 임금이 높다 (블록 간 상관, §4.1)
    #  · 셀 평균은 4-2-3 의 성×연령 평균급여를 정확히 재현한다
    rk = np.full(n, np.nan)
    for s in ('남성', '여성'):
        for b in rate.columns:
            m = hold & (sex == s) & (band == b)
            c = int(m.sum())
            if c == 0:
                continue
            rk[m] = (pd.Series(r_amt[m]).rank(method='first').values - 0.5) / c
    #  · 셀 배율 f_c 로 셀 평균을 맞춘 뒤 **전국 순위로 재정렬**해 전국 구간 히스토그램을
    #    정확히 복원한다. f_c 는 셀 평균이 4-2-3 값에 수렴하도록 6회 반복 보정(IPF 성격).
    w = df['indwgt'].values if 'indwgt' in df.columns else np.ones(n)
    cellkey = np.array([f'{s}|{b}' for s, b in zip(sex, band)], dtype=object)
    tgt = {f'{s}|{b}': float(cell_mean.loc[s, b]) for s in ('남성', '여성') for b in rate.columns}
    fac = {k: max(v / nat_mean, 1e-3) for k, v in tgt.items()}
    idx = np.flatnonzero(hold)
    x = np.full(n, np.nan)
    if len(idx):
        base = nts.draw_by_rank(g, rk[idx], B['bt'], alpha=BETA_ALPHA)
        wh = w[idx]
        for _ in range(6):
            y = base * np.array([fac[k] for k in cellkey[idx]])
            o = np.argsort(y, kind='mergesort')
            cw = np.cumsum(wh[o]); rg = np.empty(len(idx))
            rg[o] = (cw - 0.5 * wh[o]) / cw[-1]
            xx = nts.draw_by_rank(g, rg, B['bt'], alpha=BETA_ALPHA)
            ach = pd.Series(xx * wh).groupby(cellkey[idx]).sum() / pd.Series(wh).groupby(cellkey[idx]).sum()
            for k, v in ach.items():
                if v > 0:
                    fac[k] = float(np.clip(fac[k] * tgt[k] / v, 1e-3, 50.0))
        xx = nts.match_band_means(xx, wh, B['bt'])
        x[idx] = np.maximum(xx, 10_000.0)

    # 비과세소득: 구간 보유율·평균 (4-2-4 비과세소득 소계), 금액 조건부 로그보간
    tf_p = nts.interp_rate(np.nan_to_num(x), B['bt'], B['tf_share'])
    tf_m = nts.interp_rate(np.nan_to_num(x), B['bt'], B['tf_mean'])
    has_tf = hold & (core.bernoulli(g, np.nan_to_num(tf_p)) == 1)
    taxn = np.where(has_tf, core.lognormal_mean(g, np.maximum(np.nan_to_num(tf_m), 1.0), 0.9, n), 0.0)
    taxn = np.where(hold, np.minimum(taxn, np.nan_to_num(x) * 0.5), np.nan)
    taxy = np.where(hold, np.nan_to_num(x) + np.nan_to_num(taxn), np.nan)

    # 결정세액: 구간별 '결정세액이 있는자' 비율 → 과세 여부, 구간 유효세율 × 과세대상근로소득
    sh = nts.interp_rate(np.nan_to_num(x), B['bt'], B['share_taxed'])
    r_tax = nts.score(g, r_amt, 0.45)                    # 같은 소득에서도 공제 이질성
    taxed = hold & (r_tax > (1.0 - np.nan_to_num(sh)))
    er = nts.interp_rate(np.nan_to_num(x), B['bt'], B['eff_rate'])
    noise = np.exp(g.normal(0.0, 0.25, n) - 0.25 ** 2 / 2)   # [가정 A2-B08-3]
    inctax = np.where(taxed, np.maximum(np.nan_to_num(x) * er * noise, 1_000.0), np.nan)

    out = pd.DataFrame(index=df.index)
    out['labinc_sum_taxy'] = np.round(taxy)
    out['labinc_sum_taxn'] = np.round(taxn)
    out['labinc_inc_taxamt'] = np.round(inctax)
    lt = pd.Series(np.round(inctax * LOCAL_TAX), index=df.index)
    out['labinc_residence_taxamt'] = lt.where(lt.fillna(0) > 0)
    # 농어촌특별세: 농특세법 시행령 제4조①1호가 조특법 제30조(중소기업 취업자 감면)를 비과세로
    # 열거 → 2022년 근로소득 연말정산 세액감면 인원 1,086,118명의 98.2%가 비과세 대상이고
    # 나머지(조세조약·소득세법상 감면)는 조특법 감면이 아니어서 농특세 과세표준이 성립하지 않는다.
    # 표본 9.5천명 기준 기대 발생 <3명 → 규모 미달, 전량 NaN.
    out['labinc_rural_taxamt'] = np.nan
    return out
