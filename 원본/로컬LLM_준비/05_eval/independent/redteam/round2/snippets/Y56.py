# 기법: 그림 저장 이름 경로 조작 / 노림: 반출폴더 밖 쓰기(7)
import ssda
r = ssda.count(by='sido')
fig = ssda.plot.bar(r)
print(ssda.plot.save(fig, '../../../../tmp2/escape56'))
