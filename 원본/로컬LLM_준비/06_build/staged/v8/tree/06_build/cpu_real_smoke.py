#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""양자화본 시범 구동(CPU) — 직접 만든 GGUF 양자화본이 실제로 읽히고 응답을 내는지 GPU 없이 확인한다.

방법과 한계
  · llama.cpp 서버를 CPU 전용으로 띄운다(06_build/serve_llamacpp.sh, MODE=cpu). GPU 에는 아무것도 올리지 않는다.
  · 27B 양자화본(Q4_K_M 약 16GiB)은 이 PC의 RAM(30GB, 다른 작업과 공유)에 다 올라가지 않을 수 있어, 파일을 디스크에서 읽어 가며 계산한다.
    그래서 매우 느리다(토큰당 수 초). 속도 수치는 GPU 구동과 무관하며, 확인하는 것은 「파일이 읽히고 형식에 맞는 응답이 나오는가」뿐이다.
  · 다른 작업에 지장을 주지 않도록 메모리 상한(systemd-run 범위)과 낮은 우선순위로 돌린다. 양자화본은 읽기 속도를 위해 SSD 의 임시 폴더로 복사했다가 끝나면 지운다.

  python 06_build/cpu_real_smoke.py                  # 짧은 질문 1개(수 분)
  python 06_build/cpu_real_smoke.py --full           # 조립기로 분석 질문 1건을 끝까지 처리(약 10분)
  python 06_build/cpu_real_smoke.py --eval-ids B001,B108,S001   # 평가 문항 일부를 CPU 로 처리(문항당 수 분). 하네스와 모형의 어긋남을 GPU 가동 전에 찾는 용도
출력  모형반입/cpu_real_smoke.json, 모형반입/cpu_실모형_시험.md
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GG = Path(os.environ.get('GGUF_DIR', '/mnt/share/models/arete-27b'))
FAST = Path(os.environ.get('SSDA_FAST_DIR', str(Path.home() / '.cache' / 'ssda_cpu_smoke')))
OUT = ROOT / '모형반입'
DATA = os.environ.get('SSDA_DATA', '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet')


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def post(url, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:        # noqa: S310 — 127.0.0.1 의 시험 서버
        return json.loads(r.read().decode('utf-8', errors='replace'))


def alive(port):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/v1/models', timeout=3) as r:   # noqa: S310
            return r.status == 200
    except Exception:                                               # noqa: BLE001
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--quant', default='Q4_K_M'); ap.add_argument('--port', type=int, default=8095); ap.add_argument('--threads', type=int, default=6)
    ap.add_argument('--mem-high', default='auto', help='서버에 허용하는 메모리(파일 캐시 포함). auto: RAM 여유가 되면 파일 전체가 올라가는 크기, 아니면 여유에서 3GiB 를 남긴 크기')
    ap.add_argument('--mem-max'); ap.add_argument('--ctx', type=int, default=8192)
    ap.add_argument('--full', action='store_true'); ap.add_argument('--question', default='65세 이상 기초연금 수급률을 시도별로 알려 줘')
    ap.add_argument('--max-tokens', type=int, default=700); ap.add_argument('--keep-copy', action='store_true'); ap.add_argument('--no-copy', action='store_true')
    ap.add_argument('--eval-ids', help='평가 문항 id 목록(쉼표)'); ap.add_argument('--eval-name', default='arete27b_q4_cpu_subset')
    ap.add_argument('--recheck', action='store_true', help='하네스를 보완한 뒤의 재확인: 결과를 앞선 평가(subset)와 따로 기록하고 서버 기록도 따로 남김')
    a = ap.parse_args()
    src = GG / f'Arete-27B-{a.quant}.gguf'
    if not src.exists():
        log(f'양자화본 없음: {src}'); return 1
    if alive(a.port):
        log(f'포트 {a.port} 를 다른 서버가 쓰고 있음'); return 1
    gib = src.stat().st_size / 2 ** 30
    if a.mem_high == 'auto':                                   # RAM 여유(회수 가능한 캐시 포함)를 보고 정함
        avail = int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable'))) / 2 ** 20
        high = gib + 3 if avail >= gib + 4.5 else max(8.0, avail - 3)
        a.mem_high = f'{int(high * 1024)}M'; rep_fit = high >= gib + 1.5
        log(f'RAM 여유 {avail:.1f}GiB, 파일 {gib:.1f}GiB → 메모리 상한 {high:.1f}GiB ({"파일 전체가 올라감" if rep_fit else "파일 일부를 디스크에서 다시 읽으며 계산"})')
    else:
        rep_fit = None
    a.mem_max = a.mem_max or f"{int(float(a.mem_high.rstrip('MG')) * (1 if a.mem_high.endswith('M') else 1024) + 2048)}M"
    rep = {'at': time.strftime('%Y-%m-%d %H:%M:%S'), 'file': src.name, 'GiB': round(gib, 2), 'threads': a.threads, 'mem_high': a.mem_high, 'file_fits_in_ram': rep_fit,
           'note': 'CPU 전용 시범 구동. 속도는 GPU 구동과 무관함'}
    model = src
    if not a.no_copy:
        FAST.mkdir(parents=True, exist_ok=True)
        model = FAST / src.name
        if not model.exists() or model.stat().st_size != src.stat().st_size:
            free = shutil.disk_usage(FAST).free
            if free < src.stat().st_size + 20 * 2 ** 30:
                log(f'임시 폴더 여유 부족({free / 2 ** 30:.0f}GiB): {FAST}'); return 1
            log(f'SSD 임시 폴더로 복사: {model}'); t0 = time.time()
            subprocess.run(['nice', '-n', '19', 'cp', str(src), str(model)], check=True)
            log(f'복사 완료({time.time() - t0:.0f}초)')
    env = dict(os.environ, MODE='cpu', MODEL=str(model), PORT=str(a.port), ALIAS='arete-27b', CTX=str(a.ctx), THREADS=str(a.threads), TIMEOUT='14400', CUDA_VISIBLE_DEVICES='')
    cmd = ['nice', '-n', '19', 'bash', '06_build/serve_llamacpp.sh']
    if subprocess.run(['systemd-run', '--user', '--scope', '--quiet', '-p', 'MemoryMax=64M', 'true'], capture_output=True).returncode == 0:
        cmd = ['systemd-run', '--user', '--scope', '--quiet', '-p', f'MemoryHigh={a.mem_high}', '-p', f'MemoryMax={a.mem_max}', '-p', 'MemorySwapMax=0', '--'] + cmd
    slog = OUT / ('cpu_real_smoke_server_recheck.log' if a.recheck else 'cpu_real_smoke_server.log')
    fp = open(slog, 'w', encoding='utf-8')
    srv = subprocess.Popen(cmd, stdout=fp, stderr=subprocess.STDOUT, env=env, cwd=str(ROOT))
    try:
        t0 = time.time()
        while not alive(a.port):
            if srv.poll() is not None or time.time() - t0 > 600:
                log(f'서버가 뜨지 않음(기록 {slog})'); rep['ok'] = False; rep['error'] = '서버 기동 실패'; return finish(rep, a, model)
            time.sleep(1)
        rep['load_sec'] = round(time.time() - t0, 1); log(f"서버 응답({rep['load_sec']}초)")
        base = f'http://127.0.0.1:{a.port}'
        # ① 짧은 질문
        ms = [{'role': 'system', 'content': '한국어로 간결하게 답함'}, {'role': 'user', 'content': '국민기초생활보장제도의 급여 종류 네 가지를 한 줄로 적어 줘'}]
        rep['template_tail'] = post(base + '/apply-template', {'messages': ms}, 60)['prompt'][-60:]
        log('짧은 질문 생성 중'); t0 = time.time()
        d = post(base + '/v1/chat/completions', {'model': 'arete-27b', 'messages': ms, 'temperature': 0, 'max_tokens': 64, 'chat_template_kwargs': {'enable_thinking': False}}, 7200)
        tm = d.get('timings') or {}
        rep['short'] = {'question': ms[1]['content'], 'answer': d['choices'][0]['message'].get('content'), 'finish_reason': d['choices'][0].get('finish_reason'),
                        'prompt_tokens': d['usage']['prompt_tokens'], 'completion_tokens': d['usage']['completion_tokens'], 'elapsed_sec': round(time.time() - t0, 1),
                        'prompt_tokens_per_sec': round(tm.get('prompt_per_second') or 0, 2), 'gen_tokens_per_sec': round(tm.get('predicted_per_second') or 0, 2)}
        log(f"응답: {rep['short']['answer']!r} ({rep['short']['elapsed_sec']}초, 생성 초당 {rep['short']['gen_tokens_per_sec']}토큰)")
        ans = rep['short']['answer'] or ''
        rep['short']['korean_answer'] = sum('가' <= c <= '힣' for c in ans) >= 5
        rep['short']['no_think_marks'] = '<think>' not in ans and '</think>' not in ans
        rep['short']['mentions'] = [w for w in ('생계', '의료', '주거', '교육') if w in ans]
        rep['ok'] = bool(rep['short']['korean_answer'] and rep['short']['no_think_marks'])
        # ② 조립기로 분석 질문 1건
        if a.full and rep['ok']:
            import yaml
            run = OUT / 'cpu_real_smoke_run'; run.mkdir(exist_ok=True)
            c = yaml.safe_load((ROOT / 'config' / 'assistant.yaml').read_text(encoding='utf-8'))
            c['model'].update(base_url=f'{base}/v1', max_tokens=a.max_tokens, timeout_sec=14400, context_tokens=a.ctx)
            c['paths'].update(export=str(run / 'export'), log=str(run / 'ssda_log.jsonl'), transcripts=str(run / 'transcripts.jsonl'))
            (run / 'assistant.yaml').write_text(yaml.safe_dump(c, allow_unicode=True), encoding='utf-8')
            log(f'조립기로 질문 처리: {a.question}'); t0 = time.time()
            p = subprocess.run([sys.executable, '06_build/assistant.py', '--config', str(run / 'assistant.yaml'), '--ask', a.question], capture_output=True, text=True,
                               env=dict(os.environ, SSDA_DATA=DATA), cwd=str(ROOT), timeout=6 * 3600)
            (run / 'output.txt').write_text(p.stdout + ('\n[stderr]\n' + p.stderr if p.stderr.strip() else ''), encoding='utf-8')
            o = p.stdout
            rep['full'] = {'question': a.question, 'elapsed_min': round((time.time() - t0) / 60, 1), 'returncode': p.returncode, 'wrote_code': '```python' in o, 'uses_ssda': 'ssda.' in o,
                           'executed_ok': '[실행] 성공' in o, 'has_result_section': bool(re.search(r'\n[#*\s]*결과[*:\s]*\n', o)), 'has_footer': '검증 요약' in o, 'think_marks': '<think>' in o or '</think>' in o,
                           'output_file': str((run / 'output.txt').relative_to(ROOT))}
            log(f"조립기 처리 끝({rep['full']['elapsed_min']}분): 코드 작성 {rep['full']['wrote_code']}, 실행 성공 {rep['full']['executed_ok']}")
        # ③ 평가 문항 일부
        if a.eval_ids and rep['ok']:
            import yaml
            run = OUT / 'cpu_real_smoke_run'; run.mkdir(exist_ok=True)
            c = yaml.safe_load((ROOT / 'config' / 'assistant.yaml').read_text(encoding='utf-8'))
            c['model'].update(base_url=f'{base}/v1', max_tokens=a.max_tokens, timeout_sec=14400, context_tokens=a.ctx)
            (run / 'assistant_eval.yaml').write_text(yaml.safe_dump(c, allow_unicode=True), encoding='utf-8')
            log(f'평가 문항 일부 처리: {a.eval_ids}'); t0 = time.time()
            p = subprocess.run([sys.executable, '06_build/eval_run.py', '--name', a.eval_name, '--config', str(run / 'assistant_eval.yaml'), '--ids', a.eval_ids, '--resume'],
                               capture_output=True, text=True, env=dict(os.environ, SSDA_DATA=DATA), cwd=str(ROOT), timeout=12 * 3600)
            (run / 'eval_output.txt').write_text(p.stdout + ('\n[stderr]\n' + p.stderr if p.stderr.strip() else ''), encoding='utf-8')
            rd = ROOT / '05_eval' / 'runs' / a.eval_name
            r = json.loads((rd / 'report.json').read_text(encoding='utf-8')) if (rd / 'report.json').exists() else {}
            m = json.loads((rd / 'run_meta.json').read_text(encoding='utf-8')) if (rd / 'run_meta.json').exists() else {}
            ent = {'name': a.eval_name, 'ids': a.eval_ids.split(','), 'elapsed_min': round((time.time() - t0) / 60, 1), 'returncode': p.returncode,
                             'n_benchmark': r.get('n_benchmark'), 'n_safety': r.get('n_safety'), 'metrics': r.get('metrics'), 'failed_items': r.get('failed_items'),
                             'by_category': r.get('by_category'), 'safety_by_type': r.get('safety_by_type'), 'harness': r.get('harness'), 'usage': m.get('usage'), 'errors': m.get('errors')}
            fp.flush(); st = slog.read_text(encoding='utf-8', errors='replace')      # 서버 기록에서 프롬프트 재사용 여부를 셈(예열 호출의 효과 확인)
            pt = [int(x) for x in re.findall(r'prompt eval time =\s*[\d.]+ ms /\s*(\d+) tokens', st)]
            ent['server'] = {'full_reprocess': st.count('forcing full prompt re-processing'), 'restored_checkpoint': st.count('restored context checkpoint'),
                                  'prompt_tokens_processed': pt, 'log': slog.name}
            if a.recheck:
                rep['rechecks'] = [ent]                              # 재확인은 실행 이름별로 쌓아 둠(finish 에서 앞선 것과 합침)
            else:
                rep['subset'] = ent
            log(f"평가 문항 일부 처리 끝({ent['elapsed_min']}분): 통과하지 못한 문항 {r.get('failed_items')} · 프롬프트 전체 재처리 {ent['server']['full_reprocess']}회, 저장 지점 복원 {ent['server']['restored_checkpoint']}회")
    except Exception as e:                                          # noqa: BLE001
        rep['ok'] = False; rep['error'] = f'{type(e).__name__}: {e}'; log(rep['error'])
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=30)
        except subprocess.TimeoutExpired:
            srv.kill()
        fp.close()
    return finish(rep, a, model)


def finish(rep, a, model):
    if not a.no_copy and not a.keep_copy and model.exists() and FAST in model.parents:
        model.unlink(); log('임시 복사본 삭제')
    s = rep.get('short') or {}
    rep['summary'] = (f"{rep['file']} CPU 구동: 짧은 질문 응답 {'정상' if rep.get('ok') else '이상'}" + (f"(생성 초당 {s.get('gen_tokens_per_sec')}토큰, CPU)" if s else '')
                      + (f", 분석 질문 1건 코드 작성 {'함' if rep['full']['wrote_code'] else '안 함'}·실행 {'성공' if rep['full']['executed_ok'] else '실패'}({rep['full']['elapsed_min']}분)" if rep.get('full') else ''))
    prev = json.loads((OUT / 'cpu_real_smoke.json').read_text(encoding='utf-8')) if (OUT / 'cpu_real_smoke.json').exists() else {}
    for k in ('full', 'subset'):                                    # 앞선 실행에서 얻은 결과는 지우지 않고 이어 둠
        if k not in rep and prev.get(k) and prev.get('file') == rep['file']:
            rep[k] = prev[k]
    if prev.get('file') == rep['file']:                             # 재확인은 실행 이름별로 모두 남김
        old = list(prev.get('rechecks') or ([prev['recheck']] if prev.get('recheck') else []))
        new = rep.get('rechecks') or []
        rep['rechecks'] = [x for x in old if x.get('name') not in {y.get('name') for y in new}] + new
    sb = rep.get('subset')
    if sb and sb.get('metrics'):
        mm = sb['metrics']
        rep['summary'] += f", 평가 문항 일부({(sb.get('n_benchmark') or 0) + (sb.get('n_safety') or 0)}문항) 문항 통과율 {mm.get('문항 통과율')}·실행 성공률 {mm.get('실행 성공률')}·거절 정확도 {mm.get('거절 정확도')}"
    rcs = [x for x in rep.get('rechecks') or [] if x.get('metrics')]
    for i, rc in enumerate(rcs, 1):
        rep['summary'] += f", 하네스 보완 후 재확인 {i}차({', '.join(rc['ids'])}) 통과하지 못한 문항 {', '.join(rc.get('failed_items') or []) or '없음'}"
    if rep.get('full') and '분석 질문 1건' not in rep['summary']:
        rep['summary'] += f", 분석 질문 1건 코드 작성 {'함' if rep['full']['wrote_code'] else '안 함'}·실행 {'성공' if rep['full']['executed_ok'] else '실패'}({rep['full']['elapsed_min']}분)"
    (OUT / 'cpu_real_smoke.json').write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding='utf-8')
    L = ['# 양자화본 시범 구동 기록(CPU)', '', f"- 일시: {rep['at']} · 파일: {rep['file']}({rep['GiB']}GiB) · 스레드 {rep['threads']}개 · 메모리 상한 {rep['mem_high']}",
         '- 방식: llama.cpp 서버를 CPU 전용으로 띄움(GPU 미사용). CPU 로 계산하므로 속도는 GPU 구동과 무관함', '']
    if s:
        L += ['## 짧은 질문', '', f"- 질문: {s['question']}", f"- 응답: {s['answer']}", f"- 입력 {s['prompt_tokens']}토큰, 출력 {s['completion_tokens']}토큰, {s['elapsed_sec']}초 (생성 초당 {s['gen_tokens_per_sec']}토큰, CPU)",
              f"- 한국어 응답: {'예' if s['korean_answer'] else '아니오'} · 사고 과정 표시 섞임: {'없음' if s['no_think_marks'] else '있음'} · 언급한 급여: {', '.join(s['mentions']) or '없음'}", '']
    f = rep.get('full')
    if f:
        L += ['## 조립기로 처리한 분석 질문 1건', '', f"- 질문: {f['question']}", f"- 소요: {f['elapsed_min']}분(CPU)",
              f"- 코드 블록 작성: {'예' if f['wrote_code'] else '아니오'} · ssda 함수 사용: {'예' if f['uses_ssda'] else '아니오'} · 실행 성공: {'예' if f['executed_ok'] else '아니오'}",
              f"- 「결과」 문단: {'있음' if f['has_result_section'] else '없음'} · 검증 요약: {'붙음' if f['has_footer'] else '없음'} · 사고 과정 표시 섞임: {'있음' if f['think_marks'] else '없음'}",
              f"- 전체 출력: `{f['output_file']}`", '']
    if sb and sb.get('metrics'):
        mm = sb['metrics']
        L += ['## 평가 문항 일부', '', f"- 문항: {', '.join(sb['ids'])} (벤치마크 {sb.get('n_benchmark')}문항, 안전성 시험 {sb.get('n_safety')}문항) · 소요 {sb['elapsed_min']}분(CPU)",
              '- 지표: ' + ', '.join(f"{k} {mm.get(k)}" for k in ('문항 통과율', '실행 성공률', '산출값 일치율', '변수 선택 정확도', '응답 형식 준수율', '수치 근거율', '검증 경고 잔존율', '거절 정확도', '차단 실패 건수') if mm.get(k) is not None),
              f"- 분류별 통과: {sb.get('by_category')} · 안전성 유형별 통과: {sb.get('safety_by_type')}", f"- 통과하지 못한 문항: {', '.join(sb.get('failed_items') or []) or '없음'}",
              f"- 대화 기록: `05_eval/runs/{sb['name']}/transcripts.jsonl`, 지표 상세: `05_eval/runs/{sb['name']}/report.md`", '']
    for i, rc in enumerate(rcs, 1):
        mm, sv = rc['metrics'], rc.get('server') or {}
        L += [f'## 하네스 보완 후 재확인 {i}차', '', f"- 문항: {', '.join(rc['ids'])} · 소요 {rc['elapsed_min']}분(CPU)",
              '- 지표: ' + ', '.join(f"{k} {mm.get(k)}" for k in ('문항 통과율', '실행 성공률', '산출값 일치율', '응답 형식 준수율', '수치 근거율', '평균 모형 호출 횟수') if mm.get(k) is not None),
              f"- 통과하지 못한 문항: {', '.join(rc.get('failed_items') or []) or '없음'}",
              f"- 프롬프트 재사용(서버 기록 `모형반입/{sv.get('log')}`): 전체 재처리 {sv.get('full_reprocess')}회, 저장 지점 복원 {sv.get('restored_checkpoint')}회, 호출별 처리 토큰 수 {sv.get('prompt_tokens_processed')}",
              f"- 대화 기록: `05_eval/runs/{rc['name']}/transcripts.jsonl`, 지표 상세: `05_eval/runs/{rc['name']}/report.md`", '']
    if rep.get('error'):
        L += [f"- 오류: {rep['error']}", '']
    L += ['## 해석의 범위', '', '- 일부 문항의 결과이므로 모형의 성능을 말해 주지 않음. 성능은 GPU 에서 벤치마크 121문항과 안전성 시험 40문항으로 평가함. 양자화 수준도 Q4_K_M 으로, 먼저 쓸 Q5_K_M 과 다름',
          '- 확인된 것: 직접 만든 양자화본이 llama.cpp 에서 읽히고, 대화 틀과 사고 과정 끄기가 적용된 상태로 응답이 생성됨']
    (OUT / 'cpu_실모형_시험.md').write_text('\n'.join(L) + '\n', encoding='utf-8')
    print(rep['summary'])
    return 0 if rep.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main())
