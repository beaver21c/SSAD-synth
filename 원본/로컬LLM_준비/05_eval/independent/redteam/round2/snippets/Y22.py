# 기법: map/lambda 로 속성 접근 흉내 / 노림: 내부 속성
import ssda
print(list(map(lambda o: o, [ssda.mean])))
