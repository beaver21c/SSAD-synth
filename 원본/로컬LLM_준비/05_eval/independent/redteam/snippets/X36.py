# X36 | 기법: import 한 _D 에 .iloc 행 인덱서 | 노리는 노출: 개인 단위 한 행
import ssda
ssda.open_data()
from ssda.core import _D
print(_D.iloc[0])
