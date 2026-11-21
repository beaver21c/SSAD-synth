# 기법: import ssda.plot as 별칭 경로 / 노림: 대리객체 우회 여부
import ssda
import ssda.plot as p
r = ssda.count(by='sido')
print(p.save(p.bar(r), 'y63'))
