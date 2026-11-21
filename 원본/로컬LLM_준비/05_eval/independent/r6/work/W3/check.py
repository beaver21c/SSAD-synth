# -*- coding: utf-8 -*-
"""W3 문서형 과제 검산(6차).

1) docs.jsonl 을 json 으로 다시 읽어 형식 확인
2) 산출 정의(specs)를 pandas 로 직접 계산(칸별 가중 값, 관측 수, 비율의 분자·여집합 관측 수)
3) 문서 문구에서 다시 풀어 쓴 계산(정의와 독립된 코드)과 대조
4) F 항목: 주장 수치와 자료 값 대조, 틀린 주장의 차이 크기 확인
5) 같은 대화 안 대상 차이 소집단(관측 30건 미만) 점검
6) 1인당 구성(유형별 수, 맞는·틀린 주장, 영문 1개, 변형 3개, 문서 유형 수) 세기
7) N·V 근거(codebook.tsv, 값없는_사업.tsv) 확인, 문서에 변수명이 없는지, P 기준값이 문서에 없는지 확인

실행: /mnt/share/행정데이터_set/.venv/bin/python check.py > check_output.txt
"""
import json
import math
import re
from itertools import combinations

import numpy as np
import pandas as pd

BASE = "/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent"
DOCS = BASE + "/r6/work/W3/docs.jsonl"
DATA = "/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet"
CODEBOOK = BASE + "/inputs/codebook.tsv"
NOVAL = BASE + "/r5/inputs/값없는_사업.tsv"
FACTS = [BASE + "/r5/facts/facts_%s.jsonl" % k for k in "ABC"]

df = pd.read_parquet(DATA)
W = "indwgt"
cb = pd.read_csv(CODEBOOK, sep="\t")
noval = pd.read_csv(NOVAL, sep="\t")
facts = {}
for p in FACTS:
    for line in open(p, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            facts[r["id"]] = r

# ------------------------------------------------------------------ 1. 형식
docs = []
with open(DOCS, encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        docs.append(json.loads(line))
print("=" * 78)
print("1. docs.jsonl 형식: %d줄을 json 으로 읽음" % len(docs))
REQ_DOC = ["id", "doc_type", "issue", "facts", "persona", "setting", "document", "turns", "items", "variant_of"]
REQ_ITEM = ["no", "turn", "kind", "register", "text", "specs", "rubric", "note"]
fmt_err = []
for d in docs:
    for k in REQ_DOC:
        if k not in d:
            fmt_err.append((d.get("id"), "문서 키 없음 " + k))
    if [i["no"] for i in d["items"]] != [1, 2, 3, 4, 5]:
        fmt_err.append((d["id"], "항목 번호"))
    t1 = [t for t in d["turns"] if t["n"] == 1][0]
    t2 = [t for t in d["turns"] if t["n"] == 2][0]
    if sorted(t1["items"]) != [1, 2, 3, 4] or t2["items"] != [5]:
        fmt_err.append((d["id"], "차례별 항목"))
    for it in d["items"]:
        for k in REQ_ITEM:
            if k not in it:
                fmt_err.append((d["id"], it.get("no"), "항목 키 없음 " + k))
        if it["turn"] != (1 if it["no"] <= 4 else 2):
            fmt_err.append((d["id"], it["no"], "turn 값"))
        need = {"S": ["specs"], "F": ["specs", "claim"], "G": ["specs", "param"], "P": ["specs", "param"],
                "N": ["absent"], "V": ["absent"], "X": ["premise"], "C": [], "I": []}[it["kind"]]
        for k in need:
            if not it.get(k):
                fmt_err.append((d["id"], it["no"], "필수 " + k))
print("   형식 오류:", fmt_err if fmt_err else "없음")

# ------------------------------------------------------------------ 2. 산출 정의 계산기
SEX = {1: "남", 2: "여"}


def std_key(name, d):
    a = d["age"]
    if name == "sex":
        return d["gender"].map(SEX)
    if name == "age3":
        return pd.cut(a, [-np.inf, 18, 65, np.inf], right=False, labels=["0~17세", "18~64세", "65세 이상"])
    if name == "age6":
        return pd.cut(a, [-np.inf, 18, 35, 50, 65, 75, np.inf], right=False,
                      labels=["0~17", "18~34", "35~49", "50~64", "65~74", "75세 이상"])
    if name == "sido":
        return d["sido"]
    raise ValueError(name)


def by_key(b, d):
    if "std" in b:
        return std_key(b["std"], d)
    if "var" in b:
        edges = [-np.inf] + list(b["bins"]) + [np.inf]
        return pd.cut(d[b["var"]], edges, right=False, labels=b["labels"])
    if "cat" in b:
        return d[b["cat"]]
    if "groups" in b:
        raise NotImplementedError
    raise ValueError(b)


def q(expr, d):
    if not expr:
        return pd.Series(True, index=d.index)
    return d.eval(expr, engine="python").fillna(False).astype(bool)


def eval_spec(s):
    """칸별 (값, 관측 수, 분자 관측, 여집합 관측) 목록을 돌려줌."""
    d = df
    w = W
    if s.get("unit") == "household":
        d = df[df["head"] == 1]
        w = "hhwgt"
    pop = d[q(s.get("population", ""), d)]
    keys = [by_key(b, pop) for b in s.get("by", [])]
    if keys:
        groups = pop.groupby(keys, observed=True)
    else:
        groups = [("전체", pop)]
    out = []
    for k, g in groups:
        m = s["measure"]
        if m == "count":
            out.append((k, g[w].sum(), len(g), None, None))
        elif m == "rate":
            num = q(s["numerator"], g)
            out.append((k, 100 * g.loc[num, w].sum() / g[w].sum(), len(g), int(num.sum()), int((~num).sum())))
        elif m == "mean":
            gg = g[g[s["value_var"]].notna()]
            out.append((k, np.average(gg[s["value_var"]], weights=gg[w]), len(gg), None, None))
        elif m == "share":
            vv = s["value_var"]
            cat = by_key(vv, g) if isinstance(vv, dict) else g[vv]
            tot = g[w].sum()
            for c, gc in g.groupby(cat, observed=True):
                out.append(((k, c) if keys else c, 100 * gc[w].sum() / tot, len(gc), None, None))
        else:
            raise ValueError(m)
    return out


def disp(v, measure):
    if measure in ("rate", "share"):
        return "%.1f%%" % v
    if v == 0:
        return "0"
    mag = int(math.floor(math.log10(abs(v))))
    return "{:,.0f}".format(round(v, -(mag - 2)))


# ------------------------------------------------------------------ 3. 문서 문구에서 다시 풀어 쓴 계산
# 정의를 읽지 않고 문서 문장만 보고 쓴 코드. numpy 마스크로 따로 계산함.
w = df[W].to_numpy()
age = df["age"].to_numpy()
G = df["gender"].to_numpy()


def is1(v):
    return (df[v] == 1).to_numpy()


def wsum(m):
    return w[m].sum()


def wrate(num, den):
    return 100 * w[num & den].sum() / w[den].sum()


def wmean(v, m):
    x = df[v].to_numpy()
    m = m & ~np.isnan(x)
    return (x[m] * w[m]).sum() / w[m].sum()


def bands(edges):
    # edges: 구간 시작값(둘째 구간부터, 이상)
    idx = np.searchsorted(np.array(edges), age, side="right")
    return idx


manual = {}
# D01
m_kua = is1("kua_yn1")
manual[("W3-D01", 1)] = [wsum(m_kua & (df.kua_type == 1).to_numpy()), wsum(m_kua & (df.kua_type == 2).to_numpy())]
b = bands([35, 50])
manual[("W3-D01", 2)] = [100 * wsum(m_kua & (b == i)) / wsum(m_kua) for i in range(3)]
manual[("W3-D01", 3)] = [wmean("kua_jobseekbn_amt", m_kua & (df.kua_type == 1).to_numpy())]
# D02
m_es = is1("empins_support_yn1")
manual[("W3-D02", 1)] = [wsum(m_es), wsum(is1("np_support_yn1"))]
manual[("W3-D02", 2)] = [wrate(is1("empins_support_yn2"), m_es)]
manual[("W3-D02", 3)] = [wmean("empins_support_amt", m_es)]
b = bands([35, 50, 65])
manual[("W3-D02", 4)] = [wsum(m_es & (b == i)) for i in range(4)]
# D03
m_js = is1("unempbn_jobseekbn_yn")
manual[("W3-D03", 1)] = [wsum(m_js)]
manual[("W3-D03", 2)] = [wrate(age >= 50, m_js)]
daily = (df.unempbn_jobseekbn_amt / df.unempbn_jobseekbn_dur).to_numpy()
manual[("W3-D03", 3)] = [wrate(np.nan_to_num(daily) >= 66000, m_js)]
manual[("W3-D03", 5)] = [wmean("unempbn_jobseekbn_amt", m_js & (G == 1)), wmean("unempbn_jobseekbn_amt", m_js & (G == 2))]
# D04
st = df.np_status.to_numpy()
tp = df.np_type.to_numpy()
inc = df.np_inc_amt.to_numpy()
manual[("W3-D04", 1)] = [wsum(tp == c) for c in (0, 1, 5, 9)]
manual[("W3-D04", 2)] = [wrate(st == 3, tp == 1)]
manual[("W3-D04", 3)] = [wrate(np.nan_to_num(inc) >= 5530000, st == 1)]
manual[("W3-D04", 5)] = [wrate((inc <= 350000) & ~np.isnan(inc), st == 1)]
# D05
m_y = is1("youthemp_yn1")
manual[("W3-D05", 1)] = [wsum(m_y), wsum(is1("youthemp_yn2"))]
manual[("W3-D05", 2)] = [wrate((df.youthemp_cnt2 == 0).to_numpy(), m_y)]
manual[("W3-D05", 3)] = [wmean("youthemp_cnt3", m_y)]
manual[("W3-D05", 5)] = [wmean("youthemp_amt1", (df.youthemp_amt1 > 0).to_numpy())]
# D06
m_v = is1("vocaedu_yn")
manual[("W3-D06", 1)] = [wsum(m_v & (G == 1)), wsum(m_v & (G == 2))]
b = bands([35, 50])
manual[("W3-D06", 2)] = [wmean("vocaedu_amt", m_v & (b == i)) for i in range(3)]
manual[("W3-D06", 3)] = [wrate(is1("empins_yn1"), m_v)]
# D07
m_l = is1("occupins_lump_yn")
manual[("W3-D07", 1)] = [wsum(is1("occupins_pension_yn")), wsum(m_l)]
manual[("W3-D07", 2)] = [wmean("occupins_lump_amt", m_l & (G == 1)), wmean("occupins_lump_amt", m_l & (G == 2))]
b = bands([50, 65])
manual[("W3-D07", 4)] = [100 * wsum(m_l & (b == i)) / wsum(m_l) for i in range(3)]
# D08
a1864 = (age >= 18) & (age <= 64)
m_e = is1("empins_yn1")
manual[("W3-D08", 1)] = [wrate(m_e, a1864)]
manual[("W3-D08", 2)] = [wrate(m_e, a1864 & (G == 1)), wrate(m_e, a1864 & (G == 2))]
lab = df.p_labinc.to_numpy()
lab2 = df.labinc_sum_taxy.to_numpy()
manual[("W3-D08", 3)] = [wrate(lab < 22973280, m_e & (lab > 0)),
                         wrate(np.nan_to_num(lab2, nan=9e18) < 22973280, m_e & ~np.isnan(lab2))]
manual[("W3-D08", 4)] = [wsum(is1("empins_yn2"))]
manual[("W3-D08", 5)] = [wrate(m_e, df.p_dainc.to_numpy() > 0)]

# ------------------------------------------------------------------ 계산 출력
print()
print("=" * 78)
print("2~4. 산출 정의 계산(칸별 가중 값 / 관측 수) · 문서 문구 재계산 대조 · 주장 대조")
grade = dict(zip(cb["var"], cb["sensitivity_grade"]))
mismatch = []
lowcell = []
f_rows = []
vals = {}
originals = [d for d in docs if not d["variant_of"]]
for d in originals:
    print()
    print("-" * 78)
    print("[%s] %s / %s" % (d["id"], d["doc_type"], d["issue"]))
    for it in d["items"]:
        if not it["specs"]:
            print("  항목 %d (%s): 산출 정의 없음" % (it["no"], it["kind"]))
            continue
        print("  항목 %d (%s, %s): %s" % (it["no"], it["kind"], it["register"], it["text"][:70]))
        spec_vals = []
        for s in it["specs"]:
            tag = []
            if "sub" in s:
                tag.append("sub%d" % s["sub"])
            if "alt" in s:
                tag.append("alt%d" % s["alt"])
            res = eval_spec(s)
            desc = "%s | pop: %s" % (s["measure"], s.get("population"))
            if s.get("numerator"):
                desc += " | num: %s" % s["numerator"]
            if s.get("value_var"):
                desc += " | var: %s" % (s["value_var"] if isinstance(s["value_var"], str) else "구간" + str(s["value_var"]["bins"]))
            if s.get("by"):
                desc += " | by: %s" % s["by"]
            print("    정의 %s %s" % (" ".join(tag), desc))
            for k, v, n, nn, nc in res:
                extra = ""
                if nn is not None:
                    extra = " (분자 %d, 여집합 %d)" % (nn, nc)
                print("      %-14s %18s  [표시 %s]  관측 %d%s" % (str(k), "{:,.4f}".format(v), disp(v, s["measure"]), n, extra))
                main_n = min([x for x in (n, nn, nc) if x is not None])
                if main_n < 30:
                    lowcell.append((d["id"], it["no"], str(k), main_n))
            spec_vals.append([r[1] for r in res])
        # 문서 문구 재계산 대조
        flat = [v for sv in spec_vals for v in sv]
        man = manual.get((d["id"], it["no"]))
        if man is not None:
            ok = len(man) == len(flat) and all(abs(a - b) <= 1e-6 * max(1, abs(a)) for a, b in zip(man, flat))
            print("    문서 문구 재계산: %s → %s" % (["{:,.4f}".format(x) for x in man], "일치" if ok else "불일치"))
            if not ok:
                mismatch.append((d["id"], it["no"]))
        vals[(d["id"], it["no"])] = flat
        if it["kind"] == "F":
            c = it["claim"]
            v = flat[0]
            if c["unit"] == "%":
                diff = v - c["claimed_value"]
                shown = round(v, 1)
                verdict = abs(shown - c["claimed_value"]) < 0.05
                gap = "차이 %.1f%%p" % abs(diff)
                big = abs(diff) >= 3
            else:
                rel = (c["claimed_value"] - v) / v
                verdict = abs(rel) < 0.005
                gap = "상대 차이 %.1f%%" % (100 * abs(rel))
                big = abs(rel) >= 0.10
            print("    주장 대조: 주장 %s%s | 자료 %s | 자료상 판정 %s | 기록 true=%s | %s"
                  % (c["claimed_value"], c["unit"], "{:,.2f}".format(v), "맞음" if verdict else "틀림", c["true"], gap))
            f_rows.append((d["id"], it["no"], c["true"], verdict, big))
        if it["kind"] in ("G", "P"):
            print("    기준값: %s = %s%s (사실 %s, 문서에 적힘=%s)" % (it["param"]["name"], it["param"]["value"],
                  it["param"]["unit"], it["param"]["fact"], it["param"]["in_document"]))
        if it["kind"] == "X":
            print("    틀린 전제: %s → 바른 사실: %s (%s)" % (it["premise"]["error"], it["premise"]["correct"], it["premise"]["fact"]))

print()
print("  문서 문구 재계산 불일치:", mismatch if mismatch else "없음")
print("  관측 30건 미만 칸:", lowcell if lowcell else "없음")
print("  F 항목(기록 true / 자료상 판정 / 틀린 주장의 차이 기준 충족):")
for r in f_rows:
    flag = "정상" if (r[2] == r[3]) and (r[2] or r[4]) else "확인 필요"
    print("    %s 항목 %d: true=%s, 자료상 %s, 차이 기준=%s → %s" % (r[0], r[1], r[2], "맞음" if r[3] else "틀림", r[4], flag))

# 변수 민감도 등급(참고)
print("  사용 변수의 민감도 등급:")
used = set()
for d in originals:
    for it in d["items"]:
        for s in it["specs"]:
            for k in ("population", "numerator"):
                for tok in re.findall(r"[a-z][a-z0-9_]+", s.get(k) or ""):
                    if tok in grade:
                        used.add(tok)
            if isinstance(s.get("value_var"), str):
                used.add(s["value_var"])
print("    " + ", ".join("%s(%s)" % (v, grade.get(v)) for v in sorted(used)))

# ------------------------------------------------------------------ 5. 같은 대화 안 소집단 점검
print()
print("=" * 78)
print("5. 같은 대화(문서) 안 대상 집합 차이 점검(차집합 관측 1~29건이면 표시)")


def masks_of(spec):
    d = df
    pop = q(spec.get("population", ""), d)
    out = [("pop", pop)]
    if spec.get("numerator"):
        num = q(spec["numerator"], d) & pop
        out.append(("num", num))
    for bb in spec.get("by", []):
        key = by_key(bb, d)
        for c in pd.unique(key[pop]):
            out.append(("cell:%s" % c, pop & (key == c)))
    return out


small = []
for d in originals:
    ms = []
    for it in d["items"]:
        for s in it["specs"]:
            for name, m in masks_of(s):
                ms.append(("%d.%s" % (it["no"], name), m.to_numpy()))
    for (na, a), (nb, bm) in combinations(ms, 2):
        if na.split(".")[0] == nb.split(".")[0] and na.endswith("pop") and nb.endswith("pop"):
            pass
        ab = int((a & ~bm).sum())
        ba = int((bm & ~a).sum())
        if (ab == 0 and 0 < ba < 30) or (ba == 0 and 0 < ab < 30):
            small.append((d["id"], na, nb, ab, ba))
print("   소집단 차이:", small if small else "없음")

# ------------------------------------------------------------------ 6. 1인당 구성
print()
print("=" * 78)
print("6. 1인당 구성 점검")
kinds = {}
for d in originals:
    for it in d["items"]:
        kinds[it["kind"]] = kinds.get(it["kind"], 0) + 1
target = {"S": 18, "F": 6, "G": 2, "P": 2, "N": 3, "V": 2, "X": 2, "C": 3, "I": 2}
print("   원판 문서 수: %d, 항목 수: %d" % (len(originals), sum(kinds.values())))
for k in "SFGPNVXCI":
    print("   %s: %d (목표 %d) %s" % (k, kinds.get(k, 0), target[k], "일치" if kinds.get(k, 0) == target[k] else "불일치"))
ft = sum(1 for d in originals for it in d["items"] if it["kind"] == "F" and it["claim"]["true"])
ff = sum(1 for d in originals for it in d["items"] if it["kind"] == "F" and not it["claim"]["true"])
print("   F 맞는 주장 %d, 틀린 주장 %d (목표 3·3)" % (ft, ff))
regs = {}
for d in originals:
    for it in d["items"]:
        if it["kind"] in "SFGPX":
            regs[it["register"]] = regs.get(it["register"], 0) + 1
print("   register(원판 S·F·G·P·X):", regs, "영문 1개" if regs.get("영문") == 1 else "영문 개수 확인 필요")
types = sorted(set(d["doc_type"] for d in originals))
print("   문서 유형 %d종: %s" % (len(types), types))
for d in originals:
    sf_all = sum(1 for it in d["items"] if it["kind"] in "SF")
    sf_t1 = sum(1 for it in d["items"] if it["kind"] in "SF" and it["turn"] == 1)
    print("   %s: S·F %d개, 1차례 S·F %d개 %s" % (d["id"], sf_all, sf_t1, "충족" if sf_all >= 2 and sf_t1 >= 2 else "미충족"))
variants = [d for d in docs if d["variant_of"]]
print("   변형 판 %d개: %s" % (len(variants), [(v["id"], v["variant_of"]) for v in variants]))
for v in variants:
    o = next(d for d in docs if d["id"] == v["variant_of"])
    same = True
    for a, b in zip(o["items"], v["items"]):
        if a["no"] != b["no"] or a["kind"] != b["kind"] or a["specs"] != b["specs"]:
            same = False
        for k in ("param", "premise", "absent"):
            if a.get(k) != b.get(k):
                same = False
        if a.get("claim"):
            if (a["claim"]["claimed_value"], a["claim"]["true"], a["claim"]["unit"]) != (b["claim"]["claimed_value"], b["claim"]["true"], b["claim"]["unit"]):
                same = False
    changed_reg = [(a["no"], a["register"], b["register"]) for a, b in zip(o["items"], v["items"]) if a["register"] != b["register"]]
    print("     %s: 항목·산출 정의·기준값·주장 값 동일=%s, 문서 본문 변경=%s, 요청 문장 변경=%s, register 변경=%s"
          % (v["id"], same, v["document"] != o["document"], [t["q"] for t in v["turns"]] != [t["q"] for t in o["turns"]], changed_reg))
    # 변형 판의 주장 수치가 문서에 그대로 있는지
    for b in v["items"]:
        if b.get("claim"):
            cv = b["claim"]["claimed_value"]
            s = ("%g" % cv) if b["claim"]["unit"] == "%" else None
            if s and s not in v["document"]:
                print("       주의: 주장 수치 %s 가 변형 문서에 없음" % s)

# ------------------------------------------------------------------ 7. 문서 점검
print()
print("=" * 78)
print("7. 문서 점검")
varnames = set(cb["var"]) | set(df.columns)
for d in docs:
    text = d["document"] + " " + " ".join(t["q"] for t in d["turns"])
    found = sorted(set(t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text) if t in varnames))
    bad_tok = sorted(set(re.findall(r"\b[a-z]+_[a-z0-9_]+\b", text)))
    n = len(d["document"])
    fids = d["facts"]
    fstat = [(f, facts[f]["status"]) for f in fids]
    okf = all(s == "official" for _, s in fstat) and "B30" not in fids
    print("   %-8s 본문 %4d자(600~1,500: %s) | 변수명 %s | 밑줄 토큰 %s | 사실 %s %s"
          % (d["id"], n, "충족" if 600 <= n <= 1500 else "미충족", found if found else "없음",
             bad_tok if bad_tok else "없음", fids, "official" if okf else "확인 필요"))
# 단어 단위로 변수명과 같은 한 단어(예: age, year, head, city)가 문서에 있으면 위에서 표시됨

# P 기준값이 문서·요청에 없는지, G 기준값이 문서에 있는지
pchecks = {"66000": ["66,000", "66000", "6만 6천", "6만6천"], "350000": ["35만", "350,000", "350000"],
           "5530000": ["553만"], "22973280": ["22,973,280"]}
for d in docs:
    text = d["document"] + " " + " ".join(t["q"] for t in d["turns"]) + " " + " ".join(i["text"] for i in d["items"])
    for it in d["items"]:
        if it["kind"] in ("G", "P"):
            pats = pchecks[str(it["param"]["value"])]
            hit = [p for p in pats if p in text]
            want = it["kind"] == "G"
            print("   %s 항목 %d (%s): 기준값 표기 %s → %s" % (d["id"], it["no"], it["kind"], hit if hit else "없음",
                  "적합" if bool(hit) == want else "부적합"))

# 약칭이 사실 목록 aliases 에 있는지
alias_all = set(a for f in facts.values() for a in f["aliases"])
print("   약칭 항목의 약칭어(사실 목록 aliases 대조):")
alias_used = {("W3-D01", 2): "한국형 실업부조", ("W3-D02", 1): "두루누리", ("W3-D03", 1): "실업급여",
              ("W3-D05", 2): "청년공제", ("W3-D06", 2): "내일배움카드", ("W3-D01v", 1): "한국형 실업부조"}
for (did, no), a in alias_used.items():
    d = next(x for x in docs if x["id"] == did)
    it = d["items"][no - 1]
    print("     %s 항목 %d: %s | aliases 에 있음=%s | 항목 문구에 있음=%s | register=%s"
          % (did, no, a, a in alias_all, a in it["text"], it["register"]))

# N·V 근거
print()
print("   N·V 근거 확인")
cbtext = (cb["var"].astype(str) + " " + cb["name_ko"].astype(str) + " " + cb["program"].astype(str)).str.cat(sep="\n")


def cb_hits(word):
    return [l.split(" ")[0] for l in cbtext.split("\n") if word in l]


def nv_hits(word):
    return noval[noval.apply(lambda r: word in str(r["사업"]) or word in str(r["변수 이름(일부)"]), axis=1)][["사업", "보유기관"]].values.tolist()


checks = [("W3-D01", 4, "N", ["조기취업", "조기 취업"]),
          ("W3-D04", 4, "N", ["지역가입자 연금보험료", "지역가입자 보험료", "납부재개", "보험료 지원"]),
          ("W3-D07", 3, "N", ["산재보험 가입", "산재보험 적용", "산재", "특수형태", "노무제공"]),
          ("W3-D03", 4, "V", ["상병급여"]),
          ("W3-D06", 4, "V", ["시니어인턴십", "시니어"])]
for did, no, kind, words in checks:
    for wd in words:
        print("     %s 항목 %d (%s) '%s': codebook %s | 값없는_사업 %s" % (did, no, kind, wd, cb_hits(wd), nv_hits(wd)))
sick = [c for c in df.columns if "sickness" in c]
print("     상병급여 관련 자료 열과 값이 있는 행 수:", {c: int((df[c].fillna(0) != 0).sum()) for c in sick})
print("     codebook 의 국민취업지원제도 변수:", cb.loc[cb.program == "국민취업지원제도", "name_ko"].tolist())
print("     codebook 의 산재보험 관련 변수:", cb.loc[cb.name_ko.str.contains("산재"), "var"].tolist())
print("     codebook 의 노인일자리 프로그램:", sorted(set(cb.loc[cb.name_ko.str.contains("노인일자리"), "program"])))

print()
print("끝")
