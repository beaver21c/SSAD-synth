#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""학습 자료 검증기 — 생성된 대화 예시 전체를 다시 점검한다.

  V1 형식        역할 순서(system → user → assistant …), 빈 내용 없음, 마지막은 assistant
  V2 코드 점검    assistant 의 모든 코드 블록이 ssda.guard 를 통과(오류 수정 유형의 user 쪽 잘못된 코드는 제외)
  V3 재실행 일치  assistant 코드를 다시 실행한 표준 출력이 대화에 적힌 [실행 결과]와 같음
  V4 금지 내용    절대 경로, 식별자 변수(pid·hid) 사용 코드, 개인 행 출력 함수가 assistant 코드에 없음
  V5 분할 누출    평가 전용 지표의 변수가 train·valid 의 assistant 코드에 없음
  V6 문장 점검    조사·표기 오류 패턴(「만원로」 등)과 같은 항목을 최고·최저로 함께 적은 문장이 없음
  V7 수치 대조    응답 「결과」의 수치가 모두 실행 결과·검증 결과·질문·코드에 있는 값임(조립기와 같은 함수 ssda.verify.answer_issues)
  V8 변수 근거    코드가 쓴 변수가 모두 변수 사전에 있고, 그 대화의 참고 자료·질문·앞선 실행 결과에서 정의를 본 변수임
  V9 잔존 경고    마지막 실행의 「[검증 결과]」에 경고가 남아 있지 않음
  V10 요청 반영   질문에 적힌 조건(연령·성·가구원수·소득 분위·지역·가구 단위·그림·저장)이 마지막 코드에 반영돼 있음
  V11 용어 확인   되물어야 하는 제도 용어(내역이 정해지지 않은 「국기초」「본인부담금」 등)가 있는 질문에서 되묻지 않고 코드를 실행한 예시가 없음

실행  PYTHONPATH=02_library SSDA_DATA=<대역 자료> .venv/bin/python 04_training/validate.py
출력  04_training/data/validation_report.json (위반 0건이면 통과)
"""
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '02_library')); sys.path.insert(0, str(ROOT / '06_build'))
os.environ['SSDA_EXPORT'] = tempfile.mkdtemp(prefix='ssda_val_')
import ssda  # noqa: E402
from ssda import guard, runner, verify  # noqa: E402
from terms import Glossary  # noqa: E402

DATA = ROOT / '04_training' / 'data'
HELD_VARS = ['oldwork_type1_yn1', 'evou_yn', 'culvou_yn', 'vocaedu_yn', 'nhi_ceiling_subsidy_yn']
CODE = re.compile(r'```python\n(.*?)\n```', re.S)
BAD_TEXT = [r'만원로', r'없음임', r'이상로', r'미만로', r'종별별', r'/tmp/', r'/mnt/', r'(?<![^\s])(\S+)에서 [\d.,]+\S* 가장 높고 \1에서', r'None', r'nan%']


def norm(t):
    return re.sub(r'\s+', ' ', re.sub(r'export/\S+\.(png|csv)', 'export/FILE', t)).strip()


def main():
    ssda.open_data()
    TERMS = Glossary()
    rows = [dict(json.loads(l), _split=sp) for sp in ('train', 'valid', 'test') for l in (DATA / f'{sp}.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    bad = Counter(); detail = []
    n_code = n_rerun = n_answer = 0

    def flag(kind, r, msg):
        bad[kind] += 1
        if len(detail) < 60:
            detail.append({'check': kind, 'id': r['id'], 'family': r['family'], 'msg': msg[:300]})

    for r in rows:
        ms = r['messages']
        roles = [m['role'] for m in ms]
        if roles[0] != 'system' or roles[-1] != 'assistant' or any(not m['content'].strip() for m in ms) or any(a == b for a, b in zip(roles[1:], roles[2:])):
            flag('V1', r, '역할 순서 또는 빈 내용: ' + ' '.join(roles))
        tr, pending, ran = None, [], False                    # 조립기와 같은 순서로 용어 해석 상태를 따라감
        for i, m in enumerate(ms):
            if m['role'] == 'user' and '[질문]' in m['content']:
                if tr is not None:
                    pending = [u for u in tr['unresolved'] if u['policy'] in ('ask', 'absent')] if not ran else []
                tr = TERMS.resolve(m['content'].split('[질문]')[-1].strip(), pending); ran = False
            if m['role'] != 'assistant':
                continue
            for pat in BAD_TEXT:
                if re.search(pat, CODE.sub('', m['content'])):
                    flag('V6', r, f'문장 패턴 {pat}: ' + m['content'][:120])
            for code in CODE.findall(m['content']):
                n_code += 1
                v = guard.check(code)
                if v:
                    flag('V2', r, '; '.join(v))
                if re.search(r"\b(pid|hid)\b", code) or re.search(r'\.(head|tail|sample|iloc|loc)\b', code):
                    flag('V4', r, '식별자·개인 행 접근 코드')
                if r['_split'] != 'test' and any(h in code for h in HELD_VARS):
                    flag('V5', r, '평가 전용 변수가 학습·검증 자료에 있음')
                nxt = ms[i + 1]['content'] if i + 1 < len(ms) else ''
                seen = verify.names_in('\n'.join(x['content'] for x in ms[1:i] if x['role'] == 'user'))
                pre = verify.lint_code(code, seen)
                if pre['unknown'] or pre['empty'] or pre['unseen']:
                    flag('V8', r, f"없는 변수 {list(pre['unknown'])} · 값 없는 변수 {pre['empty']} · 정의를 보지 않은 변수 {pre['unseen']}")
                if nxt.startswith('[실행 결과]'):
                    out = runner.run(code, limits=False); n_rerun += 1; ran = True
                    req = Glossary.check(tr['unresolved'], pre['used']) if tr else []
                    if any(x['level'] == '주의' for x in req) and r['family'] not in ('F18', 'F19', 'F20', 'F27'):
                        flag('V11', r, req[0]['msg'][:160])
                    got = norm(verify.tool_message(out, None, os.environ['SSDA_EXPORT'], req=req if out['ok'] else None))
                    exp = norm(nxt)
                    if not out['ok'] or got != exp:
                        flag('V3', r, f"ok={out['ok']} / 기록 {exp[:120]} / 재실행 {got[:120]} {out['error'][:80]}")
        # V7 수치 대조: 실행 결과 뒤에 오는 응답마다 조립기와 같은 기준으로 점검
        codes = [c for m in ms if m['role'] == 'assistant' for c in CODE.findall(m['content'])]
        for i, m in enumerate(ms):
            if m['role'] == 'assistant' and i >= 2 and '결과' in m['content'] and not CODE.search(m['content']) and (ms[i - 1]['content'].startswith('[실행 결과]') or r['family'] == 'F23'):
                n_answer += 1
                iss = verify.answer_issues(m['content'], verify.answer_sources(ms[1:i], codes))
                if any(x['code'] == '수치 대조' for x in iss):
                    flag('V7', r, next(x['msg'] for x in iss if x['code'] == '수치 대조') + ' / ' + verify.result_part(m['content'])[:160])
        qs = [(i, m['content'].split('[질문]')[-1]) for i, m in enumerate(ms) if m['role'] == 'user' and '[질문]' in m['content']]
        for k, (qi, qtext) in enumerate(qs):                  # 질문마다 그 질문에 답한 마지막 코드를 대조
            end = qs[k + 1][0] if k + 1 < len(qs) else len(ms)
            cs = [c for m in ms[qi:end] if m['role'] == 'assistant' for c in CODE.findall(m['content'])]
            if cs and r['family'] not in ('F19', 'F20'):      # 통제 대처·거절 유형은 요청을 그대로 수행하지 않는 것이 정답
                for it in verify.check_request(qtext, cs[-1]):
                    flag('V10', r, it['msg'] + ' / ' + qtext.strip()[:80])
        tools = [m['content'] for m in ms if m['role'] == 'user' and m['content'].startswith('[실행 결과]')]
        if tools and '경고(' in tools[-1]:
            flag('V9', r, tools[-1][-200:])
        # 평가 전용 지표가 질문에만 있어도 학습 자료에서 제외되는지
        if r['_split'] != 'test' and r['meta'].get('held'):
            flag('V5', r, '평가 전용 표시 예시가 학습·검증 자료에 있음')
    q = Counter(m['content'].split('[질문]')[-1].strip() for r in rows for m in r['messages'][1:2])
    dup = sum(c - 1 for c in q.values() if c > 1)
    rep = {'rows': len(rows), 'split': dict(Counter(r['_split'] for r in rows)), 'code_blocks': n_code, 'rerun': n_rerun, 'answers_checked': n_answer, 'violations': dict(bad), 'duplicate_first_questions': dup, 'detail': detail,
           'passed': not bad}
    (DATA / 'validation_report.json').write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: v for k, v in rep.items() if k != 'detail'}, ensure_ascii=False))
    for d in detail[:25]:
        print(' ', d)
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
