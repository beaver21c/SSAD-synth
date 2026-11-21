#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""통제 계층 직접 공격 시험용 실행 도구 — 코드 파일을 보완안 사본(06_build/staged/guard_v2/lib)의 실행 전 점검 → 격리 실행기로 실행하고 결과를 보여 준다.

  python 05_eval/independent/redteam/run_snippet.py 05_eval/independent/redteam/snippets/X01.py
출력(JSON 한 줄)  ok(실행 성공), violations(실행 전 점검에 걸린 내역), error(오류 첫 줄), stdout(이용자에게 보이는 표준 출력), results(집계 결과의 이름), figures, files(작업 폴더에 생긴 파일)
조립기(06_build/assistant.py 의 execute)와 같은 명령·환경으로 실행한다: python -m ssda.runner <파일> --timeout 60 --mem 6
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TMP = Path(__file__).resolve().parent / 'tmp2'
DATA = os.environ.get('SSDA_DATA', '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet')


def run(path, timeout=60):
    exp = TMP / 'export'; exp.mkdir(parents=True, exist_ok=True)
    before = {p for p in exp.rglob('*') if p.is_file()}
    env = {**os.environ, 'SSDA_DATA': DATA, 'SSDA_EXPORT': str(exp), 'SSDA_LOG': str(TMP / 'ssda_log.jsonl'), 'PYTHONPATH': str(ROOT / '06_build' / 'staged' / 'guard_v2' / 'lib'), 'MPLBACKEND': 'Agg'}
    try:
        p = subprocess.run([sys.executable, '-m', 'ssda.runner', str(path), '--timeout', str(timeout), '--mem', '6'], capture_output=True, text=True, env=env, timeout=timeout + 30, cwd=str(ROOT))
        out = json.loads(p.stdout.strip().splitlines()[-1])
    except subprocess.TimeoutExpired:
        out = {'ok': False, 'violations': [], 'stdout': '', 'error': '시간 한도 초과', 'results': {}, 'figures': []}
    except Exception as e:                              # noqa: BLE001
        out = {'ok': False, 'violations': [], 'stdout': (p.stdout[-2000:] if 'p' in dir() else ''), 'error': f'실행기 출력 해석 실패: {e} / stderr: {(p.stderr[-800:] if "p" in dir() else "")}', 'results': {}, 'figures': []}
    after = {p for p in exp.rglob('*') if p.is_file()}
    return {'ok': out.get('ok'), 'violations': out.get('violations'), 'error': (out.get('error') or '')[:1500], 'stdout': (out.get('stdout') or '')[:6000],
            'results': list((out.get('results') or {}).keys()), 'figures': out.get('figures'), 'files': sorted(str(x.relative_to(exp)) for x in after - before)}


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1]), ensure_ascii=False))
