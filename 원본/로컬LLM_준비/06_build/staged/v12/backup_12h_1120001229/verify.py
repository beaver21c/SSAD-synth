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
import json
import os
import math
import re
from pathlib import Path

import numpy as np

from . import core
from .core import ST_COMP, ST_NA, ST_OK, ST_SUP

def v9():
    """규칙 묶음 9(독립 검증 4차 뒤의 조치)를 쓰는지. 환경변수 SSDA_RULESET(조립기가 설정 verify.ruleset 으로 정함, 기본 8)으로 켠다.
    조치: 전체·구성 변수 관계, 낱말 전체 일치 우선, 영문 질문의 조건어 대조, 자료에 없는 항목의 안내, 조건식의 함수·괄호 안내, 한 살 단위 구간.
    실행기(새 프로세스)의 산출 점검도 같은 환경변수를 읽는다."""
    try:
        return int(os.environ.get('SSDA_RULESET') or 8) >= 9
    except ValueError:
        return False


def v10():
    """규칙 묶음 10(독립 검증 5차 뒤의 보완)을 쓰는지. 9의 조치를 포함한다.
    보완: 후속 질문의 변수 카드, 정의를 확인하지 않은 변수의 실행 전 확인, 금액 단위 대조, 기준 시점 규칙을 이번 차례에 새로 쓴 변수로 한정, 문자열을 이어 만든 조건식의 괄호 점검,
    자료에 없다는 거절 전의 변수 찾기, 용어 안내의 적용 범위."""
    try:
        return int(os.environ.get('SSDA_RULESET') or 8) >= 10
    except ValueError:
        return False


def v11():
    """규칙 묶음 11(5차 개발 측정 뒤의 보완)을 쓰는지. 10의 조치를 포함한다.
    보완: 정의 미확인 변수 안내의 코드값, 금액 근거 대조의 출처를 질문·참고 자료로 한정(조립기), 닫히지 않은 코드 블록의 실행(조립기)."""
    try:
        return int(os.environ.get('SSDA_RULESET') or 8) >= 11
    except ValueError:
        return False



def v12e():
    """규칙 묶음 12e(12d 개발 점검의 보완). 규칙 묶음 12에 포함되며, 규칙 묶음 12 와 같은 조건(SSDA_RULESET >= 12)에서 작동함."""
    return v12()


def v12f():
    """규칙 묶음 12f(12e 개발 점검의 보완). 규칙 묶음 12에 포함되며, 규칙 묶음 12 와 같은 조건(SSDA_RULESET >= 12)에서 작동함."""
    return v12()


def v12():
    """규칙 묶음 12(6차 판정·규칙 묶음 11 개발 측정 뒤의 보완)를 쓰는지. 11의 조치를 포함한다.
    보완: 붙임 문서의 제도를 변수 카드 검색·제도별 변수 목록·관문에 씀(조립기), 여러 항목 요청의 일괄 거절 전 점검(조립기), 문맥 한도 처리에서 질문을 지우지 않음(조립기),
    금액 상수의 자릿수 대조, 「1인당」을 가구원 수로 나눈 코드, 월액 변수를 12로 나눈 코드, 정의 미확인 변수 안내의 되묻기 방지, 표준 분류의 변수 찾기(core), 제도 기준값 카드."""
    try:
        return int(os.environ.get('SSDA_RULESET') or 8) >= 12
    except ValueError:
        return False

_REL = None


def relations():
    """전체·구성 변수 관계(ssda/data/relations.json. 01_knowledge/build_relations.py 가 만든다).
    돌려주는 값  {'total_of': {구성 변수: 전체 변수}, 'parts': {전체 변수: [구성 변수…]}, 'words': {전체 변수: [구성 변수를 가리키는 낱말…]}}"""
    global _REL
    if _REL is None:
        p = Path(os.environ.get('SSDA_RELATIONS') or core.PKG / 'data' / 'relations.json')
        try:
            rows = json.loads(p.read_text(encoding='utf-8')).get('totals') or []
        except Exception:                                   # noqa: BLE001 — 관계 파일이 없으면 이 조치만 빠짐
            rows = []
        _REL = {'total_of': {x: r['total'] for r in rows for x in list(r['parts']) + list(r.get('not_parts') or [])}, 'parts': {r['total']: list(r['parts']) for r in rows},
                'words': {r['total']: list(r.get('part_words') or []) for r in rows}, 'not_parts': {r['total']: list(r.get('not_parts') or []) for r in rows}}
    return _REL


def totals_for(vars_, question=''):
    """참고 자료에 구성 변수만 있고 전체 변수가 빠진 경우 덧붙일 전체 변수(질문이 구성 유형을 지정했으면 덧붙이지 않음).
    2026-11-18 독립 검증 4차: 「연간 입원 재원일수」에 유형별 변수 4개와 응급실 변수만 제시되어 그 합을 답으로 냄(응급실 재원일수는 전체에 더하는 항목이 아니어서 전체 변수 nhi_in_dur 와 값이 다름. 조용한 오답 4차례)."""
    rel = relations(); vs = set(vars_); out = []
    for v in vars_:
        t = rel['total_of'].get(v)
        if t and t not in vs and t not in out and not any(w in (question or '') for w in rel['words'].get(t, [])):
            out.append(t)
    return out


def relation_note(totals):
    core._load_meta()
    ko = lambda v: core._META.get(v, {}).get('name_ko', '')
    rel = relations()
    return '■ 변수 관계(전체와 구성)\n' + '\n'.join(
        f"{t}({ko(t)})는 유형별 변수({', '.join(rel['parts'][t][:5])})를 합한 전체 값임. 질문이 유형(" + '·'.join(rel['words'].get(t, [])[:5])
        + ")을 지정하지 않았으면 유형별 변수를 더하지 말고 전체 변수를 씀"
        + (f". {', '.join(f'{x}({ko(x)})' for x in rel['not_parts'][t][:2])}는 전체에 더하는 항목이 아님" if rel['not_parts'].get(t) else '') for t in totals)


AGG = {'rate', 'mean', 'total', 'quantile', 'count', 'share', 'poverty_rate'}
WORDS = {'and', 'or', 'not', 'in', 'isna', 'notna'}
BASIC = {'age', 'gender', 'sido', 'hnum', 'head'}             # 시스템 프롬프트·자료 규약에 늘 실리는 기본 변수
AGE_BY = {'age6', 'age3', 'age10'}


_MEAS_KO = {'rate': '비율', 'mean': '평균', 'quantile': '분위값'}


def _item(code, level, msg, **kw):
    return {'code': code, 'level': level, 'msg': msg, **kw}


def _fmt(v, unit):
    return (f'{v:,.1f}' if unit in ('%', '일') or abs(v) < 100 else f'{v:,.0f}') + unit


def _idents(expr):
    expr = re.sub(r"'[^']*'|\"[^\"]*\"", ' ', str(expr or ''))          # 조건식 안의 항목 이름(문자열)은 변수가 아님. 예: sido == '충북'
    return [t for t in re.findall(r'[A-Za-z_][A-Za-z0-9_]*', expr) if t not in WORDS]


def _quiet(fn, *a, **k):
    core._QUIET = True
    core._AUDIT_ONLY = v12()                            # 규칙 묶음 12: 점검용 재계산에도 차분 점검 적용(2026-11-19 개발 측정: 보충 억제된 전체 평균이 「참고(전체 값)」 줄로 드러남)
    try:
        return fn(*a, **k)
    except (core.ControlError, core.QueryError):
        return None
    finally:
        core._QUIET = False
        core._AUDIT_ONLY = False


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
    elif n_ok == 0 and n_na == n and v12e():                # 규칙 묶음 12e: 0명으로 결론 내기 전에 조건을 나누어 확인(6차 문서 12d: 금액 변수 == 연액 조건, 합계 변수 조건의 「대상 없음」을 실제 0명으로 답함)
        out.append(_item('대상 없음', '주의', '조건에 해당하는 대상이 자료에 한 명도 없음(억제가 아님). 0명으로 결론 내기 전에 조건의 각 부분을 따로 세어(ssda.count) 어느 조건에서 대상이 사라지는지 확인할 것. '
                                         '금액 변수를 특정 금액과 같다(==)로 비교한 조건, 단위가 다른 기준값(원·만원), 자료에 없는 코드값, 함께 성립하지 않는 자격·구분이면 대상이 없게 나옴. '
                                         '확인한 뒤에도 조건이 질문과 같으면 「결과」에 「해당하는 대상이 없음」으로 적고 그 사유를 밝힘. 「억제」「최소 관측 수 미달」로 설명하지 않음'))
    elif n_ok == 0 and n_na == n and v9():                  # 조건에 해당하는 대상이 한 명도 없는 경우는 억제가 아님(2026-11-18 독립 검증 4차: 함께 성립하지 않는 자격 조건의 「대상 없음」을 억제로 설명함)
        out.append(_item('대상 없음', '주의', '조건에 해당하는 대상이 자료에 한 명도 없음(억제가 아님). 함께 성립하지 않는 조건(서로 배타적인 자격·구분)을 묶은 것인지 확인할 것. '
                                         '조건이 질문과 같다면 「결과」에 「해당하는 대상이 없음」으로 적고 그 사유(전제가 자료의 구분과 맞지 않음 등)를 밝힘. 「억제」「최소 관측 수 미달」로 설명하지 않음'))
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
            item = _item('전체 값', '참고', (f"분류 구분 없이 대상 전체로 계산한 {_MEAS_KO.get(fn, '값')} {_fmt(tv, res.unit)}(집단별 값의 합이나 나머지의 비율이 아님)" if v12f()
                                            else f'분류하지 않은 전체 값 {_fmt(tv, res.unit)}'), value=tv)      # 규칙 묶음 12f: 6차 문서 12e W4-D06v 에서 전체 빈곤율 29.9%를 「나머지 70%는 분류되지 않음」으로 읽음
            if fn in ('rate', 'mean') and n_ok == n and n > 1 and not (ok.min() - 0.11 <= tv <= ok.max() + 0.11):
                item = _item('전체 값', '주의', f'전체 값 {_fmt(tv, res.unit)}이 집단별 값의 범위({_fmt(ok.min(), res.unit)}~{_fmt(ok.max(), res.unit)}) 밖에 있음. 분류 누락 또는 조건식을 확인할 것', value=tv)
            out.append(item)
    if v12f() and by and fn in ('count', 'total') and n_sup == 0 and n_ok > 1 and n_ok == n - n_na and not nb:      # 규칙 묶음 12f: 붙임 표의 「계」(6차 문서 12e W3-D04·W4-D04)
        tot_c = core.sig3(float(df.loc[df['상태'] == ST_OK, '값'].sum()))
        miss_c = any(c['code'] == '분류 누락' for c in out)
        out.append(_item('칸 합계', '참고', f'표의 칸 합계 {_fmt(tot_c, res.unit)}. 붙임 표의 「계」에는 칸과 같은 기준의 이 값을 씀'
                         + ('(분류 기준에 값이 없어 표에서 빠진 대상은 들지 않음. 그 사실은 「유의 사항」에 밝힘)' if miss_c else
                            '. 분류 기준에 값이 없는 대상은 없음. 표시된 칸 값을 더한 값과 전체 값의 차이는 칸 값의 반올림에서 생긴 것이므로 빠진 대상이나 차이로 적지 않음'), value=tot_c))      # 5차 과제 12e W2-09: 반올림 차이 6,000명을 「값이 없어 빠진 장애인」으로 적음
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
        elif v10() and v.startswith('p_') and v[2:] in core._META and not core._META[v[2:]].get('available', True):
            out['empty'].append(v)                          # 값이 없는 사업의 금액을 옮긴 파생 변수(값이 모두 0). 2026-11-18 5차: 이 변수로 「수급자 0명」을 실제 실적처럼 답함
        elif seen is not None and v not in seen and v not in BASIC:
            out['unseen'].append(v)
    if v9() and any(v in _EXPR_FN for v in out['unknown']):      # 함수 안에 적은 변수의 가구 합산 변수를 알려 줌
        hs = []
        for v in dict.fromkeys(names):
            if v.startswith('h_') and v in core._META:
                hs.append(f'{v} 는 이미 가구 합산 변수이므로 함수 없이 「{v} > 0」처럼 씀')
            else:
                h = next((x for x in ('h_' + v[2:] if v.startswith('p_') else None, 'h_' + v) if x and (core._META.get(x) or {}).get('available', True) and x in core._META), None)
                if h:
                    hs.append(f'{v} 의 가구 합산 변수는 {h}')
        if hs:
            out['agg_hint'] = '. ' + ' / '.join(hs[:3])
    return out


_EXPR_FN = {'any', 'all', 'max', 'min', 'sum', 'len', 'abs', 'round', 'mean', 'count', 'nunique', 'groupby', 'transform', 'np', 'pd'}


def lint_error(pre):
    """실행하지 않고 돌려보낼 오류 문구(없는 변수·값이 없는 변수가 있을 때)."""
    msg = []
    for v, sim in pre['unknown'].items():
        if v9() and v in _EXPR_FN:                          # 조건식 안에 쓴 함수 이름(2026-11-18 독립 검증 4차: 「가구원 중 누구라도」를 any()·max()·sum()으로 네 번 적다가 값을 내지 못함)
            msg.append(f"조건식에는 {v}() 같은 함수를 쓸 수 없음(비교, 사칙연산, and·or·not, isna()·notna(), in 만 됨). 가구원 가운데 한 명이라도 해당하는 가구는 "
                       "가구 합산 변수(h_ 로 시작)가 있을 때 「h_변수 > 0」과 unit='가구'로 산출하고, 여러 변수의 합은 ssda.define_sum()으로 만듦. "
                       '가구 합산 변수가 없는 항목은 이 도구로 가구원 단위 조건을 낼 수 없으므로 「요청 처리 불가」로 답함' + (pre.get('agg_hint') or ''))
            continue
        msg.append(f"없는 변수: {v}." + (f" 비슷한 이름: {', '.join(sim)}." if sim else '') + ' ssda.find_vars()로 변수명을 확인할 것')
    for v in pre['empty']:
        if v10():
            m = core._META.get(v) or {}
            msg.append(f"{v}({m.get('name_ko', '')})은 변수 사전에는 있으나 이 자료에 값이 수록되지 않은 사업의 변수임. 0이나 결측으로 나오는 값은 실제 실적이 아님. 질문이 이 사업 자체를 묻는 것이면 "
                       '다른 사업의 변수로 바꿔 산출하지 말고 「요청 처리 불가」로 이 자료에 값이 없음을 밝히고 대신 볼 수 있는 변수를 「가능한 대안」에 적을 것')
            continue
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


def precheck_error(held):
    """요청 대조에서 대상을 바꾸는 경고가 붙은 코드를 실행 전에 돌려보낼 때의 문구(조립기의 precheck 가 쓴다).
    대상이 어긋난 산출을 먼저 표시하면 고친 산출이 차분 점검에 걸려 가려지므로(2026-11-18 독립 검증 3차: 연간 기준으로 먼저 산출한 뒤 12월 기준으로 고친 결과가 가려짐), 표시하기 전에 고치게 한다."""
    return ('실행하지 않음(질문과 코드의 대상이 어긋나 실행 전에 돌려보냄) — ' + ' / '.join(r['msg'] for r in held)
            + ' / 위 내용대로 고친 코드를 다시 낼 것. 질문이 이 코드의 조건을 요구한 것이 분명하면 같은 코드를 그대로 다시 내면 실행함')


def empty_programs(question):
    """질문에 이름이 나온 사업 가운데 변수 사전에는 있으나 이 자료에 값이 없는 사업(모든 변수의 값이 없음). 참고 자료에 「값이 없는 사업」 안내를 붙일 때 쓴다(규칙 묶음 10).
    2026-11-18 독립 검증 5차: 값이 없는 사업(청소년한부모 아동양육비 등)의 요청에 다른 급여의 값을 대신 내거나 값이 없음을 밝히지 않음. 값이 있는 변수만 검색되어 모형이 그 사업의 존재를 알 수 없었음."""
    core._load_meta()
    q = re.sub(r'\s+', '', re.sub(r'```.*?```', ' ', question or '', flags=re.S))
    prog = {}
    for v, m in core._META.items():
        p_ = m.get('program') or ''
        if p_ and str(m.get('grade', '')) != '제외':
            prog.setdefault(p_, []).append(bool(m.get('available', True)))
    live = [re.sub(r'[\s()·\-]+', '', k) for k, av in prog.items() if any(av)]
    split = lambda n: {w for w in re.split(r'[^0-9A-Za-z가-힣]+', n) if len(w) >= 2}
    live_words = [split(k) for k, av in prog.items() if any(av)]
    out = []
    for name, av in prog.items():
        if any(av):
            continue
        words = [w for w in re.split(r'[^0-9A-Za-z가-힣]+', name) if len(w) >= 2]
        if not words:
            continue
        hit = [w for w in words if w in q]                  # 낱말 전체가 질문에 있어야 함(앞부분만 맞는 것은 세지 않음: 「장애인」과 「장애인직업재활시설」)
        flat = re.sub(r'[\s()·\-]+', '', name)
        # 값이 있는 사업의 이름이 이 사업 이름의 일부이고 질문에 그 이름만 있으면(「한부모가족지원 아동양육비」 ↔ 「청소년 한부모가족지원 아동양육비」) 낱말이 모두 있어야 이 사업으로 봄
        need_all = any(lw and lw < set(words) and all(w in q for w in lw) for lw in live_words)
        if need_all and len(hit) < len(words):
            continue
        if len(hit) >= max(1, -(-2 * len(words) // 3)) and not any(flat in x and flat != x for x in live):
            out.append(name)
    return out[:3]


def empty_program_note(names):
    return ('■ 값이 없는 사업\n' + ', '.join(f'「{n}」' for n in names) + '은 변수 사전에는 있으나 이 자료에 값이 수록되지 않은 사업임. 질문이 이 사업의 인원·금액을 묻는 것이면 이름이 비슷한 다른 급여·사업의 값으로 대신하지 말고 '
            '「요청 처리 불가」로 이 자료에 값이 없음을 밝히며, 대신 볼 수 있는 변수가 있으면 「가능한 대안」에 그 차이와 함께 적을 것')


def redact_numbers(text, numbers):
    """응답 문장에서 실행 결과에 없는 수치(단위가 붙은 것)를 가린다. 억제된 칸이 있는 산출에서 다시 쓰게 한 뒤에도 남은 값에만 쓴다(규칙 묶음 10).
    2026-11-18 독립 검증 5차: 억제된 비율을 표시된 두 인원으로 계산해 「100%」로 적은 응답이 노출로 판정됨."""
    out = text or ''
    for n in numbers or []:
        pat = re.escape(n).replace(r'\,', ',?')
        out = re.sub(rf'(?<![\d.,]){pat}(?:\.0+)?\s*(%|퍼센트|명|가구|세대|원|만원|만 원|억원|건|일|개월)', '[표시하지 않는 값]', out)
    return out


def unseen_error(unseen):
    """이 대화에서 정의를 본 적이 없는 변수를 쓴 코드를 실행 전에 돌려보낼 때의 문구(조립기의 규칙 묶음 10).
    2026-11-18 독립 검증 5차: 이름을 짐작해 쓴 변수(p_dinc = 가처분소득)를 일용소득으로 알고 산출해 값을 제시함. 실행 뒤의 「변수 주의」로는 막지 못함."""
    core._load_meta()
    rows = []
    for v in unseen:
        m = core._META.get(v) or {}
        labs = m.get('labels') or {}
        rows.append(f"{v} = {m.get('name_ko', '')}" + (f"(사업: {m['program']})" if m.get('program') and m['program'] != m.get('name_ko') else '') + (f", 단위 {m['unit']}" if m.get('unit') else '')
                    + (f", 코드값 {'; '.join(f'{k}={x}' for k, x in list(labs.items())[:10])}" if v11() and labs else ''))
    if v12():                                           # 6차 주기 개발 측정: 이 안내 뒤 변수를 찾지 않고 「확인 필요」로 되물어 값을 내지 못한 차례(맞춤돌봄)
        return ('실행하지 않음(정의를 확인하지 않은 변수) — 이 코드의 변수 가운데 참고 자료나 변수 찾기 결과에서 뜻을 본 적이 없는 것: ' + ' / '.join(rows)
                + ' / 이 변수의 이름과 코드값이 질문이 말한 제도·항목·구분과 같은지 하나씩 대조할 것. 같으면 같은 코드를 그대로 다시 내면 실행함. 이름의 제도가 다르거나 코드값이 다르면 '
                  "되묻지 말고 다음 코드에서 print(ssda.find_vars('질문의 제도·항목 이름'))로 맞는 변수를 찾은 뒤 고칠 것. 변수명·코드값을 짐작해 쓰지 않음")
    if v11():                                           # 5차 개발 측정 2회차: 코드값 없이 이름만 알려 주자 모형이 코드를 확인하지 않고 같은 코드를 다시 냄(부부 수급 유형, 맞춤돌봄 → 장기요양)
        return ('실행하지 않음(정의를 확인하지 않은 변수) — 이 코드의 변수 가운데 참고 자료나 변수 찾기 결과에서 뜻을 본 적이 없는 것: ' + ' / '.join(rows)
                + ' / 이 변수의 이름과 코드값이 질문이 말한 제도·항목·구분과 같은지 하나씩 대조할 것. 같으면 같은 코드를 그대로 다시 내면 실행함. 이름의 제도가 다르거나 코드값이 다르면 '
                  "print(ssda.find_vars('핵심 낱말'))로 맞는 변수를 찾아 고칠 것. 변수명·코드값을 짐작해 쓰지 않음")
    return ('실행하지 않음(정의를 확인하지 않은 변수) — 이 코드의 변수 가운데 참고 자료나 변수 찾기 결과에서 뜻을 본 적이 없는 것: ' + ' / '.join(rows)
            + ' / 질문이 말한 항목과 같은 뜻이면 같은 코드를 그대로 다시 내면 실행함. 다른 뜻이면 print(ssda.find_vars(\'핵심 낱말\'))로 맞는 변수를 찾아 고칠 것. 변수명을 짐작해 쓰지 않음')


_REFUSE_ABSENT = re.compile(r'자료에[^.\n]{0,30}없|변수[가는이]?[^.\n]{0,12}없|사전에 없|수록되어 있지 않|확인할 수 없음')
_REFUSE_CONTROL = re.compile(r'개인 단위|개인별|명단|식별|억제|최솟값|최댓값|최대값|최소값|반출|통제|상위 \d|하위 \d|원자료|행 단위|목록')


def refuse_gate(reply, question):
    """변수 찾기를 실행하지 않고 「자료에 없음」을 사유로 거절한 응답인지(출력 통제에 따른 거절은 대상이 아님). 조립기의 규칙 묶음 10 이 쓴다.
    2026-11-18 독립 검증 5차: 자료에 있는 항목(고용보험료, 연간 가입 여부)을 찾아보지 않고 없다고 답한 차례가 있었음."""
    head = (reply or '')[:700]
    return bool('요청 처리 불가' in head[:200] and _REFUSE_ABSENT.search(head) and not _REFUSE_CONTROL.search(head) and not _REFUSE_CONTROL.search(question or ''))


def refuse_gate_note(cand):
    return ('[검증 결과]\n- 확인(거절 전 점검): 변수 찾기를 실행하지 않고 자료에 없다고 답함. 질문의 낱말로 변수 사전을 찾은 후보: '
            + candidates_note(cand).replace('변수명을 짐작해 바꾸지 말 것. 질문의 낱말로 변수 사전을 찾은 후보: ', '')
            + '. 질문이 말한 항목이 후보에 있거나 변수 찾기로 확인되면 산출하고, 확인해도 없으면 「요청 처리 불가」를 그대로 다시 적을 것. 질문의 배경·목적을 적은 말은 산출 조건이 아님')



# ── 규칙 묶음 12: 붙임 문서·여러 항목 요청(2026-11-19, 6차 판정의 기록) ──
_ENUM = re.compile(r'(?:^|[\s(])(?:\d{1,2}[).]|[①-⑩]|\(\d{1,2}\)|[가-하][).])(?=\s)', re.M)


def multi_items(text):
    """요청 문장·붙임 문서에 번호를 붙인 항목이 몇 개 있는지(「1)」「①」「(1)」「가.」)."""
    return len(_ENUM.findall(text or ''))


def multi_gate_note(cand=()):
    """붙임 문서·여러 항목 요청에서 실행 없이 요청 전체를 거절하거나 되물은 응답을 한 번 돌려보내는 문구(조립기의 규칙 묶음 12).
    2026-11-18 독립 검증 6차: 원판 문서 32개 가운데 14개에서 1차례를 통째로 거절했고, 값 없음 39항목 가운데 25항목은 변수 찾기 없이 「자료에 없음」으로 거절한 것."""
    return ('[검증 결과]\n- 확인(여러 항목 요청의 점검): 실행한 코드 없이 요청 전체를 거절하거나 되물음. 항목을 하나씩 다시 볼 것. '
            '① 질문이 처리해 달라고 한 붙임 문서의 항목은 이용자의 요청임 ② 산출할 수 있는 항목은 모두 산출하고, 산출할 수 없거나 응하지 않는 항목만 그 사유를 적음. '
            '한 항목을 산출할 수 없다는 이유로 다른 항목을 거절하거나 보류하지 않음 ③ [참고 자료]의 「붙임 문서의 제도와 변수」 목록과 변수 카드에서 변수를 고르고, '
            "목록에 없는 제도는 print(ssda.find_vars('제도 이름'))로 찾은 뒤에만 「자료에 없음」으로 적음 ④ 연령은 age(자료의 기준 시점 연령)로 산출하고 기준일 차이는 「유의 사항」에 적음 "
            '⑤ 여러 항목은 코드 블록 하나에서 함께 산출할 수 있음. '
            + (candidates_note(cand).replace('변수명을 짐작해 바꾸지 말 것. ', '') + '. ' if cand else '')
            + '개인 단위 조회처럼 출력 통제에 해당하는 항목은 그대로 응하지 않음. 모든 항목이 산출할 수 없거나 응할 수 없는 항목이면 앞의 답을 그대로 다시 적을 것')


_ABS_PAT = (re.compile(r'「([^」\n]{2,24})」[^.\n「]{0,20}?(?:변수|항목|정보|값)[가-힣]*\s*(?:가|이|은|는)?\s*(?:\[참고 자료\]에\s*|자료에\s*|변수 사전에\s*|따로\s*|별도로\s*)?(?:없|보이지 않|존재하지 않)'),
            re.compile(r'([가-힣·]{2,12}(?:\s[가-힣·]{2,12})?)\s*(?:여부|정보|변수|항목|자료)(?:\s*(?:변수|정보|항목))?(?:[는은이가도]|나|를|을)?\s*(?:별도로\s*|따로\s*|자료에서\s*|자료로\s*|자료에\s*|\[참고 자료\]에\s*)?'
                       r'(?:구분되지 않|구분할 수 없|구분이 안|확인할 수 없|알 수 없|없음|없어|없으며|없고|없다|존재하지 않)'))
_ABS_STOP = re.compile(r'^(여부|구분|및|또는|그리고|등|자료|변수|정보|항목|값|해당|관련|별도|따로|이|그|이런|해당하는|나타내는)')
_ABS_GENERIC = {'지급액', '지원액', '지원금', '보험료', '급여액', '수급자', '가입자', '대상자', '이용자', '금액', '인원', '여부', '기간', '시점', '연령', '가구원수', '가구원', '소득',
                '급여', '지원', '사업', '수당', '연금', '보험', '수급', '가입', '이용', '실적', '횟수', '일수', '구분', '유형', '종류', '기준', '대상', '본인', '부담', '본인부담', '적용', '시행', '제도'}


def absent_claims(reply, used=()):
    """응답이 「자료에 없음·구분할 수 없음」이라고 한 이름 가운데 변수 사전의 한글 이름에 그대로 든 것 → [(이름, [(변수, 한글 이름)…])]. 규칙 묶음 12d.
    5차 과제 최종판: 「원천징수」「일용소득」 변수가 있는데 없다고 하고 다른 변수로 산출하거나 거절함. 이름의 낱말이 모두 한 변수의 한글 이름에 있어야 함(「월별 보험료」처럼 일부만 맞으면 보지 않음)."""
    core._load_meta()
    absent = {n for e in _glossary() if e.get('id') == 'absent_2022' for n in (e.get('terms') or []) + (e.get('aliases') or [])}
    used = set(used or ())
    used_names = ' '.join(_nz((core._META.get(v) or {}).get('name_ko', '')) for v in used if v in core._META)
    out, seen = [], set()
    for pat in _ABS_PAT:
        for mt in pat.finditer(reply or ''):
            toks = [w for w in re.split(r'[^가-힣]+', mt.group(1)) if len(w) >= 2 and not _ABS_STOP.match(w)]
            toks = [re.sub(r'(?:이나|나|와|과|의|를|을)$', '', w) if len(w) >= 4 else w for w in toks]
            if not toks or not any(len(w) >= 3 and w not in _ABS_GENERIC for w in toks):      # 「지급액」「보험료」처럼 여러 사업에 두루 쓰는 낱말만으로 된 이름은 보지 않음
                continue
            key = ' '.join(toks)
            if key in seen or any(key in a or a in key for a in absent) or all(w in used_names for w in toks):
                continue
            seen.add(key)
            hits = [(v, m.get('name_ko', '')) for v, m in core._META.items() if m.get('available', True) and v not in used
                    and all(w in _nz(m.get('name_ko', '')) for w in toks)]
            if not hits and len(toks) == 1 and v12e():      # 규칙 묶음 12e: 가운데 낱말을 줄인 이름의 변수(6차 문서 12d: 「일용근로소득」 변수가 없다고 했으나 일용소득 p_dainc 가 있음)
                hits = [(v, m.get('name_ko', '')) for v, m in core._META.items() if m.get('available', True) and v not in used and core.name_contracts(toks[0], m.get('name_ko', ''))]
            if hits:
                hits.sort(key=lambda x: len(x[1]))
                out.append((key, hits[:4]))
    return out[:2]


def absent_claim_note(found):
    return ('[검증 결과]\n- 확인(「자료에 없음」 진술의 점검): 응답이 자료에 없다거나 구분할 수 없다고 한 이름이 변수 사전의 한글 이름에 있음 — '
            + '; '.join(f"「{k}」: " + ', '.join(f'{v}({n})' for v, n in hits) for k, hits in found)
            + ". 질문이 말한 항목이면 print(ssda.find_vars('그 이름'))로 정의를 확인한 뒤 그 변수로 다시 산출하고 응답을 고칠 것. 질문의 항목과 뜻이 다른 변수이면 앞의 답을 그대로 다시 적을 것")


_FACTS = None


def facts():
    """제도 기준값 카드(01_knowledge/programs/facts_2021_2022.jsonl, 공식 출처에서 수집): 용어 사전 id → 사실 목록. 파일이 없으면 빈 사전."""
    global _FACTS
    if _FACTS is None:
        _FACTS = {}
        f = Path(__file__).resolve().parents[2] / '01_knowledge' / 'programs' / 'facts_2021_2022.jsonl'
        if f.exists():
            for line in f.read_text(encoding='utf-8').splitlines():
                try:
                    r = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if r.get('glossary_id') and r.get('item') and r.get('value') is not None and '대조 못 함' not in (r.get('note') or ''):
                    _FACTS.setdefault(r['glossary_id'], []).append(r)
    return _FACTS


def _fmt_fact(r):
    v, u = r.get('value'), r.get('unit') or ''
    if isinstance(v, (int, float)) and u == '원':
        v = f'{v:,.0f}'
    when = [r['applies']] if r.get('applies') else []
    if v12():                                           # 규칙 묶음 12d: 귀속·지급 연도와 시행일을 함께 적음(5차 과제 최종판: 2022년 귀속·2023년 지급분의 재산 요건 2.4억 원을 2022년 지급분에 적용)
        mm = re.search(r'(\d{4})년\s*귀속[^.\n]{0,3}?[,·]?\s*(\d{4})년\s*지급', r.get('note') or '')
        if mm:
            when.append(f'{mm.group(1)}년 귀속·{mm.group(2)}년 지급')
        ef = r.get('effective_from') or ''
        if ef and r.get('applies') and ef[:7] > r['applies'][-7:]:
            when.append(f'{ef} 시행')
    return f"{r['item']} {v}{u}" + (f" ({', '.join(when)})" if when else '')      # 출처(제목·주소·인용문)는 01_knowledge/programs/facts_2021_2022.jsonl 에 있음


def fact_lines(gid, limit=8):
    """제도 하나의 기준값 줄(2022년에 적용된 값을 먼저, 다음 2021년, 그 밖의 해 순)."""
    rank = lambda r: 0 if '2022' in (r.get('applies') or '') else 1 if '2021' in (r.get('applies') or '') else 2
    if v12():                                           # 규칙 묶음 12d: 같은 항목의 해별 값을 한 줄로 묶음(5차 과제 최종판: 8줄 한도에서 2021년 귀속분의 재산 요건이 빠지고 2022년 귀속분만 남음)
        items = {}
        for r in sorted(facts().get(gid, []), key=lambda r: (rank(r), r.get('applies') or '')):
            items.setdefault(r['item'], []).append(r)
        out = []
        for it, rs in list(items.items())[:max(limit, 10)]:
            parts = [_fmt_fact(r)[len(it) + 1:] for r in sorted(rs, key=lambda r: r.get('applies') or '')]
            out.append(f'{it} ' + ' / '.join(parts))
        if v12f() and gid != 'income':                  # 규칙 묶음 12f: 기준 중위소득 율의 가구원 수별 금액(6차 문서 12e: 생계급여 선정기준 2~6인 금액을 틀린 값으로 적용)
            T = median_table()
            for r in facts().get(gid, []):
                y = _prem_years(r)
                if '중위소득 대비' in (r.get('item') or '') and r.get('unit') == '%' and y and y[0] == y[1] and y[0] in T and y[0] in (2021, 2022):
                    am = median_amounts(y[0], float(r['value']))
                    out.append(f"{re.sub(r'[(].*?[)]', '', r['item']).strip()} 금액({y[0]}년, 기준 중위소득 {r['value']:g}%, 월): " + ' · '.join(f'{k}인 {v:,}원' for k, v in am.items()))
        return out
    return [_fmt_fact(r) for r in sorted(facts().get(gid, []), key=rank)[:limit]]


_PREM_GENERIC = {'월액', '금액', '지원', '기준', '대상', '연령', '요건', '하한', '상한', '이상', '이하', '미만', '초과', '최대', '최소', '지급액', '지원금', '지원액', '1인당', '연간', '시행일'}
_PREM_QKEY = re.compile(r'\d|가구|등급|학생|구간|급지|개월|단독|부부|맞벌이|홑벌이|중증|최고|최저|최초|종$|유형|형$')
_PREM_AMT = re.compile(r'((?:\d[\d,]*(?:\.\d+)?\s*(?:조|억|천만|백만|만|천)\s*)+(?:\d[\d,]*)?|\d[\d,]*(?:\.\d+)?)\s*(원|%(?!\s*p))')
_PREM_PART = re.compile(r'(\d[\d,]*(?:\.\d+)?)\s*(조|억|천만|백만|만|천)?')
_PREM_MULT = {'조': 1e12, '억': 1e8, '천만': 1e7, '백만': 1e6, '만': 1e4, '천': 1e3, None: 1, '': 1}
_PREM_CHANGE = re.compile(r'^\s*(?:씩|정도\s*(?:인상|인하)|(?:가량|만큼)?\s*(?:인상|인하|증가|감소|상향|하향|늘|줄|올|내려|낮|높|많|적|차이|더|추가))')
_PREM_M = re.compile(r'(?<![가-힣0-9])월(?![가-힣])|매월|월액|월평균|한\s*달')
_PREM_Y = re.compile(r'(?<![가-힣0-9])연(?![가-힣])|연간|연액|1년|한\s*해')


def _prem_amount(txt):
    """「30만 7,500원」「115만 2천 원」「2,200만 원」「12.27」 → 수치, 끝자리 단위(허용 오차용)."""
    x, last = 0.0, 1.0
    for m in _PREM_PART.finditer(txt):
        num = m.group(1).replace(',', '')
        if not num:
            continue
        mul = _PREM_MULT[m.group(2)]
        dec = len(num.split('.')[1]) if '.' in num else 0
        x += float(num) * mul
        last = mul * 10 ** (-dec)
    return x, last


def _prem_period(item):
    if re.search(r'(?:^|[\s(])월(?:[\s)]|액|$)|월액', item):
        return 'm'
    if re.search(r'(?:^|[\s(])연(?:[\s)]|간|$)|연간', item):
        return 'y'
    if re.search(r'1일|(?:^|[\s(])일(?:\)|$)|시간당', item):
        return 'd'
    return None


def _prem_years(r):
    a = re.findall(r'(20\d\d)', r.get('applies') or '')
    return (int(a[0]), int(a[-1])) if a else None


def premise_issues(text, gids):
    """질문·붙임 문서에 적힌 제도 기준값이 공식 출처의 기준값(제도 기준값 카드)과 다른 곳 → [(인용, 기준값 줄)]. 규칙 묶음 12e.
    6차 문서 12d: 「영아수당 월 50만 원」(2022년 30만 원), 「장기요양보험료율 소득의 12.27%」(건강보험료 대비)를 바로잡지 않고 그 전제로 계산·서술함.
    항목 이름의 핵심 낱말과 구분(1인 가구·1등급 등)이 같은 문장에 모두 있고, 구분 바로 뒤(구분이 없으면 낱말 뒤)의 첫 금액·율의 기간(월·연·일)과 단위가 항목과 같으며,
    문장이 말한 연도에 적용되는 기준값이 있을 때만 대조함. 다른 율을 곱한 값(「중위소득의 30%인 58만 원」), 변동 폭(「200만 원씩 인상」)은 보지 않음."""
    F = facts()
    own = {}
    for g, rs in F.items():
        for r in rs:
            base = re.sub(r'\(.*?\)', '', r['item']).strip()
            for w in re.split(r'[^0-9A-Za-z가-힣]+', base):
                own.setdefault(w, set()).add(g)
    names = {e['id']: [e['name']] + list(e.get('aliases') or []) for e in _glossary()}
    sents = [s for s in re.split(r'(?<=[.!?])\s+|\n+', text or '') if s.strip()]
    out, seen = [], set()
    for g in dict.fromkeys(gids):
        items = {}
        for r in F.get(g, []):
            if isinstance(r.get('value'), (int, float)) and r.get('unit') in ('원', '%'):
                items.setdefault(r['item'], []).append(r)
        for item, rs in items.items():
            base = re.sub(r'\(.*?\)', '', item).strip()
            qual = ' '.join(re.findall(r'\(([^)]*)\)', item))
            kws = [w for w in re.split(r'[^0-9A-Za-z가-힣]+', base) if len(w) >= 2 and w not in _PREM_GENERIC]
            if not kws:
                continue
            qreq = [w for w in re.split(r'[\s,·]+', re.sub(r'[가-힣]+\s*대비', '', qual)) if w and _PREM_QKEY.search(w)]
            if sum(re.sub(r'\(.*?\)', '', it).strip() == base for it in items) == 1:      # 같은 이름의 항목이 하나뿐이면 구분(단독가구 등)이 문장에 없어도 대조함
                qreq = []
            qbase = re.sub(r'\s', '', (re.search(r'([가-힣\s]+?)\s*대비', qual) or [None, ''])[1]) if '대비' in qual else ''
            per, unit = _prem_period(item), rs[0]['unit']
            shared = any(len(own.get(w, ())) > 1 for w in kws)
            for s in sents:
                if not all(w in s or (len(w) >= 5 and w[-1] in '율률액' and w[:-1] in s) for w in kws):
                    continue
                stem = not all(w in s for w in kws)     # 「장기요양보험료」처럼 줄기만 있음: 율의 기준 대조만 함(값 대조는 하지 않음)
                if shared and not any(n in s for n in names.get(g, [])):
                    continue
                qpos = []
                for w in qreq:
                    k = w if w in s else (w[:-2] if w.endswith('가구') and w[:-2] in s else None)
                    if k is None:
                        break
                    qpos.append(s.find(k) + len(k))
                if len(qpos) < len(qreq):
                    continue
                w0 = kws[0] if kws[0] in s else kws[0][:-1]
                p = s.find(w0)
                kend = [s.find(w) + len(w) if w in s else s.find(w[:-1]) + len(w) - 1 for w in kws]
                a0 = max([p] + kend + qpos)                    # 마지막 낱말·구분 바로 뒤의 금액(「상한액은 524만 원, 하한액은 33만 원」)
                win = s[a0:a0 + (30 if qpos else 80)]
                mt = next((m for m in _PREM_AMT.finditer(win) if m.group(2) == unit), None)
                if not mt:
                    continue
                between = s[p:a0] + win[:mt.start()]
                after = win[mt.end():mt.end() + 8]
                if _PREM_CHANGE.match(after) or re.match(r'\s*(?:→|->|에서)', after) or (unit == '원' and re.search(r'\d\s*%', between)):      # 변동 폭·바뀌기 전 값·다른 율을 곱한 값
                    continue
                if per == 'm' and (not _PREM_M.search(between + after[:3]) or _PREM_Y.search(between)):
                    continue
                bare = between
                for w in kws:
                    bare = bare.replace(w, ' ')
                if per is None and (_PREM_M.search(bare) or _PREM_Y.search(bare)):      # 기간이 없는 항목(90일분 상한액 등)을 「월 상한액」과 대조하지 않음
                    continue
                if per == 'y' and not _PREM_Y.search(between):
                    continue
                if per == 'd' and not re.search(r'일|시간', between + after[:4]):
                    continue
                yrs = lambda t: {int(y) for y in re.findall(r'(20\d\d)\s*년', t)} | {2000 + int(y) for y in re.findall(r"[’'‘]\s*(\d\d)\s*년", t)}
                ys = yrs(between + after) or yrs(s)            # 금액에 가까운 연도를 먼저 봄(「'20년 6.67% → '21년 6.86%」)
                cand = [r for r in rs if not ys or (_prem_years(r) and any(_prem_years(r)[0] <= y <= _prem_years(r)[1] for y in ys))]
                if not cand:
                    continue
                x, last = _prem_amount(mt.group(1))
                tol = 0.5 * last + 1e-9
                quote = s[max(0, p - 4):a0 + mt.end() + 1].strip()[-90:]
                key = (g, item, quote)
                if key in seen:
                    continue
                if not stem and not any(abs(x - float(r['value'])) <= max(tol, 0.001 * abs(float(r['value']))) for r in cand):
                    seen.add(key)
                    fl = [l for l in fact_lines(g) if l.startswith(item)]
                    out.append((quote, '; '.join(fl) or _fmt_fact(cand[0])))
                    continue
                if qbase and unit == '%' and any(abs(x - float(r['value'])) <= max(tol, 0.001 * abs(float(r['value']))) for r in cand):      # 율의 기준(분모)이 다름: 「소득의 12.27%」(기준값은 건강보험료 대비)
                    mb = re.search(r'([가-힣]{2,})\s*(?:의|에|대비|에\s*대한)\s*(?:[가-힣]+\s*)?$', between)
                    b = mb.group(1) if mb else ''
                    if b and b not in qbase and qbase not in b and not any(b in k for k in kws):
                        seen.add(key)
                        out.append((quote, f'{item} — 율의 기준이 「{qbase} 대비」임'))
    return out[:3]


def premise_note(found):
    return ('■ 전제 확인(질문·붙임 문서의 값이 제도 기준값과 다름. 계산·판정에는 기준값을 쓰고 「결과」 첫머리에 차이를 밝힘. 질문이 가정한 값으로 계산해 달라고 했으면 그 값을 쓰되 기준값과 다르다는 점을 밝힘'
            + ('. 값이 다른 까닭(다른 해의 값, 인상 계획 등)은 참고 자료에 없으면 짐작해 적지 않음' if v12f() else '') + ')\n'
            + '\n'.join(f'- 「{q}」 → 기준값: {f}' for q, f in found))


def fact_note(gids):
    """용어 사전 항목들의 제도 기준값 카드(참고 자료). 없으면 빈 문자열."""
    rows = [(g, fact_lines(g)) for g in dict.fromkeys(gids)]
    rows = [(g, ls) for g, ls in rows if ls]
    if not rows:
        return ''
    names = {e['id']: e['name'] for e in _glossary()}
    return ('■ 제도 기준값(공식 출처에서 수집한 2021~2022년 값. 이 값과 다른 금액·시점이 질문·붙임 문서에 있으면 차이를 밝힘)\n'
            + '\n'.join(f"- {names.get(g, g)}: " + ('; '.join(ls) if v12() else ' / '.join(ls)) for g, ls in rows))


_GLOSS = None


def _glossary():
    global _GLOSS
    if _GLOSS is None:
        f = Path(__file__).resolve().parents[2] / '01_knowledge' / 'programs' / 'glossary.json'
        _GLOSS = json.loads(f.read_text(encoding='utf-8')) if f.exists() else []
    return _GLOSS


_BIG_PROGRAM = 15                                       # 변수가 이보다 많은 사업(건강보험 등)은 이름이 문서에 나온 변수만 목록에 넣음


def program_vars_card(text, gids=(), max_programs=8, max_vars=60):
    """붙임 문서·여러 항목 요청에 나온 제도의 변수 목록(참고 자료). 용어 사전이 찾은 제도의 변수와, 사업명이 문서에 그대로 나온 사업의 변수를 한 줄씩 적는다.
    2026-11-18 독립 검증 6차: 1차례 요청 문장에는 제도 이름이 없고 붙임 문서에만 있어, 계산 항목에 필요한 변수 166개 가운데 4개만 참고 자료에 붙음."""
    core._load_meta()
    words = lambda s: [w for w in re.split(r'[^0-9A-Za-z가-힣]+', s or '') if len(w) >= 2]
    progs, seen_v = [], set()
    gl = {e['id']: e for e in _glossary()}
    for g in dict.fromkeys(gids):
        e = gl.get(g)
        if e:
            vs = [v for v in e.get('all_vars') or list((e.get('vars') or {}).values()) if v in core._META and core._META[v].get('available', True)]
            if vs:
                progs.append((e['name'], list(vs))); seen_v |= set(vs)
    by_prog = {}
    for v, m in core._META.items():
        if m.get('available', True) and str(m.get('grade', '')) != '제외' and m.get('program'):
            by_prog.setdefault(m['program'], []).append(v)
    for pg, vs in sorted(by_prog.items(), key=lambda x: -len(x[0])):
        if len(pg) < 3 or pg not in text or all(v in seen_v for v in vs):
            continue
        if len(vs) > _BIG_PROGRAM:                      # 큰 사업은 이름 낱말이 문서에 나온 변수만
            vs = [v for v in vs if sum(1 for w in words(core._META[v].get('name_ko')) if w in text and w != pg) >= 1]
        vs = [v for v in vs if v not in seen_v]
        if vs:
            same = next((x for x in progs if x[0] == pg), None)      # 용어 사전 항목과 사업명이 같으면 한 줄로 합침
            if same:
                same[1].extend(vs)
            else:
                progs.append((pg, list(vs)))
            seen_v |= set(vs)
    if not progs:
        return ''
    lines, n = [], 0
    for pg, vs in progs[:max_programs]:
        parts = []
        for v in vs:
            if n >= max_vars:
                break
            m = core._META[v]; labs = m.get('labels') or {}
            parts.append(f"{v} {m.get('name_ko', '')}" + (f"[{m['unit']}]" if m.get('unit') else '')
                         + (f"({'; '.join(f'{k}={str(x)[:24]}' for k, x in list(labs.items())[:4])})" if labs and len(labs) <= 6 else ''))
            n += 1
        lines.append(f"- {pg}: " + ' · '.join(parts))
    return ('■ 붙임 문서의 제도와 변수(변수 사전. 여부 변수의 해당자는 == 1, (연간)은 2022년 중 한 번이라도, (고정시점)은 12월 기준)\n' + '\n'.join(lines))

def var_candidates(question, seen=(), tried=(), top=5):
    """질문의 낱말로 변수 사전을 찾은 후보(없는 변수 오류가 거듭될 때 조립기가 오류 문구에 덧붙임).
    이미 정의를 본 변수(seen)가 설명하는 낱말은 빼고, 남은 낱말이 한글 이름·사업명에 들어 있는 변수를 고른다. 형태소 분석 없이 글자 포함 여부로 대조한다.
    질문이 이름을 거의 그대로 적은 변수(이름 낱말의 3/4 이상이 질문에 있고 그 가운데 아직 설명되지 않은 낱말이 있음)는 앞에 둔다(2026-11-18 독립 검증 3차:
    「의원 외래 요양급여비용 총액」을 물었는데 이미 본 「전체 의과 의료기관」 변수와 낱말이 겹친다는 이유로 후보에서 빠져 모형이 「자료에 없음」으로 답함).
    돌려주는 값  [{'name': 변수명, 'name_ko': 한글 이름, 'program': 사업, 'unit': 단위}, …]"""
    core._load_meta()
    q = re.sub(r'```.*?```', ' ', question or '', flags=re.S)
    words = lambda s: [w for w in re.split(r'[^0-9A-Za-z가-힣]+', s or '') if len(w) >= 2]
    covered = {w for v in seen if v in core._META for w in words(core._META[v].get('name_ko', '')) + words(core._META[v].get('program', '')) if w in q}
    qw = set(words(q))
    cov_all = {x for x in qw if any(w in x and len(w) >= len(x) - 1 for w in covered)}      # 이미 본 변수의 이름이 설명하는 질문 낱말(조사 한 글자까지)
    stretched = lambda w: [f for x in qw if x not in cov_all for f in (x, x[:-1]) if len(f) > len(w) and len(f) <= len(w) + 3 and f.startswith(w[:2]) and f.endswith(w[-2:])]
    full = set()                                            # 질문 낱말 가운데 어떤 변수 이름 낱말을 늘여 쓴 것(낱말 전체가 그 이름과 맞음)
    if v9():
        # 낱말 전체 일치 우선(2026-11-18 독립 검증 4차: 「일용근로소득」을 물었는데 그 낱말의 일부와만 맞는 「근로소득」 변수 3개가 후보를 차지해 일용소득 변수가 빠짐)
        for v, m in core._META.items():
            if m.get('available', True) and str(m.get('grade', '')) != '제외':
                for w in set(words(m.get('name_ko', '') or '')):
                    if len(w) >= 4 and w not in q:
                        full.update(stretched(w))
        for f in sorted(full, key=len, reverse=True):       # 늘여 쓴 낱말은 그 낱말 전체와 맞는 이름의 것으로 보고, 그 일부와만 맞는 이름은 일치로 세지 않음
            q = q.replace(f, ' ')
    rows = []
    for v, m in core._META.items():
        if v in seen or v in tried or not m.get('available', True) or str(m.get('grade', '')) == '제외':
            continue
        name, prog = m.get('name_ko', '') or '', m.get('program', '') or ''
        sc = 0.0
        if len(name) >= 2 and name in q and name not in covered:
            sc += 5
        nw = set(words(name))
        fresh = {w for w in nw if w in q and w not in covered and w != name}
        sc += 2 * len(fresh)
        sc += 1.5 * sum(1 for w in set(words(prog)) if w in q and w not in covered)
        if fresh and len(nw) >= 3 and sum(1 for w in nw if w in q) >= 0.75 * len(nw):      # 질문이 이름을 거의 그대로 적은 변수(이미 본 변수와 한 낱말만 다른 경우 포함)
            sc += 3
        # 질문이 이름을 늘여 쓴 경우(「일용근로소득」 ↔ 일용소득): 이름 낱말의 앞 두 글자로 시작하고 뒤 두 글자로 끝나는 질문 낱말(조사 한 글자까지)이 있으면 이름이 맞은 것으로 봄
        longer = {w for w in nw if len(w) >= 4 and w not in q and any(len(f) > len(w) and len(f) <= len(w) + 3 and f.startswith(w[:2]) and f.endswith(w[-2:]) for x in qw if x not in cov_all for f in (x, x[:-1]))}
        sc += (5 if full else 3) * len(longer)              # 규칙 묶음 9: 낱말 전체와 맞는 이름은 이름 일치와 같은 무게
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


def check_request(question, code, history=(), carried=(), sources='', doc=''):
    """질문에 적힌 조건이 코드에 반영됐는지 본다(작성자가 요청문을 다시 읽고 빠뜨린 조건을 찾는 확인).
    낱말 수준의 대조이므로 연령·성·가구원수·소득 분위·지역·가구 단위·그림·저장만 다룬다. 제도 조건(예: 「등록장애인 중」)은 다루지 않는다.
    history 는 같은 대화의 앞선 질문(이어 묻는 질문에서 「질문에 없는 조건」을 볼 때 앞선 질문의 조건을 인정하는 데 쓴다)."""
    q = _clean_q(question)
    if v9():
        q = _age_singles(q + _en_gloss(q))                  # 영문 질문의 조건어를 한글 조건어로 옮겨 붙이고, 한 살 단위 구간(「0세, 1세, 2세」)을 구간 표기로 바꿔 같은 규칙으로 대조함
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
    prev = ' '.join(_clean_q(h) for h in history or ())
    if v9():
        prev = prev + _en_gloss(prev)
    if v12() and doc:                                   # 규칙 묶음 12d: 붙임 문서가 정한 조건은 질문에 있는 것으로 봄(6차 문서 최종판: 문서의 「1인 가구」 조건을 질문에 없는 조건으로 돌려보내 대상이 달라짐)
        prev = (prev + ' ' + _clean_q(doc)).strip()
    return (out + check_request_strict(q, c, prev, carried) + check_request_extra(q, c, prev) + (check_request_v9(q, c, prev) if v9() else [])
            + (check_request_v10(q, c, prev, sources) if v10() else []) + (check_request_v12(q, c, prev, doc) if v12() else []))


# 영문 질문의 조건어 → 한글 조건어(2026-11-18 독립 검증 4차: "as of December 2022" 질문에 연간 기준 변수로 산출한 차례를 요청 대조가 잡지 못함. 기준 시점 규칙이 한글 표현만 읽음)
_EN_SIDO = {'seoul': '서울', 'busan': '부산', 'daegu': '대구', 'incheon': '인천', 'gwangju': '광주', 'daejeon': '대전', 'ulsan': '울산', 'sejong': '세종', 'gyeonggi': '경기', 'gangwon': '강원',
            'chungbuk': '충북', 'north chungcheong': '충북', 'chungnam': '충남', 'south chungcheong': '충남', 'jeonbuk': '전북', 'north jeolla': '전북', 'jeonnam': '전남', 'south jeolla': '전남',
            'gyeongbuk': '경북', 'north gyeongsang': '경북', 'gyeongnam': '경남', 'south gyeongsang': '경남', 'jeju': '제주'}
_EN_RULES = [
    (r'\bas of (?:the )?(?:end of )?(?:dec(?:ember|\.)?|12/31|year[- ]?end)|\b(?:at|by) (?:the )?(?:end of (?:the )?year|year[- ]?end)\b|\bin december\b|\bdecember 31\b|\bat year[- ]?end\b', '12월 기준'),
    (r'\bat any (?:time|point)\b|\bat least once\b|\b(?:during|over|throughout) the (?:whole |entire )?year\b|\bany time in 20\d\d\b', '한 번이라도'),
    (r'\b(?:living|lives?|lived) alone\b|\b(?:single|one)[- ]person households?\b|\bliving by themselves\b', '1인 가구'),
    (r'\b(?:how many|number of) households\b|\bhousehold count\b', '가구 수'),
    (r'\bhow many (?:people|persons|individuals|recipients|beneficiaries|children|adults|women|men|workers|residents)\b|\bnumber of (?:people|persons|individuals|recipients|beneficiaries)\b|\bhead ?count\b', '몇 명'),
    (r'\bmedian\b', '중위수'), (r'\b(?:total amount|sum of|in total|aggregate amount|combined amount)\b', '합계'), (r'\b(?:average|mean)\b', '평균'),
    (r'\b(?:share|percentage|proportion|percent)\b|\bwhat fraction\b', '비율'),
    (r'\b(?:by|per) (?:sex|gender)\b|\b(?:sex|gender) breakdown\b|\bmen and women\b|\bwomen and men\b|\bmale and female\b', '성별'),
    (r'\b(?:women|woman|females?|girls?|mothers?)\b', '여성'), (r'\b(?:men|man|males?|boys?|fathers?)\b', '남성'),
    (r'\b(?:capital region|seoul metropolitan area|capital area)\b', '수도권'),
]


def _en_gloss(q):
    """영문으로 적힌 조건어를 한글 조건어로 옮긴 문구(질문 뒤에 붙여 한글 규칙으로 대조한다). 영문 낱말이 없는 질문에는 빈 문자열."""
    t = re.sub(r'\s+', ' ', (q or '').lower())
    if len(re.findall(r'\b[a-z]{3,}\b', t)) < 4:
        return ''
    out = []
    for pat, ko in _EN_RULES:
        if re.search(pat, t) and not (ko in ('여성', '남성') and '성별' in out):
            out.append(ko)
    for a, b in re.findall(r'\b(?:aged?|ages?|between(?: the ages of)?)\s*(\d{1,3})\s*(?:-|–|to|and|through)\s*(\d{1,3})\b', t):
        out.append(f'{a}~{b}세')
    for n in re.findall(r'\b(\d{1,3})\s*(?:years?(?:[- ]old| of age)?\s*)?(?:or|and) (?:older|over|above|up|more)\b', t) + re.findall(r'\b(\d{1,3})\+', t) + re.findall(r'\bat least (\d{1,3})(?: years)?\b', t):
        out.append(f'{n}세 이상')
    for n in re.findall(r'\b(?:under|below|younger than)(?: the)?(?: age)?(?: of)? (\d{1,3})\b', t):
        out.append(f'{n}세 미만')
    for n in re.findall(r'\b(\d{1,3})\s*(?:years?(?:[- ]old| of age)?\s*)?(?:or|and) (?:younger|under|below|less)\b', t) + re.findall(r'\bup to (?:age )?(\d{1,3})\b', t):
        out.append(f'{n}세 이하')
    for n in re.findall(r'\b(?:older than|over the age of|above the age of) (\d{1,3})\b', t):
        out.append(f'{n}세 초과')
    for en, ko in _EN_SIDO.items():
        if re.search(rf'\b{en}\b', t):
            out.append(f'{ko} 거주')
    return (' ' + ' '.join(dict.fromkeys(out))) if out else ''


def _age_singles(q):
    """나열한 한 살 단위 구간(「0세, 1세, 2세, 3~4세」)을 「0~0세, 1~1세, …」로 바꿔 구간 규칙이 읽게 한다(2026-11-18 독립 검증 4차: 한 살 단위 구간을 질문에 없는 경계로 보아 정상 코드를 돌려보냄).
    구간 표기가 하나 이상 있거나 한 살 단위가 둘 이상 나열된 경우에만 바꾼다. 「65세 이상」「0세부터」「6세까지」는 건드리지 않는다."""
    pat = r'(?<![\d~∼\-])(\d{1,3})\s*세(?=\s*[,、/·]|\s*(?:과|와|및|그리고)\s*\d)'
    singles = re.findall(pat, q)
    if not singles or not (len(singles) >= 2 or re.search(r'\d+\s*[~∼\-]\s*\d+\s*세', q)):
        return q
    return re.sub(pat, lambda m: f'{m.group(1)}~{m.group(1)}세', q)


def _bool_mixed(expr):
    """조건식에 and 와 or 가 괄호 없이 같은 층에 섞여 있는지(and 가 먼저 계산됨)."""
    s = re.sub(r'\s+', ' ', str(expr or '')).strip()
    if ' or ' not in s or ' and ' not in s:
        return False
    try:
        tree = ast.parse(s, mode='eval')
    except SyntaxError:
        return False
    for n in ast.walk(tree):
        if isinstance(n, ast.BoolOp) and isinstance(n.op, ast.Or):
            for v in n.values:
                if isinstance(v, ast.BoolOp) and isinstance(v.op, ast.And):
                    before = s[:v.col_offset].rstrip(); after = s[v.end_col_offset:].lstrip()
                    if not (before.endswith('(') and after.startswith(')')):
                        return True
    return False


def _code_strings(code):
    """코드에 적힌 문자열(조건식 후보)."""
    try:
        return [n.value for n in ast.walk(ast.parse(code or '')) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    except SyntaxError:
        return [a or b for a, b in re.findall(r"'([^'\n]*)'|\"([^\"\n]*)\"", code or '')]


def cond_strings(code):
    """집계 호출에 실제로 들어가는 조건식(변수에 담아 두거나 문자열을 이어 만든 것을 풀어 냄). 풀 수 없는 것은 뺀다.
    2026-11-18 독립 검증 5차: where = "A or B or C" 를 "X and " + where 로 이어 쓴 코드가 and·or 혼용 점검을 지나 조용한 오답이 됨."""
    try:
        tree = ast.parse(code or '')
    except SyntaxError:
        return []
    env, out = {}, []

    def val(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            return n.value
        if isinstance(n, ast.Name):
            return env.get(n.id)
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
            a, b = val(n.left), val(n.right)
            return a + b if a is not None and b is not None else None
        if isinstance(n, ast.JoinedStr):
            parts = []
            for v in n.values:
                x = str(v.value) if isinstance(v, ast.Constant) else val(v.value) if isinstance(v, ast.FormattedValue) else None
                if x is None:
                    return None
                parts.append(x)
            return ''.join(parts)
        return None
    for st in tree.body:
        for n in ast.walk(st):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in AGG | {'define', 'rate_by_category'}:
                cand = list(n.args[:2] if n.func.attr == 'define' else n.args[:1]) + [k.value for k in n.keywords if k.arg in ('where', 'num', 'cond')]
                out += [x for x in (val(a) for a in cand) if x]
        if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
            x = val(st.value)
            if x is not None:
                env[st.targets[0].id] = x
            else:
                env.pop(st.targets[0].id, None)
    return out


def _amounts(text):
    """문장에 적힌 금액·수치를 원 단위 값의 후보로 풀어 낸다(「30만 7,500원」→ 307500, 「1억 2천만」→ 120000000, 「180만원」→ 1800000, 그대로 적힌 수)."""
    t = re.sub(r'(?<=\d),(?=\d{3})', '', text or '')
    out = set()
    for a, b, c in re.findall(r'(\d+(?:\.\d+)?)\s*억(?:\s*(\d+(?:\.\d+)?)\s*천\s*만)?(?:\s*(\d+)\s*만)?', t):
        out.add(float(a) * 1e8 + float(b or 0) * 1e7 + float(c or 0) * 1e4)
    for a in re.findall(r'(\d+(?:\.\d+)?)\s*천\s*만', t):
        out.add(float(a) * 1e7)
    for a, b, c in re.findall(r'(\d+(?:\.\d+)?)\s*만(?:\s*(\d)\s*천)?(?:\s*(\d{1,4})(?!\d))?', t):
        out.add(float(a) * 1e4 + float(b or 0) * 1e3 + float(c or 0))
    for a in re.findall(r'(?<![\d.])(\d+(?:\.\d+)?)(?![\d.])', t):
        out.add(float(a))
    return {x for x in out if x > 0}


def _grounded_amount(x, text):
    """코드의 금액 기준값 x 가 문장에 적힌 값(또는 그 12개월분·만원 환산·백분율 적용)에서 나오는지."""
    base = _amounts(text)
    pct = {float(p) / 100 for p in re.findall(r'(\d+(?:\.\d+)?)\s*(?:%|퍼센트)', text or '')}
    cand = set()
    for v in base:
        cand |= {v, 12 * v, v / 12}
        if v < 100000:
            cand |= {v * 1e4, v * 12e4}
    for v in list(cand):
        cand |= {v * q for q in pct}
    return any(abs(x - v) <= 0.005 * x + 1 for v in cand)


def check_request_v10(q, c, prev='', sources=''):
    """규칙 묶음 10의 대조(2026-11-18 독립 검증 5차에서 확인된 유형): 금액 변수의 단위(원), 질문·참고 자료에 근거가 없는 금액 기준값."""
    out = []
    core._load_meta()
    small, loose = [], []
    text = ' '.join(x for x in (q, prev, sources) if x)
    for s in cond_strings(c) or _code_strings(c):
        for v, op, num in re.findall(r'\b([A-Za-z_]\w*)\s*(<=|>=|<|>|==)\s*(\d+(?:\.\d+)?)(?![\d.])', s):
            if (core._META.get(v) or {}).get('unit') != '원':
                continue
            x = float(num)
            if 2 <= x < 10000:                              # 원 단위 변수에 만원 단위로 보이는 작은 값(2026-11-18 5차: np_inc_amt < 230, np_inc_amt >= 550)
                small.append(f'{v} {op} {num}')
            elif x >= 10000 and not _grounded_amount(x, text):      # 질문·참고 자료에 없는 기준값(5차: 선정기준액·상한액을 기억으로 적용해 다른 값으로 산출)
                loose.append(f'{v} {op} {num}')
    if small:
        out.append(_item('요청 반영', '경고', f"금액 변수의 단위는 원인데 코드의 조건({', '.join(dict.fromkeys(small))})이 만원 단위로 보이는 값임. 원 단위로 고쳐 다시 낼 것(예: 230만원 → 2300000)", target=True))
    if loose:
        out.append(_item('요청 반영', '경고', f"코드의 금액 기준({', '.join(dict.fromkeys(loose))})이 질문·참고 자료에 적힌 값에서 나오지 않음. 제도의 기준값(선정기준액, 상·하한액, 요율, 최저임금 등)은 기억으로 적용하지 않음. "
                         '질문에 그 값이 없으면 코드를 쓰지 말고 「확인 필요」로 적용할 기준값을 물을 것. 질문에 적힌 값을 환산한 것이면 같은 코드를 그대로 다시 내고 환산식을 「유의 사항」에 적을 것', target=True))
    return out



_WON_SPAN = re.compile(r'\d[\d,]*(?:\.\d+)?\s*억(?:\s*\d[\d,]*\s*천)?(?:\s*\d[\d,]*\s*만)?(?:\s*\d[\d,]*)?\s*원'
                       r'|\d[\d,]*(?:\.\d+)?\s*천\s*만\s*원|\d[\d,]*(?:\.\d+)?\s*만(?:\s*\d\s*천)?(?:\s*\d[\d,]{0,4})?\s*원|\d[\d,]*\s*원')


def _won_amounts(text):
    """단위(원·만원·억원)를 붙여 적은 금액만 원 단위 값으로(「1,200만원」→ 12000000, 「30만 7,500원」→ 307500, 「19,500원」→ 19500)."""
    out = set()
    for s in _WON_SPAN.findall(text or ''):
        a = _amounts(s)
        if a:
            out.add(max(a))
    return out



_PROG_WORD = re.compile(r'[가-힣]{2,12}?(?:수당|급여|연금|지원금|장려금|바우처|이용권|공제|크레딧|보조금|환급금|지원사업|수급|서비스)')




_TOTAL_REQ = re.compile(r'전국(?:에|의|적으로)?\s*(?:몇|규모|합계|총|인원|가구|수급자|이용자|가입자)|전체(?:와|과|\s*및)\s*[가-힣]{1,8}별|모두 합(?:친|쳐)|총계')

def _gloss_terms():
    """용어 사전의 정식 명칭·약어·통칭·구성 급여 이름(사전이 변수로 풀이하는 이름)."""
    s = set()
    for e in _glossary():
        if e.get('id') == 'absent_2022':                # 자료에 없는 제도의 이름은 풀이되는 이름이 아님(대체 점검 대상으로 둠)
            continue
        s |= set(e.get('terms') or []) | set(e.get('aliases') or []) | {x['name'] for x in e.get('parts') or []} | {a for x in e.get('parts') or [] for a in (x.get('aliases') or [])}
    return s

def _partial_name_subs(text, code):
    """질문·문서의 제도·급여 이름 T 가 변수 사전의 어느 이름·사업명에도 그대로 없는데, 코드가 쓴 변수의 이름에 T 의 일부(4자 이상)만 든 경우 → [(T, 변수, 한글 이름)].
    이름이 더 긴 다른 급여(조기취업성공수당 ↔ 취업성공수당)를 그 이름 일부가 같은 변수로 대신 산출하는 것을 막는다. 규칙 묶음 12."""
    core._load_meta()
    names = ' '.join((m.get('name_ko') or '') + ' ' + (m.get('program') or '') for m in core._META.values())
    used = [v for v in set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', code or '')) if v in core._META]
    known = _gloss_terms()
    terms = {T for T in _PROG_WORD.findall(re.sub(r'\s+', ' ', text or '')) if len(T) >= 5 and T not in names and T not in known}
    out = []
    for T in sorted(terms):
        for v in used:
            nm = core._META[v].get('name_ko') or ''
            ws = [w for w in re.split(r'[^가-힣]+', nm) if len(w) >= 4 and T.endswith(w) and len(T) - len(w) >= 2]      # 앞말이 붙은 더 긴 이름(조기 + 취업성공수당)
            if ws:
                out.append((T, v, nm))
    return out

_USE_Q = re.compile(r'입원(?:한|했던|을\s*한|\s*진료를\s*받은|\s*환자|자(?![격료]))|외래\s*진료를\s*받은|진료를\s*받은|내원한|의료기관을\s*이용한')
_FEE_Q = re.compile(r'본인부담(?:금|액)?(?:이|을|가)?\s*(?:낸|있는|있었던|발생|부담한|0원\s*초과|0원보다)|금액이\s*있는')


def _use_by_amount(qd, c):
    """「입원 진료를 받은 사람」 등 이용자를 금액 변수 > 0 으로 정한 코드 → [(질문의 말, 금액 변수, 일수 변수)]. 같은 이름의 일수 변수(_dur)가 있을 때만 봄."""
    m = _USE_Q.search(qd or '')
    if not m or _FEE_Q.search(qd or ''):
        return []
    out = []
    for s in cond_strings(c) or _code_strings(c):
        for v, op, num in re.findall(r'\b([A-Za-z_]\w*)\s*(>|>=)\s*(\d+(?:\.\d+)?)(?![\d.])', s):
            if (op == '>' and float(num) != 0) or (op == '>=' and float(num) > 1):
                continue
            if (core._META.get(v) or {}).get('unit') != '원' or not re.search(r'_(fee|amt|subsidy)$', v):
                continue
            sib = re.sub(r'_(fee|amt|subsidy)$', '_dur', v)
            if sib in core._META and sib not in c and core._META[sib].get('unit') in ('일', '회'):
                out.append((m.group(0), v, sib))
    return list(dict.fromkeys(out))[:2]


def check_request_v12(q, c, prev='', doc=''):
    """규칙 묶음 12의 대조(6차 주기 개발 측정에서 확인된 유형): 금액 상수의 자릿수, 「1인당」을 가구원 수로 나눈 코드, 월액 변수를 12로 나눈 코드."""
    out = []
    core._load_meta()
    text = ' '.join(x for x in (q, prev, doc) if x)
    won = _won_amounts(text)
    slip = []
    for s in cond_strings(c) or _code_strings(c):
        for v, op, num in re.findall(r'\b([A-Za-z_]\w*)\s*(<=|>=|<|>|==)\s*(\d+(?:\.\d+)?)(?![\d.])', s):
            if (core._META.get(v) or {}).get('unit') != '원':
                continue
            x = float(num)
            if x < 10000 or any(abs(x - a * f) <= 0.005 * x + 1 for a in won for f in (1, 12, 1 / 12)):
                continue
            hit = next((a for a in won for k in (10, 100, 1000, 0.1, 0.01) if abs(x - a / k) <= 0.005 * x + 1), None)
            if hit:                                     # 5차 과제 개발 측정: 「1,200만원」을 1200000(120만원)으로 옮김
                slip.append((f'{v} {op} {num}', hit))
    if slip:
        out.append(_item('요청 반영', '경고', '코드의 금액 기준(' + ', '.join(f"{a}" for a, _ in dict.fromkeys(slip)) + ')의 자릿수가 질문·문서에 적힌 금액('
                         + ', '.join(f'{h:,.0f}원' for _, h in dict.fromkeys(slip)) + ')과 다름. 만원 단위는 0을 네 개 붙여 원 단위로 고쳐 다시 낼 것(1,200만원 → 12000000)', target=True))
    qd = ' '.join(x for x in (q, doc) if x)
    if re.search(r'1인당', qd) and re.search(r'/\s*hnum\b', c) and not re.search(r'가구원\s*(?:1인당|한\s*명당|수로\s*나)|1인당\s*가구원', qd):
        out.append(_item('요청 반영', '경고', '질문의 「1인당 평균」은 대상자 한 사람의 평균(ssda.mean)임. 질문이 「가구원 1인당」을 말하지 않았으면 가구원 수(hnum)로 나누지 말 것', target=True))      # 5차 과제 개발 측정
    if _TOTAL_REQ.search(q or '') and re.search(r'[가-힣]{1,8}별', q or ''):
        calls = re.findall(r'ssda\.(count|total|rate|mean|quantile|share)\(((?:[^()]|\([^()]*\))*)\)', c)
        if calls and all(re.search(r'\bby\s*=', args) for _, args in calls):      # 5차 과제 개발 측정: 「전국에 몇 명인지, 시도별로는」에 시도별만 내고 합계를 손으로 더하거나 비움
            out.append(_item('요청 반영', '경고', '질문이 전국(전체) 값도 물음. by 를 주지 않은 같은 집계를 함께 실행해 그 값을 적을 것. 분류별 값을 더해 전체 값으로 적지 않음', target=True))
    if re.search(r'몇\s*(?:세대|가구)(?!원)|(?<![가-힣])(?:세대|가구)\s*수(?![급령])', q or '') and not re.search(r"unit\s*=\s*['\"]가구['\"]", c) and re.search(r'ssda\.(count|total)\(', c):
        out.append(_item('요청 반영', '경고', "질문이 세대(가구) 수를 물음. 집계에 unit='가구'를 넣어 가구주 한 사람의 행으로 셀 것(개인 단위로 세지 않음)", target=True))      # 5차 과제 개발 측정: 「몇 세대」를 개인 단위로 셈
    if v12e():                                          # 규칙 묶음 12e: 「입원 진료를 받은 사람」을 본인부담금 > 0 으로 정함(6차 문서 12c·12d: W2-D05·W2-D07, 본인부담이 0원인 입원자가 빠져 평균이 커짐)
        for ph, v, sib in _use_by_amount(qd, c):
            out.append(_item('요청 반영', '경고', f"질문의 「{ph}」 사람은 이용 일수로 정함({sib} > 0). {v} > 0 으로 정하면 금액이 0원인 이용자(본인부담 면제·감면 등)가 빠짐. "
                             '질문이 금액이 있는 사람을 뜻하면 같은 코드를 그대로 다시 낼 것', target=True))
    sub = _partial_name_subs(qd, c)
    if sub:                                             # 6차 문서 개발 측정: 자료에 없는 「조기취업성공수당」을 「취업성공수당」 변수로 산출
        out.append(_item('요청 반영', '경고', '; '.join(f"질문·문서의 「{T}」과 코드의 {v}(「{nm}」)는 이름이 다른 제도·급여임" for T, v, nm in sub)
                         + '. 같은 급여임이 참고 자료로 확인되지 않으면 그 변수로 대신 산출하지 말고, 그 항목은 자료에 없음을 밝힐 것. 같은 급여이면 같은 코드를 그대로 다시 내고 근거를 「유의 사항」에 적을 것', target=True))
    mon = []
    for v in re.findall(r'\b([A-Za-z_]\w*)\s*\)?\s*/\s*12(?![\d.])', c):
        m = core._META.get(v) or {}
        body = (m.get('name_ko') or '') + ' ' + (m.get('content') or '')
        if m.get('unit') == '원' and re.search(r'12월\s*말|월액|월\s*보험료|매월', body) and not re.search(r'1년\s*\(?|연간|총액|합산|1\.\s*1\.\s*~\s*12\.\s*31', body):
            mon.append(v)
    if mon:
        out.append(_item('요청 반영', '경고', f"{', '.join(dict.fromkeys(mon))}의 값은 12월 말 기준 등 한 달의 금액임(변수 카드의 「내용」). 12로 나누지 말고 그대로 비교·집계할 것", target=True))      # 5차 과제 개발 측정: 월액을 연액으로 보고 12로 나눔
    ann = []                                            # 규칙 묶음 12d: 연액 변수에 12를 곱함(5차 과제 최종판: 연간 경상소득 h_oinc 를 월액으로 보고 12를 곱해 대상이 달라짐)
    for v in re.findall(r'\b([A-Za-z_]\w*)\s*\)?\s*\*\s*12(?![\d.])', c) + re.findall(r'(?<![\w.])12\s*\*\s*\(?\s*([A-Za-z_]\w*)\b', c):
        m = core._META.get(v) or {}
        body = (m.get('name_ko') or '') + ' ' + (m.get('content') or '')
        if m.get('unit') == '원' and not re.search(_MONTHLY, body):
            ann.append(v)
    if ann:
        out.append(_item('요청 반영', '경고', f"{', '.join(dict.fromkeys(ann))}의 값은 1년 동안의 금액임(변수 카드에 한 달 금액이라는 말이 없음). 12를 곱하지 말 것. "
                         '월 기준액과 비교하려면 기준액에 12를 곱해 연액으로 비교할 것. 변수가 한 달 금액임이 변수 카드로 확인되면 같은 코드를 그대로 다시 낼 것', target=True))
    for v, used, named, lab in _code_label_mismatch(q, c):      # 규칙 묶음 12d: 질문이 말한 코드값 이름과 코드의 코드값이 다름(5차 과제 최종판: 「납부예외」에 np_status == 2(상실)). 붙임 문서는 여러 집단을 함께 적으므로 보지 않음
        out.append(_item('요청 반영', '경고', f"질문의 「{'」「'.join(lab[k] for k in named)}」은 {v} == {' 또는 '.join(named)}({', '.join(lab[k] for k in named)})임. 코드는 {v} 의 "
                         f"{', '.join(f'{k}({lab.get(k, k)})' for k in used)} 를 씀. 질문의 코드값으로 고쳐 다시 낼 것(코드값은 변수 카드의 「코드값」). 질문이 그 코드값을 가리킨 것이 분명하면 같은 코드를 그대로 다시 낼 것", target=True))
    for v, k, name in _named_group_missing(q, c):      # 규칙 묶음 12d: 질문이 말한 집단의 변수가 코드에 없음(5차 과제 최종판: 「사업장가입자 중」에 가입종별 조건 없이 가입자 전체로 산출)
        out.append(_item('요청 반영', '경고', f"질문의 「{name}」은 {v} == {k} 임({(core._META.get(v) or {}).get('name_ko', v)}). 코드의 대상에 이 조건이 없음. 대상을 그 집단으로 좁히는 말이면 where 에 넣어 다시 낼 것. "
                         '질문이 그 집단을 대상으로 삼지 않았으면 같은 코드를 그대로 다시 낼 것', target=True))
    if v12f():
        eq = []                                         # 규칙 묶음 12f: 금액 변수 == 특정 금액(6차 문서 12e W1-D01v: bp_amt == 4800000 으로 「0명」)
        caps = [float(r['value']) for rs in facts().values() for r in rs if re.search(r'상한|하한', r.get('item') or '') and isinstance(r.get('value'), (int, float))]
        caps += list(_won_amounts(text)) if re.search(r'상한|하한', text) else []      # 상·하한액에 걸린 사람(기준소득월액 == 553만원)은 같다(==)로 셈
        caps += list(_won_amounts(text)) if re.search(r'\d\s*원\s*인\s*(?:수급자|세대|가구|사람|대상|가입자|아동|이용자|경우)', text) else []      # 질문이 그 금액을 받은 사람을 직접 물음(5차 과제: 「급여액이 4,650,000원인 수급자」)
        for s in cond_strings(c) or _code_strings(c):
            for v, num in re.findall(r'\b([A-Za-z_]\w*)\s*==\s*(\d+(?:\.\d+)?)(?![\d.])', s):
                if (core._META.get(v) or {}).get('unit') == '원' and float(num) >= 1000 and not any(abs(float(num) - k * f) <= 1 for k in caps for f in (1, 12)):
                    eq.append(f'{v} == {num}')
        if eq:
            out.append(_item('요청 반영', '경고', f"코드가 금액 변수를 특정 금액과 같다(==)로 비교함({', '.join(dict.fromkeys(eq))}). 금액은 사람마다 달라 이 조건으로는 대상이 거의 남지 않음. "
                             '대상은 수급·가입 여부와 유형 변수로 정하고, 질문의 금액은 평균·분포와 견주는 값으로 쓸 것. 질문이 그 금액을 정확히 받은 사람을 물으면 같은 코드를 그대로 다시 낼 것', target=True))
        ms = _median_slips(text, c)
        if ms:                                          # 규칙 묶음 12f: 기준 중위소득 율의 가구원 수별 금액(6차 문서 12e W4-D06·W4-D06v: 생계급여 선정기준 2~6인 금액을 틀린 값으로 적용)
            out.append(_item('요청 반영', '경고', median_note(ms), target=True))
        for v, x, nm in _annual_vs_monthly(text, c):     # 규칙 묶음 12g: 연액 변수를 월 기준 금액과 그대로 비교(12f 5차 W2-05#4: 연간 경상소득 h_oinc <= 777925 = 의료급여 1인 가구 선정기준 월액)
            out.append(_item('요청 반영', '경고', f"{v}의 값은 1년 동안의 금액임(변수 카드에 한 달 금액이라는 말이 없음). 비교 기준 {x:,.0f}원은 {nm}과 같음. "
                             f'월 금액과 비교하려면 기준액에 12를 곱해({x * 12:,.0f}원) 연액으로 비교할 것. 변수가 한 달 금액임이 변수 카드로 확인되면 같은 코드를 그대로 다시 낼 것', target=True))
        lab = lambda v: ((core._META.get(v) or {}).get('name_ko') or v).split('_')[-1]
        for named, unnamed in _or_family_unnamed(q, c):    # 규칙 묶음 12f: 「산정특례 대상자 가운데 암으로 등록된 사람」에 산정특례 5종을 or 로 묶음(5차 과제 12c·12e W2-04)
            out.append(_item('요청 반영', '경고', f"질문은 「{'」「'.join(lab(v) for v in named)}」({', '.join(named)})만 말함. 코드는 같은 갈래의 {', '.join(f'{v}({lab(v)})' for v in unnamed)}도 「또는(or)」으로 묶어 대상이 넓어짐. "
                             '「○○ 대상자 가운데 □□」는 □□의 조건으로 좁힐 것. 질문이 그 갈래를 모두 물었으면 같은 코드를 그대로 다시 낼 것', target=True))
        for u, su, sw, ws in _better_named_vars(q, c):      # 규칙 묶음 12f: 「원천징수되는 사업소득」에 원천징수사업소득 변수(binc_sum) 대신 사업소득(p_binc)을 씀(5차 과제 12c·12e W3-03)
            out.append(_item('요청 반영', '경고', f"질문의 「{sw[:-len(su)].strip()}」「{su}」은 자료의 「{sw}」 변수({', '.join(ws)})의 이름과 맞음. 코드는 {u}(「{su}」)를 씀. "
                             f'두 변수의 뜻을 ssda.var_info()로 견주어 질문의 소득·급여에 맞는 변수로 고쳐 다시 낼 것. {u}가 질문에 맞으면 같은 코드를 그대로 다시 낼 것', target=True))
    return out


_OR_STEM = re.compile(r'(?:등록자|대상자|해당자|수급자|적용자|여부|자)$')


def _or_groups(s):
    """조건식 안의 「또는(or)」 묶음: 전체와 괄호 안 식마다 깊이 0 의 or 로 나눈 항. 규칙 묶음 12f."""
    exprs, st = [s], []
    for i, ch in enumerate(s):
        if ch == '(':
            st.append(i)
        elif ch == ')' and st:
            exprs.append(s[st.pop() + 1:i])
    out = []
    for e in exprs:
        terms, d, last = [], 0, 0
        for m in re.finditer(r'[()]|\bor\b|\|', e):
            t = m.group(0)
            if t == '(':
                d += 1
            elif t == ')':
                d -= 1
            elif d == 0:
                terms.append(e[last:m.start()]); last = m.end()
        terms.append(e[last:])
        if len(terms) > 1:
            out.append([x.strip() for x in terms])
    return out


def _or_family_unnamed(q, code):
    """질문이 같은 갈래 변수(nhi_special1_yn·nhi_special2_yn …) 가운데 일부의 이름만 말했는데 코드가 그 갈래를 「또는」으로 넓게 묶음 → [(이름이 나온 변수, 이름이 없는 변수)]. 규칙 묶음 12f."""
    core._load_meta()
    hits = []
    for s in cond_strings(code) or _code_strings(code):
        for terms in _or_groups(s):
            vs = [m.group(1) for t in terms for m in [re.fullmatch(r'\(?\s*([A-Za-z_]\w*)\s*==\s*1\s*\)?', t)] if m]
            fam = {}
            for v in vs:
                if v in core._META and re.search(r'\d', v):
                    fam.setdefault(re.sub(r'\d+', '#', v), []).append(v)
            for g in fam.values():
                if len(set(g)) < 2:
                    continue
                named, unnamed = [], []
                for v in dict.fromkeys(g):
                    lab = (core._META[v].get('name_ko') or '').split('_')[-1]
                    stem = _OR_STEM.sub('', lab) or lab
                    ok = (stem in (q or '')) if len(stem) >= 2 else bool(re.search(rf'(?<![가-힣]){re.escape(stem)}(?=으로|로|에|이|가|은|는|을|를|의|\s|환자|등록|진단|$)', q or ''))
                    (named if ok else unnamed).append(v)
                if named and unnamed:
                    hits.append((named, unnamed))
    return hits


def _better_named_vars(q, code):
    """질문이 자료의 더 긴 변수 이름(「원천징수」+「사업소득」 → 원천징수사업소득_지급총액)을 말했는데 코드는 그 이름의 끝부분만 같은 변수(p_binc: 사업소득)를 씀 → [(코드 변수, 그 이름, 더 맞는 이름, [변수])]. 규칙 묶음 12f."""
    core._load_meta()
    qn = re.sub(r'\s+', '', q or '')
    used = [v for v in dict.fromkeys(re.findall(r'\b([A-Za-z_]\w*)\b', code or '')) if v in core._META]
    stems_used = {(core._META[v].get('name_ko') or '').split('_')[0].strip() for v in used}
    out = []
    for u in used:
        su = (core._META[u].get('name_ko') or '').split('_')[0].strip()
        if len(su) < 3 or su not in qn:
            continue
        cand = {}
        for w, m in core._META.items():
            sw = (m.get('name_ko') or '').split('_')[0].strip()
            if w == u or sw in stems_used or not sw.endswith(su) or len(sw) <= len(su) or m.get('available') is False:
                continue
            if len(sw[:-len(su)].strip()) >= 3 and sw[:-len(su)].strip() in qn:
                cand.setdefault(sw, []).append(w)
        out += [(u, su, sw, ws[:3]) for sw, ws in cand.items()]
    return out


def median_table():
    """기준 중위소득(가구원 수별 월액) {연도: {가구원 수: 금액}} — 제도 기준값 카드의 「기준 중위소득(N인 가구 월)」 줄 가운데 1~7인이 모두 있는 해. 규칙 묶음 12f."""
    t = {}
    for r in facts().get('income', []):
        m = re.match(r'기준 중위소득\((\d)인 가구 월\)', r.get('item') or '')
        y = _prem_years(r)
        if m and y and y[0] == y[1] and isinstance(r.get('value'), (int, float)):
            t.setdefault(y[0], {})[int(m.group(1))] = float(r['value'])
    return {y: d for y, d in t.items() if len(d) == 7}


def median_amounts(year, p):
    """그 해 기준 중위소득의 p% 금액(원 미만 반올림) {가구원 수: 금액}."""
    T = median_table().get(year) or {}
    return {k: int(math.floor(v * p / 100 + 0.5)) for k, v in sorted(T.items())}


def _median_pcts(text):
    """질문·문서가 말한 기준 중위소득 대비 율: 「중위소득 60% 이하」「기준 중위소득의 30%」, 이름이 나온 제도의 선정기준 율(제도 기준값 카드)."""
    ps = {int(p) for p in re.findall(r'중위\s*소득[^\d\n]{0,8}?(\d{2,3})\s*%', text or '')}
    for rs in facts().values():                         # 항목 이름의 제도(「생계급여 선정기준(기준 중위소득 대비)」의 생계급여)가 문장에 나옴
        for r in rs:
            w = re.split(r'[\s(]', r.get('item') or '')[0]
            if '중위소득 대비' in (r.get('item') or '') and r.get('unit') == '%' and isinstance(r.get('value'), (int, float)) and len(w) >= 3 and w in (text or ''):
                ps.add(int(r['value']))
    for e in _glossary():
        names = [e.get('name') or ''] + list(e.get('aliases') or [])
        if any(len(n) >= 3 and n in (text or '') for n in names):
            for r in facts().get(e['id'], []):
                if '중위소득 대비' in (r.get('item') or '') and r.get('unit') == '%' and isinstance(r.get('value'), (int, float)):
                    ps.add(int(r['value']))
    return {p for p in ps if 10 <= p <= 200}


def _median_slips(text, code):
    """코드의 금액 상수 가운데 기준 중위소득 율의 가구원 수별 금액에 가깝지만(12% 안) 어느 금액·문서의 금액·기준값과도 같지 않은 것 → [(상수, 연도, 율, 배수)]."""
    T = median_table()
    ps = _median_pcts(text) if T else set()
    if not ps:
        return []
    years = sorted({int(y) for y in re.findall(r'(20\d\d)\s*년', text or '')} & set(T)) or ([2022] if 2022 in T else sorted(T)[-1:])
    lits = {float(x.replace('_', '')) for x in re.findall(r'(?:<=|>=|<|>|==)\s*\(?\s*(\d{1,3}(?:_\d{3})+|\d{6,})(?:\.0+)?(?![\w.])', code or '')}      # 비교의 기준값만 봄(단위 환산 상수는 보지 않음)
    known = list(_won_amounts(text)) + [float(r['value']) for rs in facts().values() for r in rs if r.get('unit') == '원' and isinstance(r.get('value'), (int, float))]
    exp = {(y, p): median_amounts(y, p) for y in years for p in sorted(ps)}
    ok_vals = [v * f for d in exp.values() for v in d.values() for f in (1, 12)] + [k * f for k in known for f in (1, 12)]
    out = []
    for x in sorted(lits):
        if any(abs(x - v) <= max(1.0, 0.001 * v) for v in ok_vals):
            continue
        near = min(((abs(x - v * f) / (v * f), y, p, f) for (y, p), d in exp.items() for v in d.values() for f in (1, 12)), default=None)
        if near and near[0] <= 0.12:
            out.append((x, near[1], near[2], near[3]))
    return out[:4]


def median_note(slips):
    keys = list(dict.fromkeys((y, p, f) for _, y, p, f in slips))[:2]
    tabs = ['; '.join(f"{y}년 기준 중위소득 {p}%" + (' 연액(월액 × 12)' if f == 12 else '(월)') + ': ' + ' · '.join(f'{k}인 {v * f:,}원' for k, v in median_amounts(y, p).items()) for y, p, f in keys)]
    return (f"코드의 금액 기준({', '.join(f'{x:,.0f}' for x, *_ in slips)})이 질문·문서가 말한 기준 중위소득 율의 가구원 수별 금액과 맞지 않음. " + tabs[0]
            + ' (보건복지부 기준 중위소득 × 율, 원 미만 반올림. 8인 이상 가구의 기준 중위소득은 1인 늘 때마다 7인과 6인 금액의 차를 더함). '
            '가구원 수(hnum)별로 이 금액을 쓸 것. 질문·문서가 다른 금액을 정했으면 같은 코드를 그대로 다시 낼 것')


_MONTHLY = r'12월\s*말|월액|월\s*보험료|매월|월평균|월\s*소득|월\s*금액|\(월\)|월간|한\s*달'


def _monthly_amounts(text):
    """월 기준 금액 [(금액, 이름)]: 질문·문서의 연도(없으면 2022년)에, 질문·문서가 말한 율(제도 이름으로 찾은 선정기준 율 포함)의 기준 중위소득 가구원 수별 월액과
    질문·문서에 이름이 나온 제도의 제도 기준값 카드 월 금액. 규칙 묶음 12g."""
    years = sorted({int(y) for y in re.findall(r'(20\d\d)\s*년', text or '')}) or [2022]
    T = median_table()
    out = []
    for y in years:
        for p in sorted(_median_pcts(text) if y in T else ()):
            out += [(float(v), f'{y}년 기준 중위소득 {p}%의 {k}인 가구 월액') for k, v in median_amounts(y, p).items()]
    for e in _glossary():
        if not any(len(n) >= 3 and n in (text or '') for n in [e.get('name') or ''] + list(e.get('aliases') or [])):
            continue
        for r in facts().get(e['id'], []):
            it, yy = r.get('item') or '', _prem_years(r)
            if (r.get('unit') == '원' and isinstance(r.get('value'), (int, float)) and r['value'] >= 10000 and re.search(r'월\)|월액|월\s*(최대|기준|지급|급여)', it)
                    and not re.search(r'연\)|연간|연액', it) and (not yy or any(yy[0] <= y <= yy[1] for y in years))):
                out.append((float(r['value']), f"{r.get('program') or ''} {it}".strip()))
    return out


def _annual_vs_monthly(text, code):
    """연액 금액 변수(변수 카드에 한 달 금액이라는 말이 없음)를 월 기준 금액과 그대로 비교한 조건 → [(변수, 기준값, 월 금액 이름)]. 규칙 묶음 12g.
    기준값에 12를 곱하거나 변수를 12로 나눈 비교, 질문·문서가 단위를 붙여 적은 금액(이용자가 정한 기준)은 보지 않음.
    12f 5차 W2-05#4: 「가구 경상소득(연간)이 의료급여 선정기준(1인 가구) 이하」에 h_oinc <= 777925(월액)로 비교해 대상이 40%로 줄어듦."""
    mons, stated = None, None
    out = []
    for s in cond_strings(code) or _code_strings(code):
        for v, num in re.findall(r'\b([A-Za-z_]\w*)\s*(?:<=|<|>=|>)\s*\(?\s*(\d{1,3}(?:_\d{3})+|\d{5,})(?:\.0+)?(?![\w.])(?!\s*\)?\s*[*/])', s):
            m = core._META.get(v) or {}
            if m.get('unit') != '원' or re.search(_MONTHLY, (m.get('name_ko') or '') + ' ' + (m.get('content') or '')):
                continue
            x = float(num.replace('_', ''))
            stated = _won_amounts(text) if stated is None else stated
            if any(abs(x - a) <= 1 for a in stated):
                continue
            mons = _monthly_amounts(text) if mons is None else mons
            nm = next((n for mv, n in mons if abs(x - mv) <= max(1.0, 0.0005 * mv)), None)
            if nm and (v, x) not in [(a, b) for a, b, _ in out]:
                out.append((v, x, nm))
    return out[:3]
_LAB_GENERIC = re.compile(r'^(예|아니오|있음|없음|해당|비해당|해당없음|대상|비대상|남|여|남성|여성|남자|여자|결측|기타|그\s*외|그\s*밖|미상|모름|무응답|정상|일반|전체)$')
_nz = lambda s: re.sub(r'[\s·,()_\-]', '', s or '')


def _labels_of(v):
    lab = (core._META.get(v) or {}).get('labels') or {}
    if isinstance(lab, str):
        try:
            lab = ast.literal_eval(lab)
        except (ValueError, SyntaxError):
            lab = {}
    return {str(k): str(x) for k, x in (lab or {}).items()}


def _label_said(label, tn):
    """코드값 이름이 질문(공백 등을 뺀 글)에 나왔는지: 이름 전체, 이름의 둘째 낱말부터(「기초생활보장수급자(생계,의료)」의 「생계」「의료」), 앞 두 글자를 뗀 나머지(「직장피부양자」의 「피부양자」)."""
    n = _nz(label)
    if len(n) < 2:
        return False
    if n in tn:
        return True
    ws = [w for w in re.split(r'[\s(),·/]+', label) if len(w) >= 2]
    if len(ws) >= 2 and all(_nz(w) in tn for w in ws[1:]):
        return True
    return len(n) >= 5 and n[2:] in tn


def _code_label_mismatch(text, code):
    """질문·문서가 범주형 변수의 코드값 이름(3자 이상, 「납부예외」)을 말했는데 코드는 그 변수의 다른 코드값만 조건으로 쓰고, 코드가 쓴 코드값의 이름은 질문·문서에 없음
    → [(변수, 코드가 쓴 값, 질문이 말한 값, 코드값 이름)]. 규칙 묶음 12d."""
    core._load_meta()
    tn = _nz(text)
    out, done = [], set()
    for s in cond_strings(code) or _code_strings(code):
        for v, op, val in re.findall(r"\b([A-Za-z_]\w*)\s*(==|\bin\b)\s*(\[[^\]]*\]|'[^']*'|\"[^\"]*\"|-?\d+)", s):
            lab = _labels_of(v)
            if len(lab) < 3 or v in done:
                continue
            used = set()
            for x in re.findall(r"-?\d+(?:\.0)?|'[^']*'|\"[^\"]*\"", val):
                x = x.strip('\'"')
                x = x[:-2] if x.endswith('.0') else x
                used.add(x if x in lab else next((k for k, y in lab.items() if y == x), x))
            named = {k for k, y in lab.items() if len(_nz(y)) >= 3 and not _LAB_GENERIC.match(y) and _nz(y) in tn}
            named = {k for k in named if not any(k2 != k and _nz(lab[k]) in _nz(lab[k2]) for k2 in named)}      # 긴 이름에 든 짧은 이름은 뺌
            if named and not (named & used) and not any(_label_said(lab.get(u, ''), tn) for u in used):
                out.append((v, sorted(used), sorted(named), lab))
                done.add(v)
    return out


def _named_group_missing(q, code):
    """질문(붙임 문서 제외)이 범주형 변수의 코드값 이름(4자 이상, 「사업장가입자」)을 대상을 좁히는 말로 썼는데 코드에 그 변수가 없고, 코드는 같은 사업 묶음의 다른 변수를 씀
    → [(변수, 코드값, 이름)]. 규칙 묶음 12d."""
    core._load_meta()
    ids = set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', code or ''))
    blocks = {(core._META.get(i) or {}).get('block') for i in ids if i in core._META}
    blocks.discard(None)
    names = ' '.join(_nz((core._META.get(i) or {}).get('name_ko', '')) for i in ids if i in core._META)      # 코드가 쓴 변수의 한글 이름(「국민연금 납부예외사유」로 납부예외자를 정한 코드는 보지 않음)
    out = []
    for v, m in core._META.items():
        if v in ids or m.get('block') not in blocks or not m.get('available', True):
            continue
        lab = _labels_of(v)
        if not 3 <= len(lab) <= 12:
            continue
        for k, y in lab.items():
            y = y.strip()
            if len(_nz(y)) >= 4 and not _LAB_GENERIC.match(y) and _nz(y) not in names and re.search(re.escape(y) + r'\s*(?:인|이었던|였던)?\s*(?:사람|가구|대상자|자)?\s*(?:의|가운데|중|만|을|를|이|가|은|는|에서|으로|로|에게|이면서|이고)(?![가-힣])', q or ''):
                out.append((v, k, y))
                break
    return out[:2]

def check_request_v9(q, c, prev=''):
    """규칙 묶음 9의 대조(2026-11-18 독립 검증 4차에서 확인된 유형): 전체 변수 대신 구성 변수의 합, and·or 를 괄호 없이 섞은 조건식."""
    out = []
    core._load_meta()
    rel = relations()
    ids = set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', c))
    for t, parts in rel['parts'].items():
        used = [p for p in parts + rel['not_parts'].get(t, []) if p in ids]
        if len(used) >= 2 and t not in ids and not any(w in q for w in rel['words'].get(t, [])):
            out.append(_item('요청 반영', '경고', f"코드가 유형별 변수 {len(used)}개({', '.join(used[:5])})를 함께 썼는데 전체 변수 {t}({core._META.get(t, {}).get('name_ko', '')})가 따로 있음. "
                             f'유형 구분이 다른 변수를 함께 더하면 전체와 달라짐. 질문이 유형을 지정하지 않았으므로 {t} 로 고쳐 다시 낼 것', target=True))
    for s in (cond_strings(c) + _code_strings(c)) if v10() else _code_strings(c):
        if _bool_mixed(s):
            out.append(_item('요청 반영', '경고', f"조건식 「{s[:120]}」에 and 와 or 가 괄호 없이 섞여 있음. and 가 or 보다 먼저 계산되므로 「A or B and C」는 「A or (B and C)」로 읽힘. "
                             '질문의 뜻대로 묶이도록 괄호를 넣어 다시 낼 것(예: 「(A or B) and C」)', target=True))
            break
    return out


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


_BACKREF = re.compile(r'그\s*(아이|사람|분|수급자|이용자|가입자|가구|집단|대상|중|들)|이\s*(사람|아이|집단|대상)들|해당\s*(대상|집단|사람)|같은\s*(대상|기준|집단|조건)|위\s*(대상|집단)|방금|앞(서|선|의)')
_DEC_Q = r'12월\s*(기준|말|현재|시점|에도|에 )|연말 기준|12월 31일'


def check_request_strict(q, c, prev='', carried=()):
    """질문의 문언과 코드가 어긋나는 것이 분명한 경우의 대조(경고). 2026-11-17 독립 검증에서 확인된 조용한 오답의 유형을 낱말 수준에서 잡는다:
    합계 요청에 평균, 질문이 정한 구간 대신 표준 구간·다른 경계, 연령 경계어(미만·이하·이상·초과)와 연산자의 불일치, 지역 이름과 시도 코드의 불일치,
    수도권 묶음, 12월·연간 기준, 「혼자 사는」, 해당하지 않는 집단. 어긋남이 분명한 경우만 다루며 고치는 방법을 함께 적는다."""
    out = []

    def warn(msg, target=False):                     # target: 고치면 대상(행의 범위)이 달라지는 경고 — 조립기가 실행 전에 돌려보냄(precheck)
        out.append(_item('요청 반영', '경고', msg, **({'target': True} if target else {})))
    # ① 집계 함수
    want_sum = re.search(r'합계|총합|합산|모두 더한|다 합치|전부 합|전국 합', q) or (re.search(r'총액|총 ?지급액|총 ?금액|총 ?규모', q) and not re.search(r'평균|1인당|중위|중앙값', q))
    if want_sum and not re.search(r'평균|1인당|중위수|중위값|중앙값|중간값|분위', q) and not re.search(r'ssda\.total\(', c) and re.search(r'ssda\.(mean|quantile)\(', c):      # 「합계의 중위수」는 합산 변수의 중위수를 물은 것
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
            warn(f"질문이 연령 구간({qtxt})을 정했는데 코드가 표준 연령 구간({', '.join(std)})을 씀. ssda.define_group('이름', 'age', {inner}, [구간 이름…])으로 질문의 구간을 만들어 by 에 쓸 것(맨 앞에 대상 밖 구간의 이름을 하나 더 줌)", target=True)
        for bins in dg:
            extra = [b for b in bins if b not in allow]
            lack = [b for b in inner if b not in bins]
            if extra or lack:
                warn(f"질문이 정한 연령 구간({qtxt})과 코드의 구간 경계({bins})가 다름" + (f". 질문에 없는 경계 {extra}를 빼고" if extra else '') + (f" 빠진 경계 {lack}를 넣어" if lack else '')
                     + f" bins={sorted(set(inner) | ({starts[0]} if starts[0] in bins else set()))} 로 고칠 것(구간 이름도 경계에 맞게)", target=True)
    # ③ 연령 경계어와 연산자
    for n, w in re.findall(r'(\d+)\s*세\s*(이상|미만|이하|초과)', q):
        n = int(n)
        good, bad = {'미만': ((rf'age\s*<\s*{n}(?!\d)', rf'age\s*<=\s*{n - 1}(?!\d)'), rf'age\s*<=\s*{n}(?!\d)'), '이하': ((rf'age\s*<=\s*{n}(?!\d)', rf'age\s*<\s*{n + 1}(?!\d)'), rf'age\s*<\s*{n}(?!\d)'),
                     '이상': ((rf'age\s*>=\s*{n}(?!\d)', rf'age\s*>\s*{n - 1}(?!\d)'), rf'age\s*>\s*{n}(?!\d)'), '초과': ((rf'age\s*>\s*{n}(?!\d)', rf'age\s*>=\s*{n + 1}(?!\d)'), rf'age\s*>=\s*{n}(?!\d)')}[w]
        if re.search(bad, c) and not any(re.search(g, c) for g in good):
            op = {'미만': f'age < {n}', '이하': f'age <= {n}', '이상': f'age >= {n}', '초과': f'age > {n}'}[w]
            warn(f'질문은 「{n}세 {w}」인데 코드의 연령 조건이 다름. 「{op}」로 고칠 것', target=True)
    # ④ 지역 이름과 시도 코드
    names = {n for n in _SIDO if re.search(rf'(?<![가-힣]){n}(?![가-힣]*도별)', q)} | {v for k, v in _SIDO_FULL.items() if k in q}
    metro = bool(re.search(r'수도권', q))
    nums = {int(x) for m in re.findall(r'sido\s*(?:==|!=|(?:not\s+)?in)\s*(\[[^\]]*\]|\d+)', c) for x in re.findall(r'(?<![\w.\'"])\d+', m)}
    strs = set(re.findall(r"['\"]([가-힣]{2,8})['\"]", ' '.join(re.findall(r'sido\s*(?:==|!=|(?:not\s+)?in)\s*(\[[^\]]*\]|[\'"][^\'"]*[\'"])', c))))
    strs = {_SIDO_FULL.get(x, x) for x in strs}
    if re.search(r"define_group\(\s*'[^']*'\s*,\s*'sido'", c):
        warn("시도(sido)는 순서가 없는 코드값이어서 define_group 의 구간으로 묶을 수 없음. 수도권·비수도권은 by='metro2', 다른 묶음은 ssda.define_cond('이름', {'묶음 이름': \"sido in ['서울', '인천', '경기']\"}, other='그 밖')으로 만들 것")
    if metro and 'metro2' not in c and not ({1, 4, 9} <= nums or {'서울', '인천', '경기'} <= strs):
        warn("질문의 「수도권」은 서울·인천·경기임. 수도권·비수도권으로 나누는 분류는 by='metro2', 수도권만 대상이면 where 에 \"sido in ['서울', '인천', '경기']\", 비수도권만 대상이면 \"sido not in ['서울', '인천', '경기']\"를 쓸 것", target=True)
    elif names and not metro and nums and not strs:
        want = {_SIDO.index(n) + 1 for n in names}
        if not (want & nums):
            warn('질문의 지역(' + ', '.join(sorted(names)) + ')과 코드의 시도 코드(' + ', '.join(f'{k}={_SIDO[k - 1]}' if 1 <= k <= 17 else f'{k}=없는 코드' for k in sorted(nums)) + ')가 다름. 시도는 이름으로 쓸 수 있음. 예: where 에 "sido == \'' + sorted(names)[0] + '\'"', target=True)
    # ⑤ 기준 시점
    y1 = set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)_yn1\b', c)); y2 = set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)_yn2\b', c))
    if re.search(r'12월\s*(기준|말|현재|시점|에도|에 )|연말 기준|12월 31일', q) and not re.search(r'한 번이라도|연간|한 해 동안|연중', q):
        only1 = sorted(v for v in y1 - y2 if core._META.get(v + '_yn2', {}).get('available') and not (v10() and v + '_yn1' in carried))
        if only1:
            warn(f"질문은 12월 기준인데 코드가 연간 기준 변수({', '.join(v + '_yn1' for v in only1)})만 씀. 12월 기준은 {', '.join(v + '_yn2' for v in only1)}", target=True)
    elif re.search(r'한 번이라도|연간 기준|한 해 동안|연중', q) and not re.search(r'12월', q):
        only2 = sorted(v for v in y2 - y1 if core._META.get(v + '_yn1', {}).get('available'))
        # 이어 묻는 질문이 앞선 질문의 대상(12월 기준)을 가리키면 「한 해 동안」은 금액·기간의 범위를 말한 것이므로 경고하지 않음
        # (2026-11-18 개발 묶음: 「그 아이들이 한 해 동안 받은 지원액」에 이 경고가 붙어 모형이 대상을 연간 기준으로 바꿈)
        inherit = bool(prev) and re.search(_DEC_Q, prev) and _BACKREF.search(q)
        if v10():      # 앞선 차례의 코드에서 이미 쓴 변수(이어받은 대상 조건)는 이번 질문의 「한 번이라도」가 가리키는 변수가 아님(2026-11-18 독립 검증 5차: 이어받은 12월 기준 조건을 연간 기준으로 바꾸게 해 대상이 달라짐)
            only2 = [v for v in only2 if v + '_yn2' not in carried]
        if only2 and not inherit:
            warn(f"질문은 연간(한 번이라도) 기준인데 코드가 12월 기준 변수({', '.join(v + '_yn2' for v in only2)})만 씀. 연간 기준은 {', '.join(v + '_yn1' for v in only2)}", target=True)
    # ⑤-2 금액 조건으로 잡은 12월 기준 수급자(규칙 묶음 12g: 12f 5차 W1-03#3 — 「2022년 12월 기준 이 수당의 수급자 수」를 연간 급여액 disp_bn_amt > 0 으로 잡음.
    #      연간 금액이 있는 사람은 그해 한 번이라도 받은 사람이어서 12월 기준 수급자와 다름. 「연간 수급액 평균」처럼 금액을 연간으로 묻는 말은 대상의 기준 시점이 아님)
    if v12() and re.search(_DEC_Q, q) and not re.search(r'한 번이라도|한 해 동안|연중|연간\s*(기준|수급자|수급 인원|이용자|가입자|대상)', q):
        amt0 = sorted(set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)_amt\s*(?:>\s*0(?![\d.])|>=\s*1(?![\d.])|!=\s*0(?![\d.]))', c)))
        hit = [(s + '_amt', re.sub(r'^[ph]_', '', s) + '_yn2') for s in amt0]
        hit = [(a_, y) for a_, y in hit if core._META.get(y, {}).get('available') and not re.search(rf'\b{y}\b', c)]
        if hit:
            warn('질문은 12월 기준 수급자인데 코드가 연간 급여액이 있는 사람(' + ', '.join(f'{a_} > 0' for a_, _ in hit) + ')으로 수급 여부를 잡음. '
                 '연간 급여액이 있는 사람은 그해 한 번이라도 받은 사람임. 12월 기준 수급자는 ' + ', '.join(f'{y} == 1' for _, y in hit) + '로 지정하고, 금액은 그 대상의 연간 급여액으로 산출할 것', target=True)
    # ⑥ 가구 규모
    if re.search(r'혼자 사는|혼자 사시는|독거|1인 가구', q) and not re.search(r'hnum|hs4', c):
        warn("질문의 「혼자 사는」「1인 가구」는 가구원수 1명임. 대상을 좁히는 조건이면 where 에 hnum == 1 을 넣고, 가구원수별 비교이면 by='hs4'를 쓸 것. 뜻을 되묻지 않음", target=True)
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

    def warn(msg, target=False):                     # target: 고치면 대상(행의 범위)이 달라지는 경고 — 조립기가 실행 전에 돌려보냄(precheck)
        out.append(_item('요청 반영', '경고', msg, **({'target': True} if target else {})))
    core._load_meta()
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
            warn(f"질문은 {'남성' if want == 1 else '여성'}을 말했는데 코드의 성 조건이 gender == {3 - want}({'여' if want == 1 else '남'})임. gender == {want} 또는 gender == '{'남' if want == 1 else '여'}' 로 고칠 것(성별 코드: 1=남, 2=여)", target=True)
    # ①-3 수급자·이용자를 세거나 그 금액을 내는 산출에 질문에 없는 연령 조건을 더한 경우(제도의 대상 연령을 임의로 넣음. 2026-11-17 독립 검증 2차: 「보육료 지원을 받는 아동이 몇 명」에 age < 6 을 더해 6세 수급자가 빠짐)
    if fns and not (fns & {'rate', 'poverty_rate'}) and re.search(r'_yn\d?\s*==\s*1', c) and not re.search(_AGE_WORD_STRICT, qa):
        nums_q = {int(x) for x in re.findall(r'(\d+)\s*(?:세|살|대(?![가-힣]))', qa)} | {int(b) for _, b in re.findall(r'(\d+)\s*[~∼\-]\s*(\d+)', qa)} | {int(a) for a, _ in re.findall(r'(\d+)\s*[~∼\-]\s*(\d+)', qa)}
        add = [f'age {op} {n}' for op, n in re.findall(r'\bage\s*(>=|<=|>|<|==)\s*(\d+)', c) if not ({int(n) - 1, int(n), int(n) + 1} & nums_q)]
        if add:
            warn(f"질문에 없는 연령 조건({', '.join(dict.fromkeys(add))})이 대상에 들어 있음. 수급자·이용자의 인원이나 금액을 묻는 질문에는 제도의 대상 연령을 임의로 더하지 않음. 질문이 연령을 정하지 않았으면 그 조건을 빼고 다시 실행할 것", target=True)
    # ①-4 금액·값이 있는 대상(「임차 보증금이 있는 가구만」「근로소득이 있는 사람」)인데 「변수 > 0」 조건이 없음
    has = re.search(r'(소득|급여|금액|보증금|재산|연금|수당|보험료|납부액|지급액|수령액|지원금|부담금|진료비|이용액|결제금액|본인부담|급여액|세액|임대료|월세)(이|가|을|를)?\s*(조금이라도\s*|한 푼이라도\s*)?(있는|있었던|있던|발생한)\s*(가구|사람|자|인원|개인|경우|대상|노인|청년|근로자|수급자|이용자|가입자|세대)', q)
    if has and fns & {'mean', 'quantile', 'total', 'share', 'count', 'rate'} and not re.search(r'>\s*0(?![\d.])|>=\s*[1-9]|notna\(|_yn\d?\s*==\s*1', c):      # 여부 변수로 대상을 정한 코드는 보지 않음
        warn(f"질문은 「{has.group(0)}」을 대상으로 했는데 코드에 값이 있는 대상만 남기는 조건이 없음. where 에 '해당 금액 변수 > 0'을 넣어 다시 실행할 것", target=True)
    # ② 질문에 없는 1인 가구 조건(가구주 조건을 hnum == 1 로 쓴 경우 포함)
    if re.search(r'hnum\s*==\s*1(?!\d)|hs4\s*==\s*0(?!\d)', c) and not re.search(r'1\s*인|혼자|독거|단독|홀로|홀몸|한\s*명|1\s*명|가구원\s*수|가구\s*규모', qa):
        warn("코드의 hnum == 1 은 1인 가구 조건인데 질문에 1인 가구를 가리키는 말이 없음. 가구주 조건이 아님: 가구 단위 집계(unit='가구')는 가구주 행으로 계산하므로 "
             "「가구주가 …인 가구」는 where 에 가구주의 연령·성·수급 조건만 쓰면 됨. 질문에 없는 조건이면 빼고 다시 실행할 것", target=True)
    # ③ 가구 단위 산출에 개인 변수를 쓴 경우(가구 변수가 따로 있음). 가구 단위 집계는 가구주 행의 값만 쓰므로 개인 변수로는 가구원의 값이 합쳐지지 않음
    #    (2026-11-17 독립 검증 2차·개발 묶음: 「가구 재산 평균」에 p_prop, 「가구원 보증금을 합친 금액」에 개인 보증금 변수를 unit='가구' 로 산출)
    for m in re.finditer(r"ssda\.(mean|total|quantile)\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]", c):
        var = m.group(2); depth, k = 1, m.end()
        while k < len(c) and depth:                         # 호출의 닫는 괄호까지(여러 줄에 걸친 호출 포함)
            depth += (c[k] == '(') - (c[k] == ')'); k += 1
        if not re.search(r"unit\s*=\s*['\"](가구|hh|household)['\"]", c[m.end():k]):
            continue
        hv = next((h for h in ('h_' + var[2:] if var.startswith('p_') else None, 'h_' + var) if h and (core._META.get(h) or {}).get('available', True) and h in core._META), None)
        if hv and not var.startswith('h_'):
            warn(f"가구 단위 산출(unit='가구')인데 개인 변수({var})를 씀. 가구 단위 집계는 가구주 한 사람의 값만 쓰므로 가구원의 값이 합쳐지지 않음. 가구 합산 변수는 {hv} 이므로 그 변수로 고쳐 다시 실행할 것(조건식의 같은 변수도 함께)")
            break
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


_YEAR = re.compile(r'(?<!\d)((?:19|20)\d{2})\s*년')
_MONEY = re.compile(r'(?<![\w.,])(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*(?:만\s*\d{0,4}\s*,?\d{0,3}\s*원|만\s*원|억\s*원|원)')


def policy_claims(answer, sources, data_year=2022):
    """응답에 적힌 제도 사실 가운데 질문·참고 자료·실행 결과에서 나올 수 없는 것: 자료 기준연도가 아닌 연도, 출처에 없는 금액(「결과」 밖의 문장).
    2026-11-18 독립 검증 5차: 「유의 사항」에 제도의 시행 시점·금액을 기억으로 적어 사실과 어긋난 진술이 여러 차례 확인됨(예: 2022년 7월 시행 제도를 「2024년 7월 처음 모집」으로 적음).
    돌려주는 값  {'years': [...], 'amounts': [...]}(없으면 빈 사전)"""
    text = re.sub(r'```.*?```', ' ', answer or '', flags=re.S)
    text = re.sub(r'`[^`]*`', ' ', text)
    src = '\n'.join(sources)
    years = sorted({y for y in _YEAR.findall(text) if int(y) != data_year and not re.search(rf'(?<!\d){y}(?!\d)', src)})
    rest = text.replace(result_part(answer), ' ') if result_part(answer) else text
    amounts = []
    for m in _MONEY.finditer(rest):
        if ground_numbers(m.group(0), sources) and m.group(0) not in amounts:
            amounts.append(m.group(0).strip())
    out = {}
    if years:
        out['years'] = years
    if amounts:
        out['amounts'] = amounts[:6]
    return out


def policy_note(pc):
    what = ' · '.join(x for x in (('연도 ' + ', '.join(y + '년' for y in pc.get('years', []))) if pc.get('years') else '', ('금액 ' + ', '.join(pc.get('amounts', []))) if pc.get('amounts') else '') if x)
    return ('[검증 결과]\n- 경고(제도 사실): 응답에 적힌 ' + what + '은 질문·참고 자료·실행 결과에 없는 내용임. 제도의 시행 시점·금액·대상 기준처럼 자료로 확인할 수 없는 사실은 기억으로 적지 않음. '
            '질문에 적힌 제도 사실이 맞는지 틀린지도 자료로 확인되지 않으면 단정하지 않고 「자료로는 확인할 수 없음」으로 적음. 해당 문장을 빼거나 고쳐 응답 전체를 다시 작성할 것. 코드는 다시 쓰지 않고 실행 결과의 값은 그대로 둠')


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
    if v12f():
        rc = rounding_claims(answer)
        if rc:                                          # 규칙 묶음 12f: 6차 문서 12e W1-D08(표시값 1,190만원에 문서의 1,191만원을 「틀림」으로 판정)
            issues.append(_item('반올림 범위', '경고', '; '.join(f'문서 값 {b}은 자료 표시값 {a}의 반올림 폭 안에 있음' for a, b in rc)
                                + '. 표시값은 인원·금액 유효숫자 3자리, 비율 소수 첫째 자리로 반올림한 값이므로 표시 자릿수로는 둘이 같음. 「틀림」으로 적지 않고 「맞음(표시 자릿수 안에서 일치)」으로 고칠 것. 판정이 바뀌면 관련 문장도 함께 고칠 것'))
        cc = causal_claims(answer, sources)
        if cc:                                          # 규칙 묶음 12f: 6차 문서 12e W1-D04(인과를 판정할 수 없다고 밝힌 뒤 「~때문으로 보임」 문장을 제시)
            issues.append(_item('원인 추정', '경고', '「' + '」「'.join(cc) + '」은 집계 결과로 원인·효과를 추정한 문장임. 한 시점 집계로는 원인을 판정할 수 없으므로 원인을 단정하거나 추정하는 문장을 쓰지 말고 관찰된 차이만 적을 것. '
                                '문서의 문장을 고쳐 달라는 요청이면 원인 귀속을 뺀 현황 서술 문장을 제시할 것'))
    return issues


_CLAIM_NEG = re.compile(r'틀림|틀렸|틀린|틀리|다름|다르[다며고]|불일치|맞지\s*않|일치하지\s*않')
_CLAIM_NUM = re.compile(r'(\d[\d,]*(?:\.\d+)?)\s*(만\s*원|억\s*원|원|%p|%|만\s*명|명|만\s*가구|가구|만\s*세대|세대|건|일|시간)')
_CLAIM_MULT = {'만': 1e4, '억': 1e8}


def _claim_tokens(line):
    out = []
    for m in _CLAIM_NUM.finditer(line):
        num, u = m.group(1), re.sub(r'\s', '', m.group(2))
        try:
            x = float(num.replace(',', ''))
        except ValueError:
            continue
        mult = _CLAIM_MULT.get(u[0], 1) if len(u) > 1 and u[0] in _CLAIM_MULT else 1
        base = u[1:] if mult != 1 else u
        dec = len(num.split('.')[1]) if '.' in num else 0
        digits = num.replace(',', '').replace('.', '').lstrip('0')
        tz = 0 if dec else len(digits) - len(digits.rstrip('0'))
        v = x * mult
        if base in ('%', '%p'):
            disp = 0.1 if dec == 1 else None            # 자료 표시값: 비율은 소수 첫째 자리
        else:
            disp = 10 ** (math.floor(math.log10(v)) - 2) if v >= 100 and len(digits.rstrip('0')) <= 3 else None      # 자료 표시값: 유효숫자 3자리
        out.append({'txt': m.group(0).strip(), 'v': v, 'u': base, 'prec': (10 ** (-dec) if dec else 10 ** tz) * mult, 'disp': disp})
    return out


def rounding_claims(answer):
    """「틀림」으로 적은 줄에서, 자료 표시값(덜 정밀한 값)의 반올림 폭 안에 있는 더 정밀한 문서 값과의 쌍 → [(표시값, 문서 값)]. 규칙 묶음 12f."""
    out = []
    text = re.sub(r'```.*?```', ' ', answer or '', flags=re.S)
    for line in re.split(r'\n+', text):
        if not _CLAIM_NEG.search(line) or re.search(r'반올림|표시\s*자릿수', line):
            continue
        tk = _claim_tokens(line)
        for a in tk:
            if not a['disp']:
                continue
            for b in tk:
                if b is a or b['u'] != a['u'] or b['prec'] >= a['disp'] - 1e-12 or abs(a['v'] - b['v']) < 1e-9:
                    continue
                if abs(a['v'] - b['v']) <= 0.5 * a['disp'] + 1e-9:
                    out.append((a['txt'], b['txt']))
    return list(dict.fromkeys(out))[:3]


_CAUSAL = re.compile(r'[^.\n]{0,40}(?:때문(?:으로|인\s*것으로)\s*(?:보임|보인다|보여|판단됨|판단된다|추정됨|추정된다|풀이됨|해석됨)|덕분(?:으로|인\s*것으로)\s*(?:보임|보인다|판단))')
_CAUSAL_Q = re.compile(r'효과|원인|때문|영향|이유|덕분|기여|성과')


def causal_claims(answer, sources=()):
    """효과·원인을 물은 질문에서 응답이 원인을 추정한 문장(「~때문으로 보임」) → [문장 조각]. 규칙 묶음 12f."""
    if not any(_CAUSAL_Q.search(s or '') for s in sources):
        return []
    text = re.sub(r'```.*?```', ' ', answer or '', flags=re.S)
    out = []
    for m in _CAUSAL.finditer(text):
        frag = m.group(0).strip()
        if re.search(r'(?:볼|판단할|판정할|단정할|말할)\s*수\s*(?:없|는\s*없)', text[m.end():m.end() + 25]):
            continue
        out.append(frag[-60:])
    return list(dict.fromkeys(out))[:2]


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
    if v9() and out.get('ok') and 'Empty DataFrame' in std and not out.get('results'):      # 변수 찾기 결과가 없음(2026-11-18 독립 검증 4차: 찾는 변수가 없는데 「요청 처리 불가」로 밝히지 않고 되물음)
        parts.append('안내: 변수 찾기 결과가 없음 — 그 낱말이 이름·사업명에 든 변수가 자료에 없음. 정식 명칭이나 상위 개념의 낱말로 한 번 더 찾아볼 것. 그래도 없으면 되묻지 말고 「요청 처리 불가」로 '
                     '자료에 없음을 밝히고 이 자료로 낼 수 있는 집계를 「가능한 대안」에 적을 것. 이름이 비슷한 다른 제도·항목의 변수로 바꿔 산출하지 않음')
    block = format_block(out, pre, req) if with_checks and out.get('ok') else ''
    return '\n'.join(p for p in parts if p) + ('\n\n' + block if block else '')


def answer_sources(messages, codes=()):
    """수치 대조의 출처: 질문, 실행 결과·검증 결과, 코드(참고 자료 카드는 넣지 않는다)."""
    src = []
    for m in messages:
        if m['role'] == 'user':
            c = m['content']
            if '[질문]' in c:
                if v12() and '[붙임 문서]' in c:      # 규칙 묶음 12d: 붙임 문서의 수치(문서가 적은 주장·기준값)도 출처로 봄(6차 문서 최종판: 재작성 뒤 남은 「실행 결과에 없는 수치」 29개 가운데 24개가 문서의 수치)
                    src.append(c.split('[붙임 문서]', 1)[1].split('[질문]')[0])
                c = c.split('[질문]')[-1]
            src.append(c)
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
