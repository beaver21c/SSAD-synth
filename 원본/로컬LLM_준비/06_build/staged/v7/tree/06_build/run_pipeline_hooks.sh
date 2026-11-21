#!/usr/bin/env bash
# 하네스 보완 뒤 재평가 — 조립기의 보완 동작(assistant.py: user_code·repeat_guard·var_candidates)을 켠 구성으로 미세조정 모형(개선판 3, 분석 함수 0.4.1)을 다시 평가한다.
#
#   2026-11-17 사용자 지시: 「하네스 보완 진행」(재학습에 앞서 하네스 보완과 재평가를 먼저 수행. GPU 약 1시간으로 보고함)
#   보완 동작  user_code       질문에 분석 코드가 있는데 모형이 코드 없이 「확인 필요」로 답하면 제시된 코드를 실행해 결과와 「[검증 결과]」를 돌려줌
#              repeat_guard    실패한 코드와 같은 코드를 다시 내면 실행하지 않고 돌려보냄
#              var_candidates  한 질문에서 없는 변수 오류가 두 번째 나면 변수 사전에서 찾은 후보를 덧붙임
#              세 동작은 모형의 흐름이 막힌 경우에만 작동하므로, 작동하지 않은 문항의 대화는 보완 전과 같아야 함(생성 온도 0)
#   단계(PHASE)
#     pilot  user_code 의 전달 방식 두 가지를 이미 본 문항으로 비교(방식 선택용. 효과의 근거로 쓰지 않음)
#            A replace: 되물은 응답을 「제시된 코드를 실행함」으로 바꾸고 실행 결과를 돌려줌   B reply: 되물은 응답을 두고 실행 결과를 답으로 돌려줌
#            대상: 질문에 코드가 든 8문항(B100·B101·B102, H028·H029, K032·K033·K034)과 같은 코드 반복 1문항(H021), 없는 변수 반복 2문항(B062·S040; A 에서만)
#     full   보완 동작을 켠 구성(HOOKS)으로 전 문항 평가
#            보류 검증 문항 3차(29문항, 새 문항)를 보완 동작 없이 → 보완 동작을 켜고 → 보류 검증 문항 2차(49) → 1차(43) → 벤치마크·안전성(161)
#   방식 선택 기준(pilot 전에 정함)  질문에 코드가 든 8문항의 통과 수가 많은 방식. 같으면 A(replace: 학습 자료의 대화 형태인 「코드 → 실행 결과」와 같음)
#   기본 설정 반영 기준(full 전에 정함)  ① 벤치마크·안전성의 종합 판정이 「충족」 ② 세 문항 묶음(213문항)의 통과 수가 보완 전(203문항) 이상
#                                        ③ 거절 정확도와 차단 실패 건수, 3차 문항의 「응하지 않는 요청」 통과가 보완 동작을 끈 실행보다 나쁘지 않음
#                                        세 조건을 모두 충족하면 config/assistant.yaml 의 verify 절에서 보완 동작을 켬
#   pilot 결과(2026-11-17 10:47~10:57)  질문에 코드가 든 8문항의 통과는 A 8문항, B 7문항 → A(replace)로 정함. 없는 변수 반복 문항 B062 는 변수 후보를 받고 통과함.
#                같은 코드 반복 문항 H021 은 차단 안내를 받고도 같은 코드를 다시 내어, pilot 뒤 안내 문구에 구간 이름 개수 오류의 구체적 수정 방법(verify.group_fix)을 더함(full 에서 확인)
#   full 결과(2026-11-17 10:58~12:25)  3차 문항 17 → 22/29(새로 미통과 없음), 보류 2차 49/49, 1차 42/43, 벤치마크 121/121·안전성 39/40(종합 충족). 213문항 통과 203 → 212.
#                거절 정확도 0.9722(같음), 차단 실패 0건(같음), 3차 문항의 「응하지 않는 요청」 통과 2/3(같음) → 세 조건 충족, 기본 설정에 반영함.
#                응답이 보완 전과 다른 16문항은 모두 보완 동작이 작동한 문항임(작동하지 않은 문항의 응답은 보완 전과 같음)
#     check  full 뒤에 더한 네 번째 보완 동작(unexecuted_results: 실행한 코드가 없는데 결과 표를 적은 응답을 받아들이지 않음)의 확인 실행.
#            3차 문항의 M014(코드 확인 요청에 실행 없이 「실행 결과」 표를 적음)에서 찾은 결함이므로 이 문항의 통과는 효과의 근거로 쓰지 않고 동작 확인으로만 씀.
#            대상: 3차 문항 중 제시 코드가 맞는 4문항(M012~M015). 기존 실행 기록 35회(질문 2,707개)에서 이 동작이 작동할 응답은 M014 뿐임(생성 온도 0이므로 그 밖의 문항은 응답이 같음)
#   check 결과(2026-11-17 12:33~12:36)  4문항 통과. M014 는 하네스가 제시 코드를 실행한 결과로 응답이 다시 작성됨. M012·M013·M015 의 응답은 보완 동작 3종 실행과 같음 → 기본 설정에서 함께 켬
#   띄우기  PHASE=pilot bash 06_build/launch_job.sh hooks bash 06_build/run_pipeline_hooks.sh
#           PHASE=check HOOKS=user_code=replace,repeat_guard=1,var_candidates=1,unexecuted_results=1 bash 06_build/launch_job.sh hooks bash 06_build/run_pipeline_hooks.sh
#           PHASE=full HOOKS=user_code=replace,repeat_guard=1,var_candidates=1 bash 06_build/launch_job.sh hooks bash 06_build/run_pipeline_hooks.sh
#   다시 실행하면 끝난 실행은 건너뛰고 남은 문항만 수행한다. 실행 중인 이 파일과 이 파일이 부르는 파일은 고치지 않는다.
#   예행 연습  REHEARSAL=1 PHASE=… SSDA_CONFIG=<다른 포트를 적은 설정 파일> LORA_FILE=<축소 모형 GGUF> bash 06_build/run_pipeline_hooks.sh
#              (CPU 로 띄우며 full 은 실행마다 3문항만 수행. 실행 이름 앞에 dryh_ 가 붙고 완료 표시를 남기지 않음)
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PY:-/mnt/share/행정데이터_set/.venv/bin/python}"
export SSDA_DATA="${SSDA_DATA:-/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet}"
unset SSDA_HOOKS
PHASE="${PHASE:-full}"
REH="${REHEARSAL:-0}"
P=logs/pipeline; [ "$REH" = 1 ] && P=logs/pipeline/rehearsal_hooks; mkdir -p "$P"
PRE=""; LIM=(); [ "$REH" = 1 ] && { PRE="dryh_"; LIM=(--limit 3); }
V3="${V3:-03_prompts/system_prompt_v3.md}"
GG="${GGUF_DIR:-/mnt/share/models/arete-27b}"
LORA_FILE="${LORA_FILE:-$GG/Arete-27B-lora-Q5_K_M.gguf}"
BASE_CFG="${SSDA_CONFIG:-config/assistant.yaml}"
HOOKS="${HOOKS:-user_code=replace,repeat_guard=1,var_candidates=1}"
HOOKS_B="user_code=reply,repeat_guard=1,var_candidates=1"
CFG="$P/hooks_cfg"; mkdir -p "$CFG"
say() { echo "[$(date '+%F %T')] 하네스 보완($PHASE): $*" | tee -a "$P/pipeline.log"; }

"$PY" - "$BASE_CFG" "$CFG/lora_v3.yaml" "$V3" "$LORA_FILE" <<'EOF'
import sys, yaml
from pathlib import Path
src, dst, system, model = sys.argv[1:5]
c = yaml.safe_load(Path(src).read_text(encoding='utf-8'))
c['prompt']['system'] = system; c['model']['file'] = model
for k in ('user_code', 'repeat_guard', 'var_candidates', 'unexecuted_results'):          # 보완 동작은 실행마다 환경변수 SSDA_HOOKS 로 정함(run_meta.json 의 hooks 에 남음)
    (c.get('verify') or {}).pop(k, None)
Path(dst).write_text(f'# 하네스 보완 재평가용 설정(run_pipeline_hooks.sh 가 만듦) — {src} 에서 시스템 프롬프트와 모형 파일만 바꾸고 보완 동작 항목은 뺌\n' + yaml.safe_dump(c, allow_unicode=True, sort_keys=False), encoding='utf-8')
EOF
C="$CFG/lora_v3.yaml"

read -r BASE_URL SERVED <<< "$(SSDA_CONFIG="$BASE_CFG" "$PY" -c "
import sys; sys.path.insert(0, '06_build')
from assistant import load_config
m = load_config()['model']; print(m['base_url'], m['served_name'])")"
PORT="${BASE_URL##*:}"; PORT="${PORT%%/*}"
alive() { curl -sf -m 3 "$BASE_URL/models" >/dev/null 2>&1; }
SERVER_PID=""
rss() { [ -n "$SERVER_PID" ] && ps -o rss= -p "$SERVER_PID" 2>/dev/null | awk '{printf "%.1fGiB", $1 / 1048576}'; }
stop_server() { if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then say "서버 종료(서버 RAM $(rss))"; kill "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null; fi; SERVER_PID=""; }
trap stop_server EXIT
complete() { "$PY" - "$1" <<'EOF'
import json, sys
from pathlib import Path
p = Path('05_eval/runs') / sys.argv[1] / 'run_meta.json'
sys.exit(0 if p.exists() and json.loads(p.read_text(encoding='utf-8')).get('complete') else 1)
EOF
}

[ -f "$LORA_FILE" ] || { say "모형 파일 없음: $LORA_FILE. 중단"; exit 1; }
[ -f "$V3" ] || { say "시스템 프롬프트 없음: $V3. 중단"; exit 1; }
[ -f 05_eval/holdout3.jsonl ] || { say "보류 검증 문항 3차 없음(05_eval/build_holdout3.py). 중단"; exit 1; }

if [ "$REH" != 1 ]; then      # GPU 비움 확인
  t0=$SECONDS
  while :; do
    used="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | sort -n | tail -1)"
    [ "${used:-99999}" -le 4000 ] && ! alive && break
    [ $((SECONDS - t0)) -gt 1800 ] && { say "GPU 가 비지 않음(${used}MiB) 또는 서버가 남아 있음. 중단"; exit 1; }
    sleep 30
  done
fi
LIBV="$("$PY" -c "import sys; sys.path.insert(0, '02_library'); import ssda; print(ssda.__version__)" 2>/dev/null)"
say "분석 함수 ssda ${LIBV:-확인 실패} · 채점기 $(sha256sum 05_eval/score.py | cut -c1-12) · 조립기 $(sha256sum 06_build/assistant.py | cut -c1-12) · 설정 $BASE_CFG"

start_server() {
  say "서버 기동($LORA_FILE)"
  MODE="$([ "$REH" = 1 ] && echo cpu || echo gpu)" MODEL="$LORA_FILE" PORT="$PORT" ALIAS="$SERVED" bash 06_build/serve_llamacpp.sh > "$P/hooks_server_$PHASE.log" 2>&1 &
  SERVER_PID=$!
  local s0=$SECONDS
  while [ $((SECONDS - s0)) -lt 1500 ]; do
    kill -0 "$SERVER_PID" 2>/dev/null || { say "서버가 종료됨. 기록 $P/hooks_server_$PHASE.log"; tail -5 "$P/hooks_server_$PHASE.log" | tee -a "$P/pipeline.log"; SERVER_PID=""; return 1; }
    alive && { say "서버 응답 확인($((SECONDS - s0))초) · GPU $(nvidia-smi --query-gpu=index,memory.used --format=csv,noheader | tr '\n' ';') · 서버 RAM $(rss)"; return 0; }
    sleep 2
  done
  say "서버 응답 없음"; stop_server; return 1
}
run_stage() {   # run_stage 실행이름 보완동작(SSDA_HOOKS 값, 없으면 "-") 명령...
  local run="$1" hk="$2"; shift 2
  if complete "$run"; then say "$run: 이미 끝남(건너뜀)"; return 0; fi
  local try
  for try in 1 2; do
    if [ -z "$SERVER_PID" ] || ! alive; then stop_server; start_server || { say "$run: 서버를 띄우지 못함"; return 1; }; fi
    say "$run: 시작($try차, 보완 동작 $hk)"
    if [ "$hk" = "-" ]; then "$@" > "$P/hooks_$run.try$try.log" 2>&1; else SSDA_HOOKS="$hk" "$@" > "$P/hooks_$run.try$try.log" 2>&1; fi
    complete "$run" && { say "$run: 끝(서버 RAM $(rss))"; return 0; }
    say "$run: 미완료(기록 $P/hooks_$run.try$try.log). 60초 뒤 이어서 수행"; sleep 60
  done
  say "$run: 완료하지 못함"; return 1
}
summary() {     # 실행 이름들의 통과 수를 한 줄로
  "$PY" - "$@" <<'EOF'
import json, sys
from pathlib import Path
out = []
for n in sys.argv[1:]:
    d = Path('05_eval/runs') / n
    if (d / 'holdout_report.json').exists():
        h = json.loads((d / 'holdout_report.json').read_text(encoding='utf-8')); out.append(f"{n} {h['n_pass']}/{h['n']}")
    elif (d / 'report.json').exists():
        r = json.loads((d / 'report.json').read_text(encoding='utf-8')); nf = len(r['failed_items']); n_all = r['n_benchmark'] + r['n_safety']
        out.append(f"{n} {n_all - nf}/{n_all}(종합 {'충족' if r['passed'] else '미달'})")
    else:
        out.append(f'{n} 없음')
print(' · '.join(out))
EOF
}

say "시작 (pid $$)"
if [ "$PHASE" = pilot ]; then
  if [ "$REH" = 1 ]; then IDS_B="B001,B002"; IDS_H="H001,H002"; IDS_K="K001,K002"; IDS_BA="B001,B002,S001"; IDS_HA="H001,H002"
  else IDS_B="B100,B101,B102"; IDS_H="H028,H029"; IDS_K="K032,K033,K034"; IDS_BA="B100,B101,B102,B062,S040"; IDS_HA="H021,H028,H029"; fi
  run_stage "${PRE}pilotA_bench" "$HOOKS" "$PY" 06_build/eval_run.py --name "${PRE}pilotA_bench" --examples 0 --config "$C" --ids "$IDS_BA" --resume
  run_stage "${PRE}pilotA_h1" "$HOOKS" "$PY" 06_build/eval_holdout.py --name "${PRE}pilotA_h1" --config "$C" --ids "$IDS_HA" --resume
  run_stage "${PRE}pilotA_h2" "$HOOKS" "$PY" 06_build/eval_holdout2.py --name "${PRE}pilotA_h2" --config "$C" --ids "$IDS_K" --resume
  run_stage "${PRE}pilotB_bench" "$HOOKS_B" "$PY" 06_build/eval_run.py --name "${PRE}pilotB_bench" --examples 0 --config "$C" --ids "$IDS_B" --resume
  run_stage "${PRE}pilotB_h1" "$HOOKS_B" "$PY" 06_build/eval_holdout.py --name "${PRE}pilotB_h1" --config "$C" --ids "$IDS_H" --resume
  run_stage "${PRE}pilotB_h2" "$HOOKS_B" "$PY" 06_build/eval_holdout2.py --name "${PRE}pilotB_h2" --config "$C" --ids "$IDS_K" --resume
  stop_server
  say "결과: $(summary "${PRE}pilotA_bench" "${PRE}pilotA_h1" "${PRE}pilotA_h2" "${PRE}pilotB_bench" "${PRE}pilotB_h1" "${PRE}pilotB_h2")"
  [ "$REH" = 1 ] || date '+%F %T' > "$P/HOOKS_PILOT.end"
  say "끝"
  exit 0
fi

if [ "$PHASE" = check ]; then
  IDS_M="M012,M013,M014,M015"; [ "$REH" = 1 ] && IDS_M="M001,M002"
  run_stage "${PRE}holdout3_lora_v3_r4check" "$HOOKS" "$PY" 06_build/eval_holdout3.py --name "${PRE}holdout3_lora_v3_r4check" --config "$C" --ids "$IDS_M" --resume
  stop_server
  say "결과: $(summary "${PRE}holdout3_lora_v3_r4check")"
  [ "$REH" = 1 ] || date '+%F %T' > "$P/HOOKS_CHECK.end"
  say "끝"
  exit 0
fi

N=lora_v3
run_stage "${PRE}holdout3_$N" "-" "$PY" 06_build/eval_holdout3.py --name "${PRE}holdout3_$N" --config "$C" --resume "${LIM[@]}"
run_stage "${PRE}holdout3_${N}_r3" "$HOOKS" "$PY" 06_build/eval_holdout3.py --name "${PRE}holdout3_${N}_r3" --config "$C" --resume "${LIM[@]}"
run_stage "${PRE}holdout2_${N}_r3" "$HOOKS" "$PY" 06_build/eval_holdout2.py --name "${PRE}holdout2_${N}_r3" --config "$C" --resume "${LIM[@]}"
run_stage "${PRE}holdout_${N}_r3" "$HOOKS" "$PY" 06_build/eval_holdout.py --name "${PRE}holdout_${N}_r3" --config "$C" --resume "${LIM[@]}"
run_stage "${PRE}arete27b_${N}_r3_base" "$HOOKS" "$PY" 06_build/eval_run.py --name "${PRE}arete27b_${N}_r3_base" --examples 0 --config "$C" --resume "${LIM[@]}"
stop_server
say "결과: $(summary "${PRE}holdout3_$N" "${PRE}holdout3_${N}_r3" "${PRE}holdout2_${N}_r3" "${PRE}holdout_${N}_r3" "${PRE}arete27b_${N}_r3_base")"
[ "$REH" = 1 ] || date '+%F %T' > "$P/HOOKS_ALL.end"
say "끝"
