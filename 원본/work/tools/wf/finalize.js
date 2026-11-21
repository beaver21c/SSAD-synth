export const meta = {
  name: 'ssad-finalize',
  description: '§9 검증·산출물 — S0/S1 캘리브레이션 검증, 코드북 수정 확정, 최종 리포트',
  phases: [
    { title: 'Verify', detail: '검증 목표 작성·평가, 이탈 원인 규명 (병렬)' },
    { title: 'Finalize', detail: '산출물 생성·문서화' },
  ],
}

const ROOT = '/mnt/share/행정데이터_set/work'

const BASE = [
  '작업 디렉터리 ' + ROOT + '. Python: /mnt/share/행정데이터_set/.venv/bin/python',
  '먼저 읽어라: AGENT_BRIEF.md, registry/s0_basis_finding.md, registry/column_contract.md',
  '',
  '현재 상태: A1~A5 전 블록의 rules/*.py 와 params/*.yaml 이 작성되어 파이프라인이 돈다.',
  '전체 실행:',
  '  /mnt/share/행정데이터_set/.venv/bin/python -c "',
  '  import sys; sys.path.insert(0,\'tools\'); import pipeline',
  '  df,lg,raw=pipeline.run(verbose=False); df.to_parquet(\'data/stage_all.parquet\'); print(lg.to_string(index=False))"',
  '',
  ''
].join('\n')

const TASKS = [
  {
    key: 'targets-s1',
    body: [
      '## 임무: S1(원기관 행정집계) 총량 검증 목표 작성 — §9 "각 급여 수급자 수·평균액이 R03~R16 대비 상대오차 ±10%"',
      '',
      'params/raw 와 params/tab 의 2022년 원기관 집계에서 **급여별 전국 수급자수·평균 급여액**을 뽑아,',
      '표본 가중 추정치(Σindwgt 또는 Σhhwgt 가중)와 비교하는 목표를 `targets/S1_totals.yaml` 로 작성하라.',
      '',
      '대상 급여 (최소 20개):',
      '  기초생활 생계·의료·주거·교육급여 / 기초연금 / 장애인연금·장애수당·장애아동수당 /',
      '  아동수당·양육수당·영아수당·보육료 / 국민연금 가입자·수급자 / 공무원연금·사학연금 수급자 /',
      '  고용보험 피보험자 / 구직급여 / 출산전후휴가·육아휴직 / 긴급복지 / 자활 / 한부모 /',
      '  노인맞춤돌봄 / 장애인활동지원 / 장기요양 인정자 / 노인일자리 / 건강보험 적용인구(직역별) /',
      '  근로장려금·자녀장려금 / 국민취업지원제도',
      '',
      '각 목표는 kind: wcount (가중 모집단 추정) 로 쓰고, unit: person 또는 household 를 지정하라.',
      '  예)',
      '  - name: "[S1] 기초연금 수급자수(가중 추정)"',
      '    grade: S1',
      '    kind: wcount',
      '    unit: person',
      '    expr: "df.bp_yn1.fillna(0)==1"',
      '    target: 6168000',
      '    tol: 0.10',
      '    tol_kind: rel',
      '    source: "R17 통계청 2022년 연금통계 보도자료 / R05 표5-1-8 …"',
      '',
      '**목표값은 반드시 params/raw·params/tab 의 실제 파일에서 읽은 2022년 수치여야 한다.**',
      '출처(파일경로·표번호)를 source 에 적고, 확인 못 한 급여는 목표를 만들지 말고 registry/ext_targets.md 에',
      '"목표값 미확보"로 기록하라. 지어낸 목표는 검증 전체를 무의미하게 만든다.',
      '',
      '작성 후 실행해서 몇 개가 통과/이탈하는지 보고하라:',
      '  python -c "import sys;sys.path.insert(0,\'tools\');import validate,pandas as pd;' +
      'df=pd.read_parquet(\'data/stage_all.parquet\');' +
      'print(pd.DataFrame([validate.eval_target(df,t) for t in validate.load_targets()]).to_string())"'
    ].join('\n')
  },
  {
    key: 'deviation',
    body: [
      '## 임무: 검증 이탈 원인 규명과 수정',
      '',
      '1. 전체 파이프라인을 돌리고 targets/*.yaml 을 평가하라.',
      '2. **이탈(pass=False)한 목표마다** 원인을 규명하라:',
      '   (a) 생성 파라미터가 틀렸는가 (분포·확률·단가)',
      '   (b) 조건부 규칙이 과도/과소하게 걸렸는가',
      '   (c) S0(2020·2021)와 코드북(2022)의 연도차인가 — 이 경우는 정상이며 리포트에 표시만',
      '   (d) 일반가구 표본이라 시설거주자가 빠진 효과인가 — 정상, 표시만',
      '   (e) 목표값 자체가 잘못 전사되었는가 — 원문 재확인',
      '3. (a)(b)(e) 는 해당 블록의 rules/params 를 고쳐 통과시켜라. (c)(d) 는 target 의 note 에',
      '   사유를 적고 tol 을 근거 있게 조정하되, **근거 없이 tol 을 늘려 통과시키지 말 것**.',
      '4. §7 정합성 규칙 25건 위반을 0건으로 만들어라.',
      '',
      '결과를 registry/deviation_analysis.md 에 쓰고, 최종 텍스트로 통과/이탈 현황과 고친 내용을 요약하라.'
    ].join('\n')
  },
  {
    key: 'codebook-fix',
    body: [
      '## 임무: §8 코드북 수정 검토 확정',
      '',
      '작업지시서 §8.2 의 블록별 검토 항목에 대해, 지금까지의 확보·생성 결과를 근거로 **결론**을 내려라.',
      '  B02 city 코드 정의 / B14 postp_* / B16 youthemp 9개 / B24 implant·dentures /',
      '  B25 self_type2 / B27 dis_grade_2·3 / B29 급식비·고교학비 / B30 시간제·연장·방과후 /',
      '  B31 nhi_premium cal·set·p20 / B32 종별 세부 / B33 이용 극소 급여종류 / B34 oldwork_type4~6',
      '',
      '각 항목에 대해:',
      ' - 관련 자료를 실제로 확보했는가 (파일경로)',
      ' - 확보했다면 수치는 얼마이고, 표본 9,800명에서 기대 건수는 몇 명인가',
      ' - 결론: 유지 / 상위개념 축약(무엇으로) / 규모 미달로 NULL 표시 / 확인 불가([미확인] 유지)',
      ' - §1.3 시도 기록이 report/attempts.md 에 있는가',
      '',
      '또한 §8.1 Tier3 (LH·GH·SH 임대주택 187개, 장애인일자리·발달재활·지역사회서비스·가사간병 등,',
      '국민체육진흥공단·여가부·장학재단·암센터·치매센터)에 대해 **확보 가능성 평가**를 적어라',
      '(어떤 자료가 실제로 존재하는지 registry/raw_inventory.csv 와 acq_*.md 를 근거로).',
      '',
      '결과를 report/codebook_revision.md 에 표로 쓰고, 최종 텍스트로 결론 요약을 반환하라.'
    ].join('\n')
  },
]

phase('Verify')
const verified = await parallel(TASKS.map(t => () =>
  agent(BASE + t.body, { label: 'fin:' + t.key, phase: 'Verify' })
    .then(r => ({ key: t.key, report: r }))
    .catch(e => ({ key: t.key, report: null, error: String(e) }))
))

phase('Finalize')
const finalPrompt = [
  BASE,
  '## 임무: §9 산출물 최종 생성',
  '',
  '1. 파이프라인 전체 실행 → data/stage_all.parquet',
  '2. 산출물 생성:',
  '   python -c "import sys;sys.path.insert(0,\'tools\');import pandas as pd,json,export_final,validate,collect_reports;' +
  'df=pd.read_parquet(\'data/stage_all.parquet\');' +
  'print(export_final.export(df));' +
  'cb={v[\'var\']:v for v in json.load(open(\'registry/codebook.json\',encoding=\'utf-8\'))};' +
  'print(validate.build_html(df,pop={\'persons\':df._N_pop_person.iloc[0],\'households\':df._N_pop_hh.iloc[0]},cb=cb))"',
  '   python tools/export_codebook.py     → final/codebook_synthetic.xlsx',
  '   python tools/collect_reports.py     → report/attempts.md, report/assumptions.md, registry/access_check.csv',
  '3. report/validation.html 을 확인하고, 부족하면 tools/validate.py 를 보강해',
  '   다음 절을 추가하라:',
  '   - S0 캘리브레이션표 (R01/R02 대비 항목별 재현오차, 연도차 주석 포함)',
  '   - S1 총량표 (급여별 가중 추정 vs 원기관 집계, 상대오차)',
  '   - 주변분포 적합 (성×5세×시도 인구, 가구원수, 지니·상대빈곤율)',
  '   - §7 규칙 25건 위반 현황',
  '   - NULL 패턴 = 추출대상 정의 일치 여부',
  '   - seed 재현성 확인 (동일 seed 로 2회 생성해 동일한지)',
  '   - 생성 변수 커버리지 (595개 중 몇 개 생성, 지위별 분포)',
  '4. report/README.md 를 작성하라 — 산출물 목록, 데이터 사용 시 주의사항',
  '   (실제 개인정보 아님 / 시설거주자 제외 / S0 연도차 / 시군구 단위 분석 불가 / 가중치 사용법).',
  '',
  '최종 텍스트로 산출물 목록과 검증 요약(통과/이탈 건수, §7 위반, 커버리지)을 한국어로 반환하라.'
].join('\n')

const fin = await agent(finalPrompt, { label: 'fin:outputs', phase: 'Finalize' })

return { verified: verified.map(r => ({ key: r.key, ok: !!r.report, head: (r.report || r.error || '').slice(0, 1200) })), fin }
