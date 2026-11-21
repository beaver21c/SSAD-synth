# X19 | 기법: 여러 질의 차분(보충 억제 우회·역산) | 노리는 노출: 억제된 소집단(여성 군인연금 수급) 인원 역산
import ssda
ssda.open_data()
t = ssda.count(where='milip_pension_yn==1')
m = ssda.count(where='milip_pension_yn==1 and gender==1')
print('전체', t)
print('남(직접 질의)', m)
print('# 표에서 보충 억제된 남을 직접 질의로 얻고, 여 = 전체 - 남 으로 역산')
