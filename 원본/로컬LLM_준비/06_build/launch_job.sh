#!/usr/bin/env bash
# 긴 작업을 세션과 분리해 띄우기 — 작업 단위(scope)와 메모리 압력 감시(psi_guard.py)를 함께 시작한다.
#
#   bash 06_build/launch_job.sh <이름> <명령...>
#   예) bash 06_build/launch_job.sh eval bash 06_build/run_pipeline_eval.sh
#
#   · 작업은 systemd 사용자 단위 ssda-<이름>-<시각>.scope 로 뜨므로 이 창(Claude 세션)이 닫혀도 계속 돈다
#   · 감시는 ssda-<이름>-<시각>-guard.scope 로 따로 뜬다. 세션의 메모리 압력이 오르면 작업을 잠시 멈춰 systemd-oomd 의 종료를 막는다
#     (2026-11-15 13:31 에 모형 적재 중 압력이 72% 까지 올라 Claude 앱과 평가 작업이 종료된 일의 재발 방지)
#   · 출력: logs/pipeline/<단위>.out, 감시 기록: logs/pipeline/psi_guard.log
#   · 중지: systemctl --user stop <단위>.scope   (감시는 작업이 끝나면 스스로 끝남)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
[ $# -ge 2 ] || { echo "사용법: bash 06_build/launch_job.sh <이름> <명령...>"; exit 1; }
NAME="$1"; shift
PY="${PY:-/mnt/share/행정데이터_set/.venv/bin/python}"
UNIT="ssda-$NAME-$(date +%m%d%H%M%S)"
mkdir -p logs/pipeline
# 감시를 먼저 띄워 작업 단위가 생기기를 기다리게 한다
setsid systemd-run --user --scope --quiet --unit="$UNIT-guard" "$PY" 06_build/psi_guard.py --unit "$UNIT.scope" --sample "${GUARD_SAMPLE:-60}" > "logs/pipeline/$UNIT-guard.out" 2>&1 < /dev/null &
setsid systemd-run --user --scope --quiet --unit="$UNIT" "$@" > "logs/pipeline/$UNIT.out" 2>&1 < /dev/null &
echo "$UNIT" > logs/pipeline/last_unit_"$NAME"
echo "$UNIT"
