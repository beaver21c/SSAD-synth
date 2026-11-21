# 기법: 고소득 소집단 95% 분위로 최댓값 근사 / 노림: 최댓값(3)
import ssda
print(ssda.quantile('p_labinc', q=0.95, where='p_labinc >= 300000000'))
