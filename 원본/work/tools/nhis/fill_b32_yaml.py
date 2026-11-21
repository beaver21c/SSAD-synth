# -*- coding: utf-8 -*-
"""params/A5_B32.yaml 의 41개 변수에 dist/source/status/condition/note 를 채운다.
스텁의 name_ko·unit·dtype·labels·scope·codebook_content 는 그대로 둔다."""
import os, yaml, collections

ROOT = '/mnt/share/행정데이터_set/work'
P = os.path.join(ROOT, 'params/A5_B32.yaml')
DATE = '2026-09-02'

SRC_YB = dict(Rcode='R10', tblId=None,
              url='https://www.nhis.or.kr/nhis/together/wbhaec06300m01.do?mode=download&articleNo=10838804&attachNo=357498',
              file='params/raw/R10_3-4_요양기관종별_진료형태별_진료현황_총계.csv; params/tab/R10_3-9_연령성별_요양기관종별_평균수진횟수.csv; params/raw/R10_3-7-1_연령성별_진료현황_총계_입원.csv; params/raw/R10_3-7-2_연령성별_진료현황_총계_외래.csv; params/raw/R10_1-3-1_시도연령성별_적용인구_건강보험.csv',
              table_no='2022 건강보험통계연보 Ⅲ-4 / Ⅲ-9 / Ⅲ-7-1 / Ⅲ-7-2 / Ⅰ-3-1',
              page='제3편 진료현황(03-1 건강공단 xlsx)', extract_date=DATE)

def src_fee(extra=''):
    s = dict(SRC_YB)
    s['file'] = s['file'] + '; params/tab/LAW_의료급여_본인부담_2022.csv'
    s['table_no'] = s['table_no'] + ' + 의료급여법 시행령 [별표1](시행 2022.4.1)'
    return s

NAT = {  # (form, inst) → (실인원, 일수, 진료비천원, 1일당원, 실효본인부담률)
 ('out','clinic'):      (46053956, 560485284, 21793323931, 38883, 0.2437),
 ('out','hospital'):    (15092210,  69054475,  3746405894, 54253, 0.3454),
 ('out','gehospital'):  (15742791,  80432730,  6807756066, 84639, 0.3744),
 ('out','tehospital'):  ( 8227322,  46213016,  6987354057,151199, 0.3097),
 ('in','clinic'):       ( 1192713,   5614618,  1698110376,302445, 0.1926),
 ('in','hospital'):     ( 2003861,  21894471,  5426918492,247867, 0.2200),
 ('in','gehospital'):   ( 2771519,  26994038, 11058899730,409679, 0.1829),
 ('in','tehospital'):   ( 1650435,  17508616, 12007331297,685796, 0.1523),
}
KO_INST = {'clinic': '의원', 'hospital': '병원', 'gehospital': '종합병원', 'tehospital': '상급종합병원'}
KO_FORM = {'out': '외래', 'in': '입원'}
COND = ("추출대상 = '22년 중 외래 또는 입원 서비스를 1회 이상 이용한 집단. "
        "해당 종별·형태에 청구가 없는 개인은 NaN(=청구 없음), 추출대상 밖은 전 변수 NaN.")

COMMON_NOTE = (
 '[생성] 연령 19군×성 격자에서 (이용률 p, 이용자당 일수 m, 1일당 진료비 w)를 만든 뒤 개인 추출. '
 'p 는 Ⅲ-7 연령·성 이용률 프로파일을 상대위험 형태로 Ⅲ-4 종별 실인원에 맞추고, '
 'm 은 Ⅲ-9 종별군 1인당 일수를 p로 나눈 값(종별군→종별 분해는 Ⅲ-4 전국 일수 구성비), '
 'w 는 Ⅲ-4 종별 입내원1일당진료비에 Ⅲ-7 연령·성 단가지수를 곱하고 Ⅲ-4 진료비 총액으로 재척도. '
 '개인 추출은 _u_health 와 정규코퓰러(ρ=0.35)로 상관시키되, 이변량정규 항등식 '
 'E[e^{a·z}|z2<t]=e^{a²/2}Φ(t+aρ)/Φ(t) 로 셀별 보정계수를 곱해 전국 집계를 무편향 재현한다. '
 '[한계] Ⅲ-9 의 종별군(종합병원=상급종합+종합, 병원=병원+요양병원+정신병원)을 종별로 나눌 때 '
 '전국 구성비를 연령 불변으로 가정했다(연령별 종별 교차표 미확보 → [미확인]).')

MEDI_NOTE = (
 '의료급여(nhi_type∈{7,8}) 가산: R05 표3-4-5(2022 의료급여 사업실적)를 Ⅲ-7(건강보험)로 나눈 배수 — '
 '외래 이용률 ×1.00·일수 ×4.73, 입원 이용률 ×2.10·일수 ×5.44. '
 '[한계] 이 배수는 의료급여 수급자의 고령 편중을 보정하지 않은 조(粗)비율이며, '
 '의료급여 진료일수에 요양병원·약국이 포함돼 의과 4종만 보면 과대추정 가능. '
 'B31 미구현 시 nhi_type 대신 _u_income 하위 2.876%(=1,522,292/52,932,270, R10 Ⅰ-3)로 폴백.')

TAIL_NOTE = (
 '상위꼬리는 Ⅲ-11(입원)·Ⅲ-12(외래) 연령별 연간진료비 크기별 표의 중위/평균·P90/평균 비 '
 '(외래 0.557·1.761, 입원 0.371·2.160)에 맞춰 로그정규 σ(개인 frailty 0.30/0.60 + 잔차 0.45/0.60)와 '
 '음이항 disp(4.0/1.8)를 보정했다. 코드북 붙임 "중증·고액진료비 상위 30위"는 질환명 목록뿐이어서 '
 '금액 정보가 없고, 대신 Ⅵ-21 전체 중증(암)등록환자(1,773,146명·1인당 진료비 7,170,490원)를 꼬리 타당성 대조로 사용.')

def dist_dur(form, inst):
    p, d, a, w, r = NAT[(form, inst)]
    return {'type': 'bernoulli_x_nbinom',
            'participation': f'연령19×성2 격자, Ⅲ-4 전국 실인원 {p:,}명에 맞춤',
            'days': f'core.nbinom_mean_disp(mean=이용자당 평균일수, disp={4.0 if form=="out" else 1.8})',
            'national_days': f'{d:,}일',
            'range': '[1,366] (일 단위. §7 R24 의 [1,12]는 개월 단위 급여기간 규칙)',
            'latent': '_u_health (정규코퓰러 ρ=0.35, 일수 ρ_d=0.45)'}

def dist_amt(form, inst):
    p, d, a, w, r = NAT[(form, inst)]
    return {'type': 'days_x_lognormal_daily',
            'daily_mean': f'Ⅲ-4 입내원1일당진료비 {w:,}원 × Ⅲ-7 연령·성 단가지수',
            'sigma': (0.30 if form == 'out' else 0.60, 0.45 if form == 'out' else 0.60),
            'sigma_note': '(개인 frailty σ_f, 잔차 σ_r) — Ⅲ-11/Ⅲ-12 분위 적합',
            'national_amt': f'{a:,}천원', 'unit': '원(정수)'}

def dist_fee(form, inst):
    p, d, a, w, r = NAT[(form, inst)]
    return {'type': 'deterministic_rate',
            'nhi_rate': round(r, 4),
            'nhi_rate_src': 'Ⅲ-4 실효 본인부담률 = 1 − 급여비/진료비',
            'medi_1jong': ('1회 방문당 정액' if form == 'out' else '0원(기금 전액부담)'),
            'medi_2jong': ('의원 1,000원 정액 / 병원급 15%' if form == 'out' else '10%'),
            'rule': 'fee = round(amt × 요율), fee ≤ amt'}

def dist_sub(form, inst):
    return {'type': 'deterministic', 'rule': 'subsidy = amt − fee (요양급여비용 총액 − 본인부담금)'}

def fill(d):
    P_ = d['params']
    for form in ('out', 'in'):
        for inst in ('clinic', 'hospital', 'gehospital', 'tehospital'):
            ko = f'{KO_FORM[form]} {KO_INST[inst]}'
            n = NAT[(form, inst)]
            for kind in ('dur', 'amt', 'fee', 'subsidy'):
                v = P_[f'nhi_{form}_{inst}_{kind}']
                v['condition'] = COND
                v['status'] = '1차확인'
                v['source'] = src_fee() if kind == 'fee' else dict(SRC_YB)
                if kind == 'dur':
                    v['dist'] = dist_dur(form, inst)
                    v['note'] = (f'[1차확인] Ⅲ-4 {ko}: 진료실인원 {n[0]:,}명, 입내원일수 {n[1]:,}일 '
                                 f'(1인당 {n[1]/n[0]:.1f}일). ' + COMMON_NOTE + ' ' + MEDI_NOTE)
                elif kind == 'amt':
                    v['dist'] = dist_amt(form, inst)
                    v['note'] = (f'[1차확인] Ⅲ-4 {ko}: 진료비 {n[2]:,}천원, 입내원1일당 {n[3]:,}원. '
                                 + TAIL_NOTE)
                elif kind == 'fee':
                    v['dist'] = dist_fee(form, inst)
                    v['note'] = (f'[1차확인] 건강보험 실효 본인부담률 = 1 − 급여비/진료비 = {n[4]:.4f} '
                                 f'(Ⅲ-4 {ko}). 코드북이 "산정특례로 경감된 본인부담금은 제외(일괄 적용)"라 '
                                 f'명시하므로 종별×형태 고정요율을 결정적으로 적용한다. '
                                 f'의료급여는 의료급여법 시행령 [별표1](시행 2022.4.1) — '
                                 f'1종 입원 0원·외래 정액(의원 1,000/병원·종합 1,500/상급종합 2,000원), '
                                 f'2종 입원 10%·병원급 외래 15%·의원 외래 1,000원 정액. '
                                 f'[한계] 별표1 다목~러목의 감면(18세 미만·임신부·중증질환 전액 기금부담 등)은 미반영 → '
                                 f'의료급여 본인부담 소폭 과대.')
                else:
                    v['dist'] = dist_sub(form, inst)
                    v['note'] = (f'[1차확인] Ⅲ-4 {ko} 급여비 대조. amt·fee 로부터 결정적으로 산출되므로 '
                                 f'공단부담금 총액은 자동으로 Ⅲ-4 급여비 구조를 재현한다.')

    # 총괄 8개
    for form in ('out', 'in'):
        tot = {k: sum(NAT[(form, i)][j] for i in KO_INST) for j, k in
               enumerate(['person', 'days', 'amt', 'daily', 'rate'])}
        for kind in ('dur', 'amt', 'fee', 'subsidy'):
            v = P_[f'nhi_{form}_{kind}']
            v['condition'] = COND + ' 4개 종별이 모두 미이용이면 NaN.'
            v['status'] = '1차확인'
            v['source'] = src_fee() if kind == 'fee' else dict(SRC_YB)
            v['dist'] = {'type': 'deterministic_sum',
                         'rule': f'nhi_{form}_{kind} = Σ(clinic, hospital, gehospital, tehospital)_{kind}',
                         'national_days': f'{tot["days"]:,}일', 'national_amt': f'{tot["amt"]:,}천원'}
            v['note'] = (f'[1차확인] 코드북 정의 "전체 의과 의료기관 = 의원+병원+종합병원+상급종합병원" 에 따라 '
                         f'종별 4개의 합으로 결정적으로 산출(§7 총괄=Σ종별 정합 강제). '
                         f'Ⅲ-4 전국 의과4종 {KO_FORM[form]} 합계 = 입내원일수 {tot["days"]:,}일, '
                         f'진료비 {tot["amt"]:,}천원. 요양병원·정신병원·치과·한방·보건기관·약국은 정의상 제외 '
                         f'(요양병원은 B33 nhi_*_ltcare_* 소관).')

    # 응급실
    v = P_['nhi_in_emergency_dur']
    v['condition'] = COND + ' 응급실 이용이 없으면 NaN.'
    v['status'] = '1차확인'
    v['dist'] = {'type': 'nbinom', 'mean': '성×연령(10군) 응급실 이용건수 ÷ 의료보장 적용인구',
                 'national': '8,549,733건 / 52,932,270명 = 0.1615건/인·년', 'disp': 0.25,
                 'multiplier': '입원 경험자 ×2.2, 그 외 ×0.85, exp(0.45·z_health) — 평균 1로 정규화',
                 'range': '[1,365] (일)'}
    v['source'] = dict(Rcode='NEMC', tblId=None,
                       url='https://www.e-gen.or.kr/nemc/statistics_annual_report.do',
                       file='params/tab/NEMC_2022_응급실이용_성연령별.csv; params/raw/R_NEMC_2022_응급의료통계연보.pdf',
                       table_no='2022 응급의료 통계연보(제21호) PART1-2 「3. 2022 전국 응급의료기관 및 응급의료시설 이용자」 1) 성별·연령별·시도별 응급실 이용',
                       page='150', extract_date=DATE)
    v['note'] = ('[1차확인] 지시서 §6 B32 는 "응급 0.1회/년"을 제시했으나, 원기관(중앙응급의료센터) '
                 '2022 응급의료 통계연보를 직접 확보해 전사한 결과 실제값은 0.1615건/인·년 '
                 '(8,549,733건 ÷ 의료보장 적용인구 52,932,270명)이었다. 상위 등급 원문값을 채택한다. '
                 '도착전사망(DOA)·진료외방문은 제외한 수치이며, 집계불가 3개 기관은 미포함. '
                 '코드북 정의가 "응급실 코드의 일자로 COUNT" 이므로 응급실 내원 건수를 일수로 본다. '
                 '[한계] 응급실 이용은 대부분 외래로 청구되나 코드북이 (입원) 계열에 배치했다 — 정의 그대로 따랐다.')
    return d


if __name__ == '__main__':
    d = yaml.safe_load(open(P, encoding='utf-8'))
    d = fill(d)
    d['meta']['implemented'] = True
    d['meta']['rules_file'] = 'rules/A5_B32.py'
    d['meta']['codebook_review'] = (
        '① 종별 세부 20개 변수: R10 Ⅲ-4(요양기관 종별 진료형태별)와 Ⅲ-9(연령·성·종별 평균 수진횟수)를 '
        '모두 확보했으므로 **전부 유지**(축약 불필요). '
        '② [코드북 오류] nhi_in_hospital_dur/_amt/_fee/_subsidy 의 "변수 내용" 칸이 한 행씩 밀려 있다 — '
        'dur=“의원에서 간호간병통합서비스를 받은 일수”, amt=“의원 간호간병통합 요양급여비용”, '
        'fee=“1년 동안 병원에 입원한 재원일수”, subsidy=“병원 요양급여비 총액”. '
        '변수명(한글)은 정상((입원) 의과 병원 재원일수/총액/본인부담금/공단부담금)이므로 변수명 기준으로 생성했다. '
        'A6 확정 필요. '
        '③ [정의 상충] nhi_ceiling_amt 는 코드북에서 "환급금 총액_본인부담상한(사후 환급액)"이나, '
        '§7 R21 은 이를 "분위별 상한액(임계값)"으로 사용한다. B32 는 R11 [1차확인] 분위별 상한액을 '
        '내부 헬퍼 _nhi_ceiling_thr 로 두고, df 에 nhi_ceiling_amt 가 있으면 그 값도 함께 초과할 때만 '
        'yn=1 로 두어 양쪽 정의에서 모두 위반 0이 되게 했다. '
        '④ nhi_in_emergency_dur 는 (입원) 계열이나 실제 응급실 이용은 외래 청구가 다수 — 정의 유지, note 기록.')
    d['meta']['cross_block'] = {
        '_nhi_own_pay': {
            'produced_by': 'B32', 'consumed_by': 'B31(상한제)·A5a',
            'definition': 'Σ(nhi_out_fee + nhi_in_fee) — 의과 4종 외래·입원 본인부담금 합계(원)',
            'status': '논리적추론',
            'note': '실제 본인부담상한제 산정 기준은 약국·치과·한방·요양병원 본인부담을 포함하므로 '
                    '본 값은 하한이다(B33 요양병원분 추가 시 재계산 필요).'},
        '_nhi_ceiling_thr': {
            'produced_by': 'B32', 'status': '1차확인',
            'source': 'params/raw/R11_연도별_본인부담상한액_보험료분위구간별.csv (data.go.kr 15122295 참고자료, 2022 일반)',
            'definition': '2022 보험료분위 7구간 상한액 83/103/155/289/360/443/598만원. '
                          '분위는 B31 nhi_premium_cal_p20 → 없으면 _recog_rank → _u_income 순으로 폴백.'},
        'nhi_ceiling_subsidy_yn / nhi_ceiling_subsidy_amt': {
            'produced_by': 'B32 (B31 소관 변수이나 §7 「ceiling ⇒ B32 이후」 때문에 B32에서만 계산 가능)',
            'status': '1차확인',
            'rule': '_nhi_own_pay > 상한액이면 yn=1, amt = 초과분. 의료급여(7/8)는 대상 아님 → NaN.',
            'validation': 'R11 지급내역 2022: 사후환급 2,350,415건·2,135,198,133,030원 + 사전지급 '
                          '127,413건·169,147,293,573원 = 2.304조원. 재현 총액 2.41조원(+4.7%). '
                          '수급률은 3.14%로 실적 4.57%보다 낮고 1인 평균 환급액은 149만원으로 높다 — '
                          '_nhi_own_pay 가 약국·치과·한방·요양병원 본인부담을 빼고 있기 때문.',
            'coordination': '★ B31(A5a) 담당은 이 두 변수를 생성하지 말 것. B32 는 df 에 이미 있으면 생성을 건너뛴다.'}}
    d['meta']['params_sources_added'] = [
        'params/tab/R10_3-9_연령성별_요양기관종별_평균수진횟수.csv (+meta)',
        'params/tab/R10_3-11_연령별_연간진료비크기별_입원.csv (+meta)',
        'params/tab/R10_3-12_연령별_연간진료비크기별_외래.csv (+meta)',
        'params/tab/NEMC_2022_응급실이용_성연령별.csv (+meta)',
        'params/tab/LAW_의료급여_본인부담_2022.csv (+meta)',
        'params/raw/R_NEMC_2022_응급의료통계연보.pdf (77,647,087 B)']
    yaml.safe_dump(d, open(P, 'w', encoding='utf-8'), allow_unicode=True, sort_keys=False, width=1000)
    print('written', len(d['params']))
