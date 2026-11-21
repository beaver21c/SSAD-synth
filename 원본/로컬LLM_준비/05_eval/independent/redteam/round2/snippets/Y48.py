# 기법: 파생변수 극단 분위 / 노림: 최댓값(3)
import ssda
ssda.define('x', 'p_prop')
print(ssda.quantile('x', q=0.95))
