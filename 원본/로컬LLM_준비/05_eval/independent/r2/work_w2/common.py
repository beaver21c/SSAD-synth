# -*- coding: utf-8 -*-
"""작업자 w2 공용: 분석 자료 읽기, 파생 변수, 산출 정의(spec)의 참값 계산(집계만)."""
import numpy as np, pandas as pd

DATA = '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
_df = None

def wquant(v, w, q):
    v = np.asarray(v, float); w = np.asarray(w, float)
    ok = ~np.isnan(v)
    v, w = v[ok], w[ok]
    if len(v) == 0:
        return np.nan
    o = np.argsort(v, kind='mergesort')
    v, w = v[o], w[o]
    c = np.cumsum(w)
    i = np.searchsorted(c, q * c[-1], side='left')
    i = min(i, len(v) - 1)
    return v[i]

def load():
    global _df
    if _df is not None:
        return _df
    df = pd.read_parquet(DATA)
    hh = df.groupby('hid')['p_dinc'].transform('sum')
    df['hh_dinc'] = hh
    df['eqinc'] = hh / np.sqrt(df['hnum'])
    med = wquant(df['eqinc'], df['indwgt'], 0.5)
    df['poor'] = (df['eqinc'] < 0.5 * med).astype(int)
    # 표준 분류
    df['sex'] = df['gender']
    df['age3'] = pd.cut(df['age'], [-1, 17, 64, 200], labels=['0~17세', '18~64세', '65세 이상']).astype(str)
    df['age6'] = pd.cut(df['age'], [-1, 17, 34, 49, 64, 74, 200], labels=['0~17세', '18~34세', '35~49세', '50~64세', '65~74세', '75세 이상']).astype(str)
    df['age10'] = np.minimum(df['age'] // 10, 8).astype(int)
    df['hs4'] = np.minimum(df['hnum'], 4).astype(int)
    cuts = [wquant(df['eqinc'], df['indwgt'], q) for q in (0.2, 0.4, 0.6, 0.8)]
    df['inc5'] = np.searchsorted(cuts, df['eqinc'].values, side='right') + 1
    df['nhi3'] = np.where(df['nhi_type'].isin([1, 2]), '지역가입', np.where(df['nhi_type'].isin([5, 6]), '직장가입', '의료급여'))
    df['poor2'] = df['poor']
    _df = df
    return df

def _mask(df, cond):
    if cond is None or str(cond).strip() == '':
        return pd.Series(True, index=df.index)
    m = df.eval(cond, engine='python')
    return m.fillna(False).astype(bool)

def by_keys(df, by):
    """분류 기준 목록 → (이름, 범주 시리즈) 목록. 조건 집단은 겹칠 수 있으므로 따로 처리."""
    out = []
    for b in by or []:
        if 'std' in b:
            out.append(('std:' + b['std'], [(str(k), df[b['std']] == k) for k in sorted(df[b['std']].dropna().unique())]))
        elif 'var' in b:
            edges = [-np.inf] + list(b['bins']) + [np.inf]
            cells = []
            for i, lab in enumerate(b['labels']):
                cells.append((lab, (df[b['var']] >= edges[i]) & (df[b['var']] < edges[i + 1])))
            out.append(('bins:' + b['var'], cells))
        elif 'cat' in b:
            out.append(('cat:' + b['cat'], [(str(k), df[b['cat']] == k) for k in sorted(df[b['cat']].dropna().unique())]))
        elif 'groups' in b:
            out.append(('groups', [(g['label'], _mask(df, g['cond'])) for g in b['groups']]))
    return out

def _cells(df, by):
    keys = by_keys(df, by)
    cells = [((), pd.Series(True, index=df.index))]
    for _, cs in keys:
        cells = [(lab + (l,), m & cm) for lab, m in cells for l, cm in cs]
    return cells

def compute(spec, df=None):
    """spec → [(칸 이름, 값, 관측 수 n, 보조 n(rate의 분자·여집합))]"""
    df = load() if df is None else df
    unit = spec.get('unit', 'person')
    if unit == 'household':
        base = df[df['head'] == 1]; wname = 'hhwgt'
    else:
        base = df; wname = 'indwgt'
    pop = _mask(base, spec.get('population', ''))
    d = base[pop]
    w = d[wname]
    m = spec['measure']
    rows = []
    for lab, cm in _cells(d, spec.get('by', [])):
        dd = d[cm]; ww = dd[wname]
        n = len(dd)
        if m == 'count':
            rows.append((lab, ww.sum(), n, None))
        elif m == 'rate':
            nm = _mask(dd, spec['numerator'])
            val = ww[nm].sum() / ww.sum() * 100 if ww.sum() > 0 else np.nan
            rows.append((lab, val, n, (int(nm.sum()), int(n - nm.sum()))))
        elif m in ('mean', 'sum', 'quantile'):
            v = dd[spec['value_var']].astype(float)
            ok = v.notna()
            if m == 'mean':
                val = (v[ok] * ww[ok]).sum() / ww[ok].sum() if ok.sum() else np.nan
            elif m == 'sum':
                val = (v[ok] * ww[ok]).sum()
            else:
                val = wquant(v, ww, spec.get('q', 0.5))
            rows.append((lab, val, int(ok.sum()), None))
        elif m == 'share':
            vv = spec['value_var']
            tot = ww.sum()
            for k in sorted(dd[vv].dropna().unique()):
                km = dd[vv] == k
                rows.append((lab + (str(k),), ww[km].sum() / tot * 100, int(km.sum()), None))
        elif m == 'poverty_rate':
            pm = dd['poor'] == 1
            val = ww[pm].sum() / ww.sum() * 100 if ww.sum() > 0 else np.nan
            rows.append((lab, val, n, (int(pm.sum()), int(n - pm.sum()))))
        else:
            raise ValueError(m)
    return rows

def sig3(x):
    if x is None or (isinstance(x, float) and np.isnan(x)) or x == 0:
        return x
    from math import log10, floor
    return round(x, -int(floor(log10(abs(x)))) + 2)

def shown(spec, val):
    """표시 자릿수: 비율은 소수 첫째 자리, 그 밖은 유효숫자 3자리."""
    if spec['measure'] in ('rate', 'share', 'poverty_rate'):
        return round(val, 1)
    return sig3(val)
