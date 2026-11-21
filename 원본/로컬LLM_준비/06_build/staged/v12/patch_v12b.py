"""규칙 묶음 12 수정판(12b): 붙임 문서의 「사전에 없는 이름」 안내, 이름 일부만 같은 다른 급여 변수로의 대체 점검. 인자: 대상 루트"""
import sys
from pathlib import Path
root = Path(sys.argv[1])
p = root / '02_library/ssda/verify.py'; t = p.read_text(encoding='utf-8')
def rep(old, new):
    global t
    assert t.count(old) == 1, old[:70]
    t = t.replace(old, new)
rep("""    mon = []
    for v in re.findall(r'\\b([A-Za-z_]\\w*)\\s*\\)?\\s*/\\s*12(?![\\d.])', c):""",
"""    sub = _partial_name_subs(qd, c)
    if sub:                                             # 6차 문서 개발 측정: 자료에 없는 「조기취업성공수당」을 「취업성공수당」 변수로 산출
        out.append(_item('요청 반영', '경고', '; '.join(f"질문·문서의 「{T}」과 코드의 {v}(「{nm}」)는 이름이 다른 제도·급여임" for T, v, nm in sub)
                         + '. 같은 급여임이 참고 자료로 확인되지 않으면 그 변수로 대신 산출하지 말고, 그 항목은 자료에 없음을 밝힐 것. 같은 급여이면 같은 코드를 그대로 다시 내고 근거를 「유의 사항」에 적을 것', target=True))
    mon = []
    for v in re.findall(r'\\b([A-Za-z_]\\w*)\\s*\\)?\\s*/\\s*12(?![\\d.])', c):""")
anchor = "\n\ndef check_request_v12(q, c, prev='', doc=''):"
rep(anchor, '''


_PROG_WORD = re.compile(r'[가-힣]{2,12}?(?:수당|급여|연금|지원금|장려금|바우처|이용권|공제|크레딧|보조금|환급금|지원사업|수급|서비스)')


def _partial_name_subs(text, code):
    """질문·문서의 제도·급여 이름 T 가 변수 사전의 어느 이름·사업명에도 그대로 없는데, 코드가 쓴 변수의 이름에 T 의 일부(4자 이상)만 든 경우 → [(T, 변수, 한글 이름)].
    이름이 더 긴 다른 급여(조기취업성공수당 ↔ 취업성공수당)를 그 이름 일부가 같은 변수로 대신 산출하는 것을 막는다. 규칙 묶음 12."""
    core._load_meta()
    names = ' '.join((m.get('name_ko') or '') + ' ' + (m.get('program') or '') for m in core._META.values())
    used = [v for v in set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', code or '')) if v in core._META]
    terms = {T for T in _PROG_WORD.findall(re.sub(r'\\s+', ' ', text or '')) if len(T) >= 5 and T not in names}
    out = []
    for T in sorted(terms):
        for v in used:
            nm = core._META[v].get('name_ko') or ''
            ws = [w for w in re.split(r'[^가-힣]+', nm) if len(w) >= 4 and w in T and w != T]
            if ws:
                out.append((T, v, nm))
    return out''' + anchor)
p.write_text(t, encoding='utf-8')

a = root / '06_build/assistant.py'; s = a.read_text(encoding='utf-8')
old = """        if extra and not doc:
            cards.append(extra)"""
assert s.count(old) == 1
s = s.replace(old, """        if extra and not doc:
            cards.append(extra)
        if doc:                                                             # 붙임 문서에 나온 「사전에 없는 이름」의 안내(6차 문서 개발 측정: 자료에 없는 급여를 이름 일부가 같은 다른 급여로 산출)
            have_n = set(tr['notes'])
            cards += [n for n in trd.get('notes') or [] if '이 이름 그대로는 없음' in n and n not in have_n][:3]""")
a.write_text(s, encoding='utf-8')
print('patched', root)

# 12b 수정: 용어 사전에 있는 이름은 빼고, 「앞말 + 다른 급여의 완전한 이름」(T 가 변수 이름 낱말 w 로 끝나고 앞말이 2자 이상)만 잡음
t = p.read_text(encoding='utf-8')
old = """    terms = {T for T in _PROG_WORD.findall(re.sub(r'\\s+', ' ', text or '')) if len(T) >= 5 and T not in names}
    out = []
    for T in sorted(terms):
        for v in used:
            nm = core._META[v].get('name_ko') or ''
            ws = [w for w in re.split(r'[^가-힣]+', nm) if len(w) >= 4 and w in T and w != T]"""
assert t.count(old) == 1
t = t.replace(old, """    known = _gloss_terms()
    terms = {T for T in _PROG_WORD.findall(re.sub(r'\\s+', ' ', text or '')) if len(T) >= 5 and T not in names and T not in known}
    out = []
    for T in sorted(terms):
        for v in used:
            nm = core._META[v].get('name_ko') or ''
            ws = [w for w in re.split(r'[^가-힣]+', nm) if len(w) >= 4 and T.endswith(w) and len(T) - len(w) >= 2]      # 앞말이 붙은 더 긴 이름(조기 + 취업성공수당)""")
old2 = "\n\ndef _partial_name_subs(text, code):"
assert t.count(old2) == 1
t = t.replace(old2, '''


def _gloss_terms():
    """용어 사전의 정식 명칭·약어·통칭·구성 급여 이름(사전이 변수로 풀이하는 이름)."""
    s = set()
    for e in _glossary():
        s |= set(e.get('terms') or []) | set(e.get('aliases') or []) | {x['name'] for x in e.get('parts') or []} | {a for x in e.get('parts') or [] for a in (x.get('aliases') or [])}
    return s''' + old2)
p.write_text(t, encoding='utf-8')
print('patched 12b-2')

# 12b-3: 전국(전체) 값과 분류별 값을 함께 묻는 질문에 분류별 집계만 실행한 코드
t = p.read_text(encoding='utf-8')
old = """    sub = _partial_name_subs(qd, c)"""
assert t.count(old) == 1
t = t.replace(old, """    if _TOTAL_REQ.search(q or '') and re.search(r'[가-힣]{1,8}별', q or ''):
        calls = re.findall(r'ssda\\.(count|total|rate|mean|quantile|share)\\(((?:[^()]|\\([^()]*\\))*)\\)', c)
        if calls and all(re.search(r'\\bby\\s*=', args) for _, args in calls):      # 5차 과제 개발 측정: 「전국에 몇 명인지, 시도별로는」에 시도별만 내고 합계를 손으로 더하거나 비움
            out.append(_item('요청 반영', '경고', '질문이 전국(전체) 값도 물음. by 를 주지 않은 같은 집계를 함께 실행해 그 값을 적을 것. 분류별 값을 더해 전체 값으로 적지 않음', target=True))
    sub = _partial_name_subs(qd, c)""")
old2 = "\n\ndef _gloss_terms():"
assert t.count(old2) == 1
t = t.replace(old2, """


_TOTAL_REQ = re.compile(r'전국(?:에|의|적으로)?\\s*(?:몇|규모|합계|총|인원|가구|수급자|이용자|가입자)|전체(?:와|과|\\s*및)\\s*[가-힣]{1,8}별|모두 합(?:친|쳐)|총계')""" + old2)
p.write_text(t, encoding='utf-8')

# 개선판 7: 「A 가운데 B인 사람이 몇 명」, 「각각」의 적용 범위
pp = root / '03_prompts/system_prompt_v7.md'; s = pp.read_text(encoding='utf-8')
old = "- 「A 가운데 B인 사람의 비율」은 A가 분모(`where`), B가 분자임."
assert s.count(old) == 1
s = s.replace(old, "- 「A 가운데 B인 사람의 비율」은 A가 분모(`where`), B가 분자임. 「A 가운데 B인 사람이 몇 명」은 A와 B를 모두 `where`에 `and`로 넣음(A 전체를 세지 않음).")
old = "- 질문이 집단 몇 개의 값만 물으면(「사업장가입자와 지역가입자 각각」) 그 집단만 표에 냄"
assert s.count(old) == 1
s = s.replace(old, "- 질문이 집단 몇 개의 값만 물으면(「사업장가입자와 지역가입자 각각」) 그 지표는 그 집단만 표에 냄. 같은 질문의 다른 지표(예: 「모두 몇 명인지」)는 질문의 대상 전체로 냄\n- 질문이 전국(전체) 값과 분류별 값을 함께 물으면 `by`를 주지 않은 집계를 따로 실행해 전국 값을 냄. 분류별 값을 더해 전국 값으로 적지 않음")
pp.write_text(s, encoding='utf-8')
print('patched 12b-3')

# 12b-4: 점검 줄(전체 값)의 재계산에도 대화 단위 차분 점검을 적용(기록은 하지 않음)
c = root / '02_library/ssda/core.py'; u = c.read_text(encoding='utf-8')
old = "_POP = None               # 직전 _prep 의 대상 — (행 선택, 칸 번호, 칸 수)"
assert u.count(old) == 1
u = u.replace(old, old + "\n_AUDIT_ONLY = False       # 규칙 묶음 12: 점검용 재계산(_QUIET)에서도 차분 점검은 적용하고 기록은 하지 않음(점검 줄의 전체 값이 보충 억제를 우회하지 않게 함)")
old = "    if _SESSION is None or _QUIET or not _SESSION:\n        return 0\n    blocked = 0"
assert u.count(old) == 1
u = u.replace(old, "    if _SESSION is None or (_QUIET and not _AUDIT_ONLY) or not _SESSION:\n        return 0\n    blocked = 0")
old = "    if _SESSION is not None and not _QUIET and _POP is not None:\n        m0, idx0, size0 = _POP"
assert u.count(old) == 1
u = u.replace(old, "    if _SESSION is not None and (not _QUIET or _AUDIT_ONLY) and _POP is not None:\n        m0, idx0, size0 = _POP")
c.write_text(u, encoding='utf-8')
t = p.read_text(encoding='utf-8')
old = """def _quiet(fn, *a, **k):
    core._QUIET = True
    try:
        return fn(*a, **k)
    except (core.ControlError, core.QueryError):
        return None
    finally:
        core._QUIET = False"""
assert t.count(old) == 1
t = t.replace(old, """def _quiet(fn, *a, **k):
    core._QUIET = True
    core._AUDIT_ONLY = v12()                            # 규칙 묶음 12: 점검용 재계산에도 차분 점검 적용(2026-11-19 개발 측정: 보충 억제된 전체 평균이 「참고(전체 값)」 줄로 드러남)
    try:
        return fn(*a, **k)
    except (core.ControlError, core.QueryError):
        return None
    finally:
        core._QUIET = False
        core._AUDIT_ONLY = False""")
p.write_text(t, encoding='utf-8')
print('patched 12b-4')

# 12b-5: 표 전체의 관측 수가 최소 기준 미만이면 모든 칸을 억제(「대상 없음」으로 소수 집단의 위치가 드러나지 않게)
u = c.read_text(encoding='utf-8')
old = """    multi = bool(shape) and int(np.prod(shape)) > 1
    st = np.array(st, np.int8)
    if multi:
        st = _complement(st, key, shape)"""
assert u.count(old) == 1
u = u.replace(old, """    multi = bool(shape) and int(np.prod(shape)) > 1
    st = np.array(st, np.int8)
    if multi and _rs() >= 12 and key is not None and float(np.nansum(np.asarray(key, float))) < THR[grade]:
        st[:] = 1                                       # 규칙 묶음 12(2026-11-19 개발 측정): 소수 집단의 시도별 표에서 「억제」·「대상 없음」의 구분으로 거주 시도가 드러남 → 표 전체 억제
    if multi:
        st = _complement(st, key, shape)""")
c.write_text(u, encoding='utf-8')

# 12b-6: 「몇 세대·몇 가구·가구 수」 질문에 가구 단위가 아닌 코드
t = p.read_text(encoding='utf-8')
old = """    sub = _partial_name_subs(qd, c)"""
assert t.count(old) == 1
t = t.replace(old, """    if re.search(r'몇\\s*(?:세대|가구)(?!원)|(?<![가-힣])(?:세대|가구)\\s*수(?![급령])', q or '') and not re.search(r"unit\\s*=\\s*['\\"]가구['\\"]", c) and re.search(r'ssda\\.(count|total)\\(', c):
        out.append(_item('요청 반영', '경고', "질문이 세대(가구) 수를 물음. 집계에 unit='가구'를 넣어 가구주 한 사람의 행으로 셀 것(개인 단위로 세지 않음)", target=True))      # 5차 과제 개발 측정: 「몇 세대」를 개인 단위로 셈
    sub = _partial_name_subs(qd, c)""")
p.write_text(t, encoding='utf-8')
print('patched 12b-5,6')
