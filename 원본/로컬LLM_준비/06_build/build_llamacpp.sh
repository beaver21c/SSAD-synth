#!/usr/bin/env bash
# llama.cpp 실행 파일 빌드 — 컴파일만 하며 GPU 를 쓰지 않는다.
#
#   cpu   llama-quantize · llama-server · llama-cli  → ~/llama.cpp/build-cpu/bin   (양자화, GPU 없는 시범 구동)
#   cuda  llama-server                               → ~/llama.cpp/build-cuda/bin  (GPU 구동용. CUDA 도구 /usr/local/cuda 필요)
#
#   · 이 PC의 ~/llama.cpp(2026-05-21 판)를 그대로 쓴다. 새로 내려받는 것은 없다(화면 UI 내려받기와 HTTPS 지원을 끔).
#   · 기존 ~/llama.cpp/build 폴더는 건드리지 않는다.
#   · 낮은 우선순위(nice 19)로 돌린다. 작업 수는 J(기본 4).
#   · 이 PC의 CPU 에 맞춘 빌드다(GGML_NATIVE). 다른 장비로 옮길 때는 그 장비에서 다시 빌드한다.
#
# 사용  bash 06_build/build_llamacpp.sh cpu | cuda | all
set -euo pipefail
LLAMA="${LLAMA:-$HOME/llama.cpp}"; J="${J:-4}"; WHAT="${1:-all}"
[ -f "$LLAMA/CMakeLists.txt" ] || { echo "llama.cpp 없음: $LLAMA"; exit 1; }
COMMON=(-DCMAKE_BUILD_TYPE=Release -DLLAMA_BUILD_UI=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_OPENSSL=OFF)

build() {   # build <이름> <ON|OFF> <대상...>
  local name="$1" cuda="$2"; shift 2
  local dir="$LLAMA/build-$name" t0=$SECONDS
  mkdir -p "$dir"
  echo "[$(date '+%F %T')] 구성 $dir (GGML_CUDA=$cuda)"
  cmake -S "$LLAMA" -B "$dir" "${COMMON[@]}" -DGGML_CUDA="$cuda" > "$dir/configure.log" 2>&1 || { tail -40 "$dir/configure.log"; exit 1; }
  echo "[$(date '+%F %T')] 빌드 $* (작업 $J개)"
  nice -n 19 cmake --build "$dir" --target "$@" -j "$J" > "$dir/build.log" 2>&1 || { tail -60 "$dir/build.log"; exit 1; }
  {
    echo "built_at: $(date '+%F %T')"
    echo "source: $LLAMA @ $(git -C "$LLAMA" log -1 --format='%h %ad' --date=short)"
    echo "options: ${COMMON[*]} -DGGML_CUDA=$cuda"
    echo "compiler: $(gcc --version | head -1)"
    [ "$cuda" = ON ] && echo "cuda: $(nvcc --version | grep -i release)"
    echo "targets: $*"
    echo "elapsed_sec: $((SECONDS - t0))"
  } > "$dir/BUILD_INFO.txt"
  for t in "$@"; do [ -x "$dir/bin/$t" ] || { echo "실행 파일 없음: $dir/bin/$t"; exit 1; }; done
  echo "[$(date '+%F %T')] 완료 $dir/bin ($((SECONDS - t0))초)"; ls -la "$dir/bin" | grep -E "llama-(quantize|server|cli)$" || true
}

case "$WHAT" in
  cpu)  build cpu OFF llama-quantize llama-server llama-cli ;;
  cuda) build cuda ON llama-server ;;
  all)  build cpu OFF llama-quantize llama-server llama-cli; build cuda ON llama-server ;;
  *) echo "사용: $0 cpu|cuda|all"; exit 1 ;;
esac
