# -*- coding: utf-8 -*-
"""§7 R01~R25 **독립 재구현** — tools/consistency.py 를 import 하지 않고
작업지시서 §7 표(registry/instr.txt 703~729행)의 규칙 문장에서 직접 구현한다.

※ 이 파일은 2026-09-02 최종 재검증에서 **새로 추가**한 검증 스크립트다.
   tools/core.py · pipeline.py · consistency.py · validate.py 는 일절 수정하지 않았다.
   실행: cd work && ../.venv/bin/python tools/verify_s7_independent.py
가능한 곳은 consistency.py 보다 **엄격하게** 읽고, 해석이 갈리는 곳은 두 판정을 모두 낸다."""
import json, os, sys, re
import numpy as np, pandas as pd

df = pd.read_parquet('data/stage_all.parquet')
CB = {v['var']: v for v in json.load(open('registry/codebook.json', encoding='utf-8'))}
CBV = pd.read_csv('registry/codebook_vars.csv')
CBC = dict(zip(CBV['변수명(영문)'].astype(str), CBV['변수 내용'].astype(str)))
CBU = dict(zip(CBV['변수명(영문)'].astype(str), CBV['단위'].astype(str)))
N = len(df)
res, notes = [], []
def R(rid, desc, v, extra=''):
    res.append({'id': rid, 'rule': desc, 'viol': v, 'note': extra})

col = lambda c: df[c] if c in df.columns else None
def cnt(m): return int(np.asarray(pd.Series(m).fillna(False)).sum())

# ── R01 bp_yn1=1 ⇒ age≥65
R('R01', 'bp_yn1=1 ⇒ age>=65', cnt((df.bp_yn1 == 1) & (df.age < 65)))

# ── R02 bp_type∈{2,3} ⇒ 배우자 존재 ∧ 배우자 65+
#    "배우자 존재"를 _spouse_age 유무가 아니라 **가구 내 spouse/head 짝**으로 독립 확인
sp_age = {}
for hid_, sub in df.groupby('hid')[['_role', 'age']]:
    a = dict(zip(sub['_role'], sub['age']))
    sp_age[hid_] = a
def spouse_age_row(r):
    a = sp_age[r['hid']]
    if r['_role'] == 'head':   return a.get('spouse', np.nan)
    if r['_role'] == 'spouse': return a.get('head', np.nan)
    return np.nan
sa = df.apply(spouse_age_row, axis=1)
m2 = df.bp_type.isin([2, 3])
R('R02', 'bp_type in {2,3} => 배우자 존재 & 배우자 65+',
  cnt(m2 & (sa.isna() | (sa < 65))),
  '배우자 연령을 df 헬퍼가 아니라 hid×_role 재구성으로 독립 산출')

# ── R03 노령연금 ⇒ 수급개시연령(출생연도별) ∧ 가입기간 120개월+
#    국민연금법 부칙: 1953~56 → 61 / 57~60 → 62 / 61~64 → 63 / 65~68 → 64 / 69~ → 65
def start_age(byear):
    b = np.asarray(byear, float)
    return np.select([b <= 1952, b <= 1956, b <= 1960, b <= 1964, b <= 1968],
                     [60, 61, 62, 63, 64], default=65)
if 'np_pension_yn' in df.columns:
    m = df.np_pension_yn == 1
    sa_req = start_age(df['year'])
    dur = df['np_dur'].copy()
    if '_np_months_total' in df.columns:
        dur = dur.fillna(df['_np_months_total'])
    v_loose = cnt(m & ((dur.fillna(0) < 120) | (df.age < 60)))
    v_strict = cnt(m & ((dur.fillna(0) < 120) | (df.age < sa_req)))
    R('R03', '노령연금 => 수급개시연령 & 누적가입 120개월+', v_loose,
      '엄격판정(출생연도별 수급개시연령 적용) = %d 건' % v_strict)
else:
    R('R03', 'n/a', None)

# ── R04 np_yn=1 ⇒ 18≤age≤64
R('R04', 'np_yn=1 => 18<=age<=64', cnt((df.np_yn == 1) & ((df.age < 18) | (df.age > 64))))

# ── R05 직역연금 가입 ⇒ np_yn=0
occ = [c for c in ('govp_yn1', 'privschp_yn1', 'milp_yn1', 'postp_yn1') if c in df.columns]
R('R05', '직역연금 가입 => np_yn=0',
  cnt((df[occ].fillna(0).eq(1).any(axis=1)) & (df.np_yn == 1)), '대상열 %s' % occ)

# ── R06 childbn ⇒ age<8
R('R06', 'childbn_yn1=1 => age<8', cnt((df.childbn_yn1 == 1) & (df.age >= 8)))

# ── R07 infantbn·carebn·childcare 배타
c7 = [c for c in ('infantbn_yn1', 'carebn_yn1', 'childcare_yn1') if c in df.columns]
R('R07', '영유아 3급여 배타', cnt(df[c7].fillna(0).eq(1).sum(axis=1) > 1), '대상열 %s' % c7)

# ── R08 nbls_medi ⇔ nhi_type∈{7,8}  (쌍방향)
a = df.nbls_medi_yn1.fillna(0) == 1
b = df.nhi_type.isin([7, 8])
R('R08', 'nbls_medi <=> nhi_type in {7,8}', cnt(a ^ b),
  'a&~b=%d / b&~a=%d' % (cnt(a & ~b), cnt(b & ~a)))

# ── R09 nbls_live ⇒ 균등화소득 하위 ∧ 저재산  (consistency.py 는 저재산을 검사하지 않는다)
eq = df.groupby('hid')['p_minc'].transform('sum') / np.sqrt(df['hnum'].clip(lower=1)) \
     if 'p_minc' in df.columns else None
eqh = df['_h_eq_inc'] if '_h_eq_inc' in df.columns else eq
prop = df['_h_prop'] if '_h_prop' in df.columns else None
m = df.nbls_live_yn1.fillna(0) == 1
v_inc = cnt(m & (eqh > eqh.quantile(0.25)))
v_prop = cnt(m & (prop > prop.quantile(0.60))) if prop is not None else None
R('R09', 'nbls_live => 균등화소득 하위25% & 재산 하위60%', v_inc,
  '재산조건 위반 %s 건 (consistency.py 는 이 조건을 검사하지 않음)' % v_prop)

# ── R10 disp ⇒ dis_yn ∧ 중증(dis_grade_1=1) ∧ 18+
R('R10', 'disp_yn1 => dis_yn=1 & 중증 & 18+',
  cnt((df.disp_yn1 == 1) & ((df.dis_yn != 1) | (df.dis_grade_1 != 1) | (df.age < 18))))

# ── R11 disp_bn ⇒ 경증(dis_grade_1=2) ∧ 18+
R('R11', 'disp_bn_yn1 => 경증 & 18+',
  cnt((df.disp_bn_yn1 == 1) & ((df.dis_grade_1 != 2) | (df.age < 18))))

# ── R12 육아휴직 ⇒ 0~8세 자녀 ∧ 고용보험  (자녀 존재를 hid×age 로 독립 재계산)
kid = df.assign(_k=((df.age >= 0) & (df.age <= 8)).astype(int)).groupby('hid')['_k'].transform('max')
R('R12', 'empins_parentleave => 가구 내 0~8세 & empins_yn1=1',
  cnt((df.empins_parentleave_yn1 == 1) & ((kid != 1) | (df.empins_yn1 != 1))),
  '0~8세 자녀 존재를 hid groupby 로 독립 재계산')

# ── R13 실업급여 ⇒ 고용보험 이력 ∧ 15+
R('R13', 'unempbn_jobseekbn_yn => 고용보험 이력 & 15+',
  cnt((df.unempbn_jobseekbn_yn == 1) & ((df['_empins_hist'] != 1) | (df.age < 15))))

# ── R14 ltcare ⇒ 65+ (예외 ≤5%)
m = df.ltcare_yn == 1
u = cnt(m & (df.age < 65)); t = cnt(m)
R('R14', 'ltcare => 65+ (65세미만 5% 이하 허용)', 0 if (t == 0 or u / t <= 0.05) else u,
  '65세미만 %d / %d = %.3f' % (u, t, (u / t if t else 0)))

# ── R15 시설급여 ⇒ 재가급여 0
home = [c for c in df.columns if re.match(r'ltcare_(visit|bath|nursing|daynight|short)\w*_yn$', c)]
R('R15', 'ltcare_institute => 재가급여 전부 0',
  cnt((df.ltcare_institute_yn == 1) & (df[home].fillna(0).eq(1).any(axis=1))), '재가열 %s' % home)

# ── R16 nhi_type=6 ⇒ 무소득 ∧ 가구 내 nhi_type=5 존재
dep = df.nhi_type == 6
has5 = df.assign(_e=(df.nhi_type == 5).astype(int)).groupby('hid')['_e'].transform('max')
v_inc = cnt(dep & (df.p_minc.fillna(0) > 0))
v_h5 = cnt(dep & (has5 != 1))
R('R16', 'nhi_type=6 => p_minc<=0 & 가구 내 nhi_type=5', v_inc + v_h5,
  '소득위반 %d / 가구내5 없음 %d' % (v_inc, v_h5))

# ── R17 itc ⇒ 근로·사업소득 ∧ 요건 (요건 = 가구유형별 총소득 상한, 2022 귀속 조특법 §100의3)
m = df.itc_yn == 1
inc = df.p_labinc.fillna(0) + df.p_binc.fillna(0)
v_inc = cnt(m & (inc <= 0))
R('R17', 'itc_yn => 근로+사업소득 > 0', v_inc)

# ── R18 single ⇒ 한부모 ∧ 자녀<18  (한부모 판정을 _role 로 독립 재계산)
def is_sp(sub):
    roles = set(sub['_role'])
    return int(('child' in roles) and ('spouse' not in roles)
               and (sub.loc[sub['_role'] == 'child', 'age'] < 18).any())
sp_flag = df.groupby('hid').apply(is_sp, include_groups=False)
sp_row = df['hid'].map(sp_flag)
R('R18', 'single_rear_yn1 => 한부모(head+child, spouse 없음) & 자녀<18',
  cnt((df.single_rear_yn1 == 1) & (sp_row != 1)),
  '한부모 여부를 _role 조합으로 독립 재구성')

# ── R19 rm ⇒ 주택소유(ptax_housing>0) ∧ 55+
R('R19', 'rm_yn => ptax_housing>0 & 55+',
  cnt((df.rm_yn == 1) & ((df.ptax_housing.fillna(0) <= 0) | (df.age < 55))))

# ── R20 공익활동 ⇒ bp ∧ 65+
R('R20', 'oldwork_type1_yn1 => bp_yn1=1 & 65+',
  cnt((df.oldwork_type1_yn1 == 1) & ((df.bp_yn1 != 1) | (df.age < 65))))

# ── R21 ceiling ⇒ 본인부담 > 분위 상한
own = df['_nhi_own_pay'] if '_nhi_own_pay' in df.columns else None
R('R21', 'nhi_ceiling_subsidy_yn => 본인부담 > nhi_ceiling_amt',
  cnt((df.nhi_ceiling_subsidy_yn == 1) & (own.fillna(0) <= df.nhi_ceiling_amt.fillna(np.inf))))

# ── R22 p_pubinc = Σ(49개 p_*_amt) ; h_* = Σ 가구원  (consistency.py 는 h_pubinc 만 본다)
# 49개 목록을 B04 코드가 아니라 **코드북(program='개인 공적이전소득')** 에서 독립 구성
pub = [v['var'] for v in CB.values() if v.get('program') == '개인 공적이전소득']
pub = [c for c in pub if c in df.columns]
s_pub = df[pub].fillna(0).sum(axis=1)
v22a = cnt((df.p_pubinc.fillna(0) - s_pub).abs() > 1)
v22b = 0; det = []
for p, h in [('p_minc','h_minc'), ('p_pubinc','h_pubinc'), ('p_tax','h_tax'),
             ('p_soin_amt','h_soin_amt'), ('p_oinc','h_oinc'), ('p_dinc','h_dinc')]:
    if p in df.columns and h in df.columns:
        k = cnt((df[h].fillna(0) - df.groupby('hid')[p].transform('sum')).abs() > 1)
        v22b += k
        if k: det.append('%s=%d' % (h, k))
R('R22', 'p_pubinc=Σ49개 p_*_amt ; h_*=Σ가구원 (6쌍 전부)', v22a + v22b,
  'p_pubinc 합산불일치 %d / h_* 불일치 %d %s (합산열 %d개)' % (v22a, v22b, det, len(pub)))

# ── R23 head 가구당 1 ; hnum = 실제 행수 ; hid·pid 유일성
g = df.groupby('hid')
v23 = cnt(g['head'].transform(lambda s: (s == 1).sum()) != 1) \
    + cnt(g['hid'].transform('size') != df.hnum)
dupe = int(df['pid'].duplicated().sum())
R('R23', 'head 가구당 1개 & hnum=행수', v23, 'pid 중복 %d 건' % dupe)

# ── R24 yn2⇒yn1 ; dur 범위 ; amt>0 ⇔ yn1   ★amt⇔yn1 은 consistency.py 가 검사하지 않는다
v_yn2 = 0; d_yn2 = []
for c in df.columns:
    if c.endswith('_yn2'):
        c1 = c[:-1] + '1'
        if c1 in df.columns:
            k = cnt((df[c] == 1) & (df[c1] != 1))
            v_yn2 += k
            if k: d_yn2.append('%s:%d' % (c, k))
RANGE = {'개월': (1, 12), '일': (1, 366), '시간': (1, 8784)}
CUM = {v for v, c in CBC.items() if v.endswith('_dur') and
       (('가입 개월 수' in c) or ('재직기간' in c) or ('거주시작시점' in c))}
v_dur = 0; d_dur = []
for c in [x for x in df.columns if x.endswith('_dur')]:
    s = df[c]
    if c in CUM:
        k = cnt(s.notna() & (s < 0))
    else:
        lo, hi = RANGE.get((CBU.get(c) or '개월').strip(), (1, 12))
        k = cnt(s.notna() & ((s < lo) | (s > hi)))
    v_dur += k
    if k: d_dur.append('%s:%d' % (c, k))
# amt > 0  ⇔  yn1 = 1
v_amt = 0; d_amt = []
for c in [x for x in df.columns if re.search(r'_amt\d?$', x) and not x.startswith(('p_', 'h_', '_'))]:
    base = re.sub(r'_amt\d?$', '', c)
    y = None
    for cand in (base + '_yn1', base + '_yn'):
        if cand in df.columns: y = cand; break
    if y is None: continue
    pos = df[c].fillna(0) > 0
    on = df[y] == 1
    k1 = cnt(pos & ~on)                 # 금액 있는데 수급 아님
    if k1: d_amt.append('%s>0 & %s!=1 : %d' % (c, y, k1))
    v_amt += k1
R('R24', 'yn2=>yn1 ; dur 범위 ; amt>0 => yn1', v_yn2 + v_dur + v_amt,
  'yn2 %d %s / dur %d %s / amt>0&yn1!=1 %d %s' % (v_yn2, d_yn2, v_dur, d_dur, v_amt, d_amt[:6]))

# ── R25 Σindwgt ≈ 인구, Σhhwgt(가구주) ≈ 가구수, ±1%
Np, Nh = float(df._N_pop_person.iloc[0]), float(df._N_pop_hh.iloc[0])
r1 = df['indwgt'].sum() / Np
r2 = df.loc[df['head'] == 1, 'hhwgt'].sum() / Nh
R('R25', 'Σindwgt≈인구 & Σhhwgt≈가구수 (±1%)',
  int(abs(r1 - 1) > 0.01) + int(abs(r2 - 1) > 0.01),
  'Σindwgt=%.0f (배수 %.6f) / Σhhwgt=%.0f (배수 %.6f)'
  % (df['indwgt'].sum(), r1, df.loc[df['head'] == 1, 'hhwgt'].sum(), r2))

out = pd.DataFrame(res)
pd.set_option('display.width', 260); pd.set_option('display.max_colwidth', 120)
print(out.to_string(index=False))
tot = int(out['viol'].fillna(0).sum())
print('\nINDEPENDENT TOTAL VIOLATIONS =', tot)
print('rules with viol>0:', out[out.viol.fillna(0) > 0]['id'].tolist())
