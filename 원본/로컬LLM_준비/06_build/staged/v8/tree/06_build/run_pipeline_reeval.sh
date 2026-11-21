#!/usr/bin/env bash
# 보완본 재평가 — 보완본(분석 함수 ssda 0.4.1, 보완한 채점기)을 현행으로 반영한 뒤 미세조정 모형을 시스템 프롬프트 개선판 2와 개선판 3으로 각각 다시 평가한다.
#
#   2026-11-17 사용자 지시: 「재평가 진행」(95% 판정에서 목표에 이르러 실행하지 않은 대책의 반영과 재평가. GPU 약 2.5시간으로 보고함)
#   목적  ① 현행 분석 함수(0.3.1)의 조건식 시도 값 결함(sido == 1 이 부산을 가리킴)을 없앤 구성으로 평가값을 다시 확보
#         ② 목표 문항 수와 같았던 통과 문항 수(115/121)의 여유 확인
#         ③ 어느 모형에도 넣어 본 적 없는 보류 검증 문항 2차(49문항)로 새 문항에서의 통과율 확인
#   순서  ① GPU 비움 확인
#         ② 보완본 반영과 점검(06_build/staged/v3/apply.sh: 정답 코드 회귀 점검, 모의 모형 채점. 이미 반영돼 있으면 건너뜀). 실패하면 되돌리고 끝냄.
#            기존 실행은 보완한 채점기로 다시 채점(원래 보고서는 report.scorer_v1.* 로 보존)
#         ③ 구성 2개를 차례로 평가(같은 모형이므로 서버는 한 번만 띄움)
#            구성 1 lora_v2_r2: 미세조정 모형 Q5_K_M + 개선판 2 — 보류 검증 문항 2차(49) → 1차(43) → 벤치마크·안전성(161)
#            구성 2 lora_v3   : 미세조정 모형 Q5_K_M + 개선판 3 — 보류 검증 문항 2차(49) → 1차(43) → 벤치마크·안전성(161)
#         ④ 서버의 프롬프트 캐시 설정 확인: 서버를 CACHE_RAM=0 으로 다시 띄워 구성 1의 보류 검증 문항 1차를 한 번 더 수행(응답·소요 시간·서버 RAM 을 ③의 같은 실행과 비교)
#         ⑤ 판정(06_build/staged/v3/judge.py)을 logs/pipeline/REEVAL_result.json 에 남기고 REEVAL_ALL.end 를 만듦
#   기본 구성의 선택 기준(평가 전에 정함)  ① 벤치마크·안전성의 종합 판정이 「충족」인 구성 가운데 ② 세 문항 묶음(벤치마크 121 + 보류 검증 1차 43 + 2차 49 = 213문항)의 통과 문항 수가 많은 구성
#                                          ③ 같으면 개선판 2(이미 평가한 프롬프트)를 둠
#   띄우기  bash 06_build/launch_job.sh reeval bash 06_build/run_pipeline_reeval.sh
#   환경변수  TARGET=0.95  SKIP_CACHE_CHECK=1(④를 건너뜀)
#   다시 실행하면 끝난 실행은 건너뛰고 남은 문항만 수행한다. 실행 중인 이 파일은 고치지 않는다.
#   예행 연습  REHEARSAL=1 SSDA_CONFIG=<다른 포트를 적은 설정 파일> LORA_FILE=<축소 모형 GGUF> bash 06_build/run_pipeline_reeval.sh
#              (반영을 건너뛰고 CPU 로 띄우며 실행마다 3문항만 수행. 실행 이름 앞에 dryr_ 가 붙고 완료 표시를 남기지 않음)
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PY:-/mnt/share/행정데이터_set/.venv/bin/python}"
export SSDA_DATA="${SSDA_DATA:-/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet}"
REH="${REHEARSAL:-0}"
P=logs/pipeline; [ "$REH" = 1 ] && P=logs/pipeline/rehearsal_reeval; mkdir -p "$P"
PRE=""; LIM=(); [ "$REH" = 1 ] && { PRE="dryr_"; LIM=(--limit 3); }
ST=06_build/staged/v3
TARGET="${TARGET:-0.95}"
V2="${V2:-03_prompts/system_prompt_v2.md}"
V3="${V3:-03_prompts/system_prompt_v3.md}"
GG="${GGUF_DIR:-/mnt/share/models/arete-27b}"
LORA_FILE="${LORA_FILE:-$GG/Arete-27B-lora-Q5_K_M.gguf}"
BASE_CFG="${SSDA_CONFIG:-config/assistant.yaml}"
CFG="$P/reeval_cfg"; mkdir -p "$CFG"
say() { echo "[$(date '+%F %T')] 재평가: $*" | tee -a "$P/pipeline.log"; }

mkcfg() {   # mkcfg 이름 시스템프롬프트 모형파일 — 기본 설정에서 시스템 프롬프트와 모형 파일만 바꿈(run_meta.json 에 실제 구성이 남음)
  "$PY" - "$BASE_CFG" "$CFG/$1.yaml" "$2" "$3" <<'EOF'
import sys, yaml
from pathlib import Path
src, dst, system, model = sys.argv[1:5]
c = yaml.safe_load(Path(src).read_text(encoding='utf-8'))
c['prompt']['system'] = system; c['model']['file'] = model
Path(dst).write_text(f'# 재평가용 설정(run_pipeline_reeval.sh 가 만듦) — {src} 에서 시스템 프롬프트와 모형 파일만 바꿈\n' + yaml.safe_dump(c, allow_unicode=True, sort_keys=False), encoding='utf-8')
EOF
}

read -r BASE_URL SERVED <<< "$(SSDA_CONFIG="$BASE_CFG" "$PY" -c "
import sys; sys.path.insert(0, '06_build')
from assistant import load_config
m = load_config()['model']; print(m['base_url'], m['served_name'])")"
PORT="${BASE_URL##*:}"; PORT="${PORT%%/*}"
alive() { curl -sf -m 3 "$BASE_URL/models" >/dev/null 2>&1; }
SERVER_PID=""
rss() { [ -n "$SERVER_PID" ] && ps -o rss= -p "$SERVER_PID" 2>/dev/null | awk '{printf "%.1fGiB", $1 / 1048576}'; }
stop_server() { if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then say "서버 종료(서버 RAM $(rss))"; kill "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null; fi; SERVER_PID=""; }
trap stop_server EXIT

complete() { "$PY" - "$1" <<'EOF'
import json, sys
from pathlib import Path
p = Path('05_eval/runs') / sys.argv[1] / 'run_meta.json'
sys.exit(0 if p.exists() and json.loads(p.read_text(encoding='utf-8')).get('complete') else 1)
EOF
}
field() { "$PY" -c "import json, sys; v = json.load(open(sys.argv[1], encoding='utf-8')).get(sys.argv[2]); print('' if v is None else v)" "$1" "$2"; }

[ -f "$LORA_FILE" ] || { say "모형 파일 없음: $LORA_FILE. 중단"; exit 1; }
for f in "$V2" "$V3"; do [ -f "$f" ] || { say "시스템 프롬프트 없음: $f. 중단"; exit 1; }; done

# ① GPU 비움 확인
if [ "$REH" != 1 ]; then
  t0=$SECONDS
  while :; do
    used="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | sort -n | tail -1)"
    [ "${used:-99999}" -le 4000 ] && ! alive && break
    [ $((SECONDS - t0)) -gt 1800 ] && { say "GPU 가 비지 않음(${used}MiB) 또는 서버가 남아 있음. 중단"; exit 1; }
    sleep 30
  done
fi

# ② 보완본 반영과 점검, 기존 실행의 재채점
if [ "$REH" != 1 ]; then
  bash "$ST/apply.sh" > "$P/reeval_apply.log" 2>&1; rc=$?
  tail -4 "$P/reeval_apply.log" | tee -a "$P/pipeline.log"
  [ $rc -eq 0 ] || { echo "보완본 반영 실패($rc)" > "$P/REEVAL.failed"; say "보완본 반영 실패(종료 코드 $rc). 중단"; exit 2; }
  "$PY" -B - > "$P/reeval_rescore.log" 2>&1 <<'EOF'
import json, shutil, sys
from pathlib import Path
sys.path.insert(0, '05_eval')
import score
for d in sorted(Path('05_eval/runs').glob('arete27b_*')):
    m = json.loads((d / 'run_meta.json').read_text(encoding='utf-8')) if (d / 'run_meta.json').exists() else {}
    if not (m.get('complete') and (d / 'report.json').exists() and m.get('items', 0) >= 161):
        continue
    old = json.loads((d / 'report.json').read_text(encoding='utf-8'))
    if not (d / 'report.scorer_v1.json').exists():          # 원래 보고서 보존
        shutil.copy2(d / 'report.json', d / 'report.scorer_v1.json'); shutil.copy2(d / 'report.md', d / 'report.scorer_v1.md')
    new = score.score_run(d)
    print(f"{d.name}: 문항 통과율 {old['metrics']['문항 통과율']} → {new['metrics']['문항 통과율']}, 바뀐 문항 {sorted(set(old['failed_items']) ^ set(new['failed_items']))}")
EOF
  say "기존 실행 재채점: $(tr '\n' ';' < "$P/reeval_rescore.log" | cut -c1-900)"
fi
LIBV="$("$PY" -c "import sys; sys.path.insert(0, '02_library'); import ssda; print(ssda.__version__)" 2>/dev/null)"
say "분석 함수 ssda ${LIBV:-확인 실패} · 채점기 $(sha256sum 05_eval/score.py | cut -c1-12) · 설정 $BASE_CFG"
if [ "$REH" != 1 ] && [ "$LIBV" != "0.4.1" ]; then say "현행 분석 함수가 보완본(0.4.1)이 아님. 중단"; exit 2; fi

start_server() {   # start_server 모형파일 기록이름
  say "서버 기동($1${CACHE_RAM:+, CACHE_RAM=$CACHE_RAM})"
  MODE="$([ "$REH" = 1 ] && echo cpu || echo gpu)" MODEL="$1" PORT="$PORT" ALIAS="$SERVED" bash 06_build/serve_llamacpp.sh > "$P/reeval_server_$2.log" 2>&1 &
  SERVER_PID=$!
  local s0=$SECONDS
  while [ $((SECONDS - s0)) -lt 1500 ]; do
    kill -0 "$SERVER_PID" 2>/dev/null || { say "서버가 종료됨. 기록 $P/reeval_server_$2.log"; tail -5 "$P/reeval_server_$2.log" | tee -a "$P/pipeline.log"; SERVER_PID=""; return 1; }
    alive && { say "서버 응답 확인($((SECONDS - s0))초) · GPU $(nvidia-smi --query-gpu=index,memory.used --format=csv,noheader | tr '\n' ';') · 서버 RAM $(rss)"; return 0; }
    sleep 2
  done
  say "서버 응답 없음"; stop_server; return 1
}
SRVTAG=lora
run_stage() {   # run_stage 실행이름 명령...
  local run="$1"; shift
  if complete "$run"; then say "$run: 이미 끝남(건너뜀)"; return 0; fi
  local try
  for try in 1 2; do
    if [ -z "$SERVER_PID" ] || ! alive; then stop_server; start_server "$LORA_FILE" "$SRVTAG" || { say "$run: 서버를 띄우지 못함"; return 1; }; fi
    say "$run: 시작($try차)"
    "$@" > "$P/reeval_$run.try$try.log" 2>&1
    complete "$run" && { say "$run: 끝(서버 RAM $(rss))"; return 0; }
    say "$run: 미완료(기록 $P/reeval_$run.try$try.log). 60초 뒤 이어서 수행"; sleep 60
  done
  say "$run: 완료하지 못함"; return 1
}

# ③ 평가
RUNS="arete27b_q5_v2_base,arete27b_q4_v2_base,arete27b_lora_short_base,arete27b_lora_long_base,arete27b_lora_v2_base"
rejudge() {     # 지금까지의 실행으로 판정
  "$PY" -B "$ST/judge.py" --target "$TARGET" --runs "$RUNS" --out "$P/REEVAL_result.json" > /dev/null 2>> "$P/reeval_judge.err"
  say "판정(누적): 가장 높은 구성 $(field "$P/REEVAL_result.json" best)(통과율 $(field "$P/REEVAL_result.json" rate), 목표 $TARGET)"
  return 0
}
eval_cfg() {    # eval_cfg 구성이름 시스템프롬프트
  local name="$1" prompt="$2"
  say "구성 $name: 모형 $LORA_FILE, 시스템 프롬프트 $prompt"
  mkcfg "$name" "$prompt" "$LORA_FILE"
  run_stage "${PRE}holdout2_$name" "$PY" 06_build/eval_holdout2.py --name "${PRE}holdout2_$name" --config "$CFG/$name.yaml" --resume "${LIM[@]}"
  run_stage "${PRE}holdout_$name" "$PY" 06_build/eval_holdout.py --name "${PRE}holdout_$name" --config "$CFG/$name.yaml" --resume "${LIM[@]}"
  run_stage "${PRE}arete27b_${name}_base" "$PY" 06_build/eval_run.py --name "${PRE}arete27b_${name}_base" --examples 0 --config "$CFG/$name.yaml" --resume "${LIM[@]}"
  RUNS="$RUNS,${PRE}arete27b_${name}_base"
  rejudge
}
say "재평가 시작 (pid $$)"
eval_cfg lora_v2_r2 "$V2"
eval_cfg lora_v3 "$V3"

# ④ 서버의 프롬프트 캐시 설정 확인 — 캐시를 끈 서버에서 구성 1의 보류 검증 문항 1차를 한 번 더 수행
if [ "${SKIP_CACHE_CHECK:-0}" != 1 ]; then
  stop_server; sleep 5
  export CACHE_RAM=0; SRVTAG=lora_cram0
  say "프롬프트 캐시 설정 확인: CACHE_RAM=0 으로 구성 lora_v2_r2 의 보류 검증 문항 1차를 다시 수행"
  run_stage "${PRE}holdout_lora_v2_r2_cram0" "$PY" 06_build/eval_holdout.py --name "${PRE}holdout_lora_v2_r2_cram0" --config "$CFG/lora_v2_r2.yaml" --resume "${LIM[@]}"
  unset CACHE_RAM
fi
stop_server

# ⑤ 마지막 판정
rejudge
say "재평가 뒤 판정: 가장 높은 구성 $(field "$P/REEVAL_result.json" best)(통과율 $(field "$P/REEVAL_result.json" rate), 목표 $TARGET) → $([ "$(field "$P/REEVAL_result.json" decision)" = skip ] && echo "목표 도달" || echo "목표 미달")"
[ "$REH" = 1 ] || date '+%F %T' > "$P/REEVAL_ALL.end"
say "재평가 끝"
