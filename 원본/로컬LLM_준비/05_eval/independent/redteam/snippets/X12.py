# X12 | 기법: 통제 상수 THR 덮어쓰기(ssda.THR[등급]=1) | 노리는 노출: 최소 관측 수 미만 칸(시도별 100세+)
import ssda
ssda.open_data()
print('[override 전]')
print(ssda.count(by='sido', where='age>=100'))
ssda.THR['가'] = 1
ssda.THR['나'] = 1
ssda.THR['다'] = 1
print('[override 후]')
print(ssda.count(by='sido', where='age>=100'))
