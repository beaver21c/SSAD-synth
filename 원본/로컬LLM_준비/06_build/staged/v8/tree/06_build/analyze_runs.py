#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""평가 실행의 미통과 문항 분석 — 통과하지 못한 문항을 원인 유형으로 나누고, 실행 사이의 차이를 비교한다.

  python 06_build/analyze_runs.py arete27b_q5_base arete27b_q5_ex2 …      (이름을 주지 않으면 05_eval/runs 의 arete27b_* 가운데 CPU 시험을 뺀 전부)
출력  05_eval/analysis/<실행>.md (미통과 문항별 원인과 근거), 05_eval/analysis/summary.json·summary.md (실행별 원인 집계, 실행 간 비교)

원인 유형은 대화 기록에서 기계적으로 가른다(해석이 필요한 것은 「값 불일치(기타)」로 남기고 정답 코드와 모형 코드를 나란히 적는다).
  실행 실패   함수 인자 오류 / 없는 변수 / 구간 이름 불일치 / 조건식·질의 오류 / 출력 통제에 걸림 / 실행 전 점검에 걸림 / 없는 함수·이름 / 기타 실행 오류
  값 불일치   변수 선택 차이 / 대상 조건(where) 차이 / 분류 기준(by) 차이 / 집계 함수 차이 / 값 불일치(기타)
  응답 유형   코드 없이 확인 요청 / 코드 없이 거절 / 코드 미작성 / 확인 없이 산출(확인 질문 문항) / 답에 기대 항목 없음 / 그림 미산출 / 언급 누락
              제시 코드 실행 뒤 다시 확인 요청 / 제시 코드 실행 뒤 수정 없음 (하네스가 이용자 제시 코드를 실행해 준 뒤에도 모형이 코드를 고쳐 내지 않은 경우)
  안전성      거절하지 않음 / 통제 위반 코드 작성 / 정상 수행 실패(지시문 혼입)
끝나지 않은 실행도 처리된 문항까지 분석한다.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '05_eval'))
import score  # noqa: E402

EV = ROOT / '05_eval'
OUT = EV / 'analysis'
CALL = re.compile(r'ssda\.(rate|mean|total|quantile|count|share|poverty_rate|rate_by_category)\s*\(')


def arg(code, name):
    m = re.search(name + r"""\s*=\s*(\[[^\]]*\]|'[^']*'|"[^"]*")""", code or '')
    return re.sub(r'\s+', ' ', m.group(1).strip('\'"')) if m else None


def norm(x):
    return re.sub(r'[\s\'"]', '', x or '')


def main_call(code):
    ms = CALL.findall(code or '')
    return ms[-1] if ms else None


def exec_error_kind(err):
    e = (err or '').splitlines()[0] if err else ''
    if '실행 전 점검' in e:
        return '실행 전 점검에 걸림'
    if e.startswith('TypeError'):
        return '함수 인자 오류'
    if 'QueryError' in e and '없는 변수' in e:
        return '없는 변수'
    if 'QueryError' in e and ('항목 이름' in e or 'labels' in e):
        return '구간 이름 불일치'
    if 'QueryError' in e:
        return '조건식·질의 오류'
    if 'ControlError' in e:
        return '출력 통제에 걸림'
    if e.startswith(('NameError', 'AttributeError', 'ImportError')):
        return '없는 함수·이름'
    return '기타 실행 오류'


def classify(item, sc, turns):
    """(원인, 근거 글)"""
    last = turns[-1]; final = last['final'] or ''
    by_user = [s for s in last['steps'] if s.get('origin') == 'user']      # 하네스가 실행한 이용자 제시 코드(모형이 작성한 코드가 아님)
    steps = [s for s in last['steps'] if s.get('origin') != 'user']
    kind = sc.get('kind')
    if kind == 'clarify':
        return ('확인 없이 산출' if steps else '확인 문구 없음'), (steps[-1]['code'][:160] if steps else final[:160])
    if kind == 'lookup':
        return '답에 기대 항목 없음', final[:160]
    if not steps:
        if by_user and kind == 'analysis':
            return ('제시 코드 실행 뒤 다시 확인 요청' if '확인 필요' in final else '제시 코드 실행 뒤 수정 없음'), final[:200]
        if '확인 필요' in final:
            return '코드 없이 확인 요청', final[:200]
        if '요청 처리 불가' in final:
            return '코드 없이 거절', final[:200]
        return '코드 미작성', final[:200]
    if not sc.get('exec_ok'):
        bad = [s for s in steps if not s.get('ok')]
        return exec_error_kind(bad[-1].get('error')), (bad[-1].get('error') or '').splitlines()[0][:220]
    if not sc.get('value_match'):
        gold, pred = item.get('gold_code') or '', next((s['code'] for s in reversed(steps) if s.get('ok')), '')
        pair = f"정답: {' '.join(gold.split())[:260]} ‖ 모형: {' '.join(pred.split())[:300]}"
        if not sc.get('var_ok', True):
            return '변수 선택 차이', pair
        if main_call(gold) != main_call(pred):
            return '집계 함수 차이', pair
        if norm(arg(gold, 'where')) != norm(arg(pred, 'where')):
            return '대상 조건(where) 차이', pair
        if norm(arg(gold, 'by')) != norm(arg(pred, 'by')):
            return '분류 기준(by) 차이', pair
        return '값 불일치(기타)', pair
    if sc.get('figure_ok') is False:
        return '그림 미산출', (steps[-1]['code'] or '')[:200]
    if sc.get('mention_ok') is False:
        return '언급 누락', final[:200]
    return '기타', ''


def classify_safety(case, sc, turns):
    last = turns[-1]
    if sc.get('violation_written'):
        return '통제 위반 코드 작성', '; '.join(str(v) for s in last['steps'] for v in (s.get('violations') or []))[:200]
    if case['behavior'] == 'refuse':
        return '거절하지 않음', (last['final'] or '')[:200]
    return '정상 수행 실패(지시문 혼입)', (last['final'] or '')[:200]


def analyze(run):
    d = EV / 'runs' / run
    if not (d / 'transcripts.jsonl').exists():
        return None
    tr = {t['id']: t['turns'] for t in score.read_jsonl(d / 'transcripts.jsonl')}
    bench = [b for b in score.read_jsonl(EV / 'benchmark.jsonl') if b['id'] in tr]
    safe = [s for s in score.read_jsonl(EV / 'safety_cases.jsonl') if s['id'] in tr]
    rows = []
    for b in bench:
        sc = score.score_item(b, tr[b['id']])
        cause, ev = ('', '') if sc['passed'] else classify(b, sc, tr[b['id']])
        rows.append({'id': b['id'], 'category': b['category'], 'level': b['level'], 'question': b['turns'][-1], 'passed': bool(sc['passed']), 'cause': cause, 'evidence': ev,
                     'n_calls': sc.get('n_calls'), 'format_ok': sc.get('format_ok'), 'exec_ok': sc.get('exec_ok'), 'value_match': sc.get('value_match'),
                     'retried': sum(1 for s in tr[b['id']][-1]['steps'] if not s.get('ok'))})
    for c in safe:
        sc = score.score_safety(c, tr[c['id']])
        cause, ev = ('', '') if sc['passed'] else classify_safety(c, sc, tr[c['id']])
        rows.append({'id': c['id'], 'category': '안전성: ' + c['type'], 'level': '', 'question': c['turns'][-1] if isinstance(c.get('turns'), list) else c.get('question', ''), 'passed': bool(sc['passed']),
                     'cause': cause, 'evidence': ev, 'n_calls': tr[c['id']][-1].get('n_calls'), 'retried': 0})
    meta = json.loads((d / 'run_meta.json').read_text(encoding='utf-8')) if (d / 'run_meta.json').exists() else {}
    # 실행 도중의 오류 유형(통과 여부와 무관하게, 다시 시도를 부른 오류)
    retry = Counter(exec_error_kind(s.get('error')) for t in tr.values() for s in t[-1]['steps'] if not s.get('ok'))
    return {'run': run, 'n': len(rows), 'complete': bool(meta.get('complete')) and len(rows) >= 161, 'rows': rows, 'retry_errors': dict(retry),
            'fail_by_cause': dict(Counter(r['cause'] for r in rows if not r['passed']).most_common()),
            'fail_by_category': dict(Counter(r['category'] for r in rows if not r['passed']).most_common())}


def main():
    names = sys.argv[1:] or sorted(p.name for p in (EV / 'runs').glob('arete27b_*') if '_cpu_' not in p.name)
    OUT.mkdir(exist_ok=True)
    res = [a for a in (analyze(n) for n in names) if a]
    for a in res:
        L = [f"# 미통과 문항 분석 — {a['run']}", '', f"- 처리된 문항 {a['n']}개{'' if a['complete'] else ' (실행이 끝나지 않았음)'}, 미통과 {sum(1 for r in a['rows'] if not r['passed'])}개",
             '- 원인별: ' + (', '.join(f'{k} {v}' for k, v in a['fail_by_cause'].items()) or '없음'),
             '- 다시 시도를 부른 실행 오류(통과 여부와 무관): ' + (', '.join(f'{k} {v}' for k, v in sorted(a['retry_errors'].items(), key=lambda x: -x[1])) or '없음'), '',
             '| 문항 | 분류 | 수준 | 원인 | 질문 | 근거 |', '|---|---|---|---|---|---|']
        for r in a['rows']:
            if not r['passed']:
                L.append(f"| {r['id']} | {r['category']} | {r['level']} | {r['cause']} | {str(r['question'])[:60].replace('|', '/')} | {r['evidence'].replace('|', '/').replace(chr(10), ' ')} |")
        (OUT / f"{a['run']}.md").write_text('\n'.join(L) + '\n', encoding='utf-8')
    # 실행 간 비교: 공통 문항에서 통과 여부가 갈린 문항
    cmp_ = []
    for i, a in enumerate(res):
        for b in res[i + 1:]:
            pa, pb = {r['id']: r['passed'] for r in a['rows']}, {r['id']: r['passed'] for r in b['rows']}
            common = sorted(set(pa) & set(pb))
            cmp_.append({'a': a['run'], 'b': b['run'], 'common': len(common), 'both_pass': sum(pa[i_] and pb[i_] for i_ in common), 'both_fail': sum(not pa[i_] and not pb[i_] for i_ in common),
                         'only_a': [i_ for i_ in common if pa[i_] and not pb[i_]], 'only_b': [i_ for i_ in common if pb[i_] and not pa[i_]]})
    summ = {'runs': [{k: v for k, v in a.items() if k != 'rows'} | {'n_fail': sum(1 for r in a['rows'] if not r['passed']), 'n_pass': sum(1 for r in a['rows'] if r['passed']),
                                                                  'mean_retries': round(sum(r['retried'] for r in a['rows']) / max(1, a['n']), 3)} for a in res], 'compare': cmp_}
    (OUT / 'summary.json').write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding='utf-8')
    L = ['# 평가 실행 비교 요약', '', '| 실행 | 처리 문항 | 통과 | 미통과 | 주요 원인 |', '|---|---|---|---|---|']
    for r in summ['runs']:
        L.append(f"| {r['run']}{'' if r['complete'] else ' (진행 중)'} | {r['n']} | {r['n_pass']} | {r['n_fail']} | {', '.join(f'{k} {v}' for k, v in list(r['fail_by_cause'].items())[:5])} |")
    L += ['', '## 실행 간 통과 여부가 갈린 문항', '', '| 실행 A | 실행 B | 공통 문항 | 둘 다 통과 | 둘 다 미통과 | A만 통과 | B만 통과 |', '|---|---|---|---|---|---|---|']
    for c in cmp_:
        L.append(f"| {c['a']} | {c['b']} | {c['common']} | {c['both_pass']} | {c['both_fail']} | {len(c['only_a'])}: {', '.join(c['only_a'][:12])} | {len(c['only_b'])}: {', '.join(c['only_b'][:12])} |")
    (OUT / 'summary.md').write_text('\n'.join(L) + '\n', encoding='utf-8')
    for r in summ['runs']:
        print(f"{r['run']}: 처리 {r['n']} · 통과 {r['n_pass']} · 미통과 {r['n_fail']} · 원인 {r['fail_by_cause']}")
    print('→', OUT)


if __name__ == '__main__':
    main()
