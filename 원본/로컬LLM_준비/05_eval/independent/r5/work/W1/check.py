# -*- coding: utf-8 -*-
"""W1 과제의 산출 정의 자기 대조.

두 경로로 값을 계산해 칸별로 대조함.
  (가) 직접 계산: 질문 문장을 다시 읽고 pandas 불리언 조건으로 풀어 쓴 계산(MANUAL)
  (나) 정의 계산: cases.jsonl 의 specs 를 일반 평가기로 계산(eval_spec)
출력: 칸별 가중 값, 가중하지 않은 관측 수(비율은 분모·분자·여집합), 두 경로의 일치 여부.
끝에 유형·표현별 차례 수, 관계 점검, 양식 점검을 함께 출력함.

실행: /mnt/share/행정데이터_set/.venv/bin/python check.py > check_output.txt
"""
import json
import os
from collections import Counter

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = "/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet"
CASES = os.path.join(HERE, "cases.jsonl")

SIDO = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원",
        "충북", "충남", "전북", "전남", "경북", "경남", "제주"]


# ------------------------------------------------------------------ 공통
def wquantile(values, weights, q):
    """자료 규약: 오름차순으로 놓고 가중치 누적합이 전체의 q배에 처음 이르는 값."""
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    ok = ~np.isnan(v)
    v, w = v[ok], w[ok]
    order = np.argsort(v, kind="mergesort")
    v, w = v[order], w[order]
    cum = np.cumsum(w)
    idx = int(np.searchsorted(cum, q * cum[-1], side="left"))
    return float(v[min(idx, len(v) - 1)])


def load():
    df = pd.read_parquet(DATA)
    hh = df.groupby("hid")["p_dinc"].transform("sum")
    df["hh_dinc"] = hh
    df["eqinc"] = hh / np.sqrt(df["hnum"])
    med = wquantile(df["eqinc"], df["indwgt"], 0.5)
    df["poor"] = (df["eqinc"] < 0.5 * med).astype(int)
    return df


# ------------------------------------------------------------------ (나) 정의 계산
def std_group(df, name):
    if name == "sido":
        return df["sido"].map(lambda c: SIDO[int(c) - 1]), SIDO
    if name == "sex":
        return df["gender"].map({1: "남", 2: "여"}), ["남", "여"]
    if name == "age3":
        lab = ["0~17세", "18~64세", "65세 이상"]
        return pd.Series(np.select([df["age"] < 18, df["age"] < 65], lab[:2], lab[2]), index=df.index), lab
    if name == "age6":
        lab = ["0~17세", "18~34세", "35~49세", "50~64세", "65~74세", "75세 이상"]
        idx = np.digitize(df["age"], [18, 35, 50, 65, 75])
        return pd.Series([lab[i] for i in idx], index=df.index), lab
    if name == "hs4":
        lab = ["1인", "2인", "3인", "4인 이상"]
        return df["hnum"].clip(upper=4).map(lambda k: lab[int(k) - 1]), lab
    raise ValueError("이 과제에서 쓰지 않는 표준 분류: " + name)


def by_groups(sub, by):
    """분류 기준 목록 → (분류 열, 항목 순서)의 목록."""
    out = []
    for b in by:
        if "std" in b:
            out.append(std_group(sub, b["std"]))
        elif "var" in b:
            idx = np.digitize(sub[b["var"]], b["bins"])
            out.append((pd.Series([b["labels"][i] for i in idx], index=sub.index), b["labels"]))
        elif "cat" in b:
            vals = sorted(sub[b["cat"]].dropna().unique())
            out.append((sub[b["cat"]].map(lambda x: None if pd.isna(x) else str(int(x))), [str(int(v)) for v in vals]))
        elif "groups" in b:
            s = pd.Series([None] * len(sub), index=sub.index, dtype=object)
            labels = []
            for g in b["groups"]:
                m = sub.eval(g["cond"], engine="python")
                s[m & s.isna()] = g["label"]
                labels.append(g["label"])
            out.append((s, labels))
        else:
            raise ValueError(b)
    return out


def eval_spec(df, spec):
    """산출 정의 1개 → {칸 이름: dict(value, n, n_num, n_comp)}"""
    if spec.get("unit", "person") == "household":
        base, w = df[df["head"] == 1], "hhwgt"
    else:
        base, w = df, "indwgt"
    pop = spec.get("population", "")
    sub = base.query(pop, engine="python") if pop else base
    groups = by_groups(sub, spec.get("by", []))
    if groups:
        key = groups[0][0].astype(object)
        order = list(groups[0][1])
        for s, lab in groups[1:]:
            key = key.astype(str) + " × " + s.astype(str)
            order = [a + " × " + b for a in order for b in lab]
        cells = [(k, sub[key == k]) for k in order]
    else:
        cells = [("전체", sub)]
    res = {}
    m = spec["measure"]
    for name, g in cells:
        r = {"n": len(g)}
        if m == "count":
            r["value"] = g[w].sum()
        elif m == "rate":
            num = g.eval(spec["numerator"], engine="python")
            r["value"] = 100.0 * g.loc[num, w].sum() / g[w].sum() if len(g) else float("nan")
            r["n_num"] = int(num.sum())
            r["n_comp"] = int(len(g) - num.sum())
        elif m in ("mean", "sum", "quantile"):
            v = g[spec["value_var"]]
            ok = v.notna()
            r["n"] = int(ok.sum())
            if m == "mean":
                r["value"] = float((v[ok] * g.loc[ok, w]).sum() / g.loc[ok, w].sum())
            elif m == "sum":
                r["value"] = float((v[ok] * g.loc[ok, w]).sum())
            else:
                r["value"] = wquantile(v[ok], g.loc[ok, w], spec["q"])
        else:
            raise ValueError("이 과제에서 쓰지 않는 지표: " + m)
        res[name] = r
    return res


# ------------------------------------------------------------------ (가) 직접 계산
def W(df, mask, hh=False):
    """가중 합(개인 가중치 또는 가구주 행의 가구 가중치)과 관측 수."""
    if hh:
        mask = mask & (df["head"] == 1)
        return float(df.loc[mask, "hhwgt"].sum()), int(mask.sum())
    return float(df.loc[mask, "indwgt"].sum()), int(mask.sum())


def cnt(df, mask, hh=False):
    v, n = W(df, mask, hh)
    return {"value": v, "n": n}


def rate(df, den, num, hh=False):
    d, nd = W(df, den, hh)
    a, na = W(df, den & num, hh)
    return {"value": 100.0 * a / d, "n": nd, "n_num": na, "n_comp": nd - na}


def mean(df, mask, var, hh=False):
    if hh:
        mask = mask & (df["head"] == 1)
    wt = "hhwgt" if hh else "indwgt"
    g = df[mask & df[var].notna()]
    return {"value": float(np.average(g[var], weights=g[wt])), "n": len(g)}


def median(df, mask, var):
    g = df[mask & df[var].notna()].sort_values(var, kind="mergesort")
    cum = g["indwgt"].cumsum()
    half = 0.5 * g["indwgt"].sum()
    return {"value": float(g.loc[cum >= half, var].iloc[0]), "n": len(g)}


def manual(df):
    """질문 문장에서 다시 풀어 쓴 계산. 키: (과제 id, 차례, part)."""
    M = {}
    age = df["age"]
    kid, mid, old = age <= 17, (age >= 18) & (age <= 64), age >= 65
    male, female = df["gender"] == 1, df["gender"] == 2
    one, two, three, four = df["hnum"] == 1, df["hnum"] == 2, df["hnum"] == 3, df["hnum"] >= 4

    # 12월(고정시점) 수급 여부: 1이면 수급, 0·결측은 비수급 / 연간 수급 여부: 1 또는 결측
    live_dec = df["nbls_live_yn2"].eq(1)
    medi_dec = df["nbls_medi_yn2"].eq(1)
    house_dec = df["nbls_house_yn2"].eq(1)
    live_year = df["nbls_live_yn1"].notna()
    medi_year = df["nbls_medi_yn1"].notna()

    # --- W1-01
    M[("W1-01", 1, None)] = {"0~17세": cnt(df, live_dec & kid), "18~64세": cnt(df, live_dec & mid), "65세 이상": cnt(df, live_dec & old)}
    M[("W1-01", 2, 1)] = {"전체": cnt(df, live_dec & ~medi_dec)}
    M[("W1-01", 2, 2)] = {"전체": rate(df, live_dec, ~medi_dec)}

    # --- W1-02
    bp_dec = df["bp_yn2"].eq(1)
    M[("W1-02", 1, None)] = {SIDO[c - 1]: rate(df, old & (df["sido"] == c), bp_dec) for c in range(1, 18)}
    M[("W1-02", 2, None)] = {"전체": rate(df, bp_dec, df["bp_type"].eq(3))}
    full_single = bp_dec & df["bp_type"].eq(1) & df["bp_dur"].eq(12)
    M[("W1-02", 3, None)] = {"전체": mean(df, full_single, "bp_amt")}
    line = 1_800_000 * 12   # 단독가구 선정기준액 월 180만 원의 12개월분(A09)
    M[("W1-02", 4, None)] = {"전체": rate(df, old & one & (df["h_oinc"] <= line), bp_dec)}

    # --- W1-03
    severe_adult = df["dis_disp_yn"].eq(1) & (age >= 18)
    disp_dec = df["disp_yn2"].eq(1)
    M[("W1-03", 1, None)] = {"18~64세": rate(df, severe_adult & (age <= 64), disp_dec), "65세 이상": rate(df, severe_adult & old, disp_dec)}
    top_amt = 387_500 * 12   # 월 최대 387,500원의 12개월분(A11)
    M[("W1-03", 2, None)] = {"전체": cnt(df, df["disp_yn1"].notna() & (df["disp_amt"] == top_amt))}
    bn_dec = df["disp_bn_yn2"].eq(1)
    M[("W1-03", 3, 1)] = {"남": cnt(df, bn_dec & male), "여": cnt(df, bn_dec & female)}
    M[("W1-03", 3, 2)] = {"남": mean(df, bn_dec & male, "disp_bn_amt"), "여": mean(df, bn_dec & female, "disp_bn_amt")}

    # --- W1-04
    aid = df["aid_live_yn1"].notna()
    M[("W1-04", 1, 1)] = {"전체": cnt(df, aid)}
    M[("W1-04", 1, 2)] = {"전체": mean(df, aid, "aid_live_amt")}
    M[("W1-04", 2, 1)] = {"1인 가구": cnt(df, aid & one), "2인 이상 가구": cnt(df, aid & ~one)}
    M[("W1-04", 2, 2)] = {"1인 가구": mean(df, aid & one, "aid_live_dur"), "2인 이상 가구": mean(df, aid & ~one, "aid_live_dur")}

    # --- W1-05
    eitc = df["itc_yn"].eq(1)
    hm = {"11": df["itc_hmember"].eq(11), "21": df["itc_hmember"].eq(21), "23": df["itc_hmember"].eq(23)}
    M[("W1-05", 1, 1)] = {k: cnt(df, eitc & m) for k, m in hm.items()}
    M[("W1-05", 1, 2)] = {k: mean(df, eitc & m, "itc_amt") for k, m in hm.items()}
    ctc = df["itc_child_yn"].eq(1)
    ch = {"1명": df["itc_child"] <= 1, "2명": df["itc_child"].eq(2), "3명 이상": df["itc_child"] >= 3}
    M[("W1-05", 2, 1)] = {k: cnt(df, ctc & m) for k, m in ch.items()}
    M[("W1-05", 2, 2)] = {k: mean(df, ctc & m, "itc_child_amt") for k, m in ch.items()}
    M[("W1-05", 3, None)] = {"전체": cnt(df, eitc & (df["h_prop"] >= 200_000_000))}   # 재산요건 2억 원(A17)
    bands = {"18~34세": (age >= 18) & (age <= 34), "35~49세": (age >= 35) & (age <= 49), "50~64세": (age >= 50) & (age <= 64), "65세 이상": old}
    M[("W1-05", 4, None)] = {k: rate(df, m, eitc) for k, m in bands.items()}

    # --- W1-06
    rear_dec = df["single_rear_yn2"].eq(1)
    M[("W1-06", 1, None)] = {"남": cnt(df, rear_dec & male), "여": cnt(df, rear_dec & female)}
    extra_dec = df["single_extra_yn2"].eq(1)
    M[("W1-06", 2, 1)] = {"전체": cnt(df, extra_dec)}
    M[("W1-06", 2, 2)] = {"전체": mean(df, extra_dec, "single_extra_amt")}
    M[("W1-06", 4, None)] = {"전체": median(df, df["single_rear_yn1"].notna() & df["single_rear_dur"].eq(12), "single_rear_amt")}

    # --- W1-07 (세대 = 가구 단위)
    ev = df["evou_yn"].eq(1)
    M[("W1-07", 1, 1)] = {"전체": cnt(df, ev & (df["evou_amt"] == 347_000), hh=True)}
    M[("W1-07", 1, 2)] = {"전체": rate(df, ev, df["evou_amt"] == 347_000, hh=True)}
    M[("W1-07", 2, None)] = {"전체": cnt(df, ev & ~live_year & ~medi_year, hh=True)}
    left = df["evou_bal"] > 0
    M[("W1-07", 3, None)] = {"1인 세대": rate(df, ev & one, left, hh=True), "2인 이상 세대": rate(df, ev & ~one, left, hh=True)}

    # --- W1-08
    cul = df["culvou_yn"].eq(1)
    a3 = {"0~17세": kid, "18~64세": mid, "65세 이상": old}
    M[("W1-08", 1, None)] = {k: cnt(df, cul & m) for k, m in a3.items()}
    M[("W1-08", 2, None)] = {k: rate(df, cul & m, df["culvou_bn"] >= 110_000) for k, m in a3.items()}
    M[("W1-08", 3, 1)] = {"수급": cnt(df, cul & live_year), "비수급": cnt(df, cul & ~live_year)}
    M[("W1-08", 3, 2)] = {"수급": mean(df, cul & live_year, "culvou_bn"), "비수급": mean(df, cul & ~live_year, "culvou_bn")}

    # --- W1-09
    rm = df["rm_yn"].eq(1)
    M[("W1-09", 1, 1)] = {"전체": cnt(df, rm)}
    M[("W1-09", 1, 2)] = {"전체": median(df, rm, "rm_amt")}
    M[("W1-09", 2, None)] = {"전체": rate(df, rm & old, bp_dec)}
    eligible = (age >= 55) & (df["h_ptax_housing"] > 0) & (df["h_ptax_housing"] <= 900_000_000)   # 만 55세, 공시가격 9억 원(A21)
    M[("W1-09", 3, None)] = {"전체": rate(df, eligible, rm, hh=True)}

    # --- W1-10 (가구 단위)
    lm = live_dec | medi_dec
    hs = {"1인": one, "2인": two, "3인": three, "4인 이상": four}
    M[("W1-10", 1, None)] = {k: cnt(df, lm & m, hh=True) for k, m in hs.items()}
    M[("W1-10", 2, None)] = {"전체": cnt(df, rear_dec & ~live_dec & ~medi_dec, hh=True)}

    # --- W1-11
    M[("W1-11", 1, None)] = {k: cnt(df, house_dec & m, hh=True) for k, m in hs.items()}
    M[("W1-11", 2, None)] = {k: cnt(df, house_dec & ~live_dec & m, hh=True) for k, m in hs.items()}
    young_single = house_dec & (age >= 19) & (age <= 29) & one
    M[("W1-11", 4, 1)] = {"전체": cnt(df, young_single)}
    M[("W1-11", 4, 2)] = {"전체": mean(df, young_single, "nbls_house_amt")}
    return M


# ------------------------------------------------------------------ 대조와 출력
def fmt(v):
    return f"{v:,.4f}" if abs(v) < 1000 else f"{v:,.1f}"


def main():
    df = load()
    cases = [json.loads(l) for l in open(CASES, encoding="utf-8") if l.strip()]
    M = manual(df)
    print(f"자료: {len(df):,}행, {df['hid'].nunique():,}가구, 가중 인구 {df['indwgt'].sum():,.0f}, 가중 가구 {df.loc[df['head'] == 1, 'hhwgt'].sum():,.0f}")
    print(f"과제 수: {len(cases)}\n")

    n_spec = n_cell = n_bad = n_small = 0
    used = set()
    truth = {}          # (id, 차례) → 첫 count 정의의 칸별 값(관계 점검용)
    for c in cases:
        print("=" * 100)
        print(f"{c['id']}  {c['issue']}")
        for t in c["turns"]:
            head = f"[{c['id']} 차례 {t['n']}] kind={t['kind']}" + (f" register={t['register']}" if "register" in t else "")
            print("-" * 100)
            print(head)
            print("  질문:", t["q"])
            if "param" in t:
                print("  기준값:", json.dumps(t["param"], ensure_ascii=False))
            if "premise" in t:
                print("  전제:", t["premise"])
            if "absent" in t:
                print("  자료에 없음:", t["absent"])
            for s in t.get("specs", []):
                n_spec += 1
                part = s.get("part")
                key = (c["id"], t["n"], part)
                res = eval_spec(df, s)
                desc = f"measure={s['measure']} unit={s.get('unit', 'person')} population=\"{s.get('population', '')}\""
                if "numerator" in s:
                    desc += f" numerator=\"{s['numerator']}\""
                if "value_var" in s:
                    desc += f" value_var={s['value_var']}"
                if "q" in s:
                    desc += f" q={s['q']}"
                print(f"  정의(part={part}, alt={s.get('alt', 1)}): {desc}")
                if s["measure"] == "count" and (c["id"], t["n"]) not in truth:
                    truth[(c["id"], t["n"])] = {k: v["value"] for k, v in res.items()}
                man = M.get(key)
                if man is None:
                    raise SystemExit(f"직접 계산이 없음: {key}")
                used.add(key)
                if set(man) != set(res):
                    raise SystemExit(f"칸 이름 불일치: {key} {sorted(man)} / {sorted(res)}")
                for name, r in res.items():
                    n_cell += 1
                    mv = man[name]
                    same = np.isclose(r["value"], mv["value"], rtol=1e-9, atol=1e-6) and r["n"] == mv["n"]
                    if "n_num" in r:
                        same = same and r["n_num"] == mv["n_num"]
                    if not same:
                        n_bad += 1
                    n_min = min(r["n"], r.get("n_num", r["n"]), r.get("n_comp", r["n"]))
                    if n_min < 30:
                        n_small += 1
                    extra = f" 분자 {r['n_num']:,} 여집합 {r['n_comp']:,}" if "n_num" in r else ""
                    flag = "일치" if same else f"불일치(직접 계산 {fmt(mv['value'])}, 관측 {mv['n']})"
                    warn = "  ※ 관측 수 30건 미만" if n_min < 30 else ""
                    print(f"    {name:<14} 값 {fmt(r['value']):>18}   관측 {r['n']:>6,}{extra}   {flag}{warn}")

    unused = set(M) - used
    print("\n" + "=" * 100)
    print(f"산출 정의 {n_spec}개, 칸 {n_cell}개, 불일치 칸 {n_bad}개, 관측 수 30건 미만 칸 {n_small}개, 쓰이지 않은 직접 계산 {len(unused)}개")

    # ---- 유형·표현별 차례 수
    kinds = Counter(t["kind"] for c in cases for t in c["turns"])
    regs = Counter(t["register"] for c in cases for t in c["turns"] if t["kind"] in "SGPX")
    target = {"S": 24, "G": 3, "P": 3, "N": 3, "V": 2, "T": 2, "X": 2, "C": 3, "I": 2}
    print("\n유형별 차례 수:", " ".join(f"{k} {kinds.get(k, 0)}(기준 {v})" for k, v in target.items()),
          "→", "일치" if all(kinds.get(k, 0) == v for k, v in target.items()) and sum(kinds.values()) == 44 else "불일치")
    rng = {"공식": (9, 11), "약칭": (10, 12), "서술": (8, 10), "영문": (2, 2)}
    print("표현별 차례 수:", " ".join(f"{k} {regs.get(k, 0)}(기준 {a}~{b})" for k, (a, b) in rng.items()),
          "→", "일치" if all(a <= regs.get(k, 0) <= b for k, (a, b) in rng.items()) and sum(regs.values()) == 32 else "불일치")

    # ---- 양식 점검
    problems = []
    for c in cases:
        ks = [t["kind"] for t in c["turns"]]
        if len(ks) != 4 or [t["n"] for t in c["turns"]] != [1, 2, 3, 4]:
            problems.append(f"{c['id']}: 차례가 4개가 아님")
        if ks.count("S") < 2:
            problems.append(f"{c['id']}: S가 2개 미만")
        if ks[0] not in ("S", "G"):
            problems.append(f"{c['id']}: 첫 차례가 S·G가 아님")
        if "C" in ks and ks.index("C") < 2:
            problems.append(f"{c['id']}: C가 앞쪽 차례에 있음")
        for t in c["turns"]:
            k = t["kind"]
            need = {"S": ["specs", "register"], "G": ["specs", "param", "register"], "P": ["specs", "param", "register"],
                    "N": ["absent"], "V": ["absent"], "T": [], "X": ["premise", "register"], "C": [], "I": []}[k]
            for f in need + ["rubric", "q"]:
                if not t.get(f):
                    problems.append(f"{c['id']} 차례 {t['n']}: {f} 없음")
            if k in "NVTCI" and ("specs" in t or "register" in t):
                problems.append(f"{c['id']} 차례 {t['n']}: {k} 차례에 specs·register 가 있음")
    print("양식 점검:", "문제 없음" if not problems else problems)
    print("과제별 유형:", " / ".join(c["id"][-2:] + ":" + "".join(t["kind"] for t in c["turns"]) for c in cases))
    facts = sorted({f for c in cases for f in c["facts"]})
    print(f"쓴 사실 id {len(facts)}개:", ", ".join(facts))

    # ---- 관계 점검(참값 기준)
    rels = [(c["id"], r) for c in cases for r in c.get("relations", [])]
    print(f"\n관계 점검 {len(rels)}개(기준 5개 이상)")
    for cid, r in rels:
        if r["type"] == "parts_sum":
            whole = sum(truth[(cid, r["whole"])].values())
            parts = sum(truth[(cid, r["parts"])].values())
            ok = np.isclose(whole, parts)
            print(f"  {cid} parts_sum 차례 {r['whole']} 전체 {whole:,.1f} = 차례 {r['parts']} 합 {parts:,.1f} → {'성립' if ok else '불성립'}")
        elif r["type"] == "subset_le":
            large = truth[(cid, r["large"])]
            small = truth[(cid, r["small"])]
            if set(large) == set(small) and len(large) > 1:
                ok = all(small[k] <= large[k] + 1e-6 for k in large)
                print(f"  {cid} subset_le 칸별: " + ", ".join(f"{k} {small[k]:,.1f} ≤ {large[k]:,.1f}" for k in large) + f" → {'성립' if ok else '불성립'}")
            else:
                ok = sum(small.values()) <= sum(large.values()) + 1e-6
                print(f"  {cid} subset_le 차례 {r['small']} {sum(small.values()):,.1f} ≤ 차례 {r['large']} {sum(large.values()):,.1f} → {'성립' if ok else '불성립'}")

    # ---- N·V 차례의 자료 확인
    print("\nN·V 차례의 자료 확인")
    cb = pd.read_csv(os.path.join(HERE, "..", "..", "..", "inputs", "codebook.tsv"), sep="\t")
    text = (cb["var"].astype(str) + " " + cb["name_ko"].astype(str) + " " + cb["program"].astype(str) + " " + cb["content"].astype(str))
    for kw in ["금융재산", "금융", "한시", "긴급생활", "월세", "청년", "청소년", "차상위"]:
        hit = cb.loc[text.str.contains(kw), "var"].tolist()
        print(f"  codebook '{kw}' 검색: {len(hit)}개 {hit[:8]}")
    for v in ["single_youth_rear_yn1", "single_youth_rear_yn2", "single_youth_rear_dur", "single_youth_rear_amt",
              "self_lower_yn1", "self_lower_yn2", "self_lower_type1", "self_lower_type2", "self_lower_dur", "self_lower_amt"]:
        s = df[v]
        print(f"  값없는 변수 {v}: 값이 있는 행 {int(s.notna().sum())}, 0이 아닌 행 {int((s.fillna(0) != 0).sum())}")
    print(f"  소득 합산용 변수 p_single_youth_rear_amt: 0이 아닌 행 {int((df['p_single_youth_rear_amt'] != 0).sum())}")
    print(f"  농지연금 가입자 관측 수: {int(df['frm_yn'].eq(1).sum())}, 지급방식별 {df.loc[df['frm_yn'].eq(1), 'frm_type'].value_counts().sort_index().astype(int).to_dict()}")


if __name__ == "__main__":
    main()
