#!/usr/bin/env bash
# 개선판 프롬프트 확인 실행 — 앞 단계가 끝난 뒤 GPU 에서 시스템 프롬프트 개선판(03_prompts/system_prompt_v2.md)을 평가한다.
#
#   2026-11-16 작성. 기본 평가(arete27b_q5_base)의 미통과 52문항 가운데 31문항이 「코드 없이 확인 요청」이어서, 되묻는 범위를 줄인 개선판의 효과를 잰다.
#   순서  ① 앞 단계 종료 대기(기본은 미세조정 단계의 logs/pipeline/FINETUNE_ALL.end. WAIT_FILE·WAIT_UNIT 으로 바꿈)와 GPU 비움 확인
#            2026-11-16 09시: 원인 확인을 앞당기기 위해 양자화 수준 비교 평가 바로 뒤(미세조정 앞)에 수행하도록 순서를 바꿈
#            (WAIT_FILE=logs/pipeline/EVAL_ALL.end WAIT_UNIT=<평가 단위>). 미세조정은 run_after.sh 로 이 실행 뒤에 이어짐
#         ② 공식 가중치 Q5_K_M 서버 기동(평가 단계와 같은 서버 설정)
#         ③ 보류 검증 문항(05_eval/holdout.jsonl, 43문항)을 현행 프롬프트로 → holdout_q5_v1
#         ④ 보류 검증 문항을 개선판 프롬프트로 → holdout_q5_v2
#         ⑤ 벤치마크·안전성 161문항을 개선판 프롬프트로 → arete27b_q5_v2_base (기준선은 arete27b_q5_base)
#   띄우기  bash 06_build/launch_job.sh extra bash 06_build/run_pipeline_extra.sh
#   다시 실행하면 끝난 실행은 건너뛰고 남은 문항만 수행한다. 실행 중인 이 파일은 고치지 않는다.
#   예행 연습  REHEARSAL=1 SSDA_CONFIG=<다른 포트를 적은 설정 파일> MODEL_FILE=<축소 모형 GGUF> bash 06_build/run_pipeline_extra.sh
#              (대기를 건너뛰고 CPU 로 띄우며 실행마다 3문항만 수행. 실행 이름 앞에 dryx_ 가 붙고 완료 표시를 남기지 않음)
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PY:-/mnt/share/행정데이터_set/.venv/bin/python}"
REH="${REHEARSAL:-0}"
P=logs/pipeline; [ "$REH" = 1 ] && P=logs/pipeline/rehearsal_extra; mkdir -p "$P"
PRE=""; LIM=(); [ "$REH" = 1 ] && { PRE="dryx_"; LIM=(--limit 3); }
V2="${V2:-03_prompts/system_prompt_v2.md}"
MODEL_FILE="${MODEL_FILE:-/mnt/share/models/arete-27b/Arete-27B-Q5_K_M.gguf}"
say() { echo "[$(date '+%F %T')] 추가: $*" | tee -a "$P/pipeline.log"; }

read -r BASE_URL SERVED <<< "$("$PY" -c "
import sys; sys.path.insert(0, '06_build')
from assistant import load_config
m = load_config()['model']; print(m['base_url'], m['served_name'])")"
PORT="${BASE_URL##*:}"; PORT="${PORT%%/*}"
alive() { curl -sf -m 3 "$BASE_URL/models" >/dev/null 2>&1; }
SERVER_PID=""
stop_server() { if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then kill "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null; say "서버 종료"; fi; SERVER_PID=""; }
trap stop_server EXIT

complete() { "$PY" - "$1" <<'EOF'
import json, sys
from pathlib import Path
p = Path('05_eval/runs') / sys.argv[1] / 'run_meta.json'
sys.exit(0 if p.exists() and json.loads(p.read_text(encoding='utf-8')).get('complete') else 1)
EOF
}

# ① 앞 단계 종료 대기 (WAIT_FILE: 끝난 표시 파일, WAIT_UNIT: 그 단계의 작업 단위. 기본은 미세조정 단계)
if [ "$REH" != 1 ]; then
WAIT_FILE="${WAIT_FILE:-$P/FINETUNE_ALL.end}"
FT_UNIT="${WAIT_UNIT:-$(cat "$P/last_unit_finetune" 2>/dev/null || true)}"
say "앞 단계가 끝나기를 기다림($WAIT_FILE 또는 단위 ${FT_UNIT:-없음}의 종료)"
while [ ! -f "$WAIT_FILE" ]; do
  if [ -n "$FT_UNIT" ] && ! systemctl --user is-active --quiet "$FT_UNIT.scope"; then say "앞 단계의 단위가 끝남(완료 표시 없음). 계속 진행"; break; fi
  sleep 60
done
t0=$SECONDS
while :; do
  used="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | sort -n | tail -1)"
  [ "${used:-99999}" -le 4000 ] && ! alive && break
  [ $((SECONDS - t0)) -gt 3600 ] && { say "GPU 가 비지 않음(${used}MiB) 또는 서버가 남아 있음. 중단"; exit 1; }
  sleep 30
done
fi

# ② 서버 기동
start_server() {
  say "서버 기동($MODEL_FILE)"
  MODE="$([ "$REH" = 1 ] && echo cpu || echo gpu)" MODEL="$MODEL_FILE" PORT="$PORT" ALIAS="$SERVED" bash 06_build/serve_llamacpp.sh > "$P/extra_server.log" 2>&1 &
  SERVER_PID=$!
  local s0=$SECONDS
  while [ $((SECONDS - s0)) -lt 1500 ]; do
    kill -0 "$SERVER_PID" 2>/dev/null || { say "서버가 종료됨. 기록 $P/extra_server.log"; tail -5 "$P/extra_server.log" | tee -a "$P/pipeline.log"; SERVER_PID=""; return 1; }
    alive && { say "서버 응답 확인($((SECONDS - s0))초) · GPU $(nvidia-smi --query-gpu=index,memory.used --format=csv,noheader | tr '\n' ';')"; return 0; }
    sleep 2
  done
  say "서버 응답 없음"; stop_server; return 1
}

run_stage() {   # run_stage 실행이름 명령...
  local run="$1"; shift
  if complete "$run"; then say "$run: 이미 끝남(건너뜀)"; return 0; fi
  local try
  for try in 1 2; do
    alive || start_server || { say "$run: 서버를 띄우지 못함"; return 1; }
    say "$run: 시작($try차)"
    "$@" > "$P/extra_$run.try$try.log" 2>&1
    complete "$run" && { say "$run: 끝"; return 0; }
    say "$run: 미완료(기록 $P/extra_$run.try$try.log). 60초 뒤 이어서 수행"; sleep 60
  done
  say "$run: 완료하지 못함"; return 1
}

say "개선판 프롬프트 확인 실행 시작 (pid $$)"
run_stage "${PRE}holdout_q5_v1" "$PY" 06_build/eval_holdout.py --name "${PRE}holdout_q5_v1" --resume "${LIM[@]}"
run_stage "${PRE}holdout_q5_v2" "$PY" 06_build/eval_holdout.py --name "${PRE}holdout_q5_v2" --system "$V2" --resume "${LIM[@]}"
run_stage "${PRE}arete27b_q5_v2_base" "$PY" 06_build/eval_run.py --name "${PRE}arete27b_q5_v2_base" --examples 0 --system "$V2" --resume "${LIM[@]}"
stop_server
[ "$REH" = 1 ] || date '+%F %T' > "$P/EXTRA_ALL.end"
say "개선판 프롬프트 확인 실행 끝"
