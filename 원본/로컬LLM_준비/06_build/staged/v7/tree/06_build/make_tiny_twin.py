#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""축소 모형 만들기 — Arete-27B 와 구조(클래스, 층 종류의 배열, 모듈 이름)가 같고 크기만 줄인 무작위 가중치 모형. GPU 를 쓰지 않는다.

쓰는 이유
  · 27B 모형은 이 PC의 RAM(30GB)에 올릴 수 없어 GPU 없이는 서버·미세조정 스크립트를 끝까지 돌려 볼 수 없다.
  · 구조가 같은 축소 모형이면 같은 클래스(Qwen3_5ForConditionalGeneration), 같은 토크나이저·대화 틀, 같은 LoRA 대상 모듈 이름으로
    적재 → 생성 → LoRA 부착 → 역전파 → 저장 → 다시 적재의 코드 경로를 CPU 에서 실행해 볼 수 있다.
  · 확인되는 것은 코드 경로와 형식뿐이다. 가중치가 무작위이므로 응답 내용, 속도, 메모리 소요는 알 수 없다.

  conda activate vllm
  python 06_build/make_tiny_twin.py                 # /mnt/share/models/arete-27b/test/tiny-twin 에 저장(약 0.2GB)
"""
import argparse
import copy
import glob
import json
import os
import sys
from pathlib import Path

os.environ.setdefault('CUDA_VISIBLE_DEVICES', '')        # GPU 를 건드리지 않음
SNAP = glob.glob('/mnt/share/hf_cache/hub/models--NousResearch--Arete-27B/snapshots/*/')
OUT = Path(os.environ.get('TINY_TWIN', '/mnt/share/models/arete-27b/test/tiny-twin'))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', default=str(OUT)); ap.add_argument('--layers', type=int, default=8); a = ap.parse_args()
    if not SNAP:
        print('공식 가중치 없음'); return 1
    import torch
    from transformers import AutoConfig, AutoTokenizer
    from transformers import Qwen3_5ForConditionalGeneration as ModelCls
    real = AutoConfig.from_pretrained(SNAP[0])
    cfg = copy.deepcopy(real)
    t, v = cfg.text_config, cfg.vision_config
    # 층 종류의 배열(선형 주의 3 + 일반 주의 1 의 반복)은 원본의 앞 N개를 그대로 쓴다
    t.num_hidden_layers = a.layers; t.layer_types = list(real.text_config.layer_types[:a.layers])
    t.hidden_size, t.intermediate_size = 64, 128
    t.num_attention_heads, t.num_key_value_heads, t.head_dim = 4, 2, 256               # head_dim 은 원본과 같게 둠: 회전 위치 부호화가 head_dim 의 1/4(64차원 = 11+11+10 쌍)을 씀
    t.linear_num_key_heads, t.linear_num_value_heads, t.linear_key_head_dim, t.linear_value_head_dim = 2, 6, 8, 8     # 원본의 16:48 비율 유지
    v.depth, v.hidden_size, v.intermediate_size, v.num_heads, v.out_hidden_size = 1, 32, 64, 2, 64
    for c in (cfg, t, v):
        if getattr(c, 'dtype', None) is not None:
            c.dtype = 'float32'
    torch.manual_seed(20261115)
    model = ModelCls(cfg).eval()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out)
    tok = AutoTokenizer.from_pretrained(SNAP[0]); tok.save_pretrained(out)          # 토크나이저와 대화 틀은 원본 그대로
    for f in ('generation_config.json', 'chat_template.jinja'):
        src = Path(SNAP[0]) / f
        if src.exists() and not (out / f).exists():
            (out / f).write_bytes(src.read_bytes())
    names = [n for n, _ in model.named_modules()]
    kinds = sorted({n.rsplit('.', 1)[-1] for n in names if n.rsplit('.', 1)[-1] in
                    ('q_proj', 'k_proj', 'v_proj', 'o_proj', 'in_proj_qkv', 'in_proj_a', 'in_proj_b', 'in_proj_z', 'out_proj', 'gate_proj', 'up_proj', 'down_proj')
                    and '.language_model.' in n})
    info = {'path': str(out), 'class': ModelCls.__name__, 'layers': a.layers, 'layer_types': t.layer_types, 'hidden_size': t.hidden_size,
            'parameters': sum(p.numel() for p in model.parameters()), 'vocab_size': t.vocab_size, 'lora_target_kinds': kinds,
            'note': '무작위 가중치. 코드 경로 시험 전용이며 응답 내용에는 의미가 없음'}
    (out / 'TINY_TWIN.json').write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(info, ensure_ascii=False))
    return 0 if len(kinds) == 12 else 1


if __name__ == '__main__':
    sys.exit(main())
