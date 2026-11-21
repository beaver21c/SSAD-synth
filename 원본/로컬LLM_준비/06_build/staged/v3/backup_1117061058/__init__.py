# -*- coding: utf-8 -*-
"""ssda — 사회보장행정데이터 분석 함수 묶음(집계 전용, 출력 통제 내장).

    import ssda
    ssda.open_data()                                   # 자료 열기(환경변수 SSDA_DATA)
    ssda.find_vars('기초연금')                           # 변수 찾기
    r = ssda.rate('bp_yn1 == 1', where='age >= 65', by='sido')
    print(r)                                           # 집계표(억제 칸 표시)
    ssda.plot.bar(r, title='시도별 기초연금 수급률')        # 그림
"""
from .core import (ControlError, QueryError, Result, THR, MAXDIM, open_data, info, groups, define, define_group, define_sum,
                   count, rate, mean, total, quantile, share, poverty_rate, find_vars, var_info, log)
from . import plot, verify  # noqa: E402

__all__ = ['open_data', 'info', 'groups', 'define', 'define_group', 'define_sum', 'count', 'rate', 'mean', 'total', 'quantile', 'share',
           'poverty_rate', 'find_vars', 'var_info', 'log', 'plot', 'Result', 'ControlError', 'QueryError', 'THR', 'MAXDIM']
__version__ = '0.3.1'      # 0.3.1(2026-11-15): 인자 오류의 사용법 안내, 구간 이름·경계 대조, 그림 이름 확장자 처리
