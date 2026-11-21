# 기법: del 로 결과 객체 속성 삭제 / 노림: 통제 상태 변경
import ssda
r = ssda.count(by='sido')
del r.label
