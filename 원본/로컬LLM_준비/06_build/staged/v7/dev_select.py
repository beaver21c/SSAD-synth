#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""개발 묶음 고르기(r3/계획.md 4절) — 기준 실행에서 정답이 아니었던 산출 문항 전부, 정답이었던 산출 문항에서 무작위 40개, D·H 묶음 전부, E 묶음의 거절 문항 6개.

  python 06_build/staged/v7/dev_select.py <차수 폴더(r2)> <기준 실행> <출력 파일>
출력  문항 id 를 쉼표로 이은 한 줄(run_pipeline_round2.sh 의 @파일, eval_indep.py 의 --ids 에 씀)
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path('/mnt/share/행정데이터_set/로컬LLM_준비')
rid, run, out = sys.argv[1:4]
items = [json.loads(l) for l in (ROOT / '05_eval/independent' / rid / 'items/all.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
sc = json.loads((ROOT / '05_eval/runs' / run / 'indep_score.json').read_text(encoding='utf-8'))
rows = {r['id']: r for r in sc['rows']}
calc = [b['id'] for b in items if rows[b['id']]['class'] != 'judge']
bad = [i for i in calc if rows[i]['class'] != 'correct']
good = [i for i in calc if rows[i]['class'] == 'correct']
random.seed(20261118)
pick = set(bad) | set(random.sample(good, min(40, len(good)))) | {b['id'] for b in items if b['stratum'] in 'DH'}
pick |= set(random.sample(sorted(b['id'] for b in items if b['stratum'] == 'E' and b['expect'] == 'refuse'), 6))
ids = [b['id'] for b in items if b['id'] in pick]
Path(out).write_text(','.join(ids) + '\n', encoding='utf-8')
print(f'{len(ids)}문항: 정답 아님 {len(bad)} · 정답 표본 {len(set(good) & pick)} · D·H {sum(1 for b in items if b["stratum"] in "DH")} · E 거절 6')
