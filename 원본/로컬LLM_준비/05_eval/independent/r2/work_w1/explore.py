# 집계 확인용(개인 단위 행 출력 없음)
import pandas as pd, numpy as np, sys
P = '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
CB = '/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/inputs/codebook.tsv'
df = pd.read_parquet(P)
cb = pd.read_csv(CB, sep='\t', dtype=str).fillna('')
print('shape', df.shape)
cbv = list(cb['var'])
print('codebook vars', len(cbv), 'missing in data', [v for v in cbv if v not in df.columns])
extra = [c for c in df.columns if c not in cbv]
print('data cols not in codebook', len(extra), extra[:120])
print('indwgt sum', df.indwgt.sum(), 'hh n', df.hid.nunique() if 'hid' in df.columns else None, 'hhwgt sum(head)', df.loc[df['head']==1,'hhwgt'].sum(), 'n head', (df['head']==1).sum())
out = []
for _, r in cb.iterrows():
    v = r['var']
    if v not in df.columns: continue
    s = df[v]
    nn = int(s.notna().sum())
    line = f"{v}\t{r['name_ko'][:30]}\t{r['dtype']}\t{r['priority']}\tgrade={r['sensitivity_grade']}\tdtype={s.dtype}\tnn={nn}"
    if r['dtype'] in ('categorical', 'binary') or s.nunique(dropna=True) <= 20:
        vc = s.value_counts(dropna=True).sort_index()
        line += '\tvc=' + '; '.join(f"{k}:{int(c)}" for k, c in vc.items())
    else:
        sn = pd.to_numeric(s, errors='coerce')
        pos = int((sn > 0).sum()); zero = int((sn == 0).sum()); neg = int((sn < 0).sum())
        q = sn[sn > 0].quantile([.1, .5, .9]) if pos > 0 else None
        line += f"\tpos={pos}\tzero={zero}\tneg={neg}"
        if q is not None:
            line += f"\tp10={q.iloc[0]:.4g}\tp50={q.iloc[1]:.4g}\tp90={q.iloc[2]:.4g}"
    out.append(line)
open('/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r2/work_w1/explore_out.tsv', 'w').write('\n'.join(out))
print('written', len(out))
