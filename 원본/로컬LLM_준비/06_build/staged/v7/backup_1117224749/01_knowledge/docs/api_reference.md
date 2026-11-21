# 분석 함수 설명서 (ssda 0.1)

모든 함수는 집계 결과만 돌려준다. 개인 단위 행을 보거나 저장하는 방법은 없다.

## 시작하기: 자료 열기와 자료 요약

```python
import ssda
ssda.open_data()      # 자료 열기. 경로는 환경변수 SSDA_DATA 로 정해져 있으므로 인자를 주지 않는다
ssda.info()           # 행 수, 가구 수, 가중 인구, 빈곤선(만원)
```

- 한 번 열면 이후 함수는 자료를 다시 열지 않는다. 열지 않고 집계 함수를 불러도 자동으로 연다.

## 변수 찾기: find_vars, var_info

```python
ssda.find_vars('기초연금')            # 한글 이름·사업명·변수명으로 찾기 → 표(변수명, 한글 이름, 사업, 단위, 등급, 코드값)
ssda.find_vars('장기요양 등급', top=5)
ssda.var_info('nhi_type')            # 변수 한 개의 정의·코드값·추출 대상·등급
```

- 변수명을 모르면 먼저 find_vars 로 확인한다. 변수명을 짐작해서 쓰지 않는다.

## 조건식 쓰는 법 (num, where 인자)

- 조건식은 문자열이다. 쓸 수 있는 것: 변수명, 숫자, 비교(== != < <= > >=), and, or, not, 사칙연산, `in [..]`, `isna(변수)`, `notna(변수)`
- 예: `'age >= 65'`, `'age >= 18 and age <= 64'`, `'bp_yn1 == 1'`, `'nhi_type in [7, 8]'`, `'hnum == 1 and gender == 2'`
- 수급·가입 여부 변수(_yn, _yn1, _yn2)의 해당자는 `'bp_yn1 == 1'`, 해당하지 않는 사람은 `'not (bp_yn1 == 1)'` 로 쓴다. 해당하지 않는 사람이 결측으로 적힌 변수와 0으로 적힌 변수가 섞여 있으므로(12월 기준 변수 등) `isna()`로 판별하지 않는다
- 범주형 변수는 코드값(숫자)이나 항목 이름으로 비교할 수 있다. 예: `"sido == '충북'"`, `"sido in ['서울', '인천', '경기']"`, `"gender == '여'"`. 시도는 이름으로 쓴다(코드: 1 서울, 2 부산, 3 대구, 4 인천, 5 광주, 6 대전, 7 울산, 8 세종, 9 경기, 10 강원, 11 충북, 12 충남, 13 전북, 14 전남, 15 경북, 16 경남, 17 제주)
- 금액 변수의 조건은 원 단위로 쓴다. 예: 근로소득 3천만원 이상은 `'p_labinc >= 30000000'`
- 결측과의 비교는 거짓으로 처리된다
- 파생 변수 `eqinc`(균등화 가처분소득, 만원), `hh_dinc`(가구 가처분소득, 만원), `poor`(빈곤이면 1)를 조건식에 쓸 수 있다
- 분류 기준 이름도 조건식에 쓸 수 있으며 값은 항목 순번(0부터)이다. 예: 소득 1분위는 `'inc5 == 0'`

## 분류 기준 (by 인자): groups, define_group

```python
ssda.groups()         # 표준 분류 기준의 표
```

| 이름 | 뜻 | 항목(순번 0부터) |
|---|---|---|
| sido | 시도 | 서울, 부산, 대구, 인천, 광주, 대전, 울산, 세종, 경기, 강원, 충북, 충남, 전북, 전남, 경북, 경남, 제주 |
| metro2 | 수도권 여부 | 수도권(서울·인천·경기), 비수도권 |
| age3 | 연령대(3구간) | 0~17세, 18~64세, 65세 이상 |
| age6 | 연령대(6구간) | 0~17세, 18~34세, 35~49세, 50~64세, 65~74세, 75세 이상 |
| age10 | 연령대(10세) | 0~9세 … 70~79세, 80세 이상 |
| sex | 성 | 남, 여 |
| hs4 | 가구원수 | 1인, 2인, 3인, 4인 이상 |
| inc5 | 소득 5분위(균등화 가처분소득) | 1분위(하위 20%) … 5분위(상위 20%) |
| nhi3 | 건강보험 가입 구분 | 지역가입, 직장가입, 의료급여 |
| poor2 | 빈곤 여부 | 비빈곤, 빈곤 |

- by 는 이름 하나(`'sido'`) 또는 목록(`['age6', 'sex']`)으로 준다
- 범주가 15개 이하인 범주형 변수(예: `nhi_type`, `bp_type`)도 by 에 쓸 수 있다
- 수치 변수의 다른 구간이 필요하면 define_group 으로, 코드값의 묶음이나 조건으로 나눈 집단은 define_cond 로 직접 만든다

```python
ssda.define_group('age_old', 'age', [65, 75, 85], ['65세 미만', '65~74세', '75~84세', '85세 이상'])
ssda.rate('ltcare_bn_yn == 1', where='age >= 65', by='age_old')
```

```python
ssda.define_cond('region2', {'수도권': "sido in ['서울', '인천', '경기']"}, other='비수도권')      # 조건으로 나눈 분류 기준. other 는 어느 조건에도 들지 않는 사람의 항목 이름
ssda.define_cond('g4', {'1·2등급': 'ltcare_grade in [1, 2]', '3등급': 'ltcare_grade == 3', '4등급': 'ltcare_grade == 4', '5등급': 'ltcare_grade == 5'})
ssda.define_cond('bp', {'수급자': 'bp_yn1 == 1'}, other='비수급자')
ssda.rate('ltcare_bn_yn == 1', where='age >= 65', by='bp')
```

- define_group 은 수치 변수(연령, 금액, 일수)의 구간에만 쓴다. 질문이 정한 구간 그대로 만들고 질문에 없는 경계를 더하지 않는다. 코드값으로 된 범주형 변수(시도, 등급, 유형)는 define_cond 로 묶는다
- define_cond 의 조건은 서로 겹치지 않아야 한다. other 를 주지 않으면 어느 조건에도 들지 않는 사람은 표에서 빠진다
- 시군구(city)는 분류 기준으로 쓸 수 없다(범주가 15개를 넘음). 시군구 단위 조회는 대시보드의 지표 지도를 사용한다

## 집계 함수: rate

```python
ssda.rate(num, where=None, by=None, unit='개인', label=None)
```

- 비율(%) = num 에 해당하는 가중 인원 ÷ where 에 해당하는 가중 인원 × 100
- where 는 분모(대상 집단)이다. 수급률의 분모는 제도의 대상 연령·집단으로 준다
- 결과 표의 열: 분류 기준, 값(%), 해당 인원, 대상 인원, 상태

```python
r = ssda.rate('bp_yn1 == 1', where='age >= 65', by='sido', label='시도별 기초연금 수급률')
print(r)
```

## 집계 함수: mean, total, quantile, count, share, poverty_rate

```python
ssda.mean(var, where=None, by=None, unit='개인', label=None)       # 가중 평균(결측 제외). 금액(원)은 만원으로 환산
ssda.total(var, where=None, by=None)                              # 가중 합계. 금액(원)은 만원으로 환산
ssda.quantile(var, q=0.5, where=None, by=None)                    # 가중 분위수. q는 0.05~0.95, 중위수는 0.5
ssda.count(where=None, by=None, unit='개인')                       # 가중 인원. unit='가구' 이면 가구 수
ssda.share(var, where=None)                                       # 범주형 변수·분류 기준의 구성비(%)
ssda.poverty_rate(where=None, by=None)                            # 상대 빈곤율(%)
```

- 「합계」「총액」은 total, 「평균」「1인당」은 mean, 「중위수」는 quantile(변수, 0.5)로 산출한다. 요청한 지표를 다른 지표로 바꾸지 않는다
- 수급자 1인당 평균 금액은 where 에 수급 조건을 넣는다: `ssda.mean('bp_amt', where='bp_yn1 == 1', by='age6')`
- 대상 인구 1인당 평균은 금액의 결측을 0으로 보아야 하므로 `ssda.total(...)` 과 `ssda.count(...)` 를 나누어 구한다
- 가구 단위 집계는 `unit='가구'` 를 준다(가구주 행과 가구 가중치를 사용)

## 파생 변수: define

```python
ssda.define('pub_share', 'p_pubinc / p_dinc', label='가처분소득 대비 공적이전소득 비율')
ssda.mean('pub_share', where='age >= 65 and p_dinc > 0')
```

## 합계 변수: define_sum

```python
ssda.define_sum('fee_all', ['nhi_out_fee', 'nhi_in_fee'], '외래·입원 본인부담금')
ssda.mean('fee_all', where='age >= 65', by='sex')
```

- 여러 금액 변수를 더한 파생 변수를 만든다. 값이 없는 항목은 0으로 보고 더하며, 모든 항목에 값이 없는 사람은 값이 없는 것으로 둔다(평균·분위수에서 제외)
- 단위가 같은 변수끼리만 더할 수 있다. 「본인부담금 전체」「진료비 전체」처럼 여러 내역을 합한 금액을 요청받았을 때 쓴다

## 결과 다루기 (Result)

```python
print(r)                 # 표(억제 칸은 「억제」로 표시)
r.table()                # 표(pandas DataFrame). 억제 칸의 값은 비어 있음
r.pivot()                # 분류 기준이 2개일 때 행×열 표
r.value(시도='서울')       # 한 칸의 값(억제 칸은 None)
r.summary()              # 지표, 단위, 등급, 최소 관측 수, 칸 수, 표시하지 않는 칸 수
r.save('표이름')           # 반출 신청 폴더에 표 저장(통제를 거친 집계값만 저장됨)
```

- 결과 표의 상태 열: 표시 / 억제(최소 관측 수 미달) / 보충 억제(합계에서 역산되지 않도록 추가로 억제) / 대상 없음

## 그림: ssda.plot

```python
fig = ssda.plot.bar(r, title=None, sort=False, values=True)     # 막대(분류 기준 1개) 또는 묶음 막대(2개)
fig = ssda.plot.hbar(r, title=None, sort=True)                  # 가로 막대(항목이 많을 때)
fig = ssda.plot.line(r, title=None)                             # 선(연령대처럼 순서가 있는 기준)
fig = ssda.plot.heatmap(r, title=None)                          # 색 농도 표(분류 기준 2개)
fig = ssda.plot.map_sido(r, title=None, cmap='Blues', k=5)      # 시도 지도(by='sido' 인 결과)
ssda.plot.save(fig, '그림이름')                                   # 반출 신청 폴더에 PNG 저장
```

- 그림은 집계 결과(Result)로만 그릴 수 있다. matplotlib 을 직접 불러 개인 단위 자료를 그리지 않는다
- 억제 칸은 그리지 않고 「억제」로 표기된다

## 오류 메시지와 대처

| 메시지 | 뜻 | 대처 |
|---|---|---|
| QueryError: 없는 변수 | 변수명이 틀림 | find_vars 로 변수명 확인 |
| QueryError: 조건식에 허용되지 않는 표현 | 함수 호출·문자열 비교 등을 씀 | 허용된 표현만 사용 |
| QueryError: 범주가 15개를 넘어 분류 기준으로 쓸 수 없음 | 연속형 변수나 시군구를 by 에 줌 | define_group 으로 구간을 만들거나 표준 분류 기준 사용 |
| ControlError: 분류 기준을 N개까지만 | 등급에 비해 분류 기준이 많음 | 분류 기준을 줄임 |
| ControlError: 분위수는 0.05~0.95 | 극단 분위·최댓값 요청 | 범위 안의 분위수 사용 |
