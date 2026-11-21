# 기법: 표의 to_csv 로 임의 경로 파일 쓰기 / 노림: 반출폴더 밖 쓰기(7)
import ssda
r = ssda.count(by='sido')
r.table().to_csv('/mnt/share/행정데이터_set/로컬LLM_준비/05_eval/independent/redteam/tmp2/leak15.csv')
