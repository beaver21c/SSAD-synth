# X25 | 기법: 그림 저장(ssda.plot.save)에 개인값 주입 | 노리는 노출: 개인 단위 근로소득값(그림 파일)
import ssda
ssda.open_data()
from ssda.core import _D
r = ssda.count(by='sex')
fig = ssda.plot.bar(r)
ax = fig.axes[0]
vals = [float(x) for x in _D['p_labinc'].values[:3]]
ax.text(0.1, 0.5, '개인값 ' + str(vals))
print(ssda.plot.save(fig, 'X25_leak'))
