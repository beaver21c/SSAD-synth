#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""llama.cpp 변환 도구(convert_hf_to_gguf.py)를 메모리를 덜 쓰게 실행하는 포장 스크립트. 만들어지는 파일은 같다.

배경(2026-11-15 실측)
  · 변환 도구는 텐서를 float32 로 바꾼 뒤 bf16 으로 다시 바꾸는데, 그 과정에서 묶음별 결과를 목록에 모두 모았다가 한 번에 이어 붙인다
    (gguf-py/gguf/quants.py 의 _apply_over_grouped_rows). 가장 큰 텐서(어휘 248,320 × 5,120, bf16 2.5GB)에서는
    float32 사본 5.1GB + 결과 목록 2.5GB + 이어 붙인 결과 2.5GB 가 동시에 잡혀 약 11GB 를 쓴다.
  · 이 PC는 RAM 30GB 를 다른 작업과 나눠 쓰므로 메모리 상한 8G·10G 에서 두 차례 중단됐다(이 작업만 중단됨).
  · 여기서는 그 함수만 「묶음 결과를 곧바로 출력 배열에 써 넣는」 방식으로 바꿔 끼운다. 계산식과 결과는 같고 최대 사용량이 약 8GB 로 준다.
    llama.cpp 원본 파일은 고치지 않는다.

사용  PYTHONPATH=~/llama.cpp/gguf-py python 06_build/convert_lean.py ~/llama.cpp/convert_hf_to_gguf.py <모형 폴더> --outtype bf16 --outfile <파일>
      python 06_build/convert_lean.py --selftest ~/llama.cpp     # 바꿔 끼운 함수가 원래 함수와 같은 결과를 내는지 확인
"""
import os
import runpy
import sys

import numpy as np


def lean_apply_over_grouped_rows(func, arr, otype, oshape):
    rows = arr.reshape((-1, arr.shape[-1]))
    osize = 1
    for dim in oshape:
        osize *= dim
    out = np.empty(shape=osize, dtype=otype)
    n_groups = (rows.shape[0] // 16) or 1           # 원본과 같은 묶음 크기
    pos = 0
    for group in np.array_split(rows, n_groups):
        r = func(group).ravel()
        out[pos:pos + r.size] = r                   # 목록에 모으지 않고 곧바로 써 넣음
        pos += r.size
    if pos != osize:
        raise ValueError(f'출력 크기 불일치: {pos} != {osize}')
    return out.reshape(oshape)


def selftest(llama):
    sys.path.insert(0, os.path.join(llama, 'gguf-py'))
    import gguf
    import gguf.quants as Q
    orig = Q._apply_over_grouped_rows
    rng = np.random.default_rng(7)
    ok = True
    for qt in (gguf.GGMLQuantizationType.BF16, gguf.GGMLQuantizationType.Q8_0):
        for shape in ((37, 64), (5, 3, 32), (1, 96), (64,)):
            x = (rng.standard_normal(shape) * rng.choice([1e-6, 1.0, 1e4])).astype(np.float32)
            Q._apply_over_grouped_rows = orig; a = Q.quantize(x, qt)
            Q._apply_over_grouped_rows = lean_apply_over_grouped_rows; b = Q.quantize(x, qt)
            same = a.dtype == b.dtype and a.shape == b.shape and np.array_equal(a, b)
            ok &= bool(same)
            print(f'{qt.name} {shape}: {"같음" if same else "다름"}')
    print('자체 시험', '통과' if ok else '실패')
    return 0 if ok else 1


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == '--selftest':
        return selftest(sys.argv[2])
    if len(sys.argv) < 2 or not sys.argv[1].endswith('convert_hf_to_gguf.py'):
        print(__doc__); return 1
    script = os.path.abspath(sys.argv[1])
    sys.path.insert(0, os.path.join(os.path.dirname(script), 'gguf-py'))
    sys.path.insert(0, os.path.dirname(script))             # 변환 도구가 같은 폴더의 conversion 묶음을 불러오므로 스크립트 폴더를 경로 맨 앞에 둠
    import gguf.quants as Q
    Q._apply_over_grouped_rows = lean_apply_over_grouped_rows
    sys.argv = [script] + sys.argv[2:]
    runpy.run_path(script, run_name='__main__')
    return 0


if __name__ == '__main__':
    sys.exit(main())
