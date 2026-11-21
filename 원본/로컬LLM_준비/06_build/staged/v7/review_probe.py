#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""검토 단계(review)의 판별력 측정 — 기록된 대화의 산출(질문·코드·산출 정의)을 모형에 검토시켜, 채점 결과(정답·오답)별로 「불일치」 판정 비율을 본다.

  python 06_build/staged/v7/review_probe.py --tree <ssda·조립기를 읽을 폴더> --system <시스템 프롬프트> --out <결과 json> <INDEP_DIR>:<run> [<INDEP_DIR>:<run> …] [--limit N]
- 추론 서버가 떠 있어야 함(config/assistant.yaml 의 주소). 대화를 다시 실행하지 않고 검토 요청 1회만 보냄(문항당 모형 호출 1회)
- 대상: 산출을 요구하는 차례 가운데 성공한 실행이 있고 채점이 정답(correct) 또는 오답(wrong)인 차례
- 개발 묶음(이미 결과를 본 문항)에서의 측정이며 판정에 쓰지 않음. 반영 여부를 정하는 기준은 실행 전에 r3/계획.md 에 적음
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path('/mnt/share/행정데이터_set/로컬LLM_준비')
ap = argparse.ArgumentParser()
ap.add_argument('--tree', required=True); ap.add_argument('--system', required=True); ap.add_argument('--out', required=True); ap.add_argument('--limit', type=int)
ap.add_argument('runs', nargs='+')
a = ap.parse_args()
tree = Path(a.tree).resolve()
sys.path.insert(0, str(tree / '02_library')); sys.path.insert(0, str(tree / '06_build'))
from assistant import load_config  # noqa: E402
from clients import OpenAICompatClient  # noqa: E402
from ssda import verify  # noqa: E402
import os  # noqa: E402

cfg = load_config(str(ROOT / 'config' / 'assistant.yaml'))
m = cfg['model']
client = OpenAICompatClient(m['base_url'], m['served_name'], os.environ.get(m.get('api_key_env') or '', ''), m.get('temperature', 0.0), 400, m.get('timeout_sec', 600), m.get('extra_body'))
system = Path(a.system).read_text(encoding='utf-8').strip()
rows = []
t0 = time.time()
for spec in a.runs:
    indep, run = spec.split(':')
    sc = json.loads((ROOT / '05_eval/runs' / run / 'indep_score.json').read_text(encoding='utf-8'))
    cls = {(r['id'], t['turn']): t['class'] for r in sc['rows'] for t in r['turns']}
    T = [json.loads(l) for l in (ROOT / '05_eval/runs' / run / 'transcripts.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    todo = []
    for t in T:
        for k, tr in enumerate(t['turns'], 1):
            c = cls.get((t['id'], k))
            last = next((s for s in reversed(tr['steps']) if s.get('ok') and s.get('results')), None)
            if c in ('correct', 'wrong') and last:
                todo.append((t, k, tr, c, last))
    if a.limit:
        wrong = [x for x in todo if x[3] == 'wrong']; right = [x for x in todo if x[3] == 'correct']
        todo = wrong + right[:max(a.limit - len(wrong), 0)]
    for t, k, tr, c, last in todo:
        qs = [x['question'] for x in t['turns'][:k]]
        unused = [i[4:] for i in tr.get('context_ids') or [] if i.startswith('var:')]
        req = verify.review_request(qs, last, unused)
        text = client.chat([{'role': 'system', 'content': system}, {'role': 'user', 'content': req}])
        rows.append({'run': run, 'id': t['id'], 'turn': k, 'class': c, 'flag': verify.review_verdict(text), 'text': text[:600]})
        if len(rows) % 20 == 0:
            print(f'{len(rows)}건 · {time.time() - t0:.0f}초', flush=True)
out = {'system': a.system, 'tree': str(tree), 'rows': rows}
tab = {}
for r in rows:
    d = tab.setdefault(r['run'], {'correct': [0, 0], 'wrong': [0, 0]})
    d[r['class']][1] += 1; d[r['class']][0] += int(r['flag'])
out['summary'] = {run: {c: {'flagged': v[0], 'n': v[1]} for c, v in d.items()} for run, d in tab.items()}
Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
print(json.dumps(out['summary'], ensure_ascii=False))
