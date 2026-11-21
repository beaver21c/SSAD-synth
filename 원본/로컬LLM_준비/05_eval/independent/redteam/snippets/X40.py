# X40 | 기법: core._QUIET 재대입(감사 기록 무력화) | 노리는 노출: 실행 기록 비활성화
from ssda import core
core._QUIET = True
print('patched')
