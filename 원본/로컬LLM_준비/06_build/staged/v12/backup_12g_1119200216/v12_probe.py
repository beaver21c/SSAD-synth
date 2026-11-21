#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""규칙 묶음 12(6차 판정·규칙 묶음 11 개발 측정 뒤의 보완)의 자체 시험 — 규칙 묶음 11에서는 동작이 바뀌지 않는지와 12에서 보완이 작동하는지를 본다.

  SSDA_DATA=… python 06_build/v12_probe.py
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


Q_DIGIT = '청년공제는 2년 만기를 채우면 1,200만원(청년 300만원, 기업 300만원, 정부 600만원)을 받습니다. 세전 지급액이 1,200만원 이상인 사람은 몇 명입니까?'
C_DIGIT = "r = ssda.count(where='youthemp_amt1 > 0 and youthemp_amt1 >= 1200000')"
C_DIGIT_OK = "r = ssda.count(where='youthemp_amt1 >= 12000000')"
Q_MON = '12월 말 기준 산정보험료(월액)가 19,500원 이하인 지역가입자 세대주는 몇 명입니까?'
C_MON = "r = ssda.rate('(nhi_premium_cal / 12) <= 19500', where='nhi_type == 1')"
Q_PP = '지역가입자 세대주가 2022년에 낸 건강보험료 연간 합계의 1인당 평균을 가구원수별로 보여 주세요.'
C_PP = "ssda.define('pp', 'nhi_premium_amt3_y / hnum')\nr = ssda.mean('pp', where='nhi_type == 1', by='hs4')"
DOC = ('국회 요구자료\n2. 요구 사항\n ① 2022년 기초연금을 한 번이라도 받은 65세 이상 수급자 수를 시도별로 제출\n ② 12월 기준 수급유형(단독, 부부 1인, 부부 2인)별 구성비\n'
       ' ③ 노인맞춤돌봄서비스 이용자 수\n ④ 국민취업지원제도 구직촉진수당 수급자 수')

# ── 규칙 묶음 11: 바뀌지 않음 ──
rs(11)
t('11: v12() 꺼짐', not verify.v12() and verify.v11())
t('11: 금액 자릿수 점검 없음', not any('자릿수' in i['msg'] for i in verify.check_request(Q_DIGIT, C_DIGIT, doc='')))
t('11: 월액 점검 없음', not any('한 달의 금액' in i['msg'] for i in verify.check_request(Q_MON, C_MON)))
t('11: 정의 미확인 안내는 기존 문구', '되묻지 말고' not in verify.unseen_error(['bp_type']))
# ── 규칙 묶음 12 ──
rs(12)
t('12: v12() 켜짐(9~11 포함)', verify.v12() and verify.v11() and verify.v10() and verify.v9())
t('12: 1,200만원 → 1200000 돌려보냄', any('자릿수' in i['msg'] and i.get('target') for i in verify.check_request(Q_DIGIT, C_DIGIT)))
t('12: 1,200만원 → 12000000 은 통과', not any('자릿수' in i['msg'] for i in verify.check_request(Q_DIGIT, C_DIGIT_OK)))
t('12: 붙임 문서의 금액도 대조', any('자릿수' in i['msg'] for i in verify.check_request('세전 지급액 기준 인원을 내 주세요.', C_DIGIT, doc='만기 지급액은 1,200만원임')))
t('12: 월액 변수를 12로 나눔 → 돌려보냄', any('한 달의 금액' in i['msg'] and i.get('target') for i in verify.check_request(Q_MON, C_MON)))
t('12: 연간 합계 변수를 12로 나눔은 통과', not any('한 달의 금액' in i['msg'] for i in verify.check_request('연간 보험료의 월평균', "ssda.define('m', 'nhi_premium_amt3_y / 12')")))
t('12: 「1인당」을 가구원 수로 나눔 → 돌려보냄', any('1인당' in i['msg'] and i.get('target') for i in verify.check_request(Q_PP, C_PP)))
t('12: 「가구원 1인당」은 통과', not any('가구원 수(hnum)로 나누지' in i['msg'] for i in verify.check_request('가구원 1인당 보험료 평균', C_PP)))
t('12: 정의 미확인 안내에 되묻기 방지', '되묻지 말고' in verify.unseen_error(['bp_type']))
t('12: 번호 붙은 항목 수(절 번호 포함)', verify.multi_items(DOC) >= 4 and verify.multi_items('기초연금 수급률을 알려 주세요.') == 0)
card = verify.program_vars_card(DOC, ['bp', 'oldcare', 'kua'])
t('12: 제도별 변수 목록에 기초연금 여부·유형 변수', all(v in card for v in ('bp_yn1', 'bp_yn2', 'bp_type')))
t('12: 제도별 변수 목록에 국민취업지원제도 변수', 'kua_' in card)
t('12: 여러 항목 관문 문구', '산출할 수 있는 항목은 모두 산출' in verify.multi_gate_note())
C_KUA = "r = ssda.total('kua_employmentbn_amt', where='kua_yn1 == 1')"
t('12: 이름 일부만 같은 다른 급여로 대체 → 돌려보냄', any('이름이 다른 제도·급여' in i['msg'] and i.get('target') for i in verify.check_request('2022년 신설된 조기취업성공수당 지급 총액', C_KUA)))
t('12: 같은 급여 이름은 통과', not any('이름이 다른' in i['msg'] for i in verify.check_request('국민취업지원제도 취업성공수당 지급 총액', C_KUA)))
t('12: 용어 사전의 이름(가정양육수당)은 통과', not any('이름이 다른' in i['msg'] for i in verify.check_request('가정양육수당 수급 아동 수', "r = ssda.count(where='carebn_yn1 == 1')")))
t('12: 전국 값과 시도별 → 분류별만이면 돌려보냄', any('전국(전체) 값' in i['msg'] and i.get('target') for i in verify.check_request('전국에 몇 명인지, 시도별로는 몇 명인지', "r = ssda.count(where='nhi_type in [1, 2]', by='sido')")))
t('12: 전국 값도 실행하면 통과', not any('전국(전체) 값' in i['msg'] for i in verify.check_request('전국에 몇 명인지, 시도별로는 몇 명인지', "a = ssda.count(where='nhi_type in [1, 2]')\nb = ssda.count(where='nhi_type in [1, 2]', by='sido')")))
t('12: 「몇 세대」를 개인 단위로 셈 → 돌려보냄', any("unit='가구'" in i['msg'] and i.get('target') for i in verify.check_request('이용 세대 가운데 몇 세대입니까?', "r = ssda.count(where='evou_yn == 1')")))
t('12: 가구 단위면 통과', not any("세대(가구) 수" in i['msg'] for i in verify.check_request('몇 세대입니까?', "r = ssda.count(where='evou_yn == 1', unit='가구')")))
t('12: 가구원 수는 대상 아님', not any("세대(가구) 수" in i['msg'] for i in verify.check_request('평균 가구원 수', "r = ssda.mean('hnum')")))
# 12c: 자료에 없는 사업의 용어 사전 항목, 사전에 없는 이름 안내의 근거 요건
from terms import Glossary  # noqa: E402
G = Glossary()
rd = G.resolve('재난적의료비 지원사업 실적을 소득 분위별로 뽑아 주세요.', [], [])
t('12: 재난적의료비 → 자료에 없는 항목(본인부담상한제는 다른 제도)', any(u['policy'] == 'absent' for u in rd['unresolved']) and any('다른 제도' in n for n in rd['notes']))
t('12: 조기취업성공수당 → 자료에 없는 항목', any(u['policy'] == 'absent' for u in G.resolve('조기취업성공수당 지급 인원', [], [])['unresolved']))
t('12: 주택담보노후연금 → 주택연금으로 풀이', any(m['id'] == 'rm' for m in G.resolve('주택담보노후연금 가입자 수', [], [])['matches']))
nu = G.resolve('청년마음건강바우처 이용자 수', [], [])['notes']
t('12: 사전에 없는 이름 안내에 근거 요건', any('근거가' in n and '비슷하다는 이유만으로' in n for n in nu))
rs(11)
t('11: 사전에 없는 이름 안내는 기존 문구', not any('비슷하다는 이유만으로' in n for n in Glossary().resolve('청년마음건강바우처 이용자 수', [], [])['notes']))
rs(12)

if os.environ.get('SSDA_DATA'):
    import ssda  # noqa: E402
    rs(11); f11 = ssda.find_vars('균등화', top=5)
    rs(12); f12 = ssda.find_vars('균등화', top=5)
    t('11: 변수 찾기에 표준 분류 없음', f11.empty or 'inc5' not in set(f11['변수명']))
    t('12: 「균등화」로 inc5 를 찾음', not f12.empty and 'inc5' in set(f12['변수명']))
    # 12b(2026-11-19 개발 측정 1회차의 원인): 소수 집단 표 전체 억제, 점검 줄의 차분 점검
    from ssda import core  # noqa: E402
    rs(11); s11 = list(core.count(where='unempbn_jobseekbn_type == 4', by='sido').table()['상태'])
    rs(12); s12 = list(core.count(where='unempbn_jobseekbn_type == 4', by='sido').table()['상태'])
    t('11: 소수 집단 시도별 표에 「대상 없음」이 섞임(기존 동작)', '대상 없음' in s11)
    t('12: 소수 집단 시도별 표는 모두 억제', set(s12) == {'억제'})
    t('12: 일반 표는 그대로 표시', '표시' in set(core.count(where='bp_yn1 == 1', by='sido').table()['상태']))
    ov = {}
    for n in ('11', '12'):
        rs(n); core.session_start([])
        core.mean('bp_amt', where='age >= 65 and bp_yn1 == 1')
        b = core.mean('bp_amt', where="(age >= 65 and bp_yn1 == 1) or (age == 64 and sido == '세종')", by='sex')
        ov[n] = [c for c in verify.check_result(b) if c['code'] == '전체 값']
        core.session_stop()
    t('11: 점검 줄이 보충 억제된 전체 값을 보임(기존 동작)', bool(ov['11']))
    t('12: 점검 줄도 차분 점검을 거침', not ov['12'])
    rs(12)

    from assistant import Assistant, load_config  # noqa: E402
    from retriever import Retriever  # noqa: E402

    class Script:
        def __init__(self, replies):
            self.replies, self.usage, self.seen = list(replies), {}, []

        def chat(self, messages):
            self.seen.append([dict(m) for m in messages])
            return self.replies.pop(0) if self.replies else '**결과**\n- 확인함'

    def make(n, replies, ctx_tokens=None):
        cfg = load_config(); cfg['verify']['ruleset'] = n; cfg['prompt']['n_examples'] = 0
        if ctx_tokens:
            cfg['model']['context_tokens'] = ctx_tokens
        cfg['paths'].update(export='/tmp/v12p_export', log='/tmp/v12p_log.jsonl', transcripts='/tmp/v12p_tr.jsonl')
        sc = Script(replies)
        return Assistant(cfg, sc, Retriever()), sc

    refuse = '**요청 처리 불가**\n- [참고 자료]에 기초연금 변수가 없음. 자료에 없는 항목임'
    for n in (11, 12):
        a, sc = make(n, [refuse, refuse, refuse, '**결과**\n- 끝'])
        rec = a.ask('붙임 요구 사항 ①~④를 2022년 자료로 작성해 주세요.', extra_context='■ 붙임 문서\n' + DOC)
        first = sc.seen[0][1]['content']
        if n == 11:
            t('11: 붙임 문서는 참고 자료 안(기존 동작)', '[붙임 문서]' not in first and '기초연금' in first and not (rec.get('hooks') or {}).get('multi'))
        else:
            t('12: 붙임 문서는 별도 블록', '[붙임 문서]' in first and first.index('[붙임 문서]') < first.index('[질문]'))
            t('12: 제도별 변수 목록이 참고 자료에 붙음', '붙임 문서의 제도와 변수' in first and 'bp_yn1' in first)
            t('12: 여러 항목 요청의 일괄 거절 → 한 번 돌려보냄', (rec.get('hooks') or {}).get('multi') == 1)
            t('12: 실행 횟수 한도 +2', a.multi)
        a.close()
    # 문맥 한도 처리: 이번 질문 메시지를 지우지 않음
    big = 'x' * 6000
    code = "```python\nimport ssda\nprint(ssda.count(where='age >= 65'))\n```"
    for n in (11, 12):
        a, sc = make(n, [code + '\n' + big, code.replace('65', '64') + '\n' + big, code.replace('65', '66') + '\n' + big, '**결과**\n- 끝'], ctx_tokens=8000)
        rec = a.ask('65세 이상 인구가 몇 명인지 알려 주세요.')
        last = sc.seen[-1]
        kept = any(m['role'] == 'user' and '[질문]' in m['content'] and '65세 이상 인구' in m['content'] for m in last)
        t(f'{n}: 한도를 넘을 때 이번 질문 메시지 ' + ('지워짐(기존 동작)' if n == 11 else '남음'), kept == (n == 12))
        a.close()

    # ── 규칙 묶음 12d(최종판 개발 측정의 오답 원인) ──
    from ssda import core
    DOC1 = '■ 작성 항목\n3) 1인 가구 가운데 월평균 가처분소득이 583,444원 이하인 가구의 비율'
    C1 = "r = ssda.rate('h_dinc / 12 <= 583444', where='hnum == 1', unit='가구')"
    Q_NP = '2022년 말 국민연금 사업장가입자 중 기준소득월액이 230만원 미만인 사람 가운데 국민연금 보험료 지원을 받은 사람의 비율은?'
    ABS = '**결과**\n- 63.7%\n\n**유의 사항**\n- 사업소득(`p_binc`)으로 해석함. 위탁·도급 여부나 원천징수 여부는 별도로 구분되지 않음'
    for n in (11, 12):
        rs(n)
        hold = lambda q, c, doc='': [i['msg'] for i in verify.check_request(q, c, doc=doc) if i.get('target')]
        tag = f'{n}: ' if n == 11 else '12d: '
        t(tag + '붙임 문서의 1인 가구 조건 ' + ('돌려보냄(기존 동작)' if n == 11 else '인정'), any('1인 가구를 가리키는 말이 없음' in x for x in hold('붙임 문서의 항목을 산출해 주세요.', C1, DOC1)) == (n == 11))
        t(tag + '연액 변수 ×12 점검 ' + ('없음' if n == 11 else '작동'), any('1년 동안의 금액' in x for x in hold('선정기준 이하 가구 수', "r = ssda.count(where='h_oinc * 12 <= 9335100', unit='가구')")) == (n == 12))
        t(tag + '「납부예외」에 상실 코드 점검 ' + ('없음' if n == 11 else '작동'), any('np_status == 3' in x for x in hold('납부예외자를 연령 구간별로', "r = ssda.count(where='np_status == 2', by='age3')")) == (n == 12))
        t(tag + '「사업장가입자 중」 가입종별 조건 점검 ' + ('없음' if n == 11 else '작동'), any('np_type == 0' in x for x in hold(Q_NP, "r = ssda.rate('np_support_yn1 == 1', where='np_yn == 1 and np_inc_amt < 2300000')")) == (n == 12))
        t(tag + '맞는 코드에는 점검 없음', not hold(Q_NP, "r = ssda.rate('np_support_yn1 == 1', where='np_type == 0 and np_inc_amt < 2300000')") and not hold('납부예외자 수', "r = ssda.count(where='np_status == 3')"))
        try:
            core.define_group('a01', 'age', [0, 1, 2], ['0세', '1세', '2세 이상']); e = ''
        except Exception as ex:
            e = str(ex)
        t(tag + '구간 이름 개수 오류의 경계 제안 ' + ('없음' if n == 11 else '작동'), ('bins=[1, 2]' in e) == (n == 12))
        fl = ' '.join(verify.fact_lines('itc'))
        if n == 12:
            t('12d: 기준값 카드에 귀속·지급 연도와 2021년 귀속분', '2021년 귀속·2022년 지급' in fl and '200,000,000원' in fl and '2023-01-01 시행' in fl)
            t('12d: 「자료에 없음」 진술 점검(원천징수·일용소득) 작동, 일반 낱말·자료에 없는 제도는 보지 않음',
              verify.absent_claims(ABS, {'p_binc'}) and verify.absent_claims('「일용소득」에 해당하는 변수가 없음', set())
              and not verify.absent_claims('월별 보험료 자료가 없어 비교할 수 없음', set()) and not verify.absent_claims('「조기취업성공수당」 변수가 자료에 없음', set())
              and not verify.absent_claims('적용 여부나 지급액 변수가 자료에 없음', set()))
        code = "```python\nimport ssda\nprint(ssda.rate('empins_yn1 == 1', where='p_binc > 0', by='sex'))\n```"
        a, sc = make(n, ([code] if n == 12 else []) + [code, ABS, '**결과**\n- 끝'])      # 12f: ⑨(더 맞는 이름의 변수)가 첫 코드를 돌려보내므로 같은 코드를 다시 냄
        rec = a.ask('원천징수되는 사업소득이 있었던 사람 가운데 고용보험 가입 비율을 남녀별로')
        t(tag + '「자료에 없음」 진술의 되돌림 ' + ('없음' if n == 11 else '1회'), ((rec.get('hooks') or {}).get('absent_claim', 0) == 1) == (n == 12))
        a.close()

    msg = [{'role': 'user', 'content': '[참고 자료]\n카드 777,000\n\n[붙임 문서]\n② 수급률 50.8%(보도자료)\n\n[질문]\n붙임 문서의 항목을 확인'}]
    for n in (11, 12):
        rs(n)
        src = '\n'.join(verify.answer_sources(msg))
        t(f'{n}: 수치 대조 출처에 붙임 문서 ' + ('없음(기존 동작)' if n == 11 else '포함'), ('50.8' in src) == (n == 12) and '777,000' not in src)

    # ── 규칙 묶음 12e(12d 개발 점검의 보완) ──
    for n in (11, 12):
        rs(n)
        core.define_sum('fee_t', ['nhi_out_fee', 'nhi_in_fee'], '합계')
        cnt = core.count(where='fee_t > 830000').table()
        t(f'{n}: 합계 변수 조건을 원 단위로 비교(모든 규칙 묶음)', len(cnt) and float(cnt.iloc[0]['값'] or 0) > 1e6)
        fv = core.find_vars('일용근로소득')
        t(('12e' if n == 12 else '11') + ': 줄임 이름 변수 찾기 ' + ('작동' if n == 12 else '없음'), ('p_dainc' in list(fv.get('변수명', []))) == (n == 12))
        r0 = [c for c in verify.check_result(core.count(where='bp_amt == 4800000 and age >= 65')) if c['code'] == '대상 없음']
        t(('12e' if n == 12 else '11') + ': 「대상 없음」 안내에 조건 나누어 세기 ' + ('있음' if n == 12 else '없음'), bool(r0) and (('ssda.count' in r0[0]['msg']) == (n == 12)))
        PQ = '2022년 1월 1일 이후 출생아에게 영아수당 월 50만 원을 현금으로 지급함. 영아수당 수급 아동의 연간 평균 수급액을 산출'
        t(('12e' if n == 12 else '11') + ': 전제 확인 카드 ' + ('작동' if n == 12 else '없음'), bool(verify.premise_issues(PQ, ['child_support']) if n == 12 else not verify.v12e()))
    rs(12)
    t('12e: 줄임 이름 — 대상을 한정하는 가운데 낱말·자료에 없는 제도는 보지 않음', not core.name_contracts('장애아동수당', '장애수당') and core.find_vars('조기취업성공수당').empty
      and core.name_contracts('일용근로소득', '일용소득'))
    t('12e: 「자료에 없음」 진술 점검에 줄임 이름', any(v == 'p_dainc' for k, h in verify.absent_claims('자료에 「일용근로소득」 변수가 없음') for v, _ in h))
    t('12e: 전제 확인 — 맞는 값·다른 율을 곱한 값·변동 폭·바뀌기 전 값은 보지 않음',
      not verify.premise_issues('2022년 영아수당은 월 30만 원임', ['child_support'])
      and not verify.premise_issues('생계급여 선정기준은 기준 중위소득의 30%로 1인 가구 월 583,444원임', ['income', 'nbls'])
      and not verify.premise_issues('2022년 귀속 근로장려금의 총소득 기준금액이 가구 유형별로 200만 원씩 올랐음', ['itc'])
      and not verify.premise_issues("직장가입자 건강보험료율은 '20년 6.67% → '21년 6.86%로 오름", ['nhi_premium']))
    hold12 = lambda q, c, doc='': [i['msg'] for i in verify.check_request(q, c, doc=doc) if i.get('target')]
    t('12e: 「입원 진료를 받은 사람」을 본인부담금 > 0 으로 정한 코드 점검', any('nhi_in_dur > 0' in x for x in hold12('붙임 문서의 항목을 산출', "r = ssda.mean('nhi_in_fee', where='nhi_in_fee > 0')", '③ 입원 진료를 받은 사람의 1인당 본인부담금 평균'))
      and not any('nhi_in_dur' in x for x in hold12('붙임 문서의 항목을 산출', "r = ssda.mean('nhi_in_fee', where='nhi_in_fee > 0')", '③ 입원 본인부담금이 있는 사람의 평균')))
    t('12e: 전제 확인 — 율의 기준(분모)이 다름', any('율의 기준' in f for _, f in verify.premise_issues('2022년 장기요양보험료율은 소득의 12.27%로 매김', ['nhi_premium'])))
    a, sc = make(12, ['**결과**\n- 끝'])
    a.ask('붙임 문서의 항목을 산출해 주세요.', extra_context='■ 붙임 문서\n○ 2022년 1월 1일 이후 출생아에게 영아수당 월 50만 원을 현금으로 지급함\n① 영아수당 수급 아동 수')
    t('12e: 전제 확인 카드가 참고 자료에 붙음', '■ 전제 확인' in sc.seen[0][1]['content'] and '300,000원' in sc.seen[0][1]['content'])
    a.close()
    a, sc = make(11, ['**결과**\n- 끝'])
    a.ask('붙임 문서의 항목을 산출해 주세요.', extra_context='■ 붙임 문서\n○ 2022년 1월 1일 이후 출생아에게 영아수당 월 50만 원을 현금으로 지급함\n① 영아수당 수급 아동 수')
    t('11: 전제 확인 카드 없음(기존 동작)', '■ 전제 확인' not in sc.seen[0][1]['content'])
    a.close()

    # ── 규칙 묶음 12f(12e 개발 점검의 보완) ──
    for n in (11, 12):
        rs(n)
        ov = [c['msg'] for c in verify.check_result(core.rate(num='poor == 1', where='age >= 65', by=['sex'])) if c['code'] == '전체 값']
        t(('12f' if n == 12 else '11') + ': 전체 값 문구 ' + ('「분류 구분 없이 대상 전체로 계산한 비율」' if n == 12 else '기존'), bool(ov) and (('분류 구분 없이 대상 전체로 계산한 비율' in ov[0]) == (n == 12)))
        kc = [c['msg'] for c in verify.check_result(core.count(where='np_yn == 1', by=['np_type'])) if c['code'] == '칸 합계']
        t(('12f' if n == 12 else '11') + ': 칸 합계 ' + ('있음' if n == 12 else '없음'), bool(kc) == (n == 12) and (n == 11 or '「계」' in kc[0]))
        eqh = [i['msg'] for i in verify.check_request('기초연금 단독가구 수급자 수', "r = ssda.count(where='bp_yn2 == 1 and bp_amt == 4800000')") if i.get('target') and '같다(==)' in i['msg']]
        t(('12f' if n == 12 else '11') + ': 금액 == 조건 점검 ' + ('작동' if n == 12 else '없음'), bool(eqh) == (n == 12))
        t(('12f' if n == 12 else '11') + ': 반올림 범위·원인 추정 응답 점검 ' + ('작동' if n == 12 else '없음'),
          any(i['code'] == '반올림 범위' for i in verify.answer_issues('**결과**\n- 평균 1,190만원(문서 1,191만원) → 틀림', [])) == (n == 12)
          and any(i['code'] == '원인 추정' for i in verify.answer_issues('**결과**\n- 소득이 낮기 때문으로 보임', ['수급률이 높은 원인을 정리'])) == (n == 12))
    rs(12)
    H = lambda q, c, doc='': [i['msg'] for i in verify.check_request(q, c, doc=doc) if i.get('target')]
    t('12f: 금액 == — 상·하한액, 그 금액을 받은 사람을 묻는 질문은 보지 않음',
      not any('같다(==)' in x for x in H('기준소득월액이 상한액 553만원에 해당하는 사람의 비율', "r = ssda.rate('np_inc_amt == 5530000', where='np_yn == 1')"))
      and not any('같다(==)' in x for x in H('2022년 연간 장애인연금 급여액이 4,650,000원인 수급자는 몇 명입니까?', "r = ssda.count(where='disp_yn1 == 1 and disp_amt == 4650000')")))
    DOC = '② 가구 가처분소득의 월평균이 2022년 생계급여 선정기준 이하인 가구의 비율을 가구원수별(1인, 2인, 3~6인)로 제시'
    t('12f: 기준 중위소득 율의 가구원 수별 금액과 다른 코드 점검', any('978,026원' in x for x in H('붙임 문서의 항목을 산출', "w = 'hnum == 2 and h_dinc / 12 <= 1026244'", DOC))
      and not any('기준 중위소득 율' in x for x in H('붙임 문서의 항목을 산출', "w = 'hnum == 2 and h_dinc / 12 <= 978026'", DOC))
      and not any('기준 중위소득 율' in x for x in H('붙임 문서의 항목을 산출', "w = 'hnum == 2 and h_dinc <= 1026244 * 12 / 1000000'", '가구원수별 평균 소득을 산출')))
    t('12f: 제도 카드의 가구원 수별 선정기준 금액', any('2인 978,026원' in l for l in verify.fact_lines('nbls')) and any('2인 가구 월' in l for l in verify.fact_lines('income')))
    t('12f: 반올림 범위 — 차이가 표시 자릿수보다 크거나 덜 정밀한 문서 값은 보지 않음',
      not verify.rounding_claims('문서 10% / 자료 5% → 틀림') and not verify.rounding_claims('문서 300만원 / 자료 350만원 → 틀림')
      and not verify.rounding_claims('문서 9.8% / 자료 6.1% → 틀림') and bool(verify.rounding_claims('4등급 48.7%(문서 48.69%와 다름)')))
    t('12f: 원인 추정 — 판정할 수 없다는 문장·효과를 묻지 않은 질문은 보지 않음',
      not verify.causal_claims('소득이 낮기 때문으로 판단할 수 없음', ['효과']) and not verify.causal_claims('소득이 낮기 때문으로 보임', ['수급자 수를 산출']))
    t('12f: 전제 확인 카드에 까닭을 짐작하지 않는다는 문구', '짐작해 적지 않음' in verify.premise_note([('영아수당 월 50만 원', '영아수당 월액 300,000원')]))
    kr = [c['msg'] for c in verify.check_result(core.count(where='dis_yn == 1', by=['dis_grade_1'])) if c['code'] == '칸 합계']
    t('12f: 칸 합계 — 분류 누락이 없으면 반올림 차이 안내', bool(kr) and '반올림에서 생긴' in kr[0])
    t('12f: 같은 갈래 변수의 「또는」 묶음 — 질문이 일부만 말했을 때만',
      any('같은 갈래' in x for x in H('산정특례 대상자 가운데 암으로 등록된 사람이 몇 명인지', "r = ssda.count(where='nhi_special1_yn == 1 or nhi_special2_yn == 1 or nhi_special4_yn == 1')"))
      and not any('같은 갈래' in x for x in H('산정특례 대상자가 몇 명인지', "r = ssda.count(where='nhi_special1_yn == 1 or nhi_special2_yn == 1')")))
    t('12f: 더 맞는 이름의 변수 — 질문이 긴 이름을 말했을 때만',
      any('원천징수사업소득' in x for x in H('지급할 때 원천징수되는 사업소득이 있었던 사람의 고용보험 가입 비율', "r = ssda.rate('empins_yn1 == 1', where='p_binc > 0')"))
      and not any('원천징수사업소득' in x for x in H('사업소득이 있는 사람의 고용보험 가입 비율', "r = ssda.rate('empins_yn1 == 1', where='p_binc > 0')")))

bad = [n for n, ok in R if not ok]
for n in bad:
    print('실패:', n)
print(f'규칙 묶음 12 자체 시험 {len(R) - len(bad)}/{len(R)}')
sys.exit(1 if bad else 0)
