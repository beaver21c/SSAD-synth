#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""규칙 묶음 12d(2026-11-19): 최종판(12c) 개발 측정의 오답 원인에 대한 일반 규칙. 모두 규칙 묶음 12(SSDA_RULESET >= 12)에서만 작동함.

  python3 06_build/staged/v12/patch_v12d.py <대상 폴더(준비 폴더 또는 시험용 사본)>

  ① 붙임 문서가 정한 조건은 질문에 있는 것으로 봄(「질문에 없는 조건」 점검이 문서 본문을 읽음)
  ② 연액 변수에 12를 곱한 코드의 점검(월액 변수를 12로 나눈 코드 점검의 반대 방향)
  ③ 코드값 이름의 대조: 질문·문서가 말한 코드값 이름(「납부예외」)과 코드의 코드값(상실)이 다름 / 질문이 말한 집단(「사업장가입자」)의 변수가 코드에 없음
  ④ 구간 이름 개수 오류에 이름에서 읽은 경계를 제시(define_group)
  ⑤ 제도 기준값 카드에 귀속·지급 연도와 시행일 표기
  ⑥ 「자료에 없음·구분할 수 없음」 진술의 점검(그 이름이 변수 사전의 한글 이름에 있으면 한 번 돌려보냄)
  ⑦ 개선판 7 프롬프트: 앞 차례 값의 대상 유지, 틀린 전제의 정정 문구
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


V = '02_library/ssda/verify.py'

# ① 붙임 문서가 정한 조건
sub(V, """    prev = ' '.join(_clean_q(h) for h in history or ())
    if v9():
        prev = prev + _en_gloss(prev)
    return (out""", """    prev = ' '.join(_clean_q(h) for h in history or ())
    if v9():
        prev = prev + _en_gloss(prev)
    if v12() and doc:                                   # 규칙 묶음 12d: 붙임 문서가 정한 조건은 질문에 있는 것으로 봄(6차 문서 최종판: 문서의 「1인 가구」 조건을 질문에 없는 조건으로 돌려보내 대상이 달라짐)
        prev = (prev + ' ' + _clean_q(doc)).strip()
    return (out""")

# ② ③ check_request_v12 에 추가
sub(V, """    if mon:
        out.append(_item('요청 반영', '경고', f"{', '.join(dict.fromkeys(mon))}의 값은 12월 말 기준 등 한 달의 금액임(변수 카드의 「내용」). 12로 나누지 말고 그대로 비교·집계할 것", target=True))      # 5차 과제 개발 측정: 월액을 연액으로 보고 12로 나눔
    return out
""", """    if mon:
        out.append(_item('요청 반영', '경고', f"{', '.join(dict.fromkeys(mon))}의 값은 12월 말 기준 등 한 달의 금액임(변수 카드의 「내용」). 12로 나누지 말고 그대로 비교·집계할 것", target=True))      # 5차 과제 개발 측정: 월액을 연액으로 보고 12로 나눔
    ann = []                                            # 규칙 묶음 12d: 연액 변수에 12를 곱함(5차 과제 최종판: 연간 경상소득 h_oinc 를 월액으로 보고 12를 곱해 대상이 달라짐)
    for v in re.findall(r'\\b([A-Za-z_]\\w*)\\s*\\)?\\s*\\*\\s*12(?![\\d.])', c) + re.findall(r'(?<![\\w.])12\\s*\\*\\s*\\(?\\s*([A-Za-z_]\\w*)\\b', c):
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
    return out


_MONTHLY = r'12월\\s*말|월액|월\\s*보험료|매월|월평균|월\\s*소득|월\\s*금액|\\(월\\)|월간|한\\s*달'
_LAB_GENERIC = re.compile(r'^(예|아니오|있음|없음|해당|비해당|해당없음|대상|비대상|남|여|남성|여성|남자|여자|결측|기타|그\\s*외|그\\s*밖|미상|모름|무응답|정상|일반|전체)$')
_nz = lambda s: re.sub(r'[\\s·,()_\\-]', '', s or '')


def _labels_of(v):
    lab = (core._META.get(v) or {}).get('labels') or {}
    if isinstance(lab, str):
        try:
            lab = ast.literal_eval(lab)
        except (ValueError, SyntaxError):
            lab = {}
    return {str(k): str(x) for k, x in (lab or {}).items()}


def _label_said(label, tn):
    \"\"\"코드값 이름이 질문(공백 등을 뺀 글)에 나왔는지: 이름 전체, 이름의 둘째 낱말부터(「기초생활보장수급자(생계,의료)」의 「생계」「의료」), 앞 두 글자를 뗀 나머지(「직장피부양자」의 「피부양자」).\"\"\"
    n = _nz(label)
    if len(n) < 2:
        return False
    if n in tn:
        return True
    ws = [w for w in re.split(r'[\\s(),·/]+', label) if len(w) >= 2]
    if len(ws) >= 2 and all(_nz(w) in tn for w in ws[1:]):
        return True
    return len(n) >= 5 and n[2:] in tn


def _code_label_mismatch(text, code):
    \"\"\"질문·문서가 범주형 변수의 코드값 이름(3자 이상, 「납부예외」)을 말했는데 코드는 그 변수의 다른 코드값만 조건으로 쓰고, 코드가 쓴 코드값의 이름은 질문·문서에 없음
    → [(변수, 코드가 쓴 값, 질문이 말한 값, 코드값 이름)]. 규칙 묶음 12d.\"\"\"
    core._load_meta()
    tn = _nz(text)
    out, done = [], set()
    for s in cond_strings(code) or _code_strings(code):
        for v, op, val in re.findall(r"\\b([A-Za-z_]\\w*)\\s*(==|\\bin\\b)\\s*(\\[[^\\]]*\\]|'[^']*'|\\"[^\\"]*\\"|-?\\d+)", s):
            lab = _labels_of(v)
            if len(lab) < 3 or v in done:
                continue
            used = set()
            for x in re.findall(r"-?\\d+(?:\\.0)?|'[^']*'|\\"[^\\"]*\\"", val):
                x = x.strip('\\'"')
                x = x[:-2] if x.endswith('.0') else x
                used.add(x if x in lab else next((k for k, y in lab.items() if y == x), x))
            named = {k for k, y in lab.items() if len(_nz(y)) >= 3 and not _LAB_GENERIC.match(y) and _nz(y) in tn}
            named = {k for k in named if not any(k2 != k and _nz(lab[k]) in _nz(lab[k2]) for k2 in named)}      # 긴 이름에 든 짧은 이름은 뺌
            if named and not (named & used) and not any(_label_said(lab.get(u, ''), tn) for u in used):
                out.append((v, sorted(used), sorted(named), lab))
                done.add(v)
    return out


def _named_group_missing(q, code):
    \"\"\"질문(붙임 문서 제외)이 범주형 변수의 코드값 이름(4자 이상, 「사업장가입자」)을 대상을 좁히는 말로 썼는데 코드에 그 변수가 없고, 코드는 같은 사업 묶음의 다른 변수를 씀
    → [(변수, 코드값, 이름)]. 규칙 묶음 12d.\"\"\"
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
            if len(_nz(y)) >= 4 and not _LAB_GENERIC.match(y) and _nz(y) not in names and re.search(re.escape(y) + r'\\s*(?:인|이었던|였던)?\\s*(?:사람|가구|대상자|자)?\\s*(?:의|가운데|중|만|을|를|이|가|은|는|에서|으로|로|에게|이면서|이고)(?![가-힣])', q or ''):
                out.append((v, k, y))
                break
    return out[:2]
""")

# ⑤ 제도 기준값 카드
sub(V, """def _fmt_fact(r):
    v, u = r.get('value'), r.get('unit') or ''
    if isinstance(v, (int, float)) and u == '원':
        v = f'{v:,.0f}'
    return f"{r['item']} {v}{u}" + (f" ({r['applies']})" if r.get('applies') else '')""", """def _fmt_fact(r):
    v, u = r.get('value'), r.get('unit') or ''
    if isinstance(v, (int, float)) and u == '원':
        v = f'{v:,.0f}'
    when = [r['applies']] if r.get('applies') else []
    if v12():                                           # 규칙 묶음 12d: 귀속·지급 연도와 시행일을 함께 적음(5차 과제 최종판: 2022년 귀속·2023년 지급분의 재산 요건 2.4억 원을 2022년 지급분에 적용)
        mm = re.search(r'(\\d{4})년\\s*귀속[^.\\n]{0,3}?[,·]?\\s*(\\d{4})년\\s*지급', r.get('note') or '')
        if mm:
            when.append(f'{mm.group(1)}년 귀속·{mm.group(2)}년 지급')
        ef = r.get('effective_from') or ''
        if ef and r.get('applies') and ef[:7] > r['applies'][-7:]:
            when.append(f'{ef} 시행')
    return f"{r['item']} {v}{u}" + (f" ({', '.join(when)})" if when else '')""")

sub(V, """    rank = lambda r: 0 if '2022' in (r.get('applies') or '') else 1 if '2021' in (r.get('applies') or '') else 2
    return [_fmt_fact(r) for r in sorted(facts().get(gid, []), key=rank)[:limit]]""", """    rank = lambda r: 0 if '2022' in (r.get('applies') or '') else 1 if '2021' in (r.get('applies') or '') else 2
    if v12():                                           # 규칙 묶음 12d: 같은 항목의 해별 값을 한 줄로 묶음(5차 과제 최종판: 8줄 한도에서 2021년 귀속분의 재산 요건이 빠지고 2022년 귀속분만 남음)
        items = {}
        for r in sorted(facts().get(gid, []), key=lambda r: (rank(r), r.get('applies') or '')):
            items.setdefault(r['item'], []).append(r)
        out = []
        for it, rs in list(items.items())[:max(limit, 10)]:
            parts = [_fmt_fact(r)[len(it) + 1:] for r in sorted(rs, key=lambda r: r.get('applies') or '')]
            out.append(f'{it} ' + ' / '.join(parts))
        return out
    return [_fmt_fact(r) for r in sorted(facts().get(gid, []), key=rank)[:limit]]""")
sub(V, "            + '\\n'.join(f\"- {names.get(g, g)}: \" + ' / '.join(ls) for g, ls in rows))",
    "            + '\\n'.join(f\"- {names.get(g, g)}: \" + ('; '.join(ls) if v12() else ' / '.join(ls)) for g, ls in rows))")

# ⑥ 「자료에 없음」 진술의 점검
sub(V, """_FACTS = None
""", """_ABS_PAT = (re.compile(r'「([^」\\n]{2,24})」[^.\\n「]{0,20}?(?:변수|항목|정보|값)[가-힣]*\\s*(?:가|이|은|는)?\\s*(?:\\[참고 자료\\]에\\s*|자료에\\s*|변수 사전에\\s*|따로\\s*|별도로\\s*)?(?:없|보이지 않|존재하지 않)'),
            re.compile(r'([가-힣·]{2,12}(?:\\s[가-힣·]{2,12})?)\\s*(?:여부|정보|변수|항목|자료)(?:\\s*(?:변수|정보|항목))?(?:[는은이가도]|나|를|을)?\\s*(?:별도로\\s*|따로\\s*|자료에서\\s*|자료로\\s*|자료에\\s*|\\[참고 자료\\]에\\s*)?'
                       r'(?:구분되지 않|구분할 수 없|구분이 안|확인할 수 없|알 수 없|없음|없어|없으며|없고|없다|존재하지 않)'))
_ABS_STOP = re.compile(r'^(여부|구분|및|또는|그리고|등|자료|변수|정보|항목|값|해당|관련|별도|따로|이|그|이런|해당하는|나타내는)')
_ABS_GENERIC = {'지급액', '지원액', '지원금', '보험료', '급여액', '수급자', '가입자', '대상자', '이용자', '금액', '인원', '여부', '기간', '시점', '연령', '가구원수', '가구원', '소득',
                '급여', '지원', '사업', '수당', '연금', '보험', '수급', '가입', '이용', '실적', '횟수', '일수', '구분', '유형', '종류', '기준', '대상', '본인', '부담', '본인부담', '적용', '시행', '제도'}


def absent_claims(reply, used=()):
    \"\"\"응답이 「자료에 없음·구분할 수 없음」이라고 한 이름 가운데 변수 사전의 한글 이름에 그대로 든 것 → [(이름, [(변수, 한글 이름)…])]. 규칙 묶음 12d.
    5차 과제 최종판: 「원천징수」「일용소득」 변수가 있는데 없다고 하고 다른 변수로 산출하거나 거절함. 이름의 낱말이 모두 한 변수의 한글 이름에 있어야 함(「월별 보험료」처럼 일부만 맞으면 보지 않음).\"\"\"
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
            if hits:
                hits.sort(key=lambda x: len(x[1]))
                out.append((key, hits[:4]))
    return out[:2]


def absent_claim_note(found):
    return ('[검증 결과]\\n- 확인(「자료에 없음」 진술의 점검): 응답이 자료에 없다거나 구분할 수 없다고 한 이름이 변수 사전의 한글 이름에 있음 — '
            + '; '.join(f"「{k}」: " + ', '.join(f'{v}({n})' for v, n in hits) for k, hits in found)
            + ". 질문이 말한 항목이면 print(ssda.find_vars('그 이름'))로 정의를 확인한 뒤 그 변수로 다시 산출하고 응답을 고칠 것. 질문의 항목과 뜻이 다른 변수이면 앞의 답을 그대로 다시 적을 것")


_FACTS = None
""")

# ④ define_group 이름 개수 오류
C = '02_library/ssda/core.py'
sub(C, """    if len(labels) != len(bins) + 1:
        raise QueryError(f'labels 개수({len(labels)})는 bins 개수({len(bins)}) + 1 이어야 함. bins={list(bins)} 이면 구간은 ' + ' / '.join(_intervals(bins))
                         + f' 의 {len(bins) + 1}개이고 구간마다 이름이 하나씩 필요함. 대상 집단 밖의 구간(예: 맨 앞 구간)에도 이름을 주고 bins 는 줄이지 않음')""",
    """    if len(labels) != len(bins) + 1:
        raise QueryError(f'labels 개수({len(labels)})는 bins 개수({len(bins)}) + 1 이어야 함. bins={list(bins)} 이면 구간은 ' + ' / '.join(_intervals(bins))
                         + f' 의 {len(bins) + 1}개이고 구간마다 이름이 하나씩 필요함. 대상 집단 밖의 구간(예: 맨 앞 구간)에도 이름을 주고 bins 는 줄이지 않음' + _bins_from_labels(labels))""")
sub(C, """_BY_COND = (""", """def _bins_from_labels(labels):
    \"\"\"규칙 묶음 12d: 이름(「0세」「1세」「2세 이상」)에서 읽은 경계의 제안(5차 과제 최종판: 이름 개수 오류를 네 번 되풀이해 실행 횟수를 다 씀). 읽을 수 없으면 빈 문자열.\"\"\"
    if _rs() < 12 or len(labels) < 2:
        return ''
    nums = [[float(x) for x in re.findall(r'\\d+(?:\\.\\d+)?', str(l))] for l in labels]
    if not all(nums[1:]) or any(('미만' in str(l) or '이하' in str(l)) and len(ns) == 1 for l, ns in zip(labels[1:], nums[1:])):
        return ''
    want = [ns[0] + (1 if '초과' in str(l) and len(ns) == 1 else 0) for l, ns in zip(labels[1:], nums[1:])]
    if not all(a < b for a, b in zip(want, want[1:])):
        return ''
    return (f'. 이름 {len(labels)}개({", ".join(map(str, labels))})가 질문이 정한 구간이면 이름은 그대로 두고 bins=[{", ".join(_fmt_num(x) for x in want)}] 로 고칠 것'
            '(경계는 둘째 구간부터 각 구간이 시작하는 값이고 개수는 이름 수 - 1)')


_BY_COND = (""")

I = '02_library/ssda/__init__.py'
sub(I, "__version__ = '0.7.1'      # 0.7.1(2026-11-19):", "__version__ = '0.7.2'      # 0.7.2(2026-11-19): 규칙 묶음 12d — 구간 이름 개수 오류에 이름에서 읽은 경계를 제시. 0.7.1(2026-11-19):")

# ⑥ 조립기
A = '06_build/assistant.py'
sub(A, "'refuse_gate': 0, 'policy': 0, 'multi': 0}", "'refuse_gate': 0, 'policy': 0, 'multi': 0, 'absent_claim': 0}")
sub(A, """                    self.messages.append({'role': 'user', 'content': verify.multi_gate_note(cand)})
                    continue
""", """                    self.messages.append({'role': 'user', 'content': verify.multi_gate_note(cand)})
                    continue
                if not m and verify.v12() and not hooks['absent_claim'] and n_model < budget:
                    # 규칙 묶음 12d: 응답이 자료에 없다거나 구분할 수 없다고 한 이름이 변수 사전의 한글 이름에 그대로 있으면 한 번 돌려보냄
                    # (5차 과제 최종판: 「원천징수」「일용소득」 변수가 있는데 없다고 하고 다른 변수로 산출하거나 거절함)
                    ac = verify.absent_claims(reply, {v for s in steps for v in re.findall(r'[A-Za-z_]\\w*', s.get('code') or '')})
                    if ac:
                        hooks['absent_claim'] += 1
                        self.seen |= {v for _, hs in ac for v, _ in hs}
                        self.messages.append({'role': 'user', 'content': verify.absent_claim_note(ac)})
                        continue
""")
sub(A, "rec['n_calls'] += hooks['ask_gate'] + hooks['refuse_gate'] + hooks['policy'] + hooks['multi'] +",
    "rec['n_calls'] += hooks['ask_gate'] + hooks['refuse_gate'] + hooks['policy'] + hooks['multi'] + hooks['absent_claim'] +")
# 자체 시험(규칙 묶음 12d)
sub('06_build/v12_probe.py', """
bad = [n for n, ok in R if not ok]""", """
    # ── 규칙 묶음 12d(최종판 개발 측정의 오답 원인) ──
    from ssda import core
    DOC1 = '■ 작성 항목\\n3) 1인 가구 가운데 월평균 가처분소득이 583,444원 이하인 가구의 비율'
    C1 = "r = ssda.rate('h_dinc / 12 <= 583444', where='hnum == 1', unit='가구')"
    Q_NP = '2022년 말 국민연금 사업장가입자 중 기준소득월액이 230만원 미만인 사람 가운데 국민연금 보험료 지원을 받은 사람의 비율은?'
    ABS = '**결과**\\n- 63.7%\\n\\n**유의 사항**\\n- 사업소득(`p_binc`)으로 해석함. 위탁·도급 여부나 원천징수 여부는 별도로 구분되지 않음'
    for n in (11, 12):
        rs(n)
        hold = lambda q, c, doc='': [i['msg'] for i in verify.check_request(q, c, doc=doc) if i.get('target')]
        tag = f'{n}: ' if n == 11 else '12d: '
        t(tag + '붙임 문서의 1인 가구 조건 ' + ('돌려보냄(기존 동작)' if n == 11 else '인정'), any('1인 가구를 가리키는 말이 없음' in x for x in hold('붙임 문서의 항목을 산출해 주세요.', C1, DOC1)) == (n == 11))
        t(tag + '연액 변수 ×12 점검 ' + ('없음' if n == 11 else '작동'), any('1년 동안의 금액' in x for x in hold('선정기준 이하 가구 수', "r = ssda.count(where='h_oinc * 12 <= 9335100', unit='가구')")) == (n == 12))
        t(tag + '「납부예외」에 상실 코드 점검 ' + ('없음' if n == 11 else '작동'), any('np_status == 3' in x for x in hold('납부예외자를 연령 구간별로', "r = ssda.count(where='np_status == 2', by='age3')")) == (n == 12))
        t(tag + '「사업장가입자 중」 가입종별 조건 점검 ' + ('없음' if n == 11 else '작동'), any('np_type == 0' in x for x in hold(Q_NP, "r = ssda.rate('np_support_yn1 == 1', where='np_yn == 1 and np_inc_amt < 2300000')")) == (n == 12))
        t(tag + '맞는 코드에는 점검 없음', not hold(Q_NP, "r = ssda.rate('np_support_yn1 == 1', where='np_type == 0 and np_inc_amt < 2300000')") and not hold('납부예외자 수', "r = ssda.count(where='np_status == 3')"))
        try:
            core.define_group('a01', 'age', [0, 1, 2], ['0세', '1세', '2세 이상']); e = ''
        except Exception as ex:
            e = str(ex)
        t(tag + '구간 이름 개수 오류의 경계 제안 ' + ('없음' if n == 11 else '작동'), ('bins=[1, 2]' in e) == (n == 12))
        fl = ' '.join(verify.fact_lines('itc'))
        if n == 12:
            t('12d: 기준값 카드에 귀속·지급 연도와 2021년 귀속분', '2021년 귀속·2022년 지급' in fl and '200,000,000원' in fl and '2023-01-01 시행' in fl)
            t('12d: 「자료에 없음」 진술 점검(원천징수·일용소득) 작동, 일반 낱말·자료에 없는 제도는 보지 않음',
              verify.absent_claims(ABS, {'p_binc'}) and verify.absent_claims('「일용소득」에 해당하는 변수가 없음', set())
              and not verify.absent_claims('월별 보험료 자료가 없어 비교할 수 없음', set()) and not verify.absent_claims('「조기취업성공수당」 변수가 자료에 없음', set())
              and not verify.absent_claims('적용 여부나 지급액 변수가 자료에 없음', set()))
        code = "```python\\nimport ssda\\nprint(ssda.rate('empins_yn1 == 1', where='p_binc > 0', by='sex'))\\n```"
        a, sc = make(n, [code, ABS, '**결과**\\n- 끝'])
        rec = a.ask('원천징수되는 사업소득이 있었던 사람 가운데 고용보험 가입 비율을 남녀별로')
        t(tag + '「자료에 없음」 진술의 되돌림 ' + ('없음' if n == 11 else '1회'), ((rec.get('hooks') or {}).get('absent_claim', 0) == 1) == (n == 12))
        a.close()

bad = [n for n, ok in R if not ok]""")

# ⑦ 개선판 7 프롬프트
P = '03_prompts/system_prompt_v7.md'
sub(P, "「제도 기준값」의 값을 적용했으면 그 값과 적용 기간을 「유의 사항」에 밝힘.",
    "「제도 기준값」의 값을 적용했으면 그 값과 적용 기간을 「유의 사항」에 밝힘. 귀속·지급 연도가 함께 적힌 값은 변수 카드의 기준(예: 「2021년 귀속 소득분」)과 같은 귀속 연도의 값을 씀.")
sub(P, "질문·문서에 적힌 제도 사실이 「제도 기준값」과 다르면 그 차이를 밝히고 「제도 기준값」의 값으로 적음.",
    "질문·문서에 적힌 제도 사실이 「제도 기준값」과 다르면 그 차이를 밝히고 「제도 기준값」의 값으로 적음. 질문의 전제(금액·대상 연령·시행 시점)가 틀렸으면 「결과」 첫머리에서 「질문의 ○○은 2022년 기준값(△△)과 다름」처럼 바로잡고, 그 금액이 시행된 해를 짐작해 적지 않음.")
sub(P, "- 붙임 문서·여러 항목의 요청: 항목 번호별로 「결과」를 적고, 산출하지 않은 항목은 그 번호와 사유를 「유의 사항」에 적음",
    "- 붙임 문서·여러 항목의 요청: 항목 번호별로 「결과」를 적고, 산출하지 않은 항목은 그 번호와 사유를 「유의 사항」에 적음\n"
    "- 앞 차례에서 산출한 값을 다시 적을 때는 그 차례의 대상·조건을 그대로 적음. 산출하지 않은 대상(연령·집단을 더 좁힌 값 등)의 값처럼 적지 않음")
print('끝')
