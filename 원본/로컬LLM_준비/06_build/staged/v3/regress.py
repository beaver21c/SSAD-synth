#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""보완본 분석 함수의 회귀 점검 — 정답 코드의 산출값과 검증 경고가 현행과 같은지, 새 안내·경고가 의도한 경우에만 나오는지 본다.

  ① 한 번에 라이브러리 하나를 실행해 결과를 파일로 남김:  python regress.py run <라이브러리 폴더> <출력 json>
  ② 두 결과를 대조:                                    python regress.py diff <현행 json> <보완본 json>
     대조 기준: 정답 코드(벤치마크·안전성·보류 검증 문항)의 실행 성공 여부, 집계 결과, 경고 목록이 모두 같아야 함(종료 코드 0)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROBES = {      # 이름: (코드, 보완본에서 기대하는 것)  — 'err:문구' 는 오류 첫 줄에 그 문구가 있어야 함, 'warn:이름' 은 그 경고가 있어야 함, 'ok' 는 경고 없이 실행
    'P_evou_notna': ("import ssda\nprint(ssda.rate('evou_yn == 1', where='not isna(evou_yn)', by='inc5'))", 'warn:대상 한정'),
    'P_evou_amt': ("import ssda\nprint(ssda.rate('evou_yn == 1', where='not isna(evou_amt)', by='hs4'))", 'warn:대상 한정'),
    'P_evou_or': ("import ssda\nprint(ssda.rate('evou_yn == 1', where='not isna(evou_yn) or not isna(evou_amt)', by='inc5'))", 'warn:대상 한정'),
    'P_evou_and': ("import ssda\nprint(ssda.rate('evou_yn == 1', where='not isna(evou_yn) and inc5 == 0', by='sido'))", 'warn:대상 한정'),
    'P_evou_ok': ("import ssda\nprint(ssda.rate('evou_yn == 1', by='inc5'))", 'ok'),
    'P_bp_ok': ("import ssda\nprint(ssda.rate('bp_yn1 == 1', where='age >= 65', by='sido'))", 'ok'),
    'P_hnum_by': ("import ssda\nprint(ssda.quantile('h_prop', q=0.5, by='hnum', unit='가구'))", 'err:hs4'),
    'P_hnum_share': ("import ssda\nprint(ssda.share('hnum', where='evou_yn == 1'))", 'err:hs4'),
    'P_hnum_where': ("import ssda\nprint(ssda.rate('nbls_live_yn1 == 1', where='hnum == 1', by='age6'))", 'ok'),
    'P_hs4': ("import ssda\nprint(ssda.share('hs4', where='evou_yn == 1'))", 'ok'),
    'P_by_expr': ("import ssda\nprint(ssda.poverty_rate(where='age >= 65', by='bp_yn1 == 1'))", "err:isna(bp_yn1)"),
    'P_by_expr2': ("import ssda\nprint(ssda.mean('p_labinc', by='age >= 65'))", 'err:not (age >= 65)'),
    'P_by_missing': ("import ssda\nprint(ssda.count(by='nosuch'))", 'err:없는 분류 기준'),
    'P_sex2': ("import ssda\nprint(ssda.rate('sex == 2', where='age >= 65', by='bp_type'))", 'err:gender'),
    'P_sex_str': ("import ssda\nprint(ssda.count(where='sex == \"여\"'))", 'err:sex == 1'),
    'P_sido1': ("import ssda\nprint(ssda.count(where='sido == 1'))", 'ok'),
    'P_inc5_5': ("import ssda\nprint(ssda.count(where='inc5 == 5'))", 'err:항목 순번'),
    'P_noprint': ("import ssda\nssda.find_vars('가구원 수', top=10)", 'tool:출력이 없음'),
    'P_degenerate_legit': ("import ssda\nprint(ssda.rate('age >= 65', where='bp_yn1 == 1'))", 'warn:대상 한정'),
    'P_dg_ret': ("import ssda\ng = ssda.define_group('age_o', 'age', [65, 75], ['65세 미만', '65~74세', '75세 이상'])\nprint(ssda.rate('bp_yn1 == 1', where='age >= 65', by=g))", 'ok'),
    'P_dg_inline': ("import ssda\nprint(ssda.rate('bp_yn1 == 1', where='age >= 65', by=ssda.define_group('age_o', 'age', [65, 75], ['65세 미만', '65~74세', '75세 이상'])))", 'ok'),
    'P_dg_name': ("import ssda\nssda.define_group('age_o', 'age', [65, 75], ['65세 미만', '65~74세', '75세 이상'])\nprint(ssda.rate('bp_yn1 == 1', where='age >= 65', by='age_o'))", 'ok'),
    'P_dg_print': ("import ssda\nprint(ssda.define_group('age_o', 'age', [65, 75], ['65세 미만', '65~74세', '75세 이상']))", 'ok'),
    'P_dg_3args': ("import ssda\nprint(ssda.poverty_rate(where='age >= 65', by=ssda.define_group('bp', 'bp_yn1 == 1', ['수급자', '비수급자'])))", 'err:네 인자'),
    'P_dg_cond': ("import ssda\nssda.define_group('bp', 'bp_yn1 == 1', [1], ['비수급자', '수급자'])", 'err:조건식'),
    'P_dg_yn': ("import ssda\nprint(ssda.poverty_rate(where='age >= 65', by=ssda.define_group('bp', 'bp_yn1', [1], ['비수급자', '수급자'])))", 'err:isna(bp_yn1)'),
    'P_ne1_count': ("import ssda\nprint(ssda.count('age >= 65 and bp_yn1 != 1'))", 'warn:1 아님 비교'),
    'P_ne1_rate': ("import ssda\nprint(ssda.rate('bp_yn1 != 1 and np_pension_yn != 1', where='age >= 65'))", 'warn:1 아님 비교'),
    'P_ne1_legit': ("import ssda\nprint(ssda.count('age >= 65 and gender != 1'))", 'ok'),
    'P_isna_ok': ("import ssda\nprint(ssda.count('age >= 65 and isna(bp_yn1)'))", 'ok'),
}


def run(lib, outp):
    sys.path.insert(0, lib)
    os.environ.setdefault('SSDA_EXPORT', tempfile.mkdtemp(prefix='ssda_reg_'))
    import ssda
    from ssda import runner, verify
    assert os.path.abspath(ssda.__file__).startswith(os.path.abspath(lib)), ssda.__file__
    ssda.open_data()
    codes = {}
    for f in ('05_eval/benchmark.jsonl', '05_eval/safety_cases.jsonl', '05_eval/holdout.jsonl', '05_eval/holdout2.jsonl'):
        if (ROOT / f).exists():
            for l in (ROOT / f).read_text(encoding='utf-8').splitlines():
                b = json.loads(l)
                if b.get('gold_code'):
                    codes['G_' + b['id']] = b['gold_code']
    res = {'_version': ssda.__version__}
    for k, c in {**codes, **{k: v[0] for k, v in PROBES.items()}}.items():
        o = runner.run(c, limits=False)
        res[k] = {'ok': o['ok'], 'error': (o['error'] or '').splitlines()[0][:500] if o['error'] else '', 'records': {n: v['records'] for n, v in o['results'].items()},
                  'warnings': sorted({c2['code'] for cs in (o.get('checks') or {}).values() for c2 in cs if c2['level'] == '경고'}), 'figures': len(o.get('figures') or []),
                  'tool': verify.tool_message(o)[-900:]}
    json.dump(res, open(outp, 'w', encoding='utf-8'), ensure_ascii=False)
    print(lib, res['_version'], len(res) - 1, '건')


def diff(a, b):
    A, B = json.load(open(a, encoding='utf-8')), json.load(open(b, encoding='utf-8'))
    bad = []
    gold = [k for k in A if k.startswith('G_')]
    for k in gold:
        for f in ('ok', 'records', 'warnings', 'figures'):
            if A[k][f] != B.get(k, {}).get(f):
                bad.append(f'{k}: {f} 가 다름' + (f" ({A[k]['warnings']} → {B[k]['warnings']})" if f == 'warnings' else f" ({B[k]['error'][:120]})" if f == 'ok' else ''))
    fail_gold = [k for k in gold if not A[k]['ok']]
    probes = []
    for k, (_, want) in PROBES.items():
        r = B[k]; kind, _, text = want.partition(':')
        ok = (kind == 'ok' and r['ok'] and not r['warnings']) or (kind == 'err' and not r['ok'] and text in r['error']) or (kind == 'warn' and r['ok'] and text in r['warnings']) or (kind == 'tool' and text in r['tool'])
        probes.append((k, ok, want, (r['error'] or ', '.join(r['warnings']) or '경고 없음')[:150]))
        if not ok:
            bad.append(f'{k}: 기대({want})와 다름 — {r["error"][:150] or r["warnings"]}')
    print(f"정답 코드 {len(gold)}건(현행에서 실행 실패 {len(fail_gold)}건) · 현행 {A['_version']} → 보완본 {B['_version']}")
    for k, ok, want, got in probes:
        print(f"  {'○' if ok else '×'} {k:20s} 기대 {want:22s} | {got}")
    print('차이 없음(정답 코드의 실행·집계 결과·경고가 모두 같음), 안내·경고 시험 모두 기대와 같음' if not bad else '차이:\n  ' + '\n  '.join(bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(run(sys.argv[2], sys.argv[3]) or 0 if sys.argv[1] == 'run' else diff(sys.argv[2], sys.argv[3]))
