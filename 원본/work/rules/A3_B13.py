# -*- coding: utf-8 -*-
"""B13 국민연금 (가입·보험료·두루누리·실업크레딧·연금·일시금)  (A3 / order 4)

소스 (등급순):
  S1 R15 국민연금공단 「2022년 국민연금 통계연보(제35호)」 [1차확인 2026-09-02]
     표10 종별·연령별·성별 가입자 현황(p.78~79) / 표12 종별·기준소득월액 구간별 가입자(p.82~83)
     표21 연령별·납부예외 사유별 지역가입자(p.124~125) / 표32 노령연금 급여액 구간(p.186~187)
     표5·표6 급여종류별·연령별·성별 수급자·지급액(p.38~41) / 표61 반환일시금 수급사유(p.260~261)
     표2 지역별·종별 가입자 변동 현황(p.30~31, 취득·상실)
     → params/raw/R15_표*.csv (전사본), R15_국민연금_통계연보_제35호_2022.pdf (원본)
  S1 국민연금공단 data.go.kr 15094020/15094021/15094024/15094026/15094030 (월별 2022) [1차확인]
  S1 국민연금공단 data.go.kr 15122821 두루누리 지원현황(시도×월) [1차확인]
  S0 R02 <표 2-19> p.83 정부 공표자료 대비 사회보장행정데이터 국민연금 가입자 비교 [1차확인]
     → 행정데이터(일반가구 표본)의 가입률이 정부통계 대비 0.9753배. 이 보정을 적용한다.
  S2 R17 통계청 2022년 연금통계 보도자료 (부록3 용어: 국민연금 가입자 = 사업장+지역(납부예외 포함)
     +임의+임의계속 → 코드북 np_yn 정의와 일치) [1차확인]
  S4 국민연금법 제88조③④ (시행 2022.6.22, 법률 제18608호): 사업장가입자 기여금 = 기준소득월액의
     1천분의 45, 지역·임의·임의계속 = 1천분의 90 [1차확인 law.go.kr]
  S4 보건복지부고시 제2022-71호(2022.3.31, 시행 2022.7.1): 기준소득월액 하한 350,000원 /
     상한 5,530,000원 (2022.7~2023.6월분) [1차확인 law.go.kr 첨부 원문]

블록 간 계약:
  · B13 은 order 4 에서 B14 보다 먼저 실행되므로 §7 R05(직역연금 가입 ⇒ np_yn=0)를 만족시키기 위해
    **직역연금 배정을 여기서 먼저 수행**하고 헬퍼 `_occp_yn1_grp`·`_occp_grp`·`_occp_pen_grp` 로 넘긴다.
  · `_np_months_total` : 국민연금 누적 가입개월(수급자 포함). §7 R03 검사용 헬퍼(최종 산출물 제외).
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

RAW = 'params/raw'

# ── 상수 (모두 원문 확인값) ──────────────────────────────────────────────────
RATE_WORKPLACE = 0.045          # [법령] 국민연금법 §88③ 사업장가입자 기여금 1천분의 45
RATE_SELF      = 0.090          # [법령] 국민연금법 §88④ 지역·임의·임의계속 1천분의 90
INC_FLOOR      = 350_000        # [법령] 복지부고시 2022-71호 기준소득월액 하한 (2022.7~)
INC_CAP        = 5_530_000      # [법령] 복지부고시 2022-71호 기준소득월액 상한 (2022.7~)
S0_HH_ADJ      = 0.97528        # [S0] R02 <표2-19> 41.85% / 정부통계 42.91% — 일반가구 표본 보정
VOL_CONT_ACQ   = 284_146        # [1차확인] 통계연보 표2(p.31) 2022 임의계속가입자 취득자수
LUMP_DEATH_EMIG = 40_477        # [1차확인] 표61 반환일시금 사망 10,625 + 국외이주 29,852
NPCREDIT_APPLY_RATE = 0.30      # [가정 A3-6] 구직급여 수급자 중 실업크레딧 신청률 (공표통계 미확보)
JOBSEEK_N      = 1_633_175      # [1차확인] R14 고용보험통계연보 2022 구직급여 순인원
NPCREDIT_CAP_INC = 700_000      # [법령] 국민연금법 §19의2 실업크레딧 인정소득 상한 70만원
NPCREDIT_GOV_SHARE = 0.75       # [법령] 실업크레딧 국가 지원 비율 75% (코드북 명시)
NP_MAX_MONTHS  = 420            # [법령] 국민연금 시행 1988.1.1 ~ 2022.12.31 = 420개월 (최대 가입기간)

BANDS = [(18, 19), (20, 24), (25, 29), (30, 34), (35, 39), (40, 44),
         (45, 49), (50, 54), (55, 59), (60, 64)]
BLAB = ['18~19', '20~24', '25~29', '30~34', '35~39', '40~44',
        '45~49', '50~54', '55~59', '60세이상']
TYPE_CODES = [0, 1, 5, 9]       # 사업장 / 지역 / 임의 / 임의계속 (코드북 np_type)
TYPE_COLS = {0: '사업장가입자_2022', 1: '지역가입자_2022', 5: '임의가입자_2022', 9: '임의계속가입자_2022'}

# 납부예외 사유 코드 (코드북 지역가입자 사유) — 통계연보 표21 사유명 → 코드
EXC_CODE = {'실직': 1, '병역': 2, '재학': 3, '교도소': 4, '감호시설': 5, '행불': 6,
            '3월입원': 7, '자연재해': 8, '사업중단': 9, '휴직': 10,
            '재해 및 생활곤란 등': 11, '기타': 12}

# 노령연금 월평균급여액 구간 (통계연보 표32) — 단위 천원
PEN_EDGES = [0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, None]
PEN_KEYS = ['100미만', '100~200', '200~300', '300~400', '400~500', '500~600',
            '600~700', '700~800', '800~900', '900~1,000', '1,000이상']
PEN_TOP_ALPHA = 6.92            # [논리적추론] 1,000천원 이상 구간 조건부평균 1,169천원이 되도록 α 설정
                                #   → 전체 평균 월액 480천원 × 평균 수급개월 11.4 = 표6 노령연금 연평균 547만원


# ── 원자료 로더 ──────────────────────────────────────────────────────────────
def _rd(f):
    for enc in ('utf-8', 'cp949'):
        try:
            return pd.read_csv(os.path.join(RAW, f), encoding=enc)
        except Exception as e:
            err = e
    raise err


def _pop_age_sex():
    p = _rd('POPUL_MOIS01_2022_11_sigungu_age1_sex.csv')
    p = p[(p.level == 'sigungu') & (p.sex.isin(['male', 'female']))].copy()
    p['age'] = p['age'].astype(int)
    t = p.pivot_table(index='age', columns='sex', values='pop', aggfunc='sum').fillna(0)
    t.columns = [1 if c == 'male' else 2 for c in t.columns]
    return t.reindex(range(0, 101)).fillna(0)


def _t10():
    d = _rd('R15_표10_종별연령별성별_가입자현황_2022.csv')
    d = d[d.연령 != '연령'].copy()
    d['가입자수_명'] = pd.to_numeric(d['가입자수_명'], errors='coerce')
    return d


def _exc_by_age():
    d = _rd('R15_표21_납부예외사유별연령별_지역가입자_전국_2022.csv')
    d['납부예외자수_명'] = pd.to_numeric(d['납부예외자수_명'], errors='coerce')
    return d


def _exc_sex_share():
    m = _rd('R15_15094026_성별가입종별_가입자수_월별_2022.csv')
    m = m[m.기준년월 == '2022-12'].set_index('구분')
    a, b = float(m.loc['남자', '지역 납부예외']), float(m.loc['여자', '지역 납부예외'])
    return {1: a / (a + b), 2: b / (a + b)}


def _np_grid():
    """band × sex 별 소득신고·납부예외 가입자 수, 종별 구성, 인구, 가입률."""
    POP = _pop_age_sex()
    t10 = _t10()
    tot = {}
    typ = {}
    for (a, s, k), v in t10.set_index(['연령', '성', '항목'])['가입자수_명'].items():
        if s == '계':
            continue
        sx = 1 if s == '남' else 2
        if k == '2022':
            tot[(a, sx)] = v
        for c, col in TYPE_COLS.items():
            if k == col:
                typ[(a, sx, c)] = v
    exc = _exc_by_age()
    exc_age = exc[exc.납부예외사유 == '계'].set_index('연령')['납부예외자수_명']
    esh = _exc_sex_share()
    rows = []
    for i, (lo, hi) in enumerate(BANDS):
        lab = BLAB[i]
        for s in (1, 2):
            inc = float(tot[(lab, s)])
            ex = float(exc_age[lab]) * esh[s]
            popn = float(POP.loc[lo:hi, s].sum())
            r = dict(band=lab, lo=lo, hi=hi, sex=s, n_income=inc, n_exc=ex,
                     n_total=inc + ex, pop=popn)
            for c in TYPE_CODES:
                r[f'ty{c}'] = float(typ.get((lab, s, c), 0.0))
            rows.append(r)
    G = pd.DataFrame(rows)
    G['rate'] = G.n_total / G['pop']
    return G, POP


def _dur_hist():
    """납부기간 구간별 가입자 수 (사업장·임의) + 종별 평균가입기간."""
    a = _rd('R15_15094021_납부기간별_사업장가입자수_월별_2022.csv')
    b = _rd('R15_15094024_납부기간별_임의가입자수_월별_2022.csv')
    a = a[a.기준년월 == '2022-12'].iloc[0]
    b = b[b.기준년월 == '2022-12'].iloc[0]
    cols = ['1-11월', '12-35월', '36-59월', '60-119월', '120월 이상']
    edges = [1, 12, 36, 60, 120, None]
    m = _rd('R15_15094030_성별가입종별_평균가입기간_월별_2022.csv')
    m = m[m.기준년월 == '2022-12'].set_index('구분')
    means = {'계': float(m.loc['계', '계']), 0: float(m.loc['계', '사업장가입자']),
             1: float(m.loc['계', '지역 소득신고']), '납부예외': float(m.loc['계', '지역 납부예외']),
             5: float(m.loc['계', '임의가입자']), 9: float(m.loc['계', '임의계속가입자'])}
    means_sex = {(s, k): float(m.loc[lab, col])
                 for s, lab in ((1, '남자'), (2, '여자'))
                 for k, col in ((0, '사업장가입자'), (1, '지역 소득신고'), ('납부예외', '지역 납부예외'),
                                (5, '임의가입자'), (9, '임의계속가입자'))}
    return {'edges': edges,
            'w_work': [float(a[c]) for c in cols],
            'w_vol': [float(b[c]) for c in cols],
            'means': means, 'means_sex': means_sex}


def _inc_hist():
    """표12 종별 기준소득월액 구간별 가입자 수 → (edges, weights per 종별)."""
    d = _rd('R15_표12_종별_기준소득월액구간별_가입자현황_2022.csv')
    d['값'] = pd.to_numeric(d['값'], errors='coerce')
    lab2col = {0: '사업장가입자_명', 1: '지역가입자_명', 5: '임의가입자_명', 9: '임의계속가입자_명'}
    rows = d[(d.기준소득월액구간_원 != '계')]
    ords = [x for x in rows.기준소득월액구간_원.unique()]
    edges, W = [], {c: [] for c in TYPE_CODES}
    for lab in ords:
        if lab.startswith('~'):
            lo = 100_000
        else:
            lo = int(lab.split('이상')[0].replace(',', '').strip())
        edges.append(lo)
        sub = rows[rows.기준소득월액구간_원 == lab].set_index('항목')['값']
        for c in TYPE_CODES:
            W[c].append(float(sub.get(lab2col[c], 0.0)))
    edges.append(None)          # 마지막 개방구간 (상한 5,530,000 으로 절단)
    return edges, W


def _exc_reason_tab():
    d = _exc_by_age()
    d = d[(d.납부예외사유 != '계') & (d.연령 != '계')].copy()
    d['code'] = d.납부예외사유.map(EXC_CODE)
    return d.dropna(subset=['code'])


def _t5():
    d = _rd('R15_표5_급여종류별연령별성별_수급자현황_2022.csv')
    d = d[d.연령 != '연령'].copy()
    d['수급자수_명'] = pd.to_numeric(d['수급자수_명'], errors='coerce')
    return d


def _pen_hist_w():
    d = _rd('R15_표32_노령연금_기준소득월액평균액별_월평균급여액별_수급자_2022.csv')
    d['수급자수_명'] = pd.to_numeric(d['수급자수_명'], errors='coerce')
    t = d[(d.기준소득월액평균액_B값_천원 == '총계') & (d.월평균급여액구간_천원 != '계')]
    s = t.set_index('월평균급여액구간_천원')['수급자수_명']
    return [float(s[k]) for k in PEN_KEYS]


def _duruniri():
    d = _rd('R15_두루누리_시도별월별_지원현황_2022.csv')
    m = d.groupby('결정년월')[['지원가입자수_명', '지원금액_원']].sum()
    return {'dec_n': float(m.loc['2022-12', '지원가입자수_명']),
            'mean_n': float(m['지원가입자수_명'].mean()),
            'year_amt': float(m['지원금액_원'].sum()),
            'per_person_month': float(m['지원금액_원'].sum() / m['지원가입자수_명'].sum())}


# ── 직역연금 배정 (§7 R05 · B14 로 인계) ─────────────────────────────────────
GOVP_RETIRE_2022 = 50_479       # [1차확인] 15053026 2022 공무원 퇴직자 합계
PRIVSCHP_N = 333_231            # [1차확인] 보건복지통계연보 표5-1-1 사학 가입자 (남138,513+여194,718)
PRIVSCHP_M_SHARE = 138_513 / 333_231
MILP_N_M, MILP_N_F = 174_705, 17_381     # [1차확인] 표5-1-1 군인연금 가입자
MILP_RETIRE_RATE = 0.06         # [가정 A3-7] 연간 전역률 (군인연금 공표 통계 미확보)
PRIVSCHP_RETIRE_RATE = GOVP_RETIRE_2022 / 1_280_994   # [논리적추론] 공무원 퇴직률 3.94% 준용
MILP_AGE_LO, MILP_AGE_HI, MILP_AGE_PEAK, MILP_AGE_W = 20, 56, 33, 10   # [가정 A3-8]


def _govp_age_sex():
    d = pd.read_csv('params/tab/R16_15053027_공무원연금_연령별성별_가입자_2022.csv')
    t = d.pivot_table(index='연령', columns='성', values='가입자수_명', aggfunc='sum')
    out = {}
    for lab, r in t.iterrows():
        lab = str(lab)
        if lab.startswith('18세미만'):
            continue
        if lab.startswith('65'):
            a = 65
        elif lab.startswith('18세이상'):
            a = 18
        else:
            a = int(''.join(ch for ch in lab if ch.isdigit()))
        out[a] = (float(r['남']), float(r['여']))
    return out


def _govp_ret_age():
    d = _rd('R16_15053026_공무원연금_연령별급여종류별_퇴직자_2022.csv')
    d.columns = [c.replace(' ', '') for c in d.columns]
    d['급여종류'] = d['급여종류'].astype(str).str.replace(' ', '')
    d['인원_명'] = pd.to_numeric(d['인원_명'], errors='coerce')
    d = d[d['급여종류'] == '합계'].copy()
    out = {}
    for _, r in d.iterrows():
        lab = str(r['구분']).replace(' ', '')
        digs = ''.join(ch for ch in lab if ch.isdigit())
        if not digs:
            continue
        out[int(digs)] = float(r['인원_명'])
    return out


def _privschp_age():
    d = _rd('R16b_사학연금_연령별학교급별_가입자현황_20220430.csv')
    d = d[d.학교급직종 == '합계'].copy()
    d['가입자수_명'] = pd.to_numeric(d['가입자수_명'], errors='coerce')
    out = {}
    for _, r in d.iterrows():
        lab = str(r['연령'])
        digs = ''.join(ch for ch in lab if ch.isdigit())
        if not digs:
            continue
        out[int(digs)] = float(r['가입자수_명'])
    return out


def _govp_pen_age_sex():
    d = _rd('R16_15052969_공무원연금_연령별성별급여종류별_수급자_2022.csv')
    d = d[d.구분 != '구분'].copy()
    d['수급자수_명'] = pd.to_numeric(d['수급자수_명'], errors='coerce')
    out = {}
    for _, r in d.iterrows():
        if r['항목'] not in ('총계(남)', '총계(여)'):
            continue
        lab = str(r['구분']).replace(' ', '')
        digs = ''.join(ch for ch in lab if ch.isdigit())
        if not digs:
            continue
        a = int(digs)
        if '미만' in lab:
            a = a - 2
        s = 1 if '남' in r['항목'] else 2
        out[(a, s)] = out.get((a, s), 0.0) + float(r['수급자수_명'])
    return out


def _privschp_pen_age():
    """사학 퇴직연금 수급자 연령분포(교원·직원, 남녀 합) + 유족연금 연령분포."""
    d = _rd('R16b_사학연금_연령별직종별성별_퇴직연금수급자수_평균연금월액_2022.csv')
    d['값'] = pd.to_numeric(d['값'], errors='coerce')
    c = d[d.항목.str.contains('수급자수')].copy()
    c['a'] = c.연령.map(lambda s: (int(''.join(ch for ch in s if ch.isdigit())) - 1)
                        if '미만' in s else int(''.join(ch for ch in s if ch.isdigit())))
    c['sex'] = np.where(c.항목.str.contains('남성'), 1, 2)
    ret = c.groupby(['a', 'sex'])['값'].sum()
    u = _rd('R16b_사학연금_연령별성별_유족연금수급자수_평균연금월액_2022.csv')
    u['값'] = pd.to_numeric(u['값'], errors='coerce')
    uc = u[u.항목.str.contains('수급자수')].copy()
    uc['a'] = uc.연령.map(lambda s: int(''.join(ch for ch in s if ch.isdigit())) - 2)
    uc['sex'] = np.where(uc.항목.str.contains('남성'), 1, 2)
    sur = uc.groupby(['a', 'sex'])['값'].sum()
    return ret, sur


# ── 확률 보정 유틸 ───────────────────────────────────────────────────────────
def _tilt(p, u, k):
    """잠재변수 u(0~1)로 로짓 기울기 k 를 주되 **평균 확률을 보존**한다."""
    p = np.clip(np.asarray(p, float), 1e-9, 1 - 1e-9)
    if k == 0 or len(p) == 0:
        return p
    base = np.log(p / (1 - p))
    z = k * (np.asarray(u, float) - 0.5)
    target = p.mean()
    lo, hi = -12.0, 12.0
    for _ in range(60):
        mid = (lo + hi) / 2
        q = 1.0 / (1.0 + np.exp(-(base + z + mid)))
        if q.mean() > target:
            hi = mid
        else:
            lo = mid
    return 1.0 / (1.0 + np.exp(-(base + z + (lo + hi) / 2)))


def _wfit(p, w, target, cap=0.995):
    """개인가중치 w 로 확대한 기대인원이 target 이 되도록 확률을 비례 조정한다.
    (표본의 성·연령 구성이 모집단과 달라 단순 인구비율만으로는 총량이 어긋나기 때문)"""
    p = np.clip(np.asarray(p, float), 0.0, cap)
    if target <= 0 or p.sum() <= 0:
        return p
    for _ in range(60):
        cur = float(np.asarray(w, float) @ p)
        if cur <= 0:
            break
        f = target / cur
        if abs(f - 1.0) < 1e-6:
            break
        p = np.clip(p * f, 0.0, cap)
    return p


def _pick(g, p, order_key):
    """Madow 체계적 추출 — 기대인원 Σp 를 정확히 재현하고, order_key(개인가중치)로
    정렬해 가중 총량의 분산까지 줄인다. 단순 베르누이는 표본 300명 규모에서
    ±10% 이상 흔들려 §9 S1 총량 허용오차(±10%)를 넘기기 때문."""
    p = np.clip(np.asarray(p, float), 0.0, 1.0)
    n = len(p)
    sel = np.zeros(n, dtype=bool)
    if p.sum() <= 0:
        return sel
    o = np.lexsort((g.random(n), np.asarray(order_key, float)))
    c = np.cumsum(p[o])
    u = g.random()
    pts = np.arange(u, c[-1], 1.0)
    idx = np.searchsorted(c, pts, side='left')
    idx = idx[idx < n]
    sel[o[idx]] = True
    return sel


def _pick_seq(g, plist, targets, w, base_mask=None):
    """상호배타 그룹을 순차 배정. 각 단계에서 남은 후보만으로 목표 가중총량을 다시 맞춘다."""
    n = len(w)
    avail = np.ones(n, bool) if base_mask is None else np.asarray(base_mask, bool).copy()
    out = []
    for p, t in zip(plist, targets):
        q = np.where(avail, np.asarray(p, float), 0.0)
        q = _wfit(q, w, t)
        sel = _pick(g, q, w)
        out.append(sel)
        avail &= ~sel
    return out, avail


def _band_of(age):
    a = np.asarray(age)
    idx = np.full(a.shape, -1, dtype=int)
    for i, (lo, hi) in enumerate(BANDS):
        idx = np.where((a >= lo) & (a <= hi), i, idx)
    return idx


# ── 생성 ─────────────────────────────────────────────────────────────────────
def generate(df, params, ctx):
    g = core.rng('B13')
    n = len(df)
    age = df['age'].to_numpy()
    sex = df['gender'].to_numpy()
    ui, ue, uw = df['_u_income'].to_numpy(), df['_u_emp'].to_numpy(), df['_u_welfare'].to_numpy()
    out = pd.DataFrame(index=df.index)

    POP = _pop_age_sex()
    N_pop = float(POP.values.sum())
    frac = n / N_pop                       # 표본추출률 (참고)
    wt = df['indwgt'].to_numpy() if 'indwgt' in df.columns else np.full(n, N_pop / n)
    ADJ = S0_HH_ADJ                        # 일반가구 표본 보정 (S0 R02 <표2-19>)

    # 근로소득 지표 (B03 미구현 시 _u_income 으로 폴백)
    if '_p_earned' in df.columns:
        earn = df['_p_earned'].fillna(0).to_numpy()
        earn_rank = pd.Series(earn).rank(pct=True).to_numpy()
    else:
        earn_rank = ui                     # [폴백] B03 미실행 → _u_income 사용 (note 명시)

    # ═══ 0. 직역연금 사전배정 (§7 R05) ═══════════════════════════════════════
    govp = _govp_age_sex()
    govp_ret = _govp_ret_age()
    psc = _privschp_age()
    psc_tot = sum(psc.values())

    p_gov = np.zeros(n); p_psc = np.zeros(n); p_mil = np.zeros(n)
    for a in range(18, 66):
        m = (age == a) if a < 65 else (age >= 65)
        if not m.any():
            continue
        pm = float(POP.loc[a, 1]) if a < 65 else float(POP.loc[65:, 1].sum())
        pf = float(POP.loc[a, 2]) if a < 65 else float(POP.loc[65:, 2].sum())
        nm, nf = govp.get(a, (0.0, 0.0))
        p_gov[m & (sex == 1)] = nm / max(pm, 1)
        p_gov[m & (sex == 2)] = nf / max(pf, 1)
        # 사학: 연령분포(2022-04-30 스냅샷)를 2022.12.31 총량 333,231명으로 스케일
        npsc = psc.get(a, 0.0) * (PRIVSCHP_N / psc_tot)
        p_psc[m & (sex == 1)] = npsc * PRIVSCHP_M_SHARE / max(pm, 1)
        p_psc[m & (sex == 2)] = npsc * (1 - PRIVSCHP_M_SHARE) / max(pf, 1)
    # 군인: 연령분포 [가정 A3-8] 가우시안, 성별 총량은 [1차확인]
    ga = np.arange(MILP_AGE_LO, MILP_AGE_HI + 1)
    gw = np.exp(-0.5 * ((ga - MILP_AGE_PEAK) / MILP_AGE_W) ** 2)
    gw = gw / gw.sum()
    for j, a in enumerate(ga):
        m = (age == a)
        if not m.any():
            continue
        pm, pf = float(POP.loc[a, 1]), float(POP.loc[a, 2])
        p_mil[m & (sex == 1)] = MILP_N_M * gw[j] / max(pm, 1)
        p_mil[m & (sex == 2)] = MILP_N_F * gw[j] / max(pf, 1)

    # 고용안정성(_u_emp)이 높을수록 직역연금 재직 확률↑ (평균 보존) → 가중 총량 캘리브레이션
    # [T2-d] 직역연금 재직자는 근로소득(B08 연말정산) 보유자 위주로 배정한다. 총량은 _wfit 이 다시 맞춘다.
    OCC_NOWAGE_RR = 0.03       # 근로소득 미보유자의 상대확률 [가정 A3-B13-WAGE] (연중 전 기간 무급휴직 등)
    if 'labinc_sum_taxy' in df.columns:
        _nw = ~(df['labinc_sum_taxy'].fillna(0).to_numpy() > 0)
        p_gov = np.where(_nw, p_gov * OCC_NOWAGE_RR, p_gov)
        p_psc = np.where(_nw, p_psc * OCC_NOWAGE_RR, p_psc)
        p_mil = np.where(_nw, p_mil * OCC_NOWAGE_RR, p_mil)
    p_gov = _wfit(_tilt(p_gov, ue, 1.2), wt, 1_280_994 * ADJ)
    p_psc = _wfit(_tilt(p_psc, ue, 1.2), wt, PRIVSCHP_N * ADJ)
    p_mil = _wfit(_tilt(p_mil, ue, 1.2), wt, (MILP_N_M + MILP_N_F) * ADJ)
    (s_gov, s_psc, s_mil), _ = _pick_seq(
        g, [p_gov, p_psc, p_mil],
        [1_280_994 * ADJ, PRIVSCHP_N * ADJ, (MILP_N_M + MILP_N_F) * ADJ], wt, (age >= 18))
    grp = np.where(s_gov, 1, np.where(s_psc, 2, np.where(s_mil, 3, 0))).astype(np.int8)

    # 연중 퇴직자 (12.31 미재직이나 연중 가입이력 有)
    ret_p = np.zeros(n)
    for a, v in govp_ret.items():
        pm = float(POP.loc[a, :].sum()) if a <= 100 else 0.0
        if pm > 0:
            ret_p[(age == a)] = v / pm
    yn1_grp = grp.copy()
    add = (grp == 0) & (g.random(n) < ret_p)
    yn1_grp[add] = 1
    for gcode, rate, base_p in ((2, PRIVSCHP_RETIRE_RATE, p_psc), (3, MILP_RETIRE_RATE, p_mil)):
        addm = (yn1_grp == 0) & (g.random(n) < base_p * rate / max(1 - rate, 1e-9))
        yn1_grp[addm] = gcode

    out['_occp_grp'] = grp                 # 12.31 기준 직역연금 가입자 그룹
    out['_occp_yn1_grp'] = yn1_grp.astype(np.int8)   # 2022 중 한 번이라도 가입

    # 직역연금 수급자 그룹 (B14 가 급여액을 만든다)
    gpen = _govp_pen_age_sex()
    psc_ret, psc_sur = _privschp_pen_age()
    pp_gov = np.zeros(n); pp_psc = np.zeros(n); pp_mil = np.zeros(n)
    for (a, s), v in gpen.items():
        aa = min(max(a, 0), 100)
        m = (age == aa) if aa < 85 else (age >= 85)
        pd_ = float(POP.loc[aa, s]) if aa < 85 else float(POP.loc[85:, s].sum())
        if pd_ > 0:
            pp_gov[m & (sex == s)] = v / pd_
    for (a, s), v in psc_ret.items():
        aa = int(min(max(a, 0), 100))
        m = (age == aa) if aa < 90 else (age >= 90)
        pd_ = float(POP.loc[aa, s]) if aa < 90 else float(POP.loc[90:, s].sum())
        if pd_ > 0:
            pp_psc[m & (sex == s)] += v / pd_
    for (a, s), v in psc_sur.items():
        aa = int(min(max(a, 0), 100))
        lo = max(aa - 4, 0)
        m = (age >= lo) & (age <= aa)
        pd_ = float(POP.loc[lo:aa, s].sum())
        if pd_ > 0:
            pp_psc[m & (sex == s)] += v / pd_
    # 군인 수급자 [가정 A3-9] 공무원 수급 연령분포를 6세 조기 이동(20년 복무 후 즉시 퇴역연금)
    for (a, s), v in gpen.items():
        aa = int(min(max(a - 6, 40), 100))
        m = (age == aa)
        pd_ = float(POP.loc[aa, s])
        if pd_ > 0:
            share = (MILP_N_M if s == 1 else MILP_N_F) / (MILP_N_M + MILP_N_F)
            pp_mil[m & (sex == s)] += v * (101_386 / 628_250) * 2 * share / pd_
    # [T2-e] 직역연금 수급자는 건강보험 피부양자(nhi_type=6)에 거의 배정하지 않는다
    #        (공적연금 연 2,000만원 초과 시 피부양자 탈락 — 시행규칙 [별표 1의2] 1-가)
    OCC_PEN_DEP_RR = 0.05      # 피부양자의 상대확률 [가정 A3-B13-DEP]
    if 'nhi_type' in df.columns:
        _dep6 = (df['nhi_type'].to_numpy() == 6)
        pp_gov = np.where(_dep6, pp_gov * OCC_PEN_DEP_RR, pp_gov)
        pp_psc = np.where(_dep6, pp_psc * OCC_PEN_DEP_RR, pp_psc)
        pp_mil = np.where(_dep6, pp_mil * OCC_PEN_DEP_RR, pp_mil)
    pp_gov = _wfit(pp_gov, wt, 628_250 * ADJ)         # [1차확인] 15052969 총계
    pp_psc = _wfit(pp_psc, wt, 106_891 * ADJ)         # [1차확인] 표5-1-1 사학 수급자
    pp_mil = _wfit(pp_mil, wt, 101_386 * ADJ)         # [1차확인] 국방부 OA-9534 2022
    (q_gov, q_psc, q_mil), _ = _pick_seq(
        g, [pp_gov, pp_psc, pp_mil], [628_250 * ADJ, 106_891 * ADJ, 101_386 * ADJ], wt)
    pen_grp = np.where(q_gov, 1, np.where(q_psc, 2, np.where(q_mil, 3, 0))).astype(np.int8)
    pen_grp[yn1_grp > 0] = 0               # 재직자는 수급자가 아니다
    out['_occp_pen_grp'] = pen_grp

    # ═══ 1. np_pension_* (노령·장애·유족) ════════════════════════════════════
    T5 = _t5()
    PBANDS = [('60~64', 60, 64), ('65~69', 65, 69), ('70~74', 70, 74),
              ('75~79', 75, 79), ('80세이상', 80, 100)]
    PKINDS = ['노령연금', '장애연금', '유족연금']
    p_pen = np.zeros(n)
    kind_w = {}
    for lab, lo, hi in PBANDS:
        for s in (1, 2):
            sub = T5[(T5.연령 == lab) & (T5.성 == ('남' if s == 1 else '여'))]
            w = sub.set_index('급여종류')['수급자수_명']
            tot = float(sum(w.get(k, 0) for k in PKINDS))
            popn = float(POP.loc[lo:hi, s].sum())
            if popn > 0:
                p_pen[(age >= lo) & (age <= hi) & (sex == s)] = min(tot / popn, 0.99) * S0_HH_ADJ
            kind_w[(lab, s)] = [float(w.get(k, 0)) for k in PKINDS]
    p_pen = np.where(age >= 60, p_pen, 0.0)                       # §7 R03
    p_pen = _wfit(_tilt(np.clip(p_pen, 0, 0.99), ui, 0.8), wt, 6_202_925 * ADJ)
    pen = _pick(g, p_pen, wt) & (age >= 60)
    out['np_pension_yn'] = np.where(pen, 1, np.nan)

    kind = np.full(n, -1)
    for lab, lo, hi in PBANDS:
        for s in (1, 2):
            sel = pen & (age >= lo) & (age <= hi) & (sex == s)
            k = int(sel.sum())
            if not k:
                continue
            w = np.array(kind_w[(lab, s)], float)
            if w.sum() <= 0:
                w = np.array([1.0, 0.0, 0.0])
            kind[sel] = core.choice_p(g, [0, 1, 2], w, k)
    PW = _pen_hist_w()
    pen_amt = np.full(n, np.nan)
    mon = np.full(n, np.nan)
    if pen.any():
        # 수급개월: 신규 수급자 10% 는 연중 개시 [논리적추론 — 수급자 전년 대비 증가율]
        mon[pen] = np.where(g.random(int(pen.sum())) < 0.90, 12, g.integers(1, 12, int(pen.sum())))
    sel = pen & (kind == 0)
    if sel.any():
        x = core.hist_loguniform(g, PEN_EDGES, PW, int(sel.sum()), pareto_alpha=PEN_TOP_ALPHA) * 1000.0
        pen_amt[sel] = np.rint(x * mon[sel])
    for kk, mean_m in ((1, 408_241.0), (2, 236_369.0)):        # 표6/표5 60세+ 장애·유족 월평균
        sel = pen & (kind == kk)
        if sel.any():
            x = core.lognormal_mean(g, np.full(int(sel.sum()), mean_m), 0.55, int(sel.sum()))
            pen_amt[sel] = np.rint(x * mon[sel])
    out['np_pension_amt'] = pen_amt

    # §7 R03 검사용 헬퍼: 국민연금 누적 가입개월 (연금 수급자) — np_dur 확정 후 아래에서 채운다
    pen_months = np.full(n, np.nan)
    if pen.any():
        k = int(pen.sum())
        extra = 120 + core.nbinom_mean_disp(g, np.full(k, 100.0), 3.0, k)
        pen_months[pen] = np.minimum(np.minimum(extra, NP_MAX_MONTHS),
                                     np.maximum((age[pen] - 17) * 12, 120))

    # ═══ 2. np_yn / np_status ════════════════════════════════════════════════
    G, _ = _np_grid()
    bidx = _band_of(age)
    p_np = np.zeros(n)
    for i, (lo, hi) in enumerate(BANDS):
        for s in (1, 2):
            row = G[(G.band == BLAB[i]) & (G.sex == s)].iloc[0]
            p_np[(bidx == i) & (sex == s)] = row['rate'] * S0_HH_ADJ
    p_np = np.clip(p_np, 0, 0.98)
    p_np[yn1_grp > 0] = 0.0                # §7 R05
    p_np[(age < 18) | (age > 64)] = 0.0    # §7 R04
    p_np[pen] = 0.0                        # 노령연금 수급 개시 후 가입 불가(국민연금법 §13①) — §7 R03
    # 근로소득 상위일수록 가입확률↑ (평균 보존) → band×성 셀별 가중 총량 캘리브레이션
    p_np = _tilt(p_np, earn_rank, 1.5)
    for i, (lo, hi) in enumerate(BANDS):
        for s_ in (1, 2):
            cell = (bidx == i) & (sex == s_)
            if not cell.any():
                continue
            tgt = float(G[(G.band == BLAB[i]) & (G.sex == s_)].iloc[0]['n_total']) * ADJ
            p_np[cell] = _wfit(p_np[cell], wt[cell], tgt)
    stock = _pick(g, p_np, wt)                       # 12.31 기준 가입자(소득신고+납부예외)

    # 상실자: 2022 중 60세 도달로 자격 상실하고 임의계속 미전환 [논리적추론]
    #   = (60세 인구 × 55~59세 가입률 − 임의계속 취득 284,146) → 연령 60(일부 61)에 배치
    r5559 = float(G[G.band == '55~59'].n_total.sum() / G[G.band == '55~59']['pop'].sum())
    n_lost = max(float(POP.loc[60].sum()) * r5559 - VOL_CONT_ACQ, 0.0)
    p_lost = np.zeros(n)
    for a, sh in ((60, 0.80), (61, 0.20)):
        pa = float(POP.loc[a].sum())
        if pa > 0:
            p_lost[(age == a)] = n_lost * sh / pa * S0_HH_ADJ
    p_lost[stock] = 0.0
    p_lost[yn1_grp > 0] = 0.0
    p_lost = _wfit(_tilt(np.clip(p_lost, 0, 0.95), earn_rank, 1.5), wt, n_lost * ADJ)
    lost = _pick(g, p_lost, wt)

    np_yn = np.where(stock | lost, 1, np.nan)
    out['np_yn'] = np_yn

    # np_status: 소득신고 1 / 상실 2 / 납부예외 3
    status = np.full(n, np.nan)
    status[lost] = 2
    p_exc = np.zeros(n)                    # 가입자 중 납부예외 비율 (band×sex)
    for i in range(len(BANDS)):
        for s in (1, 2):
            row = G[(G.band == BLAB[i]) & (G.sex == s)].iloc[0]
            p_exc[(bidx == i) & (sex == s)] = row['n_exc'] / max(row['n_total'], 1)
    m = stock
    # 저소득일수록 납부예외 확률↑ (평균 보존, earn_rank 역방향)
    pe = _wfit(_tilt(np.clip(p_exc[m], 0, 0.99), 1 - earn_rank[m], 2.0), wt[m], 3_064_194 * ADJ)
    isexc = _pick(g, pe, wt[m])
    st_stock = np.where(isexc, 3, 1)
    status[m] = st_stock
    out['np_status'] = status

    # ═══ 3. np_type (12.31 기준 가입자) ══════════════════════════════════════
    ntype = np.full(n, np.nan)
    ntype[m & (status == 3)] = 1          # 납부예외자는 전원 지역가입자(통계연보 정의)
    base = m & (status == 1)
    p_ty = {c: np.zeros(n) for c in TYPE_CODES}
    for i in range(len(BANDS)):
        for s_ in (1, 2):
            row = G[(G.band == BLAB[i]) & (G.sex == s_)].iloc[0]
            tot_i = sum(float(row[f'ty{c}']) for c in TYPE_CODES)
            if tot_i <= 0:
                continue
            cell = base & (bidx == i) & (sex == s_)
            for c in TYPE_CODES:
                p_ty[c][cell] = float(row[f'ty{c}']) / tot_i
    # 사업장가입자는 근로소득 상위, 지역가입자는 하위에 오도록 기울임 (평균 보존)
    p_ty[0] = _tilt(np.clip(p_ty[0], 1e-6, 1 - 1e-6), earn_rank, 2.0) * base
    p_ty[1] = _tilt(np.clip(p_ty[1], 1e-6, 1 - 1e-6), 1 - earn_rank, 2.0) * base
    T = {0: 14_785_761.0, 1: 3_781_550.0, 5: 365_487.0, 9: 500_827.0}   # 통계연보 표10 (소득신고)
    (sw, sr, sv, sc), rest = _pick_seq(
        g, [p_ty[0], p_ty[1], p_ty[5], p_ty[9]],
        [T[0] * ADJ, T[1] * ADJ, T[5] * ADJ, T[9] * ADJ], wt, base)
    ntype[sw] = 0; ntype[sr] = 1; ntype[sv] = 5; ntype[sc] = 9
    ntype[base & rest] = 0                # 잔여는 최다 종별(사업장)로
    out['np_type'] = ntype

    # ═══ 4. np_dur (12.31 기준 가입자) ═══════════════════════════════════════
    DH = _dur_hist()
    dur = np.full(n, np.nan)
    for c in TYPE_CODES:
        for st, key in ((1, c), (3, '납부예외')):
            sel = m & (ntype == c) & (status == st)
            k = int(sel.sum())
            if not k:
                continue
            w = DH['w_vol'] if c in (5, 9) else DH['w_work']
            x = core.hist_loguniform(g, DH['edges'], w, k, pareto_alpha=2.2)
            tgt = DH['means'][key]
            # 상한: (age−17)×12 와 제도 시행 이후 최대 가입기간 420개월(1988.1~2022.12)
            cap = np.minimum(np.maximum((age[sel] - 17) * 12, 1), NP_MAX_MONTHS).astype(float)
            for _ in range(20):                            # 연령상한 절단 후 평균 재보정
                y = np.minimum(x, cap)
                r_ = tgt / max(y.mean(), 1e-9)
                if abs(r_ - 1) < 1e-3:
                    break
                x = x * r_
            dur[sel] = np.maximum(np.rint(np.minimum(x, cap)), 1)
    out['np_dur'] = dur

    # ═══ 5. np_inc_amt (12.31 소득신고 가입자) ═══════════════════════════════
    IE, IW = _inc_hist()
    inc = np.full(n, np.nan)
    for c in TYPE_CODES:
        sel = m & (status == 1) & (ntype == c)
        k = int(sel.sum())
        if not k:
            continue
        x = core.hist_loguniform(g, IE, IW[c], k, pareto_alpha=8.0)
        x = np.clip(x, INC_FLOOR, INC_CAP)
        # 근로소득 순위와 정합: band 내 정렬
        o = np.flatnonzero(sel)
        o = o[np.argsort(-earn_rank[o])]
        inc[o] = np.sort(x)[::-1]
        inc[sel] = np.rint(inc[sel])
    out['np_inc_amt'] = inc

    # ═══ 6. np_exception_reason (12.31 납부예외자) ═══════════════════════════
    ER = _exc_reason_tab()
    reason = np.full(n, np.nan)
    for i, lab in enumerate(BLAB):
        sel = (status == 3) & (bidx == i)
        k = int(sel.sum())
        if not k:
            continue
        sub = ER[ER.연령 == lab]
        w = sub.groupby('code')['납부예외자수_명'].sum()
        if w.sum() <= 0:
            sub = ER[ER.연령 == '18~19']
            w = sub.groupby('code')['납부예외자수_명'].sum()
        reason[sel] = core.choice_p(g, list(w.index.astype(int)), w.values, k)
    out['np_exception_reason'] = reason

    # ═══ 7. np_premium_amt2 (연간 본인부담 보험료) ═══════════════════════════
    prem = np.full(n, np.nan)
    pay_m = np.zeros(n)
    pay_m[m & (status == 1)] = 12
    lostm = lost
    pay_m[lostm] = core.dur_months(g, int(lostm.sum()), 0.0, 1, 11) if lostm.any() else 0
    # 상실자의 기준소득월액(추정): 55~59 사업장가입자 분포
    inc_l = np.zeros(n)
    if lostm.any():
        kk = int(lostm.sum())
        x = core.hist_loguniform(g, IE, IW[0], kk, pareto_alpha=8.0)
        inc_l[lostm] = np.clip(x, INC_FLOOR, INC_CAP)
    rate = np.where(ntype == 0, RATE_WORKPLACE, RATE_SELF)
    base = np.where(np.isnan(inc), inc_l, np.nan_to_num(inc))
    rate = np.where(lostm, RATE_WORKPLACE, rate)
    sel = (m & (status == 1)) | lostm
    prem[sel] = np.rint(base[sel] * rate[sel] * pay_m[sel])
    out['np_premium_amt2'] = prem

    # ═══ 8. 두루누리 (np_support_*) ══════════════════════════════════════════
    DU = _duruniri()
    # 연간 1회 이상 지원자 = 12월 지원자 + 연중 종료자 [논리적추론]
    #   월별 지원자 최대(1월 404,353) ~ 최소(12월 381,568) → 연간 유니크는 월평균의 1.15배로 둔다
    n_sup_year = DU['mean_n'] * 1.15
    p_sup = np.zeros(n)
    elig = (status == 1) & (ntype == 0) & (np.nan_to_num(inc) < 2_600_000)   # 월보수 260만원 미만
    if elig.any():
        p_sup[elig] = n_sup_year * frac / max(elig.sum(), 1)
    p_sup = _wfit(_tilt(np.clip(p_sup, 0, 0.999), 1 - earn_rank, 1.5), wt, n_sup_year * ADJ)
    sup = _pick(g, p_sup, wt)
    sup_yn1 = np.where(sup, 1, np.nan)
    out['np_support_yn1'] = sup_yn1
    sup_dur = np.full(n, np.nan)
    if sup.any():
        sup_dur[sup] = core.dur_months(g, int(sup.sum()), DU['dec_n'] / n_sup_year, 1, 11)
    out['np_support_dur'] = sup_dur
    out['np_support_yn2'] = np.where(sup, np.where(sup_dur >= 12, 1, 0), np.nan)
    # 근로자 지원액 = 기준소득월액 × 4.5% × 80% (코드북 산식)
    sup_amt = np.full(n, np.nan)
    if sup.any():
        sup_amt[sup] = np.rint(np.nan_to_num(inc)[sup] * RATE_WORKPLACE * 0.8 * sup_dur[sup])
    out['np_support_amt'] = sup_amt

    # ═══ 9. 실업크레딧 (unempbn_npcredit_*) ══════════════════════════════════
    n_cred = JOBSEEK_N * NPCREDIT_APPLY_RATE
    p_cr = np.zeros(n)
    elig_c = (np_yn == 1) & (age >= 18) & (age <= 59)
    if elig_c.any():
        p_cr[elig_c] = n_cred * frac / max(elig_c.sum(), 1)
    p_cr = _wfit(_tilt(np.clip(p_cr, 0, 0.999), 1 - earn_rank, 1.0), wt, n_cred * ADJ)
    cr = _pick(g, p_cr, wt)
    out['unempbn_npcredit_yn1'] = np.where(cr, 1, np.nan)
    cr_dur = np.full(n, np.nan)
    if cr.any():
        cr_dur[cr] = core.dur_months(g, int(cr.sum()), 0.05, 1, 9)
    out['unempbn_npcredit_dur'] = cr_dur
    cr_amt = np.full(n, np.nan)
    if cr.any():
        # 인정소득 = 실직 전 평균소득의 50%, 상한 70만원 → 보험료 9% 중 국가 75%
        rec = np.minimum(np.nan_to_num(inc_l)[cr] * 0.5 + 700_000 * 0.0, NPCREDIT_CAP_INC)
        rec = np.where(rec <= 0, NPCREDIT_CAP_INC * 0.7, rec)
        cr_amt[cr] = np.rint(rec * RATE_SELF * NPCREDIT_GOV_SHARE * cr_dur[cr])
    out['unempbn_npcredit_amt'] = cr_amt

    # ═══ 10. np_lump_* (반환·사망일시금·장애일시보상금) ═══════════════════════
    LKINDS = ['반환일시금', '사망일시금', '장애일시보상금']
    LMEAN = {'반환일시금': 5_329_364.0, '사망일시금': 2_839_530.0, '장애일시보상금': 18_314_929.0}
    LBANDS = ['5세미만', '5~9', '10~14', '15~19', '20~24', '25~29', '30~34', '35~39', '40~44',
              '45~49', '50~54', '55~59', '60~64', '65~69', '70~74', '75~79', '80세이상']
    LRANGE = {'5세미만': (0, 4), '80세이상': (80, 100)}

    def _lrange(lab):
        if lab in LRANGE:
            return LRANGE[lab]
        a, b = lab.split('~')
        return int(a), int(b)
    p_lu = np.zeros(n); lw = {}
    for lab in LBANDS:
        lo, hi = _lrange(lab)
        for s in (1, 2):
            sub = T5[(T5.연령 == lab) & (T5.성 == ('남' if s == 1 else '여'))]
            w = sub.set_index('급여종류')['수급자수_명']
            tot = float(sum(w.get(k, 0) for k in LKINDS))
            popn = float(POP.loc[lo:hi, s].sum())
            if popn > 0:
                p_lu[(age >= lo) & (age <= hi) & (sex == s)] = min(tot / popn, 0.99) * S0_HH_ADJ
            lw[(lab, s)] = [float(w.get(k, 0)) for k in LKINDS]
    p_lu = _wfit(_tilt(np.clip(p_lu, 0, 0.99), ui, 0.5), wt, 231_993 * ADJ)
    lu = _pick(g, p_lu, wt)
    out['np_lump_yn'] = np.where(lu, 1, np.nan)
    lu_amt = np.full(n, np.nan)
    for lab in LBANDS:
        lo, hi = _lrange(lab)
        for s in (1, 2):
            sel = lu & (age >= lo) & (age <= hi) & (sex == s)
            k = int(sel.sum())
            if not k:
                continue
            w = np.array(lw[(lab, s)], float)
            if w.sum() <= 0:
                w = np.array([1.0, 0.0, 0.0])
            kk = core.choice_p(g, [0, 1, 2], w, k)
            mu = np.array([LMEAN[LKINDS[int(z)]] for z in kk], float)
            lu_amt[sel] = np.rint(core.lognormal_mean(g, mu, 0.55, k))
    out['np_lump_amt'] = lu_amt

    # §7 R03 헬퍼 확정: 가입자는 np_dur, 연금수급자는 pen_months
    out['_np_months_total'] = np.where(np.isnan(dur), pen_months, dur)

    return out
