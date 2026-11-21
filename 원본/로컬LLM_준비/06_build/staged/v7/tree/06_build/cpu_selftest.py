#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPU 없이 하는 코드 경로 자체 시험 — 구조가 같은 축소 모형으로 서버·미세조정·양자화 경로를 끝까지 실행해 본다.

무엇을 확인하는가(모두 CPU, GPU 에는 아무것도 올리지 않음)
  hf     06_build/serve_transformers.py 를 축소 모형으로 띄워 적재 → 대화 틀 → 생성 → 응답 형식, 오류 응답, 하네스 연결을 확인
  train  06_build/finetune_lora.py 를 축소 모형과 실제 학습 자료(1,536토큰 상한)로 돌려 LoRA 부착 → 응답 구간 손실 → 역전파 → 체크포인트 저장·재개 →
         어댑터 저장을 확인하고, 저장한 어댑터를 서버에 붙여 응답을 받음
  gguf   llama.cpp 경로: 변환(convert_lean.py) → 양자화 → 06_build/serve_llamacpp.sh(MODE=cpu) 기동 → 대화 틀·토큰화가 transformers 와 같은지
         학습 자료로 대조 → 하네스 연결(서버가 응답을 해석하지 못할 때의 예비 경로 포함) → 어댑터를 기반 가중치에 합쳐(merge_lora.py) 변환·구동
확인하지 못하는 것  4비트 적재, GPU 2장 분할, 27B 원본의 메모리 소요·속도·응답 품질(축소 모형은 가중치가 무작위임)

  conda activate vllm
  python 06_build/cpu_selftest.py                 # 전체(2~3분)
  python 06_build/cpu_selftest.py --only gguf     # 일부만 (hf,train,gguf)
출력  모형반입/cpu_selftest.json
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST = Path(os.environ.get('SSDA_TEST_DIR', '/mnt/share/models/arete-27b/test'))
TWIN, RUN = TEST / 'tiny-twin', TEST / 'run'
LLAMA = Path(os.environ.get('LLAMA', str(Path.home() / 'llama.cpp')))
PYC = sys.executable                                                                       # transformers·peft 가 있는 환경(conda vllm)
PYV = os.environ.get('PY', '/mnt/share/행정데이터_set/.venv/bin/python')                    # 하네스 실행 환경
DATA = os.environ.get('SSDA_DATA', '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet')
ENV = dict(os.environ, CUDA_VISIBLE_DEVICES='', SSDA_DATA=DATA, PYTHONPATH=str(LLAMA / 'gguf-py'))
P_HF, P_GG = 8093, 8094
QUESTION = '65세 이상 기초연금 수급률을 시도별로 알려 줘'
MSGS = [{'role': 'system', 'content': '분석 지원기임'}, {'role': 'user', 'content': f'[질문]\n{QUESTION}'}]


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def sh(cmd, timeout=900, env=None):
    p = subprocess.run(cmd, capture_output=True, text=True, env=env or ENV, timeout=timeout, cwd=str(ROOT))
    return p.returncode, p.stdout + p.stderr


def http(url, body=None, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode('utf-8') if body is not None else None, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:      # noqa: S310 — 127.0.0.1 의 시험 서버
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode('utf-8'))
        except Exception:                                             # noqa: BLE001
            return e.code, {}
    except Exception as e:                                            # noqa: BLE001
        return 0, {'error': str(e)}


class Server:
    """시험 서버를 띄우고 응답할 때까지 기다린다. 끝나면 내린다."""

    def __init__(self, cmd, port, logname, env=None):
        self.cmd, self.port, self.log, self.env = cmd, port, RUN / logname, env or ENV

    def __enter__(self):
        if http(f'http://127.0.0.1:{self.port}/v1/models', timeout=2)[0] == 200:
            raise RuntimeError(f'포트 {self.port} 를 다른 서버가 쓰고 있음')
        self.fp = open(self.log, 'w', encoding='utf-8')
        self.p = subprocess.Popen(self.cmd, stdout=self.fp, stderr=subprocess.STDOUT, env=self.env, cwd=str(ROOT))
        for _ in range(240):
            if self.p.poll() is not None:
                raise RuntimeError(f'서버가 종료됨(기록 {self.log})')
            if http(f'http://127.0.0.1:{self.port}/v1/models', timeout=2)[0] == 200:
                return self
            time.sleep(0.5)
        raise RuntimeError('서버 응답 없음')

    def __exit__(self, *a):
        self.p.terminate()
        try:
            self.p.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.p.kill()
        self.fp.close()

    def text(self):
        return self.log.read_text(encoding='utf-8', errors='replace')


def chat(port, messages, thinking=False, max_tokens=24, model='tiny-twin', **kw):
    return http(f'http://127.0.0.1:{port}/v1/chat/completions', {'model': model, 'messages': messages, 'temperature': 0, 'max_tokens': max_tokens,
                                                                   'chat_template_kwargs': {'enable_thinking': thinking}, **kw})


def harness(port, tag):
    """조립기(assistant.py)를 시험 서버에 연결해 질문 1건을 처리한다."""
    cfg = RUN / f'assistant_{tag}.yaml'
    tr = RUN / f'transcripts_{tag}.jsonl'
    tr.unlink(missing_ok=True)
    code, out = sh([PYV, '-c', (
        "import yaml,sys\n"
        f"c=yaml.safe_load(open(r'{ROOT / 'config' / 'assistant.yaml'}',encoding='utf-8'))\n"
        f"c['model'].update(base_url='http://127.0.0.1:{port}/v1',served_name='tiny-twin',max_tokens=48)\n"
        f"c['paths'].update(export=r'{RUN / 'export'}',log=r'{RUN / 'ssda_log.jsonl'}',transcripts=r'{tr}')\n"
        f"yaml.safe_dump(c,open(r'{cfg}','w',encoding='utf-8'),allow_unicode=True)\n")])
    if code:
        return {'ok': False, 'error': out[-300:]}
    code, out = sh([PYV, '06_build/assistant.py', '--config', str(cfg), '--ask', QUESTION])
    n = len(tr.read_text(encoding='utf-8').splitlines()) if tr.exists() else 0
    return {'ok': code == 0 and n == 1 and '모형 호출' in out, 'records': n, 'tail': out.strip().splitlines()[-1][:80] if out.strip() else ''}


def tokenizer():
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(str(TWIN))


def n_tokens(tok, messages, thinking):
    return len(tok(tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=thinking), add_special_tokens=False)['input_ids'])


# ───────────────────────── hf: transformers 서버 ─────────────────────────
def check_hf(tok):
    r = {}
    with Server([PYC, '06_build/serve_transformers.py', '--device', 'cpu', '--model', str(TWIN), '--name', 'tiny-twin', '--port', str(P_HF), '--ctx', '8192'], P_HF, 'serve_transformers.log') as s:
        st, d = http(f'http://127.0.0.1:{P_HF}/v1/models'); r['models'] = st == 200 and d['data'][0]['id'] == 'tiny-twin'
        st, d = chat(P_HF, MSGS, False)
        r['chat_thinking_off'] = st == 200 and isinstance(d['choices'][0]['message']['content'], str) and d['usage']['completion_tokens'] == 24
        r['prompt_tokens_off'] = [d.get('usage', {}).get('prompt_tokens'), n_tokens(tok, MSGS, False)]
        st, d = chat(P_HF, MSGS, True)
        r['chat_thinking_on'] = st == 200 and '</think>' not in d['choices'][0]['message']['content']
        r['prompt_tokens_on'] = [d.get('usage', {}).get('prompt_tokens'), n_tokens(tok, MSGS, True)]
        st, d = chat(P_HF, MSGS, False, max_tokens=9000); r['context_overflow_rejected'] = st == 400 and '문맥 한도 초과' in json.dumps(d, ensure_ascii=False)
        st, d = http(f'http://127.0.0.1:{P_HF}/v1/chat/completions', {'model': 'tiny-twin'}); r['bad_request_rejected'] = st == 400
        r['harness'] = harness(P_HF, 'hf')
        m = re.findall(r'요청 처리: 입력 (\d+)토큰', s.text()); r['harness_prompt_tokens'] = int(m[-1]) if m else None
    r['ok'] = all([r['models'], r['chat_thinking_off'], r['chat_thinking_on'], r['context_overflow_rejected'], r['bad_request_rejected'], r['harness']['ok'],
                   r['prompt_tokens_off'][0] == r['prompt_tokens_off'][1], r['prompt_tokens_on'][0] == r['prompt_tokens_on'][1]])
    return r


# ───────────────────────── train: 미세조정 ─────────────────────────
def check_train():
    r = {}
    out = RUN / 'lora'
    if out.exists():
        subprocess.run(['rm', '-rf', str(out)], check=True)
    base = [PYC, '06_build/finetune_lora.py', '--device', 'cpu', '--base', str(TWIN), '--limit', '16', '--save-every', '2', '--out', str(out)]
    code, o = sh(base + ['--smoke'])
    loss = [float(x) for x in re.findall(r'loss=([0-9.]+)', o)]
    hit = re.search(r"LoRA 부착 분포: (\{.*?\})", o)
    r['smoke'] = code == 0 and '스모크 시험 통과' in o
    r['lora_modules'] = hit.group(1) if hit else None
    r['loss'] = loss
    r['loss_near_uniform'] = bool(loss) and all(math.isfinite(x) and abs(x - math.log(248320)) < 1.0 for x in loss)     # 무작위 가중치이므로 ln(어휘 수) 근처여야 함
    m = re.search(r'학습 예시 (\d+)건\(대화 틀 불일치로 제외 (\d+)건, 길이 상한에 걸린 예시 (\d+)건, 상한 (\d+)토큰', o)
    r['examples'] = dict(zip(('used', 'skipped', 'truncated', 'max_len'), map(int, m.groups()))) if m else None
    code, o = sh(base + ['--epochs', '1'])
    r['run_1epoch'] = code == 0 and (out / 'adapter_model.safetensors').exists() and (out / 'checkpoint-4').exists()
    code, o = sh(base + ['--epochs', '2'])
    meta = json.loads((out / 'training_meta.json').read_text(encoding='utf-8')) if (out / 'training_meta.json').exists() else {}
    r['resume'] = code == 0 and '체크포인트 재개: step 4' in o and meta.get('steps') == 8
    from safetensors import safe_open
    with safe_open(str(out / 'adapter_model.safetensors'), 'pt') as f:
        keys = list(f.keys())
    r['adapter_tensors'] = len(keys)
    r['adapter_kinds'] = sorted({k.split('.lora_')[0].rsplit('.', 1)[-1] for k in keys})
    with Server([PYC, '06_build/serve_transformers.py', '--device', 'cpu', '--model', str(TWIN), '--lora', str(out), '--name', 'tiny-twin', '--port', str(P_HF), '--ctx', '8192'], P_HF, 'serve_transformers_lora.log') as s:
        st, d = chat(P_HF, MSGS, False)
        r['serve_with_adapter'] = st == 200 and d['usage']['completion_tokens'] == 24 and '어댑터 적재' in s.text()
    r['ok'] = all([r['smoke'], r['loss_near_uniform'], r['run_1epoch'], r['resume'], len(r['adapter_kinds']) == 12, r['serve_with_adapter'],
                   r['examples'] and r['examples']['skipped'] == 0])
    return r


# ───────────────────────── gguf: llama.cpp 경로 ─────────────────────────
def dialogues(n):
    rows = [json.loads(l) for l in (ROOT / '04_training' / 'data' / 'train.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    step = max(1, len(rows) // n)
    out = []
    for r in rows[::step][:n]:
        ms = r['messages']
        last = max(i for i, m in enumerate(ms) if m['role'] == 'assistant')
        out.append(ms[:2]); out.append(ms[:last])                 # 첫 질문까지 / 마지막 응답 직전까지(이력에 응답·실행 결과 포함)
    return out


def check_gguf(tok, n=60):
    r = {}
    qbin, sbin = LLAMA / 'build-cpu' / 'bin' / 'llama-quantize', LLAMA / 'build-cpu' / 'bin' / 'llama-server'
    if not (qbin.exists() and sbin.exists()):
        return {'ok': False, 'skipped': 'llama.cpp CPU 빌드 없음: bash 06_build/build_llamacpp.sh cpu'}
    f32, q4 = TEST / 'tiny-twin-f32.gguf', TEST / 'tiny-twin-Q4_K_M.gguf'
    code, o = sh([PYC, '06_build/convert_lean.py', str(LLAMA / 'convert_hf_to_gguf.py'), str(TWIN), '--outtype', 'f32', '--outfile', str(f32)])
    r['convert'] = code == 0 and f32.exists()
    q4.unlink(missing_ok=True)
    code, o = sh([str(qbin), str(f32), str(q4), 'Q4_K_M', '2'])
    r['quantize'] = code == 0 and q4.exists()
    senv = dict(ENV, MODE='cpu', MODEL=str(q4), PORT=str(P_GG), ALIAS='tiny-twin', THREADS='4', LLAMA=str(LLAMA))
    with Server(['bash', '06_build/serve_llamacpp.sh'], P_GG, 'serve_llamacpp.log', senv) as s:
        st, d = http(f'http://127.0.0.1:{P_GG}/v1/models'); r['models'] = st == 200
        same_t = same_k = 0; first = None; ds = dialogues(n)
        for ms in ds:
            want = tok.apply_chat_template(ms, tokenize=False, add_generation_prompt=True, enable_thinking=False)
            st, d = http(f'http://127.0.0.1:{P_GG}/apply-template', {'messages': ms})
            got = d.get('prompt', '') if st == 200 else ''
            same_t += got == want
            st, d = http(f'http://127.0.0.1:{P_GG}/tokenize', {'content': want, 'add_special': False, 'parse_special': True})
            ids = d.get('tokens', []) if st == 200 else []
            ref = tok(want, add_special_tokens=False)['input_ids']
            same_k += ids == ref
            if first is None and (got != want or ids != ref):
                i = next((j for j, (x, y) in enumerate(zip(got, want)) if x != y), min(len(got), len(want)))
                k = next((j for j, (x, y) in enumerate(zip(ids, ref)) if x != y), min(len(ids), len(ref)))
                first = {'template_at': i, 'got': got[max(0, i - 30):i + 40], 'want': want[max(0, i - 30):i + 40], 'token_at': k, 'tokens': [len(ids), len(ref)],
                         'piece': tok.decode(ref[max(0, k - 3):k + 3])}
        r['dialogues'] = len(ds); r['template_same'] = same_t; r['tokens_same'] = same_k; r['first_mismatch'] = first
        want = tok.apply_chat_template(MSGS, tokenize=False, add_generation_prompt=True, enable_thinking=True)
        st, d = http(f'http://127.0.0.1:{P_GG}/apply-template', {'messages': MSGS, 'chat_template_kwargs': {'enable_thinking': True}})
        r['template_thinking_on_same'] = st == 200 and d.get('prompt') == want
        st, d = chat(P_GG, MSGS, False)
        r['chat'] = st == 200 and isinstance(d['choices'][0]['message'].get('content'), str)
        r['prompt_tokens'] = [d.get('usage', {}).get('prompt_tokens'), n_tokens(tok, MSGS, False)]
        # 모형 연결부(clients.py): 무작위 가중치의 출력은 서버가 대화 형식으로 해석하지 못하는 일이 잦다(500). 그때 원문 생성으로 다시 받는지 확인
        sys.path.insert(0, str(ROOT / '06_build'))
        from clients import OpenAICompatClient
        c = OpenAICompatClient(f'http://127.0.0.1:{P_GG}/v1', 'tiny-twin', max_tokens=48, extra_body={'chat_template_kwargs': {'enable_thinking': False}})
        outs = [c.chat(ms) for ms in ds[:16:2]]
        r['client_calls'] = c.usage['calls']; r['client_raw_fallbacks'] = c.usage['raw_fallbacks']
        r['client_ok'] = len(outs) == 8 and all(isinstance(x, str) for x in outs)
        r['harness'] = harness(P_GG, 'gguf')
    # 어댑터: llama.cpp 의 어댑터 변환 도구가 이 구조를 지원하는지 기록만 하고(지원하지 않음), 기반 가중치에 합쳐 변환하는 경로를 시험
    lora = RUN / 'lora'
    if (lora / 'adapter_model.safetensors').exists():
        code, o = sh([PYC, str(LLAMA / 'convert_lora_to_gguf.py'), '--base', str(TWIN), '--outfile', str(RUN / 'lora.gguf'), str(lora)])
        r['lora_gguf_converter_supported'] = code == 0
        if code:
            r['lora_gguf_converter_error'] = o.strip().splitlines()[-1][:120] if o.strip() else ''
        mdir = RUN / 'merged'
        code, o = sh([PYC, '06_build/merge_lora.py', '--base', str(TWIN), '--adapter', str(lora), '--out', str(mdir)])
        r['merge'] = code == 0 and (mdir / 'model.safetensors').exists()
        if r['merge']:
            import torch
            from peft import PeftModel
            from safetensors.torch import load_file
            from transformers import Qwen3_5ForConditionalGeneration as ModelCls
            ref = PeftModel.from_pretrained(ModelCls.from_pretrained(str(TWIN), dtype=torch.float32), str(lora)).merge_and_unload().state_dict()
            got, orig = load_file(str(mdir / 'model.safetensors')), load_file(str(TWIN / 'model.safetensors'))
            r['merge_max_diff_vs_peft'] = max(float((ref[k] - got[k]).abs().max()) for k in got if k in ref)
            r['merge_changed_tensors'] = sum(1 for k in got if not torch.equal(got[k], orig[k]))
            mg = TEST / 'tiny-twin-merged-f32.gguf'
            code, o = sh([PYC, '06_build/convert_lean.py', str(LLAMA / 'convert_hf_to_gguf.py'), str(mdir), '--outtype', 'f32', '--outfile', str(mg)])
            r['merged_convert'] = code == 0 and mg.exists()
            if r['merged_convert']:
                with Server(['bash', '06_build/serve_llamacpp.sh'], P_GG, 'serve_llamacpp_merged.log', dict(senv, MODEL=str(mg))):
                    st, d = chat(P_GG, MSGS, False, max_tokens=8)
                    r['serve_merged'] = st == 200
    else:
        r['merge'] = None
    r['ok'] = all([r['convert'], r['quantize'], r['models'], r['template_same'] == r['dialogues'], r['tokens_same'] == r['dialogues'], r['template_thinking_on_same'], r['chat'],
                   r['prompt_tokens'][0] == r['prompt_tokens'][1], r['client_ok'], r['harness']['ok'],
                   r['merge'] is None or (r['merge'] and r['merge_max_diff_vs_peft'] < 1e-5 and r.get('merged_convert') and r.get('serve_merged'))])
    return r


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--only', default='hf,train,gguf'); ap.add_argument('--rebuild', action='store_true'); a = ap.parse_args()
    RUN.mkdir(parents=True, exist_ok=True)
    if a.rebuild or not (TWIN / 'model.safetensors').exists():
        log('축소 모형 생성'); code, o = sh([PYC, '06_build/make_tiny_twin.py', '--out', str(TWIN)])
        if code:
            print(o[-600:]); return 1
    info = json.loads((TWIN / 'TINY_TWIN.json').read_text(encoding='utf-8'))
    outp = ROOT / '모형반입' / 'cpu_selftest.json'
    rep = json.loads(outp.read_text(encoding='utf-8')) if outp.exists() else {}
    rep.update({'twin': {k: info[k] for k in ('class', 'layers', 'layer_types', 'hidden_size', 'parameters', 'lora_target_kinds')},
                'env': {'python': PYC, 'llama_cpp': subprocess.run(['git', '-C', str(LLAMA), 'log', '-1', '--format=%h %ad', '--date=short'], capture_output=True, text=True).stdout.strip()},
                'scope': '코드 경로와 형식만 확인. 가중치가 무작위인 축소 모형이므로 응답 내용·속도·메모리 소요는 확인되지 않음. 4비트 적재와 GPU 분할은 실행되지 않음'})
    tok = tokenizer()
    for name, fn in (('hf', lambda: check_hf(tok)), ('train', check_train), ('gguf', lambda: check_gguf(tok))):
        if name not in a.only.split(','):
            continue
        log(f'{name} 시험'); t0 = time.time()
        try:
            rep[name] = fn()
        except Exception as e:                                   # noqa: BLE001
            rep[name] = {'ok': False, 'error': f'{type(e).__name__}: {e}'}
        rep[name]['at'] = time.strftime('%Y-%m-%d %H:%M:%S'); rep[name]['elapsed_sec'] = round(time.time() - t0, 1)
        log(f"{name}: {'통과' if rep[name].get('ok') else '실패'} ({rep[name]['elapsed_sec']}초)")
    rep['ok'] = all(rep.get(k, {}).get('ok') for k in ('hf', 'train', 'gguf'))
    outp.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: rep[k] for k in ('hf', 'train', 'gguf') if k in rep}, ensure_ascii=False, indent=1))
    return 0 if rep['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
