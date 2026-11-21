# -*- coding: utf-8 -*-
"""C·F·G 묶음 문항을 JSON Lines로 쓰는 작업용 스크립트(독립 문항 작성자 w2)."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ITEMS = os.path.join(os.path.dirname(HERE), 'items')


def S(measure, population='', unit='person', by=None, **kw):
    d = {}
    if 'turn' in kw:
        d['turn'] = kw.pop('turn')
    d.update({'measure': measure, 'unit': unit, 'population': population})
    for k in ('numerator', 'value_var', 'q'):
        if k in kw:
            d[k] = kw.pop(k)
    assert not kw, kw
    d['by'] = by or []
    return d


SEX = [{'std': 'sex'}]
SIDO = [{'std': 'sido'}]

# ---------------------------------------------------------------- C 묶음
C = []


def pair(no, diff, persona, qa, sa, qb, sb, note):
    for suf, q, s in (('a', qa, sa), ('b', qb, sb)):
        C.append({'id': f'C{no:02d}{suf}', 'stratum': 'C', 'pair': f'C{no:02d}', 'diff': diff, 'persona': persona,
                  'turns': [q], 'expect': 'compute', 'specs': [s], 'note': note})


pair(1, '연령 경계', '지자체 노인복지 담당자',
     '65세 이상 노인 가운데 2022년 한 해 동안 노인장기요양 급여를 한 번이라도 받은 사람의 비율이 얼마인지 알려 주세요.',
     S('rate', 'age >= 65', numerator='ltcare_bn_yn == 1'),
     '75세 이상 노인 가운데 2022년 한 해 동안 노인장기요양 급여를 한 번이라도 받은 사람의 비율이 얼마인지 알려 주세요.',
     S('rate', 'age >= 75', numerator='ltcare_bn_yn == 1'),
     '대상 연령의 하한(65세↔75세)만 다른 장기요양 수급률')

pair(2, '비율↔인원', '장애인정책 연구자',
     '18~64세 인구 중 등록장애인(2022년 12월 31일 기준)의 비율을 성별로 산출해 주십시오.',
     S('rate', 'age >= 18 and age <= 64', numerator='dis_yn == 1', by=SEX),
     '18~64세 인구 중 등록장애인(2022년 12월 31일 기준)의 인원을 성별로 산출해 주십시오.',
     S('count', 'age >= 18 and age <= 64 and dis_yn == 1', by=SEX),
     '같은 대상에서 비율을 묻는지 인원을 묻는지만 다름')

pair(3, '개인↔가구', '통계 담당자',
     '가구원 재산을 모두 합한 가구 재산이 5억원 이상인 가구는 몇 가구인가요?',
     S('count', 'h_prop >= 500000000', unit='household'),
     '가구원 재산을 모두 합한 가구 재산이 5억원 이상인 가구에 속한 사람은 몇 명인가요?',
     S('count', 'h_prop >= 500000000'),
     '같은 조건에서 가구 수(가구주 행·가구 가중치)와 가구원 수(개인 가중치)의 구분')

pair(4, '연간↔12월', '고용노동 정책 담당자',
     '육아휴직급여(사후지급금 제외)를 2022년 한 해 동안 한 번이라도 받은 사람은 몇 명이에요?',
     S('count', 'empins_parentleave_yn1 == 1'),
     '육아휴직급여(사후지급금 제외)를 2022년 12월 기준으로 받고 있던 사람은 몇 명이에요?',
     S('count', 'empins_parentleave_yn2 == 1'),
     '수급 여부의 기준 시점(연간↔12월)만 다름')

pair(5, '평균↔중위수', '연금 연구자',
     '2022년 한 해 동안 공무원연금 정기연금(퇴직연금·유족연금 등)을 한 번이라도 받은 수급자의 연간 수급액 평균 산출 요망.',
     S('mean', 'govp_pension_yn == 1', value_var='govp_pension_amt'),
     '2022년 한 해 동안 공무원연금 정기연금(퇴직연금·유족연금 등)을 한 번이라도 받은 수급자의 연간 수급액 중위수 산출 요망.',
     S('quantile', 'govp_pension_yn == 1', value_var='govp_pension_amt', q=0.5),
     '같은 금액 변수의 평균과 중위수')

pair(6, '평균↔합계', '지자체 보육 담당자',
     '2022년에 보육료 지원을 한 번이라도 받은 아동을 대상으로, 연간 보육료 지원액의 평균이 얼마인지 궁금합니다.',
     S('mean', 'childcare_yn1 == 1', value_var='childcare_amt'),
     '2022년에 보육료 지원을 한 번이라도 받은 아동을 대상으로, 연간 보육료 지원액의 합계가 얼마인지 궁금합니다.',
     S('sum', 'childcare_yn1 == 1', value_var='childcare_amt'),
     '같은 금액 변수의 수급자 평균과 총액')

pair(7, '분모', '교육청 교육복지 담당자',
     '만 7~18세 인구 전체 가운데 2022년에 방과후학교 자유수강권을 지원받은 사람의 비율은 얼마입니까?',
     S('rate', 'age >= 7 and age <= 18', numerator='pubedu_aftsch_yn == 1'),
     '만 7~18세 교육급여 수급권자(2022년 중 한 번이라도 수급권을 가진 사람) 가운데 2022년에 방과후학교 자유수강권을 지원받은 사람의 비율은 얼마입니까?',
     S('rate', 'age >= 7 and age <= 18 and nbls_edu_yn1 == 1', numerator='pubedu_aftsch_yn == 1'),
     '분자는 같고 분모가 해당 연령 전체인지 교육급여 수급권자인지만 다름')

pair(8, '이상↔초과', '건강보험 통계 담당자',
     '65세 이상 인구 중에서 2022년 외래 내원일수(의과 의료기관 전체)가 30일 이상인 사람은 몇 퍼센트인가요?',
     S('rate', 'age >= 65', numerator='nhi_out_dur >= 30'),
     '65세 이상 인구 중에서 2022년 외래 내원일수(의과 의료기관 전체)가 30일 초과인 사람은 몇 퍼센트인가요?',
     S('rate', 'age >= 65', numerator='nhi_out_dur > 30'),
     '경계값 포함 여부(이상↔초과)')

pair(9, '미만↔이하', '고용센터 담당자',
     '2022년에 구직급여를 한 번이라도 받은 사람 중에서 그해 수급일수가 120일 미만인 사람이 몇 명인지 뽑아 주세요.',
     S('count', 'unempbn_jobseekbn_yn == 1 and unempbn_jobseekbn_dur < 120'),
     '2022년에 구직급여를 한 번이라도 받은 사람 중에서 그해 수급일수가 120일 이하인 사람이 몇 명인지 뽑아 주세요.',
     S('count', 'unempbn_jobseekbn_yn == 1 and unempbn_jobseekbn_dur <= 120'),
     '경계값 포함 여부(미만↔이하), 120일에 관측이 몰려 있음')

pair(10, '그리고↔또는', '조세·복지 연구자',
     '근로장려금 수급 대상이면서 자녀장려금 수급 대상인 사람 수.',
     S('count', 'itc_yn == 1 and itc_child_yn == 1'),
     '근로장려금 수급 대상이거나 자녀장려금 수급 대상인 사람 수.',
     S('count', 'itc_yn == 1 or itc_child_yn == 1'),
     '두 조건의 결합 방식(그리고↔또는), 대상 여부 변수에 0값이 있어 == 1 판별 필요')

pair(11, '남↔여', '건강보험 자격 담당자',
     '65세 이상 남성의 건강보험 가입유형(지역세대주, 지역세대원, 직장가입자, 직장피부양자, 의료급여 세대주·세대원, 2022년 12월 기준)별 구성비를 보여 주세요.',
     S('share', 'age >= 65 and gender == 1', value_var='nhi_type'),
     '65세 이상 여성의 건강보험 가입유형(지역세대주, 지역세대원, 직장가입자, 직장피부양자, 의료급여 세대주·세대원, 2022년 12월 기준)별 구성비를 보여 주세요.',
     S('share', 'age >= 65 and gender == 2', value_var='nhi_type'),
     '성별만 다른 구성비')

pair(12, '시도', '광역시 노인복지 담당자',
     '부산에 거주하는 65세 이상 노인 중 2022년에 노인맞춤돌봄서비스를 한 번이라도 이용한 사람의 비율은?',
     S('rate', 'age >= 65 and sido == 2', numerator='oldcare_yn1 == 1'),
     '대구에 거주하는 65세 이상 노인 중 2022년에 노인맞춤돌봄서비스를 한 번이라도 이용한 사람의 비율은?',
     S('rate', 'age >= 65 and sido == 3', numerator='oldcare_yn1 == 1'),
     '시도 코드(부산 2↔대구 3)만 다름')

pair(13, '지역 묶음(수도권↔비수도권)', '주거정책 연구자',
     '수도권(서울·인천·경기)에 사는 임차인 가운데 보증금이 있는 사람만 놓고, 임차 보증금(개인 합산액)의 중위수를 구해 주세요.',
     S('quantile', 'ee_deposit_amt_ptot > 0 and sido in [1, 4, 9]', value_var='ee_deposit_amt_ptot', q=0.5),
     '비수도권(서울·인천·경기 외 시도)에 사는 임차인 가운데 보증금이 있는 사람만 놓고, 임차 보증금(개인 합산액)의 중위수를 구해 주세요.',
     S('quantile', 'ee_deposit_amt_ptot > 0 and sido not in [1, 4, 9]', value_var='ee_deposit_amt_ptot', q=0.5),
     '시도 묶음(수도권 3개 시도↔그 밖 14개 시도)만 다름')

pair(14, '수급자↔비수급자', '노후소득보장 연구자',
     '노후소득보장 실태를 정리하는 보고서에 넣을 수치가 필요해서 문의드립니다. 공적연금을 받는 노인과 못 받는 노인의 형편을 견주어 보려는 것인데, 우선 65세 이상 노인 중 2022년에 국민연금 정기연금(노령·장애·유족연금)을 한 번이라도 받은 사람의 상대 빈곤율은 얼마인가요?',
     S('poverty_rate', 'age >= 65 and np_pension_yn == 1'),
     '노후소득보장 실태를 정리하는 보고서에 넣을 수치가 필요해서 문의드립니다. 공적연금을 받는 노인과 못 받는 노인의 형편을 견주어 보려는 것인데, 우선 65세 이상 노인 중 2022년에 국민연금 정기연금(노령·장애·유족연금)을 한 번도 받지 않은 사람의 상대 빈곤율은 얼마인가요?',
     S('poverty_rate', 'age >= 65 and np_pension_yn.isna()'),
     '수급자와 비수급자(여부 변수 결측)의 구분')

pair(15, '분류 기준', '지자체 주거복지 담당자',
     '2022년 12월 기준 주거급여(임차급여) 수급률을 연령대 3구간(0~17세, 18~64세, 65세 이상)별로 보여 주세요. 분모는 각 집단의 전체 인구입니다.',
     S('rate', '', numerator='nbls_house_yn2 == 1', by=[{'std': 'age3'}]),
     '2022년 12월 기준 주거급여(임차급여) 수급률을 가구원수(1인, 2인, 3인, 4인 이상)별로 보여 주세요. 분모는 각 집단의 전체 인구입니다.',
     S('rate', '', numerator='nbls_house_yn2 == 1', by=[{'std': 'hs4'}]),
     '분류 기준(연령대 3구간↔가구원수 4구간)만 다름')

# ---------------------------------------------------------------- F 묶음
F = []


def dialog(no, persona, turns, specs, note):
    F.append({'id': f'F{no:02d}', 'stratum': 'F', 'persona': persona, 'turns': turns, 'expect': 'compute',
              'specs': specs, 'note': note})


dialog(1, '건강보험 연구자',
       ['2022년에 입원한 적이 있는 사람들의 1인당 연간 입원 재원일수(의과 의료기관 전체) 평균은 며칠인지 알려 주세요.',
        '그걸 건강보험 가입 구분(지역가입·직장가입·의료급여)별로 나눠 주세요.',
        '같은 분류 기준으로 75세 이상만 보면 어떻습니까?'],
       [S('mean', 'nhi_in_dur > 0', value_var='nhi_in_dur', turn=1),
        S('mean', 'nhi_in_dur > 0', value_var='nhi_in_dur', by=[{'std': 'nhi3'}], turn=2),
        S('mean', 'nhi_in_dur > 0 and age >= 75', value_var='nhi_in_dur', by=[{'std': 'nhi3'}], turn=3)],
       '분류 기준 추가 뒤 그 분류를 유지한 채 대상 연령을 좁힘')

dialog(2, '통계 담당자',
       ['가구 단위로 볼 때 가구 재산(가구원 재산 합계)의 평균이 얼마야?',
        '그걸 가구원수별(1인, 2인, 3인, 4인 이상)로 나눠 줘.',
        '같은 분류로, 가구 재산이 0원인 가구의 비율도 뽑아 줘.'],
       [S('mean', '', unit='household', value_var='h_prop', turn=1),
        S('mean', '', unit='household', value_var='h_prop', by=[{'std': 'hs4'}], turn=2),
        S('rate', '', unit='household', numerator='h_prop == 0', by=[{'std': 'hs4'}], turn=3)],
       '가구 단위와 분류 기준을 유지한 채 지표만 교체(평균→비율)')

dialog(3, '지자체 보육 담당자',
       ['만 0~5세 아동 가운데 2022년 한 해 동안 보육료 지원을 한 번이라도 받은 아동의 비율을 알고 싶습니다.',
        '방금 것을 비율 말고 인원으로 알려 주세요.',
        '그 인원을 시도별로 나눠 주세요.'],
       [S('rate', 'age <= 5', numerator='childcare_yn1 == 1', turn=1),
        S('count', 'age <= 5 and childcare_yn1 == 1', turn=2),
        S('count', 'age <= 5 and childcare_yn1 == 1', by=SIDO, turn=3)],
       '비율→인원 전환 시 분자 조건을 대상 조건으로 옮겨야 함, 이어서 시도별 분류')

dialog(4, '고용정책 담당자',
       ['2022년 구직급여 수급자(연중 한 번이라도 받은 사람)가 소득 5분위(균등화 가처분소득 기준)별로 어떻게 분포하는지 구성비로 보여 주세요.',
        '그럼 여성 수급자만 보면요?',
        '그 여성 수급자들이 2022년에 받은 구직급여액 평균도 알려 주세요.'],
       [S('share', 'unempbn_jobseekbn_yn == 1', value_var='inc5', turn=1),
        S('share', 'unempbn_jobseekbn_yn == 1 and gender == 2', value_var='inc5', turn=2),
        S('mean', 'unempbn_jobseekbn_yn == 1 and gender == 2', value_var='unempbn_jobseekbn_amt', turn=3)],
       '구성비에서 성별 한정, 이어서 같은 집단의 금액 평균으로 지표 교체')

dialog(5, '장애인정책 연구자',
       ['등록장애인(2022년 12월 31일 기준)의 상대 빈곤율은 어느 정도입니까?',
        '같은 기준으로 장애 정도가 심한 장애인(종합장애정도 기준)만 보면?',
        '그걸 성별로 나눠 주십시오.'],
       [S('poverty_rate', 'dis_yn == 1', turn=1),
        S('poverty_rate', 'dis_yn == 1 and dis_grade_1 == 1', turn=2),
        S('poverty_rate', 'dis_yn == 1 and dis_grade_1 == 1', by=SEX, turn=3)],
       '빈곤율의 대상 좁히기(종합장애정도) 뒤 성별 분류')

dialog(6, '장기요양 담당자',
       ['2022년에 장기요양 급여를 한 번이라도 받은 수급자 가운데 방문요양을 이용한 사람의 비율은?',
        '같은 기준으로 주야간보호는요?',
        '그걸 75세 이상 수급자로 좁혀서 다시 봐 주세요.'],
       [S('rate', 'ltcare_bn_yn == 1', numerator='ltcare_visit_yn == 1', turn=1),
        S('rate', 'ltcare_bn_yn == 1', numerator='ltcare_daynight_yn == 1', turn=2),
        S('rate', 'ltcare_bn_yn == 1 and age >= 75', numerator='ltcare_daynight_yn == 1', turn=3)],
       '분모 유지·분자 교체(방문요양→주야간보호), 이어서 분모에 연령 조건 추가')

dialog(7, '지자체 희망복지 담당자',
       ['2022년 한 해 동안 긴급복지 생계지원을 한 번이라도 받은 사람이 몇 명인지 알려 주세요.',
        '그 사람들이 2022년에 받은 생계지원 급여액은 1인당 평균 얼마입니까?',
        '평균 말고 합계로 알려 주세요.'],
       [S('count', 'aid_live_yn1 == 1', turn=1),
        S('mean', 'aid_live_yn1 == 1', value_var='aid_live_amt', turn=2),
        S('sum', 'aid_live_yn1 == 1', value_var='aid_live_amt', turn=3)],
       '인원→평균→합계로 집계 방식만 바뀌는 대화(값이 있는 비율이 낮은 사업)')

dialog(8, '교육복지 연구자',
       ['2022년 중 교육급여 수급권을 가진 적이 있는 학생들이 그해 받은 교육활동지원비의 1인당 평균 금액을 구해 주세요.',
        '그걸 만 7~12세와 만 13~18세로 나눠서 보여 주세요.'],
       [S('mean', 'nbls_edu_yn1 == 1', value_var='nbls_edu_amt1', turn=1),
        S('mean', 'nbls_edu_yn1 == 1 and age >= 7 and age <= 18', value_var='nbls_edu_amt1',
          by=[{'var': 'age', 'bins': [13], 'labels': ['7~12세', '13~18세']}], turn=2)],
       '이용자 지정 연령 구간으로 나누기')

dialog(9, '공무원연금 담당자',
       ['2022년 12월 31일 기준 공무원연금 가입자는 몇 명입니까?',
        '그럼 여성만 보면?',
        '그 여성 가입자들이 2022년 한 해 납부한 공무원연금 보험료(본인부담) 평균은 얼마입니까?'],
       [S('count', 'govp_yn2 == 1', turn=1),
        S('count', 'govp_yn2 == 1 and gender == 2', turn=2),
        S('mean', 'govp_yn2 == 1 and gender == 2', value_var='govp_premium_amt', turn=3)],
       '고정시점 가입 여부(0값 있음) 유지, 성별 한정 뒤 금액 평균')

dialog(10, '여성가족 정책 연구자',
       ['2022년 한 해 동안 육아휴직급여(사후지급금 제외)를 받은 사람 중에 남성이 차지하는 비율이 얼마나 돼요?',
        '연간 말고 2022년 12월 기준 수급자로 바꾸면요?',
        '방금 것을 비율 말고 인원으로 알려 줘요.'],
       [S('rate', 'empins_parentleave_yn1 == 1', numerator='gender == 1', turn=1),
        S('rate', 'empins_parentleave_yn2 == 1', numerator='gender == 1', turn=2),
        S('count', 'empins_parentleave_yn2 == 1 and gender == 1', turn=3)],
       '기준 시점 교체(연간→12월) 뒤 비율→인원 전환')

# ---------------------------------------------------------------- G 묶음
G = []


def code_item(no, defect, persona, intent, code, spec, note):
    q = intent + '\n```python\n' + code.strip('\n') + '\n```'
    G.append({'id': f'G{no:02d}', 'stratum': 'G', 'defect': defect, 'persona': persona, 'turns': [q],
              'expect': 'compute', 'specs': [spec], 'note': note})


code_item(1, '분모 누락', '지자체 노인복지 담당자',
          '65세 이상 노인 가운데 2022년에 노인맞춤돌봄서비스를 한 번이라도 이용한 사람의 비율을 시도별로 보려고 합니다. 아래 코드가 그 의도대로 짜였는지 확인하고, 문제가 있으면 고쳐서 실행해 주세요.',
          """
import ssda
r = ssda.rate('oldcare_yn1 == 1', by='sido', label='시도별 노인맞춤돌봄서비스 이용률')
print(r)
""",
          S('rate', 'age >= 65', numerator='oldcare_yn1 == 1', by=SIDO),
          'where 가 없어 분모가 전체 인구가 됨. 의도는 65세 이상')

code_item(2, '분모 누락(조건 일부)', '장애인복지 담당자',
          '장애 정도가 심한 등록장애인(종합장애정도 기준)만을 분모로 해서, 2022년 한 해 동안 장애인활동지원을 이용한(자격 기준) 사람의 비율을 성별로 구하려는 코드입니다. 제대로 된 건지 봐 주시고 결과도 뽑아 주세요.',
          """
import ssda
ssda.open_data()
r = ssda.rate('disvou_act_yn1 == 1', where='dis_yn == 1', by='sex')
print(r)
""",
          S('rate', 'dis_yn == 1 and dis_grade_1 == 1', numerator='disvou_act_yn1 == 1', by=SEX),
          '분모에 종합장애정도(심한 장애) 조건이 빠져 등록장애인 전체가 분모가 됨')

code_item(3, '유사 변수(연간↔12월)', '고용정책 담당자',
          '2022년 12월 31일 기준으로 국민취업지원제도에 참여 중인 사람 수를 성별로 세려고 합니다. 이 코드 맞나요? 틀린 데가 있으면 고쳐서 돌려 주세요.',
          """
import ssda
r = ssda.count(where='kua_yn1 == 1', by='sex')
print(r)
""",
          S('count', 'kua_yn2 == 1', by=SEX),
          '고정시점 참여 여부를 써야 하는데 연간 참여 여부를 씀')

code_item(4, '유사 변수(가구↔개인)', '소득분배 연구자',
          '가구 단위 분석입니다. 가구원 전체의 가처분소득을 합친 가구 가처분소득의 평균을 가구원수별(1인, 2인, 3인, 4인 이상)로 구하려고 아래처럼 작성했습니다. 검토 후 실행 부탁드립니다.',
          """
import ssda
r = ssda.mean('p_dinc', by='hs4', unit='가구', label='가구원수별 가구 가처분소득 평균')
print(r)
""",
          S('mean', '', unit='household', value_var='h_dinc', by=[{'std': 'hs4'}]),
          '가구 합산 소득이 아니라 가구주 개인의 가처분소득을 평균함')

code_item(5, '경계 오류(이상·이하↔초과·미만)', '교육복지 담당자',
          '만 7세 이상 18세 이하 인구 가운데 2022년에 교육급여 수급권을 한 번이라도 가졌던 사람이 몇 명인지 세는 코드예요. 조건이 맞게 들어갔는지 확인하고 실행해 주세요.',
          """
import ssda
r = ssda.count(where='nbls_edu_yn1 == 1 and age > 7 and age < 18')
print(r)
""",
          S('count', 'nbls_edu_yn1 == 1 and age >= 7 and age <= 18'),
          '연령 조건이 초과·미만으로 적혀 양 끝 연령(7세, 18세)이 빠짐')

code_item(6, '연산자 오류(and↔or)', '기초생활보장 담당자',
          '2022년 12월 기준으로 생계급여와 주거급여(임차급여) 가운데 하나라도 받고 있는 사람 수를 연령대 3구간(0~17세, 18~64세, 65세 이상)별로 구하려 합니다. 다음 코드를 점검한 뒤 실행해 주십시오.',
          """
import ssda
r = ssda.count(where='nbls_live_yn2 == 1 and nbls_house_yn2 == 1', by='age3')
print(r)
""",
          S('count', 'nbls_live_yn2 == 1 or nbls_house_yn2 == 1', by=[{'std': 'age3'}]),
          '하나라도(or)인데 둘 다(and)로 결합함')

code_item(7, '단위 오류(개인↔가구)', '통계 담당자',
          '가구주가 65세 이상인 가구가 몇 가구인지 가구원수별(1인, 2인, 3인, 4인 이상)로 알고 싶어서 짠 코드입니다. 가구 수가 나와야 하는데 맞게 짰는지 봐 주세요.',
          """
import ssda
r = ssda.count(where='age >= 65', by='hs4')
print(r)
""",
          S('count', 'age >= 65', unit='household', by=[{'std': 'hs4'}]),
          "unit='가구'가 없어 65세 이상 인구(개인)를 세게 됨")

code_item(8, '분류 기준 오류', '장기요양 연구자',
          '65세 이상 노인을 65~74세, 75~84세, 85세 이상의 세 구간으로 나눠서, 구간별로 2022년에 장기요양 급여를 한 번이라도 받은 사람의 비율을 보려고 합니다. 아래 코드를 확인하고 실행해 주세요.',
          """
import ssda
ssda.define_group('age_old3', 'age', [70, 80], ['65~69세', '70~79세', '80세 이상'])
r = ssda.rate('ltcare_bn_yn == 1', where='age >= 65', by='age_old3')
print(r)
""",
          S('rate', 'age >= 65', numerator='ltcare_bn_yn == 1',
            by=[{'var': 'age', 'bins': [75, 85], 'labels': ['65~74세', '75~84세', '85세 이상']}]),
          '요청한 구간(65~74, 75~84, 85 이상)과 다른 구간(65~69, 70~79, 80 이상)으로 나눔')

code_item(9, '집계 함수 오류(평균↔합계)', '노인일자리 사업 담당자',
          '2022년 한 해 동안 노인일자리 공익활동에 한 번이라도 참여한 사람에게 지급된 활동비의 총액(합계)을 성별로 구하려는 코드입니다. 맞는지 확인하고 돌려 주세요.',
          """
import ssda
r = ssda.mean('oldwork_type1_amt', where='oldwork_type1_yn1 == 1', by='sex')
print(r)
""",
          S('sum', 'oldwork_type1_yn1 == 1', value_var='oldwork_type1_amt', by=SEX),
          '합계를 구해야 하는데 평균 함수를 씀')

code_item(10, '실행 불가(변수명 오류)', '직업훈련 정책 연구자',
          '2022년에 국민내일배움카드 정부지원을 받은 사람들의 연간 정부지원금 중위수를 성별로 보려고 하는데, 아래 코드를 돌리면 오류가 납니다. 고쳐서 결과를 보여 주세요.',
          """
import ssda
r = ssda.quantile('vocaedu_amt', q=0.5, where='vocaedu_yn1 == 1', by='sex')
print(r)
""",
          S('quantile', 'vocaedu_yn == 1', value_var='vocaedu_amt', q=0.5, by=SEX),
          '여부 변수 이름에 없는 접미어(_yn1)를 붙여 없는 변수 오류가 남')

code_item(11, '없음', '건강보험 정책 담당자',
          '65세 이상 인구 중 2022년에 본인부담상한제 지원을 받은 사람의 비율을 소득 5분위별로 구하는 코드입니다. 문제가 없는지 확인하고 실행해 주세요.',
          """
import ssda
r = ssda.rate('nhi_ceiling_subsidy_yn == 1', where='age >= 65', by='inc5')
print(r)
""",
          S('rate', 'age >= 65', numerator='nhi_ceiling_subsidy_yn == 1', by=[{'std': 'inc5'}]),
          '결함 없는 코드. 고칠 곳을 지어내지 않고 그대로 실행하는지 확인')

code_item(12, '없음', '주거·자산 연구자',
          '가구 단위로, 1인 가구 가운데 가구 재산이 1억원 미만인 가구의 비율을 시도별로 구하려고 합니다. 아래 코드가 맞는지 검토하고 결과를 보여 주세요.',
          """
import ssda
r = ssda.rate('h_prop < 100000000', where='hnum == 1', by='sido', unit='가구')
print(r)
""",
          S('rate', 'hnum == 1', unit='household', numerator='h_prop < 100000000', by=SIDO),
          '결함 없는 가구 단위 코드(금액 조건 원 단위, unit 지정)')


def write(name, items):
    path = os.path.join(ITEMS, name)
    with open(path, 'w', encoding='utf-8') as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + '\n')
    print(name, len(items))


if __name__ == '__main__':
    write('C.jsonl', C)
    write('F.jsonl', F)
    write('G.jsonl', G)
