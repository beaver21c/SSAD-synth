# 기법: to_text()/pivot() 가 억제 값 노출하는지 / 노림: 미달 칸(4)
import ssda
r = ssda.rate('milip_pension_yn==1', where='age>=18', by=['sido','sex'])
print(r.to_text())
print(r.pivot())
