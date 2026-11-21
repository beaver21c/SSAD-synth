# -*- coding: utf-8 -*-
"""W3 과제 검산(작성자 자체 대조).

1부  cases.jsonl 의 구조 점검(JSON, 유형·표현 수, 사실 id, 차례 배치)
2부  산출 정의(specs)를 조건식 그대로 평가한 값(A)과,
     질문 문장에서 다시 풀어 pandas 불리언 식으로 직접 계산한 값(B)을 칸별로 대조
     - 칸마다 가중 값과 가중하지 않은 관측 수를 출력
     - 관측 수 30건 미만 칸 표시
3부  관계 점검(relations)이 참값에서 성립하는지 확인

실행: /mnt/share/행정데이터_set/.venv/bin/python check.py > check_output.txt
"""
import json
import re
import os
import sys
from collections import Counter
from itertools import product

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(HERE, 'cases.jsonl')
DATA = '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
FACTS_DIR = '/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r5/facts'
MIN_N = 30

df = pd.read_parquet(DATA)
W = df['indwgt']

# ---------------------------------------------------------------- 공통 도구
SIDO = ['서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종', '경기', '강원', '충북', '충남',
        '전북', '전남', '경북', '경남', '제주']


def fmt(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return 'nan'
    if abs(v) >= 1000:
        return f'{v:,.1f}'
    return f'{v:.4f}'


def wquantile(values, weights, q):
    """자료 규약: 값을 오름차순으로 놓고 가중치 누적합이 전체의 q배에 처음 이르는 값."""
    order = np.argsort(values.values, kind='mergesort')
    v = values.values[order]
    w = weights.values[order]
    c = np.cumsum(w)
    return float(v[np.searchsorted(c, q * c[-1], side='left')])


# ---------------------------------------------------------------- A. 산출 정의 평가기
def by_levels(b, pop):
    """분류 기준 하나 → [(라벨, 불리언 Series)]"""
    if 'std' in b:
        s = b['std']
        if s == 'sex':
            return [('남', df['gender'] == 1), ('여', df['gender'] == 2)]
        if s == 'sido':
            return [(SIDO[i - 1], df['sido'] == i) for i in range(1, 18)]
        if s == 'age6':
            edges = [(0, 17, '0~17세'), (18, 34, '18~34세'), (35, 49, '35~49세'), (50, 64, '50~64세'),
                     (65, 74, '65~74세'), (75, 200, '75세 이상')]
            return [(lab, (df['age'] >= lo) & (df['age'] <= hi)) for lo, hi, lab in edges]
        raise ValueError('미구현 표준 분류: ' + s)
    if 'var' in b:
        v = df[b['var']]
        cuts = b['bins']
        labels = b['labels']
        out = [(labels[0], v < cuts[0])]
        for i, c in enumerate(cuts):
            hi = cuts[i + 1] if i + 1 < len(cuts) else None
            m = (v >= c) if hi is None else ((v >= c) & (v < hi))
            out.append((labels[i + 1], m))
        return out
    if 'cat' in b:
        vals = sorted(df.loc[pop, b['cat']].dropna().unique())
        return [(f"{b['cat']}={int(x)}", df[b['cat']] == x) for x in vals]
    if 'groups' in b:
        out = []
        for g in b['groups']:
            m = pd.Series(False, index=df.index)
            m.loc[df.query(g['cond']).index] = True
            out.append((g['label'], m))
        return out
    raise ValueError('미구현 분류: ' + str(b))


def eval_spec(spec):
    """→ [(라벨, 값, 관측 수 설명, 가장 작은 관측 수)]"""
    assert spec.get('unit', 'person') == 'person'
    pop = pd.Series(True, index=df.index)
    if spec.get('population'):
        pop = pd.Series(False, index=df.index)
        pop.loc[df.query(spec['population']).index] = True
    levels = [by_levels(b, pop) for b in spec.get('by', [])]
    cells = [((), pop)] if not levels else []
    for combo in product(*levels) if levels else []:
        lab = ' | '.join(c[0] for c in combo)
        m = pop.copy()
        for c in combo:
            m &= c[1]
        cells.append((lab, m))
    out = []
    for lab, m in cells:
        lab = lab if lab else '전체'
        meas = spec['measure']
        if meas == 'count':
            out.append((lab, float(W[m].sum()), f'n={int(m.sum())}', int(m.sum())))
        elif meas == 'rate':
            num = pd.Series(False, index=df.index)
            num.loc[df[m].query(spec['numerator']).index] = True
            val = 100 * W[num].sum() / W[m].sum()
            n1, n0 = int(num.sum()), int(m.sum())
            out.append((lab, float(val), f'분자 n={n1}, 분모 n={n0}, 여집합 n={n0 - n1}', min(n1, n0 - n1)))
        elif meas in ('mean', 'sum', 'quantile'):
            v = df[spec['value_var']]
            mm = m & v.notna()
            if meas == 'mean':
                val = (v[mm] * W[mm]).sum() / W[mm].sum()
            elif meas == 'sum':
                val = (v[mm] * W[mm]).sum()
            else:
                val = wquantile(v[mm], W[mm], spec['q'])
            out.append((lab, float(val), f'n={int(mm.sum())}', int(mm.sum())))
        else:
            raise ValueError('미구현 지표: ' + meas)
    return out


# ---------------------------------------------------------------- B. 질문 문장에서 다시 푼 직접 계산
# 조건식 문자열(query)을 쓰지 않고, 질문의 뜻을 변수 열의 비교식으로 직접 적음.
age, sex = df['age'], df['gender']
MALE, FEMALE = sex.eq(1), sex.eq(2)


def n_w(mask):
    return float(df.loc[mask, 'indwgt'].sum()), int(mask.sum())


def cnt(label, mask):
    w, n = n_w(mask)
    return (label, w, n)


def pct(label, num_mask, den_mask):
    a = num_mask & den_mask
    return (label, 100 * df.loc[a, 'indwgt'].sum() / df.loc[den_mask, 'indwgt'].sum(), min(int(a.sum()), int(den_mask.sum() - a.sum())))


def avg(label, col, mask):
    d = df.loc[mask & df[col].notna(), [col, 'indwgt']]
    return (label, float(np.average(d[col], weights=d['indwgt'])), len(d))


def tot(label, col, mask):
    d = df.loc[mask & df[col].notna(), [col, 'indwgt']]
    return (label, float((d[col] * d['indwgt']).sum()), len(d))


def med(label, col, mask):
    d = df.loc[mask & df[col].notna(), [col, 'indwgt']].sort_values(col, kind='mergesort')
    cum = d['indwgt'].cumsum()
    half = 0.5 * d['indwgt'].sum()
    return (label, float(d.loc[cum >= half, col].iloc[0]), len(d))


def both_sex(fn):
    return [fn('남', MALE), fn('여', FEMALE)]


def manual():
    M = {}
    # ---- W3-01 국민취업지원제도
    kua_year = df['kua_yn1'].eq(1)                       # 2022년에 한 번이라도 참여
    M[('W3-01', 1, 1, 1)] = [cnt('전체', kua_year)]
    M[('W3-01', 2, 1, 1)] = [cnt(f'{t}유형 {s}', kua_year & df['kua_type'].eq(t) & sm)
                             for t in (1, 2) for s, sm in (('남', MALE), ('여', FEMALE))]
    got_allow = df['kua_jobseekbn_amt'].notna() & df['kua_jobseekbn_amt'].gt(0)   # 구직촉진수당을 받은 사람
    full = df['kua_jobseekbn_amt'].ge(50 * 10000 * 6)                              # 월 50만원 × 6개월 = 300만원 이상
    M[('W3-01', 3, 1, 1)] = [pct('전체', full, got_allow)]

    # ---- W3-02 구직급여
    ui = df['unempbn_jobseekbn_yn'].eq(1)                # 2022년 구직급여 수급
    early = df['unempbn_early_yn'].eq(1)
    bands = [('34세 이하', age.le(34)), ('35~49세', age.between(35, 49)), ('50~64세', age.between(50, 64)),
             ('65세 이상', age.ge(65))]
    M[('W3-02', 1, 1, 1)] = [cnt(l, ui & m) for l, m in bands]
    M[('W3-02', 1, 1, 2)] = [cnt(l, (ui | early) & m) for l, m in bands]
    daily = df['unempbn_jobseekbn_amt'] / df['unempbn_jobseekbn_dur']             # 1일 급여액 = 연간 급여액 ÷ 수급일수
    M[('W3-02', 2, 1, 1)] = [pct('전체', daily.ge(66000), ui)]                    # 상한액 66,000원(C06)
    credit = df['unempbn_npcredit_yn1'].eq(1)
    M[('W3-02', 4, 1, 1)] = [pct('전체', credit, ui & age.ge(18) & age.lt(60))]

    # ---- W3-03 고용보험 가입
    ei_year = df['empins_yn1'].eq(1)
    ei_fixed = df['empins_yn2'].eq(1)                     # 고정시점 가입(0=미가입 제외)
    M[('W3-03', 1, 1, 1)] = [cnt('전체', ei_year)]
    M[('W3-03', 1, 2, 1)] = [cnt('전체', ei_fixed)]
    withheld_biz = df['binc_sum'].notna() & df['binc_sum'].gt(0)                  # 원천징수 사업소득이 있는 사람
    M[('W3-03', 3, 1, 1)] = both_sex(lambda l, sm: pct(l, ei_year, withheld_biz & sm))
    yearend_biz = df['ybinc_sum'].notna() & df['ybinc_sum'].gt(0)                 # 연말정산 사업소득(보험설계사 등)까지 넣는 해석
    M[('W3-03', 3, 1, 2)] = both_sex(lambda l, sm: pct(l, ei_year, (withheld_biz | yearend_biz) & sm))

    # ---- W3-04 고용보험료
    a6 = [('0~17세', age.le(17)), ('18~34세', age.between(18, 34)), ('35~49세', age.between(35, 49)),
          ('50~64세', age.between(50, 64)), ('65~74세', age.between(65, 74)), ('75세 이상', age.ge(75))]
    M[('W3-04', 1, 1, 1)] = [avg(l, 'empins_premium_amt', ei_year & m) for l, m in a6]
    M[('W3-04', 2, 1, 1)] = [tot('전체', 'empins_premium_amt', ei_year)]
    high = df['empins_premium_amt'].ge(50 * 10000)                                 # 연 50만원 이상
    M[('W3-04', 4, 1, 1)] = [pct(SIDO[i - 1], high, ei_year & df['sido'].eq(i)) for i in range(1, 18)]

    # ---- W3-05 산재보험
    lump = df['occupins_lump_yn'].eq(1)                   # 연금이 아닌 급여(수시·일시금)
    pens = df['occupins_pension_yn'].eq(1)                # 연금으로 받는 급여(정기연금)
    M[('W3-05', 1, 1, 1)] = both_sex(lambda l, sm: cnt(l, lump & sm))
    M[('W3-05', 2, 1, 1)] = [cnt('전체', pens)]
    M[('W3-05', 2, 2, 1)] = [avg('전체', 'occupins_pension_amt', pens)]
    M[('W3-05', 3, 1, 1)] = [cnt('전체', lump | pens)]

    # ---- W3-06 두루누리
    duru_np = df['np_support_yn1'].eq(1)
    duru_ei = df['empins_support_yn1'].eq(1)
    M[('W3-06', 1, 1, 1)] = [cnt('전체', duru_np)]
    M[('W3-06', 1, 2, 1)] = [avg('전체', 'np_support_amt', duru_np)]
    M[('W3-06', 2, 1, 1)] = [cnt('전체', duru_np & duru_ei)]
    workplace = df['np_type'].eq(0)
    low_pay = df['np_inc_amt'].lt(230 * 10000)            # 월평균보수 230만원 미만 → 기준소득월액(월) 230만원 미만
    M[('W3-06', 3, 1, 1)] = [pct('전체', duru_np, workplace & low_pay)]

    # ---- W3-07 지역가입자·납부예외
    regional = df['np_type'].eq(1)
    exempt = df['np_status'].eq(3)
    M[('W3-07', 1, 1, 1)] = [cnt('전체', regional)]
    M[('W3-07', 1, 2, 1)] = [pct('전체', exempt, regional)]
    M[('W3-07', 2, 1, 1)] = [cnt('34세 이하', exempt & age.le(34)), cnt('35~49세', exempt & age.between(35, 49)),
                             cnt('50세 이상', exempt & age.ge(50))]
    M[('W3-07', 2, 2, 1)] = [cnt('전체', exempt & df['np_exception_reason'].eq(9))]   # 9=사업중단

    # ---- W3-08 기준소득월액
    reporting = df['np_status'].eq(1)                     # 소득신고
    M[('W3-08', 1, 1, 1)] = [cnt('전체', reporting)]
    M[('W3-08', 1, 2, 1)] = [med('사업장가입자', 'np_inc_amt', reporting & workplace),
                             med('지역가입자', 'np_inc_amt', reporting & regional)]
    at_cap = df['np_inc_amt'].ge(553 * 10000)             # 상한액 553만원(2022.7.~2023.6., C12)
    M[('W3-08', 2, 1, 1)] = [cnt('전체', at_cap)]
    M[('W3-08', 2, 2, 1)] = [pct('전체', at_cap, reporting)]
    M[('W3-08', 3, 1, 1)] = [avg('임의가입자', 'np_dur', df['np_type'].eq(5)),
                             avg('임의계속가입자', 'np_dur', df['np_type'].eq(9))]
    M[('W3-08', 4, 1, 1)] = [avg('사업장가입자', 'np_premium_amt2', workplace),
                             avg('지역가입자', 'np_premium_amt2', regional)]

    # ---- W3-09 최저임금·근로소득
    wage = df['labinc_sum_taxy'].notna() & df['labinc_sum_taxy'].gt(0)             # 연말정산 근로소득이 있는 사람
    M[('W3-09', 1, 1, 1)] = both_sex(lambda l, sm: cnt(l, wage & sm))
    M[('W3-09', 1, 2, 1)] = both_sex(lambda l, sm: med(l, 'labinc_sum_taxy', wage & sm))
    mw_year = 9160 * 209 * 12                              # 시간급 9,160원 × 209시간 × 12개월
    assert mw_year == 1914440 * 12 == 22973280
    M[('W3-09', 2, 1, 1)] = both_sex(lambda l, sm: pct(l, df['labinc_sum_taxy'].lt(mw_year), wage & sm))
    wage2 = df['p_labinc'].gt(0)
    M[('W3-09', 2, 1, 2)] = both_sex(lambda l, sm: pct(l, df['p_labinc'].lt(mw_year), wage2 & sm))
    daily_inc = df['dainc_sum'].notna() & df['dainc_sum'].gt(0)
    M[('W3-09', 3, 1, 1)] = both_sex(lambda l, sm: cnt(l, daily_inc & sm))
    M[('W3-09', 3, 2, 1)] = both_sex(lambda l, sm: avg(l, 'dainc_sum', daily_inc & sm))

    # ---- W3-10 청년내일채움공제
    ye_year = df['youthemp_yn1'].eq(1)
    ye_dec = df['youthemp_yn2'].eq(1)
    M[('W3-10', 1, 1, 1)] = [cnt('전체', ye_year)]
    M[('W3-10', 1, 2, 1)] = [cnt('전체', ye_dec)]
    paid = df['youthemp_amt1'].notna() & df['youthemp_amt1'].gt(0)                 # 2022년에 공제금을 지급받은 사람(세전)
    matured = df['youthemp_amt1'].ge(1200 * 10000)        # 1,200만원 이상
    M[('W3-10', 2, 1, 1)] = [cnt('전체', matured)]
    M[('W3-10', 2, 2, 1)] = [pct('전체', matured, paid)]
    M[('W3-10', 4, 1, 1)] = [avg('전체', 'youthemp_cnt3', ye_dec)]

    # ---- W3-11 국민내일배움카드
    card = df['vocaedu_yn'].eq(1)
    b3 = [('34세 이하', age.le(34)), ('35~49세', age.between(35, 49)), ('50세 이상', age.ge(50))]
    M[('W3-11', 1, 1, 1)] = [cnt(f'{l} {s}', card & m & sm) for l, m in b3 for s, sm in (('남', MALE), ('여', FEMALE))]
    M[('W3-11', 2, 1, 1)] = [avg('전체', 'vocaedu_amt', card)]
    M[('W3-11', 2, 2, 1)] = [med('전체', 'vocaedu_amt', card)]
    M[('W3-11', 3, 1, 1)] = [cnt('전체', card)]
    M[('W3-11', 3, 2, 1)] = [pct('전체', ei_year, card)]
    return M


# ---------------------------------------------------------------- 실행
def main():
    problems = []
    # ---------- 1부 구조
    print('=' * 100)
    print('1부. cases.jsonl 구조 점검')
    print('=' * 100)
    cases = []
    with open(CASES, encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            line = line.rstrip('\n')
            if not line.strip():
                problems.append(f'{i}행: 빈 줄')
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as e:
                problems.append(f'{i}행: JSON 오류 {e}')
    print(f'과제 수: {len(cases)} (id: {", ".join(c["id"] for c in cases)})')

    facts = {}
    for fn in ('facts_A.jsonl', 'facts_B.jsonl', 'facts_C.jsonl'):
        with open(os.path.join(FACTS_DIR, fn), encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    facts[r['id']] = r
    varnames = set(df.columns)

    kinds, regs = Counter(), Counter()
    used_facts = set()
    n_rel = 0
    for c in cases:
        ks = [t['kind'] for t in c['turns']]
        if len(c['turns']) != 4:
            problems.append(f'{c["id"]}: 차례 수 {len(c["turns"])}')
        if [t['n'] for t in c['turns']] != [1, 2, 3, 4]:
            problems.append(f'{c["id"]}: 차례 번호')
        if ks[0] not in ('S', 'G'):
            problems.append(f'{c["id"]}: 첫 차례 {ks[0]}')
        if ks.count('S') < 2:
            problems.append(f'{c["id"]}: S 차례 {ks.count("S")}개')
        aliases = {a for fid in c['facts'] if fid in facts for a in facts[fid].get('aliases', [])}
        for t in c['turns']:
            kinds[t['kind']] += 1
            k = t['kind']
            words = set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', t['q']))
            if words & varnames:
                problems.append(f'{c["id"]}-{t["n"]}: 질문에 변수명 {words & varnames}')
            if k in 'SGPX':
                if 'register' not in t:
                    problems.append(f'{c["id"]}-{t["n"]}: register 없음')
                regs[t.get('register')] += 1
                hit = [a for a in aliases if a in t['q']]
                if t.get('register') == '약칭':
                    if not hit:
                        problems.append(f'{c["id"]}-{t["n"]}: 약칭 차례인데 과제 사실의 aliases 표현이 질문에 없음')
                    else:
                        print(f'    (약칭 확인) {c["id"]}-{t["n"]}: {hit}')
            elif 'register' in t:
                problems.append(f'{c["id"]}-{t["n"]}: {k} 차례에 register')
            if k in ('G', 'P'):
                num = str(t['param']['수치'])      # 기준값(원 단위)이 모든 산출 정의의 조건식에 그대로 들어 있는지
                if not all(num in json.dumps(s) for s in t['specs']):
                    problems.append(f'{c["id"]}-{t["n"]}: param 수치 {num} 가 일부 산출 정의에 없음')
            need = {'S': ['specs'], 'G': ['specs', 'param'], 'P': ['specs', 'param'], 'N': ['absent', 'rubric'],
                    'V': ['absent', 'rubric'], 'T': ['rubric'], 'X': ['premise', 'rubric'], 'C': ['rubric'],
                    'I': ['rubric']}[k]
            for key in need:
                if key not in t:
                    problems.append(f'{c["id"]}-{t["n"]}: {k} 차례 필수 항목 {key} 없음')
            if k == 'C' and t['n'] < 3:
                problems.append(f'{c["id"]}-{t["n"]}: C 차례가 앞쪽')
            if k in ('G', 'P', 'X') and 'param' in t and t['param'].get('fact') not in c['facts']:
                problems.append(f'{c["id"]}-{t["n"]}: param 의 fact 가 과제 facts 에 없음')
        for fid in c['facts']:
            used_facts.add(fid)
            if fid not in facts:
                problems.append(f'{c["id"]}: 사실 {fid} 없음')
            elif facts[fid].get('status') == 'unverified':
                problems.append(f'{c["id"]}: 사실 {fid} unverified')
        if len(c.get('relations', [])) > 2:
            problems.append(f'{c["id"]}: relations {len(c["relations"])}개')
        n_rel += len(c.get('relations', []))
        print(f'  {c["id"]}  유형 {"".join(ks)}  표현 {[t.get("register", "-") for t in c["turns"]]}  사실 {c["facts"]}  관계 {len(c.get("relations", []))}')

    target_k = {'S': 24, 'G': 3, 'P': 3, 'N': 3, 'V': 2, 'T': 2, 'X': 2, 'C': 3, 'I': 2}
    print('유형별 차례 수:', {k: kinds[k] for k in target_k}, '/ 목표', target_k)
    if {k: kinds[k] for k in target_k} != target_k or sum(kinds.values()) != 44:
        problems.append('유형별 차례 수가 목표와 다름')
    print('표현별 차례 수(S·G·P·X):', dict(regs), '/ 목표 공식 9~11, 약칭 10~12, 서술 8~10, 영문 2')
    if not (9 <= regs['공식'] <= 11 and 10 <= regs['약칭'] <= 12 and 8 <= regs['서술'] <= 10 and regs['영문'] == 2
            and sum(regs.values()) == 32):
        problems.append('표현별 차례 수가 목표 범위를 벗어남')
    print(f'쓴 사실 id {len(used_facts)}개: {sorted(used_facts)}')
    print(f'관계 점검 {n_rel}개(목표 5개 이상)')
    if n_rel < 5:
        problems.append('관계 점검 5개 미만')

    # ---------- 2부 산출 대조
    print()
    print('=' * 100)
    print('2부. 산출 정의 평가값(A)과 질문에서 다시 푼 직접 계산값(B) 대조')
    print('     값: 인원·합계·평균·분위수는 가중 값, 비율은 %. 관측 수는 가중하지 않은 행 수')
    print('=' * 100)
    M = manual()
    seen = set()
    truth = {}
    n_cells = n_small = 0
    for c in cases:
        print(f'\n### {c["id"]}  {c["issue"]}')
        for t in c['turns']:
            if 'specs' not in t:
                print(f'  [차례 {t["n"]} {t["kind"]}] 산출 정의 없음')
                continue
            print(f'  [차례 {t["n"]} {t["kind"]} {t.get("register", "")}] {t["q"][:70]}…')
            for s in t['specs']:
                key = (c['id'], t['n'], s.get('part', 1), s.get('alt', 1))
                seen.add(key)
                a = eval_spec(s)
                truth[key] = a
                b = M.get(key)
                head = f'    part {key[2]} alt {key[3]} | {s["measure"]}'
                if s.get('value_var'):
                    head += f'({s["value_var"]}' + (f', q={s["q"]}' if 'q' in s else '') + ')'
                head += f' | 대상: {s.get("population") or "전체"}'
                if s.get('numerator'):
                    head += f' | 분자: {s["numerator"]}'
                print(head)
                if b is None:
                    problems.append(f'{key}: 직접 계산(B) 없음')
                    b = [(None, float('nan'), -1)] * len(a)
                if len(a) != len(b):
                    problems.append(f'{key}: 칸 수 불일치 A {len(a)} / B {len(b)}')
                for i, (lab, val, ndesc, nmin) in enumerate(a):
                    bl, bv, bn = b[i] if i < len(b) else (None, float('nan'), -1)
                    ok = (abs(val - bv) <= 1e-6 * max(1.0, abs(val))) and (bn == nmin)
                    small = nmin < MIN_N
                    n_cells += 1
                    n_small += small
                    mark = '일치' if ok else '불일치'
                    if not ok:
                        problems.append(f'{key} [{lab}]: A {val} ({ndesc}) / B {bv} (n={bn})')
                    if small:
                        problems.append(f'{key} [{lab}]: 관측 수 {nmin}건(30건 미만)')
                    print(f'      {lab:<22} A={fmt(val):>20}  B={fmt(bv):>20}  {ndesc:<40} {mark}{"  ※30건 미만" if small else ""}')
    for key in M:
        if key not in seen:
            problems.append(f'{key}: 직접 계산(B)만 있고 산출 정의 없음')
    print(f'\n대조한 칸 수: {n_cells}, 30건 미만 칸: {n_small}')

    # ---------- 3부 관계 점검
    print()
    print('=' * 100)
    print('3부. 관계 점검(참값 기준 성립 여부)')
    print('=' * 100)

    def count_total(cid, n):
        """그 차례의 count 정의(alt 1) 가운데 관계에 쓰는 인원: part 가 여럿이면 count 인 첫 part"""
        cs = next(c for c in cases if c['id'] == cid)
        t = cs['turns'][n - 1]
        for s in t['specs']:
            if s['measure'] == 'count' and s.get('alt', 1) == 1:
                cells = truth[(cid, n, s.get('part', 1), 1)]
                return sum(x[1] for x in cells), sum(x[3] for x in cells)
        raise ValueError(f'{cid} 차례 {n}: count 정의 없음')

    for c in cases:
        for r in c.get('relations', []):
            if r['type'] == 'parts_sum':
                (wv, wn), (pv, pn) = count_total(c['id'], r['whole']), count_total(c['id'], r['parts'])
                ok = abs(wv - pv) < 1e-6 * wv and wn == pn
                print(f'  {c["id"]} parts_sum 전체(차례 {r["whole"]})={fmt(wv)} (n={wn}) / 부분합(차례 {r["parts"]})={fmt(pv)} (n={pn}) → {"성립" if ok else "불성립"}')
            elif r['type'] == 'subset_le':
                (lv, ln), (sv, sn) = count_total(c['id'], r['large']), count_total(c['id'], r['small'])
                ok = sv <= lv and sn <= ln
                print(f'  {c["id"]} subset_le 큰 쪽(차례 {r["large"]})={fmt(lv)} (n={ln}) ≥ 작은 쪽(차례 {r["small"]})={fmt(sv)} (n={sn}), 차이 n={ln - sn} → {"성립" if ok else "불성립"}')
                if ln - sn < MIN_N:
                    problems.append(f'{c["id"]} 관계 {r}: 차이 집단 관측 수 {ln - sn}건')
            else:
                ok = False
                print(f'  {c["id"]} 미구현 관계 {r}')
            if not ok:
                problems.append(f'{c["id"]} 관계 불성립 {r}')

    # ---------- 4부 N·V 차례의 자료 확인
    print()
    print('=' * 100)
    print('4부. N·V 차례 — 자료에 없음·값 없음 확인')
    print('=' * 100)
    cb = pd.read_csv('/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/inputs/codebook.tsv', sep='\t')
    text = (cb['var'].astype(str) + ' ' + cb['name_ko'].astype(str) + ' ' + cb['program'].astype(str))
    nov = pd.read_csv('/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r5/inputs/값없는_사업.tsv', sep='\t')
    for label, words in [('W3-03 차례 2(N) 가입 유형·직종', ['노무제공', '특고', '특수형태', '직종', '플랫폼', '예술인']),
                         ('W3-07 차례 3(N) 지역가입자 연금보험료 지원', ['납부재개', '연금보험료 지원', '지역가입자 연금', '지역가입자 지원']),
                         ('W3-10 차례 3(N) 청년내일저축계좌', ['저축계좌', '자산형성', '희망적금'])]:
        hit = {w: int(text.str.contains(w).sum()) for w in words}
        print(f'  {label}: codebook.tsv 변수명·한글 이름·사업명 검색 건수 {hit}')
        if any(hit.values()):
            problems.append(f'{label}: codebook 에 관련 변수가 있음 {hit}')
    print('  (참고) codebook.tsv 의 「보험료 지원」·「보험료 지원여부」 변수(모두 두루누리):',
          cb.loc[cb['name_ko'].str.contains('보험료 지원|고용보험료 지원'), 'var'].tolist())
    print('  (참고) 이름에 「지역가입자 보험료」가 들어가는 변수(건강보험·장기요양, 다른 항목):',
          cb.loc[cb['name_ko'].str.contains('지역가입자 보험료'), 'var'].tolist())
    for label, word, cols in [('W3-02 차례 3(V) 상병급여', '상병급여', ['unempbn_sicknessbn_yn', 'unempbn_sicknessbn_amt', 'p_unempbn_sicknessbn_amt']),
                              ('W3-11 차례 4(V) 시니어인턴십', '시니어인턴십', [])]:
        rows = nov[nov['사업'].str.contains(word)]
        print(f'  {label}: 값없는_사업.tsv 수록 {len(rows)}건 {rows["사업"].tolist()} / {rows["보유기관"].tolist()}')
        if len(rows) == 0:
            problems.append(f'{label}: 값없는_사업.tsv 에 없음')
        for col in cols:
            if col in df.columns:
                s = df[col]
                print(f'      자료 열 {col}: 결측 아닌 행 {int(s.notna().sum())}, 0보다 큰 행 {int((s > 0).sum())}')
                if (s > 0).sum() > 0:
                    problems.append(f'{label}: {col} 에 값이 있음')
            else:
                print(f'      자료 열 {col}: 없음')
    cols_intern = [c for c in df.columns if 'oldwork' in c]
    print('      자료의 노인일자리 열 접두:', sorted({c.rsplit('_', 1)[0] for c in cols_intern}))
    small = df['unempbn_jobseekbn_type'].eq(4).sum()
    print(f'  (참고) W3-03 차례 4(C)가 요구한 칸 — 구직급여 수급자유형 예술인·노무제공자 관측 수 10건 미만 여부: {bool(small < 10)}')

    # ---------- 결과
    print()
    print('=' * 100)
    print(f'점검 결과: 문제 {len(problems)}건')
    for p in problems:
        print('  -', p)
    print('=' * 100)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
