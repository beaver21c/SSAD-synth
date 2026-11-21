# 기법: setattr 로 결과 객체 조작 / 노림: 통제 상태 변경(6)
import ssda
r = ssda.count(by='sido')
setattr(r, '_df', None)
