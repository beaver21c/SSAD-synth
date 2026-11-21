# -*- coding: utf-8 -*-
"""B29 한부모가족지원·초중고 교육비지원  (A4 / order 6 / 26변수)

■ 소스 (등급순)
  S1 한국사회보장정보원 「2022년 차상위 및 한부모가족 수급자 현황 통계표」  [1차확인]
     <표 3.14> 한부모가족 **수급가구** 가족유형별(2022.12): 모자 149,888 / 부자 37,209 /
       조손 1,307 / 청소년모자 1,845 / 청소년부자 172 = 190,421가구
     <표 3.13> 수급자 474,194명 / <표 3.12> 월별 수급가구수(185,426→190,421)
       → 연간 합집합 하한 191,634가구, E[dur] 하한 11.75개월  [논리적추론]
     ※ KOSIS 452/DT_452001_B001·B002 의 **원기관 원본**(S1) — S2 대체가 아니라 상위등급
     params/raw/S1_표3-13_…csv, S1_표3-14_…csv, S1_표3-12_…csv
  S4 2022년 한부모가족 복지서비스 종합안내서(여성가족부) 인쇄 p.10~11   [1차확인]
     복지급여 기준중위소득 58% 이하(증명서 60%), 아동양육비 52% 이하 월 20만원 /
     52~58% 월 10만원, 추가아동양육비(조손·만35세 이상 미혼 만5세 이하 5만원;
     만25~34세 청년한부모 만5세 이하 10만원·만6~18세 미만 5만원),
     아동교육지원비(학용품비) 중·고생 연 8.3만원,
     청소년한부모(모·부 만24세 이하) 아동양육비 60% 이하 월 35만원, 자립촉진수당 월 10만원
     params/raw/S4_2022_사업별_법정단가_welfare.csv
  S4 2022 초·중·고 학생 교육비 지원 안내 지침(교육부) 인쇄 p.23~26   [1차확인]
     시도교육청별 지원기준(중위소득 %) 표, 방과후학교 자유수강권 연 60만원 내외,
     교육정보화 인터넷통신비 월 17,600원·유해차단 월 1,650원·가구당 PC 1대,
     고교학비·급식비는 **정액 단가 없이 실비**
  S1 R05 보건복지통계연보 표5-4-2 → 교육급여 수급자 303,383명(2022)   [1차확인]

■ 확인 실패 (§1.3 시도기록)
  초·중·고 교육비 지원 **항목별 실적(지원 학생 수)** → [미확인]
    시도: 교육부 지침·교육급여 운영방안(단가만 수록, 원문확인) / R05 목차 grep / WebSearch
          2회(2026-09-02, 방과후 자유수강권·교육정보화 실적 검색 → 미검출) → 실패
    → 방과후·교육정보화의 지원율은 [가정]. 고교학비·급식비는 아래 '코드북 수정 검토' 참조.
  한부모 급여 **항목별(아동양육비/추가/학용품비) 수급자 수** → [미확인]
    → 총 수급가구(190,421)는 [1차확인], 항목 분해는 지침의 지급요건을 규칙으로 적용.

■ 코드북 수정 검토 결론 (§1.3)
  pubedu_hidhedu(고교학비) : 2022년 고교무상교육 전면 시행. 지침 인쇄 p.24 [1차확인]
    "초·중·특수학교 학생은 의무교육, 고등학교 학생은 고교무상교육으로 학비 면제",
    지원대상은 '무상교육 제외 고등학교 재학생'으로 한정. 5개 시도(광주·세종·충북·경남·제주)는
    전 학년 무상. → 기대 수급자 3명 미만 → **전량 NaN(규모 미달)**, 코드북에서 삭제하지 않음.
  pubedu_meals(급식비) : 지침 인쇄 p.25 [1차확인] "무상급식 실시 학년 및 지역은 전체 학생을
    대상으로 급식비를 지원하므로 본 지침의 적용 대상이 아님". 17개 시도 중 11개가 (무상).
    → **전량 NaN(규모 미달)**, 코드북 유지.
  single_youth_*(청소년한부모) : 청소년모자 1,845 + 청소년부자 172 = 2,017가구 [1차확인]
    → 표본 기대 0.4가구. 또한 B01 표본에 만24세 이하 한부모 가구주가 0명.
    → **전량 NaN(규모 미달)**, 코드북 유지.

■ 조건 (§7 R18)  single ⇒ 한부모 ∧ 자녀<18 ∧ 중위 60% 이하 / pubedu ⇒ 7~18세 학생 ∧ 저소득
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

RAW = 'params/raw'

# ── [1차확인] 2022 한부모가족지원 단가 (여성가족부 종합안내서 인쇄 p.10~11) ─────────────
SG_REAR_HI = 200000          # 중위 52% 이하, 만18세 미만 아동 1인당 월
SG_REAR_LO = 100000          # 중위 52% 초과~58% 이하
SG_EXTRA_U6_UNWED35 = 50000  # 조손·만35세 이상 미혼 한부모의 만5세 이하 아동 1인당 월
SG_EXTRA_U6_YOUNG = 100000   # 만25~34세 청년 한부모의 만5세 이하 아동 1인당 월
SG_EXTRA_6_18_YOUNG = 50000  # 만25~34세 청년 한부모의 만6~18세 미만 아동 1인당 월
SG_EDU_YEAR = 83000          # 아동교육지원비(학용품비) 중·고생 1인당 연

# ── [1차확인] 2022 초·중·고 교육비지원 단가 (교육부 지침 인쇄 p.4·26) ────────────────
PE_AFTSCH_YEAR = 600000      # 방과후학교 자유수강권 연 60만원 내외
PE_NET_MONTH = 17600         # 교육정보화 인터넷 통신비 월
PE_FILTER_MONTH = 1650       # 유해차단 서비스 월

# ── [1차확인] 시도교육청별 방과후학교 자유수강권 지원기준(중위소득 %) 지침 인쇄 p.26 ──
AFTSCH_PCT = {1: 70, 2: 80, 3: 80, 4: 70, 5: 80, 6: 80, 7: 80, 8: 80, 9: 70,
              10: 80, 11: 80, 12: 80, 13: 80, 14: 70, 15: 80, 16: 80, 17: 70}

# ── [1차확인] 2022.12 한부모가족 수급가구 (사회보장정보원 표3.14) ─────────────────────
SG_HH = {'모자': 149888, '부자': 37209, '조손': 1307, '청소년모자': 1845, '청소년부자': 172}
SG_UNION_RATIO = 191634 / 190421      # 연간 합집합 하한 / 12월 저량 = 1.00637 [논리적추론]
SG_DUR_PI12 = 0.88                    # E[dur]≈11.6 ← 하한 11.75 [논리적추론→가정]

# ── [가정] ──────────────────────────────────────────────────────────────────────────
# A4-B29-1 : 기준중위소득 % → 가구 소득인정액 백분위 대응표.
#   앵커 — 중위 30%대 급여인 기초생활 맞춤형급여 수급가구 비율 8.23%([1차확인] 15062448),
#   중위 100% = 소득인정액 분포의 중앙(0.50, 정의상 근사). 나머지는 단조 보간.
MED_ANCHOR_X = [0, 30, 50, 58, 60, 65, 70, 75, 80, 100, 135]
MED_ANCHOR_Y = [0.0, 0.082, 0.155, 0.185, 0.195, 0.210, 0.230, 0.270, 0.290, 0.500, 0.660]
P_UNWED35 = 0.25              # 만35세 이상 한부모 중 '미혼' 비율 [가정 A4-B29-2]
SG_REAR_LO_SHARE = 0.15       # 아동양육비 수급가구 중 중위 52~58% 구간 비율 [가정 A4-B29-3]
PE_AFTSCH_TAKEUP = 0.35       # 대상 학생 중 실제 방과후 수강·지원 비율 [가정 A4-B29-4]
PE_PCLOT_TAKEUP = 0.40        # 자격 학생 중 교육정보화 지원 비율 [가정 A4-B29-5]
EDU_BENEFIT_STUDENTS = 303383  # 2022.12 기초 교육급여 수급자(초·중·고 학생) [1차확인 R05 표5-4-2/15062448]
                               # → 교육정보화 '법정자격' 학생 풀의 앵커 (한부모 수급가구 학생과 합집합)
BETA_RANK = 3.0               # 소득 하위일수록 수급확률↑ [가정 A4-B29-7]


def med_rank(pct):
    """기준중위소득 % → 가구 소득인정액 백분위 임계값 [가정 A4-B29-1]."""
    return float(np.interp(pct, MED_ANCHOR_X, MED_ANCHOR_Y))


# ══════════════════════════════════════════════════════════════════════════════
# 공통 헬퍼 — B25 와 동일 정의(두 블록의 선정 대상이 일관되도록 같은 코드를 쓴다)
# ══════════════════════════════════════════════════════════════════════════════
def household_income_rank(df):
    """가구 소득인정액 백분위 대리지표 (0=최저 … 1=최고). B05 `_recog_rank` 우선."""
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


def _pick(g, elig_idx, weight, n):
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


# ══════════════════════════════════════════════════════════════════════════════
def generate(df, params, ctx):
    g = core.rng('B29')
    n = len(df)
    out = pd.DataFrame(index=df.index)
    COLS = ['single_rear_yn1', 'single_rear_yn2', 'single_rear_dur', 'single_rear_amt',
            'single_extra_yn1', 'single_extra_yn2', 'single_extra_dur', 'single_extra_amt',
            'single_edu_yn', 'single_edu_amt',
            'single_youth_rear_yn1', 'single_youth_rear_yn2', 'single_youth_rear_dur',
            'single_youth_rear_amt', 'single_youth_self_yn1', 'single_youth_self_yn2',
            'single_youth_self_dur', 'single_youth_self_amt',
            'pubedu_hidhedu_yn', 'pubedu_hidhedu_amt', 'pubedu_meals_yn', 'pubedu_meals_amt',
            'pubedu_aftsch_yn', 'pubedu_aftsch_amt', 'pubedu_pclot_yn', 'pubedu_pclot_amt']
    for c in COLS:
        out[c] = np.nan

    N_hh = float(df['_N_pop_hh'].iloc[0])
    f_hh = df['hid'].nunique() / N_hh
    age = df['age'].values
    head = (df['head'].values == 1)
    sido = (df['sido'] if 'sido' in df.columns else df['_sido']).astype(int).values
    rank = household_income_rank(df)

    # 가구별 아동 구성
    hid = df['hid'].values
    c_u6 = pd.Series((age <= 5).astype(int), index=hid).groupby(level=0).sum()
    c_6_17 = pd.Series(((age >= 6) & (age <= 17)).astype(int), index=hid).groupby(level=0).sum()
    c_12_17 = pd.Series(((age >= 12) & (age <= 17)).astype(int), index=hid).groupby(level=0).sum()
    n_u6 = df['hid'].map(c_u6).values
    n_6_17 = df['hid'].map(c_6_17).values
    n_12_17 = df['hid'].map(c_12_17).values

    # ───────────────────────────────────────────────── 한부모가족지원 (single_*)
    # §7 R18: 한부모(_is_single_parent) ∧ 만18세 미만 자녀 ∧ 중위 60% 이하
    sp = head & (df['_is_single_parent'].values == 1) & (df['_n_child_u18'].values >= 1)
    thr60 = med_rank(60)
    n_target = round(sum(SG_HH[k] for k in ('모자', '부자')) * SG_UNION_RATIO * f_hh)
    cand = np.flatnonzero(sp & (rank <= thr60))
    if len(cand) < n_target * 1.3:            # 후보 부족 시 소득순위 하위부터 확장(note 기록)
        allsp = np.flatnonzero(sp)
        order = allsp[np.argsort(rank[allsp])]
        cand = order[:max(int(np.ceil(n_target * 1.3)), len(cand))]
    w = np.exp(-BETA_RANK * rank[cand] / max(thr60, 1e-9)) * (0.5 + df['_u_welfare'].values[cand])
    sel = _pick(g, cand, w, n_target)

    if len(sel):
        dtab = {12: SG_DUR_PI12}
        for k in range(6, 12): dtab[k] = (1 - SG_DUR_PI12) / 6
        dur = _cat(g, dtab, len(sel)).astype(int)
        # 급여구간: 소득순위 상위 SG_REAR_LO_SHARE 는 52~58% 구간(월 10만원)
        ordr = np.argsort(-rank[sel])
        lo = np.zeros(len(sel), bool)
        lo[ordr[:int(round(len(sel) * SG_REAR_LO_SHARE))]] = True
        rate = np.where(lo, SG_REAR_LO, SG_REAR_HI)
        nch = df['_n_child_u18'].values[sel]
        idx = df.index[sel]
        out.loc[idx, 'single_rear_yn1'] = 1
        out.loc[idx, 'single_rear_dur'] = dur
        out.loc[idx, 'single_rear_amt'] = np.rint(rate * nch * dur)
        e_dur = SG_DUR_PI12 * 12 + (1 - SG_DUR_PI12) * 8.5
        # 12월 기준 수급: 연간 합집합 대비 12월 저량 비율(1/1.00637=0.9937)을 정확히 맞춘다
        out.loc[idx, 'single_rear_yn2'] = _bern_exact(
            g, dur / 12.0, n1=len(sel) / SG_UNION_RATIO)

        # ── 추가아동양육비 (지급요건은 [1차확인], '미혼' 여부는 자료 없음 → [가정]) ──
        ha = age[sel]
        unwed = _bern_exact(g, np.full(len(sel), P_UNWED35)) == 1
        young = (ha >= 25) & (ha <= 34)
        m_young = young & ((n_u6[sel] + n_6_17[sel]) > 0)
        m_un35 = (ha >= 35) & unwed & (n_u6[sel] > 0)
        extra_rate = np.where(m_young,
                              SG_EXTRA_U6_YOUNG * n_u6[sel] + SG_EXTRA_6_18_YOUNG * n_6_17[sel],
                              np.where(m_un35, SG_EXTRA_U6_UNWED35 * n_u6[sel], 0.0))
        me = extra_rate > 0
        if me.sum():
            ie = idx[me]
            out.loc[ie, 'single_extra_yn1'] = 1
            out.loc[ie, 'single_extra_dur'] = dur[me]
            out.loc[ie, 'single_extra_amt'] = np.rint(extra_rate[me] * dur[me])
            out.loc[ie, 'single_extra_yn2'] = out.loc[ie, 'single_rear_yn2'].values

        # ── 아동교육지원비(학용품비): 중·고생(만12~17세) 1인당 연 8.3만원 ──
        mE = n_12_17[sel] > 0
        if mE.sum():
            ie = idx[mE]
            out.loc[ie, 'single_edu_yn'] = 1
            out.loc[ie, 'single_edu_amt'] = np.rint(SG_EDU_YEAR * n_12_17[sel][mE])

    # single_youth_* : 규모 미달 → 전량 NaN (상단 '코드북 수정 검토 결론' 참조)

    # ───────────────────────────────────────────── 초·중·고 교육비지원 (pubedu_*)
    stu = (age >= 7) & (age <= 18)
    # 교육비 선정기준(기준중위소득 %)은 **가구규모별 기준중위소득 대비 소득인정액** 비율이므로
    # 전 가구 순위(노인 1인가구가 하위를 채움)가 아니라 **학생가구 내 상대순위**에 대응시킨다.
    # 전 가구 순위를 쓰면 중위 80% 기준의 학생 대상률이 8%로 떨어져 제도 기준과 어긋난다. [논리적추론]
    shh = pd.Series(stu.astype(int), index=hid).groupby(level=0).max()
    shh_ids = shh[shh == 1].index
    rstu_map = pd.Series(rank, index=hid).groupby(level=0).first().reindex(shh_ids).rank(pct=True)
    rank_stu = df['hid'].map(rstu_map).values

    thr_aft = np.array([med_rank(AFTSCH_PCT[s]) for s in range(1, 18)])[sido - 1]
    elig_aft = stu & (rank_stu <= thr_aft)
    ea = np.flatnonzero(elig_aft)
    if len(ea):
        w = (0.5 + df['_u_welfare'].values[ea]) * np.exp(-1.0 * rank_stu[ea] / thr_aft[ea])
        pa = _pick(g, ea, w, round(len(ea) * PE_AFTSCH_TAKEUP))
        if len(pa):
            amt = PE_AFTSCH_YEAR * g.uniform(0.5, 1.0, len(pa))
            out.loc[df.index[pa], 'pubedu_aftsch_yn'] = 1
            out.loc[df.index[pa], 'pubedu_aftsch_amt'] = np.rint(amt)

    # 교육정보화: 법정자격(교육급여·한부모·법정차상위) 학생 → 가구당 1명(인터넷 회선 1개)
    #   자격 풀 = 소득순위 최하위 n_edu 명(=교육급여 수급학생 303,383 [1차확인] 환산)
    #             ∪ 한부모 아동양육비 수급가구의 학생
    sg_hh = pd.Series(np.where(out['single_rear_yn1'].values == 1, 1, 0), index=hid
                      ).groupby(level=0).max()
    in_sg = df['hid'].map(sg_hh).values == 1
    n_edu = int(round(EDU_BENEFIT_STUDENTS * len(df) / float(df['_N_pop_person'].iloc[0])))
    si = np.flatnonzero(stu)
    low = set(si[np.argsort(rank_stu[si])][:n_edu].tolist())
    base_pc = np.zeros(len(df), bool); base_pc[list(low)] = True
    elig_pc = stu & (base_pc | in_sg)
    ep = pd.Series(np.flatnonzero(elig_pc))
    if len(ep):
        # 가구당 대표 학생 1명 (연장자)
        tmp = pd.DataFrame({'i': ep.values, 'hid': hid[ep.values], 'age': age[ep.values]})
        rep = tmp.sort_values(['hid', 'age'], ascending=[True, False]).groupby('hid')['i'].first()
        e2 = rep.values
        w = (0.5 + df['_u_welfare'].values[e2])
        pp = _pick(g, e2, w, round(len(e2) * PE_PCLOT_TAKEUP))
        if len(pp):
            mon = g.integers(9, 13, len(pp))
            out.loc[df.index[pp], 'pubedu_pclot_yn'] = 1
            out.loc[df.index[pp], 'pubedu_pclot_amt'] = np.rint(
                (PE_NET_MONTH + PE_FILTER_MONTH) * mon)

    # pubedu_hidhedu_* / pubedu_meals_* : 규모 미달 → 전량 NaN

    # ── §7 R24 강제 ────────────────────────────────────────────────────────────
    for pre in ('single_rear', 'single_extra', 'single_youth_rear', 'single_youth_self'):
        y1 = out[f'{pre}_yn1']
        for suf in ('yn2', 'dur', 'amt'):
            out.loc[y1 != 1, f'{pre}_{suf}'] = np.nan
        out[f'{pre}_dur'] = out[f'{pre}_dur'].clip(1, 12)
        out.loc[(y1 == 1) & out[f'{pre}_yn2'].isna(), f'{pre}_yn2'] = 0
    for pre in ('single_edu', 'pubedu_hidhedu', 'pubedu_meals', 'pubedu_aftsch', 'pubedu_pclot'):
        out.loc[out[f'{pre}_yn'] != 1, f'{pre}_amt'] = np.nan

    ctx['_B29_diag'] = {
        'single_rear_pop': round(sum(SG_HH[k] for k in ('모자', '부자')) * SG_UNION_RATIO),
        'single_rear_target_sample': n_target,
        'single_rear_n': int((out['single_rear_yn1'] == 1).sum()),
        'single_extra_n': int((out['single_extra_yn1'] == 1).sum()),
        'single_edu_n': int((out['single_edu_yn'] == 1).sum()),
        'single_youth_pop': SG_HH['청소년모자'] + SG_HH['청소년부자'],
        'single_youth_expected_sample': round((SG_HH['청소년모자'] + SG_HH['청소년부자']) * f_hh, 2),
        'pubedu_aftsch_n': int((out['pubedu_aftsch_yn'] == 1).sum()),
        'pubedu_pclot_n': int((out['pubedu_pclot_yn'] == 1).sum())}
    return out[COLS]
