#!/usr/bin/env bash
# 통계 프로그램 + 자연어 명령 창 + 정책 대시보드를 한 서버로 실행한다(127.0.0.1 한정). 끝낼 때는 Ctrl+C.
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/python -m app.run --open "$@"
