# -*- coding: utf-8 -*-
"""독립 검산(check_1): 질문 문장만 보고 분석 자료에서 직접 계산.
- 개인 단위: indwgt 가중 / 가구 단위: head == 1 행에 hhwgt 가중
- 여부 변수는 == 1 판별(결측·0은 비해당), 평균·합계·분위수는 값이 있는 행만
- 개인 단위 행은 출력하지 않음(집계값만 기록)
"""
import json
import numpy as np
import pandas as pd

DATA = '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
OUT = '/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r2/truth/check_1.jsonl'

df = pd.read_parquet(DATA)
W = df['indwgt'].to_numpy(float)
HW = df['hhwgt'].to_numpy(float)
age = df['age'].to_numpy()
gender = df['gender'].to_numpy()
sido = df['sido'].to_numpy()
hnum = df['hnum'].to_numpy()
HEAD = (df['head'] == 1).to_numpy()

SIDO = {1: '서울', 2: '부산', 3: '대구', 4: '인천', 5: '광주', 6: '대전', 7: '울산', 8: '세종', 9: '경기',
        10: '강원', 11: '충북', 12: '충남', 13: '전북', 14: '전남', 15: '경북', 16: '경남', 17: '제주'}
SEX = {1: '남', 2: '여'}
CAPITAL = np.isin(sido, [1, 4, 9])


# ---------- 공통 도구 ----------
def is1(col):
    """여부 변수: 1이면 참, 결측·0은 거짓(결측 허용 정수형 포함)."""
    return df[col].eq(1).fillna(False).to_numpy(bool)


def has(col):
    """값이 있는 행."""
    return df[col].notna().to_numpy(bool)


def num(col):
    return pd.to_numeric(df[col], errors='coerce').astype('float64').to_numpy()


def gt0(col):
    v = num(col)
    return np.nan_to_num(v, nan=0.0) > 0


def wquantile(x, w, q):
    """가중 분위수: 오름차순 정렬 후 가중치 누적합이 전체의 q배에 처음 이르는 값."""
    x = np.asarray(x, float)
    w = np.asarray(w, float)
    if len(x) == 0:
        return None
    o = np.argsort(x, kind='mergesort')
    xs, ws = x[o], w[o]
    c = np.cumsum(ws)
    i = int(np.searchsorted(c, q * c[-1], side='left'))
    return float(xs[min(i, len(xs) - 1)])


def c_count(mask, w=W):
    n = int(mask.sum())
    return (float(w[mask].sum()) if n else None), n


def c_rate(den, numr, w=W):
    n = int(den.sum())
    k = int((den & numr).sum())
    v = float(100.0 * w[den & numr].sum() / w[den].sum()) if n else None
    return v, n, k


def c_mean(mask, x, w=W):
    m = mask & ~np.isnan(x)
    n = int(m.sum())
    return (float((x[m] * w[m]).sum() / w[m].sum()) if n else None), n


def c_sum(mask, x, w=W):
    m = mask & ~np.isnan(x)
    n = int(m.sum())
    return (float((x[m] * w[m]).sum()) if n else None), n


def c_q(mask, x, q, w=W):
    m = mask & ~np.isnan(x)
    n = int(m.sum())
    return (wquantile(x[m], w[m], q) if n else None), n


def cell(labels, value, n, n_num=None):
    d = {'labels': list(labels), 'value': value, 'n': n}
    if n_num is not None:
        d['n_num'] = n_num
    return d


ROWS = []


def emit(qid, reading, pct, cells, reading_no=1, ambiguous=False, note=''):
    ROWS.append({'id': qid, 'turn': 1, 'reading_no': reading_no, 'reading': reading, 'pct': pct,
                 'cells': cells, 'ambiguous': ambiguous, 'note': note})


# ---------- 균등화 가처분소득, 소득 5분위, 상대 빈곤 ----------
h_sum = df.groupby('hid')['p_dinc'].transform('sum').to_numpy(float)   # 가구원 p_dinc의 가구 합계
EQ = h_sum / np.sqrt(hnum)
MED = wquantile(EQ, W, 0.5)
POOR = EQ < 0.5 * MED
QB = [wquantile(EQ, W, q) for q in (0.2, 0.4, 0.6, 0.8)]
QUINT = 1 + sum((EQ >= b).astype(int) for b in QB)      # 경계값 이상이면 위 분위

# ====================== 질문별 계산 ======================

# A001 65세 이상 중 2022.12 기초연금 수급 비율, 시도별
den = age >= 65
emit('A001', '대상: 65세 이상 인구 / 분자: 2022년 12월 기준 기초연금 수급(bp_yn2 == 1) / 분류: 시도 / 사용 변수: age, bp_yn2, sido, indwgt',
     True, [cell([SIDO[s]], *c_rate(den & (sido == s), is1('bp_yn2'))) for s in SIDO])

# A002 65세 이상 중 2022년 고혈압 입원 비율
emit('A002', '대상: 65세 이상 인구 전체 / 분자: 고혈압 입원 여부(nhi_highbp_yn == 1) / 분류: 없음 / 사용 변수: age, nhi_highbp_yn, indwgt',
     True, [cell([], *c_rate(age >= 65, is1('nhi_highbp_yn')))])

# A003 보육료 지원 아동 수, 0~2세 / 3세 이상 (기준 시점 미기재)
grp = [('0~2세', age <= 2), ('3세 이상', age >= 3)]
note3 = '기준 시점이 적히지 않음: 2022년 연간 한 번이라도 지원(childcare_yn1)과 2022년 12월 기준 지원(childcare_yn2) 두 가지로 읽힘'
emit('A003', '대상: 2022년 중 한 번이라도 보육료 지원을 받은 아동(childcare_yn1 == 1) / 대상 변수: 가중 인원 / 분류: 연령 0~2세, 3세 이상 / 사용 변수: childcare_yn1, age, indwgt',
     False, [cell([l], *c_count(is1('childcare_yn1') & m)) for l, m in grp], 1, True, note3)
emit('A003', '대상: 2022년 12월 기준 보육료 지원 중인 아동(childcare_yn2 == 1) / 대상 변수: 가중 인원 / 분류: 연령 0~2세, 3세 이상 / 사용 변수: childcare_yn2, age, indwgt',
     False, [cell([l], *c_count(is1('childcare_yn2') & m)) for l, m in grp], 2, True, note3)

# A004 가구주 연령 구간별 임차 보증금 보유 가구 비율(가구 단위)
dep_h = gt0('h_ee_deposit_amt_ptot')
grp = [('40세 미만', age < 40), ('40~59세', (age >= 40) & (age <= 59)), ('60세 이상', age >= 60)]
emit('A004', '대상: 전체 가구(가구주 행) / 분자: 가구원 임차 보증금 합계 > 0(h_ee_deposit_amt_ptot > 0) / 분류: 가구주 연령 40세 미만, 40~59세, 60세 이상 / 사용 변수: head, age, h_ee_deposit_amt_ptot, hhwgt',
     True, [cell([l], *c_rate(HEAD & m, dep_h, HW)) for l, m in grp])

# A005 연령 구간별 응급실 재원일수 1일 이상 비율(분모: 구간 전체 인구)
er = np.nan_to_num(num('nhi_in_emergency_dur'), nan=0.0) >= 1
grp = [('40세 미만', age < 40), ('40~64세', (age >= 40) & (age <= 64)), ('65~74세', (age >= 65) & (age <= 74)), ('75세 이상', age >= 75)]
emit('A005', '대상: 전체 인구 / 분자: 응급실 재원일수 1일 이상(nhi_in_emergency_dur >= 1) / 분류: 연령 40세 미만, 40~64세, 65~74세, 75세 이상 / 사용 변수: age, nhi_in_emergency_dur, indwgt',
     True, [cell([l], *c_rate(m, er)) for l, m in grp])

# A006 국민취업지원제도 연간 참여자 수, 참여유형 x 성
kt = num('kua_type')
emit('A006', '대상: 2022년 연간 국민취업지원제도 참여자(kua_yn1 == 1) / 대상 변수: 가중 인원 / 분류: 참여유형(kua_type) x 성 / 사용 변수: kua_yn1, kua_type, gender, indwgt',
     False, [cell([f'{t}유형', SEX[g]], *c_count(is1('kua_yn1') & (kt == t) & (gender == g))) for t in (1, 2) for g in (1, 2)])

# A007 장애수당 연간 수급자(18세 이상) 1인당 평균 연간 수급액, 18~64 / 65+
x = num('disp_bn_amt')
base = is1('disp_bn_yn1') & (age >= 18)
grp = [('18~64세', (age >= 18) & (age <= 64)), ('65세 이상', age >= 65)]
emit('A007', '대상: 2022년 중 장애수당을 한 번이라도 받은 18세 이상(disp_bn_yn1 == 1) / 대상 변수: 장애수당 연간 급여액(disp_bn_amt) 평균 / 분류: 연령 18~64세, 65세 이상 / 사용 변수: disp_bn_yn1, disp_bn_amt, age, indwgt',
     False, [cell([l], *c_mean(base & m, x)) for l, m in grp])

# A008 방문요양 이용자의 평균 이용일수, 등급 묶음별
x = num('ltcare_visit_freq')
gr = num('ltcare_grade')
base = is1('ltcare_visit_yn')
grp = [('1~2등급', np.isin(gr, [1, 2])), ('3등급', gr == 3), ('4등급', gr == 4), ('5등급', gr == 5)]
emit('A008', '대상: 2022년 장기요양 방문요양 이용자(ltcare_visit_yn == 1) / 대상 변수: 방문요양 이용일수(ltcare_visit_freq) 평균 / 분류: 장기요양 등급(ltcare_grade) 1~2등급, 3등급, 4등급, 5등급 / 사용 변수: ltcare_visit_yn, ltcare_visit_freq, ltcare_grade, indwgt',
     False, [cell([l], *c_mean(base & m, x)) for l, m in grp])

# A009 일용근로소득 보유자의 연간 일용근로소득 1사분위수, 성별 (변수 두 가지)
note9 = '일용근로소득에 해당하는 변수가 둘임: 개인 일차소득의 일용소득(p_dainc)과 일용소득 자료의 총지급금액(dainc_sum). 보유자 집단은 같으나 금액이 조금 다름'
x1 = num('p_dainc')
emit('A009', '대상: 일용근로소득이 있는 사람(p_dainc > 0) / 대상 변수: 연간 일용소득(p_dainc) 가중 25% 분위수 / 분류: 성 / 사용 변수: p_dainc, gender, indwgt',
     False, [cell([SEX[g]], *c_q((x1 > 0) & (gender == g), x1, 0.25)) for g in (1, 2)], 1, True, note9)
x2 = num('dainc_sum')
emit('A009', '대상: 일용근로소득이 있는 사람(dainc_sum 값 있음, > 0) / 대상 변수: 일용소득 총지급금액(dainc_sum) 가중 25% 분위수 / 분류: 성 / 사용 변수: dainc_sum, gender, indwgt',
     False, [cell([SEX[g]], *c_q((np.nan_to_num(x2, nan=0.0) > 0) & (gender == g), x2, 0.25)) for g in (1, 2)], 2, True, note9)

# A010 65세 이상, 기초연금 연간 수급 여부별 상대 빈곤율
bp1 = is1('bp_yn1')
emit('A010', '대상: 65세 이상 인구 / 분자: 균등화 가처분소득이 전체 인구 중위값의 50% 미만 / 분류: 2022년 중 기초연금 수급 여부(bp_yn1 == 1 / 그 밖) / 사용 변수: age, bp_yn1, p_dinc, hnum, hid, indwgt',
     True, [cell(['기초연금 수급'], *c_rate((age >= 65) & bp1, POOR)), cell(['기초연금 비수급'], *c_rate((age >= 65) & ~bp1, POOR))])

# A011 자활근로(기초) 연간 참여자 중 10월 말 참여 비율
emit('A011', '대상: 2022년 자활근로(기초) 참여자(self_yn1 == 1) / 분자: 2022년 10월 31일 기준 참여(self_yn2 == 1) / 분류: 없음 / 사용 변수: self_yn1, self_yn2, indwgt',
     True, [cell([], *c_rate(is1('self_yn1'), is1('self_yn2')))])

# A012 부산·울산·경남 상급종합병원 입원자의 평균 재원일수, 시도별
x = num('nhi_in_tehospital_dur')
base = np.nan_to_num(x, nan=0.0) > 0
emit('A012', '대상: 부산·울산·경남 거주자 중 2022년 상급종합병원 입원자(nhi_in_tehospital_dur > 0) / 대상 변수: 상급종합병원 재원일수(nhi_in_tehospital_dur) 평균 / 분류: 시도(부산, 울산, 경남) / 사용 변수: sido, nhi_in_tehospital_dur, indwgt',
     False, [cell([SIDO[s]], *c_mean(base & (sido == s), x)) for s in (2, 7, 16)])

# A013 6~17세, 방과후학교 자유수강권 지원 비율, 빈곤 여부별
den = (age >= 6) & (age <= 17)
emit('A013', '대상: 6~17세 인구 / 분자: 2022년 방과후학교 자유수강권 지원(pubedu_aftsch_yn == 1) / 분류: 상대 빈곤 여부(전체 인구 균등화 가처분소득 중위값의 50% 미만) / 사용 변수: age, pubedu_aftsch_yn, p_dinc, hnum, hid, indwgt',
     True, [cell(['빈곤'], *c_rate(den & POOR, is1('pubedu_aftsch_yn'))), cell(['비빈곤'], *c_rate(den & ~POOR, is1('pubedu_aftsch_yn')))])

# A014 2022.12.31 기준 직역연금 가입자 수(3종)
emit('A014', '대상: 2022년 12월 31일 기준 직역연금 가입자(각 _yn2 == 1) / 대상 변수: 가중 인원 / 분류: 연금 종류(공무원연금 govp_yn2, 사립학교교직원연금 privschp_yn2, 군인연금 milp_yn2) / 사용 변수: govp_yn2, privschp_yn2, milp_yn2, indwgt',
     False, [cell(['공무원연금'], *c_count(is1('govp_yn2'))), cell(['사립학교교직원연금'], *c_count(is1('privschp_yn2'))), cell(['군인연금'], *c_count(is1('milp_yn2')))])

# A015 출산전후휴가급여 연간 수급자의 평균 수급일수
emit('A015', '대상: 2022년 출산전후휴가급여 수급자(empins_matleave_yn1 == 1) / 대상 변수: 수급기간(일)(empins_matleave_dur) 평균 / 분류: 없음 / 사용 변수: empins_matleave_yn1, empins_matleave_dur, indwgt',
     False, [cell([], *c_mean(is1('empins_matleave_yn1'), num('empins_matleave_dur')))])

# A016 수도권·가구주 39세 이하·임차 보증금 보유 가구의 가구당 평균 임차 보증금, 시도별(가구 단위)
x = num('h_ee_deposit_amt_ptot')
base = HEAD & (age <= 39) & (x > 0)
emit('A016', '대상: 서울·인천·경기 거주, 가구주 39세 이하, 가구원 임차 보증금 합계 > 0인 가구(가구주 행) / 대상 변수: 가구 임차 보증금 합계(h_ee_deposit_amt_ptot) 평균 / 분류: 시도(서울, 인천, 경기) / 사용 변수: head, age, sido, h_ee_deposit_amt_ptot, hhwgt',
     False, [cell([SIDO[s]], *c_mean(base & (sido == s), x, HW)) for s in (1, 4, 9)])

# A017 장애인연금 대상 18~64세 등록장애인 1인 가구원 중 장애인연금 연간 수급 비율
den = is1('dis_yn') & is1('dis_disp_yn') & (age >= 18) & (age <= 64) & (hnum == 1)
emit('A017', '대상: 장애인연금법상 중증장애인(dis_disp_yn == 1)인 18~64세 등록장애인(dis_yn == 1) 중 1인 가구(hnum == 1) / 분자: 2022년 장애인연금 수급(disp_yn1 == 1) / 분류: 없음 / 사용 변수: dis_yn, dis_disp_yn, age, hnum, disp_yn1, indwgt',
     True, [cell([], *c_rate(den, is1('disp_yn1')))])

# A018 총연금수령액 있는 65세 이상의 연간 총연금수령액 중위수, 성 x 연령
x = num('pubpen_inc')
base = (np.nan_to_num(x, nan=0.0) > 0) & (age >= 65)
agrp = [('65~74세', (age >= 65) & (age <= 74)), ('75세 이상', age >= 75)]
emit('A018', '대상: 공적연금 총연금수령액이 있는(pubpen_inc > 0) 65세 이상 / 대상 변수: 총연금수령액(pubpen_inc) 가중 중위수 / 분류: 성 x 연령(65~74세, 75세 이상) / 사용 변수: pubpen_inc, age, gender, indwgt',
     False, [cell([SEX[g], l], *c_q(base & (gender == g) & m, x, 0.5)) for g in (1, 2) for l, m in agrp])

# A019 실업급여 수급기간 연기 신고처리자의 연기사유 구성비
REASON = {1: '임신·출산·육아', 2: '본인의 질병·부상', 5: '병역법에 따른 의무복무', 6: '범죄혐의로 인한 구속 또는 형의 집행', 8: '기타'}
rs = num('unempbn_bnextended_reason')
den = is1('unempbn_bnextended_yn')
emit('A019', '대상: 2022년 실업급여 수급기간 연기 신고처리자(unempbn_bnextended_yn == 1) / 대상 변수: 연기사유(unempbn_bnextended_reason) 구성비 / 분류: 연기사유 코드값 / 사용 변수: unempbn_bnextended_yn, unempbn_bnextended_reason, indwgt',
     True, [cell([REASON[k]], *c_rate(den, rs == k)) for k in REASON])

# A020 0~5세 중 2022.12 양육수당 수급 비율, 소득 5분위별
den = age <= 5
emit('A020', '대상: 0~5세 인구 / 분자: 2022년 12월 양육수당 수급(carebn_yn2 == 1) / 분류: 소득 5분위(전체 인구 균등화 가처분소득 기준) / 사용 변수: age, carebn_yn2, p_dinc, hnum, hid, indwgt',
     True, [cell([f'{k}분위'], *c_rate(den & (QUINT == k), is1('carebn_yn2'))) for k in range(1, 6)])

# A021 서울 75세 이상 여성 종합병원 외래 이용자의 1인당 평균 공단부담금
x = num('nhi_out_gehospital_subsidy')
base = (sido == 1) & (age >= 75) & (gender == 2) & has('nhi_out_gehospital_dur')
emit('A021', '대상: 서울 거주 75세 이상 여성 중 2022년 종합병원 외래 이용자(nhi_out_gehospital_dur 값 있음) / 대상 변수: 종합병원 외래 공단부담금(nhi_out_gehospital_subsidy) 평균 / 분류: 없음 / 사용 변수: sido, age, gender, nhi_out_gehospital_dur, nhi_out_gehospital_subsidy, indwgt',
     False, [cell([], *c_mean(base, x))])

# A022 건강보험 가입 구분별 상대 빈곤율
nt = df['nhi_type'].to_numpy()
grp = [('지역가입', np.isin(nt, [1, 2])), ('직장가입', np.isin(nt, [5, 6])), ('의료급여', np.isin(nt, [7, 8]))]
emit('A022', '대상: 전체 인구 / 분자: 균등화 가처분소득이 전체 인구 중위값의 50% 미만 / 분류: 건강보험 가입 구분(nhi_type 1·2 지역가입, 5·6 직장가입, 7·8 의료급여) / 사용 변수: nhi_type, p_dinc, hnum, hid, indwgt',
     True, [cell([l], *c_rate(m, POOR)) for l, m in grp])

# A023 긴급복지 생계지원 연간 수급자 중 12월 수급 비율
emit('A023', '대상: 2022년 긴급복지 생계지원 수급자(aid_live_yn1 == 1) / 분자: 2022년 12월 기준 수급(aid_live_yn2 == 1) / 분류: 없음 / 사용 변수: aid_live_yn1, aid_live_yn2, indwgt',
     True, [cell([], *c_rate(is1('aid_live_yn1'), is1('aid_live_yn2')))])

# A024 군인연금 연간 가입자의 본인부담 보험료 납부액 평균, 연령 구간별
x = num('milp_premium_amt')
grp = [('30세 미만', age < 30), ('30~39세', (age >= 30) & (age <= 39)), ('40세 이상', age >= 40)]
emit('A024', '대상: 2022년 중 군인연금 가입자(milp_yn1 == 1) / 대상 변수: 군인연금 보험료 납부액(milp_premium_amt, 본인부담) 평균 / 분류: 연령 30세 미만, 30~39세, 40세 이상 / 사용 변수: milp_yn1, milp_premium_amt, age, indwgt',
     False, [cell([l], *c_mean(is1('milp_yn1') & m, x)) for l, m in grp])

# A025 기초연금 수급자의 수급유형 구성비, 성별 (기준 시점 미기재)
TYPE = {1: '단독', 2: '부부 1인 수급', 3: '부부 2인 수급'}
bt = num('bp_type')
note25 = '기준 시점이 적히지 않음: 수급유형(bp_type)이 12월 기준 수급자의 유형이므로 12월 수급자(bp_yn2)로 읽는 해석과 2022년 연간 수급자(bp_yn1)로 읽는 해석이 있음'
emit('A025', '대상: 2022년 12월 기준 기초연금 수급자(bp_yn2 == 1) / 대상 변수: 수급유형(bp_type) 구성비(성별 안에서 합 100%) / 분류: 성 x 수급유형 / 사용 변수: bp_yn2, bp_type, gender, indwgt',
     True, [cell([SEX[g], TYPE[t]], *c_rate(is1('bp_yn2') & (gender == g), bt == t)) for g in (1, 2) for t in TYPE], 1, True, note25)
emit('A025', '대상: 2022년 중 한 번이라도 기초연금을 수급한 사람(bp_yn1 == 1) / 대상 변수: 수급유형(bp_type) 구성비(성별 안에서 합 100%) / 분류: 성 x 수급유형 / 사용 변수: bp_yn1, bp_type, gender, indwgt',
     True, [cell([SEX[g], TYPE[t]], *c_rate(is1('bp_yn1') & (gender == g), bt == t)) for g in (1, 2) for t in TYPE], 2, True, note25)

# A026 등록장애인 / 비장애인의 상급종합병원 외래 이용률
use = np.nan_to_num(num('nhi_out_tehospital_dur'), nan=0.0) >= 1
dis = is1('dis_yn')
emit('A026', '대상: 전체 인구 / 분자: 2022년 상급종합병원 외래 내원일수 1일 이상(nhi_out_tehospital_dur >= 1) / 분류: 등록장애인(dis_yn == 1) / 비장애인(그 밖) / 사용 변수: dis_yn, nhi_out_tehospital_dur, indwgt',
     True, [cell(['등록장애인'], *c_rate(dis, use)), cell(['비장애인'], *c_rate(~dis, use))])

# A027 방과후학교 자유수강권 지원액 합계, 권역별
x = num('pubedu_aftsch_amt')
grp = [('수도권', CAPITAL), ('영남권', np.isin(sido, [2, 3, 7, 15, 16])), ('그 밖의 지역', ~CAPITAL & ~np.isin(sido, [2, 3, 7, 15, 16]))]
emit('A027', '대상: 2022년 방과후학교 자유수강권 지원액이 있는 사람 / 대상 변수: 지원액(pubedu_aftsch_amt) 가중 합계 / 분류: 수도권(서울·인천·경기), 영남권(부산·대구·울산·경북·경남), 그 밖의 지역 / 사용 변수: pubedu_aftsch_amt, sido, indwgt',
     False, [cell([l], *c_sum(m, x)) for l, m in grp])

# A028 65세 이상 1인 생계급여 수급 가구(12월) 중 에너지바우처 이용 가구 비율(가구 단위)
den = HEAD & (hnum == 1) & (age >= 65) & is1('nbls_live_yn2')
emit('A028', '대상: 가구주 65세 이상 1인 가구 중 2022년 12월 기준 생계급여 수급 가구(가구주 행, nbls_live_yn2 == 1) / 분자: 에너지바우처 이용(evou_yn == 1) / 분류: 없음 / 사용 변수: head, hnum, age, nbls_live_yn2, evou_yn, hhwgt',
     True, [cell([], *c_rate(den, is1('evou_yn'), HW))])

# A029 65세 이상 인구 대비 노인장기요양 연간 수급자 비율, 연령 x 성
agrp = [('65~74세', (age >= 65) & (age <= 74)), ('75~84세', (age >= 75) & (age <= 84)), ('85세 이상', age >= 85)]
emit('A029', '대상: 65세 이상 인구 / 분자: 2022년 노인장기요양 수급(ltcare_bn_yn == 1) / 분류: 연령(65~74세, 75~84세, 85세 이상) x 성 / 사용 변수: age, gender, ltcare_bn_yn, indwgt',
     True, [cell([l, SEX[g]], *c_rate(m & (gender == g), is1('ltcare_bn_yn'))) for l, m in agrp for g in (1, 2)])

# A030 30세 이상 금융소득 원천징수세액 보유자의 평균 세액, 개인 재산 구간별
x = num('fainc_tax')
pp = num('p_prop')
base = (age >= 30) & (np.nan_to_num(x, nan=0.0) > 0)
grp = [('1억원 미만', pp < 1e8), ('1억원 이상 5억원 미만', (pp >= 1e8) & (pp < 5e8)), ('5억원 이상', pp >= 5e8)]
emit('A030', '대상: 30세 이상이며 금융소득 원천징수세액이 있는 사람(fainc_tax > 0) / 대상 변수: 금융소득 원천징수세액(fainc_tax) 평균 / 분류: 개인 재산(p_prop) 1억원 미만, 1억원 이상 5억원 미만, 5억원 이상 / 사용 변수: age, fainc_tax, p_prop, indwgt',
     False, [cell([l], *c_mean(base & m, x)) for l, m in grp])

# A031 수도권 18~34세 고용보험 연간 가입자 중 구직급여 수급 비율, 성별
den = CAPITAL & (age >= 18) & (age <= 34) & is1('empins_yn1')
emit('A031', '대상: 서울·인천·경기 거주 18~34세 중 2022년 고용보험 가입 이력자(empins_yn1 == 1) / 분자: 2022년 구직급여 수급(unempbn_jobseekbn_yn == 1) / 분류: 성 / 사용 변수: sido, age, empins_yn1, unempbn_jobseekbn_yn, gender, indwgt',
     True, [cell([SEX[g]], *c_rate(den & (gender == g), is1('unempbn_jobseekbn_yn'))) for g in (1, 2)])

# A032 육아휴직급여 연간 수급자 중 남성 비율
emit('A032', '대상: 2022년 육아휴직급여 수급자(empins_parentleave_yn1 == 1, 사후지급금 제외) / 분자: 남성(gender == 1) / 분류: 없음 / 사용 변수: empins_parentleave_yn1, gender, indwgt',
     True, [cell([], *c_rate(is1('empins_parentleave_yn1'), gender == 1))])

# A033 가구 재산 중위수, 가구원수 구간별(가구 단위, 0원 포함)
x = num('h_prop')
grp = [('1인', hnum == 1), ('2인', hnum == 2), ('3인', hnum == 3), ('4인 이상', hnum >= 4)]
emit('A033', '대상: 전체 가구(가구주 행, 재산 0원 포함) / 대상 변수: 가구 재산(h_prop) 가중 중위수 / 분류: 가구원수 1인, 2인, 3인, 4인 이상 / 사용 변수: head, hnum, h_prop, hhwgt',
     False, [cell([l], *c_q(HEAD & m, x, 0.5, HW)) for l, m in grp])

# A034 65세 이상 1인 가구 등록장애인 수
emit('A034', '대상: 65세 이상이며 1인 가구(hnum == 1)인 등록장애인(dis_yn == 1) / 대상 변수: 가중 인원 / 분류: 없음 / 사용 변수: age, hnum, dis_yn, indwgt',
     False, [cell([], *c_count((age >= 65) & (hnum == 1) & is1('dis_yn')))])

# A035 종합병원 입원 요양급여비용 총액 합계, 연령 3구간
x = num('nhi_in_gehospital_amt')
grp = [('0~17세', age <= 17), ('18~64세', (age >= 18) & (age <= 64)), ('65세 이상', age >= 65)]
emit('A035', '대상: 2022년 종합병원 입원 요양급여비용이 있는 사람 / 대상 변수: 종합병원 입원 요양급여비용 총액(nhi_in_gehospital_amt) 가중 합계 / 분류: 연령 0~17세, 18~64세, 65세 이상 / 사용 변수: nhi_in_gehospital_amt, age, indwgt',
     False, [cell([l], *c_sum(m, x)) for l, m in grp])

# A036 75세 이상 1인 가구원 중 12월 노인맞춤돌봄서비스 이용 비율, 수도권 / 비수도권
den = (hnum == 1) & (age >= 75)
emit('A036', '대상: 1인 가구(hnum == 1)의 75세 이상 / 분자: 2022년 12월 기준 노인맞춤돌봄서비스 이용(oldcare_yn2 == 1) / 분류: 수도권(서울·인천·경기) / 비수도권 / 사용 변수: hnum, age, oldcare_yn2, sido, indwgt',
     True, [cell(['수도권'], *c_rate(den & CAPITAL, is1('oldcare_yn2'))), cell(['비수도권'], *c_rate(den & ~CAPITAL, is1('oldcare_yn2')))])

# A037 노인일자리 사회서비스형 연간 참여자 중 중도포기 비율
emit('A037', '대상: 2022년 노인일자리 사회서비스형 참여자(oldwork_type2_yn1 == 1) / 분자: 중도포기(oldwork_type2_end_yn == 1) / 분류: 없음 / 사용 변수: oldwork_type2_yn1, oldwork_type2_end_yn, indwgt',
     True, [cell([], *c_rate(is1('oldwork_type2_yn1'), is1('oldwork_type2_end_yn')))])

# A038 사립학교교직원연금 정기연금 수급자의 연간 수령액 중위수
emit('A038', '대상: 2022년 사립학교교직원연금 정기연금 수급자(privschp_pension_yn == 1) / 대상 변수: 정기연금 급여액(privschp_pension_amt) 가중 중위수 / 분류: 없음 / 사용 변수: privschp_pension_yn, privschp_pension_amt, indwgt',
     False, [cell([], *c_q(is1('privschp_pension_yn'), num('privschp_pension_amt'), 0.5))])

# A039 제주 긴급복지 생계지원 연간 수급자 수
emit('A039', '대상: 제주 거주자 중 2022년 긴급복지 생계지원 수급자(aid_live_yn1 == 1) / 대상 변수: 가중 인원 / 분류: 없음 / 사용 변수: sido, aid_live_yn1, indwgt',
     False, [cell([], *c_count((sido == 17) & is1('aid_live_yn1')))])

# A040 12월 아동수당 수급 아동의 소득 5분위 구성비
den = is1('childbn_yn2')
emit('A040', '대상: 2022년 12월 기준 아동수당 수급 아동(childbn_yn2 == 1) / 대상 변수: 소득 5분위(전체 인구 균등화 가처분소득 기준) 구성비 / 분류: 소득 5분위 / 사용 변수: childbn_yn2, p_dinc, hnum, hid, indwgt',
     True, [cell([f'{k}분위'], *c_rate(den, QUINT == k)) for k in range(1, 6)])

# A041 장기요양 시설급여 이용자의 연간 이용일수 중위수
emit('A041', '대상: 2022년 장기요양 시설급여 이용자(ltcare_institute_yn == 1) / 대상 변수: 시설이용급여 이용일수(ltcare_institute_freq) 가중 중위수 / 분류: 없음 / 사용 변수: ltcare_institute_yn, ltcare_institute_freq, indwgt',
     False, [cell([], *c_q(is1('ltcare_institute_yn'), num('ltcare_institute_freq'), 0.5))])

# A042 출산전후휴가급여 지급 총액, 35세 미만 / 35세 이상
x = num('empins_matleave_amt')
emit('A042', '대상: 2022년 출산전후휴가급여 수급자(empins_matleave_yn1 == 1) / 대상 변수: 출산전후휴가 급여액(empins_matleave_amt) 가중 합계 / 분류: 연령 35세 미만, 35세 이상 / 사용 변수: empins_matleave_yn1, empins_matleave_amt, age, indwgt',
     False, [cell(['35세 미만'], *c_sum(is1('empins_matleave_yn1') & (age < 35), x)), cell(['35세 이상'], *c_sum(is1('empins_matleave_yn1') & (age >= 35), x))])

# A043 광주·전북·전남 12월 기초연금 수급자 수, 시도 x 수급유형
emit('A043', '대상: 광주·전북·전남 거주 2022년 12월 기준 기초연금 수급자(bp_yn2 == 1) / 대상 변수: 가중 인원 / 분류: 시도 x 수급유형(bp_type) / 사용 변수: sido, bp_yn2, bp_type, indwgt',
     False, [cell([SIDO[s], TYPE[t]], *c_count(is1('bp_yn2') & (sido == s) & (bt == t))) for s in (5, 13, 14) for t in TYPE])

# A044 교육급여 교육활동지원비 수급 6~17세의 1인당 평균 지원비, 연령 구간별
x = num('nbls_edu_amt1')
base = np.nan_to_num(x, nan=0.0) > 0
grp = [('6~11세', (age >= 6) & (age <= 11)), ('12~14세', (age >= 12) & (age <= 14)), ('15~17세', (age >= 15) & (age <= 17))]
emit('A044', '대상: 2022년 교육급여 교육활동지원비를 받은(nbls_edu_amt1 > 0) 6~17세 / 대상 변수: 교육활동지원비 급여액(nbls_edu_amt1) 평균 / 분류: 연령 6~11세, 12~14세, 15~17세 / 사용 변수: nbls_edu_amt1, age, indwgt',
     False, [cell([l], *c_mean(base & m, x)) for l, m in grp])

# A045 80세 이상 남성 1인 가구원 중 종합병원 입원자의 재원일수 중위수
x = num('nhi_in_gehospital_dur')
base = (hnum == 1) & (age >= 80) & (gender == 1) & (np.nan_to_num(x, nan=0.0) > 0)
emit('A045', '대상: 1인 가구(hnum == 1)의 80세 이상 남성 중 2022년 종합병원 입원자(nhi_in_gehospital_dur > 0) / 대상 변수: 종합병원 재원일수(nhi_in_gehospital_dur) 가중 중위수 / 분류: 없음 / 사용 변수: hnum, age, gender, nhi_in_gehospital_dur, indwgt',
     False, [cell([], *c_q(base, x, 0.5))])

# A046 가구주 65세 이상 가구의 가구원수 구성비(가구 단위)
den = HEAD & (age >= 65)
grp = [('1인', hnum == 1), ('2인', hnum == 2), ('3인', hnum == 3), ('4인 이상', hnum >= 4)]
emit('A046', '대상: 가구주가 65세 이상인 가구(가구주 행) / 대상 변수: 가구원수 구간 구성비 / 분류: 가구원수 1인, 2인, 3인, 4인 이상 / 사용 변수: head, age, hnum, hhwgt',
     True, [cell([l], *c_rate(den, m, HW)) for l, m in grp])

# A047 배우자출산휴가급여 연간 수급자의 평균 수급일수, 시도별
x = num('empins_spouseleave_dur')
emit('A047', '대상: 2022년 배우자출산휴가급여 수급자(empins_spouseleave_yn1 == 1) / 대상 변수: 수급기간(일)(empins_spouseleave_dur) 평균 / 분류: 시도 / 사용 변수: empins_spouseleave_yn1, empins_spouseleave_dur, sido, indwgt',
     False, [cell([SIDO[s]], *c_mean(is1('empins_spouseleave_yn1') & (sido == s), x)) for s in SIDO])

# A048 등록장애인의 상대 빈곤율, 종합장애정도별
dg = num('dis_grade_1')
emit('A048', '대상: 2022년 12월 31일 기준 등록장애인(dis_yn == 1) / 분자: 균등화 가처분소득이 전체 인구 중위값의 50% 미만 / 분류: 종합장애정도(dis_grade_1: 1 정도가 심한, 2 심하지 않은) / 사용 변수: dis_yn, dis_grade_1, p_dinc, hnum, hid, indwgt',
     True, [cell(['정도가 심한 장애'], *c_rate(dis & (dg == 1), POOR)), cell(['심하지 않은 장애'], *c_rate(dis & (dg == 2), POOR))])

# ---------- 기록 ----------
with open(OUT, 'w', encoding='utf-8') as f:
    for r in ROWS:
        f.write(json.dumps(r, ensure_ascii=False, allow_nan=False) + '\n')

ids = sorted({r['id'] for r in ROWS})
print('질문 수:', len(ids), '/ 기록 줄 수:', len(ROWS))
print('모호 처리:', sorted({r['id'] for r in ROWS if r['ambiguous']}))
print('중위값(균등화):', MED, '/ 5분위 경계:', QB)
for r in ROWS:
    vals = ', '.join(f"{'|'.join(c['labels']) or '-'}={c['value'] if c['value'] is None else round(c['value'], 3)}(n={c['n']}" + (f",k={c['n_num']}" if 'n_num' in c else '') + ')' for c in r['cells'])
    print(r['id'], r['reading_no'], vals)
