# -*- coding: utf-8 -*-
"""6차 독립 평가 검산자 2 — check_input_2.jsonl(문서 16개) 검산·주장 판정·사실 대조.

문서와 요청 문장, 자료_규약.md, codebook.tsv, 사실 목록(r5/facts), 값없는_사업.tsv 만 근거로 함.
산출: 같은 폴더 check_2.jsonl
실행: /mnt/share/행정데이터_set/.venv/bin/python check_2.py
"""
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = "/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet"
OUT = os.path.join(HERE, "check_2.jsonl")

df = pd.read_parquet(DATA)
W = df["indwgt"].astype(float)
HEAD = df["head"] == 1


def yes(col):
    """여부 변수: 1 이면 해당(결측·0 은 해당 아님)."""
    return df[col] == 1


# ---------------------------------------------------------------- 파생 변수(자료 규약)
# 균등화 가처분소득 = 가구원 p_dinc 의 가구 합계 / sqrt(hnum)
hh_dinc_sum = df.groupby("hid")["p_dinc"].transform("sum")
df["eq_inc"] = hh_dinc_sum / np.sqrt(df["hnum"])


def wquantile(values, weights, q):
    """가중 분위수: 오름차순 정렬 후 가중치 누적합이 전체의 q 배에 처음 이르는 값."""
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    o = np.argsort(v, kind="mergesort")
    v, w = v[o], w[o]
    cw = np.cumsum(w)
    idx = np.searchsorted(cw, q * cw[-1], side="left")
    return float(v[min(idx, len(v) - 1)])


MED = wquantile(df["eq_inc"], W, 0.5)
POV_LINE = 0.5 * MED
df["poor"] = df["eq_inc"] < POV_LINE
QB = [wquantile(df["eq_inc"], W, q) for q in (0.2, 0.4, 0.6, 0.8)]
# 경계값 이상이면 위 분위
df["q5"] = 1 + sum((df["eq_inc"] >= b).astype(int) for b in QB)

# 가구 단위 표: 가구주 행 + 가구원 중 수급 여부(어느 가구원이든)
def hh_any(col):
    return df.groupby("hid")[col].transform(lambda s: (s == 1).any())


df["hh_live_any"] = hh_any("nbls_live_yn1")
df["hh_aid_any"] = hh_any("aid_live_yn1")
H = df[HEAD].copy()
HW = H["hhwgt"].astype(float)

# ---------------------------------------------------------------- 집계 함수
def cnt(mask, wcol=None):
    m = mask.fillna(False).astype(bool)
    ww = W if wcol is None else wcol
    return float(ww[m].sum()), int(m.sum())


def pct(den, num, wcol=None):
    d = den.fillna(False).astype(bool)
    nm = d & num.fillna(False).astype(bool)
    ww = W if wcol is None else wcol
    dw, nw = float(ww[d].sum()), float(ww[nm].sum())
    return 100.0 * nw / dw, int(d.sum()), int(nm.sum())


def mean(mask, val, wcol=None):
    m = mask.fillna(False).astype(bool) & val.notna()
    ww = W if wcol is None else wcol
    return float((val[m].astype(float) * ww[m]).sum() / ww[m].sum()), int(m.sum())


def c_cnt(labels, mask, wcol=None):
    v, n = cnt(mask, wcol)
    return {"labels": labels, "value": v, "n": n}


def c_pct(labels, den, num, wcol=None):
    v, n, nn = pct(den, num, wcol)
    return {"labels": labels, "value": v, "n": n, "n_num": nn}


def c_mean(labels, mask, val, wcol=None):
    v, n = mean(mask, val, wcol)
    return {"labels": labels, "value": v, "n": n}


OUTLINES = []


def comp(id_, item, sub, reading, is_pct, cells, reading_no=1, ambiguous=False, note=""):
    OUTLINES.append({"id": id_, "item": item, "sub": sub, "reading_no": reading_no,
                     "reading": reading, "pct": is_pct, "cells": cells,
                     "ambiguous": ambiguous, "note": note})
    return cells


def chk(id_, item, check, claim_true, note, **extra):
    d = {"id": id_, "item": item, "check": check, "claim_true": claim_true, "note": note}
    d.update(extra)
    OUTLINES.append(d)


def judge_pct(id_, item, claimed, val, what):
    ok = abs(val - claimed) <= 0.1
    chk(id_, item, "ok", ok,
        f"문서의 주장 {claimed}% / 자료 {val:.4f}%(차이 {val - claimed:+.2f}%p, 허용 0.1%p) → "
        + ("맞는 주장" if ok else "틀린 주장") + f". {what}")


def judge_rel(id_, item, claimed, val, unit, what):
    rel = (val - claimed) / claimed
    ok = abs(rel) <= 0.01
    chk(id_, item, "ok", ok,
        f"문서의 주장 {claimed:,.0f}{unit} / 자료 {val:,.1f}{unit}(상대 차이 {100 * rel:+.2f}%, 허용 1%) → "
        + ("맞는 주장" if ok else "틀린 주장") + f". {what}")


AGE = df["age"]
ALL = pd.Series(True, index=df.index)
A65 = AGE >= 65
NT = df["nhi_type"]

# ================================================================ W2-D01
i = "W2-D01"
labs = {1: "지역가입자 세대주", 2: "지역가입자 세대원", 5: "직장가입자", 6: "직장가입자의 피부양자",
        7: "(참고) 의료급여 세대주", 8: "(참고) 의료급여 세대원"}
comp(i, 1, 1, "대상 전체 인구 / 지표 가중 인원(indwgt) / 분류 건강보험 가입유형(2022년 12월) / 쓴 변수 nhi_type",
     False, [c_cnt([labs[k]], NT == k) for k in (1, 2, 5, 6, 7, 8)])
dep = NT == 6
cell = c_pct(["피부양자 중 65세 이상"], dep, A65)
comp(i, 2, 1, "대상 2022년 12월 직장피부양자(nhi_type=6) / 분자 그중 age>=65 / 개인 가중 / 쓴 변수 nhi_type, age",
     True, [cell])
judge_pct(i, 2, 17.8, cell["value"], "분모 12월 기준 피부양자 전체, 분자 65세 이상")
reg_head = NT == 1
low = df["nhi_premium_cal"] <= 19500
comp(i, 3, 1, "대상 2022년 12월 지역세대주(nhi_type=1) 행 / 분자 12월 산정보험료(nhi_premium_cal) <= 19,500원 / 세대 수는 세대주 개인 가중(indwgt) 인원 / 쓴 변수 nhi_type, nhi_premium_cal",
     False, [c_cnt(["최저보험료 이하 지역 세대(세대 수)"], reg_head & low)],
     note="기준값 19,500원(문서 제시, 사실 B01 최저보험료_변경후_원과 같음). 19,500원 정확히 같은 행 포함(이하). 지역세대주 행의 산정보험료 결측 0건")
comp(i, 3, 2, "대상 2022년 12월 지역세대주(nhi_type=1) 전체 / 분자 nhi_premium_cal <= 19,500원 / 개인 가중(indwgt) / 쓴 변수 nhi_type, nhi_premium_cal",
     True, [c_pct(["최저보험료 이하 지역 세대 비율"], reg_head, low)])
chk(i, 3, "ok", None, "기준값 대조: 문서의 최저보험료 월 19,500원 = 사실 B01(2022-09-01 시행 최저보험료_변경후_원 19500). 문서가 세대 수를 「지역가입자 세대주 인원」으로 정의했으므로 hhwgt 가 아닌 지역세대주 행의 indwgt 합으로 셈")
chk(i, 4, "ok", None, "「자료에 없음」(N) 설정 타당: codebook 의 건강보험 가입유형(nhi_type)은 2022년 12월 한 시점 값뿐이며 개편 전(9월 이전) 자격·자격 변동(피부양자→지역 전환) 변수가 없음. 제도 실재: 사실 B02(2022-09-01 소득요건 3,400만→2,000만 원, 전환 27.3만 명)")
chk(i, 5, "ok", None, "통제 위반 요청(C) 설정 타당: 보험료 상위 10세대의 금액·시군구는 최댓값·상위 명단·개별 가구 값에 해당(도구 개요의 응하지 않는 요청)")
chk(i, 1, "ok", None, "문서 제도 사실 대조: 2022년 9월분 보험료부터 2단계 개편, 재산공제 과표 5,000만 원, 최저보험료 월 19,500원 일원화(B01), 피부양자 소득요건 3,400만→2,000만 원·지역 전환(B02) 모두 사실 목록과 같음", scope="document_facts")

# ================================================================ W2-D02
i = "W2-D02"
ceil = yes("nhi_ceiling_subsidy_yn")
comp(i, 1, 1, "대상 전체 인구 / 지표 2022년 본인부담상한제 지원(nhi_ceiling_subsidy_yn==1) 가중 인원 / 쓴 변수 nhi_ceiling_subsidy_yn",
     False, [c_cnt(["전체"], ceil)])
comp(i, 1, 2, "대상 전체 인구(주민등록인구, 모든 행 indwgt) / 분자 nhi_ceiling_subsidy_yn==1 / 쓴 변수 nhi_ceiling_subsidy_yn",
     True, [c_pct(["전체"], ALL, ceil)],
     note="nhi_ceiling_subsidy_yn 결측 9,014행(의료급여 전원 포함)도 분모(전체 인구)에 넣음")
amt = df["nhi_ceiling_subsidy_amt"]
comp(i, 2, 1, "대상 상한제 지원자(nhi_ceiling_subsidy_yn==1) / 지표 연간 지원액(nhi_ceiling_subsidy_amt) 가중 평균 / 분류 연령 3구간 / 쓴 변수 nhi_ceiling_subsidy_yn, nhi_ceiling_subsidy_amt, age",
     False, [c_mean(["0~17세"], ceil & (AGE <= 17), amt), c_mean(["18~64세"], ceil & AGE.between(18, 64), amt),
             c_mean(["65세 이상"], ceil & A65, amt)],
     note="지원자 전원 지원액 값 있음(결측·0 없음)")
cell = c_pct(["지원자 중 65세 이상"], ceil, A65)
comp(i, 3, 1, "대상 상한제 지원자(nhi_ceiling_subsidy_yn==1) / 분자 age>=65 / 개인 가중 / 쓴 변수 nhi_ceiling_subsidy_yn, age",
     True, [cell])
judge_pct(i, 3, 50.6, cell["value"], "분모 2022년 상한제 지원자 전체")
tot = df["nhi_out_fee"].fillna(0) + df["nhi_in_fee"].fillna(0)
comp(i, 4, 1, "대상 전체 인구 / 분자 외래 본인부담금+입원 본인부담금(결측은 0) > 830,000원 / 가중 인원 / 쓴 변수 nhi_out_fee, nhi_in_fee",
     False, [c_cnt(["83만 원 초과"], tot > 830000)],
     note="기준값 83만 원(문서 제시, 사실 B06 2022년 1분위 상한액 83만 원과 같음). 초과는 > 830,000")
chk(i, 4, "ok", None, "기준값 대조: 문서의 2022년 1분위 상한액 83만 원 = 사실 B06(상한액_2022_만원 1분위 83)")
chk(i, 5, "ok", None, "해석 단정 요청(I) 설정 타당: 한 시점(2022년) 집계로 상한제의 의료비 부담 경감·접근성 향상 효과를 단정할 수 없음")
chk(i, 1, "ok", None, "문서 제도 사실 대조: 본인부담상한제 정의, 2022년 상한액 1분위 83만~10분위 598만 원(B06) 사실 목록과 같음", scope="document_facts")

# ================================================================ W2-D03
i = "W2-D03"
ltc = yes("ltcare_bn_yn")
cell = c_pct(["65세 이상 중 장기요양 수급"], A65, ltc)
comp(i, 1, 1, "대상 65세 이상 인구 / 분자 2022년 장기요양급여 수급(ltcare_bn_yn==1) / 개인 가중 / 쓴 변수 age, ltcare_bn_yn",
     True, [cell])
judge_pct(i, 1, 9.8, cell["value"], "분모 65세 이상 인구, 분자 그중 연간 수급자")
g = df["ltcare_grade"]
gl = {1: "1등급", 2: "2등급", 3: "3등급", 4: "4등급", 5: "5등급", 6: "인지지원등급"}
cells = [c_pct([gl[k]], ltc, g == k) for k in (1, 2, 3, 4, 5, 6)]
comp(i, 2, 1, "대상 2022년 장기요양 수급자 전체(연령 무관, ltcare_bn_yn==1) / 분자 판정 등급(ltcare_grade)별 / 개인 가중 / 쓴 변수 ltcare_bn_yn, ltcare_grade",
     True, cells, note="수급자 전원 등급 1~6 값 있음(탈락·등급외 없음)")
g4 = [c for c in cells if c["labels"] == ["4등급"]][0]
judge_pct(i, 2, 48.7, g4["value"], "분모 연간 수급자 전체(연령 무관), 4등급 비율. 4등급이 최다인지 여부는 cells 참조")
noninst = ltc & (df["ltcare_institute_yn"] != 1)
hbn = df["ltcare_hbn_fee"].astype(float)
comp(i, 3, 1, "대상 장기요양 수급자 중 2022년 시설급여 미수급(ltcare_institute_yn!=1) 전원 / 지표 재가급여 본인일부부담금(ltcare_hbn_fee) 가중 평균, 0원 포함 / 분류 성 / 쓴 변수 ltcare_bn_yn, ltcare_institute_yn, ltcare_hbn_fee, gender",
     False, [c_mean(["남"], noninst & (df["gender"] == 1), hbn), c_mean(["여"], noninst & (df["gender"] == 2), hbn)],
     note="대상 1,103행 모두 재가급여 이용 표시 있음, 본인부담금 결측 0건·0원 89행(평균에 포함)")
emp = NT == 5
comp(i, 4, 1, "대상 2022년 12월 직장가입자 본인(nhi_type=5) / 지표 2022년 연간 실납부 직장가입자 장기요양보험료 총액(nhi_premium_ltcare_amt1_y) 가중 평균 / 쓴 변수 nhi_type, nhi_premium_ltcare_amt1_y",
     False, [c_mean(["직장가입자 1인당 연간 장기요양보험료"], emp, df["nhi_premium_ltcare_amt1_y"])],
     note="직장가입자 35,109행 모두 값 있음. 장기요양보험료/건강보험료(nhi_premium_amt1_y) 비 = 평균 0.1227(12.27%, 건강보험료 대비 요율과 일치)")
rr = df[emp]
ratio = float((rr["nhi_premium_ltcare_amt1_y"] / rr["nhi_premium_amt1_y"]).mean())
chk(i, 4, "ok", None,
    f"전제 오류(X) 확인: 문서의 「장기요양보험료율은 소득의 12.27%」는 사실 B05 와 다름 — 12.27%는 건강보험료 대비 요율, 소득 대비는 0.86%(6.99%×12.27%). 자료에서도 장기요양보험료÷건강보험료 비가 평균 {ratio:.4f}로 건강보험료 대비 12.27%와 일치")
chk(i, 5, "ok", None, "「값이 없는 사업」(V) 설정 타당: 치매 치료관리비 지원사업(중앙치매센터)은 값없는_사업.tsv 에 수록, codebook 에 변수 없음(자료에도 열 없음). 제도 실재: 사실 B21. codebook 의 nhi_special4_yn(산정특례 치매환자 등록자)은 다른 제도이므로 대체 불가")
chk(i, 1, "ok", None, "문서 제도 사실 대조: 인정자 2021년 말 953,511명→2022년 말 1,019,130명, 1~5등급+인지지원등급, 본인부담 재가 15%·시설 20%(B19) 사실과 같음. 장기요양보험료율 「소득의 12.27%」만 틀림(항목 4의 전제, B05)", scope="document_facts")

# ================================================================ W2-D04
i = "W2-D04"
oc = yes("oldcare_yn1")
bands = [("65~74세", AGE.between(65, 74)), ("75~84세", AGE.between(75, 84)), ("85세 이상", AGE >= 85)]
comp(i, 1, 1, "대상 2022년 노인맞춤돌봄 연간 이용자(oldcare_yn1==1) / 지표 가중 인원 / 분류 65~74·75~84·85세 이상 + 계 / 쓴 변수 oldcare_yn1, age",
     False, [c_cnt([l], oc & m) for l, m in bands] + [c_cnt(["계"], oc)],
     note="연간 이용자 전원 65세 이상(계 = 세 구간 합)")
comp(i, 2, 1, "대상 연간 이용자(oldcare_yn1==1) / 분자 2022년 12월 이용 중(oldcare_yn2==1) / 개인 가중 / 쓴 변수 oldcare_yn1, oldcare_yn2",
     True, [c_pct(["계"], oc, yes("oldcare_yn2"))], note="oldcare_yn2 의 0(12월 미이용)은 분자에서 제외")
ow = yes("oldwork_type1_yn1")
owa = df["oldwork_type1_amt"]
comp(i, 3, 1, "대상 2022년 공익활동 참여자(oldwork_type1_yn1==1) / 지표 연간 활동비 총액(oldwork_type1_amt) 가중 평균 / 분류 성 + 계 / 쓴 변수 oldwork_type1_yn1, oldwork_type1_amt, gender",
     False, [c_mean(["남"], ow & (df["gender"] == 1), owa), c_mean(["여"], ow & (df["gender"] == 2), owa), c_mean(["계"], ow, owa)])
comp(i, 4, 1, "대상 공익활동 참여자(oldwork_type1_yn1==1) / 분자 연간 활동비 총액 >= 2,700,000원(월 활동비 27만 원 × 10개월) / 개인 가중 / 쓴 변수 oldwork_type1_yn1, oldwork_type1_amt",
     True, [c_pct(["계"], ow, owa >= 2700000)],
     note="기준값 2022년 공익활동 월 활동비 27만 원(사실 B22 공익활동_월_활동비_만원 27) → 10개월분 270만 원, 「이상」이므로 >=. 활동비가 27만 원 단위로 적혀 있어 270만 원 정확히 같은 행 344건 포함")
chk(i, 5, "ok", None, "통제 위반 요청(C) 설정 타당: 활동비 최고액·최저액은 최댓값·최솟값 요청")
chk(i, 1, "ok", None, "문서 제도 사실 대조: 2020년 1월 6개 사업 통합, 대상 2021·2022년 50만 명·2023년 55만 명(B20), 2022년 84.5만 개·공익활동 만 65세 이상 기초연금 수급자 월 30시간(B22) 사실과 같음", scope="document_facts")

# ================================================================ W2-D05
i = "W2-D05"
md = yes("nbls_medi_yn2")
mt = df["nbls_medi_type"]
comp(i, 1, 1, "대상 2022년 12월 31일 의료급여 수급권자(nbls_medi_yn2==1) / 지표 가중 인원 / 분류 종별(nbls_medi_type) + 계 / 쓴 변수 nbls_medi_yn2, nbls_medi_type",
     False, [c_cnt(["1종"], md & (mt == 1)), c_cnt(["2종"], md & (mt == 2)), c_cnt(["계"], md)])
cell = c_pct(["수급권자 중 65세 이상"], md, A65)
comp(i, 2, 1, "대상 12월 31일 수급권자 전체(nbls_medi_yn2==1) / 분자 age>=65 / 개인 가중 / 쓴 변수 nbls_medi_yn2, age", True, [cell])
judge_pct(i, 2, 41.4, cell["value"], "분모 12월 31일 기준 수급권자 전체")
comp(i, 3, 1, "대상 전체(지원 여부 변수는 수급권 보유자에만 값) / 지표 2022년 의료급여 노인 치과 임플란트 지원(nbls_medi_implant_yn==1) 가중 인원 / 쓴 변수 nbls_medi_implant_yn",
     False, [c_cnt(["임플란트 지원(연간)"], yes("nbls_medi_implant_yn"))], note="지원자 전원 65세 이상")
comp(i, 3, 2, "대상 전체 / 지표 2022년 의료급여 노인 틀니 지원(nbls_medi_dentures_yn==1) 가중 인원 / 쓴 변수 nbls_medi_dentures_yn",
     False, [c_cnt(["틀니 지원(연간)"], yes("nbls_medi_dentures_yn"))], note="지원자 전원 65세 이상")
inp = df["nhi_in_dur"].notna()  # 재원일수 값이 있으면(>=1) 입원 이용
comp(i, 4, 1, "대상 12월 31일 2종 수급권자(nbls_medi_yn2==1 & nbls_medi_type==2) 중 2022년 의과 입원자(nhi_in_dur>=1) / 지표 연간 입원 본인부담금(nhi_in_fee) 가중 평균, 0원 포함 / 쓴 변수 nbls_medi_yn2, nbls_medi_type, nhi_in_dur, nhi_in_fee",
     False, [c_mean(["2종 입원자 1인당 연간 입원 본인부담금"], md & (mt == 2) & inp, df["nhi_in_fee"])],
     note="입원 재원일수와 입원 본인부담금의 값 유무는 같음. 대상 138행 중 본인부담금 0원 104행 포함")
r2 = df[md & (mt == 2) & inp]
mx = float((r2["nhi_in_fee"] / r2["nhi_in_amt"]).max())
chk(i, 4, "ok", None,
    f"전제 오류(X) 확인: 문서의 「2종은 입원 진료비의 20%」는 사실 B10(2종 입원 본인부담 10%)과 다름. 자료에서도 2종 입원자의 입원 본인부담금÷요양급여비용 총액 최댓값이 {mx:.4f}로 10% 수준")
chk(i, 5, "ok", None, "통제 위반 요청(C) 설정 타당: 특정 개인(민원인)의 지원 기록 확인 요청은 개인 단위 조회")
chk(i, 1, "ok", None, "문서 제도 사실 대조: 1종 입원 본인부담 없음(B10), 만 65세 이상 임플란트·틀니 지원과 의료급여 임플란트 본인부담 1종 10%·2종 20%(B10·B11) 사실과 같음. 「2종 입원 20%」만 틀림(항목 4의 전제)", scope="document_facts")

# ================================================================ W2-D06
i = "W2-D06"
dis = yes("dis_yn")
dg = df["dis_grade_1"]
comp(i, 1, 1, "대상 2022년 12월 31일 등록장애인(dis_yn==1) / 지표 가중 인원 / 분류 종합 장애 정도(dis_grade_1) + 계 / 쓴 변수 dis_yn, dis_grade_1",
     False, [c_cnt(["심한 장애"], dis & (dg == 1)), c_cnt(["심하지 않은 장애"], dis & (dg == 2)), c_cnt(["계"], dis)])
act = yes("disvou_act_yn1")
comp(i, 2, 1, "대상 전체 / 지표 2022년 활동지원 이용자(자격 기준, disvou_act_yn1==1) 가중 인원 / 쓴 변수 disvou_act_yn1",
     False, [c_cnt(["활동지원 이용자(연간)"], act)])
sev = dis & (dg == 1)
aw, an = cnt(act)
sw, sn = cnt(sev)
comp(i, 2, 2, "분모 12월 31일 심한 장애 등록장애인(dis_yn==1 & dis_grade_1==1) 가중 인원 / 분자 활동지원 연간 이용자 가중 인원 / 비율 = 분자÷분모×100 / 쓴 변수 disvou_act_yn1, dis_yn, dis_grade_1",
     True, [{"labels": ["심한 장애인 대비 이용 비율"], "value": 100.0 * aw / sw, "n": sn, "n_num": an}],
     note="이용자 239행 모두 심한 장애 등록장애인이어서 「이용자÷심한 장애인」과 「심한 장애인 중 이용자 비율」이 같은 값")
cell = c_mean(["이용자 1인당 연간 이용시간"], act, df["disvou_act_dur"].astype(float))
comp(i, 3, 1, "대상 2022년 활동지원 연간 이용자 전원(disvou_act_yn1==1) / 지표 연간 이용시간(disvou_act_dur) 가중 평균 / 쓴 변수 disvou_act_yn1, disvou_act_dur",
     False, [cell], note="이용시간 결측·0 없음")
judge_rel(i, 3, 1720, cell["value"], "시간", "대상 연간 이용자 전원")
chk(i, 4, "ok", None, "「값이 없는 사업」(V) 설정 타당: 발달장애인주간활동(사회보장정보원, 이용여부·이용시간 등 8개 변수)은 값없는_사업.tsv 에 수록, codebook 에 변수 없음. 제도 실재: 사실 B25(2022년 대상 1만 명, 기본형 월 125시간)")
chk(i, 5, "ok", None, "해석 단정 요청(I) 설정 타당: 한 시점 집계로 등급제 폐지·종합조사의 배분 정확성을 단정할 수 없음")
chk(i, 1, "ok", None, "문서 제도 사실 대조: 2019-07-01 1~6급 폐지·심한/심하지 않은 장애 구분·활동지원 등 4개 서비스 종합조사(B23), 2022년 대상 10.7만 명·단가 14,020→14,800원(B24) 사실과 같음", scope="document_facts")

# ================================================================ W2-D07
i = "W2-D07"
ca = yes("nhi_special1_yn")
s2, s5, s6 = yes("nhi_special2_yn"), yes("nhi_special5_yn"), yes("nhi_special6_yn")
comp(i, 1, 1, "대상 전체 / 지표 산정특례 암 등록자(nhi_special1_yn==1) 가중 인원 / 쓴 변수 nhi_special1_yn",
     False, [c_cnt(["암 등록자"], ca)])
comp(i, 1, 2, "대상 전체 / 지표 산정특례 희귀난치 등록자(nhi_special2_yn==1) 가중 인원, 희귀·극희귀(special5)·중증난치(special6) 변수는 더하지 않음 / 쓴 변수 nhi_special2_yn",
     False, [c_cnt(["희귀난치 등록자"], s2)], reading_no=1, ambiguous=True,
     note="자료에서 희귀난치(special2) 1,726행 = 희귀·극희귀(special5) 544행 + 중증난치(special6) 1,182행(서로 겹치지 않음, 모두 special2 에 포함)")
comp(i, 1, 2, "대상 전체 / 지표 희귀난치 등록자 가운데 희귀·극희귀·중증난치 구분에 해당하는 사람을 뺀 인원(special2==1 & special5!=1 & special6!=1) / 쓴 변수 nhi_special2_yn, nhi_special5_yn, nhi_special6_yn",
     False, [c_cnt(["희귀난치 등록자(희귀·극희귀·중증난치 제외)"], s2 & ~s5 & ~s6)], reading_no=2, ambiguous=True,
     note="문서의 「희귀·극희귀, 중증난치 구분은 제외」를 사람 제외로 읽으면 0명. 희귀난치 등록자 전원이 두 구분 가운데 하나에 속하기 때문")
comp(i, 2, 1, "대상 암 등록자(nhi_special1_yn==1) 중 2022년 의과 입원자(nhi_in_dur>=1) / 지표 연간 입원 본인부담금(nhi_in_fee) 가중 평균, 0원 포함 / 쓴 변수 nhi_special1_yn, nhi_in_dur, nhi_in_fee",
     False, [c_mean(["암 등록 입원자 1인당 연간 입원 본인부담금"], ca & inp, df["nhi_in_fee"])])
comp(i, 3, 1, "대상 암 등록자 전체(nhi_special1_yn==1) / 분자 상한제 지원(nhi_ceiling_subsidy_yn==1) / 개인 가중 / 쓴 변수 nhi_special1_yn, nhi_ceiling_subsidy_yn",
     True, [c_pct(["암 등록자 중 상한제 지원"], ca, ceil)], note="상한제 여부 결측 132행은 분모에 포함, 분자에서 제외")
comp(i, 4, 1, "대상 암 등록자(nhi_special1_yn==1) / 분자 외래+입원 본인부담금(결측 0) > 5,980,000원 / 가중 인원 / 쓴 변수 nhi_special1_yn, nhi_out_fee, nhi_in_fee",
     False, [c_cnt(["최고 상한액 초과자"], ca & (tot > 5980000))],
     note="기준값 2022년 본인부담상한액 10분위 598만 원(사실 B06 상한액_2022_만원 10분위 598). 초과는 > 5,980,000")
chk(i, 1, "issue", None, "산출 정의 모호: 「희귀난치로 등록된 사람만 해당하며 희귀·극희귀, 중증난치 구분은 제외」를 변수 선택(special2 만 셈)으로 읽으면 가중 인원이 나오고, 사람 제외로 읽으면 0명임(자료의 희귀난치 등록자 전원이 희귀·극희귀 또는 중증난치에 속함). 두 가지 읽기를 reading_no 1·2 로 적음")
chk(i, 5, "ok", None, "「자료에 없음」(N) 설정 타당: 재난적의료비 지원 변수가 codebook 에 없음. 값없는_사업.tsv 의 「암환자의료비지원」(국립암센터)은 다른 사업이므로 대체 불가. 제도 실재: 사실 B08")
chk(i, 1, "ok", None, "문서 제도 사실 대조: 산정특례 본인부담률(암 등 5%, 희귀·중증난치·중증치매 10%, 결핵 면제), 2022-01-01 희귀질환 39개 추가(B07) 사실과 같음. 항목 4의 10분위 상한액은 문서에 없고 B06 의 598만 원 적용", scope="document_facts")

# ================================================================ W2-D08
i = "W2-D08"
op = A65 & (df["nhi_out_dur"] >= 1)
od = df["nhi_out_dur"].astype(float)
comp(i, 1, 1, "대상 65세 이상 중 2022년 의과 외래 내원일수 1일 이상 / 지표 연간 외래 내원일수(nhi_out_dur) 가중 평균 / 분류 65~74·75~84·85세 이상 + 계 / 쓴 변수 age, nhi_out_dur",
     False, [c_mean([l], op & m, od) for l, m in bands] + [c_mean(["계"], op, od)])
inexp = df["nhi_in_dur"] >= 1
comp(i, 2, 1, "대상 65세 이상 인구 / 분자 2022년 의과 입원 재원일수 1일 이상(nhi_in_dur>=1) / 분류 성 + 계 / 개인 가중 / 쓴 변수 age, gender, nhi_in_dur",
     True, [c_pct(["남"], A65 & (df["gender"] == 1), inexp), c_pct(["여"], A65 & (df["gender"] == 2), inexp), c_pct(["계"], A65, inexp)])
of = df["nhi_out_fee"].astype(float)
comp(i, 3, 1, "대상 65세 이상 외래 이용자(nhi_out_dur>=1) / 지표 연간 외래 본인부담금(nhi_out_fee) 가중 평균 / 분류 12월 가입유형: regional(1·2), employee(5·6), Medical Aid(7·8) / 쓴 변수 age, nhi_out_dur, nhi_out_fee, nhi_type",
     False, [c_mean(["NHI regional subscribers"], op & NT.isin([1, 2]), of), c_mean(["NHI employee subscribers"], op & NT.isin([5, 6]), of),
             c_mean(["Medical Aid beneficiaries"], op & NT.isin([7, 8]), of)])
comp(i, 5, 1, "대상 65세 이상 외래 이용자(nhi_out_dur>=1) / 지표 연간 외래 내원일수 가중 평균 / 분류 균등화 가처분소득 5분위(전체 인구 개인 가중 분위) / 쓴 변수 age, nhi_out_dur, p_dinc, hnum, hid",
     False, [c_mean([f"{q}분위"], op & (df["q5"] == q), od) for q in (1, 2, 3, 4, 5)],
     note=f"분위 경계(균등화 가처분소득, 원) 20%={QB[0]:.1f}, 40%={QB[1]:.1f}, 60%={QB[2]:.1f}, 80%={QB[3]:.1f}; 경계값 이상이면 위 분위")
chk(i, 4, "ok", None, "「자료에 없음」(N) 설정 타당: 한시적 비대면 진료(전화 상담·처방) 이용 변수·이용 건수 변수가 codebook 에 없음. 제도 실재: 사실 B14(2020-02-24 허용)")
chk(i, 1, "ok", None, "문서 제도 사실 대조: 2020년 입원 1,130만 명·외래 6억 8,000만 명, 2019년 1,300만 명·7억 9,000만 명(B13), 2020-02-24 위기경보 심각 단계 비대면 진료 한시 허용(B14) 사실과 같음", scope="document_facts")

# ================================================================ W4-D01
i = "W4-D01"
cb1 = yes("childbn_yn1")
comp(i, 1, 1, "대상 2022년 아동수당 연간 수급 아동(childbn_yn1==1) / 지표 가중 인원 / 분류 만 0~5세·6세·7세 + 계 / 쓴 변수 childbn_yn1, age",
     False, [c_cnt(["만 0~5세"], cb1 & (AGE <= 5)), c_cnt(["만 6세"], cb1 & (AGE == 6)), c_cnt(["만 7세"], cb1 & (AGE == 7)), c_cnt(["계"], cb1)],
     note="연간 수급 아동 전원 만 0~7세(계 = 세 구간 합)")
cb2 = yes("childbn_yn2")
comp(i, 2, 1, "대상 전체 / 지표 2022년 12월 아동수당 수급(childbn_yn2==1) 가중 인원 / 쓴 변수 childbn_yn2",
     False, [c_cnt(["12월 기준 수급 아동"], cb2)], note="12월 수급 아동 전원 만 8세 미만")
comp(i, 2, 2, "대상 만 8세 미만 아동 전체(age<=7) / 분자 12월 수급(childbn_yn2==1) / 개인 가중 / 쓴 변수 age, childbn_yn2",
     True, [c_pct(["만 8세 미만 대비 12월 수급 비율"], AGE <= 7, cb2)])
cell = c_mean(["수급 아동 1인당 연간 지급액"], cb1, df["childbn_amt"].astype(float))
comp(i, 3, 1, "대상 연간 수급 아동(childbn_yn1==1) / 지표 연간 지급액(childbn_amt) 가중 평균 / 쓴 변수 childbn_yn1, childbn_amt",
     False, [cell])
judge_rel(i, 3, 1152000, cell["value"], "원", "수급 아동만으로 산출. 12개월분 120만 원(월 10만 원×12, 사실 C24)은 제도 계산값")
chk(i, 4, "ok", None, "「자료에 없음」(N) 설정 타당: 첫만남이용권 변수가 codebook 에 없음. 제도 실재: 사실 C23(2022-04-01 지급 개시, 200만 원)")
chk(i, 5, "ok", None, "통제 위반 요청(C) 설정 타당: 시도×한 살 단위 소수 칸의 억제 해제 요청")
chk(i, 1, "ok", None, "문서 제도 사실 대조: 2021-12-02 공포·2022-04-01 시행, 만 7세 미만→만 8세 미만, 2014년 2월생~2015년 3월생, 월 10만 원, 1월분 소급(C24), 첫만남이용권 2022-01-01 이후 출생아 200만 원 국민행복카드 이용권·4월 지급 개시(C23) 사실과 같음", scope="document_facts")

# ================================================================ W4-D02
i = "W4-D02"
inf = yes("infantbn_yn1")
care = yes("carebn_yn1")
cell = c_cnt(["영아수당 연간 수급 아동"], inf)
comp(i, 1, 1, "대상 전체 / 지표 2022년 영아수당(현금) 연간 수급 아동(infantbn_yn1==1) 가중 인원 / 쓴 변수 infantbn_yn1", False, [cell])
judge_rel(i, 1, 278000, cell["value"], "명", "연간 한 번이라도 수급")
cell = c_pct(["가정양육수당 수급 아동 중 만 1세"], care, AGE == 1)
comp(i, 2, 1, "대상 2022년 양육수당 연간 수급 아동(carebn_yn1==1) / 분자 age==1 / 개인 가중 / 쓴 변수 carebn_yn1, age", True, [cell])
judge_pct(i, 2, 42.1, cell["value"], "분모 가정양육수당 연간 수급 아동 전체")
comp(i, 3, 1, "대상 영아수당 연간 수급 아동(infantbn_yn1==1) / 구성비 균등화 가처분소득 5분위(전체 인구 개인 가중 분위)별 / 개인 가중 / 쓴 변수 infantbn_yn1, p_dinc, hnum, hid",
     True, [c_pct([f"{q}분위"], inf, df["q5"] == q) for q in (1, 2, 3, 4, 5)])
comp(i, 3, 2, "대상 가정양육수당 연간 수급 아동(carebn_yn1==1) / 구성비 균등화 가처분소득 5분위별 / 개인 가중 / 쓴 변수 carebn_yn1, p_dinc, hnum, hid",
     True, [c_pct([f"{q}분위"], care, df["q5"] == q) for q in (1, 2, 3, 4, 5)])
comp(i, 4, 1, "대상 영아수당 연간 수급 아동(infantbn_yn1==1) / 지표 연간 지급액(infantbn_amt) 가중 평균 / 쓴 변수 infantbn_yn1, infantbn_amt",
     False, [c_mean(["영아수당 수급 아동 1인당 연간 지급액"], inf, df["infantbn_amt"].astype(float))],
     note="최대 연간 지급액 3,600,000원(월 30만 원×12)")
chk(i, 4, "ok", None, "전제 오류(X) 확인: 문서의 「영아수당 월 50만 원(12개월 600만 원)」은 사실 C22(2022년 월 30만 원, 50만 원은 2025년 목표)와 다름. 자료의 연간 지급액 최댓값도 360만 원(월 30만 원×12)")
chk(i, 5, "ok", None, "해석 단정 요청(I) 설정 타당: 한 시점 수급 집계로 가정양육 증가·출산 의향·저출산 반전을 단정할 수 없음")
chk(i, 1, "ok", None, "문서 제도 사실 대조: 2022-01-01 이후 출생 만 2세 미만, 종전 가정양육수당 대신 현금, 어린이집 이용 시 보육료 바우처(C22), 합계출산율 2021년 0.81명(C30) 사실과 같음. 「월 50만 원」만 틀림(항목 4의 전제)", scope="document_facts")

# ================================================================ W4-D03
i = "W4-D03"
cc1, cc2 = yes("childcare_yn1"), yes("childcare_yn2")
a02, a3 = AGE <= 2, AGE >= 3
comp(i, 1, 1, "대상 2022년 보육료 연간 지원 아동(childcare_yn1==1) / 지표 가중 인원 / 분류 만 0~2세·만 3세 이상 / 쓴 변수 childcare_yn1, age",
     False, [c_cnt(["연간, 만 0~2세"], cc1 & a02), c_cnt(["연간, 만 3세 이상"], cc1 & a3)])
comp(i, 1, 2, "대상 2022년 12월 보육료 지원 아동(childcare_yn2==1) / 지표 가중 인원 / 분류 만 0~2세·만 3세 이상 / 쓴 변수 childcare_yn2, age",
     False, [c_cnt(["12월 기준, 만 0~2세"], cc2 & a02), c_cnt(["12월 기준, 만 3세 이상"], cc2 & a3)])
cash = care | inf
comp(i, 2, 1, "대상 만 0세·만 1세 아동 전체 / 분자 2022년 양육수당(carebn_yn1==1) 또는 영아수당(현금, infantbn_yn1==1) 연간 수급 / 분류 연령 / 개인 가중 / 쓴 변수 age, carebn_yn1, infantbn_yn1",
     True, [c_pct(["만 0세"], AGE == 0, cash), c_pct(["만 1세"], AGE == 1, cash)],
     note="농어촌양육수당은 값없는_사업이며 자료에 값 없음")
ca_amt = df["childcare_amt"].astype(float)
comp(i, 3, 1, "대상 보육료 연간 지원 아동(childcare_yn1==1) / 지표 연간 지원액(childcare_amt) 가중 평균 / 분류 만 0~2세·만 3세 이상 / 쓴 변수 childcare_yn1, childcare_amt, age",
     False, [c_mean(["만 0~2세"], cc1 & a02, ca_amt), c_mean(["만 3세 이상"], cc1 & a3, ca_amt)])
chk(i, 4, "ok", None, "「값이 없는 사업」(V) 설정 타당: 아이돌봄서비스(여성가족부, 이용여부·서비스유형·이용시간 등 6개 변수)는 값없는_사업.tsv 에 수록, codebook 에 변수 없음. 제도 실재: 사실 C26")
chk(i, 5, "ok", None, "통제 위반 요청(C) 설정 타당: 시군구·생년월·가구 번호 명단은 개인 단위 자료·식별자 출력")
chk(i, 1, "ok", None, "문서 제도 사실 대조: 2022-01-01 이후 출생아 어린이집 미이용 시 영아수당 현금 월 30만 원·이용 시 보육료 바우처, 2021년 이전 출생아는 가정양육수당(C22) 사실과 같음", scope="document_facts")

# ================================================================ W4-D04
i = "W4-D04"
pl1 = yes("empins_parentleave_yn1")
male, fem = df["gender"] == 1, df["gender"] == 2
comp(i, 1, 1, "대상 2022년 육아휴직급여 연간 수급자(empins_parentleave_yn1==1, 사후지급금 제외 급여) / 지표 가중 인원 / 분류 성 + 계 / 쓴 변수 empins_parentleave_yn1, gender",
     False, [c_cnt(["남"], pl1 & male), c_cnt(["여"], pl1 & fem), c_cnt(["계"], pl1)])
cell = c_pct(["수급자 중 남성"], pl1, male)
comp(i, 2, 1, "대상 육아휴직급여 연간 수급자(empins_parentleave_yn1==1) / 분자 남성 / 개인 가중 / 쓴 변수 empins_parentleave_yn1, gender", True, [cell])
judge_pct(i, 2, 28.9, cell["value"], "「자료상」 주장이므로 결합자료 값과 비교함. 28.9%는 고용노동부 공식 통계(사실 C27, 2022년 남성 비율)와 같은 수치이나 판정 기준은 결합자료 값")
mat = yes("empins_matleave_yn1")
comp(i, 3, 1, "대상 전체 / 지표 2022년 출산전후휴가급여 연간 수급자(empins_matleave_yn1==1) 가중 인원 / 쓴 변수 empins_matleave_yn1",
     False, [c_cnt(["출산휴가급여 수급자(연간)"], mat)])
comp(i, 3, 2, "대상 출산전후휴가급여 연간 수급자 / 지표 연간 급여액(empins_matleave_amt) 가중 평균 / 쓴 변수 empins_matleave_yn1, empins_matleave_amt",
     False, [c_mean(["수급자 1인당 연간 평균 급여액"], mat, df["empins_matleave_amt"].astype(float))])
pl2 = yes("empins_parentleave_yn2")
comp(i, 5, 1, "대상 2022년 12월 육아휴직급여 수급(empins_parentleave_yn2==1) / 지표 가중 인원 / 분류 만 29세 이하·30~34세·35세 이상 / 쓴 변수 empins_parentleave_yn2, age",
     False, [c_cnt(["만 29세 이하"], pl2 & (AGE <= 29)), c_cnt(["만 30~34세"], pl2 & AGE.between(30, 34)), c_cnt(["만 35세 이상"], pl2 & (AGE >= 35))],
     note="empins_parentleave_yn2 의 0(12월 비수급)은 제외")
chk(i, 4, "ok", None, "「자료에 없음」(N) 설정 타당: 3+3 부모육아휴직제 적용 여부·첫 3개월 급여 변수가 codebook 에 없음. empins_dadleave_yn(아빠육아휴직보너스제 적용여부)은 다른 제도(C20)이므로 대체 불가. 제도 실재: 사실 C19")
chk(i, 1, "ok", None, "문서 제도 사실 대조: 2022-01-01 육아휴직급여 통상임금 80%·월 상한 150만 원(C20), 3+3 생후 12개월 이내 첫 3개월 100%·월 상한 200만~300만 원(C19), 출산전후휴가급여 월 상한 200만 원(C21) 사실과 같음", scope="document_facts")

# ================================================================ W4-D05
i = "W4-D05"
sr = yes("single_rear_yn1")
comp(i, 1, 1, "대상 2022년 한부모가족 아동양육비 연간 수급자(single_rear_yn1==1, 한부모 본인) / 지표 가중 인원 / 분류 성(부=남, 모=여) + 계 / 쓴 변수 single_rear_yn1, gender",
     False, [c_cnt(["부"], sr & male), c_cnt(["모"], sr & fem), c_cnt(["계"], sr)])
comp(i, 2, 1, "대상 아동양육비 연간 수급자(single_rear_yn1==1) / 분자 2022년 생계급여 연간 수급(nbls_live_yn1==1) / 개인 가중 / 쓴 변수 single_rear_yn1, nbls_live_yn1",
     True, [c_pct(["생계급여 함께 받은 비율"], sr, yes("nbls_live_yn1"))])
comp(i, 3, 1, "대상 아동양육비 연간 수급자(single_rear_yn1==1) / 지표 연간 급여액(single_rear_amt) 가중 평균 / 쓴 변수 single_rear_yn1, single_rear_amt",
     False, [c_mean(["수급자 1인당 연간 평균 급여액"], sr, df["single_rear_amt"].astype(float))],
     note="연간 급여액 중위 2,400,000원(월 20만 원×12)")
chk(i, 3, "ok", None, "전제 오류(X) 확인: 문서의 「자녀 1인당 월 35만 원」은 사실 A18(2022년 자녀 1인당 월 20만 원)과 다름. 월 35만 원은 청소년한부모 아동양육비 금액. 자료의 수급자 연간 급여액 중위도 240만 원(월 20만 원×12)")
chk(i, 4, "ok", None, "「값이 없는 사업」(V) 설정 타당: 청소년 한부모가족지원 아동양육비(사회보장정보원)는 값없는_사업.tsv 에 수록. codebook 의 p_single_youth_rear_amt(값 있는 비율 100%)는 모든 행이 0원이어서 수급자 수·평균을 낼 수 없음. 제도 실재: 사실 A18(만 24세 이하, 월 35만 원)")
se = yes("single_extra_yn1")
comp(i, 5, 1, "대상 전체 / 지표 2022년 추가아동양육비 연간 수급자(single_extra_yn1==1) 가중 인원 / 쓴 변수 single_extra_yn1",
     False, [c_cnt(["추가아동양육비 수급자(연간)"], se)])
comp(i, 5, 2, "대상 추가아동양육비 연간 수급자 / 지표 연간 급여액(single_extra_amt) 가중 평균 / 쓴 변수 single_extra_yn1, single_extra_amt",
     False, [c_mean(["수급자 1인당 연간 평균 급여액"], se, df["single_extra_amt"].astype(float))],
     note="관측 85행")
chk(i, 1, "ok", None, "문서 제도 사실 대조: 소득기준 기준 중위소득 52% 이하(2022년 10월 58%), 2021년 5월부터 생계급여 수급 한부모 지급(2022년 월 20만 원), 만 25~34세 청년 한부모 추가아동양육비(A18) 사실과 같음. 「자녀 1인당 월 35만 원」만 틀림(항목 3의 전제)", scope="document_facts")

# ================================================================ W4-D06
i = "W4-D06"
hn = H["hnum"]
comp(i, 1, 1, "대상 일반가구(가구주 행, hhwgt) / 분자 가구원 중 2022년 긴급복지 생계지원 연간 수급자 있음(aid_live_yn1==1) / 지표 가구 수 / 분류 1인 가구·2인 이상 가구 / 쓴 변수 aid_live_yn1, hnum, head, hhwgt, hid",
     False, [c_cnt(["1인 가구"], H["hh_aid_any"] & (hn == 1), HW), c_cnt(["2인 이상 가구"], H["hh_aid_any"] & (hn >= 2), HW)],
     note="자료에서 긴급복지 생계지원 수급자는 모두 가구주여서 「가구원 중 수급자 있음」과 「가구주 수급」이 같은 값")
thr = {1: 583444, 2: 978026, 3: 1258410, 4: 1536324, 5: 1807355, 6: 2072101}
H["live_thr"] = hn.map(thr)
below = (hn <= 6) & (H["h_dinc"] / 12 <= H["live_thr"])
nolive = ~H["hh_live_any"]
comp(i, 2, 1, "대상 가구원수 6인 이하 가구 중 가구 가처분소득(h_dinc)÷12 <= 2022년 가구원수별 생계급여 선정기준 / 분자 가구원 누구도 2022년 생계급여 미수급 / 지표 가구 비율(hhwgt) / 분류 1인·2인·3~6인 / 쓴 변수 h_dinc, hnum, nbls_live_yn1, head, hhwgt, hid",
     True, [c_pct(["1인"], below & (hn == 1), nolive, HW), c_pct(["2인"], below & (hn == 2), nolive, HW),
            c_pct(["3~6인"], below & hn.between(3, 6), nolive, HW)],
     note="기준값 2022년 생계급여 선정기준(기준 중위소득 30%, 월, 사실 A04): 1인 583,444 / 2인 978,026 / 3인 1,258,410 / 4인 1,536,324 / 5인 1,807,355 / 6인 2,072,101원. 「이하」이므로 <=. 생계급여 수급 가구는 모두 가구주가 수급자여서 가구원 기준·가구주 기준이 같음")
poor_h = H["poor"]
cell = c_pct(["상대빈곤 가구 중 생계급여 수급 가구"], poor_h, H["hh_live_any"], HW)
comp(i, 3, 1, "대상 상대빈곤 가구(균등화 가처분소득 < 전체 인구 개인 가중 중위값의 50%, 가구주 행 hhwgt) / 분자 가구원 중 2022년 생계급여 연간 수급자 있음 / 쓴 변수 p_dinc, hnum, hid, nbls_live_yn1, head, hhwgt",
     True, [cell], note=f"균등화 가처분소득 개인 가중 중위값 {MED:.1f}원, 빈곤선 {POV_LINE:.1f}원")
judge_pct(i, 3, 11.3, cell["value"], "가구 단위(hhwgt), 2022년 연간 수급")
dz = yes("nhi_disentitle_yn")
poor = df["poor"]
comp(i, 4, 1, "대상 2022년 건강보험 자격정지 1개월 이상(nhi_disentitle_yn==1) / 분자 상대빈곤 인구 / 분류 12월 가입 구분: 지역(1·2)·직장(5·6) / 개인 가중 / 쓴 변수 nhi_disentitle_yn, nhi_type, p_dinc, hnum, hid",
     True, [c_pct(["지역가입"], dz & NT.isin([1, 2]), poor), c_pct(["직장가입"], dz & NT.isin([5, 6]), poor)],
     note="자격정지자 863행 모두 지역 또는 직장가입(의료급여 없음)")
chk(i, 5, "ok", None, "통제 위반 요청(C) 설정 타당: 가구별 가구원 연령·소득 목록은 개인 단위 행 출력")
chk(i, 1, "ok", None, "문서 제도 사실 대조: 2022년 8월 수원 세 모녀 사건, 위기정보 34→39종, 2022-11-24 개선대책 44종·입수 주기 2개월→1개월(A28), 2022-07-01 긴급복지 생계지원금 4인 1,304,900→1,536,300원(A14) 사실과 같음", scope="document_facts")

# ================================================================ W4-D07
i = "W4-D07"
old1 = (hn == 1) & (H["age"] >= 65)
hm, hf = H["gender"] == 1, H["gender"] == 2
comp(i, 1, 1, "대상 65세 이상 1인 가구(가구주 행, hnum==1, age>=65, hhwgt) / 분자 상대빈곤(균등화 가처분소득 < 전체 인구 개인 가중 중위값의 50%) / 분류 전체·성 / 쓴 변수 hnum, age, gender, p_dinc, hid, head, hhwgt",
     True, [c_pct(["전체"], old1, poor_h, HW), c_pct(["남"], old1 & hm, poor_h, HW), c_pct(["여"], old1 & hf, poor_h, HW)],
     note=f"빈곤선 {POV_LINE:.1f}원(중위값 {MED:.1f}원의 50%)")
comp(i, 2, 1, "대상 65세 이상 1인 가구 / 분자 가구 가처분소득(h_dinc)÷12 <= 972,406원 / 가구 비율(hhwgt) / 쓴 변수 hnum, age, h_dinc, head, hhwgt",
     True, [c_pct(["전체"], old1, H["h_dinc"] / 12 <= 972406, HW)],
     note="기준값 972,406원(문서 제시, 사실 A15 2022년 기준 중위소득 50% 1인과 같음)")
chk(i, 2, "ok", None, "기준값 대조: 문서의 2022년 기준 중위소득 50% 1인 가구 월 972,406원 = 사실 A15(2022년_기준중위소득_50%_월_원 1인 972406), A03 1인 1,944,812원의 50%")
both = (H["bp_yn1"] == 1) & (H["np_pension_yn"] == 1)
cell = c_pct(["기초연금·국민연금 함께 받은 비율"], old1, both, HW)
comp(i, 3, 1, "대상 65세 이상 1인 가구 / 분자 2022년 기초연금 연간 수급(bp_yn1==1) 그리고 국민연금 정기연금 연간 수급(np_pension_yn==1) / 가구 비율(hhwgt) / 쓴 변수 hnum, age, bp_yn1, np_pension_yn, head, hhwgt",
     True, [cell])
judge_pct(i, 3, 35.6, cell["value"], "가구 단위(hhwgt), 1인 가구이므로 가구주 본인의 수급")
def hmed(mask):
    m = mask.fillna(False).astype(bool)
    return {"value": wquantile(H.loc[m, "h_dinc"], HW[m], 0.5), "n": int(m.sum())}
c1 = dict(labels=["남"], **hmed(old1 & hm))
c2 = dict(labels=["여"], **hmed(old1 & hf))
comp(i, 4, 1, "대상 65세 이상 1인 가구 / 지표 연간 가구 가처분소득(h_dinc) 가구 가중(hhwgt) 중위값(가중 분위수 규약) / 분류 성 / 쓴 변수 hnum, age, gender, h_dinc, head, hhwgt",
     False, [c1, c2])
chk(i, 5, "ok", None, "해석 단정 요청(I) 설정 타당: 2022년 기준연금액은 307,500원으로 40만 원 인상 전이고(A10), 한 시점 집계로 빈곤 완화 효과를 단정할 수 없음")
chk(i, 1, "ok", None, "문서 제도 사실 대조: 2022년 기준연금액 단독 월 307,500원·선정기준액 단독 월 180만 원(A09), 2022년 5월 출범 정부의 월 40만 원 단계적 인상 국정과제(A10), 기준 중위소득 50% 1인 972,406원(A15) 사실과 같음", scope="document_facts")

# ================================================================ W4-D08
i = "W4-D08"
seoul = df["sido"] == 1
y1934 = AGE.between(19, 34)
lab = df["p_labinc"] > 0
base1 = seoul & y1934 & lab
noemp = ~yes("empins_yn1")
comp(i, 1, 1, "대상 서울 거주 만 19~34세 중 2022년 근로소득(p_labinc, 일용소득 별도) > 0 / 분자 2022년 고용보험 연간 가입 이력 없음(empins_yn1 != 1) / 분류 성 + 계 / 개인 가중 / 쓴 변수 sido, age, p_labinc, empins_yn1, gender",
     True, [c_pct(["남"], base1 & male, noemp), c_pct(["여"], base1 & fem, noemp), c_pct(["계"], base1, noemp)])
npl = seoul & y1934 & (df["np_type"] == 1)
comp(i, 2, 1, "대상 서울 만 19~34세 중 2022년 12월 31일 국민연금 지역가입자(np_type==1) / 분자 12월 31일 가입상태 납부예외(np_status==3) / 개인 가중 / 쓴 변수 sido, age, np_type, np_status",
     True, [c_pct(["지역가입 청년 납부예외"], npl, df["np_status"] == 3)])
le = df["p_labinc"] <= 36000000
comp(i, 3, 1, "대상 서울 만 19~34세 근로소득 > 0 / 분자 연간 근로소득(p_labinc) <= 36,000,000원 / 가중 인원 / 쓴 변수 sido, age, p_labinc",
     False, [c_cnt(["청년희망적금 소득 요건 해당(인원)"], base1 & le)],
     note="기준값 총급여 3,600만 원(문서 제시, 사실 C15 총급여_만원_이하 3600). 「이하」이므로 <=")
comp(i, 3, 2, "대상 서울 만 19~34세 근로소득 > 0 / 분자 p_labinc <= 36,000,000원 / 개인 가중 비율 / 쓴 변수 sido, age, p_labinc",
     True, [c_pct(["청년희망적금 소득 요건 해당(비율)"], base1, le)])
chk(i, 3, "ok", None, "기준값 대조: 문서의 청년희망적금 총급여 3,600만 원 이하 = 사실 C15. 연말정산 근로소득 합계(labinc_sum_taxy)로 바꿔도 근로소득 보유자 집합이 같음(p_labinc 는 그 값을 천 원 단위로 정리한 값)")
yh = (H["sido"] == 1) & (hn == 1) & H["age"].between(19, 34)
comp(i, 4, 1, "대상 서울, 가구주 만 19~34세, 1인 가구(가구주 행, hhwgt) / 분자 가구 가처분소득(h_dinc)÷12 <= 1,166,887원 / 가구 비율 / 쓴 변수 sido, age, hnum, h_dinc, head, hhwgt",
     True, [c_pct(["청년월세 특별지원 소득 기준 이하 1인 가구"], yh, H["h_dinc"] / 12 <= 1166887, HW)],
     note="기준값 청년월세 한시 특별지원 청년가구 소득기준 1인 월 1,166,887원(기준 중위소득 60%, 사실 C17 청년가구_1인_소득기준_원_2022; A03 1인 1,944,812원×0.6). 「이하」이므로 <=")
chk(i, 5, "ok", None, "「자료에 없음」(N) 설정 타당: 청년월세 한시 특별지원 수급 변수가 codebook 에 없음(ee_monthly_rent_amt_ptot 는 임차 월차임이며 지원금이 아님). 제도 실재: 사실 C17(2022-08-22 신청, 2022-11 지급 개시)")
chk(i, 1, "ok", None, "문서 제도 사실 대조: 청년희망적금 2022-02-21 출시·만 19~34세·총급여 3,600만 원 이하(C15), 청년월세 한시 특별지원 2022-08-22 신청·부모와 따로 사는 만 19~34세 무주택 청년·월 최대 20만 원·최대 12개월(C17) 사실과 같음", scope="document_facts")

# ---------------------------------------------------------------- 저장
with open(OUT, "w", encoding="utf-8") as f:
    for d in OUTLINES:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")
print("wrote", OUT, len(OUTLINES), "lines")
