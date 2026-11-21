#!/usr/bin/env bash
# 독립 검증 4차 뒤의 조치(규칙 묶음 9)를 준비 폴더에 반영한다. 규칙 묶음은 설정 verify.ruleset(기본 8)으로 켜므로 반영만으로는 기본 구성의 동작이 바뀌지 않는다.
#   bash 06_build/staged/v9/apply.sh             사본(06_build/staged/v9/tree)의 바뀐 파일을 원본에 복사하고 자체 시험을 돌린다
#   bash 06_build/staged/v9/apply.sh --restore D 백업 폴더 D 의 파일로 되돌린다
# 평가 실행(GPU)이 도는 동안에는 반영하지 않는다(평가 대상 파일을 실행 중에 바꾸지 않음).
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
PY="${PY:-/mnt/share/행정데이터_set/.venv/bin/python}"
export SSDA_DATA="${SSDA_DATA:-/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet}"
T=06_build/staged/v9/tree
FILES=(02_library/ssda/verify.py 02_library/ssda/data/relations.json 06_build/assistant.py 06_build/terms.py 06_build/eval_indep.py 06_build/v9_probe.py
       01_knowledge/build_relations.py 01_knowledge/relations.json)
if pgrep -f 'eval_indep.py|review_probe.py|eval_run.py|eval_holdout.py' >/dev/null; then
  echo "평가 실행이 도는 중이므로 반영하지 않음"; exit 1
fi
if [ "${1:-}" = "--restore" ]; then
  B="${2:?백업 폴더 필요}"
  for f in "${FILES[@]}"; do [ -f "$B/$f" ] && cp -p "$B/$f" "$f" && echo "되돌림 $f"; done
else
  B="06_build/staged/v9/backup_$(date +%m%d%H%M%S)"
  for f in "${FILES[@]}"; do
    [ -f "$f" ] && { mkdir -p "$B/$(dirname "$f")"; cp -p "$f" "$B/$f"; }
    cmp -s "$T/$f" "$f" 2>/dev/null || { mkdir -p "$(dirname "$f")"; cp -p "$T/$f" "$f"; echo "반영 $f"; }
  done
  echo "백업: $B"
fi
echo "── 자체 시험(규칙 묶음 8 = 기존 동작)"
unset SSDA_RULESET
"$PY" 06_build/hook_probe.py | tail -1
"$PY" 06_build/usage_probe.py | tail -1
PYTHONPATH=02_library "$PY" 06_build/verify_probe.py | tail -1
"$PY" 06_build/diff_probe.py | tail -1
echo "── 자체 시험(규칙 묶음 9)"
"$PY" 06_build/v9_probe.py | tail -8
