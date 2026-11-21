# -*- coding: utf-8 -*-
"""독립 검산(check_1): 질문 문장만 보고 분석 자료에서 직접 계산한 값.

- 입력: check_input_1.jsonl(질문 48개), 가상데이터_확대본_n42000.parquet
- 규약: inputs/자료_규약.md (가중치, 결측, 균등화 소득, 5분위, 상대 빈곤, 가중 분위수)
- 산출: check_1.jsonl (질문마다 1줄, 해석이 둘이면 2줄)
- 개인 단위 행은 출력하지 않음. 분석 함수(ssda)는 쓰지 않음.
"""
import json
import numpy as np
import pandas as pd

BASE = "/mnt/share/행정데이터_set"
DATA = BASE + "/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet"
OUT = BASE + "/로컬LLM_준비/05_eval/independent/truth/check_1.jsonl"

df = pd.read_parquet(DATA)
# Int64(nullable) 열은 float로 바꿔 비교·평균을 단순화
for c in df.columns:
    if str(df[c].dtype) == "Int64":
        df[c] = df[c].astype("float64")

SIDO = {1: "서울", 2: "부산", 3: "대구", 4: "인천", 5: "광주", 6: "대전", 7: "울산", 8: "세종",
        9: "경기", 10: "강원", 11: "충북", 12: "충남", 13: "전북", 14: "전남", 15: "경북",
        16: "경남", 17: "제주"}
SEX = {1: "남", 2: "여"}


# ------------------------------------------------------------------ 공통 함수
def wq(v, w, q):
    """가중 분위수: 값을 오름차순으로 놓고 가중치 누적합이 전체의 q배에 처음 이르는 값."""
    v = np.asarray(v, dtype="float64")
    w = np.asarray(w, dtype="float64")
    o = np.argsort(v, kind="mergesort")
    v, w = v[o], w[o]
    c = np.cumsum(w)
    i = int(np.searchsorted(c, q * c[-1], side="left"))
    return float(v[min(i, len(v) - 1)])


def c_count(d, mask, w, labels=()):
    n = int(mask.sum())
    return {"labels": list(labels), "value": float(d.loc[mask, w].sum()) if n else None, "n": n}


def c_ratio(d, den, num, w, labels=()):
    n = int(den.sum())
    k = int((den & num).sum())
    val = 100.0 * float(d.loc[den & num, w].sum()) / float(d.loc[den, w].sum()) if n else None
    return {"labels": list(labels), "value": val, "n": n, "n_num": k}


def c_mean(d, mask, var, w, labels=()):
    m = mask & d[var].notna()
    n = int(m.sum())
    val = float((d.loc[m, var] * d.loc[m, w]).sum() / d.loc[m, w].sum()) if n else None
    return {"labels": list(labels), "value": val, "n": n}


def c_sum(d, mask, var, w, labels=()):
    m = mask & d[var].notna()
    n = int(m.sum())
    val = float((d.loc[m, var] * d.loc[m, w]).sum()) if n else None
    return {"labels": list(labels), "value": val, "n": n}


def c_quant(d, mask, var, w, q, labels=()):
    m = mask & d[var].notna()
    n = int(m.sum())
    val = wq(d.loc[m, var], d.loc[m, w], q) if n else None
    return {"labels": list(labels), "value": val, "n": n}


ROWS = []


def add(qid, reading, pct, cells, reading_no=1, ambiguous=False, note=""):
    ROWS.append({"id": qid, "turn": 1, "reading_no": reading_no, "reading": reading, "pct": pct,
                 "cells": cells, "ambiguous": ambiguous, "note": note})


# ------------------------------------------------------------------ 파생 변수(자료_규약)
I = "indwgt"   # 개인 가중치
HW = "hhwgt"   # 가구 가중치(가구주 행)
ALL = pd.Series(True, index=df.index)

# 균등화 가처분소득 = 가구원 p_dinc의 가구 합계 ÷ √hnum
df["eq"] = df.groupby("hid")["p_dinc"].transform("sum") / np.sqrt(df["hnum"])
MED = wq(df["eq"], df[I], 0.5)                      # 개인 가중 중위값(전체 인구)
df["poor"] = df["eq"] < 0.5 * MED                   # 상대 빈곤
QB = [wq(df["eq"], df[I], q) for q in (0.2, 0.4, 0.6, 0.8)]
df["quint"] = 1 + sum((df["eq"] >= b).astype(int) for b in QB)   # 경계값 이상이면 위 분위
df["metro"] = df["sido"].isin([1, 4, 9])           # 수도권(서울·인천·경기)
H = df[df["head"] == 1]                             # 가구 단위 = 가구주 행

age, sex = df["age"], df["gender"]
HN4 = [("1인", lambda d: d["hnum"] == 1), ("2인", lambda d: d["hnum"] == 2),
       ("3인", lambda d: d["hnum"] == 3), ("4인 이상", lambda d: d["hnum"] >= 4)]
REG = [("수도권", lambda d: d["metro"]), ("비수도권", lambda d: ~d["metro"])]

# ------------------------------------------------------------------ A001
num = df["nhi_out_tehospital_dur"] > 0
add("A001", "대상: 각 시도 전체 주민 / 분자: 상급종합병원 외래 내원일수가 있는 사람(nhi_out_tehospital_dur>0) / 분류: 시도 / 사용 변수: nhi_out_tehospital_dur, sido, indwgt",
    True, [c_ratio(df, df["sido"] == s, num, I, [SIDO[s]]) for s in SIDO])

# ------------------------------------------------------------------ A002
G = [("65~69세", age.between(65, 69)), ("70~79세", age.between(70, 79)), ("80세 이상", age >= 80)]
add("A002", "대상: 65세 이상 인구 / 분자: 12월 기준 기초연금 수급(bp_yn2==1) / 분류: 연령 3구간(65~69, 70~79, 80+) / 사용 변수: bp_yn2, age, indwgt",
    True, [c_ratio(df, m, df["bp_yn2"] == 1, I, [l]) for l, m in G])

# ------------------------------------------------------------------ A003
E = 100_000_000
G = [("1억원 미만", H["h_prop"] < E), ("1억원 이상 3억원 미만", (H["h_prop"] >= E) & (H["h_prop"] < 3 * E)),
     ("3억원 이상 6억원 미만", (H["h_prop"] >= 3 * E) & (H["h_prop"] < 6 * E)), ("6억원 이상", H["h_prop"] >= 6 * E)]
add("A003", "대상: 전체 가구(가구주 행, hhwgt) / 대상 변수: 가구 재산 h_prop(0 포함) / 분류: 재산 4구간 / 산출: 가구 수 / 사용 변수: h_prop, head, hhwgt",
    False, [c_count(H, m, HW, [l]) for l, m in G])

# ------------------------------------------------------------------ A004
den = (df["hnum"] == 1) & (age >= 65) & (sex == 2)
add("A004", "대상: 1인 가구(hnum==1)의 65세 이상 여성 / 분자: 2022년 노인맞춤돌봄서비스 이용(oldcare_yn1==1) / 분류: 없음 / 사용 변수: oldcare_yn1, hnum, age, gender, indwgt",
    True, [c_ratio(df, den, df["oldcare_yn1"] == 1, I)])

# ------------------------------------------------------------------ A005
G3 = [("0~17세", age <= 17), ("18~64세", age.between(18, 64)), ("65세 이상", age >= 65)]
add("A005", "대상: 종합병원 입원 재원일수가 있는 사람 / 대상 변수: nhi_in_gehospital_dur의 가중 중위수 / 분류: 연령 3구간 / 사용 변수: nhi_in_gehospital_dur, age, indwgt",
    False, [c_quant(df, m, "nhi_in_gehospital_dur", I, 0.5, [l]) for l, m in G3])

# ------------------------------------------------------------------ A006
den = df["unempbn_bnextended_yn"] == 1
RS = {1: "임신,출산,육아", 2: "본인의질병부상", 5: "병역법에따른의무복무", 6: "범죄혐의로인한구속또는형의집행", 8: "기타"}
add("A006", "대상: 실업급여 수급기간 연기 신고처리자(unempbn_bnextended_yn==1) / 분자: 연기사유별 인원 / 분류: 연기사유 코드(1,2,5,6,8) 구성비 / 사용 변수: unempbn_bnextended_reason, indwgt",
    True, [c_ratio(df, den, df["unempbn_bnextended_reason"] == k, I, [v]) for k, v in RS.items()],
    note="구성비의 n은 분모(신고처리자 전체), n_num은 해당 사유 관측 수")

# ------------------------------------------------------------------ A007
add("A007", "대상: 등록장애인(dis_yn==1) / 비장애인(dis_yn 결측) / 분자: 균등화 가처분소득이 전체 인구 중위값의 50% 미만 / 분류: 장애 여부 / 사용 변수: dis_yn, p_dinc, hnum, hid, indwgt",
    True, [c_ratio(df, df["dis_yn"] == 1, df["poor"], I, ["등록장애인"]),
           c_ratio(df, df["dis_yn"].isna(), df["poor"], I, ["비장애인"])])

# ------------------------------------------------------------------ A008
m0 = H["h_ee_deposit_amt_ptot"] > 0
add("A008", "대상: 가구 임차 보증금이 0보다 큰 가구(가구주 행, hhwgt) / 대상 변수: h_ee_deposit_amt_ptot의 가중 중위수 / 분류: 가구원수 4구간 / 사용 변수: h_ee_deposit_amt_ptot, hnum, head, hhwgt",
    False, [c_quant(H, m0 & f(H), "h_ee_deposit_amt_ptot", HW, 0.5, [l]) for l, f in HN4])

# ------------------------------------------------------------------ A009
add("A009", "대상: 2022년 자활근로(기초) 참여자(self_yn1==1) / 분자: 고정시점 참여(self_yn2==1) / 분류: 없음 / 사용 변수: self_yn1, self_yn2, indwgt",
    True, [c_ratio(df, df["self_yn1"] == 1, df["self_yn2"] == 1, I)],
    note="codebook 내용에는 self_yn2가 2022년 10월 31일 기준으로 적혀 있음. 고정시점 변수가 이것뿐이어서 12월 말 값으로 사용")

# ------------------------------------------------------------------ A010
A3 = [("18~34세", age.between(18, 34)), ("35~49세", age.between(35, 49)), ("50~64세", age.between(50, 64))]
add("A010", "대상: 18~64세 인구 / 분자: 고정시점 고용보험 가입(empins_yn2==1) / 분류: 성 × 연령대(18~34, 35~49, 50~64) / 사용 변수: empins_yn2, gender, age, indwgt",
    True, [c_ratio(df, (sex == g) & m, df["empins_yn2"] == 1, I, [SEX[g], l]) for g in (1, 2) for l, m in A3],
    note="codebook 내용에는 empins_yn2가 2022년 10월 31일 기준으로 적혀 있음. 고정시점 변수가 이것뿐이어서 12월 말 값으로 사용")

# ------------------------------------------------------------------ A011
add("A011", "대상: 전체(값이 있는 행) / 대상 변수: 교육급여 교육활동지원비 급여액 nbls_edu_amt1의 가중 합계 / 분류: 없음 / 사용 변수: nbls_edu_amt1, indwgt",
    False, [c_sum(df, ALL, "nbls_edu_amt1", I)])

# ------------------------------------------------------------------ A012
m0 = df["ltcare_visit_yn"] == 1
G = [("1·2등급", df["ltcare_grade"].isin([1, 2])), ("3등급", df["ltcare_grade"] == 3),
     ("4등급", df["ltcare_grade"] == 4), ("5등급", df["ltcare_grade"] == 5)]
add("A012", "대상: 방문요양서비스 수급자(ltcare_visit_yn==1) / 대상 변수: 방문요양 이용일수 ltcare_visit_freq의 가중 평균 / 분류: 등급 집단(1·2, 3, 4, 5) / 사용 변수: ltcare_visit_yn, ltcare_visit_freq, ltcare_grade, indwgt",
    False, [c_mean(df, m0 & m, "ltcare_visit_freq", I, [l]) for l, m in G])

# ------------------------------------------------------------------ A013
m0 = (df["sido"] == 1) & (age >= 65) & (df["hnum"] == 1) & (df["bp_yn2"] == 1)
add("A013", "대상: 서울(sido==1) 거주 65세 이상 1인 가구(hnum==1) / 산출: 12월 기준 기초연금 수급자(bp_yn2==1) 가중 인원 / 분류: 없음 / 사용 변수: bp_yn2, sido, age, hnum, indwgt",
    False, [c_count(df, m0, I)])

# ------------------------------------------------------------------ A014
G = [("지역가입", df["nhi_type"].isin([1, 2])), ("직장가입", df["nhi_type"].isin([5, 6])), ("의료급여", df["nhi_type"].isin([7, 8]))]
add("A014", "대상: 의원 외래 요양급여비용 총액이 있는 사람 / 대상 변수: nhi_out_clinic_amt의 가중 평균 / 분류: 건강보험 가입 구분(지역 1·2, 직장 5·6, 의료급여 7·8) / 사용 변수: nhi_out_clinic_amt, nhi_type, indwgt",
    False, [c_mean(df, m, "nhi_out_clinic_amt", I, [l]) for l, m in G])

# ------------------------------------------------------------------ A015
m0 = age.between(18, 64)
add("A015", "대상: 18~64세 인구 / 분자: 일용소득이 0보다 큰 사람(p_dainc>0, dainc_sum>0과 같은 집단) / 분류: 균등화 가처분소득 5분위(전체 인구 개인 가중 분위 경계) / 사용 변수: p_dainc, p_dinc, hnum, hid, age, indwgt",
    True, [c_ratio(df, m0 & (df["quint"] == k), df["p_dainc"] > 0, I, [f"{k}분위"]) for k in range(1, 6)])

# ------------------------------------------------------------------ A016
m0 = df["childcare_time_yn1"] == 1
add("A016", "대상: 2022년 시간제보육지원 지원 아동(childcare_time_yn1==1) / 산출: 가중 인원 / 분류: 시도 / 사용 변수: childcare_time_yn1, sido, indwgt",
    False, [c_count(df, m0 & (df["sido"] == s), I, [SIDO[s]]) for s in SIDO],
    note="전체 관측 36건. 울산·세종·전북·전남은 관측 0건(null)")

# ------------------------------------------------------------------ A017
m0 = (age >= 18) & (df["dis_yn"] == 1) & (df["dis_grade_1"] == 1)
add("A017", "대상: 18세 이상, 종합장애정도가 심한(dis_grade_1==1) 등록장애인(dis_yn==1) / 분자: 2022년 장애인연금 수급(disp_yn1==1) / 분류: 성 / 사용 변수: disp_yn1, dis_yn, dis_grade_1, age, gender, indwgt",
    True, [c_ratio(df, m0 & (sex == g), df["disp_yn1"] == 1, I, [SEX[g]]) for g in (1, 2)])

# ------------------------------------------------------------------ A018
add("A018", "대상: 전체(값이 있는 행) / 대상 변수: (입원) 상급종합병원 공단부담금 nhi_in_tehospital_subsidy의 가중 합계 / 분류: 없음 / 사용 변수: nhi_in_tehospital_subsidy, indwgt",
    False, [c_sum(df, ALL, "nhi_in_tehospital_subsidy", I)])

# ------------------------------------------------------------------ A019
m0 = df["kua_yn1"] == 1
G = [("34세 이하", age <= 34), ("35세 이상", age >= 35)]
add("A019", "대상: 2022년 국민취업지원제도 참여자(kua_yn1==1) / 분자: 참여유형별 인원(kua_type) / 분류: 연령 2구간(34세 이하, 35세 이상) 안의 참여유형 구성비 / 사용 변수: kua_yn1, kua_type, age, indwgt",
    True, [c_ratio(df, m0 & m, df["kua_type"] == t, I, [l, f"{t}유형"]) for l, m in G for t in (1, 2)],
    note="구성비의 분모는 각 연령 집단의 참여자")

# ------------------------------------------------------------------ A020
m0 = H["nbls_live_yn2"] == 1
add("A020", "대상: 가구주가 12월 기준 생계급여 수급자인 가구(head==1 & nbls_live_yn2==1) / 산출: 가중 가구 수(hhwgt) / 분류: 가구원수 4구간 / 사용 변수: nbls_live_yn2, hnum, head, hhwgt",
    False, [c_count(H, m0 & f(H), HW, [l]) for l, f in HN4])

# ------------------------------------------------------------------ A021 (해석 2개)
G = [("30세 미만", age < 30), ("30~49세", age.between(30, 49)), ("50~64세", age.between(50, 64)), ("65세 이상", age >= 65)]
m0 = df["p_dainc"] > 0
NOTE21 = "일용소득 금액 변수가 둘(p_dainc 「일용소득」, dainc_sum 「일용소득_총지급금액」)이고 대상 집단은 같으나 값이 개인별로 ±500원 안팎 다름. 평균 차이는 미미"
add("A021", "대상: 일용소득이 0보다 큰 사람(p_dainc>0) / 대상 변수: 개인 일차소득의 일용소득 p_dainc 가중 평균 / 분류: 연령 4구간(30 미만, 30~49, 50~64, 65+) / 사용 변수: p_dainc, age, indwgt",
    False, [c_mean(df, m0 & m, "p_dainc", I, [l]) for l, m in G], ambiguous=True, note=NOTE21)
add("A021", "대상: 일용소득 총지급금액이 있는 사람(dainc_sum>0) / 대상 변수: 일용소득DB의 총지급금액 dainc_sum 가중 평균 / 분류: 연령 4구간(30 미만, 30~49, 50~64, 65+) / 사용 변수: dainc_sum, age, indwgt",
    False, [c_mean(df, (df["dainc_sum"] > 0) & m, "dainc_sum", I, [l]) for l, m in G], reading_no=2, ambiguous=True, note=NOTE21)

# ------------------------------------------------------------------ A022
add("A022", "대상: 2022년 긴급복지 생계지원 수급자(aid_live_yn1==1) / 분자: 12월 기준 수급(aid_live_yn2==1) / 분류: 없음 / 사용 변수: aid_live_yn1, aid_live_yn2, indwgt",
    True, [c_ratio(df, df["aid_live_yn1"] == 1, df["aid_live_yn2"] == 1, I)])

# ------------------------------------------------------------------ A023
G = [("65~74세", age.between(65, 74)), ("75세 이상", age >= 75)]
add("A023", "대상: 65세 이상 인구 / 분자: 균등화 가처분소득이 전체 인구 중위값의 50% 미만 / 분류: 성 × 연령(65~74, 75+) / 사용 변수: p_dinc, hnum, hid, gender, age, indwgt",
    True, [c_ratio(df, (sex == g) & m, df["poor"], I, [SEX[g], l]) for g in (1, 2) for l, m in G])

# ------------------------------------------------------------------ A024 (해석 2개)
rec = df["ltcare_grade"].isin([1, 2, 3, 4, 5, 6])
NOTE24 = "「인정률」의 분모가 문장에 없음. 65세 이상 인구 대비(해석 1)와 장기요양 신청자 대비(해석 2)가 모두 통용됨"
add("A024", "대상: 65세 이상 인구 전체 / 분자: 장기요양 1~5등급·인지지원등급 판정자(ltcare_grade 1~6) / 분류: 성 / 사용 변수: ltcare_grade, age, gender, indwgt",
    True, [c_ratio(df, (age >= 65) & (sex == g), rec, I, [SEX[g]]) for g in (1, 2)], ambiguous=True, note=NOTE24)
add("A024", "대상: 65세 이상 장기요양 신청자(ltcare_yn==1) / 분자: 장기요양 1~5등급·인지지원등급 판정자(ltcare_grade 1~6) / 분류: 성 / 사용 변수: ltcare_yn, ltcare_grade, age, gender, indwgt",
    True, [c_ratio(df, (age >= 65) & (df["ltcare_yn"] == 1) & (sex == g), rec, I, [SEX[g]]) for g in (1, 2)],
    reading_no=2, ambiguous=True, note=NOTE24)

# ------------------------------------------------------------------ A025
G = [("0~2세", age.between(0, 2)), ("3~5세", age.between(3, 5))]
add("A025", "대상: 만 0~5세 아동 / 분자: 2022년 보육료지원 지원(childcare_yn1==1) / 분류: 연령 2구간(0~2, 3~5) / 사용 변수: childcare_yn1, age, indwgt",
    True, [c_ratio(df, m, df["childcare_yn1"] == 1, I, [l]) for l, m in G])

# ------------------------------------------------------------------ A026
m0 = (age >= 65) & (df["pubpen_inc"] > 0)
add("A026", "대상: 65세 이상, 공적연금 총연금수령액이 0보다 큰 사람 / 대상 변수: pubpen_inc의 가중 중위수 / 분류: 성 / 사용 변수: pubpen_inc, age, gender, indwgt",
    False, [c_quant(df, m0 & (sex == g), "pubpen_inc", I, 0.5, [SEX[g]]) for g in (1, 2)])

# ------------------------------------------------------------------ A027
m0 = df["aid_house_yn1"] == 1
add("A027", "대상: 2022년 긴급복지 주거지원 수급자(aid_house_yn1==1) / 대상 변수: 주거지원 급여액 aid_house_amt의 가중 평균 / 분류: 시도 / 사용 변수: aid_house_yn1, aid_house_amt, sido, indwgt",
    False, [c_mean(df, m0 & (df["sido"] == s), "aid_house_amt", I, [SIDO[s]]) for s in SIDO],
    note="전체 관측 33건. 부산·대전·세종·강원·제주는 관측 0건(null), 나머지 칸도 1~10건")

# ------------------------------------------------------------------ A028
G = [("40세 미만", age < 40), ("40~64세", age.between(40, 64)), ("65세 이상", age >= 65)]
add("A028", "대상: 의원 입원 재원일수가 있는 사람 / 대상 변수: nhi_in_clinic_dur의 가중 평균 / 분류: 성 × 연령(40 미만, 40~64, 65+) / 사용 변수: nhi_in_clinic_dur, gender, age, indwgt",
    False, [c_mean(df, (sex == g) & m, "nhi_in_clinic_dur", I, [SEX[g], l]) for g in (1, 2) for l, m in G])

# ------------------------------------------------------------------ A029 (해석 2개)
js = df["unempbn_jobseekbn_yn"] == 1
a1864 = age.between(18, 64)
NOTE29 = "「18~64세 인구 대비 구직급여 수급자 비율」에서 분자를 18~64세 수급자로 한정하는지(해석 1), 전 연령 수급자로 두는지(해석 2) 문장에 없음. 65세 이상 수급자 관측 167건"
add("A029", "대상: 18~64세 인구 / 분자: 18~64세 가운데 2022년 구직급여 수급자(unempbn_jobseekbn_yn==1) / 분류: 수도권(sido 1·4·9)·비수도권 / 사용 변수: unempbn_jobseekbn_yn, age, sido, indwgt",
    True, [c_ratio(df, a1864 & f(df), js, I, [l]) for l, f in REG], ambiguous=True, note=NOTE29)
cells = []
for l, f in REG:
    r = f(df)
    cells.append({"labels": [l], "value": 100.0 * float(df.loc[r & js, I].sum()) / float(df.loc[r & a1864, I].sum()),
                  "n": int((r & a1864).sum()), "n_num": int((r & js).sum())})
add("A029", "대상(분모): 18~64세 인구 / 분자: 전 연령의 2022년 구직급여 수급자(unempbn_jobseekbn_yn==1) / 분류: 수도권(sido 1·4·9)·비수도권 / 사용 변수: unempbn_jobseekbn_yn, age, sido, indwgt",
    True, cells, reading_no=2, ambiguous=True, note=NOTE29)

# ------------------------------------------------------------------ A030
den = df["itc_yn"] == 1
HM = {11: "단독가구", 21: "홑벌이가구", 23: "맞벌이가구"}
add("A030", "대상: 근로장려 수급 대상(itc_yn==1) / 분자: 가구원구성코드별 인원 / 분류: 가구 유형(itc_hmember 11·21·23) 구성비 / 사용 변수: itc_yn, itc_hmember, indwgt",
    True, [c_ratio(df, den, df["itc_hmember"] == k, I, [v]) for k, v in HM.items()])

# ------------------------------------------------------------------ A031
m0 = age.between(6, 17)
add("A031", "대상: 6~17세 / 분자: 2022년 방과후학교 자유수강권 지원(pubedu_aftsch_yn==1) / 분류: 빈곤 여부(균등화 가처분소득이 전체 인구 중위값의 50% 미만) / 사용 변수: pubedu_aftsch_yn, p_dinc, hnum, hid, age, indwgt",
    True, [c_ratio(df, m0 & df["poor"], df["pubedu_aftsch_yn"] == 1, I, ["빈곤"]),
           c_ratio(df, m0 & ~df["poor"], df["pubedu_aftsch_yn"] == 1, I, ["비빈곤"])])

# ------------------------------------------------------------------ A032
ha = H["age"]
G = [("40세 미만", ha < 40), ("40대", ha.between(40, 49)), ("50대", ha.between(50, 59)), ("60대", ha.between(60, 69)), ("70세 이상", ha >= 70)]
add("A032", "대상: 전체 가구(가구주 행, hhwgt) / 분자: 가구의 주택 외 건축물 시가표준액 합계가 0보다 큰 가구(h_ptax_building>0) / 분류: 가구주 연령대 5구간 / 사용 변수: h_ptax_building, age, head, hhwgt",
    True, [c_ratio(H, m, H["h_ptax_building"] > 0, HW, [l]) for l, m in G])

# ------------------------------------------------------------------ A033
add("A033", "대상: 2022년 출산전후휴가 급여 수급자(empins_matleave_yn1==1) / 대상 변수: 수급기간(일) empins_matleave_dur의 가중 평균 / 분류: 없음 / 사용 변수: empins_matleave_yn1, empins_matleave_dur, indwgt",
    False, [c_mean(df, df["empins_matleave_yn1"] == 1, "empins_matleave_dur", I)])

# ------------------------------------------------------------------ A034
m0 = df["disvou_act_yn1"] == 1
G = [("18세 미만", age < 18), ("18~64세", age.between(18, 64)), ("65세 이상", age >= 65)]
add("A034", "대상: 2022년 장애인활동지원 이용자(disvou_act_yn1==1) / 대상 변수: 결제금액 disvou_act_amt의 가중 중위수 / 분류: 연령 3구간(18 미만, 18~64, 65+) / 사용 변수: disvou_act_yn1, disvou_act_amt, age, indwgt",
    False, [c_quant(df, m0 & m, "disvou_act_amt", I, 0.5, [l]) for l, m in G],
    note="65세 이상은 관측 0건(null)")

# ------------------------------------------------------------------ A035
add("A035", "대상: 전체(값이 있는 행) / 대상 변수: 분리과세주택임대소득총수입금액 inc_sehou_sum의 가중 합계 / 분류: 수도권(sido 1·4·9)·비수도권 / 사용 변수: inc_sehou_sum, sido, indwgt",
    False, [c_sum(df, f(df), "inc_sehou_sum", I, [l]) for l, f in REG],
    note="n은 inc_sehou_sum 값이 있는 행(0 포함). 0보다 큰 행은 전국 512건")

# ------------------------------------------------------------------ A036
m0 = df["ltcare_bn_yn"] == 1
add("A036", "대상: 장기요양 수급자(ltcare_bn_yn==1) / 분자: 방문목욕서비스 수급(ltcare_bath_yn==1) / 분류: 성 / 사용 변수: ltcare_bn_yn, ltcare_bath_yn, gender, indwgt",
    True, [c_ratio(df, m0 & (sex == g), df["ltcare_bath_yn"] == 1, I, [SEX[g]]) for g in (1, 2)])

# ------------------------------------------------------------------ A037
m0 = (df["sido"] == 1) & (age >= 65) & (sex == 2) & (df["nhi_out_tehospital_dur"] > 0)
add("A037", "대상: 서울(sido==1) 거주 65세 이상 여성 가운데 상급종합병원 외래 내원일수가 있는 사람 / 대상 변수: nhi_out_tehospital_dur의 가중 평균 / 분류: 없음 / 사용 변수: nhi_out_tehospital_dur, sido, age, gender, indwgt",
    False, [c_mean(df, m0, "nhi_out_tehospital_dur", I)])

# ------------------------------------------------------------------ A038
m0 = df["empins_parentleave_yn1"] == 1
add("A038", "대상: 2022년 육아휴직급여 수급자(empins_parentleave_yn1==1) / 산출: 가중 인원 / 분류: 성 / 사용 변수: empins_parentleave_yn1, gender, indwgt",
    False, [c_count(df, m0 & (sex == g), I, [SEX[g]]) for g in (1, 2)])

# ------------------------------------------------------------------ A039
add("A039", "대상: 전체(값이 있는 행) / 대상 변수: 장애수당 급여액 disp_bn_amt의 가중 합계(장애아동수당 disp_bn_child_amt 제외) / 분류: 없음 / 사용 변수: disp_bn_amt, indwgt",
    False, [c_sum(df, ALL, "disp_bn_amt", I)])

# ------------------------------------------------------------------ A040
m0 = H["metro"] & (H["age"] >= 65) & (H["hnum"] == 1)
add("A040", "대상: 수도권(sido 1·4·9), 가구주 65세 이상, 1인 가구(가구주 행, hhwgt) / 대상 변수: 가구 재산 h_prop(0 포함)의 가중 75% 분위수 / 분류: 없음 / 사용 변수: h_prop, sido, age, hnum, head, hhwgt",
    False, [c_quant(H, m0, "h_prop", HW, 0.75)])

# ------------------------------------------------------------------ A041
m0 = df["pubedu_aftsch_yn"] == 1
G = [("12세 이하", age <= 12), ("13~15세", age.between(13, 15)), ("16세 이상", age >= 16)]
add("A041", "대상: 2022년 방과후학교 자유수강권 지원 학생(pubedu_aftsch_yn==1) / 대상 변수: 지원액 pubedu_aftsch_amt의 가중 평균 / 분류: 연령 3구간(12 이하, 13~15, 16+) / 사용 변수: pubedu_aftsch_yn, pubedu_aftsch_amt, age, indwgt",
    False, [c_mean(df, m0 & m, "pubedu_aftsch_amt", I, [l]) for l, m in G])

# ------------------------------------------------------------------ A042
den = df["ltcare_bn_yn"] == 1
add("A042", "대상: 장기요양 수급자(ltcare_bn_yn==1) / 분자: 소득 분위별 인원 / 분류: 균등화 가처분소득 5분위(전체 인구 개인 가중 분위 경계) 구성비 / 사용 변수: ltcare_bn_yn, p_dinc, hnum, hid, indwgt",
    True, [c_ratio(df, den, df["quint"] == k, I, [f"{k}분위"]) for k in range(1, 6)])

# ------------------------------------------------------------------ A043
den = age.between(30, 39) & (sex == 2) & (df["nhi_type"] == 5)
add("A043", "대상: 30~39세 여성 건강보험 직장가입자(nhi_type==5, 피부양자 6 제외) / 분자: 2022년 육아휴직급여 수급(empins_parentleave_yn1==1) / 분류: 없음 / 사용 변수: empins_parentleave_yn1, nhi_type, age, gender, indwgt",
    True, [c_ratio(df, den, df["empins_parentleave_yn1"] == 1, I)])

# ------------------------------------------------------------------ A044
m0 = df["aid_live_yn1"] == 1
add("A044", "대상: 2022년 긴급복지 생계지원 수급자(aid_live_yn1==1) / 대상 변수: 수급기간(개월) aid_live_dur의 가중 평균 / 분류: 1인 가구(hnum==1)·2인 이상 가구(hnum>=2) / 사용 변수: aid_live_yn1, aid_live_dur, hnum, indwgt",
    False, [c_mean(df, m0 & (df["hnum"] == 1), "aid_live_dur", I, ["1인 가구"]),
            c_mean(df, m0 & (df["hnum"] >= 2), "aid_live_dur", I, ["2인 이상 가구"])])

# ------------------------------------------------------------------ A045
m0 = df["nbls_medi_yn2"] == 1
G = [("65세 미만", age < 65), ("65세 이상", age >= 65)]
add("A045", "대상: 12월 기준 의료급여 수급권자(nbls_medi_yn2==1) / 산출: 가중 인원 / 분류: 종별(nbls_medi_type 1종·2종) × 연령(65 미만, 65+) / 사용 변수: nbls_medi_yn2, nbls_medi_type, age, indwgt",
    False, [c_count(df, m0 & (df["nbls_medi_type"] == t) & m, I, [f"{t}종", l]) for t in (1, 2) for l, m in G])

# ------------------------------------------------------------------ A046
add("A046", "대상: 2022년 한부모가족지원 아동양육비 수급자(single_rear_yn1==1) / 대상 변수: 아동양육비 급여액 single_rear_amt의 가중 평균(추가아동양육비 single_extra_amt 제외) / 분류: 없음 / 사용 변수: single_rear_yn1, single_rear_amt, indwgt",
    False, [c_mean(df, df["single_rear_yn1"] == 1, "single_rear_amt", I)])

# ------------------------------------------------------------------ A047
add("A047", "대상: 65세 이상 인구 전체 / 분자: 고혈압 입원 여부(nhi_highbp_yn==1) / 분류: 없음 / 사용 변수: nhi_highbp_yn, age, indwgt",
    True, [c_ratio(df, age >= 65, df["nhi_highbp_yn"] == 1, I)],
    note="nhi_highbp_yn은 65세 이상의 약 27%에만 값(0/1)이 있고 나머지는 결측. 0과 결측을 모두 미해당으로 보고 분모를 65세 이상 전체로 둠")

# ------------------------------------------------------------------ A048
den = (~df["metro"]) & (df["hnum"] == 1) & (age >= 75) & (sex == 2)
add("A048", "대상: 비수도권(sido 1·4·9 외) 거주, 1인 가구(hnum==1), 75세 이상 여성 / 분자: 균등화 가처분소득이 전체 인구 중위값의 50% 미만 / 분류: 없음 / 사용 변수: p_dinc, hnum, hid, sido, age, gender, indwgt",
    True, [c_ratio(df, den, df["poor"], I)])

# ------------------------------------------------------------------ 저장
with open(OUT, "w", encoding="utf-8") as f:
    for r in ROWS:
        f.write(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n")

ids = sorted({r["id"] for r in ROWS})
print("questions:", len(ids), "rows:", len(ROWS))
print("median eq:", MED, "quintile bounds:", QB)
