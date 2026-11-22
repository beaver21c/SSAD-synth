#!/usr/bin/env bash
# 삭제(macOS·Linux): 이 폴더 안에 설치·생성된 것만 지운다. 컴퓨터에 깔린 Python 자체는 건드리지 않는다.
#   1단계  실행 중인 서버 종료 + 설치된 실행 환경(.venv)과 실행 중 생긴 기록 삭제 → 내려받은 직후 상태로 되돌림
#   2단계  (선택) 폴더 전체 삭제 → 통계 프로그램·대시보드·가상데이터까지 모두 제거
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
[ -f app/run.py ] && [ -f START.sh ] || { echo "[오류] 프로그램 폴더가 아님: $ROOT"; exit 1; }
GEN=(.venv workspace_nl openstat/workspace openstat/reports "openstat/sample_data/사회보장행정데이터_가상_주요변수.csv" "openstat/sample_data/geo/시도경계_간략.geojson")

echo "삭제 대상(이 폴더 안): ${GEN[*]} 및 __pycache__"
if [ "${1:-}" != "--yes" ] && [ "${1:-}" != "--all" ]; then
  read -r -p "진행 [y/N]: " a; [ "$a" = "y" ] || [ "$a" = "Y" ] || { echo "취소함"; exit 0; }
fi
if [ -x .venv/bin/python ]; then                       # 이 폴더의 실행 환경으로 뜬 서버만 종료
  pkill -f "$ROOT/.venv/bin/python -m app.run" 2>/dev/null && echo "[완료] 실행 중인 서버 종료"
fi
for d in "${GEN[@]}"; do [ -e "$d" ] && rm -rf -- "$ROOT/$d" && echo "[삭제] $d"; done
find "$ROOT" -name __pycache__ -type d -not -path "$ROOT/.git/*" -prune -exec rm -rf {} + 2>/dev/null
echo "[완료] 설치 이전 상태로 되돌림. START.sh 를 다시 실행하면 재설치됨"

if [ "${1:-}" = "--all" ]; then a=y; elif [ "${1:-}" = "--yes" ]; then a=n; else
  read -r -p "폴더 전체($ROOT)도 삭제 [y/N]: " a; fi
if [ "$a" = "y" ] || [ "$a" = "Y" ]; then
  cd / && rm -rf -- "$ROOT" && echo "[완료] 폴더 전체 삭제: $ROOT"
fi
