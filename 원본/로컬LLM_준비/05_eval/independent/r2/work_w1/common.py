# 공통: 자료 읽기와 파생 변수(자료_규약.md 정의). 집계 확인 전용.
import pandas as pd, numpy as np
P = '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
CB = '/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/inputs/codebook.tsv'

def wquantile(v, w, q):
    v = np.asarray(v, dtype=float); w = np.asarray(w, dtype=float)
    ok = ~np.isnan(v)
    v, w = v[ok], w[ok]
    if len(v) == 0: return np.nan
    o = np.argsort(v, kind='mergesort'); v, w = v[o], w[o]
    c = np.cumsum(w)
    i = int(np.searchsorted(c, q * c[-1], side='left'))
    return v[min(i, len(v) - 1)]

def load():
    cb = pd.read_csv(CB, sep='\t', dtype=str).fillna('')
    df = pd.read_parquet(P)
    df['hh_dinc'] = df.groupby('hid')['p_dinc'].transform('sum')
    df['eqinc'] = df['hh_dinc'] / np.sqrt(df['hnum'])
    med = wquantile(df['eqinc'], df['indwgt'], 0.5)
    df['poor'] = (df['eqinc'] < 0.5 * med).astype(int)
    cuts = [wquantile(df['eqinc'], df['indwgt'], q) for q in (0.2, 0.4, 0.6, 0.8)]
    df['inc5'] = 1 + sum((df['eqinc'] >= c).astype(int) for c in cuts)
    return df, cb
