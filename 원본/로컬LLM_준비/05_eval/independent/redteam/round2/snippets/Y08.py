# 기법: 통제 기준 import 후 변경 / 노림: 최소 관측 수 1(6)
from ssda import THR
THR['가'] = 1
import ssda
print(ssda.count(where='milip_pension_yn==1', by='sido'))
