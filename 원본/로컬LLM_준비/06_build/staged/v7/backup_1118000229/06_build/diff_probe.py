#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""대화 단위 차분 점검의 자체 시험(모형·GPU 를 쓰지 않음).  python 06_build/diff_probe.py  → 「통과 수 전체 수」
같은 대화에서 앞서 표시한 집계와의 차이로 소수 집단의 값이 드러나는 칸을 가리는지, 정상적인 이어 묻기는 막지 않는지 본다."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '02_library'))
os.environ.setdefault('SSDA_DATA', '/mnt/share/행정데이터_set/work/report/활용고도화전략/적용사례/data/가상데이터_확대본_n42000.parquet')
os.environ['SSDA_EXPORT'] = tempfile.mkdtemp(prefix='ssda_diffprobe_')
from ssda import runner  # noqa: E402

T = []


def conv(name, codes, expect, session='list'):
    """codes 를 한 대화로 차례로 실행. expect: 실행마다 차분 방지로 가린 칸 수(None 은 보지 않음, '+' 는 1칸 이상)."""
    ses = [] if session == 'list' else (tempfile.mkstemp(suffix='.npz')[1] if session == 'file' else None)
    got = []
    for c in codes:
        out = runner.run('import ssda\n' + c, limits=False, session=ses)
        got.append(out.get('diff_blocked', 0) if out['ok'] else 'ERR:' + out['error'][:60])
    ok = all(e is None or (e == '+' and isinstance(g, int) and g > 0) or e == g for e, g in zip(expect, got))
    T.append(ok)
    if not ok or '-v' in sys.argv:
        print(('통과' if ok else '실패'), name, got)
    return got


W = "dis_yn == 1 and sido == '울산'"
G = "sido == '강원' and age >= 65 and nbls_live_yn1 == 1"
# 1 가려진 칸을 뺄셈으로 구하는 짝(표 → 넓은 구간): 넓은 구간을 가림
conv('표 뒤에 65세 이상', [f"print(ssda.count(where=\"{W}\", by='age6'))", f"print(ssda.count(where=\"{W} and age >= 65\"))"], [0, '+'])
# 2 순서를 바꿔도 가림(넓은 구간 → 표: 65~74세 칸을 더 가림)
conv('65세 이상 뒤에 표', [f"print(ssda.count(where=\"{W} and age >= 65\"))", f"print(ssda.count(where=\"{W}\", by='age6'))"], [0, '+'])
# 3 조건을 조금 바꾼 짝(65세 이상 → 65~94세): 인원과 합계 모두 가림
conv('65세 이상 뒤에 65~94세', [f"print(ssda.count(where=\"{G}\")); print(ssda.total('nbls_live_amt', where=\"{G}\"))",
                         f"print(ssda.count(where=\"{G} and age <= 94\")); print(ssda.total('nbls_live_amt', where=\"{G} and age <= 94\"))"], [0, 2])
# 4 파일로 넘기는 경우(프로세스를 새로 띄울 때)도 같음
conv('파일 기록', [f"print(ssda.count(where=\"{G}\"))", f"print(ssda.count(where=\"{G} and age <= 94\"))"], [0, 1], session='file')
# 5 점검을 끄면 가리지 않음
conv('점검 끔', [f"print(ssda.count(where=\"{G}\"))", f"print(ssda.count(where=\"{G} and age <= 94\"))"], [0, 0], session=None)
# 6 같은 대상의 다른 지표(인원 → 평균 → 중위수 → 비율)는 막지 않음
conv('같은 대상의 다른 지표', ["print(ssda.count(where='bp_yn1 == 1'))", "print(ssda.mean('bp_amt', where='bp_yn1 == 1'))", "print(ssda.quantile('bp_amt', where='bp_yn1 == 1'))",
                      "print(ssda.rate('gender == 2', where='bp_yn1 == 1'))"], [0, 0, 0, 0])
# 7 전체 → 분류(시도·연령대·성)와 분류 → 전체는 막지 않음(칸이 충분히 큼)
conv('전체 뒤에 분류', ["print(ssda.count(where='bp_yn1 == 1'))", "print(ssda.count(where='bp_yn1 == 1', by='sido'))", "print(ssda.count(where='bp_yn1 == 1', by='age6'))",
                  "print(ssda.rate('bp_yn1 == 1', where='age >= 65', by='gender'))", "print(ssda.rate('bp_yn1 == 1', where='age >= 65'))"], [0, 0, 0, 0, 0])
# 8 같은 코드를 다시 실행(고쳐 쓰기 전후가 같은 대상)은 막지 않음
conv('같은 집계 반복', ["print(ssda.count(where='age >= 65', by='sido'))", "print(ssda.count(where='age >= 65', by='sido'))", "print(ssda.count(where='age >= 65'))"], [0, 0, 0])
# 9 큰 집단끼리의 차이(65세 이상 → 75세 이상)는 막지 않음
conv('큰 집단의 차이', ["print(ssda.count(where='age >= 65'))", "print(ssda.count(where='age >= 75'))", "print(ssda.mean('bp_amt', where='age >= 75 and bp_yn1 == 1'))"], [0, 0, 0])
# 10 표의 가려진 칸을 전체에서 빼는 짝(분류 → 전체): 가려진 칸의 합이 최소 관측 수 미만이면 전체를 가림
g = conv('분류 뒤에 전체', [f"print(ssda.count(where=\"{W}\", by='age6'))", f"print(ssda.count(where=\"{W}\"))"], [0, None])
print(sum(T), len(T))
