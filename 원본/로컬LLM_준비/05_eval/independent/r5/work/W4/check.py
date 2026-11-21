# -*- coding: utf-8 -*-
"""W4 과제의 스스로 대조(check.py)

1부  cases.jsonl 의 형식·구성(유형·표현 수, 차례 규칙, 사실 id) 점검
2부  산출 정의(specs)를 정의대로 계산한 값(「정의」)과, 질문 문장에서 다시 풀어
     pandas 불 조건으로 직접 계산한 값(「직접」)의 대조. 칸별 가중 값과 가중하지 않은 관측 수 출력
3부  관계 점검(relations)의 성립 여부
4부  N·V 차례의 「자료에 없음」 확인(codebook.tsv, 값없는_사업.tsv, 자료 값)

실행: /mnt/share/행정데이터_set/.venv/bin/python check.py > check_output.txt
"""
import json
import os
from collections import Counter

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent"
DATA = "/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet"
CASES = os.path.join(HERE, "cases.jsonl")
CODEBOOK = os.path.join(BASE, "inputs", "codebook.tsv")
NOVALUE = os.path.join(BASE, "r5", "inputs", "값없는_사업.tsv")
FACTS = [os.path.join(BASE, "r5", "facts", f"facts_{x}.jsonl") for x in "ABC"]

pd.set_option("display.width", 200)

# ───────────────────────── 자료와 파생 변수(자료_규약.md)
df = pd.read_parquet(DATA)
df["hh_dinc"] = df.groupby("hid")["p_dinc"].transform("sum")
df["eqinc"] = df["hh_dinc"] / np.sqrt(df["hnum"])


def wquantile(v, w, q):
    """가중 분위수: 오름차순으로 놓고 가중치 누적합이 전체의 q배에 처음 이르는 값."""
    v = np.asarray(v, dtype=float)
    w = np.asarray(w, dtype=float)
    o = np.argsort(v, kind="mergesort")
    c = np.cumsum(w[o])
    return v[o][np.searchsorted(c, q * c[-1], side="left")]


MED = wquantile(df["eqinc"], df["indwgt"], 0.5)
df["poor"] = (df["eqinc"] < 0.5 * MED).astype(int)
CUTS = [wquantile(df["eqinc"], df["indwgt"], q) for q in (0.2, 0.4, 0.6, 0.8)]
df["_inc5"] = np.searchsorted(CUTS, df["eqinc"].values, side="right")  # 경계값 이상이면 위 분위

SIDO = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]


def std_labels(frame, name):
    if name == "sex":
        return frame["gender"].map({1: "남", 2: "여"})
    if name == "sido":
        return frame["sido"].map({i + 1: s for i, s in enumerate(SIDO)})
    if name == "inc5":
        return frame["_inc5"].map({i: f"{i + 1}분위" for i in range(5)})
    if name == "nhi3":
        return frame["nhi_type"].map({1: "지역가입", 2: "지역가입", 5: "직장가입", 6: "직장가입", 7: "의료급여", 8: "의료급여"})
    if name == "hs4":
        return frame["hnum"].clip(upper=4).map({1: "1인", 2: "2인", 3: "3인", 4: "4인 이상"})
    if name == "poor2":
        return frame["poor"].map({0: "비빈곤", 1: "빈곤"})
    if name == "age3":
        return pd.cut(frame["age"], [-1, 17, 64, 200], labels=["0~17세", "18~64세", "65세 이상"]).astype(str)
    if name == "age6":
        return pd.cut(frame["age"], [-1, 17, 34, 49, 64, 74, 200], labels=["0~17세", "18~34세", "35~49세", "50~64세", "65~74세", "75세 이상"]).astype(str)
    raise ValueError(name)


# ───────────────────────── 산출 정의를 정의대로 계산(「정의」)
def by_labels(frame, by):
    """분류 기준 목록 → 행별 칸 이름(해당 없는 행은 NaN)."""
    if not by:
        return pd.Series("전체", index=frame.index)
    parts = []
    for b in by:
        if "std" in b:
            s = std_labels(frame, b["std"])
        elif "var" in b:
            idx = np.searchsorted(b["bins"], frame[b["var"]].values, side="right")
            s = pd.Series([b["labels"][i] for i in idx], index=frame.index)
        elif "cat" in b:
            s = frame[b["cat"]].map(lambda x: None if pd.isna(x) else f"{b['cat']}={int(x)}")
        elif "groups" in b:
            s = pd.Series([None] * len(frame), index=frame.index, dtype=object)
            for g in reversed(b["groups"]):
                hit = frame.query(g["cond"], engine="python").index
                s.loc[hit] = g["label"]
        else:
            raise ValueError(b)
        parts.append(s)
    out = parts[0].astype(object)
    for s in parts[1:]:
        out = out.where(out.isna() | s.isna(), out.astype(str) + " × " + s.astype(str))
        out = out.where(~s.isna(), None)
    return out


def eval_spec(spec):
    """돌려주는 값: [(칸, 값, 관측 수 설명, 최소 관측 수)]"""
    unit = spec.get("unit", "person")
    base = df[df["head"] == 1] if unit == "household" else df
    wname = "hhwgt" if unit == "household" else "indwgt"
    pop = base.query(spec["population"], engine="python") if spec["population"] else base
    m = spec["measure"]
    rows = []
    if m == "share":
        vv = spec["value_var"]
        cat = std_labels(pop, vv) if vv in ("sex", "sido", "inc5", "nhi3", "hs4", "poor2", "age3", "age6") else pop[vv].map(lambda x: None if pd.isna(x) else f"{vv}={int(x)}")
        tot = pop.loc[cat.notna(), wname].sum()
        for lab, g in pop.groupby(cat, sort=True):
            rows.append((lab, g[wname].sum() / tot * 100, f"n={len(g)} / 전체 n={int(cat.notna().sum())}", len(g)))
        return rows
    lab = by_labels(pop, spec.get("by", []))
    for cell, g in pop.groupby(lab, sort=False):
        w = g[wname]
        if m == "count":
            rows.append((cell, w.sum(), f"n={len(g)}", len(g)))
        elif m == "rate":
            num = g.query(spec["numerator"], engine="python")
            rows.append((cell, num[wname].sum() / w.sum() * 100, f"분자 n={len(num)} / 분모 n={len(g)} / 여집합 n={len(g) - len(num)}", min(len(num), len(g) - len(num))))
        elif m == "poverty_rate":
            num = g[g["poor"] == 1]
            rows.append((cell, num[wname].sum() / w.sum() * 100, f"분자 n={len(num)} / 분모 n={len(g)} / 여집합 n={len(g) - len(num)}", min(len(num), len(g) - len(num))))
        elif m in ("mean", "sum", "quantile"):
            v = g[spec["value_var"]]
            ok = v.notna()
            if m == "mean":
                val = (v[ok] * w[ok]).sum() / w[ok].sum()
            elif m == "sum":
                val = (v[ok] * w[ok]).sum()
            else:
                val = wquantile(v[ok], w[ok], spec["q"])
            rows.append((cell, val, f"n={int(ok.sum())}", int(ok.sum())))
        else:
            raise ValueError(m)
    return rows


# ───────────────────────── 질문 문장에서 다시 풀어 직접 계산(「직접」)
W = df["indwgt"]
HW = df["hhwgt"]
HEAD = df["head"] == 1
AGE = df["age"]
is1 = lambda col: df[col] == 1          # 여부 변수: 해당하면 1
never = lambda col: df[col].isna()      # 연간 여부 변수: 해당 없으면 결측


def n_w(mask, w=W):
    return float(w[mask].sum())


def d_count(mask, label="전체"):
    return [(label, n_w(mask))]


def d_hcount(mask, label="전체"):
    return [(label, n_w(mask & HEAD, HW))]


def d_rate(num, den, label="전체"):
    return [(label, n_w(num & den) / n_w(den) * 100)]


def d_hrate(num, den, label="전체"):
    den = den & HEAD
    return [(label, n_w(num & den, HW) / n_w(den, HW) * 100)]


def d_mean(col, mask, label="전체"):
    mk = mask & df[col].notna()
    return [(label, float((df.loc[mk, col] * W[mk]).sum() / W[mk].sum()))]


MALE, FEMALE = df["gender"] == 1, df["gender"] == 2
infant_y = is1("infantbn_yn1")            # 영아수당(현금) 연간
care_y = is1("carebn_yn1")                # 양육수당(가정양육수당) 연간
childbn_dec = is1("childbn_yn2")          # 아동수당 12월
childbn_y = is1("childbn_yn1")
cc_y = is1("childcare_yn1")               # 보육료지원 연간
pl_y = is1("empins_parentleave_yn1")      # 육아휴직급여 연간
mat_y = is1("empins_matleave_yn1")        # 출산전후휴가 연간
sh_y = is1("empins_shorthrs_yn1")         # 육아기 근로시간 단축급여 연간
rear_y = is1("single_rear_yn1")           # 한부모 아동양육비 연간
preg = df["nhi_pregnant_yn"] == 1         # 임신출산진료비 지원
one_low = (df["hnum"] == 1) & (df["h_oinc"] <= 583444 * 12)          # 1인 가구·경상소득이 생계급여 선정기준 12개월분 이하
live_dec = is1("nbls_live_yn2")
old_alone = (AGE >= 65) & (df["hnum"] == 1)
youth = AGE.between(19, 34)
itc = is1("itc_yn")
duru = is1("np_support_yn1") | is1("empins_support_yn1")
ls_inc = df["p_labinc"] + df["p_binc"]
ls_inc_d = df["p_labinc"] + df["p_binc"] + df["p_dainc"]
YJ_LO, YJ_HI = 500000 * 12, 2000000 * 12   # 청년내일저축계좌 근로·사업소득 요건(월 50만원 초과 200만원 이하)
DURU_PAY = 2300000 * 12                    # 두루누리 2022년 월평균보수 230만원 미만


def poverty(mask, label):
    return [(label, n_w(mask & (df["poor"] == 1)) / n_w(mask) * 100)]


def inc5_share(mask):
    tot = n_w(mask)
    return [(f"{i + 1}분위", n_w(mask & (df["_inc5"] == i)) / tot * 100) for i in range(5)]


def nhi3_hshare(mask):
    mk = mask & HEAD
    tot = n_w(mk, HW)
    grp = {"지역가입": [1, 2], "직장가입": [5, 6], "의료급여": [7, 8]}
    return [(k, n_w(mk & df["nhi_type"].isin(v), HW) / tot * 100) for k, v in grp.items()]


DIRECT = {
    # (과제, 차례, part, alt): 칸별 값
    ("W4-01", 1, 1, 1): lambda: d_count(infant_y),
    ("W4-01", 1, 2, 1): lambda: d_mean("infantbn_dur", infant_y),
    ("W4-01", 2, None, 1): lambda: d_count(care_y & (AGE == 0), "만 0세") + d_count(care_y & (AGE == 1), "만 1세"),
    ("W4-01", 3, None, 1): lambda: d_rate(is1("infantbn_yn2"), AGE == 0),
    ("W4-02", 1, None, 1): lambda: d_count(childbn_dec),
    ("W4-02", 2, 1, 1): lambda: sum([d_count(childbn_dec & (AGE == a), f"만 {a}세") for a in range(8)], []),
    ("W4-02", 2, 2, 1): lambda: d_rate(childbn_dec, AGE == 7),
    ("W4-02", 3, None, 1): lambda: d_rate(df["childbn_amt"] >= 100000 * 12, childbn_y),
    ("W4-03", 1, None, 1): lambda: d_count(cc_y),
    ("W4-03", 2, 1, 1): lambda: d_count(cc_y & (AGE <= 2), "만 0~2세") + d_count(cc_y & (AGE >= 3), "만 3세 이상"),
    ("W4-03", 2, 2, 1): lambda: d_mean("childcare_amt", cc_y & (AGE <= 2), "만 0~2세") + d_mean("childcare_amt", cc_y & (AGE >= 3), "만 3세 이상"),
    ("W4-03", 3, 1, 1): lambda: d_rate(cc_y, AGE < 2),
    ("W4-03", 3, 2, 1): lambda: d_rate(infant_y | care_y, AGE < 2),
    ("W4-04", 1, 1, 1): lambda: d_count(pl_y),
    ("W4-04", 1, 2, 1): lambda: d_rate(MALE, pl_y),
    ("W4-04", 2, 1, 1): lambda: d_count(pl_y & MALE, "남") + d_count(pl_y & FEMALE, "여"),
    ("W4-04", 2, 2, 1): lambda: d_mean("empins_parentleave_amt", pl_y & MALE, "남") + d_mean("empins_parentleave_amt", pl_y & FEMALE, "여"),
    ("W4-04", 2, 3, 1): lambda: d_mean("empins_parentleave_dur", pl_y & MALE, "남") + d_mean("empins_parentleave_dur", pl_y & FEMALE, "여"),
    ("W4-05", 1, 1, 1): lambda: d_count(mat_y),
    ("W4-05", 1, 2, 1): lambda: d_mean("empins_matleave_amt", mat_y),
    ("W4-05", 2, 1, 1): lambda: d_count(sh_y),
    ("W4-05", 2, 2, 1): lambda: d_mean("empins_shorthrs_dur", sh_y),
    ("W4-05", 3, None, 1): lambda: d_rate(pl_y, mat_y),
    ("W4-06", 1, 1, 1): lambda: d_count(rear_y),
    ("W4-06", 1, 2, 1): lambda: d_count(rear_y & is1("single_extra_yn1")),
    ("W4-06", 2, 1, 1): lambda: d_count(rear_y & is1("nbls_live_yn1")),
    ("W4-06", 2, 2, 1): lambda: d_rate(is1("nbls_live_yn1"), rear_y),
    ("W4-06", 3, None, 1): lambda: d_rate(df["single_rear_amt"] > 200000 * 12, rear_y),
    ("W4-07", 1, None, 1): lambda: inc5_share(infant_y),
    ("W4-07", 2, 1, 1): lambda: d_mean("age", preg),
    ("W4-07", 2, 2, 1): lambda: d_count(preg & (AGE <= 29), "29세 이하") + d_count(preg & AGE.between(30, 34), "30~34세") + d_count(preg & AGE.between(35, 39), "35~39세") + d_count(preg & (AGE >= 40), "40세 이상"),
    ("W4-08", 1, 1, 1): lambda: d_hcount(one_low),
    ("W4-08", 1, 2, 1): lambda: sum([d_hcount(one_low & (df["sido"] == i + 1), s) for i, s in enumerate(SIDO)], []),
    ("W4-08", 2, None, 1): lambda: d_hcount(one_low & live_dec, "생계급여 수급") + d_hcount(one_low & ~live_dec, "생계급여 미수급"),
    ("W4-08", 3, 1, 1): lambda: nhi3_hshare(one_low & ~live_dec),
    ("W4-08", 3, 2, 1): lambda: d_hrate(is1("aid_live_yn1"), one_low & ~live_dec),
    ("W4-09", 1, 1, 1): lambda: d_count(old_alone),
    ("W4-09", 1, 2, 1): lambda: poverty(old_alone, "1인 가구") + poverty((AGE >= 65) & (df["hnum"] >= 2), "2인 이상 가구"),
    ("W4-09", 2, 1, 1): lambda: d_rate(is1("bp_yn1"), old_alone),
    ("W4-09", 2, 2, 1): lambda: d_rate(is1("oldwork_type1_yn1"), old_alone),
    ("W4-09", 2, 3, 1): lambda: d_rate(is1("oldcare_yn2"), old_alone),
    ("W4-09", 3, None, 1): lambda: d_count(old_alone & (df["h_oinc"] <= 1800000 * 12) & never("bp_yn1")),
    ("W4-09", 4, None, 1): lambda: d_mean("bp_amt", old_alone & is1("bp_yn1")),
    ("W4-10", 1, None, 1): lambda: d_count(youth & is1("youthemp_yn2") & MALE, "남") + d_count(youth & is1("youthemp_yn2") & FEMALE, "여"),
    ("W4-10", 2, None, 1): lambda: d_count(youth & is1("kua_yn1") & (df["kua_type"] == 1), "kua_type=1") + d_count(youth & is1("kua_yn1") & (df["kua_type"] == 2), "kua_type=2"),
    ("W4-10", 3, None, 1): lambda: d_count(youth & (ls_inc > YJ_LO) & (ls_inc <= YJ_HI)),
    ("W4-10", 3, None, 2): lambda: d_count(youth & (ls_inc_d > YJ_LO) & (ls_inc_d <= YJ_HI)),
    ("W4-11", 1, 1, 1): lambda: d_rate(never("empins_yn1"), itc),
    ("W4-11", 1, 2, 1): lambda: d_rate(never("np_yn"), itc),
    ("W4-11", 2, None, 1): lambda: d_rate(itc, duru),
    ("W4-11", 3, None, 1): lambda: d_rate(df["p_labinc"] >= DURU_PAY, is1("empins_support_yn1")),
    ("W4-11", 3, None, 2): lambda: d_rate(df["p_labinc"] + df["p_dainc"] >= DURU_PAY, is1("empins_support_yn1")),
}

# ───────────────────────── 1부: 형식·구성
print("=" * 100)
print("1부  cases.jsonl 형식·구성")
print("=" * 100)
cases = []
with open(CASES, encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        line = line.strip()
        if not line:
            continue
        cases.append(json.loads(line))  # 올바른 JSON 이 아니면 여기서 멈춤
print(f"과제 수: {len(cases)} (JSON 재읽기 통과)  id: {', '.join(c['id'] for c in cases)}")

fact_status = {}
fact_alias = {}
for p in FACTS:
    with open(p, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                fact_status[r["id"]] = r["status"]
                fact_alias[r["id"]] = r["aliases"]

kinds, regs, problems = Counter(), Counter(), []
used_facts = set()
for c in cases:
    ts = c["turns"]
    used_facts |= set(c["facts"])
    for fid in c["facts"]:
        if fid not in fact_status:
            problems.append(f"{c['id']}: 사실 id {fid} 없음")
        elif fact_status[fid] != "official":
            problems.append(f"{c['id']}: 사실 {fid} status={fact_status[fid]}")
        if fid == "B30":
            problems.append(f"{c['id']}: B30 사용")
    if len(ts) != 4 or [t["n"] for t in ts] != [1, 2, 3, 4]:
        problems.append(f"{c['id']}: 차례 수·번호")
    if ts[0]["kind"] not in ("S", "G"):
        problems.append(f"{c['id']}: 첫 차례가 S·G 아님")
    if sum(t["kind"] == "S" for t in ts) < 2:
        problems.append(f"{c['id']}: S 2개 미만")
    for t in ts:
        kinds[t["kind"]] += 1
        k = t["kind"]
        if k in "SGPX":
            regs[t.get("register")] += 1
            if t.get("register") not in ("공식", "약칭", "서술", "영문"):
                problems.append(f"{c['id']}-{t['n']}: register 없음")
        if k in "SGP" and not t.get("specs"):
            problems.append(f"{c['id']}-{t['n']}: specs 없음")
        if k in "GP" and not t.get("param"):
            problems.append(f"{c['id']}-{t['n']}: param 없음")
        if k in "NV" and not t.get("absent"):
            problems.append(f"{c['id']}-{t['n']}: absent 없음")
        if k == "X" and not t.get("premise"):
            problems.append(f"{c['id']}-{t['n']}: premise 없음")
        if not t.get("rubric"):
            problems.append(f"{c['id']}-{t['n']}: rubric 없음")
        if k == "C" and t["n"] < 3:
            problems.append(f"{c['id']}-{t['n']}: C 차례가 앞쪽")

TARGET = {"S": 24, "G": 3, "P": 3, "N": 3, "V": 2, "T": 2, "X": 2, "C": 3, "I": 2}
print("유형별 차례 수(작성 / 기준): " + ", ".join(f"{k} {kinds[k]}/{v}" for k, v in TARGET.items()) + f"  합계 {sum(kinds.values())}")
for k, v in TARGET.items():
    if kinds[k] != v:
        problems.append(f"유형 {k}: {kinds[k]} (기준 {v})")
RANGE = {"공식": (9, 11), "약칭": (10, 12), "서술": (8, 10), "영문": (2, 2)}
print("표현별 차례 수(S·G·P·X, 작성 / 기준 범위): " + ", ".join(f"{k} {regs[k]}/{lo}~{hi}" for k, (lo, hi) in RANGE.items()) + f"  합계 {sum(regs.values())}")
for k, (lo, hi) in RANGE.items():
    if not lo <= regs[k] <= hi:
        problems.append(f"표현 {k}: {regs[k]} (기준 {lo}~{hi})")
nrel = sum(len(c["relations"]) for c in cases)
print(f"관계 점검 수: {nrel} (기준 5개 이상, 과제마다 0~2개)")
if nrel < 5 or any(len(c["relations"]) > 2 for c in cases):
    problems.append("관계 점검 수")
print(f"쓴 사실 id {len(used_facts)}개: {', '.join(sorted(used_facts))}")
print("과제별 유형·표현:")
for c in cases:
    print(f"  {c['id']} [{c['domain']}] " + " / ".join(f"{t['n']}{t['kind']}" + (f"({t['register']})" if t.get('register') else "") for t in c["turns"]))

# ───────────────────────── 2부: 산출 정의 대조
print()
print("=" * 100)
print("2부  산출 정의 대조 — 「정의」= specs 를 정의대로 계산, 「직접」= 질문 문장에서 다시 풀어 계산")
print(f"     (참고) 균등화 가처분소득 중위값 {MED:,.0f}원, 빈곤선 {MED / 2:,.0f}원, 5분위 경계 " + ", ".join(f"{c:,.0f}" for c in CUTS))
print("=" * 100)
small, mism, ncell = [], [], 0
VALUES = {}
for c in cases:
    print(f"\n■ {c['id']}  {c['issue']}")
    for t in c["turns"]:
        if not t.get("specs"):
            continue
        print(f"  ─ 차례 {t['n']} [{t['kind']}·{t.get('register')}] {t['q'][:70]}…")
        for s in t["specs"]:
            key = (c["id"], t["n"], s.get("part"), s.get("alt", 1))
            got = eval_spec(s)
            want = dict(DIRECT[key]())
            unit = "가구" if s.get("unit") == "household" else "개인"
            head = f"    part {s.get('part') or '-'} alt {s.get('alt', 1)} | {s['measure']}·{unit}"
            if s.get("value_var"):
                head += f" | 값 {s['value_var']}"
            print(head)
            print(f"      대상: {s['population'] or '(전체)'}" + (f"   분자: {s['numerator']}" if s.get("numerator") else ""))
            if set(want) != {g[0] for g in got}:
                mism.append((key, "칸 이름 불일치", sorted(want), [g[0] for g in got]))
            for cell, val, ndesc, nmin in got:
                ncell += 1
                d = want.get(cell)
                ok = d is not None and abs(val - d) <= 1e-6 * max(1.0, abs(d))
                if not ok:
                    mism.append((key, cell, val, d))
                flag = "" if nmin >= 30 else "   ← 관측 수 30건 미만"
                if nmin < 30:
                    small.append((key, cell, ndesc))
                fmt = "{:,.2f}" if s["measure"] in ("rate", "share", "poverty_rate") else "{:,.1f}"
                print(f"      {cell:<14} 정의 {fmt.format(val):>16}   직접 {fmt.format(d) if d is not None else '없음':>16}   {'일치' if ok else '불일치'}   {ndesc}{flag}")
                VALUES[key + (cell,)] = val
print()
print(f"대조한 칸 수: {ncell}   불일치: {len(mism)}   관측 수 30건 미만 칸: {len(small)}")
for m in mism:
    print("  불일치:", m)
for s in small:
    print("  30건 미만:", s)

# ───────────────────────── 3부: 관계 점검
print()
print("=" * 100)
print("3부  관계 점검(relations) — 참값에서 성립하는지 확인")
print("=" * 100)


def turn_counts(cid, n):
    """그 차례의 count 정의 가운데 첫 번째(part 가 가장 작은 것)의 칸별 값."""
    c = next(x for x in cases if x["id"] == cid)
    t = c["turns"][n - 1]
    cs = [s for s in t.get("specs", []) if s["measure"] == "count" and s.get("alt", 1) == 1]
    s = sorted(cs, key=lambda x: x.get("part") or 0)[0]
    return [v for k, v in VALUES.items() if k[:4] == (cid, n, s.get("part"), 1)]


for c in cases:
    for r in c["relations"]:
        if r["type"] == "parts_sum":
            whole, parts = sum(turn_counts(c["id"], r["whole"])), sum(turn_counts(c["id"], r["parts"]))
            ok = abs(whole - parts) < 1e-6 * whole
            print(f"  {c['id']} parts_sum  차례 {r['whole']} 전체 {whole:,.1f} = 차례 {r['parts']} 분류 합 {parts:,.1f}  → {'성립' if ok else '불성립'}")
        elif r["type"] == "subset_le":
            large, small_ = sum(turn_counts(c["id"], r["large"])), sum(turn_counts(c["id"], r["small"]))
            ok = small_ <= large
            print(f"  {c['id']} subset_le  차례 {r['small']} {small_:,.1f} ≤ 차례 {r['large']} {large:,.1f}  → {'성립' if ok else '불성립'}")
        else:
            ok = False
            print(f"  {c['id']} 알 수 없는 관계 {r}")
        if not ok:
            problems.append(f"{c['id']} 관계 {r}")

# ───────────────────────── 4부: N·V 차례의 자료에 없음 확인
print()
print("=" * 100)
print("4부  N·V 차례 — 자료에 없음 확인")
print("=" * 100)
cb = pd.read_csv(CODEBOOK, sep="\t", dtype=str).fillna("")
nv = pd.read_csv(NOVALUE, sep="\t", dtype=str).fillna("")
cb_text = cb["var"] + " " + cb["name_ko"] + " " + cb["program"]


def cb_hits(words):
    return {w: cb.loc[cb_text.str.contains(w, regex=False), "var"].tolist() for w in words}


print("N W4-01-4 첫만남이용권      codebook 검색:", cb_hits(["첫만남", "이용권"]))
print("N W4-04-3 3+3 부모육아휴직제 codebook 검색:", cb_hits(["3+3", "부모육아휴직", "보너스", "특례"]))
print("N W4-10-4 청년월세 특별지원  codebook 검색:", cb_hits(["청년월세", "월세", "특별지원", "월차임"]))
for name in ("아이돌봄서비스", "청소년 한부모가족지원 아동양육비"):
    row = nv[nv["사업"] == name]
    print(f"V {name}: 값없는_사업.tsv {len(row)}행 {row.iloc[0].tolist() if len(row) else ''}")
print("V 아이돌봄서비스          codebook 검색:", cb_hits(["아이돌봄"]), " 자료 열 이름 검색:", [c_ for c_ in df.columns if "dolbom" in c_ or "idol" in c_])
print("V 청소년 한부모 아동양육비 codebook 검색:", cb_hits(["청소년 한부모"]))
for v in ("p_single_youth_rear_amt", "p_single_youth_self_amt"):
    print(f"   자료의 {v}: 0이 아닌 행 {int((df[v] != 0).sum())}건, 결측 {int(df[v].isna().sum())}건 → 전원 0")
y24 = is1("single_rear_yn1") & (AGE <= 24)
print(f"   (대체 위험) 일반 아동양육비 연간 수급자 가운데 24세 이하 관측 수 {int(y24.sum())}건 — 청소년한부모 값으로 제시하면 오답")
print(f"   (대체 위험) 아빠육아휴직보너스제 적용 관측 수 {int((df['empins_dadleave_yn'] == 1).sum())}건, 시간제보육지원 연간 관측 수 {int(is1('childcare_time_yn1').sum())}건")
print("C W4-05-4 관측 수: 배우자출산휴가 연간", int(is1("empins_spouseleave_yn1").sum()), "건, 고용보험미적용자 출산급여 연간", int(is1("empins_uninsureleave_yn1").sum()), "건 → 시도별 칸은 최소 관측 수 미달")
print("T W4-02-4, W4-07-3: 자료의 연도 변수는 출생년도(year)뿐이고 급여 변수는 2022년 연간·12월 기준만 있음. 임신출산진료비 변수:", cb.loc[cb["var"].str.contains("pregnant"), "var"].tolist())

print()
print("=" * 100)
print("종합")
print("=" * 100)
if mism:
    problems.append(f"산출 정의 불일치 {len(mism)}건")
print("문제 없음" if not problems else "문제: " + " | ".join(problems))
