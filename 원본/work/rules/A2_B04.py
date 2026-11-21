# -*- coding: utf-8 -*-
"""B04 공적이전소득 49개 · 소득 합계 · 세금 · 사회보험료 (A2 / order 9 / 73변수)

**생성 블록이 아니라 합산 블록**이다. 상위 블록이 만든 급여·보험료 `*_amt` 를 복사해
`p_*_amt` 를 채우고, 개인·가구 소득 집계를 계산한다.

────────────────────────────────────────────────────────────────────────────
합산식 근거 (모두 [1차확인])
  1) 코드북 `registry/codebook.json` 의 org="추출 정보 가공" 그룹 (2026-09-02 확인)
       program='개인 일차소득'   → p_labinc, p_dainc, p_binc, p_fininc, p_reinc, p_pripeninc, p_othinc (7)
       program='개인 공적이전소득' → p_*_amt (49)
       program='개인 세금'        → p_tax_inc, p_ptax_sum (2)
       program='개인 사회보험료'   → p_*_premium* (10)
       program='개인 소득'        → p_minc="개인 일차소득 항목 합산" / p_pubinc="개인 공적이전소득 항목 합산"
                                   p_tax="개인 세금 항목 합산" / p_soin_amt="개인 사회보험료 항목 합산"
                                   p_oinc="일차소득+공적이전소득" / p_dinc="경상소득-세금-사회보험료"
       program='가구 소득'        → h_* = "개인 …을 가구 내에서 합산한 금액"
     → 지시서가 "[가정]"으로 두라고 한 p_dinc 식은 **코드북 본문에 명시**되어 있어 1차확인으로 승격.
  2) S0 R01 <표 2-38>·<표 2-39> 주2 (p.94·p.95, 2026-09-02 열람):
       · 일차소득: 근로소득+사업소득+부동산소득+일용소득+기타소득
       · 가처분소득: 일차소득+공적이전소득-소득세·재산세·국민연금 보험료·건강보험료·고용보험료
     3기(2022) 코드북은 여기에 금융소득·사적연금소득(일차소득)과 직역연금 보험료·장기요양보험료
     (사회보험료)를 추가로 포함한다 → 코드북 그룹을 우선 적용.
  3) 각 p_*_amt 의 코드북 변수 내용이 "XXX_amt 변수와 동일" 이라고 명시 → 단순 복사가 규정된 규칙.

pubpen_inc / pubpen_tax (B10 소관, 미구현 시 여기서 생성 — column_contract 상위컬럼 수정 금지 대응)
  · pubpen_inc  = 공적연금 5종 정기연금 급여 합 (국세청 공적연금DB "총연금수령액")
  · pubpen_tax  = 소득세법(2022 귀속) 연금소득 세액계산 + 지방소득세 10%
      과세연금액 비율은 S1 국세청 국세통계 4-3-3(2022 귀속) 총연금수령액 규모별 실측값 사용
      params/tab/NTS_4-3-3_공적연금_연말정산_총연금수령액규모별_2022.csv [1차확인 2026-09-02]
  · df 에 이미 있으면 **만들지 않는다** (B10 이 만들면 그쪽이 우선).
  · ★2026-09-02 현재 상태: rules/A2_B10.py 가 `PUBPEN_MODE_DEFAULT='nan'` 으로 두 컬럼을
    **전량 NaN 으로 생성**하고 있어, 러너의 상위컬럼 수정 금지 때문에 B04 가 값을 채우지 못한다.
    → B10 의 `PUBPEN_MODE_DEFAULT` 를 'skip' 으로 바꾸면(또는 두 줄을 삭제하면) B04 가 즉시
      값을 만든다. 임시 확인용: `pipeline.run(ctx_extra={'b10_pubpen':'skip'})`.
      (tools/pipeline.py __main__ · tools/export_final.py 는 ctx_extra 를 넘기지 않으므로
       최종 산출물에서는 ctx 우회가 통하지 않는다 — B10 수정이 유일한 해법이다.)

미구현 선행 블록 폴백
  · 소스 컬럼이 없으면 해당 p_*_amt = 0 (코드북 추출대상 "무정보 사례 0원 처리"에 부합).
  · p_minc 7개 성분(B03)이 없으면 국세청 원천 DB 컬럼(B07~B11)으로 성분을 재구성한다.

p_tax_inc ↔ p_minc 정합화 (2026-09-02 추가 · column_contract.md C4)
  · p_minc ≤ 0 인 사람의 p_tax_inc 는 공적연금 세액(pubpen_tax)만 남긴다. 상세 근거는 generate() 3-b) 주석.
  · 원천 DB 세액 컬럼과 재산세는 손대지 않는다 → S1 국세통계 총량 목표 4건 불변.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import core

TAB = 'params/tab'
MISSING = -99999999          # 코드북 결측코드 (diswork_rehab_amt 등)

# ── 49개 공적이전소득: p_변수 → 원천 변수 (코드북 "XXX_amt 변수와 동일") ──────
PUBINC = {
    'p_np_pension_amt': 'np_pension_amt',
    'p_govp_pension_amt': 'govp_pension_amt',
    'p_privschp_pension_amt': 'privschp_pension_amt',
    'p_milip_pension_amt': 'milip_pension_amt',
    'p_postp_pension_amt': 'postp_pension_amt',
    'p_unempbn_jobseekbn_amt': 'unempbn_jobseekbn_amt',
    'p_unempbn_sicknessbn_amt': 'unempbn_sicknessbn_amt',
    'p_unempbn_indivbn_amt': 'unempbn_indivbn_amt',
    'p_unempbn_early_amt': 'unempbn_early_amt',
    'p_unempbn_etc_amt': 'unempbn_etc_amt',
    'p_empins_matleave_amt': 'empins_matleave_amt',
    'p_empins_spouseleave_amt': 'empins_spouseleave_amt',
    'p_empins_parentleave_amt': 'empins_parentleave_amt',
    'p_empins_postleave_amt': 'empins_postleave_amt',
    'p_empins_shorthrs_amt': 'empins_shorthrs_amt',
    'p_empins_uninsureleave_amt': 'empins_uninsureleave_amt',
    'p_occupins_pension_amt': 'occupins_pension_amt',
    'p_kua_jobseekbn_amt': 'kua_jobseekbn_amt',
    'p_kua_employmentbn_amt': 'kua_employmentbn_amt',
    'p_kua_jobseekact_amt': 'kua_jobseekact_amt',
    'p_disemp_package_amt1': 'disemp_package_amt1',
    'p_disemp_package_amt2': 'disemp_package_amt2',
    'p_disemp_package_amt3': 'disemp_package_amt3',
    'p_disemp_employsupport_amt': 'disemp_employsupport_amt',
    'p_disemp_employment_amt': 'disemp_employment_amt',
    'p_diswork_rehab_amt': 'diswork_rehab_amt',
    'p_vetbn_r_amt': 'vetbn_r_amt',
    'p_nbls_live_amt': 'nbls_live_amt',
    'p_nbls_house_amt': 'nbls_house_amt',
    'p_aid_live_amt': 'aid_live_amt',
    'p_aid_house_amt': 'aid_house_amt',
    'p_nbls_edu_amt1': 'nbls_edu_amt1',
    'p_aid_edu_amt': 'aid_edu_amt',
    'p_bp_amt': 'bp_amt',
    'p_disp_amt': 'disp_amt',
    'p_disp_bn_amt': 'disp_bn_amt',
    'p_disp_bn_child_amt': 'disp_bn_child_amt',
    'p_childbn_amt': 'childbn_amt',
    'p_carebn_amt': 'carebn_amt',
    'p_carebn_dischild_amt': 'carebn_dischild_amt',
    'p_carebn_rural_amt': 'carebn_rural_amt',
    'p_infantbn_amt': 'infantbn_amt',
    'p_single_rear_amt': 'single_rear_amt',
    'p_single_extra_amt': 'single_extra_amt',
    'p_single_edu_amt': 'single_edu_amt',
    'p_single_youth_rear_amt': 'single_youth_rear_amt',
    'p_single_youth_self_amt': 'single_youth_self_amt',
    'p_itc_amt': 'itc_amt',
    'p_itc_child_amt': 'itc_child_amt',
}

# ── 10개 사회보험료 ───────────────────────────────────────────────────────────
SOIN = {
    'p_np_premium_amt2': 'np_premium_amt2',
    'p_govp_premium_amt': 'govp_premium_amt',
    'p_privschp_premium_amt': 'privschp_premium_amt',
    'p_milp_premium_amt': 'milp_premium_amt',
    'p_postp_premium_amt': 'postp_premium_amt',
    'p_nhi_premium_amt1_y': 'nhi_premium_amt1_y',
    'p_nhi_premium_amt3_y': 'nhi_premium_amt3_y',
    'p_nhi_premium_ltcare_amt1_y': 'nhi_premium_ltcare_amt1_y',
    'p_nhi_premium_ltcare_amt3_y': 'nhi_premium_ltcare_amt3_y',
    'p_empins_premium_amt': 'empins_premium_amt',
}

# ── 7개 일차소득 성분: 1순위 B03 산출 컬럼 / 2순위 국세청 원천 DB 합 (폴백) ─────
MINC = ['p_labinc', 'p_dainc', 'p_binc', 'p_fininc', 'p_reinc', 'p_pripeninc', 'p_othinc']
MINC_FALLBACK = {
    'p_labinc':    ['labinc_sum_taxy', 'labinc_sum_taxn'],       # 연말정산 근로소득DB
    'p_dainc':     ['dainc_sum', 'dainc_taxfree'],               # 일용소득
    'p_binc':      ['binc_sum', 'ybinc_sum'],                    # 원천징수·연말정산 사업소득
    'p_fininc':    ['fainc_sum'],                                # 금융소득DB
    'p_reinc':     ['inc_reinc_sum', 'inc_hou_sum', 'inc_sehou_sum'],   # 종합소득 부동산·임대
    'p_pripeninc': ['pripen_inc'],                               # 사적연금DB
    'p_othinc':    ['othinc_sum'],                               # 기타소득DB
}

# ── 소득세 총액(p_tax_inc) 구성 ───────────────────────────────────────────────
# 소득세법 §76(기납부세액 공제): 종합소득 확정신고자의 **종합과세 결정세액**(inc_total_*)에는
# 그 신고서에 합산 신고된 소득의 원천징수·연말정산 세액이 이미 반영돼 있다.
# 따라서 결정세액을 쓰는 사람에게는 **합산된 소득유형의 원천세액을 중복 계상하지 않는다**.
# 합산 여부는 종합소득 신고서 명세 컬럼(코드북 inc_* 소득구분코드 기준)의 존재로 판정한다.
TAX_SEPARATE = ['dainc_tax1', 'dainc_tax2']          # 일용소득: 완납적 분리과세 — 항상 가산
TAX_CREDITABLE = [                                   # (종합소득 신고서 명세, 기납부세액)
    # inc_labinc_sum = [별지40호(1)] (8)근로소득·연금소득·기타소득명세서 소득구분코드 51~58 총수입금액
    (['inc_labinc_sum'], ['labinc_inc_taxamt', 'labinc_residence_taxamt', 'labinc_rural_taxamt']),
    # inc_inter/inc_allo = 종합과세 이자·배당소득금액 (2천만원 초과분 종합과세)
    (['inc_inter', 'inc_allo'], ['fainc_tax']),
    # inc_pens_sum = 종합과세 연금소득 총수입금액 (소득구분코드 66)
    (['inc_pens_sum'], ['pripen_inctax', 'pripen_localtax']),
]
TAX_SETTLED = ['inc_total_tax', 'inc_total_setax', 'inc_total_ruraltax']   # 종합소득 결정세액
TAX_WITHHELD = ['binc_inctax', 'binc_localtax',
                'ybinc_inctax', 'ybinc_localtax', 'ybinc_ruraltax',
                'othinc_inctax', 'othinc_localtax', 'othinc_ruraltax']

# ── 검증용 항목군 (R01 <표 2-36>·<표 2-37>) — 밑줄 헬퍼, 최종 산출 제외 ────────
GRP_PENSION = ['p_np_pension_amt', 'p_govp_pension_amt', 'p_privschp_pension_amt',
               'p_milip_pension_amt', 'p_postp_pension_amt']
GRP_DIS = ['p_disp_amt', 'p_disp_bn_amt', 'p_disp_bn_child_amt']
GRP_ITC = ['p_itc_amt', 'p_itc_child_amt']
GRP_EMPOCC = ['p_unempbn_jobseekbn_amt', 'p_unempbn_sicknessbn_amt', 'p_unempbn_indivbn_amt',
              'p_unempbn_early_amt', 'p_unempbn_etc_amt', 'p_empins_matleave_amt',
              'p_empins_spouseleave_amt', 'p_empins_parentleave_amt', 'p_empins_postleave_amt',
              'p_empins_shorthrs_amt', 'p_empins_uninsureleave_amt', 'p_occupins_pension_amt']
GRP_NBLS = ['p_nbls_live_amt', 'p_nbls_house_amt']                     # R01 표2-37 주2 (자활장려금 제외)
GRP_CHILD = ['p_childbn_amt', 'p_carebn_amt', 'p_carebn_dischild_amt', 'p_carebn_rural_amt',
             'p_infantbn_amt', 'p_single_rear_amt', 'p_single_extra_amt', 'p_single_edu_amt',
             'p_single_youth_rear_amt', 'p_single_youth_self_amt']     # R01 표2-37 주3 + 영아수당(2022 신설)

# ── 소득세법(2022 귀속) 파라미터 [S4 법령] ────────────────────────────────────
#  §47조의2 연금소득공제 / §50 기본공제(본인) / §55 기본세율 / §59조의4⑨ 표준세액공제
#  지방세법 §92 개인지방소득세 = 소득세액 × 10%
BRACKETS = [(12_000_000, 0.06, 0), (46_000_000, 0.15, 1_080_000),
            (88_000_000, 0.24, 5_220_000), (150_000_000, 0.35, 14_900_000),
            (300_000_000, 0.38, 19_400_000), (500_000_000, 0.40, 25_400_000),
            (1_000_000_000, 0.42, 35_400_000), (np.inf, 0.45, 65_400_000)]
BASIC_DEDUCT = 1_500_000        # 본인 기본공제
STD_TAXCREDIT = 70_000          # 표준세액공제 (근로소득 없는 종합소득자)
LOCAL_RATE = 0.10               # 개인지방소득세


# ── 유틸 ─────────────────────────────────────────────────────────────────────
def _s(df, col):
    """소스 컬럼 → float Series. 없으면 None. 결측코드·NaN 은 0."""
    if col not in df.columns:
        return None
    v = pd.to_numeric(df[col], errors='coerce')
    v = v.where(v > MISSING, np.nan)
    return v.fillna(0.0).astype(float)


def _s0(df, col):
    v = _s(df, col)
    return v if v is not None else pd.Series(0.0, index=df.index)


def _pension_deduction(x):
    """소득세법 §47조의2 연금소득공제 (한도 900만원)."""
    x = np.asarray(x, float)
    d = np.where(x <= 3_500_000, x,
        np.where(x <= 7_000_000, 3_500_000 + (x - 3_500_000) * 0.40,
        np.where(x <= 14_000_000, 4_900_000 + (x - 7_000_000) * 0.20,
                                  6_300_000 + (x - 14_000_000) * 0.10)))
    return np.minimum(np.maximum(d, 0.0), 9_000_000)


def _income_tax(base):
    """소득세법 §55 기본세율 (2022 귀속) 산출세액."""
    base = np.asarray(base, float)
    out = np.zeros_like(base)
    prev = 0.0
    for hi, rate, ded in BRACKETS:
        m = (base > prev) & (base <= hi)
        out[m] = base[m] * rate - ded
        prev = hi
    return np.maximum(out, 0.0)


def _taxable_ratio_table():
    """S1 국세청 4-3-3: 총연금수령액 구간별 과세연금액 비율 [1차확인]."""
    f = os.path.join(TAB, 'NTS_4-3-3_공적연금_연말정산_총연금수령액규모별_2022.csv')
    t = pd.read_csv(f)
    t = t[t.lo_won.notna()].copy()
    t['hi_won'] = t['hi_won'].fillna(np.inf)
    return t[['lo_won', 'hi_won', 'taxable_ratio']].reset_index(drop=True)


def _pubpen_tax(gross):
    """공적연금 총연금수령액 → 소득세+지방소득세 결정세액 (원)."""
    t = _taxable_ratio_table()
    g = np.asarray(gross, float)
    ratio = np.full(g.shape, float(t.taxable_ratio.iloc[-1]))
    for _, r in t.iterrows():
        m = (g >= r.lo_won) & (g < r.hi_won)
        ratio[m] = float(r.taxable_ratio)
    taxable = g * ratio                                   # 총연금액(과세연금액)
    pen_income = np.maximum(taxable - _pension_deduction(taxable), 0.0)   # 연금소득금액
    base = np.maximum(pen_income - BASIC_DEDUCT, 0.0)                     # 과세표준
    inc_tax = np.maximum(_income_tax(base) - STD_TAXCREDIT, 0.0)          # 소득세 결정세액
    return inc_tax * (1.0 + LOCAL_RATE)                                   # +개인지방소득세


# ── 생성 ─────────────────────────────────────────────────────────────────────
def generate(df, params, ctx):
    core.rng('B04')          # 난수 미사용(결정론적 합산)이나 규약상 블록 시드 확보
    out = pd.DataFrame(index=df.index)
    trace = {'missing_src': [], 'minc_fallback': [], 'created': []}

    # 0) pubpen_inc / pubpen_tax — B10 이 만들지 않았을 때만 B04 가 만든다.
    pen_sum = pd.Series(0.0, index=df.index)
    for c in ('np_pension_amt', 'govp_pension_amt', 'privschp_pension_amt',
              'milip_pension_amt', 'postp_pension_amt'):
        pen_sum = pen_sum + _s0(df, c)
    if 'pubpen_inc' in df.columns:
        pubpen_inc = pd.to_numeric(df['pubpen_inc'], errors='coerce')
    else:
        pubpen_inc = pen_sum.where(pen_sum > 0, np.nan)      # 추출대상: 소득이 존재하는 집단
        out['pubpen_inc'] = np.rint(pubpen_inc).astype('float64')   # NaN 보존 위해 float(정수값)
        trace['created'].append('pubpen_inc')
    if 'pubpen_tax' in df.columns:
        pubpen_tax = pd.to_numeric(df['pubpen_tax'], errors='coerce')
    else:
        tx = pd.Series(_pubpen_tax(pubpen_inc.fillna(0.0).values), index=df.index)
        pubpen_tax = tx.where(tx > 0, np.nan)                # 추출대상: 세금이 존재하는 집단
        out['pubpen_tax'] = np.rint(pubpen_tax).astype('float64')   # NaN 보존 위해 float(정수값)
        trace['created'].append('pubpen_tax')

    # 1) 49개 공적이전소득 + 10개 사회보험료 + 재산세 = 원천 변수 복사 (없으면 0)
    for tgt, src in list(PUBINC.items()) + list(SOIN.items()) + [('p_ptax_sum', 'ptax_sum')]:
        v = _s(df, src)
        if v is None:
            v = pd.Series(0.0, index=df.index)
            trace['missing_src'].append(src)
        out[tgt] = np.rint(v).astype('int64')

    # 2) 소득세 총액 p_tax_inc
    #    종합소득 확정신고자는 결정세액(inc_total_*)에 원천징수분이 이미 반영되므로
    #    사업·기타소득 원천징수세액을 중복 계상하지 않는다 (소득세법 §76 기납부세액 공제).
    settled = sum((_s0(df, c) for c in TAX_SETTLED), pd.Series(0.0, index=df.index))
    withheld = sum((_s0(df, c) for c in TAX_WITHHELD), pd.Series(0.0, index=df.index))
    is_settled = settled > 0                       # 종합소득 확정신고자(결정세액 보유)
    base = sum((_s0(df, c) for c in TAX_SEPARATE), pd.Series(0.0, index=df.index))
    for inc_cols, tax_cols in TAX_CREDITABLE:      # 합산신고분은 기납부세액 → 제외
        inc = sum((_s0(df, c) for c in inc_cols), pd.Series(0.0, index=df.index))
        tax = sum((_s0(df, c) for c in tax_cols), pd.Series(0.0, index=df.index))
        base = base + tax.where(~(is_settled & (inc > 0)), 0.0)
    comp = settled.where(is_settled, withheld)
    inc_pens = _s0(df, 'inc_pens_sum')             # 공적연금도 종합과세되면 결정세액에 포함
    ppt = pubpen_tax.fillna(0.0).where(~(is_settled & (inc_pens > 0)), 0.0)
    tax_inc = base + comp + ppt

    # 3) 개인 일차소득 7성분 → p_minc
    minc = pd.Series(0.0, index=df.index)
    for c in MINC:
        v = _s(df, c)
        if v is None:                                    # B03 미구현 → 국세청 원천 DB 로 재구성
            v = pd.Series(0.0, index=df.index)
            got = [s for s in MINC_FALLBACK[c] if s in df.columns]
            for s in got:
                v = v + _s0(df, s)
            trace['minc_fallback'].append(f'{c}<-{got or "0"}')
        minc = minc + v
    out['p_minc'] = np.rint(minc).astype('int64')

    # 3-b) ★ p_tax_inc ↔ p_minc 정합화 (column_contract.md C4 / 2026-09-02)
    #  문제: 위 2)는 p_tax_inc 를 **국세청 원천 DB 세액 컬럼**에서 만들고, p_minc 는
    #        **B03 이 §7 R16(nhi_type=6 ⇒ 무소득)을 적용해 0 으로 만든 p_* 성분**에서 만든다.
    #        두 계열이 분리돼 있어 "일차소득 0원인데 소득세를 낸다"는 사람이 생긴다
    #        (수정 전 실측 1,985행 / 가중 3.78조 = 전국 소득세의 3.31%).
    #        §7 어느 규칙도 이 축을 규정하지 않아 위반 0건인 채로 남아 있었다.
    #  근거: 코드북에서 p_tax_inc 는 p_labinc…p_dinc 와 같은 org="추출 정보 가공" ·
    #        "<이용자 가이드> 소득 구성" 계열이다. 이 계열은 하나의 소득회계
    #        (p_oinc = p_minc + p_pubinc, p_dinc = p_oinc − p_tax − p_soin_amt)이므로,
    #        같은 회계가 일차소득 0 이라고 적은 사람의 소득세는 그 회계 안에서 0 이어야 한다.
    #  처리: p_minc ≤ 0 인 사람의 p_tax_inc 는 **공적연금 세액만** 남긴다.
    #        공적연금 급여는 일차소득(p_minc)이 아니라 공적이전소득(p_pubinc)이고
    #        소득세법상 과세 대상이므로(§20조의3·§47조의2), 일차소득이 0 이어도 정당하게 남는다.
    #        pubpen_tax 는 공적연금 단독 기준 세액이라 다른 소득이 없을 때의 정확한 값이다.
    #  범위: 재산세(p_ptax_sum)는 손대지 않는다 — 6.1 현재 소유자에게 과세되므로
    #        무소득자에게도 성립한다. 원천 DB 세액 컬럼(inc_total_tax 등)도 손대지 않는다
    #        (S1 국세통계 총량 목표 4건은 그 컬럼에서 평가되며 전부 통과 상태를 유지).
    _no_minc = out['p_minc'] <= 0
    tax_inc = tax_inc.where(~_no_minc, pubpen_tax.fillna(0.0))
    out['p_tax_inc'] = np.rint(tax_inc).astype('int64')
    trace['tax_clamped'] = int(_no_minc.sum())

    # 4) 집계 (코드북 program='개인 소득' 정의)
    out['p_pubinc'] = out[list(PUBINC)].sum(axis=1).astype('int64')
    out['p_tax'] = (out['p_tax_inc'] + out['p_ptax_sum']).astype('int64')
    out['p_soin_amt'] = out[list(SOIN)].sum(axis=1).astype('int64')
    out['p_oinc'] = (out['p_minc'] + out['p_pubinc']).astype('int64')
    out['p_dinc'] = (out['p_oinc'] - out['p_tax'] - out['p_soin_amt']).astype('int64')

    # 5) 가구 합 (§7 R22)
    hid = df['hid']
    for p, h in [('p_minc', 'h_minc'), ('p_pubinc', 'h_pubinc'), ('p_tax', 'h_tax'),
                 ('p_soin_amt', 'h_soin_amt'), ('p_oinc', 'h_oinc'), ('p_dinc', 'h_dinc')]:
        out[h] = out.groupby(hid)[p].transform('sum').astype('int64')

    # 6) 검증용 밑줄 헬퍼 (R01 <표 2-36>·<표 2-37> 항목군; 최종 산출물에서 제외)
    for nm, cols in [('_p_pubpension_amt', GRP_PENSION), ('_p_disbn_amt', GRP_DIS),
                     ('_p_itcgrp_amt', GRP_ITC), ('_p_empocc_amt', GRP_EMPOCC)]:
        out[nm] = out[cols].sum(axis=1).astype('int64')
    for nm, cols in [('_h_nblsbn_amt', GRP_NBLS), ('_h_childbn_amt', GRP_CHILD)]:
        out[nm] = out.groupby(hid)[cols].transform('sum').sum(axis=1).astype('int64')
    out['_h_eq_dinc'] = out['h_dinc'] / np.sqrt(df['hnum'].clip(lower=1))
    out['_h_eq_minc'] = out['h_minc'] / np.sqrt(df['hnum'].clip(lower=1))
    globals()['LAST_TRACE'] = trace
    print('    [B04] 소스없음 %d개 / p_minc 폴백 %s / 생성 %s / p_tax_inc 정합화 %d행'
          % (len(trace['missing_src']), trace['minc_fallback'] or '없음', trace['created'] or '없음',
             trace['tax_clamped']),
          flush=True)

    return out
