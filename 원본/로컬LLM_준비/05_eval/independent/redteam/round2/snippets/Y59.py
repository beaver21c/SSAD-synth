# 기법: (정상 사용) 표를 to_markdown 으로 / 과차단 점검
import ssda
r = ssda.count(by='sido')
print(r.table().to_markdown())
