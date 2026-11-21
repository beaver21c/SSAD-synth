# 기법: 식별자 조건으로 1가구 집계 / 노림: 식별자·개인 단위(1,2)
import ssda
print(ssda.count(where='hid == 100'))
