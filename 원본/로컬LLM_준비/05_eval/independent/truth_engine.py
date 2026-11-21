#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""독립 검증의 참값 계산기 — 문항의 산출 정의(specs)를 분석 자료에서 직접 계산한다(pandas·numpy 만 쓰고 분석 함수 ssda 는 쓰지 않는다).

  python 05_eval/independent/truth_engine.py                 # items/*.jsonl 의 산출 정의 전부 → truth/truth.json
산출  truth/truth.json  {문항 id: [{turn, alt, measure, unit, cells: [{labels, value, n, n_num, w, w_num}], overall: {...}}]}
      value 는 반올림하지 않은 값(비율은 %, 금액은 원). n 은 가중하지 않은 관측 수(비율은 분모), n_num 은 분자의 관측 수.
정의는 inputs/자료_규약.md 를 따른다(가중치, 가구 단위, 균등화 소득, 소득 5분위, 상대 빈곤, 가중 분위수).
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BASE = Path(os.environ.get('INDEP_DIR') or HERE)      # 차수별 폴더(items, truth). inputs 는 공용
DATA = os.environ.get('SSDA_DATA', '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet')
SIDO = ['서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종', '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주']
_D = None
_STD = {}
_CB = None


def codebook():
    global _CB
    if _CB is None:
        _CB = pd.read_csv(HERE / 'inputs' / 'codebook.tsv', sep='\t', dtype=str).fillna('').set_index('var')
    return _CB


def data():
    """분석 자료와 파생 변수(자료_규약.md 의 정의)."""
    global _D
    if _D is not None:
        return _D
    d = pd.read_parquet(DATA)
    w = d['indwgt'].astype(float).values
    hh = d.groupby('hid')['p_dinc'].transform('sum').astype(float).values
    eq = hh / np.sqrt(d['hnum'].astype(float).values)
    o = np.argsort(eq, kind='stable'); cw = np.cumsum(w[o]); T = cw[-1]
    wq = lambda q: eq[o][min(np.searchsorted(cw, T * q), len(eq) - 1)]      # 가중 분위수: 누적 가중치가 전체의 q 배에 처음 이르는 값
    med = wq(.5); cuts = [wq(q) for q in (.2, .4, .6, .8)]
    d = d.copy()
    d['eqinc'] = eq; d['hh_dinc'] = hh; d['poor'] = (eq < 0.5 * med).astype(int)
    age = d['age'].astype(int).values
    _STD.update({
        'sido': (d['sido'].astype(int).values - 1, SIDO),
        'sex': (d['gender'].astype(int).values - 1, ['남', '여']),
        'age3': (np.digitize(age, [18, 65]), ['0~17세', '18~64세', '65세 이상']),
        'age6': (np.digitize(age, [18, 35, 50, 65, 75]), ['0~17세', '18~34세', '35~49세', '50~64세', '65~74세', '75세 이상']),
        'age10': (np.minimum(age // 10, 8), ['0~9세', '10~19세', '20~29세', '30~39세', '40~49세', '50~59세', '60~69세', '70~79세', '80세 이상']),
        'hs4': (np.minimum(d['hnum'].astype(int).values, 4) - 1, ['1인', '2인', '3인', '4인 이상']),
        'inc5': (np.digitize(eq, cuts), ['1분위', '2분위', '3분위', '4분위', '5분위']),
        'nhi3': (np.where(d['nhi_type'].isin([1, 2]).values, 0, np.where(d['nhi_type'].isin([5, 6]).values, 1, 2)), ['지역가입', '직장가입', '의료급여']),
        'poor2': ((eq < 0.5 * med).astype(int), ['비빈곤', '빈곤']),
    })
    _D = d
    return d


def mask(expr):
    d = data()
    if not expr or not str(expr).strip():
        return np.ones(len(d), bool)
    m = d.eval(expr, engine='python')
    return np.asarray(pd.Series(m).fillna(False), dtype=bool)          # 결측과의 비교는 거짓으로 둠


def partition(b):
    """분류 기준 1개 → (칸 번호 배열(해당 없음 −1), 항목 이름). 조건 집단(groups)은 여기서 다루지 않는다."""
    d = data()
    if 'std' in b:
        codes, labs = _STD[b['std']]
        return np.asarray(codes), list(labs)
    if 'bins' in b:
        x = d[b['var']].astype(float).values
        codes = np.where(np.isnan(x), -1, np.digitize(np.nan_to_num(x), b['bins']))
        labs = b.get('labels') or [f'구간{i + 1}' for i in range(len(b['bins']) + 1)]
        assert len(labs) == len(b['bins']) + 1, f"labels {len(labs)}개, bins {len(b['bins'])}개"
        return codes, list(labs)
    if 'cat' in b:
        if b['cat'] in _STD:
            return partition({'std': b['cat']})
        x = d[b['cat']]
        vals = sorted(v for v in x.dropna().unique())
        lab = {}
        if b['cat'] in codebook().index:
            for kv in codebook().loc[b['cat'], 'codes'].split('; '):
                if '=' in kv:
                    k, t = kv.split('=', 1); lab[k.strip()] = t.strip()
        idx = {v: i for i, v in enumerate(vals)}
        codes = x.map(idx).fillna(-1).astype(int).values
        fmt = lambda v: str(int(v)) if isinstance(v, (int, float, np.integer, np.floating)) and float(v).is_integer() else str(v)
        return codes, [lab.get(fmt(v), fmt(v)) for v in vals]
    raise ValueError(f'알 수 없는 분류 기준: {b}')


def wquant(x, w, q):
    o = np.argsort(x, kind='stable'); cw = np.cumsum(w[o])
    return float(x[o][min(np.searchsorted(cw, cw[-1] * q), len(x) - 1)])


def cell(measure, m, w, spec, num=None, v=None):
    """한 칸의 값과 관측 수."""
    n = int(m.sum())
    out = {'n': n, 'w': float(w[m].sum())}
    if measure == 'count':
        out['value'] = out['w']
    elif measure == 'ratio':                             # m 은 분류 칸(대상 조건을 걸지 않은 것), num 은 분자 집단, v 자리에 분모 집단의 표시가 들어옴
        den = m & v; mm = m & num
        out.update(n=int(den.sum()), w=float(w[den].sum()), n_num=int(mm.sum()), w_num=float(w[mm].sum()))
        out['value'] = 100 * out['w_num'] / out['w'] if out['w'] > 0 else None
    elif measure in ('rate', 'poverty_rate'):
        mm = m & num
        out.update(n_num=int(mm.sum()), w_num=float(w[mm].sum()), value=(100 * float(w[mm].sum()) / out['w']) if out['w'] > 0 else None)
    elif measure in ('mean', 'sum', 'quantile'):
        mv = m & ~np.isnan(v)
        out['n'] = int(mv.sum()); out['w'] = float(w[mv].sum())
        if out['n'] == 0:
            out['value'] = None
        elif measure == 'mean':
            out['value'] = float((w[mv] * v[mv]).sum() / w[mv].sum())
        elif measure == 'sum':
            out['value'] = float((w[mv] * v[mv]).sum())
        else:
            out['value'] = wquant(v[mv], w[mv], float(spec.get('q', 0.5)))
    else:
        raise ValueError(measure)
    return out


def compute(spec):
    """산출 정의 1개 → {cells, overall}."""
    d = data()
    measure = spec['measure']
    hh = spec.get('unit', 'person') in ('household', '가구', 'hh')
    w = (d['hhwgt'] if hh else d['indwgt']).astype(float).values
    base = mask(spec.get('population', ''))
    if hh:
        base = base & (d['head'].values == 1)
    num = mask(spec['numerator']) if measure == 'rate' else (d['poor'].values == 1 if measure == 'poverty_rate' else None)
    v = None
    if measure in ('mean', 'sum', 'quantile'):      # value_expr: 여러 변수를 더한 값 등 수식(5차 이중 입력에서 검산자의 다른 해석을 정답으로 더할 때 씀. pandas eval)
        v = np.asarray(d.eval(spec['value_expr'], engine='python'), dtype=float) if spec.get('value_expr') else d[spec['value_var']].astype(float).values
    if measure == 'ratio':
        num = mask(spec['num_population']); v = base.copy(); base = np.ones(len(d), bool)
        if hh:
            base = d['head'].values == 1
    by = list(spec.get('by') or [])
    if measure == 'share':                               # 구성비: 범주별 가중 인원 ÷ 범주 값이 있는 대상의 가중 인원
        vv = spec['value_var']
        codes, labs = partition(vv if isinstance(vv, dict) else {'std': vv} if vv in _STD else {'cat': vv})      # 사용자가 정한 구간의 구성비(6차 과제에서 처음 쓰임)
        valid = base & (codes >= 0)
        parts = [partition(b) for b in by if 'groups' not in b]
        gl = next((b['groups'] for b in by if 'groups' in b), [{'label': None, 'cond': ''}])
        shape = [len(l) for _, l in parts]
        cells = []
        for g in gl:
            gm = valid & mask(g['cond'])
            for idx in np.ndindex(*shape) if shape else [()]:
                sub = gm.copy()
                for (pc, _), i in zip(parts, idx):
                    sub &= pc == i
                tot = float(w[sub].sum())
                for i, lab in enumerate(labs):
                    m = sub & (codes == i)
                    cells.append({'labels': ([g['label']] if g['label'] is not None else []) + [parts[k][1][j] for k, j in enumerate(idx)] + [lab],
                                  'n': int(m.sum()), 'w': float(w[m].sum()), 'value': 100 * float(w[m].sum()) / tot if tot > 0 and m.sum() > 0 else None})
        return {'cells': cells, 'overall': {'n': int(valid.sum()), 'w': float(w[valid].sum()), 'value': 100.0}}
    groups = [b for b in by if 'groups' in b]
    parts = [partition(b) for b in by if 'groups' not in b]
    assert len(groups) <= 1, '조건 집단(groups)은 1개까지'
    glist = groups[0]['groups'] if groups else [{'label': None, 'cond': ''}]
    cells = []
    shape = [len(labs) for _, labs in parts]
    for g in glist:
        gm = base & mask(g['cond'])
        for idx in np.ndindex(*shape) if shape else [()]:
            m = gm.copy()
            for (codes, _), i in zip(parts, idx):
                m &= codes == i
            c = cell(measure, m, w, spec, num, v)
            c['labels'] = ([g['label']] if g['label'] is not None else []) + [parts[k][1][i] for k, i in enumerate(idx)]
            cells.append(c)
    valid = base.copy()
    for codes, _ in parts:
        valid &= codes >= 0
    return {'cells': cells, 'overall': cell(measure, valid, w, spec, num, v)}


def main():
    out, errors = {}, []
    files = sorted((BASE / 'items').glob('[A-Z].jsonl')) if len(sys.argv) < 2 else [Path(p) for p in sys.argv[1:]]
    for f in files:
        for line in f.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            b = json.loads(line)
            for k, s in enumerate(b.get('specs') or []):
                try:
                    r = compute(s)
                    out.setdefault(b['id'], []).append({'turn': s.get('turn', len(b['turns'])), 'alt': s.get('alt', 1), 'measure': s['measure'], 'unit': s.get('unit', 'person'), 'spec': s, **r})
                except Exception as e:                  # noqa: BLE001
                    errors.append({'id': b['id'], 'spec': k, 'error': f'{type(e).__name__}: {e}'[:300]})
    (BASE / 'truth').mkdir(exist_ok=True)
    (BASE / 'truth' / 'truth.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    (BASE / 'truth' / 'truth_errors.json').write_text(json.dumps(errors, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'문항 {len(out)}개, 산출 정의 {sum(len(v) for v in out.values())}개, 오류 {len(errors)}건')
    for e in errors:
        print('  오류', e)


if __name__ == '__main__':
    main()
