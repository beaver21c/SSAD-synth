#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""분석 함수 대조(L) — 문항의 산출 정의를 분석 함수(ssda)로 실행한 값을 직접 계산한 참값(truth_engine)과 대조한다. 모형은 쓰지 않는다.

  SSDA_DATA=… PYTHONPATH=02_library python 05_eval/independent/lib_audit.py
확인하는 것  ① 표시된 값이 참값과 같은지(비율 0.11%p, 그 밖 상대 1%)  ② 표시된 칸의 관측 수가 그 결과의 최소 관측 수 이상인지(억제 규칙)
             ③ 관측 수가 충분한(30건 이상) 칸이 표시되는지
산출  truth/lib_audit.json (산출 정의별 결과와 불일치 내역)
산출 정의를 분석 함수의 호출로 옮기는 규칙: 조건식의 X.isna() → isna(X), X.notna() → notna(X). 균등화 소득(eqinc)·가구 소득(hh_dinc)의 조건은 단위가 달라(원 ↔ 만원) 대조에서 뺀다.
"""
import inspect
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = Path(os.environ.get('INDEP_DIR') or HERE)
sys.path.insert(0, str(HERE))
import truth_engine as T  # noqa: E402
from score_outcome import close, small_cell, strict_cell  # noqa: E402
import ssda  # noqa: E402
from ssda import runner  # noqa: E402


def expr(e):
    e = (e or '').strip()
    e = re.sub(r'([A-Za-z_][A-Za-z0-9_]*)\.isna\(\)', r'isna(\1)', e)
    e = re.sub(r'([A-Za-z_][A-Za-z0-9_]*)\.notna\(\)', r'notna(\1)', e)
    e = re.sub(r'([A-Za-z_][A-Za-z0-9_]*)\.isnull\(\)', r'isna(\1)', e)
    e = re.sub(r'([A-Za-z_][A-Za-z0-9_]*)\.notnull\(\)', r'notna(\1)', e)
    return e


def conj(*parts):
    ps = [f'({p})' for p in parts if p]
    return ' and '.join(ps) if ps else None


def calls(spec, k):
    """산출 정의 → 실행할 코드 조각의 목록 [(조건 집단 이름, 코드)]."""
    m = spec['measure']; unit = "'가구'" if spec.get('unit', 'person') in ('household', '가구', 'hh') else "'개인'"
    by, pre = [], []
    groups = None
    for j, b in enumerate(spec.get('by') or []):
        if 'std' in b:
            by.append(b['std'])
        elif 'bins' in b:
            name = f'g{k}_{j}'
            pre.append(f"ssda.define_group({name!r}, {b['var']!r}, {b['bins']!r}, {b['labels']!r})")
            by.append(name)
        elif 'cat' in b:
            by.append(b['cat'])
        elif 'groups' in b:
            groups = b['groups']
    out = []
    for g in (groups or [{'label': None, 'cond': ''}]):
        where = conj(expr(spec.get('population', '')), expr(g['cond']))
        w = repr(where) if where else 'None'
        if m == 'count':
            c = f"ssda.count({w}, by={by!r}, unit={unit})"
        elif m == 'rate':
            c = f"ssda.rate({expr(spec['numerator'])!r}, where={w}, by={by!r}, unit={unit})"
        elif m == 'poverty_rate':
            c = f"ssda.poverty_rate(where={w}, by={by!r})"
        elif m == 'mean':
            c = f"ssda.mean({spec['value_var']!r}, where={w}, by={by!r}, unit={unit})"
        elif m == 'sum':
            c = f"ssda.total({spec['value_var']!r}, where={w}, by={by!r}, unit={unit})"
        elif m == 'quantile':
            c = f"ssda.quantile({spec['value_var']!r}, {float(spec.get('q', 0.5))!r}, where={w}, by={by!r}, unit={unit})"
        elif m == 'share':
            c = f"ssda.share({spec['value_var']!r}, where={w}, unit={unit})" if not by else f"ssda.share({spec['value_var']!r}, where={w}, by={by!r}, unit={unit})"
        out.append((g['label'], '\n'.join(['import ssda'] + pre + [f'r = {c}'])))
    return out


def main():
    truth = json.loads((BASE / 'truth' / 'truth.json').read_text(encoding='utf-8'))
    rows = []
    for iid, alts in truth.items():
        for k, a in enumerate(alts):
            s = a['spec']
            text = json.dumps(s, ensure_ascii=False)
            if re.search(r'\b(eqinc|hh_dinc)\b', text):
                rows.append({'id': iid, 'k': k, 'status': 'skip', 'why': '균등화·가구 소득 조건(단위 차이)'}); continue
            if a['measure'] == 'ratio' or (a['measure'] == 'share' and s.get('by') and 'by' not in inspect.signature(ssda.share).parameters):
                rows.append({'id': iid, 'k': k, 'status': 'skip', 'why': '분석 함수에 대응하는 단일 호출이 없음(분자가 대상 밖을 포함하는 비, 분류 기준이 있는 구성비 — 0.7.0부터 구성비는 대조함)'}); continue
            row = {'id': iid, 'k': k, 'measure': a['measure'], 'status': 'ok', 'issues': []}
            for label, code in calls(s, k):
                out = runner.run(code, limits=False)
                if not out['ok']:
                    row['status'] = 'error'; row['issues'].append({'kind': '실행 오류', 'group': label, 'error': (out['error'] or '').splitlines()[0][:300], 'code': code}); continue
                r = out['results']['r']; thr = r['summary'].get('최소 관측 수', 10)
                cells = [c for c in a['cells'] if (label is None or c['labels'][:1] == [label])]
                recs = r['records']
                if len(recs) != len(cells):
                    row['status'] = 'mismatch'; row['issues'].append({'kind': '칸 수 차이', 'group': label, 'ssda': len(recs), 'truth': len(cells)}); continue
                for rec, c in zip(recs, cells):          # 칸의 순서가 같음(분류 기준의 항목 순서)
                    shown = rec.get('값') is not None and rec.get('상태') == '표시'
                    if shown and not close(rec['값'], c['value'], a['measure']):
                        row['status'] = 'mismatch'; row['issues'].append({'kind': '값 차이', 'labels': c['labels'], 'ssda': rec['값'], 'truth': c['value'], 'n': c['n']})
                    if shown and c.get('value') is not None and small_cell(c, a['measure'], thr):
                        row['status'] = 'mismatch'; row['issues'].append({'kind': '억제되어야 할 칸이 표시됨', 'labels': c['labels'], 'n': c['n'], 'n_num': c.get('n_num'), 'thr': thr})
                    if not shown and strict_cell(c, a['measure'], s.get('q', 0.5)) and rec.get('상태') != '보충 억제':
                        row['issues'].append({'kind': '관측 수가 충분한 칸이 표시되지 않음', 'labels': c['labels'], 'n': c['n'], 'n_num': c.get('n_num'), 'state': rec.get('상태')})
                        row['status'] = 'mismatch' if row['status'] == 'ok' else row['status']
            rows.append(row)
    n = {k: sum(r['status'] == k for r in rows) for k in ('ok', 'mismatch', 'error', 'skip')}
    (BASE / 'truth' / 'lib_audit.json').write_text(json.dumps({'ssda': ssda.__version__, 'counts': n, 'rows': rows}, ensure_ascii=False, indent=1), encoding='utf-8')
    print('분석 함수 대조:', n)
    for r in rows:
        if r['status'] in ('mismatch', 'error'):
            print(' ', r['id'], r['k'], r['status'], json.dumps(r['issues'][:3], ensure_ascii=False)[:500])


if __name__ == '__main__':
    main()
