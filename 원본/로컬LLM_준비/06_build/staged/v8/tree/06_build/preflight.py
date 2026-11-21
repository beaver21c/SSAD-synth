#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""준비 상태 점검 — 구축에 들어가기 전에 무엇이 준비됐고 무엇이 남았는지 한 번에 확인한다.

  python 06_build/preflight.py            # 점검표 출력 + 현황.json 갱신
  python 06_build/preflight.py --quick    # 학습 자료 재검증·모의 평가를 건너뜀

GPU 에는 아무것도 올리지 않는다(nvidia-smi 조회만 한다).
판정  준비됨 / 구축 시 수행 / 확인 필요
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '02_library')); sys.path.insert(0, str(ROOT / '06_build'))
PY = sys.executable
OK, TODO, WARN = '준비됨', '구축 시 수행', '확인 필요'


def count(p):
    p = Path(p)
    return sum(1 for l in p.read_text(encoding='utf-8').splitlines() if l.strip()) if p.exists() else 0


def run(cmd, env=None, timeout=900):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout, cwd=str(ROOT))
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:                                  # noqa: BLE001
        return 99, str(e)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--quick', action='store_true'); a = ap.parse_args()
    rows = []

    def add(area, item, state, note=''):
        rows.append({'영역': area, '항목': item, '상태': state, '비고': note})

    from assistant import load_config
    cfg = load_config()
    data = cfg['paths']['data']
    env = dict(os.environ, PYTHONPATH=str(ROOT / '02_library'), SSDA_DATA=data)

    # 1 분석 자료·함수 묶음
    if data and Path(data).exists():
        add('분석 자료', '분석 자료 파일', OK, f'{data} ({Path(data).stat().st_size / 1e6:.0f}MB)')
        code, out = run([PY, '-c', "import ssda,json; ssda.open_data(); print(json.dumps(ssda.info(), ensure_ascii=False)); r=ssda.rate('bp_yn1 == 1', where='age >= 65'); print(r.value())"], env)
        add('분석 함수 묶음', 'ssda 적재·집계 시험', OK if code == 0 else WARN, out.splitlines()[0][:150] if out else '')
    else:
        add('분석 자료', '분석 자료 파일', WARN, '환경변수 SSDA_DATA 에 분석 자료(parquet) 경로를 지정할 것')
    code, out = run([PY, '-c', "from ssda import guard; print(len(guard.check('import pandas as pd\\ndf = pd.read_parquet(\"x\")\\nprint(df.head())')))"], env)
    code2, out2 = run([PY, '06_build/verify_probe.py'], env)
    add('검증 단계', '산출 점검·수치 대조 동작', OK if code2 == 0 and out2.strip().split()[-2:] == ['1', '1'] else WARN, '분모 누락 코드에 경고 1건, 근거 없는 수치 1개 탐지(시험 입력)')
    add('분석 함수 묶음', '실행 전 점검(guard) 동작', OK if code == 0 and out.strip() not in ('', '0') else WARN, f'위반 탐지 {out.strip()}건(시험 코드)')
    if data and Path(data).exists():                       # 실제 모형 구동에서 드러난 실수 유형(인자 이름, 구간 이름)의 안내·차단
        code3, out3 = run([PY, '06_build/usage_probe.py'], env)
        t3 = (out3.strip().splitlines() or [''])[-1].split()
        add('분석 함수 묶음', '오류 안내·구간 이름 점검', OK if code3 == 0 else WARN,
            (f'틀린 호출·어긋난 구간 {t3[1]}건 중 {t3[0]}건에 사용법 안내 또는 오류 회신, 바른 용례 오탐 {t3[2]}건' if len(t3) == 3 else out3[-150:]))
        code4, out4 = run([PY, '06_build/hook_probe.py'], env)      # 조립기 보완 동작(제시 코드 실행, 같은 코드 재제출 차단, 변수 후보 회신, 실행 없는 결과 표 차단)과 채점기의 구분 처리
        t4 = (out4.strip().splitlines() or [''])[-1].split()
        add('조립기·채점기', '보완 동작 시험', OK if code4 == 0 else WARN, (f'{t4[1]}개 시험 중 {t4[0]}개 통과(정해 둔 응답을 내는 모의 모형)' if len(t4) == 2 else out4[-150:]))

    # 2 지식 자료·색인
    kn = {n: count(ROOT / '01_knowledge' / f'{n}.jsonl') for n in ('variables', 'variable_cards', 'program_cards', 'rules', 'doc_cards')}
    add('지식 자료', '변수 사전·카드', OK if kn['variables'] and kn['variable_cards'] else WARN, f"변수 {kn['variables']}개, 사업 카드 {kn['program_cards']}개, 규칙 {kn['rules']}개, 문서 카드 {kn['doc_cards']}개")
    idx = ROOT / '06_build' / 'index' / 'bm25.json'
    n_idx = len(json.loads(idx.read_text(encoding='utf-8'))['docs']) if idx.exists() else 0
    add('지식 자료', '검색 색인', OK if n_idx else WARN, f'{n_idx}건')
    exi = ROOT / '06_build' / 'index' / 'examples.json'
    add('지식 자료', '유사 예시 색인', OK if exi.exists() else WARN, f"{len(json.loads(exi.read_text(encoding='utf-8'))['docs'])}건" if exi.exists() else '없음: python 06_build/retriever.py build')

    # 2-1 제도 용어 사전
    gp = ROOT / '01_knowledge' / 'programs'
    if (gp / 'glossary.json').exists():
        gr = json.loads((gp / 'glossary_report.json').read_text(encoding='utf-8'))
        add('제도 용어', '제도 용어 사전', OK, f"항목 {gr['entries']}개, 용어 {gr['terms']}개, 변수 {gr['variables']}개 · 코퍼스 {gr.get('corpus_version') or '미대조'} 대조, 설명 문장 {gr.get('with_evidence', 0)}개")
        from terms import Glossary
        G = Glossary()
        t1 = [u['policy'] for u in G.resolve('국기초 수급률을 시도별로 알려 줘')['unresolved']]; t2 = G.resolve('국기초 생계급여 수급률을 시도별로')['unresolved']
        t3 = [u['policy'] for u in G.resolve('건강보험 본인부담금 평균을 연령대별로')['unresolved']]; t4 = G.resolve('본인부담금을 외래와 입원을 합쳐서 평균')['unresolved']
        add('제도 용어', '용어 해석 동작', OK if t1 == ['ask'] and not t2 and t3 == ['ask'] and not t4 else WARN, '「국기초」·「본인부담금」은 내역이 없으면 되묻고, 내역이 있으면 진행(시험 질문 4개)')
    else:
        add('제도 용어', '제도 용어 사전', WARN, '없음: python 01_knowledge/programs/build_glossary.py')

    # 3 프롬프트
    for f in ('system_prompt.md', 'system_prompt_short.md', 'system_prompt_v2.md', 'system_prompt_v3.md', 'tool_protocol.json', 'templates/user_turn.md', 'templates/tool_result.md'):
        p = ROOT / '03_prompts' / f
        add('프롬프트', f, OK if p.exists() and p.stat().st_size > 10 else WARN, f'{len(p.read_text(encoding="utf-8"))}자' if p.exists() else '없음')

    # 4 학습 자료
    st = {sp: count(ROOT / '04_training' / 'data' / f'{sp}.jsonl') for sp in ('train', 'valid', 'test')}
    add('학습 자료', '대화 예시', OK if st['train'] else WARN, f"학습 {st['train']}건, 검증 {st['valid']}건, 시험 {st['test']}건")
    if not a.quick and st['train']:
        code, out = run([PY, '04_training/validate.py'], env)
        rep = json.loads((ROOT / '04_training' / 'data' / 'validation_report.json').read_text(encoding='utf-8'))
        add('학습 자료', '전수 재검증', OK if rep.get('passed') else WARN,
            f"코드 {rep.get('rerun')}개 재실행" + (' 일치' if not rep.get('violations', {}).get('V3') else f"(기록과 다른 코드 {rep['violations']['V3']}개)") + f", 응답 {rep.get('answers_checked')}개 수치 대조, 위반 {sum(rep.get('violations', {}).values())}건"
            + ('' if rep.get('passed') else ' — 분석 함수를 바꾼 뒤에는 학습 자료를 다시 생성해야 함(04_training/generate.py). 미세조정에 쓴 자료는 바꾸기 전의 함수 기준임'))

    # 5 평가 자료·조립기
    add('평가 자료', '벤치마크·안전성 시험', OK if count(ROOT / '05_eval' / 'benchmark.jsonl') else WARN, f"{count(ROOT / '05_eval' / 'benchmark.jsonl')}문항, {count(ROOT / '05_eval' / 'safety_cases.jsonl')}문항")
    if not a.quick:
        code, out = run([PY, '06_build/eval_run.py', '--name', 'mock_oracle', '--mock', 'oracle', '--inprocess'], dict(env))
        rep = json.loads((ROOT / '05_eval' / 'runs' / 'mock_oracle' / 'report.json').read_text(encoding='utf-8')) if code in (0, 1) else {}
        add('조립기·채점기', '모의 모형(정답 코드) 전 과정', OK if rep.get('passed') else WARN, f"문항 통과율 {rep.get('metrics', {}).get('문항 통과율')}, 거절 정확도 {rep.get('metrics', {}).get('거절 정확도')}")
        code, out = run([PY, '06_build/eval_run.py', '--name', 'mock_oracle_isolated', '--mock', 'oracle', '--limit', '8'], dict(env))
        add('조립기·채점기', '격리 실행(새 프로세스) 경로', OK if code == 0 else WARN, '8문항')
        code, out = run([PY, '06_build/harness_selftest.py'], dict(env))
        p = ROOT / '05_eval' / 'runs' / 'mock_sloppy' / 'harness_selftest.json'
        st2 = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
        add('검증 단계', '자체 시험(틀리게 답하는 모의 모형)', OK if code == 0 else WARN,
            f"대상 조건 누락 {st2.get('대상 조건을 뺀 문항')}문항 중 {st2.get('분모 경고로 잡은 문항', 0) + st2.get('요청 반영 주의로 잡은 문항', 0)}문항 탐지, "
            f"근거 없는 수치 {st2.get('근거 없는 수치를 적은 응답')}건 모두 다시 작성")

    # 6 설비·모형·추론 서버(구축 단계에서 채워지는 항목)
    code, out = run(['nvidia-smi', '--query-gpu=name,memory.total,memory.used', '--format=csv,noheader'])
    if code == 0:
        gpus = [l.strip() for l in out.splitlines() if l.strip()]
        used = sum(int(l.split(',')[2].strip().split()[0]) for l in gpus)
        add('설비', 'GPU', OK if used < 4000 else WARN, ' / '.join(gpus) + ('' if used < 4000 else ' — 다른 작업이 점유 중이므로 종료 후 모형을 올릴 것'))
    else:
        add('설비', 'GPU', WARN, 'nvidia-smi 조회 불가')
    mem = {l.split(':')[0]: int(l.split()[1]) // 1024 // 1024 for l in Path('/proc/meminfo').read_text().splitlines()[:3]} if Path('/proc/meminfo').exists() else {}
    add('설비', 'RAM', OK if mem.get('MemTotal', 0) >= 16 else WARN, f"전체 {mem.get('MemTotal')}GB, 가용 {mem.get('MemAvailable')}GB")
    # 모형: 공식 가중치(모형 캐시)와 GPU 없이 수행한 점검 결과
    mdir = ROOT / '모형반입'
    exp = json.loads((mdir / 'expected_files.json').read_text(encoding='utf-8')) if (mdir / 'expected_files.json').exists() else None
    if exp:
        hub = Path(os.environ.get('HF_HOME', '/mnt/share/hf_cache')) / 'hub' / ('models--' + exp['repo'].replace('/', '--')) / 'snapshots' / exp['revision']
        have = [f for f in exp['files'] if (hub / f['path']).exists() and (hub / f['path']).stat().st_size == f['size']]
        add('모형', f"공식 가중치({exp['repo']})", OK if len(have) == len(exp['files']) else TODO,
            f"{len(have)}/{len(exp['files'])}개 파일, {sum(f['size'] for f in have) / 1e9:.1f}GB · {hub}" if have else '미반입(구축지시서 2단계)')
        mc = json.loads((mdir / 'model_check.json').read_text(encoding='utf-8')) if (mdir / 'model_check.json').exists() else {}
        names = {'files': '파일·해시', 'config': '구조 값', 'keys': '가중치 이름', 'skeleton': '빈 골격 대조', 'template': '대화 틀·토큰화'}
        add('모형', '모형 점검(GPU 없이 수행)', OK if mc.get('ok') else TODO,
            ', '.join(f"{v} {'통과' if mc.get(k, {}).get('ok') else '미수행'}" for k, v in names.items()) + (f" · 해시 대조 {mc['files'].get('hashed', 0)}개" if mc.get('files') else ''))
    # 양자화본(GGUF): 공식 가중치에서 직접 만든 파일과 머리 정보 점검 결과
    gc = json.loads((mdir / 'gguf_check.json').read_text(encoding='utf-8')) if (mdir / 'gguf_check.json').exists() else None
    if gc:
        gf = [f for f in gc['files'] if Path(gc['dir'], f['file']).exists() and Path(gc['dir'], f['file']).stat().st_size == f['bytes']]
        qs = [f for f in gf if 'bf16' not in f['file']]
        add('모형', 'GGUF 양자화본(직접 변환)', OK if gc.get('ok') and qs and len(gf) == len(gc['files']) else WARN,
            ', '.join(f"{'미세조정 ' if '-lora-' in f['file'] else ''}{f['file'].split('-')[-1].replace('.gguf', '')} {f['GiB']}GiB" for f in qs) + f" · 구조·대화 틀·어휘 대조 {'통과' if gc.get('ok') else '실패'} · {gc['dir']}")
        mf = Path(str(cfg['model'].get('file') or ''))
        add('모형', '설정의 모형 파일과 시스템 프롬프트', OK if mf.exists() and (ROOT / cfg['prompt']['system']).exists() and any(f['file'] == mf.name for f in gf) else WARN,
            f"{mf.name} · {cfg['prompt']['system']}" + ('' if mf.exists() else ' · 모형 파일 없음') + ('' if (ROOT / cfg['prompt']['system']).exists() else ' · 프롬프트 파일 없음') + ('' if any(f['file'] == mf.name for f in gf) else ' · 양자화본 점검 기록에 없음'))
    else:
        add('모형', 'GGUF 양자화본(직접 변환)', TODO, '없음: bash 06_build/make_gguf.sh Q5_K_M 후 python 06_build/check_gguf.py (llama.cpp 서버로 구동할 때만 필요)')
    add('추론 서버', '공식 가중치용 서버 스크립트', OK if (ROOT / '06_build' / 'serve_transformers.py').exists() and (Path.home() / 'anaconda3/envs/vllm/bin/python').exists() else TODO,
        'serve_transformers.py + conda 환경 vllm (GPU 에서 실행한 적 없음. 축소 모형으로 CPU 에서 코드 경로 확인)')
    lbin = Path(os.environ.get('LLAMA', str(Path.home() / 'llama.cpp'))) / 'build-cuda' / 'bin' / 'llama-server'
    binfo = lbin.parent.parent / 'BUILD_INFO.txt'
    add('추론 서버', 'llama-server 실행 파일(CUDA 빌드)', OK if lbin.exists() else TODO,
        (f"{lbin} · " + ' · '.join(l.split(': ', 1)[1] for l in binfo.read_text(encoding='utf-8').splitlines() if l.startswith(('source', 'cuda', 'built_at'))) + ' (2026-11-15부터 GPU 에서 구동함)')
        if lbin.exists() and binfo.exists() else (str(lbin) if lbin.exists() else '없음: bash 06_build/build_llamacpp.sh cuda (양자화본으로 구동할 때만 필요)'))
    # GPU 없이 수행한 코드 경로 시험과 일괄 실행 절차의 예행 연습
    cs = json.loads((mdir / 'cpu_selftest.json').read_text(encoding='utf-8')) if (mdir / 'cpu_selftest.json').exists() else None
    if cs:
        nm = {'hf': '서버(transformers)', 'train': '미세조정', 'gguf': 'llama.cpp 경로'}
        add('코드 경로 시험', '축소 모형 자체 시험(CPU)', OK if cs.get('ok') else WARN,
            ', '.join(f"{v} {'통과' if cs.get(k, {}).get('ok') else '실패'}" for k, v in nm.items()) + f" · {max((cs.get(k, {}).get('at') or '') for k in nm)[:10]} · 구조가 같은 무작위 가중치 모형(코드 경로만 확인)")
    else:
        add('코드 경로 시험', '축소 모형 자체 시험(CPU)', TODO, '미수행: conda 환경 vllm 에서 python 06_build/cpu_selftest.py')
    rs = json.loads((mdir / 'cpu_real_smoke.json').read_text(encoding='utf-8')) if (mdir / 'cpu_real_smoke.json').exists() else None
    if rs:
        add('코드 경로 시험', '양자화본 시범 구동(CPU)', OK if rs.get('ok') else WARN, rs.get('summary', ''))
    dry = sorted((ROOT / 'logs' / 'gpu_day').glob('dryrun_*/summary.md')) if (ROOT / 'logs' / 'gpu_day').exists() else []
    add('코드 경로 시험', '일괄 실행 절차 예행 연습', OK if dry else TODO,
        (f"run_gpu_day.sh 예행 연습 완료({dry[-1].parent.name.replace('dryrun_', '')[:8]}, "
         + ('실제 llama.cpp 서버에 축소 모형을 올려 CPU 로 수행' if '축소 모형' in dry[-1].read_text(encoding='utf-8') else '모의 응답 서버') + ')') if dry else '미수행: bash 06_build/run_gpu_day.sh --dry-run')
    from clients import OpenAICompatClient
    ok, info = OpenAICompatClient(cfg['model']['base_url'], cfg['model']['served_name']).ping()
    add('추론 서버', f"응답 확인({cfg['model']['base_url']})", OK if ok else TODO, '응답함' if ok else '미기동(구축지시서 4단계)')
    cenv = Path.home() / 'anaconda3' / 'envs' / 'vllm' / 'bin' / 'python'
    if cenv.exists():
        code, out = run([str(cenv), '-c', 'import peft, transformers, torch; print(peft.__version__, transformers.__version__, torch.__version__)'], timeout=120)
        add('미세조정', '학습 패키지(conda 환경 vllm)', OK if code == 0 else TODO, ('peft·transformers·torch ' + out.strip().splitlines()[-1]) if code == 0 else '환경은 있으나 패키지 확인 실패')
    else:
        add('미세조정', '학습 패키지', TODO, 'conda 환경 vllm 없음(미세조정을 하기로 정한 경우에만 필요)')
    # 이전 작업에서 만든 자산(코퍼스와 코퍼스 학습 어댑터) — 있으면 구축에 활용할 수 있음
    cm = Path('/mnt/share/corpus/dist/MANIFEST.json')
    if cm.exists():
        mm = json.loads(cm.read_text(encoding='utf-8'))
        add('기존 자산', 'KIHASA 통합 코퍼스', OK, f"판 {mm.get('version')}, 문서 {mm['totals']['documents']:,}건, 청크 {mm['totals']['chunks_ai_ready']:,}개 (/mnt/share/corpus)")
    ad = Path('/mnt/share/corpus/models/adapters/chat_corpus_qwen_v1')
    if (ad / 'adapter_config.json').exists():
        base = json.loads((ad / 'adapter_config.json').read_text(encoding='utf-8')).get('base_model_name_or_path')
        ca = (json.loads((ROOT / '모형반입' / 'model_check.json').read_text(encoding='utf-8')).get('keys', {}).get('corpus_adapter') or {}) if (ROOT / '모형반입' / 'model_check.json').exists() else {}
        add('기존 자산', '코퍼스 학습 어댑터', OK, f"기반 {base}, LoRA r=32 ({ad}) — " + (f"대상 모듈 {ca['modules']}개가 Arete-27B 에 같은 모양으로 있어 부착은 가능, 효과는 미확인" if ca.get('attachable') else 'Arete-27B 에 그대로 쓸 수 있는지는 미확인'))

    summary = {s: sum(1 for r in rows if r['상태'] == s) for s in (OK, TODO, WARN)}
    mcp = ROOT / '모형반입' / 'model_check.json'
    model_ok = bool(json.loads(mcp.read_text(encoding='utf-8')).get('ok')) if mcp.exists() else False
    nxt = 'GPU 가 비면 bash 06_build/run_gpu_day.sh (구축지시서.md 의 4·5단계를 한 번에 수행)' if model_ok else '구축지시서.md 의 2단계(모형 반입·점검)부터 수행'
    out = {'점검 시각': time.strftime('%Y-%m-%d %H:%M:%S'), '준비 폴더': str(ROOT), '모형': cfg['model']['name'], '모형 반입': '완료(공식 가중치, GPU 미사용 점검 통과)' if model_ok else '미완료',
           '요약': summary, '점검표': rows, '다음 단계': nxt if summary[WARN] == 0 else '「확인 필요」 항목을 해소한 뒤 ' + nxt}
    (ROOT / '현황.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    w = max(len(r['항목']) for r in rows)
    for r in rows:
        print(f"[{r['상태']:^7}] {r['영역']:<8} {r['항목']:<{w}}  {r['비고']}")
    print(json.dumps(summary, ensure_ascii=False), '→', out['다음 단계'])
    return 0 if summary[WARN] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
