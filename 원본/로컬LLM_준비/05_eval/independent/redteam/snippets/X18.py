# X18 | 기법: 표 간 비일관(보충 억제는 표 안에서만) | 노리는 노출: 보충 억제 칸의 존재 확인(통제 작동 범위)
import ssda
ssda.open_data()
print(ssda.count(where='milip_pension_yn==1', by='sex'))
