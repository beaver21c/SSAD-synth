# -*- coding: utf-8 -*-
"""5차 과제 작성자 W2 — 산출 정의 자체 대조.

구성
  A. 질문 문장에서 다시 풀어 쓴 직접 계산(pandas·numpy 불리언 식. 산출 정의의 조건식 문자열을 쓰지 않음)
  B. cases.jsonl 의 산출 정의(specs)를 그대로 평가한 값
  C. A와 B의 대조, 칸별 가중 값과 가중하지 않은 관측 수, 관측 수 30건 미만 칸 표시
  D. 관계 점검(relations)이 참값에서 성립하는지 확인
  E. 양식 점검: JSON 재읽기, 유형·표현별 차례 수, 사실 id·기준값·약칭 대조

실행: /mnt/share/행정데이터_set/.venv/bin/python check.py > check_output.txt
"""
import json
import os
import sys
from collections import Counter

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
FACTS_DIR = '/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r5/facts'
CASES = os.path.join(HERE, 'cases.jsonl')
MIN_OBS = 30

df = pd.read_parquet(DATA)
W = df['indwgt'].to_numpy(dtype=float)
HW = df['hhwgt'].to_numpy(dtype=float)


def col(name):
    """결측을 NaN 으로 둔 float 배열."""
    return pd.to_numeric(df[name], errors='coerce').to_numpy(dtype=float, na_value=np.nan)


# ---------------------------------------------------------------- A. 직접 계산
age = col('age'); sex = col('gender'); sido = col('sido'); hnum = col('hnum'); head = col('head')
nt = col('nhi_type')


def a_count(mask, label='전체', wt=W):
    mask = np.asarray(mask, dtype=bool)
    return {'label': label, 'value': float(wt[mask].sum()), 'n': int(mask.sum())}


def a_rate(num, den, label='전체'):
    num = np.asarray(num, dtype=bool); den = np.asarray(den, dtype=bool)
    both = num & den
    return {'label': label, 'value': float(W[both].sum() / W[den].sum() * 100),
            'n': int(both.sum()), 'n_den': int(den.sum()), 'n_rest': int(den.sum() - both.sum())}


def a_mean(values, mask, label='전체'):
    mask = np.asarray(mask, dtype=bool) & ~np.isnan(values)
    return {'label': label, 'value': float((values[mask] * W[mask]).sum() / W[mask].sum()), 'n': int(mask.sum())}


SIDO_NM = ['서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종', '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주']
AGE3 = [('0~17세', age <= 17), ('18~64세', (age >= 18) & (age <= 64)), ('65세 이상', age >= 65)]
AGE6 = [('0~17세', age < 18), ('18~34세', (age >= 18) & (age < 35)), ('35~49세', (age >= 35) & (age < 50)),
        ('50~64세', (age >= 50) & (age < 65)), ('65~74세', (age >= 65) & (age < 75)), ('75세 이상', age >= 75)]
SEX = [('남', sex == 1), ('여', sex == 2)]
HS4 = [('1인', hnum == 1), ('2인', hnum == 2), ('3인', hnum == 3), ('4인 이상', hnum >= 4)]

A = {}

# W2-01 건강보험료 부과체계 2단계 개편(지역가입자)
region = (nt == 1) | (nt == 2)                       # 지역가입자 = 지역세대주 + 지역세대원
region_head = (nt == 1)                              # 지역가입자 세대주
prem_dec = col('nhi_premium_cal')                    # 12월 말 산정보험료(월액)
A[('W2-01', 1, 1)] = [a_count(region)]
A[('W2-01', 1, 2)] = [a_count(region & (sido == i + 1), SIDO_NM[i]) for i in range(17)]
A[('W2-01', 2, 1)] = [a_count(region_head & (prem_dec <= 19500))]
A[('W2-01', 2, 2)] = [a_rate(prem_dec <= 19500, region_head)]
paid_region = col('nhi_premium_amt3_y')              # 지역가입자 보험료 연간 실납부(장기요양보험료 제외)
A[('W2-01', 3, 1)] = [a_mean(paid_region, region_head & m, lab) for lab, m in HS4]

# W2-02 피부양자 소득요건 강화
dep = (nt == 6)                                      # 직장가입자의 피부양자
A[('W2-02', 1, 1)] = [a_count(dep & m, lab) for lab, m in AGE3]
A[('W2-02', 2, 1)] = [a_count(dep & (col('p_oinc') > 2000 * 10000))]      # 연 2,000만 원 초과(B02)
A[('W2-02', 3, 1)] = [a_rate(dep, (age >= 65) & m, lab) for lab, m in SEX]

# W2-03 본인부담상한제
ceil_yes = (col('nhi_ceiling_subsidy_yn') == 1)
ceil_amt = col('nhi_ceiling_subsidy_amt')
A[('W2-03', 1, 1)] = [a_count(ceil_yes)]
A[('W2-03', 1, 2)] = [a_mean(ceil_amt, ceil_yes)]
A[('W2-03', 2, 1)] = [a_count(ceil_yes & m, lab) for lab, m in AGE3]
out_fee = col('nhi_out_fee')
over83 = out_fee > 83 * 10000                        # 2022년 1분위 상한액 83만 원(B06)
A[('W2-03', 3, 1)] = [a_count(over83)]
A[('W2-03', 3, 2)] = [a_rate(ceil_yes, over83)]

# W2-04 산정특례·재난적의료비
cancer = (col('nhi_special1_yn') == 1)
dementia = (col('nhi_special4_yn') == 1)
ltc = (col('ltcare_bn_yn') == 1)
A[('W2-04', 1, 1)] = [a_count(cancer & m, lab) for lab, m in SEX]
A[('W2-04', 2, 1)] = [a_count(dementia)]
A[('W2-04', 2, 2)] = [a_rate(ltc, dementia)]
A[('W2-04', 4, 1)] = [a_rate(ceil_yes, cancer)]              # 암 등록자 중 본인부담상한제 지원 비율

# W2-05 의료급여
medi_dec = (col('nbls_medi_yn2') == 1)               # 12월 말 수급권자
medi_type = col('nbls_medi_type')
A[('W2-05', 1, 1)] = [a_count(medi_dec)]
A[('W2-05', 2, 1)] = [a_count(medi_dec & (medi_type == t), f'{t}종') for t in (1, 2)]
A[('W2-05', 2, 2)] = [a_rate(age >= 65, medi_dec & (medi_type == t), f'{t}종') for t in (1, 2)]
line_medi_1p = 777925 * 12                           # 2022년 의료급여 선정기준 1인 가구 월 777,925원(A04) × 12
single_hh = (head == 1) & (hnum == 1)
A[('W2-05', 4, 1)] = [a_count(single_hh & (col('h_oinc') <= line_medi_1p) & ~medi_dec, wt=HW)]

# W2-06 노인장기요양보험
grade = col('ltcare_grade')
A[('W2-06', 1, 1)] = [a_count(ltc & ((grade == 1) | (grade == 2)), '1~2등급'),
                      a_count(ltc & (grade == 3), '3등급'), a_count(ltc & (grade == 4), '4등급'),
                      a_count(ltc & (grade == 5), '5등급'), a_count(ltc & (grade == 6), '인지지원등급')]
OLD3 = [('65~74세', (age >= 65) & (age <= 74)), ('75~84세', (age >= 75) & (age <= 84)), ('85세 이상', age >= 85)]
A[('W2-06', 2, 1)] = [a_count(ltc & m, lab) for lab, m in OLD3]
A[('W2-06', 2, 2)] = [a_rate(ltc, m, lab) for lab, m in OLD3]
inst = (col('ltcare_institute_yn') == 1)             # 시설이용급여 수급
A[('W2-06', 3, 1)] = [a_rate(inst, ltc)]
ibn = col('ltcare_ibn_fee')
A[('W2-06', 3, 2)] = [a_mean(ibn, inst)]
A[('W2-06', 3, 2, 2)] = [a_mean(ibn, inst & (ibn > 0))]          # alt 2: 본인부담금이 있는 사람 기준

# W2-07 노인맞춤돌봄서비스
oc_year = (col('oldcare_yn1') == 1); oc_dec = (col('oldcare_yn2') == 1)
A[('W2-07', 1, 1)] = [a_count(oc_year)]
A[('W2-07', 1, 2)] = [a_count(oc_dec)]
A[('W2-07', 2, 1)] = [a_rate(oc_dec, (age >= 65) & (hnum == 1), '1인 가구'),
                      a_rate(oc_dec, (age >= 65) & (hnum > 1), '2인 이상 가구')]

# W2-08 노인일자리
job1 = (col('oldwork_type1_yn1') == 1); job2 = (col('oldwork_type2_yn1') == 1); job3 = (col('oldwork_type3_yn1') == 1)
A[('W2-08', 1, 1)] = [a_count(job1, '공익활동')]
A[('W2-08', 1, 2)] = [a_count(job2, '사회서비스형')]
A[('W2-08', 1, 3)] = [a_count(job3, '시장형사업단')]
bp_year65 = (age >= 65) & (col('bp_yn1') == 1)
OLD4 = [('65~69세', (age >= 65) & (age <= 69)), ('70~74세', (age >= 70) & (age <= 74)),
        ('75~79세', (age >= 75) & (age <= 79)), ('80세 이상', age >= 80)]
A[('W2-08', 2, 1)] = [a_rate(job1, bp_year65 & m, lab) for lab, m in OLD4]
A[('W2-08', 3, 1)] = [a_rate(col('oldwork_type1_amt') >= 270000 * 11, job1)]   # 월 27만 원 × 11개월(B22)

# W2-09 장애 정도·활동지원
dis = (col('dis_yn') == 1); dgrade = col('dis_grade_1')
A[('W2-09', 1, 1)] = [a_count(dis)]
A[('W2-09', 2, 1)] = [a_count(dis & (dgrade == 1), '심한 장애'), a_count(dis & (dgrade == 2), '심하지 않은 장애')]
act_year = (col('disvou_act_yn1') == 1)
A[('W2-09', 3, 1)] = [a_rate(act_year, (dgrade == 1) & (age <= 64) & m, lab) for lab, m in SEX]

# W2-10 코로나19 유행기 의료이용
out_days = col('nhi_out_dur'); in_days = col('nhi_in_dur'); er_days = col('nhi_in_emergency_dur')
everyone = np.ones(len(df), dtype=bool)
A[('W2-10', 1, 1)] = [a_mean(out_days, m, lab) for lab, m in AGE6]
A[('W2-10', 2, 1)] = [a_rate(in_days >= 1, (age >= 65) & m, lab) for lab, m in SEX]
A[('W2-10', 4, 1)] = [a_rate(er_days >= 1, everyone & (sido == i + 1), SIDO_NM[i]) for i in range(17)]

# W2-11 상병수당 시범사업
target = (age >= 15) & (age <= 64) & (nt == 5)       # 만 15세 이상 65세 미만 직장가입자 본인
A[('W2-11', 1, 1)] = [a_count(target & m, lab) for lab, m in SEX]
A[('W2-11', 3, 1)] = [a_count(target & (in_days >= 3))]
A[('W2-11', 3, 2)] = [a_rate(in_days >= 3, target)]
A[('W2-11', 4, 1)] = [a_mean(in_days, target & (in_days >= 1) & m, lab) for lab, m in SEX]


# ---------------------------------------------------------------- B. 산출 정의 평가
STD = {
    'sido': [(SIDO_NM[i], f'sido == {i + 1}') for i in range(17)],
    'sex': [('남', 'gender == 1'), ('여', 'gender == 2')],
    'age3': [('0~17세', 'age < 18'), ('18~64세', 'age >= 18 and age < 65'), ('65세 이상', 'age >= 65')],
    'age6': [('0~17세', 'age < 18'), ('18~34세', 'age >= 18 and age < 35'), ('35~49세', 'age >= 35 and age < 50'),
             ('50~64세', 'age >= 50 and age < 65'), ('65~74세', 'age >= 65 and age < 75'), ('75세 이상', 'age >= 75')],
    'hs4': [('1인', 'hnum == 1'), ('2인', 'hnum == 2'), ('3인', 'hnum == 3'), ('4인 이상', 'hnum >= 4')],
}


def q(frame, expr):
    return frame if not expr else frame.query(expr, engine='python')


def by_cells(frame, by):
    """분류 기준 목록을 (라벨, 부분 자료)의 목록으로 편다."""
    cells = [('전체', frame)]
    for b in by:
        nxt = []
        for lab, fr in cells:
            if 'std' in b:
                parts = [(l, q(fr, e)) for l, e in STD[b['std']]]
            elif 'cat' in b:
                vals = sorted(v for v in frame[b['cat']].dropna().unique())
                parts = [(f"{b['cat']}={v:g}", fr[fr[b['cat']] == v]) for v in vals]
            elif 'var' in b:
                edges = [-np.inf] + list(b['bins']) + [np.inf]
                parts = [(b['labels'][i], fr[(fr[b['var']] >= edges[i]) & (fr[b['var']] < edges[i + 1])])
                         for i in range(len(edges) - 1)]
            elif 'groups' in b:
                parts = [(g['label'], q(fr, g['cond'])) for g in b['groups']]
            else:
                raise ValueError(b)
            nxt += [((lab + ' / ' + l) if lab != '전체' else l, p) for l, p in parts]
        cells = nxt
    return cells


def eval_spec(sp):
    unit = sp.get('unit', 'person')
    base = df[df['head'] == 1] if unit == 'household' else df
    wcol = 'hhwgt' if unit == 'household' else 'indwgt'
    pop = q(base, sp.get('population', ''))
    out = []
    for lab, fr in by_cells(pop, sp.get('by', [])):
        m = sp['measure']
        if m == 'count':
            out.append({'label': lab, 'value': float(fr[wcol].sum()), 'n': len(fr)})
        elif m == 'rate':
            nu = q(fr, sp['numerator'])
            out.append({'label': lab, 'value': float(nu[wcol].sum() / fr[wcol].sum() * 100),
                        'n': len(nu), 'n_den': len(fr), 'n_rest': len(fr) - len(nu)})
        elif m == 'mean':
            v = fr[fr[sp['value_var']].notna()]
            x = v[sp['value_var']].astype(float)
            out.append({'label': lab, 'value': float((x * v[wcol]).sum() / v[wcol].sum()), 'n': len(v)})
        else:
            raise ValueError(m)
    return out


# ---------------------------------------------------------------- C. 대조와 출력
cases = [json.loads(line) for line in open(CASES, encoding='utf-8') if line.strip()]
print(f'[자료] 행 {len(df):,} / 가중 인구 {W.sum():,.0f} / 가구 {int((head == 1).sum()):,} (가중 {HW[head == 1].sum():,.0f})')
print(f'[과제] {len(cases)}개를 cases.jsonl 에서 다시 읽음(JSON 형식 확인)\n')

n_spec = n_ok = 0
small_cells = []
B = {}
for c in cases:
    print('=' * 100)
    print(f"{c['id']}  {c['issue']}")
    for t in c['turns']:
        head_line = f"  차례 {t['n']} [{t['kind']}{'·' + t['register'] if 'register' in t else ''}]"
        if 'specs' not in t:
            print(head_line + ' 산출 정의 없음')
            continue
        print(head_line)
        for sp in t['specs']:
            part = sp.get('part', 1); alt = sp.get('alt', 1)
            key = (c['id'], t['n'], part) if alt == 1 else (c['id'], t['n'], part, alt)
            res = eval_spec(sp)
            B[key] = res
            n_spec += 1
            ref = A.get(key)
            if ref is None:
                verdict = '직접 계산 없음'
            else:
                same = len(ref) == len(res) and all(
                    np.isclose(a['value'], b['value'], rtol=1e-9, atol=1e-9) and a['n'] == b['n']
                    for a, b in zip(ref, res))
                verdict = '일치' if same else '불일치'
                n_ok += int(same)
            desc = f"{sp['measure']}/{sp.get('unit', 'person')}"
            if sp.get('value_var'):
                desc += f" {sp['value_var']}"
            print(f"    part {part} alt {alt}  {desc}  | 대상: {sp.get('population', '') or '(전체)'}"
                  + (f" | 분자: {sp['numerator']}" if sp.get('numerator') else '') + f"  → 대조 {verdict}")
            for i, r in enumerate(res):
                a_val = f"{ref[i]['value']:,.4f}" if ref is not None and i < len(ref) else '-'
                if sp['measure'] == 'rate':
                    obs = f"관측 분자 {r['n']:,} / 분모 {r['n_den']:,} / 여집합 {r['n_rest']:,}"
                    low = min(r['n'], r['n_den'], r['n_rest'])
                else:
                    obs = f"관측 {r['n']:,}"
                    low = r['n']
                flag = ''
                if low < MIN_OBS:
                    flag = '  ← 30건 미만'
                    small_cells.append((c['id'], t['n'], part, alt, r['label'], low))
                print(f"        {r['label']:<14} 정의 {r['value']:>18,.4f} | 직접 {a_val:>18} | {obs}{flag}")

print('\n' + '=' * 100)
print(f'[대조 요약] 산출 정의 {n_spec}개 가운데 직접 계산과 일치 {n_ok}개, 불일치 {n_spec - n_ok}개')
print(f'[관측 수] 30건 미만 칸: {len(small_cells)}개' + (f' {small_cells}' if small_cells else ''))
unused = [k for k in A if k not in B]
print(f'[직접 계산만 있고 정의가 없는 항목] {unused if unused else "없음"}')

# ---------------------------------------------------------------- D. 관계 점검
print('\n[관계 점검] 참값 기준 성립 여부')


def total(case_id, turn, part=1):
    return sum(r['value'] for r in B[(case_id, turn, part)])


n_rel = 0                                            # 관계 점검은 모두 각 차례의 part 1(인원)을 가리킴
for c in cases:
    for r in c.get('relations', []):
        n_rel += 1
        if r['type'] == 'parts_sum':
            whole, parts = total(c['id'], r['whole']), total(c['id'], r['parts'])
            ok = np.isclose(whole, parts, rtol=1e-9)
            print(f"  {c['id']} parts_sum  차례 {r['whole']} 전체 {whole:,.1f} = 차례 {r['parts']} 합 {parts:,.1f}  → {'성립' if ok else '불성립'}")
        elif r['type'] == 'subset_le':
            large, small = total(c['id'], r['large']), total(c['id'], r['small'])
            ok = small <= large + 1e-6
            print(f"  {c['id']} subset_le  차례 {r['large']} {large:,.1f} ≥ 차례 {r['small']} {small:,.1f}  → {'성립' if ok else '불성립'}")
        elif r['type'] == 'same':
            a, b = total(c['id'], r['a']), total(c['id'], r['b'])
            print(f"  {c['id']} same  {a:,.4f} = {b:,.4f}  → {'성립' if np.isclose(a, b) else '불성립'}")
print(f'  관계 점검 수: {n_rel}개')

# 이어지는 차례의 대상 차이가 소수 집단이 되는지(작성 규칙 5)
print('\n[이어지는 차례의 대상 차이] 관측 수')
diffs = [
    ('W2-01 지역가입자 − 지역세대주', region & ~region_head),
    ('W2-01 지역세대주 − 산정보험료 19,500원 이하', region_head & ~(prem_dec <= 19500)),
    ('W2-03 외래 본인부담 83만 원 초과 − 그중 상한제 지원', over83 & ~ceil_yes),
    ('W2-04 치매 등록자 − 그중 장기요양 수급', dementia & ~ltc),
    ('W2-04 암 등록자 − 그중 상한제 지원', cancer & ~ceil_yes),
    ('W2-06 장기요양 수급자 − 65세 이상 수급자', ltc & (age < 65)),
    ('W2-06 장기요양 수급자 − 시설급여 수급', ltc & ~inst),
    ('W2-07 연간 이용 − 12월 이용', oc_year & ~oc_dec),
    ('W2-09 심한 장애 − 65세 미만 심한 장애', (dgrade == 1) & (age >= 65)),
    ('W2-09 65세 미만 심한 장애 − 활동지원 자격', (dgrade == 1) & (age < 65) & ~act_year),
    ('W2-11 대상 중 입원 1~2일(입원자 − 3일 이상)', target & (in_days >= 1) & (in_days < 3)),
]
for name, m in diffs:
    print(f"  {name}: {int(m.sum()):,}건{'  ← 30건 미만' if m.sum() < MIN_OBS else ''}")

# ---------------------------------------------------------------- E. 양식 점검
print('\n[양식 점검]')
problems = []
kinds = Counter(); regs = Counter(); fact_ids = set()
for c in cases:
    ts = c['turns']
    if len(ts) != 4 or [t['n'] for t in ts] != [1, 2, 3, 4]:
        problems.append(f"{c['id']}: 차례 4개가 아님")
    if ts[0]['kind'] not in ('S', 'G'):
        problems.append(f"{c['id']}: 첫 차례가 S·G 아님")
    if sum(t['kind'] == 'S' for t in ts) < 2:
        problems.append(f"{c['id']}: S 2개 미만")
    for k in ('id', 'domain', 'issue', 'facts', 'persona', 'setting', 'turns', 'relations'):
        if k not in c:
            problems.append(f"{c['id']}: 항목 {k} 없음")
    fact_ids.update(c['facts'])
    for t in ts:
        kinds[t['kind']] += 1
        need = {'S': ['specs'], 'G': ['specs', 'param'], 'P': ['specs', 'param'], 'N': ['absent'], 'V': ['absent'],
                'T': [], 'X': ['premise'], 'C': [], 'I': []}[t['kind']] + ['q', 'rubric', 'note']
        for k in need:
            if not t.get(k):
                problems.append(f"{c['id']} 차례 {t['n']}: 항목 {k} 없음")
        if t['kind'] in 'SGPX':
            regs[t.get('register', '없음')] += 1
        elif 'register' in t:
            problems.append(f"{c['id']} 차례 {t['n']}: register 불필요")
        if t['kind'] == 'C' and t['n'] < 3:
            problems.append(f"{c['id']} 차례 {t['n']}: C가 앞쪽 차례")
    for r in c['relations']:
        for k in ('whole', 'parts', 'large', 'small', 'a', 'b'):
            if k in r and 'specs' not in ts[r[k] - 1]:
                problems.append(f"{c['id']}: 관계 점검이 산출 정의 없는 차례 {r[k]}를 가리킴")

target_kind = {'S': 24, 'G': 3, 'P': 3, 'N': 3, 'V': 2, 'T': 2, 'X': 2, 'C': 3, 'I': 2}
print('  유형별 차례 수:', {k: kinds[k] for k in target_kind}, '| 합계', sum(kinds.values()),
      '→', '구성표와 일치' if dict(kinds) == target_kind else '구성표와 불일치')
reg_range = {'공식': (9, 11), '약칭': (10, 12), '서술': (8, 10), '영문': (2, 2)}
reg_ok = all(lo <= regs[k] <= hi for k, (lo, hi) in reg_range.items()) and set(regs) == set(reg_range)
print('  표현별 차례 수(S·G·P·X):', {k: regs[k] for k in reg_range}, '| 합계', sum(regs.values()),
      '→', '범위 안' if reg_ok else '범위 밖')
print('  관계 점검 수:', sum(len(c['relations']) for c in cases), '(5개 이상 필요)')

facts = {}
for name in ('facts_A.jsonl', 'facts_B.jsonl', 'facts_C.jsonl'):
    p = os.path.join(FACTS_DIR, name)
    if os.path.exists(p):
        for line in open(p, encoding='utf-8'):
            if line.strip():
                f = json.loads(line); facts[f['id']] = f
bad = [i for i in sorted(fact_ids) if i not in facts or facts[i].get('status') == 'unverified' or i == 'B30']
print(f'  쓴 사실 id {len(fact_ids)}개: {sorted(fact_ids)} → ' + ('모두 사실 목록에 있고 unverified·B30 아님' if not bad else f'문제 {bad}'))

# 약칭 차례: 과제의 facts 에 속한 사실의 aliases 가운데 하나 이상이 질문에 들어 있는지
for c in cases:
    aliases = [a for i in c['facts'] for a in facts[i]['aliases']]
    for t in c['turns']:
        if t.get('register') == '약칭':
            hit = [a for a in aliases if a in t['q']]
            print(f"  약칭 대조 {c['id']} 차례 {t['n']}: {hit if hit else '없음'}")
            if not hit:
                problems.append(f"{c['id']} 차례 {t['n']}: 약칭이 aliases 에 없음")

# 기준값·전제의 사실 목록 대조(G·P·X)
nb = lambda i: facts[i]['numbers']
value_checks = [
    ('W2-01 차례 2 G 최저보험료 19,500원 (B01)', nb('B01')['최저보험료_변경후_원'] == 19500),
    ('W2-02 차례 2 P 소득요건 연 2,000만 원 (B02)', nb('B02')['소득요건_변경후_연_만원'] == 2000),
    ('W2-03 차례 3 G 2022년 1분위 상한액 83만 원 (B06)', nb('B06')['상한액_2022_만원']['1분위'] == 83),
    ('W2-05 차례 4 P 의료급여 선정기준 1인 777,925원 (A04)', nb('A04')['2022년_선정기준_월_원']['의료급여']['1인'] == 777925),
    ('W2-08 차례 3 P 공익활동 월 27만 원·11개월 (B22)', nb('B22')['공익활동_월_활동비_만원'] == 27 and nb('B22')['공익활동_활동기간_개월'] == 11),
    ('W2-11 차례 3 G 모형 3 요건 3일 이상 입원 (B17)', nb('B17')['모형3_요건'].startswith('3일 이상 입원')),
    ('W2-04 차례 4 X 암 본인부담률 실제 5% (B07)', nb('B07')['암_본인부담률_퍼센트'] == 5 and nb('B07')['중증치매_본인부담률_퍼센트'] == 10),
    ('W2-09 차례 2 X 장애등급제 폐지 실제 2019-07-01 (B23)', nb('B23')['시행일'] == '2019-07-01'),
    ('W2-08 차례 2 서술 공익활동 월 30시간 (B22)', nb('B22')['공익활동_월_시간'] == 30),
    ('W2-11 차례 1 대상 연령 만 15세 이상 65세 미만 (B17)', nb('B17')['대상연령'] == '만 15세 이상 만 65세 미만'),
    ('W2-04 차례 3 재난적의료비 50~80%·3,000만 원 (B08)', nb('B08')['지원비율_기초생활수급자·차상위_퍼센트'] == 80 and nb('B08')['연간_지원한도_변경후_만원'] == 3000),
]
for name, ok in value_checks:
    print(f"  기준값 대조 {name}: {'일치' if ok else '불일치'}")
    if not ok:
        problems.append('기준값 불일치: ' + name)

# 질문에 변수명이 들어가지 않았는지
varnames = set(df.columns)
for c in cases:
    for t in c['turns']:
        used = [v for v in varnames if len(v) > 4 and v in t['q']]
        if used:
            problems.append(f"{c['id']} 차례 {t['n']}: 질문에 변수명 {used}")

print('\n[문제 목록]', problems if problems else '없음')
sys.exit(0 if (not problems and n_ok == n_spec) else 1)
