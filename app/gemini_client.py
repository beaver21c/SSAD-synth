# -*- coding: utf-8 -*-
"""Gemini API 연결부 — 조립기(Assistant)가 모형을 부르는 통로의 Gemini 판.

  원본 clients.OpenAICompatClient 와 같은 사용법(chat(messages) → 문자열, usage 집계)을 따른다.
  - 키는 HTTP 헤더(x-goog-api-key)로만 전달한다. 주소·기록 파일에 남기지 않는다.
  - 모형 이름을 지정하지 않으면 키로 쓸 수 있는 모형 목록을 받아 flash 계열 안정판을 먼저 쓴다.
  - 한도 초과(429)·지원 중단(404)·일시 장애(500·503)는 잠시 기다린 뒤 다시 부르고, 계속 실패하면 다음 모형으로 넘어간다.
  - 표준 라이브러리(urllib)만 쓴다.

  외부로 나가는 것: 질문, 참고 자료(변수 설명 등), 출력 통제를 거친 집계 결과. 개인 단위 자료는 나가지 않는다.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

BASE = 'https://generativelanguage.googleapis.com/v1beta'
KEY_ENV = 'GEMINI_API_KEY'
FALLBACK_MODELS = ['gemini-flash-latest', 'gemini-2.5-flash', 'gemini-2.0-flash']
THINK = re.compile(r'<think>.*?</think>', re.S)


class GeminiError(RuntimeError):
    def __init__(self, status, message):
        super().__init__(f'Gemini API 오류 (HTTP {status}): {message}')
        self.status = status


def rank_model(name):
    n = name.lower()
    if not n.startswith('gemini') or any(w in n for w in ('preview', 'exp', 'tts', 'image', 'embedding', 'live', 'audio', 'omni', 'transcribe', 'robotics', 'computer', 'banana', 'research')):
        return -1
    if 'flash-lite' in n:
        return 80
    if 'flash' in n:
        return 100
    if 'pro' in n:
        return 40
    return 10


def _request(url, key, body=None, timeout=120):
    headers = {'Content-Type': 'application/json'}
    if key:
        headers['x-goog-api-key'] = key
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8'), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:      # noqa: S310 — 고정된 Google API 주소
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode('utf-8'))['error']['message']
        except Exception:                                             # noqa: BLE001
            msg = e.reason
        raise GeminiError(e.code, str(msg)[:300]) from None


def list_models(key, timeout=20):
    d = _request(f'{BASE}/models?pageSize=200', key, timeout=timeout)
    names = [m['name'].replace('models/', '', 1) for m in d.get('models', []) if 'generateContent' in (m.get('supportedGenerationMethods') or [])]
    names = [n for n in names if rank_model(n) > 0]
    return sorted(names, key=lambda n: (-rank_model(n), [-ord(c) for c in n]))


def to_gemini(messages):
    """OpenAI 형식 대화 → (systemInstruction, contents). 같은 역할이 이어지면 하나로 합친다(Gemini는 역할 교대를 요구)."""
    system, contents = [], []
    for m in messages:
        if m['role'] == 'system':
            system.append(m['content'])
            continue
        role = 'model' if m['role'] == 'assistant' else 'user'
        if contents and contents[-1]['role'] == role:
            contents[-1]['parts'][0]['text'] += '\n\n' + m['content']
        else:
            contents.append({'role': role, 'parts': [{'text': m['content']}]})
    return ('\n\n'.join(system) or None), contents


class GeminiClient:
    def __init__(self, api_key=None, model=None, temperature=0.0, max_tokens=1500, timeout=120, retries=3, thinking_budget=0):
        self.key = api_key if api_key is not None else os.environ.get(KEY_ENV, '')
        self.model, self.temperature, self.max_tokens, self.timeout, self.retries = model, temperature, max_tokens, timeout, retries
        self.thinking_budget = thinking_budget
        self.models = None
        self.no_thinking_cfg = set()
        self.used_model = None
        self.usage = {'calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0}

    def candidates(self):
        if self.model:
            return [self.model]
        if self.models is None:
            try:
                self.models = list_models(self.key)[:5]
            except GeminiError as e:
                if e.status in (400, 401, 403):
                    raise
                self.models = []
            except Exception:                                         # noqa: BLE001
                self.models = []
            self.models = self.models or list(FALLBACK_MODELS)
        return self.models

    def _generate(self, model, system, contents, thinking=True):
        cfg = {'temperature': self.temperature, 'maxOutputTokens': self.max_tokens}
        if thinking and self.thinking_budget is not None:
            cfg['thinkingConfig'] = {'thinkingBudget': self.thinking_budget}
        else:
            cfg['maxOutputTokens'] = self.max_tokens * 3      # 사고 과정을 끌 수 없는 모형: 사고에 쓰이는 몫만큼 상한을 넉넉히 둠
        body = {'contents': contents, 'generationConfig': cfg}
        if system:
            body['systemInstruction'] = {'parts': [{'text': system}]}
        return _request(f'{BASE}/models/{model}:generateContent', self.key, body, self.timeout)

    def chat(self, messages):
        if not self.key:
            raise GeminiError(401, 'API 키가 없음')
        system, contents = to_gemini(messages)
        last = None
        for model in self.candidates():
            thinking = model not in self.no_thinking_cfg
            for attempt in range(self.retries):
                try:
                    d = self._generate(model, system, contents, thinking)
                except GeminiError as e:
                    last = e
                    if e.status == 400 and thinking and self.thinking_budget is not None:
                        thinking = False                               # 사고 설정을 받지 않는 모형: 설정 없이 다시 부르고 기억해 둠
                        self.no_thinking_cfg.add(model)
                        continue
                    if e.status in (429, 500, 503):
                        time.sleep(min(2 ** attempt * 3, 30))
                        continue
                    if e.status == 404:
                        break
                    raise
                u = d.get('usageMetadata') or {}
                self.usage['calls'] += 1
                self.usage['prompt_tokens'] += u.get('promptTokenCount', 0)
                self.usage['completion_tokens'] += u.get('candidatesTokenCount', 0)
                cand = (d.get('candidates') or [{}])[0]
                text = ''.join(p.get('text', '') for p in (cand.get('content') or {}).get('parts', []) if not p.get('thought'))
                if not text:
                    reason = cand.get('finishReason') or (d.get('promptFeedback') or {}).get('blockReason') or '빈 응답'
                    last = GeminiError(200, f'응답 본문 없음({reason})')
                    break
                self.used_model = model
                return THINK.sub('', text).strip()
        raise last or GeminiError(0, '사용할 수 있는 모형이 없음')

    def ping(self):
        try:
            return True, list_models(self.key)
        except Exception as e:                                        # noqa: BLE001
            return False, str(e)
