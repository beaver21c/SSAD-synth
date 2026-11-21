export const meta = {
  name: 'ssad-fix-round4',
  description: '내부 비정합(소득 0 피부양자의 소득세 21%) + 세대구성 주변분포 미적합 수정 후 최종 산출',
  phases: [
    { title: 'Fix', detail: '피부양자↔소득 정합 · 세대구성 IPF 재적합 (병렬)' },
    { title: 'Final', detail: '최종 재검증·산출물 재생성' },
  ],
}

const ROOT = '/mnt/share/행정데이터_set/work'

const BASE = [
  '작업 디렉터리 ' + ROOT + '   Python: /mnt/share/행정데이터_set/.venv/bin/python',
  '',
  '## 먼저 읽어라',
  '  ' + ROOT + '/AGENT_BRIEF.md',
  '  ' + ROOT + '/registry/column_contract.md',
  '  ' + ROOT + '/registry/deviation_analysis.md  — 직전 라운드 분석 (이 작업의 근거)',
  '  ' + ROOT + '/registry/s0_basis_finding.md',
  '',
  '## 현재 상태 — 이미 매우 좋다. 깨뜨리지 말 것',
  '  29블록 OK · 0 FAIL · 컬럼 652 · 개인 9,535 · 가구 4,200',
  '  **§7 25규칙 위반 0건** (N/A 0 — 전 규칙이 실제 평가됨)',
  '  **seed 재현성 True** (2회 독립 실행 bit-identical)',
  '  Σindwgt·Σhhwgt **배수 1.000000000**',
  '  검증목표 **247/258** (S0 56/66 · **S1 151/151** · S2 40/41), 평가불가 0',
  '',
  '## 검증 실행',
  '```bash',
  'cd ' + ROOT,
  '/mnt/share/행정데이터_set/.venv/bin/python -c "',
  'import sys; sys.path.insert(0,\'tools\'); import pipeline, consistency, validate; import pandas as pd',
  'a,lg,raw = pipeline.run(verbose=False); b,_,_ = pipeline.run(verbose=False)',
  'print(lg[lg.status!=\'OK\'].to_string(index=False)); print(\'seed\', a.equals(b))',
  'c = consistency.run(a, {\'persons\':a._N_pop_person.iloc[0],\'households\':a._N_pop_hh.iloc[0]})',
  'print(c[c.violations.apply(lambda x: isinstance(x,int) and x>0)].to_string(index=False))',
  't = pd.DataFrame([validate.eval_target(a,x) for x in validate.load_targets()])',
  'print(int(t[\'pass\'].sum()), \'/\', int(t[\'got\'].notna().sum()))',
  'print(t[t[\'pass\']==False][[\'name\',\'target\',\'got\',\'dev\']].to_string(index=False))"',
  '```',
  '',
  '## 절대 규칙',
  ' 1. **배정된 파일만 수정.** 다른 블록 파일은 건드리지 말 것 (동시 편집 중).',
  ' 2. `tools/*.py` 수정 금지 (버그는 보고만).',
  ' 3. §7 위반 0건 · seed 재현성 True · 가중치 배수 1.000000000 을 **반드시 유지**하라.',
  ' 4. 검증목표 통과 수가 **247 미만으로 떨어지면 안 된다.** 떨어지면 되돌리고 보고하라.',
  ' 5. 원문에서 확인한 수치만. tol 을 늘려 통과시키지 말 것.',
  '',
  '## 반환',
  '한국어 요약: 고친 것 / 지표 변화(전·후) / 남은 문제 / 다른 블록 필요 조치.',
  '',
  '## 담당',
  ''
].join('\n')

const TASKS = [
  {
    key: 'dep-income',
    body: [
      '### 담당: `rules/A5_B31.py` · `params/A5_B31.yaml` (+ 필요 시 `targets/A5_B31.yaml`)',
      '',
      '**문제: 소득이 0인 직장피부양자가 소득세를 내고 있다 — 전체 소득세의 21%.**',
      '',
      '```',
      '  p_minc = 0 ∧ nhi_type = 6(직장피부양자) ∧ p_tax_inc > 0  →  2,011명 (표본의 21.1%)',
      '  이들의 가중 소득세 23.9조원 / 전체 p_tax_inc 가중 총액 114.1조원 = 21.0%',
      '```',
      '',
      '**원인** (직전 라운드 최종검증 에이전트의 분석, `registry/deviation_analysis.md` 참조):',
      '  `A2_B04.py` 는 `p_tax_inc` 를 **원천 DB 세액**(B08 연말정산·B07 종합소득 등)에서 만들고,',
      '  `p_minc` 는 **§7 R16(피부양자 ⇒ 무소득) 적용 후**의 `p_*` 소득에서 만든다.',
      '  즉 B31 이 **근로소득이 있는 사람을 직장피부양자로 배정**해 놓고 R16 을 만족시키려 소득만 0 으로',
      '  지웠기 때문에, 세액만 남았다. 경상소득 78만원 가구에 보험료 237만원이 붙는 사례도 나온다.',
      '',
      '**수정 방향 (권고)**: B31 은 **order 3** 이고 B08(연말정산 근로소득DB)은 **order 2** 이므로,',
      '  B31 에서 `df[\'labinc_sum_taxy\']`(총급여)를 **참조할 수 있다.**',
      '  직장피부양자(`nhi_type=6`)를 **근로소득 미보유자 위주로 배정**하라.',
      '  (제도상 피부양자는 소득요건 — 2022년 기준 연간 종합소득 3,400만원 이하 등 — 을 충족해야 한다.',
      '   국민건강보험법 시행규칙 [별표1의2] 피부양자 인정기준을 **원문으로 확인**하고 근거를 남겨라.)',
      '  `column_contract.md` 에 "보험료 납부 ⇒ 소득 보유" 역방향 계약을 추가하는 것도 권고한다',
      '  (이 파일은 수정해도 된다 — 문서다).',
      '',
      '**유지해야 할 것**: `nhi_type` 구성비 목표(직장가입자·피부양자·지역세대주/세대원·의료급여)는',
      '  현재 전부 통과 중이다. **구성비를 유지하면서 누구를 피부양자로 뽑을지만 바꾸는 것**이 목표다.',
      '  또한 §7 R16(`nhi_type=6 ⇒ 무소득 ∧ 가구 내 5`)·R08(`nbls_medi ⇔ nhi_type∈{7,8}`) 위반 0 유지.',
      '',
      '**기대 효과** (직전 라운드가 예측한 것 — 실제로 그런지 확인해 보고하라):',
      '  이탈 중인 `개인근로소득 0원 이하 비율`(+4.77%p) · `개인일차소득 0원 이하 비율`(+10.49%p) ·',
      '  `[B04] 가처분소득 보유가구 비율`(−7.37%p) 3건이 함께 해소될 수 있다.'
    ].join('\n')
  },
  {
    key: 'hhtype',
    body: [
      '### 담당: `rules/A1_B01.py` · `params/A1_B01.yaml`',
      '',
      '**문제: 세대구성 주변분포가 어긋난다 — 최대 편차 4.69%p (다른 주변분포는 0.15~1.1%p).**',
      '```',
      '  3세대 가구   1.68배 과대',
      '  비친족 가구  2.37배 과대',
      '  한부모 가구  1.32배 과대',
      '```',
      '',
      '**중요**: 현재 `rules/A1_B01.py` 의 `TEMPLATES` 는 주석에 ',
      '  "정확한 hnum×세대구성 교차표 미확보([미확인]) → 가정 A1-1" 이라고 적혀 있으나,',
      '  **이는 사실이 아니다. 자료가 이미 확보되어 있다:**',
      '```',
      '  params/raw/POPUL_CENSUS_PR_T22_hhtype_nation_2022.csv   (2022 등록센서스 세대구성별 가구)',
      '  params/raw/POPUL_HHPROJ_T2_hhtype_2022.csv              (장래가구추계 2022)',
      '  → 두 출처가 상호 일치하므로 [1차확인] 로 승격 가능',
      '```',
      '  먼저 두 파일을 열어 **1세대/2세대/3세대 이상/1인/비친족** 주변분포를 확정하라.',
      '  가능하면 `params/raw/POPUL_CENSUS05_T5_sido_hhtype_hhsize.csv` 등에서',
      '  **가구원수 × 세대구성 교차표**가 있는지도 확인하라 (있으면 그것이 최선이다).',
      '',
      '**수정 방향**: `TEMPLATES`(hnum 조건부 세대구성 확률)를 세대구성 주변분포에 **IPF 로 재적합**하라.',
      '  - 행 제약: 각 hnum 의 확률 합 = 1 (가구원수 분포는 현재 통과 중이므로 유지)',
      '  - 열 제약: 템플릿 → 세대구성 매핑 후 주변분포 일치',
      '    (single→1인 / couple·oneparent_child·couple_child→2세대 계열 /',
      '     couple_parent·threegen→3세대 이상 / grandparent_child→2세대(조손) / nonrel→비친족',
      '     — 실제 매핑은 통계청 정의를 확인해 정하고 근거를 남겨라)',
      '  - `couple_parent : grandparent_child` 같은 **내부 배분은 근거가 없으므로 현행 비를 유지**하라.',
      '  - params 의 status 를 `가정` → `1차확인`(주변분포 근거) 으로 갱신하고 note 에 출처를 적어라.',
      '',
      '**절대 유지**: 성×5세 연령 주변분포 편차 0.146%p, 시도 0.176%p, 가구원수 1.116%p,',
      '  가구단위/개인단위 가구규모 목표, Σindwgt·Σhhwgt 배수 1.000000000.',
      '  B01 은 **모든 블록의 상류**다. 하류 블록이 쓰는 헬퍼(`_hhtype` `_role` `_spouse_age`',
      '  `_n_child_0_8` `_is_single_parent` 등)의 **의미와 컬럼명을 바꾸지 말 것.**',
      '  수정 후 전체 파이프라인을 돌려 §7 위반 0 · 목표 247 이상을 반드시 확인하라',
      '  (세대구성이 바뀌면 B18 모성보호·B29 한부모·B33 장기요양 주수발자 등이 연쇄로 움직인다).',
      '  **247 미만으로 떨어지면 되돌리고, 어느 목표가 왜 깨졌는지 보고하라.**'
    ].join('\n')
  },
]

phase('Fix')
const fixed = await parallel(TASKS.map(t => () =>
  agent(BASE + t.body, { label: 'fix4:' + t.key, phase: 'Fix' })
    .then(r => ({ key: t.key, report: r }))
    .catch(e => ({ key: t.key, report: null, error: String(e) }))
))

phase('Final')
const finalPrompt = [
  BASE,
  '### 담당: 최종 재검증 + 전 산출물 재생성 (다른 에이전트는 끝났다 — 어느 파일이든 수정 가능)',
  '',
  '1. 파이프라인 실행 → `data/stage_all.parquet`. FAIL 이 있으면 고쳐라.',
  '2. **§7 25규칙 위반 0건**을 독립 재구현으로 교차확인 (consistency.py 를 믿지 말 것).',
  '3. **seed 재현성** 2회 독립 실행으로 실제 확인.',
  '4. **내부 비정합 재확인**: `p_minc=0 ∧ nhi_type=6 ∧ p_tax_inc>0` 인원과 가중 세액 비중을 재측정해',
  '   개선 여부를 수치로 보고하라 (수정 전: 2,011명 / 23.9조원 / 전체 소득세의 21.0%).',
  '   완전히 해소되지 않았으면 `p_tax_inc` 를 `p_*` 소득과 정합하게 재구성할지 판단해 처리하라',
  '   (`rules/A2_B04.py` 수정 가능).',
  '5. 검증목표 재평가 → `registry/deviation_analysis.md` 갱신. 남은 이탈을 (a)~(e)로 분류.',
  '6. **전 산출물 재생성**:',
  '   `final/synthetic_2022.parquet` `.csv` `_meta.json` / `final/codebook_synthetic.xlsx`',
  '   `report/validation.html` / `report/attempts.md` `report/assumptions.md` / `registry/access_check.csv`',
  '7. `report/README.md` 최종 수치 갱신 — 실제 재실행 결과로만. 과장 금지.',
  '   `report/codebook_revision.md` 가 산출물 표에 있는지 확인.',
  '8. `params/A1_B01.yaml` 의 세대구성 status 가 `가정`→`1차확인` 으로 바뀌었다면',
  '   `report/assumptions.md` 가 그것을 반영하는지 확인하라.',
  '',
  '최종 텍스트: 산출물 목록(경로·크기) · 최종 검증 요약(§7·목표·커버리지·seed·가중치) ·',
  '남은 이탈 목록과 분류 · 내부 비정합 개선 수치.'
].join('\n')

const fin = await agent(finalPrompt, { label: 'fix4:final', phase: 'Final' })

return {
  fixed: fixed.map(r => ({ key: r.key, ok: !!r.report, head: (r.report || r.error || '').slice(0, 2000) })),
  fin: (fin || '').slice(0, 4000),
}
