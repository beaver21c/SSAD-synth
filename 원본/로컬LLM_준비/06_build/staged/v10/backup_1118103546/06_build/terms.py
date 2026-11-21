# -*- coding: utf-8 -*-
"""제도 용어 해석 — 질문에 나온 제도명·약어·통칭을 제도 용어 사전(01_knowledge/programs/glossary.json)과 대조한다.

  resolve(question, pending)   질문의 용어를 찾아 「제도 설명」 카드, 검색 확장어, 내역이 정해지지 않은 용어 목록을 돌려준다
  check(unresolved, used)      내역이 정해지지 않은 용어가 있는데 코드를 실행했으면 「[검증 결과]」에 넣을 항목을 만든다

내역이 정해졌다고 보는 경우  질문에 구성 급여의 이름·별칭이 있음 / 사전의 resolvers 낱말이 있음 / (수급자·수급률) 다른 제도명이 함께 있음
정책  ask: 「확인 필요」로 되묻게 함 / assume: 기본 해석으로 진행하고 가정으로 밝히게 함 / absent: 자료에 없는 항목임을 알리게 함

조립기와 학습 자료 생성기가 같은 함수를 쓴다.
"""
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = ROOT / '01_knowledge' / 'programs' / 'glossary.json'
def jo(word, pair):
    """받침에 따라 조사를 고른다. pair 예: '을를', '은는', '이가'."""
    w = re.sub(r'[)\]」\s]+$', '', word); c = w[-1] if w else ''
    has = ('가' <= c <= '힣' and (ord(c) - 0xAC00) % 28 != 0) or c.lower() in 'lmnr136780'
    return pair[0] if has else pair[1]


def _v9():
    """규칙 묶음 9(독립 검증 4차 뒤의 조치)를 쓰는지. 조립기가 환경변수 SSDA_RULESET 으로 정한다(ssda.verify.v9 와 같은 값)."""
    try:
        return int(os.environ.get('SSDA_RULESET') or 8) >= 9
    except ValueError:
        return False


# 제도·급여 이름의 끝말(사전에 없는 제도명을 찾을 때 씀)과, 앞말이 일반 낱말이어서 제도명으로 보지 않는 경우
_PROG_SUFFIX = r'(?:수당|급여|연금|지원금|장려금|보상금|바우처|이용권|보험|적금|계좌|공제|크레딧|보조금|환급금|장학금|지원비|지원사업|시범사업|지원제도)'
_GENERIC_STEM = set('평균 월평균 연평균 총 전체 해당 관련 각종 기타 현금 현물 정기 수시 사회 공적 사적 민간 공공 복지 정부 국가 지자체 본인 가구 개인 연간 주요 다른 어떤 무슨 이런 그런 받은 받는 '
                    '지급 수령 월 연 일 누적 각 모든 여러 해당자 대상자 수급자 가입자 이용자 급여별 제도별 사업별 종류별 유형별 미수령 미지급 과오 부정 중복 이중 최대 최소 최고 최저 기준 평균적 일반'.split())

LOOKUP = re.compile(r'변수|항목이 있|무슨 뜻|뜻하는|뜻인지|의미하는|설명해|정의|코드값|어떤 급여|무엇이 있|종류|차이가 뭐|차이를 알려|구성돼|구성되')


class Glossary:
    def __init__(self, path=GLOSSARY):
        self.entries = json.loads(Path(path).read_text(encoding='utf-8'))
        self.by_id = {e['id']: e for e in self.entries}
        idx = {}
        for e in self.entries:                                   # 항목의 정식 명칭·약어·통칭
            for t in e['terms']:
                idx.setdefault(t, (e['id'], None))
        for e in self.entries:                                   # 구성 급여의 이름(3글자 이상, 항목 용어와 겹치지 않는 것)
            for p in e.get('parts') or []:
                if len(p['name']) >= 3:
                    idx.setdefault(p['name'], (e['id'], p['name']))
        for e in self.entries:                                   # 항목의 용어 목록에도 들어 있는 구성 급여의 이름·별칭(「보육료 지원」「양육수당」)은 그 급여 하나를 가리킴
            for p in e.get('parts') or []:                       # (2026-11-17 독립 검증 2차: 「보육료 지원을 받는 아동」에 어느 급여인지 되물음)
                for nm in [p['name']] + list(p.get('aliases') or []):
                    if len(nm) >= 3 and idx.get(nm) == (e['id'], None):
                        idx[nm] = (e['id'], p['name'])
        self.index = sorted(idx.items(), key=lambda kv: -len(kv[0]))
        self._voc = None
        self.compounds = []                                      # 직전 match() 에서 다른 낱말의 일부로만 나와 건너뛴 용어: [(낱말 전체, 건너뛴 용어)]

    def _vocab(self):
        """사전에 실린 이름 전부(제도 용어 사전의 용어·구성 급여, 변수 사전의 한글 이름·사업명)를 이어 붙인 문자열. 어떤 낱말이 사전에 있는 말인지 볼 때 쓴다."""
        if self._voc is None:
            parts = [t for e in self.entries for t in e['terms']]
            parts += [x for e in self.entries for p in (e.get('parts') or []) for x in [p['name']] + list(p.get('aliases') or [])]
            try:
                from ssda import core
                core._load_meta()
                parts += [(m.get('name_ko') or '') + '|' + (m.get('program') or '') + '|' + (m.get('content') or '') + '|' + '|'.join(str(x) for x in (m.get('labels') or {}).values())
                          for m in core._META.values()]      # 변수의 설명문과 코드값 이름에 있는 말도 사전에 있는 말로 봄(「정기연금(퇴직연금·유족연금 등)」, 「정신장애」)
            except Exception:                                    # noqa: BLE001 — 변수 사전을 읽지 못하는 환경에서는 용어 사전만 씀
                pass
            self._voc = '|'.join(re.sub(r'[\s_·()\[\]「」/]+', '', x) for x in parts)
        return self._voc

    def unknown_programs(self, text, matched=()):
        """질문에 적힌 제도·급여 이름 가운데 제도 용어 사전과 변수 사전 어디에도 없는 것(2026-11-18 독립 검증 4차: 자료에 없는 사업을 이름이 일부 겹치는 다른 항목으로 되묻거나 바꿔 산출하려 함).
        끝말(수당·급여·연금·지원금 등)로 제도명 꼴의 낱말을 고르고, 그 이름이 사전의 어느 이름에도 들어 있지 않으며 사전의 용어를 품고 있지도 않으면 사전에 없는 이름으로 본다."""
        text = re.sub(r'```.*?```', ' ', text or '', flags=re.S)
        voc = self._vocab(); out = []
        known_terms = [t for t, _ in self.index if len(t) >= 3]
        for tok in re.findall(r'[가-힣A-Za-z0-9]{4,}', text):
            m = re.match(r'([가-힣A-Za-z0-9]{2,}?' + _PROG_SUFFIX + ')', tok)
            if not m:
                continue
            name = m.group(1); stem = re.sub(_PROG_SUFFIX + '$', '', name)
            if len(stem) < 2 or stem in _GENERIC_STEM or re.fullmatch(r'[0-9A-Za-z]+', stem) or name in out:
                continue
            if name in voc or any(t in name for t in known_terms) or any(name in t for t in matched):
                continue
            out.append(name)
        return out

    def match(self, text):
        """긴 용어부터 찾고, 이미 찾은 자리와 겹치는 짧은 용어는 버린다. [(용어, 항목 id, 구성 급여 이름 또는 None)]"""
        text = re.sub(r'```.*?```', ' ', text or '', flags=re.S)
        used = [False] * len(text); out = []
        self.compounds = []
        v9 = _v9()
        for term, (eid, part) in self.index:
            for m in re.finditer(re.escape(term), text):
                if not any(used[m.start():m.end()]):
                    if v9 and part is None and self.by_id[eid].get('kind') == '용어':
                        # 일반 낱말(의료비·보험료·연금 등)이 사전에 없는 앞말에 붙어 한 낱말을 이루면 다른 항목의 이름임(「재난적의료비」의 「의료비」). 그 낱말의 규칙을 적용하지 않음
                        k = m.start()
                        while k > 0 and '가' <= text[k - 1] <= '힣':
                            k -= 1
                        pre = text[k:m.start()]
                        if not pre and k > 1 and text[k - 1] == ' ':     # 띄어 쓴 「…적 + 낱말」(「재난적 의료비」)도 한 이름으로 봄
                            j = k - 1
                            while j > 0 and '가' <= text[j - 1] <= '힣':
                                j -= 1
                            if text[j:k - 1].endswith('적') and len(text[j:k - 1]) >= 3:
                                pre, k = text[j:k - 1], j
                        if len(pre) >= 2 and pre not in self._vocab() and pre not in _GENERIC_STEM:
                            for i in range(k, m.end()):
                                used[i] = True
                            self.compounds.append((text[k:m.end()], term))
                            continue
                    for i in range(m.start(), m.end()):
                        used[i] = True
                    out.append((term, eid, part, m.start()))
        out.sort(key=lambda x: x[3])
        seen, res = set(), []
        for term, eid, part, _ in out:
            if (eid, part) not in seen:
                seen.add((eid, part)); res.append((term, eid, part))
        return res

    def _resolved(self, e, text, matches, prev=()):
        amb = e.get('ambiguity') or {}
        if amb.get('policy') == 'absent':
            return False
        if amb.get('needs_program'):                             # 수급자·수급률: 다른 제도명·급여명이 함께 있으면 정해진 것
            if any(eid != e['id'] for _, eid, part in list(matches) + list(prev)):      # prev: 같은 대화의 앞선 질문에 나온 제도(이어 묻는 질문은 그 제도를 이어받음)
                return True
            return any(w in text for x in self.entries for p in (x.get('parts') or []) for w in [p['name']] + list(p.get('aliases') or []) if len(w) >= 4) or bool(re.search(r'[a-z]+_[a-z0-9_]+', text))
        words = list(amb.get('resolvers') or [])
        for p in e.get('parts') or []:
            words += [p['name']] + list(p.get('aliases') or [])
        return any(w in text for w in words)

    @staticmethod
    def _named_var(term, q):
        """질문에 그 용어가 든 변수의 한글 이름이 그대로 적혀 있으면 그 변수(예: 「공적연금 총연금수령액」 → pubpen_inc). 없으면 None."""
        try:
            from ssda import core
            core._load_meta()
        except Exception:                                        # noqa: BLE001 — 변수 사전을 읽지 못하는 환경에서는 이 규칙을 쓰지 않음
            return None
        nq = re.sub(r'[\s_·()\[\]「」]+', '', q)
        best = None
        for v, m in core._META.items():
            name = re.sub(r'[\s_·()\[\]「」]+', '', m.get('name_ko') or '')
            if m.get('available', True) and str(m.get('grade', '')) != '제외' and term in name and len(name) >= len(term) + 2 and name in nq and (best is None or len(name) > len(best[2])):
                best = (v, m.get('name_ko'), name)
        return best[:2] if best else None

    def _other_program_var(self, e, term, matches):
        """용어가 그 항목의 줄인 말(예: 「건강보험료」의 「보험료」)이고 질문에 다른 제도의 이름이 있으며, 그 제도에 같은 낱말의 변수가 있으면 (제도 이름, [변수…])."""
        if not any(term != t and term in t for t in e['terms']):
            return None
        try:
            from ssda import core
            core._load_meta()
        except Exception:                                        # noqa: BLE001
            return None
        for t2, eid2, _ in matches:
            if eid2 in (e['id'], 'recipient', 'absent_2022') or len(t2) < 3:
                continue
            vs = [v for v, m in core._META.items() if m.get('available', True) and term in (m.get('name_ko') or '') and t2 in ((m.get('name_ko') or '') + ' ' + (m.get('program') or ''))]
            if vs:
                return t2, vs
        return None

    REQUEST = re.compile(r'주세요|주십시오|주시기|바랍니다|바람|요망|부탁|알려|구해|뽑아|산출|계산|보여|궁금|정리해|제출|몇\s?[명가%퍼프사]|얼마|\?|인지요|나요|까요|ㄹ까|은요|는요|줘|주라|해 봐|알고 싶|보고 싶|필요합니다|필요함')

    def resolve(self, question, pending=None, history=()):
        q = re.sub(r'```.*?```', ' ', question or '', flags=re.S)
        ms = self.match(q)
        comp = list(self.compounds)                              # 이번 질문에서 건너뛴 합성어(아래 앞선 질문의 대조가 이 목록을 덮어쓰므로 먼저 받아 둠)
        prev = self.match(' '.join(history)) if history else []
        sents = [x for x in re.split(r'(?<=[.?!。])\s+|\n+', q) if x.strip()]
        req_text = ' '.join(x for x in sents if self.REQUEST.search(x))
        cards, expansion, unresolved, notes = [], [], [], []
        if _v9():                                                # 사전에 없는 제도·항목 이름: 이름이 일부 겹치는 다른 항목으로 바꾸거나 그 내역을 되묻지 않게 함
            unknown = [w for w, _ in comp] + self.unknown_programs(q, [t for t, _, _ in ms])
            for w in list(dict.fromkeys(unknown))[:3]:
                notes.append(f"■ 용어 확인: 「{w}」\n제도 용어 사전과 변수 사전에 이 이름이 없음. 이름이 일부 겹치는 다른 제도·항목의 변수로 바꿔 산출하거나 그 내역을 되묻지 않음. "
                             f"같은 제도를 다르게 적은 말일 수 있으므로 print(ssda.find_vars('핵심 낱말'))로 먼저 확인하고, 해당 변수가 없으면 「요청 처리 불가」로 자료에 없음을 밝히고 이 자료로 낼 수 있는 집계를 「가능한 대안」에 적을 것")
        for term, eid, part in ms:
            e = self.by_id[eid]
            if e['id'] != 'absent_2022':
                ttl = e['name'] + (f"(질문의 「{term}」)" if term != e['name'] else '')
                lead = f"질문의 「{term}」은 이 제도의 구성 급여 「{part}」을 가리킴. 그 급여의 변수로 산출하고, 다른 급여와 묶거나 어느 급여인지 되묻지 않음\n" if part else ''
                cards.append({'id': 'term:' + eid, 'title': '제도 설명: ' + ttl, 'text': lead + e['card']})
                expansion += [e['name']] + [p['name'] for p in (e.get('parts') or []) if part in (None, p['name'])][:4]
            amb = e.get('ambiguity')
            if amb and part is None and not self._resolved(e, q, ms, prev):
                if amb['policy'] == 'ask':
                    nv = self._named_var(term, q)
                    if nv:                                       # 질문에 변수의 한글 이름이 그대로 있음 → 그 변수로 정해진 것(2026-11-17 독립 검증: 「공적연금 총연금수령액」에 어느 연금인지 되물음)
                        notes.append(f"■ 용어 확인: 「{term}」\n질문에 변수 {nv[0]}({nv[1]})의 이름이 그대로 적혀 있으므로 그 변수로 산출함. 되묻지 않음")
                        continue
                    ov = self._other_program_var(e, term, ms)
                    if ov:                                       # 다른 제도의 이름과 함께 쓰인 일반 낱말(「군인연금 … 보험료」) → 그 제도의 변수를 가리킴
                        notes.append(f"■ 용어 확인: 「{term}」\n질문의 「{ov[0]}」에 딸린 항목임({', '.join(ov[1][:3])}). 그 제도의 변수로 산출하고 되묻지 않음")
                        continue
                    if req_text and len(sents) >= 2 and term not in req_text:      # 요청 문장이 따로 있고 용어는 배경 설명에만 쓰임 → 산출 조건이 아님
                        notes.append(f"■ 용어 확인: 「{term}」\n배경 설명에 쓰인 말이며 산출 조건이 아님. 요청 문장에 적힌 대상·지표·분류대로 산출하고 되묻지 않음")
                        continue
                ask = amb.get('ask', '')
                if amb['policy'] == 'absent':
                    ask = f"자료에 없는 항목임. {(e.get('alternatives') or {}).get(term, '대신 볼 변수가 없음')}"
                unresolved.append({'id': eid, 'term': term, 'name': e['name'], 'policy': amb['policy'], 'ask': ask, 'default': amb.get('default', ''), 'vars': e['all_vars']})
        for u in pending or []:                                  # 앞선 질문에서 되물은 용어: 이번 답에 내역이 있으면 정해진 것
            e = self.by_id[u['id']]
            if not self._resolved(e, q, ms, prev) and u['id'] not in {x['id'] for x in unresolved}:
                unresolved.append(dict(u, carried=True))
        open_terms = {u['term'] for u in unresolved}
        for u in list(unresolved):                               # 「본인부담 보험료」처럼 되물을 용어 바로 뒤에 내역이 정해진 다른 용어가 이어지면 그 용어를 꾸미는 말임
            heads = [t for t, eid, _ in ms if t != u['term'] and t not in open_terms and eid != 'recipient']      # 「수급자·수급률」은 앞말의 범위를 정해 주지 않음
            if u['policy'] == 'ask' and not u.get('carried') and heads and re.search(re.escape(u['term']) + r'\s?(' + '|'.join(re.escape(t) for t in heads) + ')', q):
                unresolved.remove(u)
                notes.append(f"■ 용어 확인: 「{u['term']}」\n뒤에 오는 항목을 꾸미는 말이며 따로 되묻지 않음")
        if LOOKUP.search(q):                                     # 변수 찾기·제도 설명 요청은 내역을 정할 필요가 없음
            unresolved = []
        seen = set(); cards = [c for c in cards if not (c['id'] in seen or seen.add(c['id']))]
        for u in unresolved:
            if u['policy'] == 'ask':
                notes.append(f"■ 용어 확인: 「{u['term']}」\n질문에 내역이 정해져 있지 않음. 코드를 쓰지 말고 「확인 필요」로 다음을 물을 것: {u['ask']}")
            elif u['policy'] == 'assume':
                notes.append(f"■ 용어 확인: 「{u['term']}」\n질문에 내역이 없으면 {u['default']}로 해석하고 「분석 계획」의 가정에 밝힐 것. 다른 해석: {u['ask']}")
            else:
                notes.append(f"■ 용어 확인: 「{u['term']}」\n{u['ask']}. " + ('되묻지 말고 코드 없이 「요청 처리 불가」에 자료에 없다는 사실을 적고 「가능한 대안」에 대신 볼 수 있는 변수를 적을 것' if _v9()
                             else '코드를 쓰지 말고 「확인 필요」에 자료에 없다는 사실과 대신 볼 수 있는 변수를 적을 것'))
        return {'matches': [{'term': t, 'id': i, 'part': p} for t, i, p in ms], 'cards': cards, 'notes': notes, 'unresolved': unresolved, 'expansion': ' '.join(dict.fromkeys(expansion))}

    @staticmethod
    def check(unresolved, used_vars):
        """내역이 정해지지 않은 용어가 있는데 코드를 실행한 경우의 점검 항목."""
        out = []
        for u in unresolved or []:
            hit = [v for v in used_vars if v in u['vars']]
            if u['policy'] == 'ask':
                out.append({'code': '용어', 'level': '주의', 'term': u['term'], 'used': hit,
                            'msg': f"질문의 「{u['term']}」{jo(u['term'], '은는')} 범위가 정해지지 않은 말임({u['ask']}). 코드는 {', '.join(hit) if hit else '해당 제도의 변수가 아닌 변수'}를 사용함. "
                                   '이 해석을 「유의 사항」에 밝히고 다른 해석이 가능함을 알릴 것'})
            elif u['policy'] == 'assume':
                out.append({'code': '용어', 'level': '참고', 'term': u['term'], 'used': hit, 'msg': f"「{u['term']}」{jo(u['term'], '을를')} {u['default']}로 해석함. 「분석 계획」의 가정 또는 「유의 사항」에 밝힐 것"})
            else:
                out.append({'code': '용어', 'level': '주의', 'term': u['term'], 'used': hit, 'msg': f"「{u['term']}」{jo(u['term'], '은는')} 자료에 없는 항목임. 대신 쓴 변수와 그 차이를 「유의 사항」에 밝힐 것"})
        return out
