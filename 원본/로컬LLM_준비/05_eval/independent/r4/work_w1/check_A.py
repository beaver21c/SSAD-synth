# -*- coding: utf-8 -*-
"""r4/items/A.jsonl, H.jsonl 확인용 스크립트(작성자 w1).

확인 내용
 1) 두 파일이 JSON Lines로 읽히는지, 공통 항목이 양식에 맞는지
 2) A의 모든 population·numerator·groups[].cond가 DataFrame.eval(engine='python')으로 실행되는지
    (파생 변수 eqinc·hh_dinc·poor는 자료_규약.md의 정의로 lib.load()에서 만듦)
 3) 산출 정의를 실제로 실행해 칸별 가중하지 않은 관측 수를 확인(개인 단위 행은 출력하지 않음)
 4) 구성 요건별 문항 수
실행: /mnt/share/행정데이터_set/.venv/bin/python check_A.py [-v]
"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
import pandas as pd
from lib import load, codebook
from runner import run_spec, ev, vars_in, GRADE_MIN, STD

ITEMS = os.path.join(os.path.dirname(HERE), "items")
VERBOSE = "-v" in sys.argv
MEASURES = {"count", "rate", "mean", "sum", "quantile", "share", "poverty_rate"}
DERIVED = {"eqinc", "hh_dinc", "poor"}
errors = []


def err(msg):
    errors.append(msg)
    print("  [오류]", msg)


def read_jsonl(name):
    rows = []
    with open(os.path.join(ITEMS, name), encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                err(f"{name} {i}행: 빈 줄")
                continue
            try:
                rows.append(json.loads(line))
            except Exception as e:
                err(f"{name} {i}행: JSON 오류 {e}")
    return rows


def tokens(txt):
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", txt or ""))


def n_conds(pop):
    pop = (pop or "").strip()
    return 0 if not pop else len(re.split(r"\band\b|\bor\b", pop))


A = read_jsonl("A.jsonl")
H = read_jsonl("H.jsonl")
print(f"A {len(A)}문항, H {len(H)}문항 (JSON Lines 읽기 완료)")

cb = codebook().set_index("var")
cols = set(cb.index)
PVARS = set(cb.index[cb["priority"] == "P"])
df = load()

# ---- 공통 항목 ----
for k, it in enumerate(A, 1):
    if it.get("id") != "A%03d" % k: err(f"{it.get('id')}: id 순번 불일치")
    if it.get("stratum") != "A" or it.get("expect") != "compute": err(f"{it['id']}: stratum/expect")
    if not it.get("persona") or not it.get("note"): err(f"{it['id']}: persona/note 없음")
    if not (isinstance(it.get("turns"), list) and len(it["turns"]) >= 1 and all(isinstance(t, str) and t.strip() for t in it["turns"])): err(f"{it['id']}: turns")
    if not it.get("specs"): err(f"{it['id']}: specs 없음")
    q = " ".join(it["turns"])
    used = [t for t in tokens(q) if t in cols or t in DERIVED or t in STD]
    if used: err(f"{it['id']}: 질문에 변수명 {used}")
for k, it in enumerate(H, 1):
    if it.get("id") != "H%02d" % k: err(f"{it.get('id')}: id 순번 불일치")
    if it.get("stratum") != "H" or it.get("expect") != "ask_or_assume": err(f"{it['id']}: stratum/expect")
    if "specs" in it: err(f"{it['id']}: H 문항에 specs가 있음")
    if not it.get("note") or not it.get("persona") or not it.get("turns"): err(f"{it['id']}: 항목 누락")
    q = " ".join(it["turns"])
    used = [t for t in tokens(q) if t in cols or t in DERIVED]
    if used: err(f"{it['id']}: 질문에 변수명 {used}")
if len({it["turns"][0] for it in A + H}) != len(A) + len(H): err("질문 문장 중복")

# ---- 산출 정의 실행 ----
rows = []
for it in A:
    feats = {"id": it["id"], "persona": it["persona"], "nspec": len(it["specs"])}
    status = []
    for k, sp in enumerate(it["specs"], 1):
        tag = f"{it['id']} spec{k}"
        m = sp.get("measure")
        if m not in MEASURES: err(f"{tag}: measure {m}")
        if sp.get("unit") not in ("person", "household"): err(f"{tag}: unit")
        if "population" not in sp or not isinstance(sp.get("by"), list): err(f"{tag}: population/by 누락")
        if m == "rate" and not sp.get("numerator"): err(f"{tag}: numerator 없음")
        if m != "rate" and "numerator" in sp: err(f"{tag}: rate가 아닌데 numerator가 있음")
        if m in ("mean", "sum", "quantile", "share") and not sp.get("value_var"): err(f"{tag}: value_var 없음")
        if m == "quantile" and not (0.05 <= sp.get("q", -1) <= 0.95): err(f"{tag}: q 범위")
        if m in ("mean", "sum", "quantile") and sp["value_var"] not in cols | DERIVED: err(f"{tag}: value_var가 변수 목록에 없음")
        if m == "share" and sp["value_var"] not in cols | set(STD): err(f"{tag}: share value_var")
        # 조건식에 쓴 이름이 모두 codebook 변수 또는 파생 변수인지
        conds = [sp.get("population", ""), sp.get("numerator", "")]
        for b in sp.get("by", []):
            keys = set(b) - {"labels"}
            if not ({"std"} == keys or {"var", "bins"} == keys or {"cat"} == keys or {"groups"} == keys): err(f"{tag}: by 형식 {b}")
            if "std" in b and b["std"] not in STD: err(f"{tag}: std {b['std']}")
            if "var" in b:
                if b["var"] not in cols | DERIVED: err(f"{tag}: bins var")
                if b["bins"] != sorted(b["bins"]) or len(b.get("labels", [])) != len(b["bins"]) + 1: err(f"{tag}: bins/labels")
            if "cat" in b and b["cat"] not in cols: err(f"{tag}: cat var")
            for g in b.get("groups", []):
                conds.append(g["cond"])
        for c in conds:
            bad = [t for t in tokens(c) if t not in cols | DERIVED | {"and", "or", "not", "in", "isna", "notna"}]
            if bad: err(f"{tag}: 조건식의 알 수 없는 이름 {bad} ← {c}")
            try:
                d0 = df[df["head"] == 1] if sp.get("unit") == "household" else df
                r = d0.eval(c, engine="python") if c.strip() else None
                if r is not None and not pd.api.types.is_bool_dtype(r): err(f"{tag}: 조건식 결과가 참·거짓이 아님 ← {c}")
            except Exception as e:
                err(f"{tag}: eval 실패 {type(e).__name__}: {e} ← {c}")
        try:
            out = run_spec(df, sp)
        except Exception as e:
            err(f"{tag}: 실행 실패 {type(e).__name__}: {e}")
            continue
        vs = vars_in(sp, cols)
        thr = max([GRADE_MIN.get(cb.loc[v, "sensitivity_grade"], 10) for v in vs] or [10])

        def shown(t):
            ok = out["n"] >= t
            if "n_num" in out:
                ok &= (out["n_num"] >= t) & (out["n_comp"] >= t)
            return int(ok.sum())
        ncell, s_thr, s30 = len(out), shown(thr), shown(30)
        if out["value"].isna().any(): err(f"{tag}: 값이 비는 칸")
        st = "전부 억제" if s_thr == 0 else ("일부 억제" if s_thr < ncell else "모두 표시")
        status.append(st)
        if VERBOSE:
            print(f"\n== {tag} {m} unit={sp['unit']} 등급 기준={thr} 칸={ncell} 표시(등급 기준)={s_thr} 표시(30건)={s30}")
            print(out.assign(value=out["value"].where(out["n"] >= 10)).to_string(float_format=lambda x: f"{x:,.2f}", na_rep="(가림)"))
        rows.append({"id": it["id"], "spec": k, "measure": m, "thr": thr, "cells": ncell, "shown_thr": s_thr, "shown30": s30,
                     "min_n": int(out["n"].min()), "status": st})
    sp0 = it["specs"][0]
    feats.update(
        measure=sp0["measure"],
        P=any((s["measure"] == "rate" and tokens(s.get("numerator")) & PVARS) or
              (s["measure"] in ("mean", "sum", "quantile", "share") and s.get("value_var") in PVARS) for s in it["specs"]),
        bins=any("bins" in b for b in sp0["by"]), groups=any("groups" in b for b in sp0["by"]),
        cat=any("cat" in b for b in sp0["by"]), std=",".join(b["std"] for b in sp0["by"] if "std" in b),
        household=sp0["unit"] == "household", by2=len(sp0["by"]) >= 2, noby=len(sp0["by"]) == 0,
        nconds=n_conds(sp0.get("population")),
        nvars_pop=len(tokens(sp0.get("population")) & (cols | DERIVED)),
        sido_limited="sido" in tokens(sp0.get("population")), alt=len(it["specs"]) > 1,
        status="/".join(sorted(set(status))))
    it["_f"] = feats

F = pd.DataFrame([it["_f"] for it in A if "_f" in it])
R = pd.DataFrame(rows)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
print("\n[문항별 요약]")
print(F.drop(columns=["persona"]).to_string(index=False))
print("\n[칸 관측 수 요약]")
print(R.to_string(index=False))

req = [
    ("P 변수를 분자·대상 변수로 쓴 문항", int(F["P"].sum()), 24),
    ("비율(rate)", int((F.measure == "rate").sum()), 16),
    ("인원·가구 수(count)", int((F.measure == "count").sum()), 6),
    ("평균(mean)", int((F.measure == "mean").sum()), 8),
    ("합계(sum)", int((F.measure == "sum").sum()), 3),
    ("분위수(quantile)", int((F.measure == "quantile").sum()), 4),
    ("구성비(share)", int((F.measure == "share").sum()), 4),
    ("상대 빈곤율(poverty_rate)", int((F.measure == "poverty_rate").sum()), 2),
    ("이용자 지정 구간(bins)", int(F["bins"].sum()), 8),
    ("조건 집단(groups)", int(F["groups"].sum()), 5),
    ("가구 단위", int(F["household"].sum()), 4),
    ("분류 기준 2개 이상", int(F["by2"].sum()), 3),
    ("분류 기준 없는 단일 값(구성비 제외)", int((F["noby"] & (F.measure != "share")).sum()), 10),
    ("조건 3개 이상 대상 집단", int((F["nconds"] >= 3).sum()), 6),
    ("  └ 그중 서로 다른 변수 3개 이상", int(((F["nconds"] >= 3) & (F["nvars_pop"] >= 3)).sum()), 6),
    ("시도(묶음) 한정", int(F["sido_limited"].sum()), 4),
]
print("\n[구성 요건]")
allok = True
for name, n, need in req:
    ok = n >= need
    allok &= ok
    print(f"  {'충족' if ok else '미달'}  {name}: {n} (최소 {need})")
print("  범주형 변수 분류(cat):", int(F["cat"].sum()), "/ 두 해석(alt):", int(F["alt"].sum()))
print("  표준 분류 사용:", dict(pd.Series([s for x in F["std"] for s in x.split(",") if s]).value_counts()))
print("  이용자 유형:", dict(F["persona"].value_counts()))
print("  전부 억제 예상:", list(F.loc[F.status == "전부 억제", "id"]))
print("  일부 억제 예상:", list(F.loc[F.status.str.contains("일부 억제"), "id"]))
n_sup = int((F.status == "전부 억제").sum())
if not 4 <= n_sup <= 6: err(f"전부 억제 문항 수 {n_sup} (4~6 범위 밖)")
print("  H 이용자 유형:", dict(pd.Series([h["persona"] for h in H]).value_counts()))
if len(A) != 48: err("A 문항 수가 48이 아님")
if len(H) != 8: err("H 문항 수가 8이 아님")
print("\n결과:", "이상 없음" if (not errors and allok) else f"오류 {len(errors)}건, 구성 요건 {'충족' if allok else '미달'}")
sys.exit(0 if (not errors and allok) else 1)
