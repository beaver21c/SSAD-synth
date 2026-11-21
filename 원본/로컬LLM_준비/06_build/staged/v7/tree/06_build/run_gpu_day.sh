#!/usr/bin/env bash
# GPU 가동일 일괄 실행 — 구축지시서 4단계(서버 기동·연결 확인)와 5단계(평가)를 한 번에 수행한다.
#
#   GPU 가 비어 있을 때 아래 한 줄을 실행하면 서버 기동 → 연결 확인 질문 → 평가(유사 예시 없음 / 2개) → 요약 → 서버 종료까지 진행한다.
#     bash 06_build/run_gpu_day.sh
#
#   순서  ① 준비 상태·GPU 점유 확인(4GB 넘게 점유돼 있으면 중단)
#         ② 추론 서버 기동: 기본은 llama.cpp + GGUF 양자화본(경로 나). 뜨지 않으면 공식 가중치 4비트 서버(경로 가)로 바꿔 다시 시도
#         ③ 적재 후 GPU 메모리 기록
#         ④ 연결 확인 질문 4개(구축지시서 4단계 확인 ②~⑤)를 조립기로 처리해 기록. 응답에 사고 과정 표시가 섞였는지 확인
#         ⑤ 평가: <이름>_base(유사 예시 없음), <이름>_ex2(유사 예시 2개). 중간에 끊기면 같은 명령을 다시 실행하면 이어서 수행함(--resume)
#         ⑥ 요약(지표·기준 대조·소요 시간·초당 토큰 수)을 logs/gpu_day/<시각>/summary.md 에 쓰고 서버를 내림
#
#   선택 인자  --path auto|gguf|transformers   서버 경로(기본 auto: gguf 를 먼저 시도)
#             --quant Q5_K_M                   GGUF 양자화 수준(기본 Q5_K_M. Q4_K_M·Q6_K 도 만들어 둠)
#             --name arete27b_q5               평가 실행 이름의 머리(기본: 경로와 양자화 수준으로 정함)
#             --examples "0 2"                 평가할 유사 예시 수 목록
#             --lora <어댑터 폴더>              transformers 경로에서 어댑터를 함께 올림(이름 뒤에 _lora 가 붙음)
#             --skip-eval                      연결 확인까지만 수행
#             --keep-server                    끝나도 서버를 내리지 않음
#             --dry-run                        GPU 를 쓰지 않는 예행 연습: 모의 응답 서버로 전 과정을 돌려 절차만 확인(평가는 6문항)
#             --cpu-rehearsal                  GPU 를 쓰지 않는 예행 연습: 실제 llama.cpp 서버를 축소 모형으로 CPU 에 띄워 기동·대기·평가·종료 절차를 확인
#                                              (축소 모형은 무작위 가중치이므로 응답과 판정에는 의미가 없음. cpu_selftest.py 를 먼저 실행해 축소 모형을 만들어 둠)
#
#   절차는 --dry-run 과 --cpu-rehearsal 로 확인했고, 2026-11-15 에 GPU 에서 처음 실행함(첫 기동에서 적재 대기 판정을 고침).
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT="$PWD"
PY="${PY:-/mnt/share/행정데이터_set/.venv/bin/python}"
PYC="${PYC:-$HOME/anaconda3/envs/vllm/bin/python}"
export SSDA_DATA="${SSDA_DATA:-/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet}"
GGUF_DIR="${GGUF_DIR:-/mnt/share/models/arete-27b}"

WAY=auto; QUANT=Q5_K_M; NAME=""; EXAMPLES="0 2"; LORA=""; SKIP_EVAL=0; KEEP=0; DRY=0; REH=0
while [ $# -gt 0 ]; do
  case "$1" in
    --path) WAY="$2"; shift 2 ;;
    --quant) QUANT="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    --examples) EXAMPLES="$2"; shift 2 ;;
    --lora) LORA="$2"; shift 2 ;;
    --skip-eval) SKIP_EVAL=1; shift ;;
    --keep-server) KEEP=1; shift ;;
    --dry-run) DRY=1; shift ;;
    --cpu-rehearsal) DRY=1; REH=1; shift ;;
    *) echo "모르는 인자: $1"; exit 1 ;;
  esac
done

read -r BASE_URL SERVED <<< "$($PY -c "
import sys; sys.path.insert(0, '06_build')
from assistant import load_config
m = load_config()['model']; print(m['base_url'], m['served_name'])")"
PORT="${BASE_URL##*:}"; PORT="${PORT%%/*}"
STAMP="$(date +%Y%m%d_%H%M%S)"; [ "$DRY" = 1 ] && STAMP="dryrun_$STAMP"
LOGDIR="$ROOT/logs/gpu_day/$STAMP"; mkdir -p "$LOGDIR"
SUM="$LOGDIR/summary.md"
say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOGDIR/run.log"; }
SERVER_PID=""
stop_server() { if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then kill "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null; say "서버 종료"; fi; SERVER_PID=""; }
cleanup() { [ "$KEEP" = 1 ] && [ -n "$SERVER_PID" ] && { say "서버를 내리지 않음(pid $SERVER_PID, --keep-server)"; return; }; stop_server; }
trap cleanup EXIT

alive() { curl -sf -m 3 "$BASE_URL/models" >/dev/null 2>&1; }   # -f: 모형을 올리는 동안 서버가 돌려주는 503(Loading model)을 응답으로 보지 않음(2026-11-15 첫 GPU 기동에서 확인)
start_server() {   # start_server gguf|transformers|mock  → 0: 응답함
  local kind="$1" wait_sec=1200
  say "서버 기동($kind)"
  case "$kind" in
    gguf) MODE="$([ "$REH" = 1 ] && echo cpu || echo gpu)" MODEL="${GGUF_FILE:-$GGUF_DIR/Arete-27B-$QUANT.gguf}" PORT="$PORT" ALIAS="$SERVED" bash 06_build/serve_llamacpp.sh > "$LOGDIR/server_$kind.log" 2>&1 & ;;
    transformers) "$PYC" 06_build/serve_transformers.py --port "$PORT" --name "$SERVED" ${LORA:+--lora "$LORA"} > "$LOGDIR/server_$kind.log" 2>&1 & ;;
    mock) wait_sec=30
          "$PY" 06_build/serve_transformers.py --dry-run --port "$PORT" --name "$SERVED" > "$LOGDIR/server_$kind.log" 2>&1 & ;;
  esac
  SERVER_PID=$!
  local t0=$SECONDS
  while [ $((SECONDS - t0)) -lt $wait_sec ]; do
    kill -0 "$SERVER_PID" 2>/dev/null || { say "서버가 종료됨($kind). 기록: $LOGDIR/server_$kind.log"; tail -5 "$LOGDIR/server_$kind.log" | tee -a "$LOGDIR/run.log"; SERVER_PID=""; return 1; }
    alive && { say "서버 응답 확인($kind, $((SECONDS - t0))초)"; return 0; }
    sleep 2
  done
  say "서버 응답 없음($kind, ${wait_sec}초)"; stop_server; return 1
}

say "준비 폴더 $ROOT · 주소 $BASE_URL · 모형 이름 $SERVED · 기록 $LOGDIR"
alive && { say "이미 $BASE_URL 에 응답하는 서버가 있음. 그 서버를 내리거나 설정 파일의 주소를 바꾼 뒤 실행"; exit 1; }

# ① 준비 상태·GPU 점유
if [ "$REH" = 1 ]; then
  GGUF_FILE="${GGUF_FILE:-$GGUF_DIR/test/tiny-twin-Q4_K_M.gguf}"
  [ -f "$GGUF_FILE" ] || { say "축소 모형 없음: $GGUF_FILE (conda 환경 vllm 에서 python 06_build/cpu_selftest.py 를 먼저 실행)"; exit 1; }
  say "예행 연습: GPU 를 쓰지 않고 축소 모형($GGUF_FILE)을 llama.cpp 서버로 CPU 에 띄워 절차를 확인"
  KIND=gguf; NAME=dryrun
elif [ "$DRY" = 1 ]; then
  say "예행 연습: GPU 를 쓰지 않고 모의 응답 서버로 절차만 확인"
  KIND=mock
else
  USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | awk '{s+=$1} END {print s+0}')
  nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv,noheader | tee -a "$LOGDIR/run.log"
  if [ "$USED" -gt 4000 ] && [ "${FORCE:-0}" != 1 ]; then say "GPU 를 다른 작업이 사용 중(${USED}MiB). 비워진 뒤 다시 실행"; exit 3; fi
  KIND="$WAY"
  if [ "$WAY" = auto ]; then
    if [ -f "$GGUF_DIR/Arete-27B-$QUANT.gguf" ] && [ -x "$HOME/llama.cpp/build-cuda/bin/llama-server" ] && [ -z "$LORA" ]; then KIND=gguf; else KIND=transformers; fi
  fi
fi

# ② 서버 기동(auto: gguf 가 뜨지 않으면 transformers 로)
if ! start_server "$KIND"; then
  if [ "$WAY" = auto ] && [ "$KIND" = gguf ] && [ "$DRY" != 1 ]; then KIND=transformers; start_server "$KIND" || { say "두 경로 모두 서버가 뜨지 않음"; exit 4; }
  else exit 4; fi
fi
[ -n "$NAME" ] || { case "$KIND" in gguf) NAME="arete27b_$(echo "$QUANT" | tr 'A-Z' 'a-z' | cut -d_ -f1)" ;; transformers) NAME="arete27b_nf4" ;; mock) NAME="dryrun" ;; esac; [ -n "$LORA" ] && NAME="${NAME}_lora"; }

{
  echo "# GPU 가동일 실행 요약 — $STAMP"; echo
  echo "- 서버 경로: $KIND$([ "$KIND" = gguf ] && [ "$REH" != 1 ] && echo " ($QUANT)")$([ "$REH" = 1 ] && echo " (축소 모형, CPU)")$([ -n "$LORA" ] && echo ", 어댑터 $LORA")"
  echo "- 주소: $BASE_URL, 모형 이름: $SERVED"
  [ "$DRY" = 1 ] && echo "- 예행 연습임: $([ "$REH" = 1 ] && echo "무작위 가중치인 축소 모형" || echo "모의 응답 서버")의 결과이므로 아래의 응답 유형과 판정에는 의미가 없음(절차 확인용)"
} > "$SUM"

# ③ 적재 후 GPU 메모리
if [ "$DRY" != 1 ]; then
  echo "- 적재 후 GPU 메모리: $(nvidia-smi --query-gpu=index,memory.used --format=csv,noheader | tr '\n' ';')" | tee -a "$SUM"
fi

# ④ 연결 확인 질문
QS=("65세 이상 기초연금 수급률을 시도별로 알려 줘" "기초연금 수급률을 시도별로 알려 줘" "국기초 수급률을 시도별로 알려 줘" "국기초 생계급여 수급률을 시도별로 알려 줘")
echo -e "\n## 연결 확인 질문\n" >> "$SUM"
i=0; LEAK=0
for q in "${QS[@]}"; do
  i=$((i + 1)); t0=$SECONDS
  "$PY" 06_build/assistant.py --ask "$q" > "$LOGDIR/check_$i.txt" 2>&1; rc=$?
  grep -q "</think>\|<think>" "$LOGDIR/check_$i.txt" && LEAK=1
  kind="응답"; grep -q '```python' "$LOGDIR/check_$i.txt" && kind="코드 작성"; grep -qE "^[#*「[:space:]]*확인 필요" "$LOGDIR/check_$i.txt" && kind="되물음"; [ $rc -ne 0 ] && kind="오류"
  echo "- 질문 $i 「$q」: $kind, $((SECONDS - t0))초 (기록 check_$i.txt)" | tee -a "$SUM"
done
[ "$LEAK" = 1 ] && echo "- **주의**: 응답에 사고 과정 표시가 섞임. 사고 과정 끄기 인자가 서버에 전달되는지 확인할 것" | tee -a "$SUM"
echo "- 기대: 질문 1은 65세 이상을 분모로 한 코드, 질문 2는 분모를 65세 이상으로 두거나 경고 후 수정, 질문 3은 되물음, 질문 4는 되묻지 않고 산출" >> "$SUM"

# ⑤ 평가
if [ "$SKIP_EVAL" != 1 ]; then
  echo -e "\n## 평가\n" >> "$SUM"
  for n in $EXAMPLES; do
    run="${NAME}_$([ "$n" = 0 ] && echo base || echo "ex$n")"
    say "평가 $run (유사 예시 $n개)"
    "$PY" 06_build/eval_run.py --name "$run" --examples "$n" --resume $([ "$DRY" = 1 ] && echo "--limit 6") 2>&1 | tee "$LOGDIR/eval_$run.log" | grep -E "문항 ·|이어서|오류" | tee -a "$LOGDIR/run.log"
    rc=${PIPESTATUS[0]}
    "$PY" - "$run" "$rc" >> "$SUM" <<'EOF'
import json, sys
from pathlib import Path
run, rc = sys.argv[1], int(sys.argv[2])
d = Path('05_eval/runs') / run
rep = json.loads((d / 'report.json').read_text(encoding='utf-8')) if (d / 'report.json').exists() else None
meta = json.loads((d / 'run_meta.json').read_text(encoding='utf-8')) if (d / 'run_meta.json').exists() else {}
print(f"### {run}\n")
if not rep:
    print(f"- 결과 없음(종료 코드 {rc})\n"); sys.exit()
u = meta.get('usage') or {}; el = meta.get('elapsed_sec') or 0
print(f"- 종합 판정: {'통과' if rep['passed'] else '미달'}{'' if meta.get('complete', True) else ' (미완료: 오류 문항 ' + ', '.join(e['id'] for e in meta.get('errors', [])) + ')'}")
print(f"- 문항: 벤치마크 {rep['n_benchmark']}, 안전성 {rep['n_safety']} · 소요 {el / 60:.1f}분 · 모형 호출 {u.get('calls', 0)}회 · 입력 {u.get('prompt_tokens', 0):,}토큰, 출력 {u.get('completion_tokens', 0):,}토큰"
      + (f" · 출력 초당 {u.get('completion_tokens', 0) / el:.1f}토큰(실행 시간 포함 어림)" if el else '') + (f" · 원문 생성 예비 경로 {u['raw_fallbacks']}회" if u.get('raw_fallbacks') else ''))
bad = [k for k, v in rep['judge'].items() if v is False]
print(f"- 기준 미달 지표: {', '.join(f'{k} {rep['metrics'][k]}' for k in bad) or '없음'}")
print(f"- 차단 실패 건수: {rep['metrics'].get('차단 실패 건수')}")
print(f"- 상세: 05_eval/runs/{run}/report.md\n")
EOF
  done
fi

# ⑥ 마무리
[ "$DRY" = 1 ] || "$PY" 06_build/preflight.py --quick > "$LOGDIR/preflight.txt" 2>&1 || true
[ "$DRY" = 1 ] && rm -rf "$ROOT/05_eval/runs/dryrun_base" "$ROOT"/05_eval/runs/dryrun_ex[0-9]     # 예행 연습의 평가 결과는 의미가 없으므로 지움(기록은 logs/gpu_day 에 남음)
echo -e "\n## 다음 단계\n\n- 평가가 기준을 충족하면 구축지시서 7단계(시범 운영 설정), 미달이면 6단계(보강)로 감\n- 서버 기록: server_$KIND.log (요청별 토큰 수·속도)" >> "$SUM"
say "요약: $SUM"; cat "$SUM"
