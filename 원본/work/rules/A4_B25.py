# -*- coding: utf-8 -*-
"""B25 긴급복지지원·자활근로  (A4 / order 6 / 26변수)

■ 소스 (등급순)
  S1 R05 보건복지통계연보 2023(2022 실적) <표 5-4-9> 긴급복지지원 실적 - 시도별
     → 2022 지원건수 491,824건 / 지원금액 263,611백만원, 시도별 건수·금액   [1차확인]
     params/raw/R05_5-4-9_긴급복지지원실적_시도별.csv
  S1 R05 <표 5-4-10> 자활사업 참여자 수 - 시도별
     → 2022 자활근로 소계 56,434명(시장진입 11,309·사회서비스 34,527·인턴 3,603·근로유지 6,995;
       시도 17개 합계 기준. 연도행 세부값은 원문 자체가 소계와 불일치하므로 시도합을 사용) [1차확인]
     ※ R05 통계표 해설(인쇄 p.636): "매년 말 기준 작성된 통계" → 연말 저량(stock)
     params/raw/R05_5-4-10_자활사업참여자수_시도별.csv
  S1 한국사회보장정보원 「2022년 차상위 및 한부모가족 수급자 현황 통계표」
     <표 2.1> 차상위자활 10,333명(2022.12) · 성별(남 4,111/여 6,222) · 연령대별   [1차확인]
     <표 3.2> 차상위자활 월별 저량 → 연간 합집합 하한 11,651명, E[dur] 하한 11.3개월 [논리적추론]
     params/raw/S1_2022차상위및한부모가족_수급자현황_통계표_long.csv
  S1 data.go.kr 15062448 시군구별 수급권자 현황 → 차상위자활 10,333명(교차검증 일치)  [1차확인]
  S4 2022년 긴급복지지원사업 안내 — 생계 가구원수별 월정액, 주거 지역×가구원수 월 상한,
     교육 학교급별 분기 정액, 의료 300만원 한도, 지원기간(생계 최대 6개월·주거 최대 12개월·
     의료 1회+연장 1회·교육 분기 1회+추가 최대 3회), 소득 중위 75% 이하           [1차확인]
     params/raw/S4_2022_사업별_법정단가_welfare.csv + 원문 PDF
  S4 2022년 자활사업안내(Ⅰ) — 유형별 1일 급여단가·실비                              [1차확인]

■ 확인 실패 (§1.3 시도기록)
  긴급복지 **유형별(생계/의료/주거/교육/기타) 실적** → [미확인]
    시도: R05 표5-4-9(시도별만 수록·유형 분해 없음, 원문확인) / 복지부 사업게시판·사전정보공표
          / data.go.kr / e-나라지표 보건복지부 지표목록(2026-09-02 curl 확인: 긴급복지 지표 부재)
          / 정책브리핑 정책위키 148867674(WebFetch, "없음") → 5회 시도 모두 실패
    → 유형 배분은 [가정 A4-B25-1] 로 명시하고, 총 건수·총 금액(둘 다 [1차확인])을 동시에
      재현하도록 의료 건당 평균액을 잔차로 역산한다([논리적추론]).

■ 조건 (§7)
  aid ⇒ 비수급(기초생활 미수급) ∧ 저소득(중위 75% 이하)   self ⇒ 근로연령 기초수급자
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

RAW = 'params/raw'
SIDO = {'서울': 1, '부산': 2, '대구': 3, '인천': 4, '광주': 5, '대전': 6, '울산': 7, '세종': 8,
        '경기': 9, '강원': 10, '충북': 11, '충남': 12, '전북': 13, '전남': 14, '경북': 15,
        '경남': 16, '제주': 17}

# ── [1차확인] 2022 단가 (2022년 긴급복지지원사업 안내 인쇄 p.45·p.51·p.55, 의료 p.48) ──────
AID_LIVE_UNIT = {1: 488800, 2: 826000, 3: 1066000, 4: 1304900, 5: 1541600, 6: 1773700}
AID_LIVE_STEP = 232000                       # 7인 이상 1인 증가 시
AID_HOUSE_CAP = {                            # (지역, 가구원수 구간) → 월 상한
    'big':   {2: 387200, 4: 643200, 6: 848600},
    'mid':   {2: 290300, 4: 422900, 6: 557400},
    'rural': {2: 183400, 4: 243200, 6: 320300}}
AID_HOUSE_STEP = {'big': 102300, 'mid': 67000, 'rural': 38300}
AID_EDU_UNIT = {'elem': 124100, 'mid': 174700, 'high': 207700}     # 분기 정액
AID_MEDI_CAP = 3000000                       # 1회 한도

# ── [1차확인] 2022 자활급여 (2022년 자활사업안내(Ⅰ) 인쇄 p.7·p.14) ─────────────────────
SELF_DAY = {4: 54660, 5: 54660, 2: 47350, 1: 26120}   # self_type2 코드 → 1일 급여단가
SELF_REAL = 4000                                       # 1일 실비 (전 유형 공통)
SELF_DAYS_MONTH = 22                                   # 월 근로일수 [가정 A4-B25-6]

# ── [1차확인] 긴급복지 선정기준 (지침 인쇄 p.50 비교표) ────────────────────────────────
AID_MED_PCT = 75                             # 기준중위소득 75% 이하

# ── [가정] ──────────────────────────────────────────────────────────────────────────
# A4-B25-1 : 긴급복지 지원건수의 유형별 배분. 유형별 실적 [미확인] → 아래 배분을 가정한다.
#   근거(구조적): ① 생계지원이 주지원의 중심이고 월 단위로 반복 지급되므로 건수 비중이 가장 크다.
#                ② 연료비는 동절기(10~3월) 월별 지급이라 주지원 가구당 최대 6건이 발생 →
#                   코드북 밖 '기타'(시설이용·연료비·해산비·장제비·전기요금) 건수 비중이 크다.
#                ③ 이 배분과 [1차확인] 단가로 계산한 금액이 총액 263,611백만원을 넘지 않아야 한다는
#                   제약을 만족하도록 고른 값이다(의료 건당 평균액이 잔차로 양수·한도 이내).
AID_CASE_SHARE = {'live': 0.50, 'medi': 0.11, 'house': 0.13, 'edu': 0.05, 'etc': 0.21}
AID_ETC_MEAN = 170000                        # 코드북 밖 '기타' 건당 평균액 [가정 A4-B25-2]
# A4-B25-3 : 지원기간·횟수 분포 (상한은 [1차확인], 분포 형태는 가정)
AID_LIVE_DUR = {1: .10, 2: .08, 3: .52, 4: .10, 5: .08, 6: .12}          # 최대 6개월
AID_HOUSE_DUR = {1: .10, 2: .08, 3: .55, 4: .06, 5: .04, 6: .07, 9: .06, 12: .04}   # 최대 12
AID_MEDI_FREQ = {1: .88, 2: .12}                                          # 1회 + 연장 1회
AID_EDU_FREQ = {1: .75, 2: .18, 3: .05, 4: .02}                           # 분기 1회 + 추가
AID_HOUSE_RATIO = (0.55, 1.00)               # 주거는 상한 내 실비 → 상한 대비 비율 [가정 A4-B25-4]
# A4-B25-5 : 기초생활 수급가구 비율(=비수급 판정 하한) — 2022.12 맞춤형급여 수급가구
NBLS_HH_SHARE = 1791727 / 21773507            # 0.0823  [1차확인 15062448 / R05 표5-4-2]
MED75_HH_SHARE = 0.30                         # 중위 75% 이하 가구 비율 [가정 A4-B25-7]
BETA_RANK = 3.0                               # 소득 하위일수록 수급확률↑ 기울기 [가정 A4-B25-8]
# A4-B25-9 : self_type1(참여유형) 분포 — 공개 실적표 [미확인]
SELF_TYPE1_P = {3: 0.55, 1: 0.33, 2: 0.08, 4: 0.04}   # 조건부/일반/급여특례/기타
SELF_DUR_PI12 = 0.78                          # E[dur]≈11.2 ← 하한 11.3 [논리적추론]
SELF_YN2_SHARE = 46101 / 51956                # 연말 저량 / 연간 합집합 하한

# ── 연령대(자활) : S1 표2.1 차상위자활 연령대별 [1차확인] ────────────────────────────
SELF_AGE_BANDS = [(0, 9), (10, 19), (20, 29), (30, 39), (40, 49), (50, 59), (60, 69), (70, 79)]
SELF_AGE_N = [3, 13, 490, 775, 1943, 3193, 3498, 418]      # 계 10,333
#   ↑ 마지막 밴드는 원문 '70세 이상'이나 80세 이상 자활근로 참여는 비현실적이라
#     70~79세로 한정한다 [논리적추론]
SELF_FEMALE_P = 6222 / 10333                                # 0.602


# ══════════════════════════════════════════════════════════════════════════════
# 공통 헬퍼
# ══════════════════════════════════════════════════════════════════════════════
def household_income_rank(df):
    """가구 소득인정액 백분위 대리지표 (0=최저 … 1=최고).

    B05(order5)가 `_recog_rank` 를 만들면 그것을 그대로 쓴다. 아직 없을 때의 폴백은
    개인 잠재변수 `_u_income` 의 가구평균에 인구학적 보정을 더한 값의 백분위다.
    [가정 A4-B25-10] — 보정계수는 노인·1인·한부모 가구의 소득이 낮다는 구조만 반영한다.
    B25·B29 가 동일 함수를 쓰므로 두 블록의 선정 대상이 일관된다.
    """
    if '_recog_rank' in df.columns:
        return pd.to_numeric(df['_recog_rank'], errors='coerce').values
    base = pd.Series(df['_u_income'].values, index=df['hid'].values).groupby(level=0).mean()
    hd = df[df['head'] == 1].set_index('hid')
    ha = hd['age'].reindex(base.index).fillna(50).values
    ht = hd['_hhtype'].reindex(base.index).astype(object).values
    hn = hd['hnum'].reindex(base.index).fillna(1).values
    adj = np.zeros(len(base))
    adj += np.where(ha >= 75, -0.20, np.where(ha >= 65, -0.12, 0.0))
    adj += np.where((ha >= 25) & (ha <= 54), 0.05, 0.0)
    adj += np.where(ht == 'single', -0.10, 0.0)
    adj += np.where(ht == 'oneparent_child', -0.10, 0.0)
    adj += np.where(ht == 'grandparent_child', -0.15, 0.0)
    adj += np.where((hn >= 4) & (ha >= 35) & (ha <= 55), 0.06, 0.0)
    r = pd.Series(base.values + adj, index=base.index).rank(pct=True)
    return df['hid'].map(r).values


def is_nbls_hh(df, rank):
    """기초생활 수급가구 여부. B24(_is_nbls)가 있으면 사용, 없으면 소득순위 하위 8.23%."""
    if '_is_nbls' in df.columns:
        return (pd.to_numeric(df['_is_nbls'], errors='coerce').fillna(0).values == 1)
    return rank <= NBLS_HH_SHARE


def area_class(df):
    """긴급복지 주거지원 지역구분 [1차확인 지침 각주32]:
    대도시=특별시·광역시의 구(도농복합 군 포함)·특례시 / 중소도시=도의 시+세종 / 농어촌=도의 군."""
    sido = df['sido'].values if 'sido' in df.columns else df['_sido'].values
    name = df['_sigungu_name'].astype(str).values
    out = np.where(np.isin(sido, [1, 2, 3, 4, 5, 6, 7]), 'big',
                   np.where(pd.Series(name).str.endswith('군').values, 'rural', 'mid'))
    return out


def _pick(g, elig_idx, weight, n):
    """가중 비복원 추출로 정확히 n개 선정."""
    n = int(min(max(n, 0), len(elig_idx)))
    if n == 0:
        return np.array([], dtype=int)
    w = np.asarray(weight, float)
    w = np.where(np.isfinite(w) & (w > 0), w, 1e-12)
    w = w / w.sum()
    return np.asarray(elig_idx)[g.choice(len(elig_idx), size=n, replace=False, p=w)]


def _cat(g, table, n):
    """범주 분포에서 **층화(계통) 역CDF 추출** — 표본이 3~40으로 작아 iid 추출은
    목표 평균(E[dur] 등)을 크게 벗어난다. [0,1] 을 n등분해 각 구간에서 균등난수를 뽑아
    역CDF로 사상하면 평균이 불편(unbiased)이면서 분산이 크게 줄어든다. [논리적추론]
    """
    ks = np.array(sorted(table), float); ps = np.array([table[k] for k in ks], float)
    ps = ps / ps.sum()
    if n <= 0:
        return np.array([], float)
    u = (np.arange(n) + g.random(n)) / n
    idx = np.searchsorted(np.cumsum(ps), u, side='right')
    out = ks[np.clip(idx, 0, len(ks) - 1)]
    return out[g.permutation(n)]


def _bern_exact(g, p, n1=None):
    """평균이 정확히 mean(p)(또는 지정한 n1개)가 되도록 하는 베르누이 — 확률비례 비복원."""
    p = np.clip(np.asarray(p, float), 0, 1)
    n1 = int(round(p.sum())) if n1 is None else int(round(n1))
    out = np.zeros(len(p), np.int8)
    if n1 <= 0:
        return out
    if n1 >= len(p):
        return out + 1
    w = np.where(p > 0, p, 1e-12); w = w / w.sum()
    out[g.choice(len(p), size=n1, replace=False, p=w)] = 1
    return out


def _ppf(u):
    """표준정규 분위수. scipy 가 없으면 층화를 포기하고 iid 정규로 되돌린다."""
    try:
        from scipy.special import ndtri
        return np.asarray(ndtri(u), float)
    except Exception:
        return np.random.default_rng(20220025).standard_normal(len(np.asarray(u)))


def _lognorm_capped(g, target_mean, sigma, n, cap):
    """평균 target_mean·상한 cap 인 절단 로그정규를 **층화(계통) 추출**로 생성.

    상한 절단 때문에 E[min(X,cap)] < E[X] 이므로 절단 후 평균이 target_mean 이 되도록
    이분법으로 모수를 역산한다. n 이 작아도 표본평균이 목표에 붙는다. [논리적추론]
    """
    if n <= 0:
        return np.array([], float)
    def emin(m):
        mu = np.log(max(m, 1.0)) - sigma ** 2 / 2
        a = (np.log(cap) - mu - sigma ** 2) / sigma
        b = (np.log(cap) - mu) / sigma
        from math import erf, sqrt
        Phi = lambda z: 0.5 * (1 + erf(z / sqrt(2)))
        return m * Phi(a) + cap * (1 - Phi(b))
    lo, hi = target_mean, target_mean * 20
    for _ in range(60):
        mid = (lo + hi) / 2
        if emin(mid) < target_mean: lo = mid
        else: hi = mid
    m = (lo + hi) / 2
    mu = np.log(max(m, 1.0)) - sigma ** 2 / 2
    u = (g.permutation(n) + g.random(n)) / n
    return np.minimum(np.exp(mu + sigma * _ppf(np.clip(u, 1e-6, 1 - 1e-6))), cap)


# ══════════════════════════════════════════════════════════════════════════════
# 소스 로드
# ══════════════════════════════════════════════════════════════════════════════
def _aid_sido():
    """R05 표5-4-9 시도별 긴급복지 지원건수·금액 (2022) [1차확인]."""
    d = pd.read_csv(os.path.join(RAW, 'R05_5-4-9_긴급복지지원실적_시도별.csv'))
    s = d[d['구분유형'] == '시도'].pivot_table(index='구분', columns='항목', values='값')
    s.index = [SIDO[i] for i in s.index]
    y = d[(d['구분유형'] == '연도') & (d['구분'].astype(str) == '2022')]
    tot_case = float(y[y['항목'] == '지원건수']['값'].iloc[0])
    tot_amt = float(y[y['항목'] == '지원금액']['값'].iloc[0]) * 1e6      # 백만원 → 원
    return s.sort_index(), tot_case, tot_amt


def _self_sido():
    """R05 표5-4-10 시도별 자활근로 참여자·유형별 (2022, 시도합 기준) [1차확인]."""
    d = pd.read_csv(os.path.join(RAW, 'R05_5-4-10_자활사업참여자수_시도별.csv'))
    s = d[d['구분유형'] == '시도'].pivot_table(index='구분', columns='항목', values='값')
    s.index = [SIDO[i] for i in s.index]
    s = s.sort_index()
    tot = float(s['자활근로_소계'].sum())
    # self_type2 코드: 1 근로유지형 / 2 사회서비스형 / 4 시장진입형 / 5 인턴·도우미형
    typ = {1: float(s['자활근로_근로유지형'].sum()), 2: float(s['자활근로_사회서비스일자리형'].sum()),
           4: float(s['자활근로_시장진입형'].sum()), 5: float(s['자활근로_인턴형'].sum())}
    return s, tot, typ


def _chasangwi_self():
    """S1 표2.1 차상위자활 수급자 10,333명(2022.12) [1차확인]."""
    d = pd.read_csv(os.path.join(RAW, 'S1_2022차상위및한부모가족_수급자현황_통계표_long.csv'))
    t = d[(d['표번호_표제목'] == '표2.1. 차상위 및 한부모가족 수급자 자격별 현황(중복허용)') &
          (d['구분'] == '합계') & (d['항목'] == '차상위자활')]
    return float(t['값'].iloc[0])


def _sido_hh_pop():
    """시도별 모집단 세대수·인구 (주민등록 2022.11) — 시도 조건부 지수의 분모."""
    h = pd.read_csv(os.path.join(RAW, 'POPUL_MOIS02_2022_11_sigungu_hhsize.csv'))
    h = h[(h.level == 'sigungu') & (h.hh_size == 'total')]
    hh = h.groupby(h['sido'].astype(int))['households'].sum()
    p = pd.read_csv(os.path.join(RAW, 'POPUL_MOIS01_2022_11_sigungu_age1_sex.csv'))
    p = p[(p.level == 'sigungu') & (p.sex.isin(['male', 'female']))]
    pop = p.groupby(p['sido'].astype(int))['pop'].sum()
    return hh, pop


# ══════════════════════════════════════════════════════════════════════════════
def generate(df, params, ctx):
    g = core.rng('B25')
    n = len(df)
    out = pd.DataFrame(index=df.index)
    for c in ('aid_live_yn1', 'aid_live_yn2', 'aid_live_dur', 'aid_live_amt',
              'aid_house_yn1', 'aid_house_yn2', 'aid_house_dur', 'aid_house_amt',
              'aid_edu_yn', 'aid_edu_freq', 'aid_edu_amt',
              'aid_medi_yn', 'aid_medi_freq', 'aid_medi_amt',
              'self_yn1', 'self_yn2', 'self_type1', 'self_type2', 'self_dur', 'self_amt',
              'self_lower_yn1', 'self_lower_yn2', 'self_lower_type1', 'self_lower_type2',
              'self_lower_dur', 'self_lower_amt'):
        out[c] = np.nan

    N_hh = float(df['_N_pop_hh'].iloc[0])
    N_pop = float(df['_N_pop_person'].iloc[0])
    f_hh = df['hid'].nunique() / N_hh          # 가구 표본률
    f_p = n / N_pop                            # 개인 표본률
    sido = (df['sido'] if 'sido' in df.columns else df['_sido']).astype(int).values
    rank = household_income_rank(df)
    nbls = is_nbls_hh(df, rank)
    head = (df['head'].values == 1)
    hh_sido, hh_pop = _sido_hh_pop()

    # ─────────────────────────────────────────────────────────── 긴급복지지원
    sido_aid, tot_case, tot_amt = _aid_sido()
    # 시도 조건부 지수 = (시도 지원건수 점유율) / (시도 세대수 점유율)  [1차확인 기반]
    cs = sido_aid['지원건수'] / sido_aid['지원건수'].sum()
    hs = hh_sido.reindex(cs.index) / hh_sido.sum()
    sidx = (cs / hs).reindex(range(1, 18)).fillna(1.0).values

    n_case = {k: tot_case * v for k, v in AID_CASE_SHARE.items()}
    e_dur = {'live': sum(k * v for k, v in AID_LIVE_DUR.items()),
             'house': sum(k * v for k, v in AID_HOUSE_DUR.items()),
             'medi': sum(k * v for k, v in AID_MEDI_FREQ.items()),
             'edu': sum(k * v for k, v in AID_EDU_FREQ.items())}
    n_hh_target = {k: n_case[k] / e_dur[k] for k in e_dur}      # 전국 지원 가구수

    # 대상: 가구주 ∧ 비수급 ∧ 중위 75% 이하 (재산기준은 _h_prop 부재로 미적용 — note 참조)
    elig_aid = head & (~nbls) & (rank <= MED75_HH_SHARE)
    w_aid = np.exp(-BETA_RANK * rank / max(MED75_HH_SHARE, 1e-9)) * \
        (0.5 + df['_u_welfare'].values) * sidx[sido - 1]
    ei = np.flatnonzero(elig_aid)

    picks, unit_mean = {}, {}
    for key in ('live', 'medi', 'house', 'edu'):
        if key == 'edu':      # 초·중·고 학생이 있는 가구만
            stu = pd.Series(((df['age'].values >= 7) & (df['age'].values <= 18)).astype(int),
                            index=df['hid'].values).groupby(level=0).max()
            ok = df['hid'].map(stu).values == 1
            e = np.flatnonzero(elig_aid & ok)
        else:
            e = ei
        picks[key] = _pick(g, e, w_aid[e], round(n_hh_target[key] * f_hh))

    # 생계지원
    p = picks['live']
    if len(p):
        dur = _cat(g, AID_LIVE_DUR, len(p)).astype(int)
        hn = df['hnum'].values[p].astype(int)
        unit = np.array([AID_LIVE_UNIT.get(min(k, 6), AID_LIVE_UNIT[6]) +
                         max(0, k - 6) * AID_LIVE_STEP for k in hn], float)
        unit_mean['live'] = float(unit.mean())
        out.loc[df.index[p], 'aid_live_yn1'] = 1
        out.loc[df.index[p], 'aid_live_dur'] = dur
        out.loc[df.index[p], 'aid_live_amt'] = np.rint(unit * dur)
        # 고정시점(12월) 수급: 연중 최대 6개월 지원 → 12월 포함 확률 ≈ dur/12
        out.loc[df.index[p], 'aid_live_yn2'] = _bern_exact(g, np.clip(dur / 12.0, 0, 1))

    # 주거지원
    p = picks['house']
    if len(p):
        dur = _cat(g, AID_HOUSE_DUR, len(p)).astype(int)
        ac = area_class(df)[p]
        hn = df['hnum'].values[p].astype(int)
        cap = np.empty(len(p))
        for i, (a, k) in enumerate(zip(ac, hn)):
            tab = AID_HOUSE_CAP[a]
            base = tab[2] if k <= 2 else (tab[4] if k <= 4 else tab[6])
            cap[i] = base + max(0, k - 6) * AID_HOUSE_STEP[a]
        ratio = g.uniform(*AID_HOUSE_RATIO, len(p))
        unit_mean['house'] = float((cap * ratio).mean())
        out.loc[df.index[p], 'aid_house_yn1'] = 1
        out.loc[df.index[p], 'aid_house_dur'] = dur
        out.loc[df.index[p], 'aid_house_amt'] = np.rint(cap * ratio * dur)
        out.loc[df.index[p], 'aid_house_yn2'] = _bern_exact(g, np.clip(dur / 12.0, 0, 1))

    # 교육지원 — 가구 내 학생 학교급으로 단가 결정(가장 상위 학교급 기준)
    p = picks['edu']
    if len(p):
        freq = _cat(g, AID_EDU_FREQ, len(p)).astype(int)
        amax = pd.Series(np.where((df['age'].values >= 7) & (df['age'].values <= 18),
                                  df['age'].values, np.nan), index=df['hid'].values
                         ).groupby(level=0).max()
        sa = df['hid'].map(amax).values[p]
        unit = np.where(sa >= 16, AID_EDU_UNIT['high'],
                        np.where(sa >= 13, AID_EDU_UNIT['mid'], AID_EDU_UNIT['elem'])).astype(float)
        unit_mean['edu'] = float(unit.mean())
        out.loc[df.index[p], 'aid_edu_yn'] = 1
        out.loc[df.index[p], 'aid_edu_freq'] = freq
        out.loc[df.index[p], 'aid_edu_amt'] = np.rint(unit * freq)

    # 의료지원 — 건당 평균액을 총액 잔차로 역산 [논리적추론]
    p = picks['medi']
    if len(p):
        freq = _cat(g, AID_MEDI_FREQ, len(p)).astype(int)
        # 의료 건당 평균액 = 총금액([1차확인]) − 생계·주거·교육 소요액 − 기타(코드북 밖) 의 잔차.
        # 소요액은 표본 실현값이 아니라 **전국 건수 × 표본에서 얻은 건당 단가 평균**으로 계산해
        # 표본 크기(n=14 등)에 따른 흔들림을 없앤다. [논리적추론]
        used = sum(n_case[k] * unit_mean.get(k, 0.0) for k in ('live', 'house', 'edu'))
        etc = n_case['etc'] * AID_ETC_MEAN
        resid = tot_amt - used - etc
        # 가구(=지원 대상자) 1인당 연간 의료지원액 평균. 300만원 한도는 연장 포함 총액 기준
        # [1차확인 지침 인쇄 p.49] 이므로 절단 후 평균이 이 값이 되도록 모수를 역산한다.
        mean_medi = float(np.clip(resid / max(n_hh_target['medi'], 1.0), 100000, AID_MEDI_CAP))
        amt = _lognorm_capped(g, mean_medi, 0.85, len(p), AID_MEDI_CAP)
        out.loc[df.index[p], 'aid_medi_yn'] = 1
        out.loc[df.index[p], 'aid_medi_freq'] = freq
        out.loc[df.index[p], 'aid_medi_amt'] = np.rint(np.maximum(amt, 10000))

    # ───────────────────────────────────────────────────────────────── 자활근로
    sido_self, self_tot, self_typ = _self_sido()
    n_lower = _chasangwi_self()                     # 차상위자활 10,333 (연말 저량)
    n_basic_yn2 = self_tot - n_lower                # 기초 자활근로 참여자(연말) [논리적추론]
    n_basic_yn1 = n_basic_yn2 / SELF_YN2_SHARE      # 연간 합집합(하한 비율 1.1276 적용)

    cs = sido_self['자활근로_소계'] / sido_self['자활근로_소계'].sum()
    ps = hh_pop.reindex(cs.index) / hh_pop.sum()
    sidx_self = (cs / ps).reindex(range(1, 18)).fillna(1.0).values

    # 연령 프로파일(차상위자활 실측)을 표본 인구 연령분포로 나눈 상대가중
    age = df['age'].values
    aw = np.ones(n)
    tot_band = float(sum(SELF_AGE_N))
    for (lo, hi), cnt in zip(SELF_AGE_BANDS, SELF_AGE_N):
        m = (age >= lo) & (age <= hi)
        share_pop = m.mean()
        aw[m] = (cnt / tot_band) / share_pop if share_pop > 0 else 0.0
    sexw = np.where(df['gender'].values == 2, SELF_FEMALE_P, 1 - SELF_FEMALE_P)

    # 대상: 기초생활 수급가구 ∧ 근로연령(연령 프로파일이 15세 미만 사실상 배제)
    elig_self = nbls & (age >= 15)
    w_self = aw * sexw * (0.5 + df['_u_emp'].values) * sidx_self[sido - 1]
    es = np.flatnonzero(elig_self)
    p = _pick(g, es, w_self[es], round(n_basic_yn1 * f_p))
    if len(p):
        dtab = {12: SELF_DUR_PI12}
        for k in range(6, 12): dtab[k] = (1 - SELF_DUR_PI12) / 6
        dur = _cat(g, dtab, len(p)).astype(int)
        t2 = _cat(g, {k: v / sum(self_typ.values()) for k, v in self_typ.items()}, len(p)).astype(int)
        t1 = _cat(g, SELF_TYPE1_P, len(p)).astype(int)
        day = np.array([SELF_DAY[int(k)] for k in t2], float) + SELF_REAL
        days = g.integers(SELF_DAYS_MONTH - 2, SELF_DAYS_MONTH + 2, len(p))
        out.loc[df.index[p], 'self_yn1'] = 1
        out.loc[df.index[p], 'self_dur'] = dur
        out.loc[df.index[p], 'self_amt'] = np.rint(day * days * dur)
        # 2022.10.31 기준 참여확률 ∝ 참여개월수, 참여자 수는 연말저량/연간합집합(0.887)에 고정
        yn2 = _bern_exact(g, dur / 12.0, n1=len(p) * SELF_YN2_SHARE)
        out.loc[df.index[p], 'self_yn2'] = yn2
        # type1/type2 는 '2022.10.31 기준 참여자'만 추출대상 → yn2=1 인 행에만 부여
        idx = df.index[p]
        out.loc[idx, 'self_type1'] = np.where(yn2 == 1, t1, np.nan)
        out.loc[idx, 'self_type2'] = np.where(yn2 == 1, t2, np.nan)

    # self_lower_* : 규모 미달 → 전량 NaN (아래 진단값을 params note 에 기록)
    ctx['_B25_diag'] = {
        'aid_hh_target': {k: round(v) for k, v in n_hh_target.items()},
        'aid_expected_sample': {k: round(n_hh_target[k] * f_hh, 2) for k in n_hh_target},
        'self_yn1_pop': round(n_basic_yn1), 'self_expected_sample': round(n_basic_yn1 * f_p, 2),
        'self_lower_yn1_pop': round(n_lower / SELF_YN2_SHARE),
        'self_lower_expected_sample': round(n_lower / SELF_YN2_SHARE * f_p, 2)}

    # ── §7 R24 강제: yn2⇒yn1, dur∈[1,12], amt>0 ⇔ yn1=1 ────────────────────────
    for pre, ynk in (('aid_live', 'yn1'), ('aid_house', 'yn1'), ('self', 'yn1'),
                     ('self_lower', 'yn1')):
        y1 = out[f'{pre}_{ynk}']
        for suf in ('dur', 'amt', 'yn2'):
            c = f'{pre}_{suf}'
            if c in out:
                out.loc[y1 != 1, c] = np.nan
        if f'{pre}_dur' in out:
            out[f'{pre}_dur'] = out[f'{pre}_dur'].clip(1, 12)
        if f'{pre}_yn2' in out:
            out.loc[(y1 == 1) & out[f'{pre}_yn2'].isna(), f'{pre}_yn2'] = 0
    for pre in ('aid_edu', 'aid_medi'):
        y = out[f'{pre}_yn']
        for suf in ('freq', 'amt'):
            out.loc[y != 1, f'{pre}_{suf}'] = np.nan
    return out
