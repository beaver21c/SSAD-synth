#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""독립 검증 문항 실행 — 05_eval/independent/items/all.jsonl 의 문항을 조립기에 넣어 대화 기록만 남긴다(채점은 하지 않는다).

  python 06_build/eval_indep.py --name indep_c2                                   # 설정 파일 그대로
  python 06_build/eval_indep.py --name indep_c0 --system 03_prompts/system_prompt.md
  선택 인자  --config 파일  --ids A001,A002  --resume(끝난 문항은 건너뜀)  --limit N  --mock oracle(모형 없이 경로 점검)
  보완 동작은 설정의 verify 절 또는 환경변수 SSDA_HOOKS 로 정한다.
출력  05_eval/runs/<이름>/transcripts.jsonl, run_meta.json
채점은 05_eval/independent/score_outcome.py 가 대화 기록과 참값(truth/truth.json)으로 따로 한다. 기존 채점기(05_eval/score.py)는 쓰지 않는다.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '06_build'))
from assistant import Assistant, load_config, make_client  # noqa: E402
from retriever import Retriever  # noqa: E402

ITEMS = ROOT / '05_eval' / 'independent' / 'items' / 'all.jsonl'


def read_jsonl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding='utf-8').splitlines() if l.strip()]


def lib_version():
    import re
    try:
        return re.search(r"__version__ = '([^']+)'", (ROOT / '02_library' / 'ssda' / '__init__.py').read_text(encoding='utf-8')).group(1)
    except Exception:                                   # noqa: BLE001
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', required=True); ap.add_argument('--config'); ap.add_argument('--system'); ap.add_argument('--mock', choices=['oracle', 'naive'])
    ap.add_argument('--limit', type=int); ap.add_argument('--resume', action='store_true'); ap.add_argument('--ids'); ap.add_argument('--items', default=str(ITEMS))
    a = ap.parse_args()
    cfg = load_config(a.config)
    cfg['prompt']['n_examples'] = 0
    if a.system:
        cfg['prompt']['system'] = a.system
    run_dir = ROOT / '05_eval' / 'runs' / a.name
    run_dir.mkdir(parents=True, exist_ok=True)
    cfg['paths'].update(export=str(run_dir / 'export'), log=str(run_dir / 'ssda_log.jsonl'), transcripts=str(run_dir / 'assistant_log.jsonl'))
    items = read_jsonl(a.items)
    if a.ids:
        want = set(a.ids.split(',')); items = [b for b in items if b['id'] in want]
    if a.limit:
        items = items[:a.limit]
    client = make_client(cfg, a.mock, {} if a.mock else None)
    rt = Retriever()
    tpath = run_dir / 'transcripts.jsonl'
    done = {t['id'] for t in read_jsonl(tpath)} if a.resume and tpath.exists() else set()
    todo = [b for b in items if b['id'] not in done]
    t0 = time.time(); errors = []
    with open(tpath, 'a' if a.resume else 'w', encoding='utf-8') as fp:
        for n, b in enumerate(todo, 1):
            for attempt in (1, 2):
                try:
                    ast = Assistant(cfg, client, rt)
                    recs = [ast.ask(q, extra_context=(b.get('context') or None) if i == 0 else None) for i, q in enumerate(b['turns'])]
                    fp.write(json.dumps({'id': b['id'], 'turns': recs}, ensure_ascii=False) + '\n'); fp.flush()
                    break
                except Exception as e:                  # noqa: BLE001
                    if attempt == 2:
                        errors.append({'id': b['id'], 'error': f'{type(e).__name__}: {e}'[:500]})
                        print(f"[오류] {b['id']}: {type(e).__name__}: {str(e)[:200]}", flush=True)
            if n % 5 == 0 or n == len(todo):
                el = time.time() - t0
                print(f'{n}/{len(todo)} 문항 · {el:.0f}초 · 남은 시간 약 {el / n * (len(todo) - n) / 60:.0f}분', flush=True)
    got = {t['id'] for t in read_jsonl(tpath)}
    prev = json.loads((run_dir / 'run_meta.json').read_text(encoding='utf-8')) if a.resume and (run_dir / 'run_meta.json').exists() else {}
    usage = {k: client.usage.get(k, 0) + (prev.get('usage') or {}).get(k, 0) for k in set(client.usage) | set(prev.get('usage') or {})}
    meta = {'name': a.name, 'mock': a.mock, 'model': None if a.mock else cfg['model'], 'system_prompt': cfg['prompt']['system'], 'n_examples': 0,
            'elapsed_sec': round(time.time() - t0 + prev.get('elapsed_sec', 0), 1), 'usage': usage, 'items': len(items), 'done': len(got & {b['id'] for b in items}),
            'complete': all(b['id'] in got for b in items) and not errors, 'errors': errors, 'finished_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'ssda_version': lib_version(), 'kind': 'independent',
            'hooks': {k: cfg['verify'].get(k, False) for k in ('user_code', 'repeat_guard', 'var_candidates', 'unexecuted_results')}}
    (run_dir / 'run_meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: meta[k] for k in ('name', 'items', 'done', 'complete', 'elapsed_sec', 'hooks')}, ensure_ascii=False))
    return 0 if meta['complete'] else 2


if __name__ == '__main__':
    sys.exit(main())
