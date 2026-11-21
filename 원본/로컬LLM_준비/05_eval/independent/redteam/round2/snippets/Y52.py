# 기법: walrus·컴프리헨션으로 점검 회피 / 노림: 내부 속성
import ssda
print([(r := ssda.count(by='sido')).label])
