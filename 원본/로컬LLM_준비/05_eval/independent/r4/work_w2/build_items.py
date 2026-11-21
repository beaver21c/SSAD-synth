# -*- coding: utf-8 -*-
"""C·F·G 묶음 문항을 JSON Lines로 내보내는 스크립트(독립 문항 작성자 w2)."""
import json
import os

OUT = '/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/r4/items'


def P(measure, population='', unit='person', by=None, **kw):
    """산출 정의 1개."""
    s = {'measure': measure, 'unit': unit, 'population': population}
    for k in ('numerator', 'value_var', 'q'):
        if k in kw:
            s[k] = kw[k]
    s['by'] = by or []
    if 'turn' in kw:
        s = dict([('turn', kw['turn'])] + list(s.items()))
    return s


SEX = [{'std': 'sex'}]
SIDO = [{'std': 'sido'}]

# ---------------------------------------------------------------- C 묶음
C = []


def pair(no, persona, diff, qa, qb, sa, sb, note):
    pid = 'C%02d' % no
    for suf, q, s in (('a', qa, sa), ('b', qb, sb)):
        C.append({'id': pid + suf, 'stratum': 'C', 'pair': pid, 'diff': diff, 'persona': persona,
                  'turns': [q], 'expect': 'compute', 'specs': [s], 'note': note})


pair(1, '지자체 노인복지 담당자', '연령 경계(65세 이상 ↔ 75세 이상)',
     '65세 이상 인구 중에서 2022년 노인장기요양 급여 수급자가 차지하는 비율이 몇 %인지 알려 주세요.',
     '75세 이상 인구 중에서 2022년 노인장기요양 급여 수급자가 차지하는 비율이 몇 %인지 알려 주세요.',
     P('rate', 'age >= 65', numerator='ltcare_bn_yn == 1'),
     P('rate', 'age >= 75', numerator='ltcare_bn_yn == 1'),
     '분모의 연령 하한만 다름. 장기요양 수급률')

pair(2, '고용정책 연구자', '비율 ↔ 인원',
     '18~64세 인구 가운데 2022년 한 해 동안 구직급여(실업급여)를 한 번이라도 받은 사람의 비율을 구해 주세요.',
     '18~64세 인구 가운데 2022년 한 해 동안 구직급여(실업급여)를 한 번이라도 받은 사람의 인원을 구해 주세요.',
     P('rate', 'age >= 18 and age <= 64', numerator='unempbn_jobseekbn_yn == 1'),
     P('count', 'age >= 18 and age <= 64 and unempbn_jobseekbn_yn == 1'),
     '같은 대상·조건에서 산출 종류만 다름(연간 구직급여)')

pair(3, '통계 담당자', '개인 단위 ↔ 가구 단위',
     '가구 재산이 3억원 이상인 가구가 차지하는 비중을 가구 단위(전체 가구 수 대비 해당 가구 수)로 계산해 줘.',
     '가구 재산이 3억원 이상인 가구가 차지하는 비중을 개인 단위(전체 인구 대비 해당 가구에 속한 사람 수)로 계산해 줘.',
     P('rate', '', unit='household', numerator='h_prop >= 300000000'),
     P('rate', '', unit='person', numerator='h_prop >= 300000000'),
     '같은 가구 재산 조건에서 집계 단위(가구 가중 ↔ 개인 가중)만 다름')

pair(4, '모성보호 제도 담당 사무관', '연간 기준 ↔ 12월 기준',
     '육아휴직급여 수급자 수를 2022년 연간 기준(한 해 동안 한 번이라도 받은 사람)으로 알려 주세요.',
     '육아휴직급여 수급자 수를 2022년 12월 기준(12월 시점에 받고 있는 사람)으로 알려 주세요.',
     P('count', 'empins_parentleave_yn1 == 1'),
     P('count', 'empins_parentleave_yn2 == 1'),
     '수급 여부의 기준 시점만 다름. 12월 변수에는 0값이 있어 == 1로 판별')

pair(5, '공적연금 연구자', '평균 ↔ 중위수',
     '2022년에 공무원연금 정기연금을 받은 사람들의 연간 급여액 평균은 얼마인가요?',
     '2022년에 공무원연금 정기연금을 받은 사람들의 연간 급여액 중위수는 얼마인가요?',
     P('mean', 'govp_pension_yn == 1', value_var='govp_pension_amt'),
     P('quantile', 'govp_pension_yn == 1', value_var='govp_pension_amt', q=0.5),
     '직역연금 급여액의 대푯값 종류만 다름')

pair(6, '지자체 긴급복지 담당자', '평균 ↔ 합계',
     '2022년 연간 긴급복지 생계지원 수급자의 생계지원 급여액 1인당 평균 산출 요청.',
     '2022년 연간 긴급복지 생계지원 수급자의 생계지원 급여액 전체 합계 산출 요청.',
     P('mean', 'aid_live_yn1 == 1', value_var='aid_live_amt'),
     P('sum', 'aid_live_yn1 == 1', value_var='aid_live_amt'),
     '보고서 문체. 같은 수급자 집단에서 집계 함수만 다름')

pair(7, '장애인정책 담당자', '분모(전체 인구 ↔ 등록장애인)',
     '전체 인구 중 2022년 12월 기준 장애인연금 수급자가 차지하는 비율은?',
     '등록장애인 중 2022년 12월 기준 장애인연금 수급자가 차지하는 비율은?',
     P('rate', '', numerator='disp_yn2 == 1'),
     P('rate', 'dis_yn == 1', numerator='disp_yn2 == 1'),
     '분자는 같고 분모 집단만 다름. 짧은 질문')

pair(8, '노인돌봄 사업 담당자', '「이상」 ↔ 「초과」',
     '2022년 한 해 동안 노인맞춤돌봄서비스를 이용한 사람 가운데 연간 이용기간이 6개월 이상인 사람의 비율을 알려 주세요.',
     '2022년 한 해 동안 노인맞춤돌봄서비스를 이용한 사람 가운데 연간 이용기간이 6개월 초과인 사람의 비율을 알려 주세요.',
     P('rate', 'oldcare_yn1 == 1', numerator='oldcare_dur >= 6'),
     P('rate', 'oldcare_yn1 == 1', numerator='oldcare_dur > 6'),
     '개월 단위 변수의 경계 포함 여부만 다름')

pair(9, '건강보험 연구자', '「미만」 ↔ 「이하」',
     '입원 이용 양상을 보고 있습니다. 2022년에 입원 진료를 받은 사람 중에서 연간 입원 재원일수가 7일 미만인 사람은 몇 %인가요?',
     '입원 이용 양상을 보고 있습니다. 2022년에 입원 진료를 받은 사람 중에서 연간 입원 재원일수가 7일 이하인 사람은 몇 %인가요?',
     P('rate', 'nhi_in_dur > 0', numerator='nhi_in_dur < 7'),
     P('rate', 'nhi_in_dur > 0', numerator='nhi_in_dur <= 7'),
     '일 단위 변수의 경계 포함 여부만 다름. 분모는 입원 재원일수가 있는 사람')

pair(10, '교육청 교육복지 담당자', '「그리고」 ↔ 「또는」(둘 다 ↔ 하나라도)',
     '2022년에 초·중·고 학생 교육비 지원 중 방과후학교 자유수강권과 교육정보화 지원 두 가지를 모두 받은 사람은 몇 명입니까?',
     '2022년에 초·중·고 학생 교육비 지원 중 방과후학교 자유수강권과 교육정보화 지원 두 가지 가운데 하나라도 받은 사람은 몇 명입니까?',
     P('count', 'pubedu_aftsch_yn == 1 and pubedu_pclot_yn == 1'),
     P('count', 'pubedu_aftsch_yn == 1 or pubedu_pclot_yn == 1'),
     '두 지원 조건의 결합 방식(교집합 ↔ 합집합)만 다름')

pair(11, '노인일자리 사업 담당자', '남 ↔ 여',
     '2022년 한 해 동안 노인일자리 공익활동에 참여한 남성은 모두 몇 명인가요?',
     '2022년 한 해 동안 노인일자리 공익활동에 참여한 여성은 모두 몇 명인가요?',
     P('count', 'oldwork_type1_yn1 == 1 and gender == 1'),
     P('count', 'oldwork_type1_yn1 == 1 and gender == 2'),
     '성별 조건만 다름')

pair(12, '보육정책 연구자', '시도(부산 ↔ 대구)',
     '광역시끼리 비교하는 표를 만드는 중입니다. 부산에 사는 만 6세 이하 아동 중 2022년 한 해 동안 보육료 지원을 받은 적이 있는 아동의 비율을 구해 주세요.',
     '광역시끼리 비교하는 표를 만드는 중입니다. 대구에 사는 만 6세 이하 아동 중 2022년 한 해 동안 보육료 지원을 받은 적이 있는 아동의 비율을 구해 주세요.',
     P('rate', 'sido == 2 and age <= 6', numerator='childcare_yn1 == 1'),
     P('rate', 'sido == 3 and age <= 6', numerator='childcare_yn1 == 1'),
     '시도 한 곳만 다름. 배경 설명이 붙은 긴 요청')

pair(13, '주거복지 담당자', '지역 묶음(수도권 ↔ 비수도권)',
     '수도권(서울·인천·경기) 인구 중 2022년 12월 기준 주거급여 임차급여 수급자의 비율은 얼마입니까?',
     '비수도권(서울·인천·경기 외 지역) 인구 중 2022년 12월 기준 주거급여 임차급여 수급자의 비율은 얼마입니까?',
     P('rate', 'sido in [1, 4, 9]', numerator='nbls_house_yn2 == 1'),
     P('rate', 'sido not in [1, 4, 9]', numerator='nbls_house_yn2 == 1'),
     '시도 묶음만 다름. 12월 기준 수급 여부는 == 1로 판별')

pair(14, '노후소득보장 연구자', '수급자 ↔ 비수급자',
     '65세 이상 인구 가운데 2022년 한 해 동안 국민연금 정기연금을 받은 사람들의 상대 빈곤율을 구해 주세요.',
     '65세 이상 인구 가운데 2022년 한 해 동안 국민연금 정기연금을 받지 않은 사람들의 상대 빈곤율을 구해 주세요.',
     P('poverty_rate', 'age >= 65 and np_pension_yn == 1'),
     P('poverty_rate', 'age >= 65 and not (np_pension_yn == 1)'),
     '대상 집단의 수급 여부만 다름. 빈곤선은 전체 인구 기준')

pair(15, '직업훈련 정책 담당자', '분류 기준(성 ↔ 소득 5분위)',
     '2022년에 국민내일배움카드 정부지원을 받은 사람 수를 성별로 나눠서 보여 주세요.',
     '2022년에 국민내일배움카드 정부지원을 받은 사람 수를 소득 5분위별로 나눠서 보여 주세요.',
     P('count', 'vocaedu_yn == 1', by=SEX),
     P('count', 'vocaedu_yn == 1', by=[{'std': 'inc5'}]),
     '대상은 같고 분류 기준만 다름')

# ---------------------------------------------------------------- F 묶음
F = []


def dialog(no, persona, turns, specs, note):
    F.append({'id': 'F%02d' % no, 'stratum': 'F', 'persona': persona, 'turns': turns,
              'expect': 'compute', 'specs': specs, 'note': note})


dialog(1, '건강보험 연구자',
       ['2022년에 입원 진료를 받은 사람들의 연간 평균 입원 재원일수는 며칠인가요?',
        '그럼 여성만 놓고, 연령대 3구간(0~17세, 18~64세, 65세 이상)으로 나눠서 보면요?'],
       [P('mean', 'nhi_in_dur > 0', value_var='nhi_in_dur', turn=1),
        P('mean', 'nhi_in_dur > 0 and gender == 2', value_var='nhi_in_dur', by=[{'std': 'age3'}], turn=2)],
       '둘째 차례에서 대상 한정(여성)과 분류 추가를 한꺼번에 요청')

dialog(2, '보육정책 담당자',
       ['만 6세 이하 아동 가운데 2022년 한 해 동안 보육료 지원을 한 번이라도 받은 아동의 비율을 알려 주세요.',
        '방금 것을 비율 말고 인원으로 알려 주세요.',
        '그 인원을 시도별로 나눠 주세요.'],
       [P('rate', 'age <= 6', numerator='childcare_yn1 == 1', turn=1),
        P('count', 'age <= 6 and childcare_yn1 == 1', turn=2),
        P('count', 'age <= 6 and childcare_yn1 == 1', by=SIDO, turn=3)],
       '비율 → 인원 → 시도별 분류로 이어짐. 연령 조건과 연간 기준이 유지되어야 함')

dialog(3, '고용보험 담당자',
       ['18~64세 인구 중에서 2022년 12월 말 기준으로 고용보험에 가입해 있는 사람의 비율을 성별로 보여 줘.',
        '같은 기준으로 18~34세 청년만 보면?'],
       [P('rate', 'age >= 18 and age <= 64', numerator='empins_yn2 == 1', by=SEX, turn=1),
        P('rate', 'age >= 18 and age <= 34', numerator='empins_yn2 == 1', by=SEX, turn=2)],
       '구어체. 둘째 차례는 분모 연령만 바뀌고 12월 기준·성별 분류는 유지')

dialog(4, '장애인정책 연구자',
       ['2022년 12월 말 기준 등록장애인 가운데 장애 정도가 심한 장애인의 비율이 얼마나 됩니까?',
        '그걸 성별로 나눠 주세요.',
        '같은 기준으로 65세 이상 장애인만 보면 어떻게 됩니까?'],
       [P('rate', 'dis_yn == 1', numerator='dis_grade_1 == 1', turn=1),
        P('rate', 'dis_yn == 1', numerator='dis_grade_1 == 1', by=SEX, turn=2),
        P('rate', 'dis_yn == 1 and age >= 65', numerator='dis_grade_1 == 1', by=SEX, turn=3)],
       '셋째 차례는 성별 분류를 유지한 채 대상을 65세 이상 등록장애인으로 좁힘')

dialog(5, '통계 담당자',
       ['가구 단위로 가구 재산의 평균을 구해 줘. 재산이 0원인 가구도 포함해서.',
        '평균 말고 중위수로 다시.',
        '그 중위수를 가구원수(1인, 2인, 3인, 4인 이상)별로 나눠 줘.'],
       [P('mean', '', unit='household', value_var='h_prop', turn=1),
        P('quantile', '', unit='household', value_var='h_prop', q=0.5, turn=2),
        P('quantile', '', unit='household', value_var='h_prop', q=0.5, by=[{'std': 'hs4'}], turn=3)],
       '가구 단위가 대화 내내 유지되어야 함. 평균 → 중위수 → 가구원수별')

dialog(6, '자활사업 담당자',
       ['2022년 한 해 동안 자활근로에 한 번이라도 참여한 사람은 몇 명입니까?',
        '방금 것을 성별로 나눠 주세요.',
        '그럼 여성 참여자가 2022년에 받은 자활근로 급여액의 1인당 평균은 얼마입니까?'],
       [P('count', 'self_yn1 == 1', turn=1),
        P('count', 'self_yn1 == 1', by=SEX, turn=2),
        P('mean', 'self_yn1 == 1 and gender == 2', value_var='self_amt', turn=3)],
       '참여자 수 → 성별 → 여성 참여자의 평균 급여액. 관측 수가 적은 사업(95건)')

dialog(7, '공적연금 연구자',
       ['2022년에 공무원연금 정기연금을 받은 사람의 연간 급여액 평균을 알려 주세요.',
        '같은 걸 사립학교교직원연금 정기연금 수급자로 바꾸면요?',
        '사학연금 쪽을 평균 말고 합계로 알려 주세요.'],
       [P('mean', 'govp_pension_yn == 1', value_var='govp_pension_amt', turn=1),
        P('mean', 'privschp_pension_yn == 1', value_var='privschp_pension_amt', turn=2),
        P('sum', 'privschp_pension_yn == 1', value_var='privschp_pension_amt', turn=3)],
       '둘째 차례에서 제도가 바뀌고, 셋째 차례는 바뀐 제도에서 집계 함수만 바뀜')

dialog(8, '모성보호 제도 담당자',
       ['2022년 한 해 동안 육아휴직급여를 한 번이라도 받은 사람 수를 성별로 알려 주세요.',
        '같은 성별 구분으로, 2022년 12월 시점에 받고 있는 사람만 세면 어떻게 되나요?',
        '다시 처음의 연간 수급자 기준으로, 인원 말고 1인당 평균 급여액을 성별로 보여 주세요.'],
       [P('count', 'empins_parentleave_yn1 == 1', by=SEX, turn=1),
        P('count', 'empins_parentleave_yn2 == 1', by=SEX, turn=2),
        P('mean', 'empins_parentleave_yn1 == 1', value_var='empins_parentleave_amt', by=SEX, turn=3)],
       '연간 → 12월 → 다시 연간으로 되돌아가는 지시. 셋째 차례는 첫째 차례의 기준을 가리킴')

dialog(9, '교육복지 연구자',
       ['7~18세 아동·청소년 중 2022년에 교육급여 수급권을 한 번이라도 가졌던 사람의 비율은?',
        '그럼 같은 연령대에서 2022년에 방과후학교 자유수강권 지원을 받은 비율은?',
        '그걸 빈곤 여부(빈곤/비빈곤)로 나눠 줘.'],
       [P('rate', 'age >= 7 and age <= 18', numerator='nbls_edu_yn1 == 1', turn=1),
        P('rate', 'age >= 7 and age <= 18', numerator='pubedu_aftsch_yn == 1', turn=2),
        P('rate', 'age >= 7 and age <= 18', numerator='pubedu_aftsch_yn == 1', by=[{'std': 'poor2'}], turn=3)],
       '둘째 차례에서 분자(지원 종류)가 바뀌고 분모 연령은 유지. 셋째 차례는 둘째 차례 결과의 분류')

dialog(10, '빈곤 연구자',
       ['65세 이상 노인의 상대 빈곤율을 알려 주세요.',
        '그걸 가구원수별(1인, 2인, 3인, 4인 이상)로 나눠 주세요.',
        '같은 분류 그대로 75세 이상만 다시 보여 주세요.'],
       [P('poverty_rate', 'age >= 65', turn=1),
        P('poverty_rate', 'age >= 65', by=[{'std': 'hs4'}], turn=2),
        P('poverty_rate', 'age >= 75', by=[{'std': 'hs4'}], turn=3)],
       '빈곤율 → 가구원수별 → 같은 분류로 연령 하한만 변경')

# ---------------------------------------------------------------- G 묶음
G = []


def code_item(no, persona, defect, text, code, spec, note):
    q = text + '\n\n```python\n' + code.strip('\n') + '\n```'
    G.append({'id': 'G%02d' % no, 'stratum': 'G', 'defect': defect, 'persona': persona,
              'turns': [q], 'expect': 'compute', 'specs': [spec], 'note': note})


code_item(1, '지자체 노인복지 담당자', '분모 누락',
          '65세 이상 인구 중에서 2022년 노인장기요양 급여 수급자가 차지하는 비율을 시도별로 보려고 아래처럼 짰습니다. '
          '수치가 예상보다 많이 낮게 나오는데, 코드가 의도와 맞는지 확인하고 틀린 곳이 있으면 고쳐서 실행해 주세요.',
          "import ssda\nr = ssda.rate('ltcare_bn_yn == 1', by='sido')\nprint(r)",
          P('rate', 'age >= 65', numerator='ltcare_bn_yn == 1', by=SIDO),
          '대상 집단(where) 인자가 없어 전체 인구가 분모가 됨')

code_item(2, '공적연금 연구자', '없음',
          '2022년 12월 말 기준 사립학교교직원연금 가입자의 연간 보험료 납부액 평균을 성별로 구하는 코드입니다. '
          '틀린 데가 없는지 확인하고 결과를 알려 주세요.',
          "import ssda\nr = ssda.mean('privschp_premium_amt', where='privschp_yn2 == 1', by='sex')\nprint(r)",
          P('mean', 'privschp_yn2 == 1', value_var='privschp_premium_amt', by=SEX),
          '결함 없는 코드. 고치지 않고 그대로 실행해야 함')

code_item(3, '고용보험 사업 담당자', '유사 변수 사용(연간 ↔ 12월)',
          '2022년 12월 시점에 두루누리 고용보험료 지원을 받고 있던 사람이 몇 명인지 성별로 뽑으려고 합니다. '
          '한 해 동안 한 번이라도 받은 사람 수는 필요하지 않고 12월 시점 기준이어야 합니다. 아래 코드로 실행하면 되는지 봐 주세요.',
          "import ssda\nr = ssda.count(where='empins_support_yn1 == 1', by='sex')\nprint(r)",
          P('count', 'empins_support_yn2 == 1', by=SEX),
          '12월 기준을 요청했으나 연간 여부 변수를 씀')

code_item(4, '건강보험 연구자', '조건 경계 오류(이상 ↔ 초과)',
          '2022년에 의과 외래 진료를 받은 사람 가운데 연간 외래 내원일수가 12일 이상인 사람의 비율을 성별로 구하는 코드입니다. '
          '조건이 제대로 들어갔는지 확인해 주시고, 고칠 곳이 있으면 고쳐서 결과를 보여 주세요.',
          "import ssda\nr = ssda.rate('nhi_out_dur > 12', where='nhi_out_dur > 0', by='sex')\nprint(r)",
          P('rate', 'nhi_out_dur > 0', numerator='nhi_out_dur >= 12', by=SEX),
          '12일 이상을 > 12로 써서 12일인 사람이 분자에서 빠짐')

code_item(5, '통계 담당자', '단위 오류(개인 ↔ 가구)',
          '시도별로 전체 가구 중 가구 재산이 1억원 미만인 가구의 비율을 가구 단위로 내려고 해. '
          '아래처럼 하면 가구 기준으로 계산되는지 확인하고, 아니면 고쳐서 돌려 줘.',
          "import ssda\nr = ssda.rate('h_prop < 100000000', by='sido')\nprint(r)",
          P('rate', '', unit='household', numerator='h_prop < 100000000', by=SIDO),
          '가구 단위 인자가 없어 개인 가중으로 계산됨')

code_item(6, '아동정책 담당자', '분모 누락',
          '만 8세 미만 아동 중 2022년 12월 기준으로 아동수당을 받고 있는 아동의 비율을 성별로 구하고 싶습니다. '
          '이렇게 쓰면 되나요? 문제가 있으면 고쳐서 실행해 주세요.',
          "import ssda\nr = ssda.rate('childbn_yn2 == 1 and age < 8', by='sex')\nprint(r)",
          P('rate', 'age < 8', numerator='childbn_yn2 == 1', by=SEX),
          '연령 조건을 분자에만 넣어 분모가 전체 인구가 됨')

code_item(7, '장애인 서비스 담당자', '집계 함수 오류(합계 ↔ 평균)',
          '2022년 한 해 동안 장애인활동지원을 이용한 사람들에게 지급된 정부지원금의 전체 합계를 구하려고 합니다. '
          '아래 코드가 맞는지 확인하고 실행해 주세요.',
          "import ssda\nr = ssda.mean('disvou_act_subsidy', where='disvou_act_yn1 == 1')\nprint(r)",
          P('sum', 'disvou_act_yn1 == 1', value_var='disvou_act_subsidy'),
          '합계를 요청했으나 평균 함수를 씀')

code_item(8, '노후소득보장 연구자', '유사 변수 사용(가구 ↔ 개인)',
          '65세 이상 노인의 개인 가처분소득(본인 몫의 소득, 가구 합산 전) 평균을 성별로 비교하려고 합니다. '
          '코드 검토 부탁드립니다. 잘못된 곳이 있으면 수정해서 결과를 주세요.',
          "import ssda\nr = ssda.mean('h_dinc', where='age >= 65', by='sex')\nprint(r)",
          P('mean', 'age >= 65', value_var='p_dinc', by=SEX),
          '개인 가처분소득을 요청했으나 가구 가처분소득 변수를 씀')

code_item(9, '모성보호 제도 담당자', '실행 불가(변수명 오류)',
          '2022년 한 해 동안 출산전후휴가 급여를 받은 사람의 1인당 평균 급여액을 구하려는데 아래 코드가 오류가 나요. '
          '고쳐서 실행해 주세요.',
          "import ssda\nr = ssda.mean('matleave_amt', where='matleave_yn1 == 1')\nprint(r)",
          P('mean', 'empins_matleave_yn1 == 1', value_var='empins_matleave_amt'),
          '짐작으로 쓴 변수명이라 실행되지 않음. 올바른 변수를 찾아 고쳐야 함')

code_item(10, '고용정책 연구자', '조건 연산자 오류(and ↔ or)',
          '18~64세 인구 중 2022년 한 해 동안 국민취업지원제도에 한 번이라도 참여한 사람의 비율을 성별로 보려고 합니다. '
          '아래 코드 확인 부탁드립니다.',
          "import ssda\nr = ssda.rate('kua_yn1 == 1', where='age >= 18 or age <= 64', by='sex')\nprint(r)",
          P('rate', 'age >= 18 and age <= 64', numerator='kua_yn1 == 1', by=SEX),
          '연령 범위를 or로 이어 조건이 항상 참이 됨(전체 인구가 분모)')

code_item(11, '보건의료정책 담당자', '없음',
          '65세 이상을 65~69세, 70~79세, 80세 이상으로 나눠서, 각 연령 구간의 인구 중 2022년에 건강보험 본인부담상한제 지원을 받은 사람의 비율을 구했습니다. '
          '코드에 문제가 없는지 검토해 주시고 결과도 같이 주세요.',
          "import ssda\nssda.define_group('age_old3', 'age', [65, 70, 80], ['65세 미만', '65~69세', '70~79세', '80세 이상'])\n"
          "r = ssda.rate('nhi_ceiling_subsidy_yn == 1', where='age >= 65', by='age_old3')\nprint(r)",
          P('rate', 'age >= 65', numerator='nhi_ceiling_subsidy_yn == 1',
            by=[{'var': 'age', 'bins': [70, 80], 'labels': ['65~69세', '70~79세', '80세 이상']}]),
          '결함 없는 코드(이용자 지정 구간). 고치지 않고 그대로 실행해야 함')

code_item(12, '장애인정책 담당자', '분류 기준 오류',
          '2022년 12월 말 기준 등록장애인 수를 연령대 6구간(0~17세, 18~34세, 35~49세, 50~64세, 65~74세, 75세 이상)으로 나눠 보려고 합니다. '
          '이 코드 그대로 돌리면 되는지 확인해 주세요.',
          "import ssda\nr = ssda.count(where='dis_yn == 1', by='age3')\nprint(r)",
          P('count', 'dis_yn == 1', by=[{'std': 'age6'}]),
          '6구간을 요청했으나 3구간 분류를 씀')


def dump(name, items):
    path = os.path.join(OUT, name)
    with open(path, 'w', encoding='utf-8') as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + '\n')
    print(path, len(items))


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    dump('C.jsonl', C)
    dump('F.jsonl', F)
    dump('G.jsonl', G)
