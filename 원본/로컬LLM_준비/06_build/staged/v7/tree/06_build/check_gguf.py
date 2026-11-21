#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GGUF 양자화본 점검 — 파일의 머리 정보(구조 값, 토크나이저, 대화 틀, 텐서 목록)만 읽는다. GPU 도 큰 메모리도 쓰지 않는다.

확인하는 것
  · 구조 값이 공식 가중치의 설정과 같은지(층 64개, 은닉 크기 5,120, 어휘 248,320)
  · 파일에 들어간 대화 틀이 공식 저장소의 chat_template.jinja 와 글자 단위로 같은지
  · 파일에 들어간 어휘가 공식 토크나이저와 같은지(토큰 문자열 전수 대조)
  · 양자화 수준별 파일의 텐서 이름·모양이 중간 파일(bf16)과 같은지, 텐서 자료형 분포, 가중치당 비트 수
  · 기록해 둔 SHA-256(--hash 를 주면 다시 계산해 대조. 파일당 2~3분)
확인하지 못하는 것  양자화에 따른 응답 품질 변화(평가로 확인), GPU 에서의 구동

  conda activate vllm
  python 06_build/check_gguf.py [--hash]
출력  모형반입/gguf_check.json (+ 모형반입/반입기록.md 갱신)
"""
import argparse
import glob
import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LLAMA = Path(os.environ.get('LLAMA', str(Path.home() / 'llama.cpp')))
GGUF_DIR = Path(os.environ.get('GGUF_DIR', '/mnt/share/models/arete-27b'))
SNAP = glob.glob('/mnt/share/hf_cache/hub/models--NousResearch--Arete-27B/snapshots/*/')
os.environ.setdefault('CUDA_VISIBLE_DEVICES', '')
sys.path.insert(0, str(LLAMA / 'gguf-py'))


def field(r, key):
    f = r.fields.get(key)
    return f.contents() if f is not None else None


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as fp:
        for b in iter(lambda: fp.read(1 << 24), b''):
            h.update(b)
    return h.hexdigest()


def read_one(path, ref_tokens, ref_template, do_hash):
    from gguf import GGUFReader
    r = GGUFReader(str(path))
    arch = field(r, 'general.architecture')
    toks = field(r, 'tokenizer.ggml.tokens') or []
    tmpl = field(r, 'tokenizer.chat_template') or ''
    tens = {t.name: (tuple(int(x) for x in t.shape), t.tensor_type.name, int(t.n_elements), int(t.n_bytes)) for t in r.tensors}
    n_el = sum(v[2] for v in tens.values())
    res = {'file': path.name, 'bytes': path.stat().st_size, 'GiB': round(path.stat().st_size / 2 ** 30, 2), 'architecture': arch, 'name': field(r, 'general.name'),
           'block_count': field(r, f'{arch}.block_count'), 'embedding_length': field(r, f'{arch}.embedding_length'), 'context_length': field(r, f'{arch}.context_length'),
           'tokenizer': [field(r, 'tokenizer.ggml.model'), field(r, 'tokenizer.ggml.pre')], 'vocab': len(toks),
           'eos_token_id': field(r, 'tokenizer.ggml.eos_token_id'), 'padding_token_id': field(r, 'tokenizer.ggml.padding_token_id'),
           'tensors': len(tens), 'params_B': round(n_el / 1e9, 2), 'bits_per_weight': round(sum(v[3] for v in tens.values()) * 8 / n_el, 2),
           'tensor_types': dict(Counter(v[1] for v in tens.values()).most_common()),
           'chat_template_same_as_official': tmpl == ref_template, 'chat_template_chars': len(tmpl),
           'vocab_same_as_official': None}
    if ref_tokens is not None:
        # 토크나이저의 토큰은 248,077개이고 모형의 어휘 크기는 248,320 이다. 남는 번호(243개)는 변환 도구가 쓰지 않는 자리 표시([PAD번호])로 채운다
        diff = sum(1 for x, y in zip(toks, ref_tokens) if x != y)
        extra = toks[len(ref_tokens):]
        res['vocab_tokens_compared'] = min(len(toks), len(ref_tokens)); res['vocab_mismatch'] = diff
        res['vocab_unused_slots'] = len(extra)
        res['vocab_same_as_official'] = diff == 0 and len(toks) >= len(ref_tokens) and all(str(t).startswith('[PAD') for t in extra)
    rec = path.with_name(path.name + '.sha256')
    res['sha256'] = rec.read_text().split()[0] if rec.exists() else None
    if do_hash:
        got = sha256(path)
        res['sha256_recomputed_same'] = (got == res['sha256']) if res['sha256'] else None
        res['sha256'] = res['sha256'] or got
        if not rec.exists():
            rec.write_text(f'{got}  {path.name}\n')
    return res, {k: v[0] for k, v in tens.items()}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--hash', action='store_true'); a = ap.parse_args()
    files = sorted(p for p in GGUF_DIR.glob('Arete-27B-*.gguf') if p.stat().st_size > 0)      # 만드는 중인 파일(.part)과 빈 파일은 제외
    if not files:
        print(f'GGUF 파일 없음: {GGUF_DIR} (bash 06_build/make_gguf.sh 로 만든다)'); return 1
    snap = Path(SNAP[0]) if SNAP else None
    ref_template = (snap / 'chat_template.jinja').read_text(encoding='utf-8') if snap and (snap / 'chat_template.jinja').exists() else ''
    ref_tokens, cfg = None, {}
    if snap:
        cfg = json.loads((snap / 'config.json').read_text(encoding='utf-8')).get('text_config', {})
        try:
            from transformers import AutoTokenizer
            tok = AutoTokenizer.from_pretrained(str(snap))
            ref_tokens = tok.convert_ids_to_tokens(list(range(len(tok))))
        except Exception as e:                               # noqa: BLE001
            print('토크나이저를 읽지 못해 어휘 대조를 건너뜀:', e)
    rep = {'at': time.strftime('%Y-%m-%d %H:%M:%S'), 'dir': str(GGUF_DIR), 'files': [],
           'made_by': 'llama.cpp ' + os.popen(f'git -C {LLAMA} log -1 --format="%h %ad" --date=short').read().strip() + ' (convert_hf_to_gguf.py → llama-quantize). 파일별 원천은 files[].source'}
    shapes = {}
    for p in files:
        t0 = time.time()
        res, shp = read_one(p, ref_tokens, ref_template, a.hash)
        shapes[p.name] = shp
        res['structure_ok'] = (res['architecture'] == 'qwen35' and res['block_count'] == cfg.get('num_hidden_layers', 64) and res['embedding_length'] == cfg.get('hidden_size', 5120)
                               and res['vocab'] == cfg.get('vocab_size', 248320))
        res['source'] = '미세조정 병합 가중치(merged-lora-v1)에서 변환' if '-lora-' in p.name else '공식 가중치에서 직접 변환'
        rep['files'].append(res)
        print(f"{p.name}: {res['GiB']}GiB, {res['bits_per_weight']}비트/가중치, 텐서 {res['tensors']}개, 구조 {'일치' if res['structure_ok'] else '불일치'}, "
              f"대화 틀 {'같음' if res['chat_template_same_as_official'] else '다름'}, 어휘 {'같음' if res['vocab_same_as_official'] else '다름/미대조'} ({time.time() - t0:.0f}초)", flush=True)
    ref = next((n for n in shapes if 'bf16' in n), None) or files[0].name
    for res in rep['files']:
        res['same_tensors_as_reference'] = shapes[res['file']] == shapes[ref]
    rep['reference_for_tensor_compare'] = ref
    rep['ok'] = all(r['structure_ok'] and r['chat_template_same_as_official'] and r['vocab_same_as_official'] is not False and r['same_tensors_as_reference']
                    and r.get('sha256_recomputed_same') is not False for r in rep['files'])
    (ROOT / '모형반입' / 'gguf_check.json').write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding='utf-8')
    print('점검', '통과' if rep['ok'] else '실패', '→ 모형반입/gguf_check.json')
    return 0 if rep['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
