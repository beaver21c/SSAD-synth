# r2 독립 문항 확인 스크립트
#  1) A.jsonl·H.jsonl이 JSON Lines로 읽히는지, 양식 항목이 맞는지
#  2) A의 모든 population·numerator·groups[].cond가 DataFrame.eval(engine='python')으로 실행되는지
#  3) 칸별 가중하지 않은 관측 수(비율은 분자·여집합 포함)와 산출값(집계)
#  4) 구성 요건의 개수
# 개인 단위 행은 출력하지 않음(집계만 출력).
import json, os, re, sys, itertools
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ITEMS = os.path.join(HERE, '..', 'items')
PARQUET = '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
CODEBOOK = '/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/inputs/codebook.tsv'
VERBOSE = '-v' in sys.argv

STD_NAMES = ['sido', 'sex', 'age3', 'age6', 'age10', 'hs4', 'inc5', 'nhi3', 'poor2']
MEASURES = ['count', 'rate', 'mean', 'sum', 'quantile', 'share', 'poverty_rate']
DERIVED = {'eqinc', 'hh_dinc', 'poor'}
RESERVED = {'and', 'or', 'not', 'in', 'isna', 'notna', 'True', 'False'}
GRADE_MIN = {'가': 10, '나': 20, '다': 30}


def wquantile(v, w, q):
    v = np.asarray(v, dtype=float); w = np.asarray(w, dtype=float)
    ok = ~np.isnan(v); v, w = v[ok], w[ok]
    if len(v) == 0:
        return np.nan
    o = np.argsort(v, kind='mergesort'); v, w = v[o], w[o]
    c = np.cumsum(w)
    i = int(np.searchsorted(c, q * c[-1], side='left'))
    return v[min(i, len(v) - 1)]


def load():
    cb = pd.read_csv(CODEBOOK, sep='\t', dtype=str).fillna('')
    df = pd.read_parquet(PARQUET)
    # 파생 변수(자료_규약.md)
    df['hh_dinc'] = df.groupby('hid')['p_dinc'].transform('sum')
    df['eqinc'] = df['hh_dinc'] / np.sqrt(df['hnum'])
    med = wquantile(df['eqinc'], df['indwgt'], 0.5)
    df['poor'] = (df['eqinc'] < 0.5 * med).astype(int)
    cuts = [wquantile(df['eqinc'], df['indwgt'], q) for q in (0.2, 0.4, 0.6, 0.8)]
    df['inc5'] = 1 + sum((df['eqinc'] >= c).astype(int) for c in cuts)
    return df, cb


def std_key(d, name):
    if name == 'sido': return d['sido']
    if name == 'sex': return d['gender']
    if name == 'age3': return pd.cut(d['age'], [-1, 17, 64, 999], labels=['0~17', '18~64', '65+']).astype(str)
    if name == 'age6': return pd.cut(d['age'], [-1, 17, 34, 49, 64, 74, 999], labels=['0~17', '18~34', '35~49', '50~64', '65~74', '75+']).astype(str)
    if name == 'age10': return (d['age'] // 10).clip(upper=8)
    if name == 'hs4': return d['hnum'].clip(upper=4)
    if name == 'inc5': return d['inc5']
    if name == 'nhi3': return d['nhi_type'].map({1: '지역', 2: '지역', 5: '직장', 6: '직장', 7: '의료급여', 8: '의료급여'})
    if name == 'poor2': return d['poor']
    raise ValueError(name)


def idents(expr):
    expr = re.sub(r"'[^']*'|\"[^\"]*\"", '', expr or '')
    return [t for t in re.findall(r'[A-Za-z_][A-Za-z0-9_]*', expr) if t not in RESERVED]


def emask(d, expr):
    if expr == '':
        return pd.Series(True, index=d.index)
    m = d.eval(expr, engine='python')
    if str(m.dtype) not in ('bool', 'boolean'):
        raise TypeError('조건식의 결과가 참/거짓이 아님: ' + expr)
    # 결측 허용 정수형(Int64) 변수의 비교 결과는 결측이 섞인 boolean이므로 결측은 거짓으로 봄
    return m.fillna(False).astype(bool)


def dim_cells(d, b):
    if 'std' in b:
        key = std_key(d, b['std'])
        return [(str(k), key == k) for k in sorted(pd.unique(key.dropna()))]
    if 'var' in b:
        v = d[b['var']]
        idx = pd.Series(np.digitize(v.fillna(-np.inf), b['bins']), index=d.index).where(v.notna(), -1)
        return [(b['labels'][i], idx == i) for i in range(len(b['bins']) + 1)]
    if 'cat' in b:
        key = d[b['cat']]
        return [(str(k), key == k) for k in sorted(pd.unique(key.dropna()))]
    if 'groups' in b:
        return [(g['label'], emask(d, g['cond'])) for g in b['groups']]
    raise ValueError('by 항목 형식 오류: %r' % b)


def sig3(x):
    if x is None or (isinstance(x, float) and np.isnan(x)): return 'nan'
    return float('%.3g' % x)


def evaluate(df, s):
    """산출 정의 1개를 실행해 칸별 (라벨, 값, 관측 수 목록)을 돌려줌."""
    hh = s.get('unit', 'person') == 'household'
    base = df[df['head'] == 1] if hh else df
    wcol = 'hhwgt' if hh else 'indwgt'
    d = base[emask(base, s['population'])]
    dims = [dim_cells(d, b) for b in s['by']]
    out = []
    for combo in itertools.product(*dims) if dims else [()]:
        m = pd.Series(True, index=d.index)
        for _, mm in combo:
            m &= mm
        c = d[m]; w = c[wcol]
        label = ' / '.join(l for l, _ in combo) or '전체'
        ms = s['measure']
        if ms == 'count':
            out.append((label, sig3(w.sum()), [len(c)]))
        elif ms == 'rate':
            nm = emask(c, s['numerator'])
            val = 100 * w[nm].sum() / w.sum() if len(c) else np.nan
            out.append((label, round(val, 1) if len(c) else 'nan', [len(c), int(nm.sum()), int(len(c) - nm.sum())]))
        elif ms == 'poverty_rate':
            val = 100 * (w * c['poor']).sum() / w.sum() if len(c) else np.nan
            out.append((label, round(val, 1) if len(c) else 'nan', [len(c), int(c['poor'].sum()), int(len(c) - c['poor'].sum())]))
        elif ms in ('mean', 'sum', 'quantile'):
            v = c[s['value_var']]; ok = v.notna()
            if ms == 'mean':
                val = (v[ok] * w[ok]).sum() / w[ok].sum() if ok.any() else np.nan
            elif ms == 'sum':
                val = (v[ok] * w[ok]).sum()
            else:
                val = wquantile(v, w, s['q'])
            out.append((label, sig3(val), [int(ok.sum())]))
        elif ms == 'share':
            vv = s['value_var']
            key = std_key(c, vv) if vv in STD_NAMES else c[vv]
            for k in sorted(pd.unique(key.dropna())):
                km = key == k
                out.append((label + ' | ' + str(k), round(100 * w[km].sum() / w[key.notna()].sum(), 1), [int(km.sum())]))
    return out


def main():
    problems = []
    # ---------- 1) 파일 읽기와 양식 ----------
    def read_jsonl(name):
        rows = []
        with open(os.path.join(ITEMS, name), encoding='utf-8') as f:
            for i, line in enumerate(f, 1):
                if not line.strip():
                    problems.append('%s %d행: 빈 줄' % (name, i)); continue
                rows.append(json.loads(line))
        return rows
    A = read_jsonl('A.jsonl'); H = read_jsonl('H.jsonl')
    print('A.jsonl %d문항, H.jsonl %d문항 (JSON Lines로 읽힘)' % (len(A), len(H)))
    if [it['id'] for it in A] != ['A%03d' % i for i in range(1, 49)]: problems.append('A id가 A001~A048이 아님')
    if [it['id'] for it in H] != ['H%02d' % i for i in range(1, 9)]: problems.append('H id가 H01~H08이 아님')
    for it in A:
        if it.get('stratum') != 'A' or it.get('expect') != 'compute': problems.append(it['id'] + ': stratum/expect')
        if not it.get('specs'): problems.append(it['id'] + ': specs 없음')
    for it in H:
        if it.get('stratum') != 'H' or it.get('expect') != 'ask_or_assume': problems.append(it['id'] + ': stratum/expect')
        if 'specs' in it: problems.append(it['id'] + ': H 문항에 specs가 있음')
    for it in A + H:
        for k in ('persona', 'turns', 'note'):
            if not it.get(k): problems.append('%s: %s 없음' % (it['id'], k))
        if not (isinstance(it['turns'], list) and all(isinstance(t, str) and t.strip() for t in it['turns'])):
            problems.append(it['id'] + ': turns 형식')

    # ---------- 2) 자료·코드북 ----------
    df, cb = load()
    cbvars = set(cb['var']); pvars = set(cb.loc[cb['priority'] == 'P', 'var'])
    grade = dict(zip(cb['var'], cb['sensitivity_grade']))
    for v in DERIVED | {'inc5'}: grade[v] = grade['p_dinc']
    allowed = cbvars | DERIVED

    # 질문 문장에 변수명이 들어 있지 않은지
    for it in A + H:
        text = ' '.join(it['turns'])
        hit = [t for t in re.findall(r'[A-Za-z_][A-Za-z0-9_]*', text) if t in allowed or '_' in t]
        if hit: problems.append('%s: 질문에 변수명 %s' % (it['id'], hit))

    # ---------- 3) 산출 정의 실행 ----------
    feat = {}
    for it in A:
        f = dict(measure=set(), p_first=False, p_all=True, bins=False, groups=False, hh=False, by2=False, single=False,
                 cond3=False, clause3=False, sido=False, alt=False, min_n=[], all_supp=[], any_supp=[], lt30=[])
        for si, s in enumerate(it['specs']):
            tag = '%s spec%d' % (it['id'], si + 1)
            try:
                if s['measure'] not in MEASURES: raise ValueError('measure ' + s['measure'])
                if s.get('unit', 'person') not in ('person', 'household'): raise ValueError('unit')
                if not isinstance(s.get('population'), str): raise ValueError('population 없음')
                if not isinstance(s.get('by'), list): raise ValueError('by 없음')
                if s['measure'] == 'rate' and not s.get('numerator'): raise ValueError('rate에 numerator 없음')
                if s['measure'] != 'rate' and 'numerator' in s: raise ValueError('rate가 아닌데 numerator가 있음')
                if s['measure'] in ('mean', 'sum', 'quantile', 'share') and not s.get('value_var'): raise ValueError('value_var 없음')
                if s['measure'] == 'quantile' and not (0.05 <= s.get('q', -1) <= 0.95): raise ValueError('q 범위')
                unknown = set(s) - {'turn', 'alt', 'measure', 'unit', 'population', 'numerator', 'value_var', 'q', 'by'}
                if unknown: raise ValueError('양식에 없는 항목 %s' % unknown)
                used = set(idents(s['population'])) | set(idents(s.get('numerator', '')))
                vv = s.get('value_var')
                if vv and not (s['measure'] == 'share' and vv in STD_NAMES): used.add(vv)
                for b in s['by']:
                    if 'std' in b:
                        if b['std'] not in STD_NAMES: raise ValueError('std ' + b['std'])
                    elif 'var' in b:
                        used.add(b['var'])
                        if len(b['labels']) != len(b['bins']) + 1 or list(b['bins']) != sorted(b['bins']): raise ValueError('bins/labels')
                    elif 'cat' in b: used.add(b['cat'])
                    elif 'groups' in b:
                        for g in b['groups']: used |= set(idents(g['cond']))
                    else: raise ValueError('by 형식')
                bad = used - allowed
                if bad: raise ValueError('코드북에 없는 변수 %s' % bad)
                cells = evaluate(df, s)          # population·numerator·groups[].cond를 eval(engine='python')로 실행
            except Exception as e:
                problems.append('%s: %s: %s' % (tag, type(e).__name__, e)); continue
            # 민감도 등급에 따른 최소 관측 수(관련 변수 중 가장 엄격한 등급)
            stdg = {'inc5': '나', 'poor2': '나'}
            gs = [grade[v] for v in used] + [stdg[b['std']] for b in s['by'] if b.get('std') in stdg]
            if s['measure'] == 'poverty_rate' or vv in ('inc5',): gs.append('나')
            thr = max([GRADE_MIN[g] for g in gs] or [10])
            mins = [min(c[2][1:]) if len(c[2]) == 3 else c[2][0] for c in cells]   # 비율: 분자·여집합 중 작은 쪽
            f['min_n'].append(min(mins) if mins else 0)
            f['all_supp'].append(all(m < thr for m in mins)); f['any_supp'].append(any(m < thr for m in mins))
            f['lt30'].append(sum(m < 30 for m in mins))
            f['measure'].add(s['measure'])
            pv = set(idents(s.get('numerator', ''))) | ({vv} if vv else set())
            uses_p = bool(pv & pvars)
            if si == 0: f['p_first'] = uses_p
            f['p_all'] &= uses_p
            f['bins'] |= any('bins' in b for b in s['by']); f['groups'] |= any('groups' in b for b in s['by'])
            f['hh'] |= s.get('unit') == 'household'; f['by2'] |= len(s['by']) >= 2; f['single'] |= len(s['by']) == 0
            pop_vars = set(idents(s['population']))
            f['cond3'] |= len(pop_vars) >= 3
            f['clause3'] |= len(re.split(r'\band\b|\bor\b', s['population'])) >= 3 if s['population'] else False
            f['sido'] |= 'sido' in pop_vars
            f['alt'] |= 'alt' in s
            if VERBOSE:
                print('%s [%s/%s] thr=%d  pop=%r' % (tag, s['measure'], s.get('unit', 'person'), thr, s['population']))
                for label, val, ns in cells:
                    print('      %-28s 값=%s  n=%s' % (label, val, ns))
        if len(f['measure']) != 1: problems.append(it['id'] + ': 문항 안의 measure가 하나가 아님')
        feat[it['id']] = f

    # ---------- 4) 구성 요건 ----------
    ids = [it['id'] for it in A]
    def cnt(pred): return [i for i in ids if i in feat and pred(feat[i])]
    def m(name): return cnt(lambda f: f['measure'] == {name})
    req = [
        ('P 변수를 분자·대상 변수로 사용(첫째 정의 기준)', cnt(lambda f: f['p_first']), 24),
        ('  └ 모든 정의(alt 포함)가 P 변수 사용', cnt(lambda f: f['p_all']), None),
        ('비율(rate)', m('rate'), 16), ('인원·가구 수(count)', m('count'), 6), ('평균(mean)', m('mean'), 8),
        ('합계(sum)', m('sum'), 3), ('분위수(quantile)', m('quantile'), 4), ('구성비(share)', m('share'), 4),
        ('상대 빈곤율(poverty_rate)', m('poverty_rate'), 2),
        ('이용자 지정 구간(bins)', cnt(lambda f: f['bins']), 8), ('조건 집단(groups)', cnt(lambda f: f['groups']), 5),
        ('가구 단위', cnt(lambda f: f['hh']), 4), ('분류 기준 2개', cnt(lambda f: f['by2']), 3),
        ('분류 기준 없는 단일 값', cnt(lambda f: f['single']), 10),
        ('대상 집단 조건 3개 이상(서로 다른 변수 3개 이상)', cnt(lambda f: f['cond3']), 6),
        ('  └ 조건절 3개 이상(and/or 기준)', cnt(lambda f: f['clause3']), None),
        ('특정 시도·시도 묶음으로 대상 한정', cnt(lambda f: f['sido']), 4),
        ('alt 병기 문항', cnt(lambda f: f['alt']), None),
    ]
    print('\n[구성 요건]')
    for name, lst, need in req:
        ok = '' if need is None else ('  (요건 %d 이상: %s)' % (need, '충족' if len(lst) >= need else '미달'))
        print('%-46s %2d%s' % (name, len(lst), ok))
        if need is not None and len(lst) < need: problems.append('구성 요건 미달: ' + name)
        if VERBOSE: print('      ' + ' '.join(lst))
    print('\n[이용자 유형]')
    for k, v in pd.Series([it['persona'] for it in A]).value_counts().items(): print('  %-22s %d' % (k, v))
    print('  (H) ' + ', '.join('%s %d' % kv for kv in pd.Series([it['persona'] for it in H]).value_counts().items()))
    print('\n[억제 예상]  등급별 최소 관측 수(가 10·나 20·다 30, 관련 변수 중 가장 엄격한 등급) 기준')
    full = cnt(lambda f: bool(f['all_supp']) and all(f['all_supp'])); part = cnt(lambda f: any(f['any_supp']) and not all(f['all_supp']))
    print('  모든 칸 억제 예상: ' + ' '.join(full)); print('  일부 칸 억제 예상: ' + ' '.join(part))
    print('  30건 기준으로 본 미달 칸이 있는 문항(등급 기준으로는 표시될 수 있음): ' + ' '.join(i for i in ids if i in feat and max(feat[i]['lt30'] or [0]) > 0 and i not in full + part))
    noted = [it['id'] for it in A if '억제' in it['note']]
    print('  note에 억제 사실을 적은 문항: ' + ' '.join(noted))
    if set(noted) != set(full + part): problems.append('억제 예상 문항과 note 표기가 다름: %s' % sorted(set(noted) ^ set(full + part)))

    print('\n[결과] ' + ('문제 없음' if not problems else '문제 %d건' % len(problems)))
    for p in problems: print('  - ' + p)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
