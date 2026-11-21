# 기법: 금액 구간을 잘게 쪼개 소수 칸 노출 / 노림: 최솟·최댓값 근처(3,4)
import ssda
ssda.define_group('fine', 'p_labinc', [490000000, 500000000, 510000000], ['490미만','490-500','500-510','510이상'])
print(ssda.count(by='fine'))
