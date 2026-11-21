#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""통제 계층 공격 코드의 재실행 — 1차·2차 독립 공격 코드 110건을 지정한 분석 함수 폴더로 다시 실행해, 반영 뒤 재시험(redteam/retest_live.json)과 차단 여부·출력 길이를 견준다.

  python 06_build/staged/v7/redteam_retest.py <분석 함수 폴더(02_library 또는 사본)> <결과 json>
분석 함수를 고친 뒤 통제가 느슨해지지 않았는지 보는 회귀 확인이며 새 공격 시험이 아님.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path('/mnt/share/행정데이터_set/로컬LLM_준비')
lib, out_path = str(Path(sys.argv[1]).resolve()), sys.argv[2]
RT = ROOT / '05_eval/independent/redteam'
DATA = os.environ.get('SSDA_DATA', '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet')
TMP = Path(tempfile.mkdtemp(prefix='rt_v7_'))
prev = {x['id']: x for x in json.loads((RT / 'retest_live.json').read_text(encoding='utf-8'))}
files = sorted((RT / 'snippets').glob('X*.py')) + sorted((RT / 'round2' / 'snippets').glob('Y*.py'))
rows = []
for f in files:
    exp = TMP / 'export'; exp.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, 'SSDA_DATA': DATA, 'SSDA_EXPORT': str(exp), 'SSDA_LOG': str(TMP / 'ssda_log.jsonl'), 'PYTHONPATH': lib, 'MPLBACKEND': 'Agg'}
    try:
        p = subprocess.run([sys.executable, '-m', 'ssda.runner', str(f), '--timeout', '60', '--mem', '6'], capture_output=True, text=True, env=env, timeout=90, cwd=str(ROOT))
        o = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception as e:                              # noqa: BLE001
        o = {'ok': False, 'violations': [], 'stdout': '', 'error': f'실행기 출력 해석 실패 또는 시간 초과: {type(e).__name__}'}
    pv = prev.get(f.stem, {})
    rows.append({'id': f.stem, 'ok': bool(o.get('ok')), 'violations': o.get('violations') or [], 'error': (o.get('error') or '').splitlines()[0][:200] if o.get('error') else '', 'stdout_len': len(o.get('stdout') or ''),
                 'prev_ok': pv.get('ok'), 'prev_stdout_len': pv.get('stdout_len'), 'residual': pv.get('residual')})
chg = [r for r in rows if r['prev_ok'] is not None and (r['ok'] != bool(r['prev_ok']))]
out = {'lib': lib, 'n': len(rows), 'ok': sum(r['ok'] for r in rows), 'prev_ok': sum(bool(r['prev_ok']) for r in rows), 'changed_block_status': chg,
       'stdout_changed': [r['id'] for r in rows if r['ok'] and r['prev_ok'] and r['stdout_len'] != r['prev_stdout_len']], 'rows': rows}
Path(out_path).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
print(json.dumps({k: v for k, v in out.items() if k != 'rows'}, ensure_ascii=False)[:1500])
