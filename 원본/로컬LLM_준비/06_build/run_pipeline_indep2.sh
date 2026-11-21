#!/usr/bin/env bash
# 독립 검증의 재실행 — 현행 구성(C2)을 문항 순서만 바꿔 한 번 더 실행해 응답의 변동을 잰다.
#
#   사유  설계서 5절은 생성 온도 0에서 같은 질문의 응답이 같다고 보았으나, 보완 동작을 끈 실행(indep_c1)의 대조 10문항 가운데 5문항의 응답이 indep_c2 와 달랐음
#         (1문항은 정답 여부가 바뀜). 같은 순서로 다시 돌린 실행은 이전 평가에서 응답이 같았으므로, 차이는 직전 요청(서버의 처리 상태)에 따라 생기는 것으로 봄.
#         실제 이용에서는 직전 요청이 매번 다르므로, 문항 순서를 섞은 실행으로 같은 질문의 판정이 얼마나 바뀌는지 잼.
#   실행  indep_c2s — 미세조정 모형 Q5_K_M + 개선판 3 + 보완 동작 4종, 문항 파일 05_eval/independent/items/all_shuffled.jsonl(순서만 섞음, 내용 같음)
#   앞선 일괄 실행(run_pipeline_indep.sh)이 끝난 뒤에 시작함(logs/pipeline/INDEP_ALL.end 를 기다림)
#   띄우기  bash 06_build/launch_job.sh indep2 bash 06_build/run_pipeline_indep2.sh
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PY:-/mnt/share/행정데이터_set/.venv/bin/python}"
export SSDA_DATA="${SSDA_DATA:-/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet}"
unset SSDA_HOOKS
P=logs/pipeline
LORA_FILE="/mnt/share/models/arete-27b/Arete-27B-lora-Q5_K_M.gguf"
C="$P/indep_cfg/lora_v3.yaml"
ON="user_code=replace,repeat_guard=1,var_candidates=1,unexecuted_results=1"
RUN=indep_c2s
say() { echo "[$(date '+%F %T')] 독립 검증(재실행): $*" | tee -a "$P/pipeline.log"; }
until [ -f "$P/INDEP_ALL.end" ]; do sleep 60; done
read -r BASE_URL SERVED <<< "$("$PY" -c "
import sys; sys.path.insert(0, '06_build')
from assistant import load_config
m = load_config()['model']; print(m['base_url'], m['served_name'])")"
PORT="${BASE_URL##*:}"; PORT="${PORT%%/*}"
alive() { curl -sf -m 3 "$BASE_URL/models" >/dev/null 2>&1; }
t0=$SECONDS
while :; do
  used="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | sort -n | tail -1)"
  [ "${used:-99999}" -le 4000 ] && ! alive && break
  [ $((SECONDS - t0)) -gt 1800 ] && { say "GPU 가 비지 않음(${used}MiB). 중단"; exit 1; }
  sleep 30
done
say "시작 (pid $$) · 문항 $(wc -l < 05_eval/independent/items/all_shuffled.jsonl)개(순서 변경)"
MODE=gpu MODEL="$LORA_FILE" PORT="$PORT" ALIAS="$SERVED" bash 06_build/serve_llamacpp.sh > "$P/indep_server_rerun.log" 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null' EXIT
s0=$SECONDS
until alive; do
  kill -0 "$SERVER_PID" 2>/dev/null || { say "서버가 종료됨. 기록 $P/indep_server_rerun.log"; exit 1; }
  [ $((SECONDS - s0)) -gt 1500 ] && { say "서버 응답 없음"; exit 1; }
  sleep 2
done
say "서버 응답 확인($((SECONDS - s0))초)"
for try in 1 2; do
  SSDA_HOOKS="$ON" "$PY" 06_build/eval_indep.py --name "$RUN" --config "$C" --items 05_eval/independent/items/all_shuffled.jsonl --resume > "$P/indep_$RUN.try$try.log" 2>&1 && break
  say "$RUN: 미완료($try차). 60초 뒤 이어서 수행"; sleep 60
done
say "$RUN: $(tail -1 "$P/indep_$RUN.try$try.log" | cut -c1-200)"
date '+%F %T' > "$P/INDEP_RERUN.end"
say "끝"
