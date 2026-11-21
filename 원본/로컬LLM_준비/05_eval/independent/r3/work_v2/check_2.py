# -*- coding: utf-8 -*-
"""독립 검산(check_2): 질문 문장만 보고 pandas로 직접 계산. ssda 미사용. 집계값만 기록."""
import json
import numpy as np
import pandas as pd

P = '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
OUT = '/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r3/truth/check_2.jsonl'

df = pd.read_parquet(P)
N = len(df)
W = df['indwgt'].to_numpy(float)
HW = df['hhwgt'].to_numpy(float)
HEAD = (df['head'] == 1).to_numpy()
ALL = np.ones(N, bool)


def m(cond):
    """조건의 결측은 거짓으로 처리한 bool 배열."""
    if isinstance(cond, np.ndarray):
        return cond.astype(bool)
    return cond.fillna(False).to_numpy(bool)


def eq1(v):
    return m(df[v] == 1)


age = df['age'].to_numpy()
sex = df['gender'].to_numpy()
sido = df['sido'].to_numpy()
hnum = df['hnum'].to_numpy()

# ---------- 파생: 균등화 가처분소득, 5분위, 빈곤 ----------
hh_dinc = df.groupby('hid')['p_dinc'].transform('sum').to_numpy(float)
eqinc = hh_dinc / np.sqrt(hnum)


def wquantile(x, w, q):
    """오름차순, 가중치 누적합이 전체의 q배에 처음 이르는 값."""
    x = np.asarray(x, float)
    w = np.asarray(w, float)
    ok = ~np.isnan(x)
    x, w = x[ok], w[ok]
    if len(x) == 0:
        return None
    o = np.argsort(x, kind='mergesort')
    x, w = x[o], w[o]
    c = np.cumsum(w)
    i = int(np.searchsorted(c, q * c[-1], side='left'))
    i = min(i, len(x) - 1)
    return float(x[i])


QB = [wquantile(eqinc, W, q) for q in (0.2, 0.4, 0.6, 0.8)]
inc5 = np.zeros(N, int)
for b in QB:
    inc5 += (eqinc >= b).astype(int)
MED = wquantile(eqinc, W, 0.5)
POOR = eqinc < 0.5 * MED

# ---------- 분류 기준 ----------
SIDO_NM = ['서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종', '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주']
G_SIDO = [(SIDO_NM[i], sido == i + 1) for i in range(17)]
G_SEX = [('남', sex == 1), ('여', sex == 2)]
G_AGE3 = [('0~17세', age <= 17), ('18~64세', (age >= 18) & (age <= 64)), ('65세 이상', age >= 65)]
G_HS4 = [('1인', hnum == 1), ('2인', hnum == 2), ('3인', hnum == 3), ('4인 이상', hnum >= 4)]
G_INC5 = [(f'{i + 1}분위', inc5 == i) for i in range(5)]
nt = df['nhi_type'].to_numpy()
G_NHI3 = [('지역가입', np.isin(nt, [1, 2])), ('직장가입', np.isin(nt, [5, 6])), ('의료급여', np.isin(nt, [7, 8]))]
G_NHI6 = [('지역세대주', nt == 1), ('지역세대원', nt == 2), ('직장가입자', nt == 5), ('직장피부양자', nt == 6),
          ('의료급여세대주', nt == 7), ('의료급여세대원', nt == 8)]
G_OLD3 = [('65~74세', (age >= 65) & (age <= 74)), ('75~84세', (age >= 75) & (age <= 84)), ('85세 이상', age >= 85)]
G_NONE = [(None, ALL)]


def cross(g1, g2):
    return [((a, b), ma & mb) for a, ma in g1 for b, mb in g2]


def lab(l):
    if l is None:
        return []
    if isinstance(l, tuple):
        return list(l)
    return [l]


def wts(unit):
    return (HW, HEAD) if unit == 'hh' else (W, ALL)


# ---------- 집계 ----------
def rate(num, den, groups=G_NONE, unit='ind'):
    w, base = wts(unit)
    cells = []
    for l, g in groups:
        d = den & g & base
        nmr = num & d
        n, nn = int(d.sum()), int(nmr.sum())
        val = None if n == 0 else float(100 * w[nmr].sum() / w[d].sum())
        cells.append({'labels': lab(l), 'value': val, 'n': n, 'n_num': nn})
    return cells


def count(where, groups=G_NONE, unit='ind'):
    w, base = wts(unit)
    cells = []
    for l, g in groups:
        d = where & g & base
        n = int(d.sum())
        cells.append({'labels': lab(l), 'value': None if n == 0 else float(w[d].sum()), 'n': n})
    return cells


def _stat(var, where, groups, unit, kind, q=None):
    w, base = wts(unit)
    x = df[var].to_numpy(float) if isinstance(var, str) else np.asarray(var, float)
    cells = []
    for l, g in groups:
        d = where & g & base & ~np.isnan(x)
        n = int(d.sum())
        if n == 0:
            val = None
        elif kind == 'mean':
            val = float((x[d] * w[d]).sum() / w[d].sum())
        elif kind == 'total':
            val = float((x[d] * w[d]).sum())
        else:
            val = wquantile(x[d], w[d], q)
        cells.append({'labels': lab(l), 'value': val, 'n': n})
    return cells


def mean(var, where, groups=G_NONE, unit='ind'):
    return _stat(var, where, groups, unit, 'mean')


def total(var, where, groups=G_NONE, unit='ind'):
    return _stat(var, where, groups, unit, 'total')


def quant(var, q, where, groups=G_NONE, unit='ind'):
    return _stat(var, where, groups, unit, 'q', q)


def share(cats, where, unit='ind'):
    """구성비(%): 분모는 where 중 범주가 정해진 사람 전체."""
    w, base = wts(unit)
    anyc = np.zeros(N, bool)
    for _, g in cats:
        anyc |= g
    d = where & base & anyc
    n = int(d.sum())
    cells = []
    for l, g in cats:
        c = d & g
        nn = int(c.sum())
        val = None if n == 0 else float(100 * w[c].sum() / w[d].sum())
        cells.append({'labels': lab(l), 'value': val, 'n': n, 'n_num': nn})
    return cells


def poverty(where, groups=G_NONE):
    return rate(POOR, where, groups)


ROWS = []


def add(id_, turn, reading, pct, cells, reading_no=1, ambiguous=False, note=''):
    ROWS.append({'id': id_, 'turn': turn, 'reading_no': reading_no, 'reading': reading, 'pct': pct,
                 'cells': cells, 'ambiguous': ambiguous, 'note': note})


# ================= C =================
lt = eq1('ltcare_bn_yn')
add('C01a', 1, '대상: 65세 이상 / 분자: 장기요양 수급(연간) ltcare_bn_yn==1 / 분류: 없음 / 사용 변수: age, ltcare_bn_yn, indwgt',
    True, rate(lt, age >= 65))
add('C01b', 1, '대상: 75세 이상 / 분자: 장기요양 수급(연간) ltcare_bn_yn==1 / 분류: 없음 / 사용 변수: age, ltcare_bn_yn, indwgt',
    True, rate(lt, age >= 75))

dis = eq1('dis_yn')
a1864 = (age >= 18) & (age <= 64)
add('C02a', 1, '대상: 18~64세 인구 / 분자: 등록장애인 dis_yn==1 / 분류: 성 / 사용 변수: age, gender, dis_yn, indwgt',
    True, rate(dis, a1864, G_SEX))
add('C02b', 1, '대상: 18~64세 등록장애인(dis_yn==1) 가중 인원 / 분류: 성 / 사용 변수: age, gender, dis_yn, indwgt',
    False, count(dis & a1864, G_SEX))

hprop = df['h_prop'].to_numpy(float)
add('C03a', 1, '대상: 가구 재산 h_prop>=5억원인 가구(가구주 행, hhwgt) 수 / 분류: 없음 / 사용 변수: h_prop, head, hhwgt',
    False, count(hprop >= 5e8, unit='hh'))
add('C03b', 1, '대상: 가구 재산 h_prop>=5억원인 가구에 속한 개인(indwgt) 수 / 분류: 없음 / 사용 변수: h_prop, indwgt',
    False, count(hprop >= 5e8))

add('C04a', 1, '대상: 육아휴직급여(사후지급금 제외) 연간 수급 empins_parentleave_yn1==1 가중 인원 / 분류: 없음 / 사용 변수: empins_parentleave_yn1, indwgt',
    False, count(eq1('empins_parentleave_yn1')))
add('C04b', 1, '대상: 육아휴직급여(사후지급금 제외) 12월 기준 수급 empins_parentleave_yn2==1 가중 인원 / 분류: 없음 / 사용 변수: empins_parentleave_yn2, indwgt',
    False, count(eq1('empins_parentleave_yn2')))

gp = eq1('govp_pension_yn')
add('C05a', 1, '대상: 공무원연금 정기연금 연간 수급자 govp_pension_yn==1 / 대상 변수: govp_pension_amt 가중 평균 / 분류: 없음 / 사용 변수: govp_pension_yn, govp_pension_amt, indwgt',
    False, mean('govp_pension_amt', gp))
add('C05b', 1, '대상: 공무원연금 정기연금 연간 수급자 govp_pension_yn==1 / 대상 변수: govp_pension_amt 가중 중위수 / 분류: 없음 / 사용 변수: govp_pension_yn, govp_pension_amt, indwgt',
    False, quant('govp_pension_amt', 0.5, gp))

cc = eq1('childcare_yn1')
add('C06a', 1, '대상: 보육료지원 연간 수급 childcare_yn1==1 / 대상 변수: childcare_amt 가중 평균 / 분류: 없음 / 사용 변수: childcare_yn1, childcare_amt, indwgt',
    False, mean('childcare_amt', cc))
add('C06b', 1, '대상: 보육료지원 연간 수급 childcare_yn1==1 / 대상 변수: childcare_amt 가중 합계 / 분류: 없음 / 사용 변수: childcare_yn1, childcare_amt, indwgt',
    False, total('childcare_amt', cc))

a718 = (age >= 7) & (age <= 18)
aft = eq1('pubedu_aftsch_yn')
edu = eq1('nbls_edu_yn1')
add('C07a', 1, '대상: 만 7~18세 인구 전체 / 분자: 방과후학교 자유수강권 지원 pubedu_aftsch_yn==1 / 분류: 없음 / 사용 변수: age, pubedu_aftsch_yn, indwgt',
    True, rate(aft, a718))
add('C07b', 1, '대상: 만 7~18세 교육급여 수급권자(연간) nbls_edu_yn1==1 / 분자: 방과후학교 자유수강권 지원 pubedu_aftsch_yn==1 / 분류: 없음 / 사용 변수: age, nbls_edu_yn1, pubedu_aftsch_yn, indwgt',
    True, rate(aft, a718 & edu))

od = df['nhi_out_dur']
add('C08a', 1, '대상: 65세 이상 인구 / 분자: 외래 내원일수 nhi_out_dur>=30(결측은 미해당) / 분류: 없음 / 사용 변수: age, nhi_out_dur, indwgt',
    True, rate(m(od >= 30), age >= 65))
add('C08b', 1, '대상: 65세 이상 인구 / 분자: 외래 내원일수 nhi_out_dur>30(결측은 미해당) / 분류: 없음 / 사용 변수: age, nhi_out_dur, indwgt',
    True, rate(m(od > 30), age >= 65))

js = eq1('unempbn_jobseekbn_yn')
jd = df['unempbn_jobseekbn_dur']
add('C09a', 1, '대상: 구직급여 연간 수급 unempbn_jobseekbn_yn==1 이면서 수급일수 unempbn_jobseekbn_dur<120 가중 인원 / 분류: 없음 / 사용 변수: unempbn_jobseekbn_yn, unempbn_jobseekbn_dur, indwgt',
    False, count(js & m(jd < 120)))
add('C09b', 1, '대상: 구직급여 연간 수급 unempbn_jobseekbn_yn==1 이면서 수급일수 unempbn_jobseekbn_dur<=120 가중 인원 / 분류: 없음 / 사용 변수: unempbn_jobseekbn_yn, unempbn_jobseekbn_dur, indwgt',
    False, count(js & m(jd <= 120)))

itc, itcc = eq1('itc_yn'), eq1('itc_child_yn')
add('C10a', 1, '대상: 근로장려 대상 itc_yn==1 이고 자녀장려 대상 itc_child_yn==1 가중 인원 / 분류: 없음 / 사용 변수: itc_yn, itc_child_yn, indwgt',
    False, count(itc & itcc))
add('C10b', 1, '대상: 근로장려 대상 itc_yn==1 이거나 자녀장려 대상 itc_child_yn==1 가중 인원 / 분류: 없음 / 사용 변수: itc_yn, itc_child_yn, indwgt',
    False, count(itc | itcc))

note11 = '질문의 「의료급여 세대주·세대원」은 코드값 7·8 두 범주로 나누어 6칸으로 산출함. 한 범주로 합치면 두 칸의 합. 구성비의 n은 분모(대상 전체), n_num은 해당 범주 관측 수'
add('C11a', 1, '대상: 65세 이상 남성 / 구성비: 건강보험 가입유형 nhi_type 6범주(12월) / 사용 변수: age, gender, nhi_type, indwgt',
    True, share(G_NHI6, (age >= 65) & (sex == 1)), note=note11)
add('C11b', 1, '대상: 65세 이상 여성 / 구성비: 건강보험 가입유형 nhi_type 6범주(12월) / 사용 변수: age, gender, nhi_type, indwgt',
    True, share(G_NHI6, (age >= 65) & (sex == 2)), note=note11)

oc = eq1('oldcare_yn1')
add('C12a', 1, '대상: 부산(sido==2) 65세 이상 / 분자: 노인맞춤돌봄서비스 연간 이용 oldcare_yn1==1 / 분류: 없음 / 사용 변수: sido, age, oldcare_yn1, indwgt',
    True, rate(oc, (sido == 2) & (age >= 65)))
add('C12b', 1, '대상: 대구(sido==3) 65세 이상 / 분자: 노인맞춤돌봄서비스 연간 이용 oldcare_yn1==1 / 분류: 없음 / 사용 변수: sido, age, oldcare_yn1, indwgt',
    True, rate(oc, (sido == 3) & (age >= 65)))

cap = np.isin(sido, [1, 4, 9])
dep = m(df['ee_deposit_amt_ptot'] > 0)
add('C13a', 1, '대상: 수도권(sido 1·4·9) 거주, 임차 보증금 ee_deposit_amt_ptot>0 / 대상 변수: ee_deposit_amt_ptot 가중 중위수 / 분류: 없음 / 사용 변수: sido, ee_deposit_amt_ptot, indwgt',
    False, quant('ee_deposit_amt_ptot', 0.5, cap & dep))
add('C13b', 1, '대상: 비수도권(sido 1·4·9 외) 거주, 임차 보증금 ee_deposit_amt_ptot>0 / 대상 변수: ee_deposit_amt_ptot 가중 중위수 / 분류: 없음 / 사용 변수: sido, ee_deposit_amt_ptot, indwgt',
    False, quant('ee_deposit_amt_ptot', 0.5, ~cap & dep))

npn = eq1('np_pension_yn')
add('C14a', 1, '대상: 65세 이상, 국민연금 정기연금 연간 수급 np_pension_yn==1 / 지표: 상대 빈곤율(균등화 가처분소득 < 전체 개인 가중 중위값의 50%) / 분류: 없음 / 사용 변수: age, np_pension_yn, p_dinc, hnum, hid, indwgt',
    True, poverty((age >= 65) & npn))
add('C14b', 1, '대상: 65세 이상, 국민연금 정기연금 연간 미수급(np_pension_yn 결측) / 지표: 상대 빈곤율 / 분류: 없음 / 사용 변수: age, np_pension_yn, p_dinc, hnum, hid, indwgt',
    True, poverty((age >= 65) & ~npn))

ho2 = eq1('nbls_house_yn2')
add('C15a', 1, '대상: 각 연령대 전체 인구 / 분자: 주거급여 임차급여 12월 수급 nbls_house_yn2==1 / 분류: 연령대 3구간 / 사용 변수: age, nbls_house_yn2, indwgt',
    True, rate(ho2, ALL, G_AGE3))
add('C15b', 1, '대상: 각 가구원수 집단 전체 인구 / 분자: 주거급여 임차급여 12월 수급 nbls_house_yn2==1 / 분류: 가구원수 4구간(hnum) / 사용 변수: hnum, nbls_house_yn2, indwgt',
    True, rate(ho2, ALL, G_HS4))

# ================= F =================
inp = m(df['nhi_in_dur'] > 0)
r = '대상: 2022년 입원 경험자(nhi_in_dur 값 있음, >0) / 대상 변수: nhi_in_dur 가중 평균(일) / 분류: {} / 사용 변수: nhi_in_dur, nhi_type, age, indwgt'
add('F01', 1, r.format('없음'), False, mean('nhi_in_dur', inp))
add('F01', 2, r.format('건강보험 가입 구분 3구간(nhi_type 1·2 / 5·6 / 7·8)'), False, mean('nhi_in_dur', inp, G_NHI3))
add('F01', 3, r.format('건강보험 가입 구분 3구간, 대상을 75세 이상으로 한정'), False, mean('nhi_in_dur', inp & (age >= 75), G_NHI3))

add('F02', 1, '대상: 전체 가구(가구주 행, hhwgt) / 대상 변수: h_prop 가중 평균(원) / 분류: 없음 / 사용 변수: h_prop, head, hhwgt',
    False, mean('h_prop', ALL, unit='hh'))
add('F02', 2, '대상: 전체 가구(가구주 행, hhwgt) / 대상 변수: h_prop 가중 평균(원) / 분류: 가구원수 4구간 / 사용 변수: h_prop, hnum, head, hhwgt',
    False, mean('h_prop', ALL, G_HS4, unit='hh'))
add('F02', 3, '대상: 전체 가구(가구주 행, hhwgt) / 분자: 가구 재산 h_prop==0인 가구 / 분류: 가구원수 4구간 / 사용 변수: h_prop, hnum, head, hhwgt',
    True, rate(hprop == 0, ALL, G_HS4, unit='hh'))

a05 = age <= 5
add('F03', 1, '대상: 만 0~5세 / 분자: 보육료지원 연간 수급 childcare_yn1==1 / 분류: 없음 / 사용 변수: age, childcare_yn1, indwgt',
    True, rate(cc, a05))
add('F03', 2, '대상: 만 0~5세 중 보육료지원 연간 수급 childcare_yn1==1 가중 인원 / 분류: 없음 / 사용 변수: age, childcare_yn1, indwgt',
    False, count(cc & a05))
add('F03', 3, '대상: 만 0~5세 중 보육료지원 연간 수급 childcare_yn1==1 가중 인원 / 분류: 시도 / 사용 변수: age, childcare_yn1, sido, indwgt',
    False, count(cc & a05, G_SIDO))

n5 = '5분위 경계는 전체 인구의 균등화 가처분소득 개인 가중 20·40·60·80% 분위값. 구성비의 n은 분모(대상 전체), n_num은 해당 분위 관측 수'
add('F04', 1, '대상: 구직급여 연간 수급자 unempbn_jobseekbn_yn==1 / 구성비: 소득 5분위 / 사용 변수: unempbn_jobseekbn_yn, p_dinc, hnum, hid, indwgt',
    True, share(G_INC5, js), note=n5)
add('F04', 2, '대상: 여성 구직급여 연간 수급자 / 구성비: 소득 5분위 / 사용 변수: unempbn_jobseekbn_yn, gender, p_dinc, hnum, hid, indwgt',
    True, share(G_INC5, js & (sex == 2)), note=n5)
add('F04', 3, '대상: 여성 구직급여 연간 수급자 / 대상 변수: unempbn_jobseekbn_amt 가중 평균(원) / 분류: 없음 / 사용 변수: unempbn_jobseekbn_yn, gender, unempbn_jobseekbn_amt, indwgt',
    False, mean('unempbn_jobseekbn_amt', js & (sex == 2)))

sev = dis & m(df['dis_grade_1'] == 1)
add('F05', 1, '대상: 등록장애인 dis_yn==1 / 지표: 상대 빈곤율 / 분류: 없음 / 사용 변수: dis_yn, p_dinc, hnum, hid, indwgt',
    True, poverty(dis))
add('F05', 2, '대상: 등록장애인 중 종합장애정도 심한(dis_grade_1==1) / 지표: 상대 빈곤율 / 분류: 없음 / 사용 변수: dis_yn, dis_grade_1, p_dinc, hnum, hid, indwgt',
    True, poverty(sev))
add('F05', 3, '대상: 등록장애인 중 종합장애정도 심한(dis_grade_1==1) / 지표: 상대 빈곤율 / 분류: 성 / 사용 변수: dis_yn, dis_grade_1, gender, p_dinc, hnum, hid, indwgt',
    True, poverty(sev, G_SEX))

vis, dn = eq1('ltcare_visit_yn'), eq1('ltcare_daynight_yn')
add('F06', 1, '대상: 장기요양 연간 수급자 ltcare_bn_yn==1 / 분자: 방문요양 ltcare_visit_yn==1 / 분류: 없음 / 사용 변수: ltcare_bn_yn, ltcare_visit_yn, indwgt',
    True, rate(vis, lt))
add('F06', 2, '대상: 장기요양 연간 수급자 ltcare_bn_yn==1 / 분자: 주야간보호 ltcare_daynight_yn==1 / 분류: 없음 / 사용 변수: ltcare_bn_yn, ltcare_daynight_yn, indwgt',
    True, rate(dn, lt))
add('F06', 3, '대상: 75세 이상 장기요양 연간 수급자 / 분자: 주야간보호 ltcare_daynight_yn==1(직전 차례의 지표) / 분류: 없음 / 사용 변수: age, ltcare_bn_yn, ltcare_daynight_yn, indwgt',
    True, rate(dn, lt & (age >= 75)), ambiguous=True,
    note='「그걸」이 직전 차례의 주야간보호 비율을 가리킨다고 봄(해석 1). 첫 차례의 방문요양까지 다시 보라는 뜻으로도 읽힐 수 있어 방문요양 비율을 해석 2로 둠')
add('F06', 3, '대상: 75세 이상 장기요양 연간 수급자 / 분자: 방문요양 ltcare_visit_yn==1 / 분류: 없음 / 사용 변수: age, ltcare_bn_yn, ltcare_visit_yn, indwgt',
    True, rate(vis, lt & (age >= 75)), reading_no=2, ambiguous=True,
    note='해석 2: 75세 이상 수급자의 방문요양 이용 비율')

al = eq1('aid_live_yn1')
add('F07', 1, '대상: 긴급복지 생계지원 연간 수급 aid_live_yn1==1 가중 인원 / 분류: 없음 / 사용 변수: aid_live_yn1, indwgt',
    False, count(al))
add('F07', 2, '대상: 긴급복지 생계지원 연간 수급자 / 대상 변수: aid_live_amt 가중 평균(원) / 분류: 없음 / 사용 변수: aid_live_yn1, aid_live_amt, indwgt',
    False, mean('aid_live_amt', al))
add('F07', 3, '대상: 긴급복지 생계지원 연간 수급자 / 대상 변수: aid_live_amt 가중 합계(원) / 분류: 없음 / 사용 변수: aid_live_yn1, aid_live_amt, indwgt',
    False, total('aid_live_amt', al))

G_EDU2 = [('만 7~12세', (age >= 7) & (age <= 12)), ('만 13~18세', (age >= 13) & (age <= 18))]
add('F08', 1, '대상: 교육급여 수급권 연간 보유 nbls_edu_yn1==1 / 대상 변수: 교육활동지원비 nbls_edu_amt1 가중 평균(원) / 분류: 없음 / 사용 변수: nbls_edu_yn1, nbls_edu_amt1, indwgt',
    False, mean('nbls_edu_amt1', edu))
add('F08', 2, '대상: 교육급여 수급권 연간 보유 nbls_edu_yn1==1 / 대상 변수: 교육활동지원비 nbls_edu_amt1 가중 평균(원) / 분류: 연령 2구간(7~12세, 13~18세) / 사용 변수: nbls_edu_yn1, nbls_edu_amt1, age, indwgt',
    False, mean('nbls_edu_amt1', edu, G_EDU2))

gv2 = eq1('govp_yn2')
add('F09', 1, '대상: 공무원연금 12월 31일 기준 가입 govp_yn2==1 가중 인원 / 분류: 없음 / 사용 변수: govp_yn2, indwgt',
    False, count(gv2))
add('F09', 2, '대상: 여성 중 공무원연금 12월 31일 기준 가입 govp_yn2==1 가중 인원 / 분류: 없음 / 사용 변수: govp_yn2, gender, indwgt',
    False, count(gv2 & (sex == 2)))
add('F09', 3, '대상: 여성 공무원연금 12월 31일 기준 가입자 / 대상 변수: 보험료 납부액(본인부담, 연간) govp_premium_amt 가중 평균(원) / 분류: 없음 / 사용 변수: govp_yn2, gender, govp_premium_amt, indwgt',
    False, mean('govp_premium_amt', gv2 & (sex == 2)))

pl1, pl2 = eq1('empins_parentleave_yn1'), eq1('empins_parentleave_yn2')
add('F10', 1, '대상: 육아휴직급여(사후지급금 제외) 연간 수급 empins_parentleave_yn1==1 / 분자: 남성 gender==1 / 분류: 없음 / 사용 변수: empins_parentleave_yn1, gender, indwgt',
    True, rate(sex == 1, pl1))
add('F10', 2, '대상: 육아휴직급여(사후지급금 제외) 12월 기준 수급 empins_parentleave_yn2==1 / 분자: 남성 gender==1 / 분류: 없음 / 사용 변수: empins_parentleave_yn2, gender, indwgt',
    True, rate(sex == 1, pl2))
add('F10', 3, '대상: 육아휴직급여(사후지급금 제외) 12월 기준 수급 empins_parentleave_yn2==1 인 남성 가중 인원 / 분류: 없음 / 사용 변수: empins_parentleave_yn2, gender, indwgt',
    False, count(pl2 & (sex == 1)))

# ================= G =================
add('G01', 1, '대상: 65세 이상 / 분자: 노인맞춤돌봄서비스 연간 이용 oldcare_yn1==1 / 분류: 시도 / 사용 변수: age, oldcare_yn1, sido, indwgt',
    True, rate(oc, age >= 65, G_SIDO), note='붙은 코드는 분모에 65세 이상 조건(where)이 빠져 있음')
add('G02', 1, '대상: 종합장애정도 심한 등록장애인(dis_yn==1, dis_grade_1==1) / 분자: 장애인활동지원 연간 이용(자격 기준) disvou_act_yn1==1 / 분류: 성 / 사용 변수: dis_yn, dis_grade_1, disvou_act_yn1, gender, indwgt',
    True, rate(eq1('disvou_act_yn1'), sev, G_SEX), note='붙은 코드는 분모가 등록장애인 전체임(dis_grade_1==1 조건 누락)')
add('G03', 1, '대상: 국민취업지원제도 12월 31일 기준 참여 kua_yn2==1 가중 인원 / 분류: 성 / 사용 변수: kua_yn2, gender, indwgt',
    False, count(eq1('kua_yn2'), G_SEX), note='붙은 코드는 연간 참여(kua_yn1)를 씀')
add('G04', 1, '대상: 전체 가구(가구주 행, hhwgt) / 대상 변수: 가구 가처분소득 h_dinc 가중 평균(원) / 분류: 가구원수 4구간 / 사용 변수: h_dinc, hnum, head, hhwgt',
    False, mean('h_dinc', ALL, G_HS4, unit='hh'), note='붙은 코드는 가구주 개인의 p_dinc를 평균함')
add('G05', 1, '대상: 만 7~18세(7<=age<=18) 중 교육급여 수급권 연간 보유 nbls_edu_yn1==1 가중 인원 / 분류: 없음 / 사용 변수: age, nbls_edu_yn1, indwgt',
    False, count(edu & a718), note='붙은 코드는 초과·미만(7세, 18세 제외)으로 되어 있음')
li2 = eq1('nbls_live_yn2')
add('G06', 1, '대상: 12월 기준 생계급여(nbls_live_yn2==1) 또는 주거급여 임차급여(nbls_house_yn2==1) 수급 가중 인원 / 분류: 연령대 3구간 / 사용 변수: nbls_live_yn2, nbls_house_yn2, age, indwgt',
    False, count(li2 | ho2, G_AGE3), note='붙은 코드는 and(둘 다 수급)로 되어 있음')
add('G07', 1, '대상: 가구주(head==1) 연령 65세 이상인 가구 수(hhwgt) / 분류: 가구원수 4구간 / 사용 변수: age, head, hnum, hhwgt',
    False, count(age >= 65, G_HS4, unit='hh'), note="붙은 코드는 개인 단위 인원임(unit='가구' 누락)")
add('G08', 1, '대상: 65세 이상 / 분자: 장기요양 연간 수급 ltcare_bn_yn==1 / 분류: 연령 3구간(65~74세, 75~84세, 85세 이상) / 사용 변수: age, ltcare_bn_yn, indwgt',
    True, rate(lt, age >= 65, G_OLD3), note='붙은 코드의 구간 경계(70, 80)가 질문과 다름')
ow = eq1('oldwork_type1_yn1')
add('G09', 1, '대상: 노인일자리 공익활동 연간 참여 oldwork_type1_yn1==1 / 대상 변수: 활동비 oldwork_type1_amt 가중 합계(원) / 분류: 성 / 사용 변수: oldwork_type1_yn1, oldwork_type1_amt, gender, indwgt',
    False, total('oldwork_type1_amt', ow, G_SEX), note='붙은 코드는 평균(mean)을 구함')
ve = eq1('vocaedu_yn')
add('G10', 1, '대상: 국민내일배움카드 연간 정부지원 vocaedu_yn==1 / 대상 변수: 정부지원금 vocaedu_amt 가중 중위수(원) / 분류: 성 / 사용 변수: vocaedu_yn, vocaedu_amt, gender, indwgt',
    False, quant('vocaedu_amt', 0.5, ve, G_SEX), note='붙은 코드의 vocaedu_yn1은 없는 변수(vocaedu_yn)')
add('G11', 1, '대상: 65세 이상 / 분자: 본인부담상한제 지원 nhi_ceiling_subsidy_yn==1(결측·0은 미해당) / 분류: 소득 5분위(전체 인구 기준 경계) / 사용 변수: age, nhi_ceiling_subsidy_yn, p_dinc, hnum, hid, indwgt',
    True, rate(eq1('nhi_ceiling_subsidy_yn'), age >= 65, G_INC5))
add('G12', 1, '대상: 1인 가구(hnum==1, 가구주 행, hhwgt) / 분자: 가구 재산 h_prop<1억원 / 분류: 시도 / 사용 변수: h_prop, hnum, sido, head, hhwgt',
    True, rate(hprop < 1e8, hnum == 1, G_SIDO, unit='hh'))

# ================= E =================
add('E17', 1, '대상: 주장애유형 정신(dis_type_1==11) 등록장애인(dis_yn==1) / 분자: 장애인연금 12월 수급 disp_yn2==1 / 분류: 없음 / 사용 변수: dis_yn, dis_type_1, disp_yn2, indwgt',
    True, rate(eq1('disp_yn2'), dis & m(df['dis_type_1'] == 11)))
add('E18', 1, '대상: 근로소득 p_labinc>0 / 대상 변수: p_labinc 가중 90% 분위수(원) / 분류: 없음 / 사용 변수: p_labinc, indwgt',
    False, quant('p_labinc', 0.9, m(df['p_labinc'] > 0)), ambiguous=True,
    note='「근로소득」에 해당하는 변수가 둘임. 0원이 있는 개인 일차소득의 근로소득 p_labinc를 해석 1로 봄(「0원 초과」 조건과 맞음). 연말정산 근로소득 합계금액 labinc_sum_taxy는 대상자 집합은 같으나 금액이 조금 달라 해석 2로 둠')
add('E18', 1, '대상: 연말정산 근로소득 합계금액 labinc_sum_taxy>0 / 대상 변수: labinc_sum_taxy 가중 90% 분위수(원) / 분류: 없음 / 사용 변수: labinc_sum_taxy, indwgt',
    False, quant('labinc_sum_taxy', 0.9, m(df['labinc_sum_taxy'] > 0)), reading_no=2, ambiguous=True,
    note='해석 2: 근로소득을 연말정산 근로소득DB의 합계금액으로 본 경우')
add('E19', 1, '대상: 생계급여 연간 수급 nbls_live_yn1==1 / 대상 변수: nbls_live_amt 가중 평균(원, 개인 단위) / 분류: 가구원수 4구간(hnum) / 사용 변수: nbls_live_yn1, nbls_live_amt, hnum, indwgt',
    False, mean('nbls_live_amt', eq1('nbls_live_yn1'), G_HS4))
add('E20', 1, '대상: 65세 이상 / 분자: 기초연금 연간 수급 bp_yn1==1 / 분류: 시도(17개) / 사용 변수: age, bp_yn1, sido, indwgt',
    True, rate(eq1('bp_yn1'), age >= 65, G_SIDO))
add('E21', 1, '대상: 등록장애인(dis_yn==1)이면서 생계급여 12월 수급 nbls_live_yn2==1 가중 인원 / 분류: 없음 / 사용 변수: dis_yn, nbls_live_yn2, indwgt',
    False, count(dis & li2))
add('E21', 2, '대상: 등록장애인(dis_yn==1)이면서 생계급여 12월 미수급(nbls_live_yn2가 1이 아님: 결측 또는 0) 가중 인원 / 분류: 없음 / 사용 변수: dis_yn, nbls_live_yn2, indwgt',
    False, count(dis & ~li2))
add('E22', 1, '대상: 노인맞춤돌봄서비스 연간 이용 oldcare_yn1==1(65세 이상) 가중 인원 / 분류: 성 × 연령 3구간(65~74세, 75~84세, 85세 이상) / 사용 변수: oldcare_yn1, gender, age, indwgt',
    False, count(oc, cross(G_SEX, G_OLD3)))
add('E23', 1, '대상: 제주(sido==17) 거주, 주거급여 임차급여 12월 수급 nbls_house_yn2==1 가중 인원 / 분류: 없음 / 사용 변수: sido, nbls_house_yn2, indwgt',
    False, count((sido == 17) & ho2))
mt = df['nbls_medi_type']
G_MT = [('1종', m(mt == 1)), ('2종', m(mt == 2))]
add('E24', 1, '대상: 의료급여 12월 31일 기준 수급권자 nbls_medi_yn2==1 / 구성비: 의료급여 종별 nbls_medi_type(1종, 2종) / 사용 변수: nbls_medi_yn2, nbls_medi_type, indwgt',
    True, share(G_MT, eq1('nbls_medi_yn2')), note='구성비의 n은 분모(종별 값이 있는 수급권자 전체), n_num은 해당 종별 관측 수')

with open(OUT, 'w', encoding='utf-8') as f:
    for r_ in ROWS:
        f.write(json.dumps(r_, ensure_ascii=False) + '\n')

# ---------- 점검용 출력(집계값만) ----------
if __name__ == '__main__':
    print('rows', len(ROWS), 'ids', len({r_['id'] for r_ in ROWS}))
    print('quintile bounds', QB, 'median', MED, 'poverty line', 0.5 * MED)
    for r_ in ROWS:
        cs = r_['cells']
        s = '; '.join(f"{'/'.join(c['labels']) or '-'}={c['value'] if c['value'] is None else round(c['value'], 3)}(n={c['n']}" +
                      (f",num={c['n_num']}" if 'n_num' in c else '') + ')' for c in cs)
        print(r_['id'], r_['turn'], r_['reading_no'], '|', s)
