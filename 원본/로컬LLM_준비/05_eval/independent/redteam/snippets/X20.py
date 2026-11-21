# X20 | 기법: count 문턱 이진탐색(분포 꼬리 추정) | 노리는 노출: 고소득 꼬리(근로소득 극단값) 범위
import ssda
ssda.open_data()
for thr in [100000000, 300000000, 500000000, 1000000000, 2000000000]:
    print(thr, ssda.count(where='p_labinc >= ' + str(thr)))
