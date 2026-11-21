# -*- coding: utf-8 -*-
"""산출 정의(spec)에서 참값과 칸별 관측 수를 계산하는 확인용 도구(집계만 출력)."""
import math
import numpy as np
import pandas as pd

PARQUET = '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
SIDO = ['서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종', '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주']
_DF = None


def wquantile(v, w, q):
    v = np.asarray(v, dtype=float); w = np.asarray(w, dtype=float)
    ok = ~np.isnan(v)
    v = v[ok]; w = w[ok]
    if len(v) == 0:
        return float('nan')
    o = np.argsort(v, kind='mergesort')
    v = v[o]; w = w[o]
    cw = np.cumsum(w)
    i = int(np.searchsorted(cw, q * cw[-1], side='left'))
    return float(v[min(i, len(v) - 1)])


def load():
    global _DF
    if _DF is not None:
        return _DF
    df = pd.read_parquet(PARQUET)
    hh = df.groupby('hid')['p_dinc'].transform('sum')
    df['hh_dinc'] = hh
    df['eqinc'] = hh / np.sqrt(df['hnum'])
    med = wquantile(df['eqinc'], df['indwgt'], 0.5)
    df['poor'] = (df['eqinc'] < 0.5 * med).astype(int)
    qs = [wquantile(df['eqinc'], df['indwgt'], q) for q in (0.2, 0.4, 0.6, 0.8)]
    df['inc5'] = np.searchsorted(qs, df['eqinc'].values, side='right')
    df['sex'] = df['gender'] - 1
    df['age3'] = np.select([df['age'] < 18, df['age'] < 65], [0, 1], 2)
    df['age6'] = np.select([df['age'] < 18, df['age'] < 35, df['age'] < 50, df['age'] < 65, df['age'] < 75], [0, 1, 2, 3, 4], 5)
    df['age10'] = np.minimum(df['age'] // 10, 8)
    df['hs4'] = np.minimum(df['hnum'], 4) - 1
    df['nhi3'] = np.select([df['nhi_type'].isin([1, 2]), df['nhi_type'].isin([5, 6])], [0, 1], 2)
    df['poor2'] = df['poor']
    df['sido_i'] = df['sido'] - 1
    _DF = df
    return df


STD = {
    'sido': ('sido_i', SIDO),
    'sex': ('sex', ['남', '여']),
    'age3': ('age3', ['0~17세', '18~64세', '65세 이상']),
    'age6': ('age6', ['0~17세', '18~34세', '35~49세', '50~64세', '65~74세', '75세 이상']),
    'age10': ('age10', ['0~9세', '10~19세', '20~29세', '30~39세', '40~49세', '50~59세', '60~69세', '70~79세', '80세 이상']),
    'hs4': ('hs4', ['1인', '2인', '3인', '4인 이상']),
    'inc5': ('inc5', ['1분위', '2분위', '3분위', '4분위', '5분위']),
    'nhi3': ('nhi3', ['지역가입', '직장가입', '의료급여']),
    'poor2': ('poor2', ['비빈곤', '빈곤']),
}


def ev(df, expr):
    if expr is None or str(expr).strip() == '':
        return pd.Series(True, index=df.index)
    r = df.eval(expr, engine='python')
    return pd.Series(np.asarray(r, dtype=object), index=df.index).fillna(False).astype(bool)


def by_keys(df, by):
    """분류 기준마다 (이름, 항목 라벨 Series) 를 돌려줌. 어느 항목에도 속하지 않으면 NaN."""
    out = []
    for b in by or []:
        if 'std' in b:
            col, labels = STD[b['std']]
            s = df[col].map(lambda i: labels[int(i)])
            out.append((b['std'], s, labels))
        elif 'var' in b:
            bins = b['bins']; labels = b['labels']
            assert len(labels) == len(bins) + 1, '구간 라벨 수 불일치'
            idx = np.searchsorted(bins, df[b['var']].values, side='right')
            s = pd.Series([labels[i] for i in idx], index=df.index)
            s[df[b['var']].isna()] = np.nan
            out.append((b['var'], s, labels))
        elif 'cat' in b:
            s = df[b['cat']]
            labels = sorted(s.dropna().unique().tolist())
            out.append((b['cat'], s, labels))
        elif 'groups' in b:
            s = pd.Series(np.nan, index=df.index, dtype=object)
            labels = []
            for g in b['groups']:
                m = ev(df, g['cond'])
                assert not (s.notna() & m).any(), '조건 집단이 겹침: ' + g['label']
                s[m] = g['label']
                labels.append(g['label'])
            out.append(('groups', s, labels))
        else:
            raise ValueError('알 수 없는 분류 기준: %r' % b)
    return out


def sig3(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    if x == 0:
        return 0.0
    d = 2 - int(math.floor(math.log10(abs(x))))
    return round(x, d)


def compute(spec, df=None):
    """칸별 [{'key':(..), 'value':표시값, 'raw':원값, 'n':관측 수, 'shown':30건 이상 여부}] 를 돌려줌."""
    df = load() if df is None else df
    unit = spec.get('unit', 'person')
    wcol = 'indwgt'
    base = df
    if unit == 'household':
        base = df[df['head'] == 1]
        wcol = 'hhwgt'
    pop = base[ev(base, spec.get('population', ''))]
    m = spec['measure']
    keys = by_keys(pop, spec.get('by', []))
    if keys:
        gkey = [k[1] for k in keys]
        groups = list(pop.groupby(gkey, dropna=True, sort=False))
    else:
        groups = [((), pop)]
    cells = []
    for key, g in groups:
        if not isinstance(key, tuple):
            key = (key,)
        w = g[wcol]
        if m == 'count':
            raw = float(w.sum()); n = len(g); val = sig3(raw)
        elif m in ('rate', 'poverty_rate'):
            num = ev(g, spec['numerator']) if m == 'rate' else (g['poor'] == 1)
            a = int(num.sum()); n_all = len(g)
            raw = float(w[num].sum() / w.sum() * 100) if w.sum() > 0 else float('nan')
            n = min(a, n_all - a)
            val = round(raw, 1)
        elif m in ('mean', 'sum', 'quantile'):
            v = g[spec['value_var']].astype(float)
            ok = v.notna(); n = int(ok.sum())
            if m == 'mean':
                raw = float((v[ok] * w[ok]).sum() / w[ok].sum()) if n else float('nan')
            elif m == 'sum':
                raw = float((v[ok] * w[ok]).sum())
            else:
                raw = wquantile(v, w, spec.get('q', 0.5))
            val = sig3(raw)
        elif m == 'share':
            vv = spec['value_var']
            if vv in STD:
                col, labels = STD[vv]; s = g[col].map(lambda i: labels[int(i)])
            else:
                s = g[vv]
            tot = w[s.notna()].sum()
            for cat, gg in g.groupby(s, dropna=True):
                raw = float(gg[wcol].sum() / tot * 100)
                cells.append({'key': key + (cat,), 'value': round(raw, 1), 'raw': raw, 'n': len(gg), 'shown': len(gg) >= 30})
            continue
        else:
            raise ValueError('알 수 없는 measure: ' + m)
        cells.append({'key': key, 'value': val, 'raw': raw, 'n': n, 'shown': n >= 30})
    return cells


def show(spec, title=''):
    cells = compute(spec)
    print('#', title, '|', spec['measure'], spec.get('unit', 'person'), '| pop:', spec.get('population', ''), '| num:', spec.get('numerator', ''), '| var:', spec.get('value_var', ''))
    for c in cells:
        print('   ', c['key'], c['value'], 'n=%d' % c['n'], '' if c['shown'] else '(30건 미만)')
    return cells
