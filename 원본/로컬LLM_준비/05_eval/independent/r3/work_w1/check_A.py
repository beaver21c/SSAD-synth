# -*- coding: utf-8 -*-
"""r3 문항 파일(A.jsonl, H.jsonl) 확인용 스크립트.
- JSON Lines 형식과 필수 항목
- A의 population·numerator·groups[].cond가 DataFrame.eval(engine='python')으로 실행되는지
  (파생 변수 eqinc, hh_dinc, poor는 자료_규약.md 정의로 생성)
- 산출 정의별 칸의 가중하지 않은 관측 수와 억제 예상 여부(민감도 등급별 최소 관측 수: 가 10, 나 20, 다 30)
- 구성 요건별 개수
개인 단위 행은 출력하지 않고 집계만 출력한다.
"""
import json, re, sys, os, collections
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from lib import load, compute, CODEBOOK  # noqa: E402

ITEMS = os.path.join(os.path.dirname(HERE), 'items')
STD = {'sido': 'sido', 'sex': 'gender', 'age3': 'age', 'age6': 'age', 'age10': 'age', 'hs4': 'hnum',
       'inc5': 'p_dinc', 'nhi3': 'nhi_type', 'poor2': 'p_dinc'}
DERIVED = {'eqinc': 'p_dinc', 'hh_dinc': 'p_dinc', 'poor': 'p_dinc'}
MEASURES = {'count', 'rate', 'mean', 'sum', 'quantile', 'share', 'poverty_rate'}
THR = {'가': 10, '나': 20, '다': 30}
TOKEN = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
KEYWORDS = {'and', 'or', 'not', 'in', 'isna', 'notna', 'True', 'False'}

errors = []


def err(msg):
    errors.append(msg)
    print('  [오류]', msg)


def read_jsonl(path):
    rows = []
    with open(path, encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            line = line.rstrip('\n')
            if not line.strip():
                err('%s %d행: 빈 줄' % (os.path.basename(path), i)); continue
            try:
                rows.append(json.loads(line))
            except Exception as e:  # noqa: BLE001
                err('%s %d행: JSON 해석 실패 %r' % (os.path.basename(path), i, e))
    return rows


def tokens(expr):
    return [t for t in TOKEN.findall(expr or '') if t not in KEYWORDS]


cb = pd.read_csv(CODEBOOK, sep='\t')
VARS = set(cb['var'])
PVARS = set(cb.loc[cb['priority'] == 'P', 'var'])
GRADE = dict(zip(cb['var'], cb['sensitivity_grade']))

df = load()
ALLOWED = VARS | set(DERIVED)

A = read_jsonl(os.path.join(ITEMS, 'A.jsonl'))
H = read_jsonl(os.path.join(ITEMS, 'H.jsonl'))
print('문항 수: A %d, H %d' % (len(A), len(H)))


def spec_vars(s):
    """산출 정의에 쓰인 codebook 변수(파생·표준 분류는 원 변수로 환산)."""
    vs = set()
    for e in (s.get('population', ''), s.get('numerator', '')):
        vs |= set(tokens(e))
    vv = s.get('value_var')
    if vv:
        vs.add(vv)
    for b in s.get('by', []):
        if 'std' in b:
            vs.add(b['std'])
        elif 'bins' in b:
            vs.add(b['var'])
        elif 'cat' in b:
            vs.add(b['cat'])
        elif 'groups' in b:
            for g in b['groups']:
                vs |= set(tokens(g['cond']))
    if s['measure'] == 'poverty_rate':
        vs.add('poor')
    out = set()
    for v in vs:
        out.add(STD.get(v, DERIVED.get(v, v)))
    return out


def check_expr(iid, name, expr):
    if expr == '':
        return
    for t in tokens(expr):
        if t not in ALLOWED:
            err('%s %s: 알 수 없는 이름 %s' % (iid, name, t))
    try:
        m = df.eval(expr, engine='python')
        if not (hasattr(m, 'dtype') and len(m) == len(df)):
            err('%s %s: 행 단위 결과가 아님' % (iid, name))
        elif m.fillna(False).astype(bool).sum() == 0:
            err('%s %s: 해당 행 없음' % (iid, name))
    except Exception as e:  # noqa: BLE001
        err('%s %s: eval 실패 %r (%s)' % (iid, name, e, expr))


def suppression(s, t):
    """(상태, 임계값, 표시 칸 수, 전체 칸 수). 상태: none / partial / full"""
    thr = max(THR[GRADE[v]] for v in spec_vars(s) if v in GRADE)
    if s['measure'] in ('rate', 'poverty_rate'):
        ok = (t['n'] >= thr) & (t['n_num'] >= thr) & (t['n_comp'] >= thr)
    else:
        ok = t['n'] >= thr
    nsup = int((~ok).sum()); ncell = len(t)
    if nsup == 1 and ncell >= 2:
        nsup = 2  # 한 줄에 억제 칸이 하나뿐이면 한 칸 더 억제
    shown = ncell - nsup
    state = 'none' if nsup == 0 else ('full' if shown <= 0 else 'partial')
    return state, thr, max(shown, 0), ncell


# ---------------- A 묶음 ----------------
ids = [it.get('id') for it in A]
if ids != ['A%03d' % i for i in range(1, 49)]:
    err('A id가 A001~A048 순서가 아님')
tally = collections.Counter(); persona = collections.Counter()
sup_full, sup_partial, alt_items = [], [], []
rows = []
for it in A:
    iid = it.get('id', '?')
    for k in ('id', 'stratum', 'persona', 'turns', 'expect', 'specs', 'note'):
        if k not in it:
            err('%s: 항목 %s 없음' % (iid, k))
    if it.get('stratum') != 'A' or it.get('expect') != 'compute':
        err('%s: stratum/expect 값' % iid)
    turns = it.get('turns', [])
    if not (isinstance(turns, list) and len(turns) >= 1 and all(isinstance(x, str) and x.strip() for x in turns)):
        err('%s: turns 형식' % iid)
    for q in turns:
        for t in TOKEN.findall(q):
            if t in VARS or t in DERIVED or t in STD and t not in ('sex',):
                err('%s: 질문에 변수명 %s' % (iid, t))
    specs = it.get('specs', [])
    if not specs:
        err('%s: specs 없음' % iid); continue
    alts = [s.get('alt') for s in specs]
    if len(specs) > 1:
        if sorted(alts) != list(range(1, len(specs) + 1)):
            err('%s: alt 번호' % iid)
        alt_items.append(iid)
    states = []
    for s in specs:
        tag = iid + ('/alt%s' % s['alt'] if 'alt' in s else '')
        if s.get('measure') not in MEASURES:
            err('%s: measure %r' % (tag, s.get('measure'))); continue
        if s.get('unit') not in ('person', 'household'):
            err('%s: unit' % tag)
        if s.get('turn') != 1:
            err('%s: turn' % tag)
        if 'population' not in s or 'by' not in s:
            err('%s: population/by 없음' % tag); continue
        check_expr(tag, 'population', s['population'])
        m = s['measure']
        if m == 'rate':
            if not s.get('numerator'):
                err('%s: numerator 없음' % tag)
            else:
                check_expr(tag, 'numerator', s['numerator'])
        elif 'numerator' in s:
            err('%s: rate가 아닌데 numerator' % tag)
        if m in ('mean', 'sum', 'quantile'):
            if s.get('value_var') not in ALLOWED:
                err('%s: value_var %r' % (tag, s.get('value_var')))
        if m == 'share':
            if not (s.get('value_var') in STD or s.get('value_var') in VARS):
                err('%s: share value_var %r' % (tag, s.get('value_var')))
        if m == 'quantile':
            if not (isinstance(s.get('q'), (int, float)) and 0.05 <= s['q'] <= 0.95):
                err('%s: q' % tag)
        elif 'q' in s:
            err('%s: quantile이 아닌데 q' % tag)
        if len(s['by']) > 3:
            err('%s: 분류 기준 4개 이상' % tag)
        for b in s['by']:
            if 'std' in b:
                if b['std'] not in STD:
                    err('%s: std %r' % (tag, b['std']))
            elif 'bins' in b:
                if b.get('var') not in ALLOWED:
                    err('%s: bins var %r' % (tag, b.get('var')))
                if list(b['bins']) != sorted(b['bins']) or len(b.get('labels', [])) != len(b['bins']) + 1:
                    err('%s: bins/labels' % tag)
            elif 'cat' in b:
                if b['cat'] not in VARS:
                    err('%s: cat %r' % (tag, b['cat']))
            elif 'groups' in b:
                if len(b['groups']) < 2:
                    err('%s: groups 1개' % tag)
                for g in b['groups']:
                    check_expr(tag, 'groups.cond[%s]' % g.get('label'), g.get('cond', ''))
            else:
                err('%s: by 형식 %r' % (tag, b))
        try:
            t = compute(df, s)
            if t['value'].isna().any():
                err('%s: 값이 비어 있는 칸' % tag)
            st, thr, shown, ncell = suppression(s, t)
            states.append(st)
            nmin = int(t[[c for c in ('n', 'n_num', 'n_comp') if c in t.columns]].min().min())
            rows.append((tag, m, s['unit'], ncell, shown, thr, nmin, st))
        except Exception as e:  # noqa: BLE001
            err('%s: 산출 실패 %r' % (tag, e))
    s0 = specs[0]
    worst = 'full' if 'full' in states else ('partial' if 'partial' in states else 'none')
    if worst == 'full':
        sup_full.append(iid)
    elif worst == 'partial':
        sup_partial.append(iid)
    persona[it.get('persona')] += 1
    tally['measure:' + s0['measure']] += 1
    usesP = any((set(tokens(s.get('numerator', ''))) | ({s['value_var']} if s.get('value_var') else set())) & PVARS for s in specs)
    tally['P 변수(분자·대상 변수)'] += usesP
    tally['P 변수(대상 집단 포함)'] += any(spec_vars(s) & PVARS for s in specs)
    tally['이용자 지정 구간(bins)'] += any('bins' in b for b in s0['by'])
    tally['조건 집단(groups)'] += any('groups' in b for b in s0['by'])
    tally['가구 단위'] += s0['unit'] == 'household'
    tally['분류 기준 2개'] += len(s0['by']) == 2
    tally['분류 기준 없음(단일 값)'] += len(s0['by']) == 0
    tally['조건 3개 이상(서로 다른 변수 3개 이상)'] += len(set(tokens(s0['population']))) >= 3
    tally['시도 한정'] += 'sido' in tokens(s0['population'])

print('\n[산출 정의별 칸 수와 관측 수]')
print(pd.DataFrame(rows, columns=['spec', 'measure', 'unit', '칸', '표시 칸', '임계', '최소 n', '억제']).to_string(index=False))

REQ = [('P 변수(분자·대상 변수)', 24), ('measure:rate', 16), ('measure:count', 6), ('measure:mean', 8), ('measure:sum', 3),
       ('measure:quantile', 4), ('measure:share', 4), ('measure:poverty_rate', 2), ('이용자 지정 구간(bins)', 8),
       ('조건 집단(groups)', 5), ('가구 단위', 4), ('분류 기준 2개', 3), ('분류 기준 없음(단일 값)', 10),
       ('조건 3개 이상(서로 다른 변수 3개 이상)', 6), ('시도 한정', 4)]
print('\n[구성 요건]')
for k, need in REQ:
    ok = tally[k] >= need
    print('  %-40s %3d (최소 %d) %s' % (k, tally[k], need, '충족' if ok else '미달'))
    if not ok:
        err('구성 요건 미달: ' + k)
print('  참고: P 변수(대상 집단 포함)', tally['P 변수(대상 집단 포함)'])
print('  이용자 유형:', dict(persona))
print('  alt 문항:', alt_items)
print('  전 칸 억제 예상:', sup_full)
print('  일부 칸 억제 예상:', sup_partial)
if not (4 <= len(sup_full) + len(sup_partial) <= 6):
    err('억제 예상 문항 수가 4~6개가 아님: %d' % (len(sup_full) + len(sup_partial)))
if len(A) - len(sup_full) < 40:
    err('표시되는 칸이 있는 문항이 부족')

# ---------------- H 묶음 ----------------
if [it.get('id') for it in H] != ['H%02d' % i for i in range(1, 9)]:
    err('H id가 H01~H08 순서가 아님')
for it in H:
    iid = it.get('id', '?')
    for k in ('id', 'stratum', 'persona', 'turns', 'expect', 'note'):
        if k not in it:
            err('%s: 항목 %s 없음' % (iid, k))
    if it.get('stratum') != 'H' or it.get('expect') != 'ask_or_assume':
        err('%s: stratum/expect 값' % iid)
    if 'specs' in it:
        err('%s: specs가 있음' % iid)
    for q in it.get('turns', []):
        for t in TOKEN.findall(q):
            if t in VARS:
                err('%s: 질문에 변수명 %s' % (iid, t))
print('\nH 이용자 유형:', dict(collections.Counter(it.get('persona') for it in H)))

# ---------------- note에 적은 사실 확인(집계) ----------------
facts = {
    '의원 외래 내원일수>=1 ≡ 요양급여비용 값 있음': bool(((df.nhi_out_clinic_dur >= 1) == df.nhi_out_clinic_amt.notna()).all()),
    '교육활동지원비>0 ≡ 교육급여 수급권(연간)': bool(((df.p_nbls_edu_amt1 > 0) == (df.nbls_edu_yn1 == 1)).all()),
    '군인연금 보험료: p_ 변수 = 직역연금 변수': bool(np.isclose(df.p_milp_premium_amt, df.milp_premium_amt.fillna(0)).all()),
    '장애수당: p_ 변수 = 급여액 변수': bool(np.isclose(df.p_disp_bn_amt, df.disp_bn_amt.fillna(0)).all()),
    '사학연금 보험료: p_ 변수 = 직역연금 변수': bool(np.isclose(df.p_privschp_premium_amt, df.privschp_premium_amt.fillna(0)).all()),
    '일용소득 두 변수는 값이 다름(최대 차이 1천원 미만)': bool(0 < (df.p_dainc - df.dainc_sum.fillna(0)).abs().max() < 1000),
    '종합장애정도 = 주장애정도': bool((df.dis_grade_1.fillna(-1) == df.dis_grade_2.fillna(-1)).all()),
    '공적연금 수령액>0 ≡ 값 있음': bool(((df.pubpen_inc > 0) == df.pubpen_inc.notna()).all()),
    '근로장려 대상 ≡ 심사금액 값 있음': bool(((df.itc_yn == 1) == df.itc_amt.notna()).all()),
    '방과후 자유수강권 지원자는 모두 7~18세': bool(df.loc[df.pubedu_aftsch_yn == 1, 'age'].between(7, 18).all()),
    '방문요양 이용자의 등급은 1~5등급': bool(df.loc[df.ltcare_visit_yn == 1, 'ltcare_grade'].isin([1, 2, 3, 4, 5]).all()),
}
print('\n[note에 적은 사실]')
for k, v in facts.items():
    print('  %s: %s' % (k, v))
    if not v:
        err('사실 확인 실패: ' + k)

print('\n오류 %d건' % len(errors))
sys.exit(1 if errors else 0)
