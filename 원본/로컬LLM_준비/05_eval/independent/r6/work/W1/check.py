# -*- coding: utf-8 -*-
"""W1 문서형 과제(6차) 자체 대조.
1) docs.jsonl 형식 확인  2) 산출 정의(specs)를 범용 계산기로 계산
3) 문서 문구에서 다시 풀어 쓴 독립 계산과 대조  4) F 주장 수치와 자료 값 비교
5) 같은 대화 안 대상 차이 집단(관측 30건 미만) 점검  6) 1인당 구성·변형 판 점검
실행: /mnt/share/행정데이터_set/.venv/bin/python check.py > check_output.txt
"""
import json, sys
from collections import Counter
import numpy as np, pandas as pd

HERE = '/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r6/work/W1/'
DATA = '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'

# ------------------------------------------------------------ 1. 형식
docs = []
with open(HERE + 'docs.jsonl', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        docs.append(json.loads(line))
print(f'[형식] docs.jsonl {len(docs)}줄 모두 json 으로 읽힘')
REQ_DOC = ['id', 'doc_type', 'issue', 'facts', 'persona', 'setting', 'document', 'turns', 'items', 'variant_of']
REQ_KIND = {'S': ['specs'], 'F': ['specs', 'claim'], 'G': ['specs', 'param'], 'P': ['specs', 'param'],
            'N': ['absent', 'rubric'], 'V': ['absent', 'rubric'], 'X': ['premise', 'rubric'], 'C': ['rubric'], 'I': ['rubric']}
for d in docs:
    miss = [k for k in REQ_DOC if k not in d]
    assert not miss, (d['id'], miss)
    assert [it['no'] for it in d['items']] == [1, 2, 3, 4, 5], d['id']
    assert d['turns'][0]['items'] == [1, 2, 3, 4] and d['turns'][1]['items'] == [5], d['id']
    for it in d['items']:
        for k in REQ_KIND[it['kind']]:
            assert k in it, (d['id'], it['no'], k)
        assert it['turn'] == (1 if it['no'] <= 4 else 2)
    n = len(d['document'])
    assert 600 <= n <= 1500, (d['id'], n)
    for it in d['items']:   # F 주장 문장과 X 틀린 전제 문장이 문서 본문에 그대로 있는지
        if 'claim' in it: assert it['claim']['text'] in d['document'], (d['id'], it['no'], 'claim')
        if 'premise' in it: assert it['premise']['text'] in d['document'], (d['id'], it['no'], 'premise')
print('[형식] 필수 항목·차례·유형별 필수 키·문서 길이(600~1,500자)·주장/전제 문장의 본문 수록 확인 완료')
print('        문서 길이:', ', '.join(f"{d['id']} {len(d['document'])}자" for d in docs))

# ------------------------------------------------------------ 자료와 파생 변수
df = pd.read_parquet(DATA)

def wq(vals, w, q):
    o = np.argsort(vals, kind='mergesort'); v = np.asarray(vals)[o]; ww = np.asarray(w)[o]
    c = np.cumsum(ww)
    return v[np.searchsorted(c, c[-1] * q, side='left')]

df['hh_dinc'] = df.groupby('hid')['p_dinc'].transform(lambda s: s.fillna(0).sum())
df['eqinc'] = df['hh_dinc'] / np.sqrt(df['hnum'])
_med = wq(df['eqinc'].values, df['indwgt'].values, 0.5)
df['poor'] = (df['eqinc'] < 0.5 * _med).astype(int)
_b = np.array([wq(df['eqinc'].values, df['indwgt'].values, q) for q in (0.2, 0.4, 0.6, 0.8)])
df['inc5'] = np.searchsorted(_b, df['eqinc'].values, side='right')
SIDO = dict(enumerate('서울 부산 대구 인천 광주 대전 울산 세종 경기 강원 충북 충남 전북 전남 경북 경남 제주'.split(), 1))

def std_series(x, name):
    a = x['age']
    if name == 'sido': return x['sido'].map(SIDO)
    if name == 'sex': return x['gender'].map({1: '남', 2: '여'})
    if name == 'age3': return pd.cut(a, [-1, 17, 64, 200], labels=['0~17세', '18~64세', '65세 이상']).astype(str)
    if name == 'age6': return pd.cut(a, [-1, 17, 34, 49, 64, 74, 200], labels=['0~17세', '18~34세', '35~49세', '50~64세', '65~74세', '75세 이상']).astype(str)
    if name == 'hs4': return x['hnum'].clip(upper=4).map({1: '1인', 2: '2인', 3: '3인', 4: '4인 이상'})
    if name == 'inc5': return (x['inc5'] + 1).astype(str) + '분위'
    if name == 'nhi3': return x['nhi_type'].map({1: '지역', 2: '지역', 5: '직장', 6: '직장', 7: '의료급여', 8: '의료급여'})
    if name == 'poor2': return x['poor'].map({0: '비빈곤', 1: '빈곤'})
    raise KeyError(name)

def base(unit):
    return (df, 'indwgt') if unit == 'person' else (df[df['head'] == 1], 'hhwgt')

# ------------------------------------------------------------ 2. 범용 계산기(specs)
def spec_cells(spec):
    d, w = base(spec.get('unit', 'person'))
    if spec.get('population'): d = d.query(spec['population'], engine='python')
    cells = [('전체', d)]
    for b in spec.get('by', []):
        if 'std' in b: s = std_series(d, b['std'])
        elif 'var' in b:
            idx = np.searchsorted(np.array(b['bins']), d[b['var']].values, side='right')
            s = pd.Series(np.array(b['labels'])[idx], index=d.index)
        elif 'cat' in b: s = d[b['cat']]
        cells = [(f'{k}', d[s == k]) for k in sorted(pd.unique(s.dropna()), key=str)]
    return cells, w

def spec_eval(spec):
    cells, w = spec_cells(spec)
    m = spec['measure']; out = {}
    for lab, x in cells:
        if m == 'count':
            out[lab] = (x[w].sum(), len(x), None)
        elif m in ('rate', 'poverty_rate'):
            num = spec['numerator'] if m == 'rate' else 'poor == 1'
            y = x.query(num, engine='python')
            out[lab] = (100 * y[w].sum() / x[w].sum(), len(x), (len(y), len(x) - len(y)))
        elif m == 'mean':
            v = x[spec['value_var']]; ok = v.notna()
            out[lab] = ((v[ok] * x.loc[ok, w]).sum() / x.loc[ok, w].sum(), int(ok.sum()), None)
        elif m == 'share':
            vv = spec['value_var']
            s = std_series(x, vv) if vv in ('sido', 'sex', 'age3', 'age6', 'hs4', 'inc5', 'nhi3', 'poor2') else x[vv]
            tot = x.loc[s.notna(), w].sum()
            for k in sorted(pd.unique(s.dropna()), key=str):
                out[f'{lab}|{k}'] = (100 * x.loc[s == k, w].sum() / tot, int((s == k).sum()), None)
    return out

# ------------------------------------------------------------ 3. 문서 문구에서 다시 풀어 쓴 독립 계산
P = df; H = df[df['head'] == 1]
def wsum(x, col): return x[col].sum()
def wrate(x, cond, col): return 100 * x.loc[cond, col].sum() / x[col].sum()
def wmean(x, v, col):
    ok = x[v].notna(); return (x.loc[ok, v] * x.loc[ok, col]).sum() / x.loc[ok, col].sum()
def age_lab(a, edges, labs): return pd.Series(np.array(labs)[np.searchsorted(np.array(edges), a.values, side='right')], index=a.index)

ind = {}
# D01 1) 시도별 65세 이상 인구 대비 연간 수급자 비율
x = P[P.age >= 65]
ind[('W1-D01', 1, 1)] = {SIDO[k]: wrate(g, g.bp_yn1 == 1, 'indwgt') for k, g in x.groupby('sido')}
# D01 2) 12월 수급자의 수급 유형 구성비
x = P[P.bp_yn2 == 1]
ind[('W1-D01', 2, 1)] = {f'전체|{float(k)}': 100 * g.indwgt.sum() / x.indwgt.sum() for k, g in x.groupby('bp_type')}
# D01 3) 연간 수급자 1인당 연간 급여액 평균
x = P[P.bp_yn1 == 1]; ind[('W1-D01', 3, 1)] = {'전체': wmean(x, 'bp_amt', 'indwgt')}
# D01 4) 12월 기준 단독가구 수급자 수
x = P[(P.bp_yn2 == 1) & (P.bp_type == 1)]; ind[('W1-D01', 4, 1)] = {'전체': wsum(x, 'indwgt')}
# D02 1) 생계급여 수급자 수(개인) / 수급 가구 수(가구원 중 수급자가 있는 가구)
ind[('W1-D02', 1, 1)] = {'전체': wsum(P[P.nbls_live_yn1 == 1], 'indwgt')}
hh_any = P.groupby('hid')['nbls_live_yn1'].apply(lambda s: (s == 1).any())
ind[('W1-D02', 1, 2)] = {'전체': H[H.hid.map(hh_any)].hhwgt.sum()}
# D02 2) 수급 가구의 가구원수 구성비
x = H[H.hid.map(hh_any)]; hs = x.hnum.clip(upper=4).map({1: '1인', 2: '2인', 3: '3인', 4: '4인 이상'})
ind[('W1-D02', 2, 1)] = {f'전체|{k}': 100 * x.loc[hs == k, 'hhwgt'].sum() / x.hhwgt.sum() for k in hs.unique()}
# D02 3) 1인 가구 중 월평균 가처분소득 <= 583,444원 비율 / 그중 미수급 비율
x = H[H.hnum == 1]; low = (x.h_dinc / 12) <= 583444
ind[('W1-D02', 3, 1)] = {'전체': wrate(x, low, 'hhwgt')}
y = x[low]; ind[('W1-D02', 3, 2)] = {'전체': wrate(y, y.nbls_live_yn1 != 1, 'hhwgt')}
# D02 5) 같은 방식, 의료급여 선정기준(1인 월 777,925원)
ind[('W1-D02', 5, 1)] = {'전체': wrate(x, (x.h_dinc / 12) <= 777925, 'hhwgt')}
# D03 1) 근로장려 대상자 중 단독가구 비율
x = P[P.itc_yn == 1]; ind[('W1-D03', 1, 1)] = {'전체': wrate(x, x.itc_hmember == 11, 'indwgt')}
# D03 2) 근로장려 대상자 1인당 심사금액 평균
ind[('W1-D03', 2, 1)] = {'전체': wmean(x, 'itc_amt', 'indwgt')}
# D03 3) EITC 대상자 연령대별 인원
lab = age_lab(x.age, [35, 50, 65], ['34세 이하', '35~49세', '50~64세', '65세 이상'])
ind[('W1-D03', 3, 1)] = {k: x.loc[lab == k, 'indwgt'].sum() for k in lab.unique()}
# D03 4) 자녀장려 대상자 수 / 1인당 자녀장려 심사금액 평균
x = P[P.itc_child_yn == 1]
ind[('W1-D03', 4, 1)] = {'전체': wsum(x, 'indwgt')}; ind[('W1-D03', 4, 2)] = {'전체': wmean(x, 'itc_child_amt', 'indwgt')}
# D04 1) 심한 장애 18세 이상 등록장애인 중 장애인연금 수급률, 성별
x = P[(P.dis_yn == 1) & (P.age >= 18) & (P.dis_grade_1 == 1)]
ind[('W1-D04', 1, 1)] = {{1: '남', 2: '여'}[k]: wrate(g, g.disp_yn1 == 1, 'indwgt') for k, g in x.groupby('gender')}
# D04 2) 장애수당 수급자 수, 18~64세/65세 이상
x = P[P.disp_bn_yn1 == 1]
ind[('W1-D04', 2, 1)] = {'18~64세': x.loc[x.age < 65, 'indwgt'].sum(), '65세 이상': x.loc[x.age >= 65, 'indwgt'].sum()}
# D04 3) 장애인연금 수급자 중 부가급여 구분 「생계·의료급여 수급자」 비율
x = P[P.disp_yn1 == 1]; ind[('W1-D04', 3, 1)] = {'전체': wrate(x, x.disp_extra_type == 5, 'indwgt')}
# D04 4) 장애수당 수급자 1인당 연간 수급액 평균
x = P[P.disp_bn_yn1 == 1]; ind[('W1-D04', 4, 1)] = {'전체': wmean(x, 'disp_bn_amt', 'indwgt')}
# D05 1) 에너지바우처 이용 세대 수, 세대원 수별(세대 단위)
hh_ev = P.groupby('hid')['evou_yn'].apply(lambda s: (s == 1).any())
x = H[H.hid.map(hh_ev)]; hs = x.hnum.clip(upper=4).map({1: '1인', 2: '2인', 3: '3인', 4: '4인 이상'})
ind[('W1-D05', 1, 1)] = {k: x.loc[hs == k, 'hhwgt'].sum() for k in hs.unique()}
# D05 2) 문화누리카드 이용자 1인당 연간 결제액 평균, 연령대별
x = P[P.culvou_yn == 1]; lab = age_lab(x.age, [18, 65], ['6~17세', '18~64세', '65세 이상'])
ind[('W1-D05', 2, 1)] = {k: wmean(x[lab == k], 'culvou_bn', 'indwgt') for k in lab.unique()}
# D05 3) 이용 후 잔액 0원 비율
ind[('W1-D05', 3, 1)] = {'전체': wrate(x, x.culvou_amt == 0, 'indwgt')}
# D06 1)~3) 긴급복지 생계지원 가구
hh_aid = P.groupby('hid')['aid_live_yn1'].apply(lambda s: (s == 1).any())
x = H[H.hid.map(hh_aid)]
ind[('W1-D06', 1, 1)] = {'전체': x.hhwgt.sum()}
ind[('W1-D06', 2, 1)] = {'전체': wmean(x, 'aid_live_amt', 'hhwgt')}
lab = age_lab(x.age, [40, 65], ['39세 이하', '40~64세', '65세 이상'])
ind[('W1-D06', 3, 1)] = {k: x.loc[lab == k, 'hhwgt'].sum() for k in lab.unique()}
# D07 1) 아동양육비 수급자 수 / 1인당 연간 수급액
x = P[P.single_rear_yn1 == 1]
ind[('W1-D07', 1, 1)] = {'전체': wsum(x, 'indwgt')}; ind[('W1-D07', 1, 2)] = {'전체': wmean(x, 'single_rear_amt', 'indwgt')}
# D07 2) 수급자 중 여성 비율
ind[('W1-D07', 2, 1)] = {'전체': wrate(x, x.gender == 2, 'indwgt')}
# D07 4) 자활근로(기초) 참여자 수 / 1인당 연간 급여액
x = P[P.self_yn1 == 1]
ind[('W1-D07', 4, 1)] = {'전체': wsum(x, 'indwgt')}; ind[('W1-D07', 4, 2)] = {'전체': wmean(x, 'self_amt', 'indwgt')}
# D08 1) 주택연금 가입자 1인당 연간 지급액 평균
x = P[P.rm_yn == 1]; ind[('W1-D08', 1, 1)] = {'전체': wmean(x, 'rm_amt', 'indwgt')}
# D08 4) 주택연금 가입자 수, 74세 이하/75세 이상
ind[('W1-D08', 4, 1)] = {'74세 이하': x.loc[x.age <= 74, 'indwgt'].sum(), '75세 이상': x.loc[x.age >= 75, 'indwgt'].sum()}
# D08 2) 가구주 55세 이상 가구 중 주택 보유 가구 비율
x = H[H.age >= 55]; ind[('W1-D08', 2, 1)] = {'전체': wrate(x, x.h_ptax_housing > 0, 'hhwgt')}
# D08 5) 그 가운데 공시가격 9억 원 이하 비율
y = x[x.h_ptax_housing > 0]; ind[('W1-D08', 5, 1)] = {'전체': wrate(y, y.h_ptax_housing <= 9e8, 'hhwgt')}
# D08 3) 65세 이상 재산세 부과 대상자 비율, 연령대별
x = P[P.age >= 65]
ind[('W1-D08', 3, 1)] = {'65~74세': wrate(x[x.age <= 74], x[x.age <= 74].ptax_yn == 1, 'indwgt'),
                         '75세 이상': wrate(x[x.age >= 75], x[x.age >= 75].ptax_yn == 1, 'indwgt')}

# ------------------------------------------------------------ 출력: 칸별 값·관측 수, 독립 계산 대조, F 비교
GRADE = {}
cb = pd.read_csv('/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/inputs/codebook.tsv', sep='\t')
GRADE = dict(zip(cb['var'], cb['sensitivity_grade']))
def fmt(v, m):
    return f'{v:,.1f}%' if m in ('rate', 'share', 'poverty_rate') else (f'{v:,.0f}')

mismatch = 0; low_cells = []
print('\n================ 산출 정의 계산(가중 값, 관측 수)과 독립 계산 대조 ================')
for d in docs:
    if d['variant_of']: continue
    print(f"\n### {d['id']} {d['doc_type']} — {d['issue'][:60]}…")
    for it in d['items']:
        if 'specs' not in it:
            print(f"  [{it['no']}] {it['kind']} (산출 없음) {it['text'][:50]}")
            continue
        for k, sp in enumerate(it['specs'], 1):
            sub = sp.get('sub', k)
            res = spec_eval(sp)
            ref = ind.get((d['id'], it['no'], sub))
            print(f"  [{it['no']}-{sub}] {it['kind']} {sp['measure']}/{sp.get('unit','person')} pop=[{sp.get('population','')}]"
                  + (f" num=[{sp['numerator']}]" if 'numerator' in sp else '') + (f" var={sp['value_var']}" if 'value_var' in sp else ''))
            for lab, (v, n, nk) in res.items():
                r = None if ref is None else ref.get(lab)
                ok = '독립계산 없음' if r is None else ('일치' if abs(r - v) <= 1e-6 * max(1, abs(v)) else f'불일치({r})')
                if r is not None and ok != '일치': mismatch += 1
                extra = f'  분자 {nk[0]}·여집합 {nk[1]}' if nk else ''
                print(f'       {lab:<14} {fmt(v, sp["measure"]):>16}  관측 {n:>6}{extra}  [{ok}]')
                mn = min([n] + (list(nk) if nk else []))
                if mn < 30: low_cells.append((d['id'], it['no'], sub, lab, mn))
            if it['kind'] == 'F':
                c = it['claim']; v = list(res.values())[0][0]
                vv = v / 10000 if c['unit'] == '만원' else v
                diff = vv - c['claimed_value']
                rel = abs(diff) / abs(vv) * 100   # 자료 값 대비 차이율
                verdict = (abs(diff) < 0.05 + 1e-9) if c['unit'] == '%' else (abs(diff) <= 0.5 + 1e-9)
                print(f"       F 주장 {c['claimed_value']}{c['unit']} ↔ 자료 {vv:,.2f}{c['unit']}  차이 {diff:+.2f}"
                      + (f'%p' if c['unit'] == '%' else f' ({rel:.1f}%)') + f"  표기 true={c['true']} / 계산상 일치={verdict}"
                      + ('  [정오 표기 일치]' if verdict == c['true'] else '  [정오 표기 오류]'))
                if verdict != c['true']: mismatch += 1
                if not c['true']:
                    big = abs(diff) >= 3 if c['unit'] == '%' else rel >= 10
                    print(f"       틀린 주장 차이 기준(비율 3%p, 인원·금액 10%) 충족={big}")
                    if not big: mismatch += 1
print(f'\n[대조] 독립 계산·F 정오 불일치 {mismatch}건')
print(f'[관측] 칸·분자·여집합 관측 30건 미만: {low_cells if low_cells else "없음"}')

# ------------------------------------------------------------ 5. 같은 대화 안 대상 차이 집단 점검
print('\n================ 같은 대화 안 대상 차이 집단(관측 30건 미만) 점검 ================')
def idx_sets(sp):
    d, w = base(sp.get('unit', 'person'))
    pop = d.query(sp['population'], engine='python') if sp.get('population') else d
    out = [('pop', set(pop.index))]
    if 'numerator' in sp: out.append(('pop&num', set(pop.query(sp['numerator'], engine='python').index)))
    return sp.get('unit', 'person'), out
bad = 0
for d in docs:
    if d['variant_of']: continue
    sets = []
    for it in d['items']:
        for k, sp in enumerate(it.get('specs', []), 1):
            u, ss = idx_sets(sp)
            for nm, s in ss: sets.append((f"{it['no']}-{sp.get('sub', k)}:{nm}", u, s))
    small = []
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            a, b = sets[i], sets[j]
            if a[1] != b[1] or a[2] == b[2]: continue
            n1, n2 = len(a[2] - b[2]), len(b[2] - a[2])
            if (0 < n1 < 30) or (0 < n2 < 30): small.append((a[0], b[0], n1, n2))
    bad += len(small)
    print(f"  {d['id']}: 비교 집합 {len(sets)}개, 차이 30건 미만 쌍 {small if small else '없음'}")
print(f'[차이 집단] 문제 쌍 {bad}건')

# ------------------------------------------------------------ 6. 1인당 구성·변형 판
orig = [d for d in docs if not d['variant_of']]; var = [d for d in docs if d['variant_of']]
kinds = Counter(it['kind'] for d in orig for it in d['items'])
target = {'S': 18, 'F': 6, 'G': 2, 'P': 2, 'N': 3, 'V': 2, 'X': 2, 'C': 3, 'I': 2}
print('\n================ 1인당 구성 ================')
print('  원판', len(orig), '개 / 항목', sum(kinds.values()), '개 / 변형 판', len(var), '개:', [d['id'] for d in var])
print('  유형별:', {k: kinds.get(k, 0) for k in target}, ' 목표 일치=', all(kinds.get(k, 0) == v for k, v in target.items()))
fs = [it['claim']['true'] for d in orig for it in d['items'] if it['kind'] == 'F']
print(f'  F 맞는 주장 {sum(fs)}개, 틀린 주장 {len(fs) - sum(fs)}개')
print('  영문 표현 항목:', [(d['id'], it['no']) for d in orig for it in d['items'] if it.get('register') == '영문'])
print('  문서 유형:', dict(Counter(d['doc_type'] for d in orig)), ' 종류 수', len(set(d['doc_type'] for d in orig)))
for d in orig:
    sf = sum(it['kind'] in 'SF' for it in d['items']); sf1 = sum(it['kind'] in 'SF' for it in d['items'] if it['turn'] == 1)
    print(f"  {d['id']}: 유형 {''.join(it['kind'] for it in d['items'])}  S·F {sf}개(1차례 {sf1}개)  {'충족' if sf >= 2 and sf1 >= 2 else '미충족'}")
print('\n================ 변형 판 대조(대상·지표·분류·기준값·주장 동일 여부) ================')
for v in var:
    o = [d for d in docs if d['id'] == v['variant_of']][0]
    same = True
    strip = lambda x: {k: val for k, val in x.items() if k != 'text'} if isinstance(x, dict) else x
    for a, b in zip(o['items'], v['items']):
        for key in ('kind', 'specs', 'param', 'absent', 'rubric', 'no', 'turn'):
            if a.get(key) != b.get(key): same = False; print('   차이:', v['id'], a['no'], key)
        for key in ('claim', 'premise'):   # 문장 표현(text)만 바뀌고 수치·정오·바른 사실은 같아야 함
            if strip(a.get(key)) != strip(b.get(key)): same = False; print('   차이:', v['id'], a['no'], key)
    regs = [(a['no'], a.get('register'), b.get('register')) for a, b in zip(o['items'], v['items']) if a.get('register') != b.get('register')]
    print(f"  {v['id']} (원판 {o['id']}): 항목·산출 정의·주장·기준값 동일={same}, 바뀐 표현 {regs}, 문서 길이 {len(v['document'])}자")
    for a, b in zip(o['items'], v['items']):
        if a['kind'] == 'F':
            assert a['claim']['text'] != '' and str(a['claim']['claimed_value']).rstrip('0').rstrip('.') in v['document'].replace(',', ''), (v['id'], '주장 수치가 변형 문서에 없음')
print('\n[끝]')
