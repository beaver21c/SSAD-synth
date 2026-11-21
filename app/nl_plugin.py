# -*- coding: utf-8 -*-
"""자연어 분석 결과를 OpenStat 결과 카드로 옮기는 분석 유형(nlQuery).

원본 시제품(발표자료_행정데이터_AI/demo/nl_plugin.py)을 옮겨 온 것이며, 바꾼 곳은 언어모형 출처 표기뿐이다.
params 에는 뒷단이 돌려준 결과가 그대로 들어 있으므로, 카드가 다시 계산될 때에도 언어모형을 다시 부르지 않는다."""
from pyjamovi.analyses.base import BaseAnalysis, ResultsTable

PLUGIN_SPEC = {'id': 'nlQuery', 'group': '자연어 분석', 'title': '자연어 분석', 'module': 'openstat-nl', 'icon': 'brand-modules.svg', 'ui_schema': None}
META = ('값', '해당 인원', '대상 인원', '인원', '상태')


def fmt(v, unit=''):
    if v is None:
        return ''
    if isinstance(v, (int, float)):
        return f'{v:,.1f}' if unit == '%' or (abs(v) < 1000 and float(v) != int(v)) else f'{v:,.0f}'
    return str(v)


def cell(rec, unit):
    return fmt(rec.get('값'), unit) if rec.get('값') is not None and rec.get('상태', '표시') == '표시' else (rec.get('상태') or '억제')


def table_of(key, res, k):
    s, recs = res.get('summary') or {}, res.get('records') or []
    unit = s.get('단위', '')
    title = f"{s.get('지표', key)} (단위: {unit}, 가중 추정값)"
    labs = [c for c in (recs[0].keys() if recs else []) if c not in META]
    t = ResultsTable(f'nl{k}', title)
    if len(labs) == 2:                                   # 분류 기준 2개 → 행 × 열 교차표
        a, b = labs
        rows = list(dict.fromkeys(r[a] for r in recs)); cols = list(dict.fromkeys(r[b] for r in recs))
        t.add_column('row', a, 'text')
        for j, c in enumerate(cols):
            t.add_column(f'c{j}', str(c), 'text', super_title=b)
        for rv in rows:
            row = {'row': str(rv)}
            for j, c in enumerate(cols):
                hit = next((r for r in recs if r[a] == rv and r[b] == c), None)
                row[f'c{j}'] = cell(hit, unit) if hit else ''
            t.add_row(row)
    else:
        for c in labs:
            t.add_column(c, c, 'text')
        t.add_column('값', f'값({unit})' if unit else '값', 'text')
        extra = [c for c in ('해당 인원', '대상 인원', '인원') if any(c in r for r in recs)]
        for c in extra:
            t.add_column(c, c, 'text')
        for r in recs:
            row = {c: str(r.get(c, '')) for c in labs}
            row['값'] = cell(r, unit)
            shown = r.get('상태', '표시') == '표시'
            for c in extra:
                row[c] = fmt(r.get(c)) if shown else ''
            t.add_row(row)
    n_sup = s.get('표시하지 않는 칸', 0)
    t.add_note(f"민감도 등급 {s.get('등급', '')} · 최소 관측 수 {s.get('최소 관측 수', '')}건 · 표시하지 않는 칸 {n_sup}개" + (' (억제: 최소 관측 수 미달, 보충 억제: 역산 방지)' if n_sup else ''))
    return t


def run_plugin(df, params):
    q = params.get('question', '')
    a = BaseAnalysis('nlQuery', '자연어 분석 · ' + (q if len(q) <= 64 else q[:62] + '…'), None, {'question': q})
    steps = params.get('steps') or []
    ok = [s for s in steps if s.get('ok') and s.get('results')]
    last = ok[-1] if ok else None
    ans = ResultsTable('answer', '응답')
    ans.add_column('part', '구분', 'text'); ans.add_column('text', '내용', 'text')
    part = ''
    for line in (params.get('final') or '').splitlines():
        line = line.strip()
        if not line:
            continue
        if not line.startswith(('-', '·', '•')) and len(line) <= 12:
            part = line.strip('#* ')
            continue
        ans.add_row({'part': part, 'text': line.lstrip('-·• ').strip()})
        part = ''
    for line in (params.get('footer') or '').splitlines()[1:]:
        ans.add_note('[자동 점검] ' + line.lstrip('- ').strip())
    ans.add_note(f"언어모형 응답: Gemini API({params.get('model') or '모형 미상'}) · 수치는 가상데이터(확대 생성본)의 가중 집계값이며 실제 현황이 아님")
    if last:
        for k, (key, res) in enumerate(last['results'].items()):
            a.add_table(table_of(key, res, k))
    a.add_table(ans)
    for s in steps:
        for f in s.get('figures') or []:
            a.plots.append({'title': f.get('name', '그림'), 'src': f['src'], 'style': {}}); a.plot_vectors.append({})
    code = (last or (steps[-1] if steps else {})).get('code', '')
    a.syntax_python = ('# 자연어 명령: ' + q + '\n' + code) if code else '# 자연어 명령: ' + q
    a.apa_narrative = params.get('final') or ''
    a.references = ['분석 함수 묶음 ssda(집계 전용, 출력 통제 내장) · 실행 전 점검과 격리 실행을 거친 코드의 결과임', 'OpenStat Studio v3.0 (MIT License)']
    return a
