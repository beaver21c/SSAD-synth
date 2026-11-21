#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""규칙 묶음 12f(2026-11-19): 12e 개발 점검(6차 문서, 평가자 J5 판정)에서 남은 결함의 보완. 모두 규칙 묶음 12에서만 작동함.

  python3 06_build/staged/v12/patch_v12f.py <대상 폴더(준비 폴더 또는 시험용 사본)>

  ① 점검 문구(12): 「분류하지 않은 전체 값 29.9%」를 「분류 구분 없이 대상 전체로 계산한 비율 29.9%(집단별 값의 합이나 나머지의 비율이 아님)」로 씀
     (6차 문서 12e W4-D06v: 전체 빈곤율 29.9%를 「나머지 약 70%는 분류되지 않음」으로 읽음)
  ② 칸 합계(12): 인원·합계 표에 억제된 칸이 없으면 칸 합계를 알리고 「계」에는 칸과 같은 기준의 이 값을 쓰게 함
     (6차 문서 12e W3-D04: 「계」를 12월 31일 전 상실자까지 든 연간 가입 이력으로 셈, W4-D04: 「계」를 실행 결과에 없다며 비움)
     분류 기준에 값이 없는 대상이 없으면 칸 값 합과 전체 값의 차이가 반올림에서 생긴 것임을 알림(5차 과제 12e W2-09: 반올림 차이를 빠진 대상으로 적음)
  ③ 금액 == 조건(12): 금액 변수를 특정 금액과 같다(==)로 비교한 코드는 실행 전에 돌려보냄
     (6차 문서 12e W1-D01v: 「월 40만 원」 전제를 바로잡은 뒤 bp_amt == 4800000 으로 「0명」이라 답함)
  ④ 기준 중위소득(12): 제도 기준값 카드에 2021~2023년 기준 중위소득 1~7인 가구 금액(보건복지부 표)을 더하고,
     선정기준 율이 있는 제도의 카드에 가구원 수별 선정기준 금액을 적으며, 코드의 금액 기준이 가구원 수별 금액과 맞지 않으면 실행 전에 돌려보냄
     (6차 문서 12e W4-D06·W4-D06v: 생계급여 선정기준 2~6인 금액을 틀린 값으로 적용)
  ⑤ 반올림 범위의 판정(12): 문서 값이 자료 표시값(유효숫자 3자리·비율 소수 첫째 자리)의 반올림 폭 안에 있는데 「틀림」으로 적은 응답은 다시 쓰게 함
     (6차 문서 12e W1-D08: 표시값 1,190만원에 대해 문서의 1,191만원을 「틀림」으로 판정)
  ⑥ 원인 추정 문장(12): 효과·원인을 물은 질문에 「~때문으로 보임」처럼 원인을 추정한 문장을 적은 응답은 다시 쓰게 함
     (6차 문서 12e W1-D04: 인과를 판정할 수 없다고 밝힌 뒤 원인 귀속 문장을 제시)
  ⑦ 전제 확인 카드 문구(12): 기준값과 다른 까닭(다른 해의 값, 인상 계획 등)을 참고 자료 없이 짐작해 적지 않게 함
     (6차 문서 12e W1-D01: 「월 40만 원은 2023년 이후 기준」이라고 적음)
  ⑧ 같은 갈래 변수의 「또는」 묶음(12): 질문이 같은 갈래 변수(nhi_special1_yn·nhi_special2_yn …) 가운데 일부의 이름만 말했는데 코드가 그 갈래를 or 로 묶으면 실행 전에 돌려보냄
     (5차 과제 12c·12e W2-04: 「산정특례 대상자 가운데 암으로 등록된 사람」에 산정특례 5종의 합집합을 세고 「암 등록자로 한정」이라고 적음)
  ⑨ 더 맞는 이름의 변수(12): 질문이 자료의 더 긴 변수 이름(「원천징수」+「사업소득」)을 말했는데 코드가 이름의 끝부분만 같은 변수(p_binc: 사업소득)를 쓰면 실행 전에 돌려보냄
     (5차 과제 12c·12e W3-03: 「원천징수되는 사업소득」에 binc_sum 대신 p_binc)
"""
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()


def sub(rel, old, new, count=1):
    p = ROOT / rel
    s = p.read_text(encoding='utf-8')
    n = s.count(old)
    if n != count:
        raise SystemExit(f'{rel}: 바꿀 문자열 {n}곳(기대 {count}) — {old[:80]!r}')
    p.write_text(s.replace(old, new), encoding='utf-8')
    print('적용', rel, old[:60].replace('\n', ' '))


V = '02_library/ssda/verify.py'

# ── ① 게이트 ──
sub(V, '''def v12():
    """규칙 묶음 12(''', '''def v12f():
    """규칙 묶음 12f(12e 개발 점검의 보완). 규칙 묶음 12에 포함되며, 규칙 묶음 12 와 같은 조건(SSDA_RULESET >= 12)에서 작동함."""
    return v12()


def v12():
    """규칙 묶음 12(''')

# ── ① 전체 값 문구 ──
sub(V, """            item = _item('전체 값', '참고', f'분류하지 않은 전체 값 {_fmt(tv, res.unit)}', value=tv)""",
    """            item = _item('전체 값', '참고', (f"분류 구분 없이 대상 전체로 계산한 {_MEAS_KO.get(fn, '값')} {_fmt(tv, res.unit)}(집단별 값의 합이나 나머지의 비율이 아님)" if v12f()
                                            else f'분류하지 않은 전체 값 {_fmt(tv, res.unit)}'), value=tv)      # 규칙 묶음 12f: 6차 문서 12e W4-D06v 에서 전체 빈곤율 29.9%를 「나머지 70%는 분류되지 않음」으로 읽음""")

# ── ② 칸 합계 ──
sub(V, """    if fn == 'share' and not a.get('by') and n_ok == n and n > 1 and abs(float(df['값'].sum()) - 100) > 0.6:""",
    """    if v12f() and by and fn in ('count', 'total') and n_sup == 0 and n_ok > 1 and n_ok == n - n_na and not nb:      # 규칙 묶음 12f: 붙임 표의 「계」(6차 문서 12e W3-D04·W4-D04)
        tot_c = core.sig3(float(df.loc[df['상태'] == ST_OK, '값'].sum()))
        miss_c = any(c['code'] == '분류 누락' for c in out)
        out.append(_item('칸 합계', '참고', f'표의 칸 합계 {_fmt(tot_c, res.unit)}. 붙임 표의 「계」에는 칸과 같은 기준의 이 값을 씀'
                         + ('(분류 기준에 값이 없어 표에서 빠진 대상은 들지 않음. 그 사실은 「유의 사항」에 밝힘)' if miss_c else
                            '. 분류 기준에 값이 없는 대상은 없음. 표시된 칸 값을 더한 값과 전체 값의 차이는 칸 값의 반올림에서 생긴 것이므로 빠진 대상이나 차이로 적지 않음'), value=tot_c))      # 5차 과제 12e W2-09: 반올림 차이 6,000명을 「값이 없어 빠진 장애인」으로 적음
    if fn == 'share' and not a.get('by') and n_ok == n and n > 1 and abs(float(df['값'].sum()) - 100) > 0.6:""")

sub(V, """def _item(code, level, msg, **kw):""", """_MEAS_KO = {'rate': '비율', 'mean': '평균', 'quantile': '분위값'}


def _item(code, level, msg, **kw):""")

# ── ③·④ 금액 == 조건, 기준 중위소득 금액 ──
sub(V, """                         '질문이 그 집단을 대상으로 삼지 않았으면 같은 코드를 그대로 다시 낼 것', target=True))
    return out


_MONTHLY = """, """                         '질문이 그 집단을 대상으로 삼지 않았으면 같은 코드를 그대로 다시 낼 것', target=True))
    if v12f():
        eq = []                                         # 규칙 묶음 12f: 금액 변수 == 특정 금액(6차 문서 12e W1-D01v: bp_amt == 4800000 으로 「0명」)
        caps = [float(r['value']) for rs in facts().values() for r in rs if re.search(r'상한|하한', r.get('item') or '') and isinstance(r.get('value'), (int, float))]
        caps += list(_won_amounts(text)) if re.search(r'상한|하한', text) else []      # 상·하한액에 걸린 사람(기준소득월액 == 553만원)은 같다(==)로 셈
        caps += list(_won_amounts(text)) if re.search(r'\\d\\s*원\\s*인\\s*(?:수급자|세대|가구|사람|대상|가입자|아동|이용자|경우)', text) else []      # 질문이 그 금액을 받은 사람을 직접 물음(5차 과제: 「급여액이 4,650,000원인 수급자」)
        for s in cond_strings(c) or _code_strings(c):
            for v, num in re.findall(r'\\b([A-Za-z_]\\w*)\\s*==\\s*(\\d+(?:\\.\\d+)?)(?![\\d.])', s):
                if (core._META.get(v) or {}).get('unit') == '원' and float(num) >= 1000 and not any(abs(float(num) - k * f) <= 1 for k in caps for f in (1, 12)):
                    eq.append(f'{v} == {num}')
        if eq:
            out.append(_item('요청 반영', '경고', f"코드가 금액 변수를 특정 금액과 같다(==)로 비교함({', '.join(dict.fromkeys(eq))}). 금액은 사람마다 달라 이 조건으로는 대상이 거의 남지 않음. "
                             '대상은 수급·가입 여부와 유형 변수로 정하고, 질문의 금액은 평균·분포와 견주는 값으로 쓸 것. 질문이 그 금액을 정확히 받은 사람을 물으면 같은 코드를 그대로 다시 낼 것', target=True))
        ms = _median_slips(text, c)
        if ms:                                          # 규칙 묶음 12f: 기준 중위소득 율의 가구원 수별 금액(6차 문서 12e W4-D06·W4-D06v: 생계급여 선정기준 2~6인 금액을 틀린 값으로 적용)
            out.append(_item('요청 반영', '경고', median_note(ms), target=True))
    return out


def median_table():
    \"\"\"기준 중위소득(가구원 수별 월액) {연도: {가구원 수: 금액}} — 제도 기준값 카드의 「기준 중위소득(N인 가구 월)」 줄 가운데 1~7인이 모두 있는 해. 규칙 묶음 12f.\"\"\"
    t = {}
    for r in facts().get('income', []):
        m = re.match(r'기준 중위소득\\((\\d)인 가구 월\\)', r.get('item') or '')
        y = _prem_years(r)
        if m and y and y[0] == y[1] and isinstance(r.get('value'), (int, float)):
            t.setdefault(y[0], {})[int(m.group(1))] = float(r['value'])
    return {y: d for y, d in t.items() if len(d) == 7}


def median_amounts(year, p):
    \"\"\"그 해 기준 중위소득의 p% 금액(원 미만 반올림) {가구원 수: 금액}.\"\"\"
    T = median_table().get(year) or {}
    return {k: int(math.floor(v * p / 100 + 0.5)) for k, v in sorted(T.items())}


def _median_pcts(text):
    \"\"\"질문·문서가 말한 기준 중위소득 대비 율: 「중위소득 60% 이하」「기준 중위소득의 30%」, 이름이 나온 제도의 선정기준 율(제도 기준값 카드).\"\"\"
    ps = {int(p) for p in re.findall(r'중위\\s*소득[^\\d\\n]{0,8}?(\\d{2,3})\\s*%', text or '')}
    for rs in facts().values():                         # 항목 이름의 제도(「생계급여 선정기준(기준 중위소득 대비)」의 생계급여)가 문장에 나옴
        for r in rs:
            w = re.split(r'[\\s(]', r.get('item') or '')[0]
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
    \"\"\"코드의 금액 상수 가운데 기준 중위소득 율의 가구원 수별 금액에 가깝지만(12% 안) 어느 금액·문서의 금액·기준값과도 같지 않은 것 → [(상수, 연도, 율, 배수)].\"\"\"
    T = median_table()
    ps = _median_pcts(text) if T else set()
    if not ps:
        return []
    years = sorted({int(y) for y in re.findall(r'(20\\d\\d)\\s*년', text or '')} & set(T)) or ([2022] if 2022 in T else sorted(T)[-1:])
    lits = {float(x.replace('_', '')) for x in re.findall(r'(?:<=|>=|<|>|==)\\s*\\(?\\s*(\\d{1,3}(?:_\\d{3})+|\\d{6,})(?:\\.0+)?(?![\\w.])', code or '')}      # 비교의 기준값만 봄(단위 환산 상수는 보지 않음)
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


_MONTHLY = """)

# ── ⑧·⑨ 같은 갈래 변수의 「또는」 묶음, 더 맞는 이름의 변수(12e 5차 과제 점검: W2-04·W3-03, 12c부터 같은 오답) ──
sub(V, r'''            out.append(_item('요청 반영', '경고', median_note(ms), target=True))
    return out''', r'''            out.append(_item('요청 반영', '경고', median_note(ms), target=True))
        lab = lambda v: ((core._META.get(v) or {}).get('name_ko') or v).split('_')[-1]
        for named, unnamed in _or_family_unnamed(q, c):    # 규칙 묶음 12f: 「산정특례 대상자 가운데 암으로 등록된 사람」에 산정특례 5종을 or 로 묶음(5차 과제 12c·12e W2-04)
            out.append(_item('요청 반영', '경고', f"질문은 「{'」「'.join(lab(v) for v in named)}」({', '.join(named)})만 말함. 코드는 같은 갈래의 {', '.join(f'{v}({lab(v)})' for v in unnamed)}도 「또는(or)」으로 묶어 대상이 넓어짐. "
                             '「○○ 대상자 가운데 □□」는 □□의 조건으로 좁힐 것. 질문이 그 갈래를 모두 물었으면 같은 코드를 그대로 다시 낼 것', target=True))
        for u, su, sw, ws in _better_named_vars(q, c):      # 규칙 묶음 12f: 「원천징수되는 사업소득」에 원천징수사업소득 변수(binc_sum) 대신 사업소득(p_binc)을 씀(5차 과제 12c·12e W3-03)
            out.append(_item('요청 반영', '경고', f"질문의 「{sw[:-len(su)].strip()}」「{su}」은 자료의 「{sw}」 변수({', '.join(ws)})의 이름과 맞음. 코드는 {u}(「{su}」)를 씀. "
                             f'두 변수의 뜻을 ssda.var_info()로 견주어 질문의 소득·급여에 맞는 변수로 고쳐 다시 낼 것. {u}가 질문에 맞으면 같은 코드를 그대로 다시 낼 것', target=True))
    return out''')
sub(V, r'''

def median_table():''', r'''

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


def median_table():''')

sub(V, 'import re\n', 'import math\nimport re\n')

# ── ④ 제도 카드의 가구원 수별 선정기준 금액 ──
sub(V, """            out.append(f'{it} ' + ' / '.join(parts))
        return out""", """            out.append(f'{it} ' + ' / '.join(parts))
        if v12f() and gid != 'income':                  # 규칙 묶음 12f: 기준 중위소득 율의 가구원 수별 금액(6차 문서 12e: 생계급여 선정기준 2~6인 금액을 틀린 값으로 적용)
            T = median_table()
            for r in facts().get(gid, []):
                y = _prem_years(r)
                if '중위소득 대비' in (r.get('item') or '') and r.get('unit') == '%' and y and y[0] == y[1] and y[0] in T and y[0] in (2021, 2022):
                    am = median_amounts(y[0], float(r['value']))
                    out.append(f"{re.sub(r'[(].*?[)]', '', r['item']).strip()} 금액({y[0]}년, 기준 중위소득 {r['value']:g}%, 월): " + ' · '.join(f'{k}인 {v:,}원' for k, v in am.items()))
        return out""")

# ── ⑦ 전제 확인 카드 문구 ──
sub(V, """    return ('■ 전제 확인(질문·붙임 문서의 값이 제도 기준값과 다름. 계산·판정에는 기준값을 쓰고 「결과」 첫머리에 차이를 밝힘. 질문이 가정한 값으로 계산해 달라고 했으면 그 값을 쓰되 기준값과 다르다는 점을 밝힘)\\n'""",
    """    return ('■ 전제 확인(질문·붙임 문서의 값이 제도 기준값과 다름. 계산·판정에는 기준값을 쓰고 「결과」 첫머리에 차이를 밝힘. 질문이 가정한 값으로 계산해 달라고 했으면 그 값을 쓰되 기준값과 다르다는 점을 밝힘'
            + ('. 값이 다른 까닭(다른 해의 값, 인상 계획 등)은 참고 자료에 없으면 짐작해 적지 않음' if v12f() else '') + ')\\n'""")

# ── ⑤·⑥ 응답 점검 ──
sub(V, """        issues.append(_item('억제 안내', '주의', '표시되지 않은 칸이 있는데 응답에 억제 안내가 없음. 「유의 사항」에 밝힐 것'))
    return issues""", """        issues.append(_item('억제 안내', '주의', '표시되지 않은 칸이 있는데 응답에 억제 안내가 없음. 「유의 사항」에 밝힐 것'))
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


_CLAIM_NEG = re.compile(r'틀림|틀렸|틀린|틀리|다름|다르[다며고]|불일치|맞지\\s*않|일치하지\\s*않')
_CLAIM_NUM = re.compile(r'(\\d[\\d,]*(?:\\.\\d+)?)\\s*(만\\s*원|억\\s*원|원|%p|%|만\\s*명|명|만\\s*가구|가구|만\\s*세대|세대|건|일|시간)')
_CLAIM_MULT = {'만': 1e4, '억': 1e8}


def _claim_tokens(line):
    out = []
    for m in _CLAIM_NUM.finditer(line):
        num, u = m.group(1), re.sub(r'\\s', '', m.group(2))
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
    \"\"\"「틀림」으로 적은 줄에서, 자료 표시값(덜 정밀한 값)의 반올림 폭 안에 있는 더 정밀한 문서 값과의 쌍 → [(표시값, 문서 값)]. 규칙 묶음 12f.\"\"\"
    out = []
    text = re.sub(r'```.*?```', ' ', answer or '', flags=re.S)
    for line in re.split(r'\\n+', text):
        if not _CLAIM_NEG.search(line) or re.search(r'반올림|표시\\s*자릿수', line):
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


_CAUSAL = re.compile(r'[^.\\n]{0,40}(?:때문(?:으로|인\\s*것으로)\\s*(?:보임|보인다|보여|판단됨|판단된다|추정됨|추정된다|풀이됨|해석됨)|덕분(?:으로|인\\s*것으로)\\s*(?:보임|보인다|판단))')
_CAUSAL_Q = re.compile(r'효과|원인|때문|영향|이유|덕분|기여|성과')


def causal_claims(answer, sources=()):
    \"\"\"효과·원인을 물은 질문에서 응답이 원인을 추정한 문장(「~때문으로 보임」) → [문장 조각]. 규칙 묶음 12f.\"\"\"
    if not any(_CAUSAL_Q.search(s or '') for s in sources):
        return []
    text = re.sub(r'```.*?```', ' ', answer or '', flags=re.S)
    out = []
    for m in _CAUSAL.finditer(text):
        frag = m.group(0).strip()
        if re.search(r'(?:볼|판단할|판정할|단정할|말할)\\s*수\\s*(?:없|는\\s*없)', text[m.end():m.end() + 25]):
            continue
        out.append(frag[-60:])
    return list(dict.fromkeys(out))[:2]""")

# ── 기준 중위소득 표(보건복지부) — 제도 기준값 카드에 더함 ──
FP = ROOT / '01_knowledge' / 'programs' / 'facts_2021_2022.jsonl'
TAB = {2021: [1827831, 3088079, 3983950, 4876290, 5757373, 6628603, 7497198],
       2022: [1944812, 3260085, 4194701, 5121080, 6024515, 6907004, 7780592],
       2023: [2077892, 3456155, 4434816, 5400964, 6330688, 7227981, 8107515]}
have = {(r.get('item'), r.get('applies')) for r in (json.loads(l) for l in FP.read_text(encoding='utf-8').splitlines() if l.strip())}
add = []
for y, vals in TAB.items():
    for k, v in enumerate(vals, 1):
        item, ap = f'기준 중위소득({k}인 가구 월)', f'{y}-01~{y}-12'
        if (item, ap) in have:
            continue
        add.append({'glossary_id': 'income', 'program': '소득', 'item': item, 'value': v, 'unit': '원', 'applies': ap, 'effective_from': f'{y}-01-01',
                    'source_title': '보건복지부, 기준 중위소득(연도별 기준중위소득 표)', 'source_url': 'https://www.mohw.go.kr/menu.es?mid=a10708010900',
                    'quote': f"{y}년 " + ' '.join(f'{x:,}' for x in vals), 'note': f'{k}인 가구 기준(표의 {k}인 열, 원). 2026-11-19 규칙 묶음 12f에서 추가'})
with FP.open('a', encoding='utf-8') as fp:
    for r in add:
        fp.write(json.dumps(r, ensure_ascii=False) + '\n')
print('적용', FP.relative_to(ROOT), f'기준 중위소득 {len(add)}줄 추가')

# ── 자체 시험(06_build/v12_probe.py) ──
sub('06_build/v12_probe.py', """
bad = [n for n, ok in R if not ok]""", """
    # ── 규칙 묶음 12f(12e 개발 점검의 보완) ──
    for n in (11, 12):
        rs(n)
        ov = [c['msg'] for c in verify.check_result(core.rate(num='poor == 1', where='age >= 65', by=['sex'])) if c['code'] == '전체 값']
        t(('12f' if n == 12 else '11') + ': 전체 값 문구 ' + ('「분류 구분 없이 대상 전체로 계산한 비율」' if n == 12 else '기존'), bool(ov) and (('분류 구분 없이 대상 전체로 계산한 비율' in ov[0]) == (n == 12)))
        kc = [c['msg'] for c in verify.check_result(core.count(where='np_yn == 1', by=['np_type'])) if c['code'] == '칸 합계']
        t(('12f' if n == 12 else '11') + ': 칸 합계 ' + ('있음' if n == 12 else '없음'), bool(kc) == (n == 12) and (n == 11 or '「계」' in kc[0]))
        eqh = [i['msg'] for i in verify.check_request('기초연금 단독가구 수급자 수', "r = ssda.count(where='bp_yn2 == 1 and bp_amt == 4800000')") if i.get('target') and '같다(==)' in i['msg']]
        t(('12f' if n == 12 else '11') + ': 금액 == 조건 점검 ' + ('작동' if n == 12 else '없음'), bool(eqh) == (n == 12))
        t(('12f' if n == 12 else '11') + ': 반올림 범위·원인 추정 응답 점검 ' + ('작동' if n == 12 else '없음'),
          any(i['code'] == '반올림 범위' for i in verify.answer_issues('**결과**\\n- 평균 1,190만원(문서 1,191만원) → 틀림', [])) == (n == 12)
          and any(i['code'] == '원인 추정' for i in verify.answer_issues('**결과**\\n- 소득이 낮기 때문으로 보임', ['수급률이 높은 원인을 정리'])) == (n == 12))
    rs(12)
    H = lambda q, c, doc='': [i['msg'] for i in verify.check_request(q, c, doc=doc) if i.get('target')]
    t('12f: 금액 == — 상·하한액, 그 금액을 받은 사람을 묻는 질문은 보지 않음',
      not any('같다(==)' in x for x in H('기준소득월액이 상한액 553만원에 해당하는 사람의 비율', "r = ssda.rate('np_inc_amt == 5530000', where='np_yn == 1')"))
      and not any('같다(==)' in x for x in H('2022년 연간 장애인연금 급여액이 4,650,000원인 수급자는 몇 명입니까?', "r = ssda.count(where='disp_yn1 == 1 and disp_amt == 4650000')")))
    DOC = '② 가구 가처분소득의 월평균이 2022년 생계급여 선정기준 이하인 가구의 비율을 가구원수별(1인, 2인, 3~6인)로 제시'
    t('12f: 기준 중위소득 율의 가구원 수별 금액과 다른 코드 점검', any('978,026원' in x for x in H('붙임 문서의 항목을 산출', "w = 'hnum == 2 and h_dinc / 12 <= 1026244'", DOC))
      and not any('기준 중위소득 율' in x for x in H('붙임 문서의 항목을 산출', "w = 'hnum == 2 and h_dinc / 12 <= 978026'", DOC))
      and not any('기준 중위소득 율' in x for x in H('붙임 문서의 항목을 산출', "w = 'hnum == 2 and h_dinc <= 1026244 * 12 / 1000000'", '가구원수별 평균 소득을 산출')))
    t('12f: 제도 카드의 가구원 수별 선정기준 금액', any('2인 978,026원' in l for l in verify.fact_lines('nbls')) and any('2인 가구 월' in l for l in verify.fact_lines('income')))
    t('12f: 반올림 범위 — 차이가 표시 자릿수보다 크거나 덜 정밀한 문서 값은 보지 않음',
      not verify.rounding_claims('문서 10% / 자료 5% → 틀림') and not verify.rounding_claims('문서 300만원 / 자료 350만원 → 틀림')
      and not verify.rounding_claims('문서 9.8% / 자료 6.1% → 틀림') and bool(verify.rounding_claims('4등급 48.7%(문서 48.69%와 다름)')))
    t('12f: 원인 추정 — 판정할 수 없다는 문장·효과를 묻지 않은 질문은 보지 않음',
      not verify.causal_claims('소득이 낮기 때문으로 판단할 수 없음', ['효과']) and not verify.causal_claims('소득이 낮기 때문으로 보임', ['수급자 수를 산출']))
    t('12f: 전제 확인 카드에 까닭을 짐작하지 않는다는 문구', '짐작해 적지 않음' in verify.premise_note([('영아수당 월 50만 원', '영아수당 월액 300,000원')]))
    kr = [c['msg'] for c in verify.check_result(core.count(where='dis_yn == 1', by=['dis_grade_1'])) if c['code'] == '칸 합계']
    t('12f: 칸 합계 — 분류 누락이 없으면 반올림 차이 안내', bool(kr) and '반올림에서 생긴' in kr[0])
    t('12f: 같은 갈래 변수의 「또는」 묶음 — 질문이 일부만 말했을 때만',
      any('같은 갈래' in x for x in H('산정특례 대상자 가운데 암으로 등록된 사람이 몇 명인지', "r = ssda.count(where='nhi_special1_yn == 1 or nhi_special2_yn == 1 or nhi_special4_yn == 1')"))
      and not any('같은 갈래' in x for x in H('산정특례 대상자가 몇 명인지', "r = ssda.count(where='nhi_special1_yn == 1 or nhi_special2_yn == 1')")))
    t('12f: 더 맞는 이름의 변수 — 질문이 긴 이름을 말했을 때만',
      any('원천징수사업소득' in x for x in H('지급할 때 원천징수되는 사업소득이 있었던 사람의 고용보험 가입 비율', "r = ssda.rate('empins_yn1 == 1', where='p_binc > 0')"))
      and not any('원천징수사업소득' in x for x in H('사업소득이 있는 사람의 고용보험 가입 비율', "r = ssda.rate('empins_yn1 == 1', where='p_binc > 0')")))

bad = [n for n, ok in R if not ok]""")

# 12d 시험(「자료에 없음」 진술의 되돌림)의 대본: 질문이 「원천징수되는 사업소득」이고 코드가 p_binc 이므로 12f 의 ⑨가 첫 코드를 돌려보냄 → 같은 코드를 다시 내는 대본으로 바꿈
sub('06_build/v12_probe.py', r"""        a, sc = make(n, [code, ABS, '**결과**\n- 끝'])""",
    r"""        a, sc = make(n, ([code] if n == 12 else []) + [code, ABS, '**결과**\n- 끝'])      # 12f: ⑨(더 맞는 이름의 변수)가 첫 코드를 돌려보내므로 같은 코드를 다시 냄""")

# ── 판 번호 ──
sub('02_library/ssda/__init__.py', "__version__ = '0.7.3'      # ", "__version__ = '0.7.4'      # 0.7.4(2026-11-19): 규칙 묶음 12f — 점검 문구(전체 값·칸 합계), 금액 == 조건·기준 중위소득 금액·같은 갈래 변수의 「또는」 묶음·더 맞는 이름의 변수의 실행 전 점검, 반올림 범위의 판정·원인 추정 문장의 응답 점검. ")
