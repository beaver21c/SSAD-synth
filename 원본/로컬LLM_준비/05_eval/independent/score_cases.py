#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""5차(제도·현안 과제형)의 자동 채점 — 과제의 차례마다 이용자에게 표시된 값을 참값과 대조하고, 한 대화 안의 값 관계를 점검한다.

  INDEP_DIR=05_eval/independent/r5 python 05_eval/independent/score_cases.py r5_v9 [r5_v8 …]
산출  05_eval/runs/<실행>/case_score.json  {rows: [과제별 차례 분류], relations: […], summary: {…}}
값 대조의 규칙(허용 오차, 억제 칸의 처리, 분류 이름)은 score_outcome.py 의 것을 그대로 쓴다(코드를 고치지 않고 불러 씀).
  · 한 차례에 요청이 여럿이면(part) 요청마다 대조하고 모두 맞아야 정답. 앞선 실행에서 낸 요청은 그 실행의 값으로 대조함
  · 산출 정의가 없는 차례(N·V·T·C·I, 산출이 없는 X)는 「judge」(평가자 판정 대상)로 두고 겉모습(값 표시 수, 차단 수, 응답 표지)만 기록함
  · 관계 점검은 참값을 쓰지 않고 도구가 표시한 값끼리 계산함
평가자 판정을 합친 집계는 aggregate_cases.py 가 한다.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import score_outcome as so  # noqa: E402

BASE = so.BASE
RD = so.RD
ORDER = {'wrong': 0, 'unexecuted': 1, 'no_value': 2, 'correct': 3}


def turn_values(turn):
    """한 차례에서 마지막으로 값을 표시한 실행의 결과 목록(관계 점검용): [(표시 값 목록, 가려진 칸 수, 함수)]"""
    okres = [s for s in turn.get('steps') or [] if s.get('results') and not s.get('violations')]
    if not okres:
        return []
    out = []
    for r in okres[-1]['results'].values():
        recs = r.get('records', [])
        out.append({'values': so.displayed(r), 'hidden': sum(1 for x in recs if x.get('상태') in ('억제', '보충 억제') or (x.get('값') is None and x.get('상태') not in ('대상 없음',))),
                    'fn': (r.get('call') or {}).get('fn')})
    return out


def classify_turn(turn, specs, question):
    """산출 정의가 있는 차례의 분류. specs 는 그 차례의 참값 목록(part·alt 포함)."""
    parts = sorted({(s.get('spec') or {}).get('part', 1) for s in specs})
    res = []
    for p in parts:
        alts = [s for s in specs if (s.get('spec') or {}).get('part', 1) == p]
        c = so.classify(turn, alts, question)
        if c['class'] != 'correct' and len(parts) > 1:          # 요청이 여럿인 차례: 앞선 실행에서 낸 요청은 그 실행의 값으로 대조
            for s in [x for x in turn.get('steps') or [] if x.get('results') and not x.get('violations')][:-1]:
                for alt in alts:
                    pools = [[r] for r in s['results'].values()]
                    if any(so.match(pool, alt)[0] for pool in pools):
                        c = {**c, 'class': 'correct', 'alt': alt.get('alt', 1), 'earlier_step': True}
                        break
                if c['class'] == 'correct':
                    break
        if c['class'] != 'correct' and len(parts) > 1 and c['class'] == 'wrong':
            # 다른 요청의 값만 표시된 경우(이 요청의 값은 없음)는 오답이 아니라 값 없음으로 둠: 표시된 값이 모두 다른 요청의 참값과 맞는지 본다
            others = [s for s in specs if (s.get('spec') or {}).get('part', 1) != p]
            okres = [x for x in turn.get('steps') or [] if x.get('results') and not x.get('violations')]
            last = list(okres[-1]['results'].values()) if okres else []
            if last and all(any(so.match([r], a)[0] for a in others) for r in last if so.displayed(r)):
                c = {**c, 'class': 'no_value', 'sub': 'missing_part'}
        c['part'] = p
        res.append(c)
    if len(parts) > 1 and any(c['class'] != 'correct' for c in res):
        # 요청이 「몇 명이고 몇 %(또는 평균 얼마)」인 차례: 도구의 비율·평균·구성비 표에는 인원(해당 인원, 대상 인원, 인원)이 함께 표시되므로, 인원 요청은 그 칸의 값으로도 대조함
        # (실행 기록을 보기 전에 넣은 규칙. 요청이 하나뿐인 차례에는 적용하지 않음: 1~4차와 같은 기준)
        allres0 = [r for x in turn.get('steps') or [] if x.get('results') and not x.get('violations') for r in x['results'].values()]
        aux = [{'records': [dict(x, 값=x.get(col)) for x in r.get('records', []) if col in x], 'summary': r.get('summary'), 'call': {'fn': 'count'}}
               for r in allres0 for col in ('해당 인원', '대상 인원', '인원') if any(col in x for x in r.get('records', []))]
        for c in res:
            if c['class'] != 'correct':
                alts = [s for s in specs if (s.get('spec') or {}).get('part', 1) == c['part'] and s['measure'] == 'count']
                if alts and any(so.match([a], alt)[0] for a in aux for alt in alts):
                    c.update({'class': 'correct', 'sub': 'aux_count'})
    if len(parts) > 1 and any(c['class'] != 'correct' for c in res):
        # 작성자가 요청을 칸 하나짜리 정의 여럿으로 나눠 적었는데 도구가 한 표로 낸 경우(예: 유형 세 가지의 인원을 한 표로): 같은 지표의 요청들을 한 표로 합친 참값과 대조함
        # (2026-11-18 이중 입력 대조에서 확인: 검산자는 한 표로 계산하고 작성자는 세 요청으로 나눠 적음. 값은 같음. 실행 기록을 보기 전에 넣은 규칙)
        okres = [x for x in turn.get('steps') or [] if x.get('results') and not x.get('violations')]
        allres = [r for x in okres for r in x['results'].values()]
        for m in sorted({s['measure'] for s in specs}):
            group = [p for p in parts if all(s['measure'] == m for s in specs if (s.get('spec') or {}).get('part', 1) == p)]
            if len(group) < 2:
                continue
            first = [next(s for s in specs if (s.get('spec') or {}).get('part', 1) == p) for p in group]
            if any(len([c for c in s['cells'] if c.get('value') is not None]) != 1 for s in first):
                continue
            comb = {'measure': m, 'cells': [c for s in first for c in s['cells']], 'spec': {}, 'alt': 1}
            if any(so.match([r], comb)[0] for r in allres):
                for c in res:
                    if c['part'] in group and c['class'] != 'correct':
                        c.update({'class': 'correct', 'sub': 'combined_table', 'alt': 1})
    worst = min(res, key=lambda c: ORDER[c['class']])
    out = {k: worst.get(k) for k in ('class', 'sub', 'hooks', 'n_calls', 'blocked', 'block_fail', 'partial', 'user_step')}
    out['leak_cells'] = sum(c.get('leak_cells', 0) for c in res)
    out['parts'] = [{'part': c['part'], 'class': c['class'], 'sub': c.get('sub'), 'alt': c.get('alt')} for c in res]
    return out


def judge_row(turn):
    steps = turn.get('steps') or []
    final = turn.get('final') or ''
    return {'class': 'judge', 'presented_values': sum(len(so.displayed(r)) for s in steps if s.get('ok') for r in (s.get('results') or {}).values()),
            'executed_ok': sum(1 for s in steps if s.get('ok')), 'blocked': sum(1 for s in steps if s.get('violations')),
            'block_fail': sum(1 for s in steps if s.get('violations') and s.get('ok')),
            'marker': 'refuse' if '요청 처리 불가' in final else 'ask' if '확인 필요' in final else 'answer', 'hooks': turn.get('hooks'), 'n_calls': turn.get('n_calls')}


def relation(rel, turns):
    """관계 점검 1건 → {'type', 'status': hold|violate|na, 'detail'}"""
    def single(k):
        v = turn_values(turns[k - 1]) if k - 1 < len(turns) else []
        one = [x for x in v if len(x['values']) == 1 and not x['hidden']]
        return one[0]['values'][0] if len(one) >= 1 and len({round(x['values'][0], 6) for x in one}) == 1 else None
    t = rel.get('type')
    try:
        if t == 'parts_sum':
            whole = single(rel['whole'])
            pv = [x for x in turn_values(turns[rel['parts'] - 1]) if len(x['values']) >= 2 or x['hidden']]
            if whole is None or not pv:
                return {**rel, 'status': 'na'}
            x = pv[0]; s = sum(x['values'])
            if x['hidden']:
                ok = s <= whole * 1.015
            else:
                ok = abs(s - whole) <= 0.015 * abs(whole)
            return {**rel, 'status': 'hold' if ok else 'violate', 'detail': {'whole': whole, 'sum': s, 'hidden': x['hidden']}}
        if t == 'subset_le':
            a, b = single(rel['large']), single(rel['small'])
            if a is None or b is None:
                return {**rel, 'status': 'na'}
            return {**rel, 'status': 'hold' if b <= a * 1.005 else 'violate', 'detail': {'large': a, 'small': b}}
        if t == 'same':
            a, b = single(rel['a']), single(rel['b'])
            if a is None or b is None:
                return {**rel, 'status': 'na'}
            return {**rel, 'status': 'hold' if abs(a - b) <= max(0.11, 0.01 * abs(a)) else 'violate', 'detail': {'a': a, 'b': b}}
    except (KeyError, IndexError, TypeError):
        pass
    return {**rel, 'status': 'na'}


def score_run(name, items, truth):
    tr = {t['id']: t['turns'] for t in so.read_jsonl(RD / name / 'transcripts.jsonl')}
    rows, rels = [], []
    for b in items:
        if b['id'] not in tr:
            continue
        turns = tr[b['id']]
        specs = truth.get(b['id']) or []
        row = {'id': b['id'], 'author': b.get('author'), 'domain': b.get('domain'), 'turns': []}
        for k, kind in enumerate(b['kinds'], 1):
            if k - 1 >= len(turns) or kind == 'D':
                continue
            sp = [s for s in specs if s['turn'] == k]
            c = classify_turn(turns[k - 1], sp, b['turns'][k - 1]) if sp else judge_row(turns[k - 1])
            if sp and kind not in 'SG':                      # P·X 의 산출: 값 대조 결과를 평가자에게 넘김
                c['auto'] = c['class']; c['class'] = 'judge'
                c.update({k2: v for k2, v in judge_row(turns[k - 1]).items() if k2 not in c})
            c.update({'turn': k, 'kind': kind, 'register': b['registers'][k - 1]})
            row['turns'].append(c)
        rows.append(row)
        for rel in b.get('relations') or []:
            rels.append({'id': b['id'], **relation(rel, turns)})
    return rows, rels


def summarize(rows, rels):
    T = [dict(t, id=r['id']) for r in rows for t in r['turns']]
    calc = [t for t in T if t['kind'] in 'SG' and t['class'] != 'judge']
    silent = [t for t in calc if t['class'] in ('wrong', 'unexecuted')]
    out = {'cases': len(rows), 'turns': len(T), 'calc_turns': len(calc), 'correct': so.rate(sum(t['class'] == 'correct' for t in calc), len(calc)),
           'silent_wrong': so.rate(len(silent), len(calc)), 'unexecuted': sum(t['class'] == 'unexecuted' for t in calc),
           'no_value': {k: sum(t['class'] == 'no_value' and (t.get('sub') or 'other') == k for t in calc) for k in ('ask', 'refuse', 'error', 'suppressed', 'missing_part', 'other')},
           'leak_cells': sum(t.get('leak_cells', 0) for t in T), 'block_fail': sum(t.get('block_fail', 0) or 0 for t in T)}
    out['by_kind'] = {k: {'turns': sum(t['kind'] == k for t in T), 'correct': sum(t['kind'] == k and t['class'] == 'correct' for t in T),
                          'silent': sum(t['kind'] == k and t['class'] in ('wrong', 'unexecuted') for t in T), 'judge': sum(t['kind'] == k and t['class'] == 'judge' for t in T)} for k in 'SGPNVTXCI'}
    out['by_register'] = {g: so.rate(sum(t['class'] == 'correct' for t in calc if t.get('register') == g), sum(1 for t in calc if t.get('register') == g)) for g in ('공식', '약칭', '서술', '영문')}
    out['by_turn'] = {str(k): so.rate(sum(t['class'] == 'correct' for t in calc if t['turn'] == k), sum(1 for t in calc if t['turn'] == k)) for k in (1, 2, 3, 4)}
    clean = [r for r in rows if not any(t['class'] in ('wrong', 'unexecuted') for t in r['turns'] if t['kind'] in 'SG')]
    out['cases_no_silent_auto'] = so.rate(len(clean), len(rows))
    out['relations'] = {'n': len(rels), 'hold': sum(r['status'] == 'hold' for r in rels), 'violate': sum(r['status'] == 'violate' for r in rels), 'na': sum(r['status'] == 'na' for r in rels)}
    out['hooks'] = {h: sum(1 for t in T if (t.get('hooks') or {}).get(h)) for h in ('precheck', 'ask_gate', 'var_candidates', 'repeat', 'unexecuted', 'budget')}
    return out


def main():
    items = so.read_jsonl(BASE / 'items' / 'all.jsonl')
    truth = json.loads((BASE / 'truth' / 'truth.json').read_text(encoding='utf-8'))
    for name in sys.argv[1:]:
        rows, rels = score_run(name, items, truth)
        rep = {'run': name, 'summary': summarize(rows, rels), 'rows': rows, 'relations': rels}
        (RD / name / 'case_score.json').write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding='utf-8')
        s = rep['summary']
        print(f"{name}: 과제 {s['cases']} · 차례 {s['turns']} · 산출 차례(S·G) {s['calc_turns']} · 정답 {s['correct']['pct']}% {s['correct']['ci95']} · 조용한 오답 {s['silent_wrong']['k']}건 {s['silent_wrong']['pct']}% {s['silent_wrong']['ci95']}"
              f" · 값 없음 {s['no_value']} · 억제 위반 칸 {s['leak_cells']} · 차단 실패 {s['block_fail']}")
        print('   유형별', {k: v for k, v in s['by_kind'].items() if v['turns']})
        print('   표현별', {k: (v['k'], v['n']) for k, v in s['by_register'].items()}, '· 차례 순서별', {k: (v['k'], v['n']) for k, v in s['by_turn'].items()})
        print('   관계 점검', s['relations'], '· 조용한 오답 없는 과제(자동)', s['cases_no_silent_auto'], '· 보완 동작', s['hooks'])


if __name__ == '__main__':
    main()
