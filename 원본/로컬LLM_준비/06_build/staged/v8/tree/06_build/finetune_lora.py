#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""미세조정 스크립트(QLoRA) — 대화 예시로 분석 지원 동작을 익히게 한다.

출처와 검증 범위
  · 모형 적재, 수동 GPU 분할, LoRA 대상 모듈, 학습 루프, 체크포인트 재개는 /mnt/share/corpus/scripts/train_cpt_qwen.py 에서 옮겼다.
    그 스크립트는 이 PC(RTX 5060 Ti 16GB × 2)에서 Qwen3.8-27B 에 KIHASA 코퍼스를 학습시켜 완주했다(2026-08-23, 71.7시간, 시퀀스 512토큰, SPLIT_AT=28).
  · 이 스크립트에서 새로 쓴 부분 가운데 대화 형식 자료의 토큰화와 응답 구간 표시는 내려받은 Arete-27B 의 토크나이저와 대화 틀로 CPU 에서 확인했다
    (check_model.py, 2026-11-14: 학습 자료 1,179건 모두 응답 구간 표시 성공). 응답 구간에만 거는 손실로 학습하는 것과 512토큰보다 긴 시퀀스는 GPU 에서 실행해 본 적이 없다.
  · 기반이 Arete-27B 일 때의 적재 전제도 GPU 없이 확인했다(같은 날): 이 환경의 transformers 5.8.0 이 만든 빈 모형 골격과 가중치 파일의 이름·모양이 모두 같고,
    수동 GPU 분할 경로가 모든 가중치를 덮으며, LoRA 대상 모듈 12종이 있다. Arete-27B 를 실제로 GPU 에 올린 적은 없다.
  · 대화 예시는 참고 자료를 포함하면 평균 2,619토큰(최대 4,228)이고 참고 자료를 빼면 평균 973토큰, 95.4%가 1,536토큰 이내다(Arete-27B 토크나이저와 대화 틀 실측).
    512토큰에서만 성공한 이력이 있으므로 --context none --max-len 1536 부터 스모크 시험으로 확인한다. 메모리가 부족하면 부족한 GPU 쪽 층을 줄이도록 --split-at 을 옮기거나
    (cuda:0 부족이면 줄이고 cuda:1 부족이면 늘림) --max-len 을 낮춘다.
  · 학습 루프 전체(LoRA 부착 → 응답 구간 손실 → 역전파 → 갱신 → 체크포인트 저장·재개 → 어댑터 저장)는 구조가 같은 축소 모형으로 CPU 에서 끝까지 실행해 확인했다
    (cpu_selftest.py, 2026-11-15: 실제 학습 자료와 1,536토큰 상한 사용). 확인된 것은 코드 경로이며, 27B 원본에서의 메모리 소요와 학습 효과는 GPU 에서만 확인된다.

  · GPU 첫 실행(2026-11-16, Arete-27B, 1,536토큰)에서 고친 것
      ① 메모리 부족의 원인은 출력층이었다. 어휘가 248,320개여서 모형의 기본 손실은 1,536토큰 전체 위치의 로짓을 float32 로 만들고(1.42GiB) 같은 크기의 텐서를 여러 개 더 쓴다.
         이것이 임베딩(2.37GiB)·출력층(2.37GiB)·앞쪽 층과 함께 cuda:0 에 몰려 분할 위치 24~28, 길이 상한 1,280~1,536 의 7회 시도가 모두 실패했다.
         → 출력층(lm_head)을 마지막 층과 같은 cuda:1 로 옮기고, 응답 구간 위치만 골라 128개씩 나눠 손실을 구한다(loss_backward. 값과 기울기는 기본 손실과 같음: 축소 모형 대조).
      ② 분할 위치 28 에서는 적재 자체가 실패했다. transformers 5.8.0 의 초기화 함수가 이미 적재된 출력층 가중치의 float32 사본(4.74GiB)을 만들었다가 버리기 때문이다
         → 적재된 큰 가중치는 초기화를 건너뛰게 함. 분할 위치 기본값은 두 GPU 의 적재량이 비슷해지는 34 로 바꿈(임베딩 + 앞 34층 / 출력층 + 뒤 30층 + 시각 모듈)

순서  ① 미세조정 없이 평가(06_build/eval_run.py) → ② 기준 미달 지표 확인 → ③ --smoke 로 적재·역전파 확인 → ④ 본 학습 → ⑤ 다시 평가
입력  04_training/data/train.jsonl (대화 형식: messages = system / user / assistant …)
출력  <out>/ (PEFT 어댑터, training_meta.json) — 추론 서버에 올리는 방법은 구축지시서 6단계

  --check-data              학습 자료만 점검(기계학습 패키지 불필요, 지금 실행 가능)
  --smoke                   모형 적재 + LoRA 부착 + 2 step 만 수행
  --base ID                 기반 모형(기본 NousResearch/Arete-27B, 환경변수 QWEN_BASE). 코퍼스 어댑터를 이어 쓰려면 Qwen/Qwen3.8-27B
  --init-adapter 경로       기존 어댑터에서 이어서 학습(예: /mnt/share/corpus/models/adapters/chat_corpus_qwen_v1). 그 어댑터는 Qwen/Qwen3.8-27B 위에서 학습된 것이다.
                            Arete-27B 에도 대상 모듈 496개가 같은 모양으로 있어 부착은 되지만(check_model.py) 효과는 확인되지 않았으므로 평가로 비교한 뒤에 쓴다
  --context full|none       참고 자료 카드를 넣을지(기본 none: [질문]만 남김)
  --max-len N               시퀀스 길이 상한(기본 1536)
  --device cpu              축소 모형(make_tiny_twin.py)으로 코드 경로를 시험할 때만 씀. 4비트 적재와 GPU 분할을 건너뜀. 27B 원본은 CPU 에 올리지 않는다
  --limit N / --save-every N  학습 예시 수 제한 / 체크포인트 간격(기본 100 step) — 시험용

실행 환경  conda 환경 vllm (peft 0.19.1, transformers 5.8, torch 2.11 — 위 학습이 완주한 환경). GPU 2장을 모두 쓰므로 다른 작업과 함께 돌릴 수 없다.
"""
import argparse
import gc
import glob
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / '04_training' / 'data'


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def read(split):
    return [json.loads(l) for l in (DATA / f'{split}.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]


def strip_context(messages):
    """참고 자료 카드를 빼고 [질문]만 남긴다(시퀀스 길이를 줄이기 위함). 「용어 확인」 문단은 남긴다."""
    out = []
    for m in messages:
        c = m['content']
        if m['role'] == 'user' and c.startswith('[참고 자료]'):
            note = c[c.find('■ 용어 확인'):c.find('[질문]')] if '■ 용어 확인' in c else ''
            c = (f'[참고 자료]\n{note}' if note else '') + '[질문]' + c.split('[질문]')[-1]
        out.append({'role': m['role'], 'content': c})
    return out


def encode_dialogue(tok, messages, max_len):
    """대화 전체를 토큰으로 바꾸고 응답 구간만 정답(labels)으로 남긴다. 대화 틀이 앞부분을 그대로 잇지 않으면 None.
    06_build/check_model.py 가 실제 토크나이저로 전체 학습 자료에 적용해 확인한다(GPU 불필요)."""
    ids, labels = [], []
    for i, m in enumerate(messages):
        if m['role'] != 'assistant':
            continue
        prefix = _ids(tok.apply_chat_template(messages[:i], tokenize=True, add_generation_prompt=True, enable_thinking=False))
        upto = _ids(tok.apply_chat_template(messages[:i + 1], tokenize=True, add_generation_prompt=False, enable_thinking=False))
        if upto[:len(prefix)] != prefix or prefix[:len(ids)] != ids:
            return None
        labels += [-100] * (len(prefix) - len(ids)) + upto[len(prefix):]
        ids = upto
    return (ids[:max_len], labels[:max_len]) if ids and any(x != -100 for x in labels[:max_len]) else None


def _ids(x):
    """apply_chat_template 의 반환형이 판에 따라 목록 또는 사전이므로 토큰 목록으로 맞춘다."""
    if isinstance(x, dict) or hasattr(x, 'keys'):
        x = x['input_ids']
    return list(x[0]) if x and isinstance(x[0], (list, tuple)) else list(x)


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


def check_data():
    rep = {}
    for sp in ('train', 'valid', 'test'):
        rows = read(sp)
        chars = sorted(sum(len(m['content']) for m in r['messages']) for r in rows)
        short = sorted(sum(len(m['content']) for m in strip_context(r['messages'])) for r in rows)
        bad = [r['id'] for r in rows if r['messages'][0]['role'] != 'system' or r['messages'][-1]['role'] != 'assistant']
        rep[sp] = {'rows': len(rows), 'families': dict(sorted(Counter(r['family'] for r in rows).items())), 'chars_mean': round(sum(chars) / len(chars)), 'chars_max': chars[-1],
                   'chars_mean_no_context': round(sum(short) / len(short)), 'chars_max_no_context': short[-1], 'bad_role_order': bad}
    v = DATA / 'validation_report.json'
    rep['validation_passed'] = json.loads(v.read_text(encoding='utf-8')).get('passed') if v.exists() else None
    t = ROOT / '04_training' / 'data' / 'token_stats.json'
    rep['token_stats'] = json.loads(t.read_text(encoding='utf-8')) if t.exists() else '미측정(04_training/token_stats.py)'
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0 if rep['validation_passed'] and not any(rep[s]['bad_role_order'] for s in ('train', 'valid', 'test')) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check-data', action='store_true'); ap.add_argument('--smoke', action='store_true')
    ap.add_argument('--base', default=os.environ.get('QWEN_BASE', 'NousResearch/Arete-27B'))
    ap.add_argument('--init-adapter'); ap.add_argument('--out', default=str(ROOT / '06_build' / 'runs' / 'lora_assistant_v1'))
    ap.add_argument('--context', choices=['full', 'none'], default='none'); ap.add_argument('--max-len', type=int, default=1536)
    ap.add_argument('--epochs', type=int, default=3); ap.add_argument('--lr', type=float, default=1e-4)
    ap.add_argument('--split-at', type=int, default=int(os.environ.get('QWEN_SPLIT_AT', '34'))); ap.add_argument('--no-4bit', action='store_true')
    ap.add_argument('--device', choices=['cuda', 'cpu'], default='cuda'); ap.add_argument('--limit', type=int); ap.add_argument('--save-every', type=int, default=100)
    a = ap.parse_args()
    if a.check_data:
        return check_data()

    # ── 여기부터는 학습 패키지가 필요하다. GPU 는 --device cuda(기본)일 때 쓴다 ──────────────────────────────
    cpu = a.device == 'cpu'
    if cpu:
        os.environ['CUDA_VISIBLE_DEVICES'] = ''              # torch 를 부르기 전에 GPU 를 가림(GPU 에 아무것도 올리지 않음)
    else:
        used = subprocess.run(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'], capture_output=True, text=True).stdout.split()
        if sum(int(x) for x in used if x.isdigit()) > 4000 and os.environ.get('FORCE') != '1':
            log('GPU 를 다른 작업이 사용 중임. 종료 후 다시 실행할 것(FORCE=1 로 무시 가능)'); return 1

    base_id, a.base = a.base, resolve_model(a.base)           # 모형 캐시에 있으면 그 폴더를 씀(내려받지 않음)
    os.environ.setdefault('PYTORCH_CUDA_ALLOC_CONF', 'expandable_segments:True')      # 예약만 되고 쓰이지 않는 GPU 메모리(조각남)를 줄임
    import torch
    from peft import LoraConfig, PeftModel, TaskType, get_peft_model, set_peft_model_state_dict
    from torch.optim import AdamW
    from torch.utils.data import DataLoader, Dataset
    from transformers import AutoConfig, AutoTokenizer, BitsAndBytesConfig, get_cosine_schedule_with_warmup
    # 체크포인트는 Qwen3_5ForConditionalGeneration 구조다. AutoModelForCausalLM 을 쓰면 키가 어긋나 전 파라미터가 새로 초기화된다(원본 스크립트의 실측 기록).
    from transformers import Qwen3_5ForConditionalGeneration as ModelCls
    try:                                                      # 병렬 적재 단일 스레드 강제, 할당기 예열 생략 — 원본과 같은 처방
        import transformers.core_model_loading as _cml; _cml.GLOBAL_WORKERS = 1
    except Exception:
        pass
    try:
        import transformers.modeling_utils as _mu; _mu.caching_allocator_warmup = lambda *x, **k: None
    except Exception:
        pass

    try:                                                      # 이미 적재된 큰 선형 가중치(출력층)는 초기화를 건너뜀: 초기화 함수가 float32 사본(4.74GiB)을 GPU 에 만들었다가 버리는 것을 막음.
        _owner = next(c for c in ModelCls.__mro__ if '_init_weights' in c.__dict__)          # 적재 표시(_is_hf_initialized)가 있는 가중치는 원래도 값이 바뀌지 않음
        _orig_init = _owner._init_weights

        def _init_skip_loaded(self, module):
            w = getattr(module, 'weight', None)
            if isinstance(module, torch.nn.Linear) and w is not None and getattr(w, '_is_hf_initialized', False) and w.numel() > 5e8:
                return None
            return _orig_init(self, module)
        _owner._init_weights = _init_skip_loaded
    except Exception:
        pass

    NUM_LAYERS, SPLIT_AT = AutoConfig.from_pretrained(a.base, trust_remote_code=True).text_config.num_hidden_layers, a.split_at
    BATCH_SIZE, GRAD_ACCUM, LORA_R, LORA_ALPHA, SAVE_EVERY, LOG_EVERY = 1, 4, 32, 64, a.save_every, 10
    DEV = 'cpu' if cpu else 'cuda:0'
    if cpu and NUM_LAYERS > 16 and os.environ.get('FORCE') != '1':
        log(f'층이 {NUM_LAYERS}개인 모형은 CPU 에 올리지 않음(RAM 부족). --device cpu 는 축소 모형 시험 전용'); return 1
    TARGET_MODULES = ['q_proj', 'k_proj', 'v_proj', 'o_proj',                                   # 표준 주의 층 16개
                      'in_proj_qkv', 'in_proj_a', 'in_proj_b', 'in_proj_z', 'out_proj',         # 선형 주의 층 48개
                      'gate_proj', 'up_proj', 'down_proj']                                      # MLP 64개 층
    EXCLUDE_MODULES = r'.*(visual|vision_tower|mtp)\..*'
    OUT = a.out; os.makedirs(OUT, exist_ok=True)

    log(f'토크나이저: {a.base}')
    tok = AutoTokenizer.from_pretrained(a.base, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    # 출력층(lm_head)은 마지막 층·최종 정규화와 같은 cuda:1 에 둔다: 손실 계산의 일시 메모리가 임베딩과 앞쪽 층이 있는 cuda:0 에 겹치지 않게 함
    device_map = {'model.language_model.embed_tokens': 'cuda:0', 'model.language_model.norm': 'cuda:1', 'model.language_model.rotary_emb': 'cuda:0', 'lm_head': 'cuda:1', 'model.visual': 'cuda:1'}
    for i in range(NUM_LAYERS):
        device_map[f'model.language_model.layers.{i}'] = 'cuda:0' if i < SPLIT_AT else 'cuda:1'
    kw = dict(device_map=device_map, dtype=torch.bfloat16, trust_remote_code=True)
    if not a.no_4bit:
        kw['quantization_config'] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4', bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
    if cpu:                                                   # 축소 모형 시험: 양자화와 GPU 분할 없이 CPU 에 올림
        kw = dict(dtype=torch.float32, trust_remote_code=True)
    log('모형 적재 중' + (' (CPU, 시험용)' if cpu else '')); t0 = time.time()
    model = ModelCls.from_pretrained(a.base, **kw)
    log(f'적재 완료({time.time() - t0:.0f}초)' + ('' if cpu else ' · GPU 메모리 ' + ', '.join(f'cuda:{i} {torch.cuda.memory_allocated(i) / 2 ** 30:.1f}GiB' for i in range(torch.cuda.device_count()))))
    for name, module in model.named_modules():                # rotary inv_freq 를 해당 층의 GPU 로 옮김
        if hasattr(module, 'inv_freq') and not cpu:
            m = re.search(r'layers\.(\d+)', name)
            if m:
                module.inv_freq = module.inv_freq.to('cuda:0' if int(m.group(1)) < SPLIT_AT else 'cuda:1')

    if a.init_adapter:                                        # 코퍼스 어댑터에서 이어서 학습
        log(f'기존 어댑터에서 시작: {a.init_adapter}')
        model = PeftModel.from_pretrained(model, a.init_adapter, is_trainable=True)
    else:
        model = get_peft_model(model, LoraConfig(task_type=TaskType.CAUSAL_LM, r=LORA_R, lora_alpha=LORA_ALPHA, lora_dropout=0.0, target_modules=TARGET_MODULES, exclude_modules=EXCLUDE_MODULES, bias='none'))
    model.print_trainable_parameters()
    hit = Counter('linear_attn' if '.linear_attn.' in n else 'self_attn' if '.self_attn.' in n else 'mlp' if '.mlp.' in n else '기타' for n, _ in model.named_modules() if 'lora_A' in n)
    log(f'LoRA 부착 분포: {dict(hit)}')
    if not hit.get('linear_attn'):
        log('[중단] 선형 주의 층에 LoRA 가 붙지 않음. TARGET_MODULES 를 실제 모듈 이름과 대조할 것'); return 1
    for path in ('base_model.model.model.language_model', 'base_model.model.model', 'base_model.model', ''):
        try:
            tgt = model
            for p in filter(None, path.split('.')):
                tgt = getattr(tgt, p)
            tgt.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False}); log(f'gradient checkpointing 켬({path or "self"})'); break
        except Exception:
            continue

    encode = lambda messages: encode_dialogue(tok, messages, a.max_len)      # 대화 전체를 토큰으로 바꾸고 응답 구간만 정답으로 남김

    core = model.get_base_model()                             # LoRA 가 끼워진 원 모형
    HEAD_DEV, CHUNK = core.lm_head.weight.device, 128
    gpu_peak = lambda: ', '.join(f'cuda:{i} {torch.cuda.max_memory_allocated(i) / 2 ** 30:.1f}GiB(예약 {torch.cuda.max_memory_reserved(i) / 2 ** 30:.1f}GiB)' for i in range(torch.cuda.device_count()))

    def loss_backward(batch, scale):
        """응답 구간 위치만 출력층에 통과시켜 손실을 구하고 역전파한다. 값은 모형의 기본 손실(다음 토큰 교차 엔트로피의 응답 구간 평균)과 같다.
        ① 마지막 은닉 상태에서 정답이 있는 위치만 고르고 ② CHUNK 개씩 나눠 로짓·손실을 구해 은닉 상태에 대한 기울기로 모은 뒤 ③ 그 기울기를 모형 쪽으로 한 번 역전파한다.
        출력층 가중치는 학습 대상이 아니므로(LoRA 대상 아님) 나눠 구해도 기울기가 같다. 전체 위치의 로짓을 한꺼번에 만들지 않으므로 일시 메모리는 CHUNK × 어휘 수에 비례한다."""
        hs = core.model(input_ids=batch['input_ids'], attention_mask=batch['attention_mask'], use_cache=False)[0]
        tgt = batch['labels'][:, 1:]
        keep = tgt != -100
        h = hs[:, :-1][keep.to(hs.device)]                      # (정답 위치 수, 은닉 크기)
        y = tgt[keep].to(HEAD_DEV)
        hd = h.detach().to(HEAD_DEV).requires_grad_(True)
        n, total = y.numel(), 0.0
        for i in range(0, n, CHUNK):
            part = torch.nn.functional.cross_entropy(core.lm_head(hd[i:i + CHUNK]).float(), y[i:i + CHUNK], reduction='sum') / n
            part.backward(); total += part.item()
        h.backward(hd.grad.to(h.device, h.dtype) * scale)
        return total

    class DS(Dataset):
        def __init__(self, rows):
            self.s, self.skip, self.cut = [], 0, 0
            for r in rows:
                ms = r['messages'] if a.context == 'full' else strip_context(r['messages'])
                e = encode(ms)
                if e is None:
                    self.skip += 1; continue
                self.cut += len(e[0]) >= a.max_len
                self.s.append(e)

        def __len__(self):
            return len(self.s)

        def __getitem__(self, i):
            return self.s[i]

    def collate(batch):
        mx = max(len(x[0]) for x in batch)
        return {'input_ids': torch.tensor([x[0] + [tok.pad_token_id] * (mx - len(x[0])) for x in batch]),
                'attention_mask': torch.tensor([[1] * len(x[0]) + [0] * (mx - len(x[0])) for x in batch]),
                'labels': torch.tensor([x[1] + [-100] * (mx - len(x[1])) for x in batch])}

    rows = read('train')[:a.limit]                         # 스모크 시험도 전체에서 고름(가장 긴 예시로 메모리 소요를 확인하기 위함)
    ds = DS(rows)
    if a.smoke:                                            # 가장 긴 예시 8건을 긴 순서로 넣음: 2 step(8건)이 통과하면 본 학습의 최대 길이에서도 메모리가 충분함
        ds.s = sorted(ds.s, key=lambda e: -len(e[0]))[:8]
        log(f'스모크 시험 예시 길이(토큰): {[len(e[0]) for e in ds.s]}')
    log(f'학습 예시 {len(ds)}건(대화 틀 불일치로 제외 {ds.skip}건, 길이 상한에 걸린 예시 {ds.cut}건, 상한 {a.max_len}토큰, 참고 자료 {a.context})')
    loader = DataLoader(ds, batch_size=BATCH_SIZE, shuffle=not a.smoke, collate_fn=collate)
    total = max(1, (len(loader) * a.epochs) // GRAD_ACCUM)
    opt = AdamW([p for p in model.parameters() if p.requires_grad], lr=a.lr, weight_decay=0.01)
    sch = get_cosine_schedule_with_warmup(opt, num_warmup_steps=min(100, total // 20), num_training_steps=total)

    start = 0
    cks = sorted(glob.glob(f'{OUT}/checkpoint-*'), key=lambda p: int(p.split('-')[-1]))
    if cks and not a.smoke:                                   # 체크포인트 재개(스케줄러도 재개 지점까지 진행)
        from safetensors.torch import load_file
        sd = os.path.join(cks[-1], 'adapter_model.safetensors')
        if os.path.exists(sd):
            set_peft_model_state_dict(model, load_file(sd))
        st = os.path.join(cks[-1], 'trainer_state.json')
        start = json.load(open(st)).get('step', 0) if os.path.exists(st) else 0
        for _ in range(start):
            sch.step()
        log(f'체크포인트 재개: step {start}')

    def save_ckpt(step):
        d = f'{OUT}/checkpoint-{step}'; os.makedirs(d, exist_ok=True)
        model.save_pretrained(d); json.dump({'step': step}, open(f'{d}/trainer_state.json', 'w'))
        for old in sorted(glob.glob(f'{OUT}/checkpoint-*'), key=lambda p: int(p.split('-')[-1]))[:-3]:
            subprocess.run(['rm', '-rf', old])

    model.train()
    if a.smoke and cpu:                                       # 축소 모형(CPU): 나눠 구한 손실·기울기가 모형의 기본 손실과 같은지 대조
        b0 = {k: v.to(DEV) for k, v in next(iter(loader)).items()}
        ps = [p for p in model.parameters() if p.requires_grad]
        ref = model(**b0, use_cache=False).loss; ref.backward()
        g_ref = [None if p.grad is None else p.grad.clone() for p in ps]
        opt.zero_grad(set_to_none=True)
        mine = loss_backward(b0, 1.0)
        pairs = [(p.grad, g) for p, g in zip(ps, g_ref) if g is not None and p.grad is not None]
        diff, gmax = max(float((x - g).abs().max()) for x, g in pairs), max(float(g.abs().max()) for _, g in pairs)
        opt.zero_grad(set_to_none=True)
        log(f'손실 대조(축소 모형): 기본 {ref.item():.6f}, 나눠 구한 값 {mine:.6f}, 기울기 최대 차이 {diff:.2e}(기울기 최대 {gmax:.2e}, 대조한 텐서 {len(pairs)}개)')
        if abs(ref.item() - mine) > 1e-4 * max(1.0, abs(ref.item())) or diff > 1e-3 * max(gmax, 1e-8) or len(pairs) != sum(g is not None for g in g_ref):
            log('[중단] 나눠 구한 손실·기울기가 모형의 기본 손실과 다름'); return 1
    t_start = time.time(); step, micro, done, reached, oom = start, 0, 0, False, 0
    for _ in range(a.epochs):
        if reached:
            break
        for batch in loader:
            if step >= total:
                reached = True; break
            batch = {k: v.to(DEV) for k, v in batch.items()}
            t_b, short = time.time(), False
            try:
                loss = loss_backward(batch, 1.0 / GRAD_ACCUM)
            except torch.OutOfMemoryError:
                if a.smoke or oom >= 20:
                    raise
                short = True
            if short:                                         # 본 학습 중 메모리 부족: 그 예시를 건너뛰고 이 step 에 모아 둔 기울기를 버린 뒤 계속함(20건을 넘으면 중단)
                oom += 1; opt.zero_grad(set_to_none=True); micro -= micro % GRAD_ACCUM; gc.collect(); torch.cuda.empty_cache()
                log(f"[경고] GPU 메모리 부족으로 예시 1건({batch['input_ids'].shape[1]}토큰)을 건너뜀(누적 {oom}건)"); continue
            micro += 1
            if a.smoke:
                log(f"예시 {micro}: {batch['input_ids'].shape[1]}토큰(응답 구간 {int((batch['labels'][:, 1:] != -100).sum())}토큰), 손실 {loss:.4f}, {time.time() - t_b:.1f}초" + ('' if cpu else ' · GPU 최고 ' + gpu_peak()))
                if not cpu and micro == 1 and not loss < 8:
                    log('[중단] 첫 손실 값이 무작위 가중치 수준임(가중치 적재 이상). 적재 경로를 확인할 것'); return 1
            if micro % GRAD_ACCUM == 0:
                torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
                opt.step(); sch.step(); opt.zero_grad(set_to_none=True); step += 1; done += 1
                if step % LOG_EVERY == 0 or a.smoke:
                    el = time.time() - t_start
                    log(f'step {step}/{total} loss={loss:.4f} lr={sch.get_last_lr()[0]:.2e} 경과={el / 60:.0f}분 남은={(total - step) / (done / el) / 60:.0f}분 step당={el / done:.0f}초' + ('' if cpu or step % 50 else ' · GPU 최고 ' + gpu_peak()))
                if not a.smoke and step % SAVE_EVERY == 0:
                    save_ckpt(step)
                if a.smoke and done >= 2:
                    if not cpu:
                        log('GPU 메모리 최고 사용량: ' + gpu_peak())
                    log('스모크 시험 통과: 적재·LoRA·순전파·역전파·갱신 정상'); return 0
    model.save_pretrained(OUT); tok.save_pretrained(OUT)
    json.dump({'base': base_id, 'base_path': a.base, 'init_adapter': a.init_adapter, 'context': a.context, 'max_len': a.max_len, 'split_at': SPLIT_AT, 'lora_r': LORA_R, 'lora_alpha': LORA_ALPHA,
               'target_modules': TARGET_MODULES, 'epochs': a.epochs, 'steps': step, 'examples': len(ds), 'hours': round((time.time() - t_start) / 3600, 2), 'oom_skipped': oom, 'loss': 'response-span, chunked'},
              open(f'{OUT}/training_meta.json', 'w'), ensure_ascii=False, indent=2)
    log(f'학습 완료 → {OUT}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
