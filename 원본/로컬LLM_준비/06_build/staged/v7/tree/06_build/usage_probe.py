#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""분석 함수 묶음의 오류 안내 시험 — 실제 모형 구동(2026-11-15)에서 드러난 실수 유형을 실행기와 함수 묶음이 잡아 주는지 확인한다.

  ① 인자 이름·순서를 틀린 호출에 「사용법:」 줄(함수 서명)이 붙는지        runner.usage_hint → verify.tool_message (define_group 의 인자 누락은 0.4.1부터 함수의 오류 문구가 사용법과 용례를 안내함)
  ② 구간 경계와 항목 이름이 어긋난 define_group 을 오류로 돌려보내는지     core._check_labels (이름이 한 칸씩 밀린 표를 막음)
  ③ 바른 용례(학습 자료·함수 설명서의 용례)는 걸리지 않는지
  ④ 그림 이름에 확장자를 붙여도 파일 이름이 겹치지 않는지                 plot.save
출력  마지막 줄에 "잡은 수 / 시험 수 · 오탐 수". preflight.py 가 읽는다.   실행: SSDA_DATA 지정 후 python 06_build/usage_probe.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '02_library'))
os.environ.setdefault('SSDA_EXPORT', tempfile.mkdtemp(prefix='ssda_probe_'))
import ssda                                    # noqa: E402
from ssda import runner, verify                # noqa: E402

ssda.open_data()
HINT = {   # 틀린 호출 → 「사용법:」 줄에 들어 있어야 하는 글자
    "import ssda\nr = ssda.rate(where='bp_yn1 == 1', by='sido', denom_where='age >= 65')": 'ssda.rate(num, where=None',
    "import ssda\nr = ssda.rate('age >= 65', by='sido', numerator='bp_yn1 == 1')": 'ssda.rate(num, where=None',
    "import ssda\ng = ssda.define_group('age', [65, 75], labels=['a', 'b', 'c'])": 'ssda.define_group(name, var, bins, labels)',
    "import ssda\nr = ssda.ratio('bp_yn1 == 1')": '쓸 수 있는 함수',
    "import ssda\nr = ssda.rate('bp_yn1 == 1', where='age >= 65', by='sido')\nssda.plot.hbar(r)\nssda.plot.save('x')": 'ssda.plot.save(fig, name)',
}
BAD = [([65, 70, 75, 80], ['65~69세', '70~74세', '75~79세', '80~84세', '85세 이상']),           # 실제 모형이 쓴 것
       ([65, 70, 75, 80, 85], ['65~69세', '70~74세', '75~79세', '80~84세', '85세 이상']),       # 개수 부족
       ([65, 75], ['65~74세', '75~84세', '85세 이상']),
       ([70, 75, 80, 85], ['65세 미만', '65~69세', '70~74세', '75~79세', '80세 이상'])]
GOOD = [('age', [18, 30, 40, 50, 60, 65], ['18세 미만', '18~29세', '30~39세', '40~49세', '50~59세', '60~64세', '65세 이상']),
        ('age', [65, 75, 85], ['65세 미만', '65~74세', '75~84세', '85세 이상']),
        ('age', [3, 6, 8, 13], ['0~2세', '3~5세', '6~7세', '8~12세', '13세 이상']),
        ('age', [20, 65], ['19세 이하', '20~64세', '65세 이상']),
        ('age', [19, 35], ['아동·청소년', '청년', '중장년 이상']),
        ('hnum', [2, 3, 4], ['1인', '2인', '3인', '4인 이상']),
        ('p_labinc', [1, 12000000, 30000000, 50000000], ['근로소득 없음', '1,200만원 미만', '1,200만~3,000만원', '3,000만~5,000만원', '5,000만원 이상']),
        ('h_prop', [100000000, 300000000], ['1억원 미만', '1억~3억원', '3억원 이상'])]
ALT = {   # 분석 함수 0.4.1부터 함수가 직접 사용법을 안내하는 경우(「사용법:」 줄 대신 오류 문구에 사용법과 용례가 들어감)
    "import ssda\ng = ssda.define_group('age', [65, 75], labels=['a', 'b', 'c'])": 'define_group(이름, 변수, 경계값 목록, 항목 이름 목록)',
}
caught = tests = false_alarm = 0
for code, want in HINT.items():
    out = runner.run(code, limits=False); msg = verify.tool_message(out)
    tests += 1; ok = (not out['ok']) and (any(l.startswith('사용법: ') and want in l for l in msg.splitlines()) or (code in ALT and ALT[code] in msg)); caught += ok
    if not ok:
        print('사용법 줄 없음:', code.splitlines()[-1], '→', msg[:200])
for i, (bins, labels) in enumerate(BAD):
    tests += 1
    try:
        ssda.define_group(f'bad{i}', 'age', bins, labels); print('구간 어긋남을 놓침:', bins, labels)
    except ssda.QueryError:
        caught += 1
for i, (var, bins, labels) in enumerate(GOOD):
    try:
        ssda.define_group(f'good{i}', var, bins, labels)
    except ssda.QueryError as e:
        false_alarm += 1; print('바른 용례가 걸림:', bins, labels, '→', str(e)[:120])
out = runner.run("import ssda\nr = ssda.rate('bp_yn1 == 1', where='age >= 65', by='sido')\nfig = ssda.plot.hbar(r)\nssda.plot.save(fig, 'probe_fig.png')", limits=False)
tests += 1; caught += out['ok'] and out['figures'] == ['probe_fig.png']
print(caught, tests, false_alarm)
sys.exit(0 if caught == tests and not false_alarm else 1)
