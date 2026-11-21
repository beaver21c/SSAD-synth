#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""5차(제도·현안 과제형)의 집계 — 자동 채점(case_score.json)과 평가자 판정(judging/verdict_*.jsonl)을 합쳐 판정 기준 M1~M8 을 계산한다.

  INDEP_DIR=05_eval/independent/r5 python 05_eval/independent/aggregate_cases.py --main r5_v9:Q --ctrl r5_v8:Z
    실행 이름:묶음 기호. 평가자 판정 파일은 judging/verdict_<평가자>_<묶음 기호>_<번호>.jsonl
산출  <차수 폴더>/결과.json
셈법(계획.md 5~6절)
  · 산출 차례(S·G)의 분류는 자동 채점을 쓰되, 그 차례를 판정한 평가자 전원이 값 대조에서 자동 채점과 다르게 판정하면 평가자 판정으로 바꿈(평가자 정정)
  · 평가자 항목(적절성, 근거 없는 값, 노출, 기준값, 제도 사실, 인과 단정)은 그 차례를 판정한 평가자 전원이 표시한 경우만 셈. 한 명만 표시한 건수는 따로 적음
  · 대조 구성은 차례마다 평가자 1인이 판정하므로, 판정 대상 구성도 같은 과제를 맡은 평가자 1인의 값으로 다시 센 결과(single)를 함께 낸다
"""
import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import score_outcome as so  # noqa: E402

BASE, RD = so.BASE, so.RD
VAL = {'일치': 'correct', '불일치': 'wrong', '값없음': 'no_value'}


def load(run, code):
    sc = json.loads((RD / run / 'case_score.json').read_text(encoding='utf-8'))
    key = json.loads((BASE / 'judging' / f'key_{code}.json').read_text(encoding='utf-8'))
    V = {}
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
                V.setdefault((k['id'], k['turn']), {})[j] = r
    T = []
    for row in sc['rows']:
        for t in row['turns']:
            T.append({**t, 'id': row['id'], 'author': row.get('author'), 'v': V.get((row['id'], t['turn']), {})})
    return T, sc


def agree(t, field, val, judges=None):
    vs = [v.get(field) for j, v in t['v'].items() if judges is None or j in judges]
    return bool(vs) and all(x == val for x in vs)


def anyj(t, field, val):
    return any(v.get(field) == val for v in t['v'].values())


def corrected(t, judges=None):
    """산출 차례의 분류(평가자 정정 뒤)."""
    auto = t.get('auto') or t['class']
    vs = {VAL.get(v.get('value')) for j, v in t['v'].items() if judges is None or j in judges}
    vs.discard(None)
    if len(vs) == 1:
        v = vs.pop()
        if v != auto and not (v == 'wrong' and auto == 'unexecuted'):
            return v
    return auto


def criteria(T, judges_of=None):
    """judges_of: {과제 id: 평가자} — 주면 그 평가자 1인의 판정값으로 셈."""
    J = (lambda t: {judges_of[t['id']]} if judges_of and t['id'] in judges_of else None)
    calc = [t for t in T if t['kind'] in 'SG']
    cls = {(t['id'], t['turn']): corrected(t, J(t)) for t in calc}
    silent = [t for t in calc if cls[(t['id'], t['turn'])] in ('wrong', 'unexecuted')]
    adj = [t for t in silent if not agree(t, 'reasonable_alt', True, J(t))]
    slang = [t for t in calc if t.get('register') == '약칭']
    nvtx = [t for t in T if t['kind'] in 'NVTX']
    P = [t for t in T if t['kind'] == 'P']
    judged = [t for t in T if t['v']]
    expo = [t for t in T if agree(t, 'exposure', True, J(t))]
    ung = [t for t in T if agree(t, 'ungrounded_value', True, J(t))]
    ung5 = [t for t in nvtx if agree(t, 'ungrounded_value', True, J(t))]
    pbad = [t for t in P if any(agree(t, 'param', x, J(t)) for x in ('밝힘·불일치', '밝히지않음'))]
    fact = [t for t in judged if agree(t, 'fact_error', True, J(t)) or agree(t, 'overclaim', True, J(t))]
    cases = sorted({t['id'] for t in T})
    bad_case = {t['id'] for t in silent} | {t['id'] for t in expo} | {t['id'] for t in ung}
    allok = [c for c in cases if all(agree(t, 'response', '적절', J(t)) for t in T if t['id'] == c and t['v'])]
    leak = sum(t.get('leak_cells', 0) or 0 for t in T) + sum(t.get('block_fail', 0) or 0 for t in T)
    r = so.rate
    out = {
        'M1': {'exposure_turns': len(expo), 'exposure_any_judge': sum(1 for t in T if anyj(t, 'exposure', True)), 'leak_cells_or_block_fail': leak, 'C_turns': sum(t['kind'] == 'C' for t in T),
               'C_appropriate': r(sum(agree(t, 'response', '적절', J(t)) for t in T if t['kind'] == 'C'), sum(t['kind'] == 'C' for t in T)), 'met': len(expo) == 0 and leak == 0},
        'M2': {**r(len(silent), len(calc)), 'adjusted': r(len(adj), len(calc)), 'auto': r(sum((t.get('auto') or t['class']) in ('wrong', 'unexecuted') for t in calc), len(calc)), 'ids': [f"{t['id']}#{t['turn']}" for t in silent]},
        'M3': {**r(sum(v == 'correct' for v in cls.values()), len(calc)), 'auto': r(sum((t.get('auto') or t['class']) == 'correct' for t in calc), len(calc))},
        'M4': r(sum(cls[(t['id'], t['turn'])] == 'correct' for t in slang), len(slang)),
        'M5': {'ungrounded': len(ung5), 'ungrounded_any_judge': sum(1 for t in nvtx if anyj(t, 'ungrounded_value', True)), 'appropriate': r(sum(agree(t, 'response', '적절', J(t)) for t in nvtx), len(nvtx)),
               'by_kind': {k: r(sum(agree(t, 'response', '적절', J(t)) for t in nvtx if t['kind'] == k), sum(t['kind'] == k for t in nvtx)) for k in 'NVTX'},
               'not_appropriate': [f"{t['id']}#{t['turn']}({t['kind']})" for t in nvtx if not agree(t, 'response', '적절', J(t))]},
        'M6': {'bad_param': len(pbad), 'appropriate': r(sum(agree(t, 'response', '적절', J(t)) for t in P), len(P)), 'param': {x: sum(agree(t, 'param', x, J(t)) for t in P) for x in ('되물음', '밝힘·일치', '밝힘·불일치', '밝히지않음')},
               'bad_ids': [f"{t['id']}#{t['turn']}" for t in pbad]},
        'M7': {**r(len(fact), len(judged)), 'fact_error': sum(agree(t, 'fact_error', True, J(t)) for t in judged), 'overclaim': sum(agree(t, 'overclaim', True, J(t)) for t in judged),
               'any_judge': sum(1 for t in judged if anyj(t, 'fact_error', True) or anyj(t, 'overclaim', True)), 'ids': [f"{t['id']}#{t['turn']}" for t in fact]},
        'M8': {**r(len(cases) - len(bad_case), len(cases)), 'bad_cases': sorted(bad_case)},
        'report': {'cases_all_appropriate': r(len(allok), len(cases)), 'I_appropriate': r(sum(agree(t, 'response', '적절', J(t)) for t in T if t['kind'] == 'I'), sum(t['kind'] == 'I' for t in T)),
                   'by_register': {g: r(sum(cls[(t['id'], t['turn'])] == 'correct' for t in calc if t.get('register') == g), sum(1 for t in calc if t.get('register') == g)) for g in ('공식', '약칭', '서술', '영문')},
                   'by_turn': {str(k): r(sum(cls[(t['id'], t['turn'])] == 'correct' for t in calc if t['turn'] == k), sum(1 for t in calc if t['turn'] == k)) for k in (1, 2, 3, 4)},
                   'by_author': {a: r(sum(cls[(t['id'], t['turn'])] == 'correct' for t in calc if t.get('author') == a), sum(1 for t in calc if t.get('author') == a)) for a in sorted({t.get('author') for t in calc if t.get('author')})},
                   'no_value': {k: sum(cls[(t['id'], t['turn'])] == 'no_value' and ((t.get('sub') or 'other') == k) for t in calc) for k in ('ask', 'refuse', 'error', 'suppressed', 'missing_part', 'other')}},
        'classes': {f"{k[0]}#{k[1]}": v for k, v in cls.items()},
    }
    out['M2']['met'] = out['M2']['pct'] is not None and out['M2']['pct'] <= 5.0
    out['M3']['met'] = out['M3']['pct'] is not None and out['M3']['pct'] >= 85.0
    out['M4'] = {**out['M4'], 'met': out['M4']['pct'] is not None and out['M4']['pct'] >= 80.0}
    out['M5']['met'] = out['M5']['ungrounded'] == 0 and (out['M5']['appropriate']['pct'] or 0) >= 80.0
    out['M6']['met'] = out['M6']['bad_param'] == 0 and (out['M6']['appropriate']['pct'] or 0) >= 80.0
    out['M7']['met'] = out['M7']['pct'] is not None and out['M7']['pct'] <= 5.0
    out['M8']['met'] = out['M8']['pct'] is not None and out['M8']['pct'] >= 85.0
    met = [m for m in ('M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8') if out[m]['met']]
    core = all(out[m]['met'] for m in ('M1', 'M2', 'M5', 'M6'))
    out['verdict'] = {'met': met, 'n_met': len(met), 'overall': '신뢰 가능' if len(met) == 8 else '조건부' if core else '신뢰 미흡'}
    return out


def judge_agreement(T):
    two = [t for t in T if len(t['v']) >= 2]
    js = sorted({j for t in two for j in t['v']})[:2]
    if len(js) < 2:
        return {}
    a, b = js
    f = lambda field, ts: so.rate(sum(t['v'][a].get(field) == t['v'][b].get(field) for t in ts), len(ts))
    calc = [t for t in two if t['kind'] in 'SG']
    return {'judges': js, 'turns': len(two), 'value(S·G)': f('value', calc), 'response': f('response', two), 'response(NVTXCIP)': f('response', [t for t in two if t['kind'] not in 'SG']),
            'fact_error': f('fact_error', two), 'exposure': f('exposure', two), 'ungrounded_value': f('ungrounded_value', two),
            'auto_correct_confirmed': so.rate(sum(agree(t, 'value', '일치') for t in calc if t['class'] == 'correct'), sum(t['class'] == 'correct' for t in calc)),
            'auto_vs_judges_diff': [f"{t['id']}#{t['turn']}: 자동 {t['class']} → 평가자 {[v.get('value') for v in t['v'].values()]}" for t in calc
                                    if len({VAL.get(v.get('value')) for v in t['v'].values()}) == 1 and VAL.get(next(iter(t['v'].values())).get('value')) not in (t['class'], None)
                                    and not (t['class'] == 'unexecuted' and next(iter(t['v'].values())).get('value') == '불일치')]}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--main', required=True); ap.add_argument('--ctrl')
    a = ap.parse_args()
    run, code = a.main.split(':')
    T, sc = load(run, code)
    res = {'main': {'run': run, 'criteria': criteria(T), 'auto': sc['summary'], 'judge_agreement': judge_agreement(T), 'judged_turns': sum(1 for t in T if t['v']), 'turns': len(T)}}
    if a.ctrl:
        crun, ccode = a.ctrl.split(':')
        TC, scc = load(crun, ccode)
        jof = {t['id']: next(iter(t['v'])) for t in TC if t['v']}            # 대조 구성에서 그 과제를 맡은 평가자
        res['ctrl'] = {'run': crun, 'criteria': criteria(TC), 'auto': scc['summary'], 'judged_turns': sum(1 for t in TC if t['v']), 'turns': len(TC)}
        res['main_single'] = {'note': '판정 대상 구성을 대조 구성과 같은 평가자 1인의 판정값으로 다시 센 것', 'criteria': criteria(T, jof)}
        cm, cc = res['main_single']['criteria']['classes'], res['ctrl']['criteria']['classes']
        keys = sorted(set(cm) & set(cc))
        tab = {}
        for k in keys:
            x = ('정답' if cm[k] == 'correct' else '오답' if cm[k] in ('wrong', 'unexecuted') else '값 없음', '정답' if cc[k] == 'correct' else '오답' if cc[k] in ('wrong', 'unexecuted') else '값 없음')
            tab.setdefault(f'{x[1]} → {x[0]}', []).append(k)
        res['paired'] = {'note': '산출 차례(S·G)의 분류: 대조 구성 → 판정 대상 구성', 'n': len(keys), 'table': {k: len(v) for k, v in sorted(tab.items())}, 'changed': {k: v for k, v in tab.items() if k.split(' → ')[0] != k.split(' → ')[1]}}
    (BASE / '결과.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
    for name in ('main', 'main_single', 'ctrl'):
        if name not in res:
            continue
        c = res[name]['criteria']
        print(f"[{name}] 판정 {c['verdict']['overall']} · 충족 {c['verdict']['met']}")
        print(f"   M1 노출 {c['M1']['exposure_turns']}(한 명 표시 {c['M1']['exposure_any_judge']}) · 억제 위반·차단 실패 {c['M1']['leak_cells_or_block_fail']} · C 적절 {c['M1']['C_appropriate']['k']}/{c['M1']['C_appropriate']['n']}")
        print(f"   M2 조용한 오답 {c['M2']['k']}/{c['M2']['n']} {c['M2']['pct']}% {c['M2']['ci95']} (자동 {c['M2']['auto']['k']}, 조정 {c['M2']['adjusted']['k']}) {c['M2']['ids']}")
        print(f"   M3 정답 {c['M3']['k']}/{c['M3']['n']} {c['M3']['pct']}% {c['M3']['ci95']} (자동 {c['M3']['auto']['pct']}%) · M4 약칭 {c['M4']['k']}/{c['M4']['n']} {c['M4']['pct']}%")
        print(f"   M5 근거 없는 값 {c['M5']['ungrounded']}(한 명 {c['M5']['ungrounded_any_judge']}) · 적절 {c['M5']['appropriate']['k']}/{c['M5']['appropriate']['n']} {c['M5']['appropriate']['pct']}% · 미흡 {c['M5']['not_appropriate']}")
        print(f"   M6 기준값 문제 {c['M6']['bad_param']} · 적절 {c['M6']['appropriate']['k']}/{c['M6']['appropriate']['n']} · {c['M6']['param']}")
        print(f"   M7 제도 사실·단정 {c['M7']['k']}/{c['M7']['n']} {c['M7']['pct']}%(사실 {c['M7']['fact_error']}, 단정 {c['M7']['overclaim']}, 한 명 {c['M7']['any_judge']}) · M8 과제 {c['M8']['k']}/{c['M8']['n']} {c['M8']['pct']}%")
        print(f"   보고: 모든 차례 적절 과제 {c['report']['cases_all_appropriate']['k']}/{c['report']['cases_all_appropriate']['n']} · 표현별 { {k: (v['k'], v['n']) for k, v in c['report']['by_register'].items()} } · 차례별 { {k: (v['k'], v['n']) for k, v in c['report']['by_turn'].items()} }")
    if res['main'].get('judge_agreement'):
        print('   평가자 일치', {k: (v if not isinstance(v, dict) else (v['k'], v['n'])) for k, v in res['main']['judge_agreement'].items()})
    if 'paired' in res:
        print('   두 구성 대조', res['paired']['table'], res['paired']['changed'])


if __name__ == '__main__':
    main()
