#!/usr/bin/env bash
# 개발 점검용 추론 서버 — 모형을 올려 두고 여러 번의 짧은 점검 실행에 쓴다(평가용 일괄 실행과 따로).
#   bash 06_build/dev_server.sh start lora|base     # 서버를 띄우고 응답할 때까지 기다림(launch_job.sh 로 세션과 분리)
#   bash 06_build/dev_server.sh stop                # 서버 종료
#   bash 06_build/dev_server.sh status
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PY:-/mnt/share/행정데이터_set/.venv/bin/python}"
GG=/mnt/share/models/arete-27b
read -r BASE_URL SERVED <<< "$("$PY" -c "
import sys; sys.path.insert(0, '06_build')
from assistant import load_config
m = load_config()['model']; print(m['base_url'], m['served_name'])")"
PORT="${BASE_URL##*:}"; PORT="${PORT%%/*}"
alive() { curl -sf -m 3 "$BASE_URL/models" >/dev/null 2>&1; }
case "${1:-status}" in
  start)
    MODEL="$GG/Arete-27B-lora-Q5_K_M.gguf"; [ "${2:-lora}" = base ] && MODEL="$GG/Arete-27B-Q5_K_M.gguf"
    if alive; then echo "이미 서버가 응답함. 먼저 stop"; exit 1; fi
    MODE=gpu MODEL="$MODEL" PORT="$PORT" ALIAS="$SERVED" bash 06_build/launch_job.sh devsrv bash 06_build/serve_llamacpp.sh > logs/pipeline/dev_server.unit
    for i in $(seq 1 150); do alive && break; sleep 2; done
    alive && echo "서버 응답 확인: $(basename "$MODEL") · 단위 $(cat logs/pipeline/dev_server.unit)" || { echo "서버 응답 없음"; exit 1; } ;;
  stop)
    u="$(cat logs/pipeline/dev_server.unit 2>/dev/null)"; [ -n "$u" ] && systemctl --user stop "$u.scope" 2>/dev/null
    pkill -x llama-server 2>/dev/null; sleep 3; alive && echo "아직 응답함" || echo "종료됨" ;;
  status) alive && echo "응답함($(pgrep -x llama-server | head -1))" || echo "서버 없음" ;;
esac
