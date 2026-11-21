#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""학습 자료의 토큰 길이 측정 — 미세조정의 시퀀스 길이와 추론 서버의 문맥 길이를 정하는 근거.

  tokenizers 패키지와 모형의 tokenizer.json 이 필요하다(GPU 불필요).
  이 PC에서는  ~/anaconda3/envs/vllm/bin/python 04_training/token_stats.py
  기본 토크나이저: /mnt/share/corpus/models/adapters/chat_corpus_qwen_v1/tokenizer.json (Qwen3.8-27B, Arete-27B 와 같은 계열)

출력  04_training/data/token_stats.json
"""
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOK = sys.argv[1] if len(sys.argv) > 1 else '/mnt/share/corpus/models/adapters/chat_corpus_qwen_v1/tokenizer.json'


def main():
    from tokenizers import Tokenizer
    tok = Tokenizer.from_file(TOK); tok.no_truncation(); tok.no_padding()
    n = lambda t: len(tok.encode(t, add_special_tokens=False).ids)
    rows = [json.loads(l) for l in (ROOT / '04_training/data/train.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    full, noctx, asst, first = [], [], [], []
    for r in rows:
        t = t2 = a = 0
        for i, m in enumerate(r['messages']):
            c = m['content']; k = n(c) + 6; t += k
            t2 += n('[질문]' + c.split('[질문]')[-1]) + 6 if (m['role'] == 'user' and c.startswith('[참고 자료]')) else k
            a += k if m['role'] == 'assistant' else 0
            if i == 1:
                first.append(k)
        full.append(t); noctx.append(t2); asst.append(a)
    q = lambda xs, p: sorted(xs)[min(int(len(xs) * p), len(xs) - 1)]
    d = lambda xs: {'mean': round(statistics.mean(xs)), 'p50': q(xs, .5), 'p95': q(xs, .95), 'max': max(xs)}
    sysl = (ROOT / '03_prompts/system_prompt.md').read_text(encoding='utf-8'); syss = (ROOT / '03_prompts/system_prompt_short.md').read_text(encoding='utf-8')
    out = {'tokenizer': TOK, 'rows': len(rows), 'system_prompt_long': n(sysl), 'system_prompt_short': n(syss), 'first_user_message': d(first),
           'dialogue_full': d(full), 'dialogue_without_context': d(noctx), 'assistant_tokens': d(asst),
           'share_within': {str(L): {'full': round(sum(x <= L for x in full) / len(full), 3), 'without_context': round(sum(x <= L for x in noctx) / len(noctx), 3)} for L in (512, 1024, 1536, 2048, 3072, 4096, 6144)},
           'chars_per_token': round(sum(len(m['content']) for r in rows for m in r['messages']) / sum(full), 2)}
    (ROOT / '04_training/data/token_stats.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
