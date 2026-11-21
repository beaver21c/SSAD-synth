#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C·F·G 묶음 문항 점검 스크립트.

점검 내용
  1. 세 파일(C.jsonl, F.jsonl, G.jsonl)이 JSON Lines 로 읽히는지, 필수 항목과 형식이 맞는지
  2. 산출 정의의 population · numerator · groups[].cond 가 DataFrame.query 로 실행되는지
  3. 산출 정의마다 표시되는 칸(가중하지 않은 관측 수 30건 이상)이 1개 이상 있는지
  4. C 묶음: 쌍마다 두 참값이 다른지(표시 자릿수로 반올림한 값 기준)
  5. F 묶음: 차례 수(2~3)와 차례별 산출 정의가 있는지
  6. G 묶음: 코드 블록과 defect 항목, 결함 종류별 개수
  7. (--run-g) G 묶음의 코드를 분석 함수(ssda)로 실행하여, 결함 없는 코드는 산출 정의의 참값과 같고
     결함 있는 코드는 참값과 다르며 실행되지 않는 코드는 오류가 나는지

사용법
  python _check_CFG.py                 # 1~6
  python _check_CFG.py --values        # 1~6 + 산출 정의별 참값(집계값) 출력
  SSDA_DATA=<parquet> PYTHONPATH=<02_library> python _check_CFG.py --run-g   # 1~7

참값 계산은 inputs/자료_규약.md 의 정의를 따르며 집계값만 다룬다(개인 단위 행을 출력하지 않음).
"""
import contextlib
import io
import json
import os
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA = "/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet"
DATA = os.environ.get("SSDA_DATA", DEFAULT_DATA)
CODEBOOK = os.path.join(HERE, "..", "inputs", "codebook.tsv")
MIN_N = 30

MEASURES = {"count", "rate", "mean", "sum", "quantile", "share", "poverty_rate"}
SIDO_LABELS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남",
               "전북", "전남", "경북", "경남", "제주"]
STD_LABELS = {
    "sido": SIDO_LABELS,
    "sex": ["남", "여"],
    "age3": ["0~17세", "18~64세", "65세 이상"],
    "age6": ["0~17세", "18~34세", "35~49세", "50~64세", "65~74세", "75세 이상"],
    "age10": ["0~9세", "10~19세", "20~29세", "30~39세", "40~49세", "50~59세", "60~69세", "70~79세", "80세 이상"],
    "hs4": ["1인", "2인", "3인", "4인 이상"],
    "inc5": ["1분위(하위 20%)", "2분위", "3분위", "4분위", "5분위(상위 20%)"],
    "nhi3": ["지역가입", "직장가입", "의료급여"],
    "poor2": ["비빈곤", "빈곤"],
}
G_DEFECT_PLAN = {"분모": 2, "유사 변수": 2, "경계·연산자": 2, "단위": 1, "분류 기준": 1, "실행되지 않는 코드": 1, "없음": 3}

problems = []


def fail(msg):
    problems.append(msg)
    print("  [문제] " + msg)


# ------------------------------------------------------------------ 자료 준비
def wquantile(values, weights, q):
    """가중 분위수: 오름차순으로 놓고 가중치 누적합이 전체의 q배에 처음 이르는 값."""
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    order = np.argsort(v, kind="mergesort")
    v, w = v[order], w[order]
    cum = np.cumsum(w)
    idx = int(np.searchsorted(cum, q * cum[-1], side="left"))
    return float(v[min(idx, len(v) - 1)])


def prepare(df):
    df = df.copy()
    df["hh_dinc"] = df.groupby("hid")["p_dinc"].transform("sum")
    df["eqinc"] = df["hh_dinc"] / np.sqrt(df["hnum"])
    median = wquantile(df["eqinc"], df["indwgt"], 0.5)
    df["poor"] = (df["eqinc"] < 0.5 * median).astype(int)
    bounds = [wquantile(df["eqinc"], df["indwgt"], q) for q in (0.2, 0.4, 0.6, 0.8)]
    df["_std_sido"] = df["sido"].astype(int) - 1
    df["_std_sex"] = df["gender"].astype(int) - 1
    df["_std_age3"] = np.searchsorted([18, 65], df["age"], side="right")
    df["_std_age6"] = np.searchsorted([18, 35, 50, 65, 75], df["age"], side="right")
    df["_std_age10"] = np.minimum(df["age"].astype(int) // 10, 8)
    df["_std_hs4"] = np.minimum(df["hnum"].astype(int), 4) - 1
    df["_std_inc5"] = np.searchsorted(bounds, df["eqinc"], side="right")
    df["_std_nhi3"] = df["nhi_type"].map({1: 0, 2: 0, 5: 1, 6: 1}).fillna(2).astype(int)
    df["_std_poor2"] = df["poor"]
    return df


def run_query(frame, cond, where):
    """조건식을 DataFrame.query 로 실행. 실패하면 문제로 기록하고 빈 결과를 돌려준다."""
    if cond is None or str(cond).strip() == "":
        return frame
    try:
        return frame.query(cond)
    except Exception as exc:  # noqa: BLE001
        fail("%s: 조건식 실행 실패 `%s` (%s: %s)" % (where, cond, type(exc).__name__, exc))
        return frame.iloc[0:0]


def by_levels(frame, full, by, where):
    """분류 기준 하나를 (이름표, 행 선택 불리언) 목록으로 바꾼다."""
    if "std" in by:
        name = by["std"]
        if name not in STD_LABELS:
            fail("%s: 알 수 없는 표준 분류 %r" % (where, name))
            return []
        col = frame["_std_" + name]
        return [(lab, (col == i).to_numpy()) for i, lab in enumerate(STD_LABELS[name])]
    if "var" in by:
        bins, labels = by.get("bins", []), by.get("labels", [])
        if len(labels) != len(bins) + 1:
            fail("%s: bins 와 labels 의 개수가 맞지 않음" % where)
            return []
        val = frame[by["var"]]
        code = np.where(val.isna(), -1, np.searchsorted(bins, val.fillna(0), side="right"))
        return [(lab, code == i) for i, lab in enumerate(labels)]
    if "cat" in by:
        col = frame[by["cat"]]
        cats = sorted(full[by["cat"]].dropna().unique().tolist())
        if len(cats) > 15:
            fail("%s: 범주가 15개를 넘는 변수 %s" % (where, by["cat"]))
        return [(("%g" % c) if isinstance(c, (int, float)) else str(c), (col == c).to_numpy()) for c in cats]
    if "groups" in by:
        out = []
        for g in by["groups"]:
            sub = run_query(frame, g["cond"], where + " groups[%s]" % g.get("label"))
            out.append((g["label"], frame.index.isin(sub.index)))
        return out
    fail("%s: by 항목의 형식을 알 수 없음 %r" % (where, by))
    return []


def share_levels(frame, full, value_var):
    if value_var in STD_LABELS:
        col = frame["_std_" + value_var]
        return [(lab, (col == i).to_numpy()) for i, lab in enumerate(STD_LABELS[value_var])], np.ones(len(frame), bool)
    col = frame[value_var]
    cats = sorted(full[value_var].dropna().unique().tolist())
    return [("%g" % c, (col == c).to_numpy()) for c in cats], col.notna().to_numpy()


def evaluate(df, spec, where):
    """산출 정의 하나의 참값 표. 행마다 label(분류 이름표), value, n(가중하지 않은 관측 수), shown."""
    unit = spec.get("unit", "person")
    base = df[df["head"] == 1] if unit == "household" else df
    wcol = "hhwgt" if unit == "household" else "indwgt"
    pop = run_query(base, spec.get("population", ""), where + " population")
    measure = spec["measure"]

    cells = [((), np.ones(len(pop), bool))]
    for by in spec.get("by", []):
        levels = by_levels(pop, base, by, where)
        cells = [(lab + (l2,), m & m2) for lab, m in cells for l2, m2 in levels]

    num_mask = None
    if measure in ("rate", "poverty_rate"):
        num_cond = "poor == 1" if measure == "poverty_rate" else spec.get("numerator")
        if not num_cond:
            fail("%s: rate 에 numerator 가 없음" % where)
            num_cond = "age < 0"
        num_mask = pop.index.isin(run_query(pop, num_cond, where + " numerator").index)
    w = pop[wcol].to_numpy(dtype=float)
    rows = []
    for label, mask in cells:
        if measure == "count":
            n = int(mask.sum())
            rows.append((label, float(w[mask].sum()), n, n >= MIN_N))
        elif measure in ("rate", "poverty_rate"):
            n_den, n_num = int(mask.sum()), int((mask & num_mask).sum())
            den = w[mask].sum()
            val = 100.0 * w[mask & num_mask].sum() / den if den > 0 else float("nan")
            rows.append((label, val, n_den, n_num >= MIN_N and n_den - n_num >= MIN_N))
        elif measure in ("mean", "sum", "quantile"):
            v = pop[spec["value_var"]].to_numpy(dtype=float)
            ok = mask & ~np.isnan(v)
            n = int(ok.sum())
            if n == 0:
                val = float("nan")
            elif measure == "mean":
                val = float(np.average(v[ok], weights=w[ok]))
            elif measure == "sum":
                val = float((v[ok] * w[ok]).sum())
            else:
                val = wquantile(v[ok], w[ok], spec["q"])
            rows.append((label, val, n, n >= MIN_N))
        elif measure == "share":
            levels, valid = share_levels(pop, base, spec["value_var"])
            total = w[mask & valid].sum()
            for lab, m2 in levels:
                n = int((mask & m2).sum())
                val = 100.0 * w[mask & m2].sum() / total if total > 0 else float("nan")
                rows.append((label + (lab,), val, n, n >= MIN_N))
    return pd.DataFrame(rows, columns=["label", "value", "n", "shown"])


def display_round(value, measure):
    """도구의 표시 규칙: 비율은 소수 첫째 자리, 인원·금액은 유효숫자 3자리."""
    if value is None or np.isnan(value):
        return float("nan")
    if measure in ("rate", "share", "poverty_rate"):
        return round(value, 1)
    if value == 0:
        return 0.0
    digits = 2 - int(np.floor(np.log10(abs(value))))
    return round(value, digits)


def shown_signature(table, measure):
    return [(lab, display_round(v, measure)) for lab, v, n, s in table.itertuples(index=False) if s]


def print_table(table, measure, indent="      "):
    for lab, v, n, s in table.itertuples(index=False):
        name = " / ".join(lab) if lab else "전체"
        text = ("%s" % display_round(v, measure)) if s else "억제(관측 수 미달)"
        print("%s%s: %s" % (indent, name, text))


# ------------------------------------------------------------------ 형식 점검
def load(name):
    path = os.path.join(HERE, name + ".jsonl")
    items = []
    with open(path, encoding="utf-8") as f:
        for no, line in enumerate(f, 1):
            if not line.strip():
                fail("%s %d행: 빈 줄" % (name, no))
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                fail("%s %d행: JSON 으로 읽히지 않음 (%s)" % (name, no, exc))
    return items


def strip_code(text):
    return re.sub(r"```.*?```", " ", text, flags=re.S)


def check_common(item, stratum, columns):
    iid = item.get("id", "?")
    for key in ("id", "stratum", "persona", "turns", "expect", "specs", "note"):
        if key not in item:
            fail("%s: 항목 %s 없음" % (iid, key))
    if item.get("stratum") != stratum:
        fail("%s: stratum 이 %s 가 아님" % (iid, stratum))
    if item.get("expect") != "compute":
        fail("%s: expect 가 compute 가 아님" % iid)
    turns = item.get("turns", [])
    if not isinstance(turns, list) or not turns or not all(isinstance(t, str) and t.strip() for t in turns):
        fail("%s: turns 형식 오류" % iid)
    specs = item.get("specs", [])
    if not isinstance(specs, list) or not specs:
        fail("%s: specs 가 비어 있음" % iid)
    for k, spec in enumerate(specs):
        w = "%s specs[%d]" % (iid, k)
        if spec.get("measure") not in MEASURES:
            fail("%s: measure 오류 %r" % (w, spec.get("measure")))
        if spec.get("unit", "person") not in ("person", "household"):
            fail("%s: unit 오류" % w)
        if "population" not in spec or not isinstance(spec.get("by", []), list):
            fail("%s: population 또는 by 누락" % w)
        if spec.get("measure") == "rate" and not spec.get("numerator"):
            fail("%s: numerator 누락" % w)
        if spec.get("measure") == "count" and "numerator" in spec:
            fail("%s: count 에 numerator 가 있음" % w)
        if spec.get("measure") in ("mean", "sum", "quantile", "share"):
            vv = spec.get("value_var")
            if not vv or (vv not in columns and vv not in STD_LABELS):
                fail("%s: value_var 오류 %r" % (w, vv))
        if spec.get("measure") == "quantile" and not (0.05 <= spec.get("q", -1) <= 0.95):
            fail("%s: q 범위 오류" % w)
        if not (1 <= spec.get("turn", 1) <= len(turns)):
            fail("%s: turn 범위 오류" % w)
    # 질문 문장(코드 블록 제외)에 변수명이 들어가지 않았는지
    for t in turns:
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", strip_code(t)):
            if token in columns or token in STD_LABELS:
                fail("%s: 질문 문장에 변수명 %s 이 있음" % (iid, token))


def main():
    show_values = "--values" in sys.argv
    run_g = "--run-g" in sys.argv

    print("자료: %s" % DATA)
    df = prepare(pd.read_parquet(DATA))
    columns = set(df.columns)
    print("행 %d, 가구 %d" % (len(df), int((df["head"] == 1).sum())))

    bundles = {name: load(name) for name in ("C", "F", "G")}
    ids = [it.get("id") for items in bundles.values() for it in items]
    if len(ids) != len(set(ids)):
        fail("id 중복")

    truth = {}
    for name, items in bundles.items():
        print("\n== %s 묶음: %d문항" % (name, len(items)))
        for item in items:
            check_common(item, name, columns)
            iid = item.get("id", "?")
            for k, spec in enumerate(item.get("specs", [])):
                where = "%s specs[%d]" % (iid, k)
                try:
                    table = evaluate(df, spec, where)
                except Exception as exc:  # noqa: BLE001
                    fail("%s: 참값 계산 실패 (%s: %s)" % (where, type(exc).__name__, exc))
                    continue
                truth[(iid, k)] = table
                n_shown = int(table["shown"].sum())
                if n_shown == 0:
                    fail("%s: 표시되는 칸이 없음(모든 칸의 관측 수가 %d건 미만)" % (where, MIN_N))
                line = "  %s 차례%d %-12s 표시 칸 %d/%d, 칸 관측 수 최소 %d · 최대 %d" % (
                    iid, spec.get("turn", 1), spec["measure"], n_shown, len(table),
                    int(table["n"].min()), int(table["n"].max()))
                print(line)
                if show_values:
                    print_table(table, spec["measure"])

    # ---- C: 최소 차이 쌍
    print("\n== C 묶음 쌍 점검")
    pairs = {}
    for item in bundles["C"]:
        iid = item.get("id", "")
        if not re.fullmatch(r"C\d\d[ab]", iid):
            fail("%s: id 형식 오류" % iid)
        if item.get("pair") != iid[:-1] or not item.get("diff"):
            fail("%s: pair 또는 diff 항목 오류" % iid)
        if len(item.get("turns", [])) != 1:
            fail("%s: C 묶음은 차례가 1개여야 함" % iid)
        pairs.setdefault(item.get("pair"), {})[iid[-1:]] = item
    diff_count = {}
    for pid in sorted(pairs):
        ab = pairs[pid]
        if set(ab) != {"a", "b"}:
            fail("%s: a·b 두 문항이 갖춰지지 않음" % pid)
            continue
        a, b = ab["a"], ab["b"]
        if a["diff"] != b["diff"]:
            fail("%s: 두 문항의 diff 가 다름" % pid)
        if a["turns"] == b["turns"]:
            fail("%s: 두 질문 문장이 같음" % pid)
        kind = re.split(r"[(（]", a["diff"])[0].strip()
        diff_count[kind] = diff_count.get(kind, 0) + 1
        if (a["id"], 0) not in truth or (b["id"], 0) not in truth:
            continue
        sa = shown_signature(truth[(a["id"], 0)], a["specs"][0]["measure"])
        sb = shown_signature(truth[(b["id"], 0)], b["specs"][0]["measure"])
        same_measure = a["specs"][0]["measure"] == b["specs"][0]["measure"]
        differs = (sa != sb) or not same_measure
        if not differs:
            fail("%s: 두 참값이 같음" % pid)
        head_a = sa[0][1] if sa else float("nan")
        head_b = sb[0][1] if sb else float("nan")
        print("  %s [%s] 참값 다름=%s (첫 표시 칸 a=%s, b=%s; 표시 칸 a %d개, b %d개)" % (
            pid, a["diff"], differs, head_a, head_b, len(sa), len(sb)))
    print("  차이 종류별 쌍 수: %s" % json.dumps(diff_count, ensure_ascii=False))
    if len(pairs) != 15:
        fail("C 묶음 쌍 수가 15가 아님(%d)" % len(pairs))

    # ---- F: 이어 묻는 대화
    print("\n== F 묶음 대화 점검")
    for item in bundles["F"]:
        iid = item.get("id", "")
        turns = item.get("turns", [])
        if not re.fullmatch(r"F\d\d", iid):
            fail("%s: id 형식 오류" % iid)
        if not 2 <= len(turns) <= 3:
            fail("%s: 차례 수가 2~3이 아님" % iid)
        spec_turns = [s.get("turn") for s in item.get("specs", [])]
        if any(t is None for t in spec_turns):
            fail("%s: turn 이 없는 산출 정의가 있음" % iid)
        missing = [t for t in range(1, len(turns) + 1) if t not in spec_turns]
        if missing:
            fail("%s: 산출 정의가 없는 차례 %s" % (iid, missing))
        print("  %s 차례 %d개, 산출 정의 %d개" % (iid, len(turns), len(spec_turns)))
    if len(bundles["F"]) != 10:
        fail("F 묶음 문항 수가 10이 아님")

    # ---- G: 코드 확인 요청
    print("\n== G 묶음 코드 점검")
    defect_count = {}
    codes = {}
    for item in bundles["G"]:
        iid = item.get("id", "")
        if not re.fullmatch(r"G\d\d", iid):
            fail("%s: id 형식 오류" % iid)
        defect = item.get("defect")
        if not defect:
            fail("%s: defect 항목 없음" % iid)
            defect = "?"
        blocks = re.findall(r"```python\n(.*?)```", item["turns"][0], flags=re.S)
        if len(blocks) != 1 or "import ssda" not in blocks[0]:
            fail("%s: python 코드 블록(import ssda 포함)이 1개가 아님" % iid)
            continue
        codes[iid] = blocks[0]
        kind = re.split(r"[(（]", defect)[0].strip()
        group = kind
        for prefix, name in (("경계", "경계·연산자"), ("연산자", "경계·연산자"), ("분모", "분모"), ("단위", "단위"),
                             ("분류 기준", "분류 기준"), ("유사 변수", "유사 변수"), ("실행되지 않는", "실행되지 않는 코드")):
            if kind.startswith(prefix):
                group = name
        defect_count[group] = defect_count.get(group, 0) + 1
        print("  %s 결함: %s" % (iid, defect))
    print("  결함 종류별 문항 수: %s" % json.dumps(defect_count, ensure_ascii=False))
    if defect_count != G_DEFECT_PLAN:
        fail("G 묶음 결함 종류별 개수가 계획과 다름: 계획 %s" % json.dumps(G_DEFECT_PLAN, ensure_ascii=False))

    if run_g:
        run_g_codes(bundles["G"], codes, truth)

    print("\n== 결과: 문항 C %d · F %d · G %d, 산출 정의 %d개, 문제 %d건" % (
        len(bundles["C"]), len(bundles["F"]), len(bundles["G"]), len(truth), len(problems)))
    for p in problems:
        print("  - " + p)
    return 1 if problems else 0


# ------------------------------------------------------------------ G 코드 실행
def amount_vars():
    try:
        cb = pd.read_csv(CODEBOOK, sep="\t")
        names = set(cb.loc[cb["unit"] == "원", "var"])
    except Exception:  # noqa: BLE001
        names = set()
    return names | {"hh_dinc", "eqinc"}


def close(a, b):
    return abs(a - b) <= max(0.0051 * abs(b), 0.051)


def run_g_codes(items, codes, truth):
    print("\n== G 묶음 코드 실행(ssda)")
    try:
        import ssda  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        fail("ssda 를 불러오지 못함(PYTHONPATH 확인): %s" % exc)
        return
    amounts = amount_vars()
    for item in items:
        iid, defect = item["id"], item.get("defect", "")
        if iid not in codes or (iid, 0) not in truth:
            continue
        spec = item["specs"][0]
        scale = 10000.0 if spec.get("value_var") in amounts and spec["measure"] in ("mean", "sum", "quantile") else 1.0
        tab = truth[(iid, 0)]
        want = [v / scale if s else float("nan") for v, s in zip(tab["value"], tab["shown"])]
        ns = {}
        error = None
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                exec(codes[iid], ns)  # noqa: S102 - 문항에 실린 코드의 동작 확인
            except Exception as exc:  # noqa: BLE001
                error = "%s: %s" % (type(exc).__name__, exc)
        if defect.startswith("실행되지 않는"):
            print("  %s 실행 오류=%s (%s)" % (iid, error is not None, error))
            if error is None:
                fail("%s: 오류가 나야 하는 코드가 실행됨" % iid)
            continue
        if error is not None:
            fail("%s: 코드가 실행되지 않음 (%s)" % (iid, error))
            continue
        got = [float(x) for x in ns["r"].table()["값"].tolist()]
        if len(got) == len(want):
            pairs = [(g, w) for g, w in zip(got, want) if not (np.isnan(g) or np.isnan(w))]
            same = bool(pairs) and all(close(g, w) for g, w in pairs)
        else:
            g2 = sorted(x for x in got if not np.isnan(x))
            w2 = sorted(x for x in want if not np.isnan(x))
            same = len(g2) == len(w2) and all(close(g, w) for g, w in zip(g2, w2))
        print("  %s 실행됨, 코드 결과와 의도한 참값 일치=%s (결함: %s)" % (iid, same, defect))
        if defect == "없음" and not same:
            fail("%s: 결함 없는 코드의 결과가 산출 정의의 참값과 다름" % iid)
        if defect != "없음" and same:
            fail("%s: 결함 있는 코드의 결과가 참값과 같음(결함이 값에 드러나지 않음)" % iid)


if __name__ == "__main__":
    sys.exit(main())
