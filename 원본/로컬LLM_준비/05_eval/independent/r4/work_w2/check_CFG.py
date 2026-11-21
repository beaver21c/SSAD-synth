# -*- coding: utf-8 -*-
"""r4 문항 C·F·G 묶음의 형식·실행 가능성·참값 확인.

사용법
  python check_CFG.py              형식, 조건식 실행, 칸별 관측 수, C 쌍의 참값 차이
  python check_CFG.py --run-code   위 확인에 더해 G 묶음의 붙인 코드를 분석 함수(ssda)로 실행

개인 단위 행은 출력하지 않고 집계값과 관측 수만 출력함.
"""
import csv
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from truthlib import load, compute, ev, PARQUET  # noqa: E402

ROOT = '/mnt/share/행정데이터_set/로컬LLM_준비'
ITEMS = os.path.join(ROOT, '05_eval/independent/r4/items')
CODEBOOK = os.path.join(ROOT, '05_eval/independent/inputs/codebook.tsv')
PY = '/mnt/share/행정데이터_set/.venv/bin/python'
MIN_N = 30
MEASURES = {'count', 'rate', 'mean', 'sum', 'quantile', 'share', 'poverty_rate'}
STD_NAMES = {'sido', 'sex', 'age3', 'age6', 'age10', 'hs4', 'inc5', 'nhi3', 'poor2'}
DERIVED = {'eqinc', 'hh_dinc', 'poor'}
KEYWORDS = {'and', 'or', 'not', 'in', 'isna', 'notna'}
EXPECT_N = {'C': 30, 'F': 10, 'G': 12}

errors = []
warns = []


def err(msg):
    errors.append(msg)
    print('  [오류]', msg)


def warn(msg):
    warns.append(msg)
    print('  [주의]', msg)


def read_jsonl(name):
    path = os.path.join(ITEMS, name)
    items = []
    with open(path, encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                err('%s %d행: 빈 줄' % (name, i))
                continue
            try:
                items.append(json.loads(line))
            except Exception as e:  # JSON Lines 로 읽히지 않음
                err('%s %d행: JSON 해석 실패 %s' % (name, i, e))
    return items


def codebook_vars():
    with open(CODEBOOK, encoding='utf-8') as f:
        return {r['var'] for r in csv.DictReader(f, delimiter='\t')}


def idents(expr):
    return set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', expr or '')) - KEYWORDS


def strip_code(text):
    return re.sub(r'```.*?```', '', text, flags=re.S)


def check_spec(it, s, df, cb):
    tag = it['id'] + (' 차례%d' % s['turn'] if 'turn' in s else '')
    if s.get('measure') not in MEASURES:
        err('%s: measure 값 오류 %r' % (tag, s.get('measure')))
        return None
    if s.get('unit', 'person') not in ('person', 'household'):
        err('%s: unit 값 오류' % tag)
    m = s['measure']
    if m == 'rate' and not s.get('numerator'):
        err('%s: rate 에 numerator 없음' % tag)
    if m in ('mean', 'sum', 'quantile', 'share') and not s.get('value_var'):
        err('%s: value_var 없음' % tag)
    if m == 'quantile' and not (0.05 <= s.get('q', 0.5) <= 0.95):
        err('%s: 분위 범위 오류' % tag)
    if m == 'count' and s.get('numerator'):
        err('%s: count 에 numerator 가 있음' % tag)
    exprs = [('population', s.get('population', ''))]
    if s.get('numerator'):
        exprs.append(('numerator', s['numerator']))
    for b in s.get('by', []):
        if 'std' in b and b['std'] not in STD_NAMES:
            err('%s: 표준 분류 이름 오류 %r' % (tag, b['std']))
        if 'cat' in b and b['cat'] not in cb:
            err('%s: 범주형 변수 없음 %r' % (tag, b['cat']))
        if 'var' in b:
            if b['var'] not in cb:
                err('%s: 구간 변수 없음 %r' % (tag, b['var']))
            if len(b.get('labels', [])) != len(b.get('bins', [])) + 1:
                err('%s: 구간 수와 라벨 수 불일치' % tag)
        for g in b.get('groups', []):
            exprs.append(('groups.cond', g['cond']))
    for name, e in exprs:
        unknown = idents(e) - cb - DERIVED - STD_NAMES
        if unknown:
            err('%s: %s 에 codebook 에 없는 이름 %s' % (tag, name, sorted(unknown)))
        try:
            df.eval(e, engine='python') if e.strip() else None
            ev(df, e)
        except Exception as ex:
            err('%s: %s 조건식 실행 실패 (%s) %s' % (tag, name, e, ex))
            return None
    vv = s.get('value_var')
    if vv and vv not in cb and vv not in DERIVED and vv not in STD_NAMES:
        err('%s: value_var 가 codebook 에 없음 %r' % (tag, vv))
        return None
    try:
        cells = compute(s, df)
    except Exception as ex:
        err('%s: 참값 계산 실패 %s' % (tag, ex))
        return None
    shown = [c for c in cells if c['shown']]
    if not cells:
        err('%s: 대상이 없음' % tag)
    elif not shown:
        err('%s: 표시되는 칸이 없음(모든 칸 %d건 미만)' % (tag, MIN_N))
    elif len(shown) < len(cells):
        warn('%s: %d칸 중 %d칸이 %d건 미만 %s' % (tag, len(cells), len(cells) - len(shown), MIN_N,
                                                  [(c['key'], c['n']) for c in cells if not c['shown']]))
    return cells


def cell_map(s, cells):
    return {(s['measure'], s.get('unit', 'person')) + tuple(c['key']): c['value'] for c in cells if c['shown']}


def fmt(cells):
    if len(cells) == 1 and cells[0]['key'] == ():
        return '%s (n=%d)' % (cells[0]['value'], cells[0]['n'])
    return '; '.join('%s=%s(n=%d)' % ('·'.join(map(str, c['key'])), c['value'], c['n']) for c in cells)


def check_common(it, stratum, cb):
    for k in ('id', 'stratum', 'persona', 'turns', 'expect', 'specs', 'note'):
        if k not in it or it[k] in (None, '', []):
            err('%s: 항목 %s 없음' % (it.get('id'), k))
    if it.get('stratum') != stratum:
        err('%s: stratum 불일치' % it.get('id'))
    if it.get('expect') != 'compute':
        err('%s: expect 가 compute 가 아님' % it.get('id'))
    for t in it.get('turns', []):
        names = idents(strip_code(t)) & (cb | DERIVED | STD_NAMES)
        if names:
            err('%s: 질문 문장에 변수명 %s' % (it['id'], sorted(names)))


def run_code(it):
    """G 문항의 붙인 코드를 그대로 실행하고 결과 표를 돌려줌(실행 오류이면 오류 이름)."""
    m = re.search(r'```python\n(.*?)\n```', it['turns'][0], flags=re.S)
    if not m:
        err('%s: python 코드 블록 없음' % it['id'])
        return None
    code = m.group(1)
    if 'import ssda' not in code:
        err('%s: import ssda 없음' % it['id'])
    tail = "\nimport json as _j\nprint('@@TABLE@@' + _j.dumps(r.table().to_dict('records'), ensure_ascii=False, default=str))\n"
    env = dict(os.environ, SSDA_DATA=PARQUET, PYTHONPATH='02_library')
    p = subprocess.run([PY, '-c', code + tail], cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        last = [ln for ln in p.stderr.strip().splitlines() if ln.strip()][-1] if p.stderr.strip() else ''
        return {'error': last}
    line = [ln for ln in p.stdout.splitlines() if ln.startswith('@@TABLE@@')]
    return {'table': json.loads(line[0][len('@@TABLE@@'):])}


def same_as_truth(table, s, cells):
    """실행 결과 표가 참값과 같은지(표시 자릿수 기준). 금액은 만원 단위로 환산해 비교."""
    amount = s['measure'] in ('mean', 'sum', 'quantile') and s['value_var'].endswith(('_amt', 'inc', 'prop', '_subsidy', '_fee'))
    truth = {}
    for c in cells:
        if c['shown']:
            truth[tuple(str(k) for k in c['key'])] = c['raw'] / 1e4 if amount else c['raw']
    got = {}
    for row in table:
        if row.get('값') in (None, '') or str(row.get('상태', '표시')) != '표시':
            continue
        key = tuple(str(v) for k, v in row.items() if k not in ('값', '해당 인원', '대상 인원', '상태'))
        got[key] = float(row['값'])
    if set(truth) - set(got):
        return False, got
    for k, tv in truth.items():
        gv = got[k]
        tol = 0.051 if s['measure'] in ('rate', 'poverty_rate', 'share') else abs(tv) * 0.006
        if abs(gv - tv) > tol:
            return False, got
    return True, got


def main():
    run = '--run-code' in sys.argv
    df = load()
    cb = codebook_vars()
    data = {}
    truth = {}
    for st in ('C', 'F', 'G'):
        print('== %s 묶음' % st)
        items = read_jsonl(st + '.jsonl')
        data[st] = items
        if len(items) != EXPECT_N[st]:
            err('%s 묶음 문항 수 %d (기대 %d)' % (st, len(items), EXPECT_N[st]))
        ids = [it.get('id') for it in items]
        if len(set(ids)) != len(ids):
            err('%s 묶음 id 중복' % st)
        for it in items:
            check_common(it, st, cb)
            out = []
            for s in it.get('specs', []):
                cells = check_spec(it, s, df, cb)
                out.append((s, cells))
                if cells:
                    print('  %-5s %s%-12s %s' % (it['id'], ('차례%d ' % s['turn']) if 'turn' in s else '', s['measure'], fmt(cells)))
            truth[it['id']] = out

    print('== C 묶음: 쌍 확인')
    pairs = {}
    for it in data['C']:
        if not re.fullmatch(r'C\d\d[ab]', it['id']):
            err('%s: id 형식 오류' % it['id'])
        if it.get('pair') != it['id'][:3]:
            err('%s: pair 항목 오류' % it['id'])
        if not it.get('diff'):
            err('%s: diff 항목 없음' % it['id'])
        if len(it['turns']) != 1 or len(it['specs']) != 1:
            err('%s: 차례·산출 정의는 1개여야 함' % it['id'])
        pairs.setdefault(it.get('pair'), []).append(it)
    if len(pairs) != 15:
        err('C 묶음 쌍의 수 %d' % len(pairs))
    for pid, members in sorted(pairs.items()):
        if len(members) != 2:
            err('%s: 쌍의 문항 수 %d' % (pid, len(members)))
            continue
        a, b = sorted(members, key=lambda x: x['id'])
        if a['diff'] != b['diff']:
            err('%s: 두 문항의 diff 가 다름' % pid)
        if a['turns'] == b['turns']:
            err('%s: 두 질문이 같음' % pid)
        (sa, ca), (sb, cb_) = truth[a['id']][0], truth[b['id']][0]
        if not ca or not cb_:
            continue
        ma, mb = cell_map(sa, ca), cell_map(sb, cb_)
        if ma == mb:
            err('%s: 두 참값이 표시 자릿수에서 같음' % pid)
        else:
            print('  %s 다름 [%s] a: %s | b: %s' % (pid, a['diff'], fmt(ca), fmt(cb_)))

    print('== F 묶음: 대화 확인')
    for it in data['F']:
        nt = len(it['turns'])
        if not 2 <= nt <= 3:
            err('%s: 차례 수 %d' % (it['id'], nt))
        turns = [s.get('turn') for s in it['specs']]
        if sorted(turns) != list(range(1, nt + 1)):
            err('%s: 산출 정의의 turn %s 이 차례 1~%d 와 맞지 않음' % (it['id'], turns, nt))
    print('  차례 수 분포:', {n: sum(1 for it in data['F'] if len(it['turns']) == n) for n in (2, 3)})

    print('== G 묶음: 코드 확인')
    for it in data['G']:
        if not it.get('defect'):
            err('%s: defect 항목 없음' % it['id'])
        if '```python' not in it['turns'][0]:
            err('%s: 코드 블록 없음' % it['id'])
        if not run:
            continue
        s, cells = truth[it['id']][0]
        res = run_code(it)
        if res is None or not cells:
            continue
        if 'error' in res:
            ok = it['defect'].startswith('실행 불가')
            print('  %s [%s] 실행 오류: %s -> %s' % (it['id'], it['defect'], res['error'][:90], '의도대로' if ok else '의도와 다름'))
            if not ok:
                err('%s: 실행되어야 할 코드가 오류' % it['id'])
            continue
        same, got = same_as_truth(res['table'], s, cells)
        if it['defect'] == '없음':
            ok = same
        elif it['defect'].startswith('실행 불가'):
            ok = False
        else:
            ok = not same
        print('  %s [%s] 실행됨, 참값과 %s -> %s | 실행 결과 %s' % (it['id'], it['defect'], '같음' if same else '다름',
                                                         '의도대로' if ok else '의도와 다름', got))
        if not ok:
            err('%s: 붙인 코드의 동작이 defect 항목과 맞지 않음' % it['id'])
    if not run:
        print('  (붙인 코드 실행은 --run-code 를 주었을 때만 수행)')

    print('== 요약')
    print('  문항 수:', {st: len(v) for st, v in data.items()})
    from collections import Counter
    print('  C 차이 종류:', dict(Counter(it['diff'] for it in data['C'][::2])))
    print('  G 결함 종류:', dict(Counter(it['defect'] for it in data['G'])))
    print('  주의 %d건, 오류 %d건' % (len(warns), len(errors)))
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
