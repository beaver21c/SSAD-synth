# -*- coding: utf-8 -*-
"""문항 작성자용 검산 도구(자료_규약.md, 문항_양식.md의 정의만 사용). 집계만 산출."""
import numpy as np, pandas as pd

PARQUET = '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
CODEBOOK = '/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/inputs/codebook.tsv'


def wquantile(v, w, q):
    v = np.asarray(v, dtype=float); w = np.asarray(w, dtype=float)
    o = np.argsort(v, kind='mergesort'); v = v[o]; w = w[o]
    c = np.cumsum(w)
    i = int(np.searchsorted(c, q * c[-1], side='left'))
    return v[min(i, len(v) - 1)]


def load():
    df = pd.read_parquet(PARQUET)
    # 파생 변수(자료_규약.md)
    df['hh_dinc'] = df.groupby('hid')['p_dinc'].transform('sum')
    df['eqinc'] = df['hh_dinc'] / np.sqrt(df['hnum'])
    med = wquantile(df['eqinc'], df['indwgt'], 0.5)
    df['poor'] = (df['eqinc'] < 0.5 * med).astype(int)
    # 표준 분류
    df['sex'] = df['gender'].map({1: '남', 2: '여'})
    a = df['age']
    df['age3'] = pd.cut(a, [-1, 17, 64, 200], labels=['0~17세', '18~64세', '65세 이상']).astype(str)
    df['age6'] = pd.cut(a, [-1, 17, 34, 49, 64, 74, 200], labels=['0~17', '18~34', '35~49', '50~64', '65~74', '75+']).astype(str)
    df['age10'] = np.where(a >= 80, '80+', (a // 10 * 10).astype(int).astype(str))
    df['hs4'] = np.where(df['hnum'] >= 4, '4인 이상', df['hnum'].astype(int).astype(str) + '인')
    qs = [wquantile(df['eqinc'], df['indwgt'], q) for q in (0.2, 0.4, 0.6, 0.8)]
    df['inc5'] = 1 + sum((df['eqinc'] >= b).astype(int) for b in qs)
    df['nhi3'] = np.where(df['nhi_type'].isin([1, 2]), '지역', np.where(df['nhi_type'].isin([5, 6]), '직장', '의료급여'))
    df['poor2'] = df['poor'].map({1: '빈곤', 0: '비빈곤'})
    return df


def _by_keys(d, by):
    """분류 기준 목록을 (이름, Series) 목록으로 바꾼다."""
    keys = []
    for b in by:
        if 'std' in b:
            name = {'sido': 'sido'}.get(b['std'], b['std'])
            keys.append((b['std'], d[name]))
        elif 'bins' in b:
            edges = [-np.inf] + list(b['bins']) + [np.inf]
            labels = b['labels']
            assert len(labels) == len(b['bins']) + 1, 'labels 수 불일치'
            s = pd.cut(d[b['var']], edges, right=False, labels=labels)
            keys.append((b['var'] + '_bin', s.astype(object)))
        elif 'cat' in b:
            keys.append((b['cat'], d[b['cat']]))
        elif 'groups' in b:
            s = pd.Series(index=d.index, dtype=object)
            for g in b['groups']:
                m = d.eval(g['cond'], engine='python')
                m = m.fillna(False).astype(bool) if hasattr(m, 'fillna') else m
                assert s[m].isna().all(), '조건 집단이 겹침: ' + g['label']
                s[m] = g['label']
            keys.append(('group', s))
        else:
            raise ValueError(b)
    return keys


def compute(df, spec):
    unit = spec.get('unit', 'person')
    d = df[df['head'] == 1] if unit == 'household' else df
    wcol = 'hhwgt' if unit == 'household' else 'indwgt'
    pop = spec.get('population', '')
    if pop:
        m = d.eval(pop, engine='python')
        d = d[m.fillna(False).astype(bool)]
    d = d.copy()
    d['_w'] = d[wcol]
    meas = spec['measure']
    by = spec.get('by', [])
    keys = _by_keys(d, by)
    for i, (n, s) in enumerate(keys):
        d['_k%d' % i] = s
    kcols = ['_k%d' % i for i in range(len(keys))]
    if meas == 'rate':
        d['_num'] = d.eval(spec['numerator'], engine='python').fillna(False).astype(bool)

    def one(g):
        r = {'n': len(g)}
        if meas == 'count':
            r['value'] = g['_w'].sum()
        elif meas == 'rate':
            r['n_num'] = int(g['_num'].sum()); r['n_comp'] = int((~g['_num']).sum())
            r['value'] = 100 * g.loc[g['_num'], '_w'].sum() / g['_w'].sum() if len(g) else np.nan
        elif meas == 'poverty_rate':
            r['n_num'] = int((g['poor'] == 1).sum()); r['n_comp'] = int((g['poor'] == 0).sum())
            r['value'] = 100 * g.loc[g['poor'] == 1, '_w'].sum() / g['_w'].sum() if len(g) else np.nan
        elif meas in ('mean', 'sum', 'quantile'):
            v = g[spec['value_var']]; ok = v.notna()
            r['n'] = int(ok.sum())
            if ok.sum() == 0:
                r['value'] = np.nan
            elif meas == 'mean':
                r['value'] = (v[ok] * g.loc[ok, '_w']).sum() / g.loc[ok, '_w'].sum()
            elif meas == 'sum':
                r['value'] = (v[ok] * g.loc[ok, '_w']).sum()
            else:
                r['value'] = wquantile(v[ok], g.loc[ok, '_w'], spec['q'])
        return pd.Series(r)

    if meas == 'share':
        vv = spec['value_var']
        d = d[d[vv].notna()]
        gcols = kcols + [vv]
        t = d.groupby(gcols, dropna=True).agg(n=('_w', 'size'), w=('_w', 'sum')).reset_index()
        if kcols:
            t['value'] = 100 * t['w'] / t.groupby(kcols)['w'].transform('sum')
        else:
            t['value'] = 100 * t['w'] / t['w'].sum()
        return t.drop(columns='w')
    if not kcols:
        return pd.DataFrame([one(d)])
    return d.groupby(kcols, dropna=True).apply(one, include_groups=False).reset_index()
