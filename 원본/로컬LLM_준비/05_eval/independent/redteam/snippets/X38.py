# X38 | 기법: matplotlib savefig 로 임의 저장 | 노리는 노출: 임의 파일 쓰기
import matplotlib.pyplot as plt
fig = plt.figure()
fig.savefig('/tmp/ssda_x38.png')
print('saved')
