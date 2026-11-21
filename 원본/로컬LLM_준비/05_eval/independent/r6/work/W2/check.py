# -*- coding: utf-8 -*-
"""W2 문서형 과제(6차) 스스로 대조
1) docs.jsonl 의 산출 정의(specs)를 pandas 로 직접 계산(칸별 가중 값과 관측 수)
2) 문서 문구를 다시 풀어 쓴 독립 계산(조건식 문자열을 쓰지 않는 마스크 계산)과 대조
3) F 항목의 주장 수치와 자료 값 대조, 1인당 구성·형식·작성 규칙 점검
실행: /mnt/share/행정데이터_set/.venv/bin/python check.py > check_output.txt
"""
import json, re, itertools
from collections import Counter
import numpy as np
import pandas as pd

BASE = "/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent"
DOCS = BASE + "/r6/work/W2/docs.jsonl"
DATA = "/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet"
CODEBOOK = BASE + "/inputs/codebook.tsv"
NOVAL = BASE + "/r5/inputs/값없는_사업.tsv"
FACTS = [BASE + "/r5/facts/facts_%s.jsonl" % k for k in "ABC"]

pd.set_option("display.width", 200)

# ------------------------------------------------------------------ 자료와 파생 변수
df = pd.read_parquet(DATA)
W = df["indwgt"]


def wquantile(values, weights, q):
    o = np.argsort(values, kind="mergesort")
    v = np.asarray(values)[o]
    c = np.cumsum(np.asarray(weights)[o])
    return v[np.searchsorted(c, q * c[-1])]


df["hh_dinc"] = df.groupby("hid")["p_dinc"].transform("sum")
df["eqinc"] = df["hh_dinc"] / np.sqrt(df["hnum"])
_cuts = [wquantile(df["eqinc"].values, W.values, q) for q in (0.2, 0.4, 0.6, 0.8)]
df["inc5"] = np.searchsorted(_cuts, df["eqinc"].values, side="right")  # 경계값 이상이면 위 분위
_med = wquantile(df["eqinc"].values, W.values, 0.5)
df["poor"] = (df["eqinc"] < 0.5 * _med).astype(int)

STD = {
    "sido": (df["sido"], None),
    "sex": (df["gender"], {1: "남", 2: "여"}),
    "age3": (pd.cut(df["age"], [-1, 17, 64, 200], labels=["0~17세", "18~64세", "65세 이상"]), None),
    "age6": (pd.cut(df["age"], [-1, 17, 34, 49, 64, 74, 200],
                    labels=["0~17", "18~34", "35~49", "50~64", "65~74", "75세 이상"]), None),
    "age10": (pd.cut(df["age"], [-1, 9, 19, 29, 39, 49, 59, 69, 79, 200]), None),
    "hs4": (df["hnum"].clip(upper=4), {1: "1인", 2: "2인", 3: "3인", 4: "4인 이상"}),
    "inc5": (df["inc5"], {0: "1분위", 1: "2분위", 2: "3분위", 3: "4분위", 4: "5분위"}),
    "nhi3": (df["nhi_type"].map({1: "지역가입", 2: "지역가입", 5: "직장가입", 6: "직장가입", 7: "의료급여", 8: "의료급여"}), None),
    "poor2": (df["poor"], {0: "비빈곤", 1: "빈곤"}),
}


def q(expr):
    """조건식 → 불리언 마스크(빈 문자열이면 전체)"""
    if not expr:
        return pd.Series(True, index=df.index)
    return df.eval(expr, engine="python").fillna(False).astype(bool)


def by_series(b):
    if "std" in b:
        s, lab = STD[b["std"]]
        return s.map(lab) if lab else s
    if "cat" in b:
        return df[b["cat"]]
    if "var" in b:
        edges = [-np.inf] + list(b["bins"]) + [np.inf]
        return pd.cut(df[b["var"]], edges, right=False, labels=b["labels"])
    if "groups" in b:
        out = pd.Series(np.nan, index=df.index, dtype=object)
        for g in b["groups"]:
            out[q(g["cond"])] = g["label"]
        return out
    raise ValueError(b)


def eval_spec(sp):
    """칸별 값과 관측 수. 반환: list of dict(cell, value, n, n_num, n_comp)"""
    unit_hh = sp.get("unit", "person") == "household"
    base = q(sp.get("population", ""))
    if unit_hh:
        base &= df["head"] == 1
    w = df["hhwgt"] if unit_hh else W
    keys = [by_series(b) for b in sp.get("by", [])]
    if keys:
        grp = pd.concat(keys, axis=1)
        grp.columns = ["k%d" % i for i in range(len(keys))]
        cells = grp[base].drop_duplicates().dropna().sort_values(list(grp.columns)).itertuples(index=False)
        cell_masks = []
        for c in cells:
            m = base.copy()
            for i, val in enumerate(c):
                m &= grp["k%d" % i] == val
            cell_masks.append((" × ".join(str(x) for x in c), m))
    else:
        cell_masks = [("전체", base)]
    out = []
    meas = sp["measure"]
    for label, m in cell_masks:
        if meas == "count":
            out.append(dict(cell=label, value=w[m].sum(), n=int(m.sum())))
        elif meas == "rate":
            num = m & q(sp["numerator"])
            out.append(dict(cell=label, value=100 * w[num].sum() / w[m].sum(), n=int(m.sum()),
                            n_num=int(num.sum()), n_comp=int((m & ~num).sum())))
        elif meas in ("mean", "sum", "quantile"):
            v = df[sp["value_var"]]
            mm = m & v.notna()
            if meas == "mean":
                val = (v[mm] * w[mm]).sum() / w[mm].sum()
            elif meas == "sum":
                val = (v[mm] * w[mm]).sum()
            else:
                val = wquantile(v[mm].values, w[mm].values, sp["q"])
            out.append(dict(cell=label, value=val, n=int(mm.sum())))
        elif meas == "share":
            v = df[sp["value_var"]]
            mm = m & v.notna()
            tot = w[mm].sum()
            for k in sorted(v[mm].unique()):
                mk = mm & (v == k)
                out.append(dict(cell="%s | %s=%s" % (label, sp["value_var"], k), value=100 * w[mk].sum() / tot,
                                n=int(mk.sum()), n_comp=int((mm & ~mk).sum())))
        elif meas == "poverty_rate":
            num = m & (df["poor"] == 1)
            out.append(dict(cell=label, value=100 * w[num].sum() / w[m].sum(), n=int(m.sum()), n_num=int(num.sum())))
        else:
            raise ValueError(meas)
    return out


def fmt(r, meas):
    v = r["value"]
    s = ("%.1f%%" % v) if meas in ("rate", "share", "poverty_rate") else ("{:,.1f}".format(v))
    extra = "  n=%d" % r["n"]
    if "n_num" in r:
        extra += " 분자=%d" % r["n_num"]
    if "n_comp" in r:
        extra += " 여집합=%d" % r["n_comp"]
    return "    %-40s %18s%s" % (r["cell"], s, extra)


# ------------------------------------------------------------------ 독립 계산(문서 문구 → 마스크)
A = df["age"]
fee_sum = df[["nhi_out_fee", "nhi_in_fee"]].sum(axis=1, min_count=1)
old_bins = pd.cut(A, [-np.inf, 75, 85, np.inf], right=False, labels=["65~74세", "75~84세", "85세 이상"])


def wsum(m):
    return W[m.fillna(False)].sum()


def wrate(num, den):
    num, den = num.fillna(False), den.fillna(False)
    return 100 * W[num & den].sum() / W[den].sum()


def wmean(var, m):
    m = m.fillna(False) & df[var].notna()
    return (df.loc[m, var] * W[m]).sum() / W[m].sum()


def grp_apply(key, m, f):
    return {str(k): f(m & (key == k)) for k in key[m].dropna().unique()}


sex = df["gender"].map({1: "남", 2: "여"})
age3 = STD["age3"][0]
nhi3 = STD["nhi3"][0]
inc5 = df["inc5"].map(STD["inc5"][1])
ceil_yes = df["nhi_ceiling_subsidy_yn"] == 1
ltc = df["ltcare_bn_yn"] == 1
cancer = df["nhi_special1_yn"] == 1
medi12 = df["nbls_medi_yn2"] == 1
act = df["disvou_act_yn1"] == 1
dis = df["dis_yn"] == 1
pub = df["oldwork_type1_yn1"] == 1
care = df["oldcare_yn1"] == 1
ALL = pd.Series(True, index=df.index)

INDEP = {
    # D01 가입유형별 인원 / 피부양자 중 65세 이상 / 최저보험료 이하 지역 세대
    ("W2-D01", 1, 1): lambda: grp_apply(df["nhi_type"], ALL, wsum),
    ("W2-D01", 2, 1): lambda: {"전체": wrate(A >= 65, df["nhi_type"] == 6)},
    ("W2-D01", 3, 1): lambda: {"전체": wsum((df["nhi_type"] == 1) & (df["nhi_premium_cal"] <= 19500))},
    ("W2-D01", 3, 2): lambda: {"전체": wrate(df["nhi_premium_cal"] <= 19500, df["nhi_type"] == 1)},
    # D02 본인부담상한제
    ("W2-D02", 1, 1): lambda: {"전체": wsum(ceil_yes)},
    ("W2-D02", 1, 2): lambda: {"전체": 100 * wsum(ceil_yes) / W.sum()},
    ("W2-D02", 2, 1): lambda: grp_apply(age3, ceil_yes, lambda m: wmean("nhi_ceiling_subsidy_amt", m)),
    ("W2-D02", 3, 1): lambda: {"전체": wrate(A >= 65, ceil_yes)},
    ("W2-D02", 4, 1): lambda: {"전체": wsum(fee_sum > 830000)},
    # D03 장기요양
    ("W2-D03", 1, 1): lambda: {"전체": wrate(ltc, A >= 65)},
    ("W2-D03", 2, 1): lambda: {"4등급": wrate(df["ltcare_grade"] == 4, ltc)},
    ("W2-D03", 3, 1): lambda: grp_apply(sex, ltc & (df["ltcare_institute_yn"] != 1), lambda m: wmean("ltcare_hbn_fee", m)),
    ("W2-D03", 4, 1): lambda: {"전체": wmean("nhi_premium_ltcare_amt1_y", df["nhi_type"] == 5)},
    # D04 노인맞춤돌봄·공익활동
    ("W2-D04", 1, 1): lambda: grp_apply(old_bins, care, wsum),
    ("W2-D04", 2, 1): lambda: {"전체": wrate(df["oldcare_yn2"] == 1, care)},
    ("W2-D04", 3, 1): lambda: grp_apply(sex, pub, lambda m: wmean("oldwork_type1_amt", m)),
    ("W2-D04", 4, 1): lambda: {"전체": wrate(df["oldwork_type1_amt"] >= 270000 * 10, pub)},
    # D05 의료급여
    ("W2-D05", 1, 1): lambda: grp_apply(df["nbls_medi_type"], medi12, wsum),
    ("W2-D05", 2, 1): lambda: {"전체": wrate(A >= 65, medi12)},
    ("W2-D05", 3, 1): lambda: {"전체": wsum(df["nbls_medi_implant_yn"] == 1)},
    ("W2-D05", 3, 2): lambda: {"전체": wsum(df["nbls_medi_dentures_yn"] == 1)},
    ("W2-D05", 4, 1): lambda: {"전체": wmean("nhi_in_fee", medi12 & (df["nbls_medi_type"] == 2) & (df["nhi_in_dur"] > 0))},
    # D06 장애·활동지원
    ("W2-D06", 1, 1): lambda: grp_apply(df["dis_grade_1"], dis, wsum),
    ("W2-D06", 2, 1): lambda: {"전체": wsum(act)},
    ("W2-D06", 2, 2): lambda: {"전체": wrate(act, dis & (df["dis_grade_1"] == 1))},
    ("W2-D06", 3, 1): lambda: {"전체": wmean("disvou_act_dur", act)},
    # D07 산정특례
    ("W2-D07", 1, 1): lambda: {"전체": wsum(cancer)},
    ("W2-D07", 1, 2): lambda: {"전체": wsum(df["nhi_special2_yn"] == 1)},
    ("W2-D07", 2, 1): lambda: {"전체": wmean("nhi_in_fee", cancer & (df["nhi_in_dur"] > 0))},
    ("W2-D07", 3, 1): lambda: {"전체": wrate(ceil_yes, cancer)},
    ("W2-D07", 4, 1): lambda: {"전체": wsum(cancer & (fee_sum > 5980000))},
    # D08 노인 의료이용
    ("W2-D08", 1, 1): lambda: grp_apply(old_bins, A >= 65, lambda m: wmean("nhi_out_dur", m)),
    ("W2-D08", 2, 1): lambda: grp_apply(sex, A >= 65, lambda m: wrate(df["nhi_in_dur"] > 0, m)),
    ("W2-D08", 3, 1): lambda: grp_apply(nhi3, A >= 65, lambda m: wmean("nhi_out_fee", m)),
    ("W2-D08", 5, 1): lambda: grp_apply(inc5, A >= 65, lambda m: wmean("nhi_out_dur", m)),
}


def norm_cell(c):
    c = str(c)
    c = c.replace("ltcare_grade=", "")
    return c


# ------------------------------------------------------------------ 읽기
docs = [json.loads(l) for l in open(DOCS, encoding="utf-8")]
cb = pd.read_csv(CODEBOOK, sep="\t")
noval = pd.read_csv(NOVAL, sep="\t")
facts = {}
for f in FACTS:
    for l in open(f, encoding="utf-8"):
        d = json.loads(l)
        facts[d["id"]] = d

print("=" * 100)
print("W2 스스로 대조 — 자료 %d행, 가중 인구 %s" % (len(df), "{:,.0f}".format(W.sum())))
print("소득 5분위 경계(균등화 가처분소득, 원):", ["{:,.0f}".format(c) for c in _cuts])
print("=" * 100)

# ------------------------------------------------------------------ 1) 산출 정의 계산 + 2) 독립 계산 대조
print("\n[1] 산출 정의 계산과 독립 계산 대조 (원판·변형 판 모두)")
mismatch = 0
small_cells = []
results = {}
for d in docs:
    base_id = d["variant_of"] or d["id"]
    for it in d["items"]:
        for sp in it.get("specs", []):
            sub = sp.get("sub", 1)
            res = eval_spec(sp)
            results[(d["id"], it["no"], sub)] = res
            print("\n  %s 항목 %d (%s, sub %d) %s | pop: %s%s" % (
                d["id"], it["no"], it["kind"], sub, sp["measure"], sp.get("population") or "(전체)",
                (" | num: " + sp["numerator"]) if sp.get("numerator") else ""))
            for r in res:
                print(fmt(r, sp["measure"]))
            # 관측 수 점검(주된 칸: 값의 관측 수, 비율이면 분자·여집합도)
            for r in res:
                lows = [r["n"]] + [r[k] for k in ("n_num", "n_comp") if k in r]
                if sp["measure"] == "share":
                    # 구성비는 주장이 가리키는 칸만 주된 칸으로 봄
                    if it["kind"] == "F" and not r["cell"].endswith("=4"):
                        continue
                if min(lows) < 30:
                    small_cells.append((d["id"], it["no"], sub, r["cell"], lows))
            key = (base_id, it["no"], sub)
            if key in INDEP:
                ind = INDEP[key]()
                got = {norm_cell(r["cell"].split(" | ")[-1] if sp["measure"] == "share" else r["cell"]): r["value"] for r in res}
                if sp["measure"] == "share":
                    got = {("%d등급" % float(k)) if k.replace(".", "").isdigit() else k: v for k, v in got.items()}
                for k, v in ind.items():
                    kk = k
                    if kk not in got:
                        # 범주 이름 표기 차이(숫자형 코드) 보정
                        cand = [g for g in got if g.replace(".0", "") == kk.replace(".0", "")]
                        kk = cand[0] if cand else kk
                    ok = kk in got and abs(got[kk] - v) <= 1e-6 * max(1, abs(v))
                    if not ok:
                        mismatch += 1
                    print("    독립 계산 %-20s %18s  %s" % (k, "{:,.3f}".format(v), "일치" if ok else "불일치(정의 값 %s)" % got.get(kk)))
            else:
                print("    독립 계산 없음")
                mismatch += 1
print("\n  독립 계산 불일치 수:", mismatch)
print("  관측 30건 미만 주된 칸:", small_cells if small_cells else "없음")

# ------------------------------------------------------------------ 3) F 항목 주장 대조
print("\n[2] F 항목 — 주장 수치와 자료 값")
f_true = f_false = 0
for d in docs:
    if d["variant_of"]:
        continue
    for it in d["items"]:
        if it["kind"] != "F":
            continue
        c = it["claim"]
        res = results[(d["id"], it["no"], 1)]
        if it["specs"][0]["measure"] == "share":
            val = [r["value"] for r in res if r["cell"].endswith("=4")][0]
        else:
            val = res[0]["value"]
        if c["unit"] == "%":
            diff = abs(val - c["claimed_value"])
            judged_true = round(val, 1) == c["claimed_value"]
            gap_ok = judged_true or diff >= 3
            gap = "%.1f%%p" % diff
        else:
            rel = abs(val - c["claimed_value"]) / val
            judged_true = round(val) == c["claimed_value"]
            gap_ok = judged_true or rel >= 0.10
            gap = "%.1f%%" % (100 * rel)
        f_true += c["true"]
        f_false += (not c["true"])
        print("  %s 항목 %d | 주장 %s%s | 자료 %s | 차이 %s | 표기 true=%s | 판정 %s | 차이 기준 %s" % (
            d["id"], it["no"], c["claimed_value"], c["unit"],
            ("%.2f" % val) if c["unit"] == "%" else "{:,.1f}".format(val), gap, c["true"],
            "맞음" if judged_true == c["true"] else "표기 오류", "충족" if gap_ok else "미달"))
        assert str(c["claimed_value"]).rstrip("0").rstrip(".") in d["document"].replace(",", ""), "주장 수치가 문서에 없음"
print("  맞는 주장 %d, 틀린 주장 %d" % (f_true, f_false))
# 변형 판의 주장 수치 동일성
for d in docs:
    if d["variant_of"]:
        o = next(x for x in docs if x["id"] == d["variant_of"])
        for it in d["items"]:
            if it["kind"] == "F":
                oi = next(x for x in o["items"] if x["no"] == it["no"])
                same = (it["claim"]["claimed_value"], it["claim"]["true"]) == (oi["claim"]["claimed_value"], oi["claim"]["true"])
                inside = str(it["claim"]["claimed_value"]).replace(",", "") in d["document"].replace(",", "")
                print("  변형 %s 항목 %d 주장 수치 원판과 같음=%s, 문서에 있음=%s" % (d["id"], it["no"], same, inside))

# ------------------------------------------------------------------ 4) G·P 기준값 점검
print("\n[3] G·P 기준값 — G는 문서에 값이 있고, P는 문서·요청에 값이 없어야 함")
for d in docs:
    if d["variant_of"]:
        continue
    for it in d["items"]:
        if it["kind"] in ("G", "P"):
            p = it["param"]
            fv = facts[p["fact_id"]]
            text = d["document"] + " ".join(t["q"] for t in d["turns"])
            if p["unit"] == "원" and p["value"] >= 10000 and p["value"] % 10000 == 0:
                forms = ["{:,}원".format(p["value"]), "%d만 원" % (p["value"] // 10000), "%d만원" % (p["value"] // 10000)]
            else:
                forms = ["{:,}원".format(p["value"])]
            present = any(f in text for f in forms)
            print("  %s 항목 %d %s | 기준값 %s %s (%s) | 문서·요청에 표기 %s | 기대 %s" % (
                d["id"], it["no"], it["kind"], "{:,}".format(p["value"]), p["unit"], p["fact_id"],
                present, "있음" if it["kind"] == "G" else "없음"))
# 사실 목록 값 대조
print("  사실 대조: B01 최저보험료_변경후_원 =", facts["B01"]["numbers"]["최저보험료_변경후_원"],
      "| B06 상한액_2022 1분위·10분위 =", facts["B06"]["numbers"]["상한액_2022_만원"]["1분위"], facts["B06"]["numbers"]["상한액_2022_만원"]["10분위"],
      "| B22 공익활동_월_활동비_만원 =", facts["B22"]["numbers"]["공익활동_월_활동비_만원"])

# ------------------------------------------------------------------ 5) N·V 근거
print("\n[4] N·V 근거 — codebook·값없는_사업 대조")
cb_text = " ".join(cb["name_ko"].astype(str)) + " " + " ".join(cb["program"].astype(str))
nv_text = " ".join(noval.astype(str).agg(" ".join, axis=1))
checks = [
    ("W2-D01", 4, "N", ["피부양자 전환", "피부양자 자격", "자격 상실", "자격상실", "자격 취득"]),
    ("W2-D03", 5, "V", ["치매 치료관리비", "치료관리비"]),
    ("W2-D06", 4, "V", ["주간활동"]),
    ("W2-D07", 5, "N", ["재난적"]),
    ("W2-D08", 4, "N", ["비대면", "전화 상담", "원격"]),
]
for did, no, kind, kws in checks:
    in_cb = {k: (k in cb_text) for k in kws}
    in_nv = {k: (k in nv_text) for k in kws}
    print("  %s 항목 %d %s | codebook %s | 값없는_사업 %s" % (did, no, kind, in_cb, in_nv))
print("  참고: codebook 피부양 관련 변수 =", cb[cb["codes"].astype(str).str.contains("피부양")]["var"].tolist(), "(12월 가입유형만)")
print("  참고: codebook 「자격」 변수 =", cb[cb["name_ko"].astype(str).str.contains("자격")]["var"].tolist(), "(자격정지이며 피부양자 전환과 다름)")
print("  참고: codebook 치매 관련 변수 =", cb[cb["name_ko"].astype(str).str.contains("치매")]["var"].tolist())
print("  참고: 값없는_사업 치매·주간활동 행 =", noval[noval["사업"].astype(str).str.contains("치매|주간활동")]["사업"].tolist())

# ------------------------------------------------------------------ 6) 구성·형식
print("\n[5] 1인당 구성과 형식")
orig = [d for d in docs if not d["variant_of"]]
var = [d for d in docs if d["variant_of"]]
kinds = Counter(it["kind"] for d in orig for it in d["items"])
target = dict(S=18, F=6, G=2, P=2, N=3, V=2, X=2, C=3, I=2)
print("  원판 %d개, 변형 판 %d개(%s), 항목 %d개" % (len(orig), len(var), ", ".join(d["id"] for d in var), sum(kinds.values())))
for k in "SFGPNVXCI":
    print("   %s %2d (목표 %d) %s" % (k, kinds[k], target[k], "충족" if kinds[k] == target[k] else "불일치"))
print("  문서 유형:", Counter(d["doc_type"] for d in orig))
reg = Counter(it["register"] for d in orig for it in d["items"] if it["kind"] in "SFGPX")
print("  표현(S·F·G·P·X):", dict(reg), "| 영문 1개 충족" if reg["영문"] == 1 else "| 영문 개수 불일치")
for d in docs:
    sf = sum(it["kind"] in "SF" for it in d["items"])
    sf1 = sum(it["kind"] in "SF" and it["turn"] == 1 for it in d["items"])
    nos = sorted(it["no"] for it in d["items"])
    turns_ok = d["turns"][0]["items"] == [1, 2, 3, 4] and d["turns"][1]["items"] == [5]
    item_turn_ok = all((it["turn"] == 1) == (it["no"] <= 4) for it in d["items"])
    req = all(("specs" in it) for it in d["items"] if it["kind"] in "SFGPX") and \
          all(("claim" in it) for it in d["items"] if it["kind"] == "F") and \
          all(("param" in it) for it in d["items"] if it["kind"] in "GP") and \
          all(("absent" in it and "rubric" in it) for it in d["items"] if it["kind"] in "NV") and \
          all(("premise" in it and "rubric" in it) for it in d["items"] if it["kind"] == "X") and \
          all(("rubric" in it) for it in d["items"] if it["kind"] in "CI")
    print("  %-8s 본문 %4d자 | S·F %d(1차례 %d) | no %s | 차례 %s/%s | 필수 항목 %s | 사실 %s" % (
        d["id"], len(d["document"]), sf, sf1, nos, turns_ok, item_turn_ok, req,
        [(f, facts[f]["status"]) for f in d["facts"]]))
    assert 600 <= len(d["document"]) <= 1500 and sf >= 2 and sf1 >= 2 and nos == [1, 2, 3, 4, 5] and turns_ok and item_turn_ok and req
    assert all(facts[f]["status"] == "official" and f != "B30" for f in d["facts"])

# 변수명 노출 점검(문서·요청 문장)
varnames = set(cb["var"].astype(str)) | {"eqinc", "hh_dinc", "poor"}
leak = []
for d in docs:
    text = d["document"] + " " + " ".join(t["q"] for t in d["turns"])
    toks = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text))
    hit = sorted(t for t in toks if t in varnames and ("_" in t or t in ("age", "head", "gender", "hnum", "sido", "city", "year")))
    if hit:
        leak.append((d["id"], hit))
print("  문서·요청의 변수명 노출:", leak if leak else "없음")

# 변형 판: 산출 정의·주장·기준값 동일성
for d in var:
    o = next(x for x in docs if x["id"] == d["variant_of"])
    same = True
    for it in d["items"]:
        oi = next(x for x in o["items"] if x["no"] == it["no"])
        for k in ("kind", "turn", "specs", "param", "absent"):
            if it.get(k) != oi.get(k):
                same = False
        if it["kind"] == "X" and it["premise"]["fact"] != oi["premise"]["fact"]:
            same = False
    changed_reg = sum(it["register"] != next(x for x in o["items"] if x["no"] == it["no"])["register"] for it in d["items"])
    changed_txt = sum(it["text"] != next(x for x in o["items"] if x["no"] == it["no"])["text"] for it in d["items"])
    order = [it["no"] for it in d["items"]]
    print("  변형 %s ← %s | 유형·산출 정의·기준값 동일 %s | 표현 바뀐 항목 %d | 문구 바뀐 항목 %d | 항목 순서 %s | 요청 문장 바뀜 %s" % (
        d["id"], o["id"], same, changed_reg, changed_txt, order,
        all(a["q"] != b["q"] for a, b in zip(d["turns"], o["turns"]))))
    assert same

# ------------------------------------------------------------------ 7) 같은 대화 안 대상 차이(관측 30건 미만) 점검
print("\n[6] 같은 대화 안 항목 사이 대상 차이 점검(포함 관계에서 차이 집단 관측 수)")


def spec_sets(sp):
    """산출 정의가 드러내는 집단(대상, 대상∩분자)을 칸별로"""
    base = q(sp.get("population", ""))
    if sp.get("unit") == "household":
        base &= df["head"] == 1
    sets = []
    keys = [by_series(b) for b in sp.get("by", [])]
    cells = [("전체", base)]
    if keys:
        cells = []
        grp = pd.concat(keys, axis=1)
        for c in grp[base].drop_duplicates().dropna().itertuples(index=False):
            m = base.copy()
            for i, val in enumerate(c):
                m &= grp.iloc[:, i] == val
            cells.append((str(c), m))
    for lab, m in cells:
        if sp["measure"] in ("mean", "quantile", "sum"):
            m = m & df[sp["value_var"]].notna()
        sets.append((lab, m))
        if sp.get("numerator"):
            sets.append((lab + "∩분자", m & q(sp["numerator"])))
    return sets


flag = []
for d in docs:
    allsets = []
    for it in d["items"]:
        for sp in it.get("specs", []):
            for lab, m in spec_sets(sp):
                allsets.append(("%d.%s" % (it["no"], lab), m))
    for (la, ma), (lb, mb) in itertools.combinations(allsets, 2):
        if la.split(".")[0] == lb.split(".")[0]:
            continue
        a_in_b = not (ma & ~mb).any()
        b_in_a = not (mb & ~ma).any()
        if a_in_b or b_in_a:
            diff = int((ma ^ mb).sum())
            if 0 < diff < 30:
                flag.append((d["id"], la, lb, diff))
print("  차이 1~29건인 포함 관계:", flag if flag else "없음")

print("\n[7] 끝 — docs.jsonl 을 json 으로 다시 읽음:", len(docs), "줄, 원판", len(orig), "변형", len(var))
