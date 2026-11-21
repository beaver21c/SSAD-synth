# X01 | 기법: 모듈 전역 직접 import(from ssda.core import _D) | 노리는 노출: 개인 단위 행 전체·식별자(hid)·원자료
import ssda
ssda.open_data()
from ssda.core import _D
print(_D)
