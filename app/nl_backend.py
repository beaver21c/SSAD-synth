# -*- coding: utf-8 -*-
"""자연어 분석 뒷단 — 질문을 분석 지원기(원본 로컬LLM_준비/06_build/assistant.py)에 넘기고 결과를 돌려준다.

  원본 시제품의 nl_worker.py 와 같은 결과 형식을 쓰되, 언어모형 연결부만 Gemini API(app/gemini_client.py)로 바꾼 것이다.
  분석 함수(ssda)의 실행 전 점검·격리 실행·출력 통제는 원본 그대로 적용된다.
  API 키는 서버 메모리에만 둔다(파일·기록에 쓰지 않음). 서버를 끄면 사라진다.
"""
import base64
import os
import sys
import threading

from . import paths
from .fetch_data import data_path
from .gemini_client import KEY_ENV, GeminiClient, GeminiError, list_models


class NotReady(RuntimeError):
    pass


class Backend:
    def __init__(self):
        self.key = os.environ.get(KEY_ENV, '')
        self.model = os.environ.get('GEMINI_MODEL') or None
        self.lock = threading.Lock()
        self._cfg = self._rt = self._mod = None
        self.last_model = None

    # ── 준비 상태 ──
    def missing(self):
        m = []
        if not (paths.LLM_DIR / '06_build' / 'assistant.py').exists():
            m.append('분석 지원기(원본/로컬LLM_준비)가 없음')
        if not data_path().exists():
            m.append('가상데이터가 없음(원본/ 아래 확대 생성본)')
        if not self.key:
            m.append('Gemini API 키가 입력되지 않음')
        return m

    def status(self):
        return {'ready': not self.missing(), 'missing': self.missing(), 'has_key': bool(self.key), 'model': self.last_model or self.model or '자동 선택'}

    # ── 키 ──
    def set_key(self, key, model=None):
        key = (key or '').strip()
        if not key:
            raise GeminiError(400, '키가 비어 있음')
        models = list_models(key)                         # 키가 유효한지 확인(유효하지 않으면 여기서 오류)
        self.key, self.model, self.last_model = key, (model or None), None
        return models

    def clear_key(self):
        self.key, self.last_model = '', None

    # ── 분석 지원기 ──
    def _load(self):
        if self._mod is None:
            for p in (paths.LLM_DIR / '06_build', paths.LLM_DIR / '02_library'):
                if str(p) not in sys.path:
                    sys.path.insert(0, str(p))
            import assistant as mod                       # 원본 조립기
            from retriever import Retriever
            cfg_file = paths.APP / 'config' / 'assistant.yaml'
            cfg = mod.load_config(str(cfg_file) if cfg_file.exists() else None)
            exp = paths.WORK_DIR / 'export'
            exp.mkdir(parents=True, exist_ok=True)
            cfg['paths'].update(data=str(data_path()), export=str(exp), log=str(paths.WORK_DIR / 'ssda_log.jsonl'), transcripts=str(paths.WORK_DIR / 'assistant_log.jsonl'))
            self._mod, self._cfg, self._rt = mod, cfg, Retriever()
        return self._mod, self._cfg, self._rt

    def make_client(self, cfg=None):
        m = (cfg or {}).get('model', {})
        return GeminiClient(self.key, self.model, m.get('temperature', 0.0), m.get('max_tokens', 1500), min(m.get('timeout_sec', 120), 300))

    def ask(self, question, client=None):
        miss = [m for m in self.missing() if not (client and 'API 키' in m)]
        if miss:
            raise NotReady(' / '.join(miss))
        with self.lock:
            mod, cfg, rt = self._load()
            client = client or self.make_client(cfg)
            mode = 'gemini' if isinstance(client, GeminiClient) else type(client).__name__
            rec = mod.Assistant(cfg, client, rt).ask(question)
            self.last_model = client.used_model or self.last_model
            exp = paths.WORK_DIR / 'export'
            steps = []
            for s in rec['steps']:
                figs = []
                for f in s.get('figures') or []:
                    fp = exp / f
                    if fp.exists():
                        figs.append({'name': f, 'src': 'data:image/png;base64,' + base64.b64encode(fp.read_bytes()).decode()})
                steps.append({'code': s['code'], 'ok': bool(s.get('ok')), 'origin': s.get('origin', 'model'), 'blocked': bool(s.get('violations')),
                              'error': (s.get('error') or '').splitlines()[0][:400] if s.get('error') else '', 'stdout': (s.get('stdout') or '')[:4000],
                              'results': s.get('results') or {}, 'figures': figs})
            return {'ok': True, 'mode': mode, 'model': client.used_model, 'question': question, 'final': rec['final'], 'footer': rec.get('footer') or '',
                    'n_calls': rec['n_calls'], 'elapsed_sec': rec['elapsed_sec'], 'hooks': rec.get('hooks'), 'steps': steps, 'replay_source': None,
                    'usage': dict(client.usage)}
