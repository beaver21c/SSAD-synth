# 원본/ 구성 목록(MANIFEST)

- 작성일: 2026-11-22
- 내용: PC 작업 폴더 `행정데이터_set` 의 산출물 사본. 경로는 `행정데이터_set` 기준 상대경로와 같음
- 자료의 성격: 모든 개인 단위 자료는 코드북과 같은 변수 구조로 생성한 가상데이터이며 실제 개인·가구에 대응하지 않음. 집계값은 가상데이터의 값이며 실제 현황이 아님
- 규모: 파일 1,309개, 115.98MB(이 문서 제외)
- 복사 방식: 내용 수정 없이 그대로 복사. 대상 선정·제외는 아래 기준을 따름

## 1. 경로별 파일 수와 용량

| 경로 | 파일 수 | 용량 | 내용 |
|---|---:|---:|---|
| `work/report/활용고도화전략/적용사례/data` | 5 | 29.88MB | 가상데이터 확대 생성본(parquet), 집계 저장소·경계·모의실험 결과(json) |
| `work/report/활용고도화전략/적용사례/scripts` | 6 | 89.7KB | 확대 생성, 집계 저장소, 정책 모의실험, 대시보드 조립 스크립트 |
| `work/report/활용고도화전략/적용사례/dashboard` | 1 | 83.2KB | 대시보드 화면 틀(template.html) |
| `work/report/활용고도화전략/적용사례/사회보장행정데이터_대시보드.html` | 1 | 2.63MB | 대시보드 최신본(2026-11-21 조립, 파일 1개로 동작) |
| `로컬LLM_준비/01_knowledge` | 21 | 1.86MB | 변수·제도·문서 카드, 용어 사전, 분석 규칙 |
| `로컬LLM_준비/02_library` | 9 | 1.00MB | 분석 함수 묶음 ssda |
| `로컬LLM_준비/03_prompts` | 12 | 0.15MB | 시스템 프롬프트(개선판별) |
| `로컬LLM_준비/04_training` | 3 | 0.12MB | 학습 자료 생성·검증 스크립트 |
| `로컬LLM_준비/05_eval` | 485 | 9.96MB | 평가 문항·채점 기준·채점기, 독립 검증(independent), 실행별 report.json, 최종 구성 transcripts.jsonl |
| `로컬LLM_준비/06_build` | 592 | 37.11MB | 조립기(assistant.py), 검색기, 평가·구동 스크립트, 검색 색인, 단계별 보관본(staged) |
| `로컬LLM_준비/config` | 2 | 9.7KB | 조립기 설정(assistant.yaml, assistant_lora.yaml) |
| `발표자료_행정데이터_AI/demo` | 8 | 29.69MB | 자연어 명령 창 시제품(실행기·덧붙임 모듈·작업자·화면 코드·자료 생성), 화면용 CSV, OpenStat 사본 중 달라진 파일 |
| `work/tools` | 54 | 0.44MB | 가상데이터 생성 체계의 도구(생성·검증·수집) |
| `work/rules` | 29 | 0.71MB | 블록별 생성 규칙 |
| `work/targets` | 18 | 0.13MB | 캘리브레이션·검증 목표값(공개 통계와 공개 보고서의 표) |
| `work/registry` | 62 | 2.10MB | 코드북 구조, 자료 수집 기록, 점검 기록 |
| `work/final/synthetic_2022_meta.json` | 1 | 9.4KB | 가상데이터(기본 생성본) 메타 정보 |

### 05_eval 세부

| 구분 | 파일 수 | 용량 |
|---|---:|---:|
| 05_eval(문항·기준·채점기) | 16 | 0.42MB |
| 05_eval/independent(문항·기준·설계서·채점기) | 441 | 7.68MB |
| 05_eval/runs(report.json) | 27 | 1.08MB |
| 05_eval/runs(최종 구성 transcripts) | 1 | 0.78MB |

- independent 에 넣은 것: 문항(items, 변형 문항, 문항 작성 입력 자료·사실 자료, 통제 계층 시험 조각), 채점 기준(판정 기준, 정답 키, 사전 확정 기준 freeze, 정답 truth), 설계서·회차 계획, 채점기(파이썬), 회차 결과 요약(결과.json)
- 실행별 `report.json`: 27개 실행. `report.json` 이 없는 실행(독립 검증 회차 실행 등)은 넣지 않았으며 회차 결과는 `independent/결과.json`, `independent/r*/결과.json` 에 있음
- 최종 구성의 `transcripts.jsonl`: `05_eval/runs/r5_v9`(독립 검증 5차 판정 실행, 개선판 5 + 규칙 묶음 9, 44문항 완료, 실행 당시 ssda 0.7.0)

### OpenStat 사본 중 pyopenstat 원본(25b824f)과 달라진 파일

- `발표자료_행정데이터_AI/demo/openstat/reconstructed/pyjamovi/command_log.py` (고침)
- `발표자료_행정데이터_AI/demo/openstat/sample_data/geo/시도경계_간략.geojson` (추가)
- 비교 결과: 사본 262개 파일 중 140개가 원본과 같음(미포함). 실행 중 생긴 기록·보고 파일은 아래 제외 항목 참조
- 화면용 CSV `openstat/sample_data/사회보장행정데이터_가상_주요변수.csv` 는 요청 목록의 항목으로 따로 포함

## 2. 제외 항목과 이유

| 이유 | 건수 |
|---|---:|
| 05_eval/runs: report.json 과 최종 구성 1개의 transcripts.jsonl 만 | 1,162 |
| independent: 판정 묶음·판정 기록(문항별 모형 응답 포함) — 요청 목록 밖 | 226 |
| openstat 사본: 실행 중 생긴 기록·보고 파일(원본과 달라진 소스 파일 아님) | 119 |
| independent: 실행 결과·중간 산출물 — 요청 목록 밖 | 39 |
| 05_eval/analysis: 요청 목록(문항·채점 기준·설계서·채점기·report·최종 transcripts) 밖 | 14 |
| demo: 요청 목록 밖(갈무리 스크립트·백업·임시 폴더 등) | 13 |
| 학습 체크포인트 | 9 |
| 04_training 은 스크립트만(학습 자료·통계·문서 제외) | 7 |
| 06_build/runs: LoRA 어댑터 폴더(가중치·토크나이저·대화 틀 등 모형 부속 파일) | 6 |
| 로컬LLM_준비: 요청 목록 밖 파일(폴더 바로 아래 문서) | 5 |
| 모형 가중치·이진 가중치 형식 | 4 |
| 로컬LLM_준비: 요청 목록 밖 폴더 | 4 |

- 모형 가중치: `06_build/runs/lora_assistant_v1` 의 LoRA 어댑터(`adapter_model.safetensors` 4개, 각 약 934MB)와 체크포인트 3개 폴더, 같은 폴더의 토크나이저·대화 틀·모형 카드. GGUF 양자화 파일은 `행정데이터_set` 밖(`/mnt/share/models`)에 있어 대상이 아님
- 캐시·가상환경: `__pycache__`, `.pyc`, `.venv` 는 탐색 단계에서 건너뜀(위 건수에 포함되지 않음)
- 95MB 초과 파일: 복사 대상 안에서는 가중치 파일뿐임(가장 큰 포함 파일은 화면용 CSV 29.4MB, 가상데이터 parquet 27.3MB)
- 04_training: 스크립트(`generate.py`, `validate.py`, `token_stats.py`)만 포함. 학습 자료(`data/*.jsonl`)·통계·데이터카드 제외
- 05_eval/runs: 실행별 `report.json` 과 최종 구성 1개의 `transcripts.jsonl` 만 포함. 나머지 대화 기록·호출 기록·반출 폴더·실행 메타 제외
- 05_eval/independent: 판정 묶음(`packet_*.md`, 문항별 모형 응답 포함)과 판정 기록(`verdict_*.jsonl`), 실행 결과·중간 산출물 제외
- demo: 요청 목록 밖의 갈무리 스크립트, 백업·임시 폴더, `termfix/` 제외. `nl_worker.py` 는 `demo/termfix` 를 그림 표기용 경로로 참조하며, 이 폴더가 없어도 동작함(그림의 표기만 바뀌지 않음)
- 로컬LLM_준비 폴더 바로 아래 문서(README, 구축지시서 등)와 `docs/`, `logs/`, `export/`, `모형반입/`: 요청 목록 밖
- 발표자료 본체와 그림 폴더(`발표자료_행정데이터_AI` 의 HTML·PDF·`figures/`), 가상데이터 기본 생성본(`work/final` 의 csv·parquet·xlsx): 요청 목록 밖
- 실제(비가상) 행정데이터에서 나온 자료: 복사 대상에 없음. `피벗`·`명세서` 낱말 검사 0건

### 내용 검사 결과

- 검사 항목: 접근 토큰·비밀 키 형식, 키 인자(serviceKey·apiKey 등), 법령 API 식별자(OC), 이메일, 전화·주민등록번호 형식, 계정 경로, 사용자 이름·계정
- 결과: 제외할 파일 0개
  - 이메일 형식 3건: systemd 단위 이름(`user@UID.service`)으로 이메일이 아님
  - 법령 API 식별자 11개 파일: 값이 모두 공개 예시용 `OC=test`
  - 계정 경로 형식 6개 파일: 고용노동부 누리집 주소의 경로(`/home/hp/…`)로 계정 경로가 아님
  - 토큰·키, 전화·주민등록번호 형식, 사용자 이름·계정: 0건

### 자료 출처에 관한 참고

- `work/targets`, `work/rules`, `work/registry` 의 목표값·수집 기록은 공개 통계(국가통계포털, 국세통계, 각 기관 통계연보)와 한국보건사회연구원 「사회보장 행정데이터 구축 및 기초분석」 보고서(2023, 2024)의 표에 실린 집계값을 옮긴 것임. 보고서 원문 파일은 포함하지 않음
- `work/registry/codebook.json`, `codebook_vars.csv` 는 가상데이터가 따르는 코드북의 변수 구조임

## 3. 분석 함수와 최종 기본 구성

| 항목 | 값 |
|---|---|
| 분석 함수 ssda | 0.7.6 (`로컬LLM_준비/02_library/ssda/__init__.py`) |
| 프롬프트 판 | 개선판 5 (`로컬LLM_준비/03_prompts/system_prompt_v5.md`) |
| 규칙 묶음 | 9 (`config/assistant.yaml` 의 `verify.ruleset`, 실행 시 환경변수 `SSDA_RULESET` 으로 전달) |
| SSDA_HOOKS | `user_code=replace,repeat_guard=1,var_candidates=1,unexecuted_results=1` (판정 실행 스크립트 `06_build/run_pipeline_indep3.sh` 의 값) |
| 보완 동작 전체(실행 기록 `r5_v9` 의 hooks) | user_code=replace, repeat_guard=true, var_candidates=true, unexecuted_results=true, ask_gate=true, name_cards=true, diff_guard=true, precheck=true, review=false, ruleset=9 |
| 문맥 길이 | 32,768 토큰(`config/assistant.yaml` 의 `context_tokens`, 2026-11-19 변경) |
| 모형 | NousResearch/Arete-27B 공식 가중치의 양자화본(Q5_K_M, llama.cpp). 가중치 파일 미포함 |
| 생성 온도 | 0.0, 사고 과정 출력 끔 |

- `SSDA_HOOKS` 는 평가에서 보완 동작만 바꿔 볼 때 쓰는 환경변수이며, 지정하지 않으면 `config/assistant.yaml` 의 값(위 표의 「보완 동작 전체」와 같음)을 씀
- 독립 검증 판정: 4차 「신뢰 가능」, 5차(제도·현안 과제형)·6차(문서형 요청) 「신뢰 미흡」. 회차별 결과는 `로컬LLM_준비/05_eval/independent/r*/결과.json`

## 4. 실행에 필요한데 포함되지 않은 것

- 모형 가중치(Arete-27B 양자화 파일): 실시간 구동(`--mode live`)에 필요. 기록 재생(`--mode replay`)은 `05_eval/runs` 의 대화 기록을 쓰며, 이 사본에는 `r5_v9` 1개 실행의 기록만 있음
- OpenStat 원본: `beaver21c/pyopenstat` 25b824f 위에 위 「달라진 파일」을 덮어 사용
