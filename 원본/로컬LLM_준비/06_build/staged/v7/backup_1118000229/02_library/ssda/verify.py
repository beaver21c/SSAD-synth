# -*- coding: utf-8 -*-
"""ssda.verify — 산출 결과와 응답의 자동 검증.

분석 담당자가 결과를 내놓기 전에 하는 확인을 코드로 옮긴 것이다. 모형의 판단에 맡기지 않고 하네스가 매번 수행한다.

  check_result(res)        집계 결과 1개의 점검: 억제 현황, 분류 누락, 전체 값과의 대조, 분모(대상 집단) 점검, 대상 한정(대상이 분자와 같은 집단),
                           여부 변수의 0 비교·「!= 1」 비교, 연간·12월 기준 안내, 평균에서 빠진 대상, 0이 많이 섞인 금액
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
    expr = re.sub(r"'[^']*'|\"[^\"]*\"", ' ', str(expr or ''))          # 조건식 안의 항목 이름(문자열)은 변수가 아님. 예: sido == '충북'
    return [t for t in re.findall(r'[A-Za-z_][A-Za-z0-9_]*', expr) if t not in WORDS]


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
    elif n_ok == 0 and not getattr(res, 'diff_blocked', 0):
        out.append(_item('억제', '주의', '값이 최소 관측 수 기준에 미달해 표시되지 않음. 대상을 넓히거나 조건을 줄일 것', n_sup=1, n_cells=1))
    nb = int(getattr(res, 'diff_blocked', 0) or 0)
    if nb:                                                  # 대화 단위 차분 점검으로 가린 칸
        out.append(_item('차분 방지', '주의', f'이 대화에서 앞서 표시한 집계와의 차이로 소수 집단의 값이 드러나는 칸 {nb}개를 가림. 조건을 바꿔 같은 값을 다시 구하지 말 것. '
                                         '가려진 사유를 「유의 사항」에 밝히고 더 넓은 구간·집단으로 묶은 집계를 대안으로 제시할 것', n=nb))

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
    if fn == 'share' and not a.get('by') and n_ok == n and n > 1 and abs(float(df['값'].sum()) - 100) > 0.6:
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
        # ④-2 대상 한정 — 대상(where)에 든 사람이 모두 분자에 해당하는 경우. 비율이 100%가 되고 여집합이 없어 전 칸이 표시되지 않는다
        #     (2026-11-16 실제 모형 관찰: 이용률의 where 에 'not isna(evou_yn)' 을 넣어 대상을 이용자로 좁힘)
        if where:
            try:
                nm = core._mask(num, set()); m0 = core._prep([], where, set(), unit)[2]
                if int(m0.sum()) >= 30 and not bool((m0 & ~nm).any()):
                    na = sorted(set(re.findall(r'(?:isna|notna)\(\s*([A-Za-z_]\w*)\s*\)', str(where))))
                    out.append(_item('대상 한정', '경고', '대상(where)에 든 사람이 모두 분자 조건에 해당함(비율 100%, 여집합이 없어 표시되지 않음). '
                                     + (f"where 의 결측 조건({', '.join(na)})이 대상을 해당자로 좁힌 것임. 여부 변수는 해당하지 않으면 결측이므로 이 조건을 빼고, " if na else 'where 가 분자와 같은 집단을 가리킴. ')
                                     + '대상은 질문에 적힌 집단(없으면 제도의 대상 연령, 그것도 없으면 where 없이 전체)으로 두어 다시 실행할 것'))
            except (core.ControlError, core.QueryError):
                pass

    # ⑤ 여부 변수의 0 비교
    for expr in (a.get('num'), where):
        for v in re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\s*==\s*0(?![\d.])', str(expr or '')):
            if v in core._D.columns and v not in core._G and not core._is_flag(v) and int((core._D[v] == 0).sum()) == 0:      # 여부 변수의 「== 0」은 분석 함수가 「해당 아님」으로 계산함(0.7.0)
                out.append(_item('0 비교', '경고', f'{v}에는 0인 값이 없음(해당하지 않으면 결측). 해당하지 않는 집단은 「not ({v} == 1)」로 지정할 것'))
        # ⑤-2 여부 변수의 「!= 1」 비교(2026-11-16 미세조정 모형 관찰: 비수급자를 'bp_yn1 != 1' 로 지정하여 대상이 0명이 됨. 결측은 비교식에서 거짓으로 처리됨)
        for v in re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\s*!=\s*1(?![\d.])', str(expr or '')):
            if core._only_one(v) and not core._is_flag(v):      # 여부 변수의 「!= 1」은 분석 함수가 「해당 아님」으로 계산함(0.7.0)
                out.append(_item('1 아님 비교', '경고', f'{v}는 해당하면 1, 해당하지 않으면 결측이어서 「{v} != 1」에 해당하는 사람이 없음. 해당하지 않는 집단은 「not ({v} == 1)」로 지정할 것'))

        # ⑤-3 0값이 있는 여부 변수의 결측 조건(2026-11-17 독립 검증: 여부 변수 161개 가운데 60개에 0이 있음. isna()는 0인 사람을 빼므로 「해당하지 않는 사람」 전체를 가리키지 않음)
        for v in re.findall(r'(?:isna|notna)\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)', str(expr or '')):
            if v in core._D.columns and v not in core._G and re.search(r'_yn\d?$', v):
                n0 = int((core._D[v] == 0).sum())
                if n0 > 0:
                    out.append(_item('결측 조건', '경고', f'{v}에는 해당하지 않는 사람이 0으로 적힌 행이 {n0:,}건 있어 isna({v})·notna({v})가 해당 여부와 맞지 않음. '
                                                         f'해당하는 집단은 「{v} == 1」, 해당하지 않는 집단은 「not ({v} == 1)」로 지정할 것'))

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
        if f == 'define_cond' and n.args and isinstance(n.args[0], ast.Constant):      # 조건 집단 정의: 이름을 등록하고, 조건식(사전의 값) 안의 변수를 점검
            defined.add(n.args[0].value)
            for x in list(n.args[1:2]) + [k.value for k in n.keywords if k.arg == 'groups']:
                vals = x.values if isinstance(x, ast.Dict) else [x]
                names += [t for v in vals for s in strs(v) for t in _idents(s)]
        elif f in ('define', 'define_group', 'define_sum') and n.args and isinstance(n.args[0], ast.Constant):
            defined.add(n.args[0].value)
            for x in n.args[1:2]:
                names += [t for s in strs(x) for t in _idents(s)]
        elif f in AGG:
            for x in n.args[:1]:
                names += [t for s in strs(x) for t in _idents(s)]
            for k in n.keywords:
                if k.arg in ('where', 'by', 'num', 'var'):
                    names += [t for s in strs(k.value) for t in _idents(s)]
    std = set(core._G) | set(core._X) | {'sido', 'metro2', 'age6', 'age3', 'age10', 'sex', 'hs4', 'inc5', 'nhi3', 'poor2', 'eqinc', 'hh_dinc', 'poor'}
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


def group_fix(code):
    """define_group 의 구간 경계(bins)와 항목 이름(labels)의 개수가 맞지 않는 코드에 대해 고치는 방법을 구체적으로 적는다(같은 코드가 다시 제출됐을 때만 덧붙임).
    항목 이름의 시작값이 구간 경계와 대응하면 항목 이름을 그대로 둘 때의 bins 를 제시하고, 대응하지 않으면(금액 단위 등) 필요한 항목 이름의 개수만 적는다."""
    try:
        tree = ast.parse(code or '')
    except SyntaxError:
        return ''
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'define_group'):
            continue
        kw = {k.arg: k.value for k in n.keywords}
        b, l = (n.args[2] if len(n.args) > 2 else kw.get('bins')), (n.args[3] if len(n.args) > 3 else kw.get('labels'))
        try:
            bins, labels = list(ast.literal_eval(b)), list(ast.literal_eval(l))
        except Exception:                                   # noqa: BLE001 — 목록을 그대로 적지 않은 코드는 다루지 않음
            continue
        if len(labels) == len(bins) + 1 or not labels:
            continue
        lows = []
        for lab in labels[1:]:
            m = re.match(r'\s*(\d+(?:\.\d+)?)', str(lab))
            lows.append(float(m.group(1)) if m else None)
        ok = (None not in lows and all(x < y for x, y in zip(lows, lows[1:])) and bins and all(isinstance(x, (int, float)) for x in bins)
              and (set(map(float, bins)) <= set(lows) or set(lows) <= set(map(float, bins))))
        if ok:
            sug = [int(x) if float(x).is_integer() else x for x in lows]
            return (f'고치는 방법: 항목 이름 {len(labels)}개를 그대로 쓰려면 bins={sug} 로 바꿀 것(bins 의 값은 둘째 항목부터의 시작값과 같아야 함). '
                    f'bins={bins} 를 그대로 쓰려면 항목 이름을 {len(bins) + 1}개로 줄일 것')
        return f'고치는 방법: bins 가 {len(bins)}개이면 항목 이름은 {len(bins) + 1}개여야 함. 항목 이름을 {len(bins) + 1}개로 맞추거나 bins 를 {len(labels) - 1}개로 맞출 것'
    return ''


def repeat_error(prev_error, code=None):
    """실패한 코드와 같은 코드가 다시 제출됐을 때 돌려보내는 오류 문구(실행하지 않음). 조립기의 repeat_guard 가 쓴다."""
    first = (prev_error or '').splitlines()[0] if prev_error else ''
    fix = group_fix(code) if code and 'labels 개수' in first else ''
    return ('앞서 실패한 코드와 글자까지 같은 코드임(고친 부분이 없어 실행하지 않음). 설명만 바꾸지 말고 코드에서 오류가 가리키는 인자·변수·값을 실제로 바꿀 것'
            + (f'. {fix}' if fix else '') + (f'. 앞선 오류 — {first}' if first else ''))


def var_candidates(question, seen=(), tried=(), top=5):
    """질문의 낱말로 변수 사전을 찾은 후보(없는 변수 오류가 거듭될 때 조립기가 오류 문구에 덧붙임).
    이미 정의를 본 변수(seen)가 설명하는 낱말은 빼고, 남은 낱말이 한글 이름·사업명에 들어 있는 변수를 고른다. 형태소 분석 없이 글자 포함 여부로 대조한다.
    돌려주는 값  [{'name': 변수명, 'name_ko': 한글 이름, 'program': 사업, 'unit': 단위}, …]"""
    core._load_meta()
    q = re.sub(r'```.*?```', ' ', question or '', flags=re.S)
    words = lambda s: [w for w in re.split(r'[^0-9A-Za-z가-힣]+', s or '') if len(w) >= 2]
    covered = {w for v in seen if v in core._META for w in words(core._META[v].get('name_ko', '')) + words(core._META[v].get('program', '')) if w in q}
    rows = []
    for v, m in core._META.items():
        if v in seen or v in tried or not m.get('available', True) or str(m.get('grade', '')) == '제외':
            continue
        name, prog = m.get('name_ko', '') or '', m.get('program', '') or ''
        sc = 0.0
        if len(name) >= 2 and name in q and name not in covered:
            sc += 5
        sc += 2 * sum(1 for w in set(words(name)) if w in q and w not in covered and w != name)
        sc += 1.5 * sum(1 for w in set(words(prog)) if w in q and w not in covered)
        if sc >= 3:
            rows.append((sc - 0.01 * len(name), v, m))
    rows.sort(key=lambda x: (-x[0], x[1]))
    return [{'name': v, 'name_ko': m.get('name_ko', ''), 'program': m.get('program', ''), 'unit': m.get('unit', '')} for _, v, m in rows[:top]]


def candidates_note(cand):
    return ('변수명을 짐작해 바꾸지 말 것. 질문의 낱말로 변수 사전을 찾은 후보: '
            + ', '.join(f"{c['name']}({c['name_ko']}" + (f" · {c['program']}" if c['program'] and c['program'] != c['name_ko'] else '') + (f" · 단위 {c['unit']}" if c['unit'] else '') + ')' for c in cand)
            + ". 후보에 없으면 print(ssda.find_vars('핵심어'))로 먼저 찾을 것")


def claims_results(answer, sources=()):
    """실행한 코드가 없는데 결과를 적은 응답인지 본다(조립기의 unexecuted_results 가 쓴다).
    파이썬 코드가 아닌 코드 블록 안의 수치 가운데 sources(질문·참고 자료·앞선 실행 결과)에서 나올 수 없는 값이 3개 이상이면 결과 표를 지어 적은 것으로 본다
    (2026-11-17: 코드 확인 요청에 실행 없이 「실행 결과」 표를 적은 응답이 관찰됨). 앞선 질문의 실행 결과를 옮겨 적은 표는 출처에 값이 있으므로 걸리지 않는다."""
    blocks = re.findall(r'```(?!python)[^\n]*\n(.*?)```', answer or '', flags=re.S)
    return any(len(ground_numbers(b, sources)) >= 3 for b in blocks)


def claims_values(answer, sources=()):
    """실행한 코드가 없는데 「결과」 문단에 수치를 적은 응답인지 본다(2026-11-17 독립 검증: 수행할 수 없는 질문에 실행 없이 「1,288명」「28.3%」를 답으로 적은 응답이 확인됨).
    질문·참고 자료·앞선 실행 결과에서 나올 수 없는 수치가 「결과」에 하나라도 있으면 해당한다. 되묻는 응답과 거절은 대상이 아니다."""
    part = result_part(answer)
    if not part or re.search(r'확인 필요|요청 처리 불가', (answer or '')[:200]):
        return False
    return bool(ground_numbers(part, sources))


UNEXECUTED_NOTE = ('[검증 결과]\n- 경고(실행 없음): 실행한 코드가 없는데 응답에 수치가 적혀 있음. 실행하지 않은 값은 쓸 수 없음. '
                   '산출할 수 있으면 파이썬 코드 블록을 작성해 실행한 뒤 [실행 결과]에 있는 값만으로 「결과」와 「유의 사항」을 작성하고, '
                   '자료나 기능이 없어 산출할 수 없으면 수치 없이 「요청 처리 불가」로 사유와 가능한 대안을 적을 것')
UNEXECUTED_FOOT = '- 경고: 실행한 코드가 없음. 응답에 적힌 수치는 실행 결과가 아니므로 쓰지 말 것'


def ask_gate_note(cand=()):
    """모형이 코드 없이 「확인 필요」로 되물었을 때 한 번 돌려보내는 문구(조립기의 ask_gate 가 쓴다).
    2026-11-17 독립 검증: 질문에 항목 이름·단위·대상이 적혀 있는데도 되물어 답을 내지 못한 차례가 산출 차례의 6~9%였음."""
    return ('[검증 결과]\n- 확인(되묻기 전 점검): 질문에 적힌 내용만으로 산출이 정해지는지 다시 볼 것. '
            '① 질문에 적힌 항목 이름·단위·기준 시점·대상 조건은 그대로 따름(「수급일수」는 일수 변수, 「몇 명」은 인원) '
            '② 이어 묻는 질문이면 앞선 질문의 제도·대상·기준을 이어받음 ③ 배경 설명에 쓰인 말은 산출 조건이 아님 '
            '④ 질문이 정하지 않은 세부 사항은 가장 일반적인 해석을 골라 「분석 계획」의 가정에 밝힘. '
            + (candidates_note(cand).replace('변수명을 짐작해 바꾸지 말 것. ', '') + '. ' if cand else '')
            + '위에 따라 정해지면 코드를 작성해 산출할 것. 서로 다른 산출로 갈리는데 문장으로는 정할 수 없을 때만 「확인 필요」를 다시 적고, 자료나 기능이 없어 산출할 수 없으면 「요청 처리 불가」로 답할 것')


def review_request(questions, step, unused=()):
    """실행한 산출이 질문과 일치하는지 모형에 따로 묻는 검토 요청문(조립기의 review 가 쓴다). 대화와 분리된 새 요청으로 보낸다.
    questions 는 대화의 질문들(마지막이 이번 질문), step 은 마지막으로 성공한 실행, unused 는 참고 자료에 있었으나 쓰지 않은 변수 이름."""
    core._load_meta()
    ko = lambda v: (core._META.get(v, {}).get('name_ko') or '')
    defs = [def_ko(r.get('call') or {}) for r in (step.get('results') or {}).values()][:4]
    used = [v for v in (step.get('pre') or {}).get('used', []) if ko(v)]
    L = ['[검토 요청]', '아래는 이용자의 질문과 그 질문에 답하려고 실행한 코드임. 실행한 산출이 질문의 문언과 일치하는지만 대조할 것. 코드를 쓰지 말고 맨 아래 형식으로만 답할 것.', '']
    if len(questions) > 1:
        L += ['[앞선 질문]'] + [f'- {q.strip()}' for q in questions[:-1]] + ['']
    L += ['[질문]', questions[-1].strip(), '', '[실행한 코드]', '```', (step.get('code') or '').strip(), '```', '', '[산출 정의]'] + [f'- {d}' for d in defs]
    if used:
        L += ['', '[쓴 변수의 뜻]'] + [f'- {v}: {ko(v)}' for v in used[:12]]
    un = [v for v in unused if ko(v) and v not in used][:6]
    if un:
        L += ['', '[참고 자료에 있었으나 쓰지 않은 변수]'] + [f'- {v}: {ko(v)}' for v in un]
    L += ['', '[대조 항목]',
          '1. 지표: 질문이 요청한 지표(인원·가구 수, 비율, 평균, 합계, 중위수, 구성비, 빈곤율)와 산출 함수가 같은가',
          '2. 대상: 질문이 정한 대상 조건(연령 경계, 성, 지역, 가구 규모, 제도의 대상·수급 여부)이 빠짐없이 들어 있고, 질문에 없는 조건이 더해지지 않았는가',
          '3. 변수: 질문이 말한 항목과 같은 뜻의 변수인가(연간 기준과 12월 기준, 개인 변수와 가구 변수, 금액과 기간·일수, 대상 여부와 수급 여부)',
          '4. 분류: 질문이 요청한 분류 기준·구간과 같은가(질문이 한 집단의 값만 물었는데 표로 나누지 않았는가)',
          '5. 단위: 개인 단위와 가구 단위',
          '질문이 정하지 않은 사항을 합리적으로 가정한 것은 일치로 본다. 문언과 분명히 어긋난 경우만 불일치로 한다.', '',
          '[답 형식] 아래 세 줄만 적을 것',
          '질문의 요구: 지표 … / 대상 조건 … / 분류 … / 단위 …  (질문 문장에서 읽은 그대로 한 줄로)',
          '판정: 일치  (또는  판정: 불일치)',
          '사유: 불일치일 때만, 항목 번호와 함께 무엇이 어긋나는지와 고칠 방법을 한두 줄로']
    return '\n'.join(L)


def review_verdict(text):
    """검토 응답에서 판정을 읽는다. 불일치라고 분명히 적은 경우만 True(형식을 지키지 않은 응답은 일치로 봄)."""
    m = re.search(r'판정\s*[:：]?\s*\**\s*(불일치|일치)', text or '')
    return bool(m and m.group(1) == '불일치')


def review_note(text):
    """검토에서 불일치로 본 사유를 대화에 돌려주는 문구."""
    m = re.search(r'사유\s*[:：]?\s*(.+)', text or '', flags=re.S)
    why = re.sub(r'\s+', ' ', (m.group(1) if m else text or '')).strip()[:500]
    return ('[검증 결과]\n- 경고(검토): 실행한 산출이 질문과 어긋난다는 검토 의견이 있음 — ' + why
            + '\n질문의 문언에 비추어 이 지적이 맞으면 코드를 고쳐 다시 실행할 것. 맞지 않으면 코드를 다시 쓰지 말고 앞의 「결과」와 「유의 사항」을 그대로 다시 적을 것')


def names_in(text, meta=None):
    """문장 안에 나온 변수명(참고 자료·실행 결과에서 정의를 본 변수의 집합을 만들 때 쓴다)."""
    core._load_meta()
    return {t for t in re.findall(r'[A-Za-z_][A-Za-z0-9_]*', text or '') if t in core._META}


# ───────────────────────── 질문과 코드의 대조 ─────────────────────────
_SIDO = ['서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종', '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주']


def _clean_q(question):
    q = re.sub(r'```.*?```', ' ', question or '', flags=re.S)
    return '\n'.join(l for l in q.splitlines() if not re.match(r'\s*(오류|\w*Error|실행 전 점검)', l))     # 붙여 넣은 오류 문구는 요청이 아님


def check_request(question, code, history=()):
    """질문에 적힌 조건이 코드에 반영됐는지 본다(작성자가 요청문을 다시 읽고 빠뜨린 조건을 찾는 확인).
    낱말 수준의 대조이므로 연령·성·가구원수·소득 분위·지역·가구 단위·그림·저장만 다룬다. 제도 조건(예: 「등록장애인 중」)은 다루지 않는다.
    history 는 같은 대화의 앞선 질문(이어 묻는 질문에서 「질문에 없는 조건」을 볼 때 앞선 질문의 조건을 인정하는 데 쓴다)."""
    q = _clean_q(question)
    c = (code or '').replace("\\'", "'").replace('\\"', '"')      # 따옴표 안의 따옴표(\\')를 풀어 지역 이름 등을 읽음
    miss = []
    age_by = _age_grouped(q) and bool(re.search(r"by=\[?[^)\]]*'age\w*'", c) or re.search(r"define_(group|cond)\([^)]*\bage\b", c))      # 질문이 연령 구간을 나열했고 코드가 연령을 분류 기준으로 씀(구간은 조건이 아님)
    for a, b in re.findall(r'(\d+)\s*[~∼]\s*(\d+)\s*세', q):
        if not (re.search(rf'(?<!\d){a}(?!\d)', c) and re.search(rf'(?<!\d)({b}|{int(b) + 1})(?!\d)', c)) and not age_by:
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
    if any(re.search(rf'(?<![가-힣]){n}(?![가-힣]*도별)(에 사는|만 | 거주|의 |에서)', q) for n in _SIDO) and 'sido' not in c and 'metro2' not in c:
        miss.append(('지역', '시도 조건'))
    out = [_item('요청 반영', '주의', f"질문의 「{n}」에 해당하는 {w}이 코드에 보이지 않음. 빠뜨린 조건이면 넣어 다시 실행할 것") for n, w in dict.fromkeys(miss)]
    return out + check_request_strict(q, c) + check_request_extra(q, c, ' '.join(_clean_q(h) for h in history or ()))


def _age_grouped(q):
    """질문이 연령 구간을 나열해 나누라고 한 것인지(구간이 둘 이상이거나 맞닿은 구간이 있음). 한 구간만 적은 것(「18~64세 가운데」)은 대상 조건임."""
    rng = [(int(a), int(b)) for a, b in re.findall(r'(\d+)\s*[~∼\-]\s*(\d+)\s*세', q)]
    ge = [int(n) for n in re.findall(r'(\d+)\s*세\s*이상', q)]
    lt = [int(n) for n in re.findall(r'(\d+)\s*세\s*미만', q)] + [int(n) + 1 for n in re.findall(r'(\d+)\s*세\s*이하', q)]
    st = {a for a, _ in rng}
    return len(rng) >= 2 or any(b + 1 in ge or b + 1 in st for _, b in rng) or any(x in ge or x in st for x in lt)


_AGE_STD = {'age3': [18, 65], 'age6': [18, 35, 50, 65, 75], 'age10': [10, 20, 30, 40, 50, 60, 70, 80]}
_SIDO_FULL = {'서울특별시': '서울', '부산광역시': '부산', '대구광역시': '대구', '인천광역시': '인천', '광주광역시': '광주', '대전광역시': '대전', '울산광역시': '울산', '세종특별자치시': '세종', '세종시': '세종',
              '경기도': '경기', '강원도': '강원', '강원특별자치도': '강원', '충청북도': '충북', '충청남도': '충남', '전라북도': '전북', '전북특별자치도': '전북', '전라남도': '전남', '경상북도': '경북', '경상남도': '경남',
              '제주도': '제주', '제주특별자치도': '제주'}


def check_request_strict(q, c):
    """질문의 문언과 코드가 어긋나는 것이 분명한 경우의 대조(경고). 2026-11-17 독립 검증에서 확인된 조용한 오답의 유형을 낱말 수준에서 잡는다:
    합계 요청에 평균, 질문이 정한 구간 대신 표준 구간·다른 경계, 연령 경계어(미만·이하·이상·초과)와 연산자의 불일치, 지역 이름과 시도 코드의 불일치,
    수도권 묶음, 12월·연간 기준, 「혼자 사는」, 해당하지 않는 집단. 어긋남이 분명한 경우만 다루며 고치는 방법을 함께 적는다."""
    out = []

    def warn(msg):
        out.append(_item('요청 반영', '경고', msg))
    # ① 집계 함수
    want_sum = re.search(r'합계|총합|합산|모두 더한|다 합치|전부 합|전국 합', q) or (re.search(r'총액|총 ?지급액|총 ?금액|총 ?규모', q) and not re.search(r'평균|1인당|중위|중앙값', q))
    if want_sum and not re.search(r'평균|1인당', q) and not re.search(r'ssda\.total\(', c) and re.search(r'ssda\.(mean|quantile)\(', c):
        warn('질문은 합계(총액)를 요청했는데 코드가 평균·분위수를 산출함. 합계는 ssda.total(변수, where=…)로 산출할 것')
    if re.search(r'중위수|중위값|중앙값|중간값', q) and not re.search(r'ssda\.quantile\(', c) and re.search(r'ssda\.(mean|total)\(', c):
        warn('질문은 중위수를 요청했는데 코드에 ssda.quantile()이 없음. 중위수는 ssda.quantile(변수, 0.5, where=…)로 산출할 것')
    # ② 질문이 정한 연령 구간
    rng = [(int(a), int(b)) for a, b in re.findall(r'(\d+)\s*[~∼\-]\s*(\d+)\s*세', q)]
    ge = [int(n) for n in re.findall(r'(\d+)\s*세\s*이상', q)]
    lt = [int(n) for n in re.findall(r'(\d+)\s*세\s*미만', q)] + [int(n) + 1 for n in re.findall(r'(\d+)\s*세\s*이하', q)]
    starts = sorted({a for a, _ in rng} | set(ge))
    adj = any(b + 1 in ge or b + 1 in {a2 for a2, _ in rng} for _, b in rng)        # 이어지는 구간(65~74세, 75세 이상)
    adj = adj or any(x in ge or x in {a2 for a2, _ in rng} for x in lt)               # 맞닿은 구간(35세 미만과 35세 이상)
    grouped = len(rng) >= 2 or adj or (len(rng) + len(ge) + len(lt) >= 2 and len(rng) + len(ge) >= 1 and re.search(r'구간|나누|나눠|구분|별로|별 |각각|교차', q))
    if grouped and starts:
        inner = sorted(set(starts[1:]))                                    # 구간의 경계 = 둘째 구간부터의 시작 연령
        low = bool(lt) and min(lt) <= starts[0]                           # 맨 앞에 「…세 미만·이하」 구간이 따로 있음 → 첫 시작 연령도 경계
        if low:
            inner = sorted(set(starts))
        allow = set(starts) | set(lt) | {b + 1 for _, b in rng}
        std = re.findall(r"by=\[?[^)\]]*'(age3|age6|age10)'", c)
        dg = [[int(float(x)) for x in re.findall(r'-?\d+(?:\.\d+)?', m)] for m in re.findall(r"define_group\(\s*'[^']*'\s*,\s*'age'\s*,\s*\[([^\]]*)\]", c)]
        qtxt = ', '.join([f'{a}~{b}세' for a, b in rng] + [f'{n}세 이상' for n in ge])
        if std and not dg and 'define_cond' not in c and inner and not all(set(inner) == set(_AGE_STD[x]) or set(inner) <= set(_AGE_STD[x]) and len(inner) == len([v for v in _AGE_STD[x] if v > starts[0]]) for x in std):
            warn(f"질문이 연령 구간({qtxt})을 정했는데 코드가 표준 연령 구간({', '.join(std)})을 씀. ssda.define_group('이름', 'age', {inner}, [구간 이름…])으로 질문의 구간을 만들어 by 에 쓸 것(맨 앞에 대상 밖 구간의 이름을 하나 더 줌)")
        for bins in dg:
            extra = [b for b in bins if b not in allow]
            lack = [b for b in inner if b not in bins]
            if extra or lack:
                warn(f"질문이 정한 연령 구간({qtxt})과 코드의 구간 경계({bins})가 다름" + (f". 질문에 없는 경계 {extra}를 빼고" if extra else '') + (f" 빠진 경계 {lack}를 넣어" if lack else '')
                     + f" bins={sorted(set(inner) | ({starts[0]} if starts[0] in bins else set()))} 로 고칠 것(구간 이름도 경계에 맞게)")
    # ③ 연령 경계어와 연산자
    for n, w in re.findall(r'(\d+)\s*세\s*(이상|미만|이하|초과)', q):
        n = int(n)
        good, bad = {'미만': ((rf'age\s*<\s*{n}(?!\d)', rf'age\s*<=\s*{n - 1}(?!\d)'), rf'age\s*<=\s*{n}(?!\d)'), '이하': ((rf'age\s*<=\s*{n}(?!\d)', rf'age\s*<\s*{n + 1}(?!\d)'), rf'age\s*<\s*{n}(?!\d)'),
                     '이상': ((rf'age\s*>=\s*{n}(?!\d)', rf'age\s*>\s*{n - 1}(?!\d)'), rf'age\s*>\s*{n}(?!\d)'), '초과': ((rf'age\s*>\s*{n}(?!\d)', rf'age\s*>=\s*{n + 1}(?!\d)'), rf'age\s*>=\s*{n}(?!\d)')}[w]
        if re.search(bad, c) and not any(re.search(g, c) for g in good):
            op = {'미만': f'age < {n}', '이하': f'age <= {n}', '이상': f'age >= {n}', '초과': f'age > {n}'}[w]
            warn(f'질문은 「{n}세 {w}」인데 코드의 연령 조건이 다름. 「{op}」로 고칠 것')
    # ④ 지역 이름과 시도 코드
    names = {n for n in _SIDO if re.search(rf'(?<![가-힣]){n}(?![가-힣]*도별)', q)} | {v for k, v in _SIDO_FULL.items() if k in q}
    metro = bool(re.search(r'수도권', q))
    nums = {int(x) for m in re.findall(r'sido\s*(?:==|!=|(?:not\s+)?in)\s*(\[[^\]]*\]|\d+)', c) for x in re.findall(r'(?<![\w.\'"])\d+', m)}
    strs = set(re.findall(r"['\"]([가-힣]{2,8})['\"]", ' '.join(re.findall(r'sido\s*(?:==|!=|(?:not\s+)?in)\s*(\[[^\]]*\]|[\'"][^\'"]*[\'"])', c))))
    strs = {_SIDO_FULL.get(x, x) for x in strs}
    if re.search(r"define_group\(\s*'[^']*'\s*,\s*'sido'", c):
        warn("시도(sido)는 순서가 없는 코드값이어서 define_group 의 구간으로 묶을 수 없음. 수도권·비수도권은 by='metro2', 다른 묶음은 ssda.define_cond('이름', {'묶음 이름': \"sido in ['서울', '인천', '경기']\"}, other='그 밖')으로 만들 것")
    if metro and 'metro2' not in c and not ({1, 4, 9} <= nums or {'서울', '인천', '경기'} <= strs):
        warn("질문의 「수도권」은 서울·인천·경기임. 수도권·비수도권으로 나누는 분류는 by='metro2', 수도권만 대상이면 where 에 \"sido in ['서울', '인천', '경기']\", 비수도권만 대상이면 \"sido not in ['서울', '인천', '경기']\"를 쓸 것")
    elif names and not metro and nums and not strs:
        want = {_SIDO.index(n) + 1 for n in names}
        if not (want & nums):
            warn('질문의 지역(' + ', '.join(sorted(names)) + ')과 코드의 시도 코드(' + ', '.join(f'{k}={_SIDO[k - 1]}' if 1 <= k <= 17 else f'{k}=없는 코드' for k in sorted(nums)) + ')가 다름. 시도는 이름으로 쓸 수 있음. 예: where 에 "sido == \'' + sorted(names)[0] + '\'"')
    # ⑤ 기준 시점
    y1 = set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)_yn1\b', c)); y2 = set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)_yn2\b', c))
    if re.search(r'12월\s*(기준|말|현재|시점|에도|에 )|연말 기준|12월 31일', q) and not re.search(r'한 번이라도|연간|한 해 동안|연중', q):
        only1 = sorted(v for v in y1 - y2 if core._META.get(v + '_yn2', {}).get('available'))
        if only1:
            warn(f"질문은 12월 기준인데 코드가 연간 기준 변수({', '.join(v + '_yn1' for v in only1)})만 씀. 12월 기준은 {', '.join(v + '_yn2' for v in only1)}")
    elif re.search(r'한 번이라도|연간 기준|한 해 동안|연중', q) and not re.search(r'12월', q):
        only2 = sorted(v for v in y2 - y1 if core._META.get(v + '_yn1', {}).get('available'))
        if only2:
            warn(f"질문은 연간(한 번이라도) 기준인데 코드가 12월 기준 변수({', '.join(v + '_yn2' for v in only2)})만 씀. 연간 기준은 {', '.join(v + '_yn1' for v in only2)}")
    # ⑥ 가구 규모
    if re.search(r'혼자 사는|혼자 사시는|독거|1인 가구', q) and not re.search(r'hnum|hs4', c):
        warn("질문의 「혼자 사는」「1인 가구」는 가구원수 1명임. 대상을 좁히는 조건이면 where 에 hnum == 1 을 넣고, 가구원수별 비교이면 by='hs4'를 쓸 것. 뜻을 되묻지 않음")
    # ⑥-2 대상 조건을 분류 기준으로 바꿔 쓴 경우(질문은 한 집단의 값을 묻는데 표 전체를 냄. 2026-11-17 개발 묶음: 「65세 이상 / 여성 / 혼자 사는 사람」에 성×가구원수 표를 제시)
    if re.search(r'혼자 사는|혼자 사시는|독거|1인 가구', q) and not re.search(r'가구원수별|가구원수에 따라|가구 규모별|인 가구와|인 이상 가구|다인 가구', q) and re.search(r'hs4', c) and not re.search(r'hnum\s*==\s*1|hs4\s*==\s*0', c):
        warn("질문의 「혼자 사는」「1인 가구」는 대상 조건임. by 에 hs4 를 쓰지 말고 where 에 hnum == 1 을 넣어 그 집단의 값만 산출할 것")
    for word, code_, name in (('여성|여자', 2, '여'), ('남성|남자', 1, '남')):
        other = '남성|남자' if code_ == 2 else '여성|여자'
        if re.search(rf'(?<![가-힣])({word})', q) and not re.search(rf'성별|남녀|{other}', q) and re.search(r"by=[^)]*'sex'", c) and not re.search(r'gender\s*==', c):
            warn(f"질문의 「{name}성」은 대상 조건임. by 에 sex 를 쓰지 말고 where 에 gender == {code_} 를 넣어 그 집단의 값만 산출할 것")
    # ⑦ 해당하지 않는 집단
    neg = re.search(r'(받지 않|수급하지 않|가입하지 않|이용하지 않|참여하지 않|미수급|비수급|미가입|미이용|미참여)(?![^.\n]{0,16}(포함|도 분모|까지))', q)
    if neg and not re.search(r'isna\(|not\s*\(|!=|define_cond|notna\(', c):
        out.append(_item('요청 반영', '주의', '질문에 해당하지 않는 집단(받지 않은·가입하지 않은 사람 등)이 적혀 있는데 코드에 그 조건이 보이지 않음. 그 집단이 산출 대상이면 「not (변수 == 1)」로 지정하고, 질문이 요청한 지표를 다른 지표로 바꾸지 않을 것'))
    return out


_COUNT_Q = r'몇\s*명|몇\s*가구|몇\s*사람|인원\s*수|사람\s*수|명\s*수|가구\s*수|(수급|이용|가입|대상|참여|해당|등록)자\s*수|인원(?!\s*(대비|중|가운데))'
_RATE_Q = r'비율|비중|구성비|퍼센트|%|[가-힣](?<!법)률(?![가-힣])|분포|몇\s*프로|차지'
_AGE_WORD = r'노인|고령|어르신|아동|어린이|영유아|유아|영아|청년|청소년|미성년|성인|중장년|장년|중년|생산가능|근로연령|경제활동|학령|초등|중학|고등|대학|은퇴|정년|노년|신생아|아이|애들|자녀|학생|연금 수급 연령|수급 연령'


_AGE_WORD_STRICT = r'노인|고령|어르신|영유아|유아|영아|청년|청소년|미성년|성인|중장년|장년|중년|생산가능|근로연령|경제활동|학령|초등|중학|고등|대학|은퇴|정년|노년|신생아|연령대'


def check_request_extra(q, c, prev=''):
    """질문과 코드의 대조(2026-11-17 독립 검증 2차에서 확인된 유형): 인원 요청에 비율·비율 요청에 인원, 질문에 없는 1인 가구 조건.
    prev 는 같은 대화의 앞선 질문(앞선 질문이 정한 조건은 질문에 있는 것으로 봄)."""
    out = []

    def warn(msg):
        out.append(_item('요청 반영', '경고', msg))
    qa = (prev + ' ' + q) if prev else q
    fns = set(re.findall(r'ssda\.(count|rate|mean|total|quantile|share|rate_by_category|poverty_rate)\(', c))
    # ① 지표의 종류: 인원(가구 수) ↔ 비율
    want_count = re.search(_COUNT_Q, q) and not re.search(_RATE_Q, q) and not re.search(r'평균|중위|합계|총액|금액|빈곤율', q)
    want_rate = re.search(r'비율|[가-힣](?<!법)률(?![가-힣])|몇\s*%|몇\s*퍼센트|몇\s*프로', q) and not re.search(_COUNT_Q, q) and not re.search(r'평균|중위|합계|총액|구성비|분포', q)
    if want_count and fns and fns <= {'rate', 'poverty_rate', 'rate_by_category', 'share'}:
        warn("질문은 인원(가구 수)을 요청했는데 코드가 비율만 산출함. 인원·가구 수는 ssda.count(where='대상 조건', by=…)로 산출할 것(가구 수는 unit='가구'). 질문에 없는 조건을 대상에 더하지 않음")
    if want_rate and fns == {'count'}:
        warn("질문은 비율을 요청했는데 코드가 인원만 산출함. 비율은 ssda.rate('분자 조건', where='대상 조건', by=…)로 산출할 것")
    # ①-2 성 조건: 질문은 한쪽 성만 말했는데 코드의 조건이 반대쪽 성임
    male, female = re.search(r'남성|남자|(?<![가-힣])남아|아버지', q), re.search(r'여성|여자|(?<![가-힣])여아|어머니|임산부|산모', q)
    gc = {{'1': 1, '2': 2, '남': 1, '여': 2}.get(x.strip('\'"')) for x in re.findall(r"gender\s*==\s*('[^']*'|\"[^\"]*\"|\d)", c)}
    if not re.search(r'성별|남녀|양성|남성과 여성|여성과 남성', q) and bool(male) != bool(female) and gc:
        want = 1 if male else 2
        if want not in gc:
            warn(f"질문은 {'남성' if want == 1 else '여성'}을 말했는데 코드의 성 조건이 gender == {3 - want}({'여' if want == 1 else '남'})임. gender == {want} 또는 gender == '{'남' if want == 1 else '여'}' 로 고칠 것(성별 코드: 1=남, 2=여)")
    # ①-3 수급자·이용자를 세거나 그 금액을 내는 산출에 질문에 없는 연령 조건을 더한 경우(제도의 대상 연령을 임의로 넣음. 2026-11-17 독립 검증 2차: 「보육료 지원을 받는 아동이 몇 명」에 age < 6 을 더해 6세 수급자가 빠짐)
    if fns and not (fns & {'rate', 'poverty_rate'}) and re.search(r'_yn\d?\s*==\s*1', c) and not re.search(_AGE_WORD_STRICT, qa):
        nums_q = {int(x) for x in re.findall(r'(\d+)\s*(?:세|살|대(?![가-힣]))', qa)} | {int(b) for _, b in re.findall(r'(\d+)\s*[~∼\-]\s*(\d+)', qa)} | {int(a) for a, _ in re.findall(r'(\d+)\s*[~∼\-]\s*(\d+)', qa)}
        add = [f'age {op} {n}' for op, n in re.findall(r'\bage\s*(>=|<=|>|<|==)\s*(\d+)', c) if not ({int(n) - 1, int(n), int(n) + 1} & nums_q)]
        if add:
            warn(f"질문에 없는 연령 조건({', '.join(dict.fromkeys(add))})이 대상에 들어 있음. 수급자·이용자의 인원이나 금액을 묻는 질문에는 제도의 대상 연령을 임의로 더하지 않음. 질문이 연령을 정하지 않았으면 그 조건을 빼고 다시 실행할 것")
    # ①-4 금액·값이 있는 대상(「임차 보증금이 있는 가구만」「근로소득이 있는 사람」)인데 「변수 > 0」 조건이 없음
    has = re.search(r'(소득|급여|금액|보증금|재산|연금|수당|보험료|납부액|지급액|수령액|지원금|부담금|진료비|이용액|결제금액|본인부담|급여액|세액|임대료|월세)(이|가|을|를)?\s*(조금이라도\s*|한 푼이라도\s*)?(있는|있었던|있던|발생한)\s*(가구|사람|자|인원|개인|경우|대상|노인|청년|근로자|수급자|이용자|가입자|세대)', q)
    if has and fns & {'mean', 'quantile', 'total', 'share', 'count', 'rate'} and not re.search(r'>\s*0(?![\d.])|>=\s*[1-9]|notna\(|_yn\d?\s*==\s*1', c):      # 여부 변수로 대상을 정한 코드는 보지 않음
        warn(f"질문은 「{has.group(0)}」을 대상으로 했는데 코드에 값이 있는 대상만 남기는 조건이 없음. where 에 '해당 금액 변수 > 0'을 넣어 다시 실행할 것")
    # ② 질문에 없는 1인 가구 조건(가구주 조건을 hnum == 1 로 쓴 경우 포함)
    if re.search(r'hnum\s*==\s*1(?!\d)|hs4\s*==\s*0(?!\d)', c) and not re.search(r'1\s*인|혼자|독거|단독|홀로|홀몸|한\s*명|1\s*명|가구원\s*수|가구\s*규모', qa):
        warn("코드의 hnum == 1 은 1인 가구 조건인데 질문에 1인 가구를 가리키는 말이 없음. 가구주 조건이 아님: 가구 단위 집계(unit='가구')는 가구주 행으로 계산하므로 "
             "「가구주가 …인 가구」는 where 에 가구주의 연령·성·수급 조건만 쓰면 됨. 질문에 없는 조건이면 빼고 다시 실행할 것")
    return out


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
    for r in list((out.get('results') or {}).values())[:3]:      # 산출 정의의 풀이(코드값·변수명을 한글로): 질문의 지표·대상·분류와 맞는지 모형이 다시 보게 함
        if r.get('call'):
            try:
                lines.append('- 산출 정의: ' + def_ko(r['call']) + ' — 질문이 요청한 지표·대상·분류와 다르면 코드를 고쳐 다시 실행할 것')
            except Exception:                                # noqa: BLE001 — 풀이 오류가 산출을 막지 않게 함
                pass
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
    if out.get('ok') and not std and not out.get('results') and not out['figures']:    # 변수 찾기 등을 print 없이 부른 경우(2026-11-16, 실제 모형이 빈 출력을 「결과 없음」으로 판단함)
        parts.append("안내: 출력이 없음. 결과는 print()로 감싸야 보임. 예: print(ssda.find_vars('가구원수'))")
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
            'unseen_vars': sorted({v for s in ran if s.get('origin') != 'user' for v in s.get('pre', {}).get('unseen', [])}),     # 이용자가 제시한 코드(origin=user)의 변수는 세지 않음
            'used_vars': sorted({v for s in ran for v in s.get('pre', {}).get('used', [])}),
            'warnings': [c['code'] for c in flat if c['level'] == '경고'], 'cautions': [c['code'] for c in flat if c['level'] == '주의'] + [r['code'] for r in (last.get('req') or [] if last else []) if r['level'] == '주의'],
            'terms': [{'term': r['term'], 'level': r['level'], 'used': r.get('used', [])} for r in (last.get('req') or [] if last else []) if r['code'] == '용어'],
            'suppressed': sum(c.get('n_sup', 0) for c in flat if c['code'] == '억제'), 'cells': sum(c.get('n_cells', 0) for c in flat if c['code'] == '억제'),
            'overall': [c['msg'] for c in flat if c['code'] == '전체 값'], 'figures': len(figs), 'figure_issues': [i for f in figs for i in f['issues']],
            'ungrounded_numbers': answer_bad or [], 'answer_numbers': n_answer_numbers, 'answer_retried': retried,
            'defs': [_def_text(r.get('call') or {}) for r in ((last.get('results') or {}).values() if last else [])][:4],
            'defs_ko': [_quiet(def_ko, r.get('call') or {}) for r in ((last.get('results') or {}).values() if last else [])][:4]}


_FN_KO = {'rate': '비율', 'count': '인원', 'mean': '평균', 'total': '합계', 'quantile': '분위수', 'share': '구성비'}


def _def_text(call):
    """집계 호출 1건의 산출 정의를 한 줄로(검증 요약에 붙여 이용자가 질문과 대조하게 함. 2026-11-17 독립 검증: 조건 누락·다른 구간이 응답만으로는 드러나지 않았음)."""
    a = call.get('args') or {}
    parts = [_FN_KO.get(call.get('fn'), str(call.get('fn')))]
    if a.get('num'):
        parts.append(f"분자 [{a['num']}]")
    if a.get('var'):
        parts.append(f"변수 [{a['var']}]" + (f" {int(round(float(a['q']) * 100))}% 분위" if a.get('q') is not None else ''))
    parts.append(f"대상 [{a.get('where') or '전체'}]")
    if a.get('by'):
        parts.append(f"분류 [{', '.join(a['by'])}]")
    parts.append('가구 단위' if a.get('unit') in ('가구', 'hh', 'household') else '개인 단위')
    return ' · '.join(parts)


_OPS = {'==': '=', '!=': '≠', '>=': '≥', '<=': '≤', '>': '>', '<': '<', 'in': '=', 'not in': '≠'}


def explain(expr):
    """조건식의 변수와 코드값을 한글 이름과 항목 이름으로 풀어 적는다(모형과 이용자가 질문과 대조하게 함).
    예: 'gender == 2 and bp_yn1 == 1 and age >= 65' → '성별 = 여; 기초연금 수급여부(연간) 해당; 만 나이 ≥ 65'
    2026-11-17 독립 검증 2차: 「남성이 차지하는 비율」에 gender == 2 를 쓴 코드가 「남성 비율」이라는 이름으로 제시됨."""
    core._load_meta()
    out = []
    for neg, v, op, val in re.findall(r"(not\s*\(\s*)?\b([A-Za-z_]\w*)\s*(==|!=|>=|<=|>|<|not\s+in|in)\s*(\[[^\]]*\]|'[^']*'|\"[^\"]*\"|-?\d+(?:\.\d+)?)", str(expr or '')):
        m = core._META.get(v)
        if not m:
            continue
        name = m.get('name_ko') or v
        labs = m.get('labels') or {}
        op = re.sub(r'\s+', ' ', op)
        if re.search(r'_yn\d?$', v) and op == '==' and val == '1':
            out.append(f"{name} {'해당 없음' if neg else '해당'}")
            continue
        items = re.findall(r"'([^']*)'|\"([^\"]*)\"|(-?\d+(?:\.\d+)?)", val)
        vals = [a or b or labs.get(c, labs.get(str(int(float(c))) if c and float(c).is_integer() else c, c)) for a, b, c in items]
        sym = _OPS[op]
        if neg:
            sym = {'=': '≠', '≠': '='}.get(sym, sym) if sym in ('=', '≠') else sym
        out.append(f"{name} {sym} {'·'.join(str(x) for x in vals)}" + (' (부정)' if neg and sym not in ('=', '≠') else ''))
    for v in re.findall(r'(?:isna|notna)\(\s*([A-Za-z_]\w*)\s*\)', str(expr or '')):
        if v in core._META:
            out.append(f"{core._META[v].get('name_ko') or v} 값 {'없음' if re.search(rf'isna\(\s*{v}', str(expr)) else '있음'}")
    return '; '.join(dict.fromkeys(out))


def def_ko(call):
    """집계 호출 1건의 산출 정의를 한글로 풀어 한 줄로."""
    core._load_meta()
    a = call.get('args') or {}
    ko = lambda v: (core._META.get(v, {}).get('name_ko') or (core._G[v][2] if v in core._G else v))
    parts = [_FN_KO.get(call.get('fn'), str(call.get('fn')))]
    if a.get('num'):
        parts.append(f"분자: {explain(a['num']) or a['num']}")
    if a.get('var'):
        parts.append(f"변수: {ko(a['var'])}" + (f" {int(round(float(a['q']) * 100))}% 분위" if a.get('q') is not None else ''))
    parts.append(f"대상: {(explain(a['where']) or a['where']) if a.get('where') else '전체(조건 없음)'}")
    if a.get('by'):
        parts.append('분류: ' + ', '.join(f"{ko(b)}({' / '.join(str(x) for x in core._G[b][1][:8])})" if b in core._G else ko(b) for b in a['by']))
    parts.append('가구 단위(가구주 기준)' if a.get('unit') in ('가구', 'hh', 'household') else '개인 단위')
    return ' · '.join(parts)


def footer(v):
    """이용자에게 보여 주는 「검증 요약」. 모형이 쓰지 않고 하네스가 만든다."""
    if not v['n_runs']:
        return ''
    L = ['검증 요약(자동 점검)']
    L.append(f"- 실행: 코드 {v['n_ok']}회 실행" + (f", 수정 {v['n_runs'] - v['n_ok']}회" if v['n_runs'] > v['n_ok'] else '') + (f", 실행 전 점검에서 차단 {v['n_blocked']}회" if v['n_blocked'] else ''))
    if v['used_vars']:
        L.append(f"- 변수: 사용 변수 {len(v['used_vars'])}개" + (' 모두 정의를 확인한 변수임' if not v['unseen_vars'] else f" 중 {', '.join(v['unseen_vars'])}은 정의 확인 없이 사용됨"))
    for d, k in zip(v.get('defs') or [], (v.get('defs_ko') or []) + [None] * 4):
        L.append('- 산출 정의: ' + d + (f' ⇒ {k}' if k else ''))
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
