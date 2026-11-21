# acq_popul.md — 소스 확보 기록 (작업코드 popul / 블록 B01·B02 골격 주변분포)

- 담당: 소스 확보 에이전트 (작업지시서 v2)
- 접근일(모든 항목 공통): **2026-09-02**
- 목적: 개인 N≈9,800 / 가구 ≈4,200 골격 생성용 주변분포
  (성×1세 연령 인구, 가구원수 분포, 세대구성 템플릿 확률, 시군구 모집단 규모, 시군구코드↔sido 매핑)
- 환경 전제: KOSIS OpenAPI 인증키 없음(A0). 따라서 **원기관 직접 공표자료(S1)** 및
  **통계청 보도자료 첨부 통계표(S2 동일 원천)** 를 사용.

---

## 1. 확보한 표 (실제 다운로드·열람하여 전사한 것만)

### 1-1. 행정안전부 주민등록 인구통계 (S1, 원기관 직접 공표)

| # | 자료명 / 표 | 기준시점 | URL | HTTP | 원본파일 | 전사 CSV | 행수 | 지위 |
|---|---|---|---|---|---|---|---|---|
| A1 | 주민등록 인구통계 「연령별 인구현황(월간)」 시군구×1세(0~100+)×성(계·남·여) | 2022.11 | POST `https://jumin.mois.go.kr/downloadCsvAge.do?searchYearMonth=month&xlsStats=2` (Referer `ageStatMonth.do`) | 200 (624,585 B, CSV/CP949) | `params/raw/POP_MOIS_2022_11_ageStatMonth_sigungu_1se_sex.cp949.csv` | `params/raw/POPUL_MOIS01_2022_11_sigungu_age1_sex.csv` | 88,173 | **[1차확인]** |
| A2 | 주민등록 인구통계 「지역별 세대원수별 세대수」 시군구×세대원수(1~9,10+) | 2022.11 | POST `https://jumin.mois.go.kr/downloadCsvEtc.do?searchYearMonth=households&xlsStats=2` (Referer `etcStatHouseholds.do`) | 200 (27,116 B, CSV/CP949) | `params/raw/HH_MOIS_2022_11_etcStatHouseholds_sigungu_hhsize.cp949.csv` | `params/raw/POPUL_MOIS02_2022_11_sigungu_hhsize.csv` | 2,717 | **[1차확인]** |

폼 파라미터 재현(성공): `sltOrgType=1&sltOrgLvl1=A&sltOrgLvl2=&gender=gender&sum=sum&sltUndefType=&searchYearStart=2022&searchMonthStart=11&searchYearEnd=2022&searchMonthEnd=11&sltOrderType=1&sltOrderValue=ASC&sltArgTypes=1&sltArgTypeA=0&sltArgTypeB=100&category=month&state=2`
(`sltArgTypes=1` → 1세 단위, `state=2` → 전체 시군구 현황. 세대수는 `category=households`, gender/sum/sltArgTypes 파라미터 없음)

내부 검증(스크립트 산출):
- A1: 시도 17개 합계 = 시군구 229개 합계 = **51,450,829명** (남 25,643,889 / 여 25,806,940) — 완전 일치
- A2: 전국 행 전체세대 **23,699,243** = 1~10인이상 합계 = 시군구 229개 합계 — 완전 일치

### 1-2. 통계청(현 국가데이터처) 2022년 인구주택총조사 등록센서스 (S2 원천의 원기관 공표본)

원본: 보도자료 게시판 bid=203, list_no=426429 (2023-07-27 공표)
- `params/raw/POPUL_CENSUS2022_보도자료_통계표.xls` (139,776 B, seq=16)
- `params/raw/POPUL_CENSUS2022_보도자료.pdf` (12,231,716 B, 125p, seq=13)

| # | 표번호 / 표명 | 단위 | 전사 CSV | 행수 | 지위 |
|---|---|---|---|---|---|
| C1 | 통계표 **표1** 시도별 인구, 가구 및 주택 | 명·가구·호 | `params/raw/POPUL_CENSUS01_T1_sido_pop_hh_dwelling.csv` | 72 | **[1차확인]** |
| C2 | 통계표 **표2** 시군구별 인구(총인구·내국인·외국인 × 계·남·여) | 명 | `params/raw/POPUL_CENSUS02_T2_sigungu_pop_sex_nationality.csv` | 2,538 | **[1차확인]** |
| C3 | 통계표 **표3** 시도 및 연령별 인구(유소년·생산연령·고령 × 성) | 명 | `params/raw/POPUL_CENSUS03_T3_sido_agegroup3_sex.csv` | 312 | **[1차확인]** |
| C5 | 통계표 **표5** 시도별 가구형태 및 가구원수별 가구(1·2·3·4·5인이상, 집단·외국인가구) | 가구 | `params/raw/POPUL_CENSUS05_T5_sido_hhtype_hhsize.csv` | 216 | **[1차확인]** |
| C22 | 보도자료 **표22**(p.48) 가구유형별 가구 및 평균가구원수 — 1세대/2세대/3세대이상/비친족/1인 | 천가구 | `params/raw/POPUL_CENSUS_PR_T22_hhtype_nation_2022.csv` | 9 | **[1차확인]** |
| C25 | 보도자료 **표25**(p.51) 가구원수별 가구(전국) | 천가구 | `params/raw/POPUL_CENSUS_PR_T25_hhsize_nation_2022.csv` | 6 | **[1차확인]** |
| C47 | 보도자료 **표47**(p.78) 성·연령별 1인가구 | 천가구 | `params/raw/POPUL_CENSUS_PR_T47_1person_hh_sex_age_2022.csv` | 24 | **[1차확인]** |
| C58 | 보도자료 **표58**(p.90) 시도별 고령자가구(고령자 있는/고령자만/고령자 1인) | 천가구 | `params/raw/POPUL_CENSUS_PR_T58_sido_elderly_hh_2022.csv` | 18 | **[1차확인]** |

내부 검증:
- C2: 시군구 229개 합계 = 전국 행 = **51,692,272명** (완전 일치). 일반구 32개는 `level='gu'`로 분리 표기(합산 제외).
- C5: 시도 17개 일반가구 합계 = 전국 **21,773,507가구**; 1+2+3+4+5인이상 = 일반가구; 일반+집단+외국인 = 총가구 **22,383,187** (모두 일치)

### 1-3. 통계청 장래가구추계: 2022~2052년 (2024-09 공표) — **2022년 기준연도 실적치만 전사**

원본: 보도자료 게시판 bid=207, list_no=432696, seq=13
- `params/raw/POPUL_HHPROJ2022_장래가구추계_전국편_보도자료.pdf` (1,864,130 B, 45p)
- 사용 사유: 코드북이 요구하는 **가구주 성·연령·세대구성별 가구**(KOSIS DT_1JC1517)를 KOSIS에서 받지 못해,
  동일 원기관이 인구주택총조사를 기초로 공표한 2022년 실적치로 대체. 단위는 **만가구(소수 1자리)**로 정밀도 제한.

| # | 표번호 / 표명 (2022년 열만) | 전사 CSV | 행수 | 지위 |
|---|---|---|---|---|
| P7 | **표7**(p.16) 가구주의 성·연령별 가구 (계/19세이하~80세이상/65세미만·이상, 성별) | `params/raw/POPUL_HHPROJ_T7_head_sex_age_2022.csv` | 33 | **[1차확인]** |
| P2 | **표2**(p.9) 주요 가구유형별 가구 (1인/친족(부부·부부+자녀·부+자녀·모+자녀·3세대이상·기타)/비친족) | `params/raw/POPUL_HHPROJ_T2_hhtype_2022.csv` | 10 | **[1차확인]** |
| P3 | **표3**(p.11) 성·연령별 1인가구 | `params/raw/POPUL_HHPROJ_T3_1person_hh_sex_age_2022.csv` | 33 | **[1차확인]** |
| P456 | **표4·5·6**(p.12~14) 가구주 연령별 부부가구 / 부부+자녀가구 / 부(모)+자녀가구 | `params/raw/POPUL_HHPROJ_T4T5T6_headage_by_hhtype_2022.csv` | 27 | **[1차확인]** |
| P10 | **표10**(p.19) 가구원수별 가구 | `params/raw/POPUL_HHPROJ_T10_hhsize_2022.csv` | 6 | **[1차확인]** |
| P111213 | **표11·12·13**(p.20~22) 가구주 연령별·가구유형별 2인/3인/4인 가구 | `params/raw/POPUL_HHPROJ_T11T12T13_hhsize_headage_type_2022.csv` | 38 | **[1차확인]** |

전사 시 자체 합계 검증(반올림 ±0.2만가구 이내 일치) 완료:
표7 전체 연령합 2,166.3 vs 계 2,166.4 / 표2 친족 소계 1,377.6 vs 1,377.5 / 표10 합 2,166.5 vs 2,166.4 등.

### 1-4. 행정표준코드 시군구코드 5자리 (2022년 기준) + sido 매핑

| 항목 | 내용 |
|---|---|
| 원본1 | `params/raw/CODE_법정동코드_전체자료_code.go.kr.zip` (413,346 B) — POST `https://www.code.go.kr/etc/codeFullDown.do` (`disuseAt=ALL`), HTTP 200 |
| 원본1(전개) | `params/raw/CODE_법정동코드_전체자료.utf8.tsv` (53,387행, 컬럼: 법정동코드/법정동명/폐지여부) |
| 원본2 | `params/raw/POP_MOIS_2022_11_ageStatMonth_sigungu_1se_sex.cp949.csv` 의 행정기관코드 10자리 (**2022.11 시점 스냅샷**) |
| 산출 | `params/raw/CODE_sigungu_2022.csv` (291행) |

컬럼: `sigungu_code(5자리), admin_code10, name_full, sigungu_name, sido_code2, sido_name, sido, level, in_bjd, bjd_status`

- **level 구분**: `sido` 17 / `sigungu` 229 / `gu`(일반구·비자치구) 32 / `branch`(출장소, 행정기관코드에만 존재) 13
  - `sigungu` 229개 확정 근거: 주민등록 「세대원수별 세대수」 파일의 시군구 행 집합(=행안부가 시군구 단위로 공표하는 집합).
  - 시도별 시군구 수: 서울25·부산16·대구8·인천10·광주5·대전5·울산5·세종1·경기31·강원18·충북11·충남15·전북14·전남22·경북23·경남18·제주2 = **229** (2022년 기준, 군위군은 경북 소속)
- **검증**: MOIS 2022.11 행정기관코드 291개 중 277개가 법정동코드에 존재하고 **명칭 불일치 0건**.
  미존재 14개는 출장소 13개 + 세종 시도코드 `3600000000`(법정동코드는 `3611000000` 단일코드) → 모두 소명됨.
  법정동코드 전체자료가 폐지분(강원도42·전라북도45·광주광역시29·전라남도46 등)을 명칭과 함께 보존하므로 2022년 명칭이 그대로 확인됨.
- **sido 매핑** (registry/codebook_vars.csv 18행 `sido` 정의 원문에서 확인한 코드북 순서):
  서울1 · 부산2 · 대구3 · 인천4 · 광주5 · 대전6 · 울산7 · 세종8 · 경기9 · 강원10 · 충북11 · 충남12 · 전북13 · 전남14 · 경북15 · 경남16 · 제주17
  (행정표준 2자리 코드와의 대응: 11→1, 26→2, 27→3, 28→4, 29→5, 30→6, 31→7, 36→8, 41→9, 42→10, 43→11, 44→12, 45→13, 46→14, 47→15, 48→16, 50→17)

---

## 2. 실패 항목 · [미확인] (시도기록)

### 2-1. KOSIS statHtml 스크래핑 실패 — DT_1JC1502 / DT_1JC1517 / DT_1IN1502 / DT_1B040M1
호출 순서와 결과:
1. `GET https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1JC1502&conn_path=I2` → **200** (21,751 B, iframe 셸)
2. `POST https://kosis.kr/statHtml/right_layout.do` → **200** (26,376 B)
3. `POST https://kosis.kr/statHtml/statHtmlContent.do` (ParamInfo 87필드 재현) → **200** (259,531 B, 표명 "가구원수별 가구 - 읍면동" 확인, 수치 없음)
4. `POST https://kosis.kr/statHtml/html.do` (ParamInfo 142필드 재현) → **HTTP 500** (910 B 에러 페이지)
   원인: 그리드 데이터 요청에 필요한 `jsonStr`(분류·항목 선택 트리)가 외부 JS(statHtml.js)에서 동적으로 조립되며 정적 HTML/폼에 없음.
5. 나머지 3개 표에 대해서도 각각 1회씩 확인:
   - `DT_1JC1517` → 셸 200 (21,834 B) / `html.do` **500**
   - `DT_1IN1502` → 셸 200 (21,805 B) / `html.do` **500**
   - `DT_1B040M1` → 셸 200 (21,782 B) / `html.do` **500**
   → 동일 호출 3회 초과 재시도 금지 원칙에 따라 중단. **KOSIS 4개 표 모두 미확보.**
   (KOSIS OpenAPI는 A0에서 인증키 없음 확인 → err=11)

### 2-2. 그 결과로 남는 [미확인] 항목
| 미확보 항목 | 원래 소스 | 현재 상태 | 사용 가능한 대체(등급·범위 명시) |
|---|---|---|---|
| **시군구별 총가구수(센서스 일반가구)** | KOSIS 101/DT_1IN1502 | **[미확인]** | 시도 단위는 센서스 표1·표5로 확보. 시군구 배분은 주민등록 세대수(A2, S1, 2022.11) 사용 — **개념 상이(주민등록 세대 ≠ 센서스 일반가구)** 를 반드시 명시 |
| **가구원수별 가구 – 시군구(센서스)** | KOSIS 101/DT_1JC1502 | **[미확인]** | 센서스 시도 단위(C5) + 주민등록 시군구 세대원수별 세대수(A2). 센서스는 1·2·3·4·5인이상 5구간, 주민등록은 1~9·10인이상 |
| **가구주 성·연령·세대구성별 가구 – 시군구** | KOSIS 101/DT_1JC1517 | **[미확인]** (시군구·시도 단위 모두) | 전국 단위는 장래가구추계 P7·P2·P456·P111213 + 센서스 C22·C47로 확보. **시도 단위 교차표는 미확보** (시도 단위로는 C58 고령자가구만 존재) |
| 행정표준코드의 시군구코드 생성일자·폐지일자 | code.go.kr | **[미확인]** | code.go.kr 공개 다운로드(`codeFullDown.do`, `regCodeFileDown.do`)는 **법정동코드/법정동명/폐지여부 3컬럼만** 제공(날짜 없음). 2022.11 스냅샷은 MOIS 주민등록 2022.11 행정기관코드로 확정(§1-4 검증) |

### 2-3. 그 밖에 시도했으나 성과 없던 경로
| URL / 방법 | HTTP | 결과 |
|---|---|---|
| `https://www.data.go.kr/tcs/dss/selectDataSetList.do` 키워드 `인구주택총조사` / `가구원수별 가구` / `등록센서스` (dType=FILE) | 200 | 전국 시군구 단위 센서스 파일데이터 **없음** (서울시·개별 지자체 자료만) |
| `https://census.go.kr/cds/cdsCensusRslt2021.do?q_menu=3&q_sub=2` | **404** | 데스크톱 도메인 미존재 |
| `https://m.census.go.kr/cds/cdsCensusRslt2021.do?q_menu=3&q_sub=2` | 200 | 통계표 첨부 없음(홍보자료·뷰어만) |
| `https://census.go.kr/sub/ehpp/fc/ehppfc100m01` (연도별 총조사 결과) | 200 | 다국어 안내 PDF만, 통계표 없음 |
| `https://mods.go.kr/board.es` bid=203 검색어 `장래가구추계`/`가구추계`/`장래가구` | 200 | 0건 (해당 자료는 bid=207에 있음 → 재검색 성공) |
| `https://repository.kihasa.re.kr` | — | A0에서 403 확인, 미시도 |

---

## 3. 참고 — 두 원천 간 수치 차이(사용 시 반드시 인지)

| 항목 | 주민등록(행안부, 2022.11) | 등록센서스(통계청, 2022.11.1) |
|---|---|---|
| 총인구 | 51,450,829 (내국인 주민등록) | 51,692,272 (총인구) / 49,939,926 (내국인) / 1,752,346 (외국인) |
| 가구/세대 | 23,699,243 세대 | 22,383,187 총가구 / 21,773,507 일반가구 / 592,468 외국인가구 / 17,212 집단가구 |
| 1인 | 9,719,128 (1인세대) | 7,502,350 (1인가구) |

→ 코드북의 추출대상은 **"2022.11.1. 기준 일반가구 및 일반가구원"** 이므로 **가구 규모·가구원수 분포의 기준은 센서스 일반가구**,
주민등록 자료는 **시군구 배분(상대 가중치)과 1세 연령×성 분포**에 사용하는 것이 정합적임. 이 판단은 [논리적추론]이며 params status에 기록 필요.
