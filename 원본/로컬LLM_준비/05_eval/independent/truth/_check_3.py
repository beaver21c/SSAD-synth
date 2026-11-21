# -*- coding: utf-8 -*-
"""독립 검산 3: check_input_3.jsonl(E17~E24)의 답을 분석 자료에서 pandas로 직접 계산.
규약: 자료_규약.md(개인 단위 indwgt 가중, 여부 변수는 == 1, 평균은 값이 있는 행만,
소득 5분위는 전체 인구 균등화 가처분소득의 개인 가중 20·40·60·80% 분위값 경계).
개인 단위 행은 출력하지 않음."""
import json
import numpy as np
import pandas as pd

BASE = "/mnt/share/행정데이터_set"
DATA = BASE + "/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet"
OUT = BASE + "/로컬LLM_준비/05_eval/independent/truth/check_3.jsonl"

COLS = ["hid", "head", "age", "hnum", "sido", "indwgt", "p_dinc",
        "disp_yn1", "disp_yn2", "dis_yn",
        "bp_yn1", "bp_yn2", "bp_amt", "bp_dur",
        "nbls_live_yn1", "nbls_live_yn2", "nhi_diabetes_yn",
        "single_rear_yn1", "single_rear_yn2", "oldcare_yn1", "oldcare_yn2"]
df = pd.read_parquet(DATA, columns=COLS)
W = df["indwgt"]

SIDO = {1: "서울", 2: "부산", 3: "대구", 4: "인천", 5: "광주", 6: "대전", 7: "울산", 8: "세종",
        9: "경기", 10: "강원", 11: "충북", 12: "충남", 13: "전북", 14: "전남", 15: "경북",
        16: "경남", 17: "제주"}


def wcount(mask):
    """가중 인원과 비가중 관측 수"""
    return float(W[mask].sum()), int(mask.sum())


def wpct(num, den):
    """비율(%) = 분자 가중합 / 분모 가중합 × 100"""
    num = num & den
    return float(W[num].sum() / W[den].sum() * 100), int(den.sum()), int(num.sum())


def wmean(var, mask):
    """값이 있는 행만의 가중 평균"""
    m = mask & df[var].notna()
    return float((df.loc[m, var] * W[m]).sum() / W[m].sum()), int(m.sum())


def wquantile(values, weights, q):
    """오름차순 정렬 후 가중치 누적합이 전체의 q배에 처음 이르는 값"""
    order = np.argsort(values.to_numpy(), kind="mergesort")
    v = values.to_numpy()[order]
    cw = np.cumsum(weights.to_numpy()[order])
    idx = int(np.searchsorted(cw, q * cw[-1], side="left"))
    return float(v[min(idx, len(v) - 1)])


def quintile(values, bounds):
    """경계값 이상이면 위 분위"""
    q = np.ones(len(values), dtype=int)
    for b in bounds:
        q += (values.to_numpy() >= b).astype(int)
    return pd.Series(q, index=values.index)


# 균등화 가처분소득과 소득 5분위(전체 인구 기준)
df["eq_dinc"] = df.groupby("hid")["p_dinc"].transform("sum") / np.sqrt(df["hnum"])
BOUNDS = [wquantile(df["eq_dinc"], W, q) for q in (0.2, 0.4, 0.6, 0.8)]
df["q5"] = quintile(df["eq_dinc"], BOUNDS)

rows = []


def add(id_, reading_no, reading, pct, cells, ambiguous, note):
    rows.append({"id": id_, "turn": 1, "reading_no": reading_no, "reading": reading,
                 "pct": pct, "cells": cells, "ambiguous": ambiguous, "note": note})


def count_item(id_, var_base, label, note):
    for no, (suffix, when) in enumerate([("yn1", "2022년 연간(한 번이라도)"), ("yn2", "2022년 12월 기준")], 1):
        var = f"{var_base}_{suffix}"
        v, n = wcount(df[var] == 1)
        add(id_, no, f"대상: 전국 전체 인구 중 {label} {when} / 대상 변수: 가중 인원(indwgt 합계) / 분류: 없음 / 사용 변수: {var} == 1, indwgt",
            False, [{"labels": [], "value": v, "n": n}], True, note)


# E17 장애인연금 수급 인원
count_item("E17", "disp", "장애인연금 수급자",
           "질문이 기준 시점을 정하지 않음. 연간 수급(disp_yn1)과 12월 기준 수급(disp_yn2)으로 읽힘")

# E18 등록장애인 비율
v, n, nn = wpct(df["dis_yn"] == 1, pd.Series(True, index=df.index))
add("E18", 1, "대상: 전국 전체 인구 / 분자: 등록장애인(2022.12.31. 기준) / 분류: 없음 / 사용 변수: dis_yn == 1, indwgt",
    True, [{"labels": [], "value": v, "n": n, "n_num": nn}], False, "")

# E19 기초연금 수급자 1인당 평균 급여액
m1 = df["bp_yn1"] == 1
monthly = float(((df.loc[m1, "bp_amt"] / df.loc[m1, "bp_dur"]) * W[m1]).sum() / W[m1].sum())
note19 = ("급여액 변수(bp_amt)는 2022년 연간 총액 하나뿐이나 수급자 범위가 연간 수급(bp_yn1)과 12월 기준 수급(bp_yn2)으로 읽힘. "
          "연간 총액이 연간 수급자 전체에 정의되어 있어 해석 1이 우선. "
          f"참고: 월평균 환산(bp_amt ÷ bp_dur, 연간 수급자) 가중 평균 {monthly!r}원")
for no, (var, when) in enumerate([("bp_yn1", "2022년 연간 수급자"), ("bp_yn2", "2022년 12월 기준 수급자")], 1):
    v, n = wmean("bp_amt", df[var] == 1)
    add("E19", no, f"대상: 기초연금 {when} / 대상 변수: 연간 급여 총액의 가중 평균(값이 있는 행) / 분류: 없음 / 사용 변수: {var} == 1, bp_amt, indwgt",
        False, [{"labels": [], "value": v, "n": n}], True, note19)

# E20 시도별 생계급여 수급률(전체 인구 대비)
for no, (var, when) in enumerate([("nbls_live_yn1", "2022년 연간(한 번이라도)"), ("nbls_live_yn2", "2022년 12월 기준")], 1):
    cells = []
    for code, name in SIDO.items():
        v, n, nn = wpct(df[var] == 1, df["sido"] == code)
        cells.append({"labels": [name], "value": v, "n": n, "n_num": nn})
    add("E20", no, f"대상: 시도별 전체 인구 / 분자: 생계급여 수급자 {when} / 분류: 시도(sido 17개) / 사용 변수: {var} == 1, sido, indwgt",
        True, cells, True, "질문이 기준 시점을 정하지 않음. 연간 수급(nbls_live_yn1)과 12월 기준 수급(nbls_live_yn2)으로 읽힘")

# E21 당뇨병 입원 경험 인원
v, n = wcount(df["nhi_diabetes_yn"] == 1)
add("E21", 1, "대상: 전국 전체 인구 중 1년 동안 한 번이라도 당뇨병으로 입원한 사람 / 대상 변수: 가중 인원(indwgt 합계) / 분류: 없음 / 사용 변수: nhi_diabetes_yn == 1, indwgt",
    False, [{"labels": [], "value": v, "n": n}], False, "")

# E22 65세 이상 소득 5분위별 기초연금 수급률
old = df["age"] >= 65
ob = [wquantile(df.loc[old, "eq_dinc"], W[old], q) for q in (0.2, 0.4, 0.6, 0.8)]
oq = quintile(df["eq_dinc"], ob)
inner = [wpct(df["bp_yn1"] == 1, old & (oq == k))[0] for k in range(1, 6)]
note22 = ("질문이 기준 시점을 정하지 않음. 연간 수급(bp_yn1)과 12월 기준 수급(bp_yn2)으로 읽힘. "
          "5분위 경계는 자료 규약대로 전체 인구 기준. "
          f"참고: 65세 이상 내부 분위 경계로 나눈 연간 수급률(1~5분위) {inner!r}")
for no, (var, when) in enumerate([("bp_yn1", "2022년 연간(한 번이라도)"), ("bp_yn2", "2022년 12월 기준")], 1):
    cells = []
    for k in range(1, 6):
        v, n, nn = wpct(df[var] == 1, old & (df["q5"] == k))
        cells.append({"labels": [f"{k}분위"], "value": v, "n": n, "n_num": nn})
    add("E22", no, f"대상: 65세 이상(age >= 65) / 분자: 기초연금 수급자 {when} / 분류: 소득 5분위(전체 인구 균등화 가처분소득의 개인 가중 분위 경계) / 사용 변수: {var} == 1, age, p_dinc, hnum, hid, indwgt",
        True, cells, True, note22)

# E23 한부모가족지원 아동양육비 수급 인원
count_item("E23", "single_rear", "한부모가족지원 아동양육비 수급자",
           "질문이 기준 시점을 정하지 않음. 연간 수급(single_rear_yn1)과 12월 기준 수급(single_rear_yn2)으로 읽힘. 추가아동양육비(single_extra_*)는 별도 급여로 보아 제외")

# E24 노인맞춤돌봄서비스 이용자 평균 연령
for no, (var, when) in enumerate([("oldcare_yn1", "2022년 연간 이용자(한 번이라도)"), ("oldcare_yn2", "2022년 12월 기준 이용자")], 1):
    v, n = wmean("age", df[var] == 1)
    add("E24", no, f"대상: 노인맞춤돌봄서비스 {when} / 대상 변수: 연령(만 나이)의 가중 평균 / 분류: 없음 / 사용 변수: {var} == 1, age, indwgt",
        False, [{"labels": [], "value": v, "n": n}], True, "질문이 기준 시점을 정하지 않음. 연간 이용(oldcare_yn1)과 12월 기준 이용(oldcare_yn2)으로 읽힘")

with open(OUT, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

# 집계 결과 요약(개인 단위 행 없음)
print("5분위 경계:", BOUNDS)
for r in rows:
    print(r["id"], r["reading_no"], "pct" if r["pct"] else "val",
          [(c["labels"], round(c["value"], 4), c["n"], c.get("n_num")) for c in r["cells"]])
print("lines:", len(rows), "ids:", sorted({r["id"] for r in rows}))
