# 기법: 결과 객체 내부 _df 직접 접근 / 노림: 억제 전 값(4)
import ssda
r = ssda.count(where='milip_pension_yn==1', by='sido')
print(r._df)
