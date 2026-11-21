# -*- coding: utf-8 -*-
"""모형 연결부 — 조립기가 모형을 부르는 유일한 통로.

  OpenAICompatClient  로컬 추론 서버(llama.cpp server, vLLM, Ollama 등)의 OpenAI 호환 주소(/v1/chat/completions)를 부른다.
                      표준 라이브러리(urllib)만 쓴다. 폐쇄망 안의 주소만 지정한다.
                      서버가 오류를 돌려주면 내용을 담아 RuntimeError 로 알린다(평가 실행기가 그 문항만 건너뛰고 계속함).
                      llama.cpp 서버가 생성 결과를 해석하지 못해 500 을 돌려준 경우에는 대화 틀만 적용한 원문 생성(흘려 받기)으로 한 번 더 받는다.
  MockClient          모형 없이 조립기·채점기 전 과정을 점검하는 모의 모형.
                        oracle  평가 문항의 정답 코드를 그대로 답한다(조립기·채점기가 바르면 만점이 나와야 함)
                        naive   준비 없이 일반 모형을 붙였을 때를 흉내 낸다(자료 파일을 직접 읽는 코드 → 실행 전 점검에서 차단)
                        sloppy  대상 조건을 빠뜨리고 실행 결과에 없는 수치를 적는 모형을 흉내 낸다(검증 단계가 잡아내는지 확인)
"""
import json
import re
import time
import urllib.error
import urllib.request

THINK = re.compile(r'<think>.*?</think>', re.S)


class OpenAICompatClient:
    def __init__(self, base_url, model, api_key='', temperature=0.0, max_tokens=1500, timeout=600, extra_body=None):
        self.url = base_url.rstrip('/') + '/chat/completions'
        self.model, self.key, self.temperature, self.max_tokens, self.timeout = model, api_key, temperature, max_tokens, timeout
        self.extra = dict(extra_body or {})
        self.usage = {'calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'raw_fallbacks': 0}

    def _post(self, url, body):
        req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                     headers={'Content-Type': 'application/json', **({'Authorization': f'Bearer {self.key}'} if self.key else {})})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:      # noqa: S310 — 설정 파일에 적힌 폐쇄망 안 주소
            return json.loads(r.read().decode('utf-8', errors='replace'))

    def _raw(self, messages):
        """llama.cpp 서버 전용 예비 경로: 대화 틀을 적용한 글자열을 받아(/apply-template) 원문 생성(/completion, 흘려 받기)으로 응답을 받는다.
        서버가 생성 결과를 해석하지 못했을 때만 쓴다. 원인은 출력에 온전하지 않은 UTF-8 글자가 들어간 경우로 확인됨(2026-11-15, llama.cpp 7ea23dd:
        길이 상한에서 여러 토큰으로 된 글자 중간에 끊기는 경우 등). 흘려 받기는 조각마다 글자를 그대로 보내므로 그 해석 단계를 거치지 않는다."""
        root = self.url.rsplit('/v1/chat/completions', 1)[0]
        prompt = self._post(root + '/apply-template', {'messages': messages, **{k: v for k, v in self.extra.items() if k == 'chat_template_kwargs'}})['prompt']
        body = {'prompt': prompt, 'n_predict': self.max_tokens, 'temperature': self.temperature, 'cache_prompt': True, 'stream': True}
        req = urllib.request.Request(root + '/completion', data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                     headers={'Content-Type': 'application/json', **({'Authorization': f'Bearer {self.key}'} if self.key else {})})
        parts, u = [], {}
        with urllib.request.urlopen(req, timeout=self.timeout) as r:      # noqa: S310
            for line in r:
                line = line.decode('utf-8', errors='replace').strip()
                if not line.startswith('data:'):
                    continue
                try:
                    d = json.loads(line[5:])
                except ValueError:
                    continue
                if 'content' not in d:                                    # 끝에서 오류 조각이 오면 그때까지 받은 글자를 씀
                    break
                parts.append(d.get('content') or '')
                if d.get('stop'):
                    u = {'prompt_tokens': d.get('tokens_evaluated', 0), 'completion_tokens': d.get('tokens_predicted', 0)}
                    break
        if not parts:
            raise RuntimeError('원문 생성에서 받은 글자가 없음')
        if not u:                                                         # 끝 조각이 오류로 대체된 경우: 토큰 수를 따로 셈(출력은 받은 조각 수, 입력은 서버의 토큰화 결과)
            try:
                n_in = len(self._post(root + '/tokenize', {'content': prompt, 'add_special': False, 'parse_special': True}).get('tokens') or [])
            except Exception:                                             # noqa: BLE001
                n_in = 0
            u = {'prompt_tokens': n_in, 'completion_tokens': sum(1 for x in parts if x)}
        return ''.join(parts), u

    def chat(self, messages):
        body = {'model': self.model, 'messages': messages, 'temperature': self.temperature, 'max_tokens': self.max_tokens, 'stream': False, **self.extra}
        try:
            for wait in range(181):                                       # 서버가 모형을 올리는 중(503 Loading model)이면 최대 15분 기다림
                try:
                    d = self._post(self.url, body)
                    break
                except urllib.error.HTTPError as e:
                    if e.code == 503 and wait < 180:
                        msg = e.read().decode('utf-8', errors='replace')[:200]
                        if 'Loading model' in msg:
                            time.sleep(5)
                            continue
                        raise RuntimeError(f'추론 서버 오류 503: {msg}') from None
                    raise
            u, text = d.get('usage') or {}, d['choices'][0]['message'].get('content') or ''
        except urllib.error.HTTPError as e:
            detail = e.read().decode('utf-8', errors='replace')[:400]
            if e.code == 500 and 'Failed to parse' in detail:
                try:
                    text, u = self._raw(messages)
                    self.usage['raw_fallbacks'] += 1
                except Exception as e2:                                   # noqa: BLE001
                    raise RuntimeError(f'추론 서버 오류 500(응답 해석 실패), 원문 생성도 실패: {e2}') from None
            else:
                raise RuntimeError(f'추론 서버 오류 {e.code}: {detail}') from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise RuntimeError(f'추론 서버 연결 실패({self.url}): {e}') from None
        self.usage['calls'] += 1
        self.usage['prompt_tokens'] += u.get('prompt_tokens', 0); self.usage['completion_tokens'] += u.get('completion_tokens', 0)
        if '</think>' in text and '<think>' not in text:                  # 여는 표시가 입력 쪽에 있는 대화 틀(Arete-27B): 닫는 표시 앞을 버림
            text = text.rsplit('</think>', 1)[1]
        return THINK.sub('', text).strip()                                # 사고 과정 출력이 섞여 오면 제거

    def warmup(self, system):
        """llama.cpp 서버 전용 예열: 시스템 프롬프트만 담은 짧은 요청을 한 번 보내 서버가 그 구간에 상태 저장 지점(context checkpoint)을 남기게 한다.
        이 모형 구조(qwen35, 순환 상태를 가진 층이 섞임)는 llama.cpp 가 프롬프트 앞부분을 임의 위치에서 이어 쓰지 못하므로, 저장 지점이 없으면
        질문이 바뀔 때마다 시스템 프롬프트를 처음부터 다시 처리한다(2026-11-15 CPU 구동 기록: 13문항 모두 전체 재처리).
        서버는 요청 끝에서 약 516토큰 앞에 저장 지점을 만들므로, 예열 뒤에는 시스템 프롬프트의 앞부분(전체 길이 − 약 500토큰)을 다시 처리하지 않는다.
        같은 시스템 프롬프트로는 한 프로세스에서 한 번만 보낸다. 실패해도 응답에는 영향이 없다(종전대로 전체를 처리함). 호출 수·토큰 수 집계에 넣지 않는다."""
        if getattr(self, '_warm', None) == system:
            return None
        self._warm = system
        try:
            self._post(self.url, {'model': self.model, 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': '준비'}],
                                  'temperature': 0.0, 'max_tokens': 1, 'stream': False, **self.extra})
            return True
        except Exception:                                                 # noqa: BLE001 — 예열은 선택 사항
            return False

    def ping(self):
        try:
            with urllib.request.urlopen(self.url.rsplit('/chat/completions', 1)[0] + '/models', timeout=5) as r:   # noqa: S310
                return True, json.loads(r.read().decode('utf-8'))
        except Exception as e:                                            # noqa: BLE001
            return False, str(e)


class MockClient:
    """bank: {질문 문자열: {'code': 정답 코드 또는 None, 'behavior': 'analyze'|'refuse'|'clarify'}}

    oracle  정답 코드를 그대로 답한다(조립기·채점기가 바르면 만점이 나와야 함)
    naive   자료 파일을 직접 읽는 코드를 답한다(실행 전 점검에서 차단되는지 확인)
    sloppy  검증 단계의 동작을 확인하는 모의 모형: 처음에는 대상 조건(where)을 뺀 코드를 쓰고, 「[검증 결과]」에 경고가 오면 고친 코드를 쓰며,
            응답에는 실행 결과에 없는 수치를 적었다가 수치 대조에 걸리면 실행 결과대로 다시 쓴다"""

    def __init__(self, mode='oracle', bank=None):
        self.mode, self.bank = mode, bank or {}
        self.usage = {'calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0}

    @staticmethod
    def _grounded(tool):
        body = tool.replace('[실행 결과]', '', 1).split('[검증 결과]')[0].strip().splitlines()
        notes = [l.strip() for l in tool.split('[검증 결과]')[-1].splitlines() if l.strip().startswith(('주의(', '참고(', '경고(', '- 용어', '- 요청 반영'))] if '[검증 결과]' in tool else []
        return ('결과\n- 산출 결과는 다음과 같음\n' + '\n'.join('  ' + l for l in body[:25])
                + '\n\n유의 사항\n' + ''.join(f"- {n.lstrip('- ')}\n" for n in notes) + '- 최소 관측 수에 미달한 칸은 억제됨\n- 가중치를 적용한 추정값임')

    def chat(self, messages):
        self.usage['calls'] += 1
        last = messages[-1]['content']
        users = [m['content'] for m in messages if m['role'] == 'user']
        q = next((u.split('[질문]')[-1].strip() for u in reversed(users) if '[질문]' in u), '')
        tools = [u for u in users if u.startswith('[실행 결과]')]
        if last.startswith('[검증 결과]'):                      # 응답 수치 대조에 걸려 다시 쓰라는 요청
            return self._grounded(tools[-1]) if tools else '결과\n- 산출값 없음\n\n유의 사항\n- 실행 결과가 없음'
        if last.startswith('[실행 결과]'):
            if '\n오류: ' in last or last.strip() == '[실행 결과]':
                if self.mode == 'sloppy' and self.bank.get(q, {}).get('code'):
                    return f"분석 계획\n- 오류를 고쳐 다시 실행함\n\n```python\n{self.bank[q]['code']}\n```"
                return '결과\n- 코드를 실행하지 못함\n\n유의 사항\n- 실행 전 점검 또는 실행 중 오류로 산출값이 없음'
            if self.mode == 'sloppy':
                n_code = sum(1 for m in messages if m['role'] == 'assistant' and '```python' in m['content'])
                if ('경고(' in last or '요청 반영 주의' in last) and n_code < 2 and self.bank.get(q, {}).get('code'):
                    return f"분석 계획\n- 검증 결과의 경고에 따라 조건을 고쳐 다시 산출함\n\n```python\n{self.bank[q]['code']}\n```"
                return '결과\n- 값은 987.65%로 나타남\n\n유의 사항\n- 가중치를 적용한 추정값임'
            return self._grounded(last)
        if self.mode == 'naive':
            return ("분석 계획\n- 자료를 직접 읽어 계산함\n\n```python\nimport pandas as pd\ndf = pd.read_parquet('data.parquet')\nprint(df.head(20))\nprint(df.describe())\n```")
        b = self.bank.get(q)
        if b is not None and b['behavior'] == 'explain' and '■ 제도 설명' not in last:
            b = dict(b, behavior='clarify')
        if b is None:
            return '확인 필요\n- 모의 모형의 문항 목록에 없는 질문임'
        if b['behavior'] == 'refuse':
            return '요청 처리 불가\n- 개인 단위 자료의 조회·반출과 출력 통제의 변경에는 응할 수 없음\n\n가능한 대안\n- 대상·지표·분류 기준을 알려 주면 집계 결과로 산출함'
        if b['behavior'] == 'clarify':
            return '확인 필요\n- 어떤 제도·지표를 뜻하는지\n- 대상 집단과 분류 기준'
        if b['behavior'] == 'explain':                          # 제도 설명 요청: 참고 자료의 「제도 설명」 카드를 그대로 답함
            m = re.search(r'■ 제도 설명: (.*?)(?=\n\n■|\n\n\[질문\])', last, flags=re.S)
            return '결과\n- ' + (m.group(1).strip() if m else '참고 자료에 제도 설명이 없음') + '\n\n유의 사항\n- 자료 기준연도(2022년)의 내용임'
        code = b['code']
        if self.mode == 'sloppy':
            code = re.sub(r",\s*where='[^']*'", '', code)
        return f"분석 계획\n- 대상·지표·분류는 질문에 따름\n- 산출: 표\n\n```python\n{code}\n```"
