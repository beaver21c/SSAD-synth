# 기법: 연속변수 임계 차분으로 극단 꼬리 좁히기 / 노림: 개인 값 근사(1,3) [설계상 잔여]
import ssda
for x in [600000000, 650000000, 700000000, 750000000, 800000000]:
    r = ssda.count(where='p_labinc >= ' + str(x))
    print(x, r.records()[0])
