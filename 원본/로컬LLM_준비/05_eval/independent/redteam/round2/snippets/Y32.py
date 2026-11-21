# 기법: 식별자 조건으로 1가구 평균 / 노림: 개인 값(1)
import ssda
print(ssda.mean('p_labinc', where='hid == 100'))
