# -*- coding: utf-8 -*-
"""산출 정의(spec) 실행기: 칸별 가중 값과 가중하지 않은 관측 수(집계만)를 돌려줌."""
import re
import numpy as np
import pandas as pd
from lib import wquantile

STD = {"sido": "sido", "sex": "sex", "age3": "age3", "age6": "age6", "age10": "age10",
       "hs4": "hs4", "inc5": "inc5", "nhi3": "nhi3", "poor2": "poor2"}
GRADE_MIN = {"가": 10, "나": 20, "다": 30}


def ev(d, cond):
    if cond is None or str(cond).strip() == "":
        return pd.Series(True, index=d.index)
    r = d.eval(cond, engine="python")
    if not isinstance(r, pd.Series):
        r = pd.Series(r, index=d.index)
    return r.fillna(False).astype(bool)


def by_series(d, b):
    if "std" in b:
        return d[STD[b["std"]]].astype(str).rename(b["std"])
    if "var" in b:
        edges = [-np.inf] + list(b["bins"]) + [np.inf]
        labels = b.get("labels") or [str(i) for i in range(len(edges) - 1)]
        assert len(labels) == len(edges) - 1, "labels 수가 구간 수와 다름"
        s = pd.cut(d[b["var"]], edges, right=False, labels=labels)
        return s.astype(object).rename(b["var"] + "_bin")
    if "cat" in b:
        return d[b["cat"]].rename(b["cat"])
    if "groups" in b:
        s = pd.Series(np.nan, index=d.index, dtype=object)
        cnt = pd.Series(0, index=d.index)
        for g in b["groups"]:
            m = ev(d, g["cond"])
            cnt += m.astype(int)
            s[m] = g["label"]
        assert (cnt <= 1).all(), "조건 집단이 서로 겹침"
        return s.rename("group")
    raise ValueError(b)


def run_spec(df, spec):
    unit = spec.get("unit", "person")
    d = df[df["head"] == 1] if unit == "household" else df
    w = "hhwgt" if unit == "household" else "indwgt"
    d = d[ev(d, spec.get("population", ""))]
    keys = [by_series(d, b) for b in spec.get("by", [])]
    m = spec["measure"]
    if m == "share":
        vv = spec["value_var"]
        col = d[STD[vv]].astype(str) if vv in STD else d[vv]
        d = d.assign(_cat=col.values)
        d = d[d["_cat"].notna()]
        keys = [k.loc[d.index] for k in keys]
        if keys:
            g = d.groupby(keys + [d["_cat"]], dropna=True)
            tot = d.groupby(keys, dropna=True)[w].sum()
            out = g.agg(n=(w, "size"), wsum=(w, "sum")).reset_index()
            kn = [k.name for k in keys]
            out["value"] = out.apply(lambda r: 100 * r["wsum"] / tot.loc[tuple(r[k] for k in kn) if len(kn) > 1 else r[kn[0]]], axis=1)
        else:
            out = d.groupby("_cat").agg(n=(w, "size"), wsum=(w, "sum")).reset_index()
            out["value"] = 100 * out["wsum"] / d[w].sum()
        return out.drop(columns="wsum")

    def cell(x):
        r = {"n": len(x)}
        if m == "count":
            r["value"] = x[w].sum()
        elif m == "rate":
            num = ev(x, spec["numerator"])
            r["n_num"] = int(num.sum())
            r["n_comp"] = int((~num).sum())
            r["value"] = 100 * x.loc[num, w].sum() / x[w].sum() if len(x) else np.nan
        elif m == "poverty_rate":
            num = x["poor"] == 1
            r["n_num"] = int(num.sum())
            r["n_comp"] = int((~num).sum())
            r["value"] = 100 * x.loc[num, w].sum() / x[w].sum() if len(x) else np.nan
        elif m in ("mean", "sum", "quantile"):
            v = pd.to_numeric(x[spec["value_var"]], errors="coerce")
            ok = v.notna()
            r["n"] = int(ok.sum())
            if m == "mean":
                r["value"] = np.average(v[ok], weights=x.loc[ok, w]) if ok.any() else np.nan
            elif m == "sum":
                r["value"] = (v[ok] * x.loc[ok, w]).sum()
            else:
                r["value"] = wquantile(v[ok], x.loc[ok, w], spec["q"])
        return pd.Series(r)

    if keys:
        out = d.groupby(keys, dropna=True).apply(cell, include_groups=False).reset_index()
    else:
        out = cell(d).to_frame().T
    return out


def vars_in(spec, cols):
    txt = " ".join(str(spec.get(k, "")) for k in ("population", "numerator", "value_var"))
    for b in spec.get("by", []):
        txt += " " + b.get("var", "") + " " + b.get("cat", "")
        for g in b.get("groups", []):
            txt += " " + g["cond"]
    toks = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", txt))
    return sorted(t for t in toks if t in cols)
