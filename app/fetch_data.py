# -*- coding: utf-8 -*-
"""가상데이터 위치 — 저장소 안 원본 사본에 든 가상데이터 파일을 찾는다.

  환경 변수 SSDA_DATA 로 다른 파일을 지정할 수 있다. 없으면 원본/ 아래에서 확대 생성본을 찾는다.
"""
import os
from pathlib import Path

from . import paths

MAIN_FILE = '가상데이터_확대본_n42000.parquet'


def data_path():
    env = os.environ.get('SSDA_DATA')
    if env:
        return Path(env)
    p = paths.CASE_DIR / 'data' / MAIN_FILE
    if p.exists() or not paths.ORIG.exists():
        return p
    hits = sorted(paths.ORIG.rglob(MAIN_FILE))
    return hits[0] if hits else p


def screen_csv():
    """통계 프로그램 화면에 여는 주요 변수 CSV(원본 시제품의 자료 폴더에 있음)."""
    hits = sorted(paths.ORIG.rglob(paths.SCREEN_CSV)) if paths.ORIG.exists() else []
    return hits[0] if hits else None


if __name__ == '__main__':
    p = data_path()
    print(f'{p}: ' + (f'있음({p.stat().st_size / 1e6:.1f}MB)' if p.exists() else '없음'))
