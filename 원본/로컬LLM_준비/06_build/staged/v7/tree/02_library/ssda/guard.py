# -*- coding: utf-8 -*-
"""ssda.guard — 실행 전 코드 점검(정적 검사). 허용 목록 방식(2026-11-17 개정).

AI가 작성했거나 이용자가 붙인 코드를 실행하기 전에 검사한다. 위반이 있으면 실행하지 않는다.

개정 사유  2026-11-17 독립 검증의 직접 공격 시험에서 금지 목록 방식의 점검이 우회됨(40건 중 19건):
           from ssda.core import _D(import 되는 이름을 보지 않음), core.os.open(허용 모듈의 속성 사슬), ssda.THR[...] = 1(통제 기준 변경) 등.
           금지할 것을 나열하는 방식은 나열하지 않은 경로를 막지 못하므로, 쓸 수 있는 것을 나열하는 방식으로 바꿈.
원칙  ① 불러올 수 있는 모듈은 ssda 와 math 뿐. ssda 에서는 공개 함수만 가져올 수 있음(내부 모듈·내부 이름 불가)
      ② 속성은 허용 목록에 있는 것만(분석 함수, 그림 함수, 집계 결과의 메서드, 집계표를 다루는 최소한의 메서드, 문자열·목록의 기본 메서드)
      ③ 속성에 값을 넣는 문장, 통제 기준에 값을 넣는 문장은 쓸 수 없음
      ④ 문자열의 format 계열은 쓸 수 없음(서식 문자열 안에서 속성에 접근할 수 있음). f-문자열은 쓸 수 있음(안의 식을 그대로 검사함)
실행기(runner)는 이와 별도로, 코드에 실제 ssda 모듈 대신 공개 함수만 담은 대리 객체를 넘긴다(이 점검이 뚫려도 내부 모듈에 닿지 않게 하는 두 번째 단계).
"""
from __future__ import annotations

import ast

ALLOW_IMPORT = {'ssda', 'ssda.plot', 'math'}
SSDA_PUBLIC = {'open_data', 'info', 'groups', 'define', 'define_group', 'define_cond', 'define_sum', 'count', 'rate', 'mean', 'total', 'quantile', 'share', 'poverty_rate',
               'find_vars', 'var_info', 'log', 'plot', 'ControlError', 'QueryError'}
PLOT_PUBLIC = {'bar', 'hbar', 'line', 'heatmap', 'map_sido', 'save'}
RESULT_ATTR = {'table', 'pivot', 'value', 'summary', 'save', 'records', 'to_text', 'label', 'unit', 'grade', 'kind'}
TABLE_ATTR = {'sort_values', 'round', 'T', 'columns', 'tolist', 'reset_index', 'set_index', 'rename', 'sum', 'max', 'min', 'idxmax', 'idxmin', 'astype', 'shape', 'fillna', 'dropna', 'to_string', 'to_dict'}
BASIC_ATTR = {'join', 'items', 'keys', 'values', 'append', 'extend', 'get', 'strip', 'replace', 'split', 'sort', 'lower', 'upper', 'startswith', 'endswith', 'index', 'copy'}
ALLOW_ATTR = SSDA_PUBLIC | PLOT_PUBLIC | RESULT_ATTR | TABLE_ATTR | BASIC_ATTR
NOARG_ONLY = {'to_string'}              # 인자를 주면 파일로 쓸 수 있는 메서드는 인자 없이만
BAN_NAME = {'open', 'eval', 'exec', 'compile', '__import__', 'input', 'globals', 'locals', 'vars', 'dir', 'getattr', 'setattr', 'delattr',
            'breakpoint', 'exit', 'quit', 'help', 'memoryview', 'super', 'type', 'object'}
HINT = '쓸 수 있는 것: ssda 의 분석 함수, ssda.plot 의 그림 함수, 집계 결과의 table·pivot·value·summary·save'


def check(code):
    """위반 목록을 돌려준다(빈 목록이면 통과)."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f'문법 오류: {e.msg} (줄 {e.lineno})']
    v = []
    mods = {}                                       # 코드 안에서 모듈을 가리키는 이름 → 'ssda' | 'ssda.plot' | 'math'
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name not in ALLOW_IMPORT:
                    v.append(f'허용되지 않는 모듈: {a.name}')
                else:
                    mods[a.asname or a.name.split('.')[0]] = a.name if a.asname else a.name.split('.')[0]
        elif isinstance(n, ast.ImportFrom):
            m = n.module or ''
            if n.level or m not in ALLOW_IMPORT:
                v.append(f'허용되지 않는 모듈: {m or "(상대 경로)"}')
                continue
            pub = SSDA_PUBLIC if m == 'ssda' else PLOT_PUBLIC if m == 'ssda.plot' else None
            for a in n.names:
                if a.name == '*' or a.name.startswith('_') or (pub is not None and a.name not in pub):
                    v.append(f'가져올 수 없는 이름: {m}.{a.name} ({HINT})')
                elif m == 'ssda' and a.name == 'plot':
                    mods[a.asname or a.name] = 'ssda.plot'
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            if n.id in BAN_NAME or n.id.startswith('__'):
                v.append(f'허용되지 않는 이름: {n.id}')
        elif isinstance(n, ast.Attribute):
            a = n.attr
            root = _root(n)
            if isinstance(n.ctx, (ast.Store, ast.Del)):
                v.append(f'속성에 값을 넣거나 지울 수 없음: .{a}')
            elif a.startswith('_'):
                v.append(f'내부 속성 접근: .{a}')
            elif mods.get(root) == 'math' and isinstance(n.value, ast.Name):
                continue                              # math.sqrt 등
            elif mods.get(root) in ('ssda', 'ssda.plot') and isinstance(n.value, ast.Name):
                continue                              # ssda.<이름>: 없는 이름은 실행 때 「없는 함수」 오류와 사용법 안내로 돌려줌(대리 객체에는 공개 함수만 있음)
            elif a not in ALLOW_ATTR:
                if a.startswith(('read_', 'to_')) or a in ('savefig', 'tofile', 'dump', 'load', 'save'):
                    v.append(f'파일 읽기·쓰기 함수: .{a} (표는 결과.save(), 그림은 ssda.plot.save()로 저장)')
                else:
                    v.append(f'허용되지 않는 함수·속성: .{a} ({HINT})')
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in NOARG_ONLY and (n.args or n.keywords):
            v.append(f'.{n.func.attr}() 에는 인자를 줄 수 없음')
        elif isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Delete)):
            targets = n.targets if isinstance(n, (ast.Assign, ast.Delete)) else [n.target]
            for t in targets:
                for s in ast.walk(t):
                    if isinstance(s, ast.Subscript) and mods.get(_root(s)):
                        v.append('분석 함수의 설정값은 바꿀 수 없음')
                    if isinstance(s, ast.Name) and isinstance(s.ctx, (ast.Store, ast.Del)) and s.id in mods and not isinstance(n, ast.Delete):
                        v.append(f'모듈 이름에는 값을 넣을 수 없음: {s.id}')
        elif isinstance(n, (ast.Global, ast.Nonlocal, ast.ClassDef, ast.AsyncFunctionDef, ast.Await, ast.Yield, ast.YieldFrom)):
            v.append('허용되지 않는 구문')
        elif isinstance(n, (ast.FunctionDef, ast.Lambda)) and getattr(n, 'decorator_list', None):
            v.append('허용되지 않는 구문(장식자)')
    return sorted(set(v))


def _root(n):
    """속성·첨자 사슬의 맨 앞 이름(이름이 아니면 None)."""
    while isinstance(n, (ast.Attribute, ast.Subscript, ast.Call)):
        n = n.value if isinstance(n, (ast.Attribute, ast.Subscript)) else n.func
    return n.id if isinstance(n, ast.Name) else None
