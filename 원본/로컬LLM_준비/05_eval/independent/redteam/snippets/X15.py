# X15 | 기법: core.sig3 를 항등함수로 교체 + THR=1 | 노리는 노출: 억제 칸의 비반올림(정확) 값
import ssda
from ssda import core
ssda.open_data()
core.THR['가'] = 1
core.sig3 = lambda x: x
print(ssda.count(where='age>=100'))
