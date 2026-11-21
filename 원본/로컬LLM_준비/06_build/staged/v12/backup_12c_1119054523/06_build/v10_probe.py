#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""규칙 묶음 10(독립 검증 5차 뒤의 보완)의 자체 시험 — 모형 없이 검증 단계·용어 해석·조립기의 동작만 본다.

  SSDA_DATA=… python 06_build/v10_probe.py
규칙 묶음 9에서는 동작이 바뀌지 않는지와 10에서 보완이 작동하는지를 함께 본다. 시험 문장은 5차 기록에서 확인한 오류 유형을 일반화한 것이다.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '02_library')); sys.path.insert(0, str(ROOT / '06_build'))
from ssda import runner, verify  # noqa: E402
from terms import Glossary  # noqa: E402

R = []


def t(name, cond):
    R.append((name, bool(cond)))


def rs(n):
    os.environ['SSDA_RULESET'] = str(n)


def targets(q, c, hist=(), carried=()):
    return [r['msg'] for r in verify.check_request(q, c, hist, carried) if r.get('target')]


C_CAT = ('import ssda\nwhere = "oldwork_type1_yn1 == 1 or oldwork_type2_yn1 == 1 or oldwork_type3_yn1 == 1"\n'
         'r1 = ssda.count(where="oldwork_type1_yn1 == 1 and " + where)\nprint(r1)')
Q_CAT = '2022년 노인일자리 참여자를 공익활동, 사회서비스형, 시장형사업단 세 유형으로 나눠 각각 몇 명인지 알려 주세요.'
rs(9); t('9: 이어 만든 조건식은 괄호 점검에 걸리지 않음(기존 동작)', not any('괄호' in m for m in targets(Q_CAT, C_CAT)))
rs(10); t('10: v10() 켜짐', verify.v10() and verify.v9())
t('10: 이어 만든 조건식을 풀어 냄', any(' and ' in s and ' or ' in s for s in verify.cond_strings(C_CAT)))
t('10: 이어 만든 조건식의 괄호 경고', any('괄호' in m for m in targets(Q_CAT, C_CAT)))
t('10: 괄호로 묶어 이으면 경고 없음', not any('괄호' in m for m in targets(Q_CAT, C_CAT.replace('" + where', '(" + where + ")"'))))
t('10: f-문자열로 이은 조건식', any('괄호' in m for m in targets(Q_CAT, C_CAT.replace('"oldwork_type1_yn1 == 1 and " + where', 'f"oldwork_type1_yn1 == 1 and {where}"'))))

Q_U = '두루누리 지원 기준은 월평균보수 230만원 미만입니다. 국민연금 사업장가입자 중 기준소득월액이 230만원 미만인 사람 가운데 보험료 지원을 받은 사람의 비율은 몇 %입니까?'
C_U = "import ssda\nprint(ssda.rate('np_support_yn1 == 1', where='np_type == 0 and np_inc_amt < 230'))"
rs(9); t('9: 단위 경고 없음(기존 동작)', not any('단위' in m for m in targets(Q_U, C_U)))
rs(10); t('10: 만원 단위로 적은 금액 조건 경고', any('단위' in m and 'np_inc_amt < 230' in m for m in targets(Q_U, C_U)))
t('10: 원 단위로 적으면 경고 없음', not any('단위' in m for m in targets(Q_U, C_U.replace('< 230', '< 2300000'))))
t('10: 금액이 아닌 변수는 대상 아님', not any('단위' in m for m in targets('가입기간이 120개월 이상이고 연금액이 50만원 이상인 사람 수', "import ssda\nprint(ssda.count(where='np_dur >= 120 and np_pension_amt >= 500000'))")))

Q_C = '생계비를 받지 않는 쪽 가구만 놓고 보겠습니다. 이 가구들 가운데 2022년에 긴급복지 생계지원금을 한 번이라도 받은 가구의 비율을 뽑아 주세요.'
C_C = "import ssda\nprint(ssda.rate('aid_live_yn1 == 1', where='hnum == 1 and not (nbls_live_yn2 == 1)', unit='가구'))"
H_C = ['1인 가구 가운데 가구주가 2022년 12월 현재 생계급여를 받고 있는 가구와 받지 않는 가구로 나눠 가구 수를 보여 주세요.']
rs(9); t('9: 이어받은 12월 기준 조건에 연간 기준 경고(기존 동작)', any('nbls_live_yn1' in m for m in targets(Q_C, C_C, H_C, {'nbls_live_yn2'})))
rs(10); t('10: 앞선 차례에서 쓴 변수는 기준 시점 경고 대상이 아님', not any('nbls_live_yn1' in m for m in targets(Q_C, C_C, H_C, {'nbls_live_yn2'})))
t('10: 이번 차례에 새로 쓴 변수는 경고함', any('nbls_live_yn1' in m for m in targets(Q_C, C_C, H_C, set())))

# 금액 단위와 기준값의 근거(질문·참고 자료에 없는 기준값)
Q_P = '그 소득신고자 가운데 기준소득월액 상한액에 걸려 있는 사람은 몇 명입니까? 2022년 말에 적용되던 상한액으로 봐 주십시오.'
t('10: 질문에 금액이 없어도 만원 단위로 적은 조건 경고', any('단위' in m for m in targets(Q_P, "import ssda\nprint(ssda.count(where='np_status == 1 and np_inc_amt >= 550'))")))
t('10: 기억으로 적용한 기준값 경고', any('기억으로' in m for m in targets(Q_P, "import ssda\nprint(ssda.count(where='np_status == 1 and np_inc_amt >= 5530000'))")))
Q_G = '2022년 기초연금 선정기준액이 단독가구 월 180만원입니다. 연간 가구 경상소득이 이 기준의 12개월분 이하인 사람은 몇 명인지 구해 주세요.'
t('10: 질문 금액의 12개월분은 근거 있음', not any('기억으로' in m for m in targets(Q_G, "import ssda\nprint(ssda.count(where='age >= 65 and hnum == 1 and h_oinc <= 21600000'))")))
t('10: 질문 금액(원 표기) 그대로는 근거 있음', not any('기억으로' in m for m in targets('1인 가구 생계급여 선정기준 월 583,444원의 12개월분(7,001,328원) 이하인 가구 수', "import ssda\nprint(ssda.count(where='hnum == 1 and h_oinc <= 7001328', unit='가구'))")))
t('10: 참고 자료(출처)에 적힌 값은 근거 있음', not any('기억으로' in m for m in [r['msg'] for r in verify.check_request(Q_P, "import ssda\nprint(ssda.count(where='np_inc_amt >= 5530000'))", (), (), '[참고 자료] 상한액 553만원') if r.get('target')]))
t('10: 30만 7,500원 표기의 연간 환산', verify._grounded_amount(3690000, '기준연금액 월 30만 7,500원'))
t('10: 백분율 적용(중위소득 30%)', verify._grounded_amount(583444, '1인 기준 중위소득 1,944,812원의 30%'))
t('10: 금액 변수 아닌 조건은 대상 아님', not any('기억으로' in m or '단위' in m for m in targets(Q_P, "import ssda\nprint(ssda.count(where='np_dur >= 120 and age >= 60'))")))
# 값이 없는 사업
rs(10)
t('10: 질문에 나온 값 없는 사업', any('청소년' in n for n in verify.empty_programs('청소년 한부모 아동양육비를 받은 사람은 몇 명인가요?')))
t('10: 값 있는 사업은 대상 아님', not verify.empty_programs('한부모가족지원 아동양육비를 받은 사람은 몇 명인가요?') and not verify.empty_programs('기초연금 수급자 수'))
t('10: 값 없는 사업 안내 문구', '값이 수록되지 않은' in verify.empty_program_note(['자활근로(차상위)']))
t('10: 값 없는 사업의 금액 파생 변수는 실행 전에 돌려보냄', 'p_unempbn_sicknessbn_amt' in verify.lint_code("import ssda\nprint(ssda.count(where='p_unempbn_sicknessbn_amt > 0'))")['empty'])
rs(9); t('9: 금액 파생 변수는 그대로 실행(기존 동작)', not verify.lint_code("import ssda\nprint(ssda.count(where='p_unempbn_sicknessbn_amt > 0'))")['empty'])
rs(10)
t('10: 실행 결과 밖의 값 가림', verify.redact_numbers('비율은 100%에 해당함. 인원은 19,000,000명', ['100']) == '비율은 [표시하지 않는 값]에 해당함. 인원은 19,000,000명')

e = verify.unseen_error(['p_dinc'])
t('10: 정의를 확인하지 않은 변수의 뜻을 알림', '가처분소득' in e and '실행하지 않음' in e)
t('10: 거절 전 점검 — 자료에 없다는 거절', verify.refuse_gate('**요청 처리 불가**\n\n- 「본인부담분」을 산출할 변수가 자료에 없음', '고용보험료 본인부담분 평균을 연령대별로'))
t('10: 거절 전 점검 — 통제에 따른 거절은 대상 아님', not verify.refuse_gate('**요청 처리 불가**\n\n- 개인 단위 자료는 제공할 수 없음. 해당 변수가 자료에 없는 것은 아님', '수급자 명단을 뽑아 주세요')
  and not verify.refuse_gate('**요청 처리 불가**\n- 자료에 없음', '지원액 상위 10명의 금액을 뽑아 주세요'))
t('10: 거절 전 점검 — 되묻기·산출 응답은 대상 아님', not verify.refuse_gate('**확인 필요**\n- 자료에 없음', '평균') and not verify.refuse_gate('**결과**\n- 12.3%', '평균'))

SRC = ['[질문]\n올해 7월에 처음 모집한 청년내일저축계좌 가입자 수를 알려 주세요. 기준은 월 50만원 초과입니다.']
pc = verify.policy_claims('**요청 처리 불가**\n- 청년내일저축계좌는 2024년 7월에 처음 모집한 제도로 자료에 없음\n- 2022년 자료에는 변수가 없음', SRC)
t('10: 출처에 없는 연도 진술', pc.get('years') == ['2024'])
t('10: 자료 기준연도와 질문에 있는 값은 대상 아님', not verify.policy_claims('**결과**\n- 2022년 기준 12,300명\n\n**유의 사항**\n- 질문의 기준(월 50만원 초과)을 적용함', SRC))
t('10: 출처에 없는 금액 진술(결과 밖)', '33만 6,000원' in ' '.join(verify.policy_claims('**결과**\n- 평균 310만원\n\n**유의 사항**\n- 기준연금액은 월 33만 6,000원임', SRC + ['[실행 결과]\n평균 310']).get('amounts', [])))
t('10: 실행 결과의 값은 대상 아님', not verify.policy_claims('**결과**\n- 평균 310만원\n\n**유의 사항**\n- 평균 310만원은 수급자만의 값임', SRC + ['[실행 결과]\n평균 310']))
t('10: 재작성 요청 문구', '기억으로 적지 않음' in verify.policy_note({'years': ['2024']}))

t('결과 객체 연산 오류의 사용법 안내', 'ssda.rate' in runner.usage_hint("TypeError: '>' not supported between instances of 'Result' and 'int'") and 'ssda.rate' in runner.usage_hint("AttributeError: 'Result' object has no attribute 'values'"))

G = Glossary()
rs(9); n9 = G.resolve('2022년 한 해 동안 주택담보노후연금에 가입해 있던 사람 수를 알려 주세요.')['notes']
rs(10); n10 = G.resolve('2022년 한 해 동안 주택담보노후연금에 가입해 있던 사람 수를 알려 주세요.')['notes']
t('9: 사전에 없는 이름 안내(기존 문구)', any('이 이름이 없음' in n for n in n9))
t('10: 사전에 없는 이름 안내 — 공식 명칭이면 산출', any('공식 명칭' in n and '되묻지 않음' in n for n in n10))
a10 = G.resolve('상병수당 시범사업의 대상 연령인 만 15세 이상 65세 미만 직장가입자가 몇 명인지 알려 주세요.')['notes']
t('10: 자료에 없는 제도가 배경으로 쓰인 요청', any('배경' in n and '그 조건대로 산출' in n for n in a10))
r = G.resolve('2022년 한 해 동안 주택담보노후연금에 가입해 있던 사람 수와 이들이 받은 연금 지급액의 중위수를 알려 주세요.')
t('10: 같은 질문의 고유 명칭을 가리키는 일반 낱말은 되묻지 않음', not any(u['policy'] == 'ask' for u in r['unresolved']))
r = G.resolve('수급자 가운데 시설에 입소한 사람이 1년 동안 낸 시설급여 본인부담금의 1인당 평균을 알려 주세요.')
t('10: 수식어와 함께 변수 이름이 되는 낱말은 되묻지 않음', not any(u['policy'] == 'ask' for u in r['unresolved']) and any('ltcare_ibn_fee' in n and '대상 조건' in n for n in r['notes']))
r = G.resolve('부양자녀가 있는 저소득 가구에 자녀 1인당 최대 70만원까지 주는 장려금의 수급 대상자 수를 알려 주세요.')
t('10: 설명으로 구성 급여가 정해지면 되묻지 않음', not any(u['term'] == '장려금' for u in r['unresolved']) and any('자녀장려금' in n for n in r['notes']))
r = G.resolve('장려금 수급자 수를 알려 주세요.')
t('10: 정해지지 않으면 그대로 되물음', any(u['policy'] == 'ask' for u in r['unresolved']))
rs(9); r = G.resolve('수급자 가운데 시설에 입소한 사람이 1년 동안 낸 시설급여 본인부담금의 1인당 평균을 알려 주세요.')
t('9: 수식어가 있어도 되물음(기존 동작)', any(u['policy'] == 'ask' for u in r['unresolved']))
rs(10)
k10 = G.resolve('65세 이상의 진료비 평균을 알려 주세요.')['notes']
t('10: 되묻기 안내의 적용 범위', any('설명하는 구절' in n for n in k10))

if os.environ.get('SSDA_DATA'):
    from assistant import Assistant, load_config  # noqa: E402
    from retriever import Retriever  # noqa: E402

    class Script:
        def __init__(self, replies):
            self.replies, self.usage, self.seen = list(replies), {}, []

        def chat(self, messages):
            self.seen.append(messages[-1]['content'])
            return self.replies.pop(0) if self.replies else '**결과**\n- 확인함'
    code = "```python\nimport ssda\nprint(ssda.count(where='p_dinc > 0', by='sex'))\n```"
    for n in (9, 10):
        cfg = load_config(); cfg['verify']['ruleset'] = n; cfg['prompt']['n_examples'] = 0
        cfg['paths'].update(export='/tmp/v10p_export', log='/tmp/v10p_log.jsonl', transcripts='/tmp/v10p_tr.jsonl')
        cl = Script([code, code, '**결과**\n- 표와 같음\n\n**유의 사항**\n- 없음'])
        a = Assistant(cfg, cl, Retriever())
        rec = a.ask('How many people had day labor income in 2022? Break down by sex.')
        if n == 9:
            t('9: 정의를 확인하지 않은 변수도 바로 실행(기존 동작)', rec['steps'][0].get('ok') and not rec['steps'][0].get('held'))
        else:
            t('10: 정의를 확인하지 않은 변수는 실행 전에 돌려보냄', rec['steps'][0].get('held') and '가처분소득' in rec['steps'][0]['error'] and rec['steps'][1].get('ok') and (rec.get('hooks') or {}).get('unseen') == 1)
        ids = a.context('그 가운데 2022년에 국민내일배움카드 지원을 받은 사람은 몇 명인가요?')[1]
        t(f'{n}: 후속 질문의 이름 일치 변수 카드 ' + ('없음(기존 동작)' if n == 9 else '있음'), ('var:vocaedu_yn' in ids) == (n == 10))
        if n == 10:
            ids2 = a.context('그 가운데 기초생활보장에서 월세를 지원하는 급여를 받는 사람은 몇 명인가요?')[1]
            t('10: 후속 질문에 검색 순위로 고른 카드는 붙이지 않음', not [i for i in ids2 if i.startswith('var:')] or all(i.startswith('var:nbls_house') for i in ids2 if i.startswith('var:')))
        a.close()

bad = [n for n, ok in R if not ok]
for n in bad:
    print('실패:', n)
print(f'규칙 묶음 10 자체 시험 {len(R) - len(bad)}/{len(R)}')
sys.exit(1 if bad else 0)
