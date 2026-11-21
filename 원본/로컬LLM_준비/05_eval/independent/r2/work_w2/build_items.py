# -*- coding: utf-8 -*-
"""작업자 w2: C(최소 차이 쌍)·F(이어 묻는 대화)·G(코드 확인 요청) 문항을 JSON Lines로 기록."""
import json, os

OUT = '/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r2/items'
SUDO = 'sido in [1, 4, 9]'
NONSUDO = 'sido not in [1, 4, 9]'


def spec(measure, population='', unit='person', by=None, **kw):
    s = {'measure': measure, 'unit': unit, 'population': population}
    s.update(kw)
    s['by'] = by or []
    return s


# ---------------------------------------------------------------- C 묶음
# (쌍 번호, 차이의 종류, 화자, 문장 틀, (a 표현, b 표현), (a 산출 정의, b 산출 정의), 작성 의도)
C = [
    ('C01', '연령 경계(65세 이상 ↔ 75세 이상)', '지자체 복지 담당자',
     '{}세 이상 인구 가운데 2022년 한 해 동안 노인장기요양보험 급여를 한 번이라도 받은 사람의 비율은 얼마인가요?',
     ('65', '75'),
     (spec('rate', 'age >= 65', numerator='ltcare_bn_yn == 1'),
      spec('rate', 'age >= 75', numerator='ltcare_bn_yn == 1')),
     '장기요양 수급률의 분모 연령 하한만 바꾼 쌍'),
    ('C02', '비율 ↔ 인원', '중앙부처 정책 담당자',
     '2022년 한 해 동안 육아휴직급여를 한 번이라도 받은 사람 가운데 남성이 {} 알려주세요.',
     ('몇 퍼센트인지', '몇 명인지'),
     (spec('rate', 'empins_parentleave_yn1 == 1', numerator='gender == 1'),
      spec('count', 'empins_parentleave_yn1 == 1 and gender == 1')),
     '육아휴직급여 연간 수급자 중 남성: 비율을 묻는지 인원을 묻는지만 다름'),
    ('C03', '개인 단위 ↔ 가구 단위', '통계 담당자',
     '저희 과에서 자산 분포 자료를 정리하고 있습니다. 가구 재산이 5억원 이상인 경우의 비율을 {}로 구해 주세요.',
     ('개인 단위(전체 인구 대비)', '가구 단위(전체 가구 대비)'),
     (spec('rate', '', numerator='h_prop >= 500000000'),
      spec('rate', '', unit='household', numerator='h_prop >= 500000000')),
     '같은 가구 재산 조건을 개인 가중과 가구 가중으로 집계할 때의 차이'),
    ('C04', '연간 기준 ↔ 12월 기준', '지자체 복지 담당자',
     '긴급복지지원 생계지원 수급자가 {}으로 몇 명인지 궁금합니다.',
     ('2022년 연간 기준(한 해 동안 한 번이라도 수급)', '2022년 12월 기준'),
     (spec('count', 'aid_live_yn1 == 1'),
      spec('count', 'aid_live_yn2 == 1')),
     '단기 급여인 긴급복지 생계지원의 연간 수급과 12월 시점 수급 구분'),
    ('C05', '평균 ↔ 중위수', '연구자',
     '외래 진료를 이용한 65세 이상 노인의 2022년 연간 외래 본인부담금(의과 의료기관 전체) {} 얼마입니까?',
     ('평균은', '중위수는'),
     (spec('mean', 'age >= 65 and nhi_out_fee.notna()', value_var='nhi_out_fee'),
      spec('quantile', 'age >= 65 and nhi_out_fee.notna()', value_var='nhi_out_fee', q=0.5)),
     '오른쪽으로 치우친 진료비 분포에서 평균과 중위수의 구분'),
    ('C06', '평균 ↔ 합계', '중앙부처 정책 담당자',
     '2022년 12월 기준 장애인연금 수급자가 2022년 한 해 동안 받은 장애인연금 급여액의 {} 알려주십시오.',
     ('평균을', '합계를'),
     (spec('mean', 'disp_yn2 == 1', value_var='disp_amt'),
      spec('sum', 'disp_yn2 == 1', value_var='disp_amt')),
     '같은 대상·같은 변수에서 집계 방식만 평균과 합계로 다름'),
    ('C07', '분모의 차이(전체 인구 중 ↔ 수급자 중)', '지자체 복지 담당자',
     '에너지 취약계층 지원이 실제로 얼마나 닿고 있는지 보려고 합니다. {} 가운데 에너지바우처를 사업기간(2022년 7월~2023년 4월) 동안 한 번이라도 이용한 사람의 비율은 몇 %인가요?',
     ('전체 인구', '2022년 12월 기준 생계급여 수급자'),
     (spec('rate', '', numerator='evou_yn == 1'),
      spec('rate', 'nbls_live_yn2 == 1', numerator='evou_yn == 1')),
     '분자는 같고 분모만 전체 인구와 생계급여 수급자로 다름'),
    ('C08', '「이상」 ↔ 「초과」', '연구자',
     '2022년 한 해 구직급여를 받은 사람 가운데 연간 수급일수가 120일 {}인 사람은 몇 %인가요?',
     ('이상', '초과'),
     (spec('rate', 'unempbn_jobseekbn_yn == 1', numerator='unempbn_jobseekbn_dur >= 120'),
      spec('rate', 'unempbn_jobseekbn_yn == 1', numerator='unempbn_jobseekbn_dur > 120')),
     '수급일수가 정확히 120일인 사람이 많아 경계 포함 여부에 따라 값이 달라짐'),
    ('C09', '「미만」 ↔ 「이하」', '지자체 복지 담당자',
     '2022년 한 해 보육료 지원 받은 아이들 중에 연간 지원기간이 6개월 {}인 아이는 몇 명이야?',
     ('미만', '이하'),
     (spec('count', 'childcare_yn1 == 1 and childcare_dur < 6'),
      spec('count', 'childcare_yn1 == 1 and childcare_dur <= 6')),
     '지원기간 6개월의 경계 포함 여부'),
    ('C10', '「그리고」 ↔ 「또는」', '통계 담당자',
     '2022년 한 해 동안 초·중·고 학생 교육비 지원 가운데 방과후학교 자유수강권 지원과 교육정보화 지원을 {} 받은 사람이 몇 명인지 구해 주세요.',
     ('둘 다', '둘 중 하나라도'),
     (spec('count', 'pubedu_aftsch_yn == 1 and pubedu_pclot_yn == 1'),
      spec('count', 'pubedu_aftsch_yn == 1 or pubedu_pclot_yn == 1')),
     '두 지원의 교집합과 합집합 구분'),
    ('C11', '남 ↔ 여', '연구자',
     '2022년 한 해 동안 공무원연금 정기연금(퇴직연금·유족연금 등)을 받은 {}의 연간 연금액 평균 산출 요망.',
     ('남성', '여성'),
     (spec('mean', 'govp_pension_yn == 1 and gender == 1', value_var='govp_pension_amt'),
      spec('mean', 'govp_pension_yn == 1 and gender == 2', value_var='govp_pension_amt')),
     '직역연금 수급액 평균에서 성별 조건만 다름'),
    ('C12', '시도만 다른 경우(부산 ↔ 대구)', '지자체 복지 담당자',
     '{} 주거급여(임차급여) 수급자 수, 2022년 12월 기준으로 알려주세요.',
     ('부산', '대구'),
     (spec('count', 'sido == 2 and nbls_house_yn2 == 1'),
      spec('count', 'sido == 3 and nbls_house_yn2 == 1')),
     '시도 코드의 대응(부산 2, 대구 3) 확인'),
    ('C13', '지역 묶음(수도권 ↔ 비수도권)', '중앙부처 정책 담당자',
     '지역별 근로빈곤층 지원 수준을 비교하는 보고서를 쓰고 있습니다. {}에 사는 근로장려금 수급 대상자(2022년 기준)의 근로장려금 심사금액 평균을 알려주세요.',
     ('수도권(서울·인천·경기)', '비수도권(서울·인천·경기를 뺀 나머지 시도)'),
     (spec('mean', 'itc_yn == 1 and ' + SUDO, value_var='itc_amt'),
      spec('mean', 'itc_yn == 1 and ' + NONSUDO, value_var='itc_amt')),
     '여러 시도를 묶은 지역 조건(수도권과 그 여집합)'),
    ('C14', '수급자 ↔ 비수급자', '연구자',
     '65세 이상 인구 가운데 2022년 한 해 동안 국민연금 정기연금(노령·장애·유족연금)을 {} 사람들의 상대 빈곤율을 구해 주세요.',
     ('받은', '받지 않은'),
     (spec('poverty_rate', 'age >= 65 and np_pension_yn == 1'),
      spec('poverty_rate', 'age >= 65 and np_pension_yn.isna()')),
     '비수급자는 여부 변수의 결측으로 판별해야 함'),
    ('C15', '분류 기준만 다른 경우(성 ↔ 의료급여 종별)', '통계 담당자',
     '2022년 12월 기준 의료급여 수급권자 수, {}로 나눠서 표로 부탁드립니다.',
     ('성별', '종별(1종·2종)'),
     (spec('count', 'nbls_medi_yn2 == 1', by=[{'std': 'sex'}]),
      spec('count', 'nbls_medi_yn2 == 1', by=[{'cat': 'nbls_medi_type'}])),
     '같은 대상의 인원을 표준 분류(성)와 범주형 변수(종별)로 나누는 차이'),
]

# ---------------------------------------------------------------- F 묶음
AGE_OLD3 = {'var': 'age', 'bins': [75, 85], 'labels': ['65~74세', '75~84세', '85세 이상']}
REGION2 = {'groups': [{'label': '수도권', 'cond': SUDO}, {'label': '비수도권', 'cond': NONSUDO}]}

F = [
    ('F01', '연구자',
     ['2022년에 입원한 적이 있는 65세 이상 노인의 연간 입원 재원일수(의과 의료기관 전체) 평균이 며칠인지 알려 주세요.',
      '그럼 여성만 보면요?',
      '그걸 65~74세, 75~84세, 85세 이상으로 나눠 주세요.'],
     [spec('mean', 'age >= 65 and nhi_in_dur.notna()', value_var='nhi_in_dur'),
      spec('mean', 'age >= 65 and gender == 2 and nhi_in_dur.notna()', value_var='nhi_in_dur'),
      spec('mean', 'age >= 65 and gender == 2 and nhi_in_dur.notna()', value_var='nhi_in_dur', by=[AGE_OLD3])],
     '건강보험 입원 실적: 성 조건을 더한 뒤 그 상태로 이용자 지정 연령 구간을 적용'),
    ('F02', '중앙부처 정책 담당자',
     ['18~64세 인구 중 2022년 12월 말 기준 고용보험 가입자 비율이 궁금합니다.',
      '같은 기준으로 18~34세 청년층은 어떤가요?',
      '방금 것을 비율 말고 인원으로 알려주세요.'],
     [spec('rate', 'age >= 18 and age <= 64', numerator='empins_yn2 == 1'),
      spec('rate', 'age >= 18 and age <= 34', numerator='empins_yn2 == 1'),
      spec('count', 'age >= 18 and age <= 34 and empins_yn2 == 1')],
     '고용보험: 연령 범위 교체 뒤 비율을 해당 인원으로 전환'),
    ('F03', '지자체 복지 담당자',
     ['2022년 12월 말 기준 등록장애인 가운데 장애 정도가 심한 장애인의 비율을 구해 주세요.',
      '그걸 65세 미만과 65세 이상으로 나눠 주세요.'],
     [spec('rate', 'dis_yn == 1', numerator='dis_grade_1 == 1'),
      spec('rate', 'dis_yn == 1', numerator='dis_grade_1 == 1',
           by=[{'var': 'age', 'bins': [65], 'labels': ['65세 미만', '65세 이상']}])],
     '장애: 앞 차례의 비율에 이용자 지정 2구간 분류를 추가'),
    ('F04', '지자체 복지 담당자',
     ['2022년 12월 기준으로 보육료 지원을 받고 있는 아동이 몇 명이야?',
      '그 아이들이 2022년 한 해 동안 받은 보육료 지원액은 1인당 평균 얼마야?',
      '평균 말고 합계로 보여줘.'],
     [spec('count', 'childcare_yn2 == 1'),
      spec('mean', 'childcare_yn2 == 1', value_var='childcare_amt'),
      spec('sum', 'childcare_yn2 == 1', value_var='childcare_amt')],
     '보육: 인원 → 같은 대상의 금액 평균 → 합계(구어체)'),
    ('F05', '통계 담당자',
     ['가구주가 65세 이상인 가구의 가구 재산 중위수를 가구 단위로 구해 주십시오.',
      '그것을 가구원수(1인, 2인, 3인, 4인 이상)별로 나누어 주십시오.'],
     [spec('quantile', 'age >= 65', unit='household', value_var='h_prop', q=0.5),
      spec('quantile', 'age >= 65', unit='household', value_var='h_prop', q=0.5, by=[{'std': 'hs4'}])],
     '재산: 가구 단위 중위수에 가구원수 분류를 추가(가구 단위 유지)'),
    ('F06', '연구자',
     ['2022년 한 해 노인장기요양보험 급여 수급자 가운데 방문요양 서비스를 이용한 사람의 비율은 얼마인가요?',
      '주야간보호 서비스는요?',
      '그걸 성별로 나눠서 보여 주세요.'],
     [spec('rate', 'ltcare_bn_yn == 1', numerator='ltcare_visit_yn == 1'),
      spec('rate', 'ltcare_bn_yn == 1', numerator='ltcare_daynight_yn == 1'),
      spec('rate', 'ltcare_bn_yn == 1', numerator='ltcare_daynight_yn == 1', by=[{'std': 'sex'}])],
     '장기요양: 분모는 유지하고 분자(서비스 종류)만 바꾼 뒤 성 분류 추가'),
    ('F07', '지자체 복지 담당자',
     ['2022년 한 해 동안 긴급복지지원 생계지원을 한 번이라도 받은 사람이 몇 명인지 알려 주세요.',
      '그중 1인 가구인 사람의 비율은요?'],
     [spec('count', 'aid_live_yn1 == 1'),
      spec('rate', 'aid_live_yn1 == 1', numerator='hnum == 1')],
     '긴급복지: 앞 차례의 집단을 분모로 삼는 비율로 전환'),
    ('F08', '중앙부처 정책 담당자',
     ['7~18세 아동·청소년 가운데 2022년 한 해 방과후학교 자유수강권 지원을 받은 비율을 구해 주세요.',
      '그걸 수도권(서울·인천·경기)과 비수도권으로 나눠 주세요.',
      '같은 지역 구분으로, 지원을 받은 7~18세의 1인당 연간 지원액 평균도 알려 주세요.'],
     [spec('rate', 'age >= 7 and age <= 18', numerator='pubedu_aftsch_yn == 1'),
      spec('rate', 'age >= 7 and age <= 18', numerator='pubedu_aftsch_yn == 1', by=[REGION2]),
      spec('mean', 'age >= 7 and age <= 18 and pubedu_aftsch_yn == 1', value_var='pubedu_aftsch_amt', by=[REGION2])],
     '교육비 지원: 지역 묶음 분류 추가 뒤 분류를 유지한 채 지표를 금액 평균으로 교체'),
    ('F09', '연구자',
     ['2022년 한 해 공무원연금 정기연금 수급자의 연간 연금액 평균은 얼마입니까?',
      '평균 말고 중위수로는요?',
      '같은 중위수를 사립학교교직원연금 정기연금 수급자(2022년 한 해 수급)에 대해서도 구해 주십시오.'],
     [spec('mean', 'govp_pension_yn == 1', value_var='govp_pension_amt'),
      spec('quantile', 'govp_pension_yn == 1', value_var='govp_pension_amt', q=0.5),
      spec('quantile', 'privschp_pension_yn == 1', value_var='privschp_pension_amt', q=0.5)],
     '직역연금: 평균 → 중위수 → 같은 지표를 다른 제도(사학연금)에 적용'),
    ('F10', '중앙부처 정책 담당자',
     ['2022년 한 해 육아휴직급여를 받은 사람 수를 성별로 알려주세요.',
      '그 사람들의 2022년 평균 수급기간(개월)도 성별로 보여주세요.',
      '그럼 여성 중에서 30대(30~39세)만 보면 평균 수급기간이 얼마나 되나요?'],
     [spec('count', 'empins_parentleave_yn1 == 1', by=[{'std': 'sex'}]),
      spec('mean', 'empins_parentleave_yn1 == 1', value_var='empins_parentleave_dur', by=[{'std': 'sex'}]),
      spec('mean', 'empins_parentleave_yn1 == 1 and gender == 2 and age >= 30 and age <= 39',
           value_var='empins_parentleave_dur')],
     '모성보호: 인원 → 기간 평균(분류 유지) → 성·연령 조건으로 좁힘'),
]

# ---------------------------------------------------------------- G 묶음
def code(*lines):
    return '\n\n```python\n' + '\n'.join(lines) + '\n```'


G = [
    ('G01', '분모(대상 집단) 누락', '지자체 복지 담당자',
     '만 0~5세 아동 가운데 2022년 12월 기준으로 보육료 지원을 받고 있는 아동의 비율을 구하려고 아래 코드를 짰습니다. '
     '맞게 짠 건지 확인해 주시고, 문제가 있으면 고쳐서 실행해 주세요.'
     + code('import ssda', "r = ssda.rate('childcare_yn2 == 1')", 'print(r)'),
     spec('rate', 'age <= 5', numerator='childcare_yn2 == 1'),
     '분모 조건(where)이 빠져 전체 인구 대비 비율이 됨'),
    ('G02', '없음', '연구자',
     '65세 이상 인구 가운데 2022년 한 해 동안 노인일자리 공익활동에 한 번이라도 참여한 사람의 비율을 '
     '65~74세, 75~84세, 85세 이상 세 구간으로 나눠 보려고 합니다. 아래 코드를 그대로 돌려도 되는지 봐 주시고 결과도 알려 주세요.'
     + code('import ssda',
            "ssda.define_group('age_old3', 'age', [75, 85], ['65~74세', '75~84세', '85세 이상'])",
            "r = ssda.rate('oldwork_type1_yn1 == 1', where='age >= 65', by='age_old3')",
            'print(r)'),
     spec('rate', 'age >= 65', numerator='oldwork_type1_yn1 == 1', by=[AGE_OLD3]),
     '결함 없는 코드. 첫 구간의 하한은 분모 조건(65세 이상)으로 정해지므로 구간 정의가 맞음'),
    ('G03', '비슷하지만 다른 변수 사용(연간 ↔ 12월)', '중앙부처 정책 담당자',
     '국민취업지원제도에 2022년 12월 기준으로 참여 중인 사람이 몇 명인지 참여유형(1유형, 2유형)별로 보고 싶어요. '
     '이렇게 하면 되나요? 틀린 데 있으면 고쳐서 돌려 주세요.'
     + code('import ssda', "r = ssda.count(where='kua_yn1 == 1', by='kua_type')", 'print(r)'),
     spec('count', 'kua_yn2 == 1', by=[{'cat': 'kua_type'}]),
     '12월 기준을 요구했으나 연간 참여 여부 변수를 씀'),
    ('G04', '조건의 경계 오류(이상 ↔ 초과)', '지자체 복지 담당자',
     '65세 이상 인구 가운데 2022년 12월 기준 노인맞춤돌봄서비스 이용자의 비율을 성별로 산출하는 코드입니다. '
     '검토 후 실행 부탁드립니다. 잘못된 부분이 있으면 수정해 주십시오.'
     + code('import ssda', "r = ssda.rate('oldcare_yn2 == 1', where='age > 65', by='sex')", 'print(r)'),
     spec('rate', 'age >= 65', numerator='oldcare_yn2 == 1', by=[{'std': 'sex'}]),
     '65세 이상을 age > 65로 써서 65세가 분모에서 빠짐'),
    ('G05', '단위(개인 ↔ 가구) 오류', '통계 담당자',
     '전체 가구 중에서 가구 가처분소득이 연 3천만원 미만인 가구의 비율을 시도별로, 가구 단위로 구하고 싶습니다. '
     '아래 코드가 맞는지 확인하고 실행해 주세요. 맞지 않으면 고쳐 주시고요.'
     + code('import ssda', "r = ssda.rate('h_dinc < 30000000', by='sido')", 'print(r)'),
     spec('rate', '', unit='household', numerator='h_dinc < 30000000', by=[{'std': 'sido'}]),
     "unit='가구'가 빠져 개인 가중 비율이 됨"),
    ('G06', '실행되지 않는 코드(인자 이름 오류)', '지자체 복지 담당자',
     '2022년 한 해 문화누리카드(통합문화이용권)를 이용한 사람의 연간 결제액 평균을 성별로 뽑으려는데, 아래 코드를 돌리면 오류가 나요. '
     '고쳐서 결과 좀 보여 주세요.'
     + code('import ssda', "r = ssda.mean('culvou_bn', where='culvou_yn == 1', groupby='sex')", 'print(r)'),
     spec('mean', 'culvou_yn == 1', value_var='culvou_bn', by=[{'std': 'sex'}]),
     '분류 기준 인자 이름이 by가 아니라 groupby로 적혀 실행되지 않음'),
    ('G07', '조건의 연산자 오류(또는 ↔ 그리고)', '연구자',
     '2022년 한 해 동안 공무원연금, 사립학교교직원연금, 군인연금 가운데 하나라도 정기연금을 받은 사람이 모두 몇 명인지 세려고 합니다. '
     '코드를 봐 주시고, 틀렸으면 바로잡아 실행해 주세요.'
     + code('import ssda',
            "r = ssda.count(where='govp_pension_yn == 1 and privschp_pension_yn == 1 and milip_pension_yn == 1')",
            'print(r)'),
     spec('count', 'govp_pension_yn == 1 or privschp_pension_yn == 1 or milip_pension_yn == 1'),
     '「하나라도」를 and로 이어 세 연금을 모두 받는 사람(해당 없음)을 세게 됨'),
    ('G08', '분류 기준 오류', '연구자',
     '외래 진료 이용자의 2022년 연간 외래 내원일수(의과 의료기관 전체) 평균을 10세 단위 연령대별로 보려고 합니다. '
     '아래 코드로 되는지 확인해서 실행해 주세요. 요구와 다르면 고쳐 주세요.'
     + code('import ssda', "r = ssda.mean('nhi_out_dur', by='age6')", 'print(r)'),
     spec('mean', 'nhi_out_dur.notna()', value_var='nhi_out_dur', by=[{'std': 'age10'}]),
     '10세 단위를 요구했으나 6구간 연령대(age6)를 씀'),
    ('G09', '분모(대상 집단) 누락', '중앙부처 정책 담당자',
     '등록장애인(2022년 12월 말 기준) 중 2022년 한 해 동안 장애인활동지원 서비스를 한 번이라도 이용한 사람의 비율을 성별로 알고 싶습니다. '
     '이 코드 맞나요? 아니면 고쳐서 돌려 주세요.'
     + code('import ssda', "r = ssda.rate('disvou_act_yn1 == 1', by='sex')", 'print(r)'),
     spec('rate', 'dis_yn == 1', numerator='disvou_act_yn1 == 1', by=[{'std': 'sex'}]),
     '분모가 등록장애인이어야 하나 where가 없어 전체 인구 대비 비율이 됨'),
    ('G10', '집계 함수 오류(합계 ↔ 평균)', '통계 담당자',
     '근로장려금 수급 대상자(2022년 기준)의 근로장려금 심사금액 합계(총액)를 가구 구성(단독·홑벌이·맞벌이)별로 내고 싶습니다. '
     '아래 코드 확인 후 실행 바랍니다. 문제가 있으면 수정해 주세요.'
     + code('import ssda', "r = ssda.mean('itc_amt', where='itc_yn == 1', by='itc_hmember')", 'print(r)'),
     spec('sum', 'itc_yn == 1', value_var='itc_amt', by=[{'cat': 'itc_hmember'}]),
     '합계를 요구했으나 평균 함수를 씀'),
    ('G11', '비슷하지만 다른 변수 사용(가구 ↔ 개인 변수)', '통계 담당자',
     '가구 단위로 본 가구 재산 평균을 가구원수(1인·2인·3인·4인 이상)별로 구하려고 합니다. '
     '맞게 짰는지 봐주시고 실행해 주세요. 틀렸으면 고쳐서요.'
     + code('import ssda', "r = ssda.mean('p_prop', by='hs4', unit='가구')", 'print(r)'),
     spec('mean', '', unit='household', value_var='h_prop', by=[{'std': 'hs4'}]),
     '가구 재산이 아니라 가구주 개인 재산 변수를 씀'),
    ('G12', '없음', '연구자',
     '18~59세 인구 가운데 2022년 한 해 동안 국민연금에 한 번도 가입한 적이 없는 사람이 몇 명인지 성별로 확인하려고 합니다. '
     '이대로 실행해도 되는지 확인하고 결과를 알려주세요.'
     + code('import ssda', "r = ssda.count(where='age >= 18 and age <= 59 and isna(np_yn)', by='sex')", 'print(r)'),
     spec('count', 'age >= 18 and age <= 59 and np_yn.isna()', by=[{'std': 'sex'}]),
     '결함 없는 코드. 미가입자를 여부 변수의 결측(isna)으로 판별한 것이 규약에 맞음'),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for pid, diff, persona, tpl, (xa, xb), (sa, sb), note in C:
        for suf, x, s in (('a', xa, sa), ('b', xb, sb)):
            rows.append({'id': pid + suf, 'stratum': 'C', 'pair': pid, 'diff': diff, 'persona': persona,
                         'turns': [tpl.format(x)], 'expect': 'compute', 'specs': [s], 'note': note})
    with open(os.path.join(OUT, 'C.jsonl'), 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    with open(os.path.join(OUT, 'F.jsonl'), 'w', encoding='utf-8') as f:
        for fid, persona, turns, specs, note in F:
            ss = []
            for i, s in enumerate(specs, 1):
                t = {'turn': i}
                t.update(s)
                ss.append(t)
            f.write(json.dumps({'id': fid, 'stratum': 'F', 'persona': persona, 'turns': turns,
                                'expect': 'compute', 'specs': ss, 'note': note}, ensure_ascii=False) + '\n')

    with open(os.path.join(OUT, 'G.jsonl'), 'w', encoding='utf-8') as f:
        for gid, defect, persona, q, s, note in G:
            f.write(json.dumps({'id': gid, 'stratum': 'G', 'defect': defect, 'persona': persona, 'turns': [q],
                                'expect': 'compute', 'specs': [s], 'note': note}, ensure_ascii=False) + '\n')
    print('written', len(rows), len(F), len(G))


if __name__ == '__main__':
    main()
