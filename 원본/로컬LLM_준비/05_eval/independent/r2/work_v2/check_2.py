# -*- coding: utf-8 -*-
"""독립 검산(이중 입력) 2차: check_input_2.jsonl 의 질문을 pandas 로 직접 계산.

- 분석 함수(ssda)를 쓰지 않음. 개인 단위 행을 출력하지 않음.
- 산출: r2/truth/check_2.jsonl (산출을 요구하는 차례마다 한 줄)
"""
import json
import numpy as np
import pandas as pd

DATA = '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
OUT = '/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r2/truth/check_2.jsonl'

df = pd.read_parquet(DATA)
N = len(df)
W = df['indwgt'].astype(float)
HW = df['hhwgt'].astype(float)
HEAD = (df['head'] == 1)
ALL = pd.Series(True, index=df.index)
age = df['age']
male = df['gender'] == 1
female = df['gender'] == 2
metro = df['sido'].isin([1, 4, 9])

SIDO = {1: '서울', 2: '부산', 3: '대구', 4: '인천', 5: '광주', 6: '대전', 7: '울산', 8: '세종', 9: '경기',
        10: '강원', 11: '충북', 12: '충남', 13: '전북', 14: '전남', 15: '경북', 16: '경남', 17: '제주'}


def is1(col):
    """여부 변수: 해당하면 1. 결측·0은 해당하지 않음."""
    return df[col].eq(1).fillna(False).astype(bool)


# ---- 파생: 균등화 가처분소득, 빈곤 ----
def wquantile(values, weights, q):
    """값을 오름차순으로 놓고 가중치 누적합이 전체의 q배에 처음 이르는 값."""
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    ok = ~np.isnan(v)
    v, w = v[ok], w[ok]
    if len(v) == 0:
        return None
    order = np.argsort(v, kind='mergesort')
    v, w = v[order], w[order]
    cum = np.cumsum(w)
    idx = int(np.searchsorted(cum, q * cum[-1], side='left'))
    idx = min(idx, len(v) - 1)
    return float(v[idx])


hh_dinc_sum = df.groupby('hid')['p_dinc'].transform('sum').astype(float)
eqinc = hh_dinc_sum / np.sqrt(df['hnum'].astype(float))
POV_LINE = 0.5 * wquantile(eqinc, W, 0.5)
poor = eqinc < POV_LINE


# ---- 집계 도우미 ----
def cell(labels, value, n, n_num=None):
    c = {'labels': list(labels), 'value': (None if value is None else float(value)), 'n': int(n)}
    if n_num is not None:
        c['n_num'] = int(n_num)
    return c


def c_count(mask, labels=(), w=W):
    n = int(mask.sum())
    return cell(labels, (w[mask].sum() if n > 0 else None), n)


def c_rate(num, den, labels=(), w=W):
    n = int(den.sum())
    nn = int((num & den).sum())
    val = (w[num & den].sum() / w[den].sum() * 100.0) if n > 0 else None
    return cell(labels, val, n, nn)


def c_mean(var, mask, labels=(), w=W):
    m = mask & df[var].notna()
    n = int(m.sum())
    val = ((df.loc[m, var].astype(float) * w[m]).sum() / w[m].sum()) if n > 0 else None
    return cell(labels, val, n)


def c_total(var, mask, labels=(), w=W):
    m = mask & df[var].notna()
    n = int(m.sum())
    val = (df.loc[m, var].astype(float) * w[m]).sum() if n > 0 else None
    return cell(labels, val, n)


def c_quant(var, mask, q, labels=(), w=W):
    m = mask & df[var].notna()
    n = int(m.sum())
    val = wquantile(df.loc[m, var], w[m], q) if n > 0 else None
    return cell(labels, val, n)


def c_pov(mask, labels=()):
    return c_rate(poor, mask, labels)


ROWS = []


def add(qid, turn, reading, pct, cells, reading_no=1, ambiguous=False, note=''):
    ROWS.append({'id': qid, 'turn': turn, 'reading_no': reading_no, 'reading': reading, 'pct': pct,
                 'cells': cells, 'ambiguous': ambiguous, 'note': note})


# 자주 쓰는 구간
old3 = [('65~74세', (age >= 65) & (age <= 74)), ('75~84세', (age >= 75) & (age <= 84)), ('85세 이상', age >= 85)]
u65 = [('65세 미만', age < 65), ('65세 이상', age >= 65)]
sexes = [('남', male), ('여', female)]
region2 = [('수도권', metro), ('비수도권', ~metro)]
hs4 = [('1인', df['hnum'] == 1), ('2인', df['hnum'] == 2), ('3인', df['hnum'] == 3), ('4인 이상', df['hnum'] >= 4)]
age3 = [('0~17세', age <= 17), ('18~64세', (age >= 18) & (age <= 64)), ('65세 이상', age >= 65)]
age10 = [(f'{a}~{a + 9}세', (age >= a) & (age <= a + 9)) for a in range(0, 80, 10)] + [('80세 이상', age >= 80)]

# ================= C =================
ltc = is1('ltcare_bn_yn')
add('C01a', 1, '대상: 65세 이상 인구 / 분자: 2022년 연간 노인장기요양 수급(ltcare_bn_yn==1) / 분류: 없음 / 사용 변수: age, ltcare_bn_yn, indwgt',
    True, [c_rate(ltc, age >= 65)])
add('C01b', 1, '대상: 75세 이상 인구 / 분자: 2022년 연간 노인장기요양 수급(ltcare_bn_yn==1) / 분류: 없음 / 사용 변수: age, ltcare_bn_yn, indwgt',
    True, [c_rate(ltc, age >= 75)])

pl = is1('empins_parentleave_yn1')
add('C02a', 1, '대상: 2022년 연간 육아휴직급여 수급자(empins_parentleave_yn1==1) / 분자: 남성(gender==1) / 분류: 없음 / 사용 변수: empins_parentleave_yn1, gender, indwgt',
    True, [c_rate(male, pl)])
add('C02b', 1, '대상: 2022년 연간 육아휴직급여 수급자(empins_parentleave_yn1==1) 중 남성 / 지표: 가중 인원 / 분류: 없음 / 사용 변수: empins_parentleave_yn1, gender, indwgt',
    False, [c_count(pl & male)])

rich = df['h_prop'] >= 500_000_000
add('C03a', 1, '대상: 전체 인구(개인 단위, indwgt) / 분자: 가구 재산 h_prop >= 5억원 / 분류: 없음 / 사용 변수: h_prop, indwgt',
    True, [c_rate(rich, ALL)])
add('C03b', 1, '대상: 전체 가구(가구주 행, hhwgt) / 분자: 가구 재산 h_prop >= 5억원 / 분류: 없음 / 사용 변수: h_prop, head, hhwgt',
    True, [c_rate(rich, HEAD, w=HW)])

add('C04a', 1, '대상: 긴급복지지원 생계지원 2022년 연간 수급자(aid_live_yn1==1) / 지표: 가중 인원 / 분류: 없음 / 사용 변수: aid_live_yn1, indwgt',
    False, [c_count(is1('aid_live_yn1'))])
add('C04b', 1, '대상: 긴급복지지원 생계지원 2022년 12월 기준 수급자(aid_live_yn2==1) / 지표: 가중 인원 / 분류: 없음 / 사용 변수: aid_live_yn2, indwgt',
    False, [c_count(is1('aid_live_yn2'))])

out_user = df['nhi_out_fee'].notna()
add('C05a', 1, '대상: 65세 이상 외래 이용자(nhi_out_fee 값 있음) / 대상 변수: 연간 외래 본인부담금 nhi_out_fee 평균(원) / 분류: 없음 / 사용 변수: age, nhi_out_fee, indwgt',
    False, [c_mean('nhi_out_fee', (age >= 65) & out_user)])
add('C05b', 1, '대상: 65세 이상 외래 이용자(nhi_out_fee 값 있음) / 대상 변수: 연간 외래 본인부담금 nhi_out_fee 가중 중위수(원) / 분류: 없음 / 사용 변수: age, nhi_out_fee, indwgt',
    False, [c_quant('nhi_out_fee', (age >= 65) & out_user, 0.5)])

dp2 = is1('disp_yn2')
add('C06a', 1, '대상: 2022년 12월 기준 장애인연금 수급자(disp_yn2==1) / 대상 변수: 연간 장애인연금 급여액 disp_amt 평균(원) / 분류: 없음 / 사용 변수: disp_yn2, disp_amt, indwgt',
    False, [c_mean('disp_amt', dp2)])
add('C06b', 1, '대상: 2022년 12월 기준 장애인연금 수급자(disp_yn2==1) / 대상 변수: 연간 장애인연금 급여액 disp_amt 가중 합계(원) / 분류: 없음 / 사용 변수: disp_yn2, disp_amt, indwgt',
    False, [c_total('disp_amt', dp2)])

ev = is1('evou_yn')
add('C07a', 1, '대상: 전체 인구 / 분자: 에너지바우처 사업기간 이용(evou_yn==1) / 분류: 없음 / 사용 변수: evou_yn, indwgt',
    True, [c_rate(ev, ALL)])
add('C07b', 1, '대상: 2022년 12월 기준 생계급여 수급자(nbls_live_yn2==1) / 분자: 에너지바우처 사업기간 이용(evou_yn==1) / 분류: 없음 / 사용 변수: nbls_live_yn2, evou_yn, indwgt',
    True, [c_rate(ev, is1('nbls_live_yn2'))])

js = is1('unempbn_jobseekbn_yn')
jd = df['unempbn_jobseekbn_dur']
add('C08a', 1, '대상: 2022년 연간 구직급여 수급자(unempbn_jobseekbn_yn==1) / 분자: 연간 수급일수 unempbn_jobseekbn_dur >= 120 / 분류: 없음 / 사용 변수: unempbn_jobseekbn_yn, unempbn_jobseekbn_dur, indwgt',
    True, [c_rate((jd >= 120).fillna(False), js)])
add('C08b', 1, '대상: 2022년 연간 구직급여 수급자(unempbn_jobseekbn_yn==1) / 분자: 연간 수급일수 unempbn_jobseekbn_dur > 120 / 분류: 없음 / 사용 변수: unempbn_jobseekbn_yn, unempbn_jobseekbn_dur, indwgt',
    True, [c_rate((jd > 120).fillna(False), js)])

cc1 = is1('childcare_yn1')
cd = df['childcare_dur']
add('C09a', 1, '대상: 2022년 연간 보육료 지원 아동(childcare_yn1==1) 중 연간 지원기간 childcare_dur < 6개월 / 지표: 가중 인원 / 분류: 없음 / 사용 변수: childcare_yn1, childcare_dur, indwgt',
    False, [c_count(cc1 & (cd < 6).fillna(False))])
add('C09b', 1, '대상: 2022년 연간 보육료 지원 아동(childcare_yn1==1) 중 연간 지원기간 childcare_dur <= 6개월 / 지표: 가중 인원 / 분류: 없음 / 사용 변수: childcare_yn1, childcare_dur, indwgt',
    False, [c_count(cc1 & (cd <= 6).fillna(False))])

af = is1('pubedu_aftsch_yn')
pc = is1('pubedu_pclot_yn')
add('C10a', 1, '대상: 2022년 연간 방과후학교 자유수강권(pubedu_aftsch_yn==1)과 교육정보화 지원(pubedu_pclot_yn==1)을 둘 다 받은 사람 / 지표: 가중 인원 / 분류: 없음 / 사용 변수: pubedu_aftsch_yn, pubedu_pclot_yn, indwgt',
    False, [c_count(af & pc)])
add('C10b', 1, '대상: 2022년 연간 방과후학교 자유수강권(pubedu_aftsch_yn==1) 또는 교육정보화 지원(pubedu_pclot_yn==1)을 하나라도 받은 사람 / 지표: 가중 인원 / 분류: 없음 / 사용 변수: pubedu_aftsch_yn, pubedu_pclot_yn, indwgt',
    False, [c_count(af | pc)])

gp = is1('govp_pension_yn')
add('C11a', 1, '대상: 2022년 연간 공무원연금 정기연금 수급자(govp_pension_yn==1) 중 남성 / 대상 변수: 연간 급여액 govp_pension_amt 평균(원) / 분류: 없음 / 사용 변수: govp_pension_yn, govp_pension_amt, gender, indwgt',
    False, [c_mean('govp_pension_amt', gp & male)])
add('C11b', 1, '대상: 2022년 연간 공무원연금 정기연금 수급자(govp_pension_yn==1) 중 여성 / 대상 변수: 연간 급여액 govp_pension_amt 평균(원) / 분류: 없음 / 사용 변수: govp_pension_yn, govp_pension_amt, gender, indwgt',
    False, [c_mean('govp_pension_amt', gp & female)])

hs2 = is1('nbls_house_yn2')
add('C12a', 1, '대상: 부산(sido==2) 거주, 2022년 12월 기준 주거급여 임차급여 수급자(nbls_house_yn2==1) / 지표: 가중 인원 / 분류: 없음 / 사용 변수: sido, nbls_house_yn2, indwgt',
    False, [c_count(hs2 & (df['sido'] == 2))])
add('C12b', 1, '대상: 대구(sido==3) 거주, 2022년 12월 기준 주거급여 임차급여 수급자(nbls_house_yn2==1) / 지표: 가중 인원 / 분류: 없음 / 사용 변수: sido, nbls_house_yn2, indwgt',
    False, [c_count(hs2 & (df['sido'] == 3))])

itc = is1('itc_yn')
add('C13a', 1, '대상: 수도권(sido 1·4·9) 거주 근로장려금 수급 대상자(itc_yn==1) / 대상 변수: 근로장려 심사금액 itc_amt 평균(원) / 분류: 없음 / 사용 변수: sido, itc_yn, itc_amt, indwgt',
    False, [c_mean('itc_amt', itc & metro)])
add('C13b', 1, '대상: 비수도권(sido 1·4·9 제외) 거주 근로장려금 수급 대상자(itc_yn==1) / 대상 변수: 근로장려 심사금액 itc_amt 평균(원) / 분류: 없음 / 사용 변수: sido, itc_yn, itc_amt, indwgt',
    False, [c_mean('itc_amt', itc & ~metro)])

npp = is1('np_pension_yn')
add('C14a', 1, '대상: 65세 이상 중 2022년 연간 국민연금 정기연금 수급자(np_pension_yn==1) / 지표: 상대 빈곤율(균등화 가처분소득 < 전체 인구 가중 중위값의 50%) / 분류: 없음 / 사용 변수: age, np_pension_yn, p_dinc, hnum, hid, indwgt',
    True, [c_pov((age >= 65) & npp)])
add('C14b', 1, '대상: 65세 이상 중 2022년 연간 국민연금 정기연금 비수급자(np_pension_yn 결측) / 지표: 상대 빈곤율(균등화 가처분소득 < 전체 인구 가중 중위값의 50%) / 분류: 없음 / 사용 변수: age, np_pension_yn, p_dinc, hnum, hid, indwgt',
    True, [c_pov((age >= 65) & ~npp)])

md2 = is1('nbls_medi_yn2')
note_medi = '의료급여 수급권 여부(고정시점) nbls_medi_yn2==1 사용. 자료에서 nhi_type in [7,8](12월 가입유형 의료급여)과 대상이 일치함'
add('C15a', 1, '대상: 2022년 12월 기준 의료급여 수급권자(nbls_medi_yn2==1) / 지표: 가중 인원 / 분류: 성 / 사용 변수: nbls_medi_yn2, gender, indwgt',
    False, [c_count(md2 & m, [lab]) for lab, m in sexes], note=note_medi)
mt = df['nbls_medi_type']
add('C15b', 1, '대상: 2022년 12월 기준 의료급여 수급권자(nbls_medi_yn2==1) / 지표: 가중 인원 / 분류: 의료급여 종별(nbls_medi_type 1종·2종) / 사용 변수: nbls_medi_yn2, nbls_medi_type, indwgt',
    False, [c_count(md2 & (mt == 1), ['1종']), c_count(md2 & (mt == 2), ['2종'])], note=note_medi)

# ================= F =================
inp = df['nhi_in_dur'].notna()
base = (age >= 65) & inp
add('F01', 1, '대상: 65세 이상 입원 이용자(nhi_in_dur 값 있음) / 대상 변수: 연간 입원 재원일수 nhi_in_dur 평균(일) / 분류: 없음 / 사용 변수: age, nhi_in_dur, indwgt',
    False, [c_mean('nhi_in_dur', base)])
add('F01', 2, '대상: 65세 이상 여성 입원 이용자(nhi_in_dur 값 있음) / 대상 변수: 연간 입원 재원일수 nhi_in_dur 평균(일) / 분류: 없음 / 사용 변수: age, gender, nhi_in_dur, indwgt',
    False, [c_mean('nhi_in_dur', base & female)])
add('F01', 3, '대상: 65세 이상 여성 입원 이용자(앞 차례의 여성 한정을 이어받음) / 대상 변수: 연간 입원 재원일수 nhi_in_dur 평균(일) / 분류: 65~74세·75~84세·85세 이상 / 사용 변수: age, gender, nhi_in_dur, indwgt',
    False, [c_mean('nhi_in_dur', base & female & m, [lab]) for lab, m in old3])

ei2 = is1('empins_yn2')
note_ei = '고정시점 가입여부 empins_yn2 사용. codebook 정의는 2022년 10월 31일 기준 가입여부이며 질문의 「12월 말 기준」에 해당하는 별도 변수는 없음'
a1864 = (age >= 18) & (age <= 64)
a1834 = (age >= 18) & (age <= 34)
add('F02', 1, '대상: 18~64세 인구 / 분자: 고용보험 고정시점 가입(empins_yn2==1) / 분류: 없음 / 사용 변수: age, empins_yn2, indwgt',
    True, [c_rate(ei2, a1864)], note=note_ei)
add('F02', 2, '대상: 18~34세 인구 / 분자: 고용보험 고정시점 가입(empins_yn2==1) / 분류: 없음 / 사용 변수: age, empins_yn2, indwgt',
    True, [c_rate(ei2, a1834)], note=note_ei)
add('F02', 3, '대상: 18~34세 중 고용보험 고정시점 가입자(empins_yn2==1) / 지표: 가중 인원 / 분류: 없음 / 사용 변수: age, empins_yn2, indwgt',
    False, [c_count(ei2 & a1834)], note=note_ei)

dis = is1('dis_yn')
sev = df['dis_grade_1'].eq(1).fillna(False)
add('F03', 1, '대상: 2022년 12월 말 기준 등록장애인(dis_yn==1) / 분자: 종합장애정도 「정도가 심한」(dis_grade_1==1) / 분류: 없음 / 사용 변수: dis_yn, dis_grade_1, indwgt',
    True, [c_rate(sev, dis)], note='종합장애정도(dis_grade_1) 사용. 자료에서 주장애정도(dis_grade_2)와 값이 일치함')
add('F03', 2, '대상: 2022년 12월 말 기준 등록장애인(dis_yn==1) / 분자: 종합장애정도 「정도가 심한」(dis_grade_1==1) / 분류: 65세 미만·65세 이상 / 사용 변수: dis_yn, dis_grade_1, age, indwgt',
    True, [c_rate(sev, dis & m, [lab]) for lab, m in u65], note='종합장애정도(dis_grade_1) 사용. 자료에서 주장애정도(dis_grade_2)와 값이 일치함')

cc2 = is1('childcare_yn2')
add('F04', 1, '대상: 2022년 12월 기준 보육료 지원 아동(childcare_yn2==1) / 지표: 가중 인원 / 분류: 없음 / 사용 변수: childcare_yn2, indwgt',
    False, [c_count(cc2)])
add('F04', 2, '대상: 2022년 12월 기준 보육료 지원 아동(childcare_yn2==1) / 대상 변수: 연간 보육료 지원액 childcare_amt 평균(원) / 분류: 없음 / 사용 변수: childcare_yn2, childcare_amt, indwgt',
    False, [c_mean('childcare_amt', cc2)])
add('F04', 3, '대상: 2022년 12월 기준 보육료 지원 아동(childcare_yn2==1) / 대상 변수: 연간 보육료 지원액 childcare_amt 가중 합계(원) / 분류: 없음 / 사용 변수: childcare_yn2, childcare_amt, indwgt',
    False, [c_total('childcare_amt', cc2)])

hh_old = HEAD & (age >= 65)
add('F05', 1, '대상: 가구주가 65세 이상인 가구(가구주 행, hhwgt) / 대상 변수: 가구 재산 h_prop 가중 중위수(원) / 분류: 없음 / 사용 변수: head, age, h_prop, hhwgt',
    False, [c_quant('h_prop', hh_old, 0.5, w=HW)])
add('F05', 2, '대상: 가구주가 65세 이상인 가구(가구주 행, hhwgt) / 대상 변수: 가구 재산 h_prop 가중 중위수(원) / 분류: 가구원수 4구간(hnum) / 사용 변수: head, age, hnum, h_prop, hhwgt',
    False, [c_quant('h_prop', hh_old & m, 0.5, [lab], w=HW) for lab, m in hs4])

vis = is1('ltcare_visit_yn')
dn = is1('ltcare_daynight_yn')
add('F06', 1, '대상: 2022년 연간 노인장기요양 수급자(ltcare_bn_yn==1) / 분자: 방문요양 수급(ltcare_visit_yn==1) / 분류: 없음 / 사용 변수: ltcare_bn_yn, ltcare_visit_yn, indwgt',
    True, [c_rate(vis, ltc)])
add('F06', 2, '대상: 2022년 연간 노인장기요양 수급자(ltcare_bn_yn==1) / 분자: 주야간보호 수급(ltcare_daynight_yn==1) / 분류: 없음 / 사용 변수: ltcare_bn_yn, ltcare_daynight_yn, indwgt',
    True, [c_rate(dn, ltc)])
add('F06', 3, '대상: 2022년 연간 노인장기요양 수급자(ltcare_bn_yn==1) / 분자: 주야간보호 수급(ltcare_daynight_yn==1) / 분류: 성 / 사용 변수: ltcare_bn_yn, ltcare_daynight_yn, gender, indwgt',
    True, [c_rate(dn, ltc & m, [lab]) for lab, m in sexes])

al1 = is1('aid_live_yn1')
add('F07', 1, '대상: 긴급복지지원 생계지원 2022년 연간 수급자(aid_live_yn1==1) / 지표: 가중 인원 / 분류: 없음 / 사용 변수: aid_live_yn1, indwgt',
    False, [c_count(al1)])
add('F07', 2, '대상: 긴급복지지원 생계지원 2022년 연간 수급자(aid_live_yn1==1) / 분자: 1인 가구(hnum==1) / 분류: 없음 / 사용 변수: aid_live_yn1, hnum, indwgt',
    True, [c_rate(df['hnum'] == 1, al1)])

a718 = (age >= 7) & (age <= 18)
add('F08', 1, '대상: 7~18세 인구 / 분자: 2022년 연간 방과후학교 자유수강권 지원(pubedu_aftsch_yn==1) / 분류: 없음 / 사용 변수: age, pubedu_aftsch_yn, indwgt',
    True, [c_rate(af, a718)])
add('F08', 2, '대상: 7~18세 인구 / 분자: 2022년 연간 방과후학교 자유수강권 지원(pubedu_aftsch_yn==1) / 분류: 수도권(sido 1·4·9)·비수도권 / 사용 변수: age, sido, pubedu_aftsch_yn, indwgt',
    True, [c_rate(af, a718 & m, [lab]) for lab, m in region2])
add('F08', 3, '대상: 7~18세 중 2022년 연간 방과후학교 자유수강권 지원을 받은 사람(pubedu_aftsch_yn==1) / 대상 변수: 연간 지원액 pubedu_aftsch_amt 평균(원) / 분류: 수도권(sido 1·4·9)·비수도권 / 사용 변수: age, sido, pubedu_aftsch_yn, pubedu_aftsch_amt, indwgt',
    False, [c_mean('pubedu_aftsch_amt', a718 & af & m, [lab]) for lab, m in region2])

add('F09', 1, '대상: 2022년 연간 공무원연금 정기연금 수급자(govp_pension_yn==1) / 대상 변수: 연간 급여액 govp_pension_amt 평균(원) / 분류: 없음 / 사용 변수: govp_pension_yn, govp_pension_amt, indwgt',
    False, [c_mean('govp_pension_amt', gp)])
add('F09', 2, '대상: 2022년 연간 공무원연금 정기연금 수급자(govp_pension_yn==1) / 대상 변수: 연간 급여액 govp_pension_amt 가중 중위수(원) / 분류: 없음 / 사용 변수: govp_pension_yn, govp_pension_amt, indwgt',
    False, [c_quant('govp_pension_amt', gp, 0.5)])
pp = is1('privschp_pension_yn')
add('F09', 3, '대상: 2022년 연간 사립학교교직원연금 정기연금 수급자(privschp_pension_yn==1) / 대상 변수: 연간 급여액 privschp_pension_amt 가중 중위수(원) / 분류: 없음 / 사용 변수: privschp_pension_yn, privschp_pension_amt, indwgt',
    False, [c_quant('privschp_pension_amt', pp, 0.5)])

add('F10', 1, '대상: 2022년 연간 육아휴직급여 수급자(empins_parentleave_yn1==1) / 지표: 가중 인원 / 분류: 성 / 사용 변수: empins_parentleave_yn1, gender, indwgt',
    False, [c_count(pl & m, [lab]) for lab, m in sexes])
add('F10', 2, '대상: 2022년 연간 육아휴직급여 수급자(empins_parentleave_yn1==1) / 대상 변수: 연간 수급기간 empins_parentleave_dur 평균(개월) / 분류: 성 / 사용 변수: empins_parentleave_yn1, empins_parentleave_dur, gender, indwgt',
    False, [c_mean('empins_parentleave_dur', pl & m, [lab]) for lab, m in sexes])
add('F10', 3, '대상: 2022년 연간 육아휴직급여 수급자(empins_parentleave_yn1==1) 중 30~39세 여성 / 대상 변수: 연간 수급기간 empins_parentleave_dur 평균(개월) / 분류: 없음 / 사용 변수: empins_parentleave_yn1, empins_parentleave_dur, gender, age, indwgt',
    False, [c_mean('empins_parentleave_dur', pl & female & (age >= 30) & (age <= 39))])

# ================= G =================
add('G01', 1, '대상: 만 0~5세 인구(age<=5) / 분자: 2022년 12월 기준 보육료 지원(childcare_yn2==1) / 분류: 없음 / 사용 변수: age, childcare_yn2, indwgt',
    True, [c_rate(cc2, age <= 5)], note='붙은 코드는 분모(where) 한정이 없어 전체 인구 대비로 계산됨. 질문 의도대로 0~5세를 분모로 함')

ow = is1('oldwork_type1_yn1')
add('G02', 1, '대상: 65세 이상 인구 / 분자: 2022년 연간 노인일자리 공익활동 참여(oldwork_type1_yn1==1) / 분류: 65~74세·75~84세·85세 이상 / 사용 변수: age, oldwork_type1_yn1, indwgt',
    True, [c_rate(ow, m, [lab]) for lab, m in old3], note='붙은 코드는 경계 [75, 85]·이름 3개에 where 로 65세 이상을 한정하여 질문 의도와 같은 구간이 됨')

ku2 = is1('kua_yn2')
kt = df['kua_type']
add('G03', 1, '대상: 2022년 12월(12.31.) 기준 국민취업지원제도 참여자(kua_yn2==1) / 지표: 가중 인원 / 분류: 참여유형(kua_type 1유형·2유형) / 사용 변수: kua_yn2, kua_type, indwgt',
    False, [c_count(ku2 & (kt == 1), ['1유형']), c_count(ku2 & (kt == 2), ['2유형'])], note='붙은 코드는 연간 참여(kua_yn1)를 써서 12월 기준과 다름')

oc2 = is1('oldcare_yn2')
add('G04', 1, '대상: 65세 이상 인구(age>=65) / 분자: 2022년 12월 기준 노인맞춤돌봄서비스 이용(oldcare_yn2==1) / 분류: 성 / 사용 변수: age, oldcare_yn2, gender, indwgt',
    True, [c_rate(oc2, (age >= 65) & m, [lab]) for lab, m in sexes], note='붙은 코드는 age > 65 로 65세를 제외함')

low = df['h_dinc'] < 30_000_000
add('G05', 1, '대상: 전체 가구(가구주 행, hhwgt) / 분자: 가구 가처분소득 h_dinc < 3천만원 / 분류: 시도 / 사용 변수: head, h_dinc, sido, hhwgt',
    True, [c_rate(low, HEAD & (df['sido'] == k), [v], w=HW) for k, v in SIDO.items()], note="붙은 코드는 unit='가구' 지정이 없어 개인 단위로 계산됨")

cv = is1('culvou_yn')
add('G06', 1, '대상: 2022년 문화누리카드 이용자(culvou_yn==1) / 대상 변수: 연간 결제액 culvou_bn 평균(원) / 분류: 성 / 사용 변수: culvou_yn, culvou_bn, gender, indwgt',
    False, [c_mean('culvou_bn', cv & m, [lab]) for lab, m in sexes], note='붙은 코드는 인자 이름이 groupby 로 잘못됨(by 가 맞음)')

mp = is1('milip_pension_yn')
add('G07', 1, '대상: 2022년 연간 공무원연금·사립학교교직원연금·군인연금 정기연금 중 하나라도 수급(govp_pension_yn==1 or privschp_pension_yn==1 or milip_pension_yn==1) / 지표: 가중 인원 / 분류: 없음 / 사용 변수: govp_pension_yn, privschp_pension_yn, milip_pension_yn, indwgt',
    False, [c_count(gp | pp | mp)], note='붙은 코드는 and 로 묶어 셋 모두 수급한 사람만 셈')

add('G08', 1, '대상: 외래 이용자(nhi_out_dur 값 있음) / 대상 변수: 연간 외래 내원일수 nhi_out_dur 평균(일) / 분류: 10세 단위 연령대(0~9 … 70~79, 80세 이상) / 사용 변수: nhi_out_dur, age, indwgt',
    False, [c_mean('nhi_out_dur', m, [lab]) for lab, m in age10], note='붙은 코드는 6구간(age6)을 씀. 10세 단위(age10)로 계산함')

da = is1('disvou_act_yn1')
add('G09', 1, '대상: 2022년 12월 말 기준 등록장애인(dis_yn==1) / 분자: 2022년 연간 장애인활동지원 이용(disvou_act_yn1==1) / 분류: 성 / 사용 변수: dis_yn, disvou_act_yn1, gender, indwgt',
    True, [c_rate(da, dis & m, [lab]) for lab, m in sexes], note='붙은 코드는 분모 한정이 없어 전체 인구 대비로 계산됨')

hm = df['itc_hmember']
add('G10', 1, '대상: 근로장려금 수급 대상자(itc_yn==1) / 대상 변수: 근로장려 심사금액 itc_amt 가중 합계(원) / 분류: 가구원구성(itc_hmember 단독·홑벌이·맞벌이) / 사용 변수: itc_yn, itc_amt, itc_hmember, indwgt',
    False, [c_total('itc_amt', itc & (hm == k), [v]) for k, v in [(11, '단독가구'), (21, '홑벌이가구'), (23, '맞벌이가구')]], note='붙은 코드는 평균(mean)을 냄. 합계로 계산함')

add('G11', 1, '대상: 전체 가구(가구주 행, hhwgt) / 대상 변수: 가구 재산 h_prop 평균(원) / 분류: 가구원수 4구간(hnum) / 사용 변수: head, h_prop, hnum, hhwgt',
    False, [c_mean('h_prop', HEAD & m, [lab], w=HW) for lab, m in hs4], note='붙은 코드는 개인 재산 p_prop(가구주 개인분)을 씀. 가구 재산 h_prop 로 계산함')

nonp = ~is1('np_yn')
add('G12', 1, '대상: 18~59세 중 2022년 연간 국민연금 가입 이력이 없는 사람(np_yn 결측) / 지표: 가중 인원 / 분류: 성 / 사용 변수: age, np_yn, gender, indwgt',
    False, [c_count((age >= 18) & (age <= 59) & nonp & m, [lab]) for lab, m in sexes], note='붙은 코드는 질문 의도와 일치하는 것으로 봄')

# ================= E =================
add('E17', 1, '대상: 전체 가구(가구주 행, hhwgt) / 대상 변수: 가구 가처분소득 h_dinc 가중 90% 분위값(원) / 분류: 없음 / 사용 변수: head, h_dinc, hhwgt',
    False, [c_quant('h_dinc', HEAD, 0.9, w=HW)])

ca = is1('nhi_special1_yn')
add('E18', 1, '대상: 암 산정특례 등록자(nhi_special1_yn==1) / 지표: 가중 인원 / 분류: 65세 미만·65세 이상 / 사용 변수: nhi_special1_yn, age, indwgt',
    False, [c_count(ca & m, [lab]) for lab, m in u65])

add('E19', 1, '대상: 경기(sido==9) 거주 1인 가구(hnum==1) 65세 이상 여성 / 지표: 상대 빈곤율(균등화 가처분소득 < 전체 인구 가중 중위값의 50%) / 분류: 없음 / 사용 변수: sido, hnum, age, gender, p_dinc, hid, indwgt',
    True, [c_pov((df['sido'] == 9) & (df['hnum'] == 1) & (age >= 65) & female)])

add('E20', 1, '대상: 시도별 전체 인구 / 분자: 2022년 12월 기준 의료급여 수급권자(nbls_medi_yn2==1) / 분류: 시도 / 사용 변수: nbls_medi_yn2, sido, indwgt',
    True, [c_rate(md2, df['sido'] == k, [v]) for k, v in SIDO.items()], note=note_medi)

add('E21', 1, '대상: 2022년 12월 31일 기준 등록장애인(dis_yn==1) / 분자: 종합장애정도 「정도가 심한」(dis_grade_1==1) / 분류: 성 / 사용 변수: dis_yn, dis_grade_1, gender, indwgt',
    True, [c_rate(sev, dis & m, [lab]) for lab, m in sexes])

lv1 = is1('nbls_live_yn1')
add('E22', 1, '대상: 2022년 연간 생계급여 수급자(nbls_live_yn1==1) / 지표: 가중 인원 / 분류: 없음 / 사용 변수: nbls_live_yn1, indwgt',
    False, [c_count(lv1)])
add('E22', 2, '대상: 2022년 연간 생계급여 수급자(nbls_live_yn1==1) / 지표: 연령대 3구간 구성비(%) / 분류: 0~17세·18~64세·65세 이상 / 사용 변수: nbls_live_yn1, age, indwgt',
    True, [c_rate(m, lv1, [lab]) for lab, m in age3])

bp2 = is1('bp_yn2')
add('E23', 1, '대상: 65세 이상 인구 / 분자: 2022년 12월 기준 기초연금 수급(bp_yn2==1) / 분류: 성 / 사용 변수: age, bp_yn2, gender, indwgt',
    True, [c_rate(bp2, (age >= 65) & m, [lab]) for lab, m in sexes])

lv2 = is1('nbls_live_yn2')
add('E24', 1, '대상: 2022년 12월 기준 생계급여 수급자(nbls_live_yn2==1) / 대상 변수: 연간 생계급여 급여액 nbls_live_amt 가중 중위수(원) / 분류: 없음 / 사용 변수: nbls_live_yn2, nbls_live_amt, indwgt',
    False, [c_quant('nbls_live_amt', lv2, 0.5)])

# ---- 저장 ----
with open(OUT, 'w', encoding='utf-8') as f:
    for r in ROWS:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')

# ---- 점검 출력(집계만) ----
src = [json.loads(l) for l in open('/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r2/truth/check_input_2.jsonl', encoding='utf-8')]
ids_in = {s['id']: len(s['turns']) for s in src}
done = {}
for r in ROWS:
    done.setdefault(r['id'], set()).add(r['turn'])
missing = {k: sorted(set(range(1, v + 1)) - done.get(k, set())) for k, v in ids_in.items() if set(range(1, v + 1)) - done.get(k, set())}
print('rows', len(ROWS), 'ids', len(done), 'of', len(ids_in), 'missing turns', missing)
print('pov line(원)', POV_LINE, 'pop', W.sum(), 'hh', HW[HEAD].sum())
for r in ROWS:
    print(r['id'], r['turn'], r['pct'], [(c['labels'], None if c['value'] is None else round(c['value'], 3), c['n'], c.get('n_num')) for c in r['cells']])
