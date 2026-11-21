# -*- coding: utf-8 -*-
"""ssda.verify — 산출 결과와 응답의 자동 검증.

분석 담당자가 결과를 내놓기 전에 하는 확인을 코드로 옮긴 것이다. 모형의 판단에 맡기지 않고 하네스가 매번 수행한다.

  check_result(res)        집계 결과 1개의 점검: 억제 현황, 분류 누락, 전체 값과의 대조, 분모(대상 집단) 점검,
                           여부 변수의 0 비교, 연간·12월 기준 안내, 평균에서 빠진 대상, 0이 많이 섞인 금액
  lint_code(code, seen)    실행 전 변수 점검: 없는 변수(비슷한 이름 제시), 값이 없는 변수, 정의를 확인하지 않고 쓴 변수
  check_request(q, code)   질문에 적힌 조건(연령, 성, 1인 가구, 소득 분위, 지역, 가구 단위, 그림·저장)이 코드에 반영됐는지 대조
  ground_numbers(text, …)  응답 문장의 수치가 실행 결과에 있는 값인지 대조
  format_block(out, pre)   모형에 돌려주는 「[검증 결과]」 문단
  footer(...)              이용자에게 보여 주는 「검증 요약」

수준  경고: 고치거나, 고치지 않는 사유를 유의 사항에 적어야 함 / 주의: 유의 사항에 밝힘 / 참고: 해석에 쓰는 정보
모든 점검은 통제를 거친 집계값과 연령대 수준의 정보만 사용하며 개인 단위 값을 내보내지 않는다.
"""
from __future__ import annotations

import ast
import difflib
import re

import numpy as np

from . import core
from .core import ST_COMP, ST_NA, ST_OK, ST_SUP

AGG = {'rate', 'mean', 'total', 'quantile', 'count', 'share', 'poverty_rate'}
WORDS = {'and', 'or', 'not', 'in', 'isna', 'notna'}
BASIC = {'age', 'gender', 'sido', 'hnum', 'head'}             # 시스템 프롬프트·자료 규약에 늘 실리는 기본 변수
AGE_BY = {'age6', 'age3', 'age10'}


def _item(code, level, msg, **kw):
    return {'code': code, 'level': level, 'msg': msg, **kw}


def _fmt(v, unit):
    return (f'{v:,.1f}' if unit in ('%', '일') or abs(v) < 100 else f'{v:,.0f}') + unit


def _idents(expr):
    return [t for t in re.findall(r'[A-Za-z_][A-Za-z0-9_]*', str(expr or '')) if t not in WORDS]


def _quiet(fn, *a, **k):
    core._QUIET = True
    try:
        return fn(*a, **k)
    except (core.ControlError, core.QueryError):
        return None
    finally:
        core._QUIET = False


# ───────────────────────── 집계 결과 점검 ─────────────────────────
def check_result(res):
    """집계 결과 1개를 점검해 항목 목록을 돌려준다."""
    c = getattr(res, 'call', None)
    if not c:
        return []
    fn, a = c['fn'], c['args']
    df = res._df
    out = []
    n = len(df)
    n_sup = int(df['상태'].isin([ST_SUP, ST_COMP]).sum()); n_na = int((df['상태'] == ST_NA).sum()); n_ok = int((df['상태'] == ST_OK).sum())
    by = a.get('by') or ([a['var']] if fn == 'share' else [])
    where, unit = a.get('where'), a.get('unit', '개인')

    # ① 억제 현황
    if n > 1:
        lv = '주의' if n_sup > 0.5 * max(n - n_na, 1) else '참고'
        out.append(_item('억제', lv, f'억제 {n_sup}/{n - n_na}칸' + (' — 절반을 넘음. 분류 기준을 줄이거나 범주를 합칠 것' if lv == '주의' else ''), n_sup=n_sup, n_cells=n - n_na))
    elif n_ok == 0:
        out.append(_item('억제', '주의', '값이 최소 관측 수 기준에 미달해 표시되지 않음. 대상을 넓히거나 조건을 줄일 것', n_sup=1, n_cells=1))

    # ② 분류 누락: 분류 기준에 값이 없어 표에서 빠진 대상의 비율
    if by and fn != 'share':
        try:
            used = set()
            _, _, m1, w, *_ = core._prep(by, where, used, unit)
            _, _, m0, w0, *_ = core._prep([], where, set(), unit)
            if fn in ('mean', 'total', 'quantile'):
                v = core._num(a['var'], set())[0]; m1 = m1 & ~np.isnan(v); m0 = m0 & ~np.isnan(v)
            miss = 100 * (1 - w[m1].sum() / max(w0[m0].sum(), 1e-9))
            if miss >= 0.5:
                out.append(_item('분류 누락', '주의', f'분류 기준에 값이 없는 대상 {miss:.1f}%가 표에서 빠짐', pct=round(float(miss), 1)))
        except (core.ControlError, core.QueryError):
            pass

    # ③ 전체 값과의 대조
    if by and fn in ('rate', 'mean', 'quantile'):
        kw = {k: v for k, v in a.items() if k != 'by'}
        tot = _quiet(getattr(core, fn), **kw)
        tv = tot.value() if tot is not None else None
        if tv is not None:
            ok = df.loc[df['상태'] == ST_OK, '값']
            item = _item('전체 값', '참고', f'분류하지 않은 전체 값 {_fmt(tv, res.unit)}', value=tv)
            if fn in ('rate', 'mean') and n_ok == n and n > 1 and not (ok.min() - 0.11 <= tv <= ok.max() + 0.11):
                item = _item('전체 값', '주의', f'전체 값 {_fmt(tv, res.unit)}이 집단별 값의 범위({_fmt(ok.min(), res.unit)}~{_fmt(ok.max(), res.unit)}) 밖에 있음. 분류 누락 또는 조건식을 확인할 것', value=tv)
            out.append(item)
    if fn == 'share' and n_ok == n and n > 1 and abs(float(df['값'].sum()) - 100) > 0.6:
        out.append(_item('구성비 합', '주의', f"구성비의 합이 {df['값'].sum():.1f}%임"))

    # ④ 분모(대상 집단) 점검 — 분자에 해당하는 사람이 한 명도 없는 연령대가 분모의 15% 이상을 차지하는 경우
    #    (질병처럼 연령에 따라 드물 뿐인 지표는 걸리지 않는다. 해당자가 소수라도 있는 연령대는 대상 밖으로 보지 않는다)
    if fn == 'rate':
        num = a.get('num')
        used_num = set(_idents(num))
        named = [v for v in used_num if v in core._META and v not in BASIC]
        if named and 'age' not in used_num and not (set(by) & AGE_BY) and unit == '개인':
            try:
                nm = core._mask(num, set()); m0 = core._mask(where, set())
                g, labs = core._G['age6'][0], core._G['age6'][1]
                pos = m0 & nm
                if int(pos.sum()) >= 30:
                    npos = np.bincount(g[pos], minlength=len(labs)); nden = np.bincount(g[m0], minlength=len(labs))
                    wd = np.bincount(g[m0], weights=core._W[m0], minlength=len(labs))
                    outg = (npos == 0) & (nden >= 300)             # 해당자가 한 명도 없는 연령대(제도의 대상이 아닐 가능성)
                    out_share = 100 * wd[outg].sum() / max(wd.sum(), 1e-9)
                    if out_share >= 15:
                        out.append(_item('분모', '경고', f"분자에 해당하는 사람이 없는 연령대({', '.join(l for l, o in zip(labs, outg) if o)})가 분모의 {out_share:.0f}%를 차지함. "
                                                         '제도의 대상이 아닌 연령대이면 분모(where)를 대상 집단으로 한정할 것', pct=round(float(out_share))))
            except (core.ControlError, core.QueryError):
                pass
        if n == 1 and n_ok == 1 and float(df['값'].iloc[0]) == 0.0:
            out.append(_item('분자 없음', '주의', '분자에 해당하는 사람이 없음(0%). 조건식을 확인할 것'))

    # ⑤ 여부 변수의 0 비교
    for expr in (a.get('num'), where):
        for v in re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\s*==\s*0(?![\d.])', str(expr or '')):
            if v in core._D.columns and v not in core._G and int((core._D[v] == 0).sum()) == 0:
                out.append(_item('0 비교', '경고', f'{v}에는 0인 값이 없음(해당하지 않으면 결측). 해당하지 않는 집단은 isna({v})로 지정할 것'))

    # ⑥ 연간·12월 기준 안내
    for v in sorted(set(_idents(a.get('num')) + _idents(where) + _idents(a.get('var')))):
        if v.endswith('_yn1') and core._META.get(v[:-1] + '2', {}).get('available'):
            out.append(_item('기준 시점', '참고', f'{v}은 연간(1.1.~12.31.) 기준임. 12월 기준은 {v[:-1]}2'))

    # ⑦ 평균·분위수·합계에서 빠진 대상(값이 없는 행은 제외됨)
    if fn in ('mean', 'quantile') and a.get('var') in core._D.columns:
        try:
            v = core._num(a['var'], set())[0]
            _, _, m0, w0, *_ = core._prep([], where, set(), unit)
            cov = 100 * w0[m0 & ~np.isnan(v)].sum() / max(w0[m0].sum(), 1e-9)
            if cov < 99:
                out.append(_item('값 있는 대상', '참고', f'대상 가운데 값이 있는 {cov:.0f}%만 계산에 포함됨(값이 없는 사람을 0으로 넣은 값이 아님)', pct=round(float(cov))))
            inc = m0 & ~np.isnan(v)                             # ⑧ 0이 많이 섞인 금액의 평균·분위수
            zero = 100 * w0[inc & (v == 0)].sum() / max(w0[inc].sum(), 1e-9)
            if res.unit == '만원' and zero >= 20:
                out.append(_item('0 포함', '주의', f"계산 대상의 {zero:.0f}%는 값이 0임. 금액이 있는 사람만 대상으로 하려면 where에 '{a['var']} > 0'을 넣을 것", pct=round(float(zero))))
        except (core.ControlError, core.QueryError):
            pass
    return out


# ───────────────────────── 실행 전 변수 점검 ─────────────────────────
def lint_code(code, seen=None):
    """코드가 쓰는 변수를 변수 사전과 대조한다.
    돌려주는 값  {'used': [...], 'unknown': {이름: [비슷한 이름…]}, 'empty': [값이 없는 변수…], 'unseen': [정의를 확인하지 않은 변수…]}"""
    core._load_meta()
    out = {'used': [], 'unknown': {}, 'empty': [], 'unseen': []}
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return out
    defined, names = set(), []
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
            continue
        f = n.func.attr
        strs = lambda node: [e.value for e in ast.walk(node) if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        if f in ('define', 'define_group', 'define_sum') and n.args and isinstance(n.args[0], ast.Constant):
            defined.add(n.args[0].value)
            for x in n.args[1:2]:
                names += [t for s in strs(x) for t in _idents(s)]
        elif f in AGG:
            for x in n.args[:1]:
                names += [t for s in strs(x) for t in _idents(s)]
            for k in n.keywords:
                if k.arg in ('where', 'by', 'num', 'var'):
                    names += [t for s in strs(k.value) for t in _idents(s)]
    std = set(core._G) | set(core._X) | {'sido', 'age6', 'age3', 'age10', 'sex', 'hs4', 'inc5', 'nhi3', 'poor2', 'eqinc', 'hh_dinc', 'poor'}
    allnames = list(core._META)
    for v in dict.fromkeys(names):
        if v in defined or v in std:
            continue
        m = core._META.get(v)
        if m is None:
            out['unknown'][v] = difflib.get_close_matches(v, allnames, n=3, cutoff=0.6)
            continue
        out['used'].append(v)
        if not m.get('available', True):
            out['empty'].append(v)
        elif seen is not None and v not in seen and v not in BASIC:
            out['unseen'].append(v)
    return out


def lint_error(pre):
    """실행하지 않고 돌려보낼 오류 문구(없는 변수·값이 없는 변수가 있을 때)."""
    msg = []
    for v, sim in pre['unknown'].items():
        msg.append(f"없는 변수: {v}." + (f" 비슷한 이름: {', '.join(sim)}." if sim else '') + ' ssda.find_vars()로 변수명을 확인할 것')
    for v in pre['empty']:
        msg.append(f'{v}은 이 자료에 값이 없는 변수임. ssda.find_vars()로 값이 있는 변수를 찾을 것')
    return ' / '.join(msg)


def names_in(text, meta=None):
    """문장 안에 나온 변수명(참고 자료·실행 결과에서 정의를 본 변수의 집합을 만들 때 쓴다)."""
    core._load_meta()
    return {t for t in re.findall(r'[A-Za-z_][A-Za-z0-9_]*', text or '') if t in core._META}


# ───────────────────────── 질문과 코드의 대조 ─────────────────────────
_SIDO = ['서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종', '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주']


def check_request(question, code):
    """질문에 적힌 조건이 코드에 반영됐는지 본다(작성자가 요청문을 다시 읽고 빠뜨린 조건을 찾는 확인).
    낱말 수준의 대조이므로 연령·성·가구원수·소득 분위·지역·가구 단위·그림·저장만 다룬다. 제도 조건(예: 「등록장애인 중」)은 다루지 않는다."""
    q = re.sub(r'```.*?```', ' ', question or '', flags=re.S)
    q = '\n'.join(l for l in q.splitlines() if not re.match(r'\s*(오류|\w*Error|실행 전 점검)', l))     # 붙여 넣은 오류 문구는 요청이 아님
    c = code or ''
    miss = []
    for a, b in re.findall(r'(\d+)\s*[~∼]\s*(\d+)\s*세', q):
        if not (re.search(rf'(?<!\d){a}(?!\d)', c) and re.search(rf'(?<!\d)({b}|{int(b) + 1})(?!\d)', c)) and 'age' not in re.findall(r"by=\[?'(age\w*)", c):
            miss.append((f'{a}~{b}세', '연령 조건'))
    for n, w in re.findall(r'(\d+)\s*세\s*(이상|미만|이하|초과)', q):
        if not re.search(rf'(?<!\d)({n}|{int(n) - 1}|{int(n) + 1})(?!\d)', c) and not re.search(r"by=\[?[^)]*age", c):
            miss.append((f'{n}세 {w}', '연령 조건'))
    def need(pat, ok, name, what):
        if re.search(pat, q) and not re.search(ok, c):
            miss.append((name, what))
    need(r'여성|(?<![가-힣])여자', r'gender|sex', '여성', '성 조건')
    need(r'남성|(?<![가-힣])남자', r'gender|sex', '남성', '성 조건')
    need(r'1인 가구|혼자 사는|독거', r'hnum|hs4', '1인 가구', '가구원수 조건')
    need(r'빈곤층|빈곤 가구|빈곤 여부', r'poor', '빈곤층', '빈곤 조건')
    need(r'소득\s*\d\s*분위|소득 분위|소득 5분위', r'inc5', '소득 분위', '소득 분위 조건')
    need(r'가구 단위|가구 수(?![급령])|(?<![인상] )가구 기준', r"unit='가구'", '가구 단위', "unit='가구'")
    need(r'그림|그래프|지도|히트맵|단계구분도|막대로|선으로', r'ssda\.plot\.', '그림', '그림 작성')
    need(r'저장', r'\.save\(', '저장', '저장')
    if any(re.search(rf'(?<![가-힣]){n}(?![가-힣]*도별)(에 사는|만 | 거주|의 |에서)', q) for n in _SIDO) and 'sido' not in c:
        miss.append(('지역', '시도 조건'))
    return [_item('요청 반영', '주의', f"질문의 「{n}」에 해당하는 {w}이 코드에 보이지 않음. 빠뜨린 조건이면 넣어 다시 실행할 것") for n, w in dict.fromkeys(miss)]


# ───────────────────────── 수치 대조 ─────────────────────────
_NUM = re.compile(r'(?<![\w.,])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?![\d])')


def _numbers(text):
    """[(값, 소수 자릿수, 뒤따르는 글자)]"""
    out = []
    for m in _NUM.finditer(text or ''):
        s = m.group(1).replace(',', '') + (m.group(2) or '')
        out.append((float(s), len(m.group(2)) - 1 if m.group(2) else 0, (text[m.end():m.end() + 2] or '').strip()[:1]))
    return out


_DATES = [re.compile(r'(?:19|20)\d{2}\s*년(?:도)?(?:\s*\d{1,2}\s*월)?(?:\s*\d{1,2}\s*일)?'),      # 2022년, 2022년 12월 31일
          re.compile(r'\d{1,2}\.\s?\d{1,2}\.\s*[~\-–]\s*\d{1,2}\.\s?\d{1,2}\.'),                  # 1.1.~12.31.
          re.compile(r'(?<![\d.])\d{1,2}\s*월\s*\d{1,2}\s*일')]                                    # 12월 31일


def _strip_dates(text):
    """기준 시점을 적은 표현(연도, 날짜, 기간)은 산출값이 아니므로 수치 대조에서 뺀다.
    실제 모형이 「결과」에 「2022년 1.1.~12.31.」처럼 기준 기간을 적는 것을 확인함(2026-11-15)."""
    for pat in _DATES:
        text = pat.sub(' ', text)
    return text


def ground_numbers(text, sources):
    """text 의 수치 가운데 sources(실행 결과·질문·코드 등)에서 나올 수 없는 것을 돌려준다.
    인정하는 경우: 출처에 있는 값, 그 값을 만 단위(÷1만)·억 단위(÷1억)로 바꾼 값 — 문장에 적힌 자릿수로 반올림해 비교.
                  문장이 인용한 두 값(위 기준을 통과한 값)의 차이.
    항목 개수 같은 12 이하의 정수(%가 붙지 않은 것)와 기준 시점 표현(연도·날짜·기간)은 대조하지 않는다."""
    text = re.sub(r'```.*?```', ' ', text or '', flags=re.S)
    text = _strip_dates(re.sub(r'`[^`]*`', ' ', text))
    src = sorted({v for v, _, _ in _numbers('\n'.join(sources))})
    cand = src + [v / 1e4 for v in src if v >= 1e3] + [v / 1e8 for v in src if v >= 1e6]
    good, rest = [], []
    for x, d, nxt in _numbers(text):
        if d == 0 and x <= 12 and nxt != '%':
            continue
        tol = 0.5 * 10 ** (-d) + 1e-9
        (good if any(abs(x - y) <= tol for y in cand) else rest).append((x, d, tol))
    bad = []
    for x, d, tol in rest:
        if not any(abs(x - abs(p[0] - q[0])) <= tol + 0.5 * 10 ** (-max(p[1], q[1])) for i, p in enumerate(good) for q in good[i + 1:]):
            bad.append(f'{x:,.{d}f}')
    return list(dict.fromkeys(bad))


def count_numbers(text):
    """대조 대상 수치의 개수(검증 요약에 쓴다)."""
    text = _strip_dates(re.sub(r'```.*?```', ' ', text or '', flags=re.S))
    return sum(1 for x, d, nxt in _numbers(text) if not (d == 0 and x <= 12 and nxt != '%'))


_DECO = r'[ \t#*_>■▶●\[\]【】「」]*'          # 문단 이름 앞뒤에 붙는 꾸밈(굵은 글씨 **, 제목 #, 괄호 등)


def result_part(answer):
    """응답에서 「결과」 구간(「유의 사항」 앞까지).
    문단 이름에 꾸밈이 붙어도 찾는다(예: 「**결과**」「## 결과」「결과:」). 실제 모형(Arete-27B)이 굵은 글씨 표시를 붙여 쓰는 것을 확인함(2026-11-15)."""
    m = re.search(rf'(?:^|\n){_DECO}결과{_DECO}[:：]?{_DECO}\n(.*?)(?=\n{_DECO}유의 사항|\Z)', answer or '', flags=re.S)
    return m.group(1) if m else ''


def answer_issues(answer, sources, checks=None):
    """마지막 응답의 점검: 수치 대조, 억제 안내, 남은 경고의 처리 여부."""
    issues = []
    part = result_part(answer)
    if part:
        bad = ground_numbers(part, sources)
        if bad:
            issues.append(_item('수치 대조', '경고', f"「결과」의 수치 {', '.join(bad[:6])}은 실행 결과에 없는 값임. 실행 결과에 있는 값만 써서 다시 작성할 것", numbers=bad))
    flat = [c for cs in (checks or {}).values() for c in cs]
    if any(c['code'] == '억제' and c.get('n_sup') for c in flat) and '억제' not in answer and '표시되지 않' not in answer:
        issues.append(_item('억제 안내', '주의', '표시되지 않은 칸이 있는데 응답에 억제 안내가 없음. 「유의 사항」에 밝힐 것'))
    return issues


# ───────────────────────── 문단 만들기 ─────────────────────────
def format_block(out, pre=None, req=None):
    """모형에 돌려주는 「[검증 결과]」 문단. out 은 runner.run() 의 결과, pre 는 변수 점검, req 는 질문과 코드의 대조 결과."""
    lines = []
    for name, cs in (out.get('checks') or {}).items():
        ref = [c['msg'] for c in cs if c['level'] == '참고' and c['code'] in ('전체 값', '억제')]
        warn = [c for c in cs if c['level'] in ('경고', '주의')]
        nw, nc = sum(c['level'] == '경고' for c in warn), sum(c['level'] == '주의' for c in warn)
        lines.append(f"- {name}: " + ('이상 없음' if not warn else ', '.join(x for x in (f'경고 {nw}건' if nw else '', f'주의 {nc}건' if nc else '') if x)) + (' · ' + ' · '.join(ref) if ref else ''))
        lines += [f"  {c['level']}({c['code']}): {c['msg']}" for c in warn]
        lines += [f"  참고({c['code']}): {c['msg']}" for c in cs if c['level'] == '참고' and c['code'] not in ('전체 값', '억제')]
    for f in out.get('figure_checks') or []:
        lines.append(f"- 그림 {f['file']}: " + ('이상 없음' if not f['issues'] else '주의 — ' + '; '.join(f['issues'])) + (f" · {'; '.join(f['fixed'])}" if f.get('fixed') else ''))
    if pre and pre.get('unseen'):
        lines.append(f"- 변수 주의: {', '.join(pre['unseen'])}은 참고 자료나 변수 찾기 결과에서 정의를 확인하지 않은 변수임. ssda.var_info()로 뜻을 확인할 것")
    lines += [f"- {r['code']} {r['level']}: {r['msg']}" for r in req or []]          # 요청 반영 주의, 용어 주의·참고
    return '[검증 결과]\n' + '\n'.join(lines) if lines else ''


def tool_message(out, pre=None, export_dir=None, stdout_chars=4000, with_checks=True, req=None):
    """코드 실행 뒤 모형에 돌려주는 문단: 「[실행 결과]」 + 「[검증 결과]」. 조립기와 학습 자료 생성기가 함께 쓴다."""
    std = out['stdout'].rstrip()
    if export_dir:
        std = std.replace(str(export_dir).rstrip('/') + '/', 'export/')
    parts = ['[실행 결과]', std[-stdout_chars:]]
    if out['error']:
        parts.append('오류: ' + out['error'].splitlines()[0])
        if out.get('hint'):                                  # 인자 오류일 때 실행기가 붙이는 함수 사용법(runner.usage_hint)
            parts.append('사용법: ' + out['hint'])
    if out['figures']:
        parts.append('저장된 그림: ' + ', '.join(out['figures']))
    block = format_block(out, pre, req) if with_checks and out.get('ok') else ''
    return '\n'.join(p for p in parts if p) + ('\n\n' + block if block else '')


def answer_sources(messages, codes=()):
    """수치 대조의 출처: 질문, 실행 결과·검증 결과, 코드(참고 자료 카드는 넣지 않는다)."""
    src = []
    for m in messages:
        if m['role'] == 'user':
            src.append(m['content'].split('[질문]')[-1] if '[질문]' in m['content'] else m['content'])
    return src + list(codes)


def summarize(steps, answer_bad=None, n_answer_numbers=None, retried=False):
    """한 질문의 검증 내역(기록·채점·검증 요약에 쓴다)."""
    ran = [s for s in steps if s.get('ok')]
    last = ran[-1] if ran else None
    flat = [c for cs in (last.get('checks') or {}).values() for c in cs] if last else []
    figs = last.get('figure_checks') or [] if last else []
    return {'n_runs': len(steps), 'n_ok': len(ran), 'n_blocked': sum(1 for s in steps if s.get('violations')), 'n_var_errors': sum(1 for s in steps if s.get('pre', {}).get('unknown') or s.get('pre', {}).get('empty')),
            'unseen_vars': sorted({v for s in ran for v in s.get('pre', {}).get('unseen', [])}), 'used_vars': sorted({v for s in ran for v in s.get('pre', {}).get('used', [])}),
            'warnings': [c['code'] for c in flat if c['level'] == '경고'], 'cautions': [c['code'] for c in flat if c['level'] == '주의'] + [r['code'] for r in (last.get('req') or [] if last else []) if r['level'] == '주의'],
            'terms': [{'term': r['term'], 'level': r['level'], 'used': r.get('used', [])} for r in (last.get('req') or [] if last else []) if r['code'] == '용어'],
            'suppressed': sum(c.get('n_sup', 0) for c in flat if c['code'] == '억제'), 'cells': sum(c.get('n_cells', 0) for c in flat if c['code'] == '억제'),
            'overall': [c['msg'] for c in flat if c['code'] == '전체 값'], 'figures': len(figs), 'figure_issues': [i for f in figs for i in f['issues']],
            'ungrounded_numbers': answer_bad or [], 'answer_numbers': n_answer_numbers, 'answer_retried': retried}


def footer(v):
    """이용자에게 보여 주는 「검증 요약」. 모형이 쓰지 않고 하네스가 만든다."""
    if not v['n_runs']:
        return ''
    L = ['검증 요약(자동 점검)']
    L.append(f"- 실행: 코드 {v['n_ok']}회 실행" + (f", 수정 {v['n_runs'] - v['n_ok']}회" if v['n_runs'] > v['n_ok'] else '') + (f", 실행 전 점검에서 차단 {v['n_blocked']}회" if v['n_blocked'] else ''))
    if v['used_vars']:
        L.append(f"- 변수: 사용 변수 {len(v['used_vars'])}개" + (' 모두 정의를 확인한 변수임' if not v['unseen_vars'] else f" 중 {', '.join(v['unseen_vars'])}은 정의 확인 없이 사용됨"))
    if v['n_ok']:
        L.append('- 산출: ' + (f"경고 {len(v['warnings'])}건({', '.join(v['warnings'])})" if v['warnings'] else '경고 없음') + (f", 주의 {len(v['cautions'])}건({', '.join(v['cautions'])})" if v['cautions'] else '')
                 + (f" · 억제 {v['suppressed']}/{v['cells']}칸" if v['cells'] else '') + (' · ' + v['overall'][0] if v['overall'] else ''))
    for t in v.get('terms') or []:
        L.append(f"- 용어: 「{t['term']}」 → {', '.join(t['used']) or '다른 변수'}로 해석해 산출함" + (' — 질문에 범위가 없었으므로 확인 필요' if t['level'] == '주의' else '(기본 해석)'))
    if v['figures']:
        L.append(f"- 그림: {v['figures']}개 저장, " + ('이상 없음' if not v['figure_issues'] else '주의 — ' + '; '.join(v['figure_issues'])))
    if v['answer_numbers'] is not None:
        L.append('- 수치 대조: ' + (f"「결과」의 수치 {v['answer_numbers']}개가 실행 결과와 일치" if not v['ungrounded_numbers'] else f"실행 결과에 없는 수치 {', '.join(v['ungrounded_numbers'][:5])} — 확인 필요")
                 + (' (1회 다시 작성함)' if v['answer_retried'] else ''))
    L.append('- 자동 점검 범위 밖: 지표 정의의 적절성, 해석의 타당성')
    return '\n'.join(L)
