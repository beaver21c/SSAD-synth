# -*- coding: utf-8 -*-
"""ssda.guard — 실행 전 코드 점검(정적 검사).

AI가 작성했거나 이용자가 고친 코드를 실행하기 전에, 개인 단위 자료에 직접 접근하거나
파일·시스템에 접근하는 표현이 있는지 검사한다. 위반이 있으면 실행하지 않는다."""
from __future__ import annotations

import ast

ALLOW_IMPORT = {'ssda', 'math', 'numpy', 'pandas', 'matplotlib'}
BAN_NAME = {'open', 'eval', 'exec', 'compile', '__import__', 'input', 'globals', 'locals', 'vars', 'dir', 'getattr', 'setattr', 'delattr',
            'breakpoint', 'exit', 'quit', 'help', 'memoryview', 'super', 'type', 'object'}
BAN_ATTR_PREFIX = ('read_', 'to_csv', 'to_parquet', 'to_pickle', 'to_excel', 'to_json', 'to_sql', 'to_hdf', 'to_feather', 'to_clipboard')
BAN_ATTR = {'savefig', 'tofile', 'save', 'load', 'loadtxt', 'savetxt', 'genfromtxt', 'fromfile', 'system', 'popen', 'environ', 'iloc', 'loc', 'head', 'tail', 'sample',
            'itertuples', 'iterrows', 'query', 'eval'}
ALLOW_SAVE = {('ssda', 'plot', 'save')}          # 그림 저장은 ssda.plot.save 만, 표 저장은 Result.save 만 허용(아래에서 처리)


def check(code):
    """위반 목록을 돌려준다(빈 목록이면 통과)."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f'문법 오류: {e.msg} (줄 {e.lineno})']
    v = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split('.')[0] not in ALLOW_IMPORT:
                    v.append(f'허용되지 않는 모듈: {a.name}')
        elif isinstance(n, ast.ImportFrom):
            if (n.module or '').split('.')[0] not in ALLOW_IMPORT:
                v.append(f'허용되지 않는 모듈: {n.module}')
        elif isinstance(n, ast.Name):
            if n.id in BAN_NAME or n.id.startswith('__'):
                v.append(f'허용되지 않는 이름: {n.id}')
        elif isinstance(n, ast.Attribute):
            a = n.attr
            if a.startswith('_'):
                v.append(f'내부 속성 접근: .{a}')
            elif a.startswith(BAN_ATTR_PREFIX):
                v.append(f'파일 읽기·쓰기 함수: .{a} (표는 결과.save(), 그림은 ssda.plot.save()로 저장)')
            elif a in BAN_ATTR:
                chain = _chain(n)
                if a == 'save' and (chain in ALLOW_SAVE or _is_result_save(n)):
                    continue
                v.append(f'허용되지 않는 함수·속성: .{a}')
        elif isinstance(n, (ast.Global, ast.Nonlocal, ast.With, ast.AsyncWith, ast.Try, ast.Lambda, ast.ClassDef)) and isinstance(n, (ast.Global, ast.Nonlocal, ast.ClassDef)):
            v.append('허용되지 않는 구문')
    return sorted(set(v))


def _chain(n):
    out = []
    while isinstance(n, ast.Attribute):
        out.append(n.attr); n = n.value
    if isinstance(n, ast.Name):
        out.append(n.id)
    return tuple(reversed(out))


def _is_result_save(n):
    """변수.save('이름') 꼴(집계 결과의 저장)인지 본다. ssda·np·pd·plt 의 save 는 제외."""
    c = _chain(n)
    return len(c) == 2 and c[0] not in ('np', 'numpy', 'pd', 'pandas', 'plt', 'matplotlib', 'fig')
