# -*- coding: utf-8 -*-
"""ssda.runner — 분석 코드의 격리 실행.

    python -m ssda.runner <코드 파일> [--timeout 60] [--mem 6]

  1) guard.check()로 정적 검사  2) 제한된 내장 함수만으로 실행  3) 표준 출력, 집계 결과(Result), 저장한 그림 경로,
     자동 점검 내역(ssda.verify: 집계 결과별 점검, 그림 점검)을 JSON 으로 출력
CPU 시간·메모리 한도를 두고, 작업 폴더는 호출자가 정한 임시 폴더(SSDA_EXPORT)로 한다."""
from __future__ import annotations

import builtins
import contextlib
import io
import json
import os
import sys
import traceback

SAFE = ['print', 'len', 'range', 'round', 'sum', 'min', 'max', 'sorted', 'enumerate', 'zip', 'list', 'dict', 'set', 'tuple', 'str', 'int', 'float', 'bool',
        'abs', 'isinstance', 'any', 'all', 'map', 'filter', 'reversed', 'format', 'repr', 'True', 'False', 'None', 'Exception', 'ValueError', 'KeyError']
ALLOW = {'ssda', 'ssda.plot', 'math'}
_FACADE = None


class _Facade:
    """분석 코드에 넘기는 대리 객체 — 공개 함수만 담는다. 실제 모듈(ssda, ssda.core)과 통제 기준(THR, MAXDIM), 자료(_D)는 여기서 닿지 않는다.
    (2026-11-17 독립 검증: from ssda.core import _D, core.os.open, ssda.THR[...] = 1 로 통제를 우회할 수 있었음)"""
    __slots__ = ('_name', '_items')

    def __init__(self, name, items):
        object.__setattr__(self, '_name', name); object.__setattr__(self, '_items', dict(items))

    def __getattr__(self, k):
        items = object.__getattribute__(self, '_items')
        if k in items:
            return items[k]
        raise AttributeError(f"module '{object.__getattribute__(self, '_name')}' has no attribute '{k}'")      # usage_hint() 가 읽는 문구(모듈과 같은 꼴)

    def __setattr__(self, k, v):
        raise AttributeError('분석 함수의 설정값은 바꿀 수 없음')

    def __delattr__(self, k):
        raise AttributeError('분석 함수의 설정값은 바꿀 수 없음')

    def __dir__(self):
        return sorted(object.__getattribute__(self, '_items'))

    def __repr__(self):
        return f"<module '{object.__getattribute__(self, '_name')}'>"


def _facade():
    global _FACADE
    if _FACADE is None:
        import ssda
        from . import guard
        pl = _Facade('ssda.plot', {k: getattr(ssda.plot, k) for k in guard.PLOT_PUBLIC})
        items = {k: getattr(ssda, k) for k in guard.SSDA_PUBLIC if k not in ('plot', 'open_data')}
        items['plot'] = pl
        items['open_data'] = lambda *a, **k: ssda.open_data()       # 자료 경로는 환경변수로만 정함(코드에서 다른 파일을 열 수 없음)
        _FACADE = _Facade('ssda', items)
    return _FACADE


def _imp(name, globals=None, locals=None, fromlist=(), level=0):
    if level or name not in ALLOW:
        raise ImportError(f'허용되지 않는 모듈: {name}')
    if name == 'math':
        import math
        return math
    f = _facade()
    return f.plot if (name == 'ssda.plot' and fromlist) else f


def usage_hint(error):
    """인자 오류·없는 함수 오류에 붙이는 사용법 한 줄. 모형이 인자 이름을 짐작해 같은 오류를 되풀이하는 것을 막는다
    (2026-11-15 실제 모형 관찰: rate(where=…, denom_where=…), define_group('age', [..], labels=[..]) 를 거듭 씀)."""
    import inspect
    import re
    import ssda
    first = (error or '').splitlines()[0] if error else ''
    m = re.match(r'TypeError: (?:[\w.]+\.)?(\w+)\(\) ', first)
    if m and not m.group(1).startswith('_'):
        for owner, prefix in ((ssda, 'ssda.'), (ssda.plot, 'ssda.plot.'), (ssda.Result, '결과.')):
            fn = getattr(owner, m.group(1), None)
            if callable(fn):
                try:
                    sig = str(inspect.signature(fn)).replace('(self, ', '(').replace('(self)', '()')
                except (TypeError, ValueError):
                    continue
                doc = (inspect.getdoc(fn) or '').splitlines()
                return f'{prefix}{m.group(1)}{sig}' + (f' — {doc[0]}' if doc else '')
    m = re.match(r"AttributeError: module '(ssda(?:\.plot)?)' has no attribute '(\w+)'", first)
    if m:
        owner = ssda.plot if m.group(1).endswith('plot') else ssda
        names = [n for n in (getattr(owner, '__all__', None) or dir(owner)) if not n.startswith('_') and callable(getattr(owner, n, None)) and not isinstance(getattr(owner, n), type)]
        return f"{m.group(1)} 에 {m.group(2)} 는 없음. 쓸 수 있는 함수: " + ', '.join(sorted(names))
    return ''


def run(code, timeout=60, mem_gb=6, limits=True):
    """limits=False 는 한 프로세스에서 여러 번 부르는 경우(학습 자료 생성기·채점기)에만 쓴다.
    이용자 질의를 처리할 때는 질의마다 새 프로세스(python -m ssda.runner)로 실행해 한도를 건다."""
    from . import guard
    out = {'ok': False, 'violations': [], 'stdout': '', 'error': '', 'results': {}, 'figures': [], 'checks': {}, 'figure_checks': []}
    out['violations'] = guard.check(code)
    if out['violations']:
        out['error'] = '실행 전 점검에서 걸림: ' + '; '.join(out['violations'])
        return out
    if limits:
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout + 5))
            resource.setrlimit(resource.RLIMIT_AS, (mem_gb << 30, mem_gb << 30))
        except Exception:                               # 한도 설정이 안 되는 환경(예: Windows)
            pass
    import ssda
    from . import core, plot, verify
    core._CREATED.clear(); plot._FIGLOG.clear()
    env = {'__builtins__': {k: getattr(builtins, k) for k in SAFE if hasattr(builtins, k)}}
    env['__builtins__']['__import__'] = _imp
    exp = os.environ.get('SSDA_EXPORT', 'export')
    before = {f: os.path.getmtime(os.path.join(exp, f)) for f in os.listdir(exp)} if os.path.isdir(exp) else {}
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(code, '<분석 코드>', 'exec'), env)       # noqa: S102 — 정적 검사를 통과한 코드만 실행
        out['ok'] = True
    except (ssda.ControlError, ssda.QueryError) as e:
        out['error'] = f'{type(e).__name__}: {e}'
    except Exception as e:                              # noqa: BLE001
        out['error'] = f'{type(e).__name__}: {e}\n' + traceback.format_exc(limit=2)
        out['hint'] = usage_hint(out['error'])
    out['stdout'] = buf.getvalue()[-6000:]
    names = {id(v): k for k, v in env.items() if isinstance(v, ssda.Result)}
    for i, v in enumerate(core._CREATED):                 # 변수에 담지 않은 결과도 기록·점검한다
        k = names.get(id(v), f'결과{i + 1}')
        out['results'][k] = {'summary': v.summary(), 'records': v.records(), 'call': v.call}
        try:
            out['checks'][k] = verify.check_result(v)
        except Exception as e:                          # noqa: BLE001 — 점검 오류가 산출을 막지 않게 함
            out['checks'][k] = [{'code': '점검 오류', 'level': '주의', 'msg': f'자동 점검을 수행하지 못함: {type(e).__name__}'}]
    out['figure_checks'] = list(plot._FIGLOG)
    if os.path.isdir(exp):
        out['figures'] = sorted(f for f in os.listdir(exp) if f.endswith('.png') and before.get(f) != os.path.getmtime(os.path.join(exp, f)))   # 새로 만들었거나 덮어쓴 그림
    return out


if __name__ == '__main__':
    code = open(sys.argv[1], encoding='utf-8').read()
    t = int(sys.argv[sys.argv.index('--timeout') + 1]) if '--timeout' in sys.argv else 60
    g = int(sys.argv[sys.argv.index('--mem') + 1]) if '--mem' in sys.argv else 6
    print(json.dumps(run(code, timeout=t, mem_gb=g), ensure_ascii=False))
