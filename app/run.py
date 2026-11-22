#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""통합 실행 — OpenStat Studio 화면에 자연어 명령 창(Gemini API)을 덧붙이고, 같은 서버에서 정책 대시보드를 함께 연다.

  python -m app.run [--port 8500] [--open]
  화면   /            통계 프로그램 + 자연어 명령 창(원본 화면 코드는 고치지 않고 스크립트만 덧붙임)
         /dashboard   정책 대시보드(단일 HTML, 사전 집계값만 포함)
  뒷단   POST /api/nl/run {question}   질문 → Gemini → 분석 함수(ssda) 코드 → 실행 전 점검·격리 실행·출력 통제 → 결과 카드
         GET  /api/nl/info             준비 상태·예시
         POST /api/nl/key {key}        Gemini API 키 등록(서버 메모리에만 보관) / DELETE 로 삭제
  서버는 127.0.0.1 에만 연다. 접속자 구분이 없는 1인용 구조이므로 외부에 그대로 공개하지 않는다.
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

from . import paths

OST = paths.openstat_dir()
if OST is None:
    sys.exit('OpenStat Studio 사본(openstat/)을 찾지 못함.')
sys.path.insert(0, str(OST / 'reconstructed'))
os.environ.setdefault('MPLBACKEND', 'Agg')

import uvicorn  # noqa: E402
from fastapi import Body  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from starlette.routing import Route  # noqa: E402
import importlib.util  # noqa: E402

import pyjamovi  # noqa: E402,F401

# 명령 기록 모듈은 원본 시제품에서 고친 판을 쓴다(openstat/ 의 파일은 고치지 않고, 불러올 때만 바꿔 끼움).
_cl = paths.DEMO_DIR / 'openstat' / 'reconstructed' / 'pyjamovi' / 'command_log.py'
if _cl.exists():
    _spec = importlib.util.spec_from_file_location('pyjamovi.command_log', str(_cl))
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules['pyjamovi.command_log'] = _mod
    _spec.loader.exec_module(_mod)
    pyjamovi.command_log = _mod

import pyjamovi.plugins as plugins  # noqa: E402
from pyjamovi import command_log, stata_transpiler  # noqa: E402
from pyjamovi.server import SAMPLE_DIR, STATE, WEB_DIR, RunAnalysisRequest, app, run_analysis  # noqa: E402

from . import nl_plugin  # noqa: E402
from .fetch_data import screen_csv  # noqa: E402
from .gemini_client import GeminiError  # noqa: E402
from .nl_backend import Backend, NotReady  # noqa: E402

EXAMPLES = [
    {'kind': '조건별 표', 'q': '2022년 12월 기준 65세 이상 인구의 기초연금 수급률을 연령 구간(65~69세, 70~79세, 80세 이상)별로 산출 바람.'},
    {'kind': '교차분석', 'q': '65세 이상 인구 / 상대 빈곤율(균등화 가처분소득이 전체 인구 중위값의 50% 미만인 사람 비율) / 성별 × 연령(65~74세, 75세 이상) 교차표'},
    {'kind': '그래프', 'q': '소득 분위별 에너지바우처 이용률 막대그래프'},
    {'kind': '지도', 'q': '65세 이상 빈곤율을 시도 단계구분도로'},
    {'kind': '여러 조건', 'q': '혼자 사시는 65세 이상 여성 어르신 중에 2022년에 노인맞춤돌봄서비스를 한 번이라도 이용하신 분이 몇 퍼센트나 되나요?'},
    {'kind': '색 농도 그림', 'q': '문화누리카드 이용률을 연령대와 가구원수로 교차해 색 농도 그림으로'},
]
BACKEND = Backend()

# ── 분석 유형 nlQuery 등록(OpenStat 의 plugins 폴더에 파일을 두지 않고 실행 시점에 더함) ──
_discover = plugins.discover_plugins


def discover_plugins():
    d = _discover()
    d['nlQuery'] = {'spec': nl_plugin.PLUGIN_SPEC, 'runner': nl_plugin.run_plugin, 'path': nl_plugin.__file__}
    return d


plugins.discover_plugins = discover_plugins

# 명령 기록(왼쪽 아래 코드 창): nlQuery 는 질문과 그 질문에서 생성되어 실행된 분석 코드를 남김. 다른 분석 유형의 기록은 그대로
if hasattr(command_log, 'ANALYSIS_RECORDERS'):
    command_log.ANALYSIS_RECORDERS['nlQuery'] = nl_plugin.command_record
_transpile = stata_transpiler.transpile_stata_script
stata_transpiler.transpile_stata_script = lambda text: _transpile(nl_plugin.rerunnable(text))   # 코드 창에서 다시 실행하면 저장된 결과를 다시 엶


def err(message, code=200):
    return JSONResponse({'status': 'error', 'message': message}, status_code=code)


@app.post('/api/nl/run')
def nl_run(body: dict = Body(...)):
    q = (body.get('question') or '').strip()
    if not q:
        return err('질문이 비어 있음')
    try:
        out = BACKEND.ask(q)
    except NotReady as e:
        return err(str(e))
    except GeminiError as e:
        return err(str(e))
    except Exception as e:                                # noqa: BLE001
        return err(f'처리하지 못함: {type(e).__name__}: {e}'[:400])
    key = f'nl-{len(nl_plugin.STORE) + 1}'
    nl_plugin.STORE[key] = {k: out.get(k) for k in ('question', 'final', 'footer', 'steps', 'replay_source', 'mode', 'model', 'n_calls', 'elapsed_sec')}
    payload = run_analysis(RunAnalysisRequest(analysis_type='nlQuery', params={'question': q, 'key': key}))
    payload['nl'] = {'mode': out['mode'], 'model': out.get('model'), 'n_calls': out['n_calls'], 'elapsed_sec': out['elapsed_sec'], 'executed': any(s['ok'] for s in out['steps'])}
    return payload


@app.get('/api/nl/info')
def nl_info():
    BACKEND.load_models()
    return {'mode': 'gemini', **BACKEND.status(), 'examples': EXAMPLES, 'dashboard': paths.DASHBOARD_HTML.exists()}


@app.post('/api/nl/key')
def nl_key(body: dict = Body(...)):
    try:
        models = BACKEND.set_key(body.get('key'), body.get('model'))
    except GeminiError as e:
        return err('키를 확인하지 못함: ' + str(e))
    except Exception as e:                                # noqa: BLE001
        return err(f'키 확인 중 연결 오류: {type(e).__name__}')
    return {'status': 'success', **BACKEND.status()}


@app.post('/api/nl/model')
def nl_model(body: dict = Body(...)):
    try:
        BACKEND.set_model(body.get('model'))
    except GeminiError as e:
        return err(str(e))
    return {'status': 'success', **BACKEND.status()}


@app.delete('/api/nl/key')
def nl_key_clear():
    BACKEND.clear_key()
    return {'status': 'success', **BACKEND.status()}


@app.get('/dashboard')
def dashboard():
    if not paths.DASHBOARD_HTML.exists():
        return HTMLResponse('<meta charset="utf-8"><p>대시보드 파일이 아직 없음(원본/ 미도착).</p>', status_code=404)
    return FileResponse(str(paths.DASHBOARD_HTML), media_type='text/html', headers={'Cache-Control': 'no-store'})


async def nl_index(request):
    html = (Path(WEB_DIR) / 'index.html').read_text(encoding='utf-8')
    return HTMLResponse(html.replace('</body>', '<script src="/nl-assets/nl_command.js"></script>\n</body>'), headers={'Cache-Control': 'no-store'})


def load_screen_data():
    """화면에 여는 자료(주요 변수 CSV)가 받아져 있으면 OpenStat 의 자료 폴더에 두고 연다."""
    src = screen_csv()
    dst = Path(SAMPLE_DIR) / paths.SCREEN_CSV
    if src and src.resolve() != dst.resolve() and not dst.exists():
        shutil.copyfile(src, dst)
    geo = paths.DEMO_DIR / 'openstat' / 'sample_data' / 'geo'
    if geo.exists():
        for f in geo.iterdir():
            g = Path(SAMPLE_DIR) / 'geo' / f.name
            if not g.exists():
                g.parent.mkdir(exist_ok=True)
                shutil.copyfile(f, g)
    if dst.exists():
        STATE.load_file(paths.SCREEN_CSV, sync_ws=True)
        return True
    return False


def setup_app():
    paths.WORK_DIR.mkdir(parents=True, exist_ok=True)
    app.mount('/nl-assets', StaticFiles(directory=str(paths.APP / 'web')), name='nl-assets')
    app.router.routes.insert(0, Route('/', nl_index, methods=['GET']))   # 첫 화면을 자연어 창이 붙은 화면으로
    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=int(os.environ.get('PORT', 8500)))
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--open', action='store_true', help='서버가 준비되면 기본 브라우저로 연다')
    a = ap.parse_args()
    setup_app()
    shown = load_screen_data()
    st = BACKEND.status()
    print(f'통계 프로그램 + 자연어 명령 창: http://127.0.0.1:{a.port}/', flush=True)
    print(f'정책 대시보드: http://127.0.0.1:{a.port}/dashboard' + ('' if paths.DASHBOARD_HTML.exists() else ' (파일 없음)'), flush=True)
    print('화면 자료: ' + ('주요 변수 CSV' if shown else '없음(예제 자료로 시작)') + ' · 자연어 분석: ' + ('준비됨' if st['ready'] else '준비 안 됨 — ' + ' / '.join(st['missing'])), flush=True)
    if a.open:
        import threading
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(f'http://127.0.0.1:{a.port}/')).start()
    uvicorn.run(app, host=a.host, port=a.port, log_level='warning')


if __name__ == '__main__':
    main()
