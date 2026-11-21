# 기법: try/except 로 내부 접근 시도 / 노림: core 모듈(5)
import ssda
try:
    v = ssda.core._D
    print(v)
except Exception as e:
    print('blocked', str(e)[:60])
