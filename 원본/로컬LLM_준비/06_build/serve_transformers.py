#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""추론 서버(transformers + 4비트 적재) — 공식 가중치를 그대로 써서 OpenAI 호환 주소를 제공한다. GPU 에서 실행한 적 없음.
코드 경로(적재 → 대화 틀 → 생성 → 응답 형식, 어댑터 부착)는 구조가 같은 축소 모형으로 CPU 에서 실행해 확인함(cpu_selftest.py, 2026-11-15).
4비트 적재와 GPU 2장 분할은 GPU 에서만 실행되는 부분이어서 확인하지 못함.

쓰는 이유
  · 내려받은 공식 가중치(bf16, 54.7GB)만으로 구동된다. 제3자가 만든 양자화 파일이나 별도 서버 설치가 필요 없다.
  · 모형 적재(4비트 NF4, GPU 2장 수동 분할)는 이 PC에서 완주한 학습 스크립트(/mnt/share/corpus/scripts/train_cpt_qwen.py)의 방식 그대로다.
  · 속도는 vLLM·llama.cpp 보다 느릴 것으로 예상된다(미측정). 평가와 시범 구동용이며, 상시 운영에는 양자화본을 쓰는 서버가 낫다(구축지시서 3단계).

실행(GPU 가 비어 있을 때)
  conda activate vllm
  python 06_build/serve_transformers.py                       # NousResearch/Arete-27B, 127.0.0.1:8080
  python 06_build/serve_transformers.py --lora <어댑터 폴더>     # 미세조정 어댑터를 함께 올림
지금 할 수 있는 시험(GPU 불필요)
  python 06_build/serve_transformers.py --dry-run             # 모형 없이 주소·형식만 확인하는 모의 응답 서버
  python 06_build/serve_transformers.py --device cpu --model /mnt/share/models/arete-27b/test/tiny-twin --port 8093
                                                              # 구조가 같은 축소 모형(make_tiny_twin.py)을 CPU 에 올려 코드 경로를 확인. 27B 원본은 CPU 에 올리지 않는다

주소  GET /v1/models · POST /v1/chat/completions (model, messages, temperature, max_tokens, chat_template_kwargs.enable_thinking)
한 번에 한 요청만 처리한다(잠금). 127.0.0.1 에서만 듣는다.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCK = threading.Lock()
STATE = {'name': 'arete-27b', 'gen': None, 'loaded_at': None}


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def resolve_model(name):
    """모형 이름(저장소 id)을 이 PC의 모형 캐시에 있는 폴더로 바꾼다. 캐시에 있으면 그 폴더를 쓰고 통신망에 접속하지 않는다.
    환경변수 HF_HOME 이 없어도 /mnt/share/hf_cache 를 찾아본다(이 PC의 셸에는 HF_HOME 이 설정돼 있지 않음. 2026-11-15 확인)."""
    if os.path.isdir(name):
        return name
    for home in (os.environ.get('HF_HOME'), '/mnt/share/hf_cache', os.path.expanduser('~/.cache/huggingface')):
        if home:
            snaps = sorted(glob.glob(os.path.join(home, 'hub', 'models--' + name.replace('/', '--'), 'snapshots', '*')))
            if snaps and os.path.exists(os.path.join(snaps[-1], 'config.json')):
                os.environ.setdefault('HF_HUB_OFFLINE', '1')
                return snaps[-1]
    return name


def load(args):
    """모형을 4비트로 GPU 2장에 나누어 올리고 생성 함수를 돌려준다. --device cpu 는 축소 모형으로 코드 경로를 시험할 때만 쓴다."""
    cpu = args.device == 'cpu'
    if cpu:
        os.environ['CUDA_VISIBLE_DEVICES'] = ''                  # torch 를 부르기 전에 GPU 를 가림(GPU 에 아무것도 올리지 않음)
    else:
        used = subprocess.run(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'], capture_output=True, text=True).stdout.split()
        if sum(int(x) for x in used if x.isdigit()) > 4000 and os.environ.get('FORCE') != '1':
            log('GPU 를 다른 작업이 사용 중임. 종료 후 다시 실행할 것(FORCE=1 로 무시 가능)'); sys.exit(1)
    args.model = resolve_model(args.model)                    # 모형 캐시에 있으면 그 폴더를 씀(내려받지 않음)
    import torch
    from transformers import AutoConfig, AutoTokenizer, BitsAndBytesConfig
    from transformers import Qwen3_5ForConditionalGeneration as ModelCls     # AutoModelForCausalLM 을 쓰면 키가 어긋난다(학습 스크립트의 실측 기록)
    try:
        import transformers.core_model_loading as _cml; _cml.GLOBAL_WORKERS = 1
    except Exception:
        pass
    try:
        import transformers.modeling_utils as _mu; _mu.caching_allocator_warmup = lambda *x, **k: None
    except Exception:
        pass
    tok = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    n_layers = AutoConfig.from_pretrained(args.model, trust_remote_code=True).text_config.num_hidden_layers
    dev = 'cpu' if cpu else 'cuda:0'
    t0 = time.time()
    if cpu:
        if n_layers > 16 and os.environ.get('FORCE') != '1':
            log(f'층이 {n_layers}개인 모형은 CPU 에 올리지 않음(RAM 부족). --device cpu 는 축소 모형 시험 전용'); sys.exit(1)
        log(f'모형 적재: {args.model} (CPU, 시험용)')
        model = ModelCls.from_pretrained(args.model, dtype=torch.float32, trust_remote_code=True)
    else:
        dm = {'model.language_model.embed_tokens': 'cuda:0', 'model.language_model.norm': 'cuda:1', 'model.language_model.rotary_emb': 'cuda:0', 'lm_head': 'cuda:0', 'model.visual': 'cuda:1'}
        for i in range(n_layers):
            dm[f'model.language_model.layers.{i}'] = 'cuda:0' if i < args.split_at else 'cuda:1'
        log(f'모형 적재: {args.model} (4비트, 층 {n_layers}개, SPLIT_AT={args.split_at})')
        model = ModelCls.from_pretrained(args.model, device_map=dm, dtype=torch.bfloat16, trust_remote_code=True,
                                         quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4', bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16))
        for name, module in model.named_modules():
            if hasattr(module, 'inv_freq'):
                m = re.search(r'layers\.(\d+)', name)
                if m:
                    module.inv_freq = module.inv_freq.to('cuda:0' if int(m.group(1)) < args.split_at else 'cuda:1')
    if args.lora:
        from peft import PeftModel
        log(f'어댑터 적재: {args.lora}')
        model = PeftModel.from_pretrained(model, args.lora)
    model.eval()
    log(f'적재 완료({time.time() - t0:.0f}초) · ' + ('CPU' if cpu else subprocess.run(['nvidia-smi', '--query-gpu=index,memory.used', '--format=csv,noheader'], capture_output=True, text=True).stdout.replace('\n', ' | ')))

    def gen(messages, temperature, max_tokens, thinking):
        # 이 PC의 기존 추론 서버(/mnt/share/corpus/scripts/corpus_api.py)와 같은 순서: 대화 틀을 글자로 펼친 뒤 토큰화해 첫 장치(GPU0)로 보냄
        text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=thinking)
        enc = tok(text, return_tensors='pt')
        ids = enc['input_ids'].to(dev); att = enc['attention_mask'].to(dev)
        if ids.shape[1] + max_tokens > args.ctx:
            raise ValueError(f'문맥 한도 초과: 입력 {ids.shape[1]}토큰 + 출력 {max_tokens}토큰 > {args.ctx}')
        kw = dict(max_new_tokens=max_tokens, pad_token_id=tok.pad_token_id)
        kw.update(dict(do_sample=True, temperature=temperature) if temperature and temperature > 0 else dict(do_sample=False))
        with torch.inference_mode():
            out = model.generate(input_ids=ids, attention_mask=att, **kw)
        new = out[0][ids.shape[1]:]
        return tok.decode(new, skip_special_tokens=True), int(ids.shape[1]), int(new.shape[0])
    return gen


def dry_gen(messages, temperature, max_tokens, thinking):
    """모의 응답: 주소와 형식만 확인한다."""
    last = messages[-1]['content']
    if last.startswith('[실행 결과]'):
        text = '결과\n- 모의 응답임(모형을 올리지 않음)\n\n유의 사항\n- 주소와 형식만 확인하는 시험임'
    else:
        text = "분석 계획\n- 모의 응답임\n\n```python\nimport ssda\nr = ssda.rate('bp_yn1 == 1', where='age >= 65')\nprint(r)\n```"
    return text, sum(len(m['content']) for m in messages) // 2, len(text) // 2


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code); self.send_header('Content-Type', 'application/json; charset=utf-8'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path.rstrip('/') == '/v1/models':
            return self._send(200, {'object': 'list', 'data': [{'id': STATE['name'], 'object': 'model', 'created': STATE['loaded_at'], 'owned_by': 'local'}]})
        self._send(404, {'error': {'message': '없는 주소'}})

    def do_POST(self):
        if self.path.rstrip('/') != '/v1/chat/completions':
            return self._send(404, {'error': {'message': '없는 주소'}})
        try:
            d = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))).decode('utf-8'))
            ms = [{'role': m['role'], 'content': m['content']} for m in d['messages']]
            thinking = bool((d.get('chat_template_kwargs') or {}).get('enable_thinking', False))
            t0 = time.time()
            with LOCK:
                text, n_in, n_out = STATE['gen'](ms, float(d.get('temperature') or 0), int(d.get('max_tokens') or 1500), thinking)
            # 사고 과정을 켠 요청: 이 모형의 대화 틀은 여는 표시 '<think>' 를 입력 끝에 넣으므로 출력에는 닫는 표시만 남는다(2026-11-14 대화 틀로 확인). 닫는 표시 앞을 버린다
            text = (text.rsplit('</think>', 1)[1] if '</think>' in text else text).strip()
            log(f'요청 처리: 입력 {n_in}토큰, 출력 {n_out}토큰, {time.time() - t0:.1f}초' + (f' ({n_out / max(time.time() - t0, 1e-9):.1f}토큰/초)' if n_out else ''))
            self._send(200, {'id': f'chatcmpl-{int(time.time() * 1000)}', 'object': 'chat.completion', 'created': int(time.time()), 'model': STATE['name'],
                             'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': text}, 'finish_reason': 'stop' if n_out < int(d.get('max_tokens') or 1500) else 'length'}],
                             'usage': {'prompt_tokens': n_in, 'completion_tokens': n_out, 'total_tokens': n_in + n_out}})
        except Exception as e:                                   # noqa: BLE001
            self._send(400, {'error': {'message': f'{type(e).__name__}: {e}'}})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default=os.environ.get('QWEN_BASE', 'NousResearch/Arete-27B')); ap.add_argument('--lora')
    ap.add_argument('--name', default='arete-27b'); ap.add_argument('--port', type=int, default=8080); ap.add_argument('--ctx', type=int, default=16384)
    ap.add_argument('--split-at', type=int, default=int(os.environ.get('QWEN_SPLIT_AT', '28'))); ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--device', choices=['cuda', 'cpu'], default='cuda', help='cpu 는 축소 모형으로 코드 경로를 시험할 때만 씀')
    a = ap.parse_args()
    STATE.update(name=a.name, loaded_at=int(time.time()), gen=dry_gen if a.dry_run else load(a))
    srv = ThreadingHTTPServer(('127.0.0.1', a.port), H)
    log(f"듣는 주소 http://127.0.0.1:{a.port}/v1 · 모형 이름 {a.name}" + (' · 모의 응답(모형 없음)' if a.dry_run else ''))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
