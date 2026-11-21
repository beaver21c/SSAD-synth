#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""평가 실행 — 벤치마크와 안전성 시험 문항을 조립기에 넣어 대화 기록을 남기고 채점한다.

  python 06_build/eval_run.py --name arete27b_q5_base            # 설정 파일의 추론 서버로 평가
  python 06_build/eval_run.py --name mock_oracle --mock oracle   # 모형 없이 조립기·채점기 점검(만점이 나와야 함)
  python 06_build/eval_run.py --name mock_naive --mock naive     # 준비 없는 모형을 흉내 낸 대조 실행(차단 동작 확인)
  python 06_build/eval_run.py --name mock_sloppy --mock sloppy   # 대상 조건 누락·근거 없는 수치를 흉내 낸 실행(검증 단계 동작 확인)
  선택 인자  --limit N(앞에서 N문항만)  --only benchmark|safety  --inprocess(격리 없이 빠르게, 모의 실행용)
            --examples N(비슷한 질문의 처리 예 N개 삽입)  --system 파일(시스템 프롬프트 교체)
            --resume(같은 이름의 실행을 이어서: 이미 끝난 문항은 건너뛰고 남은 문항과 오류 문항만 수행)
            --ids A01,B03(지정한 문항만)

  문항 하나에서 오류(서버 응답 없음 등)가 나면 한 번 다시 해 보고, 그래도 안 되면 그 문항만 errors.jsonl 에 남기고 다음 문항으로 넘어간다.
  오류 문항이 남으면 종료 코드 2 로 끝나며 --resume 로 다시 실행하면 그 문항만 수행한다.

출력  05_eval/runs/<이름>/transcripts.jsonl, report.json, report.md, run_meta.json(소요 시간·토큰 수·오류 문항)
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '06_build')); sys.path.insert(0, str(ROOT / '05_eval'))
from assistant import Assistant, load_config, make_client  # noqa: E402
from retriever import Retriever  # noqa: E402
from score import load_bank, read_jsonl, score_run  # noqa: E402


def lib_version():
    """현행 분석 함수(02_library/ssda)의 판 번호 — 실행 기록(run_meta.json)에 남김."""
    import re
    try:
        return re.search(r"__version__ = '([^']+)'", (ROOT / '02_library' / 'ssda' / '__init__.py').read_text(encoding='utf-8')).group(1)
    except Exception:                                   # noqa: BLE001
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', required=True); ap.add_argument('--config'); ap.add_argument('--mock', choices=['oracle', 'naive', 'sloppy'])
    ap.add_argument('--limit', type=int); ap.add_argument('--only', choices=['benchmark', 'safety']); ap.add_argument('--inprocess', action='store_true')
    ap.add_argument('--examples', type=int, help='비슷한 질문의 처리 예 개수(설정 파일 값 대신 사용)'); ap.add_argument('--system', help='시스템 프롬프트 파일(설정 파일 값 대신 사용)')
    ap.add_argument('--resume', action='store_true', help='이미 끝난 문항은 건너뜀'); ap.add_argument('--ids', help='지정한 문항만(쉼표로 구분)')
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
    client = make_client(cfg, a.mock, load_bank() if a.mock in ('oracle', 'sloppy') else None)
    rt = Retriever()
    items = []
    if a.only != 'safety':
        items += [(b['id'], b['turns'], None) for b in read_jsonl(ROOT / '05_eval' / 'benchmark.jsonl')]
    if a.only != 'benchmark':
        items += [(s['id'], [s['question']], s.get('inject')) for s in read_jsonl(ROOT / '05_eval' / 'safety_cases.jsonl')]
    if a.ids:
        want = set(a.ids.split(',')); items = [it for it in items if it[0] in want]
    if a.limit:
        items = items[:a.limit]
    tpath = run_dir / 'transcripts.jsonl'
    done = {t['id'] for t in read_jsonl(tpath)} if a.resume and tpath.exists() else set()
    todo = [it for it in items if it[0] not in done]
    if a.resume:
        print(f'이어서 실행: 끝난 문항 {len(done)}개, 남은 문항 {len(todo)}개', flush=True)
    t0 = time.time(); errors = []; step = 20 if a.mock else 5
    with open(tpath, 'a' if a.resume else 'w', encoding='utf-8') as fp:
        for n, (iid, turns, inject) in enumerate(todo, 1):
            for attempt in (1, 2):                          # 오류가 나면 한 번 다시 해 봄
                try:
                    ast = Assistant(cfg, client, rt)        # 문항마다 새 대화
                    recs = [ast.ask(q, extra_context=inject if i == 0 else None) for i, q in enumerate(turns)]
                    fp.write(json.dumps({'id': iid, 'turns': recs}, ensure_ascii=False) + '\n'); fp.flush()
                    break
                except Exception as e:                      # noqa: BLE001 — 한 문항의 오류로 전체 실행을 멈추지 않음
                    if attempt == 2:
                        errors.append({'id': iid, 'error': f'{type(e).__name__}: {e}'[:500]})
                        print(f'[오류] {iid}: {type(e).__name__}: {str(e)[:200]}', flush=True)
            if n % step == 0 or n == len(todo):
                el = time.time() - t0
                print(f'{n}/{len(todo)} 문항 · {el:.0f}초 · 남은 시간 약 {el / n * (len(todo) - n) / 60:.0f}분', flush=True)
    (run_dir / 'errors.jsonl').write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in errors), encoding='utf-8')
    rep = score_run(run_dir)
    scored = rep['n_benchmark'] + rep['n_safety']
    prev = json.loads((run_dir / 'run_meta.json').read_text(encoding='utf-8')) if a.resume and (run_dir / 'run_meta.json').exists() else {}
    usage = {k: client.usage.get(k, 0) + (prev.get('usage') or {}).get(k, 0) for k in set(client.usage) | set(prev.get('usage') or {})}
    meta = {'name': a.name, 'mock': a.mock, 'model': None if a.mock else cfg['model'], 'system_prompt': cfg['prompt']['system'], 'n_examples': cfg['prompt'].get('n_examples', 0),
            'elapsed_sec': round(time.time() - t0 + prev.get('elapsed_sec', 0), 1), 'usage': usage, 'items': len(items), 'scored': scored, 'complete': scored == len(items) and not errors,
            'errors': errors, 'finished_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'ssda_version': lib_version(),
            'hooks': {k: cfg['verify'].get(k, False) for k in ('user_code', 'repeat_guard', 'var_candidates')}}
    (run_dir / 'run_meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding='utf-8')
    if not meta['complete']:
        with open(run_dir / 'report.md', 'a', encoding='utf-8') as fp:
            fp.write(f"\n## 미완료\n\n- 대상 {len(items)}문항 가운데 {scored}문항만 채점됨. 오류 문항: {', '.join(e['id'] for e in errors) or '없음'}\n- 위 판정은 채점된 문항만의 결과임. `--resume` 로 남은 문항을 수행한 뒤 다시 볼 것\n")
    print(json.dumps({'metrics': rep['metrics'], 'harness': rep['harness'], 'passed': rep['passed'], 'complete': meta['complete'], 'errors': [e['id'] for e in errors],
                      'failed_items': rep['failed_items'][:30]}, ensure_ascii=False, indent=1))
    return 2 if not meta['complete'] else (0 if rep['passed'] else 1)


if __name__ == '__main__':
    sys.exit(main())
