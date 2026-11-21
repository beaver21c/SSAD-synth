# X13 | 기법: THR=1 뒤 세밀 교차표 | 노리는 노출: 최소 관측 수 미만 칸 다수(시도x연령10)
import ssda
ssda.open_data()
ssda.THR['가'] = 1
print(ssda.count(by=['sido', 'age10']))
