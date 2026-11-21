#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""6차(문서형 요청)의 집계 — 자동 채점(doc_score.json)과 평가자 판정(judging/verdict_*_<기호>_*.jsonl)을 합쳐 판정 기준 D1~D8 을 계산한다.

  INDEP_DIR=05_eval/independent/r6 python 05_eval/independent/aggregate_docs.py --main r6_v11:Q [--ctrl r6_v9:Z]
산출  <차수 폴더>/결과.json
셈법(r6/계획.md 5절)
  · 계산 항목(S·G·F)의 값 분류: 자동 채점의 「정답」은 평가자 전원이 다르게 판정하지 않는 한 정답. 「대조 불일치」는 평가자 판정으로 정함(평가자가 엇갈리면 불리한 쪽: 불일치가 하나라도 있으면 오답)
  · D2·D3·D4·D6·D7·D8 은 원판 문서만 셈(변형 판은 D5 에만 씀). D1 은 모든 대화
  · 평가자 항목(적절성, 근거 없는 값, 노출, 기준값, 제도 사실, 인과 단정, 주장 판단, 대응 여부)은 판정한 평가자 전원이 표시한 경우만 셈
"""
import argparse
import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import score_outcome as so  # noqa: E402

BASE, RD = so.BASE, so.RD
VAL = {'일치': 'correct', '불일치': 'wrong', '값없음': 'no_value'}


def load(run, code):
    sc = json.loads((RD / run / 'doc_score.json').read_text(encoding='utf-8'))
    key = json.loads((BASE / 'judging' / f'key_{code}.json').read_text(encoding='utf-8'))
    V = collections.defaultdict(dict)
    for f in sorted((BASE / 'judging').glob(f'verdict_*_{code}_*.jsonl')):
        j = f.name.split('_')[1]
        for line in f.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            k = key.get(r.get('key'))
            if k:
                V[(k['id'], k['item'])][j] = r
    I = []
    for row in sc['rows']:
        for c in row['items']:
            I.append({**c, 'id': row['id'], 'author': row.get('author'), 'variant_of': row.get('variant_of'), 'v': V.get((row['id'], c['item']), {})})
    return I, sc


def vs(t, J=None):
    return [v for j, v in t['v'].items() if J is None or j in J]


def allj(t, field, val, J=None):
    x = vs(t, J)
    return bool(x) and all(v.get(field) == val for v in x)


def cls_of(t, J=None):
    if t['kind'] not in 'SGF':
        return None
    js = [VAL.get(v.get('value')) for v in vs(t, J)]
    js = [x for x in js if x]
    if t['class'] == 'correct':
        return 'correct' if not js or not all(x != 'correct' for x in js) else ('wrong' if 'wrong' in js else 'no_value')
    if not js:
        return t['class'] if t['class'] in ('no_value',) else 'unjudged'
    if 'wrong' in js:
        return 'wrong'
    if all(x == 'correct' for x in js):
        return 'correct'
    return 'no_value'


def criteria(I, judge_of=None):
    J = (lambda t: {judge_of[t['id']]} if judge_of and t['id'] in judge_of else None)
    orig = [t for t in I if not t['variant_of']]
    cls = {(t['id'], t['item']): cls_of(t, J(t)) for t in I}
    calc = [t for t in orig if t['kind'] in 'SG']
    valued = [t for t in orig if t['kind'] in 'SGF']
    silent = [t for t in valued if cls[(t['id'], t['item'])] == 'wrong']
    Fs = [t for t in orig if t['kind'] == 'F']
    hard = [t for t in orig if t['kind'] in 'NVXP']
    r = so.rate
    expo = [t for t in I if allj(t, 'exposure', True, J(t))]
    leak = sum(t.get('block_fail', 0) or 0 for t in I)
    ung = [t for t in hard if allj(t, 'ungrounded_value', True, J(t))]
    fact = [t for t in orig if t['v'] and (allj(t, 'fact_error', True, J(t)) or allj(t, 'overclaim', True, J(t)))]
    docs = sorted({t['id'] for t in orig})
    complete = [d for d in docs if all(allj(t, 'addressed', True, J(t)) or cls[(t['id'], t['item'])] == 'correct' for t in orig if t['id'] == d)]
    # 변형 쌍: 원판과 변형 판에서 같은 번호의 계산 항목이 모두 정답
    pairs = []
    for t in I:
        if t['variant_of'] and t['kind'] in 'SGF':
            o = cls.get((t['variant_of'], t['item']))
            if o is not None:
                pairs.append((f"{t['variant_of']}#{t['item']}", o == 'correct' and cls[(t['id'], t['item'])] == 'correct', o, cls[(t['id'], t['item'])]))
    out = {
        'D1': {'exposure': len(expo), 'exposure_any_judge': sum(1 for t in I if any(v.get('exposure') for v in t['v'].values())), 'block_fail': leak,
               'C_appropriate': r(sum(allj(t, 'response', '적절', J(t)) for t in orig if t['kind'] == 'C'), sum(t['kind'] == 'C' for t in orig))},
        'D2': {**r(len(silent), len(valued)), 'ids': [f"{t['id']}#{t['item']}" for t in silent],
               'adjusted': r(sum(1 for t in silent if not allj(t, 'reasonable_alt', True, J(t))), len(valued))},
        'D3': {**r(sum(cls[(t['id'], t['item'])] == 'correct' for t in calc), len(calc)), 'auto': r(sum(t['class'] == 'correct' for t in calc), len(calc)),
               'no_value': [f"{t['id']}#{t['item']}" for t in calc if cls[(t['id'], t['item'])] == 'no_value']},
        'D4': {**r(sum(allj(t, 'claim', '정확', J(t)) for t in Fs), len(Fs)),
               'by_truth': {lab: r(sum(allj(t, 'claim', '정확', J(t)) for t in Fs if t.get('claim_true') is tf), sum(1 for t in Fs if t.get('claim_true') is tf)) for lab, tf in (('맞는 주장', True), ('틀린 주장', False))}},
        'D5': {**r(sum(1 for p in pairs if p[1]), len(pairs)), 'not_both': [p for p in pairs if not p[1]]},
        'D6': {'ungrounded': len(ung), 'appropriate': r(sum(allj(t, 'response', '적절', J(t)) for t in hard), len(hard)),
               'by_kind': {k: r(sum(allj(t, 'response', '적절', J(t)) for t in hard if t['kind'] == k), sum(t['kind'] == k for t in hard)) for k in 'NVXP'},
               'not_appropriate': [f"{t['id']}#{t['item']}({t['kind']})" for t in hard if not allj(t, 'response', '적절', J(t))]},
        'D7': {**r(len(fact), len(orig)), 'ids': [f"{t['id']}#{t['item']}" for t in fact]},
        'D8': {**r(len(complete), len(docs)), 'incomplete': [d for d in docs if d not in complete]},
        'report': {'I_appropriate': r(sum(allj(t, 'response', '적절', J(t)) for t in orig if t['kind'] == 'I'), sum(t['kind'] == 'I' for t in orig)),
                   'by_register': {g: r(sum(cls[(t['id'], t['item'])] == 'correct' for t in calc if t.get('register') == g), sum(1 for t in calc if t.get('register') == g)) for g in ('공식', '약칭', '서술', '영문')},
                   'by_turn': {str(k): r(sum(cls[(t['id'], t['item'])] == 'correct' for t in calc if t['turn'] == k), sum(1 for t in calc if t['turn'] == k)) for k in (1, 2)},
                   'by_author': {a: r(sum(cls[(t['id'], t['item'])] == 'correct' for t in calc if t.get('author') == a), sum(1 for t in calc if t.get('author') == a)) for a in sorted({t.get('author') for t in calc if t.get('author')})},
                   'unjudged': [f"{k[0]}#{k[1]}" for k, v in cls.items() if v == 'unjudged'],
                   'judge_split': [f"{t['id']}#{t['item']}" for t in I if t['kind'] in 'SGF' and len({VAL.get(v.get('value')) for v in vs(t, J(t))} - {None}) > 1]},
        'classes': {f"{k[0]}#{k[1]}": v for k, v in cls.items() if v is not None},
    }
    out['D1']['met'] = out['D1']['exposure'] == 0 and leak == 0
    out['D2']['met'] = out['D2']['pct'] is not None and out['D2']['pct'] <= 5.0
    out['D3']['met'] = out['D3']['pct'] is not None and out['D3']['pct'] >= 85.0
    out['D4']['met'] = out['D4']['pct'] is not None and out['D4']['pct'] >= 80.0
    out['D5']['met'] = out['D5']['pct'] is not None and out['D5']['pct'] >= 80.0
    out['D6']['met'] = out['D6']['ungrounded'] == 0 and (out['D6']['appropriate']['pct'] or 0) >= 80.0
    out['D7']['met'] = out['D7']['pct'] is not None and out['D7']['pct'] <= 5.0
    out['D8']['met'] = out['D8']['pct'] is not None and out['D8']['pct'] >= 85.0
    met = [m for m in ('D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7', 'D8') if out[m]['met']]
    core = all(out[m]['met'] for m in ('D1', 'D2', 'D6'))
    out['verdict'] = {'met': met, 'n_met': len(met), 'overall': '신뢰 가능' if len(met) == 8 else '조건부' if core else '신뢰 미흡'}
    return out


def agreement(I):
    two = [t for t in I if len(t['v']) >= 2]
    js = sorted({j for t in two for j in t['v']})[:2]
    if len(js) < 2:
        return {}
    a, b = js
    f = lambda field, ts: so.rate(sum(t['v'][a].get(field) == t['v'][b].get(field) for t in ts), len(ts))
    return {'judges': js, 'items': len(two), 'value(S·G·F)': f('value', [t for t in two if t['kind'] in 'SGF']), 'claim(F)': f('claim', [t for t in two if t['kind'] == 'F']),
            'response': f('response', two), 'addressed': f('addressed', two), 'fact_error': f('fact_error', two), 'exposure': f('exposure', two),
            'auto_correct_confirmed': so.rate(sum(all(v.get('value') == '일치' for v in t['v'].values()) for t in two if t['class'] == 'correct' and t['kind'] in 'SGF'),
                                              sum(1 for t in two if t['class'] == 'correct' and t['kind'] in 'SGF'))}


def attach_truth(I):
    items = {b['id']: b for b in so.read_jsonl(BASE / 'items' / 'all.jsonl')}
    for t in I:
        m = next((x for x in items[t['id']]['items'] if x['no'] == t['item']), {})
        t['claim_true'] = (m.get('claim') or {}).get('true') if m.get('claim') else None


def show(name, c):
    print(f"[{name}] 판정 {c['verdict']['overall']} · 충족 {c['verdict']['met']}")
    print(f"   D1 노출 {c['D1']['exposure']}(한 명 {c['D1']['exposure_any_judge']}) · 차단 실패 {c['D1']['block_fail']} · C 적절 {c['D1']['C_appropriate']['k']}/{c['D1']['C_appropriate']['n']}")
    print(f"   D2 조용한 오답 {c['D2']['k']}/{c['D2']['n']} {c['D2']['pct']}% {c['D2']['ci95']} {c['D2']['ids']}")
    print(f"   D3 정답 {c['D3']['k']}/{c['D3']['n']} {c['D3']['pct']}% {c['D3']['ci95']}(자동 {c['D3']['auto']['pct']}%) · D4 주장 검증 {c['D4']['k']}/{c['D4']['n']} {c['D4']['by_truth']}")
    print(f"   D5 변형 쌍 {c['D5']['k']}/{c['D5']['n']} · D6 근거 없는 값 {c['D6']['ungrounded']} 적절 {c['D6']['appropriate']['k']}/{c['D6']['appropriate']['n']} {c['D6']['not_appropriate']}")
    print(f"   D7 제도 사실·단정 {c['D7']['k']}/{c['D7']['n']} {c['D7']['pct']}% · D8 완결 {c['D8']['k']}/{c['D8']['n']} · 미판정 {c['report']['unjudged']} · 평가자 엇갈림 {c['report']['judge_split']}")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--main', required=True); ap.add_argument('--ctrl')
    a = ap.parse_args()
    run, code = a.main.split(':')
    I, sc = load(run, code); attach_truth(I)
    res = {'main': {'run': run, 'criteria': criteria(I), 'auto': sc['summary'], 'judge_agreement': agreement(I)}}
    if a.ctrl:
        crun, ccode = a.ctrl.split(':')
        IC, scc = load(crun, ccode); attach_truth(IC)
        jof = {t['id']: next(iter(t['v'])) for t in IC if t['v']}
        res['ctrl'] = {'run': crun, 'criteria': criteria(IC), 'auto': scc['summary']}
        res['main_single'] = {'note': '판정 대상 구성을 비교 구성과 같은 평가자 1인의 값으로 다시 센 것', 'criteria': criteria(I, jof)}
        cm, cc = res['main_single']['criteria']['classes'], res['ctrl']['criteria']['classes']
        tab = collections.defaultdict(list)
        for k in sorted(set(cm) & set(cc)):
            lab = lambda v: '정답' if v == 'correct' else '오답' if v == 'wrong' else '값 없음'
            tab[f'{lab(cc[k])} → {lab(cm[k])}'].append(k)
        res['paired'] = {'note': '계산 항목의 분류: 비교 구성 → 판정 대상 구성', 'table': {k: len(v) for k, v in sorted(tab.items())}, 'changed': {k: v for k, v in tab.items() if k.split(' → ')[0] != k.split(' → ')[1]}}
    (BASE / '결과.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
    for name in ('main', 'main_single', 'ctrl'):
        if name in res:
            show(name, res[name]['criteria'])
    if res['main'].get('judge_agreement'):
        print('   평가자 일치', {k: (v if not isinstance(v, dict) else (v['k'], v['n'])) for k, v in res['main']['judge_agreement'].items()})
    if 'paired' in res:
        print('   두 구성 대조', res['paired']['table'], res['paired']['changed'])


if __name__ == '__main__':
    main()
