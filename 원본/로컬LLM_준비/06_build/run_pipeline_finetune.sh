#!/usr/bin/env bash
# 미세조정 단계 연속 실행 — 스모크 시험 → 본 학습 → 어댑터 병합 → GGUF 변환·양자화 → 미세조정 모형 평가를 사람 없이 이어서 수행한다.
#
#   2026-11-15 사용자 지시(범위 E까지 전체 수행)에 따라 작성. GPU 2장을 모두 쓴다(병합·변환은 CPU).
#   평가 단계(run_pipeline_eval.sh)가 끝난 표시(logs/pipeline/EVAL_ALL.end)를 기다렸다가 시작한다. WAIT_EVAL=0 을 주면 기다리지 않는다.
#   단계마다 끝난 표시(logs/pipeline/<단계>.done)를 남기며, 다시 실행하면 끝난 단계는 건너뛴다. 학습은 체크포인트에서, 평가는 남은 문항에서 이어진다.
#   띄우는 법(세션과 분리 + 메모리 압력 감시):  bash 06_build/launch_job.sh finetune bash 06_build/run_pipeline_finetune.sh
#   진행 상황  logs/pipeline/pipeline.log, 단계별 기록 logs/pipeline/<단계>*.log
#   실행 중인 이 파일은 고치지 않는다.
#
#   단계  F1 스모크 시험: 가장 긴 예시 8건으로 적재·역전파를 확인. GPU 메모리가 부족하면 분할 위치(--split-at)를 옮기고, 그래도 안 되면 길이 상한을 낮춰 다시 시도
#         F2 본 학습: F1 에서 통과한 설정으로 3에폭. 중단되면 체크포인트에서 이어서(최대 4회)
#         F3 병합: 어댑터를 공식 가중치에 합침(merge_lora.py, CPU)
#         F4 변환·양자화: 합친 모형 → GGUF Q5_K_M (make_gguf.sh, CPU)
#         F5 평가(짧은 시스템 프롬프트: 학습 자료와 같은 문구)   F6 평가(긴 시스템 프롬프트: 미세조정 전 평가와 같은 조건)
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT="$PWD"
VENV_PY="/mnt/share/행정데이터_set/.venv/bin/python"
CONDA_PY="$HOME/anaconda3/envs/vllm/bin/python"
P=logs/pipeline; mkdir -p "$P"
GG="${GGUF_DIR:-/mnt/share/models/arete-27b}"
ADAPTER="$ROOT/06_build/runs/lora_assistant_v1"
MERGED="$GG/merged-lora-v1"
BASE_SNAP="$(ls -d /mnt/share/hf_cache/hub/models--NousResearch--Arete-27B/snapshots/*/ | head -1)"
FT_EXTRA=(); QUANT=Q5_K_M; OUTNAME=Arete-27B-lora
if [ "${REHEARSAL:-0}" = 1 ]; then     # 예행 연습: 축소 모형으로 F1~F4 의 연결을 CPU 에서 확인(GPU 미사용, 평가 단계는 건너뜀)
  RD="${REHEARSAL_DIR:?REHEARSAL_DIR 지정}"; P="$RD/pipeline"; mkdir -p "$P"
  GG="$RD/gguf"; ADAPTER="$RD/adapter"; MERGED="$RD/merged"; BASE_SNAP=/mnt/share/models/arete-27b/test/tiny-twin
  FT_EXTRA=(--device cpu --base "$BASE_SNAP" --limit 24 --epochs 1); QUANT=Q4_K_M; OUTNAME=tiny-lora; WAIT_EVAL=0
  export CUDA_VISIBLE_DEVICES=""
fi
say() { echo "[$(date '+%F %T')] $*" | tee -a "$P/pipeline.log"; }
gpu_used() { [ "${REHEARSAL:-0}" = 1 ] && { echo 0; return; }; nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | awk '{s+=$1} END {print s+0}'; }
eval_complete() {
  "$VENV_PY" - "$@" <<'EOF'
import json, sys
from pathlib import Path
ok = True
for run in sys.argv[1:]:
    d = Path('05_eval/runs') / run
    m = json.loads((d / 'run_meta.json').read_text(encoding='utf-8')) if (d / 'run_meta.json').exists() else {}
    ok = ok and bool(m.get('complete')) and (d / 'report.json').exists()
sys.exit(0 if ok else 1)
EOF
}

say "미세조정 단계 연속 실행 시작 (pid $$)"
if [ "${WAIT_EVAL:-1}" = 1 ]; then
  say "평가 단계가 끝나기를 기다림(logs/pipeline/EVAL_ALL.end)"
  while [ ! -f "$P/EVAL_ALL.end" ]; do sleep 30; done
fi
t0=$SECONDS
while [ "$(gpu_used)" -gt 4000 ]; do
  [ $((SECONDS - t0)) -gt 1800 ] && { say "GPU 가 30분 넘게 비지 않음. 중단"; echo "GPU 점유" > "$P/F0.failed"; exit 3; }
  sleep 20
done

# ── F1 스모크 시험 ─────────────────────────────────────────────────────────────
CFG="$P/finetune_config.env"
if [ ! -f "$P/F1_smoke.done" ]; then
  S0=34; L=1536; S=$S0; moved=0; try=0; ok=0     # 분할 위치 기본 34: 임베딩 + 앞 34층은 GPU 0, 출력층 + 뒤 30층은 GPU 1 (2026-11-16 변경. 그 전 28 은 적재 단계에서 GPU 0 부족)
  while [ $try -lt 7 ]; do
    try=$((try + 1))
    say "F1 스모크 시험 $try차: 길이 상한 $L, 분할 위치 $S"
    "$CONDA_PY" 06_build/finetune_lora.py --smoke --max-len "$L" --split-at "$S" "${FT_EXTRA[@]}" --out "$ADAPTER.smoke" > "$P/F1_smoke.try$try.log" 2>&1; rc=$?
    if [ $rc -eq 0 ] && grep -q "스모크 시험 통과" "$P/F1_smoke.try$try.log"; then ok=1; break; fi
    if grep -qiE "out of memory" "$P/F1_smoke.try$try.log"; then
      g="$(grep -oiE "GPU [01]" "$P/F1_smoke.try$try.log" | head -1 | grep -oE "[01]")"
      say "F1: GPU 메모리 부족(GPU ${g:-?}). 설정을 바꿔 다시 시도"
      if [ $moved -lt 2 ] && [ -n "$g" ]; then
        moved=$((moved + 1)); if [ "$g" = 0 ]; then S=$((S - 2)); else S=$((S + 2)); fi
      else
        moved=0; S=$S0
        case $L in 1536) L=1280 ;; 1280) L=1024 ;; 1024) L=768 ;; *) break ;; esac
      fi
      sleep 20
    else
      say "F1: 메모리 부족이 아닌 오류로 실패(종료 코드 $rc). 기록 $P/F1_smoke.try$try.log"; tail -5 "$P/F1_smoke.try$try.log" | tee -a "$P/pipeline.log"
      break
    fi
  done
  if [ $ok -ne 1 ]; then echo "스모크 시험 실패" > "$P/F1_smoke.failed"; say "F1 실패. 미세조정 단계를 중단함"; exit 4; fi
  echo "MAX_LEN=$L SPLIT_AT=$S" > "$CFG"; date '+%F %T' > "$P/F1_smoke.done"; rm -rf "$ADAPTER.smoke"
  say "F1 끝: 길이 상한 $L, 분할 위치 $S · $(grep -E "GPU 메모리 최고" "$P/F1_smoke.try$try.log" | tail -1 | cut -c12-)"
fi
# shellcheck disable=SC1090
MAX_LEN=$(sed -E 's/.*MAX_LEN=([0-9]+).*/\1/' "$CFG"); SPLIT_AT=$(sed -E 's/.*SPLIT_AT=([0-9]+).*/\1/' "$CFG")

# ── F2 본 학습 ────────────────────────────────────────────────────────────────
if [ ! -f "$P/F2_train.done" ]; then
  for try in 1 2 3 4; do
    say "F2 본 학습 $try차: 길이 상한 $MAX_LEN, 분할 위치 $SPLIT_AT, 3에폭 (기록 $P/F2_train.try$try.log)"
    t1=$SECONDS
    while [ "$(gpu_used)" -gt 4000 ] && [ $((SECONDS - t1)) -lt 600 ]; do sleep 15; done
    "$CONDA_PY" 06_build/finetune_lora.py --max-len "$MAX_LEN" --split-at "$SPLIT_AT" --save-every 50 "${FT_EXTRA[@]}" --out "$ADAPTER" > "$P/F2_train.try$try.log" 2>&1; rc=$?
    if [ $rc -eq 0 ] && [ -f "$ADAPTER/training_meta.json" ]; then date '+%F %T' > "$P/F2_train.done"; say "F2 끝: $(grep -E "학습 완료" "$P/F2_train.try$try.log" | tail -1 | cut -c12-)"; break; fi
    say "F2: 중단됨(종료 코드 $rc). $(tail -1 "$P/F2_train.try$try.log" | cut -c1-200)"; sleep 60
  done
  [ -f "$P/F2_train.done" ] || { echo "학습 실패" > "$P/F2_train.failed"; say "F2 실패. 중단함"; exit 5; }
fi

# ── F3 병합 ───────────────────────────────────────────────────────────────────
if [ ! -f "$P/F3_merge.done" ]; then
  say "F3 병합: $ADAPTER → $MERGED"
  nice -n 10 "$CONDA_PY" 06_build/merge_lora.py --base "$BASE_SNAP" --adapter "$ADAPTER" --out "$MERGED" > "$P/F3_merge.log" 2>&1; rc=$?
  if [ $rc -eq 0 ] && [ -f "$MERGED/MERGE_INFO.json" ]; then date '+%F %T' > "$P/F3_merge.done"; say "F3 끝"; else echo "병합 실패" > "$P/F3_merge.failed"; say "F3 실패(종료 코드 $rc). 기록 $P/F3_merge.log"; exit 6; fi
fi

# ── F4 변환·양자화 ─────────────────────────────────────────────────────────────
if [ ! -f "$P/F4_gguf.done" ]; then
  say "F4 변환·양자화: $MERGED → $GG/$OUTNAME-$QUANT.gguf"
  NO_SCOPE=1 SNAP="$MERGED" NAME="$OUTNAME" OUT="$GG" bash 06_build/make_gguf.sh "$QUANT" > "$P/F4_gguf.log" 2>&1; rc=$?
  if [ $rc -eq 0 ] && [ -f "$GG/$OUTNAME-$QUANT.gguf" ]; then date '+%F %T' > "$P/F4_gguf.done"; say "F4 끝: $(du -h "$GG/$OUTNAME-$QUANT.gguf" | cut -f1)"; else echo "변환 실패" > "$P/F4_gguf.failed"; say "F4 실패(종료 코드 $rc). 기록 $P/F4_gguf.log"; exit 7; fi
fi

# ── F5·F6 미세조정 모형 평가 ──────────────────────────────────────────────────
[ "${REHEARSAL:-0}" = 1 ] && { say "예행 연습 끝(F1~F4). 평가 단계는 건너뜀"; exit 0; }
"$VENV_PY" - <<'EOF'
import yaml
from pathlib import Path
c = yaml.safe_load(Path('config/assistant.yaml').read_text(encoding='utf-8'))
c['prompt']['system'] = '03_prompts/system_prompt_short.md'          # 학습 자료와 같은 문구
c['model']['file'] = '/mnt/share/models/arete-27b/Arete-27B-lora-Q5_K_M.gguf'
Path('config/assistant_lora.yaml').write_text('# 미세조정 모형 평가용 설정 — config/assistant.yaml 에서 시스템 프롬프트만 짧은 판으로 바꾼 것(run_pipeline_finetune.sh 가 만듦)\n' + yaml.safe_dump(c, allow_unicode=True, sort_keys=False), encoding='utf-8')
EOF
ev() {   # ev 단계 실행이름머리 [환경변수=값...]
  local n="$1" name="$2"; shift 2
  [ -f "$P/$n.done" ] && { say "$n: 이미 끝남(건너뜀)"; return 0; }
  local try
  for try in 1 2 3; do
    say "$n: 시작($try차) — ${name}_base"
    env "$@" GGUF_FILE="$GG/Arete-27B-lora-Q5_K_M.gguf" bash 06_build/run_gpu_day.sh --path gguf --name "$name" --examples "0" > "$P/$n.try$try.log" 2>&1
    if eval_complete "${name}_base"; then date '+%F %T' > "$P/$n.done"; say "$n: 끝"; return 0; fi
    say "$n: 미완료. 60초 뒤 이어서 수행"; sleep 60
  done
  echo "미완료" > "$P/$n.failed"; say "$n: 3차까지 완료하지 못함"; return 1
}
ev F5_eval_short arete27b_lora_short SSDA_CONFIG="$ROOT/config/assistant_lora.yaml"
ev F6_eval_long arete27b_lora_long SSDA_DUMMY=1
date '+%F %T' > "$P/FINETUNE_ALL.end"
say "미세조정 단계 연속 실행 끝"
