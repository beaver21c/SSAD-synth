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

    def _resolved(self, e, text, matches):
        amb = e.get('ambiguity') or {}
        if amb.get('policy') == 'absent':
            return False
        if amb.get('needs_program'):                             # 수급자·수급률: 다른 제도명·급여명이 함께 있으면 정해진 것
            if any(eid != e['id'] for _, eid, part in matches):
                return True
            return any(w in text for x in self.entries for p in (x.get('parts') or []) for w in [p['name']] + list(p.get('aliases') or []) if len(w) >= 4) or bool(re.search(r'[a-z]+_[a-z0-9_]+', text))
        words = list(amb.get('resolvers') or [])
        for p in e.get('parts') or []:
            words += [p['name']] + list(p.get('aliases') or [])
        return any(w in text for w in words)

    def resolve(self, question, pending=None):
        q = re.sub(r'```.*?```', ' ', question or '', flags=re.S)
        ms = self.match(q)
        cards, expansion, unresolved, notes = [], [], [], []
        for term, eid, part in ms:
            e = self.by_id[eid]
            if e['id'] != 'absent_2022':
                ttl = e['name'] + (f"(질문의 「{term}」)" if term != e['name'] else '')
                cards.append({'id': 'term:' + eid, 'title': '제도 설명: ' + ttl, 'text': e['card']})
                expansion += [e['name']] + [p['name'] for p in (e.get('parts') or []) if part in (None, p['name'])][:4]
            amb = e.get('ambiguity')
            if amb and part is None and not self._resolved(e, q, ms):
                ask = amb.get('ask', '')
                if amb['policy'] == 'absent':
                    ask = f"자료에 없는 항목임. {(e.get('alternatives') or {}).get(term, '대신 볼 변수가 없음')}"
                unresolved.append({'id': eid, 'term': term, 'name': e['name'], 'policy': amb['policy'], 'ask': ask, 'default': amb.get('default', ''), 'vars': e['all_vars']})
        for u in pending or []:                                  # 앞선 질문에서 되물은 용어: 이번 답에 내역이 있으면 정해진 것
            e = self.by_id[u['id']]
            if not self._resolved(e, q, ms) and u['id'] not in {x['id'] for x in unresolved}:
                unresolved.append(dict(u, carried=True))
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
