#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""규칙 묶음 11(5차 개발 측정 뒤의 보완)의 자체 시험 — 규칙 묶음 10에서는 동작이 바뀌지 않는지와 11에서 보완이 작동하는지를 본다.

  SSDA_DATA=… python 06_build/v11_probe.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '02_library')); sys.path.insert(0, str(ROOT / '06_build'))
from ssda import verify  # noqa: E402

R = []


def t(name, cond):
    R.append((name, bool(cond)))


def rs(n):
    os.environ['SSDA_RULESET'] = str(n)


rs(10); e10 = verify.unseen_error(['bp_type']); off = not verify.v11()
rs(11); e11 = verify.unseen_error(['bp_type'])
t('10: 코드값 없음(기존 동작)', '코드값' not in e10 and off)
t('11: v11() 켜짐', verify.v11() and verify.v10() and verify.v9())
t('11: 코드값을 함께 알림', '코드값' in e11 and '=' in e11.split('코드값')[1][:20] and '대조' in e11)
t('11: 코드값이 없는 변수는 이름만', '코드값' not in verify.unseen_error(['p_dinc']).split('/')[0])

if os.environ.get('SSDA_DATA'):
    from assistant import Assistant, load_config  # noqa: E402
    from retriever import Retriever  # noqa: E402

    class Script:
        def __init__(self, replies):
            self.replies, self.usage = list(replies), {}

        def chat(self, messages):
            return self.replies.pop(0) if self.replies else '**결과**\n- 확인함'

    def make(n, replies):
        cfg = load_config(); cfg['verify']['ruleset'] = n; cfg['prompt']['n_examples'] = 0
        cfg['paths'].update(export='/tmp/v11p_export', log='/tmp/v11p_log.jsonl', transcripts='/tmp/v11p_tr.jsonl')
        return Assistant(cfg, Script(replies), Retriever())
    # 닫히지 않은 코드 블록
    open_reply = "**분석 계획**\n- 65세 이상 인원\n\n```python\nimport ssda\nprint(ssda.count(where='age >= 65'))\n"
    for n in (10, 11):
        a = make(n, [open_reply, '**결과**\n- 표와 같음\n\n**유의 사항**\n- 없음'])
        rec = a.ask('65세 이상 인구가 몇 명인지 알려 주세요.')
        ran = any(s.get('ok') for s in rec['steps'])
        t(f'{n}: 닫히지 않은 코드 블록 ' + ('실행 안 함(기존 동작)' if n == 10 else '실행함'), ran == (n == 11))
        a.close()
    # 금액 근거의 출처: 앞선 실행 결과의 수치(만원 단위 120)가 근거로 쓰이는지
    code = "```python\nimport ssda\nprint(ssda.count(where='youthemp_amt1 >= 1200000'))\n```"
    for n in (10, 11):
        a = make(n, [code, code, '**결과**\n- 표와 같음\n\n**유의 사항**\n- 없음'])
        a.seen.add('youthemp_amt1')                 # 변수 정의는 본 것으로 둠(정의 미확인 변수의 실행 전 확인과 구분)
        a.messages.append({'role': 'user', 'content': '[실행 결과]\n[청년내일채움공제 청년적립금 평균] 단위: 만원\n  값\n 120'})
        a.messages.append({'role': 'assistant', 'content': '**결과**\n- 120만원'})
        rec = a.ask('청년공제는 2년 만기를 채우면 1,200만원을 받습니다. 지급액이 1,200만원 이상인 사람은 몇 명입니까?')
        held = bool(rec['steps']) and bool(rec['steps'][0].get('held'))
        t(f'{n}: 실행 결과의 수치를 근거로 ' + ('인정(기존 동작)' if n == 10 else '보지 않음 → 돌려보냄'), held == (n == 11))
        a.close()

bad = [n for n, ok in R if not ok]
for n in bad:
    print('실패:', n)
print(f'규칙 묶음 11 자체 시험 {len(R) - len(bad)}/{len(R)}')
sys.exit(1 if bad else 0)
