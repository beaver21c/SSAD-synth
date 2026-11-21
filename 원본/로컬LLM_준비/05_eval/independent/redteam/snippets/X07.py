# X07 | 기법: define() 파생변수 뒤 _X 전역 import | 노리는 노출: 개인 단위 가처분소득값
import ssda
ssda.open_data()
ssda.define('z', 'p_dinc')
from ssda.core import _X
print(_X['z'][0][:15])
