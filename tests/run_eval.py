#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""자연어 분석 자동 시험(Gemini) — 원본의 독립 검증 문항을 Gemini 로 돌리고, 원본 채점기로 채점한 뒤, 보완할 곳을 정리한다.

  원본의 실행기(06_build/eval_indep.py)와 채점기(05_eval/independent/score_outcome.py)를 고치지 않고 불러 쓴다.
  바꾸는 것은 두 가지뿐이다: ① 언어모형 연결부 → Gemini API ② 결과가 쌓이는 곳 → tests/results/ (원본/ 안에는 쓰지 않음)
  채점은 pandas 로 직접 계산해 둔 참값(truth.json)과 화면에 제시된 값을 대조하는 방식이다(코드 모양은 보지 않음).

사용 (키는 환경 변수 GEMINI_API_KEY)
  python tests/run_eval.py --name g1 --sample 3          # 묶음(A~H)마다 3문항씩 뽑아 시험(무료 한도 안에서 먼저 돌려 보는 용도)
  python tests/run_eval.py --name g1 --resume            # 한도 초과 등으로 멈춘 뒤 이어서(끝난 문항은 건너뜀)
  python tests/run_eval.py --name full                   # 188문항 전체
  python tests/run_eval.py --name g1 --score-only        # 채점·보고서만 다시
  선택  --round r4(다른 차수의 문항 묶음: r2·r3·r4 는 각 188문항, 보완 효과를 처음 보는 문항으로 잴 때)  --prompt 파일(시스템 프롬프트 바꿔 보기)  --ruleset N(조립기 규칙 묶음)
        --ids A001,B003  --model gemini-2.5-flash  --rpm 8(분당 호출 상한)  --mock(키 없이 경로만 점검)
산출  tests/results/<이름>/transcripts.jsonl · run_meta.json · indep_score.json · report.md(문항별 판정과 실패 유형별 보완 단서)
"""
import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import paths  # noqa: E402
from app.fetch_data import data_path  # noqa: E402
from app.gemini_client import KEY_ENV, GeminiClient  # noqa: E402

OUT = ROOT / 'tests' / 'results'
INDEP = paths.LLM_DIR / '05_eval' / 'independent'
LABEL = {'correct': '정답', 'wrong': '조용한 오답', 'unexecuted': '실행 없이 값 제시', 'no_value': '값 없음'}


def read_jsonl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding='utf-8').splitlines() if l.strip()]


class Throttled:
    """분당 호출 수를 넘지 않게 간격을 두는 덧씌움(무료 한도 대응)."""

    def __init__(self, client, rpm):
        self.c, self.gap, self.last, self.quota_fail = client, (60.0 / rpm if rpm else 0), 0.0, 0

    def chat(self, messages):
        wait = self.gap - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.time()
        try:
            out = self.c.chat(messages)
        except Exception as e:
            if getattr(e, 'status', None) == 429:
                self.quota_fail += 1
                if self.quota_fail >= 3:                   # 일일 한도 소진: 남은 문항을 오류로 채우지 않고 멈춤
                    print('[중단] 한도 초과(429)가 3회 이어져 멈춤. 한도가 풀린 뒤 --resume 으로 이어서 실행.', flush=True)
                    raise SystemExit(3)
            raise
        self.quota_fail = 0
        return out

    def __getattr__(self, k):
        return getattr(self.c, k)


def pick_items(a):
    items = read_jsonl(INDEP / 'items' / 'all.jsonl')
    if a.ids:
        want = set(a.ids.split(','))
        return [b for b in items if b['id'] in want]
    if a.sample:
        rnd = random.Random(a.seed)
        by = {}
        for b in items:
            by.setdefault(b['stratum'], []).append(b)
        return [b for s in sorted(by) for b in sorted(rnd.sample(by[s], min(a.sample, len(by[s]))), key=lambda x: x['id'])]
    return items


def run(a, run_dir):
    for p in (paths.LLM_DIR / '06_build', paths.LLM_DIR / '02_library'):
        sys.path.insert(0, str(p))
    os.environ['SSDA_DATA'] = str(data_path())
    os.environ.pop('SSDA_HOOKS', None)
    import eval_indep as ev                                # 원본 실행기
    items_file = run_dir / 'items.jsonl'
    if not (a.resume and items_file.exists()):             # 이어 돌릴 때는 처음 뽑은 문항 그대로
        items_file.write_text('\n'.join(json.dumps(b, ensure_ascii=False) for b in pick_items(a)) + '\n', encoding='utf-8')
    client = None if a.mock else Throttled(GeminiClient(model=a.model, timeout=180, retries=4), a.rpm)
    ev.ROOT = _Shim(run_dir)                               # 결과 폴더만 tests/results/<이름> 으로
    if client:
        ev.make_client = lambda cfg, mock=None, bank=None: client
    argv = ['eval_indep', '--name', a.name, '--items', str(items_file)] + (['--system', str((ROOT / a.prompt).resolve())] if a.prompt else []) + (['--ruleset', str(a.ruleset)] if a.ruleset else []) + (['--resume'] if a.resume else []) + (['--mock', 'oracle'] if a.mock else [])
    old, sys.argv = sys.argv, argv
    try:
        rc = ev.main()
    finally:
        sys.argv = old
    if client:
        meta_p = run_dir / 'run_meta.json'
        meta = json.loads(meta_p.read_text(encoding='utf-8'))
        meta['model'] = {'provider': 'gemini', 'name': client.used_model or a.model, 'rpm': a.rpm}
        meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding='utf-8')
    return rc


class _Shim:
    """원본 실행기가 ROOT / '05_eval' / 'runs' / 이름 으로 만드는 경로를 결과 폴더 하나로 모은다. 그 밖의 경로는 원본 그대로."""

    def __init__(self, run_dir):
        self.run_dir = run_dir

    def __truediv__(self, part):
        return _Runs(self.run_dir) if part == '05_eval' else paths.LLM_DIR / part


class _Runs:
    def __init__(self, run_dir, depth=0):
        self.run_dir, self.depth = run_dir, depth

    def __truediv__(self, part):
        return self.run_dir if self.depth == 1 else _Runs(self.run_dir, self.depth + 1)


def score(a, run_dir):
    sys.path.insert(0, str(INDEP))
    import score_outcome as so                             # 원본 채점기
    so.RD = OUT
    so.BASE = INDEP
    ids = {b['id'] for b in read_jsonl(run_dir / 'items.jsonl')}
    done = {t['id'] for t in read_jsonl(run_dir / 'transcripts.jsonl')}
    items = [b for b in read_jsonl(INDEP / 'items' / 'all.jsonl') if b['id'] in ids & done]
    truth = json.loads((INDEP / 'truth' / 'truth.json').read_text(encoding='utf-8'))
    rows = so.score_run(a.name, items, truth)
    rep = {'run': a.name, 'summary': so.summarize(rows), 'rows': rows}
    (run_dir / 'indep_score.json').write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding='utf-8')
    return rep, items


def clue(turn_rec):
    """실패한 차례에서 보완 단서를 뽑는다(마지막 단계의 오류·차단·경고, 응답 머리)."""
    out = []
    for s in turn_rec.get('steps') or []:
        if s.get('violations'):
            out.append('실행 전 점검 차단: ' + '; '.join(str(v) for v in s['violations'])[:160])
        elif s.get('error'):
            out.append('오류: ' + s['error'].splitlines()[0][:160])
    ver = turn_rec.get('verification') or {}
    for k in ('warnings', 'number_mismatch'):
        if ver.get(k):
            out.append(f'{k}: ' + json.dumps(ver[k], ensure_ascii=False)[:160])
    return out


def report(a, run_dir, rep, items):
    tr = {t['id']: t['turns'] for t in read_jsonl(run_dir / 'transcripts.jsonl')}
    meta = json.loads((run_dir / 'run_meta.json').read_text(encoding='utf-8')) if (run_dir / 'run_meta.json').exists() else {}
    s = rep['summary']
    L = [f"# 자연어 분석 자동 시험 결과 — {a.name}", '',
         f"- 모형: {json.dumps(meta.get('model'), ensure_ascii=False)} · 프롬프트: {meta.get('system_prompt')} · 분석 함수 ssda {meta.get('ssda_version')}",
         f"- 문항 차수: {a.round or '1차'} · 문항: {len(items)}개 · 완료 여부: {meta.get('complete')} · 호출: {json.dumps(meta.get('usage'), ensure_ascii=False)} · 소요 {meta.get('elapsed_sec')}초",
         f"- 산출 차례 {s['core_turns']} · 정답 {s['correct_turns']['k']}건({s['correct_turns']['pct']}%, 95% 구간 {s['correct_turns']['ci95']}) · 조용한 오답 {s['silent_wrong']['k']}건({s['silent_wrong']['pct']}%)",
         '- 참고(원본 로컬 모형의 독립 검증 4차 판정): 정답 96.1%, 조용한 오답 3.2% — 문항 구성이 같을 때만 견줄 수 있음', '',
         '## 묶음별', '', '| 묶음 | 문항 | 정답 | 조용한 오답 | 실행 없이 값 | 값 없음 |', '|---|---:|---:|---:|---:|---:|']
    for st, v in sorted((s.get('by_stratum') or {}).items()):
        L.append(f"| {st} | {v['items']} | {v['correct']['k']} ({v['correct']['pct']}%) | {v['wrong']} | {v['unexecuted']} | {v['no_value']} |")
    L += ['', '## 정답이 아닌 차례(보완 대상)', '']
    n = 0
    for r in rep['rows']:
        for t in r.get('turns') or []:
            if t.get('class') == 'correct' or not t.get('core', True):
                continue
            n += 1
            rec = (tr.get(r['id']) or [{}] * 9)[t.get('turn', 1) - 1]
            L += [f"### {r['id']} · 차례 {t.get('turn', 1)} · {LABEL.get(t.get('class'), t.get('class'))}" + (f" ({t.get('sub')})" if t.get('sub') else ''),
                  '', '- 질문: ' + ' '.join((rec.get('question') or '').split())[:300]]
            code = next((x['code'] for x in reversed(rec.get('steps') or []) if x.get('code')), '')
            if code:
                L += ['- 마지막 코드:', '', '```python', code.strip()[:900], '```']
            L += ['- 단서: ' + c for c in clue(rec)]
            L += ['- 응답 머리: ' + ' '.join((rec.get('final') or '').split())[:240], '']
    if not n:
        L.append('없음')
    if meta.get('errors'):
        L += ['', '## 실행하지 못한 문항', ''] + [f"- {e['id']}: {e['error'][:200]}" for e in meta['errors']]
    (run_dir / 'report.md').write_text('\n'.join(L) + '\n', encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', required=True); ap.add_argument('--sample', type=int); ap.add_argument('--seed', type=int, default=20261122)
    ap.add_argument('--ids'); ap.add_argument('--resume', action='store_true'); ap.add_argument('--score-only', action='store_true')
    ap.add_argument('--round', help='문항 차수 폴더(r2·r3·r4). 주지 않으면 1차 문항'); ap.add_argument('--prompt', help='시스템 프롬프트 파일(저장소 기준 경로)'); ap.add_argument('--ruleset', type=int, help='조립기 규칙 묶음(기본은 원본 설정의 9)')
    ap.add_argument('--model', default=os.environ.get('GEMINI_MODEL')); ap.add_argument('--rpm', type=float, default=8); ap.add_argument('--mock', action='store_true')
    a = ap.parse_args()
    global INDEP
    if a.round:
        INDEP = INDEP / a.round
    run_dir = OUT / a.name
    run_dir.mkdir(parents=True, exist_ok=True)
    rc = 0
    if not a.score_only:
        if not a.mock and not os.environ.get(KEY_ENV):
            sys.exit(f'환경 변수 {KEY_ENV} 가 없음')
        rc = run(a, run_dir)
    rep, items = score(a, run_dir)
    report(a, run_dir, rep, items)
    s = rep['summary']
    print(f"채점: 산출 차례 {s['core_turns']} · 정답 {s['correct_turns']['pct']}% · 조용한 오답 {s['silent_wrong']['pct']}% → {run_dir / 'report.md'}")
    return rc


if __name__ == '__main__':
    sys.exit(main())
