#!/usr/bin/env bash
# 평가 단계 연속 실행 — 기본 평가(Q5_K_M, 유사 예시 0·2개)와 양자화 수준 비교(Q4_K_M, Q6_K)를 사람 없이 이어서 수행한다.
#
#   2026-11-15 사용자 지시(범위 E까지 전체 수행)에 따라 작성. GPU 2장을 모두 쓴다.
#   단계마다 끝난 표시(logs/pipeline/<단계>.done)를 남기며, 다시 실행하면 끝난 단계는 건너뛰고 평가는 남은 문항만 수행한다(eval_run.py --resume).
#   이 창(세션)이 닫혀도 계속 돌도록 따로 띄운다:
#     setsid systemd-run --user --scope --unit=ssda-eval bash 06_build/run_pipeline_eval.sh > logs/pipeline/unit_eval.out 2>&1 < /dev/null &
#   진행 상황  logs/pipeline/pipeline.log, 단계별 기록 logs/pipeline/<단계>.log, 실행별 요약 logs/gpu_day/<시각>/summary.md
#   실행 중인 이 파일은 고치지 않는다(셸이 파일을 읽어 가며 실행하므로 중단됨).
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PY:-/mnt/share/행정데이터_set/.venv/bin/python}"
P=logs/pipeline; mkdir -p "$P"
say() { echo "[$(date '+%F %T')] $*" | tee -a "$P/pipeline.log"; }

complete() {   # complete 실행이름...  → 모두 끝났으면 0
  "$PY" - "$@" <<'EOF'
import json, sys
from pathlib import Path
ok = True
for run in sys.argv[1:]:
    p = Path('05_eval/runs') / run / 'run_meta.json'
    m = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
    ok = ok and bool(m.get('complete')) and (Path('05_eval/runs') / run / 'report.json').exists()
sys.exit(0 if ok else 1)
EOF
}

stage() {      # stage 단계이름 "실행이름들" 명령...
  local n="$1" runs="$2"; shift 2
  if [ -f "$P/$n.done" ]; then say "$n: 이미 끝남(건너뜀)"; return 0; fi
  local try
  for try in 1 2 3; do
    say "$n: 시작($try차) — $*"
    "$@" > "$P/$n.try$try.log" 2>&1; local rc=$?
    # shellcheck disable=SC2086
    if complete $runs; then date '+%F %T' > "$P/$n.done"; rm -f "$P/$n.failed"; say "$n: 끝(평가 완료: $runs)"; return 0; fi
    say "$n: 미완료(종료 코드 $rc, 기록 $P/$n.try$try.log). 60초 뒤 남은 문항을 이어서 수행"
    sleep 60
  done
  echo "미완료" > "$P/$n.failed"; say "$n: 3차까지 완료하지 못함. 다음 단계로 넘어감"
  return 1
}

say "평가 단계 연속 실행 시작 (pid $$)"
stage S1_q5 "arete27b_q5_base arete27b_q5_ex2" bash 06_build/run_gpu_day.sh
stage S2_q4 "arete27b_q4_base" bash 06_build/run_gpu_day.sh --quant Q4_K_M --examples "0"
stage S3_q6 "arete27b_q6_base" bash 06_build/run_gpu_day.sh --quant Q6_K --examples "0"
date '+%F %T' > "$P/EVAL_ALL.end"
say "평가 단계 연속 실행 끝"
