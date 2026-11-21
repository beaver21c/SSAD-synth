# 기법: 두 질의 차분으로 억제 칸 복원 / 노림: 미달 칸(4) [설계상 잔여]
import ssda
a = ssda.count(where='age==99')
b = ssda.count(where='age==99 and gender==1')
print(a.records(), b.records())
