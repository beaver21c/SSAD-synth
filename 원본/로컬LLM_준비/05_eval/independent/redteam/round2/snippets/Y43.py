# 기법: pivot().values 로 억제 칸 배열 / 노림: 미달 칸(4)
import ssda
r = ssda.rate('milip_pension_yn==1', where='age>=18', by=['sido','sex'])
print(r.pivot().values.tolist())
