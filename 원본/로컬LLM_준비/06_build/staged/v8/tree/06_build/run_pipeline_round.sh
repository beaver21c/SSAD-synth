#!/usr/bin/env bash
# 독립 검증의 차수별 GPU 평가 — 새 독립 문항(차수 폴더의 items/all.jsonl)을 지정한 구성들에 적용해 대화 기록을 남긴다.
#
#   2026-11-17 사용자 지시: 「조치 후 재판정, 이후 다시 검토하여 내일 06시 이전까지 가능하다면 성능 개선을 위하여 계속 반복. (저 시간 넘어갈 것 같으면 하지 말고)」
#   사용법  TAG=r2 ITEMS=05_eval/independent/r2/items/all.jsonl STAGES=logs/pipeline/round_r2.stages DEADLINE="2026-11-18 05:30" bash 06_build/launch_job.sh round bash 06_build/run_pipeline_round.sh
#   STAGES 파일: 한 줄에 「실행이름 모형(lora|base) 시스템프롬프트 보완동작(on|off) [문항ids]」(공백 구분). 위에서부터 차례로 수행
#   · 추론 서버가 중단되면(GPU 드라이버 감시 시간 초과 등) 다시 띄워 남은 문항을 이어서 수행함(실행마다 최대 6회)
#   · 마감(DEADLINE): 실행을 시작하기 전에 예상 소요(문항 수 × 모형별 문항당 시간)가 마감을 넘으면 그 실행과 뒤의 실행을 시작하지 않음. 실행 중 마감이 되면 그 실행을 멈춤
#   · 대화 기록만 남긴다. 채점은 05_eval/independent/score_outcome.py(INDEP_DIR=차수 폴더)와 독립 평가자가 따로 한다
#   끝 표시  logs/pipeline/ROUND_<TAG>.end, 진행 기록 logs/pipeline/pipeline.log 의 「독립 검증(<TAG>)」
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PY:-/mnt/share/행정데이터_set/.venv/bin/python}"
export SSDA_DATA="${SSDA_DATA:-/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet}"
unset SSDA_HOOKS
TAG="${TAG:?TAG 필요}"; ITEMS="${ITEMS:?ITEMS 필요}"; STAGES="${STAGES:?STAGES 필요}"; DEADLINE="${DEADLINE:-2026-11-18 05:30}"
P=logs/pipeline
GG=/mnt/share/models/arete-27b
ON="user_code=replace,repeat_guard=1,var_candidates=1,unexecuted_results=1"
OFF="user_code=0,repeat_guard=0,var_candidates=0,unexecuted_results=0"
SEC_LORA="${SEC_LORA:-21}"; SEC_BASE="${SEC_BASE:-31}"          # 문항당 소요(초): 1차 독립 문항의 실측(미세조정 모형 19초, 공식 가중치 28초)에 여유를 둠
say() { echo "[$(date '+%F %T')] 독립 검증($TAG): $*" | tee -a "$P/pipeline.log"; }
left() { echo $(( $(date -d "$DEADLINE" +%s) - $(date +%s) )); }
read -r BASE_URL SERVED <<< "$("$PY" -c "
import sys; sys.path.insert(0, '06_build')
from assistant import load_config
m = load_config()['model']; print(m['base_url'], m['served_name'])")"
PORT="${BASE_URL##*:}"; PORT="${PORT%%/*}"
alive() { curl -sf -m 3 "$BASE_URL/models" >/dev/null 2>&1; }
SERVER_PID=""; SERVER_MODEL=""
stop_server() { [ -n "$SERVER_PID" ] && { kill "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null; }; SERVER_PID=""; SERVER_MODEL=""; sleep 5; }
trap stop_server EXIT
start_server() {   # start_server lora|base
  local f="$GG/Arete-27B-lora-Q5_K_M.gguf"; [ "$1" = base ] && f="$GG/Arete-27B-Q5_K_M.gguf"
  local t0=$SECONDS used
  while :; do
    used="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | sort -n | tail -1)"
    [ "${used:-99999}" -le 4000 ] && ! alive && break
    [ $((SECONDS - t0)) -gt 900 ] && { say "GPU 가 비지 않음(${used}MiB)"; return 1; }
    sleep 15
  done
  MODE=gpu MODEL="$f" PORT="$PORT" ALIAS="$SERVED" bash 06_build/serve_llamacpp.sh > "$P/round_${TAG}_server.log" 2>&1 &
  SERVER_PID=$!; SERVER_MODEL="$1"
  local s0=$SECONDS
  until alive; do
    kill -0 "$SERVER_PID" 2>/dev/null || { say "서버가 종료됨($1)"; SERVER_PID=""; SERVER_MODEL=""; return 1; }
    [ $((SECONDS - s0)) -gt 900 ] && { say "서버 응답 없음($1)"; stop_server; return 1; }
    sleep 2
  done
  say "서버 응답 확인($1, $((SECONDS - s0))초)"
}
mkcfg() {   # mkcfg lora|base → 설정 파일 경로(모형 파일만 바꾸고 보완 동작 항목은 뺌)
  local f="$GG/Arete-27B-lora-Q5_K_M.gguf"; [ "$1" = base ] && f="$GG/Arete-27B-Q5_K_M.gguf"
  mkdir -p "$P/round_cfg"
  "$PY" - config/assistant.yaml "$P/round_cfg/$1.yaml" "$f" <<'EOF'
import sys, yaml
from pathlib import Path
src, dst, model = sys.argv[1:4]
c = yaml.safe_load(Path(src).read_text(encoding='utf-8'))
c['model']['file'] = model
for k in ('user_code', 'repeat_guard', 'var_candidates', 'unexecuted_results'):
    (c.get('verify') or {}).pop(k, None)
Path(dst).write_text(f'# 차수별 평가용 설정(run_pipeline_round.sh 가 만듦) — {src} 에서 모형 파일만 바꾸고 보완 동작 항목은 뺌(실행마다 SSDA_HOOKS 로 정함)\n' + yaml.safe_dump(c, allow_unicode=True, sort_keys=False), encoding='utf-8')
EOF
  echo "$P/round_cfg/$1.yaml"
}
complete() { "$PY" -c "
import json, sys
from pathlib import Path
p = Path('05_eval/runs/$1/run_meta.json')
sys.exit(0 if p.exists() and json.loads(p.read_text(encoding='utf-8')).get('complete') else 1)"; }

[ -f "$ITEMS" ] && [ -f "$STAGES" ] || { say "문항 또는 실행 목록 파일 없음"; exit 1; }
NITEMS="$(wc -l < "$ITEMS")"
say "시작 (pid $$) · 문항 $NITEMS개($(sha256sum "$ITEMS" | cut -c1-12)) · 분석 함수 $("$PY" -c "import sys; sys.path.insert(0, '02_library'); import ssda; print(ssda.__version__)") · 조립기 $(sha256sum 06_build/assistant.py | cut -c1-12) · 마감 $DEADLINE"
skip=0
while read -r RUN MODEL SYS HK IDS <&3; do
  [ -z "${RUN:-}" ] || [ "${RUN:0:1}" = "#" ] && continue
  if complete "$RUN"; then say "$RUN: 이미 끝남(건너뜀)"; continue; fi
  n="$NITEMS"; [ -n "${IDS:-}" ] && n="$(echo "$IDS" | tr ',' '\n' | wc -l)"
  per="$SEC_LORA"; [ "$MODEL" = base ] && per="$SEC_BASE"
  got="$(wc -l < "05_eval/runs/$RUN/transcripts.jsonl" 2>/dev/null || echo 0)"
  need=$(( (n - got) * per + 240 ))
  if [ "$skip" = 1 ] || [ "$need" -gt "$(left)" ]; then say "$RUN: 예상 소요 $((need / 60))분이 마감까지 남은 $(( $(left) / 60 ))분을 넘어 시작하지 않음"; skip=1; continue; fi
  C="$(mkcfg "$MODEL")"; hk="$ON"; [ "$HK" = off ] && hk="$OFF"
  ARGS=(--name "$RUN" --config "$C" --system "$SYS" --items "$ITEMS" --resume); [ -n "${IDS:-}" ] && ARGS+=(--ids "$IDS")
  for try in 1 2 3 4 5 6; do
    if [ -z "$SERVER_PID" ] || ! kill -0 "$SERVER_PID" 2>/dev/null || ! alive || [ "$SERVER_MODEL" != "$MODEL" ]; then stop_server; start_server "$MODEL" || { sleep 30; continue; }; fi
    [ "$(left)" -le 120 ] && { say "$RUN: 마감이 되어 멈춤"; break; }
    say "$RUN: 시작($try차 · $MODEL · $SYS · 보완 동작 $HK · 문항 $n개 중 끝난 것 $(wc -l < "05_eval/runs/$RUN/transcripts.jsonl" 2>/dev/null || echo 0))"
    SSDA_HOOKS="$hk" timeout "$(( $(left) - 60 ))" "$PY" 06_build/eval_indep.py "${ARGS[@]}" > "$P/round_${TAG}_$RUN.try$try.log" 2>&1
    complete "$RUN" && { say "$RUN: 끝 · $(tail -1 "$P/round_${TAG}_$RUN.try$try.log" | cut -c1-150)"; break; }
    say "$RUN: 미완료($try차). 서버 상태를 확인하고 이어서 수행"
  done
done 3< "$STAGES"
stop_server
date '+%F %T' > "$P/ROUND_$TAG.end"
say "끝"
