#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""규칙 묶음 12e(2026-11-19): 12d 개발 점검(6차 문서)에서 확인한 결함과 오답 원인의 보완.

  python3 06_build/staged/v12/patch_v12e.py <대상 폴더(준비 폴더 또는 시험용 사본)>

  ① 분석 함수 결함(모든 규칙 묶음): define_sum() 합계 변수를 조건식에서 만원 값으로 비교하던 결함.
     조건식은 원래 단위(원)의 값으로 비교함. 6차 문서 12d·12c·1회차·기준 구성(r6_v9)에서 「합계 > 830,000원」이 「대상 없음」으로 나와 0명으로 답함
  ② 변수 찾기(12): 정확히 맞는 이름이 없으면 가운데 낱말을 줄인·풀어 쓴 이름의 변수를 「이름 일부 생략」으로 표시해 보여 줌(「일용근로소득」 → 일용소득)
  ③ 「자료에 없음」 진술 점검(12): 같은 줄임 관계의 변수도 알림
  ④ 「대상 없음」 안내(12): 0명으로 결론 내기 전에 조건의 각 부분을 따로 세어 확인하도록 함(금액 == 비교, 단위가 다른 기준값, 없는 코드값)
  ⑤ 전제 확인 카드(12): 질문·붙임 문서에 적힌 제도 기준값(월액·율 등)이 공식 출처의 기준값과 다르거나 율의 기준(분모)이 다르면 참고 자료에 적음
"""
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


C = '02_library/ssda/core.py'
V = '02_library/ssda/verify.py'
A = '06_build/assistant.py'
I = '02_library/ssda/__init__.py'

# ① define_sum 의 조건식 단위
sub(C, """    a = np.vstack(arrs)
    allnan = np.isnan(a).all(axis=0)
    s = np.nansum(a, axis=0); s[allnan] = np.nan
    _X[name] = (s, label or ' + '.join(vars), units.pop(), _grade_of(used))
    return f"파생 변수 {name} 생성({label or ' + '.join(vars)})\"""",
    """    a = np.vstack(arrs)
    allnan = np.isnan(a).all(axis=0)
    s = np.nansum(a, axis=0); s[allnan] = np.nan
    unit = units.pop()
    raw = s * 1e4 if unit == '만원' and all((_META.get(v) or {}).get('unit') == '원' for v in vars) else s     # 조건식에서는 원래 단위(원)의 값으로 비교함(2026-11-19 12d 개발 점검: 「합계 > 830000」을 만원 값과 비교해 「대상 없음」)
    _X[name] = (s, label or ' + '.join(vars), unit, _grade_of(used), raw)
    return f"파생 변수 {name} 생성({label or ' + '.join(vars)})\"""")
sub(C, """def _col(name, used):
    used.add(name)
    if name in _X:
        return _X[name][0]""", """def _col(name, used):
    used.add(name)
    if name in _X:
        return _X[name][4] if len(_X[name]) > 4 else _X[name][0]      # define_sum 합계 변수: 조건식은 원래 단위의 값""")

# ② 변수 찾기: 가운데 낱말을 줄인·풀어 쓴 이름
sub(C, """    rows.sort(key=lambda x: -x[0])
    return pd.DataFrame([{'변수명': v, '한글 이름': m.get('name_ko', ''), '사업': m.get('program', ''), '단위': m.get('unit', ''), '등급': m.get('grade', ''), '코드값': '; '.join(f'{k}={x}' for k, x in (m.get('labels') or {}).items())[:60]}
                         for _, v, m in rows[:top]])""", """    near = set()
    if _rs() >= 12 and not rows:                        # 규칙 묶음 12e: 맞는 이름이 없으면 가운데 낱말을 줄이거나 풀어 쓴 이름의 변수(「일용근로소득」 → 일용소득). 6차 문서 12d: 빈 결과로 변수가 없다고 단정
        for t in toks:
            for v, m in _META.items():
                if (not only_available or m.get('available', True)) and name_contracts(t, m.get('name_ko', '')):
                    rows.append((1.0 - 0.01 * len(m.get('name_ko', '')), v, m)); near.add(v)
    rows.sort(key=lambda x: -x[0])
    df = pd.DataFrame([{'변수명': v, '한글 이름': m.get('name_ko', ''), '사업': m.get('program', ''), '단위': m.get('unit', ''), '등급': m.get('grade', ''), '코드값': '; '.join(f'{k}={x}' for k, x in (m.get('labels') or {}).items())[:60]}
                       for _, v, m in rows[:top]])
    if near and len(df):
        df['찾은 방식'] = ['이름 일부 생략·풀어 씀(같은 항목인지 var_info 로 확인)' if v in near else '' for _, v, _m in rows[:top]]
    return df


_TARGET_WORDS = ('아동', '청년', '노인', '장애', '영아', '유아', '조기', '여성', '남성', '부부', '단독', '한부모', '가구', '세대', '자녀', '배우자', '중증', '경증', '저소득', '차상위',
                 '긴급', '특별', '추가', '임시', '일시', '농어', '외국', '신규', '재', '부')


def name_contracts(query, name_ko):
    \"\"\"질문의 이름과 변수 한글 이름의 낱말 하나가 가운데 낱말만 다른 줄임·풀어 쓴 관계인지(앞 2자·뒤 2자 이상이 같고 한쪽에만 가운데 낱말이 있음).
    가운데 낱말이 대상·집단을 한정하는 말(아동·청년·조기 등)이면 다른 제도일 수 있으므로 보지 않음(「장애아동수당」과 「장애수당」, 「조기취업성공수당」과 「취업성공수당」).\"\"\"
    q = re.sub(r'[^가-힣A-Za-z0-9]', '', str(query or ''))
    if len(q) < 4 or not re.fullmatch(r'[가-힣]+', q):
        return False
    for w in re.split(r'[^가-힣]+', name_ko or ''):
        if len(w) < 4 or w == q:
            continue
        a, b = (w, q) if len(w) < len(q) else (q, w)
        if len(a) == len(b):
            continue
        for i in range(2, len(a) - 1):
            if b.startswith(a[:i]) and b.endswith(a[i:]):
                mid = b[i:len(b) - (len(a) - i)]
                if mid and not any(t in mid for t in _TARGET_WORDS):
                    return True
    return False""")

# ③ 「자료에 없음」 진술 점검: 줄임 관계의 변수
sub(V, """            hits = [(v, m.get('name_ko', '')) for v, m in core._META.items() if m.get('available', True) and v not in used
                    and all(w in _nz(m.get('name_ko', '')) for w in toks)]
            if hits:""", """            hits = [(v, m.get('name_ko', '')) for v, m in core._META.items() if m.get('available', True) and v not in used
                    and all(w in _nz(m.get('name_ko', '')) for w in toks)]
            if not hits and len(toks) == 1 and v12e():      # 규칙 묶음 12e: 가운데 낱말을 줄인 이름의 변수(6차 문서 12d: 「일용근로소득」 변수가 없다고 했으나 일용소득 p_dainc 가 있음)
                hits = [(v, m.get('name_ko', '')) for v, m in core._META.items() if m.get('available', True) and v not in used and core.name_contracts(toks[0], m.get('name_ko', ''))]
            if hits:""")
sub(V, """def v12():""", """def v12e():
    \"\"\"규칙 묶음 12e(12d 개발 점검의 보완). 규칙 묶음 12에 포함되며, 규칙 묶음 12 와 같은 조건(SSDA_RULESET >= 12)에서 작동함.\"\"\"
    return v12()


def v12():""")

# ④ 「대상 없음」 안내
sub(V, """    elif n_ok == 0 and n_na == n and v9():                  # 조건에 해당하는 대상이 한 명도 없는 경우는 억제가 아님(2026-11-18 독립 검증 4차: 함께 성립하지 않는 자격 조건의 「대상 없음」을 억제로 설명함)
        out.append(_item('대상 없음', '주의', '조건에 해당하는 대상이 자료에 한 명도 없음(억제가 아님). 함께 성립하지 않는 조건(서로 배타적인 자격·구분)을 묶은 것인지 확인할 것. '
                                         '조건이 질문과 같다면 「결과」에 「해당하는 대상이 없음」으로 적고 그 사유(전제가 자료의 구분과 맞지 않음 등)를 밝힘. 「억제」「최소 관측 수 미달」로 설명하지 않음'))""",
    """    elif n_ok == 0 and n_na == n and v12e():                # 규칙 묶음 12e: 0명으로 결론 내기 전에 조건을 나누어 확인(6차 문서 12d: 금액 변수 == 연액 조건, 합계 변수 조건의 「대상 없음」을 실제 0명으로 답함)
        out.append(_item('대상 없음', '주의', '조건에 해당하는 대상이 자료에 한 명도 없음(억제가 아님). 0명으로 결론 내기 전에 조건의 각 부분을 따로 세어(ssda.count) 어느 조건에서 대상이 사라지는지 확인할 것. '
                                         '금액 변수를 특정 금액과 같다(==)로 비교한 조건, 단위가 다른 기준값(원·만원), 자료에 없는 코드값, 함께 성립하지 않는 자격·구분이면 대상이 없게 나옴. '
                                         '확인한 뒤에도 조건이 질문과 같으면 「결과」에 「해당하는 대상이 없음」으로 적고 그 사유를 밝힘. 「억제」「최소 관측 수 미달」로 설명하지 않음'))
    elif n_ok == 0 and n_na == n and v9():                  # 조건에 해당하는 대상이 한 명도 없는 경우는 억제가 아님(2026-11-18 독립 검증 4차: 함께 성립하지 않는 자격 조건의 「대상 없음」을 억제로 설명함)
        out.append(_item('대상 없음', '주의', '조건에 해당하는 대상이 자료에 한 명도 없음(억제가 아님). 함께 성립하지 않는 조건(서로 배타적인 자격·구분)을 묶은 것인지 확인할 것. '
                                         '조건이 질문과 같다면 「결과」에 「해당하는 대상이 없음」으로 적고 그 사유(전제가 자료의 구분과 맞지 않음 등)를 밝힘. 「억제」「최소 관측 수 미달」로 설명하지 않음'))""")

# ⑤ 전제 확인 카드
sub(V, """def fact_note(gids):""", '''_PREM_GENERIC = {'월액', '금액', '지원', '기준', '대상', '연령', '요건', '하한', '상한', '이상', '이하', '미만', '초과', '최대', '최소', '지급액', '지원금', '지원액', '1인당', '연간', '시행일'}
_PREM_QKEY = re.compile(r'\\d|가구|등급|학생|구간|급지|개월|단독|부부|맞벌이|홑벌이|중증|최고|최저|최초|종$|유형|형$')
_PREM_AMT = re.compile(r'((?:\\d[\\d,]*(?:\\.\\d+)?\\s*(?:조|억|천만|백만|만|천)\\s*)+(?:\\d[\\d,]*)?|\\d[\\d,]*(?:\\.\\d+)?)\\s*(원|%(?!\\s*p))')
_PREM_PART = re.compile(r'(\\d[\\d,]*(?:\\.\\d+)?)\\s*(조|억|천만|백만|만|천)?')
_PREM_MULT = {'조': 1e12, '억': 1e8, '천만': 1e7, '백만': 1e6, '만': 1e4, '천': 1e3, None: 1, '': 1}
_PREM_CHANGE = re.compile(r'^\\s*(?:씩|정도\\s*(?:인상|인하)|(?:가량|만큼)?\\s*(?:인상|인하|증가|감소|상향|하향|늘|줄|올|내려|낮|높|많|적|차이|더|추가))')
_PREM_M = re.compile(r'(?<![가-힣0-9])월(?![가-힣])|매월|월액|월평균|한\\s*달')
_PREM_Y = re.compile(r'(?<![가-힣0-9])연(?![가-힣])|연간|연액|1년|한\\s*해')


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
    if re.search(r'(?:^|[\\s(])월(?:[\\s)]|액|$)|월액', item):
        return 'm'
    if re.search(r'(?:^|[\\s(])연(?:[\\s)]|간|$)|연간', item):
        return 'y'
    if re.search(r'1일|(?:^|[\\s(])일(?:\\)|$)|시간당', item):
        return 'd'
    return None


def _prem_years(r):
    a = re.findall(r'(20\\d\\d)', r.get('applies') or '')
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
            base = re.sub(r'\\(.*?\\)', '', r['item']).strip()
            for w in re.split(r'[^0-9A-Za-z가-힣]+', base):
                own.setdefault(w, set()).add(g)
    names = {e['id']: [e['name']] + list(e.get('aliases') or []) for e in _glossary()}
    sents = [s for s in re.split(r'(?<=[.!?])\\s+|\\n+', text or '') if s.strip()]
    out, seen = [], set()
    for g in dict.fromkeys(gids):
        items = {}
        for r in F.get(g, []):
            if isinstance(r.get('value'), (int, float)) and r.get('unit') in ('원', '%'):
                items.setdefault(r['item'], []).append(r)
        for item, rs in items.items():
            base = re.sub(r'\\(.*?\\)', '', item).strip()
            qual = ' '.join(re.findall(r'\\(([^)]*)\\)', item))
            kws = [w for w in re.split(r'[^0-9A-Za-z가-힣]+', base) if len(w) >= 2 and w not in _PREM_GENERIC]
            if not kws:
                continue
            qreq = [w for w in re.split(r'[\\s,·]+', re.sub(r'[가-힣]+\\s*대비', '', qual)) if w and _PREM_QKEY.search(w)]
            if sum(re.sub(r'\\(.*?\\)', '', it).strip() == base for it in items) == 1:      # 같은 이름의 항목이 하나뿐이면 구분(단독가구 등)이 문장에 없어도 대조함
                qreq = []
            qbase = re.sub(r'\\s', '', (re.search(r'([가-힣\\s]+?)\\s*대비', qual) or [None, ''])[1]) if '대비' in qual else ''
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
                if _PREM_CHANGE.match(after) or re.match(r'\\s*(?:→|->|에서)', after) or (unit == '원' and re.search(r'\\d\\s*%', between)):      # 변동 폭·바뀌기 전 값·다른 율을 곱한 값
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
                yrs = lambda t: {int(y) for y in re.findall(r'(20\\d\\d)\\s*년', t)} | {2000 + int(y) for y in re.findall(r"[’'‘]\\s*(\\d\\d)\\s*년", t)}
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
                    mb = re.search(r'([가-힣]{2,})\\s*(?:의|에|대비|에\\s*대한)\\s*(?:[가-힣]+\\s*)?$', between)
                    b = mb.group(1) if mb else ''
                    if b and b not in qbase and qbase not in b and not any(b in k for k in kws):
                        seen.add(key)
                        out.append((quote, f'{item} — 율의 기준이 「{qbase} 대비」임'))
    return out[:3]


def premise_note(found):
    return ('■ 전제 확인(질문·붙임 문서의 값이 제도 기준값과 다름. 계산·판정에는 기준값을 쓰고 「결과」 첫머리에 차이를 밝힘. 질문이 가정한 값으로 계산해 달라고 했으면 그 값을 쓰되 기준값과 다르다는 점을 밝힘)\\n'
            + '\\n'.join(f'- 「{q}」 → 기준값: {f}' for q, f in found))


def fact_note(gids):''')

sub(A, """            fn = verify.fact_note(gids)
            if fn:
                self.shown.update('fact:' + g for g in gids)
                cards.append(fn)""", """            fn = verify.fact_note(gids)
            if fn:
                self.shown.update('fact:' + g for g in gids)
                cards.append(fn)
            if verify.v12e():                                               # 규칙 묶음 12e: 질문·붙임 문서의 기준값이 공식 출처의 값과 다르면 알림(6차 문서 12d: 틀린 전제 X 유형 적절 4/8)
                allg = [c['id'][5:] for c in tr['cards'] + trd['cards'] if c['id'].startswith('term:')] + [m['id'] for m in tr['matches'] + trd['matches']]
                pi = [x for x in verify.premise_issues(text, list(dict.fromkeys(allg))) if 'premise:' + x[0] not in self.shown]
                if pi:
                    self.shown.update('premise:' + x[0] for x in pi)
                    cards.append(verify.premise_note(pi))""")

# ⑦ 이용자를 금액 > 0 으로 정한 코드(12e)
sub(V, """    sub = _partial_name_subs(qd, c)
    if sub:""", """    if v12e():                                          # 규칙 묶음 12e: 「입원 진료를 받은 사람」을 본인부담금 > 0 으로 정함(6차 문서 12c·12d: W2-D05·W2-D07, 본인부담이 0원인 입원자가 빠져 평균이 커짐)
        for ph, v, sib in _use_by_amount(qd, c):
            out.append(_item('요청 반영', '경고', f"질문의 「{ph}」 사람은 이용 일수로 정함({sib} > 0). {v} > 0 으로 정하면 금액이 0원인 이용자(본인부담 면제·감면 등)가 빠짐. "
                             '질문이 금액이 있는 사람을 뜻하면 같은 코드를 그대로 다시 낼 것', target=True))
    sub = _partial_name_subs(qd, c)
    if sub:""")
sub(V, """def check_request_v12(q, c, prev='', doc=''):""", """_USE_Q = re.compile(r'입원(?:한|했던|을\\s*한|\\s*진료를\\s*받은|\\s*환자|자(?![격료]))|외래\\s*진료를\\s*받은|진료를\\s*받은|내원한|의료기관을\\s*이용한')
_FEE_Q = re.compile(r'본인부담(?:금|액)?(?:이|을|가)?\\s*(?:낸|있는|있었던|발생|부담한|0원\\s*초과|0원보다)|금액이\\s*있는')


def _use_by_amount(qd, c):
    \"\"\"「입원 진료를 받은 사람」 등 이용자를 금액 변수 > 0 으로 정한 코드 → [(질문의 말, 금액 변수, 일수 변수)]. 같은 이름의 일수 변수(_dur)가 있을 때만 봄.\"\"\"
    m = _USE_Q.search(qd or '')
    if not m or _FEE_Q.search(qd or ''):
        return []
    out = []
    for s in cond_strings(c) or _code_strings(c):
        for v, op, num in re.findall(r'\\b([A-Za-z_]\\w*)\\s*(>|>=)\\s*(\\d+(?:\\.\\d+)?)(?![\\d.])', s):
            if (op == '>' and float(num) != 0) or (op == '>=' and float(num) > 1):
                continue
            if (core._META.get(v) or {}).get('unit') != '원' or not re.search(r'_(fee|amt|subsidy)$', v):
                continue
            sib = re.sub(r'_(fee|amt|subsidy)$', '_dur', v)
            if sib in core._META and sib not in c and core._META[sib].get('unit') in ('일', '회'):
                out.append((m.group(0), v, sib))
    return list(dict.fromkeys(out))[:2]


def check_request_v12(q, c, prev='', doc=''):""")

# ⑥ 자체 시험(v12_probe.py)
P = '06_build/v12_probe.py'
sub(P, """bad = [n for n, ok in R if not ok]
for n in bad:""", """    # ── 규칙 묶음 12e(12d 개발 점검의 보완) ──
    for n in (11, 12):
        rs(n)
        core.define_sum('fee_t', ['nhi_out_fee', 'nhi_in_fee'], '합계')
        cnt = core.count(where='fee_t > 830000').table()
        t(f'{n}: 합계 변수 조건을 원 단위로 비교(모든 규칙 묶음)', len(cnt) and float(cnt.iloc[0]['값'] or 0) > 1e6)
        fv = core.find_vars('일용근로소득')
        t(('12e' if n == 12 else '11') + ': 줄임 이름 변수 찾기 ' + ('작동' if n == 12 else '없음'), ('p_dainc' in list(fv.get('변수명', []))) == (n == 12))
        r0 = [c for c in verify.check_result(core.count(where='bp_amt == 4800000 and age >= 65')) if c['code'] == '대상 없음']
        t(('12e' if n == 12 else '11') + ': 「대상 없음」 안내에 조건 나누어 세기 ' + ('있음' if n == 12 else '없음'), bool(r0) and (('ssda.count' in r0[0]['msg']) == (n == 12)))
        PQ = '2022년 1월 1일 이후 출생아에게 영아수당 월 50만 원을 현금으로 지급함. 영아수당 수급 아동의 연간 평균 수급액을 산출'
        t(('12e' if n == 12 else '11') + ': 전제 확인 카드 ' + ('작동' if n == 12 else '없음'), bool(verify.premise_issues(PQ, ['child_support']) if n == 12 else not verify.v12e()))
    rs(12)
    t('12e: 줄임 이름 — 대상을 한정하는 가운데 낱말·자료에 없는 제도는 보지 않음', not core.name_contracts('장애아동수당', '장애수당') and core.find_vars('조기취업성공수당').empty
      and core.name_contracts('일용근로소득', '일용소득'))
    t('12e: 「자료에 없음」 진술 점검에 줄임 이름', any(v == 'p_dainc' for k, h in verify.absent_claims('자료에 「일용근로소득」 변수가 없음') for v, _ in h))
    t('12e: 전제 확인 — 맞는 값·다른 율을 곱한 값·변동 폭·바뀌기 전 값은 보지 않음',
      not verify.premise_issues('2022년 영아수당은 월 30만 원임', ['child_support'])
      and not verify.premise_issues('생계급여 선정기준은 기준 중위소득의 30%로 1인 가구 월 583,444원임', ['income', 'nbls'])
      and not verify.premise_issues('2022년 귀속 근로장려금의 총소득 기준금액이 가구 유형별로 200만 원씩 올랐음', ['itc'])
      and not verify.premise_issues("직장가입자 건강보험료율은 '20년 6.67% → '21년 6.86%로 오름", ['nhi_premium']))
    hold12 = lambda q, c, doc='': [i['msg'] for i in verify.check_request(q, c, doc=doc) if i.get('target')]
    t('12e: 「입원 진료를 받은 사람」을 본인부담금 > 0 으로 정한 코드 점검', any('nhi_in_dur > 0' in x for x in hold12('붙임 문서의 항목을 산출', \"r = ssda.mean('nhi_in_fee', where='nhi_in_fee > 0')\", '③ 입원 진료를 받은 사람의 1인당 본인부담금 평균'))
      and not any('nhi_in_dur' in x for x in hold12('붙임 문서의 항목을 산출', \"r = ssda.mean('nhi_in_fee', where='nhi_in_fee > 0')\", '③ 입원 본인부담금이 있는 사람의 평균')))
    t('12e: 전제 확인 — 율의 기준(분모)이 다름', any('율의 기준' in f for _, f in verify.premise_issues('2022년 장기요양보험료율은 소득의 12.27%로 매김', ['nhi_premium'])))
    a, sc = make(12, ['**결과**\\n- 끝'])
    a.ask('붙임 문서의 항목을 산출해 주세요.', extra_context='■ 붙임 문서\\n○ 2022년 1월 1일 이후 출생아에게 영아수당 월 50만 원을 현금으로 지급함\\n① 영아수당 수급 아동 수')
    t('12e: 전제 확인 카드가 참고 자료에 붙음', '■ 전제 확인' in sc.seen[0][1]['content'] and '300,000원' in sc.seen[0][1]['content'])
    a.close()
    a, sc = make(11, ['**결과**\\n- 끝'])
    a.ask('붙임 문서의 항목을 산출해 주세요.', extra_context='■ 붙임 문서\\n○ 2022년 1월 1일 이후 출생아에게 영아수당 월 50만 원을 현금으로 지급함\\n① 영아수당 수급 아동 수')
    t('11: 전제 확인 카드 없음(기존 동작)', '■ 전제 확인' not in sc.seen[0][1]['content'])
    a.close()

bad = [n for n, ok in R if not ok]
for n in bad:""")

sub(I, "__version__ = '0.7.2'      # ", "__version__ = '0.7.3'      # 0.7.3(2026-11-19): define_sum() 합계 변수를 조건식에서 원래 단위(원)로 비교(모든 규칙 묶음), 규칙 묶음 12e — 변수 찾기의 줄임·풀어 쓴 이름. ")
print('끝')
