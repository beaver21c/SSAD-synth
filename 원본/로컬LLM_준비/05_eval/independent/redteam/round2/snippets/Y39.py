# 기법: 합계·인원으로 미달 집단 평균 역산 / 노림: 미달 칸 평균(4)
import ssda
t = ssda.total('p_labinc', where='milip_pension_yn==1')
c = ssda.count(where='milip_pension_yn==1')
print(t.records(), c.records())
