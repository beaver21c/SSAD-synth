#!/usr/bin/env bash
# 독립 검증의 GPU 평가 — 독립 작성자가 만든 문항(05_eval/independent/items/all.jsonl)을 네 구성에 적용해 대화 기록을 남긴다.
#
#   2026-11-17 사용자 지시: 「테스트의 방법에 대해 완전 다시 설계하여 테스트 진행하여 실제 믿을만 한 것인지 성능 검증」
#   설계와 판정 기준은 05_eval/independent/설계서.md (문항 작성과 이 실행 전에 확정함). 평가 대상은 05_eval/independent/freeze.json 의 파일이며 실행이 끝날 때까지 고치지 않는다.
#   구성(같은 문항, 분석 함수 0.4.1)
#     C2 indep_c2  현행: 미세조정 모형 Q5_K_M + 개선판 3 + 보완 동작 4종(config/assistant.yaml 그대로)
#     C1 indep_c1  현행에서 보완 동작만 끔 — C2 에서 보완 동작이 작동한 문항과, 작동하지 않은 문항 가운데 무작위 10개(응답의 동일성 확인용)만 실행
#     C3 indep_c3  공식 가중치 Q5_K_M + 개선판 3 + 보완 동작 4종(미세조정의 효과 분리)
#     C0 indep_c0  출발점: 공식 가중치 Q5_K_M + 처음 판 프롬프트 + 보완 동작 없음
#   이 스크립트는 대화 기록만 남긴다. 채점은 05_eval/independent/score_outcome.py(참값 대조)와 독립 평가자가 따로 한다.
#   띄우기  bash 06_build/launch_job.sh indep bash 06_build/run_pipeline_indep.sh
#   다시 실행하면 끝난 실행은 건너뛰고 남은 문항만 수행한다. 실행 중인 이 파일과 이 파일이 부르는 파일은 고치지 않는다.
#   예행 연습  REHEARSAL=1 SSDA_CONFIG=<다른 포트를 적은 설정 파일> LORA_FILE=<축소 모형 GGUF> BASE_FILE=<축소 모형 GGUF> bash 06_build/run_pipeline_indep.sh
#              (CPU 로 띄우며 실행마다 3문항만 수행. 실행 이름 앞에 dryi_ 가 붙고 완료 표시를 남기지 않음)
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PY:-/mnt/share/행정데이터_set/.venv/bin/python}"
export SSDA_DATA="${SSDA_DATA:-/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet}"
unset SSDA_HOOKS
REH="${REHEARSAL:-0}"
P=logs/pipeline; [ "$REH" = 1 ] && P=logs/pipeline/rehearsal_indep; mkdir -p "$P"
PRE=""; LIM=(); [ "$REH" = 1 ] && { PRE="dryi_"; LIM=(--limit 3); }
V3="03_prompts/system_prompt_v3.md"; V0="03_prompts/system_prompt.md"
GG="${GGUF_DIR:-/mnt/share/models/arete-27b}"
LORA_FILE="${LORA_FILE:-$GG/Arete-27B-lora-Q5_K_M.gguf}"
BASE_FILE="${BASE_FILE:-$GG/Arete-27B-Q5_K_M.gguf}"
BASE_CFG="${SSDA_CONFIG:-config/assistant.yaml}"
OFF="user_code=0,repeat_guard=0,var_candidates=0,unexecuted_results=0"
ON="user_code=replace,repeat_guard=1,var_candidates=1,unexecuted_results=1"
CFG="$P/indep_cfg"; mkdir -p "$CFG"
say() { echo "[$(date '+%F %T')] 독립 검증: $*" | tee -a "$P/pipeline.log"; }

mkcfg() {   # mkcfg 출력파일 모형파일 시스템프롬프트
  "$PY" - "$BASE_CFG" "$1" "$2" "$3" <<'EOF'
import sys, yaml
from pathlib import Path
src, dst, model, system = sys.argv[1:5]
c = yaml.safe_load(Path(src).read_text(encoding='utf-8'))
c['prompt']['system'] = system; c['model']['file'] = model
for k in ('user_code', 'repeat_guard', 'var_candidates', 'unexecuted_results'):      # 보완 동작은 실행마다 환경변수 SSDA_HOOKS 로 정함(run_meta.json 의 hooks 에 남음)
    (c.get('verify') or {}).pop(k, None)
Path(dst).write_text(f'# 독립 검증용 설정(run_pipeline_indep.sh 가 만듦) — {src} 에서 모형 파일과 시스템 프롬프트만 바꾸고 보완 동작 항목은 뺌\n' + yaml.safe_dump(c, allow_unicode=True, sort_keys=False), encoding='utf-8')
EOF
}
mkcfg "$CFG/lora_v3.yaml" "$LORA_FILE" "$V3"
mkcfg "$CFG/base_v3.yaml" "$BASE_FILE" "$V3"
mkcfg "$CFG/base_v0.yaml" "$BASE_FILE" "$V0"

read -r BASE_URL SERVED <<< "$(SSDA_CONFIG="$BASE_CFG" "$PY" -c "
import sys; sys.path.insert(0, '06_build')
from assistant import load_config
m = load_config()['model']; print(m['base_url'], m['served_name'])")"
PORT="${BASE_URL##*:}"; PORT="${PORT%%/*}"
alive() { curl -sf -m 3 "$BASE_URL/models" >/dev/null 2>&1; }
SERVER_PID=""; SERVER_MODEL=""
rss() { [ -n "$SERVER_PID" ] && ps -o rss= -p "$SERVER_PID" 2>/dev/null | awk '{printf "%.1fGiB", $1 / 1048576}'; }
stop_server() { if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then say "서버 종료(서버 RAM $(rss))"; kill "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null; fi; SERVER_PID=""; SERVER_MODEL=""; }
trap stop_server EXIT
complete() { "$PY" - "$1" <<'EOF'
import json, sys
from pathlib import Path
p = Path('05_eval/runs') / sys.argv[1] / 'run_meta.json'
sys.exit(0 if p.exists() and json.loads(p.read_text(encoding='utf-8')).get('complete') else 1)
EOF
}
wait_gpu() {
  [ "$REH" = 1 ] && return 0
  local t0=$SECONDS used
  while :; do
    used="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | sort -n | tail -1)"
    [ "${used:-99999}" -le 4000 ] && ! alive && return 0
    [ $((SECONDS - t0)) -gt 1800 ] && { say "GPU 가 비지 않음(${used}MiB) 또는 서버가 남아 있음"; return 1; }
    sleep 30
  done
}

for f in "$LORA_FILE" "$BASE_FILE" "$V3" "$V0" 05_eval/independent/items/all.jsonl; do [ -f "$f" ] || { say "파일 없음: $f. 중단"; exit 1; }; done
wait_gpu || exit 1
LIBV="$("$PY" -c "import sys; sys.path.insert(0, '02_library'); import ssda; print(ssda.__version__)" 2>/dev/null)"
say "분석 함수 ssda ${LIBV:-확인 실패} · 조립기 $(sha256sum 06_build/assistant.py | cut -c1-12) · 문항 $(wc -l < 05_eval/independent/items/all.jsonl)개($(sha256sum 05_eval/independent/items/all.jsonl | cut -c1-12)) · 설정 $BASE_CFG"

start_server() {   # start_server 모형파일
  say "서버 기동($1)"
  MODE="$([ "$REH" = 1 ] && echo cpu || echo gpu)" MODEL="$1" PORT="$PORT" ALIAS="$SERVED" bash 06_build/serve_llamacpp.sh > "$P/indep_server_$(basename "$1").log" 2>&1 &
  SERVER_PID=$!; SERVER_MODEL="$1"
  local s0=$SECONDS
  while [ $((SECONDS - s0)) -lt 1500 ]; do
    kill -0 "$SERVER_PID" 2>/dev/null || { say "서버가 종료됨. 기록 $P/indep_server_$(basename "$1").log"; tail -5 "$P/indep_server_$(basename "$1").log" | tee -a "$P/pipeline.log"; SERVER_PID=""; SERVER_MODEL=""; return 1; }
    alive && { say "서버 응답 확인($((SECONDS - s0))초) · GPU $(nvidia-smi --query-gpu=index,memory.used --format=csv,noheader | tr '\n' ';') · 서버 RAM $(rss)"; return 0; }
    sleep 2
  done
  say "서버 응답 없음"; stop_server; return 1
}
run_stage() {   # run_stage 실행이름 모형파일 보완동작(SSDA_HOOKS 값) 명령...
  local run="$1" model="$2" hk="$3"; shift 3
  if complete "$run"; then say "$run: 이미 끝남(건너뜀)"; return 0; fi
  local try
  for try in 1 2; do
    if [ -z "$SERVER_PID" ] || ! alive || [ "$SERVER_MODEL" != "$model" ]; then stop_server; wait_gpu || return 1; start_server "$model" || { say "$run: 서버를 띄우지 못함"; return 1; }; fi
    say "$run: 시작($try차, 보완 동작 $hk)"
    SSDA_HOOKS="$hk" "$@" > "$P/indep_$run.try$try.log" 2>&1
    complete "$run" && { say "$run: 끝(서버 RAM $(rss)) · $(tail -1 "$P/indep_$run.try$try.log" | cut -c1-200)"; return 0; }
    say "$run: 미완료(기록 $P/indep_$run.try$try.log). 60초 뒤 이어서 수행"; sleep 60
  done
  say "$run: 완료하지 못함"; return 1
}

say "시작 (pid $$)"
run_stage "${PRE}indep_c2" "$LORA_FILE" "$ON" "$PY" 06_build/eval_indep.py --name "${PRE}indep_c2" --config "$CFG/lora_v3.yaml" --resume "${LIM[@]}"
# C1: 보완 동작이 작동한 문항 + 작동하지 않은 문항 가운데 무작위 10개
IDS="$("$PY" - "${PRE}indep_c2" <<'EOF'
import json, random, sys
from pathlib import Path
p = Path('05_eval/runs') / sys.argv[1] / 'transcripts.jsonl'
rows = [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()] if p.exists() else []
fired = [r['id'] for r in rows if any(t.get('hooks') for t in r['turns'])]
rest = sorted(r['id'] for r in rows if r['id'] not in set(fired))
random.seed(20261117)
print(','.join(fired + random.sample(rest, min(10, len(rest)))))
EOF
)"
if [ -n "$IDS" ]; then
  echo "$IDS" > "$P/${PRE}indep_c1_ids.txt"
  run_stage "${PRE}indep_c1" "$LORA_FILE" "$OFF" "$PY" 06_build/eval_indep.py --name "${PRE}indep_c1" --config "$CFG/lora_v3.yaml" --ids "$IDS" --resume
else
  say "indep_c1: 대상 문항 없음(건너뜀)"
fi
run_stage "${PRE}indep_c3" "$BASE_FILE" "$ON" "$PY" 06_build/eval_indep.py --name "${PRE}indep_c3" --config "$CFG/base_v3.yaml" --resume "${LIM[@]}"
run_stage "${PRE}indep_c0" "$BASE_FILE" "$OFF" "$PY" 06_build/eval_indep.py --name "${PRE}indep_c0" --config "$CFG/base_v0.yaml" --resume "${LIM[@]}"
stop_server
say "결과: $("$PY" - "${PRE}indep_c2" "${PRE}indep_c1" "${PRE}indep_c3" "${PRE}indep_c0" <<'EOF'
import json, sys
from pathlib import Path
out = []
for n in sys.argv[1:]:
    p = Path('05_eval/runs') / n / 'run_meta.json'
    if p.exists():
        m = json.loads(p.read_text(encoding='utf-8')); out.append(f"{n} {m['done']}/{m['items']}문항 {m['elapsed_sec'] / 60:.0f}분{'' if m['complete'] else '(미완료)'}")
    else:
        out.append(f'{n} 없음')
print(' · '.join(out))
EOF
)"
[ "$REH" = 1 ] || date '+%F %T' > "$P/INDEP_ALL.end"
say "끝"
