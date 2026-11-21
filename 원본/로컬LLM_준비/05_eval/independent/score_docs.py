#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""6차(문서형 요청)의 자동 채점 — 문서의 항목마다, 그 항목이 요청된 차례에서 이용자에게 표시된 값을 참값과 대조한다.

  INDEP_DIR=05_eval/independent/r6 python 05_eval/independent/score_docs.py r6_v11 [r6_v9 …]
산출  05_eval/runs/<실행>/doc_score.json  {rows: [문서별 항목 분류], summary}
값 대조의 규칙(허용 오차, 억제 칸)은 score_outcome.py 의 것을 그대로 씀.
  · 한 차례에 항목이 여럿이므로, 그 차례의 성공한 실행(뒷줄에서 오류가 난 실행 포함)에서 나온 집계 결과를 하나씩, 또 같은 함수의 결과 2~3개를 묶어 항목의 참값과 대조함
  · 비율·평균 표에 함께 표시되는 인원(해당 인원·대상 인원·인원)도 인원 요청의 값으로 대조함(5차와 같음)
  · 자동 채점은 「정답」만 확정하고, 맞는 결과가 없는 항목은 「대조 불일치(unmatched)」로 두어 평가자가 오답·값 없음을 판정함
  · F 항목은 값 대조만 자동으로 하고 주장의 맞고 틀림 판단은 평가자가 판정함
"""
import itertools
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import score_outcome as so  # noqa: E402

BASE, RD = so.BASE, so.RD


def turn_results(turn):
    out = []
    for s in turn.get('steps') or []:
        if s.get('results') and not s.get('violations'):
            out += list(s['results'].values())
    return out


def aux_counts(results):
    return [{'records': [dict(x, 값=x.get(col)) for x in r.get('records', []) if col in x], 'summary': r.get('summary'), 'call': {'fn': 'count'}}
            for r in results for col in ('해당 인원', '대상 인원', '인원') if any(col in x for x in r.get('records', []))]


def matches(results, alts):
    pools = [[r] for r in results]
    for fn in {(r.get('call') or {}).get('fn') for r in results}:
        same = [r for r in results if (r.get('call') or {}).get('fn') == fn]
        for k in (2, 3):
            if len(same) >= k:
                pools += [list(c) for c in itertools.combinations(same, k)][:80]
    for alt in alts:
        for pool in pools:
            if so.match(pool, alt)[0]:
                return alt.get('alt', 1)
        if alt['measure'] == 'count':
            for a in aux_counts(results):
                if so.match([a], alt)[0]:
                    return alt.get('alt', 1)
    return None


def score_run(name, items, truth):
    tr = {t['id']: t['turns'] for t in so.read_jsonl(RD / name / 'transcripts.jsonl')}
    rows = []
    for b in items:
        if b['id'] not in tr:
            continue
        turns = tr[b['id']]
        specs = truth.get(b['id']) or []
        row = {'id': b['id'], 'author': b.get('author'), 'variant_of': b.get('variant_of'), 'items': []}
        for m in b['items']:
            if m['kind'] == 'D':
                continue
            t = m['turn']; turn = turns[t - 1] if t and t - 1 < len(turns) else {}
            sp = [s for s in specs if (s.get('spec') or {}).get('item') == m['no']]
            res = turn_results(turn)
            c = {'item': m['no'], 'turn': t, 'kind': m['kind'], 'register': m.get('register'),
                 'n_displayed': sum(len(so.displayed(r)) for r in res), 'blocked': sum(1 for s in turn.get('steps') or [] if s.get('violations')),
                 'block_fail': sum(1 for s in turn.get('steps') or [] if s.get('violations') and s.get('ok')), 'hooks': turn.get('hooks')}
            if sp and m['kind'] in 'SFG':
                subs = sorted({(s.get('spec') or {}).get('sub', 1) for s in sp})
                got = {u: matches(res, [s for s in sp if (s.get('spec') or {}).get('sub', 1) == u]) for u in subs}
                c['subs'] = {str(u): (a is not None) for u, a in got.items()}
                if all(a is not None for a in got.values()):
                    c['class'] = 'correct'
                else:
                    c['class'] = 'unmatched' if res or turn.get('final') else 'no_value'
            else:
                c['class'] = 'judge'
                if sp:
                    subs = sorted({(s.get('spec') or {}).get('sub', 1) for s in sp})
                    c['auto_value'] = all(matches(res, [s for s in sp if (s.get('spec') or {}).get('sub', 1) == u]) is not None for u in subs)
            row['items'].append(c)
        rows.append(row)
    return rows


def summarize(rows):
    I = [dict(c, id=r['id'], variant=bool(r.get('variant_of'))) for r in rows for c in r['items']]
    orig = [c for c in I if not c['variant']]
    calc = [c for c in orig if c['kind'] in 'SG']
    f = [c for c in orig if c['kind'] == 'F']
    out = {'conversations': len(rows), 'items': len(I), 'items_original': len(orig), 'calc_items': len(calc),
           'calc_correct_auto': so.rate(sum(c['class'] == 'correct' for c in calc), len(calc)), 'calc_unmatched': sum(c['class'] == 'unmatched' for c in calc),
           'F_value_auto': so.rate(sum(c['class'] == 'correct' for c in f), len(f)),
           'by_kind': {k: {'items': sum(c['kind'] == k for c in orig), 'correct_auto': sum(c['kind'] == k and c['class'] == 'correct' for c in orig)} for k in 'SFGPNVXCI'},
           'by_register': {g: so.rate(sum(c['class'] == 'correct' for c in calc if c.get('register') == g), sum(1 for c in calc if c.get('register') == g)) for g in ('공식', '약칭', '서술', '영문')},
           'block_fail': sum(c.get('block_fail', 0) for c in I),
           'hooks': {h: sum(1 for c in I if (c.get('hooks') or {}).get(h)) for h in ('precheck', 'ask_gate', 'unseen', 'refuse_gate', 'policy', 'budget', 'unexecuted')}}
    return out


def main():
    items = so.read_jsonl(BASE / 'items' / 'all.jsonl')
    truth = json.loads((BASE / 'truth' / 'truth.json').read_text(encoding='utf-8'))
    for name in sys.argv[1:]:
        rows = score_run(name, items, truth)
        rep = {'run': name, 'summary': summarize(rows), 'rows': rows}
        (RD / name / 'doc_score.json').write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding='utf-8')
        s = rep['summary']
        print(f"{name}: 대화 {s['conversations']} · 항목 {s['items']}(원판 {s['items_original']}) · 계산 항목(S·G) {s['calc_items']} · 자동 정답 {s['calc_correct_auto']['k']}({s['calc_correct_auto']['pct']}%) · 대조 불일치 {s['calc_unmatched']} · F 값 일치 {s['F_value_auto']['k']}/{s['F_value_auto']['n']} · 차단 실패 {s['block_fail']}")
        print('   유형별', {k: v for k, v in s['by_kind'].items() if v['items']}, '· 표현별', {k: (v['k'], v['n']) for k, v in s['by_register'].items()}, '· 보완 동작', s['hooks'])


if __name__ == '__main__':
    main()
