#!/usr/bin/env bash
# 실행기(macOS·Linux): 최초 1회 가상환경·패키지 설치 후, 서버(127.0.0.1:8500)를 켜고 기본 브라우저로 화면을 연다. 끝낼 때는 Ctrl+C.
set -e
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then echo "[오류] Python 3.10 이상이 필요함 (https://www.python.org/downloads/)"; exit 1; fi
if [ ! -x .venv/bin/python ]; then
  echo "[최초 1회] 가상환경 생성 및 패키지 설치 — 인터넷 속도에 따라 3~10분 소요"
  "$PY" -m venv .venv
fi
if ! cmp -s requirements.txt .venv/requirements.installed.txt; then
  .venv/bin/python -m pip install --upgrade pip --quiet
  .venv/bin/python -m pip install -r requirements.txt --quiet
  cp requirements.txt .venv/requirements.installed.txt
fi
exec "$PWD/.venv/bin/python" -m app.run --open "$@"
