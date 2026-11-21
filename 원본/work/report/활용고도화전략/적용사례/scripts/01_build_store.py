#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""집계 저장소 산출 — 가상데이터(확대본) → 대시보드용 집계표(JSON)

원칙
  · 개인 단위 값은 저장하지 않는다. 저장하는 것은 집계값뿐이다.
  · 변수 민감도 등급(가·나·다)에 따라 최소 관측 수(10·20·30) 미만 칸을 저장 단계에서 억제한다(R1).
    비율은 분자·분모·여집합 모두 기준 이상이어야 한다.
  · 한 줄에 억제 칸이 하나뿐이면 합계에서 역산되지 않도록 가장 작은 칸을 보충 억제한다(R2).
  · 가중 인원·금액은 유효숫자 3자리, 비율은 소수 첫째 자리로 반올림한다(R6).
  · 시군구 단위는 등급 가만 값으로 제공하고, 등급 나는 5개 구간으로만 제공하며, 등급 다는 제공하지 않는다.
  · 교차 차원은 등급 가·나 3개, 등급 다 2개까지 저장한다.

실행
  .venv/bin/python scripts/01_build_store.py data/가상데이터_확대본_n42000.parquet data/geo.json data/store.json
"""
import itertools
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SRC, GEO, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
CB = '/mnt/share/행정데이터_set/work/registry/codebook_vars.csv'
THR = {'가': 10, '나': 20, '다': 30}
MAXDIM = {'가': 3, '나': 3, '다': 2}
SIDO = ['서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종', '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주']
CITYFIX = {'28177': '28170', '47720': '27720'}        # 자료의 시군구 코드 → 경계 자료 코드


def sig3(x):
    if x is None or not np.isfinite(x) or x == 0:
        return 0 if x == 0 else None
    k = int(math.floor(math.log10(abs(x)))) - 2
    v = round(x / 10 ** k) * 10 ** k
    return int(v) if k >= 0 else round(v, -k)


# ───────────────────────── 자료 적재·분류 변수 ─────────────────────────
df = pd.read_parquet(SRC)
N = len(df)
w = df['indwgt'].astype(float).values
age = df['age'].astype(int).values
hh_dinc = df.groupby('hid')['p_dinc'].transform('sum').astype(float).values
eq = hh_dinc / np.sqrt(df['hnum'].astype(float).values)          # 균등화 가처분소득(원)
o = np.argsort(eq); cw = np.cumsum(w[o]); tot = cw[-1]
median_eq = eq[o][np.searchsorted(cw, tot / 2)]
qcut = [eq[o][np.searchsorted(cw, tot * q)] for q in (.2, .4, .6, .8)]
poor = eq < 0.5 * median_eq

D = {
    'sido': df['sido'].astype(int).values - 1,
    'age': np.digitize(age, [18, 35, 50, 65, 75]),
    'sex': df['gender'].astype(int).values - 1,
    'hs': np.minimum(df['hnum'].astype(int).values, 4) - 1,
    'inc': np.digitize(eq, qcut),
}
DIMS = {
    'sido': {'label': '시도', 'cats': SIDO},
    'age': {'label': '연령대', 'cats': ['0~17세', '18~34세', '35~49세', '50~64세', '65~74세', '75세 이상']},
    'sex': {'label': '성', 'cats': ['남', '여']},
    'hs': {'label': '가구원수', 'cats': ['1인', '2인', '3인', '4인 이상']},
    'inc': {'label': '소득 5분위', 'cats': ['1분위(하위 20%)', '2분위', '3분위', '4분위', '5분위(상위 20%)']},
}
ORDER = ['sido', 'age', 'sex', 'hs', 'inc']
SHAPE = {k: len(v['cats']) for k, v in DIMS.items()}

geo = json.load(open(GEO, encoding='utf-8'))
city_codes = [g['code'] for g in geo['sgg']]
cidx = {c: i for i, c in enumerate(city_codes)}
city = np.array([cidx[CITYFIX.get(str(c), str(c))] for c in df['city'].astype(int).values])
NC = len(city_codes)


def yes(col):
    return (df[col] == 1).values


def amt(col):                                    # 원 → 만원
    return df[col].fillna(0).astype(float).values / 1e4


ALL = np.ones(N, bool)
# ───────────────────────── 지표 정의 ─────────────────────────
# kind: rate(분자÷분모×100) / mean_r(금액 합÷수급자) / mean_u(금액 합÷대상 인구)
IND = [
    # 영역, id, 지표명, 등급, kind, 단위, 대상(분모), 분자, 금액, 산식 설명
    ('인구·가구', 'age65', '65세 이상 인구 비율', '가', 'rate', '%', ALL, age >= 65, None, '65세 이상 인구 ÷ 전체 인구 × 100'),
    ('인구·가구', 'age75', '75세 이상 인구 비율', '가', 'rate', '%', ALL, age >= 75, None, '75세 이상 인구 ÷ 전체 인구 × 100'),
    ('인구·가구', 'child', '18세 미만 인구 비율', '가', 'rate', '%', ALL, age < 18, None, '18세 미만 인구 ÷ 전체 인구 × 100'),
    ('인구·가구', 'single', '1인 가구 거주 인구 비율', '가', 'rate', '%', ALL, df['hnum'].values == 1, None, '1인 가구원 ÷ 전체 인구 × 100'),
    ('인구·가구', 'oldalone', '65세 이상 중 1인 가구 비율', '가', 'rate', '%', age >= 65, df['hnum'].values == 1, None, '65세 이상 1인 가구원 ÷ 65세 이상 인구 × 100'),
    ('사회보험', 'np', '국민연금 가입률(18~59세)', '가', 'rate', '%', (age >= 18) & (age <= 59), yes('np_yn'), None, '국민연금 가입자 ÷ 18~59세 인구 × 100'),
    ('사회보험', 'empins', '고용보험 가입률(18~64세)', '가', 'rate', '%', (age >= 18) & (age <= 64), yes('empins_yn1'), None, '고용보험 가입자 ÷ 18~64세 인구 × 100'),
    ('사회보험', 'nhiemp', '건강보험 직장가입자 비율', '가', 'rate', '%', ALL, df['nhi_type'].values == 5, None, '직장가입자(본인) ÷ 전체 인구 × 100'),
    ('사회보험', 'nppen', '국민연금 수급률(60세 이상)', '가', 'rate', '%', age >= 60, yes('np_pension_yn'), None, '국민연금 정기연금 수급자 ÷ 60세 이상 인구 × 100'),
    ('사회보험', 'nppen_amt', '국민연금 평균 수급액(수급자)', '나', 'mean_r', '만원', age >= 60, yes('np_pension_yn'), amt('np_pension_amt'), '국민연금 정기연금 연 급여액 합 ÷ 수급자 수'),
    ('사회보험', 'jobseek', '구직급여 수급률(18~64세)', '가', 'rate', '%', (age >= 18) & (age <= 64), yes('unempbn_jobseekbn_yn'), None, '구직급여 수급자 ÷ 18~64세 인구 × 100'),
    ('노인', 'bp', '기초연금 수급률(65세 이상)', '나', 'rate', '%', age >= 65, yes('bp_yn1'), None, '기초연금 수급자 ÷ 65세 이상 인구 × 100'),
    ('노인', 'bp_amt', '기초연금 평균 수급액(수급자)', '나', 'mean_r', '만원', age >= 65, yes('bp_yn1'), amt('bp_amt'), '기초연금 연 급여액 합 ÷ 수급자 수'),
    ('노인', 'oldwork', '노인일자리 공익활동 참여율(65세 이상)', '나', 'rate', '%', age >= 65, yes('oldwork_type1_yn1'), None, '공익활동 참여자 ÷ 65세 이상 인구 × 100'),
    ('노인', 'ltc', '장기요양 수급률(65세 이상)', '다', 'rate', '%', age >= 65, yes('ltcare_bn_yn'), None, '장기요양 수급자 ÷ 65세 이상 인구 × 100'),
    ('기초보장', 'live', '생계급여 수급률', '나', 'rate', '%', ALL, yes('nbls_live_yn1'), None, '생계급여 수급자 ÷ 전체 인구 × 100'),
    ('기초보장', 'live_amt', '생계급여 평균 수급액(수급자)', '나', 'mean_r', '만원', ALL, yes('nbls_live_yn1'), amt('nbls_live_amt'), '생계급여 연 급여액 합 ÷ 수급자 수'),
    ('기초보장', 'house', '주거급여(임차) 수급률', '나', 'rate', '%', ALL, yes('nbls_house_yn1'), None, '주거급여 임차급여 수급자 ÷ 전체 인구 × 100'),
    ('기초보장', 'medi', '의료급여 수급권자 비율', '나', 'rate', '%', ALL, yes('nbls_medi_yn1'), None, '의료급여 수급권자 ÷ 전체 인구 × 100'),
    ('기초보장', 'evou', '에너지바우처 이용률', '나', 'rate', '%', ALL, yes('evou_yn'), None, '에너지바우처 이용자 ÷ 전체 인구 × 100'),
    ('기초보장', 'culvou', '문화누리카드 이용률', '나', 'rate', '%', ALL, yes('culvou_yn'), None, '문화누리카드 이용자 ÷ 전체 인구 × 100'),
    ('근로·조세', 'itc', '근로장려금 대상 비율(18세 이상)', '나', 'rate', '%', age >= 18, yes('itc_yn'), None, '근로장려금 대상자 ÷ 18세 이상 인구 × 100'),
    ('근로·조세', 'itc_amt', '근로장려금 평균 금액(대상자)', '나', 'mean_r', '만원', age >= 18, yes('itc_yn'), amt('itc_amt'), '근로장려 심사금액 합 ÷ 대상자 수'),
    ('근로·조세', 'ptax', '재산세 부과 대상 비율(18세 이상)', '나', 'rate', '%', age >= 18, yes('ptax_yn'), None, '재산세 부과 대상자 ÷ 18세 이상 인구 × 100'),
    ('아동·가족', 'childbn', '인구 대비 아동수당 수급 아동 비율', '가', 'rate', '%', ALL, yes('childbn_yn1'), None, '아동수당 수급 아동 ÷ 전체 인구 × 100'),
    ('아동·가족', 'childcare', '보육료 지원 이용률(6세 미만)', '가', 'rate', '%', age < 6, yes('childcare_yn1'), None, '보육료 지원 아동 ÷ 6세 미만 인구 × 100'),
    ('장애·건강', 'dis', '등록장애인 비율', '다', 'rate', '%', ALL, yes('dis_yn'), None, '등록장애인 ÷ 전체 인구 × 100'),
    ('장애·건강', 'disp', '장애인연금 대상 비율(18세 이상)', '다', 'rate', '%', age >= 18, yes('dis_disp_yn'), None, '장애인연금 대상자 ÷ 18세 이상 인구 × 100'),
    ('장애·건강', 'cancer', '암 산정특례 등록자 비율', '다', 'rate', '%', ALL, yes('nhi_special1_yn'), None, '암 산정특례 등록자 ÷ 전체 인구 × 100'),
    ('장애·건강', 'ceiling', '본인부담상한제 지원 비율', '다', 'rate', '%', ALL, yes('nhi_ceiling_subsidy_yn'), None, '본인부담상한제 지원 대상 ÷ 전체 인구 × 100'),
    ('장애·건강', 'outdays', '1인당 외래 이용 일수', '다', 'mean_u', '일', ALL, ALL, df['nhi_out_dur'].fillna(0).astype(float).values, '외래 이용 일수 합 ÷ 전체 인구'),
    ('소득·빈곤', 'poor', '상대 빈곤율', '나', 'rate', '%', ALL, poor, None, '균등화 가처분소득이 중위값의 50% 미만인 인구 ÷ 전체 인구 × 100'),
    ('소득·빈곤', 'poor65', '65세 이상 상대 빈곤율', '나', 'rate', '%', age >= 65, poor, None, '빈곤 노인 ÷ 65세 이상 인구 × 100'),
    ('소득·빈곤', 'bpgap', '빈곤 노인 중 기초연금 비수급 비율', '나', 'rate', '%', (age >= 65) & poor, ~yes('bp_yn1'), None, '기초연금 비수급 빈곤 노인 ÷ 65세 이상 빈곤 인구 × 100'),
    ('소득·빈곤', 'eqinc', '균등화 가처분소득 평균', '나', 'mean_u', '만원', ALL, ALL, eq / 1e4, '균등화 가처분소득 합 ÷ 전체 인구'),
    ('소득·빈곤', 'pubinc', '1인당 공적이전소득', '나', 'mean_u', '만원', ALL, ALL, amt('p_pubinc'), '공적이전소득 합 ÷ 전체 인구'),
]

# ───────────────────────── 집계 ─────────────────────────
def cell_index(dims):
    idx = np.zeros(N, np.int64)
    for d in dims:
        idx = idx * SHAPE[d] + D[d]
    return idx, int(np.prod([SHAPE[d] for d in dims])) if dims else 1


def agg(idx, size, mask, weights=None):
    return np.bincount(idx[mask], weights=None if weights is None else weights[mask], minlength=size)


def complement(st, nn, shape):
    """R2 보충 억제: 한 줄에 억제 칸이 하나뿐이면 가장 작은 표시 칸을 추가 억제한다."""
    a = st.reshape(shape); n = nn.reshape(shape).astype(float)
    for _ in range(12):
        changed = False
        for ax in range(a.ndim):
            a_m = np.moveaxis(a, ax, -1); n_m = np.moveaxis(n, ax, -1)
            flat = a_m.reshape(-1, a_m.shape[-1]); nf = n_m.reshape(-1, n_m.shape[-1])
            for r in range(flat.shape[0]):
                sup = (flat[r] == 1) | (flat[r] == 2); ok = flat[r] == 0
                if sup.sum() == 1 and ok.sum() >= 1:
                    j = np.where(ok)[0][np.argmin(nf[r][ok])]
                    flat[r, j] = 2; changed = True
        if not changed:
            break
    return a.reshape(-1)


def build_table(ind, idx, size, shape):
    grp, iid, name, grade, kind, unit, uni, num, am, desc = ind
    thr = THR[grade]
    n_den = agg(idx, size, uni); w_den = agg(idx, size, uni, w)
    nm = uni & num
    n_num = agg(idx, size, nm); w_num = agg(idx, size, nm, w)
    st = np.zeros(size, np.int8)
    st[n_den == 0] = 3                                            # 대상 없음
    if kind == 'rate':
        bad = (n_den < thr) | (n_num < thr) | ((n_den - n_num) < thr)
        val = np.divide(100 * w_num, w_den, out=np.full(size, np.nan), where=w_den > 0)
        key_n = n_num
    elif kind == 'mean_r':
        s = agg(idx, size, nm, w * am)
        bad = n_num < thr
        val = np.divide(s, w_num, out=np.full(size, np.nan), where=w_num > 0)
        key_n = n_num
    else:                                                          # mean_u
        s = agg(idx, size, uni, w * am)
        bad = n_den < thr
        val = np.divide(s, w_den, out=np.full(size, np.nan), where=w_den > 0)
        key_n = n_den
    st[(st == 0) & bad] = 1
    if len(shape) >= 1 and size > 1:
        st = complement(st, key_n, shape)
    out = {'st': st.tolist(), 'v': [], 'wn': [], 'wd': []}
    if kind != 'rate':
        out['s'] = []
    for i in range(size):
        if st[i] != 0:
            out['v'].append(None); out['wn'].append(None); out['wd'].append(None)
            if kind != 'rate':
                out['s'].append(None)
            continue
        out['v'].append(round(float(val[i]), 1) if kind == 'rate' else sig3(float(val[i])))
        out['wn'].append(sig3(float(w_num[i]))); out['wd'].append(sig3(float(w_den[i])))
        if kind != 'rate':
            out['s'].append(sig3(float(s[i])))
    return out, int((st == 1).sum()), int((st == 2).sum()), int((st == 0).sum())


def city_table(ind):
    grp, iid, name, grade, kind, unit, uni, num, am, desc = ind
    if grade == '다':
        return None
    t, s1, s2, ok = build_table(ind, city, NC, (NC,))
    if grade == '나':                                              # 구간화 단일 지표: 값 대신 5개 구간만 제공
        vals = np.array([x if x is not None else np.nan for x in t['v']], float)
        good = np.isfinite(vals)
        cls = [None] * NC
        if good.sum() >= 5:
            qs = np.quantile(vals[good], [.2, .4, .6, .8])
            for i in range(NC):
                if good[i]:
                    cls[i] = int(np.digitize(vals[i], qs)) + 1
        return {'st': t['st'], 'cls': cls}
    return t


tabs, summary = {}, []
keys = ['']
for r in (1, 2, 3):
    keys += ['|'.join(c) for c in itertools.combinations(ORDER, r)]
for ind in IND:
    iid, grade = ind[1], ind[3]
    T = {}
    n1 = n2 = n0 = 0
    for k in keys:
        dims = k.split('|') if k else []
        if len(dims) > MAXDIM[grade]:
            continue
        idx, size = cell_index(dims)
        shape = tuple(SHAPE[d] for d in dims)
        t, a, b, c = build_table(ind, idx, size, shape)
        T[k] = t; n1 += a; n2 += b; n0 += c
    ct = city_table(ind)
    if ct is not None:
        T['city'] = ct
    tabs[iid] = T
    summary.append({'id': iid, 'name': ind[2], 'grade': grade, 'cells_shown': n0, 'suppressed': n1, 'complementary': n2,
                    'city_shown': None if ct is None else int(sum(1 for x in ct['st'] if x == 0))})

# ───────────────────────── 기준 인구(지표 만들기의 분모) ─────────────────────────
head = (df['head'].values == 1)
hw = df['hhwgt'].astype(float).values
BASE_DEF = [('pop', '전체 인구', ALL, w), ('pop0017', '18세 미만 인구', age < 18, w), ('pop1864', '18~64세 인구', (age >= 18) & (age < 65), w),
            ('pop65', '65세 이상 인구', age >= 65, w), ('hh', '가구 수', head, hw), ('poorpop', '빈곤 인구', poor, w)]
base = {}
for bid, bname, m, ww in BASE_DEF:
    e = {'name': bname}
    for lvl, idx, size in (('', np.zeros(N, np.int64), 1), ('sido', D['sido'], 17), ('city', city, NC)):
        n = agg(idx, size, m); s = agg(idx, size, m, ww)
        e[lvl] = [sig3(float(s[i])) if n[i] >= 10 else None for i in range(size)]
    base[bid] = e

# ───────────────────────── 전 변수 기술통계 ─────────────────────────
cb = pd.read_csv(CB)
cb.columns = ['org', 'prog', 'var', 'label', 'unit', 'desc', 'target', 'note'][:len(cb.columns)]
cbm = {r['var']: r for _, r in cb.iterrows()}
S1 = ('dis', 'disp', 'disvou', 'ltcare', 'nhi', 'aid_medi', 'nbls_medi', 'oldcare')
S2 = ('p', 'h', 'inc', 'labinc', 'dainc', 'binc', 'ybinc', 'fainc', 'othinc', 'pripen', 'pubpen', 'ptax', 'or', 'ee', 'nbls', 'bp', 'itc',
      'evou', 'culvou', 'aid', 'single', 'kua', 'oldwork', 'self', 'rm', 'frm', 'pubedu', 'vetbn')
SKIP = {'pid', 'hid', 'indwgt', 'hhwgt', 'year'}


def var_grade(v):
    if v == 'nhi_type':
        return '가'
    pre = v.split('_')[0]
    if any(v.startswith(x + '_') or v == x for x in S1) or pre in S1:
        return '다'
    if pre in S2 or v.endswith('_amt') or 'amt' in v or v.endswith('_fee'):
        return '나'
    return '가'


variables = []
for v in df.columns:
    if v in SKIP:
        continue
    s = df[v]
    if not pd.api.types.is_numeric_dtype(s) or s.notna().sum() == 0:
        continue
    g = var_grade(v); thr = THR[g]
    m = cbm.get(v, {})
    x = s.astype(float).values; ok = np.isfinite(x)
    unit = str(m.get('unit', '') or '').strip()
    if unit == '원':                                               # 금액은 만원 단위로 환산해 제공
        x = x / 1e4; unit = '만원'
    rec = {'var': v, 'label': str(m.get('label', '') or '').strip(), 'prog': re.sub(r'\s+', ' ', str(m.get('prog', '') or '')).strip(),
           'org': str(m.get('org', '') or '').strip(), 'unit': unit, 'grade': g,
           'has': round(100 * w[ok].sum() / w.sum(), 1) if ok.sum() >= thr else None}
    vals = np.unique(x[ok])
    if len(vals) <= 12:
        cats = []
        for c in vals:
            mm = ok & (x == c)
            n = int(mm.sum())
            cats.append([float(c) if c != int(c) else int(c), round(100 * w[mm].sum() / w[ok].sum(), 1) if n >= thr else None, n])
        sup = [c for c in cats if c[1] is None]
        if len(sup) == 1 and len(cats) > 1:                        # 보충 억제
            j = min((c for c in cats if c[1] is not None), key=lambda c: c[2], default=None)
            if j is not None:
                j[1] = None
        rec['type'] = 'cat'; rec['cats'] = [[c[0], c[1]] for c in cats]
    else:
        nz = ok & (x != 0)
        n = int(nz.sum())
        rec['type'] = 'num'
        rec['nonzero'] = round(100 * w[nz].sum() / w[ok].sum(), 1) if n >= thr and (ok.sum() - n == 0 or ok.sum() - n >= thr) else None
        if n >= 4 * thr:
            xs = x[nz]; ws = w[nz]; oo = np.argsort(xs); cws = np.cumsum(ws[oo]); T_ = cws[-1]
            q = lambda p: float(xs[oo][min(np.searchsorted(cws, T_ * p), len(xs) - 1)])
            rec['mean'] = sig3(float((xs * ws).sum() / T_)); rec['q'] = [sig3(q(.25)), sig3(q(.5)), sig3(q(.75))]
            lo, hi = q(.05), q(.95)
            if hi > lo:
                edges = np.linspace(lo, hi, 9)
                hist = []
                b = np.digitize(xs, edges)
                for k in range(0, 10):
                    mk = b == k
                    hist.append(round(100 * ws[mk].sum() / T_, 1) if mk.sum() >= thr else None)
                rec['edges'] = [sig3(float(e)) for e in edges]; rec['hist'] = hist
    variables.append(rec)

# ───────────────────────── 공개용 집계표(국민용 요약 화면) ─────────────────────────
# 공개 기준: 전국·시도·연령대 단위만, 최소 관측 수 30건(등급과 무관), 교차표·시군구·변수 분포 미제공
PUB = {  # id: (쉬운 이름, 대상 표현)
    'age65': ('65세 이상인 사람', '국민'), 'single': ('혼자 사는 사람', '국민'), 'bp': ('기초연금을 받는 사람', '65세 이상'),
    'nppen': ('국민연금을 받는 사람', '60세 이상'), 'ltc': ('장기요양 서비스를 받는 사람', '65세 이상'), 'live': ('생계급여를 받는 사람', '국민'),
    'medi': ('의료급여 대상인 사람', '국민'), 'np': ('국민연금에 가입한 사람', '18~59세'), 'empins': ('고용보험에 가입한 사람', '18~64세'),
    'jobseek': ('구직급여를 받은 사람', '18~64세'), 'itc': ('근로장려금 대상인 사람', '18세 이상'), 'childcare': ('보육료 지원을 받는 아동', '6세 미만 아동'),
    'dis': ('등록장애인', '국민'), 'poor': ('소득이 중위소득의 절반에 못 미치는 사람', '국민'),
}
pub_tabs = {}
for ind in IND:
    if ind[1] not in PUB:
        continue
    ind30 = ind[:3] + ('다',) + ind[4:]                            # 최소 30건 적용
    T = {}
    for k in ('', 'sido', 'age'):
        dims = [k] if k else []
        idx, size = cell_index(dims)
        t, *_ = build_table(ind30, idx, size, tuple(SHAPE[d] for d in dims))
        T[k] = {'st': t['st'], 'v': t['v']}                        # 비율만 제공(인원·금액 미제공)
    pub_tabs[ind[1]] = T
public = {
    'meta': {'title': '한눈에 보는 사회보장(가상데이터 시연)', 'built': pd.Timestamp.now().strftime('%Y-%m-%d'), 'public': True,
             'thr': {'가': 30, '나': 30, '다': 30}, 'maxdim': {'가': 1, '나': 1, '다': 1}, 'pop': sig3(float(w.sum())),
             'poverty_line': sig3(float(0.5 * median_eq / 1e4)), 'n_var': 0, 'n_person': int(N), 'n_hh': int(df['hid'].nunique()),
             'note': '코드북과 같은 변수 구조로 생성한 가상데이터의 집계값. 실제 통계가 아님'},
    'dims': {k: DIMS[k] for k in ('sido', 'age')}, 'order': ['sido', 'age'],
    'city': {'codes': [], 'names': [], 'sido': []},
    'inds': [{'group': i[0], 'id': i[1], 'name': i[2], 'grade': '다', 'kind': i[4], 'unit': i[5], 'desc': i[9],
              'easy': PUB[i[1]][0], 'who': PUB[i[1]][1]} for i in IND if i[1] in PUB],
    'tabs': pub_tabs, 'base': {}, 'vars': [],
}
Path(OUT).with_name('store_public.json').write_text(json.dumps(public, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

# ───────────────────────── 저장 ─────────────────────────
store = {
    'meta': {'title': '사회보장행정데이터 대시보드(가상데이터 시연)', 'built': pd.Timestamp.now().strftime('%Y-%m-%d'),
             'n_person': int(N), 'n_hh': int(df['hid'].nunique()), 'n_var': int(len(variables)),
             'pop': sig3(float(w.sum())), 'median_eq': sig3(float(median_eq / 1e4)), 'poverty_line': sig3(float(0.5 * median_eq / 1e4)),
             'thr': THR, 'maxdim': MAXDIM,
             'note': '코드북과 같은 변수 구조로 생성한 가상데이터의 집계값. 실제 현황이 아님'},
    'dims': DIMS, 'order': ORDER,
    'city': {'codes': city_codes, 'names': [g['name'] for g in geo['sgg']], 'sido': [g['sido'] for g in geo['sgg']]},
    'inds': [{'group': i[0], 'id': i[1], 'name': i[2], 'grade': i[3], 'kind': i[4], 'unit': i[5], 'desc': i[9]} for i in IND],
    'tabs': tabs, 'base': base, 'vars': variables,
}
Path(OUT).write_text(json.dumps(store, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
pd.DataFrame(summary).to_csv(Path(OUT).with_name('store_출력통제_요약.csv'), index=False, encoding='utf-8-sig')
print(f'store: {Path(OUT).stat().st_size / 1e6:.2f} MB · 지표 {len(IND)} · 변수 {len(variables)} · 인구 {N:,}')
sm = pd.DataFrame(summary)
print(sm[['id', 'grade', 'cells_shown', 'suppressed', 'complementary', 'city_shown']].to_string(index=False))
print('전체 칸: 표시', sm.cells_shown.sum(), '억제', sm.suppressed.sum(), '보충 억제', sm.complementary.sum())
