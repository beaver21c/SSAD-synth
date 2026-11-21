#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""폐쇄망 반입 목록 만들기 — 반입 대상(준비 폴더, 모형 파일, 추론 서버, 파이썬 패키지)의 위치·크기·해시를 한 문서로 정리한다.

  python 06_build/make_manifest.py              # 목록만 다시 만듦
  python 06_build/make_manifest.py --wheels     # 조립기 실행에 필요한 파이썬 wheel 을 내려받아 목록에 넣음(requirements-serve.txt)
  python 06_build/make_manifest.py --source     # llama.cpp 원본을 현재 판 그대로 묶음 파일로 만들어 목록에 넣음(다른 장비에서 다시 빌드할 때 씀)
출력  모형반입/반입목록.md, 모형반입/준비폴더_파일목록.tsv

반입 절차와 심사 양식은 정해지지 않았음(결정필요사항 5번). 이 목록은 그 결정에 쓸 기초 자료이며, 최종 구성(양자화 수준, 미세조정 여부)이 정해지면 다시 만든다.
"""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / '모형반입'
STORE = Path(os.environ.get('GGUF_DIR', '/mnt/share/models/arete-27b'))
LLAMA = Path(os.environ.get('LLAMA', str(Path.home() / 'llama.cpp')))
SKIP_DIRS = {'logs', 'export', '__pycache__', 'runs', 'cpu_real_smoke_run'}


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as fp:
        for b in iter(lambda: fp.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()


def run(cmd, **kw):
    p = subprocess.run(cmd, capture_output=True, text=True, **kw)
    return p.returncode, (p.stdout + p.stderr).strip()


def gb(n):
    return f'{n / 1e9:.2f}GB' if n >= 1e8 else f'{n / 1e6:.1f}MB'


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--wheels', action='store_true'); ap.add_argument('--source', action='store_true'); a = ap.parse_args()
    L = ['# 폐쇄망 반입 목록(안)', '', f"작성 {time.strftime('%Y-%m-%d %H:%M')} · `06_build/make_manifest.py` 가 만든 목록", '',
         '반입 절차와 심사 양식은 정해지지 않았음(결정필요사항 5번). 최종 구성(양자화 수준, 미세조정 여부)이 정해지면 다시 만듦.', '']
    # 1 준비 폴더
    files = sorted(p for p in ROOT.rglob('*') if p.is_file() and not (set(p.relative_to(ROOT).parts[:-1]) & SKIP_DIRS) and p.name not in ('준비폴더_파일목록.tsv', '반입목록.md') and not p.name.endswith('.log'))
    rows = [(str(p.relative_to(ROOT)), p.stat().st_size, sha(p)) for p in files]
    (OUT / '준비폴더_파일목록.tsv').write_text('경로\t크기(바이트)\tSHA-256\n' + ''.join(f'{r[0]}\t{r[1]}\t{r[2]}\n' for r in rows), encoding='utf-8')
    L += ['## 1. 준비 폴더', '', f"- 위치: `{ROOT}`", f"- 파일 {len(rows):,}개, {gb(sum(r[1] for r in rows))} (실행 기록·평가 실행 결과·임시 산출물 제외)",
          '- 파일별 크기와 SHA-256: `모형반입/준비폴더_파일목록.tsv`', '- 개인 단위 값은 들어 있지 않음(지식 자료는 변수 정의와 값 유무만, 학습·평가 자료는 가상데이터의 집계 결과만 수록)', '']
    # 2 모형
    L += ['## 2. 모형 파일', '', '| 구분 | 위치 | 파일 | 크기 | 해시 기록 | 쓰임 |', '|---|---|---|---|---|---|']
    exp = json.loads((OUT / 'expected_files.json').read_text(encoding='utf-8')) if (OUT / 'expected_files.json').exists() else None
    if exp:
        L.append(f"| 공식 가중치(bf16) | `/mnt/share/hf_cache/hub/models--{exp['repo'].replace('/', '--')}` | {len(exp['files'])}개 | {gb(sum(f['size'] for f in exp['files']))} | `모형반입/반입기록.md`(SHA-256 {sum(1 for f in exp['files'] if f.get('sha256'))}개) | 4비트 적재 서버, 미세조정, 양자화본 재제작 |")
    gc = json.loads((OUT / 'gguf_check.json').read_text(encoding='utf-8')) if (OUT / 'gguf_check.json').exists() else None
    for f in (gc['files'] if gc else []):
        lora = '-lora-' in f['file']
        use = ('다른 양자화 수준을 만들 때 쓰는 중간 파일(반입 불필요)' if 'bf16' in f['file']
               else 'llama.cpp 서버용 양자화본(미세조정 모형. 설정 파일의 기본 구성)' if lora else 'llama.cpp 서버용 양자화본(공식 가중치. 쓸 수준 하나만 반입)')
        L.append(f"| GGUF {'미세조정 ' if lora else ''}{f['file'].split('-')[-1].replace('.gguf', '')} | `{gc['dir']}/{f['file']}` | 1개 | {gb(f['bytes'])} | `{(f.get('sha256') or '미계산')[:16]}…` | {use} |")
    L += ['', '- llama.cpp 서버로 구동하면 양자화본 하나만 반입하면 됨(기본 구성은 미세조정 모형 Q5_K_M). 공식 가중치는 4비트 적재 서버를 쓰거나 미세조정을 할 때 필요함', '- 미세조정 모형의 양자화본은 공식 가중치에 어댑터(`06_build/runs/lora_assistant_v1`)를 합쳐 직접 변환한 파일임(2026-11-16)', '- 제3자가 올린 양자화 파일은 포함하지 않음', '']
    # 3 추론 서버
    L += ['## 3. 추론 서버(llama.cpp)', '']
    code, commit = run(['git', '-C', str(LLAMA), 'log', '-1', '--format=%H %ad', '--date=short'])
    code2, url = run(['git', '-C', str(LLAMA), 'remote', 'get-url', 'origin'])
    L.append(f"- 원본: {url if code2 == 0 else '—'} · 판 `{commit if code == 0 else '—'}` · 위치 `{LLAMA}`")
    if a.source and code == 0:
        d = STORE / 'src'; d.mkdir(parents=True, exist_ok=True)
        tar = d / f'llama.cpp-{commit[:7]}.tar.gz'
        if not tar.exists():
            run(['git', '-C', str(LLAMA), 'archive', '--format=tar.gz', f'--prefix=llama.cpp-{commit[:7]}/', '-o', str(tar), 'HEAD'])
    for tar in sorted((STORE / 'src').glob('llama.cpp-*.tar.gz')) if (STORE / 'src').exists() else []:
        L.append(f"- 원본 묶음 파일: `{tar}` ({gb(tar.stat().st_size)}, SHA-256 `{sha(tar)}`) — 다른 장비에서 `06_build/build_llamacpp.sh`로 다시 빌드할 때 씀")
    for n in ('cuda', 'cpu'):
        b = LLAMA / f'build-{n}' / 'bin'
        if (b / 'llama-server').exists():
            fs = [p for p in b.iterdir() if p.is_file() and not p.is_symlink()]
            info = (b.parent / 'BUILD_INFO.txt').read_text(encoding='utf-8').replace('\n', ' · ') if (b.parent / 'BUILD_INFO.txt').exists() else ''
            L.append(f"- {'CUDA' if n == 'cuda' else 'CPU'} 빌드: `{b}` (파일 {len(fs)}개, {gb(sum(p.stat().st_size for p in fs))}, llama-server SHA-256 `{sha(b / 'llama-server')[:16]}…`) — {info}")
    L += ['- 실행 파일은 이 PC의 CPU 명령어 집합, GPU 세대(RTX 50 계열, 빌드 대상 120a-real), CUDA 13.1 라이브러리에 맞춰 빌드한 것임. 구성이 다른 장비에는 원본을 반입해 그 장비에서 다시 빌드함. CUDA 빌드는 실행에 CUDA 13 런타임 라이브러리(libcudart, libcublas)가 필요함', '']
    # 4 파이썬 패키지
    L += ['## 4. 파이썬 패키지', '']
    wdir = STORE / 'wheels-serve'
    if a.wheels:
        wdir.mkdir(parents=True, exist_ok=True)
        code, out = run([sys.executable, '-m', 'pip', 'download', '-q', '-r', str(ROOT / '06_build' / 'requirements-serve.txt'), '-d', str(wdir), '--only-binary=:all:'])
        if code:
            L.append(f"- wheel 내려받기 실패: {out.splitlines()[-1][:200] if out else ''}")
    ws = sorted(wdir.glob('*.whl')) if wdir.exists() else []
    L.append(f"- 조립기 실행 환경(`requirements-serve.txt`): Python {platform.python_version()}, " + (f"wheel {len(ws)}개 {gb(sum(w.stat().st_size for w in ws))} — `{wdir}`" if ws else 'wheel 은 내려받지 않았음(`--wheels`)'))
    if ws:
        L += ['', '| wheel | 크기 | SHA-256 |', '|---|---|---|'] + [f"| {w.name} | {gb(w.stat().st_size)} | `{sha(w)}` |" for w in ws] + ['',
              f"- 설치: `pip install --no-index --find-links {wdir} -r 06_build/requirements-serve.txt` (같은 운영체제·Python 판이어야 함)"]
    pyc = Path.home() / 'anaconda3' / 'envs' / 'vllm' / 'bin' / 'python'
    if pyc.exists():
        code, out = run([str(pyc), '-m', 'pip', 'list', '--format=freeze'])
        if code == 0:
            keep = [l for l in out.splitlines() if l.split('==')[0].lower() in ('torch', 'transformers', 'tokenizers', 'peft', 'accelerate', 'bitsandbytes', 'safetensors', 'huggingface-hub', 'huggingface_hub', 'numpy', 'gguf', 'sentencepiece', 'vllm', 'triton')]
            (ROOT / '06_build' / 'requirements-vllm-freeze.txt').write_text('# conda 환경 vllm 의 주요 패키지 판 — 4비트 적재 서버(serve_transformers.py)와 미세조정에 쓰는 환경. 이 PC에서 확인한 판이며 wheel 은 내려받지 않았음\n' + '\n'.join(keep) + '\n', encoding='utf-8')
            L.append(f"- 4비트 적재 서버·미세조정 환경(conda vllm, Python {run([str(pyc), '-c', 'import platform; print(platform.python_version())'])[1]}): 주요 패키지 판을 `06_build/requirements-vllm-freeze.txt`에 기록함({', '.join(keep[:6])} 등). 용량이 커 wheel 은 내려받지 않았음. llama.cpp 서버만 쓰면 필요 없음")
    L.append('')
    # 5 설비 정보
    code, drv = run(['nvidia-smi', '--query-gpu=name,driver_version,memory.total', '--format=csv,noheader'])
    code2, nvcc = run(['bash', '-c', 'nvcc --version | grep -i release'])
    L += ['## 5. 이 목록을 만든 설비', '', f"- 운영체제: {platform.platform()}", f"- GPU·드라이버: {drv.replace(chr(10), ' / ') if code == 0 else '조회 불가'}", f"- CUDA 도구: {nvcc if code2 == 0 else '없음'}", '',
          '## 6. 반입하지 않는 것', '', '- 평가 실행 결과와 실행 기록(`05_eval/runs`, `logs`) — 폐쇄망 안에서 실제 자료로 다시 수행함', '- 가상데이터 원본 — 개발용 대역 자료이며 폐쇄망에서는 실제 분석 자료를 씀',
          '- 시험용 축소 모형(`/mnt/share/models/arete-27b/test`) — 필요하면 `06_build/make_tiny_twin.py`로 다시 만듦']
    (OUT / '반입목록.md').write_text('\n'.join(L) + '\n', encoding='utf-8')
    print(f"반입목록.md 작성: 준비 폴더 파일 {len(rows)}개, GGUF {len(gc['files']) if gc else 0}개, wheel {len(ws)}개")
    return 0


if __name__ == '__main__':
    sys.exit(main())
