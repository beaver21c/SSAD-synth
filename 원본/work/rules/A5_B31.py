# -*- coding: utf-8 -*-
"""B31 건강보험 자격·보험료·상한제·건강수준·만성질환·산정특례 (A5 / order 3, 30개 변수)

소스 (등급순, 전부 [1차확인] — registry/acq_nhis.md §1~§6 및 params/tab/*.meta.json 참조)
  S1 R10 2022 건강보험통계연보 (NHIS 통계자료실 wbhaec06300m01, 본문.zip 내 xlsx 직접 열람)
     Ⅰ-3-1/2/3/4  시도·연령·성별 적용인구 (건강보험/직장/지역/의료급여)  → nhi_type
     Ⅱ-7          보험료분위(20분위)별 보험료 현황(직장·지역)            → premium·p20
     Ⅱ-3/Ⅱ-6     보수월액 구간별(직장)·산정보험료 점수구간별(지역)       → 보조 검증
     Ⅲ-3          시도별 현금급여 지급현황 (임신·출산 진료비, 상한제 사후환급) → nhi_pregnant
     Ⅲ-6/Ⅲ-7-1   연령별 성별 진료현황(총계/입원)                          → _nhi_care_yn/_nhi_inp_yn
     Ⅵ-2          298 질병분류별 진료현황 → 코드북 (붙임) 상위30위 30개 코드 → nhi_highmedi_num
     Ⅵ-4/Ⅵ-11    (65세이상) 입원 다빈도 상병 ICD3 → 만성질환 5종 입원율
     Ⅵ-22         산정특례 연령·성별 진료현황 → nhi_special1~7
  S1 R11 본인부담상한제 (data.go.kr 15122295 참고자료 xlsx / 15020230) → nhi_ceiling_amt
  S1 R12 특정질환별 산정특례 신규등록·적용 (data.go.kr 15113453)       → 희귀/중증난치 분리비
  S1 R13 2022 건강보험 주요통계 (NHIS wbhaec06400m01)                  → 보험료 총량 검증
  S1 건강검진통계연보 2022 Ⅰ-6 연령별 성별 일반건강검진 판정현황        → nhi_healthlevel
  S4 국민건강보험법·시행령, 노인장기요양보험법 시행령 (법제처 DRF)      → 요율·단가

블록 결합 (registry/column_contract.md):
  - 본 블록이 nhi_type 을 확정한다. B24(order5)는 nhi_type∈{7,8} 을 받아 nbls_medi_yn1=1 로 맞춘다 (§7 R08).
  - §7 R16 (nhi_type=6 ⇒ 무소득 ∧ 가구 내 5) 는 가구 단위 배정으로 "가구 내 5" 를 구조적으로 보장하고,
    "무소득" 은 B03(order4)이 `_no_p_minc==1` 인 개인의 p_minc 를 0 으로 두어야 성립한다.
  - `_nhi_care_yn` `_nhi_inp_yn` 은 B32(order4)가 진료 이용 extensive margin 으로 재사용해야 한다.
  - nhi_ceiling_subsidy_yn/_amt 는 B32 가 진료비 확정 후 생성한다(본 블록은 만들지 않는다, §7 R21).
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

RAW = 'params/raw'
TAB = 'params/tab'

AG = ['0', '1~4', '5~9', '10~14', '15~19', '20~24', '25~29', '30~34', '35~39', '40~44',
      '45~49', '50~54', '55~59', '60~64', '65~69', '70~74', '75~79', '80~84', '85+']
AG_LO = np.array([0, 1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85])
SEX = {1: '남자', 2: '여자'}

# ── [1차확인] 상수 (원문 표·조문에서 직접 옮긴 값만) ─────────────────────────
POP_MEDI_TOTAL   = 52932270      # R10 Ⅰ-3   의료보장 적용인구 계
POP_NHI_TOTAL    = 51409978      # R10 Ⅰ-3-1 건강보험 적용인구 계
MEDI_65P_SHARE   = 0.4110182     # R10 Ⅰ-3-4 의료급여 적용인구 중 65세 이상 625,687/1,522,292 [1차확인]
MEDIAID_TOTAL    = 1522292       # R10 Ⅰ-3-4 의료급여 적용인구 계 (세대주 1,199,220 + 부양가족 323,072)
MEDIAID_HEAD_SH  = 0.7877726480859125   # 1,199,220 / 1,522,292
LOCAL_HEAD_SH    = 0.6303114638590238   # R10 Ⅰ-3-3 세대수 9,314,231 / 지역가입자 14,777,188
# 시설거주자 제외 보정: AGENT_BRIEF ★ — 행정데이터(등록센서스 일반가구)의 생계급여 수급률
# 2.53% vs 정부공표 2.88% (R01, 2021) → 자산조사형 급여 총량 보정계수
INST_ADJ         = 2.53 / 2.88

RATE_NHI_EMP     = 0.0699        # 국민건강보험법 시행령 제44조제1항 (1만분의 699)
RATE_NHI_EMP_OWN = 0.03495       # 법 제76조제1항 사업주와 1/2 씩
RATE_LTCARE      = 0.1227        # 노인장기요양보험법 시행령 제4조 (1만분의 1,227), 부과기준=건강보험료액
PREG_CAP_SINGLE  = 1000000       # 국민건강보험법 시행령 제23조제7항제1호
PREG_CAP_MULTI   = 1400000       # 동 제2호
PREG_TOTAL_KRW   = 334207784 * 1000   # R10 Ⅲ-3 임신·출산 진료비 지급액 (천원)

# R11 2022년 본인부담상한액(일반) — 보험료 10분위 → 7구간
CEILING_2022 = {1: 830000, 2: 1030000, 3: 1030000, 4: 1550000, 5: 1550000,
                6: 2890000, 7: 2890000, 8: 3600000, 9: 4430000, 10: 5980000}

# R10 Ⅵ-4 / Ⅵ-11 만성질환 입원 진료실인원 (ICD 3단위 합, 명)
INP_TOTAL, INP_65P = 7088365, 2284557          # R10 Ⅲ-7-1 입원 진료실인원 (계 / 65세이상 합)
CHRONIC = {                                     # var: (전체 실인원, 65세이상 실인원, 65+ 근거)
    'nhi_highbp_yn':   (41981, 28442, '1차확인'),                 # I10
    'nhi_diabetes_yn': (97257, 57451, '1차확인'),                 # E10+E11+E14 / 65+ E11+E14
    'nhi_asthma_yn':   (19379, int(19379 * 0.35), '가정'),        # J45+J46, 65+ 몫 [가정] (Ⅵ-11 100위 컷 6,915 미만)
    'nhi_copd_yn':     (37077, 19896, '1차확인'),                 # J40+J42+J44+J47 / 65+ J40+J44
    'nhi_cardiac_yn':  (31760, 27034, '1차확인'),                 # I50
}
HIGHMEDI_SUM  = 1596811        # R10 Ⅵ-2 상위30위 30개 코드 진료실인원 합 (질환×인 중복)
CARE_TOTAL    = 49078863       # R10 Ⅵ-1 진료실인원 계
RARE_SPLIT    = 345976 / (345976 + 698285)   # R12 2022 연도말적용자 희귀질환 / (희귀+중증난치)

# [가정] 자격정지 (국민건강보험법 제54조 2호 국외체류·3호 병역·4호 수용) — 공표 통계 없음
DISENT_MIL_M_1928 = 0.080      # 남 19~28세
DISENT_ADULT      = 0.006      # 그 외 19세 이상
DISENT_CHILD      = 0.001      # 18세 이하
PI12_EMP, PI12_LOC = 0.93, 0.95   # 연간 보험료 납부 12개월 비율 [가정]

# ── 피부양자 소득요건 — 국민건강보험법 시행규칙 [별표 1의2] <개정 2022. 9. 1.> ────────
#   [1차확인 2026-09-02] 법제처 DRF `lawService.do?OC=test&target=law&MST=244551&type=XML`
#   (2022.9.1 시행본) 별표키 000102E. 원문 전사 → params/raw/LAW_2022_건보시행규칙_별표1의2_
#   피부양자_소득재산요건.md, 인용 → registry/acq_A5_B31.md §1.4
#     1. 소득요건 (모두 충족)
#        가. 영 제41조제1항 각 호에 따른 소득의 합계액이 **연간 2천만원 이하**일 것
#        나. 사업소득이 **없을 것**. 다만 ① 사업자등록이 되어 있지 않은 경우(주택임대소득 제외)
#            ② 장애인 등록 ③ 상이등급 국가유공자 ④ 상이등급 보훈보상대상자 중 하나에 해당하고
#            사업소득 합계액이 **연간 500만원 이하**이면 사업소득이 없는 것으로 본다
#        라. 기혼자는 부부 모두 가목~다목 요건을 충족하여야 한다
#     2. 재산요건: 재산세 과세표준 합 5.4억원 이하(또는 5.4억~9억이면서 소득 1천만원 이하)
#   영 제41조제1항(MST=244519, 2022.9.1 시행) 소득 = 이자·배당·사업·근로·연금·기타
#   (「소득세법」상 비과세소득 제외. 제5호 단서: 공적연금소득은 연금소득 **전부**)
#   ※ 재산요건(제2호)은 B05(order 5)가 재산을 만들기 전이라 본 블록에서 평가할 수 없다 → 미적용.
DEP_INC_CAP = 20_000_000       # [별표 1의2] 1-가
DEP_BIZ_CAP =  5_000_000       # [별표 1의2] 1-나 단서
# tier 별 **직장가입자(5) 우선 배정 가산점** — 아래 _dep_tier 의 tier 인덱스로 참조하며
# 로짓+Gumbel 경쟁키(_gkey)에 더한다. [가정 A5-B31-DEP]
#   경쟁키의 로짓 부분은 R10 Ⅰ-3-2 연령·성별 가입자 몫 p5_job([1차확인])이고 실효 범위가
#   대략 logit(0.05)≈−3 ~ logit(0.95)≈+3 이다. 따라서 가산점 3.0 은 "요건 미충족자를
#   연령·성 프로파일 한 폭만큼 가입자 쪽으로 민다"는 뜻이며, 프로파일을 지우지는 않는다.
#   민감도(2026-09-02 실측, 피부양자가 낸 소득세 / 전국 소득세):
#     0(종전) 21.0% · 2.0 → 4.9% · **3.0 → 3.2%** · 4.0 → 2.3% · ∞ → 1.1%
#   3.0 초과에서는 개선폭이 작아지는 반면 B18·B19 처럼 표본 6~50행짜리 소규모 급여 블록의
#   가중 총량 목표가 난수열 위치 이동만으로 흔들려(검증목표 247 → 244~245) 순손실이다.
DEP_TIER_W = (0.0, 0.0, 0.0, 3.0)
# ── [T2] 자격 ↔ 근로소득 연결 (개편지시서 T2) ───────────────────────────────────
DEP_T3_FORCE5 = True           # 소득요건 명백 불충족(tier 3)은 직장 가구 안에서 피부양자가 될 수 없다 → 직장가입자로 확정
DEP_WAGE_W = 2.0               # 연말정산 근로소득 보유자의 직장가입자 우선 배정 가산점 [가정 A5-B31-WAGE]
JOB_HH_WAGE_W = 3.0            # 근로소득 보유자가 있는 가구의 직장 가구 우선 배정 가산점 [가정 A5-B31-WAGE]
PAY_JITTER = 0.15              # 보수 순위 → 보험료 20분위 배정 시 근무월수 이질성 [가정]
PART_YEAR_EMP     = 0.11       # 12월 기준 비직장이나 연중 직장 보수월액 보험료 이력 보유 [가정]
PART_YEAR_LOC     = 0.04       # 12월 기준 비지역세대주나 연중 지역 보험료 납부 이력 보유 [가정]
PREG_USE_MEAN_SH  = 0.90       # 이용권 상한 대비 평균 사용률 [가정]
PREG_MULTI_SH     = 0.035      # 다태아 비율 [가정]


# ── 원자료 로더 ──────────────────────────────────────────────────────────────
def _norm_ag(s):
    s = str(s).strip()
    if '85' in s:
        return '85+'
    return s.replace('세', '').strip()


def _load(fn):
    d = pd.read_csv(os.path.join(RAW, fn))
    d['ag'] = d['연령군'].map(_norm_ag)
    return d


def _cell(d, key, col='적용인구_명'):
    x = d[(d['구분'] == key) & (d['성별'].isin(['남자', '여자']))]
    return x.set_index(['ag', '성별'])[col]


def _grid(series, default=0.0):
    """(ag, 성별) Series → shape (19, 2) ndarray  [남자, 여자]"""
    out = np.full((len(AG), 2), float(default))
    for i, a in enumerate(AG):
        for j, s in enumerate(('남자', '여자')):
            try:
                out[i, j] = float(series.loc[(a, s)])
            except Exception:
                pass
    return out


def load_type_rates():
    hi = _load('R10_1-3-1_시도연령성별_적용인구_건강보험.csv')
    jb = _load('R10_1-3-2_시도연령성별_적용인구_직장.csv')
    lo = _load('R10_1-3-3_시도연령성별_적용인구_지역.csv')
    mi = _load('R10_1-3-4_시도연령성별_적용인구_의료급여.csv')
    HI = _grid(_cell(hi, '계'), 1.0)
    J5, J6 = _grid(_cell(jb, '가입자')), _grid(_cell(jb, '피부양자'))
    L, LH = _grid(_cell(lo, '가입자'), 1.0), _grid(_cell(lo, '세대수'))
    MT, MH = _grid(_cell(mi, '계'), 1.0), _grid(_cell(mi, '세대수'))
    return {
        'HI': HI,
        'p_job':  (J5 + J6) / HI,                       # 건강보험 적용자 중 직장(가입자+피부양자)
        'p5_job': np.where((J5 + J6) > 0, J5 / np.maximum(J5 + J6, 1), 0.0),   # 직장 내 가입자 몫
        'p_lhead': np.clip(LH / np.maximum(L, 1), 0.0, 0.98),
        'p_mhead': np.clip(MH / np.maximum(MT, 1), 0.0, 0.98),
        'p_medi': MT / np.maximum(HI + MT, 1),
    }


def load_prem_quantiles():
    d = pd.read_csv(os.path.join(RAW, 'R10_II-7_보험료분위별_보험료현황.csv'))
    out = {}
    for grp, key in (('직장계', 'emp'), ('지역', 'loc')):
        x = d[d['자격구분'] == grp]
        mx = x[x['지표'] == '최대보험료_원'].set_index('보험료분위')['값']
        mn = x[x['지표'] == '평균보험료_원'].set_index('보험료분위')['값']
        hi = np.array([float(mx[f'{q}분위']) for q in range(1, 21)])
        mean = np.array([float(mn[f'{q}분위']) for q in range(1, 21)])
        lo_ = np.concatenate([[0.0], hi[:-1]])
        out[key] = {'lo': lo_, 'hi': hi, 'mean': mean}
    return out


def load_care_rates():
    hi = _load('R10_1-3-1_시도연령성별_적용인구_건강보험.csv')
    HI = _grid(_cell(hi, '계'), 1.0)
    ca = _load('R10_3-6_연령성별_진료현황_총계_전체.csv')
    ip = _load('R10_3-7-1_연령성별_진료현황_총계_입원.csv')

    def _p(d):
        x = d[(d['지표'] == '진료실인원수_명') & (d['성별'].isin(['남자', '여자']))]
        return _grid(x.set_index(['ag', '성별'])['값'])
    return np.clip(_p(ca) / HI, 0, 0.99), np.clip(_p(ip) / HI, 0, 0.98)


def load_special():
    hi = _load('R10_1-3-1_시도연령성별_적용인구_건강보험.csv')
    HI = _grid(_cell(hi, '계'), 1.0)
    d = pd.read_csv(os.path.join(RAW, 'R10_6-22_산정특례_연령성별_진료현황.csv'))
    d['ag'] = d['연령군'].map(_norm_ag)
    d = d[(d['지표'] == '진료실인원수_명') & (d['성별'].isin(['남자', '여자']))]

    def gg(dz):
        return _grid(d[d['산정특례질환'] == dz].set_index(['ag', '성별'])['값'])
    tot = gg('계')
    return {
        'p_any': np.clip(tot / HI, 0, 0.9),
        'cond': {k: np.clip(gg(k) / np.maximum(tot, 1), 0, 1) for k in
                 ('암질환', '희귀난치성질환', '중증치매', '중증화상')},
    }


def load_healthexam():
    d = pd.read_csv(os.path.join(RAW, 'nhi_healthlevel_I-6_연령별성별_일반건강검진_판정현황.csv'))
    d = d[d['성별'].isin(['남자', '여자'])]
    p = d.pivot_table(index=['연령군', '성별'], columns='종합판정', values='인원_명')
    lab = ['19세이하'] + [f'{a}~{a+4}세' for a in range(20, 85, 5)] + ['85세이상']
    out = np.full((len(lab), 2), 0.01)
    for i, a in enumerate(lab):
        for j, s in enumerate(('남자', '여자')):
            try:
                r = p.loc[(a, s)]
                out[i, j] = float(r['유질환자']) / float(r['계'])
            except Exception:
                pass
    return lab, out


# ── 유틸 ────────────────────────────────────────────────────────────────────
def _agi(age):
    return np.clip(np.digitize(np.asarray(age), AG_LO[1:], right=False), 0, len(AG) - 1)


def _hei(age):
    """건강검진 Ⅰ-6 연령군 인덱스: 0=19세이하, 1=20~24 … 14=85+"""
    a = np.asarray(age)
    idx = np.where(a < 20, 0, np.clip((a - 20) // 5 + 1, 1, 14))
    return idx.astype(int)


def _tilt(p, u, spread=1.2):
    """평균을 보존하면서 잠재변수 u(0,1) 로 확률을 기울인다."""
    return np.clip(p * (1.0 - spread / 2.0 + spread * u), 0.0, 1.0)


def _draw_in_bin(g, lo, hi, mean, n):
    """[lo,hi] 안에서 평균이 mean 이 되도록: x = lo + (hi-lo)*U^k, k=(hi-lo)/(mean-lo)-1"""
    if hi <= lo or mean <= lo:
        return np.full(n, float(hi if hi > 0 else lo))
    k = (hi - lo) / (mean - lo) - 1.0
    k = float(np.clip(k, 0.02, 60.0))
    return lo + (hi - lo) * g.random(n) ** k


def _p20_of(prem, hi_edges):
    """보험료 → 20분위(1..20). hi_edges 는 각 분위 상한."""
    return np.clip(np.searchsorted(hi_edges, np.asarray(prem), side='left') + 1, 1, 20)


def _bern_exact(p, u, mask=None):
    """통제선택(Gumbel top-k): 기대인원 Σp 를 정확히 맞추면서 포함확률이 p 에 비례하도록
    대상을 고른다. 소규모 셀(수급자 수 한 자리)에서 표집분산으로 총량이 흔들리는 것을 막는다.
    u 는 잠재변수 혼합값 → 블록 간·변수 간 상관 유지."""
    p = np.asarray(p, float).copy()
    if mask is not None:
        p = np.where(mask, p, 0.0)
    out = np.zeros(len(p), dtype=np.int8)
    k = int(round(float(p.sum())))
    if k <= 0:
        return out
    q = np.clip(p, 1e-12, 1 - 1e-9)
    sc = np.log(q / (1 - q)) - np.log(-np.log(np.clip(u, 1e-12, 1 - 1e-12)))
    sc = np.where(p > 0, sc, -np.inf)
    out[np.argsort(-sc)[:k]] = 1
    return out


def _dep_tier(df, n):
    """피부양자(6) 배제 우선순위 tier — 클수록 **먼저 직장가입자(5)** 로 뽑는다.

    근거는 위 [별표 1의2] 소득요건([1차확인])과 국민건강보험법 제6조제2항(모든 사업장의
    근로자·사용자는 직장가입자)이다. B31 은 order 3 이므로 order 1~2 와 order 3 의 앞선
    에이전트(A2 B07·B10·B11, A4 B27)가 만든 **원천 DB 소득**을 그대로 참조할 수 있다.

      영 제41조제1항 소득 ← 본 시점 가용 원천 DB 컬럼
        1·2호 이자·배당 : fainc_sum                      (B10, order 3·A2)
        3호   사업      : binc_sum_inc + ybinc_sum_inc     (B09, order 2 — 원천징수·연말정산
                          사업소득 = 인적용역, **사업자등록 없음**에 대응 → 단서 ① 적용)
                          inc_binc + inc_reinc + inc_hou + inc_sehou
                          (B07, order 3·A2 — 종합소득 신고 사업·부동산임대 = 사업자등록 있음)
        4호   근로      : labinc_sum_taxy − labinc_sum_taxn (B08, order 2 — 총급여 − 비과세)
        5호   연금      : pubpen_inc(공적, 전액) + pripen_inc  (B10·B11)
        6호   기타      : othinc_sum_inc                 (B09, 소득금액)
      일용근로소득(dainc_sum)은 「소득세법」 제20조 근로소득에 해당하므로 합계액에 포함한다
      [논리적추론] (분리과세분이라 종합소득에는 합산되지 않는다).
      장애인 등록(dis_yn, B27 order 3·A4)은 단서 ②에 해당한다.

    tier 3 = 소득요건 **명백 불충족** — 사업소득 보유(1-나 단서 초과) ∨ 합계 2천만원 초과(1-가)
             ⇒ 피부양자가 될 수 없다. **DEP_TIER_W 로 실제 가산점을 받는 유일한 tier.**
    tier 2 = 요건은 충족하나 **근로·일용소득 보유** — 국민건강보험법 제6조제2항
             (모든 사업장의 근로자·사용자는 직장가입자)에 따라 가입자 쪽으로 먼저 배정.
             단 같은 항 제1호는 **고용 기간 1개월 미만 일용근로자를 직장가입자에서 제외**하므로
             일용소득만 있는 사람에게는 이 근거가 미치지 않는다 (그래서 가산점 0)
    tier 1 = 요건 충족 + 사업·부동산·기타소득만 보유 — 제6조제3항상 본래 지역가입자
    tier 0 = 일차소득 없음 (무소득 또는 금융·연금소득만) — 실제 피부양자의 전형
             (금융·연금소득은 2천만원 이하이면 [별표 1의2] 요건을 충족한다)

    ※ tier 1·2 의 가산점은 현재 0 이다(DEP_TIER_W). 요건을 **충족하는** 소득보유자를
      피부양자에서 밀어내는 것은 [별표 1의2] 가 요구하지 않는 조작이고, 실측에서도
      다른 블록의 소규모 급여 목표만 흔들고 이득이 없었다(위 DEP_TIER_W 주석의 민감도).
      두 tier 는 진단·리포트용으로 계산만 해 둔다.
    """
    def S(c):
        return df[c].fillna(0).to_numpy(float) if c in df.columns else np.zeros(n)
    # 영 제41조제1항은 「소득세법」상 **소득(금액)** 을 가리키므로, 총수입금액(_sum) 이 아니라
    # 소득금액 컬럼(inc_binc·inc_reinc·binc_sum_inc·othinc_sum_inc …)을 쓴다. 이자·배당은
    # 필요경비가 없어 지급액이 곧 소득금액이고, 근로소득은 총급여 − 비과세로 잡는다.
    def SI(inc_col, gross_col):
        return S(inc_col) if inc_col in df.columns else S(gross_col)
    wage = np.maximum(S('labinc_sum_taxy') - S('labinc_sum_taxn'), 0.0)
    day = S('dainc_sum')
    fin = S('fainc_sum')
    pens = S('pubpen_inc') + S('pripen_inc')
    oth = SI('othinc_sum_inc', 'othinc_sum')
    biz_u = SI('binc_sum_inc', 'binc_sum') + SI('ybinc_sum_inc', 'ybinc_sum')   # 사업자등록 없음
    biz_r = (SI('inc_binc', 'inc_binc_sum') + SI('inc_reinc', 'inc_reinc_sum')
             + SI('inc_hou', 'inc_hou_sum') + SI('inc_sehou', 'inc_sehou_sum'))  # 사업자등록 있음·부동산임대
    inc41 = wage + day + fin + pens + oth + biz_u + biz_r
    dis = (df['dis_yn'].fillna(0).to_numpy() == 1) if 'dis_yn' in df.columns else np.zeros(n, bool)
    biz_tot = biz_u + biz_r
    exempt = (biz_r <= 0) | dis                                  # 단서 ①(사업자등록 없음) 또는 ②(장애인)
    biz_bad = np.where(exempt, biz_tot > DEP_BIZ_CAP, biz_tot > 0)
    t3 = biz_bad | (inc41 > DEP_INC_CAP)
    t2 = (wage > 0) | (day > 0)                                  # 소득세법 §20 근로소득
    prim = t2 | (biz_tot > 0) | (oth > 0)                        # 일차소득(§7 R16 대상 성분)
    tier = np.where(t3, 3, np.where(t2, 2, np.where(prim, 1, 0))).astype(np.int8)
    return tier, inc41


def _poisson_q(lam, u):
    """Poisson(lam) 의 u-분위수 (잠재변수 연동 → 블록 간 상관 유지)."""
    lam = np.asarray(lam, float); u = np.asarray(u, float)
    out = np.zeros(len(lam), dtype=int)
    cdf = np.exp(-lam); term = np.exp(-lam).copy()
    rem = u > cdf
    k = 0
    while rem.any() and k < 40:
        k += 1
        term = term * lam / k
        cdf = cdf + term
        out = out + rem.astype(int)
        rem = u > cdf
    return out


# ── 생성 ─────────────────────────────────────────────────────────────────────
def generate(df, params, ctx):
    g = core.rng('B31')
    n = len(df)
    age = df['age'].to_numpy()
    sex = df['gender'].to_numpy()          # 1=남자 2=여자
    hid = df['hid'].to_numpy()
    head = df['head'].to_numpy()
    ui = df['_u_income'].to_numpy()
    uh = df['_u_health'].to_numpy()
    uw = df['_u_welfare'].to_numpy()
    ue = df['_u_emp'].to_numpy()
    ai = _agi(age)
    si = (sex == 2).astype(int)            # 0=남 1=여

    T = load_type_rates()
    p_job = T['p_job'][ai, si]
    p5_job = T['p5_job'][ai, si]
    p_lhead = T['p_lhead'][ai, si]
    p_mhead = T['p_mhead'][ai, si]
    p_medi_i = T['p_medi'][ai, si]         # R10 Ⅰ-3-4 연령×성별 의료급여 적용률 [1차확인]

    # ── 1. 의료급여 세대 (nhi_type 7/8) — 가구 단위 ────────────────────────
    hh = pd.DataFrame({'hid': hid, 'age': age, 'ui': ui, 'uw': uw, 'head': head})
    adult = age >= 15
    hh['ui_a'] = np.where(adult, ui, np.nan)
    grp = hh.groupby('hid')
    hh_ui = grp['ui_a'].mean().fillna(grp['ui'].mean())
    hh_uw = grp['uw'].mean()
    hh_n = grp.size()
    hh_headage = hh[hh['head'] == 1].set_index('hid')['age'].reindex(hh_ui.index)
    hh_maxage = grp['age'].max()

    dis_hh = None
    if 'dis_yn' in df.columns:                       # B27(A4, order3)이 먼저 실행된 경우만
        dis_hh = pd.DataFrame({'hid': hid, 'd': (df['dis_yn'] == 1).astype(int)}).groupby('hid')['d'].max()
    sp_hh = pd.DataFrame({'hid': hid, 'sp': df['_is_single_parent'].to_numpy()}).groupby('hid')['sp'].max()

    # ── [2026-09-02 최종검증 정정 (b)] 의료급여 세대 선정의 연령 조건부 재보정 ──
    # 종전: base_sc 에 "가구주 65세 이상" 더미 −0.15 (연령 프로파일 근거 없음).
    #   → 의료급여 수급권자 중 65세 이상이 가중 64.0% 가 되어
    #     R10 Ⅰ-3-4 실측 625,687/1,522,292 = 41.10% 를 크게 초과했다(+51.5%).
    # 변경: load_type_rates() 가 이미 읽고 있으나 선정에는 쓰이지 않던
    #   **연령×성별 의료급여 적용률 p_medi (R10 Ⅰ-3-4)** 로 가구 성향 z_pm 을 만들고,
    #   그 계수 w_age 를 **65세 이상 가중 비율이 실측 41.10% 가 되도록 이분탐색**한다.
    #   저소득 순위(0.55·hh_ui)와 세대규모(1.269명/세대) 보정은 그대로 둔다.
    hh['pm'] = p_medi_i
    hh_pm = np.log(np.maximum(grp['pm'].mean(), 1e-6))
    z_pm = (hh_pm - hh_pm.mean()) / max(float(hh_pm.std()), 1e-9)
    u_hh = pd.Series(g.random(len(hh_ui)), index=hh_ui.index)
    sc_fixed = 0.55 * hh_ui - 0.25 * hh_uw - 0.10 * sp_hh.astype(float) + 0.30 * u_hh
    if dis_hh is not None:
        sc_fixed = sc_fixed - 0.15 * dis_hh.astype(float)

    share_medi = (MEDIAID_TOTAL / POP_MEDI_TOTAL) * INST_ADJ
    target_medi = int(round(share_medi * n))
    tgt_size = MEDIAID_TOTAL / 1199220.0            # R10 Ⅰ-3-4: 1.269 명/세대
    wgt = df['indwgt'].to_numpy() if 'indwgt' in df.columns else np.ones(n, dtype=float)
    o65 = age >= 65

    # ── [2026-09-02 라운드5 정정] 세대 선정 컷오프를 **가중 모집단 기준**으로 ──
    #   종전에는 표본 인원 누적합(비가중)으로 끊어, 가중치가 낮은 가구가 뽑히면
    #   모집단 추정이 미달했다(실측 1,290,990 vs 목표 1,438,045, −10.2%).
    #   목표는 R10 Ⅰ-3-4 의료급여 적용인구에 시설보호자 보정(INST_ADJ)을 적용한 가중 인원이다.
    hh_w = pd.Series(wgt, index=hid).groupby(level=0).sum()   # 가구별 가중 인원 합
    #   시설거주자 보정은 생계급여에서 유도한 일반계수(INST_ADJ)가 아니라,
    #   R05 <표3-4-1> 의료급여 대상자 유형별에 **명시된 시설보호자 80,592명**을 직접 뺀다 [1차확인].
    #   1,522,292 − 80,592 = 1,441,700 (= targets 의 "의료급여 수급권자 수(가중, 시설보호자 제외)")
    MEDIAID_INST = 80592
    target_medi_w = MEDIAID_TOTAL - MEDIAID_INST

    def _pick(w_age):
        # 연령 가중 w_age 에서 의료급여 세대 집합과 65세 이상 비율(가중)을 돌려준다.
        base = sc_fixed - w_age * z_pm
        w_single, sel = 0.10, set()
        for _ in range(12):
            score = base - w_single * (hh_n == 1).astype(float) + 0.03 * (hh_n - 1).astype(float)
            ordr = score.sort_values().index.to_numpy()
            sizes = hh_n.reindex(ordr).to_numpy()
            csum = np.cumsum(sizes)
            wsum = np.cumsum(hh_w.reindex(ordr).to_numpy())
            kk = max(int(np.searchsorted(wsum, target_medi_w, side='left') + 1), 1)
            kk = min(kk, len(ordr))
            sel = set(ordr[:kk].tolist())
            avg = csum[kk - 1] / kk
            if abs(avg - tgt_size) < 0.02:
                break
            w_single -= 0.35 * (tgt_size - avg)
        m = np.isin(hid, list(sel))
        tot = float((m * wgt).sum())
        return sel, (float(((m & o65) * wgt).sum()) / tot if tot > 0 else 0.0)

    lo_w, hi_w = -3.0, 3.0                          # 65+ 비율은 w_age 에 대해 단조증가
    medi_hh, sh = _pick(0.0)
    for _ in range(24):                             # 이분탐색 (결정론적)
        if abs(sh - MEDI_65P_SHARE) <= 0.005:
            break
        mid = 0.5 * (lo_w + hi_w)
        medi_hh, sh = _pick(mid)
        if sh > MEDI_65P_SHARE:
            hi_w = mid
        else:
            lo_w = mid
    is_medi = np.isin(hid, list(medi_hh))


    # ── 2. 직장 가구 / 지역 가구 (가구 단위) + 개인 자격 ──────────────────
    #  [별표 1의2] 소득요건으로 매긴 피부양자 배제 우선순위 (난수 사용 없음)
    dep_tier, dep_inc41 = _dep_tier(df, n)
    ins = ~is_medi
    hj = pd.DataFrame({'hid': hid, 'p': np.where(ins, p_job, np.nan), 'ue': ue})
    hh_pjob = hj.groupby('hid')['p'].mean()
    hh_ue = hj.groupby('hid')['ue'].mean()
    # 가구 내 직장가입자 후보(15~74세)가 없으면 직장 가구가 될 수 없다
    cand = ins & (age >= 15) & (age <= 74)
    hh_cand = pd.DataFrame({'hid': hid, 'c': cand.astype(int)}).groupby('hid')['c'].max()

    # ── [2026-09-02 정정] 직장/지역 배정을 **가중 총량 할당**으로 교체 ───────
    #  종전: 가구별 베르누이 추출 + 비가중 표본비율(in_job.sum()/ins.sum())로 6회 보정.
    #    결함 두 가지가 겹쳐 있었다.
    #    (1) tgt_job·tgt_emp 는 전국 적용인구 가중평균(=모집단 비율)인데, 층화
    #        확률비례계통추출 표본에서 비가중 표본비율은 모집단 비율이 아니다.
    #    (2) 반복마다 베르누이를 새로 뽑아 비중이 ±1.5%p 출렁였고(추적 0.695→0.706→
    #        0.696→0.711→0.717→0.686) 6회에서 끊긴 마지막 draw 가 그대로 확정됐다.
    #    그 결과 모집단 기준 직장 비중이 68.0%(공표 71.26%)에 그치고 남는 인구가 전부
    #    지역가입자로 흘러 지역세대주가 10,188,094세대(공표 9,314,231, +9.4%)까지 부풀었다
    #    — 이것이 "지역가입자 보험료 연간 총액 +15.9%" 의 주된 원인이다.
    #    (12월말 월 산정보험료 평균 89,085원은 이미 공표치 90,458원과 일치했다.)
    #  변경: 성향 p 의 로짓에 Gumbel 경쟁키를 씌워 정렬(=확률비례 무작위 순위)하고,
    #    Σindwgt 누적이 목표 총량에 닿을 때까지 채운다. 같은 파일의 _alloc() ·
    #    B24 의 _solve_threshold() 와 동일한 방식이며 결정론적으로 목표를 맞춘다.
    tgt_job = float(np.average(T['p_job'], weights=T['HI']))
    tgt_emp = float(np.average(T['p5_job'], weights=T['HI'] * T['p_job']))
    wins = float((ins * wgt).sum())

    def _gkey(p, u):
        q = np.clip(np.asarray(p, float), 1e-9, 1 - 1e-9)
        return np.log(q / (1 - q)) - np.log(-np.log(np.clip(u, 1e-12, 1 - 1e-12)))

    def _fill_w(key, wv, target_w, eligible):
        # key 내림차순으로 Σwv 가 target_w 에 닿을 때까지 선택한다.
        k2 = np.where(eligible, key, -np.inf)
        o = np.argsort(-k2)
        o = o[np.isfinite(k2[o])]
        out = np.zeros(len(k2), bool)
        if o.size == 0 or target_w <= 0:
            return out
        cw = np.cumsum(np.asarray(wv, float)[o])
        kk = int(min(np.searchsorted(cw, target_w, side='left') + 1, o.size))
        out[o[:kk]] = True
        return out

    nhi_type = np.zeros(n, dtype=float)
    #  (a) 직장 가구 — 가구별 ins 가중인원 합이 tgt_job × Σ(ins·indwgt) 가 되게 채운다
    hpos = pd.Series(np.arange(len(hh_pjob)), index=hh_pjob.index).reindex(hid).to_numpy()
    wpn = np.bincount(hpos, weights=np.where(ins, wgt, 0.0), minlength=len(hh_pjob))
    pj = np.clip(hh_pjob.to_numpy() + 0.20 * (hh_ue.to_numpy() - 0.5), 0.01, 0.99)
    #  ※ [2026-09-02 시도기록] 직장 가구 선정 자체를 **가구별 소득보유 밀도**로 기울여
    #    (직장부문 tier≥1 가중 = 직장가입자 예산이 되도록 이분탐색) 남는 소득보유자를
    #    지역가입자로 보내는 안을 구현해 실측했으나, 직장/지역 가구 구성이 크게 바뀌면서
    #    가구 재산·소득인정액 경로를 타고 B24·B26(기초연금 전액수급자 비율 −24.3%p,
    #    부부2인 비율 −12.4%p)·균등화 가구일차소득 중윗값(+18.0%)이 무너져 검증목표가
    #    247 → 242 로 떨어졌다. **채택하지 않는다.** 가구 단위 선정은 종전대로 두고
    #    (b) 의 개인 단위 5/6 배정만 소득 조건부로 바꾼다.
    # [T2-a] 직장 가구 선정: 근로소득 보유자가 있는 가구를 우선한다(Σindwgt 총량 할당은 그대로)
    _wage_pos = ((df['labinc_sum_taxy'].fillna(0).to_numpy(float) > 0)
                 if 'labinc_sum_taxy' in df.columns else np.zeros(n, bool))
    _hh_wage = np.bincount(hpos, weights=(_wage_pos & ins).astype(float), minlength=len(hh_pjob)) > 0
    job_sel = _fill_w(_gkey(pj, g.random(len(pj))) + JOB_HH_WAGE_W * _hh_wage, wpn, tgt_job * wins,
                      hh_cand.to_numpy() > 0)
    in_job = job_sel[hpos] & ins

    #  (b) 직장가입자(5) — 직장 가구마다 최소 1명 강제(§7 R16: 6 ⇒ 가구 내 5) 후
    #      나머지를 Σindwgt 가 tgt_emp × Σ(직장·indwgt) 가 되게 채운다
    prop = 0.6 * ue + 0.4 * ui
    p5c = np.clip(p5_job + 0.25 * (prop - 0.5), 1e-6, 1 - 1e-6)
    k5 = _gkey(p5c, g.random(n))
    # ── [2026-09-02 라운드] 5/6 배정을 **원천 DB 소득 조건부**로 바꾼다 ─────────────
    #  종전: p5_job(연령·성 프로파일) + 잠재변수만으로 뽑아, 근로·사업소득 보유자가
    #    피부양자(6)로 배정되는 일이 흔했다. §7 R16(6 ⇒ 무소득)에 따라 B03(order 4)이
    #    그 사람의 p_* 소득을 0 으로 지우는데, p_tax_inc(B04)는 **원천 DB 세액**에서
    #    만들어지므로 지워지지 않는다 → "소득 0 · 소득세 199만원"인 사람 2,011명,
    #    이들이 낸 소득세 가중 23.9조(전국 114.1조의 21.0%)라는 내부 불일치가 남았다
    #    (registry/deviation_analysis.md §3-A·§3-C).
    #  변경: 위 _dep_tier() 가 [별표 1의2] 소득요건으로 매긴 tier 를 **1순위 정렬키**로
    #    쓴다(같은 tier 안에서는 종전 k5 순서를 그대로 유지). 구성비 목표
    #    (직장가입자 37.0% / 피부양자 32.2%)는 Σindwgt 총량 할당이 그대로 지키므로
    #    **누가 피부양자가 되는지만** 바뀐다.
    k5 = k5 + np.asarray(DEP_TIER_W, float)[dep_tier]
    k5 = k5 + DEP_WAGE_W * _wage_pos                 # [T2-b] 근로소득 보유자 우선
    elig5 = in_job & (age >= 15)
    cand5 = in_job & cand                    # 15~74세 — 가구당 1명 강제용 후보
    kc = np.where(cand5, k5, -np.inf)
    force5 = np.zeros(n, bool)
    bestpos = pd.Series(kc).groupby(hpos).idxmax()
    for i, ix in bestpos.items():
        if job_sel[i] and np.isfinite(kc[ix]):
            force5[ix] = True
    if DEP_T3_FORCE5:                                # [T2-c] tier 3 은 피부양자 불가
        force5 |= (dep_tier == 3) & elig5
    wjob = float((in_job * wgt).sum())
    rest_w = max(tgt_emp * wjob - float((force5 * wgt).sum()), 0.0)
    is5 = force5 | _fill_w(k5, wgt, rest_w, elig5 & ~force5)

    nhi_type[is5] = 5
    nhi_type[in_job & ~is5] = 6                       # 직장피부양자 (가구 내 5 존재 보장)
    local = ins & ~in_job

    # 지역: 세대주(1) / 세대원(2) — 연령·성 프로파일 × 전국 63.03% 로 스케일
    off_lh = 1.0
    lh = np.zeros(n, dtype=bool)
    for _ in range(8):
        p = np.clip(p_lhead * off_lh, 0.0, 0.99)
        lh = local & (g.random(n) < p)
        d = pd.DataFrame({'hid': hid, 'l': lh.astype(int), 'lc': local.astype(int), 'age': age})
        gg2 = d.groupby('hid')[['l', 'lc']].max()
        miss = gg2[(gg2['lc'] == 1) & (gg2['l'] == 0)].index
        if len(miss):
            sub = d[d['hid'].isin(miss) & (d['lc'] == 1)]
            idx = sub.groupby('hid')['age'].idxmax()
            lh[idx.to_numpy()] = True
        cur = float((lh * wgt).sum()) / max(float((local * wgt).sum()), 1.0)   # 모집단 비율
        if abs(cur - LOCAL_HEAD_SH) < 0.005:
            break
        off_lh *= (LOCAL_HEAD_SH / max(cur, 1e-6)) ** 0.8
    nhi_type[lh] = 1
    nhi_type[local & ~lh] = 2

    # 의료급여: 세대주(7) / 부양가족(8)
    off_mh = 1.0
    mh = np.zeros(n, dtype=bool)
    for _ in range(8):
        p = np.clip(p_mhead * off_mh, 0.0, 0.99)
        mh = is_medi & (g.random(n) < p)
        d = pd.DataFrame({'hid': hid, 'l': mh.astype(int), 'm': is_medi.astype(int), 'age': age})
        gg2 = d.groupby('hid')[['l', 'm']].max()
        miss = gg2[(gg2['m'] == 1) & (gg2['l'] == 0)].index
        if len(miss):
            sub = d[d['hid'].isin(miss) & (d['m'] == 1)]
            idx = sub.groupby('hid')['age'].idxmax()
            mh[idx.to_numpy()] = True
        cur = mh.sum() / max(is_medi.sum(), 1)
        if abs(cur - MEDIAID_HEAD_SH) < 0.005:
            break
        off_mh *= (MEDIAID_HEAD_SH / max(cur, 1e-6)) ** 0.8
    nhi_type[mh] = 7
    nhi_type[is_medi & ~mh] = 8
    nhi_type = nhi_type.astype(int)

    # ── 3. 보험료 (Ⅱ-7 20분위, 12월말 월 산정보험료) ─────────────────────
    Q = load_prem_quantiles()
    prem_cal = np.full(n, np.nan)
    p20_cal = np.full(n, np.nan)

    def _assign(mask, key, rankv=None):
        idx = np.flatnonzero(mask)
        if idx.size == 0:
            return
        # 소득 성향 순위로 20분위 배정 — R10 <표 Ⅱ-7> 의 20분위는 **모집단 세대수**
        # 균등 분위이므로 표본에서도 Σindwgt 균등으로 잘라야 한다. 종전에는 표본
        # 관측치 수 균등으로 잘라, 고분위에 큰 가중치가 몰리면서 지역세대주의
        # **가중** 평균 산정보험료가 공표치보다 6~7% 높게 나왔다(총액 과다의 잔여 원인).
        #
        # [2026-09-02 라운드] 직장가입자는 **보수 순위**로 배정한다.
        #   국민건강보험법 제69조제4항제1호 + 제70조제1항 [1차확인, MST=242985]
        #   "보수월액보험료: 제70조에 따라 산정한 보수월액에 … 보험료율을 곱하여 얻은 금액"
        #   "직장가입자의 보수월액은 직장가입자가 지급받는 보수를 기준으로 하여 산정한다"
        #   → 보수(labinc_sum_taxy, B08 order 2)가 없는 사람에게 고분위 보험료가 붙던
        #     구조(registry/deviation_analysis.md §3-C: 경상소득 78만원 가구에 보험료 237만원)를
        #     끊는다. 보수 자료가 없는 직장가입자는 하위 분위로 간다(법 제70조제3항 후단
        #     "보수 관련 자료가 없는 경우 … 고시하는 금액을 보수로 본다" = 최저보수월액).
        #   20분위의 주변분포(Ⅱ-7 구간·평균)는 Σindwgt 균등 절단이 그대로 지키므로
        #   **누구에게 어느 분위가 가는지만** 바뀐다.
        if rankv is None:
            r = ui[idx] + 0.15 * g.random(idx.size)
        else:
            rr = (pd.Series(rankv[idx]).rank(method='average').to_numpy() - 0.5) / idx.size
            r = rr + PAY_JITTER * (g.random(idx.size) - 0.5)
        o = np.argsort(r)
        wv = wgt[idx][o]
        cwm = (np.cumsum(wv) - 0.5 * wv) / max(float(wv.sum()), 1e-9)
        q = np.empty(idx.size, dtype=int)
        q[o] = np.clip(np.floor(cwm * 20).astype(int) + 1, 1, 20)
        pr = np.empty(idx.size)
        for b in range(1, 21):
            m = q == b
            c = int(m.sum())
            if c:
                pr[m] = _draw_in_bin(g, Q[key]['lo'][b - 1], Q[key]['hi'][b - 1],
                                     Q[key]['mean'][b - 1], c)
        prem_cal[idx] = np.round(pr)
        p20_cal[idx] = q

    pay = (df['labinc_sum_taxy'].fillna(0.0).to_numpy(float)
           if 'labinc_sum_taxy' in df.columns else None)
    _assign(nhi_type == 5, 'emp', pay)
    _assign(nhi_type == 1, 'loc')          # 지역은 소득+재산 점수 → 소득성향 ui 유지
    zero = np.isin(nhi_type, [2, 6])
    prem_cal[zero] = 0.0
    p20_cal[zero] = 0.0

    # 정산반영보험료 [가정]: 직장은 퇴직·중도정산 반영(로그정규 ±), 지역은 산정=정산
    prem_set = prem_cal.copy()
    m5 = nhi_type == 5
    prem_set[m5] = np.round(np.clip(prem_cal[m5] * np.exp(g.normal(0.0, 0.10, int(m5.sum()))),
                                    0.0, Q['emp']['hi'][19]))
    edges_emp = Q['emp']['hi']; edges_loc = Q['loc']['hi']
    p20_set = p20_cal.copy()
    p20_set[m5] = _p20_of(prem_set[m5], edges_emp)
    m1 = nhi_type == 1
    p20_set[m1] = _p20_of(prem_set[m1], edges_loc)

    # 연간 실납부 보험료 (본인부담) — 12월 산정보험료 × 납부개월수
    mon_e = core.dur_months(g, n, PI12_EMP, 6, 11).astype(float)
    mon_l = core.dur_months(g, n, PI12_LOC, 6, 11).astype(float)
    amt1 = np.full(n, np.nan)
    amt3 = np.full(n, np.nan)
    amt1[m5] = np.round(prem_cal[m5] * mon_e[m5])
    amt3[m1] = np.round(prem_cal[m1] * mon_l[m1])
    # 12월 기준 자격은 아니나 연중 이력 보유자 [가정] (R10 Ⅰ-6 / Ⅰ-6-1 자격변동 규모 근거)
    wk = (age >= 18) & (age <= 64) & np.isin(nhi_type, [1, 2, 6])
    ex1 = wk & (g.random(n) < PART_YEAR_EMP * (0.4 + 1.2 * ue))
    if ex1.any():
        q = g.integers(1, 21, int(ex1.sum()))
        pr = np.array([_draw_in_bin(g, Q['emp']['lo'][b - 1], Q['emp']['hi'][b - 1],
                                    Q['emp']['mean'][b - 1], 1)[0] for b in q])
        amt1[ex1] = np.round(pr * g.integers(1, 11, int(ex1.sum())))
    wk3 = (age >= 18) & np.isin(nhi_type, [2, 5, 6])
    ex3 = wk3 & (g.random(n) < PART_YEAR_LOC * (0.4 + 1.2 * (1 - ue)))
    if ex3.any():
        q = g.integers(1, 21, int(ex3.sum()))
        pr = np.array([_draw_in_bin(g, Q['loc']['lo'][b - 1], Q['loc']['hi'][b - 1],
                                    Q['loc']['mean'][b - 1], 1)[0] for b in q])
        amt3[ex3] = np.round(pr * g.integers(1, 11, int(ex3.sum())))

    lt1 = np.where(np.isnan(amt1), np.nan, np.round(amt1 * RATE_LTCARE))
    lt3 = np.where(np.isnan(amt3), np.nan, np.round(amt3 * RATE_LTCARE))

    # ── 4. 본인부담상한액 (세대 단위 보험료 10분위) ───────────────────────
    pay_p20 = np.where(np.isin(nhi_type, [1, 5]), p20_cal, np.nan)
    hp = pd.DataFrame({'hid': hid, 'q': pay_p20}).groupby('hid')['q'].max()
    q_hh = hp.reindex(hid).to_numpy()
    q_ind = np.where(np.isnan(pay_p20), q_hh, pay_p20)
    p10 = np.where(np.isnan(q_ind), np.nan, np.ceil(np.nan_to_num(q_ind, nan=1.0) / 2.0))
    ceil_amt = np.full(n, np.nan)
    ok = ~np.isnan(p10) & ~is_medi
    ceil_amt[ok] = [CEILING_2022[int(min(max(x, 1), 10))] for x in p10[ok]]

    # ── 5. 진료 이용 extensive margin (B32 재사용) ────────────────────────
    P_CARE, P_INP = load_care_rates()
    # 진료 이용률은 1에 가까워 곱셈형 tilt 가 상한에 걸리므로 미이용 확률을 기울인다(평균 보존)
    p_care = np.clip(1.0 - (1.0 - P_CARE[ai, si]) * (1.5 - 1.0 * uh), 0.0, 1.0)
    p_inp = _tilt(P_INP[ai, si], uh, 1.3)
    inp_yn = core.bernoulli(g, p_inp).astype(bool)
    care_yn = core.bernoulli(g, p_care).astype(bool) | inp_yn

    # ── 6. 건강수준 (CCI 그룹 1~17) ───────────────────────────────────────
    _, HE = load_healthexam()
    p_ill = HE[_hei(age), si]
    lam = -np.log(np.clip(1.0 - p_ill, 1e-6, 1.0))
    cci = _poisson_q(lam, uh)
    healthlevel = np.where(care_yn, np.clip(1 + cci, 1, 17), np.nan)

    # ── 7. 중증·고액진료비 상위 30위 질환 보유 개수 ──────────────────────
    SP = load_special()
    cancer_prof = SP['p_any'][ai, si] * SP['cond']['암질환'][ai, si]
    base = cancer_prof / max(float(np.mean(cancer_prof)), 1e-9)
    lam_hm = (HIGHMEDI_SUM / CARE_TOTAL) * base
    highmedi = np.where(care_yn, np.clip(_poisson_q(lam_hm, uh), 0, 10), np.nan)

    # ── 8. 만성질환 입원 5종 (추출대상 = 당해연도 입원 경험자) ───────────
    chronic = {}
    o65 = (age >= 65)
    for var, (tot, t65, _st) in CHRONIC.items():
        p65 = t65 / INP_65P
        pu = max(tot - t65, 0) / (INP_TOTAL - INP_65P)
        p = np.where(o65, p65, pu)
        ud = 0.5 * uh + 0.5 * g.random(n)
        chronic[var] = np.where(inp_yn, _bern_exact(p, ud, inp_yn).astype(float), np.nan)

    # ── 9. 임신·출산 진료비 ───────────────────────────────────────────────
    baby = pd.DataFrame({'hid': hid, 'b': (age <= 1).astype(int)}).groupby('hid')['b'].max()
    has_baby = baby.reindex(hid).to_numpy()
    mother = (sex == 2) & (age >= 15) & (age <= 49)
    sc = (2.5 * has_baby * ((age >= 19) & (age <= 45)).astype(float)
          + g.random(n)) * mother
    n_preg_target = PREG_TOTAL_KRW / (PREG_USE_MEAN_SH * (PREG_CAP_SINGLE * (1 - PREG_MULTI_SH)
                                                          + PREG_CAP_MULTI * PREG_MULTI_SH))
    # [2026-09-02] 종전에는 **표본 관측치 수** k 로 뽑았다. 그러나 검증목표
    #   '임신·출산 진료비 지원액 총액'은 **가중 총액**(Σ indwgt×amt)이므로, 뽑힌 사람의
    #   indwgt 구성에 따라 총액이 ±13% 흔들렸다(실측 −12.8%). 다른 총량과 마찬가지로
    #   Σindwgt 가 모집단 기대인원에 닿을 때까지 채워 총액을 구조적으로 맞춘다.
    preg_w = n_preg_target * float(wgt.sum()) / POP_MEDI_TOTAL
    preg = _fill_w(sc, wgt, preg_w, mother).astype(int)
    cap = np.where(g.random(n) < PREG_MULTI_SH, PREG_CAP_MULTI, PREG_CAP_SINGLE)
    kk_ = PREG_USE_MEAN_SH / (1 - PREG_USE_MEAN_SH)
    preg_amt = np.where(preg == 1, np.round(cap * g.random(n) ** (1.0 / kk_)), np.nan)
    preg_amt = np.where((preg == 1) & (preg_amt < 10000), 10000.0, preg_amt)
    preg_yn = np.where(preg == 1, 1.0, 0.0)

    # ── 10. 산정특례 ──────────────────────────────────────────────────────
    p_any = SP['p_any'][ai, si]
    spec_any = _bern_exact(p_any, 0.65 * uh + 0.35 * g.random(n)).astype(bool)
    def _cd(name):
        pc = SP['cond'][name][ai, si]
        ud = 0.5 * uh + 0.5 * g.random(n)
        return _bern_exact(pc, ud, spec_any).astype(bool) & spec_any
    s_cancer = _cd('암질환')
    s_rare_all = _cd('희귀난치성질환')
    s_dem = _cd('중증치매')
    s_rare = s_rare_all & (g.random(n) < RARE_SPLIT)
    s_intr = s_rare_all & ~s_rare
    nanv = np.full(n, np.nan)
    sp1 = np.where(spec_any, s_cancer.astype(float), np.nan)
    sp2 = np.where(spec_any, s_rare_all.astype(float), np.nan)
    sp3 = nanv.copy()                                   # 중증화상: 규모 미달
    sp4 = np.where(spec_any, s_dem.astype(float), np.nan)
    sp5 = np.where(spec_any, s_rare.astype(float), np.nan)
    sp6 = np.where(spec_any, s_intr.astype(float), np.nan)
    sp7 = nanv.copy()                                   # 기타염색체이상: 규모 미달·분리불가

    # ── 11. 자격정지 [가정] ───────────────────────────────────────────────
    p_dis = np.where((sex == 1) & (age >= 19) & (age <= 28), DISENT_MIL_M_1928,
                     np.where(age >= 19, DISENT_ADULT, DISENT_CHILD))
    dis_yn_ = np.where(is_medi, np.nan, core.bernoulli(g, p_dis).astype(float))
    dur = core.dur_months(g, n, 0.35, 1, 11).astype(float)
    dis_dur = np.where(dis_yn_ == 1, dur, np.nan)

    out = pd.DataFrame({
        'nhi_type': nhi_type,
        'nhi_premium_amt1_y': amt1,
        'nhi_premium_amt3_y': amt3,
        'nhi_premium_ltcare_amt1_y': lt1,
        'nhi_premium_ltcare_amt3_y': lt3,
        'nhi_premium_cal': prem_cal,
        'nhi_premium_set': prem_set,
        'nhi_premium_cal_p20': p20_cal,
        'nhi_premium_set_p20': p20_set,
        'nhi_disentitle_yn': dis_yn_,
        'nhi_disentitle_dur': dis_dur,
        'nhi_ceiling_amt': ceil_amt,
        'nhi_healthlevel': healthlevel,
        'nhi_highmedi_num': highmedi,
        'nhi_highbp_yn': chronic['nhi_highbp_yn'],
        'nhi_diabetes_yn': chronic['nhi_diabetes_yn'],
        'nhi_asthma_yn': chronic['nhi_asthma_yn'],
        'nhi_copd_yn': chronic['nhi_copd_yn'],
        'nhi_cardiac_yn': chronic['nhi_cardiac_yn'],
        'nhi_pregnant_yn': preg_yn,
        'nhi_pregnant_amt': preg_amt,
        'nhi_special1_yn': sp1, 'nhi_special2_yn': sp2, 'nhi_special3_yn': sp3,
        'nhi_special4_yn': sp4, 'nhi_special5_yn': sp5, 'nhi_special6_yn': sp6,
        'nhi_special7_yn': sp7,
        # ── 헬퍼 (코드북 변수 아님) ──
        '_nhi_care_yn': care_yn.astype(int),
        '_nhi_inp_yn': inp_yn.astype(int),
        '_nhi_special_any': spec_any.astype(int),
        '_nhi_ceiling_limit': ceil_amt,
        '_nhi_prem_p10': p10,
        '_no_p_minc': (nhi_type == 6).astype(int),
    }, index=df.index)

    # _amt 계열은 원 단위 정수 (NaN 보존 위해 float64 유지, 값은 정수)
    for c in ('nhi_premium_amt1_y', 'nhi_premium_amt3_y', 'nhi_premium_ltcare_amt1_y',
              'nhi_premium_ltcare_amt3_y', 'nhi_premium_cal', 'nhi_premium_set',
              'nhi_ceiling_amt', 'nhi_pregnant_amt', '_nhi_ceiling_limit'):
        out[c] = np.where(out[c].isna(), np.nan, np.round(out[c].to_numpy()))
    return out
