#!/usr/bin/env bash
# 추론 서버 기동(llama.cpp llama-server + GGUF 양자화본) — 구축지시서 3단계 경로 나.
#
#   · 실행 파일은 build_llamacpp.sh 로 만든 것을 쓴다(GPU 구동용 ~/llama.cpp/build-cuda, GPU 없는 시험용 ~/llama.cpp/build-cpu).
#   · 인자는 이 PC의 빌드(2026-05-21 판, 7ea23dd)의 `--help`로 확인했다. 다른 판을 쓸 때는 `llama-server --help`로 다시 확인한다.
#   · 127.0.0.1 에서만 듣는다(폐쇄망 안에서도 다른 PC에 열지 않음). 주소를 넓힐 때는 --api-key 를 함께 쓴다.
#   · 사고 과정은 `--reasoning off`로 끈다(이 모형의 대화 틀은 끄지 않으면 사고 과정을 켜고 영어 안내문을 덧붙임).
#     요청이 chat_template_kwargs 로 enable_thinking 을 보내면 요청 값이 우선한다(축소 모형으로 확인, 2026-11-15).
#   · 두 GPU에 층 단위로 나눈다(--split-mode layer). tensor 방식은 이 계열 모형에서 충돌 보고가 있어 쓰지 않는다.
#   · 시각 입력은 쓰지 않으므로 mmproj 파일은 지정하지 않는다.
#   · GPU 구동(MODE=gpu)은 실행한 적 없음. MODE=cpu 는 축소 모형 시험과 양자화본 시범 구동에 썼다(cpu_selftest.py, 모형반입/cpu_실모형_시험.md).
#
# 사용  MODEL=/mnt/share/models/arete-27b/Arete-27B-Q5_K_M.gguf bash 06_build/serve_llamacpp.sh              # GPU 2장(기본)
#       MODE=cpu MODEL=<파일.gguf> PORT=8094 bash 06_build/serve_llamacpp.sh                                  # GPU 를 쓰지 않는 시험
# 환경변수  PORT(8080) CTX(16384) ALIAS(arete-27b) LORA(어댑터.gguf) THREADS(cpu 모드 스레드 수, 기본 6) BIN(실행 파일 경로) FORCE(1: GPU 점유 무시)
#           CACHE_RAM(요청별 상태를 RAM 에 보관하는 캐시의 상한 MiB. 지정하지 않으면 서버 기본값 8192, 0 이면 끔)
set -euo pipefail

MODEL="${MODEL:?양자화 모형 파일(.gguf) 경로를 MODEL 로 지정}"
MODE="${MODE:-gpu}"
PORT="${PORT:-8080}"                 # config/assistant.yaml 의 model.base_url 과 맞춘다
CTX="${CTX:-16384}"                  # config/assistant.yaml 의 model.context_tokens 와 맞춘다
ALIAS="${ALIAS:-arete-27b}"          # config/assistant.yaml 의 model.served_name 과 맞춘다
LORA="${LORA:-}"                     # 미세조정 어댑터(.gguf)가 있으면 경로 지정
LLAMA="${LLAMA:-$HOME/llama.cpp}"

[ -f "$MODEL" ] || { echo "모형 파일 없음: $MODEL (bash 06_build/make_gguf.sh 로 만든다)"; exit 1; }
ARGS=(-m "$MODEL" -c "$CTX" --host 127.0.0.1 --port "$PORT" -a "$ALIAS" -np 1 --jinja --reasoning off --no-ui --offline)

if [ "$MODE" = "cpu" ]; then
  BIN="${BIN:-$LLAMA/build-cpu/bin/llama-server}"
  export CUDA_VISIBLE_DEVICES=""     # GPU 를 건드리지 않음
  ARGS+=(-t "${THREADS:-6}" --no-warmup -to "${TIMEOUT:-7200}")
else
  BIN="${BIN:-$LLAMA/build-cuda/bin/llama-server}"
  [ -x "$BIN" ] || BIN="$(command -v llama-server || true)"
  # GPU 여유 확인(다른 작업이 점유 중이면 올리지 않는다)
  if command -v nvidia-smi >/dev/null; then
    nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader
    USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | awk '{s+=$1} END {print s}')
    if [ "${USED:-0}" -gt 4000 ] && [ "${FORCE:-0}" != "1" ]; then
      echo "GPU 메모리를 다른 작업이 사용 중(${USED}MiB). 종료 후 다시 실행하거나 FORCE=1 지정"; exit 1
    fi
  fi
  ARGS+=(-ngl all -sm layer -ts 1,1)
fi
# 파일 읽기 방식: 기본값(메모리 매핑 + 전체 미리 읽기)을 쓰지 않고 직접 읽기(O_DIRECT)로 올린다.
#   2026-11-15 13:31 에 17.9GiB 양자화본을 HDD 에서 메모리 매핑으로 올리던 중 세션의 메모리 압력이 72% 까지 올라
#   systemd-oomd 가 Claude 앱과 평가 작업을 종료했다(RAM 은 26GB 남아 있었음). 직접 읽기는 페이지 캐시를 거치지 않아 압력을 만들지 않는다.
#   MMAP=1 을 주면 종전 방식으로 올린다(SSD 에 둔 작은 파일을 빨리 올릴 때만).
[ "${MMAP:-0}" = "1" ] || ARGS+=(--no-mmap --direct-io)
[ -n "$BIN" ] && [ -x "$BIN" ] || { echo "llama-server 실행 파일 없음: bash 06_build/build_llamacpp.sh $([ "$MODE" = cpu ] && echo cpu || echo cuda) 로 빌드"; exit 1; }
[ -n "$LORA" ] && ARGS+=(--lora "$LORA")
[ -n "${CACHE_RAM:-}" ] && ARGS+=(--cache-ram "$CACHE_RAM")

echo "$BIN ${ARGS[*]}"
exec "$BIN" "${ARGS[@]}"
