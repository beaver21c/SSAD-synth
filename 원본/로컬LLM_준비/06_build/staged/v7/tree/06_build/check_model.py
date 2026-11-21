#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""내려받은 모형의 점검 — GPU 를 쓰지 않고 할 수 있는 확인을 모은 것.

  files     파일이 모두 있고 크기가 기대 목록(모형반입/expected_files.json)과 같은지. --hash 를 주면 SHA-256 도 대조(약 55GB 를 읽음)
  config    구조 값이 미세조정·추론 스크립트의 전제와 같은지(층 수 64, 선형 주의 층 48 + 일반 주의 층 16, 어휘 수)
  keys      가중치 파일의 머리 정보만 읽어 텐서 이름·모양을 확인: GPU 분할에 쓰는 경로, LoRA 대상 모듈, 기반 모형(Qwen3.8-27B)과의 일치 여부,
            이 PC의 코퍼스 어댑터(chat_corpus_qwen_v1)가 겨냥한 모듈이 이 모형에 같은 모양으로 있는지
  skeleton  이 PC의 transformers 로 설정을 읽어 빈 모형 골격(가중치 없음, 메모리 미사용)을 만들고 가중치 이름·모양을 파일과 대조: 적재할 때 빠지거나 남는 가중치가 없는지,
            수동 GPU 분할 경로가 모든 가중치를 덮는지
  template  실제 토크나이저와 대화 틀로 학습 자료 전체를 토큰화해 봄: 응답 구간 표시가 되는지, 토큰 길이, 사고 과정 끄기 인자가 듣는지
            (transformers 가 필요하므로 conda 환경 vllm 의 파이썬으로 실행)
  convert   (선택, --only convert) 이 PC의 llama.cpp 변환 도구가 이 모형을 읽는지 시험 실행(--dry-run, 파일을 쓰지 않음). GGUF 를 직접 만들 때의 사전 확인

  ~/anaconda3/envs/vllm/bin/python 06_build/check_model.py [--hash] [--only files,config,keys,skeleton,template,convert]
출력  모형반입/model_check.json
"""
import argparse
import hashlib
import json
import os
import struct
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / '모형반입'
HUB = Path(os.environ.get('HF_HOME', '/mnt/share/hf_cache')) / 'hub'


def snapshot(repo, rev=None):
    d = HUB / ('models--' + repo.replace('/', '--')) / 'snapshots'
    if not d.exists():
        return None
    c = [p for p in d.iterdir() if p.is_dir() and (rev is None or p.name == rev)]
    return max(c, key=lambda p: p.stat().st_mtime) if c else None


def st_header(path):
    """safetensors 파일의 머리 정보(텐서 이름 → dtype, shape). 가중치는 읽지 않는다."""
    with open(path, 'rb') as f:
        n = struct.unpack('<Q', f.read(8))[0]
        h = json.loads(f.read(n))
    h.pop('__metadata__', None)
    return {k: (v['dtype'], tuple(v['shape'])) for k, v in h.items()}


def all_keys(snap):
    out = {}
    for p in sorted(snap.glob('model-*.safetensors')):
        out.update(st_header(p))
    return out


def check_files(snap, exp, do_hash):
    res = {'missing': [], 'size_mismatch': [], 'hash_mismatch': [], 'hashed': 0}
    for f in exp['files']:
        p = snap / f['path']
        if not p.exists():
            res['missing'].append(f['path']); continue
        if p.stat().st_size != f['size']:
            res['size_mismatch'].append(f['path']); continue
        if do_hash and f.get('sha256'):
            h = hashlib.sha256()
            with open(p, 'rb') as fp:
                for b in iter(lambda: fp.read(1 << 24), b''):
                    h.update(b)
            res['hashed'] += 1
            if h.hexdigest() != f['sha256']:
                res['hash_mismatch'].append(f['path'])
    res['n_files'] = len(exp['files']); res['bytes'] = sum(f['size'] for f in exp['files'])
    res['ok'] = not (res['missing'] or res['size_mismatch'] or res['hash_mismatch'])
    return res


def write_record(rep, exp, snap):
    """반입 기록: 무엇을 어디서 받았고 어떻게 확인했는지."""
    f = rep.get('files', {})
    L = ['# 모형 반입 기록', '', f"작성 {rep['checked_at']} · `06_build/check_model.py` 가 만든 기록", '',
         '| 항목 | 내용 |', '|---|---|', f"| 모형 | {exp['repo']} |", f"| 출처 | {exp['source']} (공식 저장소) |", f"| 판(커밋) | `{exp['revision']}` |", f"| 라이선스 | {exp['license']} |",
         f"| 받은 날 | {exp['listed_at']} |", '| 받은 방법 | `hf download`(conda 환경 vllm), 계정 토큰 없이 익명으로 받음 |', f"| 저장 위치 | `{snap}` |",
         f"| 파일 | {f.get('n_files')}개, {f.get('bytes', 0) / 1e9:.2f}GB |",
         f"| 크기 대조 | {'일치' if not f.get('missing') and not f.get('size_mismatch') else '불일치: ' + str(f.get('missing', []) + f.get('size_mismatch', []))} |",
         f"| SHA-256 대조 | {'저장소가 해시를 제공하는 ' + str(f.get('hashed')) + '개 파일(가중치·토크나이저) 일치' + (' (' + str(f.get('hashed_at'))[:16] + ')' if f.get('hashed_at') else '') if f.get('hashed') and not f.get('hash_mismatch') else ('불일치: ' + str(f.get('hash_mismatch')) if f.get('hash_mismatch') else '미수행(--hash)')} |",
         '', '## 파일 목록', '', '| 파일 | 크기(바이트) | SHA-256(저장소 기록) |', '|---|---|---|']
    L += [f"| {x['path']} | {x['size']:,} | {x['sha256'] or '—'} |" for x in exp['files']]
    L += ['', '## GPU 없이 수행한 점검', '']
    g, k, sk, t, cv = rep.get('config', {}), rep.get('keys', {}), rep.get('skeleton', {}), rep.get('template', {}), rep.get('convert', {})
    ok = lambda d: '통과' if d.get('ok') else '확인 필요'
    if g:
        lt = g.get('layer_types', {})
        L.append(f"- 구조 값: {ok(g)} — {g.get('model_type')} 구조, 층 {g.get('num_hidden_layers')}개(선형 주의 {lt.get('linear_attention')} + 일반 주의 {lt.get('full_attention')}), 은닉 크기 {g.get('hidden_size')}, 어휘 {g.get('vocab_size')}")
    if k:
        L.append(f"- 가중치 이름·모양: {ok(k)} — 텐서 {k.get('tensors')}개, 매개변수 {k.get('params_B')}B, 언어 층 {k.get('language_layers')}개, LoRA 대상 모듈 {len(k.get('lora_target_modules', {}))}종이 모두 있음")
        b = k.get('base_compare')
        if b:
            L.append(f"- 기반 모형(Qwen3.8-27B) 대비: 이 모형에만 있는 가중치 {b['only_in_model']}개, 모양이 다른 가중치 {b['shape_mismatch']}개, 기반에만 있는 가중치 {b['only_in_base']}개({', '.join(f'{x}.* {n}개' for x, n in b.get('only_in_base_prefixes', {}).items()) or '없음'})."
                     + (' 기반에만 있는 것은 적재 클래스가 읽지 않는 보조 가중치이므로 적재 기준으로는 같은 구성임' if b.get('same_for_loading') else ' 적재 기준으로 구성이 다름'))
            cd = b.get('config_diff')
            if isinstance(cd, dict):
                benign = set(cd) <= {'text_config.mtp_num_hidden_layers', 'transformers_version', 'vision_config.dtype', 'vision_config.model_type'}
                L.append(f"- 기반 모형과의 설정(config.json) 차이: {len(cd)}개 항목 — " + ', '.join(f"{kk}({va} / 기반 {vb})" for kk, (va, vb) in cd.items())
                         + ('. 층 구성·크기 등 적재에 쓰이는 값은 모두 같음(기반 모형은 이 PC에서 적재·학습된 이력이 있음)' if benign else '. 적재에 쓰이는 값에 차이가 있는지 확인이 필요함'))
        c = k.get('corpus_adapter')
        if c:
            L.append(f"- 코퍼스 어댑터(`{c['path']}`) 대비: 대상 모듈 {c['modules']}개 가운데 이 모형에 없는 것 {c['missing_in_model']}개, 모양이 맞지 않는 것 {c['shape_mismatch']}개"
                     + (' → 구조상 부착 가능. 어댑터는 Qwen3.8-27B의 가중치 위에서 학습된 것이어서 이 모형에서의 효과는 확인되지 않았음' if c.get('attachable') else ' → 그대로는 부착할 수 없음'))
    if sk:
        L.append(f"- 빈 모형 골격 대조: {ok(sk)} — 이 PC의 transformers {sk.get('transformers')}(모형은 {sk.get('saved_with_transformers')}로 저장됨)가 설정을 읽어 {sk.get('model_class')} 골격(텐서 {sk.get('tensors')}개)을 만듦. "
                 f"파일에 없는 가중치 {sk.get('missing_in_files')}개, 골격에 없는 가중치 {sk.get('unexpected_in_files')}개, 모양 불일치 {sk.get('shape_mismatch')}개, 수동 GPU 분할 경로가 덮지 못하는 가중치 {sk.get('weights_not_covered_by_device_map')}개")
    if t:
        L.append(f"- 대화 틀·토큰화: {ok(t)} — 학습 자료 {t['full']['encoded']}건을 토큰화, 응답 구간 표시 실패 {t['full']['skipped_prefix_mismatch'] + t['without_context']['skipped_prefix_mismatch']}건. "
                 f"사고 과정 끄기 인자(enable_thinking)는 대화 틀에 {'있음' if t.get('template_has_enable_thinking') else '없음'}. 참고 자료를 뺀 대화는 평균 {t['without_context']['tokens_mean']}토큰(95% {t['without_context']['tokens_p95']}, 최대 {t['without_context']['tokens_max']}), "
                 f"1,536토큰 이내 {t['without_context']['share_within_1536'] * 100:.1f}%")
        if 'vocab_merges_same_as_base' in t:
            L.append(f"- 토크나이저의 기반 모형 대비: 어휘·병합 규칙 파일 {'같음' if t['vocab_merges_same_as_base'] else '다름'}, 추가 토큰 {'같음' if t['added_tokens_same_as_base'] else '다름'}, 대화 틀 {'같음' if t.get('chat_template_same_as_base') else '다름'}, "
                     f"tokenizer.json 파일 {'같음' if t['tokenizer_json_same_as_base'] else '다름(저장 형식' + ('' if t.get('pre_tokenizer_same_as_base') else '과 사전 분절 규칙') + ')'}. 학습 자료 가운데 두 토크나이저의 결과가 다른 것 {t['train_rows_tokenized_differently_from_base']}건")
    if cv:
        L.append(f"- llama.cpp 변환 도구 시험 실행(선택 경로): {ok(cv)} — llama.cpp {cv.get('llama_cpp')} 판의 변환 도구가 텐서 {cv.get('n_tensors')}개({cv.get('total_size')})를 읽음. 파일은 쓰지 않았음")
    load = lambda n: json.loads((OUT / n).read_text(encoding='utf-8')) if (OUT / n).exists() else None
    gc, cs, rs = load('gguf_check.json'), load('cpu_selftest.json'), load('cpu_real_smoke.json')
    llama = Path(os.environ.get('LLAMA', str(Path.home() / 'llama.cpp')))
    if gc:
        has_lora = any('-lora-' in x['file'] for x in gc['files'])
        L += ['', '## 양자화본(GGUF) — 공식 가중치에서 직접 변환' + ('(미세조정 모형 포함)' if has_lora else ''), '',
              f"- 만든 방법: {gc['made_by'].split('. 파일별')[0]}. 제3자가 올린 양자화 파일은 받지 않았음"]
        if has_lora:
            L.append('- 이름에 `lora`가 든 파일은 미세조정 모형임: 공식 가중치에 어댑터(`06_build/runs/lora_assistant_v1`)를 합친 가중치(`merged-lora-v1`)를 같은 도구로 변환함(2026-11-16). 나머지는 공식 가중치를 그대로 변환한 파일임')
        L += [
              f"- 위치: `{gc['dir']}` · 점검 {gc['at']} (`06_build/check_gguf.py`, 파일의 머리 정보만 읽음)", '',
              '| 파일 | 크기 | 가중치당 비트 | 텐서 | 구조 값 | 대화 틀 | 어휘 | SHA-256 |', '|---|---|---|---|---|---|---|---|']
        for x in gc['files']:
            L.append(f"| {x['file']} | {x['GiB']}GiB | {x['bits_per_weight']} | {x['tensors']}개 | {'일치' if x['structure_ok'] else '불일치'} | {'공식과 같음' if x['chat_template_same_as_official'] else '다름'} | "
                     f"{'공식과 같음' if x['vocab_same_as_official'] else '다름' if x['vocab_same_as_official'] is False else '미대조'} | {('`' + x['sha256'][:16] + '…`') if x.get('sha256') else '—'} |")
        L += ['', '- 변환 대상은 언어 모형 부분(텐서 851개, 26.9B)임. 시각 인코더는 쓰지 않으므로 넣지 않았음',
              '- 변환 도구를 그대로 쓰면 가장 큰 텐서에서 약 11GB 의 메모리를 써 중단됐으므로, 결과가 같고 메모리를 덜 쓰는 포장 스크립트(`06_build/convert_lean.py`)로 실행함. 축소 모형에서 두 방식의 산출 파일이 바이트 단위로 같음을 확인함',
              '- 어휘는 토크나이저의 토큰 248,077개가 모두 같고, 남는 번호 243개는 쓰지 않는 자리 표시로 채워져 있음']
    bi = [(n, (llama / f'build-{n}' / 'BUILD_INFO.txt')) for n in ('cpu', 'cuda')]
    if any(f.exists() for _, f in bi):
        L += ['', '## 실행 파일(llama.cpp) — 이 PC에서 빌드', '']
        for n, f in bi:
            if f.exists():
                d = dict(l.split(': ', 1) for l in f.read_text(encoding='utf-8').splitlines() if ': ' in l)
                L.append(f"- {'CPU 빌드(양자화·GPU 없는 시험용)' if n == 'cpu' else 'CUDA 빌드(GPU 구동용)'}: `{f.parent}/bin` — {d.get('targets')}, 원본 {d.get('source', '').split(' @ ')[-1]}, {d.get('compiler')}"
                         + (f", {d.get('cuda')}" if d.get('cuda') else '') + f", {d.get('built_at')}" + (' · GPU 에서 실행한 적 없음(GPU 를 가린 상태에서 실행 파일과 CUDA 라이브러리 연결만 확인)' if n == 'cuda' else ''))
    if cs:
        L += ['', '## GPU 없이 수행한 코드 경로 시험(축소 모형)', '',
              f"- 대상: 구조가 같은 축소 모형({cs['twin']['class']}, 층 {cs['twin']['layers']}개, 무작위 가중치, 토크나이저·대화 틀은 원본). `06_build/cpu_selftest.py`",
              f"- 범위: {cs.get('scope')}"]
        h, tr, g = cs.get('hf') or {}, cs.get('train') or {}, cs.get('gguf') or {}
        if h:
            L.append(f"- 서버(serve_transformers.py): {ok(h)} — 적재·생성·응답 형식, 문맥 초과와 잘못된 요청의 오류 응답, 입력 토큰 수가 대화 틀 적용 결과와 같음({h.get('prompt_tokens_off')}), 조립기 연결(입력 {h.get('harness_prompt_tokens')}토큰) ({h.get('at')})")
        if tr:
            ex = tr.get('examples') or {}
            L.append(f"- 미세조정(finetune_lora.py): {ok(tr)} — 실제 학습 자료 {ex.get('used')}건·상한 {ex.get('max_len')}토큰으로 LoRA 부착({len(tr.get('adapter_kinds') or [])}종 모듈) → 응답 구간 손실({tr.get('loss')}, 무작위 가중치의 기댓값 12.42 근처) → "
                     f"역전파 → 체크포인트 저장·재개 → 어댑터 저장, 어댑터를 붙인 서버 응답 ({tr.get('at')})")
        if g:
            L.append(f"- llama.cpp 경로: {ok(g)} — 변환·양자화·서버 기동(serve_llamacpp.sh), 학습 자료 {g.get('dialogues')}개 대화에서 대화 틀 적용 결과가 transformers 와 같은 것 {g.get('template_same')}개·토큰 번호가 같은 것 {g.get('tokens_same')}개, "
                     f"조립기 연결, 서버가 응답을 해석하지 못할 때의 예비 경로({g.get('client_raw_fallbacks')}/{g.get('client_calls')}회 사용) ({g.get('at')})")
            if g.get('lora_gguf_converter_supported') is False:
                L.append(f"- 어댑터의 GGUF 변환: llama.cpp 의 변환 도구가 이 구조의 어댑터를 지원하지 않음({g.get('lora_gguf_converter_error')}). 대신 어댑터를 기반 가중치에 합쳐 변환하는 경로(`06_build/merge_lora.py`)를 확인함 — "
                         f"PEFT 병합 결과와의 최대 차이 {g.get('merge_max_diff_vs_peft')}, 합친 모형의 변환·구동 {'성공' if g.get('serve_merged') else '실패'}")
    if rs:
        L += ['', '## 양자화본 시범 구동(CPU)', '', f"- {rs.get('summary')} ({rs.get('at')})", '- 상세는 `cpu_실모형_시험.md`. 문항 1~2개의 결과이며 성능 평가가 아님']
    L += ['', '## 하지 않은 것', '', '- 모형을 GPU 에 올려 응답을 생성한 적 없음(GPU 2장을 다른 작업이 사용 중). GPU 에서의 속도와 메모리 소요, 벤치마크 성능은 측정되지 않았음',
          '- 제3자가 올린 양자화 파일(GGUF, AWQ 등)은 받지 않았음' + ('. 양자화본은 공식 가중치에서 직접 만들었음' if gc else '. 양자화본도 만들지 않았음'),
          '- 4비트 적재(bitsandbytes)와 GPU 2장 분할은 GPU 에서만 실행되는 부분이어서 확인하지 못했음', '',
          '상세는 `model_check.json`, `gguf_check.json`, `cpu_selftest.json`.']
    (OUT / '반입기록.md').write_text('\n'.join(L) + '\n', encoding='utf-8')


def check_config(snap):
    c = json.loads((snap / 'config.json').read_text(encoding='utf-8'))
    t = c.get('text_config', c)
    lt = Counter(t.get('layer_types') or [])
    res = {'model_type': c.get('model_type'), 'architectures': c.get('architectures'), 'num_hidden_layers': t.get('num_hidden_layers'), 'hidden_size': t.get('hidden_size'),
           'vocab_size': t.get('vocab_size'), 'layer_types': dict(lt), 'num_key_value_heads': t.get('num_key_value_heads'), 'head_dim': t.get('head_dim'),
           'max_position_embeddings': t.get('max_position_embeddings'), 'has_vision': 'vision_config' in c}
    res['ok'] = (res['model_type'] == 'qwen3_5' and res['num_hidden_layers'] == 64 and lt.get('linear_attention') == 48 and lt.get('full_attention') == 16
                 and (c.get('architectures') or [''])[0] == 'Qwen3_5ForConditionalGeneration')
    return res


def check_keys(snap, base_snap):
    k = all_keys(snap)
    layers = sorted({int(n.split('.layers.')[1].split('.')[0]) for n in k if n.startswith('model.language_model.layers.')})
    targets = ['q_proj', 'k_proj', 'v_proj', 'o_proj', 'in_proj_qkv', 'in_proj_a', 'in_proj_b', 'in_proj_z', 'out_proj', 'gate_proj', 'up_proj', 'down_proj']
    cnt = {t: sum(1 for n in k if n.startswith('model.language_model.') and n.endswith(f'.{t}.weight')) for t in targets}
    res = {'tensors': len(k), 'params_B': round(sum(_prod(s) for _, s in k.values()) / 1e9, 2), 'dtypes': dict(Counter(d for d, _ in k.values())),
           'language_layers': len(layers), 'prefix_ok': {p: any(n.startswith(p) for n in k) for p in ('model.language_model.embed_tokens', 'model.language_model.norm', 'lm_head', 'model.visual', 'mtp')},
           'lora_target_modules': cnt, 'linear_attn_layers': len({n.split('.layers.')[1].split('.')[0] for n in k if '.linear_attn.' in n}),
           'self_attn_layers': len({n.split('.layers.')[1].split('.')[0] for n in k if '.self_attn.' in n})}
    res['ok'] = (layers == list(range(64)) and res['prefix_ok']['lm_head'] and res['prefix_ok']['model.language_model.embed_tokens'] and all(v > 0 for v in cnt.values())
                 and res['linear_attn_layers'] == 48 and res['self_attn_layers'] == 16)
    if base_snap:
        b = all_keys(base_snap)
        only_b = sorted(set(b) - set(k))
        res['base_compare'] = {'base': str(base_snap.parent.parent.name), 'only_in_model': len(set(k) - set(b)), 'only_in_base': len(only_b),
                               'only_in_base_prefixes': dict(Counter(n.split('.')[0] for n in only_b)),
                               'shape_mismatch': sum(1 for n in set(k) & set(b) if k[n][1] != b[n][1]), 'same_names_and_shapes': set(k) == set(b) and all(k[n][1] == b[n][1] for n in k)}
        # 적재 클래스는 mtp.* 를 읽지 않는다(transformers 의 _keys_to_ignore_on_load_unexpected). 그 밖의 가중치가 이름·모양까지 같으면 적재 기준으로 같은 구성이다
        bc = res['base_compare']
        bc['same_for_loading'] = bc['only_in_model'] == 0 and bc['shape_mismatch'] == 0 and all(n.startswith('mtp.') for n in only_b)
        # 설정 파일(config.json)의 차이: 기반 모형은 이 PC에서 적재·학습된 이력이 있으므로, 차이가 적재와 무관한 항목뿐이면 같은 조건으로 적재된다
        def flat(d, pre=''):
            o = {}
            for kk, v in d.items():
                o.update(flat(v, pre + kk + '.')) if isinstance(v, dict) else o.__setitem__(pre + kk, v)
            return o
        try:
            fa, fb = flat(json.loads((snap / 'config.json').read_text(encoding='utf-8'))), flat(json.loads((base_snap / 'config.json').read_text(encoding='utf-8')))
            bc['config_diff'] = {kk: [fa.get(kk), fb.get(kk)] for kk in sorted(set(fa) | set(fb)) if fa.get(kk) != fb.get(kk)}
        except Exception as e:                              # noqa: BLE001
            bc['config_diff'] = f'비교 실패: {e}'
    ad = Path(os.environ.get('CORPUS_ADAPTER', '/mnt/share/corpus/models/adapters/chat_corpus_qwen_v1'))
    if (ad / 'adapter_model.safetensors').exists():
        import re
        mods = {}
        for n, (_, shp) in st_header(ad / 'adapter_model.safetensors').items():
            m = re.match(r'(?:base_model\.model\.)?(.*)\.lora_([AB])\.weight$', n)
            if m:
                mods.setdefault(m.group(1), {})[m.group(2)] = shp
        miss = [m for m in mods if m + '.weight' not in k]
        bad = [m for m in mods if m + '.weight' in k and (mods[m]['A'][1] != k[m + '.weight'][1][1] or mods[m]['B'][0] != k[m + '.weight'][1][0])]
        res['corpus_adapter'] = {'path': str(ad), 'modules': len(mods), 'missing_in_model': len(miss), 'shape_mismatch': len(bad), 'attachable': bool(mods) and not miss and not bad}
    return res


def check_skeleton(snap):
    """빈 모형 골격(메타 장치, 가중치 없음)을 만들어 가중치 이름·모양을 파일과 대조한다. GPU·RAM 을 쓰지 않는다."""
    import math
    import transformers
    from accelerate import init_empty_weights
    from transformers import AutoConfig
    from transformers import Qwen3_5ForConditionalGeneration as M
    cfg = AutoConfig.from_pretrained(str(snap))
    with init_empty_weights():
        model = M(cfg)
    sd = {n: tuple(v.shape) for n, v in model.state_dict().items()}
    ck = all_keys(snap)
    names = {n for n, _ in model.named_modules()}
    dm = ['model.language_model.embed_tokens', 'model.language_model.norm', 'model.language_model.rotary_emb', 'lm_head', 'model.visual'] + [f'model.language_model.layers.{i}' for i in range(64)]
    res = {'transformers': transformers.__version__, 'saved_with_transformers': json.loads((snap / 'config.json').read_text(encoding='utf-8')).get('transformers_version'),
           'model_class': M.__name__, 'config_class': type(cfg).__name__, 'vision_config_class': type(cfg.vision_config).__name__,
           'tensors': len(sd), 'params_B': round(sum(math.prod(x) for x in sd.values()) / 1e9, 2),
           'missing_in_files': len(set(sd) - set(ck)), 'unexpected_in_files': len(set(ck) - set(sd)), 'shape_mismatch': sum(1 for n in sd if n in ck and sd[n] != ck[n][1]),
           'device_map_paths_missing': [x for x in dm if x not in names], 'weights_not_covered_by_device_map': sum(1 for n in sd if not any(n == x or n.startswith(x + '.') for x in dm))}
    res['ok'] = not (res['missing_in_files'] or res['unexpected_in_files'] or res['shape_mismatch'] or res['device_map_paths_missing'] or res['weights_not_covered_by_device_map'])
    return res


def _prod(s):
    p = 1
    for x in s:
        p *= x
    return p


def check_template(snap):
    from transformers import AutoTokenizer
    sys.path.insert(0, str(ROOT / '06_build'))
    from finetune_lora import _ids, encode_dialogue, strip_context
    tok = AutoTokenizer.from_pretrained(str(snap))
    tpl = (snap / 'chat_template.jinja').read_text(encoding='utf-8') if (snap / 'chat_template.jinja').exists() else (tok.chat_template or '')
    rows = [json.loads(l) for l in (ROOT / '04_training/data/train.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    res = {'vocab': len(tok), 'template_chars': len(tpl), 'template_has_enable_thinking': 'enable_thinking' in tpl, 'eos': tok.eos_token, 'pad': tok.pad_token}
    m = rows[0]['messages']
    on = tok.apply_chat_template(m[:2], tokenize=False, add_generation_prompt=True, enable_thinking=True)
    off = tok.apply_chat_template(m[:2], tokenize=False, add_generation_prompt=True, enable_thinking=False)
    res['generation_prompt_tail_thinking_on'] = on[-60:]; res['generation_prompt_tail_thinking_off'] = off[-60:]; res['thinking_switch_changes_prompt'] = on != off
    for name, prep in (('without_context', strip_context), ('full', lambda x: x)):
        n_ok, skip, lens, lab = 0, 0, [], []
        for r in rows:
            e = encode_dialogue(tok, prep(r['messages']), 10 ** 9)
            if e is None:
                skip += 1; continue
            n_ok += 1; lens.append(len(e[0])); lab.append(sum(1 for x in e[1] if x != -100))
        lens.sort()
        q = lambda p: lens[min(int(len(lens) * p), len(lens) - 1)]
        res[name] = {'encoded': n_ok, 'skipped_prefix_mismatch': skip, 'tokens_mean': round(sum(lens) / max(len(lens), 1)), 'tokens_p95': q(.95), 'tokens_max': lens[-1] if lens else 0,
                     'label_tokens_mean': round(sum(lab) / max(len(lab), 1)), 'share_within_1536': round(sum(x <= 1536 for x in lens) / max(len(lens), 1), 3),
                     'share_within_1024': round(sum(x <= 1024 for x in lens) / max(len(lens), 1), 3), 'share_within_512': round(sum(x <= 512 for x in lens) / max(len(lens), 1), 3)}
    # 응답 구간 표시가 맞는지 한 건을 되돌려 확인
    e = encode_dialogue(tok, strip_context(rows[0]['messages']), 10 ** 9)
    res['label_span_decoded_head'] = tok.decode([x for x in e[1] if x != -100])[:120] if e else None
    sysl = (ROOT / '03_prompts/system_prompt.md').read_text(encoding='utf-8')
    res['system_prompt_long_tokens'] = len(_ids(tok(sysl)['input_ids']))
    base = snapshot('Qwen/Qwen3.8-27B')
    if base and (base / 'tokenizer.json').exists():
        same = lambda f: (snap / f).exists() and (base / f).exists() and (snap / f).read_bytes() == (base / f).read_bytes()
        res['tokenizer_json_same_as_base'] = same('tokenizer.json')          # 저장한 transformers 판이 달라 파일 형식이 다를 수 있다
        res['vocab_merges_same_as_base'] = same('vocab.json') and same('merges.txt')
        ja, jb = json.loads((snap / 'tokenizer.json').read_text(encoding='utf-8')), json.loads((base / 'tokenizer.json').read_text(encoding='utf-8'))
        res['added_tokens_same_as_base'] = ja.get('added_tokens') == jb.get('added_tokens')
        res['pre_tokenizer_same_as_base'] = ja.get('pre_tokenizer') == jb.get('pre_tokenizer')
        tb = AutoTokenizer.from_pretrained(str(base))
        res['train_rows_tokenized_differently_from_base'] = sum(1 for r in rows if tok('\n'.join(m['content'] for m in r['messages']))['input_ids'] != tb('\n'.join(m['content'] for m in r['messages']))['input_ids'])
        res['chat_template_same_as_base'] = (base / 'chat_template.jinja').exists() and (base / 'chat_template.jinja').read_text(encoding='utf-8') == tpl
    res['ok'] = res['without_context']['skipped_prefix_mismatch'] == 0 and res['full']['skipped_prefix_mismatch'] == 0
    return res


def check_convert(snap):
    """llama.cpp 변환 도구의 시험 실행. 파일을 쓰지 않고 GPU 도 쓰지 않는다."""
    import re
    import subprocess
    llama = Path(os.environ.get('LLAMA', str(Path.home() / 'llama.cpp')))
    tool = llama / 'convert_hf_to_gguf.py'
    if not tool.exists():
        return {'ok': False, 'note': f'변환 도구 없음: {tool}'}
    env = dict(os.environ, PYTHONPATH=str(llama / 'gguf-py'), CUDA_VISIBLE_DEVICES='', HF_HUB_OFFLINE='1')
    r = subprocess.run([sys.executable, str(tool), str(snap), '--outtype', 'bf16', '--dry-run'], capture_output=True, text=True, env=env)
    m = re.search(r'n_tensors = (\d+), total_size = ([\d.]+\w)', r.stdout + r.stderr)
    ver = subprocess.run(['git', '-C', str(llama), 'log', '-1', '--format=%h %ad', '--date=short'], capture_output=True, text=True).stdout.strip()
    return {'ok': r.returncode == 0 and bool(m), 'returncode': r.returncode, 'llama_cpp': ver, 'n_tensors': int(m.group(1)) if m else None, 'total_size': m.group(2) if m else None,
            'wrote_file': False, 'tail': (r.stdout + r.stderr)[-300:] if r.returncode else ''}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', default='NousResearch/Arete-27B'); ap.add_argument('--hash', action='store_true'); ap.add_argument('--only', default='files,config,keys,skeleton,template')
    ap.add_argument('--record-only', action='store_true', help='점검을 다시 하지 않고 기록 파일(반입기록.md)만 다시 씀')
    a = ap.parse_args()
    exp = json.loads((OUT / 'expected_files.json').read_text(encoding='utf-8'))
    snap = snapshot(a.repo, exp.get('revision'))
    if snap is None:
        print('모형 폴더 없음:', HUB / ('models--' + a.repo.replace('/', '--'))); return 1
    p = OUT / 'model_check.json'
    rep = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
    if a.record_only:
        write_record(rep, exp, snap); print('반입기록.md 다시 씀'); return 0
    old_files = dict(rep.get('files') or {})
    rep.update({'repo': a.repo, 'revision': exp.get('revision'), 'snapshot': str(snap), 'checked_at': time.strftime('%Y-%m-%d %H:%M:%S')})
    for name in a.only.split(','):
        t0 = time.time()
        if name == 'files':
            rep['files'] = check_files(snap, exp, a.hash)
        elif name == 'config':
            rep['config'] = check_config(snap)
        elif name == 'keys':
            rep['keys'] = check_keys(snap, snapshot('Qwen/Qwen3.8-27B'))
        elif name == 'skeleton':
            rep['skeleton'] = check_skeleton(snap)
        elif name == 'template':
            rep['template'] = check_template(snap)
        elif name == 'convert':
            rep['convert'] = check_convert(snap)
        if name == 'files' and not a.hash and old_files.get('hashed') and rep['files']['ok']:
            rep['files']['hashed'], rep['files']['hashed_at'] = old_files['hashed'], old_files.get('hashed_at') or old_files.get('at')     # 앞서 한 해시 대조 기록을 지우지 않는다
        elif name == 'files' and a.hash:
            rep['files']['hashed_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        rep[name]['seconds'] = round(time.time() - t0, 1); rep[name]['at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{'통과' if rep[name]['ok'] else '확인 필요'}] {name}: " + json.dumps({k: v for k, v in rep[name].items() if k != 'ok'}, ensure_ascii=False)[:900])
    rep['ok'] = all(rep.get(n, {}).get('ok') for n in ('files', 'config', 'keys', 'skeleton', 'template'))
    p.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding='utf-8')
    write_record(rep, exp, snap)
    return 0 if rep['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
