#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""가상데이터 내려받기 — Hugging Face 비공개 데이터셋에서 개인 단위 가상데이터를 받아 data/ 에 둔다.

  가상데이터는 공개 저장소에 넣지 않는다(.gitignore). 접근 권한이 있는 사람만 자기 토큰으로 받는다.
  토큰은 환경 변수 HF_TOKEN 또는 `hf auth login` 으로 저장된 것을 쓴다. 코드·기록에 남기지 않는다.

사용
  python app/fetch_data.py                      # 기본 데이터셋·파일
  python app/fetch_data.py --check              # 받지 않고 준비 상태만 확인
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get('SSAD_DATA_DIR', ROOT / 'data'))
REPO_ID = os.environ.get('SSAD_HF_DATASET', 'beaver22c/ssad-synth-data')
MAIN_FILE = os.environ.get('SSAD_DATA_FILE', '가상데이터_확대본_n42000.parquet')


def data_path():
    return DATA_DIR / MAIN_FILE


def fetch(repo_id=REPO_ID, filename=MAIN_FILE, force=False):
    dst = DATA_DIR / filename
    if dst.exists() and not force:
        return dst
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        sys.exit('huggingface_hub 가 없음: pip install huggingface_hub')
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        p = hf_hub_download(repo_id, filename, repo_type='dataset', local_dir=str(DATA_DIR), token=os.environ.get('HF_TOKEN') or None)
    except Exception as e:                                             # noqa: BLE001
        sys.exit(f'가상데이터를 받지 못함({type(e).__name__}). 확인할 것: ① 데이터셋 {repo_id} 접근 권한 ② HF_TOKEN 환경 변수 또는 `hf auth login` ③ 파일 이름 {filename}')
    return Path(p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', default=REPO_ID); ap.add_argument('--file', default=MAIN_FILE)
    ap.add_argument('--force', action='store_true'); ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    if a.check:
        p = DATA_DIR / a.file
        print(f'{p}: ' + (f'있음({p.stat().st_size / 1e6:.1f}MB)' if p.exists() else '없음'))
        return
    print(fetch(a.repo, a.file, a.force))


if __name__ == '__main__':
    main()
