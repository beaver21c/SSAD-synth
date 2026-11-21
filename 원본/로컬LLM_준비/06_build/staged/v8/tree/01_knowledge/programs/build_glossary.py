#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""제도 용어 사전 조립 — glossary.yaml 을 검증하고 하네스·검색기가 읽는 자료로 바꾼다.

  1) 변수 대조      사전에 적은 변수가 변수 사전에 있고 값이 있는지 확인한다(없으면 중단)
  2) 조건식 확인    「하나라도 해당」 조건식과 합계 변수 묶음이 분석 함수로 계산되는지 확인한다(분석 자료가 있을 때)
  3) 코퍼스 대조    KIHASA 통합 코퍼스에서 정식 명칭·약어·통칭의 사용 빈도를 세고, 제도를 설명하는 문장을 1개씩 고른다
                    (코퍼스가 없으면 건너뛰고 앞서 만든 결과를 유지한다. GPU 를 쓰지 않는 문자열 검색임)
  출력  glossary.json          하네스(06_build/terms.py)가 읽는 정규화된 사전
        glossary_cards.jsonl   검색기에 넣는 용어 카드(kind=term)
        glossary_report.json   항목 수, 변수 수, 약어별 코퍼스 빈도, 코퍼스에서 확인되지 않은 약어

실행  PYTHONPATH=02_library SSDA_DATA=<분석 자료> .venv/bin/python 01_knowledge/programs/build_glossary.py [--corpus /mnt/share/corpus/dist/corpus_ai_ready.jsonl]
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CORPUS = Path('/mnt/share/corpus/dist/corpus_ai_ready.jsonl')
# 코퍼스에서 고른 설명 문장을 카드에 싣는 항목(2026-11-13 검토: 제도의 뜻을 설명하는 문장이 뽑힌 항목만. 연혁·조사 설명·법조문이 뽑힌 항목은 제외)
EVIDENCE_USE = {'nbls', 'nbls_medi', 'bp', 'nhi_special', 'ltcare', 'unemp', 'parental', 'kua', 'vocaedu', 'youthemp', 'childbn', 'disp', 'oldwork', 'evou', 'rm', 'poverty'}
CUE = re.compile(r'(제도이다|제도임|제도로|급여이다|급여로|보험이다|사업이다|말한다|의미한다|지급하는|지급한다|지원하는|지원한다|제공하는|제공한다|구성된다|나뉜다|도입되었|시행되었)')


def part_vars(p):
    v = p.get('vars') or {}
    return list(v.values()) if isinstance(v, dict) else list(v)


def entry_vars(e):
    out = part_vars(e)
    for p in e.get('parts') or []:
        out += part_vars(p)
    out += (e.get('sum') or {}).get('vars', [])
    return list(dict.fromkeys(out))


def card_text(e, ev=None):
    L = [e['desc']]
    if e.get('target'):
        L.append(f"대상: {e['target']}")
    if e.get('vars'):
        L.append('변수: ' + ', '.join(f'{k} {v}' for k, v in e['vars'].items()))
    if e.get('parts'):
        L.append('구성과 변수:')
        L += [f"- {p['name']}: " + ', '.join(f'{k} {v}' for k, v in (p.get('vars') or {}).items()) for p in e['parts']]
    if e.get('union'):
        L.append(f"하나라도 해당하는 사람: 조건식 {e['union']}")
    if e.get('sum'):
        L.append(f"{e['sum']['name']}: ssda.define_sum('이름', {e['sum']['vars']}) 로 만든 뒤 집계")
    for n in e.get('notes') or []:
        L.append(f'참고: {n}')
    if ev:
        L.append(f"코퍼스 서술 예: {ev['text']} ({ev['title']}, {ev['year']})")
    return '\n'.join(L)


def scan_corpus(path, entries):
    """약어·통칭의 빈도와 제도 설명 문장 후보를 한 번의 훑기로 모은다."""
    terms = sorted({t for e in entries for t in [e['name']] + e.get('aliases', []) + [p['name'] for p in e.get('parts') or []]}, key=len, reverse=True)
    cnt = Counter(); cand = {e['id']: [] for e in entries}
    keys = {e['id']: [e['name']] + [a for a in e.get('aliases', []) if len(a) >= 4][:3] for e in entries if e['kind'] != '용어' or e['id'] in ('nhi_fee', 'pubinc', 'poverty')}
    n = 0
    with open(path, encoding='utf-8') as f:
        for line in f:
            r = json.loads(line)
            if r.get('lang') != 'ko':
                continue
            n += 1
            tx = r['text']
            for t in terms:
                c = tx.count(t)
                if c:
                    cnt[t] += c
            for eid, ks in keys.items():
                if len(cand[eid]) >= 400 or not any(k in tx for k in ks):
                    continue
                for s in re.split(r'(?<=[다음됨])\.\s+', tx):
                    s = s.strip()
                    k = next((k for k in ks if s.startswith(k) or re.match(rf'.{{0,12}}{re.escape(k)}(은|는|이란|란)\s', s)), None)
                    if k and 60 <= len(s) <= 190 and CUE.search(s) and not re.search(r'[<>〔〕]|표 \d|그림 \d|\d{4}[a-z]?\)', s):
                        src = {'hswr': '보건사회연구', 'kihasa_report_pub': 'KIHASA 연구보고서', 'kihasa_report_local': 'KIHASA 연구보고서'}.get(r.get('source'), 'KIHASA 코퍼스')
                        cand[eid].append({'text': s.rstrip('.') + '.', 'title': src, 'year': r.get('year'), 'key': k})
    return n, cnt, cand


def pick(cs, name):
    """설명 문장 후보 가운데 정식 명칭으로 시작하고 길이가 알맞은 최근 문장을 고른다."""
    if not cs:
        return None
    def score(c):
        s = c['text']
        return (s.startswith(name), bool(re.match(rf'{re.escape(c["key"])}(은|는|이란|란)\s', s)), int(c['year'] or 0), -abs(len(s) - 120))
    return max(cs, key=score)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--corpus', default=str(CORPUS)); ap.add_argument('--no-corpus', action='store_true'); a = ap.parse_args()
    G = yaml.safe_load((HERE / 'glossary.yaml').read_text(encoding='utf-8'))
    V = {json.loads(l)['var']: json.loads(l) for l in (ROOT / '01_knowledge' / 'variables.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()}
    derived = {'eqinc', 'hh_dinc', 'poor'}

    # 1) 변수 대조
    bad = []
    ids = [e['id'] for e in G]
    assert len(ids) == len(set(ids)), '항목 id 중복'
    for e in G:
        for v in entry_vars(e):
            if v not in derived and (v not in V or not V[v]['available']):
                bad.append((e['id'], v, '없음' if v not in V else '값 없음'))
        for v in re.findall(r'[a-z_][a-z0-9_]*', e.get('union', '')):
            if v not in ('or', 'and') and v not in V:
                bad.append((e['id'], v, '조건식의 변수 없음'))
    if bad:
        print('변수 대조 실패:', bad); return 1

    # 2) 조건식·합계 확인(분석 자료가 있을 때)
    checked = {'union': 0, 'sum': 0}
    if os.environ.get('SSDA_DATA'):
        sys.path.insert(0, str(ROOT / '02_library'))
        import ssda
        ssda.open_data()
        for e in G:
            if e.get('union'):
                ssda.rate(e['union']); checked['union'] += 1
            if e.get('sum'):
                ssda.define_sum('_chk_' + e['id'], e['sum']['vars']); ssda.mean('_chk_' + e['id']); checked['sum'] += 1

    # 3) 코퍼스 대조
    rep_path = HERE / 'glossary_report.json'
    old = json.loads(rep_path.read_text(encoding='utf-8')) if rep_path.exists() else {}
    freq, evid, n_chunks, ver = old.get('corpus_freq', {}), old.get('corpus_evidence', {}), old.get('corpus_chunks'), old.get('corpus_version')
    cpath = Path(a.corpus)
    if not a.no_corpus and cpath.exists():
        n_chunks, cnt, cand = scan_corpus(cpath, G)
        freq = {t: c for t, c in cnt.most_common()}
        evid = {}
        for e in G:
            if e['id'] not in EVIDENCE_USE:                 # 고른 문장을 사람이 확인해 제도의 뜻을 설명하는 것만 카드에 싣는다
                continue
            p = pick(cand.get(e['id'], []), e['name'])
            if p:
                evid[e['id']] = {k: p[k] for k in ('text', 'title', 'year')}
        m = cpath.parent / 'MANIFEST.json'
        ver = json.loads(m.read_text(encoding='utf-8')).get('version') if m.exists() else None

    # 출력
    out, cards = [], []
    for e in G:
        ali = ([e['name']] if e.get('match_name', True) else []) + e.get('aliases', [])
        rec = dict(e, terms=ali, all_vars=entry_vars(e), corpus_freq={t: freq.get(t, 0) for t in ali}, evidence=evid.get(e['id']))
        rec['card'] = card_text(e, evid.get(e['id']))
        out.append(rec)
        ttl = f"{e['name']}" + (f" (통칭 {', '.join(e['aliases'][:6])})" if e.get('aliases') else '')
        cards.append({'id': 'term:' + e['id'], 'kind': 'term', 'title': '제도 설명: ' + ttl, 'text': rec['card']})
    (HERE / 'glossary.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    (HERE / 'glossary_cards.jsonl').write_text('\n'.join(json.dumps(c, ensure_ascii=False) for c in cards) + '\n', encoding='utf-8')
    unattested = sorted({t for e in G for t in e.get('aliases', []) if freq and freq.get(t, 0) == 0})
    rep = {'entries': len(G), 'by_kind': dict(Counter(e['kind'] for e in G)), 'terms': sum(len(e.get('aliases', [])) + 1 for e in G), 'variables': len({v for e in G for v in entry_vars(e)}),
           'ambiguity': dict(Counter((e.get('ambiguity') or {}).get('policy', '없음') for e in G)), 'checked': checked, 'corpus_version': ver, 'corpus_chunks': n_chunks,
           'with_evidence': len(evid), 'unattested_aliases': unattested, 'corpus_freq': freq, 'corpus_evidence': evid}
    rep_path.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: rep[k] for k in ('entries', 'by_kind', 'terms', 'variables', 'ambiguity', 'checked', 'corpus_version', 'corpus_chunks', 'with_evidence')}, ensure_ascii=False))
    print('코퍼스에서 확인되지 않은 약어·통칭:', unattested)
    return 0


if __name__ == '__main__':
    sys.exit(main())
