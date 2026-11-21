# -*- coding: utf-8 -*-
"""작업자 w2 확인용: C·F·G 문항 파일의 형식, 산출 정의의 실행 가능성, 참값과 표시 가능 칸을 점검.

실행: /mnt/share/행정데이터_set/.venv/bin/python check_CFG.py
집계값과 관측 수만 출력함(개인 단위 행은 출력하지 않음).
"""
import json, os, re, sys, collections
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load, compute, shown

ITEMS = '/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r2/items'
CODEBOOK = '/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/inputs/codebook.tsv'
MIN_N = 30
MEASURES = {'count', 'rate', 'mean', 'sum', 'quantile', 'share', 'poverty_rate'}
STD = {'sido', 'sex', 'age3', 'age6', 'age10', 'hs4', 'inc5', 'nhi3', 'poor2'}
DERIVED = {'eqinc', 'hh_dinc', 'poor'}
errors, warns = [], []


def err(i, msg):
    errors.append(f'{i}: {msg}')


def read_jsonl(name):
    out = []
    with open(os.path.join(ITEMS, name), encoding='utf-8') as f:
        for ln, line in enumerate(f, 1):
            if not line.strip():
                err(name, f'{ln}행이 비어 있음'); continue
            try:
                out.append(json.loads(line))
            except Exception as e:
                err(name, f'{ln}행 JSON 오류: {e}')
    return out


def conds_of(spec):
    cs = [('population', spec.get('population', ''))]
    if 'numerator' in spec:
        cs.append(('numerator', spec['numerator']))
    for b in spec.get('by', []):
        for g in b.get('groups', []):
            cs.append(('groups.cond', g['cond']))
    return cs


def check_spec(iid, spec, df, cbvars):
    """산출 정의 하나를 점검하고 (표시값 목록, 표시 가능 칸 수, 전체 칸 수)를 돌려줌."""
    m = spec.get('measure')
    if m not in MEASURES:
        err(iid, f'measure 값 오류: {m}'); return None
    if spec.get('unit', 'person') not in ('person', 'household'):
        err(iid, 'unit 값 오류')
    if m == 'rate' and not spec.get('numerator'):
        err(iid, 'rate에 numerator 없음')
    if m == 'count' and 'numerator' in spec:
        err(iid, 'count에 numerator가 있음')
    if m in ('mean', 'sum', 'quantile', 'share') and spec.get('value_var') not in df.columns:
        err(iid, f"value_var 오류: {spec.get('value_var')}")
    if m == 'quantile' and not (0.05 <= spec.get('q', -1) <= 0.95):
        err(iid, 'q 범위 오류')
    for b in spec.get('by', []):
        if 'std' in b and b['std'] not in STD:
            err(iid, f"표준 분류 이름 오류: {b['std']}")
        if 'var' in b and len(b['labels']) != len(b['bins']) + 1:
            err(iid, '구간 수와 이름 수가 맞지 않음')
        if 'cat' in b and b['cat'] not in cbvars:
            err(iid, f"범주형 변수 오류: {b['cat']}")
    # 조건식 실행(DataFrame.eval, engine='python')과 변수명 점검
    for kind, c in conds_of(spec):
        if c.strip() == '':
            continue
        try:
            r = df.eval(c, engine='python')
            if not (hasattr(r, 'dtype') and len(r) == len(df)):
                err(iid, f'{kind} 조건식이 행 단위 참·거짓을 돌려주지 않음: {c}')
        except Exception as e:
            err(iid, f'{kind} 조건식 실행 오류: {c} → {e}')
        for tok in set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', c)) - {'and', 'or', 'not', 'in', 'isna', 'notna'}:
            if tok not in cbvars and tok not in DERIVED:
                err(iid, f'{kind} 조건식에 코드북에 없는 이름: {tok}')
    try:
        rows = compute(spec, df)
    except Exception as e:
        err(iid, f'참값 계산 오류: {e}'); return None
    vals, n_ok = [], 0
    for lab, v, n, aux in rows:
        ok = n >= MIN_N and (aux is None or (aux[0] >= MIN_N and aux[1] >= MIN_N))
        n_ok += ok
        vals.append(('/'.join(lab), shown(spec, float(v)) if v == v else None, n, aux, ok))
    if n_ok == 0:
        err(iid, '표시되는 칸이 없음(모든 칸의 관측 수가 30건 미만)')
    elif n_ok < len(rows):
        warns.append(f'{iid}: 표시 {n_ok}/{len(rows)}칸(일부 칸 억제)')
    return vals, n_ok, len(rows)


def fmt(vals):
    return '; '.join(f"{lab + '=' if lab else ''}{v:,} [n={n}{'' if aux is None else ', 분자 ' + str(aux[0]) + '·여집합 ' + str(aux[1])}]{'' if ok else ' (억제)'}"
                     for lab, v, n, aux, ok in vals)


def strip_code(text):
    return re.sub(r'```.*?```', ' ', text, flags=re.S)


def check_no_varnames(iid, turns, cbvars):
    for t in turns:
        toks = set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', strip_code(t)))
        hit = toks & (cbvars | DERIVED | STD)
        if hit:
            err(iid, f'질문 문장에 변수명이 있음: {sorted(hit)}')


def common_item_checks(it, stratum, cbvars):
    iid = it.get('id', '?')
    for k in ('id', 'stratum', 'persona', 'turns', 'expect', 'specs', 'note'):
        if k not in it:
            err(iid, f'항목 없음: {k}')
    if it.get('stratum') != stratum:
        err(iid, 'stratum 오류')
    if it.get('expect') != 'compute':
        err(iid, 'expect가 compute가 아님')
    if not it.get('specs'):
        err(iid, 'specs 없음')
    check_no_varnames(iid, it.get('turns', []), cbvars)


def one_span_diff(a, b):
    """두 문장의 공통 접두·접미를 뺀 서로 다른 부분."""
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    j = 0
    while j < min(len(a), len(b)) - i and a[-1 - j] == b[-1 - j]:
        j += 1
    return a[i:len(a) - j], b[i:len(b) - j]


def main():
    df = load()
    cbvars = set(pd.read_csv(CODEBOOK, sep='\t')['var'])
    C, F, G = read_jsonl('C.jsonl'), read_jsonl('F.jsonl'), read_jsonl('G.jsonl')
    print(f'문항 수: C {len(C)}, F {len(F)}, G {len(G)}')
    ids = [it['id'] for it in C + F + G]
    if len(ids) != len(set(ids)):
        err('전체', 'id 중복')

    # ---------------- C
    print('\n[C] 최소 차이 쌍')
    if [it['id'] for it in C] != [f'C{k:02d}{s}' for k in range(1, 16) for s in 'ab']:
        err('C', 'id 구성이 C01a…C15b가 아님')
    res = {}
    for it in C:
        common_item_checks(it, 'C', cbvars)
        if it.get('pair') != it['id'][:3] or not it.get('diff'):
            err(it['id'], 'pair·diff 항목 오류')
        if len(it['turns']) != 1 or len(it['specs']) != 1:
            err(it['id'], 'turns·specs는 1개여야 함')
        res[it['id']] = check_spec(it['id'], it['specs'][0], df, cbvars)
    by_id = {it['id']: it for it in C}
    for k in range(1, 16):
        p = f'C{k:02d}'
        a, b = by_id[p + 'a'], by_id[p + 'b']
        if a['diff'] != b['diff']:
            err(p, 'diff가 쌍 안에서 다름')
        da, db = one_span_diff(a['turns'][0], b['turns'][0])
        ra, rb = res[p + 'a'], res[p + 'b']
        if ra is None or rb is None:
            continue
        va = [(lab, v) for lab, v, n, aux, ok in ra[0]]
        vb = [(lab, v) for lab, v, n, aux, ok in rb[0]]
        same = (va == vb) if (a['specs'][0].get('by') or b['specs'][0].get('by')) else (va[0][1] == vb[0][1])
        if same:
            err(p, '두 참값이 표시 자릿수에서 같음')
        print(f"{p} [{a['diff']}] 다른 부분: 「{da}」 ↔ 「{db}」")
        print(f'    a: {fmt(ra[0])}')
        print(f'    b: {fmt(rb[0])}')

    # ---------------- F
    print('\n[F] 이어 묻는 대화')
    if [it['id'] for it in F] != [f'F{k:02d}' for k in range(1, 11)]:
        err('F', 'id 구성이 F01…F10이 아님')
    for it in F:
        common_item_checks(it, 'F', cbvars)
        nt = len(it['turns'])
        if nt not in (2, 3):
            err(it['id'], 'turns가 2~3개가 아님')
        turns_in_specs = [s.get('turn') for s in it['specs']]
        if sorted(turns_in_specs) != list(range(1, nt + 1)):
            err(it['id'], f'specs의 turn 구성 오류: {turns_in_specs}')
        print(f"{it['id']} ({nt}차례)")
        for s in it['specs']:
            r = check_spec(f"{it['id']}-t{s.get('turn')}", s, df, cbvars)
            if r:
                print(f"    t{s['turn']} {s['measure']}: {fmt(r[0])}")

    # ---------------- G
    print('\n[G] 코드 확인 요청')
    if [it['id'] for it in G] != [f'G{k:02d}' for k in range(1, 13)]:
        err('G', 'id 구성이 G01…G12가 아님')
    for it in G:
        common_item_checks(it, 'G', cbvars)
        if not it.get('defect'):
            err(it['id'], 'defect 항목 없음')
        blocks = re.findall(r'```python\n(.*?)```', it['turns'][0], flags=re.S)
        if len(blocks) != 1 or 'import ssda' not in blocks[0]:
            err(it['id'], '```python 코드 블록(import ssda 포함)이 1개가 아님')
        r = check_spec(it['id'], it['specs'][0], df, cbvars)
        if r:
            print(f"{it['id']} [{it['defect']}] {it['specs'][0]['measure']}: {fmt(r[0])}")

    # ---------------- 요약
    print('\n[요약]')
    print('C 차이 종류:', dict(collections.Counter(it['diff'] for it in C if it['id'].endswith('a'))))
    print('F 차례 수:', dict(collections.Counter(len(it['turns']) for it in F)))
    print('G 결함 종류:', dict(collections.Counter(it['defect'] for it in G)))
    print('화자:', dict(collections.Counter(it['persona'] for it in C + F + G)))
    for w in warns:
        print('주의', w)
    if errors:
        print(f'\n오류 {len(errors)}건')
        for e in errors:
            print('  -', e)
        sys.exit(1)
    print('\n오류 없음')


if __name__ == '__main__':
    main()
