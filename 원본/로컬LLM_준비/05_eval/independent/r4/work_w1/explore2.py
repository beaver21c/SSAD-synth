import sys
sys.path.insert(0, "/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r4/work_w1")
import numpy as np, pandas as pd
from lib import load, codebook, wquantile
df = load()
cb = codebook()
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 600)
out = []
for _, r in cb.iterrows():
    v = r["var"]
    if r["dtype"] in ("amount", "count", "numeric"):
        s = pd.to_numeric(df[v], errors="coerce")
        nn = s.notna().sum(); pos = (s > 0).sum(); zero = (s == 0).sum(); neg = (s < 0).sum()
        med = s[s.notna()].median() if nn else np.nan
        mean = s.mean() if nn else np.nan
        out.append((v, r["name_ko"][:20], r["priority"], r["sensitivity_grade"], nn, zero, pos, neg, med, mean))
o = pd.DataFrame(out, columns=["var", "name", "P", "g", "notna", "zero", "pos", "neg", "median", "mean"])
print(o.to_string(float_format=lambda x: f"{x:,.0f}"))
