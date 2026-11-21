#!/usr/bin/env bash
# 독립 검증 3차 뒤의 조치를 준비 폴더에 반영한다.
#   bash 06_build/staged/v8/apply.sh             사본(06_build/staged/v8/tree)의 바뀐 파일을 원본에 복사하고 지식 카드·검색 색인을 다시 만든 뒤 자체 시험을 돌린다
#   bash 06_build/staged/v8/apply.sh --restore D 백업 폴더 D 의 파일로 되돌린다
# 평가 실행(GPU)이 도는 동안에는 반영하지 않는다(평가 대상 파일을 실행 중에 바꾸지 않음).
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
PY="${PY:-/mnt/share/행정데이터_set/.venv/bin/python}"
export SSDA_DATA="${SSDA_DATA:-/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet}"
T=06_build/staged/v8/tree
FILES=(02_library/ssda/__init__.py 02_library/ssda/core.py 02_library/ssda/runner.py 02_library/ssda/verify.py
       06_build/assistant.py 06_build/terms.py 06_build/hook_probe.py 06_build/eval_indep.py 06_build/diff_probe.py
       03_prompts/system_prompt_v5.md 01_knowledge/docs/api_reference.md 01_knowledge/docs/analysis_recipes.md)
if systemctl --user list-units --type=scope --state=running --no-legend 2>/dev/null | grep -E 'ssda-(round|eval|indep|dev)' | grep -Evq 'devsrv|guard' \
   || pgrep -f 'eval_indep.py|review_probe.py|eval_run.py|eval_holdout.py' >/dev/null; then
  echo "평가 실행이 도는 중이므로 반영하지 않음"; exit 1        # 추론 서버만 떠 있는 경우(개발 서버)는 이 파일들을 읽지 않으므로 반영함
fi
if [ "${1:-}" = "--restore" ]; then
  B="${2:?백업 폴더 필요}"
  for f in "${FILES[@]}"; do [ -f "$B/$f" ] && cp -p "$B/$f" "$f" && echo "되돌림 $f"; done
  [ -f "$B/03_prompts/system_prompt_v5.md" ] || rm -f "/mnt/share/행정데이터_set/로컬LLM_준비/03_prompts/system_prompt_v5.md"
else
  B="06_build/staged/v8/backup_$(date +%m%d%H%M%S)"
  for f in "${FILES[@]}"; do
    [ -f "$f" ] && { mkdir -p "$B/$(dirname "$f")"; cp -p "$f" "$B/$f"; }
    cmp -s "$T/$f" "$f" 2>/dev/null || { cp -p "$T/$f" "$f"; echo "반영 $f"; }
  done
  echo "백업: $B"
fi
"$PY" 01_knowledge/build_knowledge.py | tail -1
"$PY" 06_build/retriever.py build | tail -2
echo "── 자체 시험"
"$PY" 06_build/hook_probe.py | tail -1
"$PY" 06_build/usage_probe.py | tail -1
PYTHONPATH=02_library "$PY" 06_build/verify_probe.py | tail -1
"$PY" 06_build/diff_probe.py | tail -1
"$PY" -c "import sys; sys.path.insert(0, '02_library'); import ssda; print('분석 함수', ssda.__version__)"
