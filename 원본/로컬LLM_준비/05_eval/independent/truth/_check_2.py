#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""독립 검산 2(이중 입력).

질문 문장(check_input_2.jsonl)과 codebook.tsv, 자료_규약.md만 보고 pandas로 직접 계산함.
분석 함수(ssda)와 다른 사람의 답·계산 파일은 사용하지 않음. 개인 단위 행은 출력하지 않음.
산출: check_2.jsonl (산출을 요구하는 차례마다 한 줄)
"""
import json
import numpy as np
import pandas as pd

DATA = '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
OUT = '/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/truth/check_2.jsonl'

df = pd.read_parquet(DATA)
N = len(df)
W_IND = df['indwgt'].astype(float).to_numpy()
W_HH = df['hhwgt'].astype(float).to_numpy()

age = df['age'].to_numpy()
gender = df['gender'].to_numpy()
sido = df['sido'].to_numpy()
hnum = df['hnum'].to_numpy()
head = (df['head'].to_numpy() == 1)
ALL = np.ones(N, dtype=bool)


def eq1(col):
    """여부 변수: 해당하면 1(== 1). 결측·0은 미해당."""
    return (df[col] == 1).fillna(False).to_numpy(dtype=bool)


def num(col):
    """수치 변수(결측은 NaN)."""
    return pd.to_numeric(df[col], errors='coerce').astype(float).to_numpy()


# ---------- 가중 분위수(자료 규약) ----------
def wquantile(x, wt, q):
    """오름차순으로 놓고 가중치 누적합이 전체의 q배에 처음 이르는 값."""
    x = np.asarray(x, float)
    wt = np.asarray(wt, float)
    ok = ~np.isnan(x)
    x, wt = x[ok], wt[ok]
    if len(x) == 0:
        return None
    o = np.argsort(x, kind='mergesort')
    x, wt = x[o], wt[o]
    c = np.cumsum(wt)
    i = int(np.searchsorted(c, q * c[-1], side='left'))
    return float(x[min(i, len(x) - 1)])


# ---------- 파생: 균등화 가처분소득, 빈곤, 소득 5분위 ----------
hh_dinc = df.groupby('hid')['p_dinc'].transform('sum').astype(float).to_numpy()  # 가구 가처분소득(원)
eqinc = hh_dinc / np.sqrt(hnum.astype(float))
MED = wquantile(eqinc, W_IND, 0.5)
poor = eqinc < 0.5 * MED
BOUNDS = [wquantile(eqinc, W_IND, q) for q in (0.2, 0.4, 0.6, 0.8)]
inc5 = np.zeros(N, dtype=int)
for b in BOUNDS:
    inc5 += (eqinc >= b).astype(int)  # 경계값 이상이면 위 분위

# ---------- 분류 기준 ----------
SIDO_NAMES = ['서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종', '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주']
G_SIDO = [(nm, sido == i + 1) for i, nm in enumerate(SIDO_NAMES)]
G_SEX = [('남', gender == 1), ('여', gender == 2)]
G_AGE3 = [('0~17세', age <= 17), ('18~64세', (age >= 18) & (age <= 64)), ('65세 이상', age >= 65)]
G_AGE6 = [('0~17세', age <= 17), ('18~34세', (age >= 18) & (age <= 34)), ('35~49세', (age >= 35) & (age <= 49)),
          ('50~64세', (age >= 50) & (age <= 64)), ('65~74세', (age >= 65) & (age <= 74)), ('75세 이상', age >= 75)]
G_HS4 = [('1인', hnum == 1), ('2인', hnum == 2), ('3인', hnum == 3), ('4인 이상', hnum >= 4)]
G_INC5 = [(f'{k + 1}분위', inc5 == k) for k in range(5)]
G_NONE = [(None, ALL)]


# ---------- 집계 ----------
def s_rate(numer, denom, wt=W_IND):
    def fn(m):
        d = denom & m
        a = numer & d
        n, nn = int(d.sum()), int(a.sum())
        v = None if n == 0 else float(100.0 * wt[a].sum() / wt[d].sum())
        return {'value': v, 'n': n, 'n_num': nn}
    return fn


def s_count(where, wt=W_IND):
    def fn(m):
        d = where & m
        n = int(d.sum())
        return {'value': None if n == 0 else float(wt[d].sum()), 'n': n}
    return fn


def s_mean(x, where, wt=W_IND):
    def fn(m):
        d = where & m & ~np.isnan(x)
        n = int(d.sum())
        return {'value': None if n == 0 else float((wt[d] * x[d]).sum() / wt[d].sum()), 'n': n}
    return fn


def s_total(x, where, wt=W_IND):
    def fn(m):
        d = where & m & ~np.isnan(x)
        n = int(d.sum())
        return {'value': None if n == 0 else float((wt[d] * x[d]).sum()), 'n': n}
    return fn


def s_quant(x, where, q, wt=W_IND):
    def fn(m):
        d = where & m & ~np.isnan(x)
        n = int(d.sum())
        return {'value': None if n == 0 else wquantile(x[d], wt[d], q), 'n': n}
    return fn


def cells(fn, groups=G_NONE):
    out = []
    for lab, m in groups:
        c = {'labels': [] if lab is None else [lab]}
        c.update(fn(m))
        out.append(c)
    return out


def share_cells(x, cats, base, wt=W_IND):
    """범주형 변수의 구성비(%): 분모는 base 가운데 변수 값이 있는 행."""
    den = base & ~np.isnan(x)
    out = []
    for lab, code in cats:
        c = {'labels': [lab]}
        c.update(s_rate(x == code, den, wt)(ALL))
        out.append(c)
    return out


RECS = []


def add(id_, turn, reading, pct, cells_, reading_no=1, ambiguous=False, note=''):
    RECS.append({'id': id_, 'turn': turn, 'reading_no': reading_no, 'reading': reading, 'pct': pct,
                 'cells': cells_, 'ambiguous': ambiguous, 'note': note})


a65 = age >= 65

# ================= C =================
oldcare = eq1('oldcare_yn1')
add('C01a', 1, '대상: 65세 이상(개인, indwgt) / 분자: 노인맞춤돌봄서비스 연간 이용(oldcare_yn1==1) / 분류: 없음 / 사용 변수: age, oldcare_yn1',
    True, cells(s_rate(oldcare, a65)))
add('C01b', 1, '대상: 75세 이상(개인, indwgt) / 분자: 노인맞춤돌봄서비스 연간 이용(oldcare_yn1==1) / 분류: 없음 / 사용 변수: age, oldcare_yn1',
    True, cells(s_rate(oldcare, age >= 75)))

dis = eq1('dis_yn')
severe = (num('dis_grade_1') == 1)
add('C02a', 1, '대상: 등록장애인(dis_yn==1, 개인, indwgt) / 분자: 종합장애정도가 심한 장애(dis_grade_1==1) / 분류: 성 / 사용 변수: dis_yn, dis_grade_1, gender',
    True, cells(s_rate(severe, dis), G_SEX))
add('C02b', 1, '대상: 등록장애인 중 종합장애정도가 심한 장애(dis_yn==1 and dis_grade_1==1)의 가중 인원(indwgt) / 분류: 성 / 사용 변수: dis_yn, dis_grade_1, gender',
    False, cells(s_count(dis & severe), G_SEX))

add('C03a', 1, '대상: 전체 가구(가구주 행 head==1, hhwgt) / 분자: 1인 가구(hnum==1) / 분류: 시도 / 사용 변수: head, hnum, sido, hhwgt',
    True, cells(s_rate(hnum == 1, head, W_HH), G_SIDO))
add('C03b', 1, '대상: 전체 인구(개인, indwgt) / 분자: 1인 가구에 속한 사람(hnum==1) / 분류: 시도 / 사용 변수: hnum, sido, indwgt',
    True, cells(s_rate(hnum == 1, ALL), G_SIDO))

h_prop = num('h_prop')
add('C04a', 1, '대상: 가구 재산 5억원 이상(h_prop>=500000000) 가구 수(가구주 행, hhwgt) / 분류: 없음 / 사용 변수: head, h_prop, hhwgt',
    False, cells(s_count(head & (h_prop >= 5e8), W_HH)))
add('C04b', 1, '대상: 가구 재산 5억원 이상(h_prop>=500000000) 가구에 속한 사람 수(개인, indwgt) / 분류: 없음 / 사용 변수: h_prop, indwgt',
    False, cells(s_count(h_prop >= 5e8)))

add('C05a', 1, '대상: 육아휴직급여 연간 수급자(empins_parentleave_yn1==1)의 가중 인원(indwgt) / 분류: 성 / 사용 변수: empins_parentleave_yn1, gender',
    False, cells(s_count(eq1('empins_parentleave_yn1')), G_SEX))
add('C05b', 1, '대상: 육아휴직급여 12월 기준 수급자(empins_parentleave_yn2==1)의 가중 인원(indwgt) / 분류: 성 / 사용 변수: empins_parentleave_yn2, gender',
    False, cells(s_count(eq1('empins_parentleave_yn2')), G_SEX))

a6_17 = (age >= 6) & (age <= 17)
add('C06a', 1, '대상: 6~17세(개인, indwgt) / 분자: 교육급여 수급권 연간(nbls_edu_yn1==1) / 분류: 없음 / 사용 변수: age, nbls_edu_yn1',
    True, cells(s_rate(eq1('nbls_edu_yn1'), a6_17)))
add('C06b', 1, '대상: 6~17세(개인, indwgt) / 분자: 교육급여 수급권 12월 기준(nbls_edu_yn2==1) / 분류: 없음 / 사용 변수: age, nbls_edu_yn2',
    True, cells(s_rate(eq1('nbls_edu_yn2'), a6_17)))

aid = eq1('aid_live_yn1')
aid_amt = num('aid_live_amt')
add('C07a', 1, '대상: 긴급복지 생계지원 연간 수급자(aid_live_yn1==1, 개인, indwgt) / 대상 변수: 생계지원 급여액(aid_live_amt) 가중 평균 / 분류: 없음 / 사용 변수: aid_live_yn1, aid_live_amt',
    False, cells(s_mean(aid_amt, aid)))
add('C07b', 1, '대상: 긴급복지 생계지원 연간 수급자(aid_live_yn1==1, 개인, indwgt) / 대상 변수: 생계지원 급여액(aid_live_amt) 가중 중위수(q=0.5) / 분류: 없음 / 사용 변수: aid_live_yn1, aid_live_amt',
    False, cells(s_quant(aid_amt, aid, 0.5)))

lt_bn = eq1('ltcare_bn_yn')
lt_inst = eq1('ltcare_institute_yn')
add('C08a', 1, '대상: 65세 이상 인구 전체(개인, indwgt) / 분자: 장기요양 시설이용급여 수급(ltcare_institute_yn==1) / 분류: 없음 / 사용 변수: age, ltcare_institute_yn',
    True, cells(s_rate(lt_inst, a65)),
    note='시설급여 변수는 ltcare_institute_yn(시설이용급여 수급여부)로 봄. ltcare_carecenter_yn(노인요양시설 입소 여부)와 자료상 값이 모두 같음')
add('C08b', 1, '대상: 65세 이상 장기요양 수급자(age>=65 and ltcare_bn_yn==1, 개인, indwgt) / 분자: 장기요양 시설이용급여 수급(ltcare_institute_yn==1) / 분류: 없음 / 사용 변수: age, ltcare_bn_yn, ltcare_institute_yn',
    True, cells(s_rate(lt_inst, a65 & lt_bn)),
    note='시설급여 변수는 ltcare_institute_yn. ltcare_carecenter_yn과 자료상 값이 모두 같음')

evou = eq1('evou_yn')
add('C09a', 1, '대상: 전체 인구(개인, indwgt) / 분자: 에너지바우처 이용(evou_yn==1) / 분류: 없음 / 사용 변수: evou_yn',
    True, cells(s_rate(evou, ALL)))
add('C09b', 1, '대상: 생계급여 연간 수급자(nbls_live_yn1==1, 개인, indwgt) / 분자: 에너지바우처 이용(evou_yn==1) / 분류: 없음 / 사용 변수: nbls_live_yn1, evou_yn',
    True, cells(s_rate(evou, eq1('nbls_live_yn1'))))

out_dur = num('nhi_out_dur')
add('C10a', 1, '대상: 65세 이상 전체(외래 미이용자 포함, 개인, indwgt) / 분자: 외래 내원일수 30일 이상(nhi_out_dur>=30) / 분류: 없음 / 사용 변수: age, nhi_out_dur',
    True, cells(s_rate(out_dur >= 30, a65)))
add('C10b', 1, '대상: 65세 이상 전체(외래 미이용자 포함, 개인, indwgt) / 분자: 외래 내원일수 30일 초과(nhi_out_dur>30) / 분류: 없음 / 사용 변수: age, nhi_out_dur',
    True, cells(s_rate(out_dur > 30, a65)))

js = eq1('unempbn_jobseekbn_yn')
js_dur = num('unempbn_jobseekbn_dur')
add('C11a', 1, '대상: 구직급여 연간 수급자(unempbn_jobseekbn_yn==1, 개인, indwgt) / 분자: 수급기간 120일 미만(unempbn_jobseekbn_dur<120) / 분류: 없음 / 사용 변수: unempbn_jobseekbn_yn, unempbn_jobseekbn_dur',
    True, cells(s_rate(js_dur < 120, js)))
add('C11b', 1, '대상: 구직급여 연간 수급자(unempbn_jobseekbn_yn==1, 개인, indwgt) / 분자: 수급기간 120일 이하(unempbn_jobseekbn_dur<=120) / 분류: 없음 / 사용 변수: unempbn_jobseekbn_yn, unempbn_jobseekbn_dur',
    True, cells(s_rate(js_dur <= 120, js)))

a18_59 = (age >= 18) & (age <= 59)
np_y = eq1('np_yn')
ei_y = eq1('empins_yn1')
add('C12a', 1, '대상: 18~59세(개인, indwgt) / 분자: 국민연금 연간 가입(np_yn==1)과 고용보험 연간 가입(empins_yn1==1) 모두 해당 / 분류: 없음 / 사용 변수: age, np_yn, empins_yn1',
    True, cells(s_rate(np_y & ei_y, a18_59)))
add('C12b', 1, '대상: 18~59세(개인, indwgt) / 분자: 국민연금 연간 가입(np_yn==1) 또는 고용보험 연간 가입(empins_yn1==1) 중 하나 이상 / 분류: 없음 / 사용 변수: age, np_yn, empins_yn1',
    True, cells(s_rate(np_y | ei_y, a18_59)))

gp = eq1('govp_pension_yn')
gp_amt = num('govp_pension_amt')
add('C13a', 1, '대상: 공무원연금 정기연금 수급자 중 남성(govp_pension_yn==1 and gender==1, 개인, indwgt) / 대상 변수: 정기연금 급여액(govp_pension_amt) 가중 평균 / 분류: 없음 / 사용 변수: govp_pension_yn, govp_pension_amt, gender',
    False, cells(s_mean(gp_amt, gp & (gender == 1))))
add('C13b', 1, '대상: 공무원연금 정기연금 수급자 중 여성(govp_pension_yn==1 and gender==2, 개인, indwgt) / 대상 변수: 정기연금 급여액(govp_pension_amt) 가중 평균 / 분류: 없음 / 사용 변수: govp_pension_yn, govp_pension_amt, gender',
    False, cells(s_mean(gp_amt, gp & (gender == 2))))

bp2 = eq1('bp_yn2')
add('C14a', 1, '대상: 충북(sido==11) 거주 65세 이상(개인, indwgt) / 분자: 기초연금 12월 기준 수급(bp_yn2==1) / 분류: 없음 / 사용 변수: sido, age, bp_yn2',
    True, cells(s_rate(bp2, a65 & (sido == 11))))
add('C14b', 1, '대상: 충남(sido==12) 거주 65세 이상(개인, indwgt) / 분자: 기초연금 12월 기준 수급(bp_yn2==1) / 분류: 없음 / 사용 변수: sido, age, bp_yn2',
    True, cells(s_rate(bp2, a65 & (sido == 12))))

POV_DEF = '빈곤(균등화 가처분소득 = 가구원 p_dinc 합계/√hnum 이 전체 인구 개인 가중 중위값의 50% 미만)'
add('C15a', 1, f'대상: 전체 인구(개인, indwgt) / 분자: {POV_DEF} / 분류: 시도 / 사용 변수: p_dinc, hid, hnum, sido, indwgt',
    True, cells(s_rate(poor, ALL), G_SIDO))
add('C15b', 1, f'대상: 전체 인구(개인, indwgt) / 분자: {POV_DEF} / 분류: 가구원수 4구간 / 사용 변수: p_dinc, hid, hnum, indwgt',
    True, cells(s_rate(poor, ALL), G_HS4))

# ================= F =================
out_amt = num('nhi_out_amt')
add('F01', 1, '대상: 65세 이상 중 외래 실적이 있는 사람(nhi_out_amt 값 있음, 개인, indwgt) / 대상 변수: 외래 전체 의과 의료기관 요양급여비용 총액(nhi_out_amt) 가중 평균 / 분류: 없음 / 사용 변수: age, nhi_out_amt',
    False, cells(s_mean(out_amt, a65)))
add('F01', 2, '대상: 65세 이상 여성 중 외래 실적이 있는 사람(개인, indwgt) / 대상 변수: nhi_out_amt 가중 평균 / 분류: 없음 / 사용 변수: age, gender, nhi_out_amt',
    False, cells(s_mean(out_amt, a65 & (gender == 2))))
add('F01', 3, '대상: 65세 이상 여성 중 외래 실적이 있는 사람(개인, indwgt) / 대상 변수: nhi_out_amt 가중 평균 / 분류: 시도 / 사용 변수: age, gender, sido, nhi_out_amt',
    False, cells(s_mean(out_amt, a65 & (gender == 2)), G_SIDO))

disp1 = eq1('disp_yn1')
dis18 = dis & (age >= 18)
add('F02', 1, '대상: 18세 이상 등록장애인(dis_yn==1 and age>=18, 개인, indwgt) / 분자: 장애인연금 연간 수급(disp_yn1==1) / 분류: 없음 / 사용 변수: dis_yn, age, disp_yn1',
    True, cells(s_rate(disp1, dis18)))
add('F02', 2, '대상: 18세 이상 등록장애인 중 종합장애정도가 심한 장애(dis_grade_1==1, 개인, indwgt) / 분자: 장애인연금 연간 수급(disp_yn1==1) / 분류: 없음 / 사용 변수: dis_yn, age, dis_grade_1, disp_yn1',
    True, cells(s_rate(disp1, dis18 & severe)))
add('F02', 3, '대상: 18세 이상·종합장애정도가 심한 등록장애인 중 장애인연금 연간 수급자(disp_yn1==1)의 가중 인원(indwgt) / 분류: 없음 / 사용 변수: dis_yn, age, dis_grade_1, disp_yn1',
    False, cells(s_count(dis18 & severe & disp1)),
    note='직전 차례 비율의 분자(수급 인원)를 인원으로 산출함')

js_amt = num('unempbn_jobseekbn_amt')
add('F03', 1, '대상: 구직급여 연간 수급자(unempbn_jobseekbn_yn==1)의 가중 인원(indwgt) / 분류: 연령대 6구간 / 사용 변수: unempbn_jobseekbn_yn, age',
    False, cells(s_count(js), G_AGE6))
add('F03', 2, '대상: 구직급여 연간 수급자(unempbn_jobseekbn_yn==1, indwgt) / 대상 변수: 구직급여 급여액(unempbn_jobseekbn_amt) 가중 합계(원) / 분류: 연령대 6구간 / 사용 변수: unempbn_jobseekbn_yn, unempbn_jobseekbn_amt, age',
    False, cells(s_total(js_amt, js), G_AGE6))
add('F03', 3, '대상: 구직급여 연간 수급자 중 여성(unempbn_jobseekbn_yn==1 and gender==2, indwgt) / 대상 변수: 구직급여 급여액(unempbn_jobseekbn_amt) 가중 합계(원) / 분류: 연령대 6구간 / 사용 변수: unempbn_jobseekbn_yn, unempbn_jobseekbn_amt, gender, age',
    False, cells(s_total(js_amt, js & (gender == 2)), G_AGE6),
    note='직전 차례의 산출(지급 총액)과 분류(연령대 6구간)를 이어받고 대상만 여성으로 좁힘')

a0_5 = age <= 5
cc1 = eq1('childcare_yn1')
cc2 = eq1('childcare_yn2')
add('F04', 1, '대상: 0~5세(개인, indwgt) / 분자: 보육료지원 연간 지원(childcare_yn1==1) / 분류: 시도 / 사용 변수: age, childcare_yn1, sido',
    True, cells(s_rate(cc1, a0_5), G_SIDO))
add('F04', 2, '대상: 0~5세(개인, indwgt) / 분자: 보육료지원 연간 지원(childcare_yn1==1) / 분류: 가구원수 4구간 / 사용 변수: age, childcare_yn1, hnum',
    True, cells(s_rate(cc1, a0_5), G_HS4))
add('F04', 3, '대상: 0~5세(개인, indwgt) / 분자: 보육료지원 12월 기준 지원(childcare_yn2==1) / 분류: 가구원수 4구간 / 사용 변수: age, childcare_yn2, hnum',
    True, cells(s_rate(cc2, a0_5), G_HS4))

hh65 = head & a65
add('F05', 1, '대상: 가구주가 65세 이상인 가구(head==1 and age>=65, hhwgt) / 대상 변수: 가구 재산(h_prop) 가중 평균 / 분류: 없음 / 사용 변수: head, age, h_prop, hhwgt',
    False, cells(s_mean(h_prop, hh65, W_HH)))
add('F05', 2, '대상: 가구주가 65세 이상인 1인 가구(head==1 and age>=65 and hnum==1, hhwgt) / 대상 변수: 가구 재산(h_prop) 가중 평균 / 분류: 없음 / 사용 변수: head, age, hnum, h_prop, hhwgt',
    False, cells(s_mean(h_prop, hh65 & (hnum == 1), W_HH)))
add('F05', 3, '대상: 가구주가 65세 이상인 1인 가구(head==1 and age>=65 and hnum==1, hhwgt) / 분자: 가구 재산 1억원 미만(h_prop<100000000) / 분류: 없음 / 사용 변수: head, age, hnum, h_prop, hhwgt',
    True, cells(s_rate(h_prop < 1e8, hh65 & (hnum == 1), W_HH)))

lt_grade = num('ltcare_grade')
GRADE_CATS = [('1급', 1), ('2급', 2), ('3급', 3), ('4급', 4), ('5급', 5), ('인지지원등급', 6)]
add('F06', 1, '대상: 65세 이상 장기요양 수급자(age>=65 and ltcare_bn_yn==1, 개인, indwgt) / 대상 변수: 장기요양 판정 등급(ltcare_grade) 구성비 / 분류: 등급(1~5급, 인지지원등급) / 사용 변수: age, ltcare_bn_yn, ltcare_grade',
    True, share_cells(lt_grade, GRADE_CATS, a65 & lt_bn),
    note='수급자(ltcare_bn_yn==1)의 등급은 자료상 1~6만 나타남(탈락 0·등급외 9 없음)')
add('F06', 2, '대상: 80세 이상 장기요양 수급자(age>=80 and ltcare_bn_yn==1, 개인, indwgt) / 대상 변수: 장기요양 판정 등급(ltcare_grade) 구성비 / 분류: 등급(1~5급, 인지지원등급) / 사용 변수: age, ltcare_bn_yn, ltcare_grade',
    True, share_cells(lt_grade, GRADE_CATS, (age >= 80) & lt_bn))
add('F06', 3, '대상: 80세 이상 장기요양 수급자(age>=80 and ltcare_bn_yn==1, 개인, indwgt) / 분자: 방문요양서비스 수급(ltcare_visit_yn==1) / 분류: 없음 / 사용 변수: age, ltcare_bn_yn, ltcare_visit_yn',
    True, cells(s_rate(eq1('ltcare_visit_yn'), (age >= 80) & lt_bn)))

self1 = eq1('self_yn1')
add('F07', 1, '대상: 자활근로(기초) 연간 참여자(self_yn1==1)의 가중 인원(indwgt) / 분류: 없음 / 사용 변수: self_yn1',
    False, cells(s_count(self1)))
add('F07', 2, '대상: 자활근로(기초) 연간 참여자(self_yn1==1, 개인, indwgt) / 대상 변수: 자활근로(기초) 급여액(self_amt) 가중 평균 / 분류: 성 / 사용 변수: self_yn1, self_amt, gender',
    False, cells(s_mean(num('self_amt'), self1), G_SEX))

occ = eq1('govp_yn2') | eq1('privschp_yn2') | eq1('milp_yn2')
add('F08', 1, '대상: 2022.12.31. 기준 공무원연금·사학연금·군인연금 중 하나 이상 가입(govp_yn2==1 or privschp_yn2==1 or milp_yn2==1)의 가중 인원(indwgt) / 분류: 없음 / 사용 변수: govp_yn2, privschp_yn2, milp_yn2',
    False, cells(s_count(occ)))
add('F08', 2, '대상: 2022.12.31. 기준 공무원연금·사학연금·군인연금 중 하나 이상 가입자(개인, indwgt) / 분자: 여성(gender==2) / 분류: 없음 / 사용 변수: govp_yn2, privschp_yn2, milp_yn2, gender',
    True, cells(s_rate(gender == 2, occ)))
add('F08', 3, '대상: 위 가입자 중 50세 이상(age>=50, 개인, indwgt) / 분자: 여성(gender==2) / 분류: 없음 / 사용 변수: govp_yn2, privschp_yn2, milp_yn2, age, gender',
    True, cells(s_rate(gender == 2, occ & (age >= 50))),
    note='직전 차례의 산출(여성 비율)을 이어받고 대상을 50세 이상 가입자로 좁힘')

mat = eq1('empins_matleave_yn1')
par = eq1('empins_parentleave_yn1')
add('F09', 1, '대상: 출산전후휴가급여 연간 수급자(empins_matleave_yn1==1, 개인, indwgt) / 대상 변수: 출산전후휴가 급여액(empins_matleave_amt) 가중 평균 / 분류: 없음 / 사용 변수: empins_matleave_yn1, empins_matleave_amt',
    False, cells(s_mean(num('empins_matleave_amt'), mat)))
add('F09', 2, '대상: 육아휴직급여 연간 수급자(empins_parentleave_yn1==1, 개인, indwgt) / 대상 변수: 육아휴직급여 급여액(empins_parentleave_amt) 가중 평균 / 분류: 성 / 사용 변수: empins_parentleave_yn1, empins_parentleave_amt, gender',
    False, cells(s_mean(num('empins_parentleave_amt'), par), G_SEX))

aft = eq1('pubedu_aftsch_yn')
add('F10', 1, '대상: 6~17세(개인, indwgt) / 분자: 방과후학교 자유수강권 지원(pubedu_aftsch_yn==1) / 분류: 없음 / 사용 변수: age, pubedu_aftsch_yn',
    True, cells(s_rate(aft, a6_17)))
add('F10', 2, f'대상: 6~17세 중 {POV_DEF} 가구의 아동(개인, indwgt) / 분자: 방과후학교 자유수강권 지원(pubedu_aftsch_yn==1) / 분류: 없음 / 사용 변수: age, pubedu_aftsch_yn, p_dinc, hid, hnum',
    True, cells(s_rate(aft, a6_17 & poor)))
add('F10', 3, '대상: 6~17세 중 상대 빈곤 가구의 아동(개인, indwgt) / 분자: 방과후학교 자유수강권 지원(pubedu_aftsch_yn==1) / 분류: 연령(6~11세, 12~17세) / 사용 변수: age, pubedu_aftsch_yn, p_dinc, hid, hnum',
    True, cells(s_rate(aft, a6_17 & poor), [('6~11세', (age >= 6) & (age <= 11)), ('12~17세', (age >= 12) & (age <= 17))]))

# ================= G =================
add('G01', 1, '대상: 65세 이상(개인, indwgt) / 분자: 노인일자리 공익활동 연간 참여(oldwork_type1_yn1==1) / 분류: 시도 / 사용 변수: age, oldwork_type1_yn1, sido',
    True, cells(s_rate(eq1('oldwork_type1_yn1'), a65), G_SIDO),
    note='붙은 코드는 분모 조건(where) 없이 전체 인구를 분모로 둠. 질문 의도는 65세 이상이 분모')

add('G02', 1, '대상: 75세 이상 중 입원 실적이 있는 사람(nhi_in_fee 값 있음, 개인, indwgt) / 대상 변수: 입원 전체 의과 의료기관 본인부담금(nhi_in_fee) 가중 평균 / 분류: 성 / 사용 변수: age, nhi_in_fee, gender',
    False, cells(s_mean(num('nhi_in_fee'), age >= 75), G_SEX),
    note='붙은 코드는 75세 이상 조건이 없음. 본인부담금 0원(입원 실적 있음)은 평균에 포함')

kua_type = num('kua_type')
add('G03', 1, '대상: 국민취업지원제도 2022.12.31. 기준 참여자(kua_yn2==1)의 가중 인원(indwgt) / 분류: 참여유형(kua_type: 1유형, 2유형) / 사용 변수: kua_yn2, kua_type',
    False, cells(s_count(eq1('kua_yn2')), [('1유형', kua_type == 1), ('2유형', kua_type == 2)]),
    note='붙은 코드는 연간 참여(kua_yn1)를 씀. 질문은 12월 기준이므로 kua_yn2==1')

add('G04', 1, '대상: 전체 가구(가구주 행 head==1, hhwgt) / 대상 변수: 가구 가처분소득(가구원 p_dinc 합계 = h_dinc) 가중 평균(원) / 분류: 가구원수 4구간 / 사용 변수: head, p_dinc(hid 합계), hnum, hhwgt',
    False, cells(s_mean(hh_dinc, head, W_HH), G_HS4),
    note='붙은 코드는 가구주 개인의 p_dinc 평균임. 질문 의도는 가구원 합계')

add('G05', 1, '대상: 8세 미만(age<8, 개인, indwgt) / 분자: 아동수당 연간 수급(childbn_yn1==1) / 분류: 없음 / 사용 변수: age, childbn_yn1',
    True, cells(s_rate(eq1('childbn_yn1'), age < 8)),
    note='붙은 코드는 age<=8(8세 포함). 질문은 만 8세 미만')

add('G06', 1, '대상: 20~39세 여성(gender==2 and age>=20 and age<=39, 개인, indwgt) / 분자: 임신출산진료비 지원(nhi_pregnant_yn==1) / 분류: 없음 / 사용 변수: gender, age, nhi_pregnant_yn',
    True, cells(s_rate(eq1('nhi_pregnant_yn'), (gender == 2) & (age >= 20) & (age <= 39))),
    note='붙은 코드는 연령 조건을 or로 묶어 분모가 넓어짐')

add('G07', 1, '대상: 가구주가 65세 이상인 가구 수(head==1 and age>=65, hhwgt) / 분류: 시도 / 사용 변수: head, age, sido, hhwgt',
    False, cells(s_count(hh65, W_HH), G_SIDO),
    note='붙은 코드는 개인 단위(개인 가중치) 집계임. 가구 수는 가구 가중치 사용')

vet = eq1('vetbn_r_yn')
add('G08', 1, '대상: 보훈급여 정기 보상금 및 수당 연간 수급자(vetbn_r_yn==1, 개인, indwgt) / 대상 변수: 급여액(vetbn_r_amt) 가중 평균 / 분류: 연령(65세 미만, 65~79세, 80세 이상) / 사용 변수: vetbn_r_yn, vetbn_r_amt, age',
    False, cells(s_mean(num('vetbn_r_amt'), vet), [('65세 미만', age < 65), ('65~79세', (age >= 65) & (age <= 79)), ('80세 이상', age >= 80)]),
    note='붙은 코드는 표준 3구간(0~17/18~64/65 이상)을 씀. 질문은 65세 미만/65~79세/80세 이상')

add('G09', 1, '대상: 문화누리카드 이용자(culvou_yn==1, 개인, indwgt) / 대상 변수: 결제액(culvou_bn) 가중 평균 / 분류: 연령대 3구간 / 사용 변수: culvou_yn, culvou_bn, age',
    False, cells(s_mean(num('culvou_bn'), eq1('culvou_yn')), G_AGE3),
    note='붙은 코드의 culvou_pay는 없는 변수. 결제액은 culvou_bn(culvou_amt는 이용 후 잔액)')

add('G10', 1, '대상: 재산세 부과자(ptax_yn==1, 개인, indwgt) / 대상 변수: 재산세 총액(ptax_sum) 가중 평균 / 분류: 소득 5분위(균등화 가처분소득, 전체 인구 개인 가중 20·40·60·80% 분위 경계) / 사용 변수: ptax_yn, ptax_sum, p_dinc, hid, hnum',
    False, cells(s_mean(num('ptax_sum'), eq1('ptax_yn')), G_INC5),
    note='붙은 코드와 질문 의도가 같다고 봄. 재산세 0원(값 있음)은 평균에 포함')

add('G11', 1, '대상: 18~59세(개인, indwgt) / 분자: 국민연금 연간 미가입(np_yn 결측) / 분류: 성 / 사용 변수: age, np_yn, gender',
    True, cells(s_rate(~np_y, a18_59), G_SEX),
    note='붙은 코드와 질문 의도가 같다고 봄')

itc_h = num('itc_hmember')
add('G12', 1, '대상: 근로장려금 수급 대상자(itc_yn==1, 개인, indwgt) / 대상 변수: 가구원구성코드(itc_hmember) 구성비 / 분류: 단독가구(11), 홑벌이가구(21), 맞벌이가구(23) / 사용 변수: itc_yn, itc_hmember',
    True, share_cells(itc_h, [('단독가구', 11), ('홑벌이가구', 21), ('맞벌이가구', 23)], eq1('itc_yn')),
    note='붙은 코드와 질문 의도가 같다고 봄(개인 단위 구성비)')

with open(OUT, 'w', encoding='utf-8') as f:
    for r in RECS:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')

# 요약(집계값만)
print('빈곤선(원):', 0.5 * MED, '/ 5분위 경계(원):', BOUNDS)
print('줄 수:', len(RECS))
for r in RECS:
    vs = [c['value'] for c in r['cells']]
    ns = [c['n'] for c in r['cells']]
    head_v = ', '.join('null' if v is None else f'{v:.6g}' for v in vs[:6])
    print(f"{r['id']} t{r['turn']} r{r['reading_no']} pct={r['pct']} cells={len(vs)} min_n={min(ns)} | {head_v}{' …' if len(vs) > 6 else ''}")
