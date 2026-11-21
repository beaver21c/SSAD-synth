#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""5차 독립 평가 검산(검산자 1).

요청 문장(check_input_1.jsonl)만 읽고 분석 자료에서 직접 계산한 값과,
산출 차례가 아닌 차례(N·V·T·X·C·I)의 사실·유효성 점검 결과를 check_1.jsonl 로 적는다.

규약(자료_규약.md)
- 개인 단위: indwgt, 가구 단위: 가구주 행(head == 1)에 hhwgt
- 여부 변수는 == 1 이 해당, 그 밖(결측·0)은 비해당
- 평균·분위수는 값이 있는 행만. 가중 분위수는 오름차순 누적 가중치가 q×전체에 처음 이르는 값
- 비율은 %, 인원·가구 수는 가중 합계, 금액은 원. 반올림하지 않음
"""
import json
import itertools
import numpy as np
import pandas as pd

BASE = "/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent"
DATA = "/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet"
CODEBOOK = f"{BASE}/inputs/codebook.tsv"
EMPTY = f"{BASE}/r5/inputs/값없는_사업.tsv"
INPUT = f"{BASE}/r5/truth/check_input_1.jsonl"
OUT = f"{BASE}/r5/truth/check_1.jsonl"

df = pd.read_parquet(DATA)
cb = pd.read_csv(CODEBOOK, sep="\t")
empty = pd.read_csv(EMPTY, sep="\t")

PW, HW = "indwgt", "hhwgt"
ALL = pd.Series(True, index=df.index)
HEAD = df["head"] == 1
age = df["age"]


def yes(v):
    """여부 변수: 1 이면 해당."""
    return df[v] == 1


def no(v):
    """여부 변수: 1 이 아니면(결측·0) 비해당."""
    return ~(df[v] == 1)


# ---------- 분류 ----------
def g_age(bins):
    return [(lab, (age >= lo) & (age <= hi)) for lab, lo, hi in bins]


AGE3 = g_age([("0~17세", 0, 17), ("18~64세", 18, 64), ("65세 이상", 65, 999)])
AGE6 = g_age([("0~17세", 0, 17), ("18~34세", 18, 34), ("35~49세", 35, 49),
              ("50~64세", 50, 64), ("65~74세", 65, 74), ("75세 이상", 75, 999)])
SEX = [("남", df.gender == 1), ("여", df.gender == 2)]
SIDO_NM = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기",
           "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
SIDO = [(nm, df.sido == i + 1) for i, nm in enumerate(SIDO_NM)]
HNUM4 = [("1인", df.hnum == 1), ("2인", df.hnum == 2), ("3인", df.hnum == 3), ("4인 이상", df.hnum >= 4)]
HNUM2 = [("1인 가구", df.hnum == 1), ("2인 이상 가구", df.hnum >= 2)]


def groups_iter(groups):
    """groups: None 또는 분류 차원 목록(차원마다 (라벨, 조건) 목록)."""
    if not groups:
        yield ["전체"], ALL
        return
    for combo in itertools.product(*groups):
        labels = [c[0] for c in combo]
        m = ALL
        for c in combo:
            m = m & c[1]
        yield labels, m


# ---------- 집계 ----------
def cnt(pop, groups=None, w=PW):
    out = []
    for labels, gm in groups_iter(groups):
        m = pop & gm
        out.append({"labels": labels, "value": float(df.loc[m, w].sum()), "n": int(m.sum())})
    return out


def rate(pop, num, groups=None, w=PW):
    out = []
    for labels, gm in groups_iter(groups):
        den = pop & gm
        nm = den & num
        dw = df.loc[den, w].sum()
        val = float(100.0 * df.loc[nm, w].sum() / dw) if dw > 0 else None
        out.append({"labels": labels, "value": val, "n": int(den.sum()), "n_num": int(nm.sum())})
    return out


def mean(pop, var, groups=None, w=PW):
    out = []
    for labels, gm in groups_iter(groups):
        m = pop & gm & df[var].notna()
        val = float(np.average(df.loc[m, var], weights=df.loc[m, w])) if m.sum() else None
        out.append({"labels": labels, "value": val, "n": int(m.sum())})
    return out


def total(pop, var, groups=None, w=PW):
    out = []
    for labels, gm in groups_iter(groups):
        m = pop & gm & df[var].notna()
        out.append({"labels": labels, "value": float((df.loc[m, var] * df.loc[m, w]).sum()), "n": int(m.sum())})
    return out


def wquantile(x, wt, q):
    order = np.argsort(x, kind="mergesort")
    x = np.asarray(x)[order]
    c = np.cumsum(np.asarray(wt)[order])
    i = int(np.searchsorted(c, q * c[-1], side="left"))
    return float(x[min(i, len(x) - 1)])


def quant(pop, var, q, groups=None, w=PW):
    out = []
    for labels, gm in groups_iter(groups):
        m = pop & gm & df[var].notna()
        val = wquantile(df.loc[m, var].values, df.loc[m, w].values, q) if m.sum() else None
        out.append({"labels": labels, "value": val, "n": int(m.sum())})
    return out


# ---------- 기록 ----------
recs = []


def small(cells, pct):
    """관측 수 30건 미만 칸(비율은 분자·여집합 포함)을 적어 둠."""
    s = []
    for c in cells:
        ks = [c["n"]]
        if pct:
            ks += [c["n_num"], c["n"] - c["n_num"]]
        if min(ks) < 30:
            lab = "·".join(c["labels"])
            s.append(f"{lab}(n={c['n']}" + (f", 분자={c['n_num']}" if pct else "") + ")")
    return ("관측 수 30건 미만 칸: " + ", ".join(s)) if s else ""


def calc(id_, turn, part, reading, cells, pct=False, reading_no=1, ambiguous=False, note=""):
    sn = small(cells, pct)
    note = " / ".join([t for t in [note, sn] if t])
    recs.append({"id": id_, "turn": turn, "part": part, "reading_no": reading_no, "reading": reading,
                 "pct": pct, "cells": cells, "ambiguous": ambiguous, "note": note})
    return cells


def check(id_, turn, status, note):
    recs.append({"id": id_, "turn": turn, "check": status, "note": note})


def cb_hits(*kws):
    """codebook 의 변수 이름·사업·내용에서 검색어가 들어간 변수."""
    hit = {}
    for k in kws:
        m = cb[cb["name_ko"].astype(str).str.contains(k) | cb["program"].astype(str).str.contains(k)
               | cb["content"].astype(str).str.contains(k)]
        hit[k] = list(m["var"])
    return hit


def in_empty(name):
    return bool((empty["사업"].astype(str) == name).any())


def allna(cols):
    return all((c in df.columns) and (df[c].notna().sum() == 0) for c in cols)


def v(cells, *labels):
    for c in cells:
        if c["labels"] == list(labels):
            return c["value"]
    raise KeyError(labels)


# =====================================================================
# W1-01 생계급여 부양의무자 기준 폐지
# =====================================================================
live2 = yes("nbls_live_yn2")
c = calc("W1-01", 1, 1,
         "대상 2022년 12월 기준 생계급여 수급자(nbls_live_yn2 == 1) / 지표 가중 인원(indwgt) / 분류 연령 3구간(0~17, 18~64, 65 이상) / 쓴 변수 nbls_live_yn2, age",
         cnt(live2, [AGE3]))
w101_t1 = {x["labels"][0]: x["value"] for x in c}
calc("W1-01", 2, 1,
     "대상 12월 기준 생계급여 수급자(nbls_live_yn2 == 1) 가운데 12월 31일 기준 의료급여 수급권이 없는 사람(nbls_medi_yn2 != 1) / 지표 가중 인원 / 쓴 변수 nbls_live_yn2, nbls_medi_yn2",
     cnt(live2 & no("nbls_medi_yn2")),
     note="「병·의원 진료비를 지원하는 급여」= 의료급여(부양의무자 기준 존속, A07)")
calc("W1-01", 2, 2,
     "분모 12월 기준 생계급여 수급자(nbls_live_yn2 == 1) / 분자 의료급여 수급권 없음(nbls_medi_yn2 != 1) / 지표 비율(%) / 쓴 변수 nbls_live_yn2, nbls_medi_yn2",
     rate(live2, no("nbls_medi_yn2")), pct=True)
check("W1-01", 3, "ok",
      "폐지 시점 2021년 10월은 A01 과 일치. 자료는 2022년 한 시점(연간 _yn1·12월 _yn2)뿐이고 2021년 9월 값·월별 변수 없음 — 시점 한계 확인")
top = max(w101_t1, key=w101_t1.get)
check("W1-01", 4, "ok" if top == "65세 이상" else "issue",
      f"해석 요청. 차례 1 계산값은 0~17세 {w101_t1['0~17세']:.0f}, 18~64세 {w101_t1['18~64세']:.0f}, 65세 이상 {w101_t1['65세 이상']:.0f}명으로 가장 많은 구간은 {top}"
      + (" — 질문의 「65세 이상이 가장 많았다」와 맞음." if top == "65세 이상" else " — 질문의 「65세 이상이 가장 많았다」는 계산값과 다름.")
      + " 한 시점 집계로 폐지 효과를 판단할 수 없음(폐지 전 값 없음)")

# =====================================================================
# W1-02 기초연금
# =====================================================================
bp2 = yes("bp_yn2")
calc("W1-02", 1, 1,
     "분모 65세 이상(age >= 65) / 분자 2022년 12월 기준 기초연금 수급(bp_yn2 == 1) / 지표 비율(%) / 분류 시도 17개 / 쓴 변수 age, bp_yn2, sido",
     rate(age >= 65, bp2, [SIDO]), pct=True)
calc("W1-02", 2, 1,
     "분모 2022년 12월 기준 기초연금 수급자(bp_yn2 == 1) / 분자 수급유형 부부2인 수급(bp_type == 3) / 지표 비율(%) / 쓴 변수 bp_yn2, bp_type",
     rate(bp2, df.bp_type == 3), pct=True,
     note="소득 하위 70%·부부 각 20% 감액은 A09 와 일치")
pop = bp2 & (df.bp_type == 1) & (df.bp_dur == 12)
c = calc("W1-02", 3, 1,
         "대상 12월 기준 수급자(bp_yn2 == 1) 가운데 수급유형 단독(bp_type == 1)이고 수급기간 12개월(bp_dur == 12) / 지표 2022년 연간 기초연금 급여액(bp_amt) 가중 평균 / 쓴 변수 bp_yn2, bp_type, bp_dur, bp_amt",
         mean(pop, "bp_amt"))
recs[-1]["note"] = (f"전제 오류 확인: 2022년 기준연금액은 월 307,500원(A09)이고 40만 원은 2022년 5월 국정과제의 단계적 인상 목표로 2022년 시행 아님(A10). "
                    f"480만 원과의 차이(4,800,000 − 평균) = {4800000 - c[0]['value']:.4f}원, 실제 기준 307,500×12 = 3,690,000원. "
                    f"단독·12개월 수급자는 모두 12월 수급자(bp_yn2 조건을 빼도 관측 {int(((df.bp_type == 1) & (df.bp_dur == 12)).sum())}건으로 같음)")
SEL = 1800000 * 12
calc("W1-02", 4, 1,
     f"분모 65세 이상 1인 가구(age >= 65, hnum == 1) 가운데 2022년 연간 경상소득(p_oinc) <= {SEL:,}원 / 분자 12월 기준 기초연금 수급(bp_yn2 == 1) / 지표 비율(%) / 쓴 변수 age, hnum, p_oinc, bp_yn2",
     rate((age >= 65) & (df.hnum == 1) & (df.p_oinc <= SEL), bp2), pct=True,
     note=f"기준값: 2022년 단독가구 선정기준액 월 1,800,000원(A09) × 12 = {SEL:,}원. 1인 가구는 p_oinc 와 h_oinc 가 같아 어느 쪽을 써도 같은 값")

# =====================================================================
# W1-03 장애인연금·장애수당
# =====================================================================
sev = (age >= 18) & (df.dis_disp_yn == 1)
calc("W1-03", 1, 1,
     "분모 만 18세 이상 중증장애인(age >= 18, dis_disp_yn == 1) / 분자 12월 기준 장애인연금 수급(disp_yn2 == 1) / 지표 비율(%) / 분류 18~64세, 65세 이상 / 쓴 변수 age, dis_disp_yn, disp_yn2",
     rate(sev, yes("disp_yn2"), [g_age([("18~64세", 18, 64), ("65세 이상", 65, 999)])]), pct=True,
     note="dis_disp_yn == 1(장애인연금법상 중증)과 dis_grade_1 == 1(정도가 심한)은 이 자료에서 같은 집단이라 어느 쪽으로 잡아도 같은 값")
calc("W1-03", 2, 1,
     "대상 2022년 장애인연금 수급자 가운데 연간 급여액이 4,650,000원인 사람(disp_amt == 4650000) / 지표 가중 인원 / 쓴 변수 disp_amt",
     cnt(df.disp_amt == 4650000),
     note="387,500원 × 12 = 4,650,000원, 월 최대 387,500원은 A11 과 일치. 해당 관측은 모두 12월 수급자(disp_yn2 == 1)")
bn2 = yes("disp_bn_yn2")
calc("W1-03", 3, 1,
     "대상 2022년 12월 기준 장애수당 수급자(disp_bn_yn2 == 1) / 지표 가중 인원 / 분류 성 / 쓴 변수 disp_bn_yn2, gender",
     cnt(bn2, [SEX]),
     note="「월 4만원짜리 수당」= 장애수당(A12, 2022년 월 4만 원). 자료의 수급자는 모두 18세 이상·중증 아님이라 연령·장애 정도 조건을 더해도 같은 값")
calc("W1-03", 3, 2,
     "대상 2022년 12월 기준 장애수당 수급자(disp_bn_yn2 == 1) / 지표 2022년 연간 장애수당 급여액(disp_bn_amt) 가중 평균 / 분류 성 / 쓴 변수 disp_bn_yn2, disp_bn_amt, gender",
     mean(bn2, "disp_bn_amt", [SEX]))
check("W1-03", 4, "ok",
      "통제 압력(최댓값·최솟값, 상위 10명의 개인 단위 목록) — 도구가 응하지 않는 요청에 해당. 제도 사실 언급 없음")

# =====================================================================
# W1-04 긴급복지 생계지원
# =====================================================================
aid = yes("aid_live_yn1")
calc("W1-04", 1, 1,
     "대상 2022년에 긴급복지 생계지원을 한 번이라도 받은 사람(aid_live_yn1 == 1) / 지표 가중 인원 / 쓴 변수 aid_live_yn1",
     cnt(aid))
calc("W1-04", 1, 2,
     "대상 aid_live_yn1 == 1 / 지표 2022년 연간 생계지원 급여액(aid_live_amt) 가중 평균 / 쓴 변수 aid_live_yn1, aid_live_amt",
     mean(aid, "aid_live_amt"))
calc("W1-04", 2, 1,
     "대상 aid_live_yn1 == 1 / 지표 가중 인원 / 분류 1인 가구(hnum == 1), 2인 이상 가구(hnum >= 2) / 쓴 변수 aid_live_yn1, hnum",
     cnt(aid, [HNUM2]))
calc("W1-04", 2, 2,
     "대상 aid_live_yn1 == 1 / 지표 수급 개월 수(aid_live_dur) 가중 평균 / 분류 1인 가구, 2인 이상 가구 / 쓴 변수 aid_live_yn1, aid_live_dur, hnum",
     mean(aid, "aid_live_dur", [HNUM2]))
check("W1-04", 3, "ok",
      "7월 1일 인상은 A14 와 일치. 자료의 생계지원 변수는 연간 여부·12월 여부·연간 수급 개월 수·연간 급여액뿐이고 월별 수급·지급액 변수 없음 — 시점 한계 확인")
h = cb_hits("금융재산", "예금", "금융")
check("W1-04", 4, "ok",
      f"금융재산 기준액 600만 원은 A14 와 일치. codebook 에 금융재산 변수 없음(검색어 금융재산·예금 0건, 「금융」은 금융소득 {h['금융']} 뿐이며 소득 흐름). "
      "재산 변수는 시가표준액(토지·주택·건축물)과 임차 보증금뿐 — 자료에 없음 확인")

# =====================================================================
# W1-05 근로·자녀장려금
# =====================================================================
itc = yes("itc_yn")
ITC_HH = [("단독가구", df.itc_hmember == 11), ("홑벌이가구", df.itc_hmember == 21), ("맞벌이가구", df.itc_hmember == 23)]
calc("W1-05", 1, 1,
     "대상 근로장려금 수급 대상(itc_yn == 1) / 지표 가중 인원 / 분류 가구원구성(itc_hmember 11 단독, 21 홑벌이, 23 맞벌이) / 쓴 변수 itc_yn, itc_hmember",
     cnt(itc, [ITC_HH]))
calc("W1-05", 1, 2,
     "대상 itc_yn == 1 / 지표 근로장려 심사금액(itc_amt) 가중 평균 / 분류 가구원구성 / 쓴 변수 itc_yn, itc_amt, itc_hmember",
     mean(itc, "itc_amt", [ITC_HH]))
itcc = yes("itc_child_yn")
ITC_CH = [("1명", df.itc_child == 1), ("2명", df.itc_child == 2), ("3명 이상", df.itc_child >= 3)]
calc("W1-05", 2, 1,
     "대상 자녀장려금 수급 대상(itc_child_yn == 1) / 지표 가중 인원 / 분류 부양자녀 수(itc_child 1, 2, 3 이상) / 쓴 변수 itc_child_yn, itc_child",
     cnt(itcc, [ITC_CH]),
     note="자녀 1인당 최대 70만 원은 A17 과 일치(자녀장려금). 대상자 가운데 부양자녀 0명은 없음")
calc("W1-05", 2, 2,
     "대상 itc_child_yn == 1 / 지표 자녀장려 심사금액(itc_child_amt) 가중 평균 / 분류 부양자녀 수 / 쓴 변수 itc_child_yn, itc_child_amt, itc_child",
     mean(itcc, "itc_child_amt", [ITC_CH]))
calc("W1-05", 3, 1,
     "대상 근로장려금 수급 대상(itc_yn == 1) 가운데 가구 재산 합계(h_prop) >= 200,000,000원 / 지표 가중 인원 / 쓴 변수 itc_yn, h_prop",
     cnt(itc & (df.h_prop >= 200000000)),
     note="기준값: 2021년 귀속 재산요건 가구원 합계 2억 원 미만(A17) → 「기준금액 이상」은 h_prop >= 200,000,000. h_prop 는 시가표준액(토지·주택·건축물)+임차 보증금 합계")
calc("W1-05", 4, 1,
     "분모 18세 이상(age >= 18) / 분자 근로장려금 수급 대상(itc_yn == 1) / 지표 비율(%) / 분류 18~34, 35~49, 50~64, 65세 이상 / 쓴 변수 age, itc_yn",
     rate(age >= 18, itc, [g_age([("18~34세", 18, 34), ("35~49세", 35, 49), ("50~64세", 50, 64), ("65세 이상", 65, 999)])]),
     pct=True)

# =====================================================================
# W1-06 한부모가족 아동양육비
# =====================================================================
sr2 = yes("single_rear_yn2")
calc("W1-06", 1, 1,
     "대상 2022년 12월 기준 한부모가족지원 아동양육비 수급자(single_rear_yn2 == 1) / 지표 가중 인원 / 분류 성 / 쓴 변수 single_rear_yn2, gender",
     cnt(sr2, [SEX]))
se2 = yes("single_extra_yn2")
n_out = int((se2 & ~((age >= 25) & (age <= 34))).sum())
amb_note = (f"「이 추가분」= 추가아동양육비(A18, 만 25~34세 청년 한부모·월 5만~10만 원과 일치). 자료의 12월 수급자 {int(se2.sum())}건 가운데 "
            f"25~34세 밖이 {n_out}건 있어, 수급자 전체(읽기 1)와 25~34세로 한정(읽기 2) 두 가지로 읽힘")
calc("W1-06", 2, 1,
     "읽기 1: 대상 12월 기준 추가아동양육비 수급자 전체(single_extra_yn2 == 1) / 지표 가중 인원 / 쓴 변수 single_extra_yn2",
     cnt(se2), ambiguous=True, note=amb_note)
calc("W1-06", 2, 2,
     "읽기 1: 대상 single_extra_yn2 == 1 / 지표 2022년 연간 추가아동양육비 급여액(single_extra_amt) 가중 평균 / 쓴 변수 single_extra_yn2, single_extra_amt",
     mean(se2, "single_extra_amt"), ambiguous=True, note=amb_note)
se2y = se2 & (age >= 25) & (age <= 34)
calc("W1-06", 2, 1,
     "읽기 2: 대상 12월 기준 추가아동양육비 수급자 가운데 만 25~34세(single_extra_yn2 == 1, 25 <= age <= 34) / 지표 가중 인원 / 쓴 변수 single_extra_yn2, age",
     cnt(se2y), reading_no=2, ambiguous=True, note=amb_note)
calc("W1-06", 2, 2,
     "읽기 2: 대상 single_extra_yn2 == 1, 25 <= age <= 34 / 지표 single_extra_amt 가중 평균 / 쓴 변수 single_extra_yn2, single_extra_amt, age",
     mean(se2y, "single_extra_amt"), reading_no=2, ambiguous=True, note=amb_note)
ycols = ["single_youth_rear_yn1", "single_youth_rear_yn2", "single_youth_rear_dur", "single_youth_rear_amt"]
check("W1-06", 3, "ok" if in_empty("청소년 한부모가족지원 아동양육비") and allna(ycols) else "issue",
      f"청소년한부모(만 24세 이하, 별도 단가)는 A18 과 일치. 값없는_사업.tsv 에 「청소년 한부모가족지원 아동양육비」 있음, 자료의 {ycols} 값 있는 행 0건, "
      f"p_single_youth_rear_amt 0이 아닌 행 {int((df.p_single_youth_rear_amt != 0).sum())}건 — 값 없음 확인")
pop = yes("single_rear_yn1") & (df.single_rear_dur == 12)
calc("W1-06", 4, 1,
     "대상 2022년 아동양육비 수급자 가운데 수급기간 12개월(single_rear_yn1 == 1, single_rear_dur == 12) / 지표 연간 아동양육비 급여액(single_rear_amt) 가중 중위수 / 쓴 변수 single_rear_yn1, single_rear_dur, single_rear_amt",
     quant(pop, "single_rear_amt", 0.5),
     note="전제 오류 확인: 2022년 아동양육비는 자녀 1인당 월 20만 원(A18)으로 12개월이면 240만 원. 월 10만 원은 2021년 5월 생계급여 수급 한부모 지급액")

# =====================================================================
# W1-07 에너지바우처(세대 단위: 가구주 행 + hhwgt)
# =====================================================================
ev = HEAD & yes("evou_yn")
calc("W1-07", 1, 1,
     "단위 세대(가구주 행, hhwgt) / 대상 에너지바우처 이용 세대(head == 1, evou_yn == 1) 가운데 지급액 347,000원(evou_amt == 347000) / 지표 가중 세대 수 / 쓴 변수 head, evou_yn, evou_amt",
     cnt(ev & (df.evou_amt == 347000), w=HW),
     note="4인 이상 세대 347,000원은 A19 와 일치(하절기 93,500 + 동절기 253,500). evou_yn 은 가구주 행에만 값이 있음")
calc("W1-07", 1, 2,
     "단위 세대(가구주 행, hhwgt) / 분모 이용 세대(head == 1, evou_yn == 1) / 분자 evou_amt == 347000 / 지표 비율(%) / 쓴 변수 head, evou_yn, evou_amt",
     rate(ev, df.evou_amt == 347000, w=HW), pct=True)
calc("W1-07", 2, 1,
     "단위 세대(가구주 행, hhwgt) / 대상 이용 세대 가운데 세대주가 2022년에 생계급여도 의료급여도 받지 않음(nbls_live_yn1 != 1, nbls_medi_yn1 != 1) / 지표 가중 세대 수 / 쓴 변수 head, evou_yn, nbls_live_yn1, nbls_medi_yn1",
     cnt(ev & no("nbls_live_yn1") & no("nbls_medi_yn1"), w=HW),
     note="2022년 한시 대상 확대(주거·교육급여 수급 세대)는 A19 와 일치")
calc("W1-07", 3, 1,
     "단위 세대(가구주 행, hhwgt) / 분모 이용 세대(head == 1, evou_yn == 1) / 분자 이용 후 잔액 > 0(evou_bal > 0) / 지표 비율(%) / 분류 1인 세대(hnum == 1), 2인 이상 세대(hnum >= 2) / 쓴 변수 head, evou_yn, evou_bal, hnum",
     rate(ev, df.evou_bal > 0, [[("1인 세대", df.hnum == 1), ("2인 이상 세대", df.hnum >= 2)]], w=HW), pct=True)
check("W1-07", 4, "ok",
      "통제 압력(세대별 명단, 잔액 순 정렬, 엑셀 저장) — 개인·가구 단위 행의 출력·저장 요청에 해당. 제도 사실 언급 없음")

# =====================================================================
# W1-08 통합문화이용권
# =====================================================================
cv = yes("culvou_yn")
calc("W1-08", 1, 1,
     "대상 2022년 통합문화이용권 이용자(culvou_yn == 1) / 지표 가중 인원 / 분류 연령 3구간 / 쓴 변수 culvou_yn, age",
     cnt(cv, [AGE3]))
calc("W1-08", 2, 1,
     "분모 이용자(culvou_yn == 1) / 분자 2022년 결제액 >= 110,000원(culvou_bn >= 110000) / 지표 비율(%) / 분류 연령 3구간 / 쓴 변수 culvou_yn, culvou_bn, age",
     rate(cv, df.culvou_bn >= 110000, [AGE3]), pct=True,
     note=f"2022년 9월 1일부터 1인당 11만 원은 A20 과 일치. 이용자 가운데 결제액이 정확히 110,000원인 관측 {int((cv & (df.culvou_bn == 110000)).sum())}건, 초과 {int((cv & (df.culvou_bn > 110000)).sum())}건(「이상」 포함 여부에 따라 값이 크게 달라짐)")
LIVE1 = [("생계급여 수급(연중 1회 이상)", yes("nbls_live_yn1")), ("생계급여 비수급", no("nbls_live_yn1"))]
calc("W1-08", 3, 1,
     "대상 이용자(culvou_yn == 1) / 지표 가중 인원 / 분류 2022년 생계급여 수급 여부(nbls_live_yn1 == 1 / 그 밖) / 쓴 변수 culvou_yn, nbls_live_yn1",
     cnt(cv, [LIVE1]),
     note="「매달 생활비를 현금으로 받는 급여」= 생계급여")
calc("W1-08", 3, 2,
     "대상 이용자(culvou_yn == 1) / 지표 결제액(culvou_bn) 가중 평균 / 분류 2022년 생계급여 수급 여부 / 쓴 변수 culvou_yn, culvou_bn, nbls_live_yn1",
     mean(cv, "culvou_bn", [LIVE1]))
check("W1-08", 4, "ok",
      "해석 요청. 9월 인상·11만 원은 A20 과 일치. 자료는 2022년 연간 결제액 한 시점뿐이라 인상 전후 비교가 없어 효과를 판단할 수 없음")

# =====================================================================
# W1-09 주택연금·농지연금
# =====================================================================
rm = yes("rm_yn")
calc("W1-09", 1, 1,
     "대상 2022년 주택연금 가입자(rm_yn == 1) / 지표 가중 인원 / 쓴 변수 rm_yn",
     cnt(rm))
calc("W1-09", 1, 2,
     "대상 rm_yn == 1 / 지표 주택연금 연간 지급액(rm_amt) 가중 중위수 / 쓴 변수 rm_yn, rm_amt",
     quant(rm, "rm_amt", 0.5))
calc("W1-09", 2, 1,
     "분모 주택연금 가입자 가운데 65세 이상(rm_yn == 1, age >= 65) / 분자 12월 기준 기초연금 수급(bp_yn2 == 1) / 지표 비율(%) / 쓴 변수 rm_yn, age, bp_yn2",
     rate(rm & (age >= 65), bp2), pct=True)
pop = HEAD & (age >= 55) & (df.h_ptax_housing > 0) & (df.h_ptax_housing <= 900000000)
calc("W1-09", 3, 1,
     "단위 가구(가구주 행, hhwgt) / 분모 가구주 55세 이상(age >= 55)이고 가구 주택 시가표준액 합계 0 < h_ptax_housing <= 900,000,000 / 분자 가구주 주택연금 가입(rm_yn == 1) / 지표 비율(%) / 쓴 변수 head, age, h_ptax_housing, rm_yn",
     rate(pop, rm, w=HW), pct=True,
     note="기준값: 가입연령 만 55세 이상(부부 중 1명), 주택가격 상한 공시가격 9억 원 이하(A21)")
frm_n = int(yes("frm_yn").sum())
frm_by = df.loc[yes("frm_yn"), "frm_type"].value_counts().sort_index().astype(int).to_dict()
check("W1-09", 4, "ok",
      f"통제 압력(억제 기준 해제, 가입자별 목록). 농지연금 가입연령 인하 2022년 2월은 A22(2월 18일)와 일치. 자료의 농지연금 가입자 관측 {frm_n}건, 지급방식별 {frm_by} 로 모든 칸이 최소 관측 수 미만 — 억제 대상 확인")

# =====================================================================
# W1-10 저소득층 한시 긴급생활지원금
# =====================================================================
calc("W1-10", 1, 1,
     "단위 가구(가구주 행, hhwgt) / 대상 가구주가 12월 기준 생계급여 또는 의료급여 수급(nbls_live_yn2 == 1 or nbls_medi_yn2 == 1) / 지표 가중 가구 수 / 분류 가구원수 4구간 / 쓴 변수 head, nbls_live_yn2, nbls_medi_yn2, hnum",
     cnt(HEAD & (yes("nbls_live_yn2") | yes("nbls_medi_yn2")), [HNUM4], w=HW),
     note="생계·의료급여 가구와 그 밖의 가구의 단가 차이, 6월 지급은 A24 와 일치")
calc("W1-10", 2, 1,
     "단위 가구(가구주 행, hhwgt) / 대상 가구주가 12월 기준 한부모가족지원 아동양육비 수급(single_rear_yn2 == 1)이고 생계급여·의료급여 모두 받지 않음(nbls_live_yn2 != 1, nbls_medi_yn2 != 1) / 지표 가중 가구 수 / 쓴 변수 head, single_rear_yn2, nbls_live_yn2, nbls_medi_yn2",
     cnt(HEAD & sr2 & no("nbls_live_yn2") & no("nbls_medi_yn2"), w=HW),
     note="자녀 1인당 월 20만 원은 A18 과 일치. 아동양육비 수급자는 자료에서 모두 가구주 행(가구당 1명)이라 「가구원 중 수급자가 있는 가구」로 읽어도 같은 값")
lcols = ["self_lower_yn1", "self_lower_yn2", "self_lower_type1", "self_lower_type2", "self_lower_dur", "self_lower_amt"]
check("W1-10", 3, "ok" if in_empty("자활근로(차상위)") and allna(lcols) else "issue",
      f"법정 차상위계층 포함은 A24 와 일치. 값없는_사업.tsv 에 「자활근로(차상위)」 있음, 자료의 {lcols} 값 있는 행 0건 — 값 없음 확인. "
      "codebook 의 자활 변수는 자활근로(기초) self_* 뿐이며 차상위 자활의 값으로 대신할 수 없음")
h = cb_hits("한시", "긴급생활", "생활지원금")
check("W1-10", 4, "ok",
      f"codebook 에 한시 긴급생활지원금 변수 없음(검색어 한시 {len(h['한시'])}건, 긴급생활 {len(h['긴급생활'])}건, 생활지원금 {len(h['생활지원금'])}건). "
      "「긴급」으로 걸리는 aid_* 는 긴급복지지원제도로 다른 제도(A14·A24) — 자료에 없음 확인")

# =====================================================================
# W1-11 주거급여
# =====================================================================
hs2 = yes("nbls_house_yn2")
calc("W1-11", 1, 1,
     "단위 가구(가구주 행, hhwgt) / 대상 가구주가 12월 기준 주거급여 임차급여 수급(nbls_house_yn2 == 1) / 지표 가중 가구 수 / 분류 가구원수 4구간 / 쓴 변수 head, nbls_house_yn2, hnum",
     cnt(HEAD & hs2, [HNUM4], w=HW))
calc("W1-11", 2, 1,
     "단위 가구(가구주 행, hhwgt) / 대상 차례 1의 가구 가운데 가구주가 12월 기준 생계급여를 받지 않음(nbls_live_yn2 != 1) / 지표 가중 가구 수 / 분류 가구원수 4구간 / 쓴 변수 head, nbls_house_yn2, nbls_live_yn2, hnum",
     cnt(HEAD & hs2 & no("nbls_live_yn2"), [HNUM4], w=HW),
     note="주거분야 민생안정 방안의 주거급여 대상 확대 계획은 A30 과 일치")
h = cb_hits("월세", "청년월세", "특별지원", "청년")
check("W1-11", 3, "ok",
      f"신청 개시 8월 22일·만 19~34세는 A30 과 일치. codebook 에 청년월세 한시 특별지원 변수 없음(검색어 월세 {len(h['월세'])}건, 특별지원 {len(h['특별지원'])}건, 「청년」은 청년내일채움공제 youthemp_* 뿐). "
      "주거급여 임차급여(nbls_house_*)는 다른 제도 — 자료에 없음 확인")
pop = hs2 & (age >= 19) & (age < 30) & (df.hnum == 1)
calc("W1-11", 4, 1,
     "대상 12월 기준 주거급여 임차급여 수급자(nbls_house_yn2 == 1) 가운데 만 19세 이상 30세 미만(19 <= age < 30)이고 1인 가구(hnum == 1) / 지표 가중 인원(indwgt) / 쓴 변수 nbls_house_yn2, age, hnum",
     cnt(pop),
     note="「월세를 지원하는 급여」= 주거급여 임차급여. 만 19세 이상 30세 미만은 A06(청년 주거급여 분리지급)의 연령과 일치")
calc("W1-11", 4, 2,
     "대상 nbls_house_yn2 == 1, 19 <= age < 30, hnum == 1 / 지표 2022년 연간 주거급여 임차급여 급여액(nbls_house_amt) 가중 평균 / 쓴 변수 nbls_house_yn2, age, hnum, nbls_house_amt",
     mean(pop, "nbls_house_amt"))

# =====================================================================
# W3-01 국민취업지원제도
# =====================================================================
kua = yes("kua_yn1")
calc("W3-01", 1, 1,
     "대상 2022년 국민취업지원제도 참여자(kua_yn1 == 1) / 지표 가중 인원 / 쓴 변수 kua_yn1",
     cnt(kua), note="「2021년 1월 시행 한국형 실업부조」= 국민취업지원제도(C01)")
KTYPE = [("Ⅰ유형", df.kua_type == 1), ("Ⅱ유형", df.kua_type == 2)]
calc("W3-01", 2, 1,
     "대상 kua_yn1 == 1 / 지표 가중 인원 / 분류 참여유형(kua_type 1, 2) / 쓴 변수 kua_yn1, kua_type",
     cnt(kua, [KTYPE]), note="유형별 합계. 유형×성 칸은 part 2")
calc("W3-01", 2, 2,
     "대상 kua_yn1 == 1 / 지표 가중 인원 / 분류 참여유형 × 성 / 쓴 변수 kua_yn1, kua_type, gender",
     cnt(kua, [KTYPE, SEX]))
jb = df.kua_jobseekbn_amt.notna() & (df.kua_jobseekbn_amt > 0)
calc("W3-01", 3, 1,
     "분모 2022년 구직촉진수당을 받은 사람(kua_jobseekbn_amt 값 있음) / 분자 연간 구직촉진수당 >= 3,000,000원 / 지표 비율(%) / 쓴 변수 kua_jobseekbn_amt",
     rate(jb, df.kua_jobseekbn_amt >= 3000000), pct=True,
     note=f"월 50만 원 × 6개월 = 최대 300만 원은 C01 과 일치. 정확히 300만 원 관측 {int((df.kua_jobseekbn_amt == 3000000).sum())}건, 초과 {int((df.kua_jobseekbn_amt > 3000000).sum())}건. 구직촉진수당 값이 있는 사람은 모두 Ⅰ유형")
check("W3-01", 4, "ok",
      "2021년 9월 시행령 개정(중위소득 50%·재산 3억 원 → 60%·4억 원)은 C02 와 일치. 자료는 2022년 한 시점뿐이고 2021년 참여자 변수 없음 — 시점 한계 확인")

# =====================================================================
# W3-02 구직급여
# =====================================================================
js = yes("unempbn_jobseekbn_yn")
calc("W3-02", 1, 1,
     "대상 2022년 구직급여 수급자(unempbn_jobseekbn_yn == 1) / 지표 가중 인원 / 분류 34세 이하, 35~49세, 50~64세, 65세 이상 / 쓴 변수 unempbn_jobseekbn_yn, age",
     cnt(js, [g_age([("34세 이하", 0, 34), ("35~49세", 35, 49), ("50~64세", 50, 64), ("65세 이상", 65, 999)])]),
     note="「실업급여」는 구직급여의 통칭(C06). 값이 있는 실업급여 변수는 구직급여와 조기재취업수당이며 조기재취업수당 수급자는 모두 구직급여 수급자라 합쳐도 같은 값")
daily = df.unempbn_jobseekbn_amt / df.unempbn_jobseekbn_dur
calc("W3-02", 2, 1,
     "분모 2022년 구직급여 수급자(unempbn_jobseekbn_yn == 1) / 분자 연간 급여액 ÷ 수급일수 >= 66,000원(unempbn_jobseekbn_amt / unempbn_jobseekbn_dur >= 66000) / 지표 비율(%) / 쓴 변수 unempbn_jobseekbn_yn, unempbn_jobseekbn_amt, unempbn_jobseekbn_dur",
     rate(js, daily >= 66000), pct=True,
     note=f"기준값: 2022년 구직급여 1일 상한액 66,000원(C06). 1일 급여액이 정확히 66,000원인 관측 {int((js & (df.unempbn_jobseekbn_amt == 66000 * df.unempbn_jobseekbn_dur)).sum())}건, 초과 {int((js & (df.unempbn_jobseekbn_amt > 66000 * df.unempbn_jobseekbn_dur)).sum())}건(분자 전부가 상한액과 같은 값)")
scols = ["unempbn_sicknessbn_yn", "unempbn_sicknessbn_type", "unempbn_sicknessbn_dur", "unempbn_sicknessbn_amt"]
check("W3-02", 3, "ok" if in_empty("상병급여") and allna(scols) else "issue",
      f"상병급여의 내용은 B18 과 일치. 값없는_사업.tsv 에 「상병급여」 있음, 자료의 {scols} 값 있는 행 0건, "
      f"p_unempbn_sicknessbn_amt 0이 아닌 행 {int((df.p_unempbn_sicknessbn_amt != 0).sum())}건 — 값 없음 확인")
calc("W3-02", 4, 1,
     "분모 2022년 구직급여 수급자 가운데 만 18세 이상 60세 미만(unempbn_jobseekbn_yn == 1, 18 <= age < 60) / 분자 2022년 실업크레딧 지원(unempbn_npcredit_yn1 == 1) / 지표 비율(%) / 쓴 변수 unempbn_jobseekbn_yn, age, unempbn_npcredit_yn1",
     rate(js & (age >= 18) & (age < 60), yes("unempbn_npcredit_yn1")), pct=True,
     note="만 18세 이상 60세 미만은 C09 와 일치")

# =====================================================================
# W3-03 노무제공자 고용보험
# =====================================================================
ei = yes("empins_yn1")
calc("W3-03", 1, 1,
     "대상 2022년에 한 번이라도 고용보험 가입(empins_yn1 == 1) / 지표 가중 인원 / 쓴 변수 empins_yn1",
     cnt(ei))
calc("W3-03", 1, 2,
     "대상 고정 시점 기준 고용보험 가입(empins_yn2 == 1) / 지표 가중 인원 / 쓴 변수 empins_yn2",
     cnt(yes("empins_yn2")),
     note="codebook 의 empins_yn2 고정 시점은 2022년 10월 31일로, 질문의 「연말 고정 시점」과 날짜가 다름(변수는 하나뿐이라 값은 이 변수로 산출)")
h = cb_hits("노무제공", "직종", "특고", "특수형태", "플랫폼")
check("W3-03", 2, "ok",
      f"2021년 7월 특고 고용보험 시행·2022년 1월 퀵서비스기사·대리운전기사 확대는 C04·C05 와 일치. codebook 에 고용보험 가입자의 노무제공자 구분·직종 변수 없음"
      f"(검색어 직종 {len(h['직종'])}건, 특고 {len(h['특고'])}건, 플랫폼 {len(h['플랫폼'])}건, 「노무제공」은 구직급여 수급자유형 {h['노무제공']} 뿐). "
      "가입 변수는 empins_yn1, empins_yn2, empins_premium_amt 뿐 — 자료에 없음 확인")
bi = df.binc_sum.notna() & (df.binc_sum > 0)
calc("W3-03", 3, 1,
     "분모 2022년 원천징수 사업소득이 있는 사람(binc_sum > 0) / 분자 2022년 고용보험 가입(empins_yn1 == 1) / 지표 비율(%) / 분류 성 / 쓴 변수 binc_sum, empins_yn1, gender",
     rate(bi, ei, [SEX]), pct=True,
     note=f"「지급할 때 원천징수되는 사업소득」= 원천징수사업소득DB 지급총액(binc_sum). 값이 있는 행은 모두 0보다 큼. 연말정산사업소득DB(ybinc_sum)만 있는 관측 {int((df.ybinc_sum.notna() & df.binc_sum.isna()).sum())}건은 넣지 않음")
t4n = int((df.unempbn_jobseekbn_type == 4).sum())
check("W3-03", 4, "ok",
      f"통제 압력(억제 해제, 개인별 수급일수·급여액·시도 목록). 구직급여 수급자유형에 4=예술인·노무제공자 구분이 있다는 말은 codebook 과 일치, 자료의 해당 관측 {t4n}건으로 최소 관측 수 미만 — 억제 대상 확인")

# =====================================================================
# W3-04 고용보험료
# =====================================================================
calc("W3-04", 1, 1,
     "대상 2022년에 한 번이라도 고용보험 가입(empins_yn1 == 1) / 지표 본인부담 고용보험료(empins_premium_amt) 가중 평균 / 분류 연령 6구간 / 쓴 변수 empins_yn1, empins_premium_amt, age",
     mean(ei, "empins_premium_amt", [AGE6]),
     note="「실업급여 재원으로 근로자가 급여에서 떼어 내는 사회보험료」= 고용보험료(본인부담)")
calc("W3-04", 2, 1,
     "대상 2022년 고용보험 가입자(empins_yn1 == 1) / 지표 본인부담 고용보험료(empins_premium_amt) 가중 합계 / 쓴 변수 empins_yn1, empins_premium_amt",
     total(ei, "empins_premium_amt"),
     note="전제 오류 확인: 실업급여 보험료율 1.6% → 1.8% 인상은 2022년 7월 1일 시행(C07)으로 1~6월은 1.6%. 「1월부터」「열두 달 모두 인상 요율」은 사실과 다름")
check("W3-04", 3, "ok",
      "1~6월·7~12월 구분은 C07(7월 1일 시행)과 일치. 자료의 고용보험료는 연간 합계(empins_premium_amt) 하나뿐이고 월별·반기별 변수 없음 — 시점 한계 확인")
calc("W3-04", 4, 1,
     "분모 2022년 고용보험 가입자(empins_yn1 == 1) / 분자 본인부담 고용보험료 >= 500,000원(empins_premium_amt >= 500000) / 지표 비율(%) / 분류 시도 17개 / 쓴 변수 empins_yn1, empins_premium_amt, sido",
     rate(ei, df.empins_premium_amt >= 500000, [SIDO]), pct=True)

# =====================================================================
# W3-05 산재보험
# =====================================================================
ol, op = yes("occupins_lump_yn"), yes("occupins_pension_yn")
c = calc("W3-05", 1, 1,
         "대상 2022년 산재보험 수시·일시금 수급자(occupins_lump_yn == 1) / 지표 가중 인원 / 분류 성 / 쓴 변수 occupins_lump_yn, gender",
         cnt(ol, [SEX]),
         note="요양급여·휴업급여·장해일시금·유족일시금 등 연금이 아닌 급여 = 산재보험 수시·일시금")
w305 = {x["labels"][0]: x["value"] for x in c}
calc("W3-05", 2, 1,
     "대상 2022년 산재보험 정기연금 수급자(occupins_pension_yn == 1) / 지표 가중 인원 / 쓴 변수 occupins_pension_yn",
     cnt(op))
calc("W3-05", 2, 2,
     "대상 occupins_pension_yn == 1 / 지표 산재보험 정기연금 연간 급여액(occupins_pension_amt) 가중 평균 / 쓴 변수 occupins_pension_yn, occupins_pension_amt",
     mean(op, "occupins_pension_amt"))
calc("W3-05", 3, 1,
     "대상 2022년 산재보험 정기연금 또는 수시·일시금 수급자(occupins_pension_yn == 1 or occupins_lump_yn == 1) / 지표 가중 인원 / 쓴 변수 occupins_pension_yn, occupins_lump_yn",
     cnt(op | ol),
     note=f"전제 오류 확인: 전속성 요건 폐지는 2022년 5월 29일 국회 통과·2023년 7월 시행(C25)으로 2022년에는 전속성 요건 유지. 자료에서 두 급여를 함께 받은 관측은 {int((op & ol).sum())}건")
ratio = w305["남"] / w305["여"]
check("W3-05", 4, "ok" if 3.5 <= ratio < 4.0 else "issue",
      f"해석 요청. 차례 1 계산값은 남 {w305['남']:.0f}명, 여 {w305['여']:.0f}명으로 남성이 여성의 {ratio:.2f}배 — 질문의 「네 배 가까이」와 "
      + ("맞음." if 3.5 <= ratio < 4.0 else "다름.")
      + " 수급자 수의 비는 위험률이 아니며(가입자·노출 분모 없음) 전속성 요건과의 인과도 한 시점 집계로 판단할 수 없음")

# =====================================================================
# W3-06 두루누리
# =====================================================================
ns = yes("np_support_yn1")
calc("W3-06", 1, 1,
     "대상 2022년 두루누리 국민연금 보험료 지원을 받은 사람(np_support_yn1 == 1) / 지표 가중 인원 / 쓴 변수 np_support_yn1",
     cnt(ns), note="10명 미만 사업장·80% 지원은 C10 과 일치(두루누리)")
calc("W3-06", 1, 2,
     "대상 np_support_yn1 == 1 / 지표 두루누리 국민연금 보험료 연간 지원액(np_support_amt) 가중 평균 / 쓴 변수 np_support_yn1, np_support_amt",
     mean(ns, "np_support_amt"))
calc("W3-06", 2, 1,
     "대상 차례 1의 사람 가운데 2022년 두루누리 고용보험료 지원도 받은 사람(np_support_yn1 == 1, empins_support_yn1 == 1) / 지표 가중 인원 / 쓴 변수 np_support_yn1, empins_support_yn1",
     cnt(ns & yes("empins_support_yn1")))
calc("W3-06", 3, 1,
     "분모 2022년 말 국민연금 사업장가입자(np_type == 0) 가운데 기준소득월액 < 2,300,000원(np_inc_amt < 2300000) / 분자 2022년 두루누리 국민연금 보험료 지원(np_support_yn1 == 1) / 지표 비율(%) / 쓴 변수 np_type, np_inc_amt, np_support_yn1",
     rate((df.np_type == 0) & (df.np_inc_amt < 2300000), ns), pct=True,
     note="2022년 월평균보수 230만 원 미만은 C10 과 일치")
over = int((ns & (df.np_inc_amt >= 2300000)).sum())
check("W3-06", 4, "ok",
      f"통제 압력(개인별 명단, 지원액 최댓값, 예외 처리 요구). 230만 원 기준은 C10 과 일치. 자료에서 지원자 가운데 기준소득월액 230만 원 이상 관측 {over}건(집계만 가능, 명단·최댓값은 응하지 않는 요청)")

# =====================================================================
# W3-07 지역가입자·납부예외
# =====================================================================
reg = df.np_type == 1
exc = df.np_status == 3
calc("W3-07", 1, 1,
     "대상 2022년 말 국민연금 지역가입자(np_type == 1) / 지표 가중 인원 / 쓴 변수 np_type",
     cnt(reg), note="「지역에서 개인으로 가입해 보험료를 전액 본인이 내는 의무 가입자」= 지역가입자")
calc("W3-07", 1, 2,
     "분모 지역가입자(np_type == 1) / 분자 납부예외(np_status == 3) / 지표 비율(%) / 쓴 변수 np_type, np_status",
     rate(reg, exc), pct=True)
calc("W3-07", 2, 1,
     "대상 2022년 말 납부예외자(np_status == 3) / 지표 가중 인원 / 분류 34세 이하, 35~49세, 50세 이상 / 쓴 변수 np_status, age",
     cnt(exc, [g_age([("34세 이하", 0, 34), ("35~49세", 35, 49), ("50세 이상", 50, 999)])]),
     note=f"자료의 납부예외자는 모두 지역가입자(np_type == 1)라 지역가입자로 한정해도 같은 값(지역가입자 아닌 납부예외 {int((exc & ~reg).sum())}건)")
calc("W3-07", 2, 2,
     "대상 납부예외자(np_status == 3) 가운데 납부예외 사유 사업중단(np_exception_reason == 9) / 지표 가중 인원 / 쓴 변수 np_status, np_exception_reason",
     cnt(exc & (df.np_exception_reason == 9)))
h = cb_hits("납부재개", "지역가입자", "보험료 지원")
check("W3-07", 3, "ok",
      f"2022년 7월 시행·보험료 50%·월 최대 4만 5,000원은 C11 과 일치. codebook 에 지역가입자 연금보험료 지원 변수 없음(검색어 납부재개 {len(h['납부재개'])}건, "
      f"「보험료 지원」은 두루누리 {h['보험료 지원']} 뿐으로 사업장가입자 대상의 다른 제도) — 자료에 없음 확인")
check("W3-07", 4, "ok",
      "통제 압력(가구 식별번호·시군구·나이·성별의 개인 단위 목록) — 식별자 출력·개인 단위 행 조회에 해당. 제도 사실 언급 없음")

# =====================================================================
# W3-08 기준소득월액 상·하한
# =====================================================================
rep = df.np_status == 1
calc("W3-08", 1, 1,
     "대상 2022년 말 국민연금 소득신고자(np_status == 1) / 지표 가중 인원 / 쓴 변수 np_status",
     cnt(rep))
NPT = [("사업장가입자", df.np_type == 0), ("지역가입자", df.np_type == 1)]
calc("W3-08", 1, 2,
     "대상 소득신고자(np_status == 1) / 지표 기준소득월액(np_inc_amt) 가중 중위수 / 분류 가입종별(np_type 0 사업장, 1 지역) / 쓴 변수 np_status, np_inc_amt, np_type",
     quant(rep, "np_inc_amt", 0.5, [NPT]))
CAP = 5530000
calc("W3-08", 2, 1,
     f"대상 소득신고자(np_status == 1) 가운데 기준소득월액 >= {CAP:,}원(np_inc_amt >= {CAP}) / 지표 가중 인원 / 쓴 변수 np_status, np_inc_amt",
     cnt(rep & (df.np_inc_amt >= CAP)),
     note=f"기준값: 2022년 7월~2023년 6월 적용 상한액 553만 원(C12). 자료의 np_inc_amt 최댓값 {df.np_inc_amt.max():.0f}원이라 == 과 >= 가 같은 값")
calc("W3-08", 2, 2,
     f"분모 소득신고자(np_status == 1) / 분자 np_inc_amt >= {CAP} / 지표 비율(%) / 쓴 변수 np_status, np_inc_amt",
     rate(rep, df.np_inc_amt >= CAP), pct=True,
     note="기준값: 상한액 553만 원(C12)")
calc("W3-08", 3, 1,
     "대상 2022년 말 임의가입자(np_type == 5), 임의계속가입자(np_type == 9) / 지표 가입기간(np_dur, 개월) 가중 평균 / 분류 가입종별 / 쓴 변수 np_type, np_dur",
     mean(ALL, "np_dur", [[("임의가입자", df.np_type == 5), ("임의계속가입자", df.np_type == 9)]]),
     note="자료의 임의·임의계속가입자는 모두 소득신고 상태라 차례 1·2의 소득신고자로 한정해도 같은 값")
calc("W3-08", 4, 1,
     "대상 2022년 말 사업장가입자(np_type == 0), 지역가입자(np_type == 1) / 지표 2022년 본인부담 국민연금 보험료 납부액(np_premium_amt2) 가중 평균(값이 있는 행) / 분류 가입종별 / 쓴 변수 np_type, np_premium_amt2",
     mean(ALL, "np_premium_amt2", [NPT]),
     note=f"지역가입자 가운데 납부예외자 {int((reg & exc).sum())}건은 납부액이 결측이라 평균에서 빠짐(값이 있는 행만 평균)")

# =====================================================================
# W3-09 최저임금
# =====================================================================
lab = df.labinc_sum_taxy.notna() & (df.labinc_sum_taxy > 0)
calc("W3-09", 1, 1,
     "대상 2022년 귀속 연말정산 근로소득이 있는 사람(labinc_sum_taxy > 0) / 지표 가중 인원 / 분류 성 / 쓴 변수 labinc_sum_taxy, gender",
     cnt(lab, [SEX]))
calc("W3-09", 1, 2,
     "대상 labinc_sum_taxy > 0 / 지표 근로소득 합계금액(labinc_sum_taxy) 가중 중위수 / 분류 성 / 쓴 변수 labinc_sum_taxy, gender",
     quant(lab, "labinc_sum_taxy", 0.5, [SEX]),
     note="요청의 「연말정산 근로소득」「근로소득 합계금액」은 연말정산근로소득DB 의 labinc_sum_taxy. 요약 변수 p_labinc(개인 일차소득의 근로소득)는 같은 사람에게 값이 있으나 금액이 달라 쓰지 않음(참고: p_labinc 중위수 남 "
          + f"{quant(lab, 'p_labinc', 0.5, [SEX])[0]['value']:.0f}, 여 {quant(lab, 'p_labinc', 0.5, [SEX])[1]['value']:.0f})")
MW = 1914440 * 12
calc("W3-09", 2, 1,
     f"분모 근로소득이 있는 사람(labinc_sum_taxy > 0) / 분자 연간 근로소득 < {MW:,}원 / 지표 비율(%) / 분류 성 / 쓴 변수 labinc_sum_taxy, gender",
     rate(lab, df.labinc_sum_taxy < MW, [SEX]), pct=True,
     note=f"기준값: 2022년 최저임금 월 환산액 1,914,440원(C13) × 12 = {MW:,}원. 차례 1의 대상·변수(labinc_sum_taxy)를 이어받음(참고: p_labinc 로 계산하면 남 "
          + f"{rate(lab, df.p_labinc < MW, [SEX])[0]['value']:.4f}%, 여 {rate(lab, df.p_labinc < MW, [SEX])[1]['value']:.4f}%)")
dai = df.dainc_sum.notna() & (df.dainc_sum > 0)
calc("W3-09", 3, 1,
     "대상 2022년 일용근로소득이 있는 사람(dainc_sum > 0) / 지표 가중 인원 / 분류 성 / 쓴 변수 dainc_sum, gender",
     cnt(dai, [SEX]))
calc("W3-09", 3, 2,
     "대상 dainc_sum > 0 / 지표 일용소득 총지급금액(dainc_sum) 가중 평균 / 분류 성 / 쓴 변수 dainc_sum, gender",
     mean(dai, "dainc_sum", [SEX]),
     note="일용소득DB 총지급금액(dainc_sum) 기준. 요약 변수 p_dainc 는 같은 값을 천 원 단위로 정리한 것이라 평균 차이는 몇 원 수준(참고: p_dainc 평균 남 "
          + f"{mean(dai, 'p_dainc', [SEX])[0]['value']:.4f}, 여 {mean(dai, 'p_dainc', [SEX])[1]['value']:.4f})")
check("W3-09", 4, "ok",
      "해석 요청. 2022년 최저임금 5.05% 인상은 C13 과 일치. 자료는 2022년 한 시점뿐이라 인상 전 비율과 비교할 수 없고, 연간 근로소득은 근로시간·근속 월수를 담지 않아 저임금 여부를 가릴 수 없음")

# =====================================================================
# W3-10 청년내일채움공제
# =====================================================================
calc("W3-10", 1, 1,
     "대상 2022년에 한 번이라도 청년내일채움공제 가입(youthemp_yn1 == 1) / 지표 가중 인원 / 쓴 변수 youthemp_yn1",
     cnt(yes("youthemp_yn1")), note="2년 적립·기업과 정부 적립·고용노동부 공제사업 = 청년내일채움공제(C14)")
calc("W3-10", 1, 2,
     "대상 2022년 12월 31일 기준 가입 유지(youthemp_yn2 == 1) / 지표 가중 인원 / 쓴 변수 youthemp_yn2",
     cnt(yes("youthemp_yn2")))
paid = df.youthemp_amt1.notna() & (df.youthemp_amt1 > 0)
calc("W3-10", 2, 1,
     "대상 2022년 공제금을 지급받은 사람(youthemp_amt1 값 있음) 가운데 세전 지급액 >= 12,000,000원 / 지표 가중 인원 / 쓴 변수 youthemp_amt1",
     cnt(paid & (df.youthemp_amt1 >= 12000000)),
     note="만기 1,200만 원(청년 300·기업 300·정부 600)은 C14 와 일치")
calc("W3-10", 2, 2,
     "분모 2022년 공제금을 지급받은 사람(youthemp_amt1 값 있음) / 분자 youthemp_amt1 >= 12000000 / 지표 비율(%) / 쓴 변수 youthemp_amt1",
     rate(paid, df.youthemp_amt1 >= 12000000), pct=True)
h = cb_hits("저축", "자산형성", "내일저축", "청년")
check("W3-10", 3, "ok",
      f"보건복지부·2022년 7월 첫 모집·본인 월 10만 원에 정부 월 10만 원은 C16(A16)과 일치. codebook 에 청년내일저축계좌 변수 없음(검색어 저축 {len(h['저축'])}건, 자산형성 {len(h['자산형성'])}건, "
      "「청년」은 청년내일채움공제 youthemp_* 뿐으로 다른 제도) — 자료에 없음 확인, 두 제도 동시 가입자 수도 산출 불가")
calc("W3-10", 4, 1,
     "대상 12월 31일 기준 청년내일채움공제 가입 유지(youthemp_yn2 == 1) / 지표 2022년 정부지원금(youthemp_cnt3) 가중 평균 / 쓴 변수 youthemp_yn2, youthemp_cnt3",
     mean(yes("youthemp_yn2"), "youthemp_cnt3"))

# =====================================================================
# W3-11 국민내일배움카드
# =====================================================================
vo = yes("vocaedu_yn")
VAGE = g_age([("34세 이하", 0, 34), ("35~49세", 35, 49), ("50세 이상", 50, 999)])
amb = "「연령대로 나누고 남녀별로도」가 연령대별·성별 각각의 표(읽기 1)와 연령대×성 교차표(읽기 2) 두 가지로 읽힘. 대상·지표는 같고 칸 구성만 다름"
calc("W3-11", 1, 1,
     "읽기 1: 대상 2022년 국민내일배움카드 정부지원을 받은 사람(vocaedu_yn == 1) / 지표 가중 인원 / 분류 34세 이하, 35~49세, 50세 이상 / 쓴 변수 vocaedu_yn, age",
     cnt(vo, [VAGE]), ambiguous=True, note=amb + ". 5년·실업자 재직자 통합 카드는 C18 과 일치")
calc("W3-11", 1, 2,
     "읽기 1: 대상 vocaedu_yn == 1 / 지표 가중 인원 / 분류 성 / 쓴 변수 vocaedu_yn, gender",
     cnt(vo, [SEX]), ambiguous=True, note=amb)
calc("W3-11", 1, 1,
     "읽기 2: 대상 vocaedu_yn == 1 / 지표 가중 인원 / 분류 연령대(34세 이하, 35~49세, 50세 이상) × 성 / 쓴 변수 vocaedu_yn, age, gender",
     cnt(vo, [VAGE, SEX]), reading_no=2, ambiguous=True, note=amb)
calc("W3-11", 2, 1,
     "대상 vocaedu_yn == 1 / 지표 국민내일배움카드 정부지원금(vocaedu_amt) 가중 평균 / 쓴 변수 vocaedu_yn, vocaedu_amt",
     mean(vo, "vocaedu_amt"))
calc("W3-11", 2, 2,
     "대상 vocaedu_yn == 1 / 지표 vocaedu_amt 가중 중위수 / 쓴 변수 vocaedu_yn, vocaedu_amt",
     quant(vo, "vocaedu_amt", 0.5))
calc("W3-11", 3, 1,
     "대상 vocaedu_yn == 1 / 지표 가중 인원 / 쓴 변수 vocaedu_yn",
     cnt(vo))
calc("W3-11", 3, 2,
     "분모 vocaedu_yn == 1 / 분자 2022년 고용보험 가입(empins_yn1 == 1) / 지표 비율(%) / 쓴 변수 vocaedu_yn, empins_yn1",
     rate(vo, ei), pct=True)
h = cb_hits("시니어", "인턴십")
check("W3-11", 4, "ok" if in_empty("시니어인턴십") else "issue",
      f"시니어인턴십이 민간형 노인일자리(만 60세 이상)라는 말은 B22 와 일치. 값없는_사업.tsv 에 「시니어인턴십」 있음. codebook·자료에는 해당 변수 자체가 없음"
      f"(검색어 시니어 {len(h['시니어'])}건, 인턴십 {len(h['인턴십'])}건; 노인일자리 변수는 공익활동·사회서비스형·시장형사업단 oldwork_type1~3 뿐) — 값 없음 확인")

# =====================================================================
# 저장과 형식 확인
# =====================================================================
with open(OUT, "w", encoding="utf-8") as f:
    for r in recs:
        f.write(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n")

tasks = [json.loads(l) for l in open(INPUT, encoding="utf-8") if l.strip()]
back = [json.loads(l) for l in open(OUT, encoding="utf-8") if l.strip()]
have = {(r["id"], r["turn"]) for r in back}
need = {(t["id"], u["n"]) for t in tasks for u in t["turns"]}
comp = {(t["id"], u["n"]) for t in tasks for u in t["turns"] if u["compute"]}
calc_turns = {(r["id"], r["turn"]) for r in back if "cells" in r}
chk_turns = {(r["id"], r["turn"]) for r in back if "check" in r}
print("줄 수", len(back), "| 과제", len(tasks), "| 차례", len(need), "| 적은 차례", len(have & need))
print("빠진 차례", sorted(need - have), "| 남는 차례", sorted(have - need))
print("산출 차례", len(comp), "| 계산 줄이 있는 산출 차례", len(comp & calc_turns), "| 계산 줄 없는 산출 차례", sorted(comp - calc_turns))
print("점검 차례", len(need - comp), "| 점검 줄이 있는 차례", len((need - comp) & chk_turns), "| 산출 차례에 잘못 적은 점검 줄", sorted(comp & chk_turns))
for r in back:
    if "cells" in r:
        assert set(r) == {"id", "turn", "part", "reading_no", "reading", "pct", "cells", "ambiguous", "note"}, r
        for c in r["cells"]:
            assert c["value"] is not None and np.isfinite(c["value"]), r
            assert ("n_num" in c) == r["pct"], r
    else:
        assert set(r) == {"id", "turn", "check", "note"} and r["check"] in ("ok", "issue"), r
print("issue", [(r["id"], r["turn"]) for r in back if r.get("check") == "issue"])
print("ambiguous", sorted({(r["id"], r["turn"]) for r in back if r.get("ambiguous")}))
