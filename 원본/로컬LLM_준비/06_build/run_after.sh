#!/usr/bin/env bash
# 앞 작업이 끝난 뒤 명령을 실행한다 — 끝난 표시 파일이 생기거나 앞 작업의 단위가 사라지면 시작한다.
#
#   bash 06_build/run_after.sh <끝난 표시 파일> <앞 작업의 단위 이름(없으면 -)> <명령...>
#   예) bash 06_build/launch_job.sh finetune bash 06_build/run_after.sh logs/pipeline/EXTRA_ALL.end ssda-extra-1116091500 bash 06_build/run_pipeline_finetune.sh
#   앞 작업이 완료 표시 없이 끝난 경우에도 뒤 작업을 시작한다(뒤 작업이 스스로 GPU 비움을 확인함).
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
[ $# -ge 3 ] || { echo "사용법: bash 06_build/run_after.sh <끝난 표시 파일> <단위 이름 또는 -> <명령...>"; exit 1; }
FILE="$1"; UNIT="$2"; shift 2
echo "[$(date '+%F %T')] 대기: $FILE 또는 단위 $UNIT 의 종료 → $*" | tee -a logs/pipeline/pipeline.log
sleep 20                                            # 앞 작업의 단위가 뜰 시간을 줌
while [ ! -f "$FILE" ]; do
  if [ "$UNIT" != "-" ] && ! systemctl --user is-active --quiet "$UNIT.scope"; then echo "[$(date '+%F %T')] 앞 작업의 단위가 끝남(완료 표시 없음). 뒤 작업을 시작" | tee -a logs/pipeline/pipeline.log; break; fi
  sleep 60
done
exec "$@"
