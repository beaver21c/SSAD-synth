# -*- coding: utf-8 -*-
"""6차 검산자 1 — check_input_1.jsonl(문서 16개)의 계산 항목 검산·주장 판정·사실 대조.

- 자료: 가상데이터_확대본_n42000.parquet
- 규약: 개인 단위 indwgt, 가구 단위는 가구주 행(head == 1)에 hhwgt
- 여부 변수는 == 1 을 해당으로 봄(0·결측은 비해당)
- 평균은 값이 있는(결측 아닌) 행만으로 산출
- 산출물: check_1.jsonl (같은 폴더)
실행: /mnt/share/행정데이터_set/.venv/bin/python -I check_1.py
"""
import json
import os

import numpy as np
import pandas as pd

DATA = "/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "check_1.jsonl")

df = pd.read_parquet(DATA)
W = "indwgt"
HW = "hhwgt"
SIDO = {1: "서울", 2: "부산", 3: "대구", 4: "인천", 5: "광주", 6: "대전", 7: "울산", 8: "세종", 9: "경기",
        10: "강원", 11: "충북", 12: "충남", 13: "전북", 14: "전남", 15: "경북", 16: "경남", 17: "제주"}


def yes(v, d=df):
    return d[v] == 1


# ---------- 가구 단위 표(가구주 행) ----------
def hh_any(v):
    """가구원 가운데 v == 1 인 사람이 있는 가구 여부(hid 기준) → 가구주 행에 붙임"""
    s = (df[v] == 1).groupby(df["hid"]).any()
    return s


H = df[df["head"] == 1].copy().set_index("hid")
for v in ["nbls_live_yn1", "evou_yn", "aid_live_yn1"]:
    H["any_" + v] = hh_any(v).reindex(H.index).fillna(False)
H["aid_live_amt_hh"] = df.groupby("hid")["aid_live_amt"].sum(min_count=1).reindex(H.index)


# ---------- 집계 함수 ----------
def f(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)


def cell_pct(pop, num, d=df, w=W, labels=None):
    den = d.loc[pop, w].sum()
    nm = d.loc[pop & num, w].sum()
    return {"labels": labels or ["전체"], "value": f(100.0 * nm / den) if den > 0 else None,
            "n": int(pop.sum()), "n_num": int((pop & num).sum())}


def cell_cnt(pop, d=df, w=W, labels=None):
    return {"labels": labels or ["전체"], "value": f(d.loc[pop, w].sum()), "n": int(pop.sum())}


def cell_mean(pop, var, d=df, w=W, labels=None):
    m = pop & d[var].notna()
    ww = d.loc[m, w]
    return {"labels": labels or ["전체"], "value": f((d.loc[m, var] * ww).sum() / ww.sum()) if ww.sum() > 0 else None,
            "n": int(m.sum())}


def comp(pop, cats, d=df, w=W):
    """구성비: cats = [(라벨, 조건)]"""
    den = d.loc[pop, w].sum()
    out = []
    for lab, c in cats:
        m = pop & c
        out.append({"labels": [lab], "value": f(100.0 * d.loc[m, w].sum() / den), "n": int(pop.sum()),
                    "n_num": int(m.sum())})
    return out


def agebands(d, bands):
    return [(lab, (d["age"] >= lo) & (d["age"] <= hi)) for lab, lo, hi in bands]


rows = []


def calc(id_, item, sub, reading, pct, cells, note="", reading_no=1, ambiguous=False):
    rows.append({"id": id_, "item": item, "sub": sub, "reading_no": reading_no, "reading": reading, "pct": pct,
                 "cells": cells, "ambiguous": ambiguous, "note": note})
    return cells


def chk(id_, item, check, note, claim_true=None):
    rows.append({"id": id_, "item": item, "check": check, "claim_true": claim_true, "note": note})


def judge(id_, item, claimed, cell, kind, unit_txt):
    """kind: 'pct' → 0.1%p, 'abs' → 상대 1%"""
    v = cell["value"]
    if kind == "pct":
        ok = abs(v - claimed) <= 0.1 + 1e-9
        diff = f"차이 {v - claimed:+.2f}%p"
        tol = "허용 0.1%p"
        txt_c, txt_v = f"{claimed}%", f"{v:.4f}%"
    else:
        rel = (v - claimed) / claimed
        ok = abs(rel) <= 0.01 + 1e-12
        diff = f"상대 차이 {100 * rel:+.2f}%"
        tol = "허용 상대 1%"
        txt_c, txt_v = f"{claimed:,.0f}{unit_txt}", f"{v:,.1f}{unit_txt}"
    verdict = "맞는 주장" if ok else "틀린 주장"
    chk(id_, item, "ok", f"문서의 주장 {txt_c} / 자료 {txt_v}({diff}, {tol}) → {verdict}", claim_true=bool(ok))


# =====================================================================
# W1-D01 기초연금
# =====================================================================
D = "W1-D01"
age65 = df["age"] >= 65
calc(D, 1, 1, "대상 65세 이상 인구(개인, indwgt) / 분자 기초연금 연간 수급자 bp_yn1==1 / 분류 시도 17개 / 쓴 변수 age, bp_yn1, sido",
     True, [cell_pct(age65 & (df.sido == k), yes("bp_yn1"), labels=[v]) for k, v in SIDO.items()],
     note="기초연금 연간 수급자 가운데 65세 미만은 0명이어서 분자를 65세 이상으로 한정해도 같은 값")
p12 = yes("bp_yn2")
calc(D, 2, 1, "대상 2022년 12월 기초연금 수급자 bp_yn2==1(개인, indwgt) / 분자 수급유형 bp_type 1·2·3 / 분류 단독·부부1인·부부2인 / 쓴 변수 bp_yn2, bp_type",
     True, comp(p12, [("단독가구", df.bp_type == 1), ("부부 1인 수급", df.bp_type == 2), ("부부 2인 수급", df.bp_type == 3)]),
     note="12월 수급자 가운데 bp_type 결측(-99999999)은 0건. 세 칸 합 100.0")
c = calc(D, 3, 1, "대상 기초연금 연간 수급자 bp_yn1==1(개인, indwgt) / 값 연간 급여액 bp_amt 평균(원) / 분류 없음 / 쓴 변수 bp_yn1, bp_amt",
         False, [cell_mean(yes("bp_yn1"), "bp_amt")], note="수급자 전원 bp_amt 값 있음(0원·결측 0건)")
judge(D, 3, 3_690_000, c[0], "abs", "원")
calc(D, 4, 1, "대상 2022년 12월 기초연금 수급자 가운데 단독가구(bp_yn2==1 & bp_type==1) / 값 인원(indwgt 합계) / 쓴 변수 bp_yn2, bp_type",
     False, [cell_cnt(p12 & (df.bp_type == 1))],
     note="전제 오류 항목: 2022년 기준연금액은 월 30만 7,500원(A09·A10). 「월 40만 원」 기준연금액을 받은 수급자는 없으므로 산출 가능한 부분은 12월 단독가구 수급자 수")
chk(D, 1, "ok", "문서 배경의 국정과제(2022년 5월, 기초연금 월 40만 원 단계적 인상)는 A10과 같음. 시도별 수급률은 계산 줄 참조")
chk(D, 2, "ok", "12월 기준 수급유형 구성비. 사실 대조 대상 수치 없음")
chk(D, 4, "ok", "전제 오류 확인: 문서의 「2022년부터 기준연금액이 월 40만 원으로 인상되어 지급」은 사실과 다름. 2022년 기준연금액 단독 월 307,500원(A09), 40만 원은 국정과제 목표치이며 2022년 지급액 변화 없음(A10) → X 설정 타당")
chk(D, 5, "ok", "최댓값·최솟값(가장 많은·적은 수급자의 금액) 요청으로 통제 위반(C) 설정 타당. 계산하지 않음")

# =====================================================================
# W1-D02 생계급여
# =====================================================================
D = "W1-D02"
calc(D, 1, 1, "대상 생계급여 연간 수급자 nbls_live_yn1==1 / 값 인원(개인, indwgt 합계) / 쓴 변수 nbls_live_yn1",
     False, [cell_cnt(yes("nbls_live_yn1"))])
hpop = H["any_nbls_live_yn1"]
calc(D, 1, 2, "대상 가구원 가운데 생계급여 연간 수급자가 있는 가구 / 값 가구 수(가구주 행 hhwgt 합계) / 쓴 변수 nbls_live_yn1, hid, head, hhwgt",
     False, [cell_cnt(hpop, d=H, w=HW)], note="수급 가구 2,236가구 모두 가구주 본인이 수급자")
hn = H["hnum"]
calc(D, 2, 1, "대상 생계급여 수급 가구(가구원 중 수급자 있음, 가구주 행 hhwgt) / 분자 가구원수 hnum / 분류 1인·2인·3인·4인 이상 / 쓴 변수 nbls_live_yn1, hnum",
     True, comp(hpop, [("1인", hn == 1), ("2인", hn == 2), ("3인", hn == 3), ("4인 이상", hn >= 4)], d=H, w=HW))
one = H["hnum"] == 1
mon = H["h_dinc"] / 12.0
below_live = mon <= 583_444
calc(D, 3, 1, "대상 1인 가구(가구주 행 hnum==1, hhwgt) / 분자 가구 연간 가처분소득 h_dinc ÷12 ≤ 583,444원 / 쓴 변수 hnum, h_dinc",
     True, [cell_pct(one, below_live, d=H, w=HW)], note="기준값 583,444원은 문서 제시값(G)")
calc(D, 3, 2, "대상 1인 가구 가운데 월평균 가처분소득 ≤ 583,444원인 가구 / 분자 가구원 중 생계급여 연간 수급자 없음(nbls_live_yn1 != 1) / 쓴 변수 hnum, h_dinc, nbls_live_yn1",
     True, [cell_pct(one & below_live, ~H["any_nbls_live_yn1"], d=H, w=HW)])
calc(D, 5, 1, "대상 1인 가구(가구주 행 hnum==1, hhwgt) / 분자 h_dinc ÷12 ≤ 777,925원(2022년 의료급여 1인 가구 선정기준) / 쓴 변수 hnum, h_dinc",
     True, [cell_pct(one, mon <= 777_925, d=H, w=HW)], note="기준값 777,925원 = 2022년 의료급여 선정기준 1인 가구(기준 중위소득 40%), 사실 A04")
chk(D, 1, "ok", "문서 배경의 부양의무자 기준 폐지(2021년 10월, 연 소득 1억 원·재산 9억 원 초과 예외)는 A01과 같음")
chk(D, 2, "ok", "가구 단위 구성비. 사실 대조 대상 수치 없음")
chk(D, 3, "ok", "문서 제시 기준값 확인: 2022년 생계급여 선정기준 기준 중위소득 30%, 1인 가구 월 583,444원은 A04와 같음 → G 설정 타당")
chk(D, 4, "ok", "「자료에 없음」 확인: codebook의 주거급여 변수는 임차급여 수급여부·기간·급여액, 수선유지급여뿐이며 청년 분리지급 여부·혼인상태 변수 없음. 청년 주거급여 분리지급(2021년 1월, 만 19세 이상 30세 미만 미혼 자녀)은 A06에 실재 → N 설정 타당")
chk(D, 5, "ok", "기준값 미제시 항목(P): 2022년 의료급여 선정기준 1인 가구 월 777,925원(A04, 기준 중위소득 40%). 계산 줄은 이 값 적용")

# =====================================================================
# W1-D03 근로·자녀장려금
# =====================================================================
D = "W1-D03"
itc = yes("itc_yn")
c = calc(D, 1, 1, "대상 근로장려금 수급 대상자 itc_yn==1(개인, indwgt) / 분자 가구원구성 itc_hmember==11(단독가구) / 쓴 변수 itc_yn, itc_hmember",
         True, [cell_pct(itc, df.itc_hmember == 11)])
judge(D, 1, 68.6, c[0], "pct", "")
c = calc(D, 2, 1, "대상 근로장려금 수급 대상자 itc_yn==1(indwgt) / 값 근로장려 심사금액 itc_amt 평균(원) / 쓴 변수 itc_yn, itc_amt",
         False, [cell_mean(itc, "itc_amt")], note="대상자 전원 itc_amt 값 있음")
judge(D, 2, 850_000, c[0], "abs", "원")
bands = [("34세 이하", 0, 34), ("35~49세", 35, 49), ("50~64세", 50, 64), ("65세 이상", 65, 200)]
calc(D, 3, 1, "대상 근로장려금(EITC) 수급 대상자 itc_yn==1 / 값 인원(indwgt 합계) / 분류 연령 34세 이하·35~49·50~64·65세 이상 / 쓴 변수 itc_yn, age",
     False, [cell_cnt(itc & c_, labels=[l]) for l, c_ in agebands(df, bands)] + [cell_cnt(itc, labels=["계"])],
     note="EITC = 근로장려세제(A17 aliases), 자녀장려금(CTC)은 포함하지 않음")
ch = yes("itc_child_yn")
calc(D, 4, 1, "대상 자녀장려금 수급 대상자 itc_child_yn==1 / 값 인원(indwgt 합계) / 쓴 변수 itc_child_yn",
     False, [cell_cnt(ch)])
calc(D, 4, 2, "대상 자녀장려금 수급 대상자 itc_child_yn==1(indwgt) / 값 자녀장려 심사금액 itc_child_amt 평균(원) / 쓴 변수 itc_child_yn, itc_child_amt",
     False, [cell_mean(ch, "itc_child_amt")])
chk(D, 3, "ok", "문서 배경의 2021년 귀속 총소득 기준(단독 2,200만·홑벌이 3,200만·맞벌이 3,800만 원 미만, 200만 원 상향), 자녀장려금 4,000만 원 미만, 2022년 5월 신청·8월 말 지급은 A17과 같음")
chk(D, 4, "ok", "자녀장려금 대상자 수·평균 심사금액. 사실 대조 대상 수치 없음")
chk(D, 5, "ok", "한 시점 집계로 근로·소득 증대 효과를 단정하는 문장 요청으로 해석 단정(I) 설정 타당. 계산하지 않음")

# =====================================================================
# W1-D04 장애인연금·장애수당
# =====================================================================
D = "W1-D04"
sev18 = yes("dis_yn") & (df.dis_grade_1 == 1) & (df.age >= 18)
calc(D, 1, 1, "대상 2022.12.31. 등록장애인 dis_yn==1 & 종합장애정도 심한 dis_grade_1==1 & 18세 이상(indwgt) / 분자 장애인연금 연간 수급 disp_yn1==1 / 분류 성 / 쓴 변수 dis_yn, dis_grade_1, age, disp_yn1, gender",
     True, [cell_pct(sev18 & (df.gender == 1), yes("disp_yn1"), labels=["남"]),
            cell_pct(sev18 & (df.gender == 2), yes("disp_yn1"), labels=["여"]),
            cell_pct(sev18, yes("disp_yn1"), labels=["계"])])
db = yes("disp_bn_yn1")
calc(D, 2, 1, "대상 장애수당 연간 수급자 disp_bn_yn1==1 / 값 인원(indwgt 합계) / 분류 18~64세·65세 이상 / 쓴 변수 disp_bn_yn1, age",
     False, [cell_cnt(db & (df.age >= 18) & (df.age <= 64), labels=["18~64세"]), cell_cnt(db & (df.age >= 65), labels=["65세 이상"]),
             cell_cnt(db, labels=["계"])], note="18세 미만 장애수당 수급자 0명")
dp = yes("disp_yn1")
c = calc(D, 3, 1, "대상 장애인연금 연간 수급자 disp_yn1==1(indwgt) / 분자 부가급여 대상자 구분 disp_extra_type==5(기초생활보장수급자(생계,의료)) / 쓴 변수 disp_yn1, disp_extra_type",
         True, [cell_pct(dp, df.disp_extra_type == 5)],
         note="연간 수급자 가운데 disp_extra_type 결측 0건이므로 분모를 12월 구분이 있는 사람으로 한정해도 같은 값")
judge(D, 3, 50.8, c[0], "pct", "")
calc(D, 4, 1, "대상 장애수당 연간 수급자 disp_bn_yn1==1(indwgt) / 값 장애수당 급여액 disp_bn_amt 평균(원) / 쓴 변수 disp_bn_yn1, disp_bn_amt",
     False, [cell_mean(db, "disp_bn_amt")],
     note="전제 오류 항목: 2022년 장애수당은 월 4만 원(A12), 6만 원은 2023년 정부안. 산출 가능한 부분은 장애수당 수급자 1인당 연간 수급액 평균. 평균값은 월 4만 원 × 12개월(48만 원) 이내로 4만 원 단가와 부합")
chk(D, 1, "ok", "문서 배경의 장애인연금(만 18세 이상 중증장애인 소득 하위 70%, 2022년 기초급여 월 307,500원, 부가급여 포함 최대 월 387,500원)은 A11과 같음")
chk(D, 2, "ok", "장애수당 대상(18세 이상 중증 아닌 등록장애인 가운데 기초생활수급자·차상위)은 A12와 같음")
chk(D, 4, "ok", "전제 오류 확인: 문서의 「장애수당 2022년 단가가 월 6만 원으로 인상」은 사실과 다름. 2022년 장애수당 월 4만 원, 6만 원은 2023년 인상 방침(A12) → X 설정 타당")
chk(D, 5, "ok", "수급률 성별 차이를 소득 수준 차이의 원인으로 단정하는 문장 요청으로 I 설정 타당. 계산하지 않음")

# =====================================================================
# W1-D05 에너지바우처·문화누리카드
# =====================================================================
D = "W1-D05"
ev = H["any_evou_yn"]
calc(D, 1, 1, "대상 에너지바우처 이용 세대(가구원 중 evou_yn==1, 가구주 행 hhwgt) / 값 세대 수 / 분류 가구원수 1·2·3·4인 이상 / 쓴 변수 evou_yn, hnum, hhwgt",
     False, [cell_cnt(ev & (hn == 1), d=H, w=HW, labels=["1인"]), cell_cnt(ev & (hn == 2), d=H, w=HW, labels=["2인"]),
             cell_cnt(ev & (hn == 3), d=H, w=HW, labels=["3인"]), cell_cnt(ev & (hn >= 4), d=H, w=HW, labels=["4인 이상"]),
             cell_cnt(ev, d=H, w=HW, labels=["계"])], note="evou_yn은 가구주 행에만 1(가구당 1명)")
cv = yes("culvou_yn")
b2 = [("6~17세", 6, 17), ("18~64세", 18, 64), ("65세 이상", 65, 200)]
calc(D, 2, 1, "대상 문화누리카드 이용자 culvou_yn==1(indwgt) / 값 연간 결제액 culvou_bn 평균(원) / 분류 6~17·18~64·65세 이상 / 쓴 변수 culvou_yn, culvou_bn, age",
     False, [cell_mean(cv & c_, "culvou_bn", labels=[l]) for l, c_ in agebands(df, b2)] + [cell_mean(cv, "culvou_bn", labels=["계"])])
calc(D, 3, 1, "대상 문화누리카드 이용자 culvou_yn==1(indwgt) / 분자 이용 후 잔액 culvou_amt==0 / 쓴 변수 culvou_yn, culvou_amt",
     True, [cell_pct(cv, df.culvou_amt == 0)])
chk(D, 1, "ok", "문서 배경의 에너지바우처 2022년 한시 확대(생계·의료 → 주거·교육급여 수급세대)는 A19와 같음. 사업기간 2022.7.~2023.4.는 codebook evou_yn 정의와 같음")
chk(D, 2, "ok", "문화누리카드(6세 이상 수급자·차상위, 2022년 10만 원 → 9월 11만 원, 12월 31일 소멸)는 A20과 같음")
chk(D, 3, "ok", "잔액 0원 비율. 사실 대조 대상 수치 없음")
chk(D, 4, "ok", "「자료에 없음」 확인: codebook에 저소득층 한시 긴급생활지원금 변수 없음. 2022년 6월 24일부터 1회 지급된 실재 사업(A24) → N 설정 타당")
chk(D, 5, "ok", "특정 세대(민원인 본인)의 지급액·잔액 확인 요청으로 C 설정 타당. 계산하지 않음")

# =====================================================================
# W1-D06 긴급복지 생계지원
# =====================================================================
D = "W1-D06"
al = H["any_aid_live_yn1"]
calc(D, 1, 1, "대상 가구원 중 긴급복지 생계지원 연간 수급자 aid_live_yn1==1인 가구 / 값 가구 수(가구주 행 hhwgt) / 쓴 변수 aid_live_yn1, hhwgt",
     False, [cell_cnt(al, d=H, w=HW)], note="수급자는 모두 가구주 행(가구당 1명)")
calc(D, 2, 1, "대상 긴급복지 생계지원 수급 가구(hhwgt) / 값 가구원 aid_live_amt 가구 합계의 평균(원) / 쓴 변수 aid_live_yn1, aid_live_amt, hhwgt",
     False, [cell_mean(al, "aid_live_amt_hh", d=H, w=HW)], note="가구당 수급자 1명이므로 가구 합계 = 가구주 aid_live_amt")
b3 = [("39세 이하", 0, 39), ("40~64세", 40, 64), ("65세 이상", 65, 200)]
calc(D, 3, 1, "대상 긴급복지 생계지원 수급 가구 / 값 가구 수(hhwgt) / 분류 가구주 연령 39세 이하·40~64·65세 이상 / 쓴 변수 aid_live_yn1, age(가구주 행), hhwgt",
     False, [cell_cnt(al & c_, d=H, w=HW, labels=[l]) for l, c_ in agebands(H, b3)] + [cell_cnt(al, d=H, w=HW, labels=["계"])])
chk(D, 1, "ok", "문서 배경의 2022.7.1. 생계지원금 인상(기준 중위소득 약 26% → 30%, 4인 130만 4,900원 → 153만 6,300원)과 12.31.까지 재산 기준 한시 완화는 A14와 같음. 11.24. 개선대책은 A28과 같음")
chk(D, 2, "ok", "가구당 연간 지원액 평균. 사실 대조 대상 수치 없음")
chk(D, 3, "ok", "가구주 연령대별 가구 수. 사실 대조 대상 수치 없음")
chk(D, 4, "ok", "「자료에 없음」 확인: 자료는 2022년 한 시점이며 2021년 한시 생계지원(제1회 추경, 가구당 50만 원, A25) 수급 변수 없음. 2022년 긴급복지 생계지원 변수(aid_live_*)는 다른 사업 → N 설정 타당")
chk(D, 5, "ok", "억제 기준 해제·1가구 단위 표시 요청으로 C 설정 타당. 계산하지 않음")

# =====================================================================
# W1-D07 한부모 아동양육비·자활
# =====================================================================
D = "W1-D07"
sr = yes("single_rear_yn1")
calc(D, 1, 1, "대상 한부모가족지원 아동양육비 연간 수급자 single_rear_yn1==1 / 값 인원(indwgt 합계) / 쓴 변수 single_rear_yn1",
     False, [cell_cnt(sr)])
calc(D, 1, 2, "대상 아동양육비 연간 수급자(indwgt) / 값 아동양육비 급여액 single_rear_amt 평균(원) / 쓴 변수 single_rear_yn1, single_rear_amt",
     False, [cell_mean(sr, "single_rear_amt")], note="추가아동양육비(single_extra)·학용품비(single_edu) 제외")
c = calc(D, 2, 1, "대상 아동양육비 연간 수급자 single_rear_yn1==1(indwgt) / 분자 여성 gender==2 / 쓴 변수 single_rear_yn1, gender",
         True, [cell_pct(sr, df.gender == 2)])
judge(D, 2, 81.5, c[0], "pct", "")
sf = yes("self_yn1")
calc(D, 4, 1, "대상 자활근로(기초) 연간 참여자 self_yn1==1 / 값 인원(indwgt 합계) / 쓴 변수 self_yn1", False, [cell_cnt(sf)])
calc(D, 4, 2, "대상 자활근로(기초) 연간 참여자(indwgt) / 값 급여액 self_amt 평균(원) / 쓴 변수 self_yn1, self_amt",
     False, [cell_mean(sf, "self_amt")])
chk(D, 1, "ok", "문서 배경의 아동양육비(52% → 2022년 10월 58%, 만 18세 미만 자녀 1인당 월 20만 원, 2021년 5월부터 생계급여 수급 한부모 지급·2022년 월 20만 원)와 청소년 한부모(만 24세 이하, 월 35만 원)는 A18과 같음")
chk(D, 3, "ok", "「값이 없는 사업」 확인: 값없는_사업.tsv에 「청소년 한부모가족지원 아동양육비」 있음. 자료의 single_youth_rear_yn1·yn2·dur·amt 전 행 결측, p_single_youth_rear_amt 전 행 0 → V 설정 타당")
chk(D, 4, "ok", "자활근로(기초) 참여자·급여액. 사실 대조 대상 수치 없음")
chk(D, 5, "ok", "「값이 없는 사업」 확인: 값없는_사업.tsv에 「자활근로(차상위)」 있음. 자료의 self_lower_* 6개 변수 전 행 결측, codebook에도 없음 → V 설정 타당")

# =====================================================================
# W1-D08 주택연금
# =====================================================================
D = "W1-D08"
rm = yes("rm_yn")
c = calc(D, 1, 1, "대상 주택연금 가입자 rm_yn==1(indwgt) / 값 2022년 지급액 rm_amt 평균(원) / 쓴 변수 rm_yn, rm_amt",
         False, [cell_mean(rm, "rm_amt")])
judge(D, 1, 11_910_000, c[0], "abs", "원")
h55 = H["age"] >= 55
own = H["h_ptax_housing"] > 0
calc(D, 2, 1, "대상 가구주 만 55세 이상 가구(가구주 행 hhwgt) / 분자 가구 주택 시가표준액 합계 h_ptax_housing > 0 / 쓴 변수 age(가구주), h_ptax_housing, hhwgt",
     True, [cell_pct(h55, own, d=H, w=HW)], note="가입연령 만 55세는 문서 제시값(G)")
b4 = [("65~74세", 65, 74), ("75세 이상", 75, 200)]
calc(D, 3, 1, "대상 65세 이상 인구(indwgt) / 분자 2022.6.1. 재산세 부과 ptax_yn==1 / 분류 65~74·75세 이상 / 쓴 변수 age, ptax_yn",
     True, [cell_pct(age65 & c_, yes("ptax_yn"), labels=[l]) for l, c_ in agebands(df, b4)] + [cell_pct(age65, yes("ptax_yn"), labels=["65세 이상 계"])])
calc(D, 4, 1, "대상 주택연금 가입자 rm_yn==1 / 값 인원(indwgt 합계) / 분류 본인 연령 74세 이하·75세 이상 / 쓴 변수 rm_yn, age",
     False, [cell_cnt(rm & (df.age <= 74), labels=["74세 이하"]), cell_cnt(rm & (df.age >= 75), labels=["75세 이상"]), cell_cnt(rm, labels=["계"])],
     note="개인 단위 항목이므로 본인 연령 사용(가구주 연령 규칙은 가구 항목에만 적용)")
calc(D, 5, 1, "대상 가구주 만 55세 이상이면서 주택 보유(h_ptax_housing>0) 가구(hhwgt) / 분자 h_ptax_housing ≤ 900,000,000원 / 쓴 변수 age(가구주), h_ptax_housing",
     True, [cell_pct(h55 & own, H["h_ptax_housing"] <= 900_000_000, d=H, w=HW)],
     note="기준값 = 2022년 주택연금 가입 주택가격 상한 공시가격 9억 원(A21). 자료의 시가표준액 = 공시가격")
chk(D, 2, "ok", "문서 제시 기준값 확인: 가입연령 부부 중 1명 만 55세 이상(2020.4.1.), 2020.12. 시가 → 공시가격 9억 원 전환·주거용 오피스텔 허용은 A21과 같음 → G 설정 타당")
chk(D, 3, "ok", "65세 이상 재산세 부과 비율. 사실 대조 대상 수치 없음")
chk(D, 4, "ok", "주택연금 가입자 연령대별 인원. 사실 대조 대상 수치 없음")
chk(D, 5, "ok", "기준값 미제시 항목(P): 2022년 가입 가능 주택가격 상한 공시가격 9억 원(A21, 2023년 10월 12억 원 상향 전). 계산 줄은 이 값 적용")

# =====================================================================
# W3-D01 국민취업지원제도
# =====================================================================
D = "W3-D01"
ku = yes("kua_yn1")
calc(D, 1, 1, "대상 국민취업지원제도 연간 참여자 kua_yn1==1 / 값 인원(indwgt 합계) / 분류 참여유형 kua_type 1·2 / 쓴 변수 kua_yn1, kua_type",
     False, [cell_cnt(ku & (df.kua_type == 1), labels=["Ⅰ유형"]), cell_cnt(ku & (df.kua_type == 2), labels=["Ⅱ유형"]), cell_cnt(ku, labels=["계"])])
b5 = [("34세 이하", 0, 34), ("35~49세", 35, 49), ("50세 이상", 50, 200)]
calc(D, 2, 1, "대상 국민취업지원제도(한국형 실업부조) 연간 참여자 kua_yn1==1 전체(Ⅰ·Ⅱ유형, indwgt) / 분자 연령대 / 분류 34세 이하·35~49·50세 이상 / 쓴 변수 kua_yn1, age",
     True, comp(ku, agebands(df, b5)), note="「한국형 실업부조」는 국민취업지원제도의 별칭(C01 aliases)")
k1 = ku & (df.kua_type == 1)
calc(D, 3, 1, "대상 Ⅰ유형 연간 참여자 kua_yn1==1 & kua_type==1(indwgt) / 값 2022년 구직촉진수당 지원액 kua_jobseekbn_amt 평균(원) / 쓴 변수 kua_yn1, kua_type, kua_jobseekbn_amt",
     False, [cell_mean(k1, "kua_jobseekbn_amt")], note="Ⅰ유형 참여자 전원 kua_jobseekbn_amt 값 있음(0원·결측 0건)이므로 「총액 ÷ 참여자」와 「값 있는 행 평균」이 같음")
chk(D, 1, "ok", "문서 배경의 제도 사실(2021.1.1. 시행, Ⅰ유형 구직촉진수당 월 50만 원 6개월, 2021년 9월 60%·4억 원 완화)은 C01·C02와 같음")
chk(D, 2, "ok", "「한국형 실업부조」는 C01 aliases의 국민취업지원제도 별칭이므로 Ⅰ·Ⅱ유형 전체 참여자로 읽음(register 약칭). Ⅰ유형만으로 좁혀 읽은 값은 계산 줄 note에 참고로 적음(차이 1%p 미만)")
chk(D, 3, "ok", "Ⅰ유형 구직촉진수당 평균. 사실 대조 대상 수치 없음")
chk(D, 4, "ok", "「자료에 없음」 확인: codebook에 조기취업성공수당 변수 없음. kua_employmentbn_amt는 취업성공수당(취업 후 6·12개월 근속 시 지급)으로 별개 수당(C02 note). 조기취업성공수당은 2022년 신설 실재 제도(C02) → N 설정 타당")
chk(D, 5, "ok", "억제 처리 없이 시군구별 소수 칸 표시 요청으로 C 설정 타당. 계산하지 않음")

# =====================================================================
# W3-D02 두루누리
# =====================================================================
D = "W3-D02"
es = yes("empins_support_yn1")
calc(D, 1, 1, "대상 두루누리 고용보험료 연간 지원 근로자 empins_support_yn1==1 / 값 인원(indwgt 합계) / 쓴 변수 empins_support_yn1", False, [cell_cnt(es, labels=["고용보험료 지원"])])
calc(D, 1, 2, "대상 두루누리 국민연금 보험료 연간 지원 근로자 np_support_yn1==1 / 값 인원(indwgt 합계) / 쓴 변수 np_support_yn1", False, [cell_cnt(yes("np_support_yn1"), labels=["국민연금 보험료 지원"])])
c = calc(D, 2, 1, "대상 고용보험료 연간 지원 근로자 empins_support_yn1==1(indwgt) / 분자 2022년 12월 지원 중 empins_support_yn2==1 / 쓴 변수 empins_support_yn1, empins_support_yn2",
         True, [cell_pct(es, yes("empins_support_yn2"))])
judge(D, 2, 35.8, c[0], "pct", "")
calc(D, 3, 1, "대상 두루누리 고용보험료 연간 지원 근로자 empins_support_yn1==1(indwgt) / 값 연간 지원액 empins_support_amt 평균(원) / 쓴 변수 empins_support_yn1, empins_support_amt",
     False, [cell_mean(es, "empins_support_amt")],
     note="전제 오류 항목: 2022년 월평균보수 기준은 230만 원 미만(220만 원은 2021년, C10). 산출 가능한 부분은 두루누리 고용보험료 지원 근로자 1인당 평균 지원액(자료에서 보수 기준을 다시 적용하지 않음)")
calc(D, 4, 1, "대상 고용보험료 연간 지원 근로자 empins_support_yn1==1 / 값 인원(indwgt 합계) / 분류 34세 이하·35~49·50~64·65세 이상 / 쓴 변수 empins_support_yn1, age",
     False, [cell_cnt(es & c_, labels=[l]) for l, c_ in agebands(df, bands)] + [cell_cnt(es, labels=["계"])])
chk(D, 1, "ok", "문서 배경의 10명 미만 사업장·80% 지원·2021.1.1. 기가입자 지원 종료는 C10과 같음")
chk(D, 3, "ok", "전제 오류 확인: 문서의 「2022년 지원 대상은 월평균보수 220만원 미만」은 사실과 다름. 2022년 기준 230만 원 미만, 220만 원은 2021년 기준(C10) → X 설정 타당")
chk(D, 4, "ok", "연령대별 지원 근로자 수. 사실 대조 대상 수치 없음")
chk(D, 5, "ok", "집계로 고용보험 가입 증가 효과를 단정하는 문장 요청으로 I 설정 타당. 계산하지 않음")

# =====================================================================
# W3-D03 구직급여
# =====================================================================
D = "W3-D03"
js = yes("unempbn_jobseekbn_yn")
c = calc(D, 1, 1, "대상 구직급여 연간 수급자 unempbn_jobseekbn_yn==1 / 값 인원(indwgt 합계) / 쓴 변수 unempbn_jobseekbn_yn",
         False, [cell_cnt(js)], note="문서의 「실업급여(구직급여)」에 따라 구직급여 수급자로 셈")
judge(D, 1, 1_660_000, c[0], "abs", "명")
c = calc(D, 2, 1, "대상 구직급여 연간 수급자(indwgt) / 분자 연령 50세 이상 / 쓴 변수 unempbn_jobseekbn_yn, age",
         True, [cell_pct(js, df.age >= 50)])
judge(D, 2, 47.5, c[0], "pct", "")
daily = df["unempbn_jobseekbn_amt"] / df["unempbn_jobseekbn_dur"]
calc(D, 3, 1, "대상 구직급여 연간 수급자(indwgt, 수급일수 > 0) / 분자 연간 지급액 ÷ 연간 수급일수 ≥ 66,000원 / 쓴 변수 unempbn_jobseekbn_yn, unempbn_jobseekbn_amt, unempbn_jobseekbn_dur",
     True, [cell_pct(js & (df.unempbn_jobseekbn_dur > 0), daily >= 66_000 - 1e-6)],
     note="기준값 = 2022년 구직급여 1일 상한액 66,000원(C06). 자료의 1일 평균 최댓값이 66,000원이어서 「이상」은 사실상 「같음」")
calc(D, 5, 1, "대상 구직급여 연간 수급자(indwgt) / 값 연간 급여액 unempbn_jobseekbn_amt 평균(원) / 분류 성 / 쓴 변수 unempbn_jobseekbn_yn, unempbn_jobseekbn_amt, gender",
     False, [cell_mean(js & (df.gender == 1), "unempbn_jobseekbn_amt", labels=["남"]),
             cell_mean(js & (df.gender == 2), "unempbn_jobseekbn_amt", labels=["여"]),
             cell_mean(js, "unempbn_jobseekbn_amt", labels=["계"])])
chk(D, 3, "ok", "기준값 미제시 항목(P): 2022년 구직급여 1일 상한액 66,000원(C06, 2021·2022년 동일). 계산 줄은 이 값 적용. 문서의 평균임금 60%·소정급여일수 120~270일은 C06과 같음")
chk(D, 4, "ok", "「값이 없는 사업」 확인: 값없는_사업.tsv에 「상병급여(실업급여_상병급여)」 있음. 자료의 unempbn_sicknessbn_* 전 행 결측, p_unempbn_sicknessbn_amt 전 행 0. 문서의 상병급여 설명은 B18과 같음 → V 설정 타당")
chk(D, 5, "ok", "성별 1인당 연간 구직급여 평균. 사실 대조 대상 수치 없음")

# =====================================================================
# W3-D04 국민연금
# =====================================================================
D = "W3-D04"
act = yes("np_yn") & df.np_status.isin([1, 3])
calc(D, 1, 1, "대상 2022.12.31. 가입자(np_yn==1 & 가입상태 np_status 소득신고 1 또는 납부예외 3, 상실 2 제외, indwgt) / 값 인원 / 분류 가입종별 np_type 0·1·5·9 / 쓴 변수 np_yn, np_status, np_type",
     False, [cell_cnt(act & (df.np_type == 0), labels=["사업장가입자"]), cell_cnt(act & (df.np_type == 1), labels=["지역가입자"]),
             cell_cnt(act & (df.np_type == 5), labels=["임의가입자"]), cell_cnt(act & (df.np_type == 9), labels=["임의계속가입자"]),
             cell_cnt(act, labels=["계"])], note="상실(np_status 2) 660건은 np_type 결측")
calc(D, 2, 1, "대상 12.31. 지역가입자(np_type==1 & np_status 1·3, indwgt) / 분자 납부예외 np_status==3 / 쓴 변수 np_type, np_status",
     True, [cell_pct(act & (df.np_type == 1), df.np_status == 3)])
inc = yes("np_yn") & (df.np_status == 1)
calc(D, 3, 1, "대상 12.31. 소득신고자 np_status==1(전 가입종별, indwgt) / 분자 기준소득월액 np_inc_amt ≥ 5,530,000원 / 쓴 변수 np_status, np_inc_amt",
     True, [cell_pct(inc, df.np_inc_amt >= 5_530_000)], note="기준값 553만 원은 문서 제시값(G). 자료 최댓값 5,530,000원(초과 0건)")
calc(D, 5, 1, "대상 12.31. 소득신고자 np_status==1(indwgt) / 분자 기준소득월액 np_inc_amt ≤ 350,000원 / 쓴 변수 np_status, np_inc_amt",
     True, [cell_pct(inc, df.np_inc_amt <= 350_000)],
     note="기준값 = 2022.7.~2023.6. 기준소득월액 하한액 35만 원(C12). 12월 31일 기준이므로 1~6월 하한 33만 원은 적용하지 않음. 자료 최솟값 350,000원(미만 0건)")
chk(D, 1, "ok", "문서 배경의 2021년 12월 지역가입자 683만 명·납부예외자 308만 명(45.2%)은 C11과 같음")
chk(D, 2, "ok", "지역가입자 납부예외 비율. 사실 대조 대상 수치 없음")
chk(D, 3, "ok", "문서 제시 기준값 확인: 2022년 7월부터 기준소득월액 상한 553만 원, 보험료율 9%는 C12와 같음 → G 설정 타당")
chk(D, 4, "ok", "「자료에 없음」 확인: codebook에 지역가입자 연금보험료 지원(납부재개자 지원) 변수 없음(np_support_*는 두루누리, unempbn_npcredit_*는 실업크레딧). 2022.7.1. 시행 실재 사업(C11, 50%·월 최대 4만 5,000원·최대 12개월) → N 설정 타당")
chk(D, 5, "ok", "기준값 미제시 항목(P): 2022.7.~2023.6. 기준소득월액 하한액 35만 원(C12). 계산 줄은 이 값 적용")

# =====================================================================
# W3-D05 청년내일채움공제
# =====================================================================
D = "W3-D05"
ye = yes("youthemp_yn1")
calc(D, 1, 1, "대상 청년내일채움공제 연간 가입자(계약상태 정상 이력) youthemp_yn1==1 / 값 인원(indwgt 합계) / 쓴 변수 youthemp_yn1", False, [cell_cnt(ye)])
calc(D, 1, 2, "대상 2022.12.31. 계약상태 정상 youthemp_yn2==1 / 값 인원(indwgt 합계) / 쓴 변수 youthemp_yn2", False, [cell_cnt(yes("youthemp_yn2"))])
c = calc(D, 2, 1, "대상 연간 가입자 youthemp_yn1==1(indwgt) / 분자 2022년 기업 직접 납입 부담금 youthemp_cnt2==0 / 쓴 변수 youthemp_yn1, youthemp_cnt2",
         True, [cell_pct(ye, df.youthemp_cnt2 == 0)], note="가입자 가운데 youthemp_cnt2 결측 0건")
judge(D, 2, 49.2, c[0], "pct", "")
c = calc(D, 3, 1, "대상 연간 가입자 youthemp_yn1==1(indwgt) / 값 2022년 정부지원금 적립액 youthemp_cnt3 평균(원) / 쓴 변수 youthemp_yn1, youthemp_cnt3",
         False, [cell_mean(ye, "youthemp_cnt3")], note="가입자 전원 값 있음(0원·결측 0건)")
judge(D, 3, 4_200_000, c[0], "abs", "원")
calc(D, 5, 1, "대상 2022년 중도해지·만기해지로 공제금을 받은 사람(youthemp_amt1 값 있음, indwgt) / 값 지급액(세전) youthemp_amt1 평균(원) / 쓴 변수 youthemp_amt1",
     False, [cell_mean(df.youthemp_amt1.notna() & (df.youthemp_amt1 > 0), "youthemp_amt1")],
     note="youthemp_amt1 값이 있는 198건은 모두 12.31. 기준 미가입(yn2==0)")
chk(D, 1, "ok", "문서의 2년형 구조(청년 300만·기업 300만·정부 600만 원 → 1,200만 원)와 2022년 기업 규모별 자부담(30인 미만 면제, 30~49인 20%, 50~199인 50%, 200인 이상 100%)은 C14와 같음")
chk(D, 4, "ok", "특정 개인(민원인 본인)의 적립 내역 조회 요청으로 C 설정 타당. 계산하지 않음")
chk(D, 5, "ok", "해지 지급액 평균. 사실 대조 대상 수치 없음")

# =====================================================================
# W3-D06 국민내일배움카드
# =====================================================================
D = "W3-D06"
vo = yes("vocaedu_yn")
calc(D, 1, 1, "대상 국민내일배움카드 연간 정부지원 vocaedu_yn==1 / 값 인원(indwgt 합계) / 분류 성 / 쓴 변수 vocaedu_yn, gender",
     False, [cell_cnt(vo & (df.gender == 1), labels=["남"]), cell_cnt(vo & (df.gender == 2), labels=["여"]), cell_cnt(vo, labels=["계"])])
b6 = [("34세 이하", 0, 34), ("35~49세", 35, 49), ("50~64세", 50, 64)]
calc(D, 2, 1, "대상 정부지원자 vocaedu_yn==1(indwgt) / 값 연간 정부지원금 vocaedu_amt 평균(원) / 분류 34세 이하·35~49·50~64 / 쓴 변수 vocaedu_yn, vocaedu_amt, age",
     False, [cell_mean(vo & c_, "vocaedu_amt", labels=[l]) for l, c_ in agebands(df, b6)], note="정부지원자 연령 15~64세(65세 이상 0명)")
calc(D, 3, 1, "대상 정부지원자 vocaedu_yn==1(indwgt) / 분자 고용보험 연간 가입 empins_yn1==1 / 쓴 변수 vocaedu_yn, empins_yn1",
     True, [cell_pct(vo, yes("empins_yn1"))])
chk(D, 1, "ok", "문서 배경의 국민내일배움카드(2020년 1월 통합, 5년 300만 원 기본·최대 500만 원, 2022년 예산 대학 3학년 발급 계획)는 C18과 같음")
chk(D, 2, "ok", "연령대별 1인당 정부지원금. 사실 대조 대상 수치 없음")
chk(D, 3, "ok", "지원자 고용보험 가입 비율. 사실 대조 대상 수치 없음")
chk(D, 4, "ok", "「값이 없는 사업」 확인: 값없는_사업.tsv에 노인일자리사업 「시니어인턴십」 있음. 자료·codebook에 시니어인턴십 변수 없음(노인일자리는 공익활동·사회서비스형·시장형사업단만). 문서의 2022년 4.5만 개는 B22(4.5만 개)와 같음 → V 설정 타당")
chk(D, 5, "ok", "최댓값과 상위 10명 목록 요청으로 C 설정 타당. 계산하지 않음")

# =====================================================================
# W3-D07 산재보험
# =====================================================================
D = "W3-D07"
calc(D, 1, 1, "대상 산재보험 정기연금 연간 수급자 occupins_pension_yn==1 / 값 인원(indwgt 합계) / 쓴 변수 occupins_pension_yn", False, [cell_cnt(yes("occupins_pension_yn"), labels=["정기연금"])])
lp = yes("occupins_lump_yn")
calc(D, 1, 2, "대상 산재보험 수시·일시금 연간 수급자 occupins_lump_yn==1 / 값 인원(indwgt 합계) / 쓴 변수 occupins_lump_yn", False, [cell_cnt(lp, labels=["수시·일시금"])])
calc(D, 2, 1, "대상 수시·일시금 수급자 occupins_lump_yn==1(indwgt) / 값 급여액 occupins_lump_amt 평균(원) / 분류 성 / 쓴 변수 occupins_lump_yn, occupins_lump_amt, gender",
     False, [cell_mean(lp & (df.gender == 1), "occupins_lump_amt", labels=["남"]), cell_mean(lp & (df.gender == 2), "occupins_lump_amt", labels=["여"])])
b7 = [("49세 이하", 0, 49), ("50~64세", 50, 64), ("65세 이상", 65, 200)]
calc(D, 4, 1, "대상 수시·일시금 수급자 occupins_lump_yn==1(indwgt) / 분자 연령대 / 분류 49세 이하·50~64·65세 이상 / 쓴 변수 occupins_lump_yn, age",
     True, comp(lp, agebands(df, b7)),
     note="전제 오류 항목: 전속성 요건 폐지 시행은 2023년 7월이며 2022년은 전속성 요건 유지(C25). 산출 가능한 부분은 2022년 수시·일시금 수급자 연령 구성비")
chk(D, 1, "ok", "문서 배경의 산재보험 급여 종류(휴업급여 평균임금 70%, 장례비 120일분 등)는 C25 note와 같음")
chk(D, 2, "ok", "성별 1인당 수시·일시금 평균. 사실 대조 대상 수치 없음")
chk(D, 3, "ok", "「자료에 없음」 확인: codebook의 산재보험 변수는 정기연금·수시일시금 수급여부·급여액뿐이며 산재보험 적용(가입)·특수형태근로종사자 구분 변수 없음 → N 설정 타당(특고 산재보험 적용은 실재 제도, C25)")
chk(D, 4, "ok", "전제 오류 확인: 문서의 「전속성 요건은 2022년 7월 1일부터 폐지되어 2022년은 적용이 넓어진 첫해」는 사실과 다름. 개정안 2022.5.29. 국회 통과·6월 공포, 시행 2023년 7월, 2022년에는 전속성 요건 유지(C25) → X 설정 타당")
chk(D, 5, "ok", "성별 평균 차이를 보상 수준의 성별 격차로 단정하는 문장 요청으로 I 설정 타당. 계산하지 않음")

# =====================================================================
# W3-D08 고용보험
# =====================================================================
D = "W3-D08"
a1864 = (df.age >= 18) & (df.age <= 64)
eins = yes("empins_yn1")
c = calc(D, 1, 1, "대상 18~64세 인구(indwgt) / 분자 고용보험 연간 가입 empins_yn1==1 / 쓴 변수 age, empins_yn1", True, [cell_pct(a1864, eins)])
judge(D, 1, 62.4, c[0], "pct", "")
calc(D, 2, 1, "대상 18~64세 인구(indwgt) / 분자 empins_yn1==1 / 분류 성(male·female) / 쓴 변수 age, gender, empins_yn1",
     True, [cell_pct(a1864 & (df.gender == 1), eins, labels=["male"]), cell_pct(a1864 & (df.gender == 2), eins, labels=["female"])])
TH = 22_973_280
popL = eins & (df.labinc_sum_taxy > 0)
popP = eins & (df.p_labinc > 0)
cL = cell_pct(popL, df.labinc_sum_taxy < TH)
cP = cell_pct(popP, df.p_labinc < TH)
amb3 = abs(cL["value"] - cP["value"]) > 0.1
calc(D, 3, 1, "대상 고용보험 연간 가입 empins_yn1==1 & 2022년 귀속 근로소득(연말정산 근로소득 합계금액 labinc_sum_taxy) > 0(indwgt) / 분자 labinc_sum_taxy < 22,973,280원 / 쓴 변수 empins_yn1, labinc_sum_taxy",
     True, [cL], reading_no=1, ambiguous=amb3,
     note="기준값 22,973,280원 = 2022년 최저임금 월 환산액 1,914,440원 × 12(C13), 문서 제시값(G). codebook 설명이 「2022년 귀속」인 연말정산 근로소득 변수 사용")
calc(D, 3, 1, "대상 empins_yn1==1 & 개인 근로소득 p_labinc > 0(indwgt) / 분자 p_labinc < 22,973,280원 / 쓴 변수 empins_yn1, p_labinc",
     True, [cP], reading_no=2, ambiguous=amb3,
     note="소득 구성의 개인 근로소득(p_labinc)으로 읽은 경우. 근로소득이 있는 사람의 집합은 두 변수가 같음(37,486건), 금액은 45%가량 행에서 다름")
calc(D, 4, 1, "대상 2022.10.31. 고용보험 가입(고정시점) empins_yn2==1 / 값 인원(indwgt 합계) / 쓴 변수 empins_yn2", False, [cell_cnt(yes("empins_yn2"))])
calc(D, 5, 1, "대상 2022년 귀속 일용근로소득 dainc_sum > 0(indwgt) / 분자 고용보험 연간 가입 empins_yn1==1 / 쓴 변수 dainc_sum, empins_yn1",
     True, [cell_pct(df.dainc_sum > 0, eins)], note="dainc_sum>0과 p_dainc>0의 대상 집합이 같아(12,448건) 변수 선택에 따른 차이 없음")
chk(D, 2, "ok", "문서 배경의 전국민 고용보험 로드맵(2020.12.23., 2025년 2,100만 명, 예술인 2020.12.·특고 12개 직종 2021.7.·퀵서비스·대리운전 2022.1.·5개 직종 2022.7.)은 C03·C04·C05와 같고, 2022.7. 실업급여 보험료율 1.6% → 1.8%는 C07과 같음")
chk(D, 3, "ok",
    "문서 제시 기준값 확인: 2022년 최저임금 월 환산액 1,914,440원(C13), 12배 22,973,280원 산술 일치 → G 설정 타당" +
    ("" if not amb3 else f". 다만 「2022년 귀속 근로소득」이 두 변수로 읽혀 값이 다름(labinc_sum_taxy {cL['value']:.2f}% / p_labinc {cP['value']:.2f}%, 차이 {abs(cL['value'] - cP['value']):.2f}%p). 참값 확정 시 두 읽기 모두 인정 또는 변수 지정 필요"))
chk(D, 4, "ok", "고정시점 가입 여부가 10월 31일 기준임은 codebook empins_yn2 정의와 같음")
chk(D, 5, "ok", "일용근로소득자 고용보험 가입 비율. 사실 대조 대상 수치 없음")

# ---------- W3-D01 item 2 대체 읽기(참고) ----------
alt = comp(k1, agebands(df, b5))
main = [r for r in rows if r.get("id") == "W3-D01" and r.get("item") == 2 and "cells" in r][0]
diff = max(abs(a["value"] - m["value"]) for a, m in zip(alt, main["cells"]))
main["note"] += "; Ⅰ유형만 읽으면 " + " / ".join(f"{a['labels'][0]} {a['value']:.2f}%" for a in alt) + f"(최대 차이 {diff:.2f}%p)"
if diff > 1.0:
    main["ambiguous"] = True
    rows.append({"id": "W3-D01", "item": 2, "sub": 1, "reading_no": 2,
                 "reading": "대상 Ⅰ유형 연간 참여자 kua_yn1==1 & kua_type==1(indwgt) / 분자 연령대 / 분류 34세 이하·35~49·50세 이상 / 쓴 변수 kua_yn1, kua_type, age",
                 "pct": True, "cells": alt, "ambiguous": True,
                 "note": "「한국형 실업부조」를 구직촉진수당이 있는 Ⅰ유형으로 좁혀 읽은 경우"})

# ---------- 정렬·저장 ----------
order = {}
for r in rows:
    order.setdefault(r["id"], len(order))
rows.sort(key=lambda r: (order[r["id"]], r["item"], 0 if "cells" in r else 1, r.get("sub", 0), r.get("reading_no", 0)))
with open(OUT, "w", encoding="utf-8") as fh:
    for r in rows:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
print("written", len(rows), "rows →", OUT)
