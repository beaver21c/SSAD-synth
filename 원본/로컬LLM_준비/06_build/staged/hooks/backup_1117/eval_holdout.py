#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""보류 검증 문항 평가 — 05_eval/holdout.jsonl 의 문항을 조립기에 넣어 채점한다(eval_run.py 와 같은 조립기·채점 함수를 쓴다).

  python 06_build/eval_holdout.py --name holdout_q5_v1                                          # 설정 파일의 시스템 프롬프트로
  python 06_build/eval_holdout.py --name holdout_q5_v2 --system 03_prompts/system_prompt_v2.md  # 시스템 프롬프트만 바꿔서
  python 06_build/eval_holdout.py --name holdout_oracle --mock oracle --inprocess               # 모형 없이 채점기 점검(만점이 나와야 함)
  선택 인자  --resume(끝난 문항은 건너뜀)  --limit N  --examples N  --config 파일

쓰는 까닭  시스템 프롬프트 개선판은 벤치마크의 미통과 원인을 보고 만들었으므로, 벤치마크로만 재면 개선 폭이 크게 나올 수 있다.
           개선판을 쓴 뒤에 따로 만든 문항(05_eval/build_holdout.py)으로 같은 방향의 개선이 나타나는지 본다.
출력  05_eval/runs/<이름>/transcripts.jsonl, holdout_report.json, holdout_report.md, run_meta.json
"""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '06_build')); sys.path.insert(0, str(ROOT / '05_eval'))
from assistant import Assistant, load_config, make_client  # noqa: E402
from retriever import Retriever  # noqa: E402
import score  # noqa: E402
import analyze_runs  # noqa: E402

ITEMS = ROOT / '05_eval' / 'holdout.jsonl'


def lib_version():
    """현행 분석 함수(02_library/ssda)의 판 번호 — 실행 기록(run_meta.json)에 남김."""
    import re
    try:
        return re.search(r"__version__ = '([^']+)'", (ROOT / '02_library' / 'ssda' / '__init__.py').read_text(encoding='utf-8')).group(1)
    except Exception:                                   # noqa: BLE001
        return None


def bank_of(items):
    """모의 모형(oracle)용: 질문 → 정답 코드·기대 행동."""
    bank = {}
    for b in items:
        beh = b['expect'].get('behavior', 'analyze')
        for i, q in enumerate(b['turns']):
            last = i == len(b['turns']) - 1
            bank[q] = {'code': b['gold_code'] if last else "import ssda\nprint(ssda.info())", 'behavior': beh if last else 'analyze'}
    return bank


def score_one(b, turns):
    if b['expect'].get('behavior') == 'refuse':
        sc = score.score_safety({'id': b['id'], 'type': b.get('type', ''), 'behavior': 'refuse'}, turns)
        cause, ev = ('', '') if sc['passed'] else analyze_runs.classify_safety({'behavior': 'refuse'}, sc, turns)
    else:
        sc = score.score_item(b, turns)
        cause, ev = ('', '') if sc['passed'] else analyze_runs.classify(b, sc, turns)
    return {'id': b['id'], 'category': b['category'], 'question': b['turns'][-1], 'passed': bool(sc['passed']), 'cause': cause, 'evidence': ev,
            'asked': '확인 필요' in (turns[-1]['final'] or '') and not turns[-1]['steps'], 'n_calls': turns[-1].get('n_calls')}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', required=True); ap.add_argument('--config'); ap.add_argument('--system'); ap.add_argument('--mock', choices=['oracle'])
    ap.add_argument('--examples', type=int); ap.add_argument('--limit', type=int); ap.add_argument('--resume', action='store_true'); ap.add_argument('--inprocess', action='store_true')
    a = ap.parse_args()
    cfg = load_config(a.config)
    if a.examples is not None:
        cfg['prompt']['n_examples'] = a.examples
    if a.system:
        cfg['prompt']['system'] = a.system
    run_dir = ROOT / '05_eval' / 'runs' / a.name
    run_dir.mkdir(parents=True, exist_ok=True)
    cfg['paths'].update(export=str(run_dir / 'export'), log=str(run_dir / 'ssda_log.jsonl'), transcripts=str(run_dir / 'assistant_log.jsonl'))
    if a.inprocess:
        cfg['run']['isolate'] = False
    items = score.read_jsonl(ITEMS)
    if a.limit:
        items = items[:a.limit]
    client = make_client(cfg, a.mock, bank_of(items) if a.mock else None)
    rt = Retriever()
    tpath = run_dir / 'transcripts.jsonl'
    done = {t['id'] for t in score.read_jsonl(tpath)} if a.resume and tpath.exists() else set()
    todo = [b for b in items if b['id'] not in done]
    t0 = time.time(); errors = []
    with open(tpath, 'a' if a.resume else 'w', encoding='utf-8') as fp:
        for n, b in enumerate(todo, 1):
            for attempt in (1, 2):
                try:
                    ast = Assistant(cfg, client, rt)
                    recs = [ast.ask(q) for q in b['turns']]
                    fp.write(json.dumps({'id': b['id'], 'turns': recs}, ensure_ascii=False) + '\n'); fp.flush()
                    break
                except Exception as e:                      # noqa: BLE001
                    if attempt == 2:
                        errors.append({'id': b['id'], 'error': f'{type(e).__name__}: {e}'[:500]})
                        print(f"[오류] {b['id']}: {type(e).__name__}: {str(e)[:200]}", flush=True)
            if n % 5 == 0 or n == len(todo):
                el = time.time() - t0
                print(f'{n}/{len(todo)} 문항 · {el:.0f}초 · 남은 시간 약 {el / n * (len(todo) - n) / 60:.0f}분', flush=True)
    tr = {t['id']: t['turns'] for t in score.read_jsonl(tpath)}
    rows = [score_one(b, tr[b['id']]) for b in items if b['id'] in tr]
    cat = {}
    for r in rows:
        c = cat.setdefault(r['category'], [0, 0]); c[0] += r['passed']; c[1] += 1
    ana = [r for r in rows if not r['category'].startswith(('Y', 'Z'))]
    rep = {'run': a.name, 'system_prompt': cfg['prompt']['system'], 'n': len(rows), 'n_pass': sum(r['passed'] for r in rows),
           'pass_rate': round(sum(r['passed'] for r in rows) / max(1, len(rows)), 4),
           '산출 문항 통과': f"{sum(r['passed'] for r in ana)}/{len(ana)}", '산출 문항에서 되물은 수': sum(r['asked'] for r in ana),
           '되물어야 하는 질문 통과': f"{cat.get('Y 되물어야 하는 질문', [0, 0])[0]}/{cat.get('Y 되물어야 하는 질문', [0, 0])[1]}",
           '응하지 않는 요청 통과': f"{cat.get('Z 응하지 않는 요청', [0, 0])[0]}/{cat.get('Z 응하지 않는 요청', [0, 0])[1]}",
           'by_category': {k: f'{v[0]}/{v[1]}' for k, v in cat.items()}, 'fail_by_cause': dict(Counter(r['cause'] for r in rows if not r['passed']).most_common()), 'rows': rows}
    (run_dir / 'holdout_report.json').write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding='utf-8')
    L = [f"# 보류 검증 문항 평가 — {a.name}", '', f"- 시스템 프롬프트: {cfg['prompt']['system']}", f"- 통과 {rep['n_pass']}/{rep['n']} ({rep['pass_rate'] * 100:.1f}%)",
         f"- 산출 문항 통과 {rep['산출 문항 통과']}, 그 가운데 코드 없이 되물은 문항 {rep['산출 문항에서 되물은 수']}개",
         f"- 되물어야 하는 질문 {rep['되물어야 하는 질문 통과']}, 응하지 않는 요청 {rep['응하지 않는 요청 통과']}", '- 분류별: ' + ', '.join(f'{k} {v}' for k, v in rep['by_category'].items()),
         '- 미통과 원인: ' + (', '.join(f'{k} {v}' for k, v in rep['fail_by_cause'].items()) or '없음'), '', '| 문항 | 분류 | 원인 | 질문 | 근거 |', '|---|---|---|---|---|']
    for r in rows:
        if not r['passed']:
            L.append(f"| {r['id']} | {r['category']} | {r['cause']} | {str(r['question'])[:60].replace('|', '/').replace(chr(10), ' ')} | {r['evidence'].replace('|', '/').replace(chr(10), ' ')} |")
    (run_dir / 'holdout_report.md').write_text('\n'.join(L) + '\n', encoding='utf-8')
    prev = json.loads((run_dir / 'run_meta.json').read_text(encoding='utf-8')) if a.resume and (run_dir / 'run_meta.json').exists() else {}
    usage = {k: client.usage.get(k, 0) + (prev.get('usage') or {}).get(k, 0) for k in set(client.usage) | set(prev.get('usage') or {})}
    meta = {'name': a.name, 'mock': a.mock, 'model': None if a.mock else cfg['model'], 'system_prompt': cfg['prompt']['system'], 'n_examples': cfg['prompt'].get('n_examples', 0),
            'elapsed_sec': round(time.time() - t0 + prev.get('elapsed_sec', 0), 1), 'usage': usage, 'items': len(items), 'scored': len(rows), 'complete': len(rows) == len(items) and not errors,
            'errors': errors, 'finished_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'ssda_version': lib_version(), 'kind': 'holdout'}
    (run_dir / 'run_meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: v for k, v in rep.items() if k != 'rows'}, ensure_ascii=False, indent=1))
    return 0 if meta['complete'] else 2


if __name__ == '__main__':
    sys.exit(main())
