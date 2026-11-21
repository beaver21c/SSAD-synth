#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LoRA 어댑터를 기반 가중치에 합쳐 새 모형 폴더를 만든다 — CPU 전용, 가중치 조각을 하나씩 처리하므로 RAM 을 적게 쓴다.

쓰는 이유
  · llama.cpp 의 어댑터 변환 도구(convert_lora_to_gguf.py, 2026-05-21 판)는 이 구조(qwen3_5)의 선형 주의 층 어댑터를 변환하지 못한다
    (변환 중 값 머리 재배열 단계에서 NotImplementedError — 축소 모형으로 확인, 2026-11-15).
  · 그래서 미세조정한 모형을 llama.cpp 서버로 구동하려면 어댑터를 기반 가중치에 합친 뒤 그 폴더를 GGUF 로 변환한다.
      python 06_build/merge_lora.py --base <기반 모형 폴더> --adapter <어댑터 폴더> --out <출력 폴더>
      SNAP=<출력 폴더> NAME=Arete-27B-lora bash 06_build/make_gguf.sh Q5_K_M
  · transformers 서버(serve_transformers.py --lora)는 어댑터를 그대로 붙이므로 합칠 필요가 없다.

계산  W' = W + (lora_alpha / r) × B·A   (rsLoRA 이면 lora_alpha / √r). 원래 자료형(bf16 등)으로 되돌려 저장한다.
검증  축소 모형에서 PEFT 의 merge_and_unload() 결과와 대조했다(cpu_selftest.py). 27B 원본에 적용한 적은 없다.
지원하지 않는 것  DoRA, 편향(bias) 학습, 층별로 다른 r(rank_pattern)
"""
import argparse
import glob
import json
import math
import os
import shutil
import sys
import time
from pathlib import Path

os.environ.setdefault('CUDA_VISIBLE_DEVICES', '')         # GPU 를 건드리지 않음


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True, help='기반 모형 폴더(safetensors 조각과 config.json 이 있는 곳)')
    ap.add_argument('--adapter', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    import torch
    from safetensors import safe_open
    from safetensors.torch import load_file, save_file

    base, ad, out = Path(a.base), Path(a.adapter), Path(a.out)
    cfg = json.loads((ad / 'adapter_config.json').read_text(encoding='utf-8'))
    if cfg.get('use_dora') or cfg.get('bias', 'none') != 'none' or cfg.get('rank_pattern') or cfg.get('alpha_pattern'):
        log('지원하지 않는 어댑터 형식(DoRA, 편향 학습, 층별 r)'); return 1
    r, alpha = cfg['r'], cfg['lora_alpha']
    scale = alpha / math.sqrt(r) if cfg.get('use_rslora') else alpha / r
    lora = load_file(str(ad / 'adapter_model.safetensors'))
    pairs = {}                                            # 기반 가중치 이름 → (A, B)
    for k, v in lora.items():
        if '.lora_A.' in k:
            name = k.split('.lora_A.')[0]
            name = name[len('base_model.model.'):] if name.startswith('base_model.model.') else name
            pairs[name + '.weight'] = (v, lora[k.replace('.lora_A.', '.lora_B.')])
    if not pairs:
        log('어댑터에서 LoRA 가중치를 찾지 못함'); return 1
    shards = sorted(glob.glob(str(base / '*.safetensors')))
    if not shards:
        log(f'기반 가중치 없음: {base}'); return 1
    out.mkdir(parents=True, exist_ok=True)
    log(f'어댑터 {len(pairs)}쌍, r={r}, 배율 {scale:g}, 기반 조각 {len(shards)}개 → {out}')
    merged, t0 = set(), time.time()
    for i, sp in enumerate(shards, 1):
        tensors = {}
        with safe_open(sp, 'pt') as f:
            meta = f.metadata() or {'format': 'pt'}
            for k in f.keys():
                w = f.get_tensor(k)
                if k in pairs:
                    A, B = pairs[k]
                    if w.shape != (B.shape[0], A.shape[1]):
                        log(f'모양 불일치: {k} {tuple(w.shape)} vs {(B.shape[0], A.shape[1])}'); return 1
                    w = (w.to(torch.float32) + scale * (B.to(torch.float32) @ A.to(torch.float32))).to(w.dtype)
                    merged.add(k)
                tensors[k] = w
        save_file(tensors, str(out / Path(sp).name), metadata=meta)
        del tensors
        log(f'조각 {i}/{len(shards)} 완료 (누적 병합 {len(merged)}개, {time.time() - t0:.0f}초)')
    if len(merged) != len(pairs):
        miss = sorted(set(pairs) - merged)
        log(f'기반 가중치에서 찾지 못한 대상 {len(miss)}개: {miss[:3]}'); return 1
    for f in base.iterdir():                              # 설정·토크나이저·대화 틀 등 나머지 파일은 그대로 복사
        if f.is_file() and f.suffix != '.safetensors':
            shutil.copy2(f, out / f.name)
    (out / 'MERGE_INFO.json').write_text(json.dumps({'base': str(base), 'adapter': str(ad), 'merged_tensors': len(merged), 'r': r, 'lora_alpha': alpha, 'scale': scale,
                                                    'at': time.strftime('%Y-%m-%d %H:%M:%S')}, ensure_ascii=False, indent=1), encoding='utf-8')
    log(f'완료: 가중치 {len(merged)}개에 어댑터를 합침 → {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
