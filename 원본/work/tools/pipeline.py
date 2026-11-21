# -*- coding: utf-8 -*-
"""DAG 러너 (작업지시서 §4): order → agent → block 순서로 rules/*.py 의 generate() 호출.
계약: generate(df, params, ctx) -> DataFrame(신규/갱신 컬럼만 포함, index=df.index)
      상위 컬럼 수정 금지 (검사됨). 추출대상 밖 = NaN. amt 는 원 단위 정수."""
from __future__ import annotations
import importlib.util, json, os, sys, time, traceback
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_module(path):
    spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def block_plan():
    bs = json.load(open(os.path.join(ROOT, 'registry/blocks.json'), encoding='utf-8'))
    return sorted(bs, key=lambda b: (b['order'], b['agent'], b['block']))

def run(n_hh=4200, out_prefix='data/stage', verbose=True, only=None, ctx_extra=None):
    plan = block_plan()
    log, df = [], None
    ctx = {'n_hh': n_hh, 'root': ROOT}
    ctx.update(ctx_extra or {})
    for b in plan:
        bid, agent = b['block'], b['agent']
        if only and bid not in only: continue
        rp = os.path.join(ROOT, f'rules/{agent}_{bid}.py')
        pp = os.path.join(ROOT, f'params/{agent}_{bid}.yaml')
        if not os.path.exists(rp):
            log.append({'block': bid, 'status': 'SKIP(no rules)', 'n_new': 0}); continue
        t0 = time.time()
        try:
            pr = core.load_params(pp) if os.path.exists(pp) else {'params': {}, 'errors': [], 'meta': {}}
            mod = load_module(rp)
            before = None if df is None else df.copy(deep=False)
            new = mod.generate(df, pr, ctx)
            if not isinstance(new, pd.DataFrame):
                raise TypeError(f'generate() 는 DataFrame 을 반환해야 한다 (받은 것: {type(new).__name__})')
            if df is not None and not new.index.equals(df.index):
                if len(new) == len(df):
                    new = new.set_axis(df.index)
                else:
                    raise RuntimeError(f'반환 index 불일치: df {len(df)}행 vs new {len(new)}행')
            if df is None:
                df = new
            else:
                overlap = [c for c in new.columns if c in df.columns]
                changed = [c for c in overlap if not df[c].equals(new[c])]
                if changed:
                    raise RuntimeError(f'상위 컬럼 수정 금지 위반: {changed[:8]}')
                df = pd.concat([df, new[[c for c in new.columns if c not in df.columns]]], axis=1)
            log.append({'block': bid, 'agent': agent, 'status': 'OK',
                        'n_new': int(len(new.columns)), 'rows': len(df),
                        'param_errors': len(pr['errors']), 'sec': round(time.time() - t0, 2)})
        except Exception as e:
            log.append({'block': bid, 'agent': agent, 'status': f'FAIL: {type(e).__name__}: {e}',
                        'trace': traceback.format_exc()[-1200:], 'sec': round(time.time() - t0, 2)})
        if verbose:
            print(f"  {bid} {agent}: {log[-1]['status']} (+{log[-1].get('n_new',0)} cols, {log[-1].get('sec')}s)", flush=True)
    return df, pd.DataFrame([{k: v for k, v in l.items() if k != 'trace'} for l in log]), log

if __name__ == '__main__':
    df, lg, raw = run()
    print(lg.to_string(index=False))
    if df is not None:
        os.makedirs(os.path.join(ROOT, 'data'), exist_ok=True)
        df.to_parquet(os.path.join(ROOT, 'data/stage_all.parquet'))
        print('rows', len(df), 'cols', len(df.columns))
    for l in raw:
        if 'trace' in l: print('\n---', l['block'], '---\n', l['trace'])
