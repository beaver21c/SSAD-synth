# -*- coding: utf-8 -*-
"""작업지시서 §7 조건부 정합성 규칙 R01~R25 — 위반 0건이 합격 기준."""
import json, os
import numpy as np, pandas as pd

# 코드북 단위 — R24 의 dur 범위 판정에 사용 (개월 단위 급여기간만 [1,12])
_CB_UNIT = {}
_CB_NAME = {}
try:
    for _v in json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                          'registry/codebook.json'), encoding='utf-8')):
        _CB_UNIT[_v['var']] = _v.get('unit', '')
        _CB_NAME[_v['var']] = _v.get('name_ko', '')
except Exception:
    pass

def _alias(df, c):
    """컬럼 해석. registry/column_contract.md 상 블록 간 헬퍼 컬럼은 '_' 접두를 쓰므로
    (`_spouse_age`·`_h_eq_inc`·`_has_child_0_8`·`_empins_hist`·`_is_single_parent`·`_nhi_own_pay`)
    코드북명이 없으면 '_'+명 으로 폴백한다. 이 폴백이 없으면 R02·R09·R12·R13·R18·R21 이
    영구히 N/A 로 남아 §7 검사가 실행되지 않는다."""
    if c in df.columns: return c
    if '_' + c in df.columns: return '_' + c
    return None

def _has(df, *c): return all(_alias(df, x) is not None for x in c)
def _g(df, c): return df[_alias(df, c)]
def _n(df, mask): return int(np.asarray(mask).sum())

RULES = []
def rule(rid, desc, area):
    def deco(fn):
        RULES.append({'id': rid, 'desc': desc, 'area': area, 'fn': fn}); return fn
    return deco


# ── _dur 단위별 허용범위 — R24 의 dur∈[1,12] 는 **개월** 단위 변수에만 적용된다.
#   코드북 단위가 '일'(oldwork_type*_dur, unempbn_*_dur, empins_matleave_dur 등) ·
#   '시간'(disvou_act_dur 등)인 _dur 변수는 상한을 달리 적용한다. 단위는 위 _CB_UNIT 사용.
def _dur_unit(col):
    return (_CB_UNIT.get(col) or '개월')

_DUR_RANGE = {'개월': (1, 12), '일': (1, 366), '시간': (1, 8784)}

# ── 누적기간 _dur (연도 내 개월수가 아님) ─────────────────────────────────────
#   코드북 단위는 '개월'이지만 "가입 개월 수"(np/govp/privschp/milp/postp_dur) ·
#   "거주시작시점부터 … 거주한 총 개월 수"(lh_*/gh_*/sh_*_dur) 는 **누적** 기간이라
#   R24 의 dur∈[1,12] 상한이 성립하지 않는다. 코드북 "변수 내용"에서 판별한다.
_DUR_CUMUL = None
def _dur_is_cumulative(col):
    global _DUR_CUMUL
    if _DUR_CUMUL is None:
        _DUR_CUMUL = set()
        try:
            import os as _os
            _p = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                               'registry/codebook_vars.csv')
            _cb = pd.read_csv(_p)
            for _v, _c in zip(_cb['변수명(영문)'].astype(str), _cb['변수 내용'].astype(str)):
                if not _v.endswith('_dur'):
                    continue
                if ('가입 개월 수' in _c) or ('재직기간' in _c) or ('거주시작시점' in _c):
                    _DUR_CUMUL.add(_v)
        except Exception:
            _DUR_CUMUL = set()
    return col in _DUR_CUMUL

@rule('R01', 'bp_yn1=1 ⇒ age≥65', '기초연금')
def r01(df):
    if not _has(df,'bp_yn1','age'): return None
    return _n(df, (df.bp_yn1==1) & (df.age<65))

@rule('R02', 'bp_type∈{2,3} ⇒ 배우자 존재 ∧ 배우자 65+', '부부유형')
def r02(df):
    if not _has(df,'bp_type','spouse_age'): return None
    sa = _g(df,'spouse_age')
    m = df.bp_type.isin([2,3])
    return _n(df, m & (sa.isna() | (sa<65)))

@rule('R03', '노령연금 ⇒ 수급개시연령 ∧ np_dur≥120', '국민연금')
def r03(df):
    # np_dur 의 코드북 추출대상은 "2022.12.31 기준 **가입자**"이므로 연금 수급자에게는
    # 정상적으로 결측이다(§7 "NULL 패턴 = 추출대상 정의"). 가입기간 120개월 요건은
    # B13 이 남기는 헬퍼 _np_months_total(누적 가입개월, 최종 산출물 제외)로 검사한다.
    if not _has(df,'np_pension_yn','np_dur','age'): return None
    dur = df['np_dur']
    if '_np_months_total' in df.columns:
        dur = dur.fillna(df['_np_months_total'])
    m = df.np_pension_yn==1
    return _n(df, m & ((dur.fillna(0)<120) | (df.age<60)))

@rule('R04', 'np_yn=1 ⇒ 18≤age≤64', '가입연령')
def r04(df):
    if not _has(df,'np_yn','age'): return None
    return _n(df, (df.np_yn==1) & ((df.age<18)|(df.age>64)))

@rule('R05', '직역연금 가입 ⇒ np_yn=0', '배타')
def r05(df):
    cols=[c for c in ('govp_yn1','privschp_yn1','milp_yn1','postp_yn1') if c in df.columns]
    if not cols or 'np_yn' not in df.columns: return None
    occ = df[cols].fillna(0).max(axis=1)==1
    return _n(df, occ & (df.np_yn==1))

@rule('R06', 'childbn ⇒ age<8', '아동수당')
def r06(df):
    if not _has(df,'childbn_yn1','age'): return None
    return _n(df, (df.childbn_yn1==1)&(df.age>=8))

@rule('R07', 'infantbn·carebn·childcare 배타', '영유아')
def r07(df):
    cols=[c for c in ('infantbn_yn1','carebn_yn1','childcare_yn1') if c in df.columns]
    if len(cols)<2: return None
    return _n(df, df[cols].fillna(0).sum(axis=1)>1)

@rule('R08', 'nbls_medi ⇔ nhi_type∈{7,8}', '의료급여')
def r08(df):
    if not _has(df,'nbls_medi_yn1','nhi_type'): return None
    a=(df.nbls_medi_yn1==1); b=df.nhi_type.isin([7,8])
    return _n(df, a^b)

@rule('R09', 'nbls_live ⇒ 균등화소득 하위 ∧ 저재산', '생계')
def r09(df):
    if not _has(df,'nbls_live_yn1','h_eq_inc'): return None
    eq = _g(df,'h_eq_inc')
    thr = eq.quantile(0.25)
    return _n(df, (df.nbls_live_yn1==1)&(eq>thr))

@rule('R10', 'disp ⇒ dis_yn ∧ 중증 ∧ 18+', '장애인연금')
def r10(df):
    if not _has(df,'disp_yn1','dis_yn','dis_grade_1','age'): return None
    return _n(df, (df.disp_yn1==1) & ((df.dis_yn!=1)|(df.dis_grade_1!=1)|(df.age<18)))

@rule('R11', 'disp_bn ⇒ 경증 ∧ 18+', '장애수당')
def r11(df):
    if not _has(df,'disp_bn_yn1','dis_grade_1','age'): return None
    return _n(df, (df.disp_bn_yn1==1) & ((df.dis_grade_1!=2)|(df.age<18)))

@rule('R12', '육아휴직 ⇒ 0~8세 자녀 ∧ 고용보험', '모성보호')
def r12(df):
    if not _has(df,'empins_parentleave_yn1','has_child_0_8','empins_yn1'): return None
    return _n(df, (df.empins_parentleave_yn1==1)&((_g(df,'has_child_0_8')!=1)|(df.empins_yn1!=1)))

@rule('R13', '실업급여 ⇒ 고용보험 이력 ∧ 15+', '실업급여')
def r13(df):
    if not _has(df,'unempbn_jobseekbn_yn','empins_hist','age'): return None
    return _n(df, (df.unempbn_jobseekbn_yn==1)&((_g(df,'empins_hist')!=1)|(df.age<15)))

@rule('R14', 'ltcare ⇒ 65+ (예외≤5%)', '장기요양')
def r14(df):
    if not _has(df,'ltcare_yn','age'): return None
    m=df.ltcare_yn==1; tot=_n(df,m)
    if tot==0: return 0
    under=_n(df, m&(df.age<65))
    return 0 if under/tot<=0.05 else under

@rule('R15', '시설급여 ⇒ 재가 0', '장기요양')
def r15(df):
    home=[c for c in ('ltcare_visit_yn','ltcare_bath_yn','ltcare_nursing_yn','ltcare_daynight_yn','ltcare_short_yn') if c in df.columns]
    if 'ltcare_institute_yn' not in df.columns or not home: return None
    return _n(df, (df.ltcare_institute_yn==1)&(df[home].fillna(0).max(axis=1)==1))

@rule('R16', 'nhi_type=6 ⇒ 피부양자 소득요건(별표 1의2) ∧ 가구 내 5', '피부양자')
def r16(df):
    # [T3] R16 개정 — 종전 "무소득"은 법정 요건이 아니다. 국민건강보험법 시행규칙 [별표 1의2]
    #   1-가: 소득 합계 연 2,000만원 이하 / 1-나: 사업소득 없음(사업자등록 없음·장애인은 500만원 이하)
    #   을 원천 DB 소득으로 평가한다. 공적연금(pubpen_inc)은 자격 반영 시차(전년도 소득을 11월에 반영)
    #   때문에 판정에서 제외하고 tools/linkcheck.py 의 감시지표로 본다.
    if not _has(df,'nhi_type','hid'): return None
    def S(c): return df[c].fillna(0).to_numpy(float) if c in df.columns else np.zeros(len(df))
    wage = np.maximum(S('labinc_sum_taxy') - S('labinc_sum_taxn'), 0.0)
    biz_u = S('binc_sum_inc') + S('ybinc_sum_inc')
    biz_r = S('inc_binc') + S('inc_reinc') + S('inc_hou') + S('inc_sehou')
    inc = wage + S('dainc_sum') + S('fainc_sum') + S('pripen_inc') + S('othinc_sum_inc') + biz_u + biz_r
    dis = (df['dis_yn'].fillna(0).to_numpy() == 1) if 'dis_yn' in df.columns else np.zeros(len(df), bool)
    biz_tot = biz_u + biz_r
    biz_bad = np.where((biz_r <= 0) | dis, biz_tot > 5_000_000, biz_tot > 0)
    dep = (df['nhi_type'] == 6).to_numpy()
    hh5 = df.assign(_e=(df['nhi_type'] == 5).astype(int)).groupby('hid')['_e'].transform('max').to_numpy()
    return _n(df, (dep & (biz_bad | (inc > 20_000_000))) | (dep & (hh5 != 1)))

@rule('R17', 'itc ⇒ 근로·사업소득 ∧ 요건', '장려금')
def r17(df):
    if not _has(df,'itc_yn','p_labinc','p_binc'): return None
    return _n(df, (df.itc_yn==1)&((df.p_labinc.fillna(0)+df.p_binc.fillna(0))<=0))

@rule('R18', 'single ⇒ 한부모 ∧ 자녀<18', '한부모')
def r18(df):
    if not _has(df,'single_rear_yn1','is_single_parent'): return None
    return _n(df, (df.single_rear_yn1==1)&(_g(df,'is_single_parent')!=1))

@rule('R19', 'rm ⇒ 주택소유 ∧ 55+', '주택연금')
def r19(df):
    if not _has(df,'rm_yn','ptax_housing','age'): return None
    return _n(df, (df.rm_yn==1)&((df.ptax_housing.fillna(0)<=0)|(df.age<55)))

@rule('R20', '공익활동 ⇒ bp ∧ 65+', '노인일자리')
def r20(df):
    if not _has(df,'oldwork_type1_yn1','bp_yn1','age'): return None
    return _n(df, (df.oldwork_type1_yn1==1)&((df.bp_yn1!=1)|(df.age<65)))

@rule('R21', 'ceiling ⇒ 본인부담 > 분위 상한', '상한제')
def r21(df):
    if not _has(df,'nhi_ceiling_subsidy_yn','nhi_own_pay','nhi_ceiling_amt'): return None
    return _n(df, (df.nhi_ceiling_subsidy_yn==1)&(_g(df,'nhi_own_pay').fillna(0)<=df.nhi_ceiling_amt.fillna(np.inf)))

@rule('R22', 'p_pubinc=Σamt; h_*=Σ가구원', '합산')
def r22(df):
    if not _has(df,'p_pubinc','h_pubinc','hid'): return None
    hs = df.groupby('hid')['p_pubinc'].transform('sum')
    return _n(df, (df.h_pubinc.fillna(0)-hs).abs()>1)

@rule('R23', 'head 가구당 1; hnum=행수', '골격')
def r23(df):
    if not _has(df,'head','hid','hnum'): return None
    g = df.groupby('hid')
    bad_head = (g['head'].transform(lambda s:(s==1).sum())!=1)
    bad_n = (g['hid'].transform('size')!=df.hnum)
    return _n(df, bad_head|bad_n)

@rule('R24', 'yn2⇒yn1; dur∈[1,12]; amt>0⇔yn1', '공통')
def r24(df):
    bad = 0
    import re as _re
    for c in df.columns:
        if c.endswith('_yn2'):
            c1 = c[:-1]+'1'
            if c1 in df.columns: bad += _n(df, (df[c]==1)&(df[c1]!=1))
        if c.endswith('_dur'):
            if _dur_is_cumulative(c):
                s = df[c]; bad += _n(df, s.notna()&(s<0))   # 누적기간: 음수만 위반
                continue
            lo, hi = _DUR_RANGE.get(_dur_unit(c), (1, 12))
            s = df[c]; bad += _n(df, s.notna()&((s<lo)|(s>hi)))
    return bad

@rule('R25', 'Σindwgt≈가구원수, Σhhwgt≈가구수 ±1%', '가중치')
def r25(df, pop=None):
    # `df.head` 는 pandas 메서드다 — 가구주 컬럼은 반드시 df['head'] 로 읽는다
    # (registry/column_contract.md 공통규칙). 예전 코드의 df.head==1 은 bool False 로
    # 평가돼 .loc[False] 에서 터졌다.
    if not _has(df,'indwgt','hhwgt','head'): return None
    if pop is None:
        # B01 이 남기는 모집단 규모 헬퍼(_N_pop_person·_N_pop_hh)를 기본 기준으로 쓴다.
        # 이것이 없으면(외부 df) 종전대로 판정 불가.
        if not _has(df,'_N_pop_person','_N_pop_hh'): return None
        pop = {'persons': float(df['_N_pop_person'].iloc[0]),
               'households': float(df['_N_pop_hh'].iloc[0])}
    a = abs(df['indwgt'].sum()/pop['persons']-1) > 0.01
    b = abs(df.loc[df['head']==1,'hhwgt'].sum()/pop['households']-1) > 0.01
    return int(a)+int(b)

def run(df, pop=None):
    rows=[]
    for r in RULES:
        try:
            v = r['fn'](df, pop) if r['id']=='R25' else r['fn'](df)
        except Exception as e:
            v = f'ERR:{type(e).__name__}:{e}'
        rows.append({'id':r['id'],'area':r['area'],'rule':r['desc'],
                     'violations': ('N/A(변수없음)' if v is None else v)})
    return pd.DataFrame(rows)
