#!/usr/bin/env bash
# 미세조정 뒤 확인 실행 — 미세조정 단계가 끝난 뒤, 개선판 프롬프트(03_prompts/system_prompt_v2.md)를 미세조정 모형과 Q4_K_M 에 적용해 평가한다.
#
#   2026-11-16 작성. 보류 검증 문항에서 개선판의 효과(현행 23/43 → 개선판 40/43, Q5_K_M)가 확인되어 아래 두 가지를 추가로 잰다.
#     (가) 미세조정 모형(Arete-27B-lora-Q5_K_M.gguf): 지시 범위 E 의 평가(F5·F6)는 벤치마크만 쓰므로, 보류 검증 문항과 개선판 프롬프트 조합을 더한다
#          holdout_lora_short(짧은 프롬프트: 학습 자료와 같은 문구) → holdout_lora_v2(개선판) → arete27b_lora_v2_base(개선판, 161문항)
#     (나) 공식 가중치 Q4_K_M: 현행 프롬프트에서 통과율이 가장 높았던 수준이 개선판에서도 같은지 본다
#          holdout_q4_v2 → arete27b_q4_v2_base
#   순서  ① 미세조정 단계 종료 대기: logs/pipeline/FINETUNE_ALL.end 가 생기거나, logs/pipeline/last_unit_finetune 의 단위가 10분 넘게 떠 있지 않을 때까지
#            (단위를 다시 띄우면 last_unit_finetune 이 바뀌므로 새 단위를 따라 기다린다). logs/pipeline/EXTRA2.hold 파일이 있으면 계속 기다린다
#         ② GPU 비움 확인(4000MiB 이하, 서버 없음. 최대 1시간)  ③ (가) → (나). 모형 파일이 없으면 그 묶음은 건너뛴다
#   띄우기  bash 06_build/launch_job.sh extra2 bash 06_build/run_pipeline_extra2.sh
#   다시 실행하면 끝난 실행은 건너뛰고 남은 문항만 수행한다. 실행 중인 이 파일은 고치지 않는다.
#   예행 연습  REHEARSAL=1 SSDA_CONFIG=<다른 포트를 적은 설정 파일> LORA_FILE=<축소 모형 GGUF> Q4_FILE=<축소 모형 GGUF> bash 06_build/run_pipeline_extra2.sh
#              (대기를 건너뛰고 CPU 로 띄우며 실행마다 3문항만 수행. 실행 이름 앞에 dryy_ 가 붙고 완료 표시를 남기지 않음)
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PY:-/mnt/share/행정데이터_set/.venv/bin/python}"
export SSDA_DATA="${SSDA_DATA:-/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet}"
REH="${REHEARSAL:-0}"
P=logs/pipeline; [ "$REH" = 1 ] && P=logs/pipeline/rehearsal_extra2; mkdir -p "$P"
PRE=""; LIM=(); [ "$REH" = 1 ] && { PRE="dryy_"; LIM=(--limit 3); }
V2="${V2:-03_prompts/system_prompt_v2.md}"
SHORT="${SHORT:-03_prompts/system_prompt_short.md}"
GG="${GGUF_DIR:-/mnt/share/models/arete-27b}"
LORA_FILE="${LORA_FILE:-$GG/Arete-27B-lora-Q5_K_M.gguf}"
Q4_FILE="${Q4_FILE:-$GG/Arete-27B-Q4_K_M.gguf}"
BASE_CFG="${SSDA_CONFIG:-config/assistant.yaml}"
CFG="$P/extra2_cfg"; mkdir -p "$CFG"
say() { echo "[$(date '+%F %T')] 추가2: $*" | tee -a "$P/pipeline.log"; }

# 실행별 설정 파일(기본 설정에서 시스템 프롬프트와 모형 파일만 바꿈 → run_meta.json 에 실제 구성이 남음)
mkcfg() {   # mkcfg 이름 시스템프롬프트 모형파일
  "$PY" - "$BASE_CFG" "$CFG/$1.yaml" "$2" "$3" <<'EOF'
import sys, yaml
from pathlib import Path
src, dst, system, model = sys.argv[1:5]
c = yaml.safe_load(Path(src).read_text(encoding='utf-8'))
c['prompt']['system'] = system; c['model']['file'] = model
Path(dst).write_text(f'# 확인 실행용 설정(run_pipeline_extra2.sh 가 만듦) — {src} 에서 시스템 프롬프트와 모형 파일만 바꿈\n' + yaml.safe_dump(c, allow_unicode=True, sort_keys=False), encoding='utf-8')
EOF
}
mkcfg lora_short "$SHORT" "$LORA_FILE"; mkcfg lora_v2 "$V2" "$LORA_FILE"; mkcfg q4_v2 "$V2" "$Q4_FILE"

read -r BASE_URL SERVED <<< "$(SSDA_CONFIG="$BASE_CFG" "$PY" -c "
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

# ① 미세조정 단계 종료 대기
if [ "$REH" != 1 ]; then
  say "미세조정 단계가 끝나기를 기다림($P/FINETUNE_ALL.end 또는 $P/last_unit_finetune 의 단위가 10분 넘게 없음)"
  idle=0
  while :; do
    if [ -f "$P/EXTRA2.hold" ]; then idle=0; sleep 60; continue; fi
    [ -f "$P/FINETUNE_ALL.end" ] && break
    u="$(cat "$P/last_unit_finetune" 2>/dev/null || true)"
    if [ -n "$u" ] && systemctl --user is-active --quiet "$u.scope"; then idle=0; else idle=$((idle + 1)); fi
    [ "$idle" -ge 10 ] && { say "미세조정 단위가 10분 넘게 없음(완료 표시 없음). 계속 진행"; break; }
    sleep 60
  done
  # ② GPU 비움 확인
  t0=$SECONDS
  while :; do
    used="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | sort -n | tail -1)"
    [ "${used:-99999}" -le 4000 ] && ! alive && break
    [ $((SECONDS - t0)) -gt 3600 ] && { say "GPU 가 비지 않음(${used}MiB) 또는 서버가 남아 있음. 중단"; exit 1; }
    sleep 30
  done
fi

start_server() {   # start_server 모형파일 기록이름
  say "서버 기동($1)"
  MODE="$([ "$REH" = 1 ] && echo cpu || echo gpu)" MODEL="$1" PORT="$PORT" ALIAS="$SERVED" bash 06_build/serve_llamacpp.sh > "$P/extra2_server_$2.log" 2>&1 &
  SERVER_PID=$!
  local s0=$SECONDS
  while [ $((SECONDS - s0)) -lt 1500 ]; do
    kill -0 "$SERVER_PID" 2>/dev/null || { say "서버가 종료됨. 기록 $P/extra2_server_$2.log"; tail -5 "$P/extra2_server_$2.log" | tee -a "$P/pipeline.log"; SERVER_PID=""; return 1; }
    alive && { say "서버 응답 확인($((SECONDS - s0))초) · GPU $(nvidia-smi --query-gpu=index,memory.used --format=csv,noheader | tr '\n' ';')"; return 0; }
    sleep 2
  done
  say "서버 응답 없음"; stop_server; return 1
}

MODEL_NOW=""; TAG_NOW=""
use_model() {   # use_model 모형파일 기록이름 — 다른 모형이 떠 있으면 내리고 바꿔 띄움
  [ -f "$1" ] || { say "모형 파일 없음: $1 (이 묶음은 건너뜀)"; return 1; }
  if [ "$MODEL_NOW" != "$1" ]; then stop_server; sleep 5; fi
  MODEL_NOW="$1"; TAG_NOW="$2"; return 0
}
run_stage() {   # run_stage 실행이름 명령...   (use_model 로 정한 모형의 서버에서 수행)
  local run="$1"; shift
  if complete "$run"; then say "$run: 이미 끝남(건너뜀)"; return 0; fi
  local try
  for try in 1 2; do
    if [ -z "$SERVER_PID" ] || ! alive; then stop_server; start_server "$MODEL_NOW" "$TAG_NOW" || { say "$run: 서버를 띄우지 못함"; return 1; }; fi
    say "$run: 시작($try차)"
    "$@" > "$P/extra2_$run.try$try.log" 2>&1
    complete "$run" && { say "$run: 끝"; return 0; }
    say "$run: 미완료(기록 $P/extra2_$run.try$try.log). 60초 뒤 이어서 수행"; sleep 60
  done
  say "$run: 완료하지 못함"; return 1
}

say "미세조정 뒤 확인 실행 시작 (pid $$)"
# (가) 미세조정 모형
if use_model "$LORA_FILE" lora; then
  run_stage "${PRE}holdout_lora_short" "$PY" 06_build/eval_holdout.py --name "${PRE}holdout_lora_short" --config "$CFG/lora_short.yaml" --resume "${LIM[@]}"
  run_stage "${PRE}holdout_lora_v2" "$PY" 06_build/eval_holdout.py --name "${PRE}holdout_lora_v2" --config "$CFG/lora_v2.yaml" --resume "${LIM[@]}"
  run_stage "${PRE}arete27b_lora_v2_base" "$PY" 06_build/eval_run.py --name "${PRE}arete27b_lora_v2_base" --examples 0 --config "$CFG/lora_v2.yaml" --resume "${LIM[@]}"
fi
# (나) 공식 가중치 Q4_K_M
if use_model "$Q4_FILE" q4; then
  run_stage "${PRE}holdout_q4_v2" "$PY" 06_build/eval_holdout.py --name "${PRE}holdout_q4_v2" --config "$CFG/q4_v2.yaml" --resume "${LIM[@]}"
  run_stage "${PRE}arete27b_q4_v2_base" "$PY" 06_build/eval_run.py --name "${PRE}arete27b_q4_v2_base" --examples 0 --config "$CFG/q4_v2.yaml" --resume "${LIM[@]}"
fi
stop_server
[ "$REH" = 1 ] || date '+%F %T' > "$P/EXTRA2_ALL.end"
say "미세조정 뒤 확인 실행 끝"
