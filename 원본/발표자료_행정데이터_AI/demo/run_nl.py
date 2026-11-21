#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenStat Studio(사본)에 자연어 명령 창을 덧붙여 실행한다 — 발표용 시제품.

  /mnt/share/temp/pyjamovi/.venv/bin/python run_nl.py [--port 8510] [--mode replay|live]
구성  화면: OpenStat 의 index.html 끝에 nl_command.js 를 덧붙여 돌려줌(원본 화면 코드는 고치지 않음)
      뒷단: POST /api/nl/run {question} → nl_worker.py(분석 지원기: 언어모형 → 분석 함수 ssda 코드 → 실행 전 점검·격리 실행·출력 통제)
            → 결과를 분석 유형 nlQuery 의 결과 카드로 결과 시트에 추가
            → 왼쪽 아래 「명령 기록·코드 편집기」에는 질문과 언어모형이 작성해 실행한 분석 코드가 실행 순서대로 기록됨
자료  화면의 자료는 sample_data/사회보장행정데이터_가상_주요변수.csv(주요 변수 41개), 자연어 창의 집계는 확대 생성본 전체(595개 변수)
"""
import argparse
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'openstat' / 'reconstructed'))
sys.path.insert(0, str(HERE))
os.environ.setdefault('MPLBACKEND', 'Agg')

import uvicorn  # noqa: E402
from fastapi import Body  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
import pyjamovi.plugins as plugins  # noqa: E402
from pyjamovi import command_log, stata_transpiler  # noqa: E402
from pyjamovi.server import app, STATE, run_analysis, RunAnalysisRequest, WEB_DIR  # noqa: E402
import nl_plugin  # noqa: E402

DATASET = '사회보장행정데이터_가상_주요변수.csv'
WORKER_PY = '/mnt/share/행정데이터_set/.venv/bin/python'
EXAMPLES = [
    {'kind': '조건별 표', 'q': '2022년 12월 기준 65세 이상 인구의 기초연금 수급률을 연령 구간(65~69세, 70~79세, 80세 이상)별로 산출 바람.'},
    {'kind': '교차분석', 'q': '65세 이상 인구 / 상대 빈곤율(균등화 가처분소득이 전체 인구 중위값의 50% 미만인 사람 비율) / 성별 × 연령(65~74세, 75세 이상) 교차표'},
    {'kind': '그래프', 'q': '소득 분위별 에너지바우처 이용률 막대그래프'},
    {'kind': '지도', 'q': '65세 이상 빈곤율을 시도 단계구분도로'},
    {'kind': '여러 조건', 'q': '혼자 사시는 65세 이상 여성 어르신 중에 2022년에 노인맞춤돌봄서비스를 한 번이라도 이용하신 분이 몇 퍼센트나 되나요?'},
    {'kind': '색 농도 그림', 'q': '문화누리카드 이용률을 연령대와 가구원수로 교차해 색 농도 그림으로'},
]

# ── 분석 유형 nlQuery 등록(plugins 폴더에 파일을 두지 않고 실행 시점에 더함) ──
_discover = plugins.discover_plugins
def discover_plugins():
    d = _discover()
    d['nlQuery'] = {'spec': nl_plugin.PLUGIN_SPEC, 'runner': nl_plugin.run_plugin, 'path': nl_plugin.__file__}
    return d
plugins.discover_plugins = discover_plugins

# ── 명령 기록(왼쪽 아래 코드 창): nlQuery 는 감싸는 호출 대신 질문에서 생성되어 실행된 분석 코드를 남김. 다른 분석 유형의 기록은 그대로 ──
command_log.ANALYSIS_RECORDERS['nlQuery'] = nl_plugin.command_record
_transpile = stata_transpiler.transpile_stata_script
stata_transpiler.transpile_stata_script = lambda text: _transpile(nl_plugin.rerunnable(text))     # 코드 창의 [선택 실행]·[전체 실행]이 자연어 명령 구간을 만나면 저장된 결과를 다시 엶


class Worker:
    def __init__(self, mode):
        self.mode, self.lock, self.p, self.info = mode, threading.Lock(), None, {}

    def start(self):
        env = dict(os.environ, NL_MODE=self.mode, NL_TMP=str(HERE / 'tmp'))
        self.p = subprocess.Popen([WORKER_PY, str(HERE / 'nl_worker.py')], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=open(HERE / 'tmp' / 'worker.err', 'a'), text=True, env=env)
        self.info = json.loads(self.p.stdout.readline())

    def ask(self, req):
        with self.lock:
            if self.p is None or self.p.poll() is not None:
                self.start()
            self.p.stdin.write(json.dumps(req, ensure_ascii=False) + '\n'); self.p.stdin.flush()
            return json.loads(self.p.stdout.readline())


WORKER = None


@app.post('/api/nl/run')
def nl_run(body: dict = Body(...)):
    q = (body.get('question') or '').strip()
    if not q:
        return {'status': 'error', 'message': '질문이 비어 있음'}
    out = WORKER.ask({'question': q})
    if not out.get('ok'):
        return {'status': 'error', 'message': out.get('error', '처리하지 못함')}
    key = f'nl-{len(nl_plugin.STORE) + 1}'
    nl_plugin.STORE[key] = {k: out.get(k) for k in ('question', 'final', 'footer', 'steps', 'replay_source', 'mode', 'n_calls', 'elapsed_sec')}
    payload = run_analysis(RunAnalysisRequest(analysis_type='nlQuery', params={'question': q, 'key': key}))      # 명령 기록에는 질문과 생성·실행된 분석 코드가 남음(nl_plugin.command_record)
    payload['nl'] = {'mode': out.get('mode'), 'n_calls': out.get('n_calls'), 'elapsed_sec': out.get('elapsed_sec'), 'executed': any(s['ok'] for s in out['steps'])}
    return payload


@app.get('/api/nl/info')
def nl_info():
    return {'mode': WORKER.mode, 'worker': WORKER.info, 'examples': EXAMPLES}


def index_html():
    html = (Path(WEB_DIR) / 'index.html').read_text(encoding='utf-8')
    return html.replace('</body>', '<script src="/nl-assets/nl_command.js"></script>\n</body>')


async def nl_index(request=None):
    return HTMLResponse(index_html())


def main():
    global WORKER
    ap = argparse.ArgumentParser(); ap.add_argument('--port', type=int, default=8510); ap.add_argument('--mode', default=os.environ.get('NL_MODE', 'replay'), choices=['replay', 'live'])
    a = ap.parse_args()
    (HERE / 'tmp').mkdir(exist_ok=True)
    WORKER = Worker(a.mode); WORKER.start()
    app.mount('/nl-assets', StaticFiles(directory=str(HERE / 'web')), name='nl-assets')
    from starlette.routing import Route
    app.router.routes.insert(0, Route('/', nl_index, methods=['GET']))        # 첫 화면을 자연어 창이 붙은 화면으로
    STATE.load_file(DATASET, sync_ws=True)
    print(f'자연어 명령 창 시제품: http://127.0.0.1:{a.port}/  (방식 {a.mode}, 뒷단 {WORKER.info})', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=a.port, log_level='warning')


if __name__ == '__main__':
    main()
