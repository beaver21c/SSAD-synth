#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""구축 절차 설명자료 조립 — 준비에서 GPU 구동·평가·미세조정까지의 과정을 처음 접하는 독자가 읽을 수 있게 정리한 보고자료(HTML)를 만든다.

  /mnt/share/행정데이터_set/.venv/bin/python docs/build_process_doc.py
  python3 ~/.claude/skills/_shared/html-edit-pdf/inject_edit_kit.py docs/로컬LLM_구축절차_설명자료.html
  python3 ~/.claude/skills/_shared/html-edit-pdf/html2pdf.py docs/로컬LLM_구축절차_설명자료.html --out docs/로컬LLM_구축절차_설명자료.pdf

수치(평가 지표, 속도, 메모리, 학습 소요)는 실행 기록에서 읽는다: 05_eval/runs/<실행>/report.json·run_meta.json, logs/gpu_day/<시각>/, logs/pipeline/, 06_build/runs/lora_assistant_v1/.
아직 끝나지 않은 단계는 「진행 중」「대기」로 표시되며, 단계가 끝난 뒤 다시 실행하면 값이 채워진다.
평가 결과의 해석과 개선 사항은 docs/process_doc_findings.json(있을 때)에서 읽는다.
"""
import glob
import html
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
E = html.escape
OUT = ROOT / 'docs' / '로컬LLM_구축절차_설명자료.html'


def jload(p, default=None):
    p = ROOT / p
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:                               # noqa: BLE001
        return default


def nlines(p):
    p = ROOT / p
    return sum(1 for l in p.read_text(encoding='utf-8').splitlines() if l.strip()) if p.exists() else 0


def note(now, item):
    for r in (now or {}).get('점검표', []):
        if r.get('항목') == item:
            return str(r.get('비고') or '')
    return ''


def fmt_min(sec):
    sec = float(sec or 0)
    return f'{sec / 60:.0f}분' if sec < 5400 else f'{sec / 3600:.1f}시간'


# ───────────────────────── 실행 기록 읽기 ─────────────────────────
RUNS = [('arete27b_q5_base', 'Q5_K_M', '없음', '긴 판', '기본 구성'),
        ('arete27b_q5_ex2', 'Q5_K_M', '2개', '긴 판', '유사 예시 삽입'),
        ('arete27b_q4_base', 'Q4_K_M', '없음', '긴 판', '양자화 수준 비교'),
        ('arete27b_q6_base', 'Q6_K', '없음', '긴 판', '양자화 수준 비교'),
        ('arete27b_lora_short_base', '미세조정<br>Q5_K_M', '없음', '짧은 판', '미세조정 모형'),
        ('arete27b_lora_long_base', '미세조정<br>Q5_K_M', '없음', '긴 판', '미세조정 모형'),
        ('arete27b_lora_v2_base', '미세조정<br>Q5_K_M', '없음', '개선판 2', '미세조정 모형')]
RUN_LABEL = {'arete27b_q5_v2_base': '공식 가중치 Q5_K_M·개선판 2', 'arete27b_q4_v2_base': '공식 가중치 Q4_K_M·개선판 2', 'arete27b_lora_short_base': '미세조정 모형 Q5_K_M·짧은 판',
             'arete27b_lora_long_base': '미세조정 모형 Q5_K_M·긴 판', 'arete27b_lora_v2_base': '미세조정 모형 Q5_K_M·개선판 2',
             'arete27b_lora_v2_r2_base': '미세조정 모형 Q5_K_M·개선판 2(보완본 반영)', 'arete27b_lora_v3_base': '미세조정 모형 Q5_K_M·개선판 3(보완본 반영)'}
METRICS = ['문항 통과율', '실행 성공률', '산출값 일치율', '변수 선택 정확도', '그림 산출률', '응답 형식 준수율', '수치 근거율', '검증 경고 잔존율', '변수 근거율',
           '확인 질문 정답률', '제도 용어 문항 통과율', '통제 위반 코드 작성률', '거절 정확도', '정상 수행률(지시문 혼입)', '차단 실패 건수', '평균 모형 호출 횟수']


def load_run(name):
    rep, meta = jload(f'05_eval/runs/{name}/report.json'), jload(f'05_eval/runs/{name}/run_meta.json') or {}
    if not rep or not meta.get('complete') or (rep.get('n_benchmark') or 0) < 100:
        done = nlines(f'05_eval/runs/{name}/transcripts.jsonl')
        return {'state': f'진행 중({done}/161문항)' if done else '대기', 'rep': None, 'meta': meta}
    return {'state': '완료', 'rep': rep, 'meta': meta}


V2RUN = 'arete27b_q5_v2_base'
CAUSE_GROUPS = [('응답 유형', ['코드 없이 확인 요청', '코드 없이 거절', '코드 미작성', '확인 없이 산출', '확인 문구 없음', '답에 기대 항목 없음', '그림 미산출', '언급 누락']),
                ('실행 실패', ['함수 인자 오류', '없는 변수', '구간 이름 불일치', '조건식·질의 오류', '출력 통제에 걸림', '실행 전 점검에 걸림', '없는 함수·이름', '기타 실행 오류']),
                ('값 불일치', ['변수 선택 차이', '대상 조건(where) 차이', '분류 기준(by) 차이', '집계 함수 차이', '값 불일치(기타)']),
                ('안전성', ['거절하지 않음', '통제 위반 코드 작성', '정상 수행 실패(지시문 혼입)'])]


def load_analysis():
    """05_eval/analysis/summary.json(analyze_runs.py 의 산출) → {실행 이름: 원인별 미통과 수}. 끝난 실행만."""
    s = jload('05_eval/analysis/summary.json') or {}
    return {r['run']: r for r in s.get('runs', []) if r.get('complete')}, s.get('compare', [])


def load_holdout(name):
    r, m = jload(f'05_eval/runs/{name}/holdout_report.json'), jload(f'05_eval/runs/{name}/run_meta.json') or {}
    return r if r and m.get('complete') else None


def gpu_days():
    """logs/gpu_day 의 실제 실행(예행 연습·실패 제외)에서 적재 시간, GPU 메모리, 속도를 읽는다."""
    out = []
    for d in sorted(glob.glob(str(ROOT / 'logs' / 'gpu_day' / '2026*'))):
        d = Path(d)
        if 'failed' in d.name or not (d / 'summary.md').exists():
            continue
        s, r = (d / 'summary.md').read_text(encoding='utf-8'), (d / 'run.log').read_text(encoding='utf-8') if (d / 'run.log').exists() else ''
        m = re.search(r'서버 경로: (\S+)(?: \((\S+?)\))?', s); load = re.search(r'서버 응답 확인\(\w+, (\d+)초\)', r)
        mem = re.findall(r'(\d+) MiB', (re.search(r'적재 후 GPU 메모리: ([^\n]*)', s) or [None, ''])[1])
        gen = pp = None; is_lora = False
        slog = next(iter(sorted(d.glob('server_*.log'))), None)
        if slog:
            t = slog.read_text(encoding='utf-8', errors='replace'); is_lora = 'Arete-27B-lora' in t[:4000]
            ev = [(int(n), float(ms)) for ms, n in re.findall(r'\n[^\n]*\|\s+eval time =\s*([\d.]+) ms /\s*(\d+) tokens', t) if int(n) >= 20]
            pe = [(int(n), float(ms)) for ms, n in re.findall(r'prompt eval time =\s*([\d.]+) ms /\s*(\d+) tokens', t) if int(n) >= 1000]
            gen = sum(n for n, _ in ev) / (sum(ms for _, ms in ev) / 1000) if ev else None
            pp = sum(n for n, _ in pe) / (sum(ms for _, ms in pe) / 1000) if pe else None
            restored, full = t.count('restored context checkpoint'), t.count('forcing full prompt re-processing')
        else:
            restored = full = 0
        checks = re.findall(r'- 질문 (\d) 「([^」]*)」: ([^,]*), (\d+)초', s)
        out.append({'dir': d.name, 'path': m.group(1) if m else '', 'quant': (m.group(2) if m else '') or '', 'load': int(load.group(1)) if load else None, 'mem': [int(x) for x in mem[:2]],
                    'gen': gen, 'pp': pp, 'restored': restored, 'full': full, 'checks': checks, 'lora': is_lora})
    return out


def pipeline_state():
    P = ROOT / 'logs' / 'pipeline'
    st = {}
    for k in ('S1_q5', 'S2_q4', 'S3_q6', 'F1_smoke', 'F2_train', 'F3_merge', 'F4_gguf', 'F5_eval_short', 'F6_eval_long'):
        st[k] = '완료' if (P / f'{k}.done').exists() else '실패' if (P / f'{k}.failed').exists() else '대기'
    log = (P / 'pipeline.log').read_text(encoding='utf-8').splitlines() if (P / 'pipeline.log').exists() else []
    for k in st:                                     # 시작했지만 끝나지 않은 단계
        if st[k] == '대기' and any(re.search(rf'\] {k.split("_")[0]}[_ ]', l) and '시작' in l or (k.startswith('F') and re.search(rf'\] {k.split("_")[0]} ', l)) for l in log):
            st[k] = '진행 중'
    return st, log


def finetune_info():
    P = ROOT / 'logs' / 'pipeline'
    info = {'config': None, 'peak': None, 'meta': jload('06_build/runs/lora_assistant_v1/training_meta.json'), 'loss': None, 'smoke_tries': 0, 'eta': None}
    if (P / 'finetune_config.env').exists():
        t = (P / 'finetune_config.env').read_text()
        a, b = re.search(r'MAX_LEN=(\d+)', t), re.search(r'SPLIT_AT=(\d+)', t)
        info['config'] = (int(a.group(1)), int(b.group(1))) if a and b else None
    sm = sorted(P.glob('F1_smoke.try*.log'))
    info['smoke_tries'] = len(sm)
    info['smoke_failed'] = len(list((P / 'F1_1차실패_1116').glob('F1_smoke.try*.log')))      # 학습 스크립트를 고치기 전의 실패 기록
    for f in sm:
        m = re.search(r'GPU 메모리 최고 사용량: ([^\n]*)', f.read_text(encoding='utf-8', errors='replace'))
        if m:
            info['peak'] = m.group(1)
    steps = []
    for f in sorted(P.glob('F2_train.try*.log')):
        for m in re.finditer(r'step (\d+)/(\d+) loss=([\d.]+).*?경과=(\d+)분 남은=(\d+)분', f.read_text(encoding='utf-8', errors='replace')):
            steps.append((int(m.group(1)), int(m.group(2)), float(m.group(3)), int(m.group(4)), int(m.group(5))))
    plog = (P / 'pipeline.log').read_text(encoding='utf-8', errors='replace') if (P / 'pipeline.log').exists() else ''
    def span(a, b):                                   # 기록의 마지막 「a」 줄부터 그 뒤의 첫 「b」 줄까지의 분
        ta = [m.group(1) for m in re.finditer(rf'\[(\d{{4}}-\d\d-\d\d \d\d:\d\d:\d\d)\] {a}', plog)]
        if not ta:
            return None
        tb = [m.group(1) for m in re.finditer(rf'\[(\d{{4}}-\d\d-\d\d \d\d:\d\d:\d\d)\] {b}', plog) if m.group(1) >= ta[-1]]
        f = lambda s: time.mktime(time.strptime(s, '%Y-%m-%d %H:%M:%S'))
        return round((f(tb[0]) - f(ta[-1])) / 60) if tb else None
    info['merge_min'], info['gguf_min'] = span('F3 병합', 'F3 끝'), span('F4 변환', 'F4 끝')
    if steps:
        k = max(1, len(steps) // 10)
        info['loss'] = (sum(s[2] for s in steps[:k]) / k, sum(s[2] for s in steps[-k:]) / k, steps[-1][0], steps[-1][1])
        info['eta'] = steps[-1][4]
    return info


# ───────────────────────── 고정 내용 ─────────────────────────
GLOSSARY = [
    ('모형 일반', [
        ('언어모형(LLM)', '많은 글을 학습해 다음에 올 낱말을 예측하는 방식으로 글을 만들어 내는 프로그램. 질문에 답하거나 코드를 작성하는 데 쓰임', '자연어 질문을 분석 코드로 옮기고 실행 결과를 설명하는 일을 맡김'),
        ('로컬 모형', '외부 서비스에 접속하지 않고 기관 안의 설비에서 직접 구동하는 언어모형', '폐쇄망에서는 외부 서비스를 쓸 수 없으므로 내부 설비(GPU 2장)에 적재하여 사용함'),
        ('매개변수·가중치', '모형이 학습으로 얻은 수치의 집합. 개수가 많을수록 표현력이 크고 필요한 메모리도 큼. 27B는 270억 개를 뜻함', '지정 모형은 약 270억 개이며 공식 저장소의 파일 크기는 54.7GB임'),
        ('토큰', '모형이 글을 처리하는 단위. 한국어는 한 낱말이 1~3개 토큰으로 나뉨. 입력과 출력의 길이, 처리 속도를 토큰 수로 잼', '질문 1건의 입력은 약 4,000토큰, 응답은 150~350토큰임'),
        ('문맥 길이', '모형이 한 번에 읽을 수 있는 토큰 수의 상한', '서버에 16,384토큰으로 설정함'),
        ('추론', '학습이 끝난 모형에 입력을 주고 응답을 받는 일. 학습(가중치를 바꾸는 일)과 구분함', '평가와 실제 이용은 모두 추론에 해당함'),
        ('프롬프트·시스템 프롬프트', '모형에 주는 입력 글. 시스템 프롬프트는 대화 맨 앞에 두는 고정 지침으로 역할, 작업 순서, 응답 형식을 정함', '긴 판(미세조정 없는 모형용)과 짧은 판(미세조정한 모형용)을 둠'),
        ('대화 틀(chat template)', '역할(시스템, 이용자, 모형)별 글을 모형이 학습한 형식의 한 줄 글로 이어 붙이는 규칙. 모형마다 다름', '공식 저장소의 대화 틀을 그대로 쓰고, 서버가 적용한 결과가 같은지 대조함'),
        ('사고 과정 출력', '일부 모형이 답을 내기 전에 풀이 과정을 따로 출력하는 기능', '응답 형식을 고정하기 위해 끔. 이 모형은 끄는 인자를 주지 않으면 켜짐'),
    ]),
    ('설비와 구동', [
        ('GPU·GPU 메모리(VRAM)', '행렬 계산을 빠르게 하는 장치와 그 전용 메모리. 모형의 가중치를 GPU 메모리에 적재해야 실용적인 속도가 나옴', 'RTX 5060 Ti 16GB 2장에 모형을 나누어 적재함'),
        ('양자화', '가중치 하나를 16비트 대신 4~6비트로 줄여 저장하는 일. 파일과 메모리 소요가 줄고 정밀도는 조금 낮아짐', '54.7GB 모형을 15~21GiB로 줄여 GPU 2장에 적재함'),
        ('GGUF, Q4_K_M·Q5_K_M·Q6_K', 'GGUF는 llama.cpp가 쓰는 모형 파일 형식. 뒤의 이름은 양자화 수준으로 숫자가 클수록 정밀하고 파일이 큼', 'Q5_K_M을 기본으로 쓰고 Q4_K_M·Q6_K와 평가 결과를 비교함'),
        ('bf16', '가중치를 16비트로 적은 형식. 공식 가중치와 양자화 전 중간 파일이 이 형식임', '양자화본을 만들 때 거치는 중간 파일(50.1GiB)'),
        ('적재', '모형 파일을 읽어 RAM이나 GPU 메모리에 올리는 일. 적재가 끝나야 서버가 요청에 응답함', 'Q5_K_M 양자화본의 적재에 약 3분이 걸림'),
        ('추론 서버·llama.cpp', '모형을 메모리에 적재해 두고 요청이 오면 응답을 회신하는 프로그램. llama.cpp는 양자화본을 구동하는 공개 소프트웨어', '하네스는 서버의 주소로 요청을 보냄. 서버는 폐쇄망 안에서만 응답함'),
        ('4비트 적재', '공식 가중치를 적재하면서 4비트로 줄이는 방식(변환 파일을 따로 만들지 않음)', '미세조정에 쓰고, llama.cpp 서버가 기동되지 않을 때의 예비 경로로 둠'),
        ('문맥 저장 지점·예열', '서버가 이미 처리한 입력의 상태를 저장해 두었다가 같은 앞부분이 다시 오면 이어서 처리하는 기능. 예열은 그 저장 지점을 미리 만드는 요청', '질문마다 시스템 프롬프트를 다시 처리하지 않도록 예열 요청을 한 번 보냄'),
        ('HDD·SSD, 페이지 캐시', '저장 장치의 종류와, 운영체제가 읽은 파일을 RAM에 임시로 두는 영역', '모형 파일은 HDD에 있어 읽는 속도가 느림. 읽는 방식에 따라 메모리 압력이 달라짐(7절)'),
    ]),
    ('학습', [
        ('미세조정', '이미 학습된 모형을 특정 과제의 예시로 추가 학습시키는 일', '분석 지원 방식의 대화 예시 1,179건으로 수행'),
        ('LoRA·QLoRA, 어댑터', '가중치 전체를 바꾸지 않고 작은 보조 행렬(어댑터)만 학습시키는 방법. QLoRA는 기반 모형을 4비트로 적재한 상태에서 LoRA를 학습시키는 방법', 'GPU 메모리 16GB 2장으로 27B 모형을 학습시키기 위해 사용'),
        ('에폭, 스텝', '에폭은 학습 자료 전체를 한 차례 학습하는 단위, 스텝은 가중치를 한 번 갱신하는 단위', '3에폭 학습'),
        ('체크포인트', '학습 도중의 상태를 저장한 것. 중단되면 그 지점부터 이어서 학습함', '50스텝마다 저장'),
        ('스모크 시험', '본 작업 전에 짧게 실행하여 장치와 설정이 맞는지 확인하는 시험', '가장 긴 예시 8건으로 메모리가 충분한지 확인한 뒤 본 학습에 들어감'),
        ('병합', '학습한 어댑터를 기반 가중치에 더해 하나의 모형으로 만드는 일', 'llama.cpp 서버로 구동하기 위해 병합 후 다시 양자화함'),
    ]),
    ('하네스와 통제', [
        ('하네스(조립기)', '모형의 앞뒤에서 입력을 조립하고, 모형이 쓴 코드를 점검·실행하고, 결과를 확인해 회신하는 프로그램의 묶음', '확인 절차를 모형에 맡기지 않고 하네스가 수행하도록 설계함'),
        ('참고 자료 카드·검색', '질문과 관련된 변수 정의, 제도 설명, 규칙을 짧은 글로 만든 것과, 질문마다 관련 카드를 선별하여 추가하는 기능', '모형은 이 자료의 변수명을 학습한 적이 없으므로 질문마다 정의를 제시함'),
        ('분석 함수 묶음(ssda)', '집계 결과만 회신하도록 만든 파이썬 함수 모음. 비율, 평균, 합계, 분위수, 인원, 구성비, 빈곤율과 그림 함수', '모형은 이 함수를 부르는 코드만 작성함'),
        ('출력 통제·억제', '관측 수가 적은 칸을 표시하지 않는 등 개인이 식별되지 않게 하는 규칙. 보충 억제는 합계에서 역산되지 않도록 추가로 표시하지 않는 것', '함수 안에 포함함: 등급별 최소 관측 10·20·30건, 분류 기준 수 제한'),
        ('실행 전 점검·격리 실행', '모형이 쓴 코드에 금지된 표현(파일 접근, 자료 직접 읽기 등)이 있는지 실행 전에 검사하고, 통과한 코드만 별도 프로세스에서 시간·메모리 한도를 적용하여 실행하는 것', '위반 코드는 실행되지 않음'),
        ('검증 결과·수치 대조·검증 요약', '실행기가 산출 결과를 자동 점검한 내역, 응답에 적힌 수치가 실행 결과에 있는 값인지의 대조, 그 내역을 응답 끝에 추가한 요약', '잘못된 값이 정상적인 형식으로 제시되는 일을 줄이기 위함'),
        ('유사 예시 삽입', '질문과 비슷한 처리 예를 학습 자료에서 골라 프롬프트에 삽입하는 방법', '미세조정 없이 성능을 높이는 수단으로 평가함'),
    ]),
    ('평가와 운영', [
        ('벤치마크·안전성 시험', '정답이 정해진 평가 문항 모음. 안전성 시험은 응하지 말아야 할 요청에 대한 반응을 봄', '벤치마크 121문항, 안전성 시험 40문항'),
        ('모의 모형', '모형 없이 하네스와 채점기를 점검하기 위해 정해진 방식으로 답하는 프로그램', '정답 코드를 답하는 것, 통제 위반 코드를 쓰는 것, 의도적으로 잘못 답하는 것 3종'),
        ('보류 검증 문항', '설정을 고칠 때 참고하지 않고 따로 둔 평가 문항. 고친 설정의 효과가 참고한 문항 밖에서도 나타나는지 확인하는 데 씀', '프롬프트 개선판의 확인을 위해 43문항을 새로 작성함'),
        ('축소 모형', '구조는 실제 모형과 같고 크기만 작게 만든 시험용 모형(가중치는 무작위)', 'GPU 없이 서버·학습·변환 스크립트의 코드 경로를 확인하는 데 씀'),
        ('폐쇄망·반입', '외부 통신망과 분리된 전산 환경과, 외부의 파일을 그 안으로 옮기는 절차', '모형, 도구, 준비 자료의 목록과 해시를 반입 목록으로 정리함'),
        ('해시(SHA-256)', '파일 내용에서 계산한 고유한 값. 파일이 바뀌면 값이 달라짐', '내려받은 가중치가 공식 저장소의 것과 같은지 대조함'),
        ('메모리 압력·systemd-oomd', '프로그램이 메모리를 기다리며 멈춘 시간의 비율과, 그 비율이 높으면 프로그램 묶음을 종료하는 운영체제 기능', '모형 적재 중 이 기능에 의해 작업이 종료된 일이 있었음(7절)'),
        ('작업 단위(scope)', '운영체제가 프로그램 묶음을 관리하는 단위. 묶음별로 일시 정지, 종료, 자원 제한을 적용할 수 있음', '긴 작업을 화면 세션과 분리해 실행하고 압력 감시를 함께 둠'),
    ]),
]

PRINCIPLES = [
    ('모형은 분석 자료를 읽지 않음', '모형에 전달되는 것은 질문, 참고 자료 카드, 집계 결과의 출력뿐임. 모형이 쓴 코드는 집계 전용 함수만 부를 수 있음', '개인 단위 자료가 모형의 입력·출력·기록에 남지 않게 하기 위함. 통제를 모형의 지침 준수에 맡기지 않음'),
    ('출력 통제는 함수 안에서 적용', '최소 관측 수, 보충 억제, 분류 기준 수 제한을 분석 함수가 수행함', '어떤 코드가 작성되더라도 통제를 거친 결과만 나오게 하기 위함'),
    ('확인 절차는 하네스가 수행', '분모 점검, 수치 대조, 변수 정의 확인 등은 프로그램이 수행하고 모형은 그 결과를 읽고 대처함', '로컬 모형이 지침을 일정하게 지키지 못하는 경우에도 확인이 빠지지 않게 하기 위함'),
    ('평가 문항과 기준을 먼저 정함', '모형을 적재하기 전에 문항, 정답, 채점기, 기준(안)을 확정함', '결과를 본 뒤 기준을 정하면 평가가 판단 근거로 기능하지 못함'),
    ('GPU 없이 수행할 수 있는 작업을 우선 완료함', '자료, 도구, 변환, 코드 경로 시험, 예행 연습을 GPU 사용 전에 수행함', 'GPU는 다른 작업과 함께 쓰는 자원이어서 사용 가능 시간이 한정됨'),
    ('공식 자료에서 직접 만듦', '제3자가 변환한 모형 파일을 받지 않고 공식 가중치에서 직접 변환함. 출처, 판, 해시를 기록함', '폐쇄망 반입 심사에서 출처와 동일성을 설명할 수 있어야 함'),
]

SIDO_FIX = ('조건식에서는 같은 이름의 변수를 먼저 찾도록 분석 함수를 수정하고 시도 조건의 산출값을 변수 사전의 코드값과 대조함' if '조건식에서는 변수 사전의 코드값으로 해석' in (ROOT / '02_library' / 'ssda' / 'core.py').read_text(encoding='utf-8')
            else '평가 실행 간의 비교 가능성을 유지하기 위해 현행 분석 함수는 두고 보완본(0.4.1)에서 수정함(조건식에서는 같은 이름의 변수를 먼저 찾음). 목표 도달로 대책을 실행하지 않아 현행에는 반영되지 않았으며 실사용 전에 반영함. 학습 자료의 해당 예시 97건은 수정 후의 해석과 일치함')

PROBLEMS = [
    ('변환 중 메모리 상한 초과로 중단', '변환 도구가 가장 큰 텐서를 처리할 때 중간 결과를 모두 누적하여 약 11GB를 사용함', '같은 결과를 내면서 메모리를 덜 쓰도록 변환 도구의 처리 방식을 수정하여 실행함. 축소 모형에서 산출 파일이 바이트 단위로 같음을 확인함', '무거운 CPU 작업에는 메모리 상한을 적용하여 다른 작업을 보호하고, 상한에 걸리면 원인을 찾아 사용량을 줄임'),
    ('실행 중인 셸 스크립트를 수정하여 실행이 중단됨', '셸은 스크립트를 읽어 가며 실행하므로 실행 중 파일이 바뀌면 오류가 발생함', '완성된 중간 파일을 두고 다시 실행함(이미 만든 파일은 건너뜀)', '실행 중인 스크립트는 수정하지 않고, 단계마다 끝난 표시를 남겨 다시 실행할 수 있게 함'),
    ('서버가 응답 대신 오류(500)를 회신함', '출력에 온전하지 않은 글자가 포함되면 서버가 응답을 해석하지 못함', '모형 연결부가 원문 생성 방식으로 한 번 더 받도록 예비 경로를 둠', '서버 오류가 발생한 문항만 건너뛰고 평가를 계속하며, 이어서 실행할 수 있게 함'),
    ('어댑터를 llama.cpp 형식으로 변환하지 못함', 'llama.cpp의 어댑터 변환 도구가 이 모형 구조의 일부 층을 지원하지 않음', '어댑터를 기반 가중치에 합친 뒤 모형 전체를 다시 변환하는 도구를 만들고 기존 병합 방식의 결과와 대조함', '도구의 지원 범위는 축소 모형으로 미리 확인함'),
    ('모형이 분석 함수의 인자 이름을 추측하여 잘못 작성함', '미세조정하지 않은 모형은 이 함수의 사용법을 학습한 적이 없고, 검색된 참고 자료에 사용법이 없으면 추측하여 작성함', '시스템 프롬프트에 함수 사용법을 추가하고, 인자 오류가 발생하면 실행기가 해당 함수의 사용법을 회신하게 함', '실제 모형의 실수 유형은 실제 모형으로만 확인되므로 GPU 사용 전에 CPU로 일부 문항을 처리해 봄'),
    ('구간 이름이 한 칸씩 밀린 표가 그대로 인용됨', '구간 경계와 항목 이름의 개수를 맞추는 과정에서 모형이 경계를 하나 제외함. 실행은 성공하므로 기존 점검에 걸리지 않음', '분석 함수가 항목 이름에 적힌 수를 구간 경계와 대조해 일치하지 않으면 오류로 회신하게 함', '실행이 성공해도 틀린 값이 나오는 유형은 함수 안의 점검으로 막음'),
    ('질문마다 시스템 프롬프트를 처음부터 다시 처리', '이 모형 구조에서는 서버가 입력의 앞부분을 임의 위치부터 이어 쓰지 못함', '시작할 때 예열 요청을 보내 서버에 저장 지점을 남김. 문항 첫 호출의 처리량이 약 4,100토큰에서 약 2,240토큰으로 줄어듦', '서버 기록에서 재처리 횟수를 확인함'),
    ('모형 적재 중에 평가가 시작됨', '서버가 모형을 적재하는 동안 회신하는 「적재 중」 응답을 기동 완료로 판정함. 축소 모형은 즉시 적재되어 예행 연습에서는 나타나지 않음', '기동 판정을 수정하고, 모형 연결부가 「적재 중」 응답에는 대기 후 다시 요청하게 함', '예행 연습이 실제와 다른 지점(파일 크기, 적재 시간)을 따로 점검함'),
    ('산출해야 할 질문에 모형이 확인을 요청함', '시스템 프롬프트가 「가정에 따라 결과가 크게 달라지면 확인을 요청한다」고만 정하여, 분모·변수·분류 기준이 질문에 적혀 있거나 기본 해석이 정해진 경우에도 모형이 확인을 요청함. 변수 카드의 「추출 대상」 설명을 분모의 불확실성으로 해석한 사례가 많음', '확인을 요청하는 경우를 두 가지(제도·지표가 없어 변수를 정할 수 없는 경우, 용어 확인 카드가 지시한 경우)로 한정하고 그 밖의 사항은 기본 해석으로 산출하도록 한 개선판 프롬프트를 작성함. 같은 문항과 따로 만든 문항으로 효과를 확인함(6.6)', '통과하지 못한 문항을 원인 유형으로 분류하여 비중이 큰 유형부터 대처함. 프롬프트를 고친 효과는 참고하지 않은 문항으로 확인함'),
    ('조건식에서 시도 값이 변수 사전과 다르게 해석됨', '분석 함수가 조건식의 이름을 표준 분류 기준에서 먼저 찾아, 같은 이름의 변수(시도, 코드값 1~17)가 있어도 분류 기준의 순번(0~16)으로 해석함. 변수 사전에서 1은 서울이나 조건식 「sido == 1」의 대상은 부산으로 산출됨. 벤치마크의 정답 코드에는 시도 조건이 없어 평가에서 드러나지 않았고, 미통과 원인을 분석하는 과정에서 확인됨', SIDO_FIX, '분류 기준과 변수의 이름이 겹치는 경우를 점검 항목에 추가함. 정답과 학습 자료를 같은 함수로 만들면 함수의 결함이 평가에 드러나지 않으므로 변수 사전의 코드값과 따로 대조함'),
    ('모형 적재 중 운영체제가 작업과 화면 세션을 종료', '서버가 17.9GiB 파일을 HDD에서 메모리 매핑(전체 미리 읽기)으로 적재하는 동안 세션의 메모리 압력이 72%에 이르러 압력 감시 기능이 프로그램 묶음을 종료함. RAM은 26GB가 남아 있었음', '파일을 직접 읽는 방식(페이지 캐시를 거치지 않음)으로 변경하고, 작업을 화면 세션과 분리해 실행하며, 세션의 압력이 오르면 작업을 일시 정지하는 감시를 함께 둠. 같은 파일의 적재에서 압력 0.0%를 확인함', '종료의 원인이 메모리 부족인지 압력 감시인지를 운영체제 기록으로 구분함. 긴 작업은 세션과 분리해 실행함'),
    ('미세조정 스모크 시험이 GPU 메모리 부족으로 7회 모두 실패함', '어휘가 248,320개여서 모형의 기본 손실 계산은 1,536토큰 전체 위치의 출력값(1.42GiB)과 같은 크기의 텐서를 여러 개 사용함. 이 계산이 임베딩(2.37GiB), 출력층(2.37GiB), 앞쪽 층과 함께 GPU 0에 배치되어 있었음. 분할 위치 28에서는 초기화 함수가 이미 적재된 출력층 가중치의 사본(4.74GiB)을 생성하여 적재 단계에서 실패함. 같은 설비의 이전 학습은 512토큰 길이여서 이 문제가 나타나지 않았고, 축소 모형의 CPU 시험으로는 메모리 소요를 확인할 수 없었음', '출력층을 마지막 층과 같은 GPU 1에 배치하고, 응답 구간의 위치만 골라 128개씩 나누어 손실을 계산하도록 학습 스크립트를 수정함. 적재된 출력층 가중치의 초기화를 건너뛰게 하고, 분할 위치를 두 GPU의 적재량이 비슷한 34로 변경함. 축소 모형에서 손실과 기울기가 기본 손실과 같음을 확인한 뒤 다시 실행하여 1회째에 통과함(길이 상한 1,536토큰 유지)', '분할 위치 이동과 길이 상한 축소로 구성한 재시도 규칙은 메모리 소요가 층의 배치에 달린 경우에만 유효함. 실패 기록에서 실패한 단계(적재, 손실 계산, 역전파)를 먼저 확인함. 어휘 수가 큰 모형은 손실 계산의 메모리를 따로 산정함'),
]

CHECKLIST = [
    ('요구와 원칙', ['모형의 역할을 한 문장으로 한정함', '모형에 전달되는 정보와 전달되지 않는 정보를 정함', '결정권자가 정할 사항을 문서로 분리함']),
    ('분석 함수와 통제', ['모형이 부를 수 있는 함수를 집계 전용으로 한정함', '출력 통제를 함수 안에 포함함', '실행 전 점검과 격리 실행을 둠', '통제 위반 시험 코드가 차단되는지 확인함']),
    ('지식 자료', ['변수 사전과 카드를 만들고 검색 색인을 구축함', '제도명·약어 사전을 만들고 모호한 용어의 확인 규칙을 정함']),
    ('프롬프트·학습 자료·평가 자료', ['응답 형식을 고정함', '학습 예시의 코드를 전수 재실행해 기록과 대조함', '평가 문항·정답·채점기·기준(안)을 모형 구동 전에 확정함', '모의 모형으로 채점기를 점검함']),
    ('모형 반입', ['공식 저장소에서 내려받고 출처·판·해시를 기록함', '구조 값, 가중치 이름, 대화 틀, 사고 과정 출력의 기본값을 점검함', '설비에 적재할 수 있는 양자화 수준을 계산함']),
    ('GPU 사용 전 준비', ['양자화본을 직접 만들고 공식 가중치와 대조함', '서버 실행 파일을 빌드함', '축소 모형으로 서버·학습·변환 경로를 끝까지 실행함', '실제 양자화본을 CPU로 구동해 일부 문항을 처리하고 하네스를 보완함', '일괄 실행 절차를 예행 연습함']),
    ('GPU 구동', ['긴 작업은 화면 세션과 분리해 실행하고 압력 감시를 함께 둠', '모형 파일은 직접 읽기로 적재함', '적재 후 GPU 메모리와 생성 속도를 기록함', '연결 확인 질문으로 핵심 동작을 먼저 봄']),
    ('평가와 미세조정', ['기본 구성으로 전 문항을 평가하고 기준과 대조함', '양자화 수준과 유사 예시 삽입의 효과를 같은 문항으로 비교함', '미세조정은 스모크 시험으로 메모리를 확인한 뒤 수행함', '미세조정 전후를 같은 문항으로 비교함', '통과하지 못한 문항을 원인 유형으로 분류함', '프롬프트를 고친 경우 참고하지 않은 문항으로 효과를 확인함']),
]

CSS = '''
  @page { size: A4; margin: 15mm 12mm 16mm 12mm; }
  :root { --ink:#1C1C1A; --paper:#F0EFEB; --muted:#6B6A64; --line:#D8D7D1; --head:#1C1C1A; }
  * { box-sizing: border-box; }
  html { font-size: 15px; }
  body { margin: 0; color: var(--ink); background: #fff; line-height: 1.58; -webkit-font-smoothing: antialiased;
         font-family: "KoPubDotum", "KoPub돋움체", "Noto Sans KR", "Noto Sans CJK KR", "NanumGothic", "Malgun Gothic", "Apple SD Gothic Neo", sans-serif; }
  .wrap { max-width: 1080px; margin: 0 auto; padding: 28px 24px 60px; }
  h1 { font-size: 1.5rem; margin: 0 0 6px; letter-spacing: -.02em; line-height: 1.3; }
  h2 { font-size: 1.18rem; margin: 34px 0 10px; padding: 6px 10px; color: #fff; background: var(--head); letter-spacing: -.01em; }
  h3 { font-size: 1.04rem; margin: 24px 0 8px; padding-bottom: 3px; border-bottom: 2px solid var(--ink); }
  h4 { font-size: .95rem; margin: 14px 0 4px; }
  p { margin: 5px 0; } ul, ol { margin: 4px 0 8px; padding-left: 21px; } li { margin: 2px 0; }
  table { border-collapse: collapse; width: 100%; margin: 8px 0 12px; font-size: .85rem; }
  th, td { border: 1px solid var(--line); padding: 4px 7px; vertical-align: top; text-align: left; }
  th { background: var(--paper); font-weight: 700; }
  td.n, th.n { text-align: right; white-space: nowrap; } td.c, th.c { text-align: center; white-space: nowrap; }
  td.k { white-space: nowrap; font-weight: 700; } td.kw { font-weight: 700; width: 16%; }
  th.w, td.w { text-align: center; white-space: normal; word-break: keep-all; }
  code { font-family: "D2Coding", "Noto Sans Mono CJK KR", "DejaVu Sans Mono", Consolas, monospace; font-size: .86em; background: var(--paper); padding: 0 3px; }
  .meta { font-size: .86rem; color: #55554F; margin-bottom: 14px; }
  .box { border: 1px solid var(--line); border-left: 5px solid var(--ink); padding: 8px 12px; margin: 10px 0; background: #FAFAF8; }
  .small { font-size: .83rem; color: #55554F; }
  .tag { display: inline-block; font-size: .76rem; padding: 0 5px; border: 1px solid var(--ink); border-radius: 2px; white-space: nowrap; }
  .tag.hold { border-style: dashed; color: var(--muted); border-color: var(--muted); }
  table.stage td.h { width: 11%; background: var(--paper); font-weight: 700; white-space: nowrap; }
  td.ok { font-weight: 700; } td.ng { color: #8A3B12; font-weight: 700; }
  .toc { columns: 2; column-gap: 28px; font-size: .9rem; } .toc li { break-inside: avoid; }
  @media print {
    html { font-size: 10pt; } .wrap { max-width: none; padding: 0; }
    h2, h3, h4 { break-after: avoid; } tr { break-inside: avoid; } .box { break-inside: avoid; }
    .no-print { display: none !important; } table { font-size: 8.3pt; }
  }
'''


def stage(title, rows):
    """단계 설명 표: (한 일, 이유, 확인 방법, 결과)"""
    labels = ['수행 내용', '절차를 둔 이유', '확인 방법', '결과']
    body = ''.join(f'<tr><td class="h">{l}</td><td>{("<ul>" + "".join(f"<li>{x}</li>" for x in r) + "</ul>") if isinstance(r, (list, tuple)) else r}</td></tr>' for l, r in zip(labels, rows) if r)
    return f'<h3>{title}</h3>\n<table class="stage">{body}</table>\n'


def main():
    now = jload('현황.json') or {}
    bst = jload('05_eval/benchmark_stats.json') or {}
    crit = (jload('05_eval/criteria.json') or {}).get('기준', {})
    gc = jload('모형반입/gguf_check.json') or {'files': []}
    gq = {f['file'].split('-')[-1].replace('.gguf', ''): f for f in gc['files'] if '-lora-' not in f['file']}
    rs = jload('모형반입/cpu_real_smoke.json') or {}
    n_tr, n_va, n_te = (nlines(f'04_training/data/{s}.jsonl') for s in ('train', 'valid', 'test'))
    runs = {name: load_run(name) for name, *_ in RUNS}
    days = gpu_days(); st, plog = pipeline_state(); ft = finetune_info()
    findings = jload('docs/process_doc_findings.json') or {}
    first = next((d for d in days if d['quant'] == 'Q5_K_M' and not d['lora']), None)
    g = lambda q, k: f"{gq[q][k]}" if q in gq else '—'
    tag = lambda s: f'<span class="tag{" hold" if s in ("대기",) else ""}">{s}</span>'
    done_all = (ROOT / 'logs' / 'pipeline' / 'FINETUNE_ALL.end').exists()
    status = (('준비, 모형 반입, GPU 구동, 평가, 미세조정, 보완본 반영 뒤의 재평가, 하네스 보완 뒤의 재평가까지 수행 완료' if (ROOT / 'logs' / 'pipeline' / 'HOOKS_ALL.end').exists()
               else '준비, 모형 반입, GPU 구동, 평가, 미세조정, 보완본 반영 뒤의 재평가까지 수행 완료' if (ROOT / 'logs' / 'pipeline' / 'REEVAL_ALL.end').exists() else '준비, 모형 반입, GPU 구동, 평가, 미세조정까지 수행 완료') if done_all else
              'GPU 구동 중 — ' + ', '.join(f"{lab} {st[k]}" for k, lab in (('S1_q5', '기본 평가'), ('S2_q4', 'Q4_K_M 평가'), ('S3_q6', 'Q6_K 평가'), ('F2_train', '미세조정 학습'), ('F5_eval_short', '미세조정 모형 평가'))))

    # ── 평가 결과 표 ──
    def cell(name, k):
        r = runs[name]
        if not r['rep']:
            return '<td class="c small">—</td>'
        v = r['rep']['metrics'].get(k)
        if v is None:
            return '<td class="c small">해당 없음</td>'
        j = r['rep'].get('judge', {}).get(k)
        return f'<td class="n {"ok" if j else "ng" if j is False else ""}">{v}</td>'
    head = ''.join(f'<th class="w">{q}<br><span class="small">예시 {ex}<br>{sp}</span></th>' for _, q, ex, sp, _ in RUNS)
    crit_txt = lambda k: (f"{crit[k]['값']} {crit[k]['방향']}" if k in crit else '—')
    rows_m = ''.join(f'<tr><td class="k">{k}</td><td class="c">{crit_txt(k)}</td>' + ''.join(cell(n, k) for n, *_ in RUNS) + '</tr>' for k in METRICS)
    rows_m += '<tr><td class="k">종합 판정</td><td class="c">전 지표 충족</td>' + ''.join(
        f'<td class="c {"ok" if r["rep"] and r["rep"]["passed"] else "ng" if r["rep"] else "small"}">{("충족" if r["rep"]["passed"] else "미달") if r["rep"] else r["state"]}</td>' for r in (runs[n] for n, *_ in RUNS)) + '</tr>'

    def usage_cell(name, f):
        r = runs[name]
        return f'<td class="n">{f(r)}</td>' if r['rep'] else '<td class="c small">—</td>'
    usage_cell_r = lambda r: f'<td class="n">{fmt_min(r["meta"].get("elapsed_sec"))}</td>' if r['rep'] else '<td class="c small">—</td>'
    rows_u = ('<tr><td class="k">소요 시간</td>' + ''.join(usage_cell(n, lambda r: fmt_min(r['meta'].get('elapsed_sec'))) for n, *_ in RUNS) + '</tr>'
              + '<tr><td class="k">모형 호출 횟수</td>' + ''.join(usage_cell(n, lambda r: f"{(r['meta'].get('usage') or {}).get('calls', 0):,}") for n, *_ in RUNS) + '</tr>'
              + '<tr><td class="k">입력 토큰</td>' + ''.join(usage_cell(n, lambda r: f"{(r['meta'].get('usage') or {}).get('prompt_tokens', 0):,}") for n, *_ in RUNS) + '</tr>'
              + '<tr><td class="k">출력 토큰</td>' + ''.join(usage_cell(n, lambda r: f"{(r['meta'].get('usage') or {}).get('completion_tokens', 0):,}") for n, *_ in RUNS) + '</tr>')
    cats = list((bst.get('by_category') or {}).keys())
    rows_c = ''.join(f'<tr><td class="k">{c}</td><td class="n">{bst["by_category"][c]}</td>' + ''.join(
        (f'<td class="n">{runs[n]["rep"]["by_category"].get(c, "—")}</td>' if runs[n]['rep'] else '<td class="c small">—</td>') for n, *_ in RUNS) + '</tr>' for c in cats)
    head_s = ''.join(f'<th class="w">{q}<br><span class="small">예시 {ex}<br>{sp}</span></th>' for _, q, ex, sp, _ in RUNS)

    # ── GPU 실측 표 ──
    def dq(q, lora=False):
        return next((d for d in reversed(days) if (d['lora'] if lora else (d['quant'] == q and not d['lora']))), None)
    def gpu_row(label, d, size):
        if not d:
            return f'<tr><td class="k">{label}</td><td class="n">{size}</td><td class="c small" colspan="5">대기</td></tr>'
        return (f'<tr><td class="k">{label}</td><td class="n">{size}</td><td class="n">{d["load"] or "—"}초</td><td class="n">{" · ".join(f"{m / 1024:.1f}GiB" for m in d["mem"]) or "—"}</td>'
                f'<td class="n">{d["gen"]:.1f}</td><td class="n">{d["pp"]:,.0f}</td><td class="n">{d["restored"]:,}회 / {d["full"]}회</td></tr>') if d['gen'] and d['pp'] else \
               (f'<tr><td class="k">{label}</td><td class="n">{size}</td><td class="n">{d["load"] or "—"}초</td><td class="n">{" · ".join(f"{m / 1024:.1f}GiB" for m in d["mem"]) or "—"}</td><td class="c small" colspan="3">측정 중</td></tr>')
    gpu_rows = (gpu_row('Q5_K_M', dq('Q5_K_M'), f"{g('Q5_K_M', 'GiB')}GiB") + gpu_row('Q4_K_M', dq('Q4_K_M'), f"{g('Q4_K_M', 'GiB')}GiB") + gpu_row('Q6_K', dq('Q6_K'), f"{g('Q6_K', 'GiB')}GiB")
                + gpu_row('Q5_K_M(미세조정 모형)', dq('', True), '—'))
    chk = ''.join(f'<tr><td class="c">{i}</td><td>{E(q)}</td><td class="c">{E(k)}</td><td class="n">{s}초</td></tr>' for i, q, k, s in (first['checks'] if first else []))

    # ── 미세조정 ──
    fm = ft['meta'] or {}
    if fm:
        ft_txt = (f"학습 완료: 예시 {fm.get('examples'):,}건, {fm.get('epochs')}에폭, {fm.get('steps'):,}스텝, {fm.get('hours')}시간. 길이 상한 {fm.get('max_len'):,}토큰, 분할 위치 {fm.get('split_at')}"
                  + (f". 손실은 학습 초반 평균 {ft['loss'][0]:.2f}에서 종반 평균 {ft['loss'][1]:.4f}로 낮아짐" if ft['loss'] else '')
                  + (f". 메모리 부족으로 건너뛴 예시 {fm.get('oom_skipped')}건" if fm.get('oom_skipped') is not None else '')
                  + (f". 어댑터 병합 {ft['merge_min']}분, 변환·양자화 {ft['gguf_min']}분" if ft.get('merge_min') and ft.get('gguf_min') else ''))
    elif ft['loss']:
        ft_txt = f"학습 진행 중: {ft['loss'][2]:,}/{ft['loss'][3]:,}스텝, 남은 시간 약 {fmt_min((ft['eta'] or 0) * 60)}. 손실은 초반 평균 {ft['loss'][0]:.2f}, 최근 평균 {ft['loss'][1]:.2f}"
    else:
        ft_txt = '평가 단계가 끝난 뒤 시작함(대기)'
    ft_cfg = ((f"처음의 스모크 시험은 {ft['smoke_failed']}회 모두 GPU 메모리 부족으로 실패함(7절). 학습 스크립트를 수정한 뒤 " if ft.get('smoke_failed') else '') + f"스모크 시험 {ft['smoke_tries']}회째에 통과: 길이 상한 {ft['config'][0]:,}토큰, 분할 위치 {ft['config'][1]}" + (f". GPU 메모리 최고 사용량 {E(ft['peak'])}" if ft['peak'] else '')) if ft['config'] else '스모크 시험 전(대기)'

    gl = ''.join(f'<tr><th colspan="3">{grp}</th></tr>' + ''.join(f'<tr><td class="kw">{E(a)}</td><td>{E(b)}</td><td>{E(c)}</td></tr>' for a, b, c in items) for grp, items in GLOSSARY)
    pr = ''.join(f'<tr><td class="kw">{E(a)}</td><td>{E(b)}</td><td>{E(c)}</td></tr>' for a, b, c in PRINCIPLES)
    pb = ''.join(f'<tr><td class="c">{i}</td><td>{E(a)}</td><td>{E(b)}</td><td>{E(c)}</td><td>{E(d)}</td></tr>' for i, (a, b, c, d) in enumerate(PROBLEMS, 1))
    ck = ''.join(f'<tr><td class="kw">{E(a)}</td><td><ul>' + ''.join(f'<li>{E(x)}</li>' for x in xs) + '</ul></td></tr>' for a, xs in CHECKLIST)
    sb = (rs.get('subset') or {}).get('metrics') or {}
    def res_summary():
        if not base['rep']:
            return f"기본 구성(Q5_K_M, 유사 예시 없음)의 평가는 {base['state']} 상태임. 결과는 6절에 기재됨"
        m = base['rep']['metrics']; bad = [k for k, v in base['rep']['judge'].items() if v is False]
        return (f"기본 구성(Q5_K_M, 유사 예시 없음)의 평가 결과는 문항 통과율 {m.get('문항 통과율')}, 실행 성공률 {m.get('실행 성공률')}, 산출값 일치율 {m.get('산출값 일치율')}, 거절 정확도 {m.get('거절 정확도')}, 차단 실패 {m.get('차단 실패 건수')}건임. "
                + (f"기준(안)에 미달한 지표는 {', '.join(bad)}임" if bad else '기준(안)의 전 지표를 충족함'))
    # ── 미통과 원인, 개선판 프롬프트 ──
    base = runs['arete27b_q5_base']
    ana, _cmp = load_analysis()
    ana_runs = [(n, q, ex, sp) for n, q, ex, sp, _ in RUNS if n in ana]
    def cause_rows():
        out = ''
        for grp, causes in CAUSE_GROUPS:
            used = [c for c in causes if any(ana[n]['fail_by_cause'].get(c) for n, *_ in ana_runs)]
            for i, c in enumerate(used):
                out += '<tr>' + (f'<td class="k" rowspan="{len(used)}">{grp}</td>' if i == 0 else '') + f'<td>{c}</td>' + ''.join(f'<td class="n">{ana[n]["fail_by_cause"].get(c, 0) or "·"}</td>' for n, *_ in ana_runs) + '</tr>'
        out += '<tr><td class="k" colspan="2">미통과 문항 계</td>' + ''.join(f'<td class="n"><b>{ana[n]["n_fail"]}</b></td>' for n, *_ in ana_runs) + '</tr>'
        out += '<tr><td class="k" colspan="2">통과 문항 계(161문항 중)</td>' + ''.join(f'<td class="n">{ana[n]["n_pass"]}</td>' for n, *_ in ana_runs) + '</tr>'
        return out
    head_a = ''.join(f'<th class="w">{q}<br><span class="small">예시 {ex}<br>{sp}</span></th>' for _, q, ex, sp in ana_runs)
    cause_tbl = (f'<table>\n<tr><th>구분</th><th>원인 유형</th>{head_a}</tr>\n{cause_rows()}\n</table>' if ana_runs else '<p class="small">평가가 끝난 실행이 없음(대기)</p>')
    b_ana = ana.get('arete27b_q5_base')
    top_cause = (max(b_ana['fail_by_cause'].items(), key=lambda kv: kv[1]) if b_ana and b_ana['fail_by_cause'] else None)
    v2 = load_run(V2RUN); v2a = (jload('05_eval/analysis/summary.json') or {}).get('runs', [])
    v2a = next((r for r in v2a if r['run'] == V2RUN and r.get('complete')), None)
    h1, h2 = load_holdout('holdout_q5_v1'), load_holdout('holdout_q5_v2')
    extra_done = (ROOT / 'logs' / 'pipeline' / 'EXTRA_ALL.end').exists()
    V2M = ['문항 통과율', '실행 성공률', '산출값 일치율', '변수 선택 정확도', '그림 산출률', '응답 형식 준수율', '확인 질문 정답률', '제도 용어 문항 통과율', '거절 정확도', '정상 수행률(지시문 혼입)', '통제 위반 코드 작성률', '차단 실패 건수', '평균 모형 호출 횟수']
    def v2cell(r, k):
        if not r['rep']:
            return '<td class="c small">—</td>'
        v, j = r['rep']['metrics'].get(k), r['rep'].get('judge', {}).get(k)
        return f'<td class="n {"ok" if j else "ng" if j is False else ""}">{v}</td>'
    v2_rows = ''.join(f'<tr><td class="k">{k}</td><td class="c">{crit_txt(k)}</td>{v2cell(base, k)}{v2cell(v2, k)}</tr>' for k in V2M)
    v2_rows += ('<tr><td class="k">미통과 문항 가운데 「코드 없이 확인 요청」</td><td class="c">—</td>'
                + (f'<td class="n">{b_ana["fail_by_cause"].get("코드 없이 확인 요청", 0)}</td>' if b_ana else '<td class="c small">—</td>')
                + (f'<td class="n">{v2a["fail_by_cause"].get("코드 없이 확인 요청", 0)}</td>' if v2a else '<td class="c small">—</td>') + '</tr>')
    v2_rows += ('<tr><td class="k">종합 판정</td><td class="c">전 지표 충족</td>' + ''.join(
        f'<td class="c {"ok" if r["rep"] and r["rep"]["passed"] else "ng" if r["rep"] else "small"}">{("충족" if r["rep"]["passed"] else "미달") if r["rep"] else r["state"]}</td>' for r in (base, v2)) + '</tr>')
    def hcell(h, k):
        return f'<td class="n">{h[k]}</td>' if h else '<td class="c small">—</td>'
    HK = [('전체 통과(43문항)', lambda h: f"{h['n_pass']}/{h['n']}"), ('산출해야 하는 문항 통과', lambda h: h['산출 문항 통과']), ('산출해야 하는 문항에서 확인을 요청한 수', lambda h: h['산출 문항에서 되물은 수']),
          ('확인을 요청해야 하는 질문 통과', lambda h: h['되물어야 하는 질문 통과']), ('응하지 않아야 하는 요청 통과', lambda h: h['응하지 않는 요청 통과'])]
    ho_rows = ''.join(f'<tr><td class="k">{lab}</td>' + ''.join((f'<td class="n">{f(h)}</td>' if h else '<td class="c small">—</td>') for h in (h1, h2)) + '</tr>' for lab, f in HK)
    hstat = jload('05_eval/holdout_stats.json') or {}
    v2_state = ('완료' if extra_done else '양자화 수준 비교 평가가 끝난 뒤 자동으로 수행함(대기)' if not (v2['rep'] or h1) else '진행 중')
    # ── 목표 통과율 판정과 대책 ──
    h2stat = jload('05_eval/holdout2_stats.json') or {}
    j3, r3 = jload('logs/pipeline/EXTRA3_judge.json'), jload('logs/pipeline/EXTRA3_result.json')
    reg = jload('06_build/staged/v3/reg_live.json') or {}
    n_gold = sum(1 for k in reg if k.startswith('G_'))
    pre3 = (f"사전 점검(GPU 미사용): 보완본 분석 함수에서 정답 코드 {n_gold}건의 산출값과 경고가 현행과 같고 안내·경고 시험 30건이 기대와 같음. 보완한 채점기로 기존 실행을 다시 채점하면 값과 인원은 같고 표 구성이 다른 응답이 통과로 바뀜. "
            f"모의 모형(정답 코드) 채점은 벤치마크·안전성 161문항, 보류 검증 문항 1차 {hstat.get('holdout', '—')}문항, 2차 {h2stat.get('holdout2', '—')}문항 모두 통과임. 반영·복구 절차와 실행 절차는 사본 폴더와 축소 모형으로 예행 연습함")
    re_started = any((ROOT / '05_eval' / 'runs' / n).exists() for n in ('holdout2_lora_v2_r2', 'arete27b_lora_v2_r2_base'))     # 보완본 반영 뒤의 재평가(5.15)를 시작했는지
    skipped = (ROOT / 'logs' / 'pipeline' / 'EXTRA3.skip').exists() and bool(j3)
    if skipped:
        bt = next((x for x in j3.get('table', []) if x.get('run') == j3.get('best')), {})
        x3_state = (f"판정(2026-11-17 01:49): 통과율이 가장 높은 구성은 {RUN_LABEL.get(j3.get('best'), j3.get('best'))}"
                    f"({bt.get('n_bench', 121)}문항 중 {bt.get('pass_bench', '—')}문항, {(j3.get('rate') or 0) * 100:.1f}%)로 목표에 이르러 대책을 실행하지 않음. 목표 문항 수(115문항)와 같아 여유 문항은 없음. "
                    + ("판정 시점에는 보완본(분석 함수 0.4.1, 채점기, 프롬프트 개선판 3)과 보류 검증 문항 2차를 반영·평가하지 않고 별도 폴더에 보존하였으며, 이후의 지시에 따라 반영하고 다시 평가함(5.15). " if re_started
                       else "보완본(분석 함수 0.4.1, 채점기, 프롬프트 개선판 3)과 보류 검증 문항 2차는 반영·평가하지 않고 별도 폴더에 보존함. ") + pre3)
    elif r3:
        x3_state = (f"판정: 대책 실행 전의 최고 구성은 {j3.get('best') if j3 else '—'}({((j3 or {}).get('rate') or 0) * 100:.1f}%)로 목표에 미달하여 대책을 실행함. "
                    f"실행 뒤의 최고 구성은 {r3.get('best')}({(r3.get('rate') or 0) * 100:.1f}%)로 목표에 {'이름' if r3.get('decision') == 'skip' else '미달함'}")
    elif j3 and j3.get('decision') == 'run':
        x3_state = f"판정: 통과율이 가장 높은 구성은 {RUN_LABEL.get(j3.get('best'), j3.get('best'))}({(j3.get('rate') or 0) * 100:.1f}%)로 목표에 미달하여 대책을 실행 중임. {pre3}"
    else:
        x3_state = f'미세조정 뒤의 확인 실행이 끝난 뒤 판정함(대기). {pre3}'

    # ── 구성별 비교(모형 파일 × 시스템 프롬프트) ──
    RD = ROOT / '05_eval' / 'runs'
    CONFIGS = [('공식 가중치 Q5_K_M', '현행(긴 판)', 'arete27b_q5_base', 'holdout_q5_v1', None),
               ('공식 가중치 Q5_K_M', '개선판 2', 'arete27b_q5_v2_base', 'holdout_q5_v2', None),
               ('공식 가중치 Q4_K_M', '현행(긴 판)', 'arete27b_q4_base', None, None),
               ('공식 가중치 Q4_K_M', '개선판 2', 'arete27b_q4_v2_base', 'holdout_q4_v2', None),
               ('공식 가중치 Q6_K', '현행(긴 판)', 'arete27b_q6_base', None, None),
               ('미세조정 모형 Q5_K_M', '짧은 판', 'arete27b_lora_short_base', 'holdout_lora_short', None),
               ('미세조정 모형 Q5_K_M', '현행(긴 판)', 'arete27b_lora_long_base', None, None),
               ('미세조정 모형 Q5_K_M', '개선판 2', 'arete27b_lora_v2_base', 'holdout_lora_v2', None)]
    if any((RD / n).exists() for n in ('arete27b_lora_v2_r2_base', 'holdout_lora_v2_r2', 'holdout2_lora_v2_r2')):
        CONFIGS.append(('미세조정 모형 Q5_K_M', '개선판 2(보완본 반영)', 'arete27b_lora_v2_r2_base', 'holdout_lora_v2_r2', 'holdout2_lora_v2_r2'))
    for tg, lab in (('q5', '공식 가중치 Q5_K_M'), ('q4', '공식 가중치 Q4_K_M'), ('lora', '미세조정 모형 Q5_K_M')):
        if any((RD / n).exists() for n in (f'arete27b_{tg}_v3_base', f'holdout_{tg}_v3', f'holdout2_{tg}_v3')):
            CONFIGS.append((lab, '개선판 3(보완본 반영)', f'arete27b_{tg}_v3_base', f'holdout_{tg}_v3', f'holdout2_{tg}_v3'))
    if any((RD / n).exists() for n in ('arete27b_lora_v3_r3_base', 'holdout_lora_v3_r3', 'holdout2_lora_v3_r3')):
        CONFIGS.append(('미세조정 모형 Q5_K_M', '개선판 3(보완본 반영, 하네스 보완)', 'arete27b_lora_v3_r3_base', 'holdout_lora_v3_r3', 'holdout2_lora_v3_r3'))
    if any((RD / n).exists() for n in ('arete27b_lora_short2_base', 'holdout2_lora_short2')):
        CONFIGS.append(('미세조정 모형 Q5_K_M', '짧은 판(보완본 반영)', 'arete27b_lora_short2_base', None, 'holdout2_lora_short2'))
    def cfg_row(model, prompt, bench, ho1, ho2):
        r = load_run(bench)
        if r['rep']:
            rate = r['rep']['metrics'].get('문항 통과율') or 0; nb = r['rep'].get('n_benchmark') or 121
            b = f'<td class="n">{round(rate * nb)}/{nb} ({rate * 100:.1f}%)</td>'
            j = f'<td class="c {"ok" if r["rep"]["passed"] else "ng"}">{"충족" if r["rep"]["passed"] else "미달"}</td>'
        else:
            b, j = f'<td class="c small">{r["state"]}</td>', '<td class="c small">—</td>'
        def hc(n):
            h = load_holdout(n) if n else None
            return f'<td class="n">{h["n_pass"]}/{h["n"]}</td>' if h else '<td class="c small">—</td>'
        return f'<tr><td class="k">{model}</td><td>{prompt}</td>{b}{j}{hc(ho1)}{hc(ho2)}</tr>'
    cfg_rows = ''.join(cfg_row(*c) for c in CONFIGS)
    rescored = (RD / 'arete27b_q5_v2_base' / 'report.scorer_v1.json').exists()
    score_note = ('보완한 채점기로 전 실행을 다시 채점한 값임(원 채점 결과는 실행 폴더의 <code>report.scorer_v1.json</code>에 보존함)' if rescored
                  else ('현행 채점기의 값임. 보완한 채점기는 반영하지 않음. 판정 시 보완한 채점기로 다시 계산한 벤치마크 통과 문항 수는 '
                        + ', '.join(f"{RUN_LABEL.get(x['run'], x['run'])} {x.get('pass_bench')}" for x in j3.get('table', [])) + '임') if skipped
                  else '현행 채점기의 값임. 보완한 채점기는 대책 실행 단계에서 반영하며, 반영 시 전 실행을 다시 채점함')

    # ── 보완본 반영과 재평가(2026-11-17) ──
    PL = ROOT / 'logs' / 'pipeline'
    re_done = (PL / 'REEVAL_ALL.end').exists()
    RE = [('arete27b_lora_v2_base', 'holdout_lora_v2', None, '개선판 2', '0.3.1<br>(반영 전)'),
          ('arete27b_lora_v2_r2_base', 'holdout_lora_v2_r2', 'holdout2_lora_v2_r2', '개선판 2', '0.4.1'),
          ('arete27b_lora_v3_base', 'holdout_lora_v3', 'holdout2_lora_v3', '개선판 3', '0.4.1')]
    re_runs = [load_run(b) for b, *_ in RE]
    re_h1 = [load_holdout(h) if h else None for _, h, *_ in RE]
    re_h2 = [load_holdout(h) if h else None for _, _, h, *_ in RE]
    re_head = ''.join(f'<th class="w">{sp}<br><span class="small">분석 함수 {lv}</span></th>' for *_, sp, lv in RE)
    def re_pass(r):
        return round((r['rep']['metrics'].get('문항 통과율') or 0) * (r['rep'].get('n_benchmark') or 121)) if r['rep'] else None
    re_rows = ('<tr><td class="k">벤치마크 통과 문항(121문항)</td><td class="c">—</td>' + ''.join(f'<td class="n">{re_pass(r)}</td>' if r['rep'] else f'<td class="c small">{r["state"]}</td>' for r in re_runs) + '</tr>'
               + ''.join(f'<tr><td class="k">{k}</td><td class="c">{crit_txt(k)}</td>' + ''.join(v2cell(r, k) for r in re_runs) + '</tr>' for k in V2M)
               + '<tr><td class="k">종합 판정</td><td class="c">전 지표 충족</td>' + ''.join(
                   f'<td class="c {"ok" if r["rep"] and r["rep"]["passed"] else "ng" if r["rep"] else "small"}">{("충족" if r["rep"]["passed"] else "미달") if r["rep"] else "—"}</td>' for r in re_runs) + '</tr>'
               + f'<tr><td class="k">보류 검증 문항 1차({hstat.get("holdout", "—")}문항)</td><td class="c">—</td>' + ''.join(f'<td class="n">{h["n_pass"]}</td>' if h else '<td class="c small">—</td>' for h in re_h1) + '</tr>'
               + f'<tr><td class="k">보류 검증 문항 2차({h2stat.get("holdout2", "—")}문항)</td><td class="c">—</td>' + ''.join(f'<td class="n">{h["n_pass"]}</td>' if h else '<td class="c small">—</td>' for h in re_h2) + '</tr>'
               + '<tr><td class="k">세 문항 묶음 합산(213문항)</td><td class="c">—</td>' + ''.join(
                   (f'<td class="n"><b>{re_pass(r) + a["n_pass"] + b["n_pass"]}</b></td>' if r['rep'] and a and b else '<td class="c small">—</td>') for r, a, b in zip(re_runs, re_h1, re_h2)) + '</tr>'
               + '<tr><td class="k">벤치마크 평가 소요</td><td class="c">—</td>' + ''.join(usage_cell_r(r) for r in re_runs) + '</tr>')
    def ho_fail(h):
        return ', '.join(f'{k} {v}' for k, v in (h.get('fail_by_cause') or {}).items()) or '없음'
    re_ho_rows = ''.join(
        f'<tr><td class="k">{lab}</td>' + ''.join((f'<td class="n">{f(h)}</td>' if h else '<td class="c small">—</td>') for h in re_h2[1:]) + '</tr>'
        for lab, f in [(f'전체 통과({h2stat.get("holdout2", "—")}문항)', lambda h: f"{h['n_pass']}/{h['n']} ({h['pass_rate'] * 100:.1f}%)"), ('산출해야 하는 문항 통과', lambda h: h['산출 문항 통과']),
                       ('산출해야 하는 문항에서 확인을 요청한 수', lambda h: h['산출 문항에서 되물은 수']), ('확인을 요청해야 하는 질문 통과', lambda h: h['되물어야 하는 질문 통과']),
                       ('응하지 않아야 하는 요청 통과', lambda h: h['응하지 않는 요청 통과']), ('미통과 원인', ho_fail)])
    # 서버의 프롬프트 캐시 설정 확인(기본값과 0의 비교)
    plog_txt = (PL / 'pipeline.log').read_text(encoding='utf-8') if (PL / 'pipeline.log').exists() else ''
    def ram_at(pat):
        m = re.findall(r'재평가: ' + pat + r'[^\n]*?서버 RAM ([\d.]+)GiB', plog_txt)
        return m[-1] if m else None
    ck_a, ck_b = load_holdout('holdout_lora_v2_r2'), load_holdout('holdout_lora_v2_r2_cram0')
    cache = None
    if ck_a and ck_b:
        ta = {json.loads(l)['id']: json.loads(l)['turns'] for l in (RD / 'holdout_lora_v2_r2' / 'transcripts.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()}
        tb = {json.loads(l)['id']: json.loads(l)['turns'] for l in (RD / 'holdout_lora_v2_r2_cram0' / 'transcripts.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()}
        key = lambda turns: [(t['final'], [s['code'] for s in t['steps']]) for t in turns]
        ma, mb = jload('05_eval/runs/holdout_lora_v2_r2/run_meta.json') or {}, jload('05_eval/runs/holdout_lora_v2_r2_cram0/run_meta.json') or {}
        cache = {'n': len(ta), 'diff': sum(1 for i in ta if i in tb and key(ta[i]) != key(tb[i])), 'pa': ck_a['n_pass'], 'pb': ck_b['n_pass'], 'ea': ma.get('elapsed_sec') or 0, 'eb': mb.get('elapsed_sec') or 0,
                 'ram_first': ram_at('holdout2_lora_v2_r2: 끝'), 'ram_last': ram_at('arete27b_lora_v3_base: 끝'), 'ram_off': ram_at('holdout_lora_v2_r2_cram0: 끝')}
    re_note = findings.get('재평가') or {}
    rs_log = (PL / 'reeval_rescore.log').read_text(encoding='utf-8').splitlines() if (PL / 'reeval_rescore.log').exists() else []
    rs_changed = sum(1 for l in rs_log if not l.rstrip().endswith('[]'))
    re_pre = (f"반영 점검: 정답 코드 {n_gold}건의 실행·산출값·경고가 반영 전과 같고 안내·경고 시험이 기대와 같으며, 모의 모형(정답 코드) 채점은 벤치마크·안전성 161문항과 보류 검증 문항 1·2차 전 문항 통과임. "
              + (f"재채점: 기존 평가 실행 {len(rs_log)}회 가운데 {rs_changed}회에서 통과 문항이 1문항씩 늘었고 종합 판정이 바뀐 실행은 없음. " if rs_log else ''))
    re_state = (re_pre + '재평가 결과는 6.8에 제시함. ' + E(re_note.get('결론', ''))) if re_done else (re_pre + '재평가 진행 중') if re_started else '대기'
    re_list = ''.join(f'<li>{E(x)}</li>' for x in re_note.get('결과', [])) or '<li>재평가가 끝난 뒤 기재함</li>'
    if cache:
        re_list += (f"<li>서버의 프롬프트 캐시 설정 확인: 캐시 상한을 0으로 둔 서버에서 같은 구성(개선판 2)으로 보류 검증 문항 1차 {cache['n']}문항을 다시 수행함. 응답 또는 코드가 기본 설정(상한 8GiB)의 실행과 다른 문항은 {cache['diff']}개이고 "
                    f"통과 문항은 {cache['pb']}개(기본 설정 {cache['pa']}개)임. 소요는 {cache['eb'] / 60:.1f}분(기본 설정 {cache['ea'] / 60:.1f}분)임. "
                    + (f"서버의 RAM 사용은 기본 설정에서 첫 평가 49문항 뒤 {cache['ram_first']}GiB, 재평가의 마지막 평가 뒤 {cache['ram_last']}GiB이고, 캐시를 끈 서버에서는 43문항 뒤 {cache['ram_off']}GiB임. " if cache['ram_first'] and cache['ram_last'] and cache['ram_off'] else '')
                    + E(re_note.get('캐시', '')) + '</li>')
    re_sum = f"<li>{E(re_note['요약'])}</li>" if re_note.get('요약') else ''

    # ── 하네스 보완 뒤의 재평가(2026-11-17) ──
    hk_started = any((RD / n).exists() for n in ('holdout3_lora_v3', 'holdout3_lora_v3_r3', 'arete27b_lora_v3_r3_base'))
    hk_done = (PL / 'HOOKS_ALL.end').exists()
    h3stat = jload('05_eval/holdout3_stats.json') or {}
    HK = [('arete27b_lora_v3_base', 'holdout_lora_v3', 'holdout2_lora_v3', 'holdout3_lora_v3', '보완 전'),
          ('arete27b_lora_v3_r3_base', 'holdout_lora_v3_r3', 'holdout2_lora_v3_r3', 'holdout3_lora_v3_r3', '보완 후')]
    hk_runs = [load_run(b) for b, *_ in HK]
    hk_h = [[load_holdout(x) for x in (a, b, c)] for _, a, b, c, _ in HK]
    hk_head = ''.join(f'<th class="w">{lab}</th>' for *_, lab in HK)
    def hk_hrow(label, j):
        return f'<tr><td class="k">{label}</td><td class="c">—</td>' + ''.join(f'<td class="n">{hs[j]["n_pass"]}</td>' if hs[j] else '<td class="c small">—</td>' for hs in hk_h) + '</tr>'
    hk_rows = ('<tr><td class="k">벤치마크 통과 문항(121문항)</td><td class="c">—</td>' + ''.join(f'<td class="n">{re_pass(r)}</td>' if r['rep'] else f'<td class="c small">{r["state"]}</td>' for r in hk_runs) + '</tr>'
               + ''.join(f'<tr><td class="k">{k}</td><td class="c">{crit_txt(k)}</td>' + ''.join(v2cell(r, k) for r in hk_runs) + '</tr>' for k in V2M)
               + '<tr><td class="k">종합 판정</td><td class="c">전 지표 충족</td>' + ''.join(
                   f'<td class="c {"ok" if r["rep"] and r["rep"]["passed"] else "ng" if r["rep"] else "small"}">{("충족" if r["rep"]["passed"] else "미달") if r["rep"] else "—"}</td>' for r in hk_runs) + '</tr>'
               + hk_hrow(f'보류 검증 문항 1차({hstat.get("holdout", "—")}문항)', 0) + hk_hrow(f'보류 검증 문항 2차({h2stat.get("holdout2", "—")}문항)', 1)
               + '<tr><td class="k">세 문항 묶음 합산(213문항)</td><td class="c">—</td>' + ''.join(
                   (f'<td class="n"><b>{re_pass(r) + hs[0]["n_pass"] + hs[1]["n_pass"]}</b></td>' if r['rep'] and hs[0] and hs[1] else '<td class="c small">—</td>') for r, hs in zip(hk_runs, hk_h)) + '</tr>'
               + hk_hrow(f'보류 검증 문항 3차({h3stat.get("holdout3", "—")}문항, 새 문항)', 2)
               + '<tr><td class="k">벤치마크 평가 소요</td><td class="c">—</td>' + ''.join(usage_cell_r(r) for r in hk_runs) + '</tr>')
    def kind3(b):                                         # 3차 문항의 유형(05_eval/build_holdout3.py 의 구성)
        ex, g = b['expect'], b.get('gold_code') or ''
        if ex.get('behavior') == 'refuse':
            return '코드를 제시한 요청 가운데 응하지 않아야 하는 요청'
        if ex.get('defect') == '분모 누락':
            return '코드 확인: 분모 누락'
        if ex.get('defect') == '없음(맞는 코드)':
            return '코드 확인: 제시한 코드가 맞는 경우'
        if ex.get('defect'):
            return '코드 확인: 그 밖의 결함'
        if 'h_prop' in g or b['category'].startswith('S'):
            return '참고 자료에 없는 변수를 찾아야 하는 문항'
        return '구간을 직접 정의하는 문항' if 'define_group' in g else '대조용 문항'
    K3 = ['코드 확인: 분모 누락', '코드 확인: 그 밖의 결함', '코드 확인: 제시한 코드가 맞는 경우', '구간을 직접 정의하는 문항', '참고 자료에 없는 변수를 찾아야 하는 문항', '대조용 문항', '코드를 제시한 요청 가운데 응하지 않아야 하는 요청']
    items3 = [json.loads(l) for l in (ROOT / '05_eval' / 'holdout3.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()] if (ROOT / '05_eval' / 'holdout3.jsonl').exists() else []
    k3 = {b['id']: kind3(b) for b in items3}
    def k3cell(h, kind):
        return f'<td class="n">{sum(1 for r in h["rows"] if k3.get(r["id"]) == kind and r["passed"])}</td>' if h else '<td class="c small">—</td>'
    hk_k3_rows = ''.join(f'<tr><td class="k">{kind}</td><td class="n">{sum(1 for v in k3.values() if v == kind)}</td>' + ''.join(k3cell(hs[2], kind) for hs in hk_h) + '</tr>' for kind in K3) \
        + (f'<tr><td class="k">계</td><td class="n">{len(k3)}</td>' + ''.join(f'<td class="n"><b>{hs[2]["n_pass"]}</b></td>' if hs[2] else '<td class="c small">—</td>' for hs in hk_h) + '</tr>')
    hk_fired = {}
    for hs in hk_h[1]:
        for k, v in ((hs or {}).get('hooks') or {}).items():
            hk_fired[k] = hk_fired.get(k, 0) + v
    for k in ('제시 코드를 하네스가 먼저 실행한 질문', '같은 코드의 재제출을 돌려보낸 횟수', '변수 후보를 덧붙인 횟수'):
        if hk_runs[1]['rep']:
            hk_fired[k] = hk_fired.get(k, 0) + (hk_runs[1]['rep'].get('harness') or {}).get(k, 0)
    hk_note = findings.get('하네스') or {}
    hk_list = ''.join(f'<li>{E(x)}</li>' for x in hk_note.get('결과', [])) or '<li>재평가가 끝난 뒤 기재함</li>'
    hk_sum = f"<li>{E(hk_note['요약'])}</li>" if hk_note.get('요약') else ''
    hk_state = (E(hk_note.get('결론', '')) + ' 결과는 6.9에 제시함.') if hk_done else '재평가 진행 중' if hk_started else '대기'

    v2_sum = ''
    if v2['rep']:
        vm, vbad = v2['rep']['metrics'], [k for k, v in v2['rep']['judge'].items() if v is False]
        v2_sum = (f"<li>개선판 프롬프트(양자화 수준과 서버 설정은 기본 구성과 같음)의 평가 결과는 문항 통과율 {vm.get('문항 통과율')}, 실행 성공률 {vm.get('실행 성공률')}, 산출값 일치율 {vm.get('산출값 일치율')}, 거절 정확도 {vm.get('거절 정확도')}, 차단 실패 {vm.get('차단 실패 건수')}건이며, "
                  + (f"기준(안)에 미달한 지표는 {', '.join(vbad)}임" if vbad else '기준(안)의 전 지표를 충족함')
                  + (f". 개선판 작성에 참고하지 않은 보류 검증 문항의 통과는 {h1['n']}문항 중 {h1['n_pass']}문항에서 {h2['n_pass']}문항으로 늘어남" if h1 and h2 else '') + '.</li>')
    ft_sum = ''
    ls_, ll_ = runs['arete27b_lora_short_base'], runs['arete27b_lora_long_base']
    if ls_['rep'] and ll_['rep']:
        sm, lm = ls_['rep']['metrics'], ll_['rep']['metrics']; sbad = [k for k, v in ls_['rep']['judge'].items() if v is False]
        ft_sum = (f"<li>미세조정 모형(Q5_K_M)의 문항 통과율은 짧은 판 프롬프트(학습 자료와 같은 문구)에서 {sm.get('문항 통과율')}, 긴 판(현행) 프롬프트에서 {lm.get('문항 통과율')}임. "
                  f"짧은 판 구성은 실행 성공률 {sm.get('실행 성공률')}, 산출값 일치율 {sm.get('산출값 일치율')}, 차단 실패 {sm.get('차단 실패 건수')}건이며, "
                  + (f"기준(안)에 미달한 지표는 {', '.join(sbad)}임" if sbad else '기준(안)의 전 지표를 충족함')
                  + '. 구성별 비교는 6.7, 목표 통과율(95%) 판정과 대책은 5.14에 제시함.</li>')
        lv_ = runs['arete27b_lora_v2_base']; hv_ = load_holdout('holdout_lora_v2')
        if lv_['rep']:
            vm_ = lv_['rep']['metrics']; vb_ = [k for k, v in lv_['rep']['judge'].items() if v is False]; nb_ = lv_['rep'].get('n_benchmark') or 121
            ft_sum += (f"<li>미세조정 모형에 개선판 2 프롬프트를 쓴 구성의 문항 통과율은 {vm_.get('문항 통과율')}({nb_}문항 중 {round((vm_.get('문항 통과율') or 0) * nb_)}문항)로 목표 통과율(95%)에 이름. "
                       f"실행 성공률 {vm_.get('실행 성공률')}, 산출값 일치율 {vm_.get('산출값 일치율')}, 거절 정확도 {vm_.get('거절 정확도')}, 차단 실패 {vm_.get('차단 실패 건수')}건이며, "
                       + (f"기준(안)에 미달한 지표는 {', '.join(vb_)}임" if vb_ else '기준(안)의 전 지표를 충족함')
                       + (f". 보류 검증 문항 1차의 통과는 {hv_['n']}문항 중 {hv_['n_pass']}문항임" if hv_ else '')
                       + ('. 판정 시점에 개발 설정의 기본 구성을 이 구성으로 변경함(재평가 뒤의 기본 구성은 아래 항목).</li>' if re_done else '. 개발 설정의 기본 구성을 이 구성으로 변경함.</li>'))
    fd_res = ''.join(f'<li>{E(x)}</li>' for x in findings.get('해석', [])) or '<li>전체 평가와 미세조정이 끝난 뒤 기재함</li>'
    fd_imp = ''.join(f'<tr><td class="c">{i}</td><td>{E(x.get("항목", ""))}</td><td>{E(x.get("근거", ""))}</td><td>{E(x.get("조치", ""))}</td></tr>' for i, x in enumerate(findings.get('개선', []), 1)) \
        or '<tr><td class="c small" colspan="4">전체 평가와 미세조정이 끝난 뒤 기재함</td></tr>'

    H = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>폐쇄망 분석 지원 로컬 언어모형 구축 절차 설명자료</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">

<h1>폐쇄망 분석 지원 로컬 언어모형 구축 절차 설명자료</h1>
<div class="meta">작성 {time.strftime('%Y-%m-%d')} · 대상 기간 2026-11-11~{time.strftime('%Y-%m-%d')} · 상태: {status} · 준비 폴더 <code>/mnt/share/행정데이터_set/로컬LLM_준비</code> · 개발용 분석 자료: 가상데이터 확대 생성본(94,430명) · 설비: RTX 5060 Ti 16GB 2장, RAM 30GB · 지정 모형: NousResearch/Arete-27B</div>

<div class="box">
<p><b>요약</b></p>
<ul>
<li>이 자료는 폐쇄망 분석환경에서 자연어 질문을 분석·시각화 코드로 옮겨 주는 로컬 언어모형을 구축한 과정을 착수 시점부터 기록한 것임. 같은 유형의 모형을 구축할 때 절차서로 활용하는 것을 목적으로 하며, 단계마다 수행 내용, 그 절차를 둔 이유, 확인 방법, 결과를 제시함.</li>
<li>구축은 요구 정리, 분석 함수 묶음과 출력 통제, 지식 자료, 프롬프트·학습 자료·평가 자료, 하네스, 모형 반입, 추론 서버 준비, GPU 구동, 평가, 미세조정의 순서로 진행함. 모형을 GPU에 적재하기 전에 수행할 수 있는 작업을 모두 마친 뒤 GPU를 사용함.</li>
<li>모형은 분석 자료를 읽지 않는 구조로 설계함. 모형은 집계 전용 함수를 부르는 코드만 작성하고, 코드는 실행 전 점검을 거쳐 별도 프로세스에서 실행되며, 출력 통제는 함수 안에서 적용됨. 분모 점검, 수치 대조 등의 확인 절차는 하네스가 수행함.</li>
<li>지정 모형(약 270억 매개변수, 54.7GB)을 공식 저장소에서 내려받아 점검하고, 4~6비트 양자화본 3종을 직접 제작함. GPU 2장에 적재한 결과 {f"적재 {first['load']}초, GPU 메모리 {' · '.join(f'{m / 1024:.1f}GiB' for m in first['mem'])}, 생성 속도 초당 {first['gen']:.1f}토큰, 입력 처리 속도 초당 {first['pp']:,.0f}토큰" if first and first['gen'] else '(측정 중)'}으로 측정됨.</li>
<li>{res_summary()}.</li>
<li>{(f"기본 구성에서 통과하지 못한 {b_ana['n_fail']}문항 가운데 {top_cause[1]}문항의 원인은 「{top_cause[0]}」임. 모형이 산출해야 할 질문에 확인을 요청한 경우로, 확인을 요청하는 범위를 한정한 개선판 프롬프트를 작성하여 효과를 확인함(5.13, 6.5, 6.6)" if top_cause else "통과하지 못한 문항의 원인 분석은 평가가 끝난 뒤 기재함")}.</li>
{v2_sum}
{ft_sum}
{re_sum}
{hk_sum}
<li>진행 중 {len(PROBLEMS)}건의 문제가 발생함. 그중 3건은 GPU에서 처음 구동할 때 발생한 것으로, 모형 적재 중 운영체제의 메모리 압력 감시에 의해 작업이 종료된 사례와 미세조정 스모크 시험이 GPU 메모리 부족으로 실패한 사례를 포함함. 원인과 조치는 7절에 정리함.</li>
</ul>
</div>

<h2>차례</h2>
<ol class="toc">
<li>자료의 목적과 구성</li><li>배경과 설계 원칙</li><li>용어 설명</li><li>전체 절차</li><li>단계별 수행 내용과 이유</li><li>평가 결과</li><li>진행 중 발생한 문제와 조치</li><li>구축 절차 점검표</li><li>남은 과제와 개선 사항</li><li>부록: 파일 위치와 재실행 방법</li>
</ol>

<h2>1. 자료의 목적과 구성</h2>
<ul>
<li>목적: 로컬 언어모형의 구축 과정을 절차 단위로 기록하여, 이후 같은 유형의 모형을 구축할 때 참고할 수 있는 보고자료로 삼음</li>
<li>독자: 언어모형의 구축을 처음 접하는 연구자와 실무자. 3절에 용어 설명을 두고, 본문에서 처음 나오는 용어는 그 뜻을 함께 적음</li>
<li>구성: 2절은 과제의 배경과 설계 원칙, 4절은 전체 절차의 개관, 5절은 단계별 수행 내용과 그 절차를 둔 이유, 6절은 평가 결과, 7절은 진행 중 발생한 문제와 조치, 8절은 절차 점검표임</li>
<li>수치의 출처: 평가 지표, 속도, 메모리, 소요 시간은 실행 기록에서 읽어 기재함. 측정하지 않은 값은 추정으로 표기함</li>
<li>한계: 개발과 평가는 가상데이터로 수행함. 실제 분석 자료에서의 성능은 폐쇄망 안에서 같은 절차로 다시 평가해야 함</li>
</ul>

<h2>2. 배경과 설계 원칙</h2>
<h3>2.1 과제의 배경</h3>
<ul>
<li>사회보장행정데이터는 개인 단위의 민감한 자료이므로 외부 통신망과 분리된 폐쇄망 분석환경에서만 다룸. 폐쇄망에서는 외부의 언어모형 서비스를 이용할 수 없음</li>
<li>분석 이용자는 변수 595개의 정의, 결측 규약, 출력 통제 규칙을 숙지해야 분석 코드를 작성할 수 있음. 자연어 질문을 분석 코드로 옮겨 주는 지원 도구가 있으면 이 부담이 줄어듦</li>
<li>이에 폐쇄망 안의 설비에서 구동하는 로컬 언어모형으로 분석 지원 도구를 구성하는 방안을 검토함. 이 과제는 가상데이터를 폐쇄망의 실제 자료로 간주하는 시나리오를 전제로 함(2026-11-11 설정)</li>
<li>2026-11-13에 구축에 필요한 자료와 도구를 사전에 준비하는 작업에 착수하였고, 같은 날 모형이 지정됨. 2026-11-15에 GPU 사용이 가능해져 구동, 평가, 미세조정을 수행함</li>
</ul>
<h3>2.2 목표와 범위</h3>
<ul>
<li>목표: 이용자의 자연어 질문을 분석 계획과 파이썬 코드로 옮기고, 실행 결과를 확인하여 「결과」와 「유의 사항」으로 설명하는 분석 지원 도구의 구축</li>
<li>모형이 수행하는 일: 변수 안내, 비율·평균·분위수 등의 집계, 집단별 비교, 그림 작성, 제도 용어의 풀이, 모호한 질문에 대한 확인, 응할 수 없는 요청의 거절</li>
<li>범위 밖: 개인 단위 자료의 조회, 통계 모형의 추정, 여러 자료를 넘나드는 조사</li>
</ul>
<h3>2.3 설계 원칙</h3>
<table>
<tr><th>원칙</th><th>내용</th><th>이유</th></tr>
{pr}
</table>
<h3>2.4 개발 환경</h3>
<table>
<tr><th>구분</th><th>내용</th></tr>
<tr><td class="k">분석 자료</td><td>가상데이터 확대 생성본(94,430명, 42,000가구, 변수 595개). 폐쇄망에서는 실제 분석 자료로 바꿈</td></tr>
<tr><td class="k">설비</td><td>CPU 6코어, RAM 30GB, GPU RTX 5060 Ti 16GB 2장, 저장 장치 HDD(모형 파일)와 SSD</td></tr>
<tr><td class="k">지정 모형</td><td>NousResearch/Arete-27B(Qwen3.8-27B 기반, Apache-2.0, 2026-11-06 공개). 층 64개 가운데 16개가 일반 주의 층, 48개가 선형 주의 층인 구조</td></tr>
<tr><td class="k">소프트웨어</td><td>llama.cpp(2026-05-21 판, 추론 서버·양자화), transformers·peft(미세조정), 분석 함수 묶음과 하네스는 자체 작성</td></tr>
</table>

<h2>3. 용어 설명</h2>
<p class="small">처음 접하는 독자를 위한 설명임. 셋째 열은 이 과제에서 그 용어가 가리키는 대상을 적은 것임.</p>
<table>
<tr><th>용어</th><th>뜻</th><th>이 과제에서의 쓰임</th></tr>
{gl}
</table>

<h2>4. 전체 절차</h2>
<table>
<tr><th class="c">단계</th><th>수행 내용</th><th>주요 산출물</th><th class="c">시기</th><th class="c">GPU</th><th class="c">상태</th></tr>
<tr><td class="c">1</td><td>요구 정리와 설계 원칙 결정</td><td>준비 폴더 구성, 결정 필요 사항 목록</td><td class="c">11-11~13</td><td class="c">불필요</td><td class="c">{tag('완료')}</td></tr>
<tr><td class="c">2</td><td>분석 함수 묶음과 출력 통제</td><td>집계 전용 함수, 실행 전 점검, 격리 실행기</td><td class="c">11-13</td><td class="c">불필요</td><td class="c">{tag('완료')}</td></tr>
<tr><td class="c">3</td><td>지식 자료와 제도 용어 사전</td><td>변수 사전·카드, 검색 색인, 용어 사전</td><td class="c">11-13</td><td class="c">불필요</td><td class="c">{tag('완료')}</td></tr>
<tr><td class="c">4</td><td>프롬프트, 학습 자료, 평가 자료</td><td>시스템 프롬프트 2종, 대화 예시 {n_tr + n_va + n_te:,}건, 벤치마크 {bst.get('benchmark')}문항·안전성 시험 {bst.get('safety')}문항</td><td class="c">11-13</td><td class="c">불필요</td><td class="c">{tag('완료')}</td></tr>
<tr><td class="c">5</td><td>하네스(조립기·검증 단계)와 모의 점검</td><td>조립기, 채점기, 자체 시험 결과</td><td class="c">11-13</td><td class="c">불필요</td><td class="c">{tag('완료')}</td></tr>
<tr><td class="c">6</td><td>모형 반입과 점검</td><td>공식 가중치, 반입 기록(출처·판·해시)</td><td class="c">11-13~14</td><td class="c">불필요</td><td class="c">{tag('완료')}</td></tr>
<tr><td class="c">7</td><td>추론 서버 준비</td><td>양자화본 3종, 서버 실행 파일, 축소 모형 시험, CPU 시범 구동 기록</td><td class="c">11-15</td><td class="c">불필요</td><td class="c">{tag('완료')}</td></tr>
<tr><td class="c">8</td><td>GPU 구동: 서버 기동과 연결 확인</td><td>적재 시간·메모리·속도 실측, 연결 확인 기록</td><td class="c">11-15~16</td><td class="c">필요</td><td class="c">{tag('완료' if first else '진행 중')}</td></tr>
<tr><td class="c">9</td><td>평가: 기본 구성, 유사 예시 삽입, 양자화 수준 비교</td><td>실행별 평가 보고서</td><td class="c">11-16</td><td class="c">필요</td><td class="c">{tag('완료' if all(st[k] == '완료' for k in ('S1_q5', 'S2_q4', 'S3_q6')) else '진행 중' if first else '대기')}</td></tr>
<tr><td class="c">10</td><td>미세조정: 스모크 시험, 학습, 병합, 변환, 재평가</td><td>어댑터, 미세조정 모형의 양자화본, 평가 보고서</td><td class="c">11-16~</td><td class="c">필요</td><td class="c">{tag('완료' if done_all else '진행 중' if st['F1_smoke'] != '대기' else '대기')}</td></tr>
<tr><td class="c">11</td><td>미통과 원인 분석과 프롬프트 개선판 확인</td><td>원인 분석 보고, 개선판 프롬프트, 보류 검증 문항, 확인 실행 결과</td><td class="c">11-16~</td><td class="c">필요</td><td class="c">{tag('완료' if extra_done else '진행 중' if ana_runs else '대기')}</td></tr>
<tr><td class="c">12</td><td>목표 통과율(95%) 판정과 대책: 분석 함수·채점 보완, 프롬프트 개선판 3, 보류 검증 문항 2차</td><td>판정 기록, 보완본, 대책 실행 뒤의 평가 보고</td><td class="c">11-16~</td><td class="c">필요</td><td class="c">{tag('완료' if r3 or (ROOT / 'logs' / 'pipeline' / 'EXTRA3.skip').exists() else '진행 중' if j3 else '대기')}</td></tr>
<tr><td class="c">13</td><td>보완본 반영과 재평가: 분석 함수 0.4.1·보완한 채점기 반영, 미세조정 모형의 개선판 2·개선판 3 평가, 보류 검증 문항 2차</td><td>반영·재채점 기록, 재평가 보고, 판정 기록</td><td class="c">11-17</td><td class="c">필요</td><td class="c">{tag('완료' if re_done else '진행 중' if re_started else '대기')}</td></tr>
<tr><td class="c">14</td><td>하네스 보완과 재평가: 제시 코드 실행·같은 코드 재제출 차단·변수 후보 회신, 보류 검증 문항 3차</td><td>보완 동작 시험, 재평가 보고</td><td class="c">11-17</td><td class="c">필요</td><td class="c">{tag('완료' if hk_done else '진행 중' if hk_started else '대기')}</td></tr>
<tr><td class="c">15</td><td>시범 운영 설정, 실제 자료로의 전환</td><td>운영 설정, 폐쇄망 반입</td><td class="c">이후</td><td class="c">필요</td><td class="c">{tag('대기')}</td></tr>
</table>
<ul>
<li>1~7단계는 GPU 없이 수행함. 이 기간에 GPU는 다른 작업이 사용하고 있었음</li>
<li>각 단계의 산출물은 다음 단계의 입력이 됨. 예를 들어 분석 함수 묶음(2단계)이 있어야 학습 자료의 코드(4단계)를 실행해 검증할 수 있고, 평가 자료(4단계)가 있어야 하네스(5단계)를 모의 모형으로 점검할 수 있음</li>
<li>준비 상태는 점검 스크립트 한 개로 확인함. 현재 점검표는 준비됨 {(now.get('요약') or {}).get('준비됨', '—')}개 항목임</li>
</ul>

<h2>5. 단계별 수행 내용과 이유</h2>
''' + stage('5.1 요구 정리와 설계 원칙 결정', [
        ['사용 시나리오를 확정함: 가상데이터를 폐쇄망의 실제 자료로 간주하고, 모형의 역할을 자연어 질문을 분석 코드로 옮기고 실행 결과를 설명하는 일로 한정함',
         '준비 폴더를 분석 함수 묶음, 지식 자료, 프롬프트, 학습 자료, 평가 자료, 구축 도구의 6개 영역으로 구성함',
         '작업자가 정할 수 없는 사항(양자화 수준, 미세조정 여부, GPU 사용 시간대, 반입 절차, 평가 기준 등 11개)을 별도 문서로 분리함'],
        ['폐쇄망에서는 구축 도중에 외부 자료를 내려받을 수 없으므로 필요한 자료와 도구를 사전에 모두 갖추어야 함',
         '모형의 역할을 좁게 정해야 통제 설계와 평가 기준의 설정이 가능함',
         '결정권자가 정할 사항을 분리해 두면 그 결정을 기다리는 동안 나머지 준비를 진행할 수 있음'],
        '준비 상태 점검표(<code>06_build/preflight.py</code>)로 영역별 준비 여부를 확인함',
        '준비 폴더와 구축 지시서, 결정 필요 사항 문서를 작성함. 결정되지 않은 사항에는 기본값을 두어 평가 단계까지 진행할 수 있게 함']) + stage('5.2 분석 함수 묶음과 출력 통제', [
        ['집계 전용 함수 7종(비율, 평균, 합계, 분위수, 인원, 구성비, 빈곤율)과 변수 찾기, 파생 변수, 구간 정의, 그림 5종을 작성함',
         '출력 통제를 함수 안에 포함함: 민감도 등급별 최소 관측 수(10·20·30건), 보충 억제, 분류 기준 수 제한(3·3·2개), 분위수 범위 제한',
         '모형이 쓴 코드는 실행 전 점검(파일 접근, 자료의 직접 읽기, 금지된 이름 등)을 통과한 것만 별도 프로세스에서 시간·메모리 한도를 적용하여 실행함'],
        ['모형이 작성한 코드가 개인 단위 자료를 출력하거나 통제를 우회하는 일을 구조적으로 막기 위함. 지침으로 금지하는 것만으로는 준수를 보장할 수 없음',
         '함수의 종류를 적게 두면 모형이 사용법을 익히기 쉽고 평가 문항의 정답을 기계적으로 대조할 수 있음',
         '격리 실행은 잘못된 코드가 조립기나 다른 질의에 영향을 주지 않게 함'],
        '통제 위반 시험 코드가 실행 전에 차단되는지, 억제 대상 칸이 표시되지 않는지를 점검표와 안전성 시험으로 확인함',
        '자료 파일을 직접 읽는 코드를 쓰는 모의 모형의 코드는 모두 실행 전에 차단됨. 이후 실제 모형의 관찰을 반영해 인자 오류의 사용법 안내와 구간 이름 점검을 추가함(5.7)']) + stage('5.3 지식 자료와 제도 용어 사전', [
        [f"변수 사전과 변수 카드, 사업 카드, 규칙 카드, 문서 카드를 만들고 검색 색인을 구축함({E(note(now, '변수 사전·카드'))}, 색인 {E(note(now, '검색 색인'))})",
         '질문이 들어오면 관련 카드를 선별하여 프롬프트에 추가함(변수 카드 5개, 문서 카드 2개, 규칙 카드 1개, 제도 설명 카드 2개 이내)',
         f"제도명·약어·통칭을 풀이하는 제도 용어 사전을 만듦({E(note(now, '제도 용어 사전'))})"],
        ['모형은 이 자료의 변수명, 코드값, 결측 규약을 학습한 적이 없음. 질문마다 관련 정의를 제시해야 변수명을 추측하여 작성하는 일을 줄일 수 있음',
         '사전 전체를 매번 포함하면 문맥 길이를 넘고 처리 시간이 늘어나므로 검색으로 일부만 고름',
         '「국기초」 같은 약어나 「본인부담금」처럼 여러 내역을 묶는 말은 해석에 따라 산출값이 달라짐. 내역이 정해지지 않은 경우에는 임의로 해석하지 않고 이용자에게 확인을 요청하도록 함'],
        '변수 근거율(정의를 확인한 변수만 썼는지), 제도 용어 문항 14개의 통과율로 확인함',
        '약어와 통칭은 KIHASA 통합 코퍼스에서 사용 빈도를 확인해 수록함. 내역이 없는 「국기초 수급률」 질문에는 확인을 요청하고, 「국기초 생계급여 수급률」 질문은 바로 산출함(연결 확인 질문 3·4)']) + stage('5.4 프롬프트(지침)', [
        ['시스템 프롬프트 긴 판을 작성함: 역할, 작업 순서, 제도 용어, 코드 작성 규칙, 함수 사용법, 검증 결과 읽는 법, 출력 통제, 응답 형식, 자료와 지시의 구분',
         '미세조정한 모형에 쓰는 짧은 판, 질문과 실행 결과를 조립하는 틀, 모형이 할 수 있는 동작(코드 블록 1개 작성)의 규약을 정함',
         '응답 형식을 고정함: 코드가 필요하면 「분석 계획」과 코드, 실행 결과를 받으면 「결과」와 「유의 사항」, 질문이 모호하면 「확인 필요」, 응할 수 없으면 「요청 처리 불가」와 「가능한 대안」'],
        ['응답 형식이 일정해야 하네스가 코드를 추출하고 문단을 인식하며 채점기가 자동으로 채점할 수 있음',
         '「유의 사항」은 이용자가 산출 조건과 한계(분모, 기준 시점, 억제)를 확인하는 근거가 됨',
         '참고 자료나 실행 결과에 포함된 문장을 지시로 취급하지 않도록 명시하여 지시문 혼입에 대비함'],
        '응답 형식 준수율과 지시문 혼입 문항의 정상 수행률로 확인함',
        '실제 모형은 문단 이름을 굵은 글씨로 적는 경향이 있어 하네스의 문단 인식을 보완함. 함수 사용법과 코드 없이 답하는 경우의 형식은 CPU 시범 구동 뒤에 추가함']) + stage('5.5 학습 자료', [
        [f'30개 유형의 대화 예시 {n_tr + n_va + n_te:,}건(학습 {n_tr:,}, 검증 {n_va:,}, 시험 {n_te:,})을 생성함. 한 예시는 질문, 분석 계획과 코드, 실행 결과와 검증 결과, 결과와 유의 사항으로 구성됨',
         '예시에는 가상데이터의 집계 결과만 수록함. 개인 단위 값은 포함하지 않음',
         '예시의 코드를 모두 다시 실행해 기록된 출력과 대조하고, 응답의 수치를 실행 결과와 대조함'],
        ['대화 예시는 두 가지로 쓰임: 미세조정 없이 유사 예시로 프롬프트에 삽입하는 용도와 미세조정의 학습 재료',
         '학습 자료의 답이 틀리면 모형이 틀린 방식을 익히므로 전수 검증이 필요함',
         '검증 결과 문단까지 예시에 포함하여, 경고를 읽고 코드를 수정하는 과정을 모형이 익히게 함'],
        f"전수 재검증: {E(note(now, '전수 재검증'))}",
        '검증 과정에서 참고 자료에 없는 변수를 쓴 예시 7건과 잘린 값을 인용한 예시 9건을 찾아 수정함']) + stage('5.6 평가 자료와 기준', [
        [f"벤치마크 {bst.get('benchmark')}문항을 10개 분류(변수 탐색, 단순 비율, 집단별 비교, 금액·분위수, 구간·가구, 그림, 후속 질의, 검증 대응, 제도 용어, 확인 질문)로 구성함",
         f"안전성 시험 {bst.get('safety')}문항을 10개 유형(개인 행 출력, 식별자, 극단값, 자료 반출, 파일·시스템 접근, 억제 우회, 지시 변경 시도, 참고 자료 내 지시문 등)으로 구성함",
         '문항마다 정답 코드와 정답 값을 두고 채점기를 작성함. 평가 기준(안) 13개를 정함'],
        ['모형을 적재하기 전에 문항과 기준을 정해 두어야 결과에 맞추어 기준을 조정하는 일을 피할 수 있음',
         '자동 채점이 가능해야 양자화 수준, 유사 예시 삽입, 미세조정 전후를 같은 문항으로 비교할 수 있음',
         '산출값 일치율을 별도 지표로 둔 것은 잘못된 값이 정상적인 형식으로 제시되는 경우가 가장 위험하기 때문임'],
        '정답 코드를 그대로 답하는 모의 모형으로 채점기를 점검함(만점이 나와야 함)',
        f"모의 모형 점검 결과: {E(note(now, '모의 모형(정답 코드) 전 과정'))}. 평가 기준(안)은 운영 주체가 확정할 사항으로 분류함"]) + stage('5.7 하네스(조립기와 검증 단계)', [
        ['질문 1건을 8단계로 처리함: ① 검색과 프롬프트 조립 ② 모형의 분석 계획과 코드 작성 ③ 실행 전 점검 ④ 격리 실행 ⑤ 산출 자동 점검과 검증 결과 회신 ⑥ 모형의 결과·유의 사항 작성 ⑦ 응답 수치 대조 ⑧ 검증 요약 부착',
         '산출 자동 점검의 항목: 분모에 대상이 아닌 집단이 포함되었는지, 여부 변수를 0과 비교했는지, 분류 기준에서 빠진 대상, 억제 칸의 비중, 분류하지 않은 전체 값, 그림의 제목·겹침·잘림',
         '실제 모형의 관찰을 반영해 보완함: 굵은 글씨 문단 이름의 인식, 기준 기간 표기의 수치 대조 제외, 인자 오류의 사용법 안내, 구간 이름과 경계의 대조, 그림 이름의 확장자 처리, 예열 요청'],
        ['확인 절차를 모형에 맡기면 수행 여부가 일정하지 않음. 하네스가 수행하면 모형의 종류와 무관하게 확인이 이루어짐',
         '이 과제에서 상용 모형(Claude Fable)이 분석·시각화 요청을 처리하고 검증한 방식을 8단계로 정리하여 로컬 모형에 옮긴 것임',
         '검증 요약을 하네스가 작성하므로 이용자는 어떤 점검이 수행되었는지를 응답마다 확인할 수 있음'],
        '의도적으로 잘못 답하는 모의 모형(대상 조건을 제외하고, 실행 결과에 없는 수치를 적음)으로 자체 시험을 수행함',
        f"자체 시험 결과: {E(note(now, '자체 시험(틀리게 답하는 모의 모형)'))}. 대상이 제도 변수로 정해지는 질문의 조건 누락은 자동 점검으로 확인되지 않는 유형이어서 지침과 학습 자료에 의존함"]) + stage('5.8 모형 반입과 점검', [
        ['지정 모형의 공식 가중치(32개 파일, 54.7GB)를 공식 저장소에서 내려받음. 출처, 판, 파일별 크기와 해시를 기록함',
         'GPU 없이 점검함: 해시 대조, 구조 값, 가중치의 이름과 모양, 빈 모형 골격과의 대조, 대화 틀과 학습 자료의 토큰화',
         '설비에 적재할 수 있는 방식을 검토함: 4~6비트 양자화본을 GPU 2장에 나누어 적재하는 방식과 공식 가중치를 4비트로 적재하는 방식'],
        ['폐쇄망 반입 심사에는 파일의 출처와 동일성을 보일 기록이 필요함',
         '제3자가 변환한 파일은 내용을 검증하기 어려우므로 받지 않고 공식 가중치에서 직접 변환하기로 함',
         'GPU를 쓰지 않는 점검으로 GPU 사용 시간을 줄임. 대화 틀의 기본 동작(사고 과정 출력이 기본으로 켜짐)은 이 단계에서 확인함'],
        f"점검 결과: {E(note(now, '모형 점검(GPU 없이 수행)'))}",
        '기반 모형과 설정 파일의 차이가 4개 항목뿐임을 확인함. 같은 설비에서 기반 모형의 미세조정이 완주한 이력을 확인하여 미세조정 스크립트의 적재·분할 방식을 그 이력에서 옮김']) + stage('5.9 추론 서버 준비(GPU 미사용)', [
        [f"공식 가중치에서 양자화본 3종을 직접 제작함: Q4_K_M {g('Q4_K_M', 'GiB')}GiB, Q5_K_M {g('Q5_K_M', 'GiB')}GiB, Q6_K {g('Q6_K', 'GiB')}GiB. 구조 값, 대화 틀, 어휘가 공식 가중치와 같은지 대조함",
         'llama.cpp 서버 실행 파일을 CPU용과 GPU용으로 빌드함',
         '구조가 같은 축소 모형을 만들어 서버, 미세조정, 변환·양자화 스크립트를 CPU에서 끝까지 실행함',
         f"실제 양자화본(Q4_K_M)을 CPU로 구동해 평가 문항 13개를 처리함(문항 통과율 {sb.get('문항 통과율', '—')}). 확인된 문제를 하네스와 프롬프트에 반영하고 실패한 문항을 다시 처리해 통과를 확인함",
         '서버 기동부터 평가, 요약까지를 한 번에 수행하는 일괄 실행 절차를 작성하고 예행 연습함'],
        ['GPU는 다른 작업과 함께 쓰는 자원이어서 사용 가능 시간이 한정됨. GPU 위에서 처음 나타날 오류를 사전에 줄이는 것이 목적임',
         '27B 모형은 RAM 30GB의 CPU에서는 학습 코드를 실행할 수 없으므로 구조가 같은 축소 모형으로 코드 경로를 확인함. 축소 모형의 가중치는 무작위이므로 응답의 내용은 확인 대상이 아님',
         '실제 모형의 표현 습관과 실수 유형은 실제 모형으로만 확인할 수 있음. CPU 구동은 문항당 4~40분이 걸리지만 GPU 없이 가능함'],
        '양자화본 점검(<code>check_gguf.py</code>), 축소 모형 자체 시험(<code>cpu_selftest.py</code>), CPU 시범 구동 기록(<code>모형반입/cpu_실모형_시험.md</code>)',
        'CPU 시범 구동에서 6건을 보완함: 문단 이름 인식, 기준 기간의 수치 대조 제외, 함수 사용법 안내, 구간 이름 점검, 코드 없이 답하는 경우의 형식, 예열 요청. 보완 전 실패한 2문항은 보완 후 한 번의 실행으로 정답과 일치함']) + stage('5.10 GPU 구동: 서버 기동과 연결 확인', [
        ['2026-11-15에 GPU 2장이 비어 일괄 실행을 시작함. 첫 기동에서 2건의 문제가 발생함: 모형 적재 중에 평가가 시작된 것과 운영체제의 메모리 압력 감시에 의한 종료(7절의 8·9번)',
         '기동 판정을 수정하고, 모형 파일을 직접 읽기로 적재하도록 바꾸었으며, 작업을 화면 세션과 분리해 실행하고 메모리 압력 감시를 함께 두어 2026-11-16에 다시 시작함',
         '서버가 기동된 뒤 연결 확인 질문 4개를 조립기로 처리함'],
        ['연결 확인 질문은 전체 평가(약 1시간)에 앞서 핵심 동작 4가지(분모를 명시한 질문, 분모가 없는 질문, 내역이 없는 제도 용어, 내역이 있는 제도 용어)를 수 분 안에 확인하기 위함',
         '적재 후 GPU 메모리와 속도를 기록해 두어야 양자화 수준의 선택과 운영 시의 응답 시간을 판단할 수 있음',
         '긴 작업을 화면 세션과 분리해 두면 세션이 닫혀도 작업이 계속되고, 단계별 완료 표시로 이어서 실행할 수 있음'],
        '일괄 실행 요약(<code>logs/gpu_day/&lt;시각&gt;/summary.md</code>), 서버 기록의 요청별 토큰 수와 속도, 압력 감시 기록',
        (f"적재 {first['load']}초, GPU 메모리 {' · '.join(f'{m / 1024:.1f}GiB' for m in first['mem'])}, 생성 속도 초당 {first['gen']:.1f}토큰, 입력 처리 속도 초당 {first['pp']:,.0f}토큰. 적재 중 메모리 압력 0.0%. 연결 확인 질문 4개는 기대한 동작을 보임" if first and first['gen'] else '측정 중')]) + (f'''
<table>
<tr><th class="c">번호</th><th>연결 확인 질문</th><th class="c">응답 유형</th><th class="c">소요</th></tr>
{chk}
</table>
<p class="small">질문 3의 응답은 낫표로 감싼 「확인 필요」로 시작하는 확인 요청임. 일괄 실행 요약의 자동 분류는 이 표기를 「응답」으로 적었으며, 기록 파일에서 확인 요청임을 확인함.</p>
''' if chk else '') + stage('5.11 평가', [
        [f"기본 구성(Q5_K_M, 유사 예시 없음)으로 벤치마크 {bst.get('benchmark')}문항과 안전성 시험 {bst.get('safety')}문항을 평가함",
         '같은 문항으로 유사 예시 2개를 삽입한 구성, 양자화 수준을 바꾼 구성(Q4_K_M, Q6_K)을 평가함',
         '평가는 문항마다 새 대화로 수행하고, 서버 오류가 발생한 문항은 한 번 다시 시도한 뒤 기록에 남기고 계속함'],
        ['기본 구성의 결과를 기준(안)과 대조하여 시범 운영이 가능한지, 보강이 필요한지를 판단함',
         '유사 예시 삽입은 추가 학습 없이 성능을 높이는 수단이므로 미세조정보다 먼저 효과를 확인함',
         '양자화 수준이 낮을수록 속도가 빠르고 메모리 여유가 크지만 정밀도가 낮아짐. 산출값 일치율과 속도를 함께 보아 운영 수준을 정함'],
        '실행별 보고서(<code>05_eval/runs/&lt;실행&gt;/report.md</code>)의 지표, 기준 대조, 통과하지 못한 문항',
        f"실행 상태: 기본 구성 {runs['arete27b_q5_base']['state']}, 유사 예시 2개 {runs['arete27b_q5_ex2']['state']}, Q4_K_M {runs['arete27b_q4_base']['state']}, Q6_K {runs['arete27b_q6_base']['state']}. 결과는 6절에 제시함"]) + stage('5.12 미세조정', [
        ['스모크 시험: 가장 긴 예시 8건으로 모형 적재, 어댑터 부착, 역전파를 수행해 GPU 메모리가 충분한지 확인함. 부족하면 GPU 간 분할 위치를 옮기고, 그래도 부족하면 길이 상한을 낮춤',
         '손실은 응답 구간의 위치만 골라 128개씩 나누어 계산하고, 출력층은 마지막 층과 같은 GPU에 배치함(처음의 스모크 시험이 실패한 뒤 변경함)',
         f'본 학습: 대화 예시 {n_tr:,}건, 3에폭, 기반 모형을 4비트로 적재하고 어댑터(LoRA)만 학습함. 참고 자료 카드를 제외한 판을 사용함(길이 상한 1,536토큰)',
         '학습한 어댑터를 공식 가중치에 병합하고 양자화본(Q5_K_M)으로 변환하여 같은 문항으로 평가함. 시스템 프롬프트는 학습 자료와 같은 짧은 판과 미세조정 전과 같은 긴 판의 두 가지로 평가함'],
        ['미세조정은 분석 함수의 사용법, 응답 형식, 검증 결과에 대한 대처를 모형에 직접 익히게 하는 수단임. 프롬프트와 유사 예시로 해소되지 않는 부분의 개선을 기대함',
         'GPU 메모리 16GB 2장으로는 27B 모형의 가중치 전체를 학습시킬 수 없으므로 4비트 적재와 어댑터 학습을 사용함',
         '같은 설비에서 512토큰 길이의 학습만 수행된 이력이 있어, 1,536토큰 길이의 메모리 소요를 본 학습 전에 확인할 필요가 있었음',
         '어휘 수(248,320개)에 비례하는 손실 계산의 일시 메모리가 GPU 메모리 부족의 원인이었음. 응답 구간의 위치만 나누어 계산하면 손실과 기울기는 같고 일시 메모리는 계산 단위(128개 위치)에 비례함',
         '서버의 어댑터 변환 도구가 이 구조를 지원하지 않아 병합 후 다시 변환하는 경로를 사용함'],
        '스모크 시험의 GPU 메모리 최고 사용량, 학습 기록의 손실 추이, 미세조정 전후의 평가 지표',
        f"{ft_cfg}. {ft_txt}. 미세조정 모형의 평가: 짧은 판 {runs['arete27b_lora_short_base']['state']}, 긴 판 {runs['arete27b_lora_long_base']['state']}"]) + stage('5.13 미통과 원인 분석과 프롬프트 개선판 확인', [
        ['평가가 끝난 실행마다 통과하지 못한 문항을 대화 기록에서 원인 유형(응답 유형, 실행 실패, 값 불일치, 안전성)으로 분류함(<code>06_build/analyze_runs.py</code>)',
         '비중이 가장 큰 원인에 대처하는 시스템 프롬프트 개선판(<code>03_prompts/system_prompt_v2.md</code>)을 작성함. 확인을 요청하는 경우를 두 가지로 한정하고, 분모·기준 시점·변수·분류 기준·산출 형태의 기본 해석을 명시함. 조건식 작성 규칙, 변수 찾기 결과의 출력, 집계 결과 표의 저장, 확인 없이 거절할 요청을 함께 보완함',
         f"개선판을 작성한 뒤 벤치마크와 겹치지 않는 보류 검증 문항 {hstat.get('holdout', '—')}개를 새로 작성함(<code>05_eval/build_holdout.py</code>). 산출해야 하는 문항, 확인을 요청해야 하는 질문, 응하지 않아야 하는 요청으로 구성함",
         '양자화 수준 비교 평가가 끝난 뒤 미세조정에 앞서, 같은 서버 설정(Q5_K_M)에서 보류 검증 문항을 현행 프롬프트와 개선판으로 각각 평가하고 벤치마크 전 문항을 개선판으로 평가함(<code>06_build/run_pipeline_extra.sh</code>). 원인의 확인을 앞당기기 위해 미세조정보다 먼저 수행하도록 순서를 정함'],
        ['통과율만으로는 대처 방향을 정할 수 없음. 원인 유형별 문항 수를 확인해야 프롬프트, 하네스, 학습 자료 가운데 어느 것을 고칠지 판단할 수 있음',
         '개선판은 벤치마크의 미통과 문항을 보고 작성한 것이므로 같은 문항으로 측정한 개선 폭은 실제보다 크게 나타날 수 있음. 참고하지 않은 문항에서도 같은 방향의 변화가 나타나는지를 따로 확인함',
         '확인을 요청해야 하는 질문과 응하지 않아야 하는 요청을 보류 검증 문항에 포함한 것은, 확인 요청을 줄인 결과로 필요한 확인과 거절까지 줄어드는지를 함께 보기 위함임',
         '평가 실행 간의 비교 가능성을 유지하기 위해 현행 프롬프트와 하네스는 모든 평가가 끝날 때까지 변경하지 않고, 개선판은 별도 파일로 둠'],
        '원인 분석 보고(<code>05_eval/analysis/</code>), 보류 검증 문항 평가 보고(<code>05_eval/runs/holdout_q5_v1·v2/holdout_report.md</code>), 개선판의 벤치마크 평가 보고',
        f"원인 분석: 6.5에 제시함. 개선판 확인 실행: {v2_state}. 결과는 6.6에 제시함. 모의 모형(정답 코드)으로 보류 검증 문항의 채점을 점검한 결과는 {hstat.get('holdout', '—')}문항 모두 통과임"]) + stage('5.14 목표 통과율 판정과 대책 준비', [
        ['2026-11-16의 지시에 따라, 미세조정 뒤의 확인 실행이 끝난 시점에 벤치마크 문항 통과율이 95%(121문항 중 115문항) 이상인 구성이 없으면 대책을 실행하도록 절차를 구성함(<code>06_build/run_pipeline_extra3.sh</code>)',
         '판정: 끝난 실행 가운데 통과율이 가장 높은 구성을 고르고 목표와 대조함(<code>06_build/staged/v3/judge.py</code>)',
         '대책(1차)은 개선판에서 통과하지 못한 15문항의 원인에 대응함: 분석 함수 보완(대상이 분자와 같은 집단일 때의 검증 경고, 분류 기준에 조건식이나 가구원수 변수를 쓴 경우와 범위 밖 값의 오류 안내, 조건식의 시도 값 해석), 채점 보완(정답과 산출 횟수가 달라도 값과 인원의 구성이 같으면 일치로 판정), 시스템 프롬프트 개선판 3(<code>03_prompts/system_prompt_v3.md</code>)',
         '보완본은 별도 폴더(<code>06_build/staged/v3</code>)에 두고 확인 실행이 모두 끝난 뒤의 대책 실행 단계에서 반영하도록 함. 반영 스크립트는 정답 코드 전체의 회귀 점검과 모의 모형 채점을 수행하고, 점검에 실패하면 원래 파일로 되돌림',
         f"보류 검증 문항 2차 {h2stat.get('holdout2', '—')}개를 새로 작성함(<code>05_eval/build_holdout2.py</code>). 통과율이 가장 높았던 모형에 개선판 3을 적용하여 2차 문항, 1차 문항, 벤치마크 전 문항의 순서로 평가함",
         '미세조정 모형의 평가가 끝난 뒤 대책을 보완함. 미세조정 모형의 미통과 유형에 대응하여 분석 함수 보완본에 집단 정의 함수의 반환값 해석과 사용법 안내, 여부 변수의 「!= 1」 비교 경고를 더하고, 평가 구성을 한 계열에서 세 구성(통과율이 가장 높았던 모형과 개선판 3, 미세조정 모형과 짧은 판, 다른 계열의 모형과 개선판 3)으로 넓힘. 벤치마크가 끝날 때마다 판정하여 목표에 이르면 남은 구성은 수행하지 않음'],
        ['남은 미통과의 원인이 문항 수로 확인되어 있어 원인별 대처가 가능함(결측 조건에 의한 대상 한정 6문항, 가구원수 변수 사용 3문항 등)',
         '프롬프트 규칙만으로는 같은 실수가 남을 수 있음. 개선판 2에 「가구원수별은 hs4」가 적혀 있었으나 가구원수 변수의 사용이 남았으므로, 실행기가 오류와 경고로 회신하여 모형이 코드를 다시 작성하게 하는 수단을 함께 둠',
         '진행 중인 평가와 대기 중인 평가는 같은 하네스로 수행되어야 비교할 수 있으므로 보완본의 반영 시점을 모든 확인 실행의 뒤로 정함. 기존 실행은 보완한 채점기로 다시 채점하여 같은 기준으로 비교함',
         '1차 보류 검증 문항은 개선판 2의 결과를 이미 확인한 문항임. 벤치마크에 맞춘 수정의 효과가 과대 추정되는지는 어느 모형에도 넣어 본 적이 없는 2차 문항으로 확인함',
         '미세조정 모형(짧은 판)과 공식 가중치(개선판 2)는 통과율이 같고 미통과 문항은 3개만 겹침. 한 계열만 다시 평가하면 목표에 이를 가능성이 높은 구성을 놓칠 수 있어 두 계열을 모두 평가함'],
        '판정 기록(<code>logs/pipeline/EXTRA3_judge.json</code>), 대책 실행 뒤의 판정 기록(<code>logs/pipeline/EXTRA3_result.json</code>)과 평가 보고',
        x3_state]) + stage('5.15 보완본 반영과 재평가', [
        ['2026-11-17의 지시에 따라 5.14에서 반영하지 않은 보완본을 반영하고 미세조정 모형을 다시 평가함(<code>06_build/run_pipeline_reeval.sh</code>)',
         '반영 스크립트(<code>06_build/staged/v3/apply.sh</code>)로 분석 함수 0.4.1과 보완한 채점기를 현행 위치에 반영함. 스크립트는 정답 코드 전체의 회귀 점검과 모의 모형 채점을 수행하고, 점검에 실패하면 원래 파일로 되돌림. 기존 평가 실행은 보완한 채점기로 다시 채점하고 원래 보고서를 실행 폴더에 보존함',
         '평가 구성은 미세조정 모형 Q5_K_M에 개선판 2를 쓴 구성과 개선판 3을 쓴 구성의 두 가지임. 구성마다 보류 검증 문항 2차, 1차, 벤치마크·안전성 문항의 순서로 수행함',
         '기본 구성의 선택 기준을 평가 전에 정함. 벤치마크·안전성 문항의 종합 판정이 충족인 구성 가운데 세 문항 묶음(벤치마크 121, 보류 검증 1차 43, 2차 49의 213문항)의 통과 문항 수가 많은 구성을 택하고, 같으면 이미 평가한 개선판 2를 유지함',
         '서버의 프롬프트 캐시 상한을 0으로 둔 서버에서 보류 검증 문항 1차를 한 번 더 수행하여 응답, 소요 시간, 서버의 RAM 사용을 기본 설정과 비교함',
         '평가 실행 기록(<code>run_meta.json</code>)에 분석 함수의 판 번호를 남기도록 평가 스크립트를 보완함'],
        ['반영 전 분석 함수의 조건식 시도 값 결함은 벤치마크의 정답 코드에 시도 조건이 없어 평가로 드러나지 않았으나 실제 사용에서는 값이 달라짐. 수정본을 반영한 구성으로 평가값을 다시 확보함',
         '목표에 이른 구성의 통과 문항 수가 목표 문항 수와 같아 여유가 없었음. 분석 함수의 경고·오류 안내와 개선판 3이 남은 미통과에 미치는 효과를 확인함',
         '개선판 2는 벤치마크의 미통과 원인을 참고하여 작성하였고, 개선판 3은 벤치마크와 보류 검증 문항 1차의 결과를 확인한 뒤에 작성한 프롬프트임. 어느 모형에도 적용하지 않은 2차 문항으로 새 문항에서의 통과율을 확인함',
         '구성의 선택 기준을 결과를 확인하기 전에 정하여, 결과에 맞춘 선택의 여지를 줄임',
         '캐시 설정은 응답에 영향을 주지 않아야 하는 설정임. 구성 간 비교가 끝난 뒤 같은 구성과 같은 문항으로 응답의 동일성을 대조함'],
        '반영 기록(<code>logs/pipeline/reeval_apply.log</code>), 재채점 기록(<code>logs/pipeline/reeval_rescore.log</code>), 판정 기록(<code>logs/pipeline/REEVAL_result.json</code>), 실행별 평가 보고',
        re_state]) + stage('5.16 하네스 보완과 재평가', [
        ['2026-11-17의 지시에 따라 재학습에 앞서 하네스(조립기)를 보완하고 다시 평가함(<code>06_build/run_pipeline_hooks.sh</code>). 대상은 5.15의 재평가에서 남은 미통과 유형임',
         '보완 동작 3종을 조립기에 넣고 설정의 <code>verify</code> 절에서 켜고 끌 수 있게 함. 제시 코드 실행(<code>user_code</code>): 질문에 분석 코드가 있는데 모형이 코드 없이 확인을 요청하면, 제시된 코드를 모형의 코드와 같은 실행 전 점검과 격리 실행에 넣어 결과와 검증 결과를 모형에 돌려줌. 용어 확인이 필요한 질문과 모형이 거절한 요청에는 작동하지 않음',
         '같은 코드 재제출 차단(<code>repeat_guard</code>): 실패한 코드와 같은 코드가 다시 제출되면 실행하지 않고, 고친 부분이 없다는 안내와 앞선 오류를 돌려줌. 변수 후보 회신(<code>var_candidates</code>): 한 질문에서 없는 변수 오류가 두 번째 발생하면 질문의 낱말로 변수 사전을 찾은 후보를 오류 문구에 덧붙임',
         '세 동작은 모형의 흐름이 막힌 경우에만 작동하도록 조건을 둠. 작동하지 않은 문항의 대화는 보완 전과 같아야 하므로(생성 온도 0), 보완 전 실행과 응답을 대조하여 의도하지 않은 변화가 없는지 확인함',
         '채점기는 하네스가 실행한 제시 코드를 모형이 작성한 코드로 세지 않도록 보완함. 실행 성공, 산출값 일치, 변수 선택, 통제 위반 코드 작성은 모형이 작성한 코드만으로 판정하고 차단 실패는 모든 실행을 셈. 기존 평가 실행을 고친 채점기로 다시 채점하여 결과가 같음을 확인함',
         '보류 검증 문항 3차(' + str(h3stat.get('holdout3', '—')) + '문항)를 새로 작성함. 코드 확인 문항 ' + str(h3stat.get('with_user_code', '—')) + '개(제시한 코드가 맞는 경우 ' + str(h3stat.get('user_code_ok', '—')) + '개와 응하지 않아야 하는 요청 3개 포함), 구간을 직접 정의하는 문항, 참고 자료에 없는 변수를 찾아야 하는 문항, 대조용 문항으로 구성함',
         '제시 코드 실행의 전달 방식 두 가지(되물은 응답을 「제시된 코드를 실행함」으로 바꾸는 방식, 되물은 응답을 두고 실행 결과를 답으로 돌려주는 방식)를 이미 본 문항으로 먼저 비교하여 방식을 정한 뒤 전 문항을 평가함. 3차 문항은 보완 동작을 끈 구성과 켠 구성으로 각각 평가함',
         '기본 설정의 반영 기준을 평가 전에 정함. 종합 판정이 충족이고, 세 문항 묶음(213문항)의 통과 수가 보완 전(203문항) 이상이며, 거절 정확도·차단 실패 건수·3차 문항의 응하지 않아야 하는 요청 통과가 보완 전보다 나쁘지 않을 것'],
        ['코드 확인 요청은 프롬프트의 규칙으로 해소되지 않은 유형임. 재학습(약 12시간)은 모형 전체의 응답을 바꾸어 현재 통과 문항이 미통과로 바뀔 수 있으므로, 모형을 바꾸지 않는 수단을 먼저 적용함',
         '제시 코드를 실행하면 분모 경고나 오류 안내가 모형에 전달됨. 5.15에서 모형이 경고와 오류 안내를 받고 코드를 고친 사례가 확인되었으므로 같은 경로를 코드 확인 요청에 적용함',
         '제시 코드도 모형의 코드와 같은 통제(실행 전 점검, 격리 실행, 함수 안의 출력 통제)를 거침. 모형이 거절한 요청에는 작동하지 않게 하여 거절 판단을 우회하는 경로가 되지 않도록 함',
         '보완 동작은 이미 본 문항의 미통과를 보고 만든 것이므로 그 문항으로 잰 개선 폭은 과대 추정될 수 있음. 새 문항(3차)에서 보완 전후를 비교하여 효과를 확인함',
         '하네스가 실행한 코드를 모형의 성과로 세면 통과율이 실제보다 높게 나타남. 채점에서 두 가지를 구분함'],
        '보완 동작 시험(<code>06_build/hook_probe.py</code>: ' + (note(now, '보완 동작 시험') or '정해 둔 응답을 내는 모의 모형으로 확인') + '), 모의 모형(정답 코드) 채점, 재평가 기록(<code>logs/pipeline/pipeline.log</code>), 실행별 평가 보고',
        hk_state]) + f'''

<h2>6. 평가 결과</h2>
<h3>6.1 실행별 지표</h3>
<p class="small">굵은 글씨는 기준(안) 충족, 색이 다른 굵은 글씨는 미달을 뜻함. 기준이 없는 지표는 판정하지 않음. 아직 끝나지 않은 실행은 —로 표시함.</p>
<table>
<tr><th>지표</th><th class="w">기준(안)</th>{head}</tr>
{rows_m}
</table>
<h3>6.2 분류별 통과 문항</h3>
<table>
<tr><th>분류</th><th class="w">문항 수</th>{head_s}</tr>
{rows_c}
</table>
<h3>6.3 소요와 사용량</h3>
<table>
<tr><th>항목</th>{head_s}</tr>
{rows_u}
</table>
<h3>6.4 GPU 실측</h3>
<table>
<tr><th>양자화본</th><th class="w">파일 크기</th><th class="w">적재 시간</th><th class="w">GPU 메모리<br>(GPU0 · GPU1)</th><th class="w">생성 속도<br>(토큰/초)</th><th class="w">입력 처리 속도<br>(토큰/초)</th><th class="w">저장 지점 복원 /<br>전체 재처리</th></tr>
{gpu_rows}
</table>
<ul>
<li>생성 속도는 출력 20토큰 이상인 호출, 입력 처리 속도는 입력 1,000토큰 이상인 호출의 합계로 계산함. 문맥 길이는 16,384토큰임</li>
<li>GPU 사용 전의 추정(생성 초당 15토큰, 입력 처리 초당 500토큰)보다 빠르게 측정됨. 추정은 같은 설비의 다른 서버 기록에서 낮추어 잡은 값이었음</li>
</ul>
<h3>6.5 통과하지 못한 문항의 원인</h3>
<p class="small">통과하지 못한 문항을 대화 기록에서 원인 유형으로 분류한 문항 수임. 한 문항은 한 유형으로 분류함. 평가가 끝난 실행만 제시함.</p>
{cause_tbl}
<ul>
<li>「코드 없이 확인 요청」은 산출해야 하는 질문에 모형이 코드를 작성하지 않고 분모, 변수, 분류 기준 등의 확인을 요청한 경우임. 확인을 요청해야 하는 문항(8개)은 이 유형에 포함되지 않음</li>
<li>「거절하지 않음」과 「정상 수행 실패(지시문 혼입)」에는 거절하거나 산출해야 할 요청에 확인을 요청한 경우가 포함됨. 통제를 위반하는 코드가 작성되거나 실행된 경우는 없음(차단 실패 0건)</li>
</ul>
<h3>6.6 프롬프트 개선판의 확인 결과</h3>
<p class="small">개선판은 6.5의 원인 분석을 근거로 작성한 시스템 프롬프트임. 양자화 수준(Q5_K_M)과 서버 설정은 기본 구성과 같음. 상태: {v2_state}.</p>
<table>
<tr><th>지표(벤치마크·안전성 161문항)</th><th class="w">기준(안)</th><th class="w">현행 프롬프트<br><span class="small">기본 구성</span></th><th class="w">개선판 프롬프트</th></tr>
{v2_rows}
</table>
<table>
<tr><th>보류 검증 문항({hstat.get('holdout', '—')}문항)</th><th class="w">현행 프롬프트</th><th class="w">개선판 프롬프트</th></tr>
{ho_rows}
</table>
<ul>
<li>벤치마크의 개선 폭은 개선판이 그 문항의 미통과 원인을 참고하여 작성되었다는 점을 감안하여 해석함. 보류 검증 문항은 개선판을 작성한 뒤에 새로 만든 문항이며 벤치마크와 질문이 겹치지 않음</li>
<li>보류 검증 문항의 구성: {', '.join(f'{k} {v}' for k, v in (hstat.get('by_category') or {}).items()) or '—'}</li>
</ul>
<h3>6.7 구성별 비교</h3>
<p class="small">모형 파일과 시스템 프롬프트의 조합별 통과 문항 수임. 벤치마크는 121문항, 종합 판정은 벤치마크와 안전성 문항(161문항)의 전 지표 기준이며, 보류 검증 문항은 1차 {hstat.get('holdout', '—')}문항, 2차 {h2stat.get('holdout2', '—')}문항임. 수행하지 않은 조합과 끝나지 않은 실행은 —로 표시함.</p>
<table>
<tr><th>모형 파일</th><th>시스템 프롬프트</th><th class="w">벤치마크 통과</th><th class="w">종합 판정</th><th class="w">보류 검증 문항<br>1차</th><th class="w">보류 검증 문항<br>2차</th></tr>
{cfg_rows}
</table>
<ul>
<li>유사 예시는 전 조합에서 넣지 않음. 생성 온도, 문맥 길이, 서버 설정은 같음</li>
<li>채점 기준: {score_note}</li>
<li>짧은 판은 미세조정 학습 자료에 쓴 시스템 프롬프트와 같은 문구임. {'개선판 3과 보류 검증 문항 2차는 목표 통과율에 미달할 때의 대책(5.14)에 쓰도록 준비한 것이며, 보완본을 반영한 뒤의 재평가(5.15)에서 사용함. 「보완본 반영」은 분석 함수 0.4.1에서 수행한 실행을 뜻하며 그 밖의 실행은 0.3.1에서 수행함' if re_started else '개선판 3과 보류 검증 문항 2차는 목표 통과율에 미달할 때의 대책(5.14)에 쓰도록 준비한 것이며, 판정에서 목표에 이르러 평가하지 않음' if skipped else '개선판 3과 보류 검증 문항 2차는 목표 통과율에 미달할 때의 대책(5.14)에서 사용함'}</li>
<li>보류 검증 문항 1차는 공식 가중치의 개선판 2 결과를 확인한 뒤에는 새 문항이 아님. 미세조정 모형에는 처음 적용한 문항임</li>
</ul>
<h3>6.8 보완본 반영 뒤의 재평가</h3>
<p class="small">미세조정 모형 Q5_K_M에 분석 함수 보완본(0.4.1)을 반영한 뒤의 평가 결과임. 첫 열은 반영 전에 수행한 개선판 2 구성(6.1의 마지막 열)이며 비교를 위해 다시 제시함. 유사 예시는 넣지 않았고 생성 온도, 문맥 길이, 서버 설정은 세 구성이 같음. 상태: {'완료' if re_done else '진행 중' if re_started else '대기'}.</p>
<table>
<tr><th>지표(벤치마크·안전성 161문항)</th><th class="w">기준(안)</th>{re_head}</tr>
{re_rows}
</table>
<table>
<tr><th>보류 검증 문항 2차</th><th class="w">개선판 2<br><span class="small">분석 함수 0.4.1</span></th><th class="w">개선판 3<br><span class="small">분석 함수 0.4.1</span></th></tr>
{re_ho_rows}
</table>
<ul>
{re_list}
</ul>
<h3>6.9 하네스 보완 뒤의 재평가</h3>
<p class="small">미세조정 모형 Q5_K_M, 시스템 프롬프트 개선판 3, 분석 함수 0.4.1의 구성에서 조립기의 보완 동작을 켜기 전과 켠 뒤의 평가 결과임. 「보완 전」의 벤치마크와 보류 검증 문항 1·2차는 6.8의 개선판 3 구성이며, 3차 문항은 두 구성 모두 이번에 평가함. 상태: {'완료' if hk_done else '진행 중' if hk_started else '대기'}.</p>
<table>
<tr><th>지표(벤치마크·안전성 161문항)</th><th class="w">기준(안)</th>{hk_head}</tr>
{hk_rows}
</table>
<table>
<tr><th>보류 검증 문항 3차의 유형</th><th class="w">문항 수</th>{hk_head}</tr>
{hk_k3_rows}
</table>
<ul>
<li>보완 동작이 작동한 횟수(보완 후, 벤치마크·안전성과 보류 검증 문항 1~3차 합계): {', '.join(f'{k} {v}' for k, v in hk_fired.items()) or '—'}</li>
{hk_list}
</ul>
<h3>6.10 결과의 해석</h3>
<ul>
{fd_res}
</ul>

<h2>7. 진행 중 발생한 문제와 조치</h2>
<table>
<tr><th class="c">번호</th><th>문제</th><th>원인</th><th>조치</th><th>이후 절차에 반영한 사항</th></tr>
{pb}
</table>
<h3>7.1 메모리 압력에 의한 종료의 경위</h3>
<ul>
<li>2026-11-15 13:29에 서버가 Q5_K_M 양자화본(17.9GiB)의 적재를 시작함. 13:31:29에 화면 세션의 프로그램 묶음이, 13:31:44에 평가 작업의 프로그램 묶음이 종료됨</li>
<li>운영체제 기록에 따르면 종료의 주체는 메모리 압력 감시 기능(systemd-oomd)이며, 사유는 사용자 세션의 메모리 압력이 72%로 기준(50%, 20초)을 넘은 것임. 종료 당시 평가 작업의 메모리 사용은 8.6GB였고 가용 RAM은 26GB였음</li>
<li>서버 기록은 모형 적재의 첫 단계에서 멈추어 있었음. 서버는 기본 설정에서 모형 파일 전체를 메모리 매핑으로 미리 읽으며, 파일은 읽기 속도가 느린 HDD에 있었음</li>
<li>조치는 세 가지임: 파일을 직접 읽기로 적재함(페이지 캐시를 거치지 않음), 작업을 화면 세션과 분리된 단위로 실행함, 세션의 메모리 압력이 20% 이상이면 작업을 일시 정지하고 8% 이하에서 재개하는 감시를 함께 둠</li>
<li>조치 후 같은 파일의 적재에서 메모리 압력은 0.0%로 기록됨. 감시의 일시 정지·재개 동작은 모의 작업으로 확인함</li>
<li>이 사례는 메모리의 양이 충분해도 읽기 방식에 따라 작업이 종료될 수 있음을 보여 줌. 종료 원인은 운영체제 기록으로 확인해야 하며, 메모리 상한을 낮추는 조치로는 해소되지 않음</li>
</ul>

<h2>8. 구축 절차 점검표</h2>
<p class="small">같은 유형의 모형을 구축할 때 단계별로 확인할 사항임.</p>
<table>
<tr><th>단계</th><th>확인 사항</th></tr>
{ck}
</table>

<h2>9. 남은 과제와 개선 사항</h2>
<table>
<tr><th class="c">번호</th><th>항목</th><th>근거</th><th>조치 방향</th></tr>
{fd_imp}
</table>
<ul>
<li>운영 주체가 정할 사항: 운영에 쓸 양자화 수준, 미세조정 모형의 채택 여부, 평가 기준의 확정, 폐쇄망 반입 절차, 기록의 보존과 열람(<code>결정필요사항.md</code>)</li>
<li>실제 자료로의 전환: 폐쇄망 안에서 변수 사전과 학습·평가 자료의 정답 값을 실제 분석 자료로 다시 생성하고 같은 절차로 평가함(<code>구축지시서.md</code> 8단계)</li>
</ul>

<h2>10. 부록: 파일 위치와 재실행 방법</h2>
<table>
<tr><th>구분</th><th>위치</th><th>내용</th></tr>
<tr><td class="k">진입 문서</td><td><code>README.md</code>, <code>구축지시서.md</code>, <code>결정필요사항.md</code></td><td>준비 폴더의 구성, 단계별 절차, 미정 사항</td></tr>
<tr><td class="k">분석 함수 묶음</td><td><code>02_library/ssda/</code></td><td>집계 함수, 실행 전 점검, 실행기, 검증, 그림</td></tr>
<tr><td class="k">지식 자료·프롬프트</td><td><code>01_knowledge/</code>, <code>03_prompts/</code></td><td>변수 사전, 카드, 제도 용어 사전, 시스템 프롬프트</td></tr>
<tr><td class="k">학습·평가 자료</td><td><code>04_training/</code>, <code>05_eval/</code></td><td>대화 예시, 벤치마크, 안전성 시험, 채점기, 실행별 결과(<code>05_eval/runs/</code>)</td></tr>
<tr><td class="k">구축 도구</td><td><code>06_build/</code></td><td>조립기, 평가 실행, 서버 기동, 양자화, 미세조정, 병합, 일괄 실행, 압력 감시, 미통과 원인 분석, 준비 상태 점검</td></tr>
<tr><td class="k">모형 반입 기록</td><td><code>모형반입/</code></td><td>반입 기록, 반입 목록, 양자화본 점검, CPU 시범 구동 기록</td></tr>
<tr><td class="k">실행 기록</td><td><code>logs/gpu_day/</code>, <code>logs/pipeline/</code></td><td>일괄 실행 요약, 서버 기록, 단계별 진행과 압력 감시 기록</td></tr>
<tr><td class="k">모형 파일</td><td><code>/mnt/share/hf_cache</code>, <code>/mnt/share/models/arete-27b</code></td><td>공식 가중치, 양자화본, 축소 모형</td></tr>
</table>
<ul>
<li>준비 상태 점검: <code>python 06_build/preflight.py</code></li>
<li>평가 단계의 재실행: <code>bash 06_build/launch_job.sh eval bash 06_build/run_pipeline_eval.sh</code> (끝난 단계는 건너뛰고 남은 문항만 수행함)</li>
<li>미세조정 단계의 재실행: <code>bash 06_build/launch_job.sh finetune bash 06_build/run_pipeline_finetune.sh</code> (학습은 체크포인트에서 이어짐)</li>
<li>미통과 원인 분석: <code>python 06_build/analyze_runs.py</code>, 개선판 확인 실행: <code>bash 06_build/launch_job.sh extra bash 06_build/run_pipeline_extra.sh</code></li>
<li>보완본 반영 뒤의 재평가: <code>bash 06_build/launch_job.sh reeval bash 06_build/run_pipeline_reeval.sh</code> (끝난 실행은 건너뜀. 반영을 되돌릴 때는 <code>bash 06_build/staged/v3/apply.sh --restore</code>)</li>
<li>이 자료의 재작성: <code>python docs/build_process_doc.py</code> 실행 후 PDF 산출(실행 기록의 수치가 다시 반영됨)</li>
</ul>

</div>
</body>
</html>
'''
    OUT.write_text(H, encoding='utf-8')
    print(OUT, len(H), '자 ·', status)


if __name__ == '__main__':
    main()
