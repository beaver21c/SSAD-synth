import sys, json
sys.path.insert(0, "/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r4/work_w1")
import numpy as np, pandas as pd
from lib import load, codebook
from runner import run_spec, vars_in, GRADE_MIN
from items_def import A
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
print("pandas", pd.__version__)
df = load(); cb = codebook().set_index("var")
only = sys.argv[1:] 
for it in A:
    if only and it["id"] not in only: continue
    for k, sp in enumerate(it["specs"]):
        vs = vars_in(sp, set(cb.index))
        thr = max([GRADE_MIN.get(cb.loc[v, "sensitivity_grade"], 10) for v in vs] or [10])
        print(f"\n== {it['id']} spec{k+1} {sp['measure']} unit={sp['unit']} thr={thr} vars={vs}")
        try:
            out = run_spec(df, sp)
            print(out.assign(value=out["value"].where(out["n"] >= 10)).to_string(float_format=lambda x: f"{x:,.2f}", na_rep="(가림)"))
        except Exception as e:
            print("ERROR", type(e).__name__, e)
