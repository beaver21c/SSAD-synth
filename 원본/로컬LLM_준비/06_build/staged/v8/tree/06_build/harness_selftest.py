#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""검증 단계 자체 시험 — 일부러 틀리게 답하는 모의 모형(sloppy)을 넣어 하네스가 얼마나 잡아내고 고치게 하는지 센다.

  모의 모형의 동작  ① 정답 코드에서 대상 조건(where)을 뺀 코드를 씀  ② 「[검증 결과]」에 경고나 요청 반영 주의가 오면 정답 코드로 고침
                  ③ 응답에 실행 결과에 없는 수치(987.65%)를 적음  ④ 수치 대조에 걸리면 실행 결과대로 다시 씀
  세는 것  대상 조건 누락을 잡은 비율(분모 경고, 요청 반영 주의), 잡지 못한 문항, 근거 없는 수치를 다시 쓰게 한 건수

  python 06_build/harness_selftest.py        # 05_eval/runs/mock_sloppy/harness_selftest.json 에 기록

하네스의 탐지 범위를 재는 시험이며 실제 모형의 성능을 재지 않는다. 잡지 못한 문항의 유형은 자동 점검의 한계에 해당한다.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / '05_eval' / 'runs' / 'mock_sloppy'


def jl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding='utf-8').splitlines() if l.strip()]


def main():
    subprocess.run([sys.executable, str(ROOT / '06_build' / 'eval_run.py'), '--name', 'mock_sloppy', '--mock', 'sloppy', '--inprocess'], check=False, capture_output=True, text=True, cwd=str(ROOT))
    B = {b['id']: b for b in jl(ROOT / '05_eval' / 'benchmark.jsonl')}
    R = json.loads((RUN / 'report.json').read_text(encoding='utf-8')); it = {r['id']: r for r in R['items']}
    T = {t['id']: t['turns'] for t in jl(RUN / 'transcripts.jsonl')}
    dropped = [i for i, b in B.items() if b['gold_code'] and re.search(r",\s*where='", b['gold_code']) and it[i]['kind'] == 'analysis']
    first = lambda i: T[i][-1]['steps'][0]
    by_warn = [i for i in dropped if any(c['level'] == '경고' for cs in (first(i).get('checks') or {}).values() for c in cs)]
    by_req = [i for i in dropped if i not in by_warn and first(i).get('req')]
    caught = by_warn + by_req
    missed = [i for i in dropped if i not in caught]
    wrong = [i for i in missed if not it[i]['value_match']]
    stat = {'대상 조건을 뺀 문항': len(dropped), '분모 경고로 잡은 문항': len(by_warn), '요청 반영 주의로 잡은 문항': len(by_req), '고쳐서 정답과 일치한 문항': sum(it[i]['value_match'] for i in caught),
            '잡지 못한 문항': len(missed), '잡지 못했으나 값이 같은 문항': len(missed) - len(wrong), '잡지 못해 값이 다른 문항': len(wrong),
            '잡지 못해 값이 다른 문항의 질문': [B[i]['turns'][-1].split('\n')[0][:60] for i in wrong],
            '근거 없는 수치를 적은 응답': R['harness']['응답을 다시 쓰게 한 문항'], '다시 쓴 뒤 수치 근거율': R['metrics']['수치 근거율'],
            '차단 실패 건수': R['metrics']['차단 실패 건수']}
    (RUN / 'harness_selftest.json').write_text(json.dumps(stat, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(stat, ensure_ascii=False, indent=1))
    ok = stat['다시 쓴 뒤 수치 근거율'] == 1.0 and stat['차단 실패 건수'] == 0 and stat['분모 경고로 잡은 문항'] > 0
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
