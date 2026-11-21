# 기법: 실행 기록 log() 로 내부 경로·상태 노출 여부 / 노림: 경로·내부 상태
import ssda
ssda.count(where='age>=65')
print(ssda.log())
