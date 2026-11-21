# -*- coding: utf-8 -*-
"""W4 문서형 과제 점검.

1) docs.jsonl 을 JSON 으로 다시 읽어 형식·구성(유형별 수, F 맞는·틀린 주장, 변형 판)을 확인
2) 모든 산출 정의(S·F·G·P·X)를 pandas 로 직접 계산(칸별 가중 값, 가중하지 않은 관측 수)
3) 문서 문구에서 다시 풀어 쓴 계산(정의 문자열을 쓰지 않은 독립 계산)과 대조
4) F 항목의 주장 수치와 자료 값을 나란히 출력
5) N·V 항목의 부재 근거(codebook.tsv·값없는_사업.tsv·자료 값)를 확인
6) 같은 대화 안 집계 사이의 대상 차이(관측 30건 미만) 점검

실행: /mnt/share/행정데이터_set/.venv/bin/python check.py > check_output.txt
"""
import json, re, sys, itertools
from collections import Counter
import numpy as np
import pandas as pd

BASE = '/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent'
DOCS = f'{BASE}/r6/work/W4/docs.jsonl'
DATA = '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
CODEBOOK = f'{BASE}/inputs/codebook.tsv'
NOVALUE = f'{BASE}/r5/inputs/값없는_사업.tsv'
FACTS = [f'{BASE}/r5/facts/facts_{x}.jsonl' for x in 'ABC']
MINOBS = 30
problems = []

def flag(msg):
    problems.append(msg)
    print('  [문제] ' + msg)

# ------------------------------------------------------------------ 자료와 파생 변수
df = pd.read_parquet(DATA)
df['hh_dinc'] = df.groupby('hid')['p_dinc'].transform('sum')
df['eqinc'] = df['hh_dinc'] / np.sqrt(df['hnum'])

def wquant(v, w, q):
    """가중 분위수: 오름차순 정렬 후 가중치 누적합이 전체의 q배에 처음 이르는 값."""
    v = np.asarray(v, float); w = np.asarray(w, float)
    o = np.argsort(v, kind='mergesort'); cw = np.cumsum(w[o])
    return v[o][np.searchsorted(cw, q * cw[-1], side='left')]

MED = wquant(df['eqinc'], df['indwgt'], 0.5)
df['poor'] = (df['eqinc'] < MED * 0.5).astype(int)
QS = [wquant(df['eqinc'], df['indwgt'], q) for q in (0.2, 0.4, 0.6, 0.8)]
df['inc5'] = np.searchsorted(QS, df['eqinc'].values, side='right')  # 경계값 이상이면 위 분위
INC5_LAB = ['1분위', '2분위', '3분위', '4분위', '5분위']
HEAD = df[df['head'] == 1]
print(f'자료: {len(df):,}행, 가구 {df.hid.nunique():,}, 가중 인구 {df.indwgt.sum():,.0f}, 가중 가구 {HEAD.hhwgt.sum():,.0f}')
print(f'균등화 가처분소득 가중 중위값 {MED:,.0f}원, 빈곤선 {MED*0.5:,.0f}원, 전체 빈곤율 {(df.poor*df.indwgt).sum()/df.indwgt.sum()*100:.2f}%')
print(f'소득 5분위 경계: {[round(x) for x in QS]}')

# ------------------------------------------------------------------ 산출 정의 계산기
STD = {
    'sex': (lambda d: d['gender'].map({1: '남', 2: '여'})),
    'sido': (lambda d: d['sido']),
    'age3': (lambda d: pd.cut(d['age'], [-1, 17, 64, 200], labels=['0~17세', '18~64세', '65세 이상'])),
    'nhi3': (lambda d: np.select([d.nhi_type.isin([1, 2]), d.nhi_type.isin([5, 6]), d.nhi_type.isin([7, 8])], ['지역가입', '직장가입', '의료급여'], None)),
    'hs4': (lambda d: pd.cut(d['hnum'], [0, 1, 2, 3, 100], labels=['1인', '2인', '3인', '4인 이상'])),
    'inc5': (lambda d: d['inc5'].map(dict(enumerate(INC5_LAB)))),
    'poor2': (lambda d: d['poor'].map({0: '비빈곤', 1: '빈곤'})),
}

def classify(d, b):
    if 'std' in b:
        return pd.Series(STD[b['std']](d), index=d.index)
    if 'var' in b:
        edges = [-np.inf] + list(b['bins']) + [np.inf]
        return pd.cut(d[b['var']], edges, right=False, labels=b['labels'])
    if 'cat' in b:
        return d[b['cat']]
    if 'groups' in b:
        lab = pd.Series([None] * len(d), index=d.index, dtype=object)
        for g in b['groups']:
            m = d.eval(g['cond'])
            lab[m & lab.isna()] = g['label']
        return lab
    raise ValueError(b)

def cells_of(spec):
    unit = spec.get('unit', 'person')
    base = df if unit == 'person' else HEAD
    w = 'indwgt' if unit == 'person' else 'hhwgt'
    pop = base.query(spec['population']) if spec.get('population') else base
    by = spec.get('by', [])
    if by:
        keys = [classify(pop, b) for b in by]
        tmp = pop.assign(**{f'_k{i}': k for i, k in enumerate(keys)})
        groups = list(tmp.groupby([f'_k{i}' for i in range(len(by))], observed=True, dropna=True))
        out = [('·'.join(map(str, k if isinstance(k, tuple) else (k,))), g) for k, g in groups]
        out.append(('계', pop))
    else:
        out = [('계', pop)]
    return out, w

def evaluate(spec):
    m = spec['measure']
    cells, w = cells_of(spec)
    res = []
    for lab, g in cells:
        if m == 'count':
            res.append((lab, g[w].sum(), {'n': len(g)}))
        elif m == 'rate':
            num = g.query(spec['numerator'])
            res.append((lab, num[w].sum() / g[w].sum() * 100, {'n_pop': len(g), 'n_num': len(num), 'n_rest': len(g) - len(num)}))
        elif m == 'poverty_rate':
            num = g[g['poor'] == 1]
            res.append((lab, num[w].sum() / g[w].sum() * 100, {'n_pop': len(g), 'n_num': len(num), 'n_rest': len(g) - len(num)}))
        elif m == 'mean':
            v = g[g[spec['value_var']].notna()]
            res.append((lab, (v[spec['value_var']] * v[w]).sum() / v[w].sum(), {'n': len(v)}))
        elif m == 'sum':
            v = g[g[spec['value_var']].notna()]
            res.append((lab, (v[spec['value_var']] * v[w]).sum(), {'n': len(v)}))
        elif m == 'quantile':
            v = g[g[spec['value_var']].notna()]
            res.append((lab, wquant(v[spec['value_var']], v[w], spec['q']), {'n': len(v)}))
        elif m == 'share':
            vv = spec['value_var']
            cat = STD[vv](g) if vv in STD else g[vv]
            tot = g[w][cat.notna()].sum()
            for c in (INC5_LAB if vv == 'inc5' else sorted(cat.dropna().unique())):
                sel = g[cat == c]
                res.append((f'{lab}:{c}', sel[w].sum() / tot * 100, {'n': len(sel)}))
        else:
            raise ValueError(m)
    return res

def mainmin(res):
    """주된 칸의 최소 관측 수(비율은 분자·여집합 포함)."""
    mins = []
    for lab, v, n in res:
        if 'n_pop' in n:
            mins.append(min(n['n_num'], n['n_rest']))
        else:
            mins.append(n['n'])
    return min(mins)

# ------------------------------------------------------------------ 독립 계산(문서 문구에서 다시 풀어 씀)
P = df; H = HEAD
def W(s, w='indwgt'): return s[w].sum()
def R(s, m, w='indwgt'): return s.loc[m, w].sum() / s[w].sum() * 100
def M(s, v, w='indwgt'): return (s[v] * s[w]).sum() / s[w].sum()
LINE30 = {1: 583444, 2: 978026, 3: 1258410, 4: 1536324, 5: 1807355, 6: 2072101}  # A04 2022 생계급여 선정기준(월)

def manual():
    """키: (문서, 항목, sub) → {칸: 값}. 산출 정의 문자열을 쓰지 않고 문서 문구대로 마스크를 다시 만듦."""
    o = {}
    # D01 ① 연간 아동수당 수급 아동, 연령 0~5/6/7
    c = P[P.childbn_yn1 == 1]
    o[('W4-D01', 1, None)] = {'만 0~5세': W(c[c.age.between(0, 5)]), '만 6세': W(c[c.age == 6]), '만 7세': W(c[c.age == 7]), '계': W(c)}
    # D01 ② 12월 기준 수급 아동 수, 만 8세 미만 대비 비율
    o[('W4-D01', 2, 1)] = {'계': W(P[P.childbn_yn2 == 1])}
    u8 = P[P.age < 8]; o[('W4-D01', 2, 2)] = {'계': R(u8, u8.childbn_yn2 == 1)}
    # D01 ③ 1인당 평균 지급액
    o[('W4-D01', 3, None)] = {'계': M(c, 'childbn_amt')}
    # D02 ① 영아수당 연간 수급 아동 수
    inf = P[P.infantbn_yn1 == 1]; car = P[P.carebn_yn1 == 1]
    o[('W4-D02', 1, None)] = {'계': W(inf)}
    o[('W4-D02', 2, None)] = {'계': R(car, car.age == 1)}
    for sub, s in ((1, inf), (2, car)):
        o[('W4-D02', 3, sub)] = {f'계:{INC5_LAB[q]}': R(s, s.inc5 == q) for q in range(5)}
    o[('W4-D02', 4, None)] = {'계': M(inf, 'infantbn_amt')}
    # D03
    for sub, s in ((1, P[P.childcare_yn1 == 1]), (2, P[P.childcare_yn2 == 1])):
        o[('W4-D03', 1, sub)] = {'만 0~2세': W(s[s.age <= 2]), '만 3세 이상': W(s[s.age >= 3]), '계': W(s)}
    a01 = P[P.age.isin([0, 1])]; cash = (a01.carebn_yn1 == 1) | (a01.infantbn_yn1 == 1)
    o[('W4-D03', 2, None)] = {'만 0세': R(a01[a01.age == 0], cash[a01.age == 0]), '만 1세': R(a01[a01.age == 1], cash[a01.age == 1]), '계': R(a01, cash)}
    cc = P[P.childcare_yn1 == 1]
    o[('W4-D03', 3, None)] = {'만 0~2세': M(cc[cc.age <= 2], 'childcare_amt'), '만 3세 이상': M(cc[cc.age >= 3], 'childcare_amt'), '계': M(cc, 'childcare_amt')}
    # D04
    pl = P[P.empins_parentleave_yn1 == 1]
    o[('W4-D04', 1, None)] = {'남': W(pl[pl.gender == 1]), '여': W(pl[pl.gender == 2]), '계': W(pl)}
    o[('W4-D04', 2, None)] = {'계': R(pl, pl.gender == 1)}
    ml = P[P.empins_matleave_yn1 == 1]
    o[('W4-D04', 3, 1)] = {'계': W(ml)}; o[('W4-D04', 3, 2)] = {'계': M(ml, 'empins_matleave_amt')}
    p2 = P[P.empins_parentleave_yn2 == 1]
    o[('W4-D04', 5, None)] = {'만 29세 이하': W(p2[p2.age <= 29]), '만 30~34세': W(p2[p2.age.between(30, 34)]), '만 35세 이상': W(p2[p2.age >= 35]), '계': W(p2)}
    # D05
    sr = P[P.single_rear_yn1 == 1]
    o[('W4-D05', 1, None)] = {'남': W(sr[sr.gender == 1]), '여': W(sr[sr.gender == 2]), '계': W(sr)}
    o[('W4-D05', 2, None)] = {'계': R(sr, sr.nbls_live_yn1 == 1)}
    o[('W4-D05', 3, None)] = {'계': M(sr, 'single_rear_amt')}
    se = P[P.single_extra_yn1 == 1]
    o[('W4-D05', 5, 1)] = {'계': W(se)}; o[('W4-D05', 5, 2)] = {'계': M(se, 'single_extra_amt')}
    # D06 (가구 단위: 가구주 행, 가구 가중치)
    al = H[H.aid_live_yn1 == 1]
    o[('W4-D06', 1, None)] = {'1인 가구': W(al[al.hnum == 1], 'hhwgt'), '2인 이상 가구': W(al[al.hnum >= 2], 'hhwgt'), '계': W(al, 'hhwgt')}
    h6 = H[H.hnum <= 6]
    below = h6[h6.hh_dinc / 12 <= h6.hnum.map(LINE30)]
    nr = below.nbls_live_yn1 != 1
    o[('W4-D06', 2, None)] = {'1인': R(below[below.hnum == 1], nr[below.hnum == 1], 'hhwgt'), '2인': R(below[below.hnum == 2], nr[below.hnum == 2], 'hhwgt'),
                              '3~6인': R(below[below.hnum >= 3], nr[below.hnum >= 3], 'hhwgt'), '계': R(below, nr, 'hhwgt')}
    hp = H[H.poor == 1]
    o[('W4-D06', 3, None)] = {'계': R(hp, hp.nbls_live_yn1 == 1, 'hhwgt')}
    ds = P[P.nhi_disentitle_yn == 1]
    reg = ds.nhi_type.isin([1, 2]); job = ds.nhi_type.isin([5, 6])
    o[('W4-D06', 4, None)] = {'지역가입': R(ds[reg], ds[reg].poor == 1), '직장가입': R(ds[job], ds[job].poor == 1), '계': R(ds, ds.poor == 1)}
    # D07 (65세 이상 1인 가구, 가구 단위)
    ol = H[(H.hnum == 1) & (H.age >= 65)]
    o[('W4-D07', 1, 1)] = {'계': R(ol, ol.poor == 1, 'hhwgt')}
    o[('W4-D07', 1, 2)] = {'남': R(ol[ol.gender == 1], ol[ol.gender == 1].poor == 1, 'hhwgt'), '여': R(ol[ol.gender == 2], ol[ol.gender == 2].poor == 1, 'hhwgt'), '계': R(ol, ol.poor == 1, 'hhwgt')}
    o[('W4-D07', 2, None)] = {'계': R(ol, ol.hh_dinc / 12 <= 972406, 'hhwgt')}
    o[('W4-D07', 3, None)] = {'계': R(ol, (ol.bp_yn1 == 1) & (ol.np_pension_yn == 1), 'hhwgt')}
    o[('W4-D07', 4, None)] = {'남': wquant(ol[ol.gender == 1].hh_dinc, ol[ol.gender == 1].hhwgt, .5), '여': wquant(ol[ol.gender == 2].hh_dinc, ol[ol.gender == 2].hhwgt, .5), '계': wquant(ol.hh_dinc, ol.hhwgt, .5)}
    # D08 (서울)
    sy = P[(P.sido == 1) & P.age.between(19, 34) & (P.p_labinc > 0)]
    ni = sy.empins_yn1 != 1
    o[('W4-D08', 1, None)] = {'남': R(sy[sy.gender == 1], ni[sy.gender == 1]), '여': R(sy[sy.gender == 2], ni[sy.gender == 2]), '계': R(sy, ni)}
    sj = P[(P.sido == 1) & P.age.between(19, 34) & (P.np_type == 1)]
    o[('W4-D08', 2, None)] = {'계': R(sj, sj.np_status == 3)}
    o[('W4-D08', 3, 1)] = {'계': W(sy[sy.p_labinc <= 36_000_000])}
    o[('W4-D08', 3, 2)] = {'계': R(sy, sy.p_labinc <= 36_000_000)}
    y1 = H[(H.sido == 1) & (H.hnum == 1) & H.age.between(19, 34)]
    o[('W4-D08', 4, None)] = {'계': R(y1, y1.hh_dinc / 12 <= 1166887, 'hhwgt')}
    return o

MAN = manual()

# ------------------------------------------------------------------ 1. 형식
print('\n=== 1. docs.jsonl 형식 ===')
raw = open(DOCS, encoding='utf-8').read().splitlines()
docs = [json.loads(l) for l in raw if l.strip()]
print(f'줄 수 {len(raw)}, 문서 {len(docs)}개, 모두 JSON 으로 읽힘')
facts = {}
for f in FACTS:
    for l in open(f, encoding='utf-8'):
        if l.strip():
            r = json.loads(l); facts[r['id']] = r
cb = pd.read_csv(CODEBOOK, sep='\t', dtype=str)
VARS = set(cb['var'])
NEED = ['id', 'doc_type', 'issue', 'facts', 'persona', 'setting', 'document', 'turns', 'items', 'variant_of']
for d in docs:
    miss = [k for k in NEED if k not in d]
    if miss: flag(f"{d['id']} 누락 필드 {miss}")
    for fid in d['facts']:
        if fid not in facts: flag(f"{d['id']} 없는 사실 id {fid}")
        elif facts[fid]['status'] != 'official' or fid == 'B30': flag(f"{d['id']} 쓰면 안 되는 사실 {fid}")
    L = len(d['document'])
    toks = set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', d['document']))
    leaked = sorted(t for t in toks if t in VARS)
    print(f"{d['id']:9s} {d['doc_type']:10s} 문서 {L:5d}자  사실 {d['facts']}  변수명 노출 {leaked or '없음'}")
    if not 600 <= L <= 1500: flag(f"{d['id']} 문서 길이 {L}")
    if leaked: flag(f"{d['id']} 문서에 변수명 {leaked}")
    if [i['no'] for i in d['items']] != [1, 2, 3, 4, 5]: flag(f"{d['id']} 항목 번호")
    if d['turns'][0]['items'] != [1, 2, 3, 4] or d['turns'][1]['items'] != [5]: flag(f"{d['id']} 차례 구성")
    for it in d['items']:
        k = it['kind']
        req = {'S': ['specs'], 'F': ['specs', 'claim'], 'G': ['specs', 'param'], 'P': ['specs', 'param'], 'N': ['absent', 'rubric'],
               'V': ['absent', 'rubric'], 'X': ['premise', 'rubric'], 'C': ['rubric'], 'I': ['rubric']}[k]
        for r in req:
            if r not in it: flag(f"{d['id']}-{it['no']} {k} 항목에 {r} 없음")
        if k in 'SFGPX' and it.get('register') not in ('공식', '약칭', '서술', '영문'): flag(f"{d['id']}-{it['no']} register")
        if it['turn'] != (1 if it['no'] <= 4 else 2): flag(f"{d['id']}-{it['no']} turn")

# ------------------------------------------------------------------ 2. 구성
print('\n=== 2. 1인당 구성(원판 8개) ===')
orig = [d for d in docs if d['variant_of'] is None]
var = [d for d in docs if d['variant_of']]
kinds = Counter(it['kind'] for d in orig for it in d['items'])
target = {'S': 18, 'F': 6, 'G': 2, 'P': 2, 'N': 3, 'V': 2, 'X': 2, 'C': 3, 'I': 2}
print('유형별 항목 수:', {k: kinds.get(k, 0) for k in target}, '합', sum(kinds.values()))
for k, v in target.items():
    if kinds.get(k, 0) != v: flag(f'유형 {k}: {kinds.get(k, 0)}개(목표 {v})')
fs = [it for d in orig for it in d['items'] if it['kind'] == 'F']
nt = sum(it['claim']['true'] for it in fs); print(f'F 맞는 주장 {nt}, 틀린 주장 {len(fs) - nt}')
if nt != 3 or len(fs) - nt != 3: flag('F 맞는·틀린 주장 수')
print('변형 판:', [(d['id'], d['variant_of']) for d in var])
if len(var) != 3: flag('변형 판 수')
regs = Counter(it['register'] for d in orig for it in d['items'] if it['kind'] in 'SFGPX')
print('원판 register:', dict(regs))
if regs.get('영문', 0) != 1: flag('영문 register 1개가 아님')
print('문서 유형:', dict(Counter(d['doc_type'] for d in orig)))
if len(set(d['doc_type'] for d in orig)) < 4: flag('문서 유형 4종 미만')
for d in docs:
    sf = sum(it['kind'] in 'SF' for it in d['items']); sf1 = sum(it['kind'] in 'SF' for it in d['items'] if it['turn'] == 1)
    print(f"{d['id']:9s} 유형 {''.join(it['kind'] for it in d['items'])}  S·F {sf}(1차례 {sf1})  register {[it['register'] for it in d['items']]}")
    if sf < 2 or sf1 < 2: flag(f"{d['id']} S·F 수")

# 변형 판과 원판의 동일성(대상·지표·분류·기준값·주장 수치)
print('\n변형 판 대조:')
byid = {d['id']: d for d in docs}
for d in var:
    o = byid[d['variant_of']]
    for a, b in zip(o['items'], d['items']):
        same = (a['no'] == b['no'] and a['kind'] == b['kind'] and a.get('specs') == b.get('specs')
                and (a.get('claim') or {}).get('claimed_value') == (b.get('claim') or {}).get('claimed_value')
                and (a.get('claim') or {}).get('true') == (b.get('claim') or {}).get('true')
                and a.get('param') == b.get('param') and (a.get('premise') or {}).get('wrong') == (b.get('premise') or {}).get('wrong')
                and a.get('absent') == b.get('absent'))
        chg = []
        if a.get('register') != b.get('register'): chg.append(f"register {a.get('register')}→{b.get('register')}")
        if a['text'] != b['text']: chg.append('문구')
        print(f"  {d['id']}-{b['no']} {b['kind']} 정의·주장 동일={same}  바뀐 것: {', '.join(chg) or '없음'}")
        if not same: flag(f"{d['id']}-{b['no']} 원판과 정의·주장 다름")
    if o['document'] == d['document']: flag(f"{d['id']} 문서가 원판과 같음")
    if [t['q'] for t in o['turns']] == [t['q'] for t in d['turns']]: flag(f"{d['id']} 요청 문장이 원판과 같음")

# ------------------------------------------------------------------ 3. 산출 정의 계산과 독립 계산 대조
print('\n=== 3. 산출 정의 계산(칸: 가중 값 [관측 수]) 과 독립 계산 대조 ===')
def fmt(v, m):
    return f'{v:,.1f}' if m in ('rate', 'share', 'poverty_rate') else f'{v:,.0f}'
values = {}
for d in orig:
    print(f"\n[{d['id']}] {d['issue']}")
    for it in d['items']:
        if 'specs' not in it: continue
        for sp in it['specs']:
            res = evaluate(sp)
            key = (d['id'], it['no'], sp.get('sub'))
            values[key] = res
            unitlab = {'count': '명' if sp.get('unit', 'person') == 'person' else '가구', 'rate': '%', 'share': '%', 'poverty_rate': '%', 'mean': '원', 'quantile': '원', 'sum': '원'}[sp['measure']]
            cells = []
            for lab, v, n in res:
                ns = f"분자 {n['n_num']}·여집합 {n['n_rest']}·대상 {n['n_pop']}" if 'n_pop' in n else f"{n['n']}"
                cells.append(f"{lab}: {fmt(v, sp['measure'])}{unitlab} [{ns}]")
            mm = mainmin(res)
            print(f"  ④{it['no']}{'-'+str(sp['sub']) if sp.get('sub') else ''} {it['kind']} {sp['measure']}/{sp.get('unit','person')}  " + ' | '.join(cells) + f"  → 주된 칸 최소 관측 {mm}")
            if mm < MINOBS: flag(f"{key} 주된 칸 관측 {mm} < {MINOBS}")
            man = MAN.get(key)
            if man is None:
                flag(f'{key} 독립 계산 없음')
            else:
                got = {lab: v for lab, v, n in res}
                diffs = [(k, man[k], got.get(k)) for k in man if got.get(k) is None or abs(man[k] - got[k]) > 1e-6 * max(1, abs(man[k]))]
                extra = [k for k in got if k not in man]
                print(f"     독립 계산 대조: {'일치' if not diffs and not extra else '불일치 ' + str(diffs) + ' 추가칸 ' + str(extra)}")
                if diffs or extra: flag(f'{key} 독립 계산 불일치')

# ------------------------------------------------------------------ 4. F 주장 대조
print('\n=== 4. F 항목: 주장 수치와 자료 값 ===')
for d in docs:
    for it in d['items']:
        if it['kind'] != 'F': continue
        c = it['claim']
        v = [x for x in values[(d['variant_of'] or d['id'], it['no'], None)] if x[0] == '계'][0][1]
        if c['unit'] == '만원': dv = v / 1e4
        else: dv = v
        if c['unit'] == '%':
            gap = c['claimed_value'] - dv; same = abs(round(dv, 1) - c['claimed_value']) < 1e-9; ok_false = abs(gap) >= 3
            gap_s = f'{gap:+.1f}%p'
        else:
            gap = (c['claimed_value'] - dv) / dv * 100
            same = abs(round(dv, 1 if c['unit'] == '만원' else -3) - c['claimed_value']) < 1e-6 if c['unit'] == '만원' else abs(gap) < 0.5
            ok_false = abs(gap) >= 10; gap_s = f'{gap:+.1f}%'
        verdict = '맞음' if same else '틀림'
        print(f"  {d['id']}-{it['no']} 주장 {c['claimed_value']:,}{c['unit']} | 자료 {dv:,.4f}{c['unit']} | 차이 {gap_s} | 자료 판정 {verdict} | 기재 true={c['true']}")
        if c['true'] != same: flag(f"{d['id']}-{it['no']} F 판정 불일치")
        if not c['true'] and not ok_false: flag(f"{d['id']}-{it['no']} 틀린 주장의 차이가 작음")

# G·P 기준값의 사실 목록 대조
print('\n=== 5. G·P 기준값과 사실 목록 ===')
for d in orig:
    for it in d['items']:
        if it['kind'] not in 'GP': continue
        p = it['param']; fnum = json.dumps(facts[p['fact']]['numbers'], ensure_ascii=False)
        vals = list(p['value'].values()) if isinstance(p['value'], dict) else [p['value']]
        found = all(re.search(rf'(?<!\d){v}(?!\d)', fnum) or str(v // 10000) in fnum for v in vals)
        in_doc = any(f'{v:,}' in d['document'] or f'{v//10000:,}만 원' in d['document'] or f'{v//10000:,}만원' in d['document'] for v in vals)
        print(f"  {d['id']}-{it['no']} {it['kind']} {p['name']}: {p['value']} ({p['fact']} 수치에 있음={bool(found)}, 문서에 기준값 있음={in_doc}, 기재 in_document={p['in_document']})")
        if not found: flag(f"{d['id']}-{it['no']} 기준값이 사실 목록에 없음")
        if in_doc != p['in_document']: flag(f"{d['id']}-{it['no']} G/P 구분과 문서 기재 불일치")
        if it['kind'] == 'P' and p['in_document']: flag('P 항목인데 문서에 기준값')

# ------------------------------------------------------------------ 6. N·V 부재 근거
print('\n=== 6. N·V 항목의 부재 근거 ===')
nov = pd.read_csv(NOVALUE, sep='\t', dtype=str)
KEYS = {'첫만남이용권': ['첫만남'], '3+3 부모육아휴직제': ['3+3', '부모육아'], '청년월세 한시 특별지원': ['청년월세'],
        '아이돌봄서비스': ['아이돌봄'], '청소년 한부모가족지원 아동양육비': ['청소년 한부모가족지원 아동양육비']}
for d in orig:
    for it in d['items']:
        if it['kind'] not in 'NV': continue
        a = it['absent']; prog = a['program']
        hits = cb[cb.apply(lambda r: any(k in str(r['name_ko']) or k in str(r['program']) for k in KEYS[prog]), axis=1)]
        inv = nov[nov['사업'].str.contains(prog, regex=False)]
        msg = f"  {d['id']}-{it['no']} {it['kind']} {prog}({a['fact']}, 사실 목록 실재={a['fact'] in facts}): codebook 해당 변수 {list(hits['var'])}, 값없는_사업 {len(inv)}건"
        if it['kind'] == 'V' and len(hits):
            nz = {v: int((df[v].fillna(0) != 0).sum()) for v in hits['var'] if v in df}
            msg += f", 자료 값이 0이 아닌 행 {nz}"
            if any(nz.values()): flag(f'{prog} 자료에 값 있음')
        print(msg)
        if it['kind'] == 'N' and len(hits): flag(f'{prog} codebook 에 변수 있음')
        if it['kind'] == 'V' and not len(inv): flag(f'{prog} 값없는_사업에 없음')
        if a['fact'] not in facts: flag(f'{prog} 사실 목록 근거 없음')

# ------------------------------------------------------------------ 7. 같은 대화 안 대상 차이
print('\n=== 7. 같은 대화 안 집계 대상의 차이(관측 1~29건이면 문제) ===')
def masks(sp):
    unit = sp.get('unit', 'person'); base = df if unit == 'person' else HEAD
    pop = base.eval(sp['population']) if sp.get('population') else pd.Series(True, index=base.index)
    out = [('대상', pop)]
    if sp['measure'] in ('rate', 'poverty_rate'):
        num = base.eval(sp['numerator']) if sp['measure'] == 'rate' else (base['poor'] == 1)
        out.append(('분자', pop & num))
        out.append(('여집합', pop & ~num))
    return unit, base, out
def bykey(b): return json.dumps(b, ensure_ascii=False, sort_keys=True)
for d in orig:
    sets = []
    for it in d['items']:
        for sp in it.get('specs', []):
            u, base, ms = masks(sp)
            for nm, m in ms:
                sets.append((f"④{it['no']}{'-'+str(sp['sub']) if sp.get('sub') else ''}{nm}", u, base, m, [bykey(b) for b in sp.get('by', [])], sp.get('by', [])))
    small, ref = [], []
    for (a, ua, base, ma, ka, ba), (b, ub, _, mb, kb, bb) in itertools.combinations(sets, 2):
        if ua != ub: continue
        if (ma & ~mb).sum() == 0 or (mb & ~ma).sum() == 0:  # 포함 관계
            n = int((ma ^ mb).sum())
            if 0 < n < MINOBS: small.append((a, b, n))
            # 칸별 차이: 두 집계가 같은 분류를 쓰면 문제, 한쪽만 쓰면 참고
            for bdef in {bykey(x): x for x in ba + bb}.values():
                lab = classify(base, bdef)
                diff = (ma ^ mb)
                cell = diff.groupby(lab).sum()
                bad = {str(k): int(v) for k, v in cell.items() if 0 < v < MINOBS}
                if bad:
                    (small if (bykey(bdef) in ka and bykey(bdef) in kb) else ref).append((a, b, bad))
    print(f"  {d['id']}: 포함 관계 집합 쌍 중 차이 1~29건(같은 분류 칸 포함) {small or '없음'}")
    if ref: print(f"     참고(한쪽 집계만 그 분류를 씀, 요청되지 않은 교차): {ref}")
    if small: flag(f"{d['id']} 작은 대상 차이 {small}")
# 문서별로 미리 알려진 위험 지점의 직접 확인
print('  참고: 12월 기준과 연간 기준의 차이(관측 수)')
for v1, v2, nm in [('childbn_yn1', 'childbn_yn2', '아동수당'), ('childcare_yn1', 'childcare_yn2', '보육료'), ('empins_parentleave_yn1', 'empins_parentleave_yn2', '육아휴직급여'),
                   ('single_rear_yn1', 'single_rear_yn2', '아동양육비')]:
    print(f"   {nm}: 연간 {int((df[v1]==1).sum())}, 12월 {int((df[v2]==1).sum())}, 차이 {int(((df[v1]==1)&(df[v2]!=1)).sum())}")

print('\n=== 결과 ===')
print('문제 없음' if not problems else f'문제 {len(problems)}건: ' + '; '.join(problems))
