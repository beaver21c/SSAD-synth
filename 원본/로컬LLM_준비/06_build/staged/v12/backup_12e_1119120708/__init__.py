# -*- coding: utf-8 -*-
"""ssda — 사회보장행정데이터 분석 함수 묶음(집계 전용, 출력 통제 내장).

    import ssda
    ssda.open_data()                                   # 자료 열기(환경변수 SSDA_DATA)
    ssda.find_vars('기초연금')                           # 변수 찾기
    r = ssda.rate('bp_yn1 == 1', where='age >= 65', by='sido')
    print(r)                                           # 집계표(억제 칸 표시)
    ssda.plot.bar(r, title='시도별 기초연금 수급률')        # 그림
"""
from .core import (ControlError, QueryError, Result, THR, MAXDIM, open_data, info, groups, define, define_group, define_cond, define_sum,
                   count, rate, mean, total, quantile, share, poverty_rate, find_vars, var_info, log)
from . import plot, verify  # noqa: E402

__all__ = ['open_data', 'info', 'groups', 'define', 'define_group', 'define_cond', 'define_sum', 'count', 'rate', 'mean', 'total', 'quantile', 'share',
           'poverty_rate', 'find_vars', 'var_info', 'log', 'plot', 'Result', 'ControlError', 'QueryError', 'THR', 'MAXDIM']
__version__ = '0.7.2'      # 0.7.2(2026-11-19): 규칙 묶음 12d — 구간 이름 개수 오류에 이름에서 읽은 경계를 제시. 0.7.1(2026-11-19): 규칙 묶음 12 — 변수 찾기가 표준 분류 기준·파생 변수(inc5·poor2·eqinc 등)도 찾음(SSDA_RULESET >= 12에서만). 0.7.0(2026-11-18): 독립 검증 2차의 조치 — 여부 변수를 by 에 쓰면 해당·해당 없음 두 항목, share() 의 by(집단별 구성비), 가구주 기준 인자 오류의 안내, 산출 정의의 한글 풀이, 대화 단위 차분 점검(앞서 표시한 집계와의 차이로 소수 집단 값이 드러나는 칸의 보충 억제). 0.6.0(2026-11-17): 독립 검증의 조치 — 조건식에 항목 이름을 쓸 수 있음(sido == '충북'), 조건 집단 정의 define_cond(), 표준 분류 metro2(수도권·비수도권), 범주형 변수의 구간 정의 차단과 안내
                           # 0.5.0(2026-11-17): 통제 계층 보완 — 실행 전 점검을 허용 목록 방식으로 바꿈, 분석 코드에 공개 함수만 담은 대리 객체를 넘김, 저장 이름 처리, 식별자 변수의 통제 오류(집계 결과는 0.4.1 과 같음)
                           # 0.4.1(2026-11-16): define_group() 의 반환값을 by 에 넣으면 등록한 이름으로 해석, define_group() 의 인자 누락·조건식·여부 변수 안내, 검증 경고 「1 아님 비교」
                           # 0.4.0(2026-11-16): 조건식에서 sido 를 변수 사전의 코드값으로 해석, 문자열 값·범위 밖 순번의 오류 안내, by 에 조건식·hnum 을 쓴 경우의 안내,
                           #                    검증 경고 「대상 한정」(대상이 분자와 같은 집단), 출력 없는 실행의 안내 / 0.3.1(2026-11-15): 인자 오류의 사용법 안내, 구간 이름·경계 대조, 그림 이름 확장자 처리
