#!/usr/bin/env bash
# 공식 가중치 → GGUF 양자화본 만들기 — llama.cpp 서버(구축지시서 3단계 경로 나)에 쓴다. GPU 를 쓰지 않는다.
#
#   · 이 PC의 ~/llama.cpp(2026-05-21 판)에 들어 있는 변환·양자화 도구를 쓴다. 새로 내려받는 것은 없다.
#   · 제3자가 올린 양자화 파일을 받지 않고 공식 가중치에서 직접 만드는 방법이다.
#   · 변환은 가중치 54.7GB 를 읽어 같은 크기의 중간 파일(bf16)을 쓰고, 양자화는 그 중간 파일에서 수준별 파일을 만든다.
#   · 다른 작업에 지장을 주지 않도록 낮은 우선순위(nice 19), 스레드 4개, 메모리 상한(기본 13G)으로 돌린다.
#     변환 도구를 그대로 쓰면 가장 큰 텐서(어휘 248,320 × 5,120)에서 약 11GB 를 써 상한 8G·10G 에서 중단됐다(2026-11-15).
#     그래서 결과는 같고 메모리를 덜 쓰는 포장 스크립트(convert_lean.py, 최대 약 8.5GB)로 변환 도구를 부른다.
#     양자화 도구(llama-quantize)는 같은 텐서에서 약 10GB 를 쓴다(상한 10G 에서 중단됨). 그래서 상한의 기본값을 13G 로 둔다. RAM 여유가 13GB 이상일 때 실행한다.
#     메모리 상한을 넘으면 이 작업만 중단되고 다른 작업에는 영향이 없다(systemd-run 범위 + oom_score_adj).
#   · 이미 있는 파일은 다시 만들지 않는다. 만드는 중인 파일은 .part 로 쓰고 끝나면 이름을 바꾼다.
#
# 사용  bash 06_build/make_gguf.sh --check                    # 변환 도구가 이 모형을 읽는지 확인만 함(파일을 쓰지 않음)
#       bash 06_build/make_gguf.sh Q5_K_M                     # 변환 + 양자화
#       bash 06_build/make_gguf.sh Q5_K_M Q4_K_M Q6_K         # 여러 수준을 차례로
# 환경변수  OUT(출력 폴더, 기본 /mnt/share/models/arete-27b)  MEM(메모리 상한, 기본 13G)  THREADS(기본 4)
#           SNAP(변환할 모형 폴더, 기본 내려받은 공식 가중치)  NAME(파일 이름 머리, 기본 Arete-27B)
#           — 어댑터를 합친 모형(merge_lora.py)을 변환할 때: SNAP=<합친 폴더> NAME=Arete-27B-lora bash 06_build/make_gguf.sh Q5_K_M
#           NO_SCOPE=1  메모리 상한 범위를 따로 만들지 않음(launch_job.sh 로 띄운 작업 단위 안에서 돌 때: 압력 감시가 그 단위를 지켜봄)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LLAMA="${LLAMA:-$HOME/llama.cpp}"
PY="${PY:-$HOME/anaconda3/envs/vllm/bin/python}"
SNAP="${SNAP:-$(ls -d /mnt/share/hf_cache/hub/models--NousResearch--Arete-27B/snapshots/*/ | head -1)}"
NAME="${NAME:-Arete-27B}"
OUT="${OUT:-/mnt/share/models/arete-27b}"
MEM="${MEM:-13G}"; THREADS="${THREADS:-4}"

[ -f "$LLAMA/convert_hf_to_gguf.py" ] || { echo "llama.cpp 없음: $LLAMA"; exit 1; }
[ -f "$SNAP/config.json" ] || { echo "공식 가중치 없음: $SNAP"; exit 1; }
export CUDA_VISIBLE_DEVICES=""              # 변환 도구가 torch 를 불러도 GPU 를 건드리지 않게 함
export PYTHONPATH="$LLAMA/gguf-py"

run() {   # 낮은 우선순위 + 메모리 상한. 상한을 넘으면 이 작업만 중단됨
  local inner='echo 1000 > /proc/self/oom_score_adj 2>/dev/null || true; exec nice -n 19 ionice -c 3 "$@"'
  if [ "${NO_SCOPE:-0}" != "1" ] && systemd-run --user --scope --quiet -p MemoryMax=64M true 2>/dev/null; then
    systemd-run --user --scope --quiet -p MemoryMax="$MEM" -p MemorySwapMax=0 -- bash -c "$inner" _ "$@"
  else
    bash -c "$inner" _ "$@"
  fi
}
stamp() { date '+%F %T'; }

if [ "${1:-}" = "--check" ]; then
  run "$PY" "$HERE/convert_lean.py" "$LLAMA/convert_hf_to_gguf.py" "$SNAP" --outtype bf16 --dry-run
  exit $?
fi
[ $# -ge 1 ] || set -- Q5_K_M

mkdir -p "$OUT"
F16="$OUT/$NAME-bf16.gguf"
if [ ! -f "$F16" ]; then
  echo "[$(stamp)] 변환 시작: $SNAP → $F16"; t0=$SECONDS
  rm -f "$F16.part"
  run "$PY" "$HERE/convert_lean.py" "$LLAMA/convert_hf_to_gguf.py" "$SNAP" --outtype bf16 --outfile "$F16.part"   # 메모리를 덜 쓰는 실행(결과는 같음)
  mv "$F16.part" "$F16"
  echo "[$(stamp)] 변환 완료: $(du -h "$F16" | cut -f1), $((SECONDS - t0))초"
else
  echo "[$(stamp)] 중간 파일 있음: $F16"
fi

QBIN="$LLAMA/build-cpu/bin/llama-quantize"
[ -x "$QBIN" ] || bash "$HERE/build_llamacpp.sh" cpu

for Q in "$@"; do
  G="$OUT/$NAME-$Q.gguf"
  if [ -f "$G" ]; then echo "[$(stamp)] 이미 있음: $G"; continue; fi
  echo "[$(stamp)] 양자화 시작: $Q"; t0=$SECONDS
  rm -f "$G.part"
  run "$QBIN" "$F16" "$G.part" "$Q" "$THREADS"
  mv "$G.part" "$G"
  (cd "$OUT" && nice -n 19 sha256sum "$(basename "$G")" > "$(basename "$G").sha256")
  echo "[$(stamp)] 양자화 완료: $Q $(du -h "$G" | cut -f1), $((SECONDS - t0))초, sha256 $(cut -c1-16 "$G.sha256")…"
done
echo "[$(stamp)] 끝. 중간 파일 $F16 은 다른 양자화 수준을 더 만들지 않을 것이면 지워도 됨"
