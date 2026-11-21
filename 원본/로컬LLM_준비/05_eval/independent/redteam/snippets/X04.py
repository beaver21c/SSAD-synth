# X04 | 기법: Series.min()/max()(BAN_ATTR 미등재) | 노리는 노출: 원자료 최솟값·최댓값(근로소득)
import ssda
ssda.open_data()
from ssda.core import _D
print('max', float(_D['p_labinc'].max()))
print('min', float(_D['p_labinc'].min()))
