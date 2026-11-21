# -*- coding: utf-8 -*-
"""독립 검산(check_2): 질문 문장만 보고 분석 자료에서 pandas로 직접 계산.
ssda 함수 미사용. 산출: ../truth/check_2.jsonl (집계값만 기록, 개인 단위 행 미출력)
"""
import json
import numpy as np
import pandas as pd

P = '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
OUT = '/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r4/truth/check_2.jsonl'

df = pd.read_parquet(P)
W = df['indwgt'].astype(float)
HW = df['hhwgt'].astype(float)
HEAD = (df['head'] == 1)

# ---------- 공통 도구 ----------

def e1(v):
    """여부 변수: 해당하면 1. 결측은 거짓."""
    return (df[v] == 1).fillna(False).astype(bool)


def wq(vals, wts, q):
    """가중 분위수: 오름차순, 가중치 누적합이 전체의 q배에 처음 이르는 값."""
    v = np.asarray(vals, dtype=float)
    w = np.asarray(wts, dtype=float)
    ok = ~np.isnan(v)
    v, w = v[ok], w[ok]
    if len(v) == 0:
        return None
    o = np.argsort(v, kind='mergesort')
    v, w = v[o], w[o]
    c = np.cumsum(w)
    i = int(np.searchsorted(c, q * c[-1], side='left'))
    i = min(i, len(v) - 1)
    return float(v[i])


# 균등화 가처분소득, 빈곤, 소득 5분위
hsum = df.groupby('hid')['p_dinc'].transform('sum').astype(float)
EQ = hsum / np.sqrt(df['hnum'].astype(float))
MED = wq(EQ, W, 0.5)
PLINE = 0.5 * MED
POOR = (EQ < PLINE)
QB = [wq(EQ, W, q) for q in (0.2, 0.4, 0.6, 0.8)]
INC5 = sum((EQ >= b).astype(int) for b in QB)  # 0..4

AGE = df['age']
SIDO_N = ['서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종', '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주']


def g_sido():
    return [(SIDO_N[i - 1], df['sido'] == i) for i in range(1, 18)]


def g_sex():
    return [('남', df['gender'] == 1), ('여', df['gender'] == 2)]


def g_age3():
    return [('0~17세', AGE <= 17), ('18~64세', (AGE >= 18) & (AGE <= 64)), ('65세 이상', AGE >= 65)]


def g_age6():
    return [('0~17세', AGE <= 17), ('18~34세', (AGE >= 18) & (AGE <= 34)), ('35~49세', (AGE >= 35) & (AGE <= 49)),
            ('50~64세', (AGE >= 50) & (AGE <= 64)), ('65~74세', (AGE >= 65) & (AGE <= 74)), ('75세 이상', AGE >= 75)]


def g_hs4():
    h = df['hnum']
    return [('1인', h == 1), ('2인', h == 2), ('3인', h == 3), ('4인 이상', h >= 4)]


def g_inc5():
    return [('%d분위' % (k + 1), INC5 == k) for k in range(5)]


def g_poor2():
    return [('비빈곤', ~POOR), ('빈곤', POOR)]


def g_none():
    return [(None, pd.Series(True, index=df.index))]


def cells_over(groups, fn):
    out = []
    for lab, m in groups:
        c = fn(m)
        c['labels'] = [] if lab is None else ([lab] if isinstance(lab, str) else list(lab))
        out.append({'labels': c['labels'], **{k: v for k, v in c.items() if k != 'labels'}})
    return out


def c_count(base, wt=None):
    wt = W if wt is None else wt

    def fn(m):
        mm = base & m
        n = int(mm.sum())
        return {'value': (float(wt[mm].sum()) if n > 0 else None), 'n': n}
    return fn


def c_rate(num, den, wt=None):
    wt = W if wt is None else wt

    def fn(m):
        d = den & m
        nu = num & d
        n = int(d.sum())
        if n == 0:
            return {'value': None, 'n': 0, 'n_num': 0}
        return {'value': float(wt[nu].sum() / wt[d].sum() * 100.0), 'n': n, 'n_num': int(nu.sum())}
    return fn


def c_mean(var, base, wt=None):
    wt = W if wt is None else wt
    x = df[var].astype(float)

    def fn(m):
        mm = base & m & x.notna()
        n = int(mm.sum())
        if n == 0:
            return {'value': None, 'n': 0}
        return {'value': float((x[mm] * wt[mm]).sum() / wt[mm].sum()), 'n': n}
    return fn


def c_sum(var, base, wt=None):
    wt = W if wt is None else wt
    x = df[var].astype(float)

    def fn(m):
        mm = base & m & x.notna()
        n = int(mm.sum())
        if n == 0:
            return {'value': None, 'n': 0}
        return {'value': float((x[mm] * wt[mm]).sum()), 'n': n}
    return fn


def c_quant(var, base, q, wt=None):
    wt = W if wt is None else wt
    x = df[var].astype(float)

    def fn(m):
        mm = base & m & x.notna()
        n = int(mm.sum())
        if n == 0:
            return {'value': None, 'n': 0}
        return {'value': wq(x[mm], wt[mm], q), 'n': n}
    return fn


ROWS = []


def add(id_, turn, reading, pct, cells, reading_no=1, ambiguous=False, note=''):
    ROWS.append({'id': id_, 'turn': turn, 'reading_no': reading_no, 'reading': reading, 'pct': pct,
                 'cells': cells, 'ambiguous': ambiguous, 'note': note})


ALL = pd.Series(True, index=df.index)
A65 = AGE >= 65
A75 = AGE >= 75
A1864 = (AGE >= 18) & (AGE <= 64)

# ================= C =================
lt = e1('ltcare_bn_yn')
add('C01a', 1, '대상: 65세 이상 인구 / 분자: 노인장기요양 수급(ltcare_bn_yn==1) / 분류: 없음 / 사용 변수: age, ltcare_bn_yn, indwgt', True,
    cells_over(g_none(), c_rate(lt, A65)))
add('C01b', 1, '대상: 75세 이상 인구 / 분자: 노인장기요양 수급(ltcare_bn_yn==1) / 분류: 없음 / 사용 변수: age, ltcare_bn_yn, indwgt', True,
    cells_over(g_none(), c_rate(lt, A75)))

js = e1('unempbn_jobseekbn_yn')
add('C02a', 1, '대상: 18~64세 인구 / 분자: 구직급여 연간 수급(unempbn_jobseekbn_yn==1) / 분류: 없음 / 사용 변수: age, unempbn_jobseekbn_yn, indwgt', True,
    cells_over(g_none(), c_rate(js, A1864)))
add('C02b', 1, '대상: 18~64세이면서 구직급여 연간 수급(unempbn_jobseekbn_yn==1)인 사람의 가중 인원 / 분류: 없음 / 사용 변수: age, unempbn_jobseekbn_yn, indwgt', False,
    cells_over(g_none(), c_count(js & A1864)))

hp3 = df['h_prop'] >= 300_000_000
add('C03a', 1, '대상: 전체 가구(가구주 행, hhwgt) / 분자: 가구 재산(h_prop) 3억원 이상 가구 / 분류: 없음 / 사용 변수: head, hhwgt, h_prop', True,
    cells_over(g_none(), c_rate(hp3 & HEAD, HEAD, HW)))
add('C03b', 1, '대상: 전체 인구(indwgt) / 분자: 가구 재산(h_prop) 3억원 이상 가구에 속한 사람 / 분류: 없음 / 사용 변수: indwgt, h_prop', True,
    cells_over(g_none(), c_rate(hp3, ALL)))

add('C04a', 1, '대상: 육아휴직급여 연간 수급자(empins_parentleave_yn1==1) 가중 인원 / 분류: 없음 / 사용 변수: empins_parentleave_yn1, indwgt', False,
    cells_over(g_none(), c_count(e1('empins_parentleave_yn1'))))
add('C04b', 1, '대상: 육아휴직급여 12월 기준 수급자(empins_parentleave_yn2==1) 가중 인원 / 분류: 없음 / 사용 변수: empins_parentleave_yn2, indwgt', False,
    cells_over(g_none(), c_count(e1('empins_parentleave_yn2'))))

gp = e1('govp_pension_yn')
add('C05a', 1, '대상: 공무원연금 정기연금 수급자(govp_pension_yn==1) / 대상 변수: govp_pension_amt 가중 평균 / 분류: 없음 / 사용 변수: govp_pension_yn, govp_pension_amt, indwgt', False,
    cells_over(g_none(), c_mean('govp_pension_amt', gp)))
add('C05b', 1, '대상: 공무원연금 정기연금 수급자(govp_pension_yn==1) / 대상 변수: govp_pension_amt 가중 중위수 / 분류: 없음 / 사용 변수: govp_pension_yn, govp_pension_amt, indwgt', False,
    cells_over(g_none(), c_quant('govp_pension_amt', gp, 0.5)))

al = e1('aid_live_yn1')
add('C06a', 1, '대상: 긴급복지 생계지원 연간 수급자(aid_live_yn1==1) / 대상 변수: aid_live_amt 가중 평균 / 분류: 없음 / 사용 변수: aid_live_yn1, aid_live_amt, indwgt', False,
    cells_over(g_none(), c_mean('aid_live_amt', al)))
add('C06b', 1, '대상: 긴급복지 생계지원 연간 수급자(aid_live_yn1==1) / 대상 변수: aid_live_amt 가중 합계 / 분류: 없음 / 사용 변수: aid_live_yn1, aid_live_amt, indwgt', False,
    cells_over(g_none(), c_sum('aid_live_amt', al)))

dp2 = e1('disp_yn2')
dis = e1('dis_yn')
add('C07a', 1, '대상: 전체 인구 / 분자: 장애인연금 12월 기준 수급(disp_yn2==1) / 분류: 없음 / 사용 변수: disp_yn2, indwgt', True,
    cells_over(g_none(), c_rate(dp2, ALL)))
add('C07b', 1, '대상: 등록장애인(dis_yn==1) / 분자: 장애인연금 12월 기준 수급(disp_yn2==1) / 분류: 없음 / 사용 변수: dis_yn, disp_yn2, indwgt', True,
    cells_over(g_none(), c_rate(dp2, dis)))

oc = e1('oldcare_yn1')
add('C08a', 1, '대상: 노인맞춤돌봄서비스 연간 이용자(oldcare_yn1==1) / 분자: 이용기간(oldcare_dur) 6개월 이상 / 분류: 없음 / 사용 변수: oldcare_yn1, oldcare_dur, indwgt', True,
    cells_over(g_none(), c_rate((df['oldcare_dur'] >= 6).fillna(False), oc)))
add('C08b', 1, '대상: 노인맞춤돌봄서비스 연간 이용자(oldcare_yn1==1) / 분자: 이용기간(oldcare_dur) 6개월 초과 / 분류: 없음 / 사용 변수: oldcare_yn1, oldcare_dur, indwgt', True,
    cells_over(g_none(), c_rate((df['oldcare_dur'] > 6).fillna(False), oc)))

inp = (df['nhi_in_dur'] > 0).fillna(False)
add('C09a', 1, '대상: 입원 진료를 받은 사람(nhi_in_dur>0) / 분자: 연간 재원일수 7일 미만 / 분류: 없음 / 사용 변수: nhi_in_dur, indwgt', True,
    cells_over(g_none(), c_rate((df['nhi_in_dur'] < 7).fillna(False), inp)))
add('C09b', 1, '대상: 입원 진료를 받은 사람(nhi_in_dur>0) / 분자: 연간 재원일수 7일 이하 / 분류: 없음 / 사용 변수: nhi_in_dur, indwgt', True,
    cells_over(g_none(), c_rate((df['nhi_in_dur'] <= 7).fillna(False), inp)))

af = e1('pubedu_aftsch_yn')
pc = e1('pubedu_pclot_yn')
add('C10a', 1, '대상: 방과후학교 자유수강권(pubedu_aftsch_yn==1)과 교육정보화 지원(pubedu_pclot_yn==1)을 모두 받은 사람의 가중 인원 / 분류: 없음 / 사용 변수: pubedu_aftsch_yn, pubedu_pclot_yn, indwgt', False,
    cells_over(g_none(), c_count(af & pc)))
add('C10b', 1, '대상: 방과후학교 자유수강권(pubedu_aftsch_yn==1) 또는 교육정보화 지원(pubedu_pclot_yn==1) 중 하나라도 받은 사람의 가중 인원 / 분류: 없음 / 사용 변수: pubedu_aftsch_yn, pubedu_pclot_yn, indwgt', False,
    cells_over(g_none(), c_count(af | pc)))

ow = e1('oldwork_type1_yn1')
add('C11a', 1, '대상: 노인일자리 공익활동 연간 참여자(oldwork_type1_yn1==1) 중 남성(gender==1)의 가중 인원 / 분류: 없음 / 사용 변수: oldwork_type1_yn1, gender, indwgt', False,
    cells_over(g_none(), c_count(ow & (df['gender'] == 1))))
add('C11b', 1, '대상: 노인일자리 공익활동 연간 참여자(oldwork_type1_yn1==1) 중 여성(gender==2)의 가중 인원 / 분류: 없음 / 사용 변수: oldwork_type1_yn1, gender, indwgt', False,
    cells_over(g_none(), c_count(ow & (df['gender'] == 2))))

cc = e1('childcare_yn1')
A06 = AGE <= 6
add('C12a', 1, '대상: 부산(sido==2) 거주 만 6세 이하 아동 / 분자: 보육료 지원 연간 수급(childcare_yn1==1) / 분류: 없음 / 사용 변수: sido, age, childcare_yn1, indwgt', True,
    cells_over(g_none(), c_rate(cc, A06 & (df['sido'] == 2))))
add('C12b', 1, '대상: 대구(sido==3) 거주 만 6세 이하 아동 / 분자: 보육료 지원 연간 수급(childcare_yn1==1) / 분류: 없음 / 사용 변수: sido, age, childcare_yn1, indwgt', True,
    cells_over(g_none(), c_rate(cc, A06 & (df['sido'] == 3))))

cap = df['sido'].isin([1, 4, 9])
nh2 = e1('nbls_house_yn2')
add('C13a', 1, '대상: 수도권(sido 1·4·9) 인구 / 분자: 주거급여 임차급여 12월 기준 수급(nbls_house_yn2==1) / 분류: 없음 / 사용 변수: sido, nbls_house_yn2, indwgt', True,
    cells_over(g_none(), c_rate(nh2, cap)))
add('C13b', 1, '대상: 비수도권(sido 1·4·9 외) 인구 / 분자: 주거급여 임차급여 12월 기준 수급(nbls_house_yn2==1) / 분류: 없음 / 사용 변수: sido, nbls_house_yn2, indwgt', True,
    cells_over(g_none(), c_rate(nh2, ~cap)))

npp = e1('np_pension_yn')
add('C14a', 1, '대상: 65세 이상이면서 국민연금 정기연금 연간 수급(np_pension_yn==1) / 분자: 상대 빈곤(균등화 가처분소득 < 전체 인구 가중 중위값의 50%) / 분류: 없음 / 사용 변수: age, np_pension_yn, p_dinc, hnum, hid, indwgt', True,
    cells_over(g_none(), c_rate(POOR, A65 & npp)))
add('C14b', 1, '대상: 65세 이상이면서 국민연금 정기연금 미수급(np_pension_yn 결측) / 분자: 상대 빈곤(균등화 가처분소득 < 전체 인구 가중 중위값의 50%) / 분류: 없음 / 사용 변수: age, np_pension_yn, p_dinc, hnum, hid, indwgt', True,
    cells_over(g_none(), c_rate(POOR, A65 & ~npp)))

ve = e1('vocaedu_yn')
add('C15a', 1, '대상: 국민내일배움카드 정부지원 수급자(vocaedu_yn==1) 가중 인원 / 분류: 성(남, 여) / 사용 변수: vocaedu_yn, gender, indwgt', False,
    cells_over(g_sex(), c_count(ve)))
add('C15b', 1, '대상: 국민내일배움카드 정부지원 수급자(vocaedu_yn==1) 가중 인원 / 분류: 소득 5분위(전체 인구 균등화 가처분소득 가중 20·40·60·80% 분위값 경계) / 사용 변수: vocaedu_yn, p_dinc, hnum, hid, indwgt', False,
    cells_over(g_inc5(), c_count(ve)))

# ================= F =================
add('F01', 1, '대상: 입원 진료를 받은 사람(nhi_in_dur>0) / 대상 변수: nhi_in_dur(연간 재원일수) 가중 평균 / 분류: 없음 / 사용 변수: nhi_in_dur, indwgt', False,
    cells_over(g_none(), c_mean('nhi_in_dur', inp)))
add('F01', 2, '대상: 입원 진료를 받은 여성(nhi_in_dur>0, gender==2) / 대상 변수: nhi_in_dur 가중 평균 / 분류: 연령대 3구간 / 사용 변수: nhi_in_dur, gender, age, indwgt', False,
    cells_over(g_age3(), c_mean('nhi_in_dur', inp & (df['gender'] == 2))))

add('F02', 1, '대상: 만 6세 이하 아동 / 분자: 보육료 지원 연간 수급(childcare_yn1==1) / 분류: 없음 / 사용 변수: age, childcare_yn1, indwgt', True,
    cells_over(g_none(), c_rate(cc, A06)))
add('F02', 2, '대상: 만 6세 이하이면서 보육료 지원 연간 수급(childcare_yn1==1)인 아동의 가중 인원 / 분류: 없음 / 사용 변수: age, childcare_yn1, indwgt', False,
    cells_over(g_none(), c_count(cc & A06)))
add('F02', 3, '대상: 만 6세 이하이면서 보육료 지원 연간 수급(childcare_yn1==1)인 아동의 가중 인원 / 분류: 시도 / 사용 변수: age, childcare_yn1, sido, indwgt', False,
    cells_over(g_sido(), c_count(cc & A06)))

ei2 = e1('empins_yn2')
NOTE_EI = '고용보험의 고정시점 가입 변수는 empins_yn2 하나이며 코드북상 기준일은 2022.10.31.임(질문은 12월 말). 고정시점 변수로 계산함'
add('F03', 1, '대상: 18~64세 인구 / 분자: 고용보험 고정시점 가입(empins_yn2==1) / 분류: 성 / 사용 변수: age, empins_yn2, gender, indwgt', True,
    cells_over(g_sex(), c_rate(ei2, A1864)), note=NOTE_EI)
add('F03', 2, '대상: 18~34세 인구 / 분자: 고용보험 고정시점 가입(empins_yn2==1) / 분류: 성 / 사용 변수: age, empins_yn2, gender, indwgt', True,
    cells_over(g_sex(), c_rate(ei2, (AGE >= 18) & (AGE <= 34))), note=NOTE_EI)

sev = (df['dis_grade_1'] == 1).fillna(False)
add('F04', 1, '대상: 등록장애인(dis_yn==1) / 분자: 종합장애정도가 심한 장애(dis_grade_1==1) / 분류: 없음 / 사용 변수: dis_yn, dis_grade_1, indwgt', True,
    cells_over(g_none(), c_rate(sev, dis)))
add('F04', 2, '대상: 등록장애인(dis_yn==1) / 분자: 종합장애정도가 심한 장애(dis_grade_1==1) / 분류: 성 / 사용 변수: dis_yn, dis_grade_1, gender, indwgt', True,
    cells_over(g_sex(), c_rate(sev, dis)))
NOTE_F04 = '3차례의 「같은 기준으로」가 직전 차례의 성별 분류까지 이어받는지, 1차례의 기준(등록장애인 중 심한 장애 비율)만 가리키는지 두 가지로 읽힘. 직전 맥락 승계(성별 유지)를 1로 봄'
add('F04', 3, '대상: 65세 이상 등록장애인(dis_yn==1, age>=65) / 분자: 종합장애정도가 심한 장애(dis_grade_1==1) / 분류: 성(직전 차례 분류 유지) / 사용 변수: dis_yn, dis_grade_1, age, gender, indwgt', True,
    cells_over(g_sex(), c_rate(sev, dis & A65)), reading_no=1, ambiguous=True, note=NOTE_F04)
add('F04', 3, '대상: 65세 이상 등록장애인(dis_yn==1, age>=65) / 분자: 종합장애정도가 심한 장애(dis_grade_1==1) / 분류: 없음 / 사용 변수: dis_yn, dis_grade_1, age, indwgt', True,
    cells_over(g_none(), c_rate(sev, dis & A65)), reading_no=2, ambiguous=True, note=NOTE_F04)

add('F05', 1, '대상: 전체 가구(가구주 행, hhwgt, 재산 0원 포함) / 대상 변수: h_prop 가중 평균 / 분류: 없음 / 사용 변수: head, hhwgt, h_prop', False,
    cells_over(g_none(), c_mean('h_prop', HEAD, HW)))
add('F05', 2, '대상: 전체 가구(가구주 행, hhwgt, 재산 0원 포함) / 대상 변수: h_prop 가중 중위수 / 분류: 없음 / 사용 변수: head, hhwgt, h_prop', False,
    cells_over(g_none(), c_quant('h_prop', HEAD, 0.5, HW)))
add('F05', 3, '대상: 전체 가구(가구주 행, hhwgt, 재산 0원 포함) / 대상 변수: h_prop 가중 중위수 / 분류: 가구원수 4구간 / 사용 변수: head, hhwgt, h_prop, hnum', False,
    cells_over(g_hs4(), c_quant('h_prop', HEAD, 0.5, HW)))

sf = e1('self_yn1')
add('F06', 1, '대상: 자활근로 연간 참여자(self_yn1==1) 가중 인원 / 분류: 없음 / 사용 변수: self_yn1, indwgt', False,
    cells_over(g_none(), c_count(sf)))
add('F06', 2, '대상: 자활근로 연간 참여자(self_yn1==1) 가중 인원 / 분류: 성 / 사용 변수: self_yn1, gender, indwgt', False,
    cells_over(g_sex(), c_count(sf)))
add('F06', 3, '대상: 자활근로 연간 참여자 중 여성(self_yn1==1, gender==2) / 대상 변수: self_amt 가중 평균 / 분류: 없음 / 사용 변수: self_yn1, gender, self_amt, indwgt', False,
    cells_over(g_none(), c_mean('self_amt', sf & (df['gender'] == 2))))

pp = e1('privschp_pension_yn')
add('F07', 1, '대상: 공무원연금 정기연금 수급자(govp_pension_yn==1) / 대상 변수: govp_pension_amt 가중 평균 / 분류: 없음 / 사용 변수: govp_pension_yn, govp_pension_amt, indwgt', False,
    cells_over(g_none(), c_mean('govp_pension_amt', gp)))
add('F07', 2, '대상: 사립학교교직원연금 정기연금 수급자(privschp_pension_yn==1) / 대상 변수: privschp_pension_amt 가중 평균 / 분류: 없음 / 사용 변수: privschp_pension_yn, privschp_pension_amt, indwgt', False,
    cells_over(g_none(), c_mean('privschp_pension_amt', pp)))
add('F07', 3, '대상: 사립학교교직원연금 정기연금 수급자(privschp_pension_yn==1) / 대상 변수: privschp_pension_amt 가중 합계 / 분류: 없음 / 사용 변수: privschp_pension_yn, privschp_pension_amt, indwgt', False,
    cells_over(g_none(), c_sum('privschp_pension_amt', pp)))

pl1 = e1('empins_parentleave_yn1')
pl2 = e1('empins_parentleave_yn2')
add('F08', 1, '대상: 육아휴직급여 연간 수급자(empins_parentleave_yn1==1) 가중 인원 / 분류: 성 / 사용 변수: empins_parentleave_yn1, gender, indwgt', False,
    cells_over(g_sex(), c_count(pl1)))
add('F08', 2, '대상: 육아휴직급여 12월 기준 수급자(empins_parentleave_yn2==1) 가중 인원 / 분류: 성 / 사용 변수: empins_parentleave_yn2, gender, indwgt', False,
    cells_over(g_sex(), c_count(pl2)))
add('F08', 3, '대상: 육아휴직급여 연간 수급자(empins_parentleave_yn1==1) / 대상 변수: empins_parentleave_amt 가중 평균 / 분류: 성 / 사용 변수: empins_parentleave_yn1, empins_parentleave_amt, gender, indwgt', False,
    cells_over(g_sex(), c_mean('empins_parentleave_amt', pl1)))

A718 = (AGE >= 7) & (AGE <= 18)
add('F09', 1, '대상: 7~18세 인구 / 분자: 교육급여 수급권 연간 보유(nbls_edu_yn1==1) / 분류: 없음 / 사용 변수: age, nbls_edu_yn1, indwgt', True,
    cells_over(g_none(), c_rate(e1('nbls_edu_yn1'), A718)))
add('F09', 2, '대상: 7~18세 인구 / 분자: 방과후학교 자유수강권 지원(pubedu_aftsch_yn==1) / 분류: 없음 / 사용 변수: age, pubedu_aftsch_yn, indwgt', True,
    cells_over(g_none(), c_rate(af, A718)))
add('F09', 3, '대상: 7~18세 인구 / 분자: 방과후학교 자유수강권 지원(pubedu_aftsch_yn==1) / 분류: 빈곤 여부(균등화 가처분소득 < 전체 인구 가중 중위값의 50%) / 사용 변수: age, pubedu_aftsch_yn, p_dinc, hnum, hid, indwgt', True,
    cells_over(g_poor2(), c_rate(af, A718)))

add('F10', 1, '대상: 65세 이상 인구 / 분자: 상대 빈곤(균등화 가처분소득 < 전체 인구 가중 중위값의 50%) / 분류: 없음 / 사용 변수: age, p_dinc, hnum, hid, indwgt', True,
    cells_over(g_none(), c_rate(POOR, A65)))
add('F10', 2, '대상: 65세 이상 인구 / 분자: 상대 빈곤 / 분류: 가구원수 4구간 / 사용 변수: age, hnum, p_dinc, hid, indwgt', True,
    cells_over(g_hs4(), c_rate(POOR, A65)))
add('F10', 3, '대상: 75세 이상 인구 / 분자: 상대 빈곤 / 분류: 가구원수 4구간 / 사용 변수: age, hnum, p_dinc, hid, indwgt', True,
    cells_over(g_hs4(), c_rate(POOR, A75)))

# ================= G =================
add('G01', 1, '대상: 65세 이상 인구 / 분자: 노인장기요양 수급(ltcare_bn_yn==1) / 분류: 시도 / 사용 변수: age, ltcare_bn_yn, sido, indwgt', True,
    cells_over(g_sido(), c_rate(lt, A65)), note='붙은 코드는 분모(65세 이상) 조건이 빠져 있음')

add('G02', 1, '대상: 사립학교교직원연금 12월 말 가입자(privschp_yn2==1) / 대상 변수: privschp_premium_amt(연간 보험료 납부액) 가중 평균 / 분류: 성 / 사용 변수: privschp_yn2, privschp_premium_amt, gender, indwgt', False,
    cells_over(g_sex(), c_mean('privschp_premium_amt', e1('privschp_yn2'))))

add('G03', 1, '대상: 두루누리 고용보험료 12월 기준 지원자(empins_support_yn2==1) 가중 인원 / 분류: 성 / 사용 변수: empins_support_yn2, gender, indwgt', False,
    cells_over(g_sex(), c_count(e1('empins_support_yn2'))), note='붙은 코드는 연간 변수(yn1)를 씀')

outp = (df['nhi_out_dur'] > 0).fillna(False)
add('G04', 1, '대상: 의과 외래 진료를 받은 사람(nhi_out_dur>0) / 분자: 연간 외래 내원일수 12일 이상(nhi_out_dur>=12) / 분류: 성 / 사용 변수: nhi_out_dur, gender, indwgt', True,
    cells_over(g_sex(), c_rate((df['nhi_out_dur'] >= 12).fillna(False), outp)), note='붙은 코드는 12일 초과(>)로 되어 있음')

add('G05', 1, '대상: 전체 가구(가구주 행, hhwgt) / 분자: 가구 재산(h_prop) 1억원 미만 가구 / 분류: 시도 / 사용 변수: head, hhwgt, h_prop, sido', True,
    cells_over(g_sido(), c_rate((df['h_prop'] < 100_000_000) & HEAD, HEAD, HW)), note='붙은 코드는 개인 단위(unit 미지정)임')

A08 = AGE < 8
add('G06', 1, '대상: 만 8세 미만 아동 / 분자: 아동수당 12월 기준 수급(childbn_yn2==1) / 분류: 성 / 사용 변수: age, childbn_yn2, gender, indwgt', True,
    cells_over(g_sex(), c_rate(e1('childbn_yn2'), A08)), note='붙은 코드는 분모가 전체 인구임')

add('G07', 1, '대상: 장애인활동지원 연간 이용자(disvou_act_yn1==1) / 대상 변수: disvou_act_subsidy(정부지원금) 가중 합계 / 분류: 없음 / 사용 변수: disvou_act_yn1, disvou_act_subsidy, indwgt', False,
    cells_over(g_none(), c_sum('disvou_act_subsidy', e1('disvou_act_yn1'))), note='붙은 코드는 평균(mean)임')

add('G08', 1, '대상: 65세 이상 인구 / 대상 변수: p_dinc(개인 가처분소득) 가중 평균 / 분류: 성 / 사용 변수: age, p_dinc, gender, indwgt', False,
    cells_over(g_sex(), c_mean('p_dinc', A65)), note='붙은 코드는 가구 가처분소득(h_dinc)을 씀')

add('G09', 1, '대상: 출산전후휴가 급여 연간 수급자(empins_matleave_yn1==1) / 대상 변수: empins_matleave_amt 가중 평균 / 분류: 없음 / 사용 변수: empins_matleave_yn1, empins_matleave_amt, indwgt', False,
    cells_over(g_none(), c_mean('empins_matleave_amt', e1('empins_matleave_yn1'))), note='붙은 코드의 변수명에 empins_ 접두어가 빠져 있음')

add('G10', 1, '대상: 18~64세 인구 / 분자: 국민취업지원제도 연간 참여(kua_yn1==1) / 분류: 성 / 사용 변수: age, kua_yn1, gender, indwgt', True,
    cells_over(g_sex(), c_rate(e1('kua_yn1'), A1864)), note='붙은 코드는 연령 조건이 or 로 되어 있음')

g_old3 = [('65~69세', (AGE >= 65) & (AGE <= 69)), ('70~79세', (AGE >= 70) & (AGE <= 79)), ('80세 이상', AGE >= 80)]
add('G11', 1, '대상: 65세 이상 인구(연령 구간별 전체 인구) / 분자: 본인부담상한제 지원(nhi_ceiling_subsidy_yn==1) / 분류: 65~69세, 70~79세, 80세 이상 / 사용 변수: age, nhi_ceiling_subsidy_yn, indwgt', True,
    cells_over(g_old3, c_rate(e1('nhi_ceiling_subsidy_yn'), A65)), note='분모는 구간별 전체 인구(지원 여부 결측 포함)')

add('G12', 1, '대상: 등록장애인(dis_yn==1) 가중 인원 / 분류: 연령대 6구간 / 사용 변수: dis_yn, age, indwgt', False,
    cells_over(g_age6(), c_count(dis)), note='붙은 코드는 3구간(age3)임')

# ================= E =================
add('E02', 1, '대상: 생계급여 12월 기준 수급자(nbls_live_yn2==1) 가중 인원 / 분류: 시도 / 사용 변수: nbls_live_yn2, sido, indwgt', False,
    cells_over(g_sido(), c_count(e1('nbls_live_yn2'))))

bp1 = e1('bp_yn1')
add('E05', 1, '대상: 기초연금 연간 수급자(bp_yn1==1, 개인 단위) / 대상 변수: 소속 가구 재산(h_prop)의 개인 가중 90% 분위수 / 분류: 없음 / 사용 변수: bp_yn1, h_prop, indwgt', False,
    cells_over(g_none(), c_quant('h_prop', bp1, 0.9)))

add('E08', 1, '대상: 65세 이상 인구 / 분자: 기초연금 연간 수급(bp_yn1==1) / 분류: 시도 / 사용 변수: age, bp_yn1, sido, indwgt', True,
    cells_over(g_sido(), c_rate(bp1, A65)))

sp1 = e1('nhi_special1_yn')
add('E11', 1, '대상: 산정특례 암 등록자(nhi_special1_yn==1) 가중 인원 / 분류: 성 / 사용 변수: nhi_special1_yn, gender, indwgt', False,
    cells_over(g_sex(), c_count(sp1)))
add('E11', 2, '대상: 산정특례 암 등록자(nhi_special1_yn==1) / 대상 변수: nhi_out_fee(의과 외래 본인부담금) 가중 합계 / 분류: 성 / 사용 변수: nhi_special1_yn, nhi_out_fee, gender, indwgt', False,
    cells_over(g_sex(), c_sum('nhi_out_fee', sp1)))

DT = ['간', '뇌병변', '뇌전증', '시각', '신장', '심장', '안면', '언어', '자폐성장애', '장루·요루', '정신', '지적장애', '지체', '청각', '호흡기']
den_dt = dis & df['dis_type_1'].notna()
g_dt = [(DT[k - 1], (df['dis_type_1'] == k).fillna(False)) for k in range(1, 16)]
cells = []
for lab, m in g_dt:
    nu = den_dt & m
    n_num = int(nu.sum())
    cells.append({'labels': [lab], 'value': (float(W[nu].sum() / W[den_dt].sum() * 100.0) if n_num > 0 else None),
                  'n': int(den_dt.sum()), 'n_num': n_num})
add('E14', 1, '대상: 등록장애인(dis_yn==1) / 분자: 주장애유형(dis_type_1) 코드별 인원(구성비) / 분류: 주장애유형 15종 / 사용 변수: dis_yn, dis_type_1, indwgt', True, cells)

g_dis2 = [('등록장애인', dis), ('비장애인', ~dis)]
add('E17', 1, '대상: 65세 이상 인구 / 분자: 상대 빈곤(균등화 가처분소득 < 전체 인구 가중 중위값의 50%) / 분류: 등록장애인(dis_yn==1), 비장애인(dis_yn 결측) / 사용 변수: age, dis_yn, p_dinc, hnum, hid, indwgt', True,
    cells_over(g_dis2, c_rate(POOR, A65)))

add('E19', 1, '대상: 장애인연금 12월 기준 수급자(disp_yn2==1) 가중 인원 / 분류: 성 / 사용 변수: disp_yn2, gender, indwgt', False,
    cells_over(g_sex(), c_count(dp2)))

g_grade = [('심한 장애', (df['dis_grade_1'] == 1).fillna(False)), ('심하지 않은 장애', (df['dis_grade_1'] == 2).fillna(False))]
add('E22', 1, '대상: 등록장애인(dis_yn==1) 중 외래 진료 기록이 있는 사람(nhi_out_fee 값 있음) / 대상 변수: nhi_out_fee 가중 평균 / 분류: 종합장애정도(dis_grade_1) / 사용 변수: dis_yn, dis_grade_1, nhi_out_fee, indwgt', False,
    cells_over(g_grade, c_mean('nhi_out_fee', dis)))

# ---------- 저장 ----------
with open(OUT, 'w', encoding='utf-8') as f:
    for r in ROWS:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')

# ---------- 점검용 요약(집계값만) ----------
print('rows', len(ROWS), 'turns', len({(r['id'], r['turn']) for r in ROWS}))
print('median eqinc', MED, 'pline', PLINE, 'q bounds', QB)
for r in ROWS:
    cs = r['cells']
    s = '; '.join('%s=%s(n=%s%s)' % ('/'.join(c['labels']) or '-', ('%.6g' % c['value']) if c['value'] is not None else 'null', c['n'],
                                      (',num=%s' % c['n_num']) if 'n_num' in c else '') for c in cs)
    print(r['id'], r['turn'], r['reading_no'], 'pct' if r['pct'] else 'val', s)
