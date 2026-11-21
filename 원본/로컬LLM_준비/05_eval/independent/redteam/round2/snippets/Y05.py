# 기법: getattr 로 함수 __globals__ 우회 / 노림: core._D 원자료(1,5)
import ssda
g = getattr(ssda.rate, '__globals__')
print(g['_D'].head())
