# X17 | 기법: THR=1 뒤 소집단 비율 | 노리는 노출: 소집단(시도별 100세+) 성별 구성 비율
import ssda
ssda.open_data()
ssda.THR['가'] = 1
ssda.THR['나'] = 1
print(ssda.rate('gender==2', where='age>=100', by='sido'))
