# X03 | 기법: _D 식별자 열 추출(.values 슬라이스) | 노리는 노출: 가구 식별자 hid 개별값
import ssda
ssda.open_data()
from ssda.core import _D
print(_D['hid'].values[:30])
