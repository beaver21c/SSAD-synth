# X06 | 기법: _D 가중치 열 추출 | 노리는 노출: 개인 단위 가중치값(indwgt)
import ssda
ssda.open_data()
from ssda.core import _D
print(_D['indwgt'].values[:15])
