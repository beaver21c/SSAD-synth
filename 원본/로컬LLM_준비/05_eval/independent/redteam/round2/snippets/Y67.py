# 기법: str.encode 로 내부 버퍼 접근 / 노림: 우회(정상메서드 과차단도 점검)
import ssda
r = ssda.count(by='sido')
print(r.label.encode('utf-8'))
