#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""95% 판정 — 끝난 평가 실행 가운데 벤치마크 문항 통과율이 가장 높은 구성을 고르고 목표(기본 0.95)에 이르렀는지 본다.

  python 06_build/staged/v3/judge.py [--target 0.95] [--runs 이름,이름…] [--out 파일]
  · 통과율은 보완한 채점기(이 폴더의 score.py: 산출 횟수가 달라도 값·인원 구성이 같으면 일치)로 대화 기록을 다시 채점한 값이다. 기존 보고서의 값도 함께 적는다.
  · 출력(JSON): decision(run: 대책 실행 / skip: 목표 도달), best(실행 이름), tag(q5·q4·lora), prompt(그 실행의 시스템 프롬프트), table(실행별 값)
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
DEFAULT = ['arete27b_q5_v2_base', 'arete27b_q4_v2_base', 'arete27b_lora_short_base', 'arete27b_lora_long_base', 'arete27b_lora_v2_base', 'arete27b_lora_v2_r2_base', 'arete27b_lora_v3_base']


def load_scorer():
    live = (ROOT / '05_eval' / 'score.py')
    path = live if 'pooled_match' in live.read_text(encoding='utf-8') else HERE / 'score.py'      # 반영 뒤에는 현행 채점기가 보완본임
    sp = importlib.util.spec_from_file_location('score_judge', path); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
    m.HERE = ROOT / '05_eval'
    return m, str(path.relative_to(ROOT))


def tag_of(run, meta):
    f = str((meta.get('model') or {}).get('file', ''))
    return 'lora' if 'lora' in run or 'lora' in f else 'q4' if '_q4_' in run or 'Q4_K_M' in f else 'q6' if '_q6_' in run else 'q5'


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--target', type=float, default=0.95); ap.add_argument('--runs'); ap.add_argument('--out'); ap.add_argument('--prefix', default='')
    a = ap.parse_args()
    sc, scorer = load_scorer()
    bench, safe = sc.read_jsonl(ROOT / '05_eval' / 'benchmark.jsonl'), sc.read_jsonl(ROOT / '05_eval' / 'safety_cases.jsonl')
    table = []
    for run in [a.prefix + r for r in (a.runs.split(',') if a.runs else DEFAULT)]:
        d = ROOT / '05_eval' / 'runs' / run
        meta = json.loads((d / 'run_meta.json').read_text(encoding='utf-8')) if (d / 'run_meta.json').exists() else {}
        if not meta.get('complete') or not (d / 'transcripts.jsonl').exists():
            table.append({'run': run, 'state': '없음 또는 미완료'}); continue
        tr = {t['id']: t['turns'] for t in sc.read_jsonl(d / 'transcripts.jsonl')}
        b = [sc.score_item(x, tr[x['id']]) for x in bench if x['id'] in tr]
        s = [sc.score_safety(x, tr[x['id']]) for x in safe if x['id'] in tr]
        old = json.loads((d / 'report.json').read_text(encoding='utf-8')) if (d / 'report.json').exists() else {}
        nb = sum(bool(r['passed']) for r in b)
        table.append({'run': run, 'state': '완료', 'tag': tag_of(run, meta), 'prompt': meta.get('system_prompt'), 'n_bench': len(b), 'pass_bench': nb, 'rate': round(nb / max(len(b), 1), 4),
                      'pass_all': nb + sum(bool(r['passed']) for r in s), 'n_all': len(b) + len(s), 'rate_report': (old.get('metrics') or {}).get('문항 통과율'),
                      'failed': [r['id'] for r in b + s if not r['passed']]})
    done = [t for t in table if t['state'] == '완료' and t['n_bench'] >= (3 if a.prefix else 100)]
    best = max(done, key=lambda t: (t['rate'], t['pass_all'])) if done else None
    out = {'target': a.target, 'scorer': scorer, 'decision': 'none' if not best else 'skip' if best['rate'] >= a.target else 'run',
           'best': best and best['run'], 'tag': best and best['tag'], 'prompt': best and best['prompt'], 'rate': best and best['rate'],
           'need': best and max(0, -(-int(a.target * best['n_bench'] * 10000) // 10000) - best['pass_bench']), 'table': table}
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if a.out:
        Path(a.out).write_text(text, encoding='utf-8')
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
