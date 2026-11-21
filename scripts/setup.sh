#!/usr/bin/env bash
# 최초 1회 준비: 가상환경, OpenStat Studio 내려받기, 필요한 패키지 설치.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
[ -d .venv ] || "$PY" -m venv .venv
if [ ! -d 원본/발표자료_행정데이터_AI/demo/openstat/reconstructed ] && [ ! -d vendor/pyopenstat ]; then
  mkdir -p vendor
  git clone --depth 1 https://github.com/beaver21c/pyopenstat vendor/pyopenstat
fi
OST=vendor/pyopenstat
[ -d "$OST" ] || OST=원본/발표자료_행정데이터_AI/demo/openstat
.venv/bin/pip install -q --upgrade pip
[ -f "$OST/requirements.txt" ] && .venv/bin/pip install -q -r "$OST/requirements.txt"
.venv/bin/pip install -q -r requirements.txt
echo "준비 완료. 다음: scripts/start.sh"
