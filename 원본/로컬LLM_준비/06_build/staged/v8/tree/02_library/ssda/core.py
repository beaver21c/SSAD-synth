# -*- coding: utf-8 -*-
"""ssda.core — 사회보장행정데이터 분석 함수(집계 전용, 출력 통제 내장)

설계 원칙
  · 모든 함수는 집계 결과(Result)만 돌려준다. 개인 단위 행을 돌려주는 함수는 없다.
  · 변수 민감도 등급(가·나·다)에 따라 최소 관측 수 10·20·30건을 적용한다(R1).
    비율은 분자·분모·여집합 모두 기준 이상일 때만 표시한다.
  · 한 줄에 억제 칸이 하나뿐이면 가장 작은 칸을 보충 억제한다(R2).
  · 분위수는 5%~95% 범위만 허용하고 최솟값·최댓값은 제공하지 않는다(R4).
  · 가중 인원·금액은 유효숫자 3자리, 비율은 소수 첫째 자리로 반올림한다(R6).
  · 분류 기준(by)은 등급 가·나 3개, 등급 다 2개까지 허용한다(R8).
  · 모든 호출은 실행 기록에 남긴다.
"""
from __future__ import annotations

import ast
import json
import math
import os
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd

PKG = Path(__file__).resolve().parent
for _k, _v in (('display.width', 250), ('display.max_columns', 60), ('display.max_rows', 200), ('display.max_colwidth', 60)):
    pd.set_option(_k, _v)                                # 교차표가 출력에서 잘리면 응답이 인용할 값이 보이지 않으므로 넓게 둠
THR = {'가': 10, '나': 20, '다': 30}
MAXDIM = {'가': 3, '나': 3, '다': 2}
SIDO = ['서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종', '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주']
ST_OK, ST_SUP, ST_COMP, ST_NA = '표시', '억제', '보충 억제', '대상 없음'

_D = None                 # 개인 단위 자료(모듈 내부 전용)
_W = None                 # 개인 가중치
_HW = None                # 가구 가중치
_G = {}                   # 분류 기준: 이름 -> (코드 배열, 항목 이름 목록, 한글 이름, 등급)
_X = {}                   # 파생 수치 변수: 이름 -> (배열, 한글 이름, 단위, 등급)
_META = {}                # 변수 사전
_LOG = []                 # 실행 기록
_INFO = {}


class ControlError(Exception):
    """출력 통제 기준에 맞지 않는 요청."""


class QueryError(Exception):
    """변수명·조건식이 잘못된 요청."""


# ───────────────────────── 변수 사전 ─────────────────────────
def _load_meta():
    global _META
    if _META:
        return
    p = Path(os.environ.get('SSDA_VARIABLES', PKG / 'data' / 'variables.jsonl'))
    for line in p.read_text(encoding='utf-8').splitlines():
        if line.strip():
            r = json.loads(line)
            _META[r['var']] = r


def _grade_of(names):
    order = {'가': 0, '나': 1, '다': 2}
    g = '가'
    for n in names:
        if n in _G:
            gg = _G[n][3]
        elif n in _X:
            gg = _X[n][3]
        else:
            gg = _META.get(n, {}).get('grade', '가')
        if gg not in order:                              # 등급 「제외」(식별자 pid·hid): 분석에 쓰지 않음(2026-11-17: 처리되지 않은 KeyError 로 중단되던 것을 통제 오류로 바꿈)
            raise ControlError(f'식별자 변수({n})는 분석에 쓸 수 없음')
        if order[gg] > order[g]:
            g = gg
    return g


def sig3(x):
    if x is None or not np.isfinite(x):
        return None
    if x == 0:
        return 0.0
    k = int(math.floor(math.log10(abs(x)))) - 2
    return float(round(x / 10 ** k) * 10 ** k) if k >= 0 else round(float(x), -k)


# ───────────────────────── 자료 열기 ─────────────────────────
def open_data(path=None):
    """분석 자료를 연다. 경로는 인자, 환경변수 SSDA_DATA 순으로 정한다. 자료 요약(행 수·가중 인구)을 돌려준다."""
    global _D, _W, _HW, _INFO
    _load_meta()
    path = path or os.environ.get('SSDA_DATA')
    if not path:
        raise QueryError('자료 경로가 없음. 환경변수 SSDA_DATA 를 지정할 것')
    d = pd.read_parquet(path)
    _D = d
    _ONLY1.clear()
    _W = d['indwgt'].astype(float).values
    _HW = d['hhwgt'].astype(float).values
    age = d['age'].astype(int).values
    hh = d.groupby('hid')['p_dinc'].transform('sum').astype(float).values
    eq = hh / np.sqrt(d['hnum'].astype(float).values)
    o = np.argsort(eq); cw = np.cumsum(_W[o]); T = cw[-1]
    med = eq[o][np.searchsorted(cw, T / 2)]
    cuts = [eq[o][np.searchsorted(cw, T * q)] for q in (.2, .4, .6, .8)]
    _G.clear(); _X.clear()
    _G['sido'] = (d['sido'].astype(int).values - 1, SIDO, '시도', '가')
    _G['age6'] = (np.digitize(age, [18, 35, 50, 65, 75]), ['0~17세', '18~34세', '35~49세', '50~64세', '65~74세', '75세 이상'], '연령대(6구간)', '가')
    _G['age3'] = (np.digitize(age, [18, 65]), ['0~17세', '18~64세', '65세 이상'], '연령대(3구간)', '가')
    _G['age10'] = (np.minimum(age // 10, 8), ['0~9세', '10~19세', '20~29세', '30~39세', '40~49세', '50~59세', '60~69세', '70~79세', '80세 이상'], '연령대(10세)', '가')
    _G['sex'] = (d['gender'].astype(int).values - 1, ['남', '여'], '성', '가')
    _G['hs4'] = (np.minimum(d['hnum'].astype(int).values, 4) - 1, ['1인', '2인', '3인', '4인 이상'], '가구원수', '가')
    _G['inc5'] = (np.digitize(eq, cuts), ['1분위(하위 20%)', '2분위', '3분위', '4분위', '5분위(상위 20%)'], '소득 5분위', '나')
    _G['nhi3'] = (np.select([d['nhi_type'].isin([1, 2]).values, d['nhi_type'].isin([5, 6]).values], [0, 1], 2), ['지역가입', '직장가입', '의료급여'], '건강보험 가입 구분', '가')
    _G['poor2'] = ((eq < 0.5 * med).astype(int), ['비빈곤', '빈곤'], '빈곤 여부', '나')
    _G['metro2'] = (np.where(np.isin(d['sido'].astype(int).values, [1, 4, 9]), 0, 1), ['수도권', '비수도권'], '수도권 여부', '가')      # 수도권 = 서울·인천·경기
    _X['eqinc'] = (eq / 1e4, '균등화 가처분소득', '만원', '나')
    _X['hh_dinc'] = (hh / 1e4, '가구 가처분소득', '만원', '나')
    _X['poor'] = ((eq < 0.5 * med).astype(float), '빈곤 여부(1=빈곤)', '', '나')
    _INFO = {'행 수': int(len(d)), '가구 수': int(d['hid'].nunique()), '가중 인구': sig3(float(_W.sum())), '빈곤선(만원)': sig3(float(0.5 * med / 1e4)),
             '변수 수': int(len(d.columns))}
    _log('open_data', {}, 0, 0)
    return dict(_INFO)


def _need():
    if _D is None:
        open_data()


# ───────────────────────── 조건식 ─────────────────────────
_CMP = {ast.Eq: np.equal, ast.NotEq: np.not_equal, ast.Lt: np.less, ast.LtE: np.less_equal, ast.Gt: np.greater, ast.GtE: np.greater_equal}
_BIN = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply, ast.Div: np.divide}


def _col(name, used):
    used.add(name)
    if name in _X:
        return _X[name][0]
    if name in _G and name in _D.columns and pd.api.types.is_numeric_dtype(_D[name]):
        return _D[name].astype(float).values           # 분류 기준과 이름이 같은 변수(sido): 조건식에서는 변수 사전의 코드값으로 해석함(2026-11-16, 「sido == 1」이 부산을 가리키던 결함)
    if name in _G:
        return _G[name][0].astype(float)
    if name in _D.columns:
        s = _D[name]
        if not pd.api.types.is_numeric_dtype(s):
            raise QueryError(f'숫자형이 아닌 변수는 조건식에 쓸 수 없음: {name}')
        return s.astype(float).values
    raise QueryError(f'없는 변수: {name}. find_vars()로 변수명을 확인할 것')


def _group_only(name):
    """조건식에서 항목 순번으로 해석되는 분류 기준인지(같은 이름의 변수가 없는 것: age6, inc5, hs4, sex 등)."""
    return name in _G and not (_D is not None and name in _D.columns)


def _items(name):
    return ', '.join(f'{i}={lab}' for i, lab in enumerate(_G[name][1]))


_SIDO_ALIAS = {'서울특별시': '서울', '서울시': '서울', '부산광역시': '부산', '부산시': '부산', '대구광역시': '대구', '대구시': '대구', '인천광역시': '인천', '인천시': '인천', '광주광역시': '광주', '광주시': '광주',
               '대전광역시': '대전', '대전시': '대전', '울산광역시': '울산', '울산시': '울산', '세종특별자치시': '세종', '세종시': '세종', '경기도': '경기', '강원도': '강원', '강원특별자치도': '강원',
               '충청북도': '충북', '충청남도': '충남', '전라북도': '전북', '전북특별자치도': '전북', '전라남도': '전남', '경상북도': '경북', '경상남도': '경남', '제주도': '제주', '제주특별자치도': '제주'}


def _label_code(name, text):
    """조건식에 적힌 항목 이름(문자열)을 코드값으로 바꾼다. 예: sido == '충북' → 11, gender == '여' → 2, sex == '여' → 1(분류 기준은 항목 순번).
    (2026-11-17 독립 검증: 충북·충남 질문에 모두 경기의 코드를 쓰고, 수도권 묶음의 코드를 틀림. 코드값을 외워 쓰게 하지 않고 이름으로 쓸 수 있게 함)"""
    t = str(text).strip()
    if name == 'sido':
        t = _SIDO_ALIAS.get(t, t)
    if _group_only(name):
        labs = _G[name][1]
        hit = [i for i, lab in enumerate(labs) if t == lab] or [i for i, lab in enumerate(labs) if t and (t in lab or lab in t)]
        if len(hit) == 1:
            return float(hit[0])
        raise QueryError(f"{name}에 '{text}'에 해당하는 항목이 없거나 둘 이상임. {name}의 항목(순번): {_items(name)}" + (' 성별 변수는 gender(1 남, 2 여)' if name == 'sex' else ''))
    labels = _META.get(name, {}).get('labels') or {}
    hit = [k for k, v in labels.items() if t == v] or [k for k, v in labels.items() if t and (t in v or v in t)]
    if len(hit) == 1:
        return float(hit[0])
    codes = ', '.join(f'{k}={v}' for k, v in list(labels.items())[:20])
    raise QueryError(f"{name}에 '{text}'에 해당하는 코드값이 없거나 둘 이상임" + (f'. {name}의 코드값: {codes}' if codes else f". 코드값은 ssda.var_info('{name}')로 확인하고 숫자로 비교할 것"))


def _resolve(left, comp):
    """비교식의 오른쪽에 문자열(항목 이름)이 있으면 코드값으로 바꾼 값을 돌려준다. 문자열이 없으면 None."""
    name = left.id if isinstance(left, ast.Name) else None

    def one(c):
        if isinstance(c, ast.Constant) and isinstance(c.value, str):
            if not name:
                raise QueryError("조건식의 문자열 값은 「변수 == '항목 이름'」 또는 「변수 in ['항목 이름', …]」 꼴로만 쓸 수 있음")
            return _label_code(name, c.value)
        if (isinstance(c, ast.Name) and name and re.search(r'[가-힣]', c.id) and c.id not in _D.columns and c.id not in _G and c.id not in _X
                and (_group_only(name) or (_META.get(name, {}).get('labels') or {}))):
            return _label_code(name, c.id)                # 따옴표가 빠진 항목 이름(sido == 대구). 조건식 문자열 안의 따옴표를 잘못 겹쳐 쓴 코드에서 생김
        return None
    if isinstance(comp, (ast.List, ast.Tuple)):
        vals = [one(e) for e in comp.elts]
        if any(v is not None for v in vals):
            return [v if v is not None else float(e.value) for v, e in zip(vals, comp.elts) if v is not None or isinstance(e, ast.Constant)]
        return None
    return one(comp)


def _check_const(left, comps):
    """비교식의 상수를 점검한다: 분류 기준의 값은 항목 순번 범위 안이어야 한다(문자열 값은 _resolve 가 코드값으로 바꾼다)."""
    name = left.id if isinstance(left, ast.Name) else None
    consts = [e for c in comps for e in (c.elts if isinstance(c, (ast.List, ast.Tuple)) else [c]) if isinstance(e, ast.Constant)]
    if name and _group_only(name):
        n = len(_G[name][1])
        for c in consts:
            if isinstance(c.value, (int, float)) and not isinstance(c.value, bool) and not 0 <= c.value <= n - 1:
                raise QueryError(f'{name}의 값은 항목 순번(0~{n - 1})임({_items(name)}). {c.value:g}에 해당하는 항목이 없음' + ('. 성별 변수는 gender(1 남, 2 여)' if name == 'sex' else ''))


def _ev(node, used):
    if isinstance(node, ast.Expression):
        return _ev(node.body, used)
    if isinstance(node, ast.BoolOp):
        vals = [np.asarray(_ev(v, used), bool) for v in node.values]
        out = vals[0]
        for v in vals[1:]:
            out = (out & v) if isinstance(node.op, ast.And) else (out | v)
        return out
    if isinstance(node, ast.UnaryOp):
        v = _ev(node.operand, used)
        if isinstance(node.op, ast.Not):
            return ~np.asarray(v, bool)
        if isinstance(node.op, ast.USub):
            return -v
    if isinstance(node, ast.Compare):
        if all(isinstance(op, (ast.Eq, ast.NotEq, ast.In, ast.NotIn)) for op in node.ops):
            _check_const(node.left, node.comparators)
        if (isinstance(node.left, ast.Name) and len(node.ops) == 1 and isinstance(node.comparators[0], ast.Constant) and isinstance(node.comparators[0].value, (int, float))
                and not isinstance(node.comparators[0].value, bool) and float(node.comparators[0].value) in (0.0, 1.0) and isinstance(node.ops[0], (ast.Eq, ast.NotEq)) and _is_flag(node.left.id)):
            # 여부 변수: 해당하지 않는 사람은 결측 또는 0으로 적혀 있으므로 「!= 1」과 「== 0」은 「해당(1)이 아님」으로 계산함
            # (2026-11-17 독립 검증 2차: 0과 결측이 섞인 12월 기준 변수에 「!= 1」을 쓰면 0인 사람만 남고 결측인 사람이 빠졌음)
            on = np.nan_to_num(np.asarray(_ev(node.left, used), float), nan=0.0) == 1.0
            return on if (float(node.comparators[0].value) == 1.0) == isinstance(node.ops[0], ast.Eq) else ~on
        left = _ev(node.left, used)
        out = None
        for op, comp in zip(node.ops, node.comparators):
            rv = _resolve(node.left, comp)                # 항목 이름(문자열)은 코드값으로
            right = rv if rv is not None else _ev(comp, used)
            with np.errstate(invalid='ignore'):
                if isinstance(op, (ast.In, ast.NotIn)):
                    r = np.isin(left, np.asarray(right, float))
                    r = ~r if isinstance(op, ast.NotIn) else r
                elif type(op) in _CMP:
                    r = _CMP[type(op)](left, right)
                else:
                    raise QueryError('허용되지 않는 비교 연산')
            r = np.asarray(r, bool) & ~np.isnan(np.asarray(left, float))
            out = r if out is None else (out & r)
            left = right
        return out
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        with np.errstate(invalid='ignore', divide='ignore'):
            return _BIN[type(node.op)](_ev(node.left, used), _ev(node.right, used))
    if isinstance(node, ast.Name):
        return _col(node.id, used)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, (ast.List, ast.Tuple)):
        return [float(e.value) for e in node.elts if isinstance(e, ast.Constant)]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ('isna', 'notna') and len(node.args) == 1:
        v = np.isnan(np.asarray(_ev(node.args[0], used), float))
        return v if node.func.id == 'isna' else ~v
    raise QueryError('조건식에 허용되지 않는 표현이 있음(변수명, 숫자, 비교, and/or/not, + - * /, in [..], isna(), notna()만 사용)')


def _mask(expr, used):
    if expr is None or str(expr).strip() == '':
        return np.ones(len(_D), bool)
    try:
        tree = ast.parse(str(expr).replace('&', ' and ').replace('|', ' or '), mode='eval')
    except SyntaxError as e:
        raise QueryError(f'조건식 문법 오류: {expr}') from e
    v = _ev(tree, used)
    if not (isinstance(v, np.ndarray) and v.dtype == bool):
        raise QueryError(f'조건식은 참·거짓 식이어야 함: {expr}')
    return v


def _num(var, used):
    if var in _X:
        used.add(var)
        return _X[var][0], _X[var][1], _X[var][2]
    v = _col(var, used)
    m = _META.get(var, {})
    unit = m.get('unit', '') or ''
    if unit == '원':                                   # 금액은 만원으로 환산해 제시
        return v / 1e4, m.get('name_ko', var), '만원'
    return v, m.get('name_ko', var), unit


# ───────────────────────── 분류 기준 ─────────────────────────
class _Made(str):
    """define_group() 의 반환값. 출력하면 안내문이 보이고, by 에 넣으면 등록한 분류 기준의 이름으로 해석된다
    (2026-11-16 미세조정 모형 관찰: g = ssda.define_group(...) 다음 by=g 로 써서 「없는 분류 기준: 분류 기준 … 생성」 오류를 고치지 못함)."""
    def __new__(cls, text, name):
        o = super().__new__(cls, text)
        o.made_name = name
        return o


def _only_one(name):
    """해당하면 1, 해당하지 않으면 결측인 여부 변수인지(1 이외의 값이 없는 변수)."""
    if _D is None or name not in _D.columns or name in _G or name in _X or not pd.api.types.is_numeric_dtype(_D[name]):
        return False
    if name not in _ONLY1:
        v = _D[name].dropna().unique()
        _ONLY1[name] = bool(len(v) == 1 and float(v[0]) == 1.0)
    return _ONLY1[name]


_ONLY1 = {}
_FLAG = {}


def _is_flag(name):
    """여부 변수인지: 이름이 …_yn·…_yn1·…_yn2 꼴이고 값이 1(해당)뿐이거나 0·1뿐인 변수. 해당하지 않는 사람은 결측 또는 0으로 기록됨."""
    if _D is None or name not in _D.columns or name in _G or name in _X or not re.search(r'_yn\d?$', name) or not pd.api.types.is_numeric_dtype(_D[name]):
        return False
    if name not in _FLAG:
        v = {float(x) for x in _D[name].dropna().unique()}
        _FLAG[name] = bool(v) and v <= {0.0, 1.0} and 1.0 in v
    return _FLAG[name]


def _group(name, used):
    used.add(name)
    if name in _G:
        return _G[name][0], _G[name][1], _G[name][2]
    if name == 'hnum':                                     # 가구원수의 표준 분류는 hs4 (2026-11-16 실제 모형 관찰: 「가구원수별」「가구원수 구성비」에 hnum 을 써서 표준 분류와 다른 표를 냄)
        raise QueryError("가구원수별 분류와 가구원수 구성비에는 표준 분류 기준 hs4(1인 / 2인 / 3인 / 4인 이상)를 쓸 것. 예: by='hs4', ssda.share('hs4', …). "
                         "hnum 은 조건식에 쓰는 변수임(예: 1인 가구는 where='hnum == 1'). 다른 구간이 필요하면 ssda.define_group()으로 만들 것")
    if name in _D.columns:
        m = _META.get(name, {})
        s = _D[name]
        vals = np.sort(s.dropna().unique())
        if _is_flag(name):                                 # 여부 변수: 해당(1) / 해당 없음(결측·0)의 두 항목으로 나눔
            # 2026-11-17 독립 검증 2차: by='bp_yn1' 로 「받은 집단과 받지 않은 집단」을 비교하려던 코드가 받은 집단 한 칸만 내고 받지 않은 집단(결측)은 표에서 빠짐
            lab = m.get('labels') or {}
            on = (s == 1).fillna(False).to_numpy(dtype=bool)
            return np.where(on, 0, 1), [lab.get('1', '해당'), lab.get('0', '해당 없음')], m.get('name_ko', name)
        if len(vals) > 15:
            raise QueryError(f'{name}은 범주가 15개를 넘어 분류 기준으로 쓸 수 없음. define_group()으로 구간을 만들 것')
        codes = np.full(len(s), -1)
        labs = []
        lab = m.get('labels') or {}
        for i, v in enumerate(vals):
            codes[(s == v).fillna(False).to_numpy(dtype=bool)] = i     # 결측 허용 정수형(Int64)도 처리
            key = str(int(v)) if float(v).is_integer() else str(v)
            labs.append(lab.get(key, f'코드 {key}'))
        return codes, labs, m.get('name_ko', name)
    if not str(name).isidentifier():                       # by 에 조건식을 넣은 경우(2026-11-16 실제 모형 관찰: by='bp_yn1 == 1' 을 고치지 못하고 4회 반복함)
        t = str(name).strip()
        m1 = re.fullmatch(r'([A-Za-z_]\w*)\s*==\s*1', t)
        ex = (f"해당 집단은 where='… and {m1.group(1)} == 1', 해당하지 않는 집단은 where='… and not ({m1.group(1)} == 1)'" if m1
              else f"한 집단은 where='… and ({t})', 나머지 집단은 where='… and not ({t})'")
        raise QueryError(f"by 에는 분류 기준의 이름만 쓸 수 있음(조건식 「{t}」은 쓸 수 없음). 조건으로 나눈 집단은 ssda.define_cond('g', {{'해당': '{t}'}}, other='그 밖') 으로 분류 기준을 만들어 by='g' 로 쓰거나, "
                         f'by 를 쓰지 않고 where 에 조건을 넣어 집단마다 따로 산출할 것: {ex}. 결과는 각각 print 할 것')
    raise QueryError(f'없는 분류 기준: {name}. groups()로 쓸 수 있는 기준을 확인할 것')


def groups():
    """쓸 수 있는 표준 분류 기준의 표(이름, 한글 이름, 항목)."""
    _need()
    return pd.DataFrame([{'이름': k, '한글 이름': v[2], '항목': ' / '.join(v[1]), '등급': v[3]} for k, v in _G.items()])


def _fmt_num(x):
    return str(int(x)) if float(x).is_integer() else str(x)


def _intervals(bins):
    """bins 가 만드는 구간의 설명(경계 수 + 1개). 예: [65, 75] → ['65 미만', '65 이상 75 미만', '75 이상']"""
    b = [_fmt_num(x) for x in bins]
    return [f'{b[0]} 미만'] + [f'{b[i - 1]} 이상 {b[i]} 미만' for i in range(1, len(b))] + [f'{b[-1]} 이상']


def _check_labels(bins, labels):
    """항목 이름에 적힌 수가 그 구간의 경계와 맞는지 본다(이름이 한 칸씩 밀린 분류 기준을 막는다).
    2026-11-15 실제 모형 관찰: bins=[65, 70, 75, 80] 에 ['65~69세', …, '85세 이상'] 을 주어 65~69세의 값이 「70~74세」로 표시됨.
    이름의 수가 경계와 같은 단위일 때만 본다(금액처럼 「1,200만원」「1억」으로 줄여 적은 이름은 보지 않음)."""
    bins = [float(x) for x in bins]
    if any(re.search(r'[만억천백,%]', str(l).replace('미만', '')) for l in labels):      # 「미만」의 '만'은 단위가 아님
        return
    nums = [[float(x) for x in re.findall(r'\d+(?:\.\d+)?', str(l))] for l in labels]
    step = max([b2 - b1 for b1, b2 in zip(bins, bins[1:])] or [max(abs(bins[0]), 1.0)])
    if not all(bins[0] - step <= x <= bins[-1] + step for ns in nums for x in ns):
        return
    desc = _intervals(bins)
    for i, (lab, ns) in enumerate(zip(labels, nums)):
        lo, hi = (bins[i - 1] if i else None), (bins[i] if i < len(bins) else None)
        t, ok = str(lab), True
        if len(ns) == 2:                                   # 「65~69세」「65세 이상 75세 미만」
            ok = (lo is None or lo == ns[0]) and (hi is None or hi in (ns[1], ns[1] + 1))
        elif len(ns) == 1 and '미만' in t:
            ok = hi == ns[0]
        elif len(ns) == 1 and '이하' in t:
            ok = hi in (ns[0], ns[0] + 1)
        elif len(ns) == 1 and '이상' in t:
            ok = lo == ns[0]
        elif len(ns) == 1 and '초과' in t:
            ok = lo in (ns[0], ns[0] + 1)
        elif len(ns) == 1:                                 # 「1인」「2인」
            ok = lo == ns[0] if lo is not None else hi in (ns[0], ns[0] + 1)
        if not ok:
            sug = ''                                       # 이름에 맞는 경계(둘째 구간부터 각 구간이 시작하는 값). 이름이 질문이 정한 구간이면 이름이 아니라 경계를 고쳐야 함
            if len(labels) == len(bins) + 1 and all(ns for ns in nums[1:]) and not any(('미만' in str(l) or '이하' in str(l)) and len(ns) == 1 for l, ns in zip(labels[1:], nums[1:])):
                want = [ns[0] + (1 if '초과' in str(l) and len(ns) == 1 else 0) for l, ns in zip(labels[1:], nums[1:])]
                if want != bins and all(a < b for a, b in zip(want, want[1:])):
                    sug = (f'이 이름들이 질문이 정한 구간이면 이름을 바꾸지 말고 경계를 bins=[{", ".join(_fmt_num(x) for x in want)}] 로 고칠 것(경계는 둘째 구간부터 각 구간이 시작하는 값). 경계가 맞는 경우에만 ')
            raise QueryError(f'항목 이름 「{lab}」이 구간과 맞지 않음. bins=[{', '.join(_fmt_num(x) for x in bins)}] 이면 {i + 1}번째 구간은 「{desc[i]}」임. '
                             f'구간은 차례로 ' + ' / '.join(desc) + f' 의 {len(desc)}개임. ' + sug + '이름을 이 순서에 맞춰 줄 것(대상 집단 밖의 구간에도 이름을 주고 bins 는 줄이지 않음)')


_BY_COND = ("조건으로 나눈 집단(받는 사람과 받지 않는 사람, 지역 묶음, 등급 묶음 등)은 ssda.define_cond('이름', {'받는 사람': 'X == 1'}, other='받지 않는 사람') 으로 분류 기준을 만들어 by 에 쓰거나, "
            "집단마다 where 에 조건을 넣어 따로 산출할 것(해당 집단은 where='… and X == 1', 해당하지 않는 집단은 where='… and not (X == 1)')")


def define_group(name, var=None, bins=None, labels=None):
    """수치 변수를 구간으로 나눈 분류 기준을 만든다. bins=[경계값...], labels=[항목 이름...](경계 수 + 1개)."""
    _need()
    if not isinstance(name, str) or not isinstance(var, str) or bins is None or labels is None or isinstance(bins, str) or isinstance(labels, str):
        raise QueryError("define_group(이름, 변수, 경계값 목록, 항목 이름 목록)의 네 인자가 모두 필요함. "
                         "예: ssda.define_group('age_old', 'age', [65, 75], ['65세 미만', '65~74세', '75세 이상']) 다음 by='age_old'. " + _BY_COND)
    if not var.isidentifier():
        raise QueryError(f"define_group 의 둘째 인자는 변수 이름임(조건식 「{var}」은 쓸 수 없음). " + _BY_COND)
    if _only_one(var):
        raise QueryError(f"{var}은 해당하면 1, 해당하지 않으면 결측인 여부 변수여서 구간으로 나눌 수 없음. " + _BY_COND.replace('X', var))
    if var in _D.columns and (_META.get(var, {}).get('labels') or {}):
        labs = _META[var]['labels']
        raise QueryError(f"{var}은 코드값으로 된 범주형 변수여서 구간(bins)으로 나눌 수 없음. 코드값을 묶으려면 ssda.define_cond()를 쓸 것. "
                         f"예: ssda.define_cond('{name}', {{'묶음 이름': \"{var} in [{', '.join(list(labs)[:2])}]\"}}, other='그 밖') 다음 by='{name}'. "
                         f"{var}의 코드값: " + ', '.join(f'{k}={v}' for k, v in list(labs.items())[:20]) + (". 수도권·비수도권은 표준 분류 기준 metro2" if var == 'sido' else ''))
    used = set()
    v, lab, _ = _num(var, used) if var in _X else (_col(var, used), _META.get(var, {}).get('name_ko', var), '')
    if len(labels) != len(bins) + 1:
        raise QueryError(f'labels 개수({len(labels)})는 bins 개수({len(bins)}) + 1 이어야 함. bins={list(bins)} 이면 구간은 ' + ' / '.join(_intervals(bins))
                         + f' 의 {len(bins) + 1}개이고 구간마다 이름이 하나씩 필요함. 대상 집단 밖의 구간(예: 맨 앞 구간)에도 이름을 주고 bins 는 줄이지 않음')
    _check_labels(bins, labels)
    codes = np.digitize(v, bins)
    codes = np.where(np.isnan(v), -1, codes)
    _G[name] = (codes, list(labels), f'{lab} 구간', _grade_of(used))
    return _Made(f'분류 기준 {name} 생성: ' + ' / '.join(labels), name)


def define_cond(name, groups=None, other=None):
    """조건으로 나눈 분류 기준을 만든다. groups={항목 이름: 조건식, …}. 어느 조건에도 들지 않는 사람은 other 이름의 항목으로 묶고, other 를 주지 않으면 표에서 빠진다.
    예: ssda.define_cond('region2', {'수도권': "sido in ['서울', '인천', '경기']"}, other='비수도권') 다음 by='region2'
        ssda.define_cond('grade4', {'1·2등급': 'ltcare_grade in [1, 2]', '3등급': 'ltcare_grade == 3', '4등급': 'ltcare_grade == 4', '5등급': 'ltcare_grade == 5'})
        ssda.define_cond('bp', {'수급자': 'bp_yn1 == 1'}, other='비수급자')
    (2026-11-17 독립 검증: 지역 묶음·등급 묶음을 구간 정의(define_group)로 만들다 틀린 사례가 많았음. 코드값의 묶음과 조건 집단을 한 표로 낼 수 있게 함)"""
    _need()
    if not isinstance(name, str) or not name.isidentifier() or not isinstance(groups, dict) or not groups:
        raise QueryError("define_cond(이름, {항목 이름: 조건식, …}, other=None) 꼴로 쓸 것. "
                         "예: ssda.define_cond('region2', {'수도권': \"sido in ['서울', '인천', '경기']\"}, other='비수도권') 다음 by='region2'")
    if name in _D.columns:
        raise QueryError(f'{name}은 자료의 변수 이름임. 분류 기준에는 다른 이름을 쓸 것')
    used = set()
    codes = np.full(len(_D), -1)
    labels = []
    for lab, cond in groups.items():
        if not isinstance(cond, str):
            raise QueryError(f"define_cond 의 조건은 조건식 문자열이어야 함(항목 「{lab}」). 예: {{'1·2등급': 'ltcare_grade in [1, 2]'}}")
        m = _mask(cond, used)
        dup = m & (codes >= 0)
        if dup.any():
            raise QueryError(f'조건이 겹침: 「{labels[int(codes[dup][0])]}」과 「{lab}」에 함께 드는 사람이 있음. 조건이 서로 겹치지 않게 쓸 것')
        codes[m] = len(labels)
        labels.append(str(lab))
    if other is not None:
        codes[codes < 0] = len(labels)
        labels.append(str(other))
    _G[name] = (codes, labels, '집단', _grade_of(used))
    return _Made(f'분류 기준 {name} 생성: ' + ' / '.join(labels), name)


def define(name, expr, label=None, unit=''):
    """수식으로 파생 변수를 만든다. 예: define('pub_share', 'p_pubinc / p_dinc')"""
    _need()
    used = set()
    v = _ev(ast.parse(str(expr), mode='eval'), used)
    v = np.asarray(v, float)
    _X[name] = (v, label or name, unit, _grade_of(used))
    return f'파생 변수 {name} 생성({label or expr})'


def define_sum(name, vars, label=None):
    """여러 금액·횟수 변수를 더한 파생 변수를 만든다. 예: define_sum('fee_all', ['nhi_out_fee', 'nhi_in_fee'], '외래·입원 본인부담금')
    값이 없는 항목은 0으로 보고 더하며, 모든 항목에 값이 없는 사람은 값이 없는 것으로 둔다(평균·분위수에서 제외됨)."""
    _need()
    vars = [vars] if isinstance(vars, str) else list(vars)
    if len(vars) < 2:
        raise QueryError('define_sum()에는 변수를 2개 이상 넣을 것')
    used = set()
    arrs, units = [], set()
    for v in vars:
        x, _, u = _num(v, used)
        arrs.append(np.asarray(x, float)); units.add(u)
    if len(units) > 1:
        raise QueryError(f'단위가 다른 변수는 더할 수 없음: {sorted(units)}')
    a = np.vstack(arrs)
    allnan = np.isnan(a).all(axis=0)
    s = np.nansum(a, axis=0); s[allnan] = np.nan
    _X[name] = (s, label or ' + '.join(vars), units.pop(), _grade_of(used))
    return f"파생 변수 {name} 생성({label or ' + '.join(vars)})"


# ───────────────────────── 집계 공통 ─────────────────────────
def _complement(st, key, shape):
    a = st.reshape(shape); n = key.reshape(shape).astype(float)
    for _ in range(12):
        ch = False
        for ax in range(a.ndim):
            am = np.moveaxis(a, ax, -1); nm = np.moveaxis(n, ax, -1)
            f = am.reshape(-1, am.shape[-1]); g = nm.reshape(-1, nm.shape[-1])
            for r in range(f.shape[0]):
                sup = (f[r] == 1) | (f[r] == 2); ok = f[r] == 0
                if sup.sum() == 1 and ok.sum() >= 1:
                    f[r, np.where(ok)[0][np.argmin(g[r][ok])]] = 2; ch = True
        if not ch:
            break
    return a.reshape(-1)


def _prep(by, where, extra_used, unit):
    _need()
    used = set(extra_used)
    by = [by] if isinstance(by, str) else list(by or [])
    by = [b.made_name if isinstance(b, _Made) else b for b in by]       # define_group() 의 반환값 → 등록한 이름
    base = _mask(where, used)
    w = _W
    if unit in ('가구', 'hh', 'household'):
        base = base & (_D['head'].values == 1)
        w = _HW
    gs = [_group(b, used) for b in by]
    grade = _grade_of(used)
    if len(by) > MAXDIM[grade]:
        raise ControlError(f'등급 {grade} 자료는 분류 기준을 {MAXDIM[grade]}개까지만 쓸 수 있음(요청 {len(by)}개). 분류 기준을 줄일 것')
    idx = np.zeros(len(_D), np.int64); size = 1; valid = np.ones(len(_D), bool)
    for codes, labs, _ in gs:
        valid &= codes >= 0
        idx = idx * len(labs) + np.maximum(codes, 0); size *= len(labs)
    global _POP
    _POP = (base & valid, idx, size)                    # 차분 점검(_audit)에 쓰는 대상(결측 제외 전의 조건·분류 기준 대상)
    return by, gs, base & valid, w, idx, size, tuple(len(g[1]) for g in gs), grade, used


def _frame(by, gs, shape):
    if not by:
        return pd.DataFrame(index=[0])
    grid = np.indices(shape).reshape(len(shape), -1)
    return pd.DataFrame({gs[i][2]: [gs[i][1][j] for j in grid[i]] for i in range(len(by))})


def _status(st):
    return np.array([ST_OK, ST_SUP, ST_COMP, ST_NA], dtype=object)[st]


def safe_name(name):
    """저장 이름에서 폴더 경로를 떼고 글자·숫자·한글·공백·일부 기호만 남긴다(반출 신청 폴더 밖에 쓰지 못하게 함)."""
    import re as _re
    n = _re.sub(r'[^0-9A-Za-z가-힣 _.()\[\]~·,%+-]', '_', str(name).replace('\\', '/').split('/')[-1]).strip(' .')
    return n[:120] or '결과'


class Result:
    """집계 결과. 개인 단위 값은 담지 않는다."""

    def __init__(self, df, label, unit, grade, kind, by_labels):
        self._df = df; self.label = label; self.unit = unit; self.grade = grade; self.kind = kind; self.by = by_labels
        self.call = None                                   # 산출 조건(함수 이름·인자) — 자동 검증(ssda.verify)과 기록에 쓴다
        self.diff_blocked = 0                              # 대화 단위 차분 점검으로 가린 칸 수

    def table(self):
        """표시용 표(억제 칸의 값은 비어 있음)."""
        return self._df.copy()

    def pivot(self):
        """분류 기준이 2개일 때 행×열 표."""
        if len(self.by) != 2:
            raise QueryError('pivot()은 분류 기준이 2개일 때만 사용')
        return self._df.pivot(index=self.by[0], columns=self.by[1], values='값').reindex(index=pd.unique(self._df[self.by[0]]), columns=pd.unique(self._df[self.by[1]]))

    def value(self, **sel):
        """한 칸의 값. 예: res.value(시도='서울'). 억제 칸은 None."""
        d = self._df
        for k, v in sel.items():
            d = d[d[k] == v]
        if len(d) != 1:
            raise QueryError('조건에 맞는 칸이 하나가 아님')
        x = d['값'].iloc[0]
        return None if pd.isna(x) else float(x)

    def records(self):
        return json.loads(self._df.to_json(orient='records', force_ascii=False))

    def summary(self):
        n = len(self._df); s = int((self._df['상태'] != ST_OK).sum())
        out = {'지표': self.label, '단위': self.unit, '등급': self.grade, '최소 관측 수': THR[self.grade], '칸 수': n, '표시하지 않는 칸': s}
        if self.diff_blocked:
            out['차분 방지로 가린 칸'] = self.diff_blocked
        return out

    def to_text(self, max_rows=60):
        d = self._df.copy()
        d['값'] = [('' if pd.isna(v) else (f'{v:,.1f}' if self.unit in ('%', '일') else f'{v:,.0f}' if abs(v) >= 100 else f'{v:,.2f}')) for v in d['값']]
        d.loc[d['상태'] != ST_OK, '값'] = d.loc[d['상태'] != ST_OK, '상태']
        for c in d.columns:                                   # 인원·합계 열은 천 단위 구분 기호로 표시
            if c not in self.by and c not in ('값', '상태'):
                d[c] = ['' if pd.isna(v) else f'{v:,.0f}' for v in d[c]]
        head = f'[{self.label}] 단위: {self.unit} · 등급 {self.grade}(최소 {THR[self.grade]}건)'
        body = d.drop(columns=['상태']).head(max_rows).to_string(index=False)
        return head + '\n' + body + ('' if len(d) <= max_rows else f'\n… 외 {len(d) - max_rows}행') + (('\n※ ' + DIFF_NOTE.format(k=self.diff_blocked)) if self.diff_blocked else '')

    def __repr__(self):
        return self.to_text()

    def save(self, name):
        """반출 신청용으로 결과 표를 저장한다(통제를 거친 집계값만 저장됨)."""
        out = Path(os.environ.get('SSDA_EXPORT', 'export')); out.mkdir(parents=True, exist_ok=True)
        name = safe_name(name)
        p = out / f'{name}.csv'
        self._df.to_csv(p, index=False, encoding='utf-8-sig')
        (out / f'{name}.meta.json').write_text(json.dumps(self.summary(), ensure_ascii=False), encoding='utf-8')
        _log('save', {'name': name}, len(self._df), 0)
        return str(p)


_QUIET = False            # 자동 검증이 내부적으로 다시 계산할 때는 호출 기록을 남기지 않는다
_SESSION = None           # 대화 단위 차분 점검의 기록: 이 대화에서 이미 표시한 칸의 대상(행 집합). None 이면 점검하지 않음(실행기가 켠다)
_POP = None               # 직전 _prep 의 대상 — (행 선택, 칸 번호, 칸 수)
DIFF_NOTE = ('차분 방지: 이 대화에서 앞서 표시한 집계와 빼거나 더하면 최소 관측 수에 못 미치는 소수 집단의 값이 드러나는 칸 {k}개를 표시하지 않음(보충 억제). '
             '조건을 바꿔 같은 값을 다시 구하지 말 것. 더 넓은 구간·집단으로 묶은 집계는 가능함')


def session_start(layers=None):
    """대화 단위 차분 점검을 켠다(실행기가 부른다). layers: 같은 대화의 앞선 실행에서 표시한 칸의 기록(없으면 새 대화)."""
    global _SESSION
    _SESSION = layers if layers is not None else []
    return _SESSION


def session_stop():
    global _SESSION
    _SESSION = None


def _layer(m, idx, size, st):
    """표시 칸(st == 0)의 대상: 행마다 칸 번호(표시하지 않는 칸·대상 밖은 -1), 칸별 관측 수."""
    lab = np.where(m, idx, -1)
    show = np.zeros(size + 1, bool); show[:size] = st == 0
    lab = np.where(show[lab], lab, -1)
    return lab, np.bincount(lab[lab >= 0], minlength=size)


def _audit(st, thr, masks, idx, size):
    """대화 단위 차분 점검(2026-11-18, 독립 검증 2차: 앞서 표시한 「65세 이상」과 「65~74세」의 차이로 가려진 「75세 이상」 값이 드러난 사례 등 2건).
    이번에 표시하려는 칸의 대상이 같은 대화에서 이미 표시한 칸(또는 그 합)의 대상과 포함 관계이고, 그 차이가 1건 이상 최소 관측 수 미만이면
    두 값을 빼서 소수 집단의 값을 알 수 있으므로 이번 칸을 표시하지 않는다. 대상은 조건(where)·분류 기준으로 정한 행 집합으로 비교한다(값이 없는 행의 제외는 보지 않음).
    → 가린 칸 수. st 를 그 자리에서 고친다(가린 칸은 2 = 보충 억제)."""
    if _SESSION is None or _QUIET or not _SESSION:
        return 0
    blocked = 0
    for _ in range(6):                                      # 칸을 가리면 합이 달라지므로 더 가릴 칸이 없을 때까지 되풀이
        hit = np.zeros(size, bool)
        for m in masks:
            lab, na = _layer(m, idx, size, st)
            if not na.any():
                continue
            for old in _SESSION:
                ol, on = old['lab'], old['n']; K = len(on); T = max(thr, old['thr'])
                both = (lab >= 0) & (ol >= 0)
                if not both.any():
                    continue
                C = np.bincount(lab[both] * K + ol[both], minlength=size * K).reshape(size, K)      # 새 칸 × 옛 칸의 겹치는 관측 수
                A, O = na[:, None], on[None, :]
                inner = (C == O) & (O > 0)                      # 새 칸 안에 온전히 든 옛 칸
                r1 = na - (inner * O).sum(1)
                hit |= inner.any(1) & (r1 > 0) & (r1 < T)       # 새 칸 − 옛 칸들의 합 = 소수 집단
                over = C > 0
                e1 = (over * O).sum(1) - na
                hit |= (na > 0) & (C.sum(1) == na) & (e1 > 0) & (e1 < T)   # 옛 칸들의 합 − 새 칸 = 소수 집단
                ain = (C == A) & (A > 0)                        # 옛 칸 안에 온전히 든 새 칸
                r2 = on - (ain * A).sum(0)
                for b in np.where(ain.any(0) & (r2 > 0) & (r2 < T))[0]:     # 옛 칸 − 새 칸들의 합 = 소수 집단 → 새 칸 가운데 가장 작은 칸을 더 가림
                    c = np.where(ain[:, b])[0]; hit[c[np.argmin(na[c])]] = True
                e2 = (over * A).sum(0) - on
                for b in np.where((on > 0) & (C.sum(0) == on) & (e2 > 0) & (e2 < T))[0]:   # 새 칸들의 합 − 옛 칸 = 소수 집단
                    c = np.where(over[:, b] & ~ain[:, b])[0]
                    if len(c):
                        hit[c[np.argmin(na[c])]] = True
        hit &= st == 0
        if not hit.any():
            break
        st[hit] = 2; blocked += int(hit.sum())
    return blocked


def _register(st, thr, masks, idx, size):
    if _SESSION is None or _QUIET:
        return
    for m in masks:
        lab, na = _layer(m, idx, size, st)
        if na.any():
            _SESSION.append({'lab': lab.astype(np.int32), 'n': na.astype(np.int64), 'thr': int(thr)})
_CREATED = []             # 이번 실행에서 만들어진 집계 결과(실행기가 점검·기록에 쓴다)


def _log(fn, args, cells, sup):
    if _QUIET:
        return
    rec = {'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'fn': fn, 'args': {k: (v if isinstance(v, (str, int, float, list, type(None))) else str(v)) for k, v in args.items()}, 'cells': cells, 'suppressed': sup}
    _LOG.append(rec)
    p = os.environ.get('SSDA_LOG')
    if p:
        with open(p, 'a', encoding='utf-8') as fp:
            fp.write(json.dumps(rec, ensure_ascii=False) + '\n')


def log():
    """이번 실행의 호출 기록."""
    return list(_LOG)


def _finish(fn, args, by, gs, shape, st, val, extra, label, unit, grade, kind, key, num=None):
    multi = bool(shape) and int(np.prod(shape)) > 1
    st = np.array(st, np.int8)
    if multi:
        st = _complement(st, key, shape)
    nblock = 0
    if _SESSION is not None and not _QUIET and _POP is not None:
        m0, idx0, size0 = _POP
        masks = [m0] if num is None else [m0, m0 & num, m0 & ~num]      # 비율: 대상·해당·해당 아님의 인원이 모두 드러남
        for _ in range(4):
            k = _audit(st, THR[grade], masks, idx0, size0)
            nblock += k
            if not k or not multi:
                break
            st = _complement(st, key, shape)
        _register(st, THR[grade], masks, idx0, size0)
    df = _frame(by, gs, shape)
    v = np.array(val, float); v[st != 0] = np.nan
    df['값'] = v
    for k, arr in extra.items():
        a = np.array(arr, float); a[st != 0] = np.nan
        df[k] = a
    df['상태'] = _status(st)
    _log(fn, args, len(df), int((st != 0).sum()))
    res = Result(df.reset_index(drop=True), label, unit, grade, kind, [g[2] for g in gs])
    res.call = {'fn': fn, 'args': dict(args)}
    res.diff_blocked = nblock
    if not _QUIET:
        _CREATED.append(res)
    return res


# ───────────────────────── 집계 함수 ─────────────────────────
def count(cond=None, by=None, unit='개인', label=None, where=None):
    """조건에 맞는 가중 인원(또는 가구 수). 유효숫자 3자리. 조건은 where='…'(또는 첫 인자)로 주며, 첫 인자와 where 를 함께 주면 두 조건을 모두 만족하는 대상을 센다.
    (2026-11-17 독립 검증 2차: 비율 함수처럼 count('조건', where='대상')으로 써서 인자 오류가 난 사례가 여러 번 있었음)"""
    if cond is not None and where is not None:
        where = f'({cond}) and ({where})'
    elif where is None:
        where = cond
    by, gs, m, w, idx, size, shape, grade, used = _prep(by, where, [], unit)
    n = np.bincount(idx[m], minlength=size); s = np.bincount(idx[m], weights=w[m], minlength=size)
    st = np.where(n == 0, 3, np.where(n < THR[grade], 1, 0)).astype(np.int8)
    val = [sig3(x) for x in s]
    return _finish('count', {'where': where, 'by': by, 'unit': unit}, by, gs, shape, st, val, {}, label or ('가구 수' if unit != '개인' else '인원') + (f'({where})' if where else ''), '가구' if unit != '개인' else '명', grade, 'count', n)


def rate(num, where=None, by=None, unit='개인', label=None):
    """비율(%) = 조건 num 에 해당하는 가중 인원 ÷ where 에 해당하는 가중 인원 × 100."""
    used0 = set(); _need(); nm = _mask(num, used0)
    by, gs, m, w, idx, size, shape, grade, used = _prep(by, where, used0, unit)
    thr = THR[grade]
    nd = np.bincount(idx[m], minlength=size); wd = np.bincount(idx[m], weights=w[m], minlength=size)
    mm = m & nm
    nn = np.bincount(idx[mm], minlength=size); wn = np.bincount(idx[mm], weights=w[mm], minlength=size)
    st = np.zeros(size, np.int8); st[nd == 0] = 3
    st[(st == 0) & ((nd < thr) | (nn < thr) | ((nd - nn) < thr))] = 1
    val = np.round(np.divide(100 * wn, wd, out=np.zeros(size), where=wd > 0), 1)
    return _finish('rate', {'num': num, 'where': where, 'by': by, 'unit': unit}, by, gs, shape, st, val,
                   {'해당 인원': [sig3(x) for x in wn], '대상 인원': [sig3(x) for x in wd]}, label or f'비율: {num}' + (f' / 대상: {where}' if where else ''), '%', grade, 'rate', nn, num=nm)


def mean(var, where=None, by=None, unit='개인', label=None):
    """가중 평균. 값이 없는(결측) 행은 제외한다. 금액(원)은 만원으로 환산한다."""
    used0 = set(); _need(); v, lab, u = _num(var, used0)
    by, gs, m, w, idx, size, shape, grade, used = _prep(by, where, used0, unit)
    m = m & ~np.isnan(v)
    n = np.bincount(idx[m], minlength=size); sw = np.bincount(idx[m], weights=w[m], minlength=size); sx = np.bincount(idx[m], weights=(w * np.nan_to_num(v))[m], minlength=size)
    st = np.where(n == 0, 3, np.where(n < THR[grade], 1, 0)).astype(np.int8)
    val = [sig3(a / b) if b > 0 else None for a, b in zip(sx, sw)]
    return _finish('mean', {'var': var, 'where': where, 'by': by, 'unit': unit}, by, gs, shape, st, [np.nan if x is None else x for x in val],
                   {'대상 인원': [sig3(x) for x in sw]}, label or f'{lab} 평균' + (f'({where})' if where else ''), u, grade, 'mean', n)


def total(var, where=None, by=None, unit='개인', label=None):
    """가중 합계. 금액(원)은 만원으로 환산한다."""
    used0 = set(); _need(); v, lab, u = _num(var, used0)
    by, gs, m, w, idx, size, shape, grade, used = _prep(by, where, used0, unit)
    m = m & ~np.isnan(v)
    n = np.bincount(idx[m], minlength=size); sx = np.bincount(idx[m], weights=(w * np.nan_to_num(v))[m], minlength=size)
    st = np.where(n == 0, 3, np.where(n < THR[grade], 1, 0)).astype(np.int8)
    return _finish('total', {'var': var, 'where': where, 'by': by, 'unit': unit}, by, gs, shape, st, [sig3(x) for x in sx], {}, label or f'{lab} 합계' + (f'({where})' if where else ''), u, grade, 'total', n)


def quantile(var, q=0.5, where=None, by=None, unit='개인', label=None):
    """가중 분위수(q는 0.05~0.95). 중위수는 q=0.5."""
    if not (0.05 <= float(q) <= 0.95):
        raise ControlError('분위수는 0.05~0.95 범위만 제공함(최솟값·최댓값과 극단 분위는 제공하지 않음)')
    used0 = set(); _need(); v, lab, u = _num(var, used0)
    by, gs, m, w, idx, size, shape, grade, used = _prep(by, where, used0, unit)
    m = m & ~np.isnan(v); thr = THR[grade]
    n = np.bincount(idx[m], minlength=size)
    val = np.full(size, np.nan); st = np.where(n == 0, 3, 0).astype(np.int8)
    for c in np.unique(idx[m]):
        mk = m & (idx == c); x = v[mk]; ww = w[mk]
        tail = min(q, 1 - q) * len(x)
        if len(x) < thr or tail < thr:
            st[c] = 1; continue
        o = np.argsort(x); cw = np.cumsum(ww[o])
        val[c] = sig3(float(x[o][min(np.searchsorted(cw, cw[-1] * q), len(x) - 1)]))
    return _finish('quantile', {'var': var, 'q': q, 'where': where, 'by': by, 'unit': unit}, by, gs, shape, st, val, {}, label or f'{lab} {int(round(q * 100))}% 분위수' + (f'({where})' if where else ''), u, grade, 'quantile', n)


def share(var, where=None, by=None, unit='개인', label=None):
    """범주형 변수(또는 분류 기준)의 구성비(%). by 를 주면 집단마다 그 집단 안에서의 구성비를 낸다(집단별 합 100%). 예: ssda.share('bp_type', where='bp_yn1 == 1', by='sex')"""
    r = rate_by_category(var, where, unit, by)
    r.label = label or r.label
    return r


def rate_by_category(var, where=None, unit='개인', by=None):
    by0 = [by] if isinstance(by, str) else list(by or [])
    by0 = [b.made_name if isinstance(b, _Made) else b for b in by0]
    var = var.made_name if isinstance(var, _Made) else var
    if var in by0:
        raise QueryError(f'구성비를 낼 변수({var})와 분류 기준(by)이 같음. by 에는 구성비를 나누어 볼 다른 기준을 쓸 것')
    by, gs, m, w, idx, size, shape, grade, used = _prep(by0 + [var], where, [], unit)
    thr = THR[grade]
    n = np.bincount(idx[m], minlength=size); s = np.bincount(idx[m], weights=w[m], minlength=size)
    st = np.where(n == 0, 3, np.where(n < thr, 1, 0)).astype(np.int8)
    k = shape[-1]                                           # 집단(by)마다 그 안에서의 구성비
    tot = s.reshape(-1, k).sum(axis=1, keepdims=True)
    val = np.round(100 * s.reshape(-1, k) / np.maximum(tot, 1e-9), 1).reshape(-1)
    args = {'var': var, 'where': where, 'unit': unit}
    if by0:
        args['by'] = by0
    return _finish('share', args, by, gs, shape, st, val, {'인원': [sig3(x) for x in s]}, f'{gs[-1][2]} 구성비' + (f'({where})' if where else '') + (f" · {', '.join(g[2] for g in gs[:-1])}별" if by0 else ''),
                   '%', grade, 'share', n)


def poverty_rate(where=None, by=None, label=None):
    """상대 빈곤율(%): 균등화 가처분소득이 전체 중위값의 50% 미만인 인구 비율."""
    return rate('poor == 1', where=where, by=by, label=label or '상대 빈곤율' + (f'({where})' if where else ''))


def info():
    """자료 요약(행 수, 가구 수, 가중 인구, 빈곤선)."""
    _need()
    return dict(_INFO)


# ───────────────────────── 변수 찾기 ─────────────────────────
def find_vars(query, top=10, only_available=True):
    """한글 이름·사업명·변수명으로 변수를 찾는다."""
    _need()
    toks = [t for t in str(query).replace(',', ' ').split() if t]
    rows = []
    for v, m in _META.items():
        if only_available and not m.get('available', True):
            continue
        hay = [m.get('name_ko', ''), m.get('program', ''), v, m.get('content', '')]
        sc = 0.0
        for t in toks:
            tl = t.lower()
            sc += 5 * (tl in hay[0].lower()) + 3 * (tl in hay[1].lower()) + 4 * (tl in hay[2].lower()) + 1 * (tl in hay[3].lower())
        if sc > 0:
            rows.append((sc - 0.01 * len(hay[0]), v, m))
    rows.sort(key=lambda x: -x[0])
    return pd.DataFrame([{'변수명': v, '한글 이름': m.get('name_ko', ''), '사업': m.get('program', ''), '단위': m.get('unit', ''), '등급': m.get('grade', ''), '코드값': '; '.join(f'{k}={x}' for k, x in (m.get('labels') or {}).items())[:60]}
                         for _, v, m in rows[:top]])


def var_info(var):
    """변수 한 개의 정의(한글 이름, 사업, 단위, 코드값, 추출 대상, 등급)."""
    _need()
    m = _META.get(var)
    if not m:
        raise QueryError(f'없는 변수: {var}')
    return {'변수명': var, '한글 이름': m.get('name_ko', ''), '사업': m.get('program', ''), '보유기관': m.get('org', ''), '단위': m.get('unit', ''),
            '내용': m.get('content', ''), '추출 대상': m.get('scope', ''), '코드값': m.get('labels') or {}, '등급': m.get('grade', ''), '값 있음': m.get('available', True)}
