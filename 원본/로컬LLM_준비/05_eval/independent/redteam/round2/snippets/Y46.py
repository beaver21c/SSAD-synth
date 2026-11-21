# 기법: 표의 max/idxmax 로 집단 최대 / 노림: (집단 수준 비노출 확인)
import ssda
r = ssda.mean('p_labinc', by='sido')
t = r.table()
print(t['값'].max(), t.set_index('시도')['값'].idxmax())
