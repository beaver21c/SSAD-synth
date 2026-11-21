# 기법: 금액 임계 이분탐색으로 극값 좁히기 / 노림: 최댓값 근사(3) [설계상 잔여]
import ssda
for x in [100000000, 300000000, 500000000, 700000000, 900000000]:
    r = ssda.count(where='p_labinc >= ' + str(x))
    print(x, r.records())
