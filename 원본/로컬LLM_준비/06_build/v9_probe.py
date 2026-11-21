#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""규칙 묶음 9(독립 검증 4차 뒤의 조치)의 자체 시험 — 모형 없이 검증 단계·용어 해석·실행기의 동작만 본다.

  python 06_build/v9_probe.py
규칙 묶음 8에서는 동작이 바뀌지 않는지(끈 상태)와 9에서 조치가 작동하는지를 함께 본다. 시험 문장은 4차 기록에서 확인한 오류 유형을 일반화한 것이다.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '02_library')); sys.path.insert(0, str(ROOT / '06_build'))
from ssda import verify  # noqa: E402
from terms import Glossary  # noqa: E402

R = []


def t(name, cond):
    R.append((name, bool(cond)))


def rs(n):
    os.environ['SSDA_RULESET'] = str(n)


def targets(q, c, hist=()):
    return [r['msg'] for r in verify.check_request(q, c, hist) if r.get('target')]


SUM5 = ("import ssda\nssda.define_sum('in_dur_all', ['nhi_in_hospital_dur', 'nhi_in_clinic_dur', 'nhi_in_emergency_dur', 'nhi_in_gehospital_dur', 'nhi_in_tehospital_dur'], '합계')\n"
        "print(ssda.rate('in_dur_all < 7', where='not isna(in_dur_all)'))")
Q_IN = '2022년에 입원 진료를 받은 사람 중에서 연간 입원 재원일수가 7일 미만인 사람은 몇 %인가요?'
rs(8); t('8: 구성 변수 합 경고 없음', not targets(Q_IN, SUM5)); t('8: v9() 꺼짐', not verify.v9())
rs(9); t('9: v9() 켜짐', verify.v9())
t('9: 구성 변수의 합에 전체 변수 안내', any('nhi_in_dur' in m for m in targets(Q_IN, SUM5)))
t('9: 전체 변수를 쓴 코드는 경고 없음', not targets(Q_IN, "import ssda\nprint(ssda.rate('nhi_in_dur < 7', where='not isna(nhi_in_dur)'))"))
t('9: 질문이 유형을 지정하면 경고 없음', not targets('종합병원과 상급종합병원 입원 재원일수를 합한 값이 7일 미만인 사람의 비율', SUM5))
t('9: 전체 변수 카드 덧붙임', verify.totals_for(['nhi_in_hospital_dur', 'nhi_in_clinic_dur'], Q_IN) == ['nhi_in_dur'])
t('9: 응급실 변수만 있어도 전체 변수 카드', verify.totals_for(['nhi_in_emergency_dur'], Q_IN) == ['nhi_in_dur'])
t('9: 유형 지정 질문에는 덧붙이지 않음', verify.totals_for(['nhi_in_hospital_dur'], '상급종합병원 입원 일수') == [])
t('9: 관계 안내 문구', 'nhi_in_dur' in verify.relation_note(['nhi_in_dur']) and '응급실' in verify.relation_note(['nhi_in_dur']))

Q_DA = '18~64세이면서 2022년에 고용보험 가입 이력도 없고 국민연금 가입 이력도 없는 사람들 가운데, 그해 일용근로소득이 있었던 사람의 비율을 남녀별로 계산해 주세요.'
rs(8); c8 = [c['name'] for c in verify.var_candidates(Q_DA, set(), top=3)]
rs(9); c9 = [c['name'] for c in verify.var_candidates(Q_DA, set(), top=3)]
t('8: 늘여 쓴 이름의 변수가 후보 3개에 없음(기존 동작)', not ({'p_dainc', 'dainc_sum'} & set(c8)))
t('9: 늘여 쓴 이름의 변수가 후보 3개에 듦', bool({'p_dainc', 'dainc_sum'} & set(c9)))
t('9: 낱말의 일부와만 맞는 변수는 후보에서 빠짐', 'p_labinc' not in c9)
t('9: 이름을 그대로 적은 질문은 그대로', 'p_labinc' in [c['name'] for c in verify.var_candidates('근로소득이 있는 사람의 비율', set(), top=3)])

Q_EN = 'Could you tell me how many people were receiving the Disability Pension (장애인연금) as of December 2022, broken down by sex?'
C_EN = "import ssda\nprint(ssda.count(where='disp_yn1 == 1', by='sex'))"
rs(8); t('8: 영문 기준 시점 경고 없음', not targets(Q_EN, C_EN))
rs(9); t('9: 영문 12월 기준에 연간 변수 경고', any('disp_yn2' in m for m in targets(Q_EN, C_EN)))
t('9: 12월 기준 변수를 쓰면 경고 없음', not targets(Q_EN, C_EN.replace('yn1', 'yn2')))
t('9: 영문 연령 경계', any('65세 이상' in m for m in targets('What share of people aged 65 or older received the Basic Pension during the year?', "import ssda\nprint(ssda.rate('bp_yn1 == 1', where='age > 65'))")))
t('9: 영문 연령 경계(맞는 코드)', not targets('What share of people aged 65 or older received the Basic Pension during the year?', "import ssda\nprint(ssda.rate('bp_yn1 == 1', where='age >= 65'))"))
t('9: 영문 성 조건', any('gender == 2' in m for m in targets('How many women under 30 were enrolled in employment insurance?', "import ssda\nprint(ssda.count(where='gender == 1 and age < 30 and empins_yn1 == 1'))")))
t('9: 한글 질문에는 영문 풀이가 붙지 않음', verify._en_gloss('65세 이상 기초연금 수급률을 시도별로 (EITC 제외)') == '')

Q_AGE = '0세부터 6세까지 아이들 중에 12월 기준으로 보육료 지원을 받고 있는 아이가 몇 퍼센트나 되는지 궁금해요. 0세, 1세, 2세, 3~4세, 5~6세로 나눠서 보여주실 수 있나요?'
C_AGE = ("import ssda\nssda.define_group('age_child', 'age', [1, 2, 3, 5], ['0세', '1세', '2세', '3~4세', '5~6세'])\n"
         "print(ssda.rate('childcare_yn2 == 1', where='age >= 0 and age <= 6', by='age_child'))")
rs(8); t('8: 한 살 단위 구간을 돌려보냄(기존 동작)', bool(targets(Q_AGE, C_AGE)))
rs(9); t('9: 한 살 단위 구간은 돌려보내지 않음', not targets(Q_AGE, C_AGE))
t('9: 경계가 다른 구간은 돌려보냄', bool(targets(Q_AGE, C_AGE.replace('[1, 2, 3, 5]', '[1, 3, 5, 6]'))))
t('9: 구간 한 개뿐인 질문은 그대로', verify._age_singles('65세 이상 노인 중 80세, 그리고') == '65세 이상 노인 중 80세, 그리고')

C_OR = ("import ssda\nprint(ssda.count(where=\"govp_pension_yn == 1 or privschp_pension_yn == 1 or milip_pension_yn == 1 and age >= 65\", by='sex'))")
Q_OR = '2022년에 군인연금, 사학연금, 공무원연금 중 적어도 한 가지에서 정기연금을 받은 65세 이상인 사람을 성별로 세어 주세요.'
rs(8); t('8: 괄호 경고 없음', not any('괄호' in m for m in targets(Q_OR, C_OR)))
rs(9); t('9: and·or 혼용에 괄호 경고', any('괄호' in m for m in targets(Q_OR, C_OR)))
t('9: 괄호로 묶은 조건식은 경고 없음', not any('괄호' in m for m in targets(Q_OR, C_OR.replace('govp_pension_yn == 1 or privschp_pension_yn == 1 or milip_pension_yn == 1 and', '(govp_pension_yn == 1 or privschp_pension_yn == 1 or milip_pension_yn == 1) and'))))
t('9: or 만 있는 조건식은 경고 없음', not verify._bool_mixed('a == 1 or b == 1') and not verify._bool_mixed('a == 1 and b == 1') and verify._bool_mixed('a == 1 and b == 1 or c == 1') and not verify._bool_mixed('(a == 1 and b == 1) or c == 1'))

C_ANY = "import ssda\nprint(ssda.rate('any(h_ptax_building > 0)', by='age6', unit='가구'))"
rs(8); t('8: 함수 이름을 없는 변수로 안내(기존 동작)', '없는 변수: any' in verify.lint_error(verify.lint_code(C_ANY)))
rs(9); e = verify.lint_error(verify.lint_code(C_ANY))
t('9: 조건식의 함수 안내', '조건식에는 any()' in e and 'h_ptax_building' in e and '없는 변수: any' not in e)
e = verify.lint_error(verify.lint_code("import ssda\nprint(ssda.rate('max(p_ptax_building) > 0', unit='가구'))"))
t('9: 가구 합산 변수 안내', 'h_ptax_building' in e)
t('9: 없는 변수 안내는 그대로', '없는 변수: xyz_abc' in verify.lint_error(verify.lint_code("import ssda\nprint(ssda.count(where='xyz_abc == 1'))")))

G = Glossary()
Q_AB = '파국적의료비 지원사업 실적을 보고 싶습니다. 2022년에 지원받은 사람 수와 1인당 평균 지원액을 소득 분위별로 뽑아 주세요.'      # 2026-11-19 예시 변경: 재난적의료비가 용어 사전의 「자료에 없는 제도」에 들어감
rs(8); r8 = G.resolve(Q_AB)
rs(9); r9 = G.resolve(Q_AB)
t('8: 합성어의 일부를 되물을 용어로 읽음(기존 동작)', any(u['policy'] == 'ask' for u in r8['unresolved']))
t('9: 합성어의 일부는 되묻지 않음', not any(u['policy'] == 'ask' for u in r9['unresolved']))
t('9: 사전에 없는 이름 안내', any('파국적의료비' in n and '요청 처리 불가' in n for n in r9['notes']))
r9b = G.resolve('파국적 의료비 지원을 받은 사람 수를 알려 주세요.')
t('9: 띄어 쓴 합성어(…적 + 낱말)도 되묻지 않음', not any(u['policy'] == 'ask' for u in r9b['unresolved']) and any('파국적' in n for n in r9b['notes']))
t('9: 사전에 없는 제도명', G.unknown_programs('2021년 상생 국민지원금을 받은 가구 수') == ['국민지원금'] and G.unknown_programs('긴급고용안정지원금 수급자') == ['긴급고용안정지원금'])
t('9: 사전에 있는 제도명은 건드리지 않음', not any(G.unknown_programs(x) for x in ('기초연금 수급자 수', '육아휴직급여 수급자', '생계급여액 평균', '구직급여 수급 기간', '근로장려금 대상', '두루누리 고용보험료 지원', '평균급여와 총급여', '국민연금보험료 납부액', '아동수당 수급률')))
rs(9); r = G.resolve('65세 이상의 진료비 평균을 알려 주세요.')
t('9: 띄어 쓴 일반 낱말의 규칙은 그대로', any(u['policy'] == 'ask' for u in r['unresolved']))
rs(8); a8 = G.resolve('첫만남이용권을 받은 가구 수를 알려 주세요')['notes']
rs(9); a9 = G.resolve('첫만남이용권을 받은 가구 수를 알려 주세요')['notes']
t('8: 자료에 없는 제도는 확인 필요(기존 동작)', any('확인 필요' in n for n in a8))
t('9: 자료에 없는 제도는 요청 처리 불가', any('요청 처리 불가' in n for n in a9) and not any('「확인 필요」에' in n for n in a9))

out = {'ok': True, 'stdout': 'Empty DataFrame\nColumns: []\nIndex: []\n', 'error': '', 'figures': [], 'results': {}, 'checks': {}}
rs(8); t('8: 빈 변수 찾기 안내 없음', '변수 찾기 결과가 없음' not in verify.tool_message(out))
rs(9); t('9: 빈 변수 찾기 안내', '변수 찾기 결과가 없음' in verify.tool_message(out))


def run(code, ruleset):
    env = dict(os.environ, PYTHONPATH=str(ROOT / '02_library'), SSDA_RULESET=str(ruleset))
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False, encoding='utf-8') as fp:
        fp.write(code); path = fp.name
    try:
        p = subprocess.run([sys.executable, '-m', 'ssda.runner', path, '--timeout', '60', '--mem', '6'], capture_output=True, text=True, env=env, cwd=str(ROOT))
        return json.loads(p.stdout.strip().splitlines()[-1])
    finally:
        os.unlink(path)


if os.environ.get('SSDA_DATA'):
    code = "import ssda\nprint(ssda.count(where=\"nhi_type in [5, 6] and nbls_medi_yn2 == 1\"))"
    flat = lambda o: [c['code'] for cs in (o.get('checks') or {}).values() for c in cs]
    t('8: 대상 없음을 억제로 안내(기존 동작)', '억제' in flat(run(code, 8)))
    f9 = flat(run(code, 9))
    t('9: 대상 없음 안내', '대상 없음' in f9 and '억제' not in f9)
    t('9: 억제된 칸은 억제로 안내', '억제' in flat(run("import ssda\nprint(ssda.count(where='age == 107'))", 9)) or '대상 없음' in flat(run("import ssda\nprint(ssda.count(where='age == 107'))", 9)))

bad = [n for n, ok in R if not ok]
for n in bad:
    print('실패:', n)
print(f'규칙 묶음 9 자체 시험 {len(R) - len(bad)}/{len(R)}')
sys.exit(1 if bad else 0)
