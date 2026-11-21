import sys; sys.path.insert(0, '.')
from common import *
df = load()
import pandas as pd
cb = pd.read_csv('/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/inputs/codebook.tsv', sep='\t')
def k2(k):
    if pd.isna(k): return None
    try:
        return int(k) if float(k).is_integer() else k
    except Exception:
        return k
start = False
for _, r in cb.iterrows():
    v = r['var']
    if v == 'oldwork_type1_end_yn': start = True; continue
    if not start: continue
    if r['dtype'] in ('categorical', 'binary'):
        vc = df[v].value_counts(dropna=False)
        try: vc = vc.sort_index()
        except Exception: pass
        if len(vc) <= 20:
            print(v, '|', r['name_ko'], '|', r['sensitivity_grade'], '|', {k2(k): int(n) for k, n in vc.items()})
        else:
            print(v, '|', r['name_ko'], '| n_unique', len(vc))
print('dtypes object:', [c for c in df.columns if df[c].dtype == object][:60])
