# -*- coding: utf-8 -*-
"""A.jsonl·H.jsonl 확인용 스크립트(독립 문항 작성자 작성).

확인 내용
 1) 두 파일이 JSON Lines로 읽히는지, 공통 항목이 양식에 맞는지
 2) A의 모든 population·numerator·groups[].cond가 DataFrame.query로 실행되는지
    (파생 변수 eqinc·hh_dinc·poor는 자료_규약.md의 정의로 생성)
 3) 산출 정의별 칸의 가중하지 않은 관측 수(비율은 분자·분모·여집합의 최솟값)
 4) 구성 요건의 개수
 5) 질문 문장에 변수명이 들어 있지 않은지, 쓰인 변수가 codebook.tsv에 있는지

실행: /mnt/share/행정데이터_set/.venv/bin/python _check_A.py
개인 단위 행은 출력하지 않고 집계만 출력함.
"""
import json
import os
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
INPUTS = os.path.join(os.path.dirname(HERE), 'inputs')
PQ = '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'

STD_NAMES = ['sido', 'sex', 'age3', 'age6', 'age10', 'hs4', 'inc5', 'nhi3', 'poor2']
DERIVED = ['eqinc', 'hh_dinc', 'poor']
MEASURES = ['count', 'rate', 'mean', 'sum', 'quantile', 'share', 'poverty_rate']
PERSONAS = ['중앙부처 정책 담당자', '지자체 복지 담당자', '연구자', '통계·보도 대응 담당자', '국회 자료 요구 대응 담당자']
GRADE_MIN = {'가': 10, '나': 20, '다': 30}
REQ = [  # (이름, 최소 개수)
    ('우선(P) 변수를 분자·대상 변수로 사용', 26), ('비율', 16), ('인원·가구 수', 6), ('평균', 8), ('합계', 3),
    ('분위수', 4), ('구성비', 4), ('상대 빈곤율', 2), ('이용자 지정 구간(bins)', 8), ('조건 집단(groups)', 4),
    ('가구 단위', 4), ('분류 기준 2개', 3), ('분류 기준 없는 단일 값', 10), ('조건 3개 이상 대상 집단', 6),
]
errors = []


def err(msg):
    errors.append(msg)
    print('  [오류]', msg)


def read_jsonl(name):
    items = []
    with open(os.path.join(HERE, name), encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                err(f'{name} {i}행: 빈 줄')
                continue
            try:
                items.append(json.loads(line))
            except Exception as e:  # noqa
                err(f'{name} {i}행: JSON 해석 실패 {e}')
    return items


def wq(v, w, q):
    """가중 분위수: 오름차순 누적 가중치가 전체의 q배에 처음 이르는 값."""
    v = np.asarray(v, float); w = np.asarray(w, float)
    o = np.argsort(v, kind='mergesort'); v = v[o]; w = w[o]
    c = np.cumsum(w)
    return v[min(np.searchsorted(c, c[-1] * q, side='left'), len(v) - 1)]


def load():
    df = pd.read_parquet(PQ)
    df['hh_dinc'] = df.groupby('hid')['p_dinc'].transform('sum')
    df['eqinc'] = df['hh_dinc'] / np.sqrt(df['hnum'])
    med = wq(df['eqinc'], df['indwgt'], 0.5)
    df['poor'] = (df['eqinc'] < 0.5 * med).astype(int)
    th = [wq(df['eqinc'], df['indwgt'], q) for q in (0.2, 0.4, 0.6, 0.8)]
    df['_inc5'] = (1 + sum((df['eqinc'] >= t).astype(int) for t in th)).astype(str)
    df['_sido'] = df['sido'].astype(int).astype(str)
    df['_sex'] = df['gender'].map({1: '남', 2: '여'})
    df['_age3'] = pd.cut(df['age'], [-1, 17, 64, 999], labels=['0~17세', '18~64세', '65세 이상']).astype(str)
    df['_age6'] = pd.cut(df['age'], [-1, 17, 34, 49, 64, 74, 999],
                         labels=['0~17세', '18~34세', '35~49세', '50~64세', '65~74세', '75세 이상']).astype(str)
    df['_age10'] = (np.minimum(df['age'] // 10 * 10, 80)).astype(int).astype(str)
    df['_hs4'] = np.minimum(df['hnum'], 4).astype(int).astype(str)
    df['_nhi3'] = df['nhi_type'].map({1: '지역가입', 2: '지역가입', 5: '직장가입', 6: '직장가입'}).fillna('의료급여')
    df['_poor2'] = df['poor'].map({1: '빈곤', 0: '비빈곤'})
    return df


def by_key(d, b, where):
    if 'std' in b:
        if b['std'] not in STD_NAMES:
            err(f'{where}: 표준 분류 이름 오류 {b["std"]}')
        return d['_' + b['std']]
    if 'var' in b:
        if len(b['labels']) != len(b['bins']) + 1 or list(b['bins']) != sorted(b['bins']):
            err(f'{where}: bins·labels 개수 또는 순서 오류')
        idx = np.searchsorted(np.asarray(b['bins'], float), d[b['var']].astype(float).values, side='right')
        s = pd.Series([b['labels'][i] for i in idx], index=d.index, dtype=object)
        s[d[b['var']].isna()] = np.nan
        return s
    if 'cat' in b:
        return d[b['cat']].map(lambda x: np.nan if pd.isna(x) else (str(int(x)) if isinstance(x, (int, float, np.integer, np.floating)) else str(x))).astype(object)
    if 'groups' in b:
        s = pd.Series(np.nan, index=d.index, dtype=object)
        for g in b['groups']:
            m = d.index.isin(d.query(g['cond']).index)  # DataFrame.query 실행 확인
            if s[m].notna().any():
                err(f'{where}: 조건 집단이 서로 겹침({g["label"]})')
            s[m] = g['label']
        return s
    err(f'{where}: by 형식 오류 {b}')
    return pd.Series(np.nan, index=d.index, dtype=object)


def evaluate(df, sp, where):
    """[(칸 이름, 값, 관측 수)] — 비율·빈곤율의 관측 수는 (분자, 분모, 여집합)."""
    unit = sp.get('unit', 'person')
    d = df[df['head'] == 1] if unit == 'household' else df
    wcol = 'hhwgt' if unit == 'household' else 'indwgt'
    if sp.get('population'):
        d = d.query(sp['population'])  # DataFrame.query 실행 확인
    keys = [by_key(d, b, where).rename(f'by{i}') for i, b in enumerate(sp.get('by', []))]
    if keys:
        d = d.assign(**{k.name: k for k in keys}).dropna(subset=[k.name for k in keys])
        parts = [(k if isinstance(k, tuple) else (k,), x) for k, x in d.groupby([k.name for k in keys], sort=True)]
    else:
        parts = [((), d)]
    m = sp['measure']
    rows = []
    for k, x in parts:
        w = x[wcol]
        if m == 'count':
            rows.append((k, w.sum(), len(x)))
        elif m in ('rate', 'poverty_rate'):
            num = x.index.isin(x.query(sp['numerator']).index) if m == 'rate' else (x['poor'] == 1).values
            rows.append((k, 100 * w[num].sum() / w.sum(), (int(num.sum()), len(x), int(len(x) - num.sum()))))
        elif m in ('mean', 'sum', 'quantile'):
            v = x[sp['value_var']].astype(float); ok = v.notna()
            if not ok.any():
                rows.append((k, np.nan, 0)); continue
            val = ((v[ok] * w[ok]).sum() / w[ok].sum() if m == 'mean' else
                   (v[ok] * w[ok]).sum() if m == 'sum' else wq(v[ok], w[ok], sp['q']))
            rows.append((k, val, int(ok.sum())))
        elif m == 'share':
            vv = sp['value_var']
            s = x['_' + vv] if vv in STD_NAMES else by_key(x, {'cat': vv}, where)
            ok = s.notna(); tot = w[ok].sum()
            for c, xx in x[ok].groupby(s[ok]):
                rows.append((k + (c,), 100 * xx[wcol].sum() / tot, len(xx)))
    return rows


def cell_n(n):
    return min(n) if isinstance(n, tuple) else n


def names_in(expr, known):
    return sorted({t for t in re.findall(r'[A-Za-z_][A-Za-z0-9_]*', expr or '') if t in known})


def spec_vars(sp, known):
    vs = set(names_in(sp.get('population', ''), known)) | set(names_in(sp.get('numerator', ''), known))
    if sp.get('value_var') and sp['value_var'] not in STD_NAMES:
        vs.add(sp['value_var'])
    for b in sp.get('by', []):
        if 'var' in b: vs.add(b['var'])
        if 'cat' in b: vs.add(b['cat'])
        if 'std' in b: vs |= {'sido': {'sido'}, 'sex': {'gender'}, 'age3': {'age'}, 'age6': {'age'}, 'age10': {'age'},
                              'hs4': {'hnum'}, 'inc5': {'p_dinc'}, 'nhi3': {'nhi_type'}, 'poor2': {'p_dinc'}}[b['std']]
        for g in b.get('groups', []):
            vs |= set(names_in(g['cond'], known))
    if sp['measure'] == 'poverty_rate' or sp.get('value_var') == 'inc5':
        vs.add('p_dinc')
    return vs


def main():
    cb = pd.read_csv(os.path.join(INPUTS, 'codebook.tsv'), sep='\t', dtype=str).fillna('')
    cbvars = set(cb['var'])
    pvars = set(cb.loc[cb['priority'] == 'P', 'var'])
    grade = dict(zip(cb['var'], cb['sensitivity_grade']))
    known = cbvars | set(DERIVED)

    print('== 1. 파일 읽기 ==')
    A = read_jsonl('A.jsonl'); H = read_jsonl('H.jsonl')
    print(f'  A {len(A)}문항, H {len(H)}문항')
    if len(A) != 48: err('A 문항 수가 48이 아님')
    if len(H) != 8: err('H 문항 수가 8이 아님')
    if [it.get('id') for it in A] != ['A%03d' % i for i in range(1, len(A) + 1)]: err('A id 순서 오류')
    if [it.get('id') for it in H] != ['H%02d' % i for i in range(1, len(H) + 1)]: err('H id 순서 오류')
    for it in A + H:
        for k in ('id', 'stratum', 'persona', 'turns', 'expect', 'note'):
            if not it.get(k): err(f'{it.get("id")}: {k} 없음')
        if it.get('persona') not in PERSONAS: err(f'{it["id"]}: persona 값 오류')
        if not (isinstance(it.get('turns'), list) and all(isinstance(t, str) and t.strip() for t in it['turns'])):
            err(f'{it["id"]}: turns 형식 오류')
        used = [t for q in it.get('turns', []) for t in re.findall(r'[A-Za-z_][A-Za-z0-9_]*', q) if t in known and len(t) > 2]
        if used: err(f'{it["id"]}: 질문에 변수명 {used}')
    for it in A:
        if it['stratum'] != 'A' or it['expect'] != 'compute' or not it.get('specs'): err(f'{it["id"]}: stratum·expect·specs 오류')
    for it in H:
        if it['stratum'] != 'H' or it['expect'] != 'ask_or_assume' or 'specs' in it: err(f'{it["id"]}: stratum·expect·specs 오류')
    if len({it['turns'][0] for it in A + H}) != len(A) + len(H): err('질문 문장 중복')

    print('== 2. 산출 정의 실행(DataFrame.query) ==')
    df = load()
    feat = {}
    for it in A:
        f = dict(P=False, measure=None, bins=False, groups=False, hh=False, by2=False, single=True, cond3=False,
                 alt=len(it['specs']) > 1, min_n=None, thr=10, cells=0, low=0)
        measures = set()
        for j, sp in enumerate(it['specs']):
            where = f'{it["id"]} spec{j + 1}'
            m = sp.get('measure'); measures.add(m)
            if m not in MEASURES: err(f'{where}: measure 오류'); continue
            if sp.get('unit', 'person') not in ('person', 'household'): err(f'{where}: unit 오류')
            if sp.get('turn') != 1: err(f'{where}: turn 오류')
            if (m == 'rate') != ('numerator' in sp): err(f'{where}: numerator는 rate에만 씀')
            if (m in ('mean', 'sum', 'quantile', 'share')) != ('value_var' in sp): err(f'{where}: value_var 유무 오류')
            if (m == 'quantile') != ('q' in sp): err(f'{where}: q 유무 오류')
            if m == 'quantile' and not 0.05 <= sp['q'] <= 0.95: err(f'{where}: q 범위 오류')
            if len(it['specs']) > 1 and 'alt' not in sp: err(f'{where}: alt 없음')
            if len(sp.get('by', [])) > 3: err(f'{where}: 분류 기준 4개 이상')
            vs = spec_vars(sp, known)
            unknown = [t for e in [sp.get('population', ''), sp.get('numerator', '')] + [g['cond'] for b in sp.get('by', []) for g in b.get('groups', [])]
                       for t in re.findall(r'[A-Za-z_][A-Za-z0-9_]*', e)
                       if t not in known and t not in ('and', 'or', 'not', 'in', 'isna', 'notna')]
            if unknown: err(f'{where}: codebook에 없는 이름 {unknown}')
            if sp.get('value_var') and sp['value_var'] not in known and sp['value_var'] not in STD_NAMES: err(f'{where}: value_var가 codebook에 없음')
            try:
                rows = evaluate(df, sp, where)
            except Exception as e:  # noqa
                err(f'{where}: 실행 실패 {type(e).__name__}: {e}'); continue
            if not rows or any(pd.isna(v) for _, v, _ in rows): err(f'{where}: 빈 결과 또는 결측 값')
            ns = [cell_n(n) for _, _, n in rows]
            thr = max([GRADE_MIN.get(grade.get(v, '가'), 10) for v in vs] + [10])
            f['min_n'] = min(ns) if f['min_n'] is None else min(f['min_n'], min(ns))
            f['thr'] = max(f['thr'], thr); f['cells'] = max(f['cells'], len(rows)); f['low'] = max(f['low'], sum(n < thr for n in ns))
            target = set(names_in(sp.get('numerator', ''), known)) | ({sp['value_var']} if sp.get('value_var') else set())
            f['P'] |= bool(target & pvars)
            f['bins'] |= any('bins' in b for b in sp.get('by', []))
            f['groups'] |= any('groups' in b for b in sp.get('by', []))
            f['hh'] |= sp.get('unit') == 'household'
            f['by2'] |= len(sp.get('by', [])) == 2
            f['single'] &= len(sp.get('by', [])) == 0
            f['cond3'] |= len(names_in(sp.get('population', ''), known)) >= 3
        if len(measures) != 1: err(f'{it["id"]}: alt 사이 measure 불일치')
        f['measure'] = next(iter(measures))
        f['flag'] = '억제' in it['note']
        feat[it['id']] = f
        print(f'  {it["id"]} {f["measure"]:<12} 칸 {f["cells"]:>2} 최소 관측 {f["min_n"]:>5} (등급 기준 {f["thr"]}, 기준 미만 칸 {f["low"]})'
              + (' P' if f['P'] else '') + (' alt' if f['alt'] else '') + (' [억제 예상]' if f['flag'] else ''))

    print('== 3. 억제 예상 문항 ==')
    flagged = [k for k, f in feat.items() if f['flag']]
    for k, f in feat.items():
        if f['flag'] and not (f['min_n'] < f['thr']): err(f'{k}: 억제 예상이라 적었으나 등급 기준 이상(최소 {f["min_n"]}, 기준 {f["thr"]})')
        if not f['flag'] and f['min_n'] < 30: err(f'{k}: 표시 대상인데 관측 30건 미만 칸 있음(최소 {f["min_n"]})')
    print(f'  억제 예상 {len(flagged)}문항: {", ".join(flagged)}')
    if not 4 <= len(flagged) <= 6: err('억제 예상 문항 수가 4~6이 아님')

    print('== 4. 구성 요건 ==')
    got = {
        '우선(P) 변수를 분자·대상 변수로 사용': sum(f['P'] for f in feat.values()),
        '비율': sum(f['measure'] == 'rate' for f in feat.values()),
        '인원·가구 수': sum(f['measure'] == 'count' for f in feat.values()),
        '평균': sum(f['measure'] == 'mean' for f in feat.values()),
        '합계': sum(f['measure'] == 'sum' for f in feat.values()),
        '분위수': sum(f['measure'] == 'quantile' for f in feat.values()),
        '구성비': sum(f['measure'] == 'share' for f in feat.values()),
        '상대 빈곤율': sum(f['measure'] == 'poverty_rate' for f in feat.values()),
        '이용자 지정 구간(bins)': sum(f['bins'] for f in feat.values()),
        '조건 집단(groups)': sum(f['groups'] for f in feat.values()),
        '가구 단위': sum(f['hh'] for f in feat.values()),
        '분류 기준 2개': sum(f['by2'] for f in feat.values()),
        '분류 기준 없는 단일 값': sum(f['single'] for f in feat.values()),
        '조건 3개 이상 대상 집단': sum(f['cond3'] for f in feat.values()),
    }
    for name, need in REQ:
        ok = got[name] >= need
        print(f'  {"충족" if ok else "미달"}  {name}: {got[name]} (최소 {need})')
        if not ok: err(f'구성 요건 미달: {name}')
    print(f'  alt 병기 문항: {sum(f["alt"] for f in feat.values())}')
    per = pd.Series([it['persona'] for it in A]).value_counts()
    print('  이용자 유형(A): ' + ', '.join(f'{k} {v}' for k, v in per.items()))
    print('  이용자 유형(H): ' + ', '.join(f'{k} {v}' for k, v in pd.Series([it['persona'] for it in H]).value_counts().items()))
    ln = pd.Series([len(it['turns'][0]) for it in A])
    print(f'  A 질문 길이(자): 최소 {ln.min()}, 중위 {int(ln.median())}, 최대 {ln.max()}')

    print('== 결과 ==')
    print('  오류 없음' if not errors else f'  오류 {len(errors)}건')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
