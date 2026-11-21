# -*- coding: utf-8 -*-
"""경로 모음 — 원본(행정데이터_set 사본, 읽기 전용 취급)과 이 저장소에서 새로 만든 것의 위치를 한곳에서 정한다."""
import os
from pathlib import Path
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app'
ORIG = Path(os.environ.get('SSAD_ORIG_DIR', ROOT / '원본'))                 # PC 원본 사본(수정하지 않음)
LLM_DIR = ORIG / '로컬LLM_준비'                                             # 분석 지원기(조립기·분석 함수·프롬프트·평가)
DEMO_DIR = ORIG / '발표자료_행정데이터_AI' / 'demo'                          # OpenStat 연결 시제품
CASE_DIR = ORIG / 'work' / 'report' / '활용고도화전략' / '적용사례'           # 대시보드·빌드 스크립트
DASHBOARD_HTML = Path(os.environ.get('SSAD_DASHBOARD', CASE_DIR / '사회보장행정데이터_대시보드.html'))
WORK_DIR = Path(os.environ.get('SSAD_WORK_DIR', ROOT / 'workspace_nl'))     # 실행 중 생기는 기록·그림(저장소에 넣지 않음)
SCREEN_CSV = '사회보장행정데이터_가상_주요변수.csv'                           # 통계 프로그램 화면에 여는 자료(주요 변수)


def openstat_dir():
    """OpenStat Studio 위치: 환경 변수 → 원본의 시제품 사본 → vendor/pyopenstat(공개 저장소를 내려받은 것)."""
    cands = [os.environ.get('OPENSTAT_DIR'), DEMO_DIR / 'openstat', ROOT / 'vendor' / 'pyopenstat']
    for c in cands:
        if c and (Path(c) / 'reconstructed' / 'pyjamovi' / 'server.py').exists():
            return Path(c)
    return None
