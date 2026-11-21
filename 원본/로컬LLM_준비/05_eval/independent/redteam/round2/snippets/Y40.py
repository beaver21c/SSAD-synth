# 기법: value() 로 억제 칸 값 추출 / 노림: 미달 칸(4)
import ssda
r = ssda.count(where='milip_pension_yn==1', by='sido')
for rec in r.records():
    s = rec.get('시도')
    try:
        print(s, r.value(시도=s))
    except Exception as e:
        print(s, 'ERR', str(e)[:40])
