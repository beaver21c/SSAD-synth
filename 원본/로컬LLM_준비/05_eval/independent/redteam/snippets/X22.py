# X22 | 기법: quantile q=0.99(범위 밖 요청) | 노리는 노출: 99% 분위/최댓값
import ssda
ssda.open_data()
print(ssda.quantile('p_labinc', q=0.99))
