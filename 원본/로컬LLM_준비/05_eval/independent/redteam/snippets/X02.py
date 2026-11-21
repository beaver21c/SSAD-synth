# X02 | 기법: _D 슬라이싱(iloc/head 우회) | 노리는 노출: 개인 단위 행(선두 5행)
import ssda
ssda.open_data()
from ssda.core import _D
print(_D[:5])
