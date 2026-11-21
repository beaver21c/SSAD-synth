#!/usr/bin/env bash
# 보완본 반영 — 06_build/staged/v3 의 분석 함수(ssda 0.4.1)와 채점기를 현행 위치에 넣고 점검한다. 점검에 실패하면 되돌린다.
#
#   bash 06_build/staged/v3/apply.sh            반영(이미 반영돼 있으면 아무것도 하지 않음)
#   bash 06_build/staged/v3/apply.sh --restore  가장 최근 사본으로 되돌림
#   · 실행 중인 평가가 있으면 반영하지 않는다(평가 간 비교 가능성. FORCE=1 로 무시)
#   · 현행 파일이 보완본을 만들 때의 기준(BASE.sha256)과 다르면 반영하지 않는다(그 사이의 수정을 덮어쓰지 않기 위함)
#   · 점검: ① 정답 코드 전체(벤치마크·안전성·보류 검증 문항 1·2차)의 실행·집계 결과·경고가 반영 전(reg_live.json)과 같고 안내·경고 시험이 기대와 같음
#           ② 모의 모형(정답 응답)으로 벤치마크·안전성 161문항과 보류 검증 문항 1·2차를 채점해 모두 통과
#   · 바뀌는 파일: 02_library/ssda/{core.py, verify.py, __init__.py}, 05_eval/score.py  (사본: 06_build/staged/v3/backup_<시각>/)
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
ST=06_build/staged/v3
PY="${PY:-/mnt/share/행정데이터_set/.venv/bin/python}"
export SSDA_DATA="${SSDA_DATA:-/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet}"
FILES=(02_library/ssda/core.py 02_library/ssda/verify.py 02_library/ssda/__init__.py 05_eval/score.py)
SRC=("$ST/lib/ssda/core.py" "$ST/lib/ssda/verify.py" "$ST/lib/ssda/__init__.py" "$ST/score.py")
say() { echo "[$(date '+%F %T')] 반영: $*"; }
restore() {   # restore 사본폴더
  local i; for i in "${!FILES[@]}"; do cp -p "$1/$(basename "${FILES[$i]}")" "${FILES[$i]}"; done
  find 02_library 05_eval -maxdepth 2 -name __pycache__ -prune -exec rm -r {} + 2>/dev/null
}
if [ "${1:-}" = "--restore" ]; then
  B="$(ls -d "$ST"/backup_* 2>/dev/null | sort | tail -1)"; [ -n "$B" ] || { say "사본이 없음"; exit 1; }
  restore "$B"; say "되돌림: $B"; exit 0
fi
same=1; for i in "${!FILES[@]}"; do cmp -s "${SRC[$i]}" "${FILES[$i]}" || same=0; done
[ $same = 1 ] && { say "이미 반영돼 있음"; exit 0; }
if [ "${FORCE:-0}" != 1 ] && pgrep -f '[e]val_run.py|[e]val_holdout|[l]lama-server|[r]un_gpu_day' >/dev/null; then say "실행 중인 평가·서버가 있어 반영하지 않음"; exit 3; fi
sha256sum --quiet -c "$ST/BASE.sha256" >/dev/null 2>&1 || { say "현행 파일이 기준(BASE.sha256)과 다름. 반영하지 않음"; sha256sum -c "$ST/BASE.sha256" 2>&1 | grep -v ': OK' | head -5; exit 4; }
B="$ST/backup_$(date +%m%d%H%M%S)"; mkdir -p "$B"
for f in "${FILES[@]}"; do cp -p "$f" "$B/"; done
for i in "${!FILES[@]}"; do cp "${SRC[$i]}" "${FILES[$i]}"; done
find 02_library 05_eval -maxdepth 2 -name __pycache__ -prune -exec rm -r {} + 2>/dev/null
say "파일 4개 반영(사본 $B). 점검 시작"
fail() { say "점검 실패: $*. 되돌림"; restore "$B"; exit 5; }
T="$(mktemp -d)"
"$PY" -B "$ST/regress.py" run 02_library "$T/after.json" > "$T/run.log" 2>&1 || { tail -3 "$T/run.log"; fail "회귀 점검을 실행하지 못함"; }
"$PY" -B "$ST/regress.py" diff "$ST/reg_live.json" "$T/after.json" > "$T/diff.log" 2>&1 || { tail -8 "$T/diff.log"; fail "정답 코드의 산출 또는 안내·경고 시험이 기대와 다름"; }
tail -1 "$T/diff.log"
"$PY" -B 06_build/eval_run.py --name v3_check_oracle --mock oracle --inprocess > "$T/o1.log" 2>&1
"$PY" -B 06_build/eval_holdout.py --name v3_check_oracle_h1 --mock oracle --inprocess > "$T/o2.log" 2>&1
"$PY" -B 06_build/eval_holdout2.py --name v3_check_oracle_h2 --mock oracle --inprocess > "$T/o3.log" 2>&1
"$PY" - <<'PYEOF' || fail "모의 모형(정답 응답) 채점이 만점이 아님"
import json, sys
from pathlib import Path
R = Path('05_eval/runs'); ok = True
r = json.loads((R / 'v3_check_oracle' / 'report.json').read_text(encoding='utf-8')); m = r['metrics']
print(f"  모의 모형 벤치마크: 문항 통과율 {m['문항 통과율']}, 거절 정확도 {m['거절 정확도']}, 정상 수행률 {m['정상 수행률(지시문 혼입)']}, 미통과 {r['failed_items']}")
ok &= m['문항 통과율'] == 1.0 and m['거절 정확도'] == 1.0 and m['정상 수행률(지시문 혼입)'] == 1.0 and r['n_benchmark'] + r['n_safety'] == 161
for n in ('v3_check_oracle_h1', 'v3_check_oracle_h2'):
    h = json.loads((R / n / 'holdout_report.json').read_text(encoding='utf-8')); print(f"  모의 모형 {n}: {h['n_pass']}/{h['n']}"); ok &= h['n_pass'] == h['n'] and h['n'] >= 43
sys.exit(0 if ok else 1)
PYEOF
rm -rf "$T"
say "점검 통과. ssda $("$PY" -c "import sys; sys.path.insert(0, '02_library'); import ssda; print(ssda.__version__)") 과 보완한 채점기가 현행으로 반영됨"
