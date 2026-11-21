# 기법: table().to_dict()/.T/.values 로 내부 표현 / 노림: 원값
import ssda
r = ssda.count(by='sido')
print(r.table().T.to_dict())
