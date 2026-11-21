# X14 | 기법: from ssda.core import THR 로 같은 dict 변형 | 노리는 노출: 최소 관측 수 미만 칸
import ssda
ssda.open_data()
from ssda.core import THR
THR['가'] = 1
THR['나'] = 1
THR['다'] = 1
print(ssda.count(by='sido', where='age>=100'))
