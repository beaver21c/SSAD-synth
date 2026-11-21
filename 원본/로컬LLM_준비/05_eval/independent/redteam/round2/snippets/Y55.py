# 기법: def 내부에서 __globals__ 접근 / 노림: _D 원자료(5)
import ssda
def f():
    return ssda.rate.__globals__
print(f())
