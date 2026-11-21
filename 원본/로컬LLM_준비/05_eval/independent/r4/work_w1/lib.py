# -*- coding: utf-8 -*-
"""문항 작성자(w1) 작업용 공통 함수: 자료 읽기, 파생 변수, 산출 정의 실행(집계만)."""
import numpy as np
import pandas as pd

DATA = "/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet"
CODEBOOK = "/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/inputs/codebook.tsv"


def wquantile(v, w, q):
    """가중 분위수: 오름차순 정렬 뒤 가중치 누적합이 전체의 q배에 처음 이르는 값."""
    v = np.asarray(v, dtype=float)
    w = np.asarray(w, dtype=float)
    ok = ~np.isnan(v)
    v, w = v[ok], w[ok]
    if len(v) == 0:
        return np.nan
    o = np.argsort(v, kind="mergesort")
    v, w = v[o], w[o]
    c = np.cumsum(w)
    i = np.searchsorted(c, q * c[-1], side="left")
    i = min(i, len(v) - 1)
    return v[i]


def load():
    df = pd.read_parquet(DATA)
    df["hh_dinc"] = df.groupby("hid")["p_dinc"].transform("sum")
    df["eqinc"] = df["hh_dinc"] / np.sqrt(df["hnum"])
    med = wquantile(df["eqinc"], df["indwgt"], 0.5)
    df["poor"] = (df["eqinc"] < 0.5 * med).astype(int)
    cuts = [wquantile(df["eqinc"], df["indwgt"], q) for q in (0.2, 0.4, 0.6, 0.8)]
    df["inc5"] = 1 + sum((df["eqinc"] >= c).astype(int) for c in cuts)
    df["sex"] = df["gender"]
    df["age3"] = pd.cut(df["age"], [-1, 17, 64, 200], labels=["0~17", "18~64", "65+"]).astype(str)
    df["age6"] = pd.cut(df["age"], [-1, 17, 34, 49, 64, 74, 200],
                        labels=["0~17", "18~34", "35~49", "50~64", "65~74", "75+"]).astype(str)
    df["age10"] = np.minimum(df["age"] // 10, 8).astype(int)
    df["hs4"] = np.minimum(df["hnum"], 4).astype(int)
    df["nhi3"] = np.where(df["nhi_type"].isin([1, 2]), "지역",
                          np.where(df["nhi_type"].isin([5, 6]), "직장", "의료급여"))
    df["poor2"] = df["poor"]
    return df


def codebook():
    return pd.read_csv(CODEBOOK, sep="\t", dtype=str).fillna("")
