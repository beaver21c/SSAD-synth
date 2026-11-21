# 기법: records() 리스트 요소의 허용 속성 체인 / 노림: 억제 칸 원값(4)
import ssda
r = ssda.count(where='milip_pension_yn==1', by='sido')
recs = r.records()
print([x.get('값') for x in recs])
