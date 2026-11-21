# -*- coding: utf-8 -*-
"""검색기 — 지식 자료(변수 카드·사업 카드·규칙·함수 문서·분석 요령)에서 질문과 관련된 문서를 찾는다.

외부 모형이나 패키지 없이 동작하는 BM25 방식이다(한글은 글자 2개 묶음과 낱말을 함께 색인).
임베딩 모형을 반입한 뒤에는 같은 인터페이스(search)로 교체하거나 결합할 수 있다.

  python3 06_build/retriever.py build          # 색인 생성 → 06_build/index/bm25.json, examples.json(유사 예시)
  python3 06_build/retriever.py "기초연금 수급률"  # 검색 시험
"""
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KN = ROOT / '01_knowledge'
IDX = Path(__file__).resolve().parent / 'index' / 'bm25.json'
EX = Path(__file__).resolve().parent / 'index' / 'examples.json'
SOURCES = ['variable_cards.jsonl', 'program_cards.jsonl', 'rules.jsonl', 'doc_cards.jsonl', 'programs/glossary_cards.jsonl']
K1, B = 1.4, 0.6


def tokens(text):
    text = text.lower()
    out = re.findall(r'[a-z0-9_]+', text)
    for w in re.findall(r'[가-힣]+', text):
        out.append(w)
        out += [w[i:i + 2] for i in range(len(w) - 1)]
    return out


def build():
    docs = []
    for name in SOURCES:
        p = KN / name
        if p.exists():
            docs += [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
    df, tfs, lens = Counter(), [], []
    for d in docs:
        tf = Counter(tokens(d['title'] + ' ' + d['title'] + ' ' + d['text']))      # 제목에 가중
        tfs.append(tf); lens.append(sum(tf.values())); df.update(tf.keys())
    N = len(docs); avg = sum(lens) / max(N, 1)
    idf = {t: math.log(1 + (N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
    IDX.parent.mkdir(parents=True, exist_ok=True)
    IDX.write_text(json.dumps({'docs': docs, 'tf': [dict(t) for t in tfs], 'len': lens, 'avg': avg, 'idf': idf}, ensure_ascii=False), encoding='utf-8')
    return N


def _write(docs, path):
    df, tfs, lens = Counter(), [], []
    for d in docs:
        tf = Counter(tokens(d['title'] + ' ' + d['title'] + ' ' + d['text']))
        tfs.append(tf); lens.append(sum(tf.values())); df.update(tf.keys())
    N = len(docs); avg = sum(lens) / max(N, 1)
    idf = {t: math.log(1 + (N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'docs': docs, 'tf': [dict(t) for t in tfs], 'len': lens, 'avg': avg, 'idf': idf}, ensure_ascii=False), encoding='utf-8')
    return N


def build_examples():
    """학습 자료(train)에서 「질문 → 첫 응답(분석 계획 + 코드, 또는 거절·확인 질문)」 쌍을 뽑아 예시 색인을 만든다.
    미세조정을 하지 않을 때 비슷한 질문의 처리 예를 프롬프트에 끼워 넣는 데 쓴다. 평가용 분할(valid·test)은 넣지 않는다."""
    p = ROOT / '04_training' / 'data' / 'train.jsonl'
    docs = []
    for l in p.read_text(encoding='utf-8').splitlines() if p.exists() else []:
        r = json.loads(l)
        if r['family'] in ('F18', 'F23'):                      # 오류 수정·결과 해석 유형은 질문에 코드·표가 들어 있어 제외
            continue
        ms = r['messages']
        q = ms[1]['content'].split('[질문]')[-1].strip()
        docs.append({'id': 'ex:' + r['id'], 'kind': 'example', 'family': r['family'], 'title': q, 'text': ms[2]['content'][:900]})
    return _write(docs, EX)


class Retriever:
    def __init__(self, path=IDX):
        d = json.loads(Path(path).read_text(encoding='utf-8'))
        self.docs, self.tf, self.len, self.avg, self.idf = d['docs'], d['tf'], d['len'], d['avg'], d['idf']

    def search(self, query, k=6, kinds=None, available_only=True):
        q = Counter(tokens(query))
        sc = []
        for i, tf in enumerate(self.tf):
            d = self.docs[i]
            if kinds and d['kind'] not in kinds:
                continue
            if available_only and d['kind'] == 'variable' and '자료에 값이 있는지: 없음' in d['text']:
                continue
            s = 0.0
            for t in q:
                f = tf.get(t)
                if f:
                    s += self.idf.get(t, 0) * f * (K1 + 1) / (f + K1 * (1 - B + B * self.len[i] / self.avg))
            if s > 0:
                sc.append((s, i))
        sc.sort(reverse=True)
        return [dict(self.docs[i], score=round(s, 2)) for s, i in sc[:k]]

    def get(self, doc_id):
        return next((d for d in self.docs if d['id'] == doc_id), None)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'build':
        print('색인 문서', build(), '건 →', IDX)
        print('예시 색인', build_examples(), '건 →', EX)
    else:
        r = Retriever()
        for d in r.search(' '.join(sys.argv[1:]) or '기초연금 수급률', k=6):
            print(d['score'], d['id'], '|', d['title'])
