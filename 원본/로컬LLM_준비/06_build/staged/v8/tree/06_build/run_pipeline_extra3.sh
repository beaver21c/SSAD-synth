#!/usr/bin/env bash
# 95% 미달 시 대책 실행 — 추가 확인 실행이 끝난 뒤 벤치마크 문항 통과율이 목표(기본 95%)에 이른 구성이 없으면 보완본을 반영해 다시 평가한다.
#
#   2026-11-16 사용자 지시: 「추가 확인 실행 후 95% 이상 성공률이 안 나올 경우 대책을 세워 자동 진행(보고 후)」. 대책의 내용과 근거는 06_build/staged/v3 와 docs 설명자료에 적음.
#   대책(1차)  ① 분석 함수 보완(ssda 0.4.1): 대상이 분자와 같은 집단일 때의 검증 경고, by 에 조건식·hnum 을 쓴 경우와 범위 밖 순번·문자열 값의 오류 안내, 조건식의 시도 값 해석,
#                 define_group() 의 반환값을 by 에 넣은 경우의 해석, define_group() 의 인자 누락·조건식·여부 변수 안내, 여부 변수의 「!= 1」 비교 경고
#              ② 채점 보완: 정답과 산출 횟수가 달라도 값·인원 구성이 같으면 일치로 봄(기존 실행도 같은 채점기로 다시 채점해 비교)
#              ③ 시스템 프롬프트 개선판 3(03_prompts/system_prompt_v3.md)
#   순서  ① 추가 확인 실행 종료 대기: logs/pipeline/EXTRA2_ALL.end 가 생기거나 logs/pipeline/last_unit_extra2 의 단위가 10분 넘게 떠 있지 않을 때까지.
#            logs/pipeline/EXTRA3.hold 파일이 있으면 계속 기다린다
#         ② 판정(06_build/staged/v3/judge.py): 끝난 실행 가운데 통과율이 가장 높은 구성을 고름. 목표에 이르렀으면 EXTRA3.skip 을 남기고 끝냄
#         ③ 보완본 반영과 점검(06_build/staged/v3/apply.sh: 정답 코드 회귀 점검, 모의 모형 채점). 실패하면 되돌리고 끝냄. 기존 실행은 보완한 채점기로 다시 채점(원래 보고서는 report.scorer_v1.* 로 보존)
#         ④ 구성 3개를 차례로 평가하고 벤치마크가 끝날 때마다 다시 판정함. 목표에 이르면 남은 구성은 수행하지 않음(ALL=1 이면 모두 수행)
#            구성 1: 통과율이 가장 높았던 모형 + 개선판 3 — 보류 검증 문항 2차(49문항, 어느 모형에도 넣어 본 적 없는 문항) → 1차(43문항) → 벤치마크·안전성 161문항
#            구성 2: 미세조정 모형 + 짧은 프롬프트(보완한 분석 함수) — 보류 검증 문항 2차 → 벤치마크·안전성
#            구성 3: 다른 계열의 모형 + 개선판 3 — 보류 검증 문항 2차 → 벤치마크·안전성
#         ⑤ 판정 결과는 logs/pipeline/EXTRA3_result.json 에 남김(구성이 끝날 때마다 갱신)
#   띄우기  bash 06_build/launch_job.sh extra3 bash 06_build/run_pipeline_extra3.sh
#   환경변수  TARGET=0.95  FORCE_TAG=q5|q4|lora(판정과 무관하게 그 모형을 구성 1로 실행)  SKIP_APPLY=1(이미 반영한 경우)  ALL=1(목표에 이르러도 구성 3개를 모두 수행)
#   다시 실행하면 끝난 실행은 건너뛰고 남은 문항만 수행한다. 실행 중인 이 파일은 고치지 않는다.
#   예행 연습  REHEARSAL=1 SSDA_CONFIG=<다른 포트를 적은 설정 파일> FORCE_TAG=q5 Q5_FILE=<축소 모형 GGUF> bash 06_build/run_pipeline_extra3.sh
#              (대기·반영을 건너뛰고 CPU 로 띄우며 실행마다 3문항만 수행. 실행 이름 앞에 dryz_ 가 붙고 완료 표시를 남기지 않음)
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PY:-/mnt/share/행정데이터_set/.venv/bin/python}"
export SSDA_DATA="${SSDA_DATA:-/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet}"
REH="${REHEARSAL:-0}"
P=logs/pipeline; [ "$REH" = 1 ] && P=logs/pipeline/rehearsal_extra3; mkdir -p "$P"
PRE=""; LIM=(); [ "$REH" = 1 ] && { PRE="dryz_"; LIM=(--limit 3); }
ST=06_build/staged/v3
TARGET="${TARGET:-0.95}"
V3="${V3:-03_prompts/system_prompt_v3.md}"
SHORT="${SHORT:-03_prompts/system_prompt_short.md}"
GG="${GGUF_DIR:-/mnt/share/models/arete-27b}"
Q5_FILE="${Q5_FILE:-$GG/Arete-27B-Q5_K_M.gguf}"
Q4_FILE="${Q4_FILE:-$GG/Arete-27B-Q4_K_M.gguf}"
LORA_FILE="${LORA_FILE:-$GG/Arete-27B-lora-Q5_K_M.gguf}"
BASE_CFG="${SSDA_CONFIG:-config/assistant.yaml}"
CFG="$P/extra3_cfg"; mkdir -p "$CFG"
say() { echo "[$(date '+%F %T')] 추가3: $*" | tee -a "$P/pipeline.log"; }

mkcfg() {   # mkcfg 이름 시스템프롬프트 모형파일 — 기본 설정에서 시스템 프롬프트와 모형 파일만 바꿈(run_meta.json 에 실제 구성이 남음)
  "$PY" - "$BASE_CFG" "$CFG/$1.yaml" "$2" "$3" <<'EOF'
import sys, yaml
from pathlib import Path
src, dst, system, model = sys.argv[1:5]
c = yaml.safe_load(Path(src).read_text(encoding='utf-8'))
c['prompt']['system'] = system; c['model']['file'] = model
Path(dst).write_text(f'# 대책 실행용 설정(run_pipeline_extra3.sh 가 만듦) — {src} 에서 시스템 프롬프트와 모형 파일만 바꿈\n' + yaml.safe_dump(c, allow_unicode=True, sort_keys=False), encoding='utf-8')
EOF
}

read -r BASE_URL SERVED <<< "$(SSDA_CONFIG="$BASE_CFG" "$PY" -c "
import sys; sys.path.insert(0, '06_build')
from assistant import load_config
m = load_config()['model']; print(m['base_url'], m['served_name'])")"
PORT="${BASE_URL##*:}"; PORT="${PORT%%/*}"
alive() { curl -sf -m 3 "$BASE_URL/models" >/dev/null 2>&1; }
SERVER_PID=""
stop_server() { if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then kill "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null; say "서버 종료"; fi; SERVER_PID=""; }
trap stop_server EXIT

complete() { "$PY" - "$1" <<'EOF'
import json, sys
from pathlib import Path
p = Path('05_eval/runs') / sys.argv[1] / 'run_meta.json'
sys.exit(0 if p.exists() and json.loads(p.read_text(encoding='utf-8')).get('complete') else 1)
EOF
}
field() { "$PY" -c "import json, sys; v = json.load(open(sys.argv[1], encoding='utf-8')).get(sys.argv[2]); print('' if v is None else v)" "$1" "$2"; }

# ① 추가 확인 실행 종료 대기와 GPU 비움 확인
if [ "$REH" != 1 ]; then
  say "추가 확인 실행이 끝나기를 기다림($P/EXTRA2_ALL.end 또는 $P/last_unit_extra2 의 단위가 10분 넘게 없음)"
  idle=0
  while :; do
    if [ -f "$P/EXTRA3.hold" ]; then idle=0; sleep 60; continue; fi
    [ -f "$P/EXTRA2_ALL.end" ] && break
    u="$(cat "$P/last_unit_extra2" 2>/dev/null || true)"
    if [ -n "$u" ] && systemctl --user is-active --quiet "$u.scope"; then idle=0; else idle=$((idle + 1)); fi
    [ "$idle" -ge 10 ] && { say "추가 확인 실행 단위가 10분 넘게 없음(완료 표시 없음). 계속 진행"; break; }
    sleep 60
  done
  t0=$SECONDS
  while :; do
    used="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | sort -n | tail -1)"
    [ "${used:-99999}" -le 4000 ] && ! alive && break
    [ $((SECONDS - t0)) -gt 3600 ] && { say "GPU 가 비지 않음(${used}MiB) 또는 서버가 남아 있음. 중단"; exit 1; }
    sleep 30
  done
fi

# ② 판정
J="$P/EXTRA3_judge.json"
"$PY" -B "$ST/judge.py" --target "$TARGET" --out "$J" > /dev/null 2> "$P/extra3_judge.err" || { say "판정 실패(기록 $P/extra3_judge.err)"; exit 1; }
DEC="$(field "$J" decision)"; BEST="$(field "$J" best)"; TAG="$(field "$J" tag)"; BPROMPT="$(field "$J" prompt)"; RATE="$(field "$J" rate)"; NEED="$(field "$J" need)"
[ -n "${FORCE_TAG:-}" ] && { DEC=run; TAG="$FORCE_TAG"; }
[ -n "${FORCE_PROMPT:-}" ] && BPROMPT="$FORCE_PROMPT"       # 예행 연습용: 가장 높았던 구성의 시스템 프롬프트를 지정
say "판정: 가장 높은 구성 ${BEST:-없음}(통과율 ${RATE:-—}, 목표 $TARGET, 모자란 문항 ${NEED:-—}) → $([ "$DEC" = run ] && echo "대책 실행(모형 $TAG)" || echo "$DEC")"
if [ "$DEC" = skip ]; then date '+%F %T' > "$P/EXTRA3.skip"; say "목표에 이르렀으므로 대책을 실행하지 않음"; exit 0; fi
[ "$DEC" = run ] || { say "판정할 수 있는 끝난 실행이 없음. 중단"; exit 1; }
case "$TAG" in q4) MODEL_FILE="$Q4_FILE" ;; lora) MODEL_FILE="$LORA_FILE" ;; *) TAG=q5; MODEL_FILE="$Q5_FILE" ;; esac
[ -f "$MODEL_FILE" ] || { say "모형 파일 없음: $MODEL_FILE. 중단"; exit 1; }

# ③ 보완본 반영과 점검, 기존 실행의 재채점
if [ "$REH" != 1 ] && [ "${SKIP_APPLY:-0}" != 1 ]; then
  bash "$ST/apply.sh" > "$P/extra3_apply.log" 2>&1; rc=$?
  tail -4 "$P/extra3_apply.log" | tee -a "$P/pipeline.log"
  [ $rc -eq 0 ] || { echo "보완본 반영 실패($rc)" > "$P/EXTRA3.failed"; say "보완본 반영 실패(종료 코드 $rc). 중단"; exit 2; }
  "$PY" -B - > "$P/extra3_rescore.log" 2>&1 <<'EOF'
import json, shutil, sys
from pathlib import Path
sys.path.insert(0, '05_eval')
import score
for d in sorted(Path('05_eval/runs').glob('arete27b_*')):
    m = json.loads((d / 'run_meta.json').read_text(encoding='utf-8')) if (d / 'run_meta.json').exists() else {}
    if not (m.get('complete') and (d / 'report.json').exists() and m.get('items', 0) >= 161):
        continue
    old = json.loads((d / 'report.json').read_text(encoding='utf-8'))
    if not (d / 'report.scorer_v1.json').exists():          # 원래 보고서 보존
        shutil.copy2(d / 'report.json', d / 'report.scorer_v1.json'); shutil.copy2(d / 'report.md', d / 'report.scorer_v1.md')
    new = score.score_run(d)
    print(f"{d.name}: 문항 통과율 {old['metrics']['문항 통과율']} → {new['metrics']['문항 통과율']}, 바뀐 문항 {sorted(set(old['failed_items']) ^ set(new['failed_items']))}")
EOF
  say "기존 실행 재채점: $(tr '\n' ';' < "$P/extra3_rescore.log" | cut -c1-600)"
fi

start_server() {   # start_server 모형파일 기록이름
  say "서버 기동($1)"
  MODE="$([ "$REH" = 1 ] && echo cpu || echo gpu)" MODEL="$1" PORT="$PORT" ALIAS="$SERVED" bash 06_build/serve_llamacpp.sh > "$P/extra3_server_$2.log" 2>&1 &
  SERVER_PID=$!
  local s0=$SECONDS
  while [ $((SECONDS - s0)) -lt 1500 ]; do
    kill -0 "$SERVER_PID" 2>/dev/null || { say "서버가 종료됨. 기록 $P/extra3_server_$2.log"; tail -5 "$P/extra3_server_$2.log" | tee -a "$P/pipeline.log"; SERVER_PID=""; return 1; }
    alive && { say "서버 응답 확인($((SECONDS - s0))초) · GPU $(nvidia-smi --query-gpu=index,memory.used --format=csv,noheader | tr '\n' ';')"; return 0; }
    sleep 2
  done
  say "서버 응답 없음"; stop_server; return 1
}
run_stage() {   # run_stage 실행이름 명령...
  local run="$1"; shift
  if complete "$run"; then say "$run: 이미 끝남(건너뜀)"; return 0; fi
  local try
  for try in 1 2; do
    if [ -z "$SERVER_PID" ] || ! alive; then stop_server; start_server "$MODEL_FILE" "$TAG" || { say "$run: 서버를 띄우지 못함"; return 1; }; fi
    say "$run: 시작($try차)"
    "$@" > "$P/extra3_$run.try$try.log" 2>&1
    complete "$run" && { say "$run: 끝"; return 0; }
    say "$run: 미완료(기록 $P/extra3_$run.try$try.log). 60초 뒤 이어서 수행"; sleep 60
  done
  say "$run: 완료하지 못함"; return 1
}

# ④ 평가 — 구성을 차례로 수행하고, 벤치마크가 끝날 때마다 다시 판정해 목표에 이르면 남은 구성은 수행하지 않음(ALL=1 이면 모두 수행)
#    구성 1  통과율이 가장 높았던 모형 + 개선판 3            : 보류 검증 문항 2차 → 1차 → 벤치마크·안전성
#    구성 2  미세조정 모형 + 짧은 프롬프트(보완한 분석 함수)  : 보류 검증 문항 2차 → 벤치마크·안전성
#    구성 3  다른 계열의 모형 + 개선판 3                     : 보류 검증 문항 2차 → 벤치마크·안전성  (구성 1이 미세조정 모형이면 공식 가중치 Q5_K_M, 아니면 미세조정 모형)
#    2026-11-16 보완: 미세조정 모형(짧은 프롬프트)의 통과율이 공식 가중치(개선판 2)와 같고 미통과 문항은 3개만 겹쳐, 한 계열만 다시 평가하던 것을 두 계열 모두로 넓힘
RUNS="arete27b_q5_v2_base,arete27b_q4_v2_base,arete27b_lora_short_base,arete27b_lora_long_base,arete27b_lora_v2_base"
REACHED=0
use_model() {   # use_model 계열(q5|q4|lora) — 다른 모형이 떠 있으면 내리고 바꿈. 모형 파일이 없으면 실패
  local f; case "$1" in q4) f="$Q4_FILE" ;; lora) f="$LORA_FILE" ;; *) f="$Q5_FILE" ;; esac
  [ -f "$f" ] || { say "모형 파일 없음: $f (이 구성은 건너뜀)"; return 1; }
  if [ "$f" != "$MODEL_FILE" ] || [ "$1" != "$TAG" ]; then stop_server; sleep 5; fi
  MODEL_FILE="$f"; TAG="$1"; return 0
}
rejudge() {     # 지금까지의 실행으로 다시 판정
  "$PY" -B "$ST/judge.py" --target "$TARGET" --runs "$RUNS" --out "$P/EXTRA3_result.json" > /dev/null 2>> "$P/extra3_judge.err"
  say "판정(누적): 가장 높은 구성 $(field "$P/EXTRA3_result.json" best)(통과율 $(field "$P/EXTRA3_result.json" rate), 목표 $TARGET)"
  [ "$(field "$P/EXTRA3_result.json" decision)" = skip ] && REACHED=1
  return 0
}
eval_cfg() {    # eval_cfg 계열 구성이름 시스템프롬프트 보류1차(1|0)
  local tag="$1" name="$2" prompt="$3" h1="$4"
  if [ "$REACHED" = 1 ] && [ "${ALL:-0}" != 1 ]; then say "$name: 목표에 이르렀으므로 수행하지 않음"; return 0; fi
  use_model "$tag" || return 0
  say "구성 $name: 모형 $MODEL_FILE, 시스템 프롬프트 $prompt"
  mkcfg "$name" "$prompt" "$MODEL_FILE"
  run_stage "${PRE}holdout2_$name" "$PY" 06_build/eval_holdout2.py --name "${PRE}holdout2_$name" --config "$CFG/$name.yaml" --resume "${LIM[@]}"
  [ "$h1" = 1 ] && run_stage "${PRE}holdout_$name" "$PY" 06_build/eval_holdout.py --name "${PRE}holdout_$name" --config "$CFG/$name.yaml" --resume "${LIM[@]}"
  run_stage "${PRE}arete27b_${name}_base" "$PY" 06_build/eval_run.py --name "${PRE}arete27b_${name}_base" --examples 0 --config "$CFG/$name.yaml" --resume "${LIM[@]}"
  RUNS="$RUNS,${PRE}arete27b_${name}_base"
  rejudge
}
say "대책 실행 시작 (pid $$) — 통과율이 가장 높았던 모형 계열 $TAG"
FIRST="$TAG"; OTHER="$([ "$FIRST" = lora ] && echo q5 || echo lora)"
eval_cfg "$FIRST" "${FIRST}_v3" "$V3" 1
eval_cfg lora lora_short2 "$SHORT" 0
eval_cfg "$OTHER" "${OTHER}_v3" "$V3" 0
stop_server

# ⑤ 마지막 판정
rejudge
say "대책 실행 뒤 판정: 가장 높은 구성 $(field "$P/EXTRA3_result.json" best)(통과율 $(field "$P/EXTRA3_result.json" rate), 목표 $TARGET) → $([ "$REACHED" = 1 ] && echo "목표 도달" || echo "목표 미달")"
[ "$REH" = 1 ] || date '+%F %T' > "$P/EXTRA3_ALL.end"
say "대책 실행 끝"
