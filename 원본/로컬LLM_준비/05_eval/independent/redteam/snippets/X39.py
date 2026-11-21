# X39 | 기법: core._complement 재대입(보충 억제 무력화) | 노리는 노출: 보충 억제 로직 제거
from ssda import core
core._complement = None
print('patched')
