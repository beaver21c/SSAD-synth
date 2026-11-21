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
    if name in _G:
        return _G[name][0].astype(float)
    if name in _D.columns:
        s = _D[name]
        if not pd.api.types.is_numeric_dtype(s):
            raise QueryError(f'숫자형이 아닌 변수는 조건식에 쓸 수 없음: {name}')
        return s.astype(float).values
    raise QueryError(f'없는 변수: {name}. find_vars()로 변수명을 확인할 것')


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
        left = _ev(node.left, used)
        out = None
        for op, comp in zip(node.ops, node.comparators):
            right = _ev(comp, used)
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
def _group(name, used):
    used.add(name)
    if name in _G:
        return _G[name][0], _G[name][1], _G[name][2]
    if name in _D.columns:
        m = _META.get(name, {})
        s = _D[name]
        vals = np.sort(s.dropna().unique())
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
            raise QueryError(f'항목 이름 「{lab}」이 구간과 맞지 않음. bins=[{', '.join(_fmt_num(x) for x in bins)}] 이면 {i + 1}번째 구간은 「{desc[i]}」임. '
                             f'구간은 차례로 ' + ' / '.join(desc) + f' 의 {len(desc)}개이므로 이름을 이 순서에 맞춰 줄 것(대상 집단 밖의 구간에도 이름을 주고 bins 는 줄이지 않음)')


def define_group(name, var, bins, labels):
    """수치 변수를 구간으로 나눈 분류 기준을 만든다. bins=[경계값...], labels=[항목 이름...](경계 수 + 1개)."""
    _need()
    used = set()
    v, lab, _ = _num(var, used) if var in _X else (_col(var, used), _META.get(var, {}).get('name_ko', var), '')
    if len(labels) != len(bins) + 1:
        raise QueryError(f'labels 개수({len(labels)})는 bins 개수({len(bins)}) + 1 이어야 함. bins={list(bins)} 이면 구간은 ' + ' / '.join(_intervals(bins))
                         + f' 의 {len(bins) + 1}개이고 구간마다 이름이 하나씩 필요함. 대상 집단 밖의 구간(예: 맨 앞 구간)에도 이름을 주고 bins 는 줄이지 않음')
    _check_labels(bins, labels)
    codes = np.digitize(v, bins)
    codes = np.where(np.isnan(v), -1, codes)
    _G[name] = (codes, list(labels), f'{lab} 구간', _grade_of(used))
    return f'분류 기준 {name} 생성: ' + ' / '.join(labels)


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
    return by, gs, base & valid, w, idx, size, tuple(len(g[1]) for g in gs), grade, used


def _frame(by, gs, shape):
    if not by:
        return pd.DataFrame(index=[0])
    grid = np.indices(shape).reshape(len(shape), -1)
    return pd.DataFrame({gs[i][2]: [gs[i][1][j] for j in grid[i]] for i in range(len(by))})


def _status(st):
    return np.array([ST_OK, ST_SUP, ST_COMP, ST_NA], dtype=object)[st]


class Result:
    """집계 결과. 개인 단위 값은 담지 않는다."""

    def __init__(self, df, label, unit, grade, kind, by_labels):
        self._df = df; self.label = label; self.unit = unit; self.grade = grade; self.kind = kind; self.by = by_labels
        self.call = None                                   # 산출 조건(함수 이름·인자) — 자동 검증(ssda.verify)과 기록에 쓴다

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
        return {'지표': self.label, '단위': self.unit, '등급': self.grade, '최소 관측 수': THR[self.grade], '칸 수': n, '표시하지 않는 칸': s}

    def to_text(self, max_rows=60):
        d = self._df.copy()
        d['값'] = [('' if pd.isna(v) else (f'{v:,.1f}' if self.unit in ('%', '일') else f'{v:,.0f}' if abs(v) >= 100 else f'{v:,.2f}')) for v in d['값']]
        d.loc[d['상태'] != ST_OK, '값'] = d.loc[d['상태'] != ST_OK, '상태']
        for c in d.columns:                                   # 인원·합계 열은 천 단위 구분 기호로 표시
            if c not in self.by and c not in ('값', '상태'):
                d[c] = ['' if pd.isna(v) else f'{v:,.0f}' for v in d[c]]
        head = f'[{self.label}] 단위: {self.unit} · 등급 {self.grade}(최소 {THR[self.grade]}건)'
        body = d.drop(columns=['상태']).head(max_rows).to_string(index=False)
        return head + '\n' + body + ('' if len(d) <= max_rows else f'\n… 외 {len(d) - max_rows}행')

    def __repr__(self):
        return self.to_text()

    def save(self, name):
        """반출 신청용으로 결과 표를 저장한다(통제를 거친 집계값만 저장됨)."""
        out = Path(os.environ.get('SSDA_EXPORT', 'export')); out.mkdir(parents=True, exist_ok=True)
        p = out / f'{name}.csv'
        self._df.to_csv(p, index=False, encoding='utf-8-sig')
        (out / f'{name}.meta.json').write_text(json.dumps(self.summary(), ensure_ascii=False), encoding='utf-8')
        _log('save', {'name': name}, len(self._df), 0)
        return str(p)


_QUIET = False            # 자동 검증이 내부적으로 다시 계산할 때는 호출 기록을 남기지 않는다
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


def _finish(fn, args, by, gs, shape, st, val, extra, label, unit, grade, kind, key):
    if shape and int(np.prod(shape)) > 1:
        st = _complement(st.copy(), key, shape)
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
    if not _QUIET:
        _CREATED.append(res)
    return res


# ───────────────────────── 집계 함수 ─────────────────────────
def count(where=None, by=None, unit='개인', label=None):
    """조건에 맞는 가중 인원(또는 가구 수). 유효숫자 3자리."""
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
                   {'해당 인원': [sig3(x) for x in wn], '대상 인원': [sig3(x) for x in wd]}, label or f'비율: {num}' + (f' / 대상: {where}' if where else ''), '%', grade, 'rate', nn)


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


def share(var, where=None, unit='개인', label=None):
    """범주형 변수(또는 분류 기준)의 구성비(%)."""
    r = rate_by_category(var, where, unit)
    r.label = label or r.label
    return r


def rate_by_category(var, where=None, unit='개인'):
    by, gs, m, w, idx, size, shape, grade, used = _prep([var], where, [], unit)
    thr = THR[grade]
    n = np.bincount(idx[m], minlength=size); s = np.bincount(idx[m], weights=w[m], minlength=size)
    st = np.where(n == 0, 3, np.where(n < thr, 1, 0)).astype(np.int8)
    val = np.round(100 * s / max(s.sum(), 1e-9), 1)
    return _finish('share', {'var': var, 'where': where, 'unit': unit}, by, gs, shape, st, val, {'인원': [sig3(x) for x in s]}, f'{gs[0][2]} 구성비' + (f'({where})' if where else ''), '%', grade, 'share', n)


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
