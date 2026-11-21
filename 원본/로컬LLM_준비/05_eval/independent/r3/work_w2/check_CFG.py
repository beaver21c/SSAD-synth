# -*- coding: utf-8 -*-
"""C·F·G 묶음 문항 점검 스크립트(독립 문항 작성자 w2).

점검 내용
 1) 세 파일이 JSON Lines로 읽히는지, 필수 항목이 있는지, id가 겹치지 않는지
 2) 모든 population·numerator·groups[].cond 가 DataFrame.eval(engine='python') 으로 실행되는지
 3) 산출 정의마다 참값을 계산하고, 표시되는 칸(가중하지 않은 관측 수 30건 이상)이 있는지
 4) C 묶음의 쌍마다 두 참값이 표시 자릿수에서 다른지
 5) 질문 문장(코드 블록 밖)에 변수명이 들어가지 않았는지
 6) (--run-g) G 묶음의 코드를 분석 함수로 실행해 정상 실행·오류 여부와 의도한 참값과의 일치 여부를 확인

개인 단위 행은 출력하지 않고 집계값만 출력한다.
사용: python check_CFG.py [--run-g] [--show]
"""
import json, math, os, re, subprocess, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ITEMS = os.path.join(os.path.dirname(HERE), 'items')
DATA = '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet'
CODEBOOK = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'inputs', 'codebook.tsv')
LIBROOT = '/mnt/share/행정데이터_set/로컬LLM_준비'
PY = '/mnt/share/행정데이터_set/.venv/bin/python'
MIN_N = 30

SIDO = ['서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종', '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주']


def wquantile(v, w, q):
    v = np.asarray(v, float); w = np.asarray(w, float)
    ok = ~np.isnan(v)
    v, w = v[ok], w[ok]
    o = np.argsort(v, kind='mergesort')
    v, w = v[o], w[o]
    c = np.cumsum(w)
    i = int(np.searchsorted(c, q * c[-1], side='left'))
    return float(v[min(i, len(v) - 1)])


def load():
    df = pd.read_parquet(DATA)
    df['hh_dinc'] = df.groupby('hid')['p_dinc'].transform('sum')
    df['eqinc'] = df['hh_dinc'] / np.sqrt(df['hnum'])
    med = wquantile(df['eqinc'], df['indwgt'], 0.5)
    df['poor'] = (df['eqinc'] < 0.5 * med).astype(int)
    cuts = [wquantile(df['eqinc'], df['indwgt'], q) for q in (0.2, 0.4, 0.6, 0.8)]
    std = {}
    std['sido'] = df['sido'].map(lambda k: SIDO[int(k) - 1])
    std['sex'] = df['gender'].map({1: '남', 2: '여'})
    std['age3'] = pd.cut(df['age'], [-1, 17, 64, 999], labels=['0~17세', '18~64세', '65세 이상']).astype(str)
    std['age6'] = pd.cut(df['age'], [-1, 17, 34, 49, 64, 74, 999], labels=['0~17세', '18~34세', '35~49세', '50~64세', '65~74세', '75세 이상']).astype(str)
    a10 = np.minimum(df['age'] // 10, 8).astype(int)
    std['age10'] = a10.map(lambda k: '80세 이상' if k == 8 else f'{k*10}~{k*10+9}세')
    std['hs4'] = np.minimum(df['hnum'], 4).astype(int).map({1: '1인', 2: '2인', 3: '3인', 4: '4인 이상'})
    q5 = np.searchsorted(cuts, df['eqinc'].values, side='right')
    std['inc5'] = pd.Series(q5, index=df.index).map(lambda k: f'{k+1}분위')
    std['nhi3'] = df['nhi_type'].map(lambda k: '지역가입' if k in (1, 2) else ('직장가입' if k in (5, 6) else '의료급여'))
    std['poor2'] = df['poor'].map({0: '비빈곤', 1: '빈곤'})
    return df, std, 0.5 * med


def ev(df, cond):
    if cond is None or str(cond).strip() == '':
        return pd.Series(True, index=df.index)
    r = df.eval(cond, engine='python')
    # 결측을 허용하는 정수형 열(Int64 등)은 비교 결과에 <NA>가 남으므로 거짓으로 둔다
    return pd.Series(r, index=df.index).astype('boolean').fillna(False).astype(bool)


def by_labels(df, std, by):
    """분류 기준 목록 → 행별 표지(튜플) Series. 어느 기준에도 속하지 않는 행은 None."""
    cols = []
    for b in by:
        if 'std' in b:
            cols.append(std[b['std']].astype(object))
        elif 'var' in b:
            bins = b['bins']; labels = b['labels']
            assert len(labels) == len(bins) + 1, '구간 표지 수는 bins+1'
            idx = np.searchsorted(bins, df[b['var']].values, side='right')
            s = pd.Series([labels[i] for i in idx], index=df.index, dtype=object)
            s[df[b['var']].isna()] = None
            cols.append(s)
        elif 'cat' in b:
            s = df[b['cat']].astype(object)
            s = s.where(df[b['cat']].notna(), None)
            cols.append(s.map(lambda x: None if x is None else str(int(x)) if float(x).is_integer() else str(x)))
        elif 'groups' in b:
            s = pd.Series([None] * len(df), index=df.index, dtype=object)
            for g in b['groups']:
                m = ev(df, g['cond'])
                s[m & s.isna()] = g['label']
            cols.append(s)
        else:
            raise ValueError('알 수 없는 분류 기준: %r' % b)
    if not cols:
        return pd.Series(['전체'] * len(df), index=df.index, dtype=object)
    out = cols[0].copy()
    for c in cols[1:]:
        out = pd.Series([None if (a is None or b_ is None or a != a or b_ != b_) else f'{a} | {b_}' for a, b_ in zip(out, c)], index=df.index, dtype=object)
    return out


def sig3(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    if x == 0:
        return 0.0
    d = 2 - int(math.floor(math.log10(abs(x))))
    return round(x, d)


def compute(df, std, spec):
    """산출 정의 → {칸: (표시값, 관측수, 표시 여부)}"""
    unit = spec.get('unit', 'person')
    base = df if unit == 'person' else df[df['head'] == 1]
    w = base['indwgt'] if unit == 'person' else base['hhwgt']
    stdb = {k: v.loc[base.index] for k, v in std.items()}
    pop = ev(base, spec.get('population', ''))
    m = spec['measure']
    out = {}
    if m == 'share':
        vv = spec['value_var']
        cat = stdb[vv].astype(object) if vv in stdb else base[vv].where(base[vv].notna(), None).astype(object)
        ok = pop & cat.notna()
        tot = w[ok].sum()
        for k in sorted(set(cat[ok]), key=str):
            mk = ok & (cat == k)
            n = int(mk.sum())
            out[str(k)] = (round(100 * w[mk].sum() / tot, 1), n, n >= MIN_N and int(ok.sum()) - n >= MIN_N)
        return out
    lab = by_labels(base, stdb, spec.get('by', []))
    for k in [x for x in pd.unique(lab[pop]) if x is not None and x == x]:
        c = pop & (lab == k)
        n = int(c.sum())
        if m == 'count':
            out[k] = (sig3(float(w[c].sum())), n, n >= MIN_N)
        elif m in ('rate', 'poverty_rate'):
            num = ev(base, spec['numerator']) if m == 'rate' else (base['poor'] == 1)
            nn = int((c & num).sum())
            val = round(100 * w[c & num].sum() / w[c].sum(), 1) if n else None
            out[k] = (val, n, nn >= MIN_N and n - nn >= MIN_N)
        elif m in ('mean', 'sum', 'quantile'):
            v = base[spec['value_var']].astype(float)
            cc = c & v.notna()
            n = int(cc.sum())
            if n == 0:
                out[k] = (None, 0, False); continue
            if m == 'mean':
                val = float((v[cc] * w[cc]).sum() / w[cc].sum())
            elif m == 'sum':
                val = float((v[cc] * w[cc]).sum())
            else:
                val = wquantile(v[cc], w[cc], spec.get('q', 0.5))
            out[k] = (sig3(val), n, n >= MIN_N)
        else:
            raise ValueError('measure: %r' % m)
    return out


def shown(tab):
    return {k: v[0] for k, v in tab.items() if v[2]}


def strip_code(text):
    return re.sub(r'```.*?```', ' ', text, flags=re.S)


def read_jsonl(name):
    path = os.path.join(ITEMS, name)
    items = []
    with open(path, encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            line = line.rstrip('\n')
            if not line.strip():
                raise SystemExit(f'{name}:{i} 빈 줄')
            items.append(json.loads(line))
    return items


def conds_of(spec):
    cs = [('population', spec.get('population', ''))]
    if 'numerator' in spec:
        cs.append(('numerator', spec['numerator']))
    for b in spec.get('by', []):
        for g in b.get('groups', []):
            cs.append(('groups.cond', g['cond']))
    return cs


def run_g_code(code):
    """G 문항의 코드를 분석 함수로 실행. (정상 여부, 결과 표의 값 목록, 출력 꼬리)"""
    tail = ("\nimport json as _j\ntry:\n    _t = r.table()\n    print('@@TABLE@@' + _j.dumps({'cols': [str(c) for c in _t.columns], "
            "'rows': [[None if (isinstance(x, float) and x != x) else (x.item() if hasattr(x, 'item') else x) for x in row] for row in _t.values.tolist()]}, ensure_ascii=False, default=str))\n"
            "except NameError:\n    pass\n")
    env = dict(os.environ, SSDA_DATA=DATA, PYTHONPATH=os.path.join(LIBROOT, '02_library'))
    p = subprocess.run([PY, '-c', code + tail], cwd=LIBROOT, env=env, capture_output=True, text=True, timeout=600)
    table = None
    for line in p.stdout.splitlines():
        if line.startswith('@@TABLE@@'):
            table = json.loads(line[len('@@TABLE@@'):])
    err = p.stderr.strip().splitlines()[-1] if p.returncode != 0 and p.stderr.strip() else ''
    return p.returncode == 0, table, err


def table_values(table):
    """결과 표에서 (분류 표지, 값) 쌍을 뽑는다. 값 열 이름은 '값'."""
    if table is None:
        return None
    cols = table['cols']
    vi = cols.index('값') if '값' in cols else None
    if vi is None:
        return None
    res = {}
    for row in table['rows']:
        key = ' | '.join(str(x) for x in row[:vi]) if vi > 0 else '전체'
        res[key] = row[vi]
    return res


def close(a, b, money):
    if a is None or b is None:
        return False
    b2 = b / 10000.0 if money else b
    if b2 == 0:
        return abs(a) < 1e-9
    return abs(a - b2) / abs(b2) < 0.006 or abs(a - b2) < 0.051


def main():
    show = '--show' in sys.argv
    run_g = '--run-g' in sys.argv
    df, std, pline = load()
    cb = pd.read_csv(CODEBOOK, sep='\t')
    varnames = set(cb['var']) | set(df.columns)
    amount_vars = set(cb.loc[cb['dtype'] == 'amount', 'var']) | {'hh_dinc', 'eqinc'}
    print(f'자료 {df.shape[0]:,}행, 가구 {df["hid"].nunique():,}, 빈곤선 {pline/10000:,.0f}만원')
    problems = []
    all_ids = set()
    truth = {}
    for name, stratum in (('C.jsonl', 'C'), ('F.jsonl', 'F'), ('G.jsonl', 'G')):
        items = read_jsonl(name)
        print(f'\n== {name}: {len(items)}문항')
        for it in items:
            iid = it.get('id', '?')
            for k in ('id', 'stratum', 'persona', 'turns', 'expect', 'specs', 'note'):
                if k not in it:
                    problems.append(f'{iid}: 항목 {k} 없음')
            if iid in all_ids:
                problems.append(f'{iid}: id 중복')
            all_ids.add(iid)
            if it.get('stratum') != stratum:
                problems.append(f'{iid}: stratum 불일치')
            if it.get('expect') != 'compute':
                problems.append(f'{iid}: expect 가 compute 아님')
            if not it.get('specs'):
                problems.append(f'{iid}: specs 없음'); continue
            turns = it['turns']
            if stratum == 'C' and (len(turns) != 1 or 'pair' not in it or 'diff' not in it):
                problems.append(f'{iid}: C 묶음 형식(turns 1개, pair, diff)')
            if stratum == 'F':
                if not 2 <= len(turns) <= 3:
                    problems.append(f'{iid}: turns 수 {len(turns)}')
                tset = [s.get('turn') for s in it['specs']]
                if any(t is None or not 1 <= t <= len(turns) for t in tset):
                    problems.append(f'{iid}: turn 표기 오류 {tset}')
                if sorted(set(tset)) != list(range(1, len(turns) + 1)):
                    problems.append(f'{iid}: 산출 정의가 없는 차례가 있음 {tset}')
            if stratum == 'G':
                if 'defect' not in it:
                    problems.append(f'{iid}: defect 없음')
                if not re.search(r'```python\n.*?import ssda.*?```', turns[0], flags=re.S):
                    problems.append(f'{iid}: python 코드 블록(import ssda) 없음')
            # 질문 문장의 변수명
            for t in turns:
                plain = strip_code(t)
                toks = set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', plain))
                bad = sorted(x for x in toks if x in varnames or x in ('eqinc', 'hh_dinc', 'poor', 'inc5', 'age3', 'age6', 'age10', 'hs4', 'nhi3', 'poor2'))
                if bad:
                    problems.append(f'{iid}: 질문 문장에 변수명 {bad}')
            # 산출 정의
            for si, sp in enumerate(it['specs'], 1):
                tag = f'{iid}#{si}'
                for cname, c in conds_of(sp):
                    try:
                        ev(df if sp.get('unit', 'person') == 'person' else df[df['head'] == 1], c)
                    except Exception as e:
                        problems.append(f'{tag}: {cname} 실행 오류 {c!r}: {e!r}')
                if sp['measure'] in ('mean', 'sum', 'quantile') and sp.get('value_var') not in df.columns:
                    problems.append(f'{tag}: value_var 없음 {sp.get("value_var")}')
                if sp['measure'] == 'share' and not (sp.get('value_var') in df.columns or sp.get('value_var') in std):
                    problems.append(f'{tag}: share value_var 없음')
                if sp['measure'] == 'rate' and 'numerator' not in sp:
                    problems.append(f'{tag}: rate 에 numerator 없음')
                if sp['measure'] == 'quantile' and not 0.05 <= sp.get('q', 0.5) <= 0.95:
                    problems.append(f'{tag}: q 범위')
                try:
                    tab = compute(df, std, sp)
                except Exception as e:
                    problems.append(f'{tag}: 참값 계산 오류 {e!r}'); continue
                truth[tag] = tab
                sh = shown(tab)
                if not sh:
                    problems.append(f'{tag}: 표시되는 칸 없음 {tab}')
                nmin = min(v[1] for v in tab.values()) if tab else 0
                hidden = len(tab) - len(sh)
                line = f'  {tag:9s} {sp["measure"]:12s} 칸 {len(tab):2d} (비표시 {hidden}) 최소 관측 {nmin}'
                if show or len(tab) <= 6:
                    line += '  ' + json.dumps({k: v[0] for k, v in tab.items()}, ensure_ascii=False)
                print(line)
        if stratum == 'C':
            pairs = {}
            for it in items:
                pairs.setdefault(it['pair'], []).append(it)
            for pk, lst in sorted(pairs.items()):
                if len(lst) != 2:
                    problems.append(f'{pk}: 쌍의 문항 수 {len(lst)}'); continue
                a, b = (shown(truth[f'{x["id"]}#1']) for x in lst)
                same = (a == b)
                if set(a) != set(b) and len(a) == 1 and len(b) == 1:
                    same = list(a.values()) == list(b.values())
                qa, qb = lst[0]['turns'][0], lst[1]['turns'][0]
                i = 0
                while i < min(len(qa), len(qb)) and qa[i] == qb[i]:
                    i += 1
                j = 0
                while j < min(len(qa), len(qb)) - i and qa[-1 - j] == qb[-1 - j]:
                    j += 1
                da, db = qa[i:len(qa) - j], qb[i:len(qb) - j]
                print(f'  쌍 {pk} [{lst[0]["diff"]}] 다름={not same}  문장 차이: 「{da}」↔「{db}」')
                if max(len(da), len(db)) > 45:
                    problems.append(f'{pk}: 두 질문의 다른 부분이 한 곳으로 좁혀지지 않음')
                if same:
                    problems.append(f'{pk}: 두 참값이 표시 자릿수에서 같음 {a} / {b}')
                if lst[0]['diff'] != lst[1]['diff']:
                    problems.append(f'{pk}: diff 표기 불일치')
        if stratum == 'G' and run_g:
            print('  -- 코드 실행 확인')
            for it in items:
                code = re.search(r'```python\n(.*?)```', it['turns'][0], flags=re.S).group(1)
                ok, table, err = run_g_code(code)
                sp = it['specs'][0]
                tv = table_values(table)
                tr = {k: v[0] for k, v in truth[f'{it["id"]}#1'].items()}
                money = sp['measure'] in ('mean', 'sum', 'quantile') and sp.get('value_var') in amount_vars
                match = None
                if ok and tv is not None:
                    norm = lambda k: re.sub(r'\(.*?\)', '', str(k)).replace(' ', '')
                    a = {norm(k): v for k, v in tv.items()}
                    b = {norm(k): v for k, v in tr.items()}
                    seen = [k for k, v in a.items() if v is not None]
                    match = set(a) == set(b) and bool(seen) and all(close(a[k], b[k], money) for k in seen)
                print(f'  {it["id"]} 결함={it["defect"]} 실행={"정상" if ok else "오류"} 의도와 일치={match} {err[:110]}')
                if show and tv is not None:
                    print('     코드 결과:', json.dumps(tv, ensure_ascii=False))
                    print('     의도 참값:', json.dumps(tr, ensure_ascii=False), '(금액은 원)' if money else '')
                d = it['defect']
                if d == '없음' and not (ok and match):
                    problems.append(f'{it["id"]}: 결함 없음인데 실행 실패 또는 참값 불일치')
                if d.startswith('실행 불가') and ok:
                    problems.append(f'{it["id"]}: 실행 불가 문항인데 정상 실행됨')
                if d != '없음' and not d.startswith('실행 불가') and (not ok or match):
                    problems.append(f'{it["id"]}: 결함 문항인데 오류가 나거나 의도한 참값과 일치함')
    print('\n문제 %d건' % len(problems))
    for p in problems:
        print(' -', p)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
