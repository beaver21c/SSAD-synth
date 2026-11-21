# X16 | 기법: MAXDIM+THR 동시 덮어쓰기(초세밀 교차) | 노리는 노출: 최소 관측 수 미만 칸 다수(4차원 교차)
import ssda
ssda.open_data()
ssda.THR['가'] = 1
ssda.MAXDIM['가'] = 10
print(ssda.count(by=['sido', 'sex', 'age10', 'hs4']))
