# -*- coding: utf-8 -*-
"""B32 건강보험 진료실적 총괄+종별 (외래·입원·응급)  — A5 / order 4 / 41개 변수

────────────────────────────────────────────────────────────────────────────
소스 (등급순, 상위 우선)
  S1 R10 2022 건강보험통계연보 (국민건강보험공단) [1차확인 2026-09-02]
     · Ⅲ-4  요양기관종별 진료형태별 진료현황(총계)
              params/raw/R10_3-4_요양기관종별_진료형태별_진료현황_총계.csv
              → 종별×(입원/외래) 진료실인원·입내원일수·진료비·급여비·입내원1일당진료비
              → 종별 실효 본인부담률 = 1 − 급여비/진료비
     · Ⅲ-9  연령별 성별 요양기관종별 평균 수진횟수(총계)   ← 본 블록에서 신규 전사
              params/tab/R10_3-9_연령성별_요양기관종별_평균수진횟수.csv
              → 연령×성×종별군 1인당 연간 내원/재원일수 (일/1,000명)
              원주3) (종합병원)=상급종합 포함, (병원)=요양병원·정신병원 포함
     · Ⅲ-7-1/Ⅲ-7-2 연령별 성별 진료현황(입원/외래)
              params/raw/R10_3-7-1_…_입원.csv, R10_3-7-2_…_외래.csv
              → 연령×성 진료실인원(이용률 프로파일), 입내원1일당진료비(단가 프로파일)
     · Ⅲ-11/Ⅲ-12 연령별 연간진료비 크기별 실인원·진료비(입원/외래) ← 본 블록에서 신규 전사
              params/tab/R10_3-11_…_입원.csv, R10_3-12_…_외래.csv
              → 연간 진료비 분포(중위·P90)로 로그정규 σ·음이항 disp 보정
     · Ⅰ-3 / Ⅰ-3-1 시도·연령·성별 적용인구(의료보장 / 건강보험) → 분모
  S1 R05 2023 보건복지통계연보(2022 실적) [1차확인]
     · 표 3-4-5 의료급여 사업실적 → 의료급여 수급자 이용률·일수 배수
     · 표 3-4-1 의료급여 대상자 유형별 → 1종/2종 구성비
  S1 NEMC 2022 응급의료 통계연보(제21호) p.150 [1차확인, 본 블록에서 신규 확보·전사]
     · 성별·연령별·시도별 응급실 이용 → nhi_in_emergency_dur
  S1 R11 data.go.kr 15122295 참고자료 [1차확인]
     · 2022 보험료분위 7구간별 본인부담상한액 → 상한제 임계값
  S4 의료급여법 시행령 [별표 1] (시행 2022.4.1) [1차확인, 본 블록에서 신규 확보·전사]
     · 1종 입원 본인부담 0 / 외래 정액 1,000~2,000원, 2종 입원 10% / 병원급 외래 15%

생성 절차
  ① 연령(20군)×성 격자에서 종별×형태별 (이용률 p, 이용자당 평균일수 m, 1일당 진료비 w) 구성
     - p : Ⅲ-7 연령×성 이용률 프로파일을 로짓 이동으로 Ⅲ-4 종별 실인원에 맞춤
     - m : Ⅲ-9 종별군 1인당 일수 ÷ p, 종별군→종별 분해는 Ⅲ-4 전국 일수 구성비
     - w : Ⅲ-4 종별 입내원1일당진료비 × Ⅲ-7 연령×성 단가지수, Ⅲ-4 진료비 총액에 맞춤
  ② 개인: 참여 = 정규코퓰러(_u_health) → 일수 ~ 음이항(core.nbinom_mean_disp)
     → 1일당진료비 ~ 로그정규(개인 frailty exp(σf·z) × 잔차 σr)  → amt = 일수 × 단가
  ③ 총괄(nhi_out_*, nhi_in_*) = 종별 4개의 합  (정합 강제)
  ④ 본인부담: 건강보험 = Ⅲ-4 실효 본인부담률(종별×형태), 의료급여 = 시행령 별표1 정액·정률
  ⑤ 응급실: NEMC 성×연령 이용률 → 음이항, _u_health·입원여부와 상관
  ⑥ 상한제(§7 R21): _nhi_own_pay > 보험료분위 상한액이면 초과분 환급

정합성 (§7)
  R21 : nhi_ceiling_subsidy_yn=1 ⇒ _nhi_own_pay > 상한액 (df에 nhi_ceiling_amt 가 있으면 그것도 함께 초과)
  R24 : *_dur 은 일(日) 단위 변수 → [0,366]. (개월 단위 급여기간 규칙의 대상이 아님)
  총괄 = Σ종별 (dur/amt/fee/subsidy 4계열 모두)
  추출대상('22년 중 외래·입원 1회 이상 이용) 밖 = NaN
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'params/raw')
TAB = os.path.join(ROOT, 'params/tab')

# ── 종별 매핑 (코드북: 전체 의과 의료기관 = 의원+병원+종합병원+상급종합병원) ──────
INST = {'clinic': '의원', 'hospital': '병원', 'gehospital': '종합병원', 'tehospital': '상급종합병원'}
ORDER = ['clinic', 'hospital', 'gehospital', 'tehospital']
FORMS = {'out': '외래', 'in': '입원'}

# ── 보정 상수 [논리적추론] — Ⅲ-11/Ⅲ-12 연간진료비 분포(중위·P90)에 맞춘 값 ─────────
#   목표(원문): 외래 중위 544,734원 P90 1,721,325원(σ_ln≈0.90)
#               입원 중위 1,914,755원 P90 11,158,830원(σ_ln≈1.38)
#   tools/nhis/calib_b32.py 로 재현 가능.
SIG_F = {'out': 0.30, 'in': 0.60}    # 개인 frailty(로그) 표준편차 — _u_health 와 결정적으로 연결
SIG_R = {'out': 0.45, 'in': 0.60}    # 1일당 진료비 잔차 로그 표준편차
DISP = {'out': 4.0, 'in': 1.8}       # 음이항 과분산 (작을수록 분산 큼)
RHO = 0.35                            # 참여-건강 잠재변수 상관 (정규 코퓰러)
RHO_D = 0.45                          # 일수-건강 잠재변수 상관
MAX_DAYS = {'out': 365, 'in': 365}


# ══════════════════════════════════════════════════════ 입력 로드 ═══════════
def _nage(s):
    s = str(s).replace(' ', '').replace('세', '')
    return '85+' if '이상' in s else s


def _nsex(s):
    return {'계': 'T', '남자': 'M', '여자': 'F'}.get(str(s).strip(), str(s).strip())


AGE_GRPS = ['0', '1~4', '5~9', '10~14', '15~19', '20~24', '25~29', '30~34', '35~39', '40~44',
            '45~49', '50~54', '55~59', '60~64', '65~69', '70~74', '75~79', '80~84', '85+']
AGE_LO = np.array([0, 1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85])


def _grp_of_age(age):
    return np.clip(np.searchsorted(AGE_LO, np.asarray(age), side='right') - 1, 0, len(AGE_GRPS) - 1)


def _load_pop():
    """Ⅰ-3-1 건강보험 적용인구, Ⅰ-3 의료보장 적용인구 (연령군×성)."""
    out = {}
    for f, key in ((os.path.join(RAW, 'R10_1-3-1_시도연령성별_적용인구_건강보험.csv'), 'hi'),
                   (os.path.join(RAW, 'R10_1-3_시도연령성별_적용인구_의료보장(건강보험+의료급여).csv'), 'all')):
        d = pd.read_csv(f)
        d = d[d['구분'].astype(str).str.strip() == '계'].copy()
        d['ag'] = d['연령군'].map(_nage); d['sx'] = d['성별'].map(_nsex)
        g = np.zeros((len(AGE_GRPS), 2))
        for i, a in enumerate(AGE_GRPS):
            for j, s in enumerate(('M', 'F')):
                v = d[(d.ag == a) & (d.sx == s)]['적용인구_명']
                g[i, j] = float(v.iloc[0]) if len(v) else 0.0
        out[key] = g
    return out['hi'], out['all']


def _load_t4():
    """Ⅲ-4 종별×형태 전국 집계 (자격구분=총계)."""
    d = pd.read_csv(os.path.join(RAW, 'R10_3-4_요양기관종별_진료형태별_진료현황_총계.csv'))
    d = d[d['자격구분'].astype(str).str.strip() == '총계']
    out = {}
    for _, r in d.iterrows():
        k = (str(r['요양기관종별']).strip(), str(r['진료형태']).strip())
        out[k] = {'person': float(r['진료실인원수_명'] or 0), 'days': float(r['입내원일수_일'] or 0),
                  'amt': float(r['진료비_천원'] or 0) * 1000.0, 'ben': float(r['급여비_천원'] or 0) * 1000.0}
    return out


def _load_d9():
    """Ⅲ-9 연령×성×종별군 평균 수진횟수 (일/1,000명) → (grp, form) → (19,2) 배열."""
    d = pd.read_csv(os.path.join(TAB, 'R10_3-9_연령성별_요양기관종별_평균수진횟수.csv'))
    d['ag'] = d['연령군'].map(_nage); d['sx'] = d['성별'].map(_nsex)
    out = {}
    for grp in ('종합병원', '병원', '의원'):
        for form in ('입원', '외래'):
            m = np.zeros((len(AGE_GRPS), 2))
            sub = d[(d.요양기관종별 == grp) & (d.진료형태 == form)]
            for i, a in enumerate(AGE_GRPS):
                for j, s in enumerate(('M', 'F')):
                    v = sub[(sub.ag == a) & (sub.sx == s)]['값']
                    m[i, j] = (float(v.iloc[0]) if len(v) and pd.notna(v.iloc[0]) else 0.0) / 1000.0
            out[(grp, form)] = m
    return out


def _load_r7():
    """Ⅲ-7-1/2 연령×성 진료실인원·입내원1일당진료비 → form → dict."""
    out = {}
    for f, form in ((os.path.join(RAW, 'R10_3-7-1_연령성별_진료현황_총계_입원.csv'), '입원'),
                    (os.path.join(RAW, 'R10_3-7-2_연령성별_진료현황_총계_외래.csv'), '외래')):
        d = pd.read_csv(f)
        d['ag'] = d['연령군'].map(_nage); d['sx'] = d['성별'].map(_nsex)
        p = d.pivot_table(index=['ag', 'sx'], columns='지표', values='값')
        per = np.zeros((len(AGE_GRPS), 2)); dly = np.zeros((len(AGE_GRPS), 2))
        for i, a in enumerate(AGE_GRPS):
            for j, s in enumerate(('M', 'F')):
                if (a, s) in p.index:
                    per[i, j] = float(p.loc[(a, s), '진료실인원수_명'])
                    dly[i, j] = float(p.loc[(a, s), '입내원1일당진료비_원'])
        out[form] = {'person': per, 'daily': dly,
                     'tot_person': float(p.loc[('계', 'T'), '진료실인원수_명']),
                     'tot_daily': float(p.loc[('계', 'T'), '입내원1일당진료비_원'])}
    return out


def _load_er():
    """NEMC 2022 성×연령(10군) 응급실 이용 건수."""
    d = pd.read_csv(os.path.join(TAB, 'NEMC_2022_응급실이용_성연령별.csv'))
    d = d[(d.연령군 != '계') & (d.성별 != '계')]
    labs = ['1세미만', '1-9세', '10-19세', '20-29세', '30-39세', '40-49세', '50-59세', '60-69세', '70-79세', '80세이상']
    arr = np.zeros((len(labs), 2))
    for i, a in enumerate(labs):
        for j, s in enumerate(('남자', '여자')):
            v = d[(d.연령군 == a) & (d.성별 == s)]['응급실이용자수_건']
            arr[i, j] = float(v.iloc[0]) if len(v) else 0.0
    return arr


def _load_medi_uplift():
    """R05 표3-4-5(의료급여 사업실적 2022) ÷ Ⅲ-7(건강보험) → 이용률·일수 배수."""
    d = pd.read_csv(os.path.join(RAW, 'R05_3-4-5_의료급여사업실적_보호종류별시도별.csv'))
    d = d[(d['구분유형'] == '연도') & (d['구분'].astype(str) == '2022')]
    g = {str(r['항목']): float(r['값']) for _, r in d.iterrows() if pd.notna(r['값'])}
    return g


def _load_medi_type():
    """R05 표3-4-1 2022 의료급여 1종/2종 대상자."""
    d = pd.read_csv(os.path.join(RAW, 'R05_3-4-1_의료급여대상자_유형별.csv'))
    d = d[(d['구분유형'] == '연도') & (d['구분'].astype(str) == '2022')]
    g = {str(r['항목']): float(r['값']) for _, r in d.iterrows() if pd.notna(r['값'])}
    return g.get('1종_소계', 0.0), g.get('2종', 0.0), g.get('계', 0.0)


def _load_ceiling():
    """R11 2022 보험료분위 7구간별 본인부담상한액(일반)."""
    d = pd.read_csv(os.path.join(RAW, 'R11_연도별_본인부담상한액_보험료분위구간별.csv'))
    d = d[(d.연도 == 2022) & (d.입원유형 == '일반')].copy()
    d['k'] = d['보험료분위구간'].str.extract(r'^(\d)구간').astype(int)
    d = d.sort_values('k')
    return d['본인부담상한액_원'].astype(float).tolist()   # 길이 7


def _load_law_medi():
    """의료급여법 시행령 별표1 (2022.4.1) 본인부담."""
    d = pd.read_csv(os.path.join(TAB, 'LAW_의료급여_본인부담_2022.csv'))
    flat, rate = {}, {}
    for _, r in d.iterrows():
        if r['진료형태'] == '외래' and r['부담방식'] == '정액':
            flat[(r['수급권자종별'], r['의료급여기관'])] = float(r['본인부담'])
        if r['부담방식'] == '정률':
            rate[(r['수급권자종별'], r['의료급여기관'], r['진료형태'])] = float(r['본인부담']) / 100.0
    return flat, rate


# ══════════════════════════════════════════════════ 격자 구성 ══════════════
def _logit(p):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


def _expit(x):
    return 1.0 / (1.0 + np.exp(-x))


def _calib_logit(p0, w, target):
    """Σ expit(logit(p0)+δ)·w = target 이 되는 δ 를 이분법으로 찾아 확률격자 반환."""
    l0 = _logit(p0)
    lo, hi = -12.0, 12.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if float((_expit(l0 + mid) * w).sum()) < target:
            lo = mid
        else:
            hi = mid
    return _expit(l0 + 0.5 * (lo + hi))


def _build_grids():
    """(form, inst) → dict(p, m, w) : 연령군(19)×성(2) 격자."""
    pop_hi, pop_all = _load_pop()
    t4, d9, r7 = _load_t4(), _load_d9(), _load_r7()
    POP = pop_hi.sum()

    # 종별군 → 종별 전국 일수 구성비 (Ⅲ-4)
    share = {}
    for form in ('입원', '외래'):
        ge_grp = t4[('상급종합병원', form)]['days'] + t4[('종합병원', form)]['days']
        hs_grp = (t4[('병원', form)]['days'] + t4[('요양병원', form)]['days']
                  + t4[('정신병원', form)]['days'])
        share[('tehospital', form)] = t4[('상급종합병원', form)]['days'] / ge_grp
        share[('gehospital', form)] = t4[('종합병원', form)]['days'] / ge_grp
        share[('hospital', form)] = t4[('병원', form)]['days'] / hs_grp

    grids = {}
    for fk, form in FORMS.items():
        R = r7[form]
        rate_grid = np.where(pop_hi > 0, R['person'] / np.maximum(pop_hi, 1), 0.0)
        rbar = R['tot_person'] / POP
        dly_idx = np.where(R['daily'] > 0, R['daily'] / R['tot_daily'], 1.0)
        for ik, inst in INST.items():
            T = t4[(inst, form)]
            # (1) 이용률: Ⅲ-7 연령×성 프로파일을 로짓 이동으로 Ⅲ-4 종별 실인원에 맞춤
            p0 = _expit(_logit(T['person'] / POP) + (_logit(rate_grid) - _logit(rbar)))
            p = _calib_logit(p0, pop_hi, T['person'])
            # (2) 1인당(무조건) 일수 → 이용자당 평균일수
            if ik == 'clinic':
                d_un = d9[('의원', form)].copy()
            elif ik == 'hospital' and form == '입원':
                # 병원군 입원일수는 요양병원·정신병원(장기입원)이 지배 → 연령 프로파일 오염.
                # 오염되지 않은 종합병원군 프로파일을 형상으로 쓰고 Ⅲ-4 병원 총일수로 재척도. [논리적추론]
                d_un = d9[('종합병원', form)].copy()
            elif ik == 'hospital':
                d_un = d9[('병원', form)] * share[('hospital', form)]
            else:
                d_un = d9[('종합병원', form)] * share[(ik, form)]
            k = T['days'] / max(float((d_un * pop_hi).sum()), 1e-9)
            d_un = d_un * k
            m = np.where(p > 0, d_un / np.maximum(p, 1e-9), 0.0)
            m = np.clip(m, 1.0, MAX_DAYS[fk])
            # (3) 1일당 진료비
            w0 = T['amt'] / max(T['days'], 1e-9) * dly_idx
            k2 = T['amt'] / max(float((d_un * pop_hi * w0).sum()), 1e-9)
            w = w0 * k2
            grids[(fk, ik)] = {'p': p, 'm': m, 'w': w,
                               'own_rate': 1.0 - T['ben'] / max(T['amt'], 1e-9),
                               'nat': T}
    return grids, pop_hi, pop_all



# ══════════════════════════════════ 개인수준 추출 ═══════════════════════════
def _draw(g, G, ai, sj, zh, p_mult, m_mult, fk, sig_f=None, sig_r=None, disp=None):
    """한 (형태×종별) 셀의 개인 추출.

    _u_health(zh) 와 상관시키면 이용자가 zh 상위에서 선택되므로 일수·단가의
    조건부 평균이 무조건부 평균보다 커진다. 이변량정규 항등식
        E[e^{a·z} | z2<t] = e^{a²/2}·Φ(t+a·ρ)/Φ(t)      (Corr(z,z2) = −ρ)
    로 셀별 보정계수 A(일수)·B(단가)를 곱해 전국 집계(Ⅲ-4)를 무편향으로 재현한다.
    """
    from scipy.stats import norm
    n = len(zh)
    sig_f = SIG_F[fk] if sig_f is None else sig_f
    sig_r = SIG_R[fk] if sig_r is None else sig_r
    disp = DISP[fk] if disp is None else disp
    b = RHO_D * 0.55

    p = np.clip(G['p'][ai, sj] * p_mult, 1e-6, 0.995)
    m = np.clip(G['m'][ai, sj] * m_mult, 1.0, MAX_DAYS[fk])
    w = G['w'][ai, sj]

    t = norm.ppf(p)
    A = p / np.maximum(norm.cdf(t + b * RHO), 1e-12)
    B = norm.cdf(t + b * RHO) / np.maximum(np.exp(b * sig_f) * norm.cdf(t + (b + sig_f) * RHO), 1e-12)

    e = norm.ppf(np.clip(g.random(n), 1e-9, 1 - 1e-9))
    # zh 가 클수록(건강위험↑) 이용확률↑ 이 되도록 부호를 뒤집는다
    use = norm.cdf(-RHO * zh + np.sqrt(1 - RHO ** 2) * e) < p

    fd = np.exp(b * zh - b ** 2 / 2.0)
    mu = np.clip(m * A * fd, 0.02, MAX_DAYS[fk])
    d = np.clip(core.nbinom_mean_disp(g, np.maximum(mu - 1.0, 0.02), disp, size=n) + 1, 1, MAX_DAYS[fk])
    d = np.where(use, d, 0).astype(np.int64)

    frail = np.exp(sig_f * zh - sig_f ** 2 / 2.0)
    dly = core.lognormal_mean(g, w * B * frail, sig_r, n)
    amt = np.rint(np.where(use, d * dly, 0.0))
    return use, d, amt, dly

# ══════════════════════════════════════════════════════ 생성 ═══════════════
def generate(df, params, ctx):
    g = core.rng('B32')
    n = len(df)
    from scipy.stats import norm

    age = df['age'].to_numpy()
    sexj = (df['gender'].to_numpy() == 2).astype(int)          # 0=남 1=여
    ai = _grp_of_age(age)
    uh = np.clip(df['_u_health'].to_numpy() if '_u_health' in df.columns else g.random(n), 1e-6, 1 - 1e-6)
    zh = norm.ppf(uh)

    grids, pop_hi, pop_all = _build_grids()
    er_arr = _load_er()
    ceil_tab = _load_ceiling()
    flat_law, rate_law = _load_law_medi()
    up = _load_medi_uplift()
    t4 = _load_t4()

    # ── 의료급여 판정 (B31 nhi_type 우선, 없으면 저소득 프록시) ─────────────
    n1, n2, ntot = _load_medi_type()
    medi_share = ntot / float(pop_all.sum())
    if 'nhi_type' in df.columns:
        is_medi = df['nhi_type'].isin([7, 8]).to_numpy()
        medi_src = 'B31 nhi_type∈{7,8}'
    else:
        ui = df['_u_income'].to_numpy() if '_u_income' in df.columns else g.random(n)
        is_medi = ui < medi_share
        medi_src = '[폴백] B31 미구현 → _u_income 하위 %.3f%%' % (medi_share * 100)
    # 1종/2종 (R05 표3-4-1 구성비) — 저소득·고령일수록 1종
    p1 = n1 / max(n1 + n2, 1.0)
    is_t1 = is_medi & (core.bernoulli(g, np.full(n, p1)) == 1)
    is_t2 = is_medi & ~is_t1

    # 의료급여 이용 배수 (R05 표3-4-5 ÷ Ⅲ-7) [1차확인 수치로부터 산출]
    r7 = _load_r7()
    up_rate = {'out': (up['외래_실인원'] / up['실인원_연간']) / (r7['외래']['tot_person'] / pop_hi.sum()),
               'in': (up['입원_실인원'] / up['실인원_연간']) / (r7['입원']['tot_person'] / pop_hi.sum())}
    up_days = {'out': up['외래_1인당진료일수'] / (t4[('총계', '외래')]['days'] / r7['외래']['tot_person']),
               'in': up['입원_1인당진료일수'] / (t4[('총계', '입원')]['days'] / r7['입원']['tot_person'])}

    # 장애(B27)가 이미 있으면 이용률 가산 [논리적추론]
    dis_boost = np.ones(n)
    if 'dis_yn' in df.columns:
        dis_boost = np.where(df['dis_yn'].to_numpy() == 1, 1.30, 1.0)

    out = {}
    days_all, amt_all, fee_all, dly_all, use_all = {}, {}, {}, {}, {}

    for fk in ('out', 'in'):
        for ik in ORDER:
            G = grids[(fk, ik)]
            p_mult = dis_boost * np.where(is_medi, up_rate[fk], 1.0)
            m_mult = np.where(is_medi, up_days[fk], 1.0)
            use, d, amt, dly = _draw(g, G, ai, sexj, zh, p_mult, m_mult, fk)
            use_all[(fk, ik)] = use
            days_all[(fk, ik)] = d
            dly_all[(fk, ik)] = dly
            amt_all[(fk, ik)] = amt

        # ── 연간 총 일수 상한 365일: 4개 종별 합이 넘으면 비례 축소 후 진료비 재계산 ──
        tot = sum(days_all[(fk, ik)] for ik in ORDER)
        over = tot > MAX_DAYS[fk]
        if over.any():
            sc = np.where(over, MAX_DAYS[fk] / np.maximum(tot, 1), 1.0)
            for ik in ORDER:
                d0 = days_all[(fk, ik)]
                d1 = np.where(d0 > 0, np.maximum(np.floor(d0 * sc), 1), 0).astype(np.int64)
                days_all[(fk, ik)] = d1
                amt_all[(fk, ik)] = np.rint(np.where(d1 > 0, d1 * dly_all[(fk, ik)], 0.0))
            # 내림 후에도 초과가 남으면 가장 일수가 많은 종별에서 차감
            tot = sum(days_all[(fk, ik)] for ik in ORDER)
            for _ in range(8):
                ex = tot - MAX_DAYS[fk]
                if not (ex > 0).any():
                    break
                arr = np.vstack([days_all[(fk, ik)] for ik in ORDER])
                j = arr.argmax(axis=0)
                for k, ik in enumerate(ORDER):
                    m = (ex > 0) & (j == k) & (days_all[(fk, ik)] > 1)
                    if m.any():
                        cut = np.minimum(ex[m], days_all[(fk, ik)][m] - 1)
                        d1 = days_all[(fk, ik)].copy(); d1[m] -= cut
                        days_all[(fk, ik)] = d1
                        amt_all[(fk, ik)] = np.rint(np.where(d1 > 0, d1 * dly_all[(fk, ik)], 0.0))
                tot = sum(days_all[(fk, ik)] for ik in ORDER)

        for ik in ORDER:
            use, d, amt = use_all[(fk, ik)], days_all[(fk, ik)], amt_all[(fk, ik)]
            G = grids[(fk, ik)]
            # 본인부담금
            own = np.rint(amt * G['own_rate'])
            if fk == 'out':
                inst_law = ('제1차의료급여기관(의원)' if ik == 'clinic'
                            else '제3차의료급여기관(상급종합병원)' if ik == 'tehospital'
                            else '제2차의료급여기관(병원·종합병원)')
                f1 = flat_law.get(('1종', inst_law), 0.0)
                own = np.where(is_t1, np.minimum(d * f1, amt), own)
                if ik == 'clinic':
                    f2 = flat_law.get(('2종', '제1차의료급여기관(의원)'), 0.0)
                    own = np.where(is_t2, np.minimum(d * f2, amt), own)
                else:
                    r2 = rate_law.get(('2종', '제2차·제3차의료급여기관(병원 이상)', '외래'), 0.15)
                    own = np.where(is_t2, np.rint(amt * r2), own)
            else:
                own = np.where(is_t1, 0.0, own)
                r2i = rate_law.get(('2종', '전(全)기관', '입원'), 0.10)
                own = np.where(is_t2, np.rint(amt * r2i), own)
            own = np.rint(np.minimum(own, amt))
            fee_all[(fk, ik)] = own

            # 미이용(청구 없음) 셀 = NaN. §7 R24 의 _dur 허용범위(일 단위 [1,366])와
            # "NULL 패턴 = 추출대상 정의"(§9)를 함께 만족시킨다.
            nan = ~use
            out[f'nhi_{fk}_{ik}_dur'] = np.where(nan, np.nan, d.astype(float))
            out[f'nhi_{fk}_{ik}_amt'] = np.where(nan, np.nan, amt)
            out[f'nhi_{fk}_{ik}_fee'] = np.where(nan, np.nan, own)
            out[f'nhi_{fk}_{ik}_subsidy'] = np.where(nan, np.nan, amt - own)

        # ── 총괄 = 종별 합 (정합 강제). 4종 모두 미이용이면 NaN ─────────────
        tot_d = sum(days_all[(fk, ik)] for ik in ORDER).astype(float)
        tot_a = sum(amt_all[(fk, ik)] for ik in ORDER)
        tot_f = sum(fee_all[(fk, ik)] for ik in ORDER)
        z = tot_d <= 0
        out[f'nhi_{fk}_dur'] = np.where(z, np.nan, tot_d)
        out[f'nhi_{fk}_amt'] = np.where(z, np.nan, tot_a)
        out[f'nhi_{fk}_fee'] = np.where(z, np.nan, tot_f)
        out[f'nhi_{fk}_subsidy'] = np.where(z, np.nan, tot_a - tot_f)

    # ── 응급실 재원(방문)일수 ─────────────────────────────────────────────
    er_lo = np.array([0, 1, 10, 20, 30, 40, 50, 60, 70, 80])
    eri = np.clip(np.searchsorted(er_lo, age, side='right') - 1, 0, 9)
    pop_er = np.zeros((10, 2))
    pack = [[0], [1, 2], [3, 4], [5, 6], [7, 8], [9, 10], [11, 12], [13, 14], [15, 16], [17, 18]]
    for i, idxs in enumerate(pack):
        pop_er[i] = pop_all[idxs].sum(axis=0)
    er_rate = np.where(pop_er > 0, er_arr / np.maximum(pop_er, 1), 0.0)
    mu_er = er_rate[eri, sexj]
    # 입원 경험자·건강위험군에서 응급실 이용↑ (NEMC: 응급실 이용의 17.4%가 입원으로 이어짐)
    mult = np.exp(0.45 * zh - 0.45 ** 2 / 2.0) * np.where(np.nan_to_num(out['nhi_in_dur']) > 0, 2.2, 0.85)
    mult = mult / max(float(mult.mean()), 1e-9)          # E[mult]=1 → 전국 이용률 보존
    er = np.clip(core.nbinom_mean_disp(g, np.maximum(mu_er * mult, 1e-6), 0.25, size=n), 0, 365)
    out['nhi_in_emergency_dur'] = np.where(er <= 0, np.nan, er.astype(float))

    # ── 추출대상: '22년 중 외래 또는 입원 1회 이상 이용한 집단 ───────────────
    in_scope = (np.nan_to_num(out['nhi_out_dur']) > 0) | (np.nan_to_num(out['nhi_in_dur']) > 0)
    res = pd.DataFrame(out, index=df.index).astype(float)
    res.loc[~in_scope, :] = np.nan

    # ── 헬퍼: 연간 본인부담금 합계 (계약: B32 → B31 상한제) ──────────────────
    own_pay = res['nhi_out_fee'].fillna(0) + res['nhi_in_fee'].fillna(0)
    res['_nhi_own_pay'] = np.rint(own_pay.to_numpy())

    # ── 본인부담상한제 (§7 R21) ──────────────────────────────────────────
    #   보험료 분위: B31 nhi_premium_cal_p20(0~20) 있으면 사용, 없으면 소득 프록시
    if 'nhi_premium_cal_p20' in df.columns:
        q10 = np.clip(np.ceil(df['nhi_premium_cal_p20'].to_numpy() / 2.0), 1, 10)
    elif '_recog_rank' in df.columns:
        q10 = np.clip(np.ceil((1.0 - df['_recog_rank'].to_numpy()) * 10.0), 1, 10)
    elif '_u_income' in df.columns:
        q10 = np.clip(np.ceil(df['_u_income'].to_numpy() * 10.0), 1, 10)
    else:
        q10 = np.full(n, 5.0)
    band = np.select([q10 <= 1, q10 <= 3, q10 <= 5, q10 <= 7, q10 <= 8, q10 <= 9],
                     [0, 1, 2, 3, 4, 5], default=6).astype(int)
    thr = np.asarray(ceil_tab, float)[band]
    res['_nhi_ceiling_thr'] = thr

    op = res['_nhi_own_pay'].to_numpy()
    if 'nhi_ceiling_amt' in df.columns:   # B31 이 분위별 상한액을 이미 배정했으면 그 값을 임계값으로
        ca = df['nhi_ceiling_amt'].to_numpy(dtype=float)
        thr = np.maximum(thr, np.where(np.isnan(ca), -np.inf, ca))
        res['_nhi_ceiling_thr'] = thr
    elig = (~is_medi) & in_scope & (op > thr)          # 의료급여는 상한제 대상 아님
    made_ceiling = ('nhi_ceiling_subsidy_yn' not in df.columns
                    and 'nhi_ceiling_subsidy_amt' not in df.columns)
    if made_ceiling:
        # yn: 상한제 적용 대상(건강보험 가입 ∧ 추출대상) 내 0/1, 그 밖은 NaN
        base = in_scope & (~is_medi)
        res['nhi_ceiling_subsidy_yn'] = np.where(base, elig.astype(float), np.nan)
        # amt: 코드북 추출대상 "1년 동안 한번이라도 수급한 집단" → 미수급은 NaN
        res['nhi_ceiling_subsidy_amt'] = np.where(elig, np.rint(op - thr), np.nan)

    ctx.setdefault('B32_notes', []).append(
        f'의료급여 판정: {medi_src}; 상한제 생성={made_ceiling}; 추출대상 {int(in_scope.sum())}/{n}')
    return res
