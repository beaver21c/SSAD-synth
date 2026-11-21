#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""독립 평가자용 판정 자료 만들기 — 응답에서 구성 표시를 지우고 순서를 섞어 묶음 파일로 만든다.

  python 05_eval/independent/judging/make_packets.py indep_c2 --tag a --both          # 판정 대상 구성: 평가자 2인 모두에게 배정
  python 05_eval/independent/judging/make_packets.py indep_c3 indep_c0 --tag b        # 비교 구성: 1인씩 번갈아 배정(P3 표본은 만들지 않음)
  선택 인자  --tag 묶음 이름(판정 번호와 파일 이름에 붙음)  --both 모든 건을 평가자 2인에게 배정  --split N 파일 하나에 담는 건수(기본 52)
묶음  P1 정성 판정: D(수행 불가)·E 의 거절 대상·H(모호한 질문)의 응답 전부
      P2 오답 재판정: 산출 문항에서 자동 채점이 「조용한 오답」「실행 없이 값 제시」로 분류한 차례 전부
      P3 자동 채점 대조: 첫 번째 실행(판정 대상 구성)의 산출 차례 가운데 무작위 40건(정답·값 없는 응답)
배정  첫 번째 실행의 응답은 평가자 2인 모두, 그 밖의 실행의 응답은 1인씩 번갈아 배정(평가자는 어느 구성의 응답인지 모름)
산출  judging/packet_J1.md, packet_J2.md (평가자별 판정 자료), judging/key.json (판정 번호 → 실행·문항·차례. 평가자에게 주지 않음)
"""
import json
import os
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
IND = HERE.parent
BASE = Path(os.environ.get('INDEP_DIR') or IND)       # 차수별 폴더(items, truth, judging)
OUTD = BASE / 'judging'
RD = IND.parent / 'runs'
KIND = {'D': '수행할 수 없는 질문', 'E': '통제상 응하면 안 되는 요청', 'H': '여러 뜻으로 읽히는 질문'}


def read_jsonl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding='utf-8').splitlines() if l.strip()]


def cut(s, n):
    s = (s or '').strip()
    return s if len(s) <= n else s[:n] + f' …(이하 {len(s) - n}자 생략)'


def render_turn(q, t, k):
    L = [f'**이용자({k})**: {q}']
    for s in t.get('steps') or []:
        who = '도구가 이용자의 코드를 그대로 실행' if s.get('origin') == 'user' else '도구가 작성·실행한 코드'
        state = '실행 전 점검에서 차단' if s.get('violations') else ('실행 성공' if s.get('ok') else '실행 실패')
        L.append(f'- {who} — {state}')
        L.append('```python\n' + cut(s.get('code'), 900) + '\n```')
        if s.get('ok') and s.get('stdout'):
            L.append('표시된 실행 결과:\n```\n' + cut(s['stdout'], 1500) + '\n```')
        elif s.get('error'):
            L.append('오류: ' + cut(s['error'].splitlines()[0], 300))
    L.append(f'**도구의 최종 응답({k})**:\n' + cut(t.get('final'), 1800))
    if t.get('footer'):
        L.append('(자동 검증 요약)\n' + cut(t['footer'], 500))
    return '\n\n'.join(L)


def render_dialog(b, turns, upto=None):
    out = []
    if b.get('context'):
        out.append('**질문에 첨부된 문서**:\n```\n' + cut(b['context'], 1200) + '\n```')
    for k, (q, t) in enumerate(zip(b['turns'], turns), 1):
        if upto and k > upto:
            break
        out.append(render_turn(q, t, k))
    return '\n\n'.join(out)


def spec_text(a):
    s = a['spec']
    by = '; '.join(json.dumps(x, ensure_ascii=False) for x in (s.get('by') or [])) or '없음'
    cells = ', '.join(f"{'·'.join(map(str, c['labels'])) or '전체'} = {('없음' if c['value'] is None else format(c['value'], ',.4g'))}(관측 {c['n']}건)" for c in a['cells'][:24])
    return (f"- 산출: {a['measure']} · 단위 {a.get('unit', 'person')} · 대상 `{s.get('population', '') or '전체'}`"
            + (f" · 분자 `{s['numerator']}`" if s.get('numerator') else '') + (f" · 분자 집단 `{s['num_population']}`" if s.get('num_population') else '')
            + (f" · 대상 변수 `{s['value_var']}`" if s.get('value_var') else '') + (f" · 분위 {s['q']}" if s.get('q') else '') + f' · 분류 {by}\n  - 참값(반올림 전. 비율은 %, 금액은 원): {cells}')


def main():
    args = sys.argv[1:]
    tag = args[args.index('--tag') + 1] if '--tag' in args else 'x'
    both = '--both' in args
    split = int(args[args.index('--split') + 1]) if '--split' in args else 52
    runs = [a for i, a in enumerate(args) if not a.startswith('--') and (i == 0 or args[i - 1] not in ('--tag', '--split'))]
    items = {b['id']: b for b in read_jsonl(BASE / 'items' / 'all.jsonl')}
    truth = json.loads((BASE / 'truth' / 'truth.json').read_text(encoding='utf-8'))
    random.seed(20261117)
    entries = []
    for ri, run in enumerate(runs):
        tr = {t['id']: t['turns'] for t in read_jsonl(RD / run / 'transcripts.jsonl')}
        sc = {r['id']: r for r in json.loads((RD / run / 'indep_score.json').read_text(encoding='utf-8'))['rows']}
        for iid, row in sc.items():
            b = items[iid]
            if row['class'] == 'judge':
                entries.append({'packet': 'P1', 'run': run, 'ri': ri, 'id': iid, 'turn': None})
            else:
                for c in row['turns']:
                    if c['class'] in ('wrong', 'unexecuted'):
                        entries.append({'packet': 'P2', 'run': run, 'ri': ri, 'id': iid, 'turn': c['turn']})
        if ri == 0 and both:
            pool = [(iid, c['turn']) for iid, row in sc.items() if row['class'] != 'judge' for c in row['turns'] if c['class'] in ('correct', 'no_value')]
            for iid, t in random.sample(pool, min(40, len(pool))):
                entries.append({'packet': 'P3', 'run': run, 'ri': ri, 'id': iid, 'turn': t})
    random.shuffle(entries)
    key, text, cache = {}, {'J1': [], 'J2': []}, {}
    alt = 0
    for n, e in enumerate(entries, 1):
        kid = f'K{tag}{n:03d}'
        if both:
            judges = ['J1', 'J2']
        else:
            judges = ['J1'] if alt % 2 == 0 else ['J2']; alt += 1
        key[kid] = {**e, 'judges': judges}
        b = items[e['id']]
        tr = cache.setdefault(e['run'], {t['id']: t['turns'] for t in read_jsonl(RD / e['run'] / 'transcripts.jsonl')})[e['id']]
        if e['packet'] == 'P1':
            head = f"## {kid} · 유형 P1 · {KIND[b['stratum']]}\n\n- 문항 작성자의 설명: {b.get('note', '')}"
            body = render_dialog(b, tr)
        else:
            alts = [a for a in truth.get(e['id'], []) if a['turn'] == e['turn']]
            head = (f"## {kid} · 유형 {e['packet']} · 산출 질문(판정할 차례: {e['turn']}번째 질문)\n\n- 문항 작성자가 정한 산출 정의와 참값(해석이 여럿이면 어느 하나와 일치하면 됨)\n"
                    + '\n'.join(spec_text(a) for a in alts))
            body = render_dialog(b, tr, upto=e['turn'])
        for j in judges:
            text[j].append(head + '\n\n' + body)
    (OUTD / f'key_{tag}.json').write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding='utf-8')
    for j in text:
        parts = [text[j][i:i + split] for i in range(0, len(text[j]), split)]
        for k, part in enumerate(parts, 1):
            (OUTD / f'packet_{j}_{tag}{k}.md').write_text(f'# 판정 자료({j}, 묶음 {tag}{k}) — {len(part)}건\n\n' + '\n\n---\n\n'.join(part) + '\n', encoding='utf-8')
            print(j, f'{tag}{k}', len(part), '건', sum(len(x) for x in part), '자')
    from collections import Counter
    print(Counter((e['packet'], e['run']) for e in entries))


if __name__ == '__main__':
    main()
