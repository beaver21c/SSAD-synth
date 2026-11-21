# -*- coding: utf-8 -*-
"""B01 개인·가구 골격 — pid, hid, head, gender, year, age, hnum  (A1 / order 1)

소스 (등급순):
  S2  통계청 2022 인구주택총조사(등록센서스) 보도자료 통계표 5 — 시도별 일반가구 가구원수별 가구
      params/raw/POPUL_CENSUS2022_보도자료_통계표.xls  [1차확인 2026-09-02]
      ※ 추출대상 "2022.11.1. 기준 일반가구"와 정의가 일치. KOSIS DT_1JC1502 와 동일 원천.
  S2  행정안전부 주민등록 인구통계 2022.11 — 시군구 × 1세 × 성별 인구
      params/tab/POP_2022_11_sigungu_age1_sex.csv (원본 POPUL_MOIS01_*.csv)  [1차확인]
      ※ KOSIS DT_1B040M1(연앙인구)의 동일 원천 행정집계. 기준시점이 2022.11.1로 코드북과 정확히 일치하여 우선 사용.
  S0  R01 <표 2-26>/<표 2-27>/<표 2-28>/<표 2-29> — 행정데이터 성·연령 분포, 가구규모 분포, 성·연령별 평균 가구원수
      params/tab/S0_R01_T2-2*.csv  [1차확인]  → 세대구성 템플릿 보정·검증 기준

생성 절차 (§6 B01):
  가구 우선 생성 → 시군구(B02 선행 아님: 여기서 함께 뽑고 B02가 코드·가중치 확정)
  → hnum(census 시도조건부) → 세대구성 템플릿 → 템플릿별 가구원 연령·성 생성
  → 성×5세×시도 IPF 1회(B02 가중치 단계에서 수행)
  year = 2022 − age − Bernoulli(0.17); 1922 이하 바텀코딩, 100세 이상 탑코딩
"""
from __future__ import annotations
import os, sys, json
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

RAW = 'params/raw'
TAB = 'params/tab'

# ── 세대구성 결합표(hnum × 세대구성) ─────────────────────────────────────────
# 2026-09-02 라운드 적용. 종전의 눈대중 확률([가정 A1-1])을 폐기하고 공표 결합표에
# **IPF 재적합한 값**으로 교체했다. 근거는 아래 4개 파일이며 본 파일에서 매 실행 시 재계산한다
# (하드코딩하지 않는다 — 원자료가 바뀌면 확률도 따라 바뀐다).
#   (1) params/raw/POPUL_HHPROJ_T11T12T13_hhsize_headage_type_2022.csv
#       장래가구추계 <표11·12·13> — 2·3·4인 가구의 가구유형 구성 (씨앗 교차표)
#   (2) params/raw/POPUL_HHPROJ_T2_hhtype_2022.csv   <표2> 가구유형별 주변분포 (열 제약)
#   (3) params/raw/POPUL_HHPROJ_T10_hhsize_2022.csv  <표10> 가구원수별 (잔차 검증)
#   (4) params/raw/POPUL_CENSUS2022_보도자료_통계표.xls 통계표5 (행 제약 — 실제 생성에 쓰는
#       가구원수 분포. 코드북 추출대상 "2022.11.1 일반가구"와 정의가 같으므로 <표10> 대신 사용)
#
# ★ 잔차 폐쇄 재검증 (2026-09-02 본 라운드에서 원자료를 직접 열어 재계산):
#     5인이상 행 = <표2> − (<표11·12·13> 2·3·4인)
#       부부 374.3−374.3 = 0.0 (부부는 정의상 2인 → 구조적 0)
#       부부+자녀 590.5−(296.5+253.3) = 40.7 · 부(모)+자녀 200.6−(137.3+55.5+7.2) = 0.6
#       3세대이상 68.0−(9.8+25.7) = 32.5 · 기타(친족+비친족) 194.2−(108.3+56.2+19.7) = 10.0
#       합계 = 83.8만 = <표10> 5인이상 83.8만  → **결합표가 모순 없이 닫힌다** [1차확인]
#     ※ <표11·12·13> 의 "기타" 열은 <표2> 의 기타(친족) 144.2 + 비친족 50.0 = 194.2 와 대응한다
#       (친족만으로 보면 144.2−184.2 = −40.0 으로 음수가 되어 닫히지 않는다 → 비친족 포함이 맞다).
#
# IPF: 행 제약 = 통계표5 가구원수 분포, 열 제약 = <표2> 세대구성 분포.
#   1인가구 열 ≡ hnum=1 행이므로 행 제약값(34.456%)을 그대로 쓰고 나머지 6열을 비례 재척도한다.
#   구조적 0(부부의 3인이상, 1인가구의 2인이상 등)은 씨앗의 0 이 IPF 에서 보존된다.
HHTYPES = ['single', 'couple', 'couple_child', 'oneparent_child',
           'threegen', 'couple_parent', 'grandparent_child', 'nonrel']

# 기타(친족) 144.2만 열의 **내부 배분** — 공표 자료에 세분이 없어 [가정 A1-9] 로 남긴다.
#   B01 의 세대구성 어휘에는 「기타(친족)」에 해당하는 항목이 couple_parent(부부+부모)와
#   grandparent_child(조손)뿐이다. 실제 기타(친족)에는 형제자매가구·부(모)+부모 등이 섞여 있으나
#   표현할 어휘가 없다. 배분 규칙:
#     · hnum ≥ 3 의 기타(친족) → 전부 couple_parent
#     · hnum = 2 의 기타(친족) → couple_parent 전국 비중이 OTHER_FAM_CP_SHARE 가 되도록 잔차 분할
#   근거 후보: 등록센서스 <표22> 친족가구 세대구분 잔차로 보면 기타(친족) 중 1세대형(형제자매 등)
#   43만 · 2세대형(부부+부모·조손 등) 100.7만 으로 갈리고 합이 143.7만 ≈ 144.2만 으로 닫힌다.
#   2세대형 제약(100.7만)을 쓰면 CP 비중 0.744, 종전 전국비 유지를 쓰면 0.546 이다.
#   ※ tools/validate.py 의 세대구성 주변분포 검사는 두 유형을 「기타(친족)」로 **묶어서** 대조하므로
#     이 배분값은 주변분포 적합도에 영향을 주지 않는다. 하류 소득·빈곤 분포에만 영향을 준다.
OTHER_FAM_CP_SHARE = 0.744


def _hhproj_cross():
    """장래가구추계 → hnum(1,2,3,4,'5+') × 세대구성 씨앗 교차표 (만가구)."""
    t2 = pd.read_csv(os.path.join(RAW, 'POPUL_HHPROJ_T2_hhtype_2022.csv'))
    t11 = pd.read_csv(os.path.join(RAW, 'POPUL_HHPROJ_T11T12T13_hhsize_headage_type_2022.csv'))
    t10 = pd.read_csv(os.path.join(RAW, 'POPUL_HHPROJ_T10_hhsize_2022.csv'))
    V = dict(zip(t2.hh_type.astype(str), t2.households_10k.astype(float)))
    col = {'single': V['one_person'], 'couple': V['couple'], 'couple_child': V['couple_child'],
           'oneparent_child': V['father_child'] + V['mother_child'], 'threegen': V['gen3_plus'],
           'other_fam': V['family_other'], 'nonrel': V['nonfamily']}
    ren = {'부부': 'couple', '부부+자녀': 'couple_child', '부(모)+자녀': 'oneparent_child',
           '3세대이상': 'threegen', '기타': 'other_all'}
    seed = {}
    for k in (2, 3, 4):
        sub = t11[(t11.hh_size == k) & (t11.dimension == 'hh_type')]
        m = {ren[c]: float(v) for c, v in zip(sub.category.astype(str), sub.households_10k)}
        seed[k] = {j: m.get(j, 0.0) for j in
                   ('couple', 'couple_child', 'oneparent_child', 'threegen', 'other_all')}
    seed[1] = {j: 0.0 for j in ('couple', 'couple_child', 'oneparent_child', 'threegen', 'other_all')}
    r5 = {'couple': col['couple'] - sum(seed[k]['couple'] for k in (2, 3, 4)),
          'couple_child': col['couple_child'] - sum(seed[k]['couple_child'] for k in (2, 3, 4)),
          'oneparent_child': col['oneparent_child'] - sum(seed[k]['oneparent_child'] for k in (2, 3, 4)),
          'threegen': col['threegen'] - sum(seed[k]['threegen'] for k in (2, 3, 4)),
          'other_all': (col['other_fam'] + col['nonrel']) - sum(seed[k]['other_all'] for k in (2, 3, 4))}
    resid = sum(r5.values())
    t10_5 = float(t10[t10.hh_size.astype(str) == '5+'].households_10k.iloc[0])
    if abs(resid - t10_5) > 0.15:            # 잔차 폐쇄 자기검증 (0.1만가구 = 반올림 오차 허용)
        raise ValueError(f'세대구성 잔차 폐쇄 실패: 5인이상 잔차 {resid:.2f} ≠ <표10> {t10_5:.2f}')
    seed['5+'] = r5
    seed[1]['single'] = col['single']
    for k in (2, 3, 4, '5+'):
        seed[k]['single'] = 0.0
    # other_all(기타+비친족) → nonrel / couple_parent / grandparent_child 로 분해
    tot_other = sum(seed[k]['other_all'] for k in (1, 2, 3, 4, '5+'))
    f_nr = col['nonrel'] / tot_other
    fam = {}
    for k in (1, 2, 3, 4, '5+'):
        o = seed[k].pop('other_all')
        seed[k]['nonrel'] = o * f_nr
        fam[k] = o * (1.0 - f_nr)
    cp_big = sum(fam[k] for k in (3, 4, '5+'))
    cp_all = col['other_fam'] * OTHER_FAM_CP_SHARE
    cp2 = min(max(cp_all - cp_big, 0.0), fam[2])
    for k in (1, 2, 3, 4, '5+'):
        seed[k]['couple_parent'] = fam[k] if k in (3, 4, '5+') else (cp2 if k == 2 else 0.0)
        seed[k]['grandparent_child'] = (fam[2] - cp2) if k == 2 else 0.0
    colv = {'single': col['single'], 'couple': col['couple'], 'couple_child': col['couple_child'],
            'oneparent_child': col['oneparent_child'], 'threegen': col['threegen'],
            'couple_parent': cp_big + cp2, 'grandparent_child': col['other_fam'] - (cp_big + cp2),
            'nonrel': col['nonrel']}
    return seed, colv


def _fit_templates(size_dist):
    """행=가구원수(등록센서스), 열=세대구성(<표2>) 두 주변분포에 씨앗 교차표를 IPF 적합.

    반환 {1,2,3,4,5,6: {hhtype: p}} — 5·6 은 같은 5인이상 조건부 분포(생성부는 min(k,6) 사용).
    """
    seed, colv = _hhproj_cross()
    rows = [1, 2, 3, 4, '5+']
    r_tgt = np.array([size_dist[1], size_dist[2], size_dist[3], size_dist[4],
                      sum(v for k, v in size_dist.items() if k >= 5)], float)
    r_tgt = r_tgt / r_tgt.sum()
    # 열 제약: 1인가구 열 = hnum=1 행 제약, 나머지 6열은 <표2> 비율로 잔여를 재척도
    ns = [j for j in HHTYPES if j != 'single']
    tot_ns = sum(colv[j] for j in ns)
    c_tgt = np.array([r_tgt[0]] + [colv[j] / tot_ns * (1.0 - r_tgt[0]) for j in ns], float)
    order = ['single'] + ns
    M = np.array([[seed[k].get(j, 0.0) for j in order] for k in rows], float)
    M = M / M.sum()
    for _ in range(400):
        rs = M.sum(1); M *= np.where(rs > 0, r_tgt / np.where(rs > 0, rs, 1), 1)[:, None]
        cs = M.sum(0); M *= np.where(cs > 0, c_tgt / np.where(cs > 0, cs, 1), 1)[None, :]
        if np.abs(M.sum(1) - r_tgt).max() < 1e-12 and np.abs(M.sum(0) - c_tgt).max() < 1e-12:
            break
    out = {}
    for i, k in enumerate(rows):
        row = M[i] / M[i].sum()
        d = {j: float(row[q]) for q, j in enumerate(order) if row[q] > 1e-9}
        if k == '5+':
            out[5] = d; out[6] = dict(d)
        else:
            out[k] = d
    return out


# ── 가구주 연령분포 [1차확인] ────────────────────────────────────────────────
# 2026-09-02 라운드 적용. 종전의 가우시안 성향가중([가정 A1-2])은 공표 가구주 연령분포와
# 최대 14.8%p 어긋났다(couple 40대 21.3 vs 6.5 · 70대 10.7 vs 22.9). 공표 밴드 비중에
# **밴드 내 전국 인구비례**를 곱해 1세 해상도로 복원한 분포로 교체한다.
#   single                        : POPUL_CENSUS_PR_T47_1person_hh_sex_age_2022.csv (등록센서스 <표47>)
#   couple · couple_child · oneparent_child
#                                 : POPUL_HHPROJ_T4T5T6_headage_by_hhtype_2022.csv (장래가구추계 <표4·5·6>)
# 공표 자료가 없는 4유형(couple_parent · threegen · grandparent_child · nonrel)은
# 종전 가우시안을 유지한다 → 지위 [가정 A1-2] 그대로.
_BAND = {'19세이하': (15, 19), '20-29세': (20, 29), '30-39세': (30, 39), '40-49세': (40, 49),
         '50-59세': (50, 59), '60-69세': (60, 69), '70-79세': (70, 79), '80세이상': (80, 100),
         '20대이하': (19, 29), '30대': (30, 39), '40대': (40, 49), '50대': (50, 59),
         '60대': (60, 69), '70대': (70, 79), '80대이상': (80, 100)}
HEAD_AGE_PRIOR = {   # (하한, 상한, 봉우리, 폭) — 공표자료 없는 유형에만 쓴다 [가정 A1-2]
    'couple_parent':     (35,  70, 52, 12),
    'threegen':          (35,  80, 56, 14),
    'grandparent_child': (55,  90, 68, 11),
    'nonrel':            (20,  85, 40, 18),
}


def _band_to_age_weights(bands, p_all, grid):
    """밴드 비중 → 밴드 내 전국 인구비례로 1세 해상도 복원."""
    w = np.zeros_like(grid, dtype=float)
    for b, share in bands.items():
        if b not in _BAND or share <= 0:
            continue
        lo, hi = _BAND[b]
        m = (grid >= lo) & (grid <= hi)
        base = p_all * m
        if base.sum() <= 0:
            base = m.astype(float)
        w += share * base / base.sum()
    return w / w.sum() if w.sum() > 0 else w


def _pub_head_age(p_all, grid):
    """공표 가구주 연령분포 → {hhtype: 1세 해상도 확률벡터}."""
    out = {}
    t = pd.read_csv(os.path.join(RAW, 'POPUL_HHPROJ_T4T5T6_headage_by_hhtype_2022.csv'))
    name = {'couple': 'couple', 'couple_child': 'couple_child', 'single_parent_child': 'oneparent_child'}
    for src, dst in name.items():
        sub = t[(t.hh_type.astype(str) == src) & (t.head_age_group.astype(str) != '계')]
        bands = {str(b): float(v) for b, v in zip(sub.head_age_group, sub.households_10k)}
        if bands:
            out[dst] = _band_to_age_weights(bands, p_all, grid)
    s = pd.read_csv(os.path.join(RAW, 'POPUL_CENSUS_PR_T47_1person_hh_sex_age_2022.csv'))
    sb = s[(s.sex.astype(str) == 'both') & (s.age_group.astype(str) != '계')]
    bands = {str(b): float(v) for b, v in zip(sb.age_group, sb.households)}
    if bands:
        out['single'] = _band_to_age_weights(bands, p_all, grid)
    return out


def _single_male_p(grid):
    """1인가구 가구주 남성 확률 — 연령 조건부 [1차확인, 등록센서스 <표47>].

    종전은 전 연령 0.50 고정이라 **고령 여성 1인가구를 구조적으로 과소생성**했다
    (실제 30대 남 63.4% / 70대 29.4% / 80세이상 18.9%).
    """
    s = pd.read_csv(os.path.join(RAW, 'POPUL_CENSUS_PR_T47_1person_hh_sex_age_2022.csv'))
    s = s[s.age_group.astype(str) != '계']
    m = s[s.sex == 'male'].set_index('age_group')['households'].astype(float)
    f = s[s.sex == 'female'].set_index('age_group')['households'].astype(float)
    p = np.full(len(grid), 0.5)
    for b in m.index:
        if b not in _BAND:
            continue
        lo, hi = _BAND[b]
        tot = float(m[b]) + float(f.get(b, 0.0))
        if tot > 0:
            p[(grid >= lo) & (grid <= hi)] = float(m[b]) / tot
    p[grid < 19] = float(m.iloc[0]) / (float(m.iloc[0]) + float(f.iloc[0])) if len(m) else 0.5
    return p


SPOUSE_GAP_MEAN, SPOUSE_GAP_SD = 3.0, 3.0     # 남편−아내 연령차 [가정 A1-3]
HETERO_P = 0.97                                # 이성 부부 비율 [가정 A1-3]
PARENT_CHILD_GAP_MEAN, PARENT_CHILD_GAP_SD = 31.0, 5.0   # 부모−자녀 연령차 [가정 A1-4]
GRAND_GAP_MEAN, GRAND_GAP_SD = 29.0, 5.0       # 조부모−부모 연령차 [가정 A1-4]
# ── [T1] 가족관계 연령 정합 · 한부모가구 가구주 세대 ─────────────────────────────
MIN_PARENT_GAP = 17            # 부모−자녀 최소 연령차 [가정 A1-6]
OP_FATHER_P = 0.20             # 가구주가 자녀 세대인 「부(모)+미혼자녀」 가구에서 부모가 부(父)일 확률
                               #   [1차확인] KOSIS 101/DT_1IN1509(2022) 65세 이상 부+미혼자녀 97,390 / (97,390 + 386,109)
OP_HEAD_CHILD_P_U50 = 0.40     # 가구주(50세 미만)가 자녀 세대일 확률 [논리적추론] DT_1IN1509 역산(개편지시서 T1)
OP_HEAD_CHILD_P_50_64 = 0.0    # 가구주(50~64세)가 자녀 세대일 확률 [논리적추론] 동상


def _p_head_is_child(ha):
    if ha < 50:
        return OP_HEAD_CHILD_P_U50
    if ha < 65:
        return OP_HEAD_CHILD_P_50_64
    return 0.0


# ── [T4] 가구 내 지위 조건부 소득 잠재변수 ──────────────────────────────────────
#  성×연령대 셀 안에서 _u_income 의 순위만 재배열한다(셀별 균등분포는 그대로 → 국세통계 성·연령
#  보유율·금액 분포는 보존). 정규점수에 아래 이동량을 더한 뒤 셀 안에서 다시 순위화한다.
#  [논리적추론] S0 R02 <표 4-7> 노인 가구유형별 빈곤율·R01 <표 2-39> 아동 빈곤율 역산(개편지시서 T4)
ROLE_TILT_MIX = -0.7           # 65세 이상과 동거하는 15~64세 가구원
ROLE_TILT_PARENT = 0.3         # 미성년 자녀와 사는 부부(부부+자녀·3세대 가구의 가구주·배우자)
ROLE_TILT_AGE_EDGES = (15, 30, 40, 50, 60, 70)


BIRTH_AFTER_NOV_P = 0.17                       # 11.1 이후 출생 보정 [지시서 §6 B01]


# ── 입력 로드 ────────────────────────────────────────────────────────────────
def _load_pop():
    p = pd.read_csv(os.path.join(RAW, 'POPUL_MOIS01_2022_11_sigungu_age1_sex.csv'))
    p = p[(p.level == 'sigungu') & (p.sex.isin(['male', 'female']))].copy()
    p['age'] = p['age'].astype(int)
    p['sido'] = p['sido'].astype(int)
    return p[['sigungu_code', 'sigungu_name', 'sido', 'sex', 'age', 'pop']]


def _load_hh():
    h = pd.read_csv(os.path.join(RAW, 'POPUL_MOIS02_2022_11_sigungu_hhsize.csv'))
    h = h[h.level == 'sigungu'].copy()
    h['sido'] = h['sido'].astype(int)
    return h


def _census_hhsize():
    """통계청 2022 등록센서스 통계표5: 전국 일반가구 가구원수별 (1,2,3,4,5+)."""
    d = pd.read_excel(os.path.join(RAW, 'POPUL_CENSUS2022_보도자료_통계표.xls'),
                      sheet_name='5.시도별 가구형태 및 가구원수별 가구', header=None)
    row = d[d[0].astype(str).str.replace(' ', '') == '전국'].iloc[0]
    total_general = float(row[2])
    sizes = {1: float(row[3]), 2: float(row[4]), 3: float(row[5]), 4: float(row[6]), 5: float(row[7])}
    return total_general, sizes


def _hhsize_dist():
    """가구원수 분포: census 1~4 + 5인이상. 5인이상 내부(5,6,7,8,9,10+) 세분은 주민등록 세대 분포 사용."""
    total, sizes = _census_hhsize()
    mois = _load_hh()
    big = mois[mois.hh_size.isin(['5', '6', '7', '8', '9', '10+'])]
    bshare = big.groupby('hh_size')['households'].sum()
    bshare = bshare / bshare.sum()
    dist = {k: sizes[k] / total for k in (1, 2, 3, 4)}
    p5 = sizes[5] / total
    for k in ('5', '6', '7', '8', '9', '10+'):
        dist[10 if k == '10+' else int(k)] = p5 * float(bshare.get(k, 0.0))
    s = sum(dist.values())
    return {k: v / s for k, v in dist.items()}, total


def _age_prior(pop):
    """전국 성×1세 인구 비율 (가구원 연령 추출의 기저분포)."""
    g = pop.groupby(['sex', 'age'])['pop'].sum().reset_index()
    g['p'] = g['pop'] / g['pop'].sum()
    return g


def _head_age_weights(tpl, ages):
    """공표자료가 없는 유형의 가우시안 성향가중 [가정 A1-2]."""
    lo, hi, peak, width = HEAD_AGE_PRIOR[tpl]
    w = np.exp(-0.5 * ((ages - peak) / width) ** 2)
    w = np.where((ages >= lo) & (ages <= hi), w, 0.0)
    return w


# ── 생성 ─────────────────────────────────────────────────────────────────────
def generate(df, params, ctx):
    g = core.rng('B01')
    n_hh = int(ctx.get('n_hh', 4200))
    n_cap = int(ctx.get('n_person_cap', 10000))

    pop = _load_pop()
    hh = _load_hh()
    size_dist, pop_hh_total = _hhsize_dist()
    ageprior = _age_prior(pop)

    # 1) 시군구 PPS 추출 (세대수 비례)
    sg = hh[hh.hh_size == 'total'][['sigungu_code', 'sigungu_name', 'sido', 'households']].copy()
    sg = sg[sg.households > 0].reset_index(drop=True)
    psg = sg.households.values / sg.households.values.sum()
    pick = g.choice(len(sg), size=n_hh, p=psg)
    hh_sigungu = sg.iloc[pick].reset_index(drop=True)

    # 2) 가구원수 (전국 census 분포; 표본이 작아 시도 조건부는 쓰지 않음 — 시도는 IPF로 보정)
    ks = np.array(sorted(size_dist)); ps = np.array([size_dist[k] for k in ks])
    hnum = g.choice(ks, size=n_hh, p=ps / ps.sum())
    # 개인 상한(≤10,000) 준수: 초과 시 큰 가구부터 줄이는 대신 가구수를 조정
    while hnum.sum() > n_cap:
        i = int(g.choice(np.flatnonzero(hnum == hnum.max())))
        hnum[i] -= 1

    # 3) 세대구성 템플릿 — 공표 결합표 IPF 재적합 [1차확인]
    templates = _fit_templates(size_dist)
    tpl = np.empty(n_hh, dtype=object)
    for k in np.unique(hnum):
        m = hnum == k
        tt = templates[min(int(k), 6)]
        names = list(tt); probs = np.array([tt[x] for x in names], float); probs /= probs.sum()
        tpl[m] = g.choice(names, size=int(m.sum()), p=probs)

    # 4) 가구원 연령·성 생성
    ages_grid = ageprior.age.values
    p_m = ageprior[ageprior.sex == 'male'].set_index('age')['p'].reindex(range(0, 101), fill_value=0).values
    p_f = ageprior[ageprior.sex == 'female'].set_index('age').reindex(range(0, 101))['p'].fillna(0).values
    p_all = p_m + p_f
    grid = np.arange(0, 101)

    pub_head = _pub_head_age(p_all, grid)      # 공표 가구주 연령분포 [1차확인]
    single_male_p = _single_male_p(grid)       # 1인가구 가구주 남성확률(연령별) [1차확인]

    def draw_head_age(t, n):
        if t in pub_head:
            return g.choice(grid, size=n, p=pub_head[t])
        w = _head_age_weights(t, grid) * p_all
        if w.sum() <= 0:
            w = _head_age_weights(t, grid)
        w = w / w.sum()
        return g.choice(grid, size=n, p=w)

    def clip_age(a): return np.clip(np.rint(a), 0, 100).astype(int)

    # ── [2026-09-02 최종검증 정정 (a)] 하한 절단(clip) → 절단정규(rejection sampling) ──
    # 정규 draw 를 np.clip 으로 하한에 가두면 하한 밖 확률질량이 **한 점에 쌓인다**.
    # 실측(주민등록 2022.11 대비 가중): age0 3.29배(+557,581) ↔ age1~4 0.39~0.68배(−557,075),
    # age15 1.45배(nonrel 의 max(a,15)). 10세 밴드 합계는 정확하므로 밴드 내부 배분만의 결함.
    # 상한 100 은 지시서 §6 B01 의 "100세 이상 탑코딩"이라 그대로 둔다.
    def _tnorm_lo(mu, sd, lo, hi, tries=16):
        for _ in range(tries):
            a = int(round(g.normal(mu, sd)))
            if lo <= a <= hi:
                return a
        return int(g.integers(lo, hi + 1))

    rows = []
    for i in range(n_hh):
        k, t = int(hnum[i]), tpl[i]
        ha = int(draw_head_age(t, 1)[0])
        # 가구주 성별: 템플릿별 [가정 A1-5] — 단 1인가구는 **연령 조건부 공표값** [1차확인]
        hsex_p = {'single': 0.50, 'couple': 0.86, 'couple_child': 0.90, 'oneparent_child': 0.30,
                  'couple_parent': 0.85, 'threegen': 0.75, 'grandparent_child': 0.45, 'nonrel': 0.60}[t]
        if t == 'single':
            hsex_p = float(single_male_p[ha])
        hsex = 1 if g.random() < hsex_p else 2
        mem = [(ha, hsex, 1, 'head')]

        def add_spouse(base_age, base_sex):
            gap = g.normal(SPOUSE_GAP_MEAN, SPOUSE_GAP_SD)
            sx = (2 if base_sex == 1 else 1) if g.random() < HETERO_P else base_sex
            a = base_age - gap if base_sex == 1 else base_age + gap
            return (int(np.clip(round(a), 19, 100)), sx, 2, 'spouse')

        def add_child(parent_age, n_child, cap_age=None):
            # [T1-a] 자녀 연령 상한 = (부모 중 연소자 연령 − MIN_PARENT_GAP). 절단정규 실패 시의
            #        폴백 균등추출이 부모 연령을 넘지 않게 한다(종전 상한 60 → 자녀가 가구주보다 연상).
            out = []
            hi_c = int(max(0, min(60, (parent_age if cap_age is None else min(parent_age, cap_age)) - MIN_PARENT_GAP)))
            for j in range(n_child):
                a = _tnorm_lo(parent_age - (PARENT_CHILD_GAP_MEAN + 3.0 * j),
                              PARENT_CHILD_GAP_SD, 0, hi_c)
                out.append((a, 1 if g.random() < 0.512 else 2, 2, 'child'))
            return out

        if t == 'single':
            pass
        elif t == 'couple':
            mem.append(add_spouse(ha, hsex))
        elif t == 'couple_child':
            mem.append(add_spouse(ha, hsex)); mem += add_child(ha, k - 2, mem[-1][0])
        elif t == 'oneparent_child':
            # [T1-b] 「부(모)+미혼자녀」 가구의 가구주는 부모일 수도, 자녀일 수도 있다.
            if g.random() < _p_head_is_child(ha):
                a_p = int(np.clip(round(ha + g.normal(PARENT_CHILD_GAP_MEAN, PARENT_CHILD_GAP_SD)),
                                  ha + MIN_PARENT_GAP, 100))
                mem.append((a_p, 1 if g.random() < OP_FATHER_P else 2, 2, 'parent'))
                for j in range(k - 2):                       # 가구주의 미혼 형제자매
                    a = int(np.clip(round(ha + g.normal(0.0, 4.0)), 15, max(15, a_p - MIN_PARENT_GAP)))
                    mem.append((a, 1 if g.random() < 0.512 else 2, 2, 'other'))
            else:
                mem += add_child(ha, k - 1)
        elif t == 'grandparent_child':
            for j in range(k - 1):
                a = _tnorm_lo(ha - 2 * GRAND_GAP_MEAN, 6, 0, 40)
                mem.append((a, 1 if g.random() < 0.512 else 2, 2, 'grandchild'))
        elif t == 'couple_parent':
            # 기타(친족) 열에서 배정되므로 2인 가구가 올 수 있다. 종전 코드는 k=2 일 때
            # range(k-2) 가 비어 **부모가 0명인 사실상 부부가구**로 축퇴했다 → 2인은
            # 「가구주+부모 1인」(2세대 2인 친족가구)으로 만든다. [논리적추론]
            n_par = max(1, k - 2) if k == 2 else (k - 2)
            if k > 2:
                mem.append(add_spouse(ha, hsex))
            for j in range(n_par):
                a = int(np.clip(round(ha + g.normal(GRAND_GAP_MEAN, 5)), 55, 100))
                mem.append((a, 1 if g.random() < 0.35 else 2, 2, 'parent'))
        elif t == 'threegen':
            mem.append(add_spouse(ha, hsex))
            a_p = int(np.clip(round(ha + g.normal(GRAND_GAP_MEAN, 5)), 55, 100))
            mem.append((a_p, 1 if g.random() < 0.35 else 2, 2, 'parent'))
            mem += add_child(ha, max(0, k - 3), mem[1][0])   # [T1-c] 배우자 연령도 상한에 반영
        else:  # nonrel
            # 비친족 가구원은 15세 이상. max(a,15) 는 15세에 질량을 쌓으므로
            # 15세 이상으로 제한한 국가 연령분포를 재정규화해 추출한다. [최종검증 정정 (a)]
            p_nr = np.where(grid >= 15, p_all, 0.0); p_nr = p_nr / p_nr.sum()
            for j in range(k - 1):
                a = int(g.choice(grid, p=p_nr))
                mem.append((a, 1 if g.random() < 0.5 else 2, 2, 'nonrel'))
        # 가구원 수 맞추기
        while len(mem) > k: mem.pop()
        while len(mem) < k:
            a = int(g.choice(grid, p=(p_all / p_all.sum())))
            mem.append((a, 1 if g.random() < 0.5 else 2, 2, 'other'))
        for (a, sx, hd, role) in mem:
            rows.append((i, a, sx, hd, role, t, k))

    d = pd.DataFrame(rows, columns=['_hh', 'age', 'gender', 'head', '_role', '_hhtype', 'hnum'])

    # 5) 식별자·출생년도·코딩 (§6 B01)
    hid_pool = g.choice(np.arange(10_000_000, 99_999_999), size=n_hh, replace=False)
    d['hid'] = hid_pool[d['_hh'].values]
    pid_pool = g.choice(np.arange(100_000_000, 999_999_999), size=len(d), replace=False)
    d['pid'] = pid_pool
    d['age'] = np.clip(d['age'].astype(int), 0, 100)                      # 100세 이상 탑코딩
    d['year'] = 2022 - d['age'] - core.bernoulli(g, np.full(len(d), BIRTH_AFTER_NOV_P))
    d.loc[d['year'] < 1922, 'year'] = 1922                                # 1922년 이하 바텀코딩
    d['hnum'] = d.groupby('hid')['hid'].transform('size').astype(int)     # R23: hnum = 실제 행수

    # 6) 지역 (B02가 city/sido 코드를 확정하지만 골격 단계에서 결정해 둔다)
    d['_sigungu_code'] = hh_sigungu.sigungu_code.values[d['_hh'].values]
    d['_sigungu_name'] = hh_sigungu.sigungu_name.values[d['_hh'].values]
    d['_sido'] = hh_sigungu.sido.values[d['_hh'].values]

    # 7) 개인 잠재변수 (전 블록 공유, §4.1)
    lat = core.latent(len(d))
    for k, v in lat.items():
        d[f'_{k}'] = v

    # 8) 가구 파생 (하위 블록 조건에 쓰임)
    d = d.sort_values(['hid', 'head', 'age'], ascending=[True, True, False]).reset_index(drop=True)
    # `_spouse_age` = **그 사람 본인의 배우자 연령** (registry/column_contract.md: "없으면 NaN").
    # 종전 구현은 가구 단위 map 이라 자녀·부모 행에까지 배우자 연령이 붙어 있었다(2,140행).
    # 그 결과 B27 `has_spouse`(disp_type)·B33 `has_sp`(ltcare_caregiver_type=배우자) 의
    # "배우자 존재" 판정이 과대해져, 배우자가 없는 사람이 배우자수발 10명·부부1인 5명으로 잡혔다.
    # B01 의 가구 템플릿상 부부는 head↔spouse 짝뿐이므로(부모 역할은 가구당 1명, 부부 아님)
    # 두 역할에만 부여한다. §7 R02 는 head/spouse 행에서만 발동하므로 판정은 불변이다.
    sp = d[d['_role'] == 'spouse'].set_index('hid')['age']
    hd = d[d['_role'] == 'head'].set_index('hid')['age']
    is_h, is_s = (d['_role'] == 'head'), (d['_role'] == 'spouse')
    d['_spouse_age'] = np.nan
    d.loc[is_h, '_spouse_age'] = d.loc[is_h, 'hid'].map(sp).to_numpy()
    d.loc[is_s, '_spouse_age'] = d.loc[is_s, 'hid'].map(hd).to_numpy()
    d['_n_child_0_8'] = d.groupby('hid')['age'].transform(lambda s: int(((s >= 0) & (s <= 8)).sum()))
    d['_has_child_0_8'] = (d['_n_child_0_8'] > 0).astype(int)
    d['_n_child_u18'] = d.groupby('hid')['age'].transform(lambda s: int((s < 18).sum()))
    d['_is_single_parent'] = (d['_hhtype'] == 'oneparent_child').astype(int)
    d['_hh_pop_total'] = pop_hh_total

    # [T4-a] 소득 잠재변수의 가구 내 지위 조건부화 (상수 주석 참조)
    if ROLE_TILT_MIX or ROLE_TILT_PARENT:
        from scipy.stats import norm as _norm
        _age = d['age'].to_numpy(); _role = d['_role'].to_numpy()
        _n65 = d.groupby('hid')['age'].transform(lambda s: int((s >= 65).sum())).to_numpy()
        _mix = (_n65 > 0) & (_n65 < d['hnum'].to_numpy()) & (_age >= 15) & (_age < 65)
        _par = (np.isin(_role, ['head', 'spouse']) & (d['_n_child_u18'].to_numpy() > 0)
                & np.isin(d['_hhtype'].to_numpy(), ['couple_child', 'threegen']))
        _z = _norm.ppf(np.clip(d['_u_income'].to_numpy(), 1e-6, 1 - 1e-6))
        _z = _z + ROLE_TILT_MIX * _mix + ROLE_TILT_PARENT * _par
        _key = d['gender'].to_numpy() * 10 + np.digitize(_age, ROLE_TILT_AGE_EDGES)
        _rk = pd.Series(_z).groupby(_key).rank(method='first')
        _cnt = pd.Series(_z).groupby(_key).transform('size')
        d['_u_income'] = ((_rk - 0.5) / _cnt).to_numpy()

    return d[['pid', 'hid', 'head', 'gender', 'year', 'age', 'hnum',
              '_hh', '_role', '_hhtype', '_sigungu_code', '_sigungu_name', '_sido',
              '_spouse_age', '_n_child_0_8', '_has_child_0_8', '_n_child_u18',
              '_is_single_parent', '_hh_pop_total',
              '_u_income', '_u_health', '_u_welfare', '_u_emp']]
