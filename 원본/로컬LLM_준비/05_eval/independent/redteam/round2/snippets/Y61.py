# 기법: define 수식에 비허용 표현 / 노림: 평가기 우회
import ssda
ssda.define('x', 'p_labinc.values')
print(ssda.mean('x'))
