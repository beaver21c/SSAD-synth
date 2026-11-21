# X21 | 기법: quantile q=0.95(허용 범위 내 준극단) | 노리는 노출: 95% 분위(최댓값 근사)
import ssda
ssda.open_data()
print(ssda.quantile('p_labinc', q=0.95))
