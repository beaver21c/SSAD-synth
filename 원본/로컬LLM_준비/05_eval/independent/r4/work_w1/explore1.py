import sys
sys.path.insert(0, "/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r4/work_w1")
import numpy as np, pandas as pd
from lib import load, codebook
df = load()
cb = codebook()
print(df.shape, "wsum ind", df.indwgt.sum(), "hh", df.loc[df["head"]==1,"hhwgt"].sum(), "nhh", df.hid.nunique())
missing = [v for v in cb["var"] if v not in df.columns]
print("codebook vars missing in data:", missing)
print("data cols not in codebook:", len([c for c in df.columns if c not in set(cb['var'])]))
# h_dinc vs hh_dinc
print("h_dinc==hh_dinc share:", np.isclose(df.h_dinc, df.hh_dinc).mean())
print("poor rate(w):", np.average(df.poor, weights=df.indwgt))
# yn variable value counts
pd.set_option("display.width", 250)
rows = []
for _, r in cb.iterrows():
    v = r["var"]
    if v not in df.columns: continue
    s = df[v]
    if r["dtype"] in ("categorical", "binary"):
        vc = s.value_counts(dropna=False)
        if len(vc) <= 12:
            rows.append((v, r["name_ko"][:22], r["priority"], dict((("NaN" if pd.isna(k) else (int(k) if isinstance(k,(int,float,np.integer,np.floating)) and float(k).is_integer() else k)), int(c)) for k, c in vc.items())))
        else:
            rows.append((v, r["name_ko"][:22], r["priority"], f"{len(vc)} levels, n_notna={s.notna().sum()}"))
for r in rows:
    print(r)
