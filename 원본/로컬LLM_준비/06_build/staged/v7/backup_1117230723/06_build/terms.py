# -*- coding: utf-8 -*-
"""제도 용어 해석 — 질문에 나온 제도명·약어·통칭을 제도 용어 사전(01_knowledge/programs/glossary.json)과 대조한다.

  resolve(question, pending)   질문의 용어를 찾아 「제도 설명」 카드, 검색 확장어, 내역이 정해지지 않은 용어 목록을 돌려준다
  check(unresolved, used)      내역이 정해지지 않은 용어가 있는데 코드를 실행했으면 「[검증 결과]」에 넣을 항목을 만든다

내역이 정해졌다고 보는 경우  질문에 구성 급여의 이름·별칭이 있음 / 사전의 resolvers 낱말이 있음 / (수급자·수급률) 다른 제도명이 함께 있음
정책  ask: 「확인 필요」로 되묻게 함 / assume: 기본 해석으로 진행하고 가정으로 밝히게 함 / absent: 자료에 없는 항목임을 알리게 함

조립기와 학습 자료 생성기가 같은 함수를 쓴다.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = ROOT / '01_knowledge' / 'programs' / 'glossary.json'
def jo(word, pair):
    """받침에 따라 조사를 고른다. pair 예: '을를', '은는', '이가'."""
    w = re.sub(r'[)\]」\s]+$', '', word); c = w[-1] if w else ''
    has = ('가' <= c <= '힣' and (ord(c) - 0xAC00) % 28 != 0) or c.lower() in 'lmnr136780'
    return pair[0] if has else pair[1]


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

    def match(self, text):
        """긴 용어부터 찾고, 이미 찾은 자리와 겹치는 짧은 용어는 버린다. [(용어, 항목 id, 구성 급여 이름 또는 None)]"""
        text = re.sub(r'```.*?```', ' ', text or '', flags=re.S)
        used = [False] * len(text); out = []
        for term, (eid, part) in self.index:
            for m in re.finditer(re.escape(term), text):
                if not any(used[m.start():m.end()]):
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
        prev = self.match(' '.join(history)) if history else []
        sents = [x for x in re.split(r'(?<=[.?!。])\s+|\n+', q) if x.strip()]
        req_text = ' '.join(x for x in sents if self.REQUEST.search(x))
        cards, expansion, unresolved, notes = [], [], [], []
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
                notes.append(f"■ 용어 확인: 「{u['term']}」\n{u['ask']}. 코드를 쓰지 말고 「확인 필요」에 자료에 없다는 사실과 대신 볼 수 있는 변수를 적을 것")
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
