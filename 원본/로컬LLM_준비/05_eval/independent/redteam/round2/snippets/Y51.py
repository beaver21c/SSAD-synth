# 기법: 전체합-부분합 차분으로 소수집단 합계 / 노림: 미달 칸 합계(4) [설계상 잔여]
import ssda
tot = ssda.total('p_labinc')
sub = ssda.total('p_labinc', where='age < 100')
print(tot.records(), sub.records())
