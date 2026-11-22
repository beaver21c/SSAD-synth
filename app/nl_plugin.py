# -*- coding: utf-8 -*-
"""자연어 분석 결과를 OpenStat 결과 카드로 옮기는 분석 유형(nlQuery).

원본 시제품(원본/발표자료_행정데이터_AI/demo/nl_plugin.py)의 사본이며, 바꾼 곳은 언어모형 출처 표기(Gemini API)뿐이다.
app/run.py 가 실행 시점에 등록한다(OpenStat 의 plugins 폴더에 파일을 두지 않는다).
params 에는 뒷단 작업자(nl_worker.py)가 돌려준 결과가 그대로 들어 있으므로, 자료가 바뀌어 카드가 다시 계산될 때에도 언어모형을 다시 부르지 않는다.
명령 기록(왼쪽 아래 코드 창)에는 command_record() 가 만든 글, 곧 질문과 그 질문에서 언어모형이 작성해 실제로 실행한 분석 코드가 남는다."""
import re

from pyjamovi.analyses.base import BaseAnalysis, ResultsTable

PLUGIN_SPEC = {'id': 'nlQuery', 'group': '자연어 분석', 'title': '자연어 분석', 'module': 'openstat-nl', 'icon': 'brand-modules.svg', 'ui_schema': None}
META = ('값', '해당 인원', '대상 인원', '인원', '상태')
STORE = {}        # key → 뒷단 작업자의 결과(질문, 응답, 단계별 코드·실행 결과)
RECORD_HEAD = '자연어 명령: '
RECORD_NOTE = '# 언어모형이 작성한 분석 코드(실행 전 점검 → 격리 실행 → 출력 통제)'
_BLOCK = re.compile(r'^# \[\d+\] \S+ ' + re.escape(RECORD_HEAD) + r'(.*)$')
_ENTRY = re.compile(r'^# \[\d+\] ')


def one_line(q):
    return ' '.join((q or '').split())


def short_error(msg, n=70):
    """오류 문구의 첫 문장(단계 주석에 붙임)."""
    s = (msg or '').splitlines()[0] if msg else ''
    for cut in ('. ', ' / '):
        s = s.split(cut)[0]
    s = s.strip().rstrip('.')
    return s if len(s) <= n else s[:n - 1] + '…'


def command_record(title, params):
    """명령 기록에 남길 (제목, 코드) — 질문에서 언어모형이 작성해 실제로 실행한 분석 코드를 실행 순서대로 적는다.
    코드 없이 답한 질문은 주석 한 줄만 남긴다. 결과가 STORE 에 없으면 None(OpenStat 의 기본 기록 sess.run('nlQuery', …)이 남음)."""
    rec = STORE.get(params.get('key'))
    if not rec:
        return None
    head = RECORD_HEAD + one_line(params.get('question') or rec.get('question'))
    steps = [s for s in rec.get('steps') or [] if (s.get('code') or '').strip()]
    if not steps:
        final = rec.get('final') or ''
        why = '요청 처리 불가' if '요청 처리 불가' in final else '확인 필요(되물음)' if '확인 필요' in final else '코드 없는 응답'
        return head, '# 코드 실행 없음: ' + why
    many = len(steps) > 1
    out = [RECORD_NOTE + (f' · 총 {len(steps)}단계' if many else '')]
    for i, s in enumerate(steps, 1):
        state = '실행 전 점검 차단(실행 안 됨)' if s.get('blocked') else '실행 완료' if s.get('ok') else '실행 오류' + (f"({short_error(s['error'])})" if s.get('error') else '')
        if s.get('origin') == 'user':
            state = '질문에 제시된 코드 · ' + state
        if many or not s.get('ok') or s.get('origin') == 'user':
            out.append(('\n' if i > 1 else '') + (f'# 단계 {i}: ' if many else '# ') + state)
        code = s['code'].strip('\n')
        out.append('\n'.join('# ' + ln for ln in code.splitlines()) if s.get('blocked') else code)      # 차단된 코드는 실행되지 않았으므로 주석으로 남김
    return head, '\n'.join(out)


def key_of(question):
    """같은 질문의 가장 최근 결과 key."""
    q = one_line(question)
    return next((k for k in reversed(list(STORE)) if one_line(STORE[k].get('question')) == q), None)


def rerunnable(code):
    """코드 창에서 명령 기록을 다시 실행할 때 쓰는 변환 — 자연어 명령 구간의 분석 코드는 분석 지원기의 격리 실행 환경에서만 돌므로,
    그 구간을 저장된 결과를 다시 여는 sess.run('nlQuery', …) 호출로 바꾼다(저장된 결과가 없으면 주석 한 줄)."""
    if RECORD_HEAD not in code:
        return code
    out, skip = [], False
    for ln in code.split('\n'):
        m = _BLOCK.match(ln)
        if m:
            key = key_of(m.group(1))
            out += [ln, f"res = sess.run('nlQuery', question={STORE[key].get('question')!r}, key={key!r})" if key else '# 저장된 결과 없음: 자연어 명령 입력 줄에서 재실행 필요']
            skip = True
        elif skip and not _ENTRY.match(ln):
            continue
        else:
            skip = False
            out.append(ln)
    return '\n'.join(out)


def term(x):
    """화면 표기: 출력 통제로 값을 내지 않은 칸은 「마킹」으로 표시(2026-11-21 발표자료 용어). 분석 함수의 상태값은 그대로 둠."""
    return x.replace('억제', '마킹') if isinstance(x, str) else x


def fmt(v, unit=''):
    if v is None:
        return ''
    if isinstance(v, (int, float)):
        return f'{v:,.1f}' if unit == '%' or (abs(v) < 1000 and float(v) != int(v)) else f'{v:,.0f}'
    return str(v)


def cell(rec, unit):
    return fmt(rec.get('값'), unit) if rec.get('값') is not None and rec.get('상태', '표시') == '표시' else term(rec.get('상태') or '억제')


def table_of(key, res, k):
    s, recs = res.get('summary') or {}, res.get('records') or []
    shown = [r for r in recs if r.get('상태') != '대상 없음']          # 대상 집단 밖의 구간(대상 없음)은 표에서 뺌
    recs = shown or recs
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
    n_sup = sum(1 for r in recs if r.get('상태') in ('억제', '보충 억제'))
    t.add_note(f"민감도 등급 {s.get('등급', '')} · 최소 관측 수 {s.get('최소 관측 수', '')}건 · 마킹된 칸 {n_sup}개" + (' (마킹: 최소 관측 수 미달, 보충 마킹: 역산 방지)' if n_sup else ''))
    return t


def run_plugin(df, params):
    params = {**(STORE.get(params.get('key')) or {}), **params}
    q = params.get('question', '')
    a = BaseAnalysis('nlQuery', '자연어 분석 · ' + term(q if len(q) <= 64 else q[:62] + '…'), None, {'question': q})
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
        ans.add_row({'part': term(part), 'text': term(line.lstrip('-·• ').strip())})
        part = ''
    for line in (params.get('footer') or '').splitlines()[1:]:
        ans.add_note('[자동 점검] ' + term(line.lstrip('- ').strip()))
    src = params.get('replay_source')
    ran = bool(steps)                                    # 되묻기·거절처럼 코드를 쓰지 않은 응답은 실행·수치 안내를 붙이지 않음
    ans.add_note('언어모형 응답: ' + ((f"평가 실행 기록의 응답을 재생함({src['run']} {src['id']})" + ('. 코드는 지금 다시 실행함' if ran else '')) if src else f"Gemini API({params.get('model') or '모형 미상'})")
                 + (' · 수치는 가상데이터(확대 생성본)의 가중 집계값이며 실제 현황이 아님' if ran else ' · 코드를 실행하지 않은 응답임(산출값 없음)'))
    if last:
        for k, (key, res) in enumerate(last['results'].items()):
            a.add_table(table_of(key, res, k))
    a.add_table(ans)
    for s in steps:
        for f in s.get('figures') or []:
            a.plots.append({'title': f.get('name', '그림'), 'src': f['src'], 'style': {}}); a.plot_vectors.append({})
    code = (last or (steps[-1] if steps else {})).get('code', '')
    a.syntax_python = ('# 자연어 명령: ' + term(q) + '\n' + code) if code else '# 자연어 명령: ' + term(q)
    a.apa_narrative = ''
    a.references = ['분석 함수 묶음 ssda(집계 전용, 출력 통제 내장) · 실행 전 점검과 격리 실행을 거친 코드의 결과임', 'OpenStat Studio v3.0 (MIT License)']
    return a
