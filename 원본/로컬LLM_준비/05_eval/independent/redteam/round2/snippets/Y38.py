# 기법: 파생변수로 민감 변수 등급 세탁 / 노림: 최소 관측 수 완화(6)
import ssda
ssda.define('x', 'p_labinc * 1')
r = ssda.quantile('x', q=0.5, by='sido')
print(r.summary())
