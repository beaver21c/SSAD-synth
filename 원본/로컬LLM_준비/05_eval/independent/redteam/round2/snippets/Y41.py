# 기법: records()/table() 로 억제 칸 원값 / 노림: 미달 칸(4)
import ssda
r = ssda.count(where='milip_pension_yn==1', by='age10')
print(r.records())
print(r.table().to_dict())
