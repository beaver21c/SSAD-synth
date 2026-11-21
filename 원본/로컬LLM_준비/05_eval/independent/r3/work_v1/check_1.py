# -*- coding: utf-8 -*-
"""독립 검산(check_1): 질문 48개를 분석 자료에서 직접 계산.
- 개인 단위: indwgt 가중 / 가구 단위: 가구주 행(head==1)에 hhwgt 가중
- 여부 변수는 == 1 로 판별(결측·0은 비해당), 평균·합계·분위수는 값이 있는 행만
- 개인 단위 행은 출력하지 않음(집계값만 기록)
"""
import json
import numpy as np
import pandas as pd

DATA = "/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet"
OUT = "/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r3/truth/check_1.jsonl"

df = pd.read_parquet(DATA)
# 결측 허용 정수형(Int64)은 float로 바꿔 조건의 결측이 거짓이 되게 함
for c in df.columns:
    if str(df[c].dtype) in ("Int64", "Int32", "boolean"):
        df[c] = df[c].astype("float64")

W = df["indwgt"]
SIDO = {1: "서울", 2: "부산", 3: "대구", 4: "인천", 5: "광주", 6: "대전", 7: "울산", 8: "세종", 9: "경기",
        10: "강원", 11: "충북", 12: "충남", 13: "전북", 14: "전남", 15: "경북", 16: "경남", 17: "제주"}
GENDER = {1: "남", 2: "여"}


# ---------- 공통 함수 ----------
def wquant(v, w, q):
    """가중 분위수: 값을 오름차순으로 놓고 가중치 누적합이 전체의 q배에 처음 이르는 값."""
    v = np.asarray(v, dtype="float64")
    w = np.asarray(w, dtype="float64")
    if len(v) == 0:
        return None
    o = np.argsort(v, kind="mergesort")
    v, w = v[o], w[o]
    cum = np.cumsum(w)
    i = int(np.searchsorted(cum, q * cum[-1], side="left"))
    i = min(i, len(v) - 1)
    return float(v[i])


def cell_count(mask, labels, w=W):
    n = int(mask.sum())
    return {"labels": labels, "value": float(w[mask].sum()) if n else None, "n": n}


def cell_ratio(den, num, labels, w=W):
    num = num & den
    n, k = int(den.sum()), int(num.sum())
    val = float(w[num].sum() / w[den].sum() * 100) if n else None
    return {"labels": labels, "value": val, "n": n, "n_num": k}


def cell_mean(mask, var, labels, w=W):
    m = mask & df[var].notna()
    n = int(m.sum())
    val = float((df.loc[m, var] * w[m]).sum() / w[m].sum()) if n else None
    return {"labels": labels, "value": val, "n": n}


def cell_sum(mask, var, labels, w=W):
    m = mask & df[var].notna()
    n = int(m.sum())
    val = float((df.loc[m, var] * w[m]).sum()) if n else None
    return {"labels": labels, "value": val, "n": n}


def cell_quant(mask, var, q, labels, w=W):
    m = mask & df[var].notna()
    n = int(m.sum())
    val = wquant(df.loc[m, var], w[m], q) if n else None
    return {"labels": labels, "value": val, "n": n}


ROWS = []


def emit(qid, reading, pct, cells, reading_no=1, ambiguous=False, note=""):
    ROWS.append({"id": qid, "turn": 1, "reading_no": reading_no, "reading": reading, "pct": pct,
                 "cells": cells, "ambiguous": ambiguous, "note": note})


# ---------- 파생 변수 ----------
age, gender, sido, hnum = df["age"], df["gender"], df["sido"], df["hnum"]
HEAD = df["head"] == 1
HW = df["hhwgt"]

# 균등화 가처분소득 = 가구원 p_dinc 가구 합계 / sqrt(hnum)
eq = df.groupby("hid")["p_dinc"].transform("sum") / np.sqrt(hnum)
MED = wquant(eq, W, 0.5)
POOR = eq < 0.5 * MED                              # 상대 빈곤(전국 중위값의 50% 미만)
QB = [wquant(eq, W, q) for q in (0.2, 0.4, 0.6, 0.8)]
QUINT = 1 + sum((eq >= b).astype(int) for b in QB)  # 경계값 이상이면 위 분위

NHI3 = pd.Series(np.where(df["nhi_type"].isin([1, 2]), "지역가입",
                 np.where(df["nhi_type"].isin([5, 6]), "직장가입", "의료급여")), index=df.index)
HN4 = pd.Series(np.where(hnum >= 4, "4인 이상", hnum.astype(str) + "인"), index=df.index)
HN4_ORDER = ["1인", "2인", "3인", "4인 이상"]
AGE6 = [("0~17세", 0, 17), ("18~34세", 18, 34), ("35~49세", 35, 49), ("50~64세", 50, 64),
        ("65~74세", 65, 74), ("75세 이상", 75, 999)]
AGE3 = [("0~17세", 0, 17), ("18~64세", 18, 64), ("65세 이상", 65, 999)]
OLD3 = [("65~74세", 65, 74), ("75~84세", 75, 84), ("85세 이상", 85, 999)]


def between(lo, hi):
    return (age >= lo) & (age <= hi)


def yes(var):
    return df[var] == 1


# ================= 질문별 계산 =================

# A001 65세 이상 기초연금 수급률, 시도별 (기준 시점 미기재 → 연간 / 12월)
den = age >= 65
emit("A001", "대상: 65세 이상 인구 / 분자: 2022년 연간 기초연금 수급(bp_yn1==1) / 분류: 시도 / 사용 변수: age, bp_yn1, sido, indwgt",
     True, [cell_ratio(den & (sido == k), yes("bp_yn1"), [nm]) for k, nm in SIDO.items()],
     reading_no=1, ambiguous=True,
     note="수급률의 기준 시점(연간 한 번이라도 수급 / 12월 기준 수급)이 질문에 적혀 있지 않음. 해석 1은 연간(bp_yn1), 해석 2는 12월 기준(bp_yn2)")
emit("A001", "대상: 65세 이상 인구 / 분자: 2022년 12월 기준 기초연금 수급(bp_yn2==1) / 분류: 시도 / 사용 변수: age, bp_yn2, sido, indwgt",
     True, [cell_ratio(den & (sido == k), yes("bp_yn2"), [nm]) for k, nm in SIDO.items()],
     reading_no=2, ambiguous=True,
     note="수급률의 기준 시점(연간 한 번이라도 수급 / 12월 기준 수급)이 질문에 적혀 있지 않음. 해석 1은 연간(bp_yn1), 해석 2는 12월 기준(bp_yn2)")

# A002 의원 외래 이용자의 의원 외래 요양급여비용 총액 1인당 평균, 생계급여 연간 수급 여부별
base = df["nhi_out_clinic_amt"].notna()
emit("A002", "대상: 2022년 의원 외래 이용자(nhi_out_clinic_amt 값 있음) / 대상 변수: 의원 외래 요양급여비용 총액 평균 / 분류: 생계급여 연간 수급 여부(nbls_live_yn1==1) / 사용 변수: nhi_out_clinic_amt, nbls_live_yn1, indwgt",
     False, [cell_mean(base & yes("nbls_live_yn1"), "nhi_out_clinic_amt", ["생계급여 수급"]),
             cell_mean(base & ~yes("nbls_live_yn1"), "nhi_out_clinic_amt", ["생계급여 비수급"])])

# A003 가구주 65세 이상 1인 가구 중 가구 재산 1억원 미만 가구 수
m = HEAD & (age >= 65) & (hnum == 1) & (df["h_prop"] < 1e8)
emit("A003", "대상: 가구주 65세 이상 1인 가구(가구주 행) / 조건: 가구 재산 h_prop < 1억원 / 산출: 가구 수(hhwgt 합계) / 사용 변수: head, age, hnum, h_prop, hhwgt",
     False, [cell_count(m, [], w=HW)])

# A004 응급실 하루 이상 이용 비율, 연령대 6구간 × 성
num = df["nhi_in_emergency_dur"] >= 1
emit("A004", "대상: 전체 인구 / 분자: 응급실 재원일수 1일 이상(nhi_in_emergency_dur>=1) / 분류: 연령대 6구간 × 성 / 사용 변수: nhi_in_emergency_dur, age, gender, indwgt",
     True, [cell_ratio(between(lo, hi) & (gender == g), num, [nm, gn])
            for nm, lo, hi in AGE6 for g, gn in GENDER.items()])

# A005 서울 임차 보증금 있는 가구의 가구 보증금 합계 중위수, 가구원수별
base = HEAD & (sido == 1) & (df["h_ee_deposit_amt_ptot"] > 0)
emit("A005", "대상: 서울 거주 가구 중 가구 임차 보증금 합계 > 0(가구주 행) / 대상 변수: h_ee_deposit_amt_ptot 가중 중위수(hhwgt) / 분류: 가구원수 4구간 / 사용 변수: head, sido, h_ee_deposit_amt_ptot, hnum, hhwgt",
     False, [cell_quant(base & (HN4 == k), "h_ee_deposit_amt_ptot", 0.5, [k], w=HW) for k in HN4_ORDER])

# A006 방문요양 이용 수급자의 연간 평균 이용일수, 등급 묶음별
base = yes("ltcare_visit_yn")
grp = [("1~2등급", [1, 2]), ("3등급", [3]), ("4등급", [4]), ("5등급", [5])]
emit("A006", "대상: 2022년 방문요양 이용 수급자(ltcare_visit_yn==1) / 대상 변수: 방문요양 이용일수(ltcare_visit_freq) 평균 / 분류: 판정 등급 묶음(1~2, 3, 4, 5) / 사용 변수: ltcare_visit_yn, ltcare_visit_freq, ltcare_grade, indwgt",
     False, [cell_mean(base & df["ltcare_grade"].isin(codes), "ltcare_visit_freq", [nm]) for nm, codes in grp])

# A007 자활근로 연간 참여자 중 10월 31일 시점 참여 비율
emit("A007", "대상: 2022년 자활근로(기초) 연간 참여자(self_yn1==1) / 분자: 2022.10.31. 기준 참여(self_yn2==1) / 사용 변수: self_yn1, self_yn2, indwgt",
     True, [cell_ratio(yes("self_yn1"), yes("self_yn2"), [])])

# A008 수도권 3개 시도 상급종합병원 입원 요양급여비용 총액 합계, 시도별
emit("A008", "대상: 서울·인천·경기 거주자 / 대상 변수: 상급종합병원 입원 요양급여비용 총액(nhi_in_tehospital_amt) 가중 합계 / 분류: 시도 / 사용 변수: nhi_in_tehospital_amt, sido, indwgt",
     False, [cell_sum(sido == k, "nhi_in_tehospital_amt", [SIDO[k]]) for k in (1, 4, 9)])

# A009 65세 이상 상대 빈곤율, 기초연금 연간 수급 여부별
den = age >= 65
emit("A009", "대상: 65세 이상 인구 / 분자: 상대 빈곤(균등화 가처분소득 < 전국 개인 가중 중위값의 50%) / 분류: 기초연금 연간 수급 여부(bp_yn1==1) / 사용 변수: p_dinc, hnum, hid, bp_yn1, age, indwgt",
     True, [cell_ratio(den & yes("bp_yn1"), POOR, ["기초연금 수급"]),
            cell_ratio(den & ~yes("bp_yn1"), POOR, ["기초연금 비수급"])])

# A010 30~49세 여성 고용보험 연간 가입자 중 육아휴직급여(사후지급금 제외) 연간 수급 비율
den = between(30, 49) & (gender == 2) & yes("empins_yn1")
emit("A010", "대상: 30~49세 여성 중 2022년 고용보험 가입 이력자(empins_yn1==1) / 분자: 육아휴직급여 연간 수급(empins_parentleave_yn1==1, 사후지급금 제외 변수) / 사용 변수: age, gender, empins_yn1, empins_parentleave_yn1, indwgt",
     True, [cell_ratio(den, yes("empins_parentleave_yn1"), [])])

# A011 시간제보육 지원 연간 수혜 아동 수, 시도별
base = yes("childcare_time_yn1")
emit("A011", "대상: 2022년 시간제보육 지원을 한 번이라도 받은 사람(childcare_time_yn1==1) / 산출: 인원(indwgt 합계) / 분류: 시도 / 사용 변수: childcare_time_yn1, sido, indwgt",
     False, [cell_count(base & (sido == k), [nm]) for k, nm in SIDO.items()],
     note="표본의 수혜 아동이 36명이어서 시도별 칸의 관측 수가 매우 적음(0건 칸은 null)")

# A012 65세 이상 종합병원 입원자의 종합병원 평균 재원일수, 65~74 / 75~84 / 85+
base = (age >= 65) & (df["nhi_in_gehospital_dur"] > 0)
emit("A012", "대상: 65세 이상이면서 종합병원 입원 이력자(nhi_in_gehospital_dur>0) / 대상 변수: 종합병원 재원일수(nhi_in_gehospital_dur) 평균 / 분류: 65~74세, 75~84세, 85세 이상 / 사용 변수: age, nhi_in_gehospital_dur, indwgt",
     False, [cell_mean(base & between(lo, hi), "nhi_in_gehospital_dur", [nm]) for nm, lo, hi in OLD3])

# A013 근로장려금 수급 대상자의 소득 5분위 구성비(분위 경계는 전체 인구 기준)
base = yes("itc_yn")
emit("A013", "대상: 근로장려금 수급 대상자(itc_yn==1) / 산출: 소득 5분위 구성비(분위 경계는 전체 인구의 균등화 가처분소득 개인 가중 20·40·60·80% 분위값) / 사용 변수: itc_yn, p_dinc, hnum, hid, indwgt / n은 대상자 전체, n_num은 해당 분위 관측 수",
     True, [cell_ratio(base, QUINT == k, [f"{k}분위"]) for k in range(1, 6)])

# A014 주택 외 건축물 보유 가구 비율, 가구주 연령대별(가구 단위)
grp = [("40세 미만", 0, 39), ("40~59세", 40, 59), ("60세 이상", 60, 999)]
emit("A014", "대상: 전체 가구(가구주 행) / 분자: 가구 시가표준액_건축물(주택 제외) 합계 > 0(h_ptax_building>0) / 분류: 가구주 연령대(40세 미만, 40~59세, 60세 이상) / 사용 변수: head, age, h_ptax_building, hhwgt",
     True, [cell_ratio(HEAD & between(lo, hi), df["h_ptax_building"] > 0, [nm], w=HW) for nm, lo, hi in grp])

# A015 긴급복지 생계지원 연간 수급자의 평균 수급 개월 수
emit("A015", "대상: 2022년 긴급복지 생계지원 수급자(aid_live_yn1==1) / 대상 변수: 수급기간(aid_live_dur, 개월) 평균 / 사용 변수: aid_live_yn1, aid_live_dur, indwgt",
     False, [cell_mean(yes("aid_live_yn1"), "aid_live_dur", [])])

# A016 65세 이상 인구 대비 장기요양 수급자 비율, 연령 × 성
emit("A016", "대상: 65세 이상 인구 / 분자: 노인장기요양 연중 수급(ltcare_bn_yn==1) / 분류: 연령(65~74, 75~84, 85세 이상) × 성 / 사용 변수: age, gender, ltcare_bn_yn, indwgt",
     True, [cell_ratio(between(lo, hi) & (gender == g), yes("ltcare_bn_yn"), [nm, gn])
            for nm, lo, hi in OLD3 for g, gn in GENDER.items()])

# A017 국민내일배움카드 정부지원금 75% 분위수, 연령 구간별
base = yes("vocaedu_yn")
grp = [("35세 미만", 0, 34), ("35~49세", 35, 49), ("50세 이상", 50, 999)]
emit("A017", "대상: 2022년 국민내일배움카드 정부지원 수혜자(vocaedu_yn==1) / 대상 변수: 정부지원금(vocaedu_amt) 가중 75% 분위수 / 분류: 35세 미만, 35~49세, 50세 이상 / 사용 변수: vocaedu_yn, vocaedu_amt, age, indwgt",
     False, [cell_quant(base & between(lo, hi), "vocaedu_amt", 0.75, [nm]) for nm, lo, hi in grp])

# A018 군인연금 가입자 본인부담 보험료 총액
emit("A018", "대상: 2022년 군인연금 가입자(milp_yn1==1) / 대상 변수: 보험료 납부액(milp_premium_amt, 본인부담) 가중 합계 / 사용 변수: milp_yn1, milp_premium_amt, indwgt",
     False, [cell_sum(yes("milp_yn1"), "milp_premium_amt", [])],
     note="질문이 2022년 납부 총액을 묻고 있어 연간 가입자 전체(milp_yn1==1, 보험료 값이 있는 350명)로 합산함. 12.31. 기준 가입자(milp_yn2==1)로 한정하면 합계가 작아지나 그 해석은 채택하지 않음")

# A019 7~18세 방과후학교 자유수강권 지원 비율, 교육급여 수급권(연간) 유무별
den = between(7, 18)
emit("A019", "대상: 7~18세 인구 / 분자: 방과후학교 자유수강권 지원(pubedu_aftsch_yn==1) / 분류: 교육급여 수급권 연간 보유 여부(nbls_edu_yn1==1) / 사용 변수: age, pubedu_aftsch_yn, nbls_edu_yn1, indwgt",
     True, [cell_ratio(den & yes("nbls_edu_yn1"), yes("pubedu_aftsch_yn"), ["교육급여 수급권 있음"]),
            cell_ratio(den & ~yes("nbls_edu_yn1"), yes("pubedu_aftsch_yn"), ["교육급여 수급권 없음"])])

# A020 대구·경북 가구 재산 구간별 가구 수
bins = [("1억원 미만", -np.inf, 1e8), ("1억원 이상 3억원 미만", 1e8, 3e8),
        ("3억원 이상 6억원 미만", 3e8, 6e8), ("6억원 이상", 6e8, np.inf)]
emit("A020", "대상: 대구·경북 가구(가구주 행) / 산출: 가구 수(hhwgt 합계) / 분류: 시도 × 가구 재산(h_prop) 4구간 / 사용 변수: head, sido, h_prop, hhwgt",
     False, [cell_count(HEAD & (sido == k) & (df["h_prop"] >= lo) & (df["h_prop"] < hi), [SIDO[k], nm], w=HW)
             for k in (3, 15) for nm, lo, hi in bins])

# A021 50세 이상 남성 일용근로소득자의 평균 일용근로소득, 건강보험 가입 구분별
base = (age >= 50) & (gender == 1) & (df["dainc_sum"] > 0)
emit("A021", "대상: 50세 이상 남성 중 2022년 귀속 일용소득 총지급금액 > 0(dainc_sum>0) / 대상 변수: dainc_sum 평균 / 분류: 건강보험 가입 구분(지역가입 1·2, 직장가입 5·6, 의료급여 7·8) / 사용 변수: age, gender, dainc_sum, nhi_type, indwgt",
     False, [cell_mean(base & (NHI3 == k), "dainc_sum", [k]) for k in ("지역가입", "직장가입", "의료급여")],
     note="2022년 귀속 과세자료 변수 dainc_sum(일용소득_총지급금액)을 사용. 개인 일차소득의 일용소득(p_dainc)은 대상자는 같고 금액이 개인별로 소폭 달라 평균이 근소하게 다름")

# A022 노인일자리 사회서비스형 참여자 중 중도포기 비율
emit("A022", "대상: 2022년 노인일자리 사회서비스형 참여자(oldwork_type2_yn1==1) / 분자: 중도포기(oldwork_type2_end_yn==1) / 사용 변수: oldwork_type2_yn1, oldwork_type2_end_yn, indwgt",
     True, [cell_ratio(yes("oldwork_type2_yn1"), yes("oldwork_type2_end_yn"), [])])

# A023 장기요양 수급자의 판정 등급별 구성비
base = yes("ltcare_bn_yn") & df["ltcare_grade"].notna()
gl = {1: "1등급", 2: "2등급", 3: "3등급", 4: "4등급", 5: "5등급", 6: "인지지원등급"}
emit("A023", "대상: 2022년 노인장기요양 수급자(ltcare_bn_yn==1) / 산출: 판정 등급(ltcare_grade) 구성비 / 사용 변수: ltcare_bn_yn, ltcare_grade, indwgt / n은 수급자 전체, n_num은 해당 등급 관측 수",
     True, [cell_ratio(base, df["ltcare_grade"] == k, [nm]) for k, nm in gl.items()])

# A024 7~18세 교육급여 교육활동지원비 실지급 비율, 상대 빈곤 여부별
den = between(7, 18)
num = df["nbls_edu_amt1"] > 0
emit("A024", "대상: 7~18세 인구 / 분자: 교육급여 교육활동지원비 지급액 > 0(nbls_edu_amt1>0) / 분류: 상대 빈곤 여부(균등화 가처분소득 < 전국 중위값의 50%) / 사용 변수: age, nbls_edu_amt1, p_dinc, hnum, hid, indwgt",
     True, [cell_ratio(den & POOR, num, ["빈곤"]), cell_ratio(den & ~POOR, num, ["비빈곤"])])

# A025 출산전후휴가 급여 수급자의 1인당 평균 수급일수
emit("A025", "대상: 2022년 출산전후휴가 급여 수급자(empins_matleave_yn1==1) / 대상 변수: 수급기간(empins_matleave_dur, 일) 평균 / 사용 변수: empins_matleave_yn1, empins_matleave_dur, indwgt",
     False, [cell_mean(yes("empins_matleave_yn1"), "empins_matleave_dur", [])])

# A026 심한 장애 18~64세 등록장애인 중 12월 기준 장애인연금 수급 비율, 성별
den = yes("dis_yn") & (df["dis_grade_1"] == 1) & between(18, 64)
emit("A026", "대상: 18~64세 등록장애인(dis_yn==1) 중 종합장애정도 심한 장애(dis_grade_1==1) / 분자: 2022년 12월 기준 장애인연금 수급(disp_yn2==1) / 분류: 성 / 사용 변수: dis_yn, dis_grade_1, age, disp_yn2, gender, indwgt",
     True, [cell_ratio(den & (gender == g), yes("disp_yn2"), [gn]) for g, gn in GENDER.items()])

# A027 주야간보호 이용 수급자의 연간 이용일수 중위수
emit("A027", "대상: 2022년 주야간보호 이용 장기요양 수급자(ltcare_daynight_yn==1) / 대상 변수: 주야간보호 이용일수(ltcare_daynight_freq) 가중 중위수 / 사용 변수: ltcare_daynight_yn, ltcare_daynight_freq, indwgt",
     False, [cell_quant(yes("ltcare_daynight_yn"), "ltcare_daynight_freq", 0.5, [])])

# A028 국민취업지원제도 12월 31일 기준 참여 인원, 참여유형별
base = yes("kua_yn2")
emit("A028", "대상: 2022.12.31. 기준 국민취업지원제도 참여자(kua_yn2==1) / 산출: 인원(indwgt 합계) / 분류: 참여유형(kua_type 1유형, 2유형) / 사용 변수: kua_yn2, kua_type, indwgt",
     False, [cell_count(base & (df["kua_type"] == k), [nm]) for k, nm in ((1, "1유형"), (2, "2유형"))])

# A029 경기 0~5세 중 보육료 지원 연간 수혜 비율, 0~2세 / 3~5세
emit("A029", "대상: 경기 거주 0~5세 / 분자: 보육료지원 연간 수혜(childcare_yn1==1) / 분류: 0~2세, 3~5세 / 사용 변수: sido, age, childcare_yn1, indwgt",
     True, [cell_ratio((sido == 9) & between(lo, hi), yes("childcare_yn1"), [nm])
            for nm, lo, hi in (("0~2세", 0, 2), ("3~5세", 3, 5))])

# A030 장애수당 연간 지급 총액, 성별
emit("A030", "대상: 2022년 장애수당 수급자(disp_bn_amt 값 있음) / 대상 변수: 장애수당 급여액(disp_bn_amt) 가중 합계 / 분류: 성 / 사용 변수: disp_bn_amt, gender, indwgt",
     False, [cell_sum(gender == g, "disp_bn_amt", [gn]) for g, gn in GENDER.items()])

# A031 방과후학교 자유수강권 지원 학생의 1인당 평균 지원액, 연령대별
base = yes("pubedu_aftsch_yn")
emit("A031", "대상: 2022년 방과후학교 자유수강권 지원 수혜자(pubedu_aftsch_yn==1) / 대상 변수: 지원액(pubedu_aftsch_amt) 평균 / 분류: 7~12세, 13~15세, 16~18세 / 사용 변수: pubedu_aftsch_yn, pubedu_aftsch_amt, age, indwgt",
     False, [cell_mean(base & between(lo, hi), "pubedu_aftsch_amt", [nm])
             for nm, lo, hi in (("7~12세", 7, 12), ("13~15세", 13, 15), ("16~18세", 16, 18))])

# A032 생계급여 연간 수급 65세 이상 1인 가구원 중 종합병원 입원 비율
den = yes("nbls_live_yn1") & (age >= 65) & (hnum == 1)
emit("A032", "대상: 2022년 생계급여 연간 수급(nbls_live_yn1==1) 65세 이상 1인 가구 가구원 / 분자: 종합병원 입원(nhi_in_gehospital_dur>0) / 사용 변수: nbls_live_yn1, age, hnum, nhi_in_gehospital_dur, indwgt",
     True, [cell_ratio(den, df["nhi_in_gehospital_dur"] > 0, [])])

# A033 부산·울산·경남 거주자 상대 빈곤율(전국 빈곤선), 연령대 3구간
reg = sido.isin([2, 7, 16])
emit("A033", "대상: 부산·울산·경남 거주자(3개 시도 합산) / 분자: 상대 빈곤(전국 균등화 가처분소득 개인 가중 중위값의 50% 미만) / 분류: 연령대 3구간 / 사용 변수: sido, age, p_dinc, hnum, hid, indwgt",
     True, [cell_ratio(reg & between(lo, hi), POOR, [nm]) for nm, lo, hi in AGE3])

# A034 광주·전북·전남 12월 기준 기초연금 수급자의 연간 급여액 평균, 수급유형 × 성
base = sido.isin([5, 13, 14]) & yes("bp_yn2")
tl = {1: "단독", 2: "부부 1인 수급", 3: "부부 2인 수급"}
emit("A034", "대상: 광주·전북·전남 거주 2022년 12월 기준 기초연금 수급자(bp_yn2==1) / 대상 변수: 연간 기초연금 급여액(bp_amt) 평균 / 분류: 수급유형(bp_type) × 성 / 사용 변수: sido, bp_yn2, bp_amt, bp_type, gender, indwgt",
     False, [cell_mean(base & (df["bp_type"] == k) & (gender == g), "bp_amt", [nm, gn])
             for k, nm in tl.items() for g, gn in GENDER.items()])

# A035 만성폐쇄성폐질환 입원자 수, 성별
emit("A035", "대상: 2022년 만성폐쇄성폐질환 입원자(nhi_copd_yn==1) / 산출: 인원(indwgt 합계) / 분류: 성 / 사용 변수: nhi_copd_yn, gender, indwgt",
     False, [cell_count(yes("nhi_copd_yn") & (gender == g), [gn]) for g, gn in GENDER.items()])

# A036 60세 이상 공적연금 총연금수령액 중위수, 연령 구간별
base = (age >= 60) & (df["pubpen_inc"] > 0)
grp = [("60~64세", 60, 64), ("65~69세", 65, 69), ("70~79세", 70, 79), ("80세 이상", 80, 999)]
emit("A036", "대상: 60세 이상 중 2022년 귀속 공적연금 총연금수령액 > 0(pubpen_inc>0) / 대상 변수: pubpen_inc 가중 중위수 / 분류: 60~64세, 65~69세, 70~79세, 80세 이상 / 사용 변수: age, pubpen_inc, indwgt",
     False, [cell_quant(base & between(lo, hi), "pubpen_inc", 0.5, [nm]) for nm, lo, hi in grp])

# A037 시간연장형 보육료 연간 수혜 아동 중 12월 지원 비율
emit("A037", "대상: 2022년 시간연장형 보육료 연간 수혜자(childcare_longtime_yn1==1) / 분자: 12월 기준 지원(childcare_longtime_yn2==1) / 사용 변수: childcare_longtime_yn1, childcare_longtime_yn2, indwgt",
     True, [cell_ratio(yes("childcare_longtime_yn1"), yes("childcare_longtime_yn2"), [])])

# A038 장애인활동지원 연간 이용자의 1인당 결제금액 평균
emit("A038", "대상: 2022년 장애인활동지원 연간 이용자(disvou_act_yn1==1) / 대상 변수: 결제금액(disvou_act_amt) 평균 / 사용 변수: disvou_act_yn1, disvou_act_amt, indwgt",
     False, [cell_mean(yes("disvou_act_yn1"), "disvou_act_amt", [])])

# A039 실업급여 수급기간 연기 신고처리자의 연기 사유 구성비
base = yes("unempbn_bnextended_yn") & df["unempbn_bnextended_reason"].notna()
rl = {1: "임신·출산·육아", 2: "본인 질병·부상", 5: "병역법에 따른 의무복무", 6: "범죄혐의로 인한 구속 또는 형의 집행", 8: "기타"}
emit("A039", "대상: 2022년 실업급여 수급기간 연기 신고처리자(unempbn_bnextended_yn==1) / 산출: 연기사유(unempbn_bnextended_reason) 구성비 / 사용 변수: unempbn_bnextended_yn, unempbn_bnextended_reason, indwgt / n은 대상자 전체, n_num은 해당 사유 관측 수",
     True, [cell_ratio(base, df["unempbn_bnextended_reason"] == k, [nm]) for k, nm in rl.items()])

# A040 65세 이상 여성 1인 가구의 노인맞춤돌봄서비스 연간 이용 비율, 수도권/비수도권
den = (gender == 2) & (age >= 65) & (hnum == 1)
cap = sido.isin([1, 4, 9])
emit("A040", "대상: 65세 이상 여성 1인 가구 가구원 / 분자: 노인맞춤돌봄서비스 연간 이용(oldcare_yn1==1) / 분류: 수도권(서울·인천·경기), 비수도권 / 사용 변수: gender, age, hnum, oldcare_yn1, sido, indwgt",
     True, [cell_ratio(den & cap, yes("oldcare_yn1"), ["수도권"]), cell_ratio(den & ~cap, yes("oldcare_yn1"), ["비수도권"])])

# A041 사학연금 연간 가입자의 본인부담 보험료 1인당 평균, 성별
emit("A041", "대상: 2022년 사립학교교직원연금 연간 가입자(privschp_yn1==1) / 대상 변수: 보험료 납부액(privschp_premium_amt, 본인부담) 평균 / 분류: 성 / 사용 변수: privschp_yn1, privschp_premium_amt, gender, indwgt",
     False, [cell_mean(yes("privschp_yn1") & (gender == g), "privschp_premium_amt", [gn]) for g, gn in GENDER.items()])

# A042 65세 이상 남성 공무원연금 정기연금 수급자의 연간 급여액 25% 분위수
m = (age >= 65) & (gender == 1) & yes("govp_pension_yn")
emit("A042", "대상: 65세 이상 남성 공무원연금 정기연금 수급자(govp_pension_yn==1) / 대상 변수: 정기연금 급여액(govp_pension_amt) 가중 25% 분위수 / 사용 변수: age, gender, govp_pension_yn, govp_pension_amt, indwgt",
     False, [cell_quant(m, "govp_pension_amt", 0.25, [])])

# A043 육아휴직급여 연간 수급자 중 12월 수급 비율, 성별
emit("A043", "대상: 2022년 육아휴직급여(사후지급금 제외) 연간 수급자(empins_parentleave_yn1==1) / 분자: 12월 기준 수급(empins_parentleave_yn2==1) / 분류: 성 / 사용 변수: empins_parentleave_yn1, empins_parentleave_yn2, gender, indwgt",
     True, [cell_ratio(yes("empins_parentleave_yn1") & (gender == g), yes("empins_parentleave_yn2"), [gn]) for g, gn in GENDER.items()])

# A044 금융소득 원천징수세액 합계, 특별·광역시 / 도
metro = sido.isin([1, 2, 3, 4, 5, 6, 7, 8])
emit("A044", "대상: 전체 인구 / 대상 변수: 금융소득 원천징수세액 합계금액(fainc_tax) 가중 합계 / 분류: 특별·광역시(시도 1~8), 도 지역(시도 9~17) / 사용 변수: fainc_tax, sido, indwgt",
     False, [cell_sum(metro, "fainc_tax", ["특별·광역시"]), cell_sum(~metro, "fainc_tax", ["도 지역"])])

# A045 가구주 75세 이상 가구의 가구 공적이전소득 평균(0원 포함), 가구원수별
base = HEAD & (age >= 75)
emit("A045", "대상: 가구주 75세 이상 가구(가구주 행) / 대상 변수: 가구 공적이전소득(h_pubinc, 0원 포함) 평균(hhwgt) / 분류: 가구원수 4구간 / 사용 변수: head, age, h_pubinc, hnum, hhwgt",
     False, [cell_mean(base & (HN4 == k), "h_pubinc", [k], w=HW) for k in HN4_ORDER])

# A046 긴급복지 생계지원 연간 수급자 중 12월 기준 수급 비율
emit("A046", "대상: 2022년 긴급복지 생계지원 연간 수급자(aid_live_yn1==1) / 분자: 12월 기준 수급(aid_live_yn2==1) / 사용 변수: aid_live_yn1, aid_live_yn2, indwgt",
     True, [cell_ratio(yes("aid_live_yn1"), yes("aid_live_yn2"), [])])

# A047 구직급여 수급자 수, 연간 수급일수 구간별
base = yes("unempbn_jobseekbn_yn")
d = df["unempbn_jobseekbn_dur"]
emit("A047", "대상: 2022년 구직급여 수급자(unempbn_jobseekbn_yn==1) / 산출: 인원(indwgt 합계) / 분류: 연간 수급일수(unempbn_jobseekbn_dur) 90일 미만, 90~149일, 150일 이상 / 사용 변수: unempbn_jobseekbn_yn, unempbn_jobseekbn_dur, indwgt",
     False, [cell_count(base & (d < 90), ["90일 미만"]), cell_count(base & (d >= 90) & (d < 150), ["90~149일"]),
             cell_count(base & (d >= 150), ["150일 이상"])])

# A048 등록장애인의 건강보험 가입 구분 구성비, 종합장애정도별
base = yes("dis_yn")
dl = {1: "심한 장애", 2: "심하지 않은 장애"}
emit("A048", "대상: 2022.12.31. 기준 등록장애인(dis_yn==1) / 산출: 건강보험 가입 구분(지역가입 1·2, 직장가입 5·6, 의료급여 7·8) 구성비 / 분류: 종합장애정도(dis_grade_1) / 사용 변수: dis_yn, dis_grade_1, nhi_type, indwgt / n은 해당 장애정도 등록장애인 전체, n_num은 해당 가입 구분 관측 수",
     True, [cell_ratio(base & (df["dis_grade_1"] == k), NHI3 == t, [nm, t])
            for k, nm in dl.items() for t in ("지역가입", "직장가입", "의료급여")])

# ---------- 기록 ----------
with open(OUT, "w", encoding="utf-8") as f:
    for r in ROWS:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print("rows", len(ROWS), "questions", len({r["id"] for r in ROWS}))
print("median eq income", MED, "quintile bounds", QB)
for r in ROWS:
    print(r["id"], r["reading_no"], "pct" if r["pct"] else "val",
          [(c["labels"], None if c["value"] is None else round(c["value"], 3), c["n"], c.get("n_num")) for c in r["cells"]])
