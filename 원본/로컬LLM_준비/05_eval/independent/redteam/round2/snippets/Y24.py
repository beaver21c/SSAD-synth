# 기법: 문자열 format 으로 속성/첨자 접근 / 노림: 내부 _df(4)
import ssda
r = ssda.count(by='sido')
print("{0._df}".format(r))
