# -*- coding: utf-8 -*-
"""독립 검산(check_1): 질문 문장만 보고 분석 자료에서 직접 계산.
- 개인 단위: indwgt 가중 / 가구 단위: 가구주 행(head == 1)에 hhwgt 가중
- 여부 변수는 == 1 로 판별(결측·0 은 해당 없음), 평균·합계·분위수는 값이 있는 행만
- 가중 분위수: 오름차순 정렬 후 가중치 누적합이 전체의 q배에 처음 이르는 값
산출: ../truth/check_1.jsonl
"""
import json
import numpy as np
import pandas as pd

P = "/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet"
OUT = "/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r4/truth/check_1.jsonl"

df = pd.read_parquet(P)
N = len(df)
W = df["indwgt"].to_numpy(float)
HW = df["hhwgt"].to_numpy(float)
age = df["age"].to_numpy()
sido = df["sido"].to_numpy()
gender = df["gender"].to_numpy()
hnum = df["hnum"].to_numpy()
HEAD = (df["head"] == 1).to_numpy()

SIDO = {1: "서울", 2: "부산", 3: "대구", 4: "인천", 5: "광주", 6: "대전", 7: "울산", 8: "세종", 9: "경기",
        10: "강원", 11: "충북", 12: "충남", 13: "전북", 14: "전남", 15: "경북", 16: "경남", 17: "제주"}
SEX = {1: "남", 2: "여"}
METRO = np.isin(sido, [1, 4, 9])  # 수도권: 서울·인천·경기


def num(col):
    """수치형(결측 허용 정수형 포함)을 float 배열로. 결측은 NaN."""
    return df[col].astype("float64").to_numpy()


def is1(col):
    """여부 변수 == 1 (결측·0 은 거짓)."""
    return num(col) == 1


def has(col):
    """값이 있는 행."""
    return ~np.isnan(num(col))


def wquant(values, weights, q):
    order = np.argsort(values, kind="mergesort")
    v = values[order]
    c = np.cumsum(weights[order])
    idx = int(np.searchsorted(c, q * c[-1], side="left"))  # 누적합이 q배에 처음 이르는 위치
    return float(v[idx])


# ---- 셀 계산기 ---------------------------------------------------------
def c_count(labels, mask, w=W):
    n = int(mask.sum())
    return {"labels": labels, "value": float(w[mask].sum()) if n else None, "n": n}


def c_ratio(labels, den, numr, w=W):
    numr = numr & den
    n = int(den.sum())
    val = float(100.0 * w[numr].sum() / w[den].sum()) if n else None
    return {"labels": labels, "value": val, "n": n, "n_num": int(numr.sum())}


def c_mean(labels, col, mask, w=W):
    x = num(col)
    m = mask & ~np.isnan(x)
    n = int(m.sum())
    val = float((x[m] * w[m]).sum() / w[m].sum()) if n else None
    return {"labels": labels, "value": val, "n": n}


def c_sum(labels, col, mask, w=W):
    x = num(col)
    m = mask & ~np.isnan(x)
    n = int(m.sum())
    val = float((x[m] * w[m]).sum()) if n else None
    return {"labels": labels, "value": val, "n": n}


def c_quant(labels, col, mask, q, w=W):
    x = num(col)
    m = mask & ~np.isnan(x)
    n = int(m.sum())
    val = wquant(x[m], w[m], q) if n else None
    return {"labels": labels, "value": val, "n": n}


rows = []


def emit(qid, reading, pct, cells, reading_no=1, ambiguous=False, note=""):
    rows.append({"id": qid, "turn": 1, "reading_no": reading_no, "reading": reading, "pct": pct,
                 "cells": cells, "ambiguous": ambiguous, "note": note})


def bands(edges_labels):
    """[(라벨, 하한, 상한(포함) 또는 None)] -> [(라벨, mask)] (연령)."""
    out = []
    for lab, lo, hi in edges_labels:
        m = age >= lo
        if hi is not None:
            m = m & (age <= hi)
        out.append((lab, m))
    return out


# ---- 공통 파생: 균등화 가처분소득, 소득 5분위, 상대 빈곤 ------------------
eq = (df.groupby("hid")["p_dinc"].transform("sum").to_numpy(float)) / np.sqrt(hnum.astype(float))
ALL = np.ones(N, bool)
qb = [wquant(eq, W, q) for q in (0.2, 0.4, 0.6, 0.8)]
quint = 1 + sum((eq >= b).astype(int) for b in qb)  # 경계값 이상이면 위 분위
pov_line = 0.5 * wquant(eq, W, 0.5)
POOR = eq < pov_line

AGE6 = bands([("0~17세", 0, 17), ("18~34세", 18, 34), ("35~49세", 35, 49), ("50~64세", 50, 64),
              ("65~74세", 65, 74), ("75세 이상", 75, None)])
AGE3 = bands([("0~17세", 0, 17), ("18~64세", 18, 64), ("65세 이상", 65, None)])
NHI3 = [("지역가입", np.isin(num("nhi_type"), [1, 2])), ("직장가입", np.isin(num("nhi_type"), [5, 6])),
        ("의료급여", np.isin(num("nhi_type"), [7, 8]))]

# =========================================================================
# A001 65세 이상 중 상급종합병원 외래 이용(내원일수 1일 이상) 비율, 시도별
den = age >= 65
numr = num("nhi_out_tehospital_dur") > 0
emit("A001", "대상: 65세 이상 인구 / 분자: 2022년 상급종합병원 외래 내원일수 1일 이상(nhi_out_tehospital_dur > 0) / 분류: 시도 / 사용 변수: age, sido, nhi_out_tehospital_dur, indwgt",
     True, [c_ratio([SIDO[s]], den & (sido == s), numr) for s in range(1, 18)])

# A002 12월 기준 생계급여·주거급여(임차) 동시 수급 인원, 연령 6구간
m = is1("nbls_live_yn2") & is1("nbls_house_yn2")
emit("A002", "대상: 2022년 12월 기준 생계급여 수급(nbls_live_yn2 == 1)이면서 주거급여 임차급여 수급(nbls_house_yn2 == 1)인 사람 / 대상 변수: 가중 인원 / 분류: 연령대 6구간 / 사용 변수: nbls_live_yn2, nbls_house_yn2, age, indwgt",
     False, [c_count([lab], m & am) for lab, am in AGE6])

# A003 장애수당 연간 수급자의 평균 장애수당 급여액, 생계급여 연간 수급 여부별
base = is1("disp_bn_yn1")
live = is1("nbls_live_yn1")
emit("A003", "대상: 2022년 장애수당 수급자(disp_bn_yn1 == 1) / 대상 변수: 장애수당 연간 급여액(disp_bn_amt) 평균 / 분류: 2022년 생계급여 수급 여부(nbls_live_yn1 == 1, 그 밖) / 사용 변수: disp_bn_yn1, disp_bn_amt, nbls_live_yn1, indwgt",
     False, [c_mean(["생계급여 수급"], "disp_bn_amt", base & live), c_mean(["생계급여 비수급"], "disp_bn_amt", base & ~live)])

# A004 0~6세 중 12월 기준 보육료 지원 비율, 연령 구간별
ab = bands([("0세", 0, 0), ("1세", 1, 1), ("2세", 2, 2), ("3~4세", 3, 4), ("5~6세", 5, 6)])
emit("A004", "대상: 0~6세 아동 / 분자: 2022년 12월 기준 보육료지원(childcare_yn2 == 1) / 분류: 연령(0세, 1세, 2세, 3~4세, 5~6세) / 사용 변수: age, childcare_yn2, indwgt",
     True, [c_ratio([lab], am, is1("childcare_yn2")) for lab, am in ab])

# A005 (가구) 임차 보증금이 있는 가구의 가구 임차 보증금 합계 중위수, 가구원수 4구간
hb = [("1인", hnum == 1), ("2인", hnum == 2), ("3인", hnum == 3), ("4인 이상", hnum >= 4)]
base = HEAD & (num("h_ee_deposit_amt_ptot") > 0)
emit("A005", "대상: 가구원 합산 임차 보증금이 0보다 큰 가구(가구주 행, h_ee_deposit_amt_ptot > 0) / 대상 변수: 가구 임차 보증금 합계(h_ee_deposit_amt_ptot) 가중 중위수 / 분류: 가구원수 4구간 / 사용 변수: head, hhwgt, hnum, h_ee_deposit_amt_ptot",
     False, [c_quant([lab], "h_ee_deposit_amt_ptot", base & hm, 0.5, w=HW) for lab, hm in hb])

# A006 등록장애인의 주장애유형 구성비
DT = {1: "간", 2: "뇌병변", 3: "뇌전증", 4: "시각", 5: "신장", 6: "심장", 7: "안면", 8: "언어", 9: "자폐성장애",
      10: "장루·요루", 11: "정신", 12: "지적장애", 13: "지체", 14: "청각", 15: "호흡기"}
base = is1("dis_yn") & has("dis_type_1")
emit("A006", "대상: 2022.12.31. 기준 등록장애인(dis_yn == 1) / 대상 변수: 주장애유형(dis_type_1) 구성비 / 분류: 주장애유형 15종 / 사용 변수: dis_yn, dis_type_1, indwgt",
     True, [c_ratio([DT[k]], base, num("dis_type_1") == k) for k in range(1, 16)])

# A007 65세 이상 12월 기준 기초연금 수급률, 연령 4구간 × 성
ab = bands([("65~69세", 65, 69), ("70~74세", 70, 74), ("75~79세", 75, 79), ("80세 이상", 80, None)])
emit("A007", "대상: 65세 이상 인구 / 분자: 2022년 12월 기준 기초연금 수급(bp_yn2 == 1) / 분류: 연령(65~69, 70~74, 75~79, 80세 이상) × 성 / 사용 변수: age, gender, bp_yn2, indwgt",
     True, [c_ratio([lab, SEX[g]], am & (gender == g), is1("bp_yn2")) for lab, am in ab for g in (1, 2)])

# A008 청년내일채움공제 지급액(세전) 평균
emit("A008", "대상: 2022년 청년내일채움공제 만기·중도해지 지급금 수령자(youthemp_amt1 값이 있는 사람) / 대상 변수: 지급액(세전) youthemp_amt1 평균 / 분류: 없음 / 사용 변수: youthemp_amt1, indwgt",
     False, [c_mean([], "youthemp_amt1", ALL)])

# A009 종합병원 입원 요양급여비용 총액 합계, 건강보험 가입 구분 × 연령대 3구간
emit("A009", "대상: 전체 인구(값이 있는 행) / 대상 변수: (입원) 종합병원 요양급여비용 총액(nhi_in_gehospital_amt) 가중 합계 / 분류: 건강보험 가입 구분(nhi_type 1·2 지역, 5·6 직장, 7·8 의료급여) × 연령대 3구간 / 사용 변수: nhi_in_gehospital_amt, nhi_type, age, indwgt",
     False, [c_sum([nl, al], "nhi_in_gehospital_amt", nm & am) for nl, nm in NHI3 for al, am in AGE3])

# A010 자활근로(기초) 연간 참여자 중 10월 31일 기준 참여 비율
emit("A010", "대상: 2022년 자활근로(기초) 참여자(self_yn1 == 1) / 분자: 2022.10.31. 기준 참여(self_yn2 == 1) / 분류: 없음 / 사용 변수: self_yn1, self_yn2, indwgt",
     True, [c_ratio([], is1("self_yn1"), is1("self_yn2"))])

# A011 65세 이상 상대 빈곤율, 기초연금 연간 수급 여부별
old = age >= 65
bp = is1("bp_yn1")
emit("A011", "대상: 65세 이상 인구 / 분자: 상대 빈곤(균등화 가처분소득 < 전체 인구 개인 가중 중위값의 50%) / 분류: 2022년 기초연금 수급 여부(bp_yn1 == 1, 그 밖) / 사용 변수: age, bp_yn1, p_dinc, hnum, hid, indwgt",
     True, [c_ratio(["기초연금 수급"], old & bp, POOR), c_ratio(["기초연금 비수급"], old & ~bp, POOR)])

# A012 (가구) 부산·울산·경남의 가구 공적이전소득 1,000만 원 이상 가구 수
m = HEAD & (num("h_pubinc") >= 10_000_000)
emit("A012", "대상: 부산·울산·경남 가구(가구주 행) 중 가구 공적이전소득(h_pubinc) 1,000만 원 이상 / 대상 변수: 가중 가구 수 / 분류: 시도(부산, 울산, 경남) / 사용 변수: head, hhwgt, sido, h_pubinc",
     False, [c_count([SIDO[s]], m & (sido == s), w=HW) for s in (2, 7, 16)])

# A013 응급실 이용자의 평균 응급실 재원일수, 연령 5구간
ab = bands([("0~17세", 0, 17), ("18~39세", 18, 39), ("40~64세", 40, 64), ("65~79세", 65, 79), ("80세 이상", 80, None)])
emit("A013", "대상: 2022년 응급실 재원일수 값이 있는 사람(nhi_in_emergency_dur > 0) / 대상 변수: 응급실 재원일수(nhi_in_emergency_dur) 평균 / 분류: 연령(0~17, 18~39, 40~64, 65~79, 80세 이상) / 사용 변수: nhi_in_emergency_dur, age, indwgt",
     False, [c_mean([lab], "nhi_in_emergency_dur", am & (num("nhi_in_emergency_dur") > 0)) for lab, am in ab])

# A014 18~64세·고용보험 미가입·국민연금 미가입자 중 일용근로소득 보유 비율, 성별
den = (age >= 18) & (age <= 64) & ~is1("empins_yn1") & ~is1("np_yn")
emit("A014", "대상: 18~64세이면서 2022년 고용보험 가입 이력 없음(empins_yn1 != 1)·국민연금 가입 이력 없음(np_yn != 1) / 분자: 2022년 일용소득 총지급금액이 0보다 큼(dainc_sum > 0) / 분류: 성 / 사용 변수: age, gender, empins_yn1, np_yn, dainc_sum, indwgt",
     True, [c_ratio([SEX[g]], den & (gender == g), num("dainc_sum") > 0) for g in (1, 2)],
     note="p_dainc > 0 으로 판별해도 분자 집단이 같음")

# A015 주야간보호서비스 이용자의 연간 이용일수 25% 분위수
emit("A015", "대상: 주야간보호서비스 이용자(ltcare_daynight_yn == 1) / 대상 변수: 연간 이용일수(ltcare_daynight_freq) 가중 25% 분위수 / 분류: 없음 / 사용 변수: ltcare_daynight_yn, ltcare_daynight_freq, indwgt",
     False, [c_quant([], "ltcare_daynight_freq", is1("ltcare_daynight_yn"), 0.25)])

# A016 긴급복지 생계지원 연간 수급자 중 12월 수급 비율
emit("A016", "대상: 2022년 긴급복지 생계지원 수급자(aid_live_yn1 == 1) / 분자: 2022년 12월 기준 수급(aid_live_yn2 == 1) / 분류: 없음 / 사용 변수: aid_live_yn1, aid_live_yn2, indwgt",
     True, [c_ratio([], is1("aid_live_yn1"), is1("aid_live_yn2"))])

# A017 육아휴직급여 수급자의 남녀 구성비, 연령 3구간별
ab = bands([("30세 미만", 0, 29), ("30~34세", 30, 34), ("35세 이상", 35, None)])
base = is1("empins_parentleave_yn1")
emit("A017", "대상: 2022년 육아휴직급여 수급자(empins_parentleave_yn1 == 1, 사후지급금 제외) / 대상 변수: 연령대 안에서의 성별 구성비 / 분류: 연령(30세 미만, 30~34세, 35세 이상) × 성 / 사용 변수: empins_parentleave_yn1, age, gender, indwgt",
     True, [c_ratio([lab, SEX[g]], base & am, gender == g) for lab, am in ab for g in (1, 2)])

# A018 수도권 65세 이상 의료급여 수급권자 중 상급종합병원 입원자의 평균 상급종합병원 입원 요양급여비용
m = METRO & (age >= 65) & is1("nbls_medi_yn2") & (num("nhi_in_tehospital_dur") > 0)
emit("A018", "대상: 수도권(서울·인천·경기) 거주 65세 이상, 2022.12.31. 기준 의료급여 수급권자(nbls_medi_yn2 == 1), 상급종합병원 입원 재원일수 1일 이상 / 대상 변수: (입원) 상급종합병원 요양급여비용 총액(nhi_in_tehospital_amt) 평균 / 분류: 없음 / 사용 변수: sido, age, nbls_medi_yn2, nhi_in_tehospital_dur, nhi_in_tehospital_amt, indwgt",
     False, [c_mean([], "nhi_in_tehospital_amt", m)])

# A019 (가구) 건축물(주택 제외) 보유 가구 비율, 가구주 연령 3구간
ab = bands([("40세 미만", 0, 39), ("40~64세", 40, 64), ("65세 이상", 65, None)])
emit("A019", "대상: 전체 가구(가구주 행) / 분자: 가구원 합산 시가표준액_건축물(주택 제외)이 0보다 큰 가구(h_ptax_building > 0) / 분류: 가구주 연령(40세 미만, 40~64세, 65세 이상) / 사용 변수: head, hhwgt, age, h_ptax_building",
     True, [c_ratio([lab], HEAD & am, num("h_ptax_building") > 0, w=HW) for lab, am in ab])

# A020 생계급여 연간 급여액 합계, 수도권/비수도권
emit("A020", "대상: 2022년 생계급여 수급자(급여액 값이 있는 행) / 대상 변수: 생계급여 연간 급여액(nbls_live_amt) 가중 합계 / 분류: 수도권(서울·인천·경기), 비수도권 / 사용 변수: nbls_live_amt, sido, indwgt",
     False, [c_sum(["수도권"], "nbls_live_amt", METRO), c_sum(["비수도권"], "nbls_live_amt", ~METRO)])

# A021 18세 이상 등록장애인 중 12.31. 기준 의료급여 수급권자 인원, 권역별
REG = [("수도권", [1, 4, 9]), ("충청권", [6, 8, 11, 12]), ("호남권", [5, 13, 14]), ("영남권", [2, 3, 7, 15, 16]), ("강원·제주", [10, 17])]
m = (age >= 18) & is1("dis_yn") & is1("nbls_medi_yn2")
emit("A021", "대상: 18세 이상 등록장애인(dis_yn == 1)이면서 2022.12.31. 기준 의료급여 수급권자(nbls_medi_yn2 == 1) / 대상 변수: 가중 인원 / 분류: 권역(수도권, 충청권, 호남권, 영남권, 강원·제주) / 사용 변수: age, dis_yn, nbls_medi_yn2, sido, indwgt",
     False, [c_count([lab], m & np.isin(sido, ss)) for lab, ss in REG])

# A022 시간제보육 지원 아동의 평균 지원액(정부지원금), 시도별
base = is1("childcare_time_yn1")
emit("A022", "대상: 2022년 시간제보육지원을 받은 아동(childcare_time_yn1 == 1) / 대상 변수: 시간제보육지원 지원액(정부지원금, childcare_time_subsidy) 평균 / 분류: 시도 / 사용 변수: childcare_time_yn1, childcare_time_subsidy, sido, indwgt",
     False, [c_mean([SIDO[s]], "childcare_time_subsidy", base & (sido == s)) for s in range(1, 18)],
     note="관측이 36건으로 적어 시도 칸 모두 10건 미만이며 4개 시도는 0건")

# A023 고용보험 연간 가입자 중 구직급여 수급 비율, 연령 4구간
ab = bands([("30세 미만", 0, 29), ("30~49세", 30, 49), ("50~64세", 50, 64), ("65세 이상", 65, None)])
emit("A023", "대상: 2022년 고용보험 가입 이력자(empins_yn1 == 1) / 분자: 2022년 구직급여 수급(unempbn_jobseekbn_yn == 1) / 분류: 연령(30세 미만, 30~49세, 50~64세, 65세 이상) / 사용 변수: empins_yn1, unempbn_jobseekbn_yn, age, indwgt",
     True, [c_ratio([lab], is1("empins_yn1") & am, is1("unempbn_jobseekbn_yn")) for lab, am in ab])

# A024 의원 외래 이용자의 의원 외래 요양급여비용 중위수, 성 × 소득 5분위
base = num("nhi_out_clinic_dur") > 0
emit("A024", "대상: 2022년 의원 외래 내원일수 1일 이상(nhi_out_clinic_dur > 0) / 대상 변수: (외래) 의원 요양급여비용 총액(nhi_out_clinic_amt) 가중 중위수 / 분류: 성 × 소득 5분위(균등화 가처분소득, 전체 인구 개인 가중 20·40·60·80% 분위값 경계) / 사용 변수: nhi_out_clinic_dur, nhi_out_clinic_amt, gender, p_dinc, hnum, hid, indwgt",
     False, [c_quant([SEX[g], f"{k}분위"], "nhi_out_clinic_amt", base & (gender == g) & (quint == k), 0.5) for g in (1, 2) for k in range(1, 6)])

# A025 65세 이상 전체 인구 중 고혈압 입원 경험 비율
emit("A025", "대상: 65세 이상 전체 인구 / 분자: 2022년 고혈압 입원(nhi_highbp_yn == 1) / 분류: 없음 / 사용 변수: age, nhi_highbp_yn, indwgt",
     True, [c_ratio([], age >= 65, is1("nhi_highbp_yn"))],
     note="분모는 nhi_highbp_yn 결측자를 포함한 65세 이상 전체")

# A026 방문요양 이용 수급자의 평균 이용일수, 등급 묶음별
gr = num("ltcare_grade")
GB = [("1~2등급", np.isin(gr, [1, 2])), ("3등급", gr == 3), ("4등급", gr == 4), ("5등급·인지지원등급", np.isin(gr, [5, 6]))]
base = is1("ltcare_bn_yn") & is1("ltcare_visit_yn")
emit("A026", "대상: 장기요양 수급자(ltcare_bn_yn == 1) 중 방문요양서비스 이용자(ltcare_visit_yn == 1) / 대상 변수: 방문요양 연간 이용일수(ltcare_visit_freq) 평균 / 분류: 판정 등급 묶음(1~2등급, 3등급, 4등급, 5등급·인지지원등급) / 사용 변수: ltcare_bn_yn, ltcare_visit_yn, ltcare_visit_freq, ltcare_grade, indwgt",
     False, [c_mean([lab], "ltcare_visit_freq", base & gm) for lab, gm in GB])

# A027 (가구) 광주·전북·전남, 가구주 65세 이상 1인 가구 중 가구 재산 5천만 원 미만 가구 수
m = HEAD & np.isin(sido, [5, 13, 14]) & (age >= 65) & (hnum == 1) & (num("h_prop") < 50_000_000)
emit("A027", "대상: 광주·전북·전남의 가구주 65세 이상 1인 가구(가구주 행) 중 가구 재산(h_prop) 5천만 원 미만 / 대상 변수: 가중 가구 수(세 지역 합계) / 분류: 없음 / 사용 변수: head, hhwgt, sido, age, hnum, h_prop",
     False, [c_count([], m, w=HW)])

# A028 6~17세 중 방과후학교 자유수강권 지원 비율, 빈곤 여부별
kid = (age >= 6) & (age <= 17)
emit("A028", "대상: 6~17세 아동 / 분자: 2022년 방과후학교 자유수강권 지원(pubedu_aftsch_yn == 1) / 분류: 상대 빈곤 여부(균등화 가처분소득 < 전체 인구 개인 가중 중위값의 50%) / 사용 변수: age, pubedu_aftsch_yn, p_dinc, hnum, hid, indwgt",
     True, [c_ratio(["빈곤"], kid & POOR, is1("pubedu_aftsch_yn")), c_ratio(["비빈곤"], kid & ~POOR, is1("pubedu_aftsch_yn"))])

# A029 사적연금 일반연금소득 합계, 10세 단위 연령대
ab = bands([(f"{lo}~{lo + 9}세", lo, lo + 9) for lo in range(0, 80, 10)] + [("80세 이상", 80, None)])
emit("A029", "대상: 전체 인구(값이 있는 행) / 대상 변수: 사적연금_일반연금소득(pripen_inc) 가중 합계 / 분류: 연령 10세 단위(0~9 … 70~79, 80세 이상) / 사용 변수: pripen_inc, age, indwgt",
     False, [c_sum([lab], "pripen_inc", am) for lab, am in ab],
     note="개인 일차소득 항목 p_pripeninc(사적연금소득)는 보유자 집단은 같으나 금액이 pripen_inc와 다름. 질문의 「일반연금소득」에 따라 pripen_inc를 씀")

# A030 사학연금 연간 가입자의 평균 보험료 납부액, 성별
emit("A030", "대상: 2022년 사립학교교직원연금 가입 이력자(privschp_yn1 == 1) / 대상 변수: 보험료 납부액(본인부담, privschp_premium_amt) 평균 / 분류: 성 / 사용 변수: privschp_yn1, privschp_premium_amt, gender, indwgt",
     False, [c_mean([SEX[g]], "privschp_premium_amt", is1("privschp_yn1") & (gender == g)) for g in (1, 2)])

# A031 장애인연금법상 중증장애인(18세 이상 등록장애인) 중 장애인연금 수급 비율, 연령 3구간
ab = bands([("18~49세", 18, 49), ("50~64세", 50, 64), ("65세 이상", 65, None)])
den = is1("dis_yn") & is1("dis_disp_yn") & (age >= 18)
note31 = ("장애인연금 수급의 기준 시점이 질문에 없음. 12월 기준 수급(disp_yn2)과 연간 수급(disp_yn1)으로 분자가 달라짐. "
          "분모(등록장애인·중증장애인 여부)가 2022.12.31. 기준이고 「받는」이 현재 시제이므로 12월 기준을 1순위로 둠")
emit("A031", "대상: 18세 이상 등록장애인(dis_yn == 1) 중 장애인연금법상 중증장애인(dis_disp_yn == 1) / 분자: 2022년 12월 기준 장애인연금 수급(disp_yn2 == 1) / 분류: 연령(18~49세, 50~64세, 65세 이상) / 사용 변수: dis_yn, dis_disp_yn, disp_yn2, age, indwgt",
     True, [c_ratio([lab], den & am, is1("disp_yn2")) for lab, am in ab], reading_no=1, ambiguous=True, note=note31)
emit("A031", "대상: 18세 이상 등록장애인(dis_yn == 1) 중 장애인연금법상 중증장애인(dis_disp_yn == 1) / 분자: 2022년 중 한 번이라도 장애인연금 수급(disp_yn1 == 1) / 분류: 연령(18~49세, 50~64세, 65세 이상) / 사용 변수: dis_yn, dis_disp_yn, disp_yn1, age, indwgt",
     True, [c_ratio([lab], den & am, is1("disp_yn1")) for lab, am in ab], reading_no=2, ambiguous=True, note=note31)

# A032 구직급여 수급기간 연기 신고처리자의 연기 사유 구성비
RS = {1: "임신·출산·육아", 2: "본인의 질병·부상", 5: "병역법에 따른 의무복무", 6: "범죄혐의로 인한 구속 또는 형의 집행", 8: "기타"}
base = is1("unempbn_bnextended_yn") & has("unempbn_bnextended_reason")
emit("A032", "대상: 2022년 구직급여 수급기간 연기 신고처리자(unempbn_bnextended_yn == 1) / 대상 변수: 연기 사유(unempbn_bnextended_reason) 구성비 / 분류: 연기 사유 5종(코드 1, 2, 5, 6, 8) / 사용 변수: unempbn_bnextended_yn, unempbn_bnextended_reason, indwgt",
     True, [c_ratio([RS[k]], base, num("unempbn_bnextended_reason") == k) for k in (1, 2, 5, 6, 8)])

# A033 출산전후휴가급여 수급자의 평균 급여액, 35세 미만/이상
base = is1("empins_matleave_yn1")
emit("A033", "대상: 2022년 출산전후휴가급여 수급자(empins_matleave_yn1 == 1) / 대상 변수: 출산전후휴가 급여액(empins_matleave_amt) 평균 / 분류: 연령(35세 미만, 35세 이상) / 사용 변수: empins_matleave_yn1, empins_matleave_amt, age, indwgt",
     False, [c_mean(["35세 미만"], "empins_matleave_amt", base & (age < 35)), c_mean(["35세 이상"], "empins_matleave_amt", base & (age >= 35))])

# A034 영남권 65세 이상 1인 가구 기초연금 연간 수급자 중 노인맞춤돌봄서비스 연간 이용 비율, 성별
den = np.isin(sido, [2, 3, 7, 15, 16]) & (age >= 65) & (hnum == 1) & is1("bp_yn1")
emit("A034", "대상: 영남권(부산·대구·울산·경북·경남) 거주 65세 이상 1인 가구(hnum == 1) 중 2022년 기초연금 수급자(bp_yn1 == 1) / 분자: 2022년 노인맞춤돌봄서비스 이용(oldcare_yn1 == 1) / 분류: 성 / 사용 변수: sido, age, hnum, bp_yn1, oldcare_yn1, gender, indwgt",
     True, [c_ratio([SEX[g]], den & (gender == g), is1("oldcare_yn1")) for g in (1, 2)])

# A035 65세 이상 중 공무원·사학·군인연금 정기연금 수급 인원, 성 × 연령 2구간
m = (age >= 65) & (is1("govp_pension_yn") | is1("privschp_pension_yn") | is1("milip_pension_yn"))
ab = bands([("65~74세", 65, 74), ("75세 이상", 75, None)])
emit("A035", "대상: 65세 이상이면서 2022년 공무원연금·사립학교교직원연금·군인연금 정기연금 중 하나 이상 수급(govp_pension_yn == 1 또는 privschp_pension_yn == 1 또는 milip_pension_yn == 1) / 대상 변수: 가중 인원 / 분류: 성 × 연령(65~74세, 75세 이상) / 사용 변수: age, gender, govp_pension_yn, privschp_pension_yn, milip_pension_yn, indwgt",
     False, [c_count([SEX[g], lab], m & (gender == g) & am) for g in (1, 2) for lab, am in ab])

# A036 사학연금 정기연금 수급자의 연간 급여액 중위수
emit("A036", "대상: 2022년 사립학교교직원연금 정기연금 수급자(privschp_pension_yn == 1) / 대상 변수: 정기연금 연간 급여액(privschp_pension_amt) 가중 중위수 / 분류: 없음 / 사용 변수: privschp_pension_yn, privschp_pension_amt, indwgt",
     False, [c_quant([], "privschp_pension_amt", is1("privschp_pension_yn"), 0.5)])

# A037 노인일자리 사회서비스형 참여자 중 중도포기 비율
emit("A037", "대상: 2022년 노인일자리사업 사회서비스형 참여자(oldwork_type2_yn1 == 1) / 분자: 중도포기(oldwork_type2_end_yn == 1) / 분류: 없음 / 사용 변수: oldwork_type2_yn1, oldwork_type2_end_yn, indwgt",
     True, [c_ratio([], is1("oldwork_type2_yn1"), is1("oldwork_type2_end_yn"))])

# A038 교육급여 수급권 보유(연간) 6~17세의 평균 교육활동지원비, 학령 3구간
ab = bands([("6~11세", 6, 11), ("12~14세", 12, 14), ("15~17세", 15, 17)])
base = is1("nbls_edu_yn1")
emit("A038", "대상: 2022년 교육급여 수급권 보유자(nbls_edu_yn1 == 1) 중 6~17세 / 대상 변수: 교육활동지원비 급여액(nbls_edu_amt1) 평균 / 분류: 연령(6~11세, 12~14세, 15~17세) / 사용 변수: nbls_edu_yn1, nbls_edu_amt1, age, indwgt",
     False, [c_mean([lab], "nbls_edu_amt1", base & am) for lab, am in ab])

# A039 아동(0~17세) 상대 빈곤율, 가구원수 4구간(2인 이하, 3인, 4인, 5인 이상)
kid = age <= 17
hb2 = [("2인 이하", hnum <= 2), ("3인", hnum == 3), ("4인", hnum == 4), ("5인 이상", hnum >= 5)]
emit("A039", "대상: 0~17세 아동 / 분자: 상대 빈곤(균등화 가처분소득 < 전체 인구 개인 가중 중위값의 50%) / 분류: 가구원수(2인 이하, 3인, 4인, 5인 이상) / 사용 변수: age, hnum, p_dinc, hid, indwgt",
     True, [c_ratio([lab], kid & hm, POOR) for lab, hm in hb2])

# A040 장려세제 자료 보유자 중 근로장려 수급 대상 비율, 가구원 구성별
HM = {11: "단독가구", 21: "홑벌이가구", 23: "맞벌이가구"}
den = has("itc_yn")
emit("A040", "대상: 장려세제 자료가 있는 사람(itc_yn 값이 있는 행) / 분자: 근로장려수급 대상(itc_yn == 1) / 분류: 가구원구성코드(itc_hmember: 11 단독, 21 홑벌이, 23 맞벌이) / 사용 변수: itc_yn, itc_hmember, indwgt",
     True, [c_ratio([HM[k]], den & (num("itc_hmember") == k), is1("itc_yn")) for k in (11, 21, 23)])

# A041 긴급복지 생계지원 급여액 전국 합계
emit("A041", "대상: 2022년 긴급복지 생계지원 수급자(급여액 값이 있는 행) / 대상 변수: 생계지원 연간 급여액(aid_live_amt) 가중 합계 / 분류: 없음 / 사용 변수: aid_live_amt, indwgt",
     False, [c_sum([], "aid_live_amt", ALL)])

# A042 배우자출산휴가급여 수급자의 평균 수급일수, 시도별
base = is1("empins_spouseleave_yn1")
emit("A042", "대상: 2022년 배우자출산휴가급여 수급자(empins_spouseleave_yn1 == 1) / 대상 변수: 배우자출산휴가 수급기간(일, empins_spouseleave_dur) 평균 / 분류: 시도 / 사용 변수: empins_spouseleave_yn1, empins_spouseleave_dur, sido, indwgt",
     False, [c_mean([SIDO[s]], "empins_spouseleave_dur", base & (sido == s)) for s in range(1, 18)],
     note="관측이 29건으로 적어 시도 칸 모두 10건 미만이며 6개 시도는 0건. 수급일수 값은 모두 5일")

# A043 65세 이상 장기요양 수급자 중 1~3등급의 시설급여 180일 이상 이용 비율
den = (age >= 65) & is1("ltcare_bn_yn") & np.isin(gr, [1, 2, 3])
emit("A043", "대상: 65세 이상 장기요양 수급자(ltcare_bn_yn == 1) 중 판정 등급 1~3등급(ltcare_grade 1·2·3) / 분자: 시설이용급여 연간 이용일수 180일 이상(ltcare_institute_freq >= 180) / 분류: 없음 / 사용 변수: age, ltcare_bn_yn, ltcare_grade, ltcare_institute_freq, indwgt",
     True, [c_ratio([], den, num("ltcare_institute_freq") >= 180)])

# A044 국민취업지원제도 연간 참여 인원, 참여유형 × 연령 2구간
base = is1("kua_yn1")
emit("A044", "대상: 2022년 국민취업지원제도 참여자(kua_yn1 == 1) / 대상 변수: 가중 인원 / 분류: 참여유형(kua_type 1 Ⅰ유형, 2 Ⅱ유형) × 연령(34세 이하, 35세 이상) / 사용 변수: kua_yn1, kua_type, age, indwgt",
     False, [c_count([tl, al], base & (num("kua_type") == t) & am) for t, tl in ((1, "Ⅰ유형"), (2, "Ⅱ유형"))
             for al, am in (("34세 이하", age <= 34), ("35세 이상", age >= 35))])

# A045 방과후학교 자유수강권 지원 학생의 지원액 중위수, 수도권/비수도권
base = is1("pubedu_aftsch_yn")
emit("A045", "대상: 2022년 방과후학교 자유수강권 지원 학생(pubedu_aftsch_yn == 1) / 대상 변수: 지원액(pubedu_aftsch_amt) 가중 중위수 / 분류: 수도권(서울·인천·경기), 비수도권 / 사용 변수: pubedu_aftsch_yn, pubedu_aftsch_amt, sido, indwgt",
     False, [c_quant(["수도권"], "pubedu_aftsch_amt", base & METRO, 0.5), c_quant(["비수도권"], "pubedu_aftsch_amt", base & ~METRO, 0.5)])

# A046 (가구) 제주, 가구주 65세 이상 가구 중 가구 재산 1억 원 미만 비율
den = HEAD & (sido == 17) & (age >= 65)
emit("A046", "대상: 제주의 가구주 65세 이상 가구(가구주 행) / 분자: 가구 재산(h_prop) 1억 원 미만 / 분류: 없음 / 사용 변수: head, hhwgt, sido, age, h_prop",
     True, [c_ratio([], den, num("h_prop") < 100_000_000, w=HW)])

# A047 장기요양 수급자의 판정 등급 구성비, 성별
GL = {1: "1등급", 2: "2등급", 3: "3등급", 4: "4등급", 5: "5등급", 6: "인지지원등급"}
base = is1("ltcare_bn_yn") & has("ltcare_grade")
emit("A047", "대상: 2022년 장기요양 수급자(ltcare_bn_yn == 1) / 대상 변수: 성별 안에서의 판정 등급(ltcare_grade) 구성비 / 분류: 성 × 판정 등급(1~5등급, 인지지원등급) / 사용 변수: ltcare_bn_yn, ltcare_grade, gender, indwgt",
     True, [c_ratio([SEX[g], GL[k]], base & (gender == g), gr == k) for g in (1, 2) for k in range(1, 7)])

# A048 장애인활동지원 이용자의 평균 결제금액, 성별
emit("A048", "대상: 2022년 장애인활동지원 이용자(disvou_act_yn1 == 1) / 대상 변수: 결제금액(disvou_act_amt) 평균 / 분류: 성 / 사용 변수: disvou_act_yn1, disvou_act_amt, gender, indwgt",
     False, [c_mean([SEX[g]], "disvou_act_amt", is1("disvou_act_yn1") & (gender == g)) for g in (1, 2)])

# ---- 저장 ---------------------------------------------------------------
with open(OUT, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    ids = sorted({r["id"] for r in rows})
    print("questions:", len(ids), "lines:", len(rows))
    print("eq median:", wquant(eq, W, 0.5), "poverty line:", pov_line, "quintile bounds:", qb)
    for r in rows:
        print(r["id"], r["reading_no"], "pct" if r["pct"] else "   ", "amb" if r["ambiguous"] else "")
        for c in r["cells"]:
            v = c["value"]
            print("    ", "/".join(c["labels"]) or "-", "|", None if v is None else round(v, 4), "| n", c["n"], "| n_num", c.get("n_num", ""))
