#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""메모리 압력 감시 — 사용자 세션의 메모리 압력이 오르면 작업 단위(scope)를 잠시 멈췄다가 압력이 내려가면 다시 돌린다.

왜 필요한가(2026-11-15 13:31 의 종료 기록)
  · 이 PC 는 systemd-oomd 가 사용자 세션(user@UID.service)의 메모리 압력(PSI, some avg10)을 감시하며, 50% 를 20초 넘게 넘으면
    그 아래 단위 가운데 하나를 통째로 종료한다. RAM 이 남아 있어도 작동한다.
  · llama.cpp 서버가 17.9GiB 양자화본을 HDD 에서 메모리 매핑으로 읽는 동안 압력이 72% 까지 올라 Claude 앱(13:31:29)과
    평가 작업(13:31:44)이 차례로 종료됐다. 당시 작업의 메모리 사용은 8.6GB, 가용 RAM 은 26GB 였다.
    (최근에 캐시에서 밀려난 파일을 느린 디스크에서 다시 읽으며 기다리는 시간이 메모리 압력으로 집계된 것으로 봄)

하는 일
  · 감시 대상의 압력(some avg10)이 --stop 이상이거나, 직전 1초의 정체 비율이 --burst 이상으로 3회 이어지면 작업 단위를 멈춤(cgroup.freeze)
  · 압력이 --resume 이하로 내려가면 다시 돌림. 멈춘 동안에는 작업이 압력을 만들지 않으므로 「50% 를 20초」 조건에 이르지 못함
  · 멈춰도 압력이 계속 올라 --kill 이상이 되고 그 압력이 이 작업에서 나오는 것이면(작업 단위 자체의 압력이 --kill-own 이상) 작업 단위를 끝냄.
    커널 안에서 한 번에 진행되는 읽기(메모리 매핑의 미리 읽기)는 멈춤이 듣지 않기 때문이며, 세션의 다른 프로그램이 종료되는 것보다 이 작업이 끝나는 쪽을 택함
  · 작업 단위가 없어지면 끝남. 끝날 때는 반드시 다시 돌려 놓음

  python 06_build/psi_guard.py --unit ssda-eval-xxxx.scope                # 작업과 다른 단위에서 실행해야 함(같이 멈추지 않도록)
  python 06_build/psi_guard.py --unit … --stop 20 --resume 8 --sample 30   # 30초마다 압력을 기록에 남김
기록  logs/pipeline/psi_guard.log (멈춤·재개와 그때의 압력)
"""
import argparse
import os
import signal
import sys
import time
from pathlib import Path

UID = os.getuid()
SESSION = Path(f'/sys/fs/cgroup/user.slice/user-{UID}.slice/user@{UID}.service')


def read_psi(path):
    """(some avg10, some total 마이크로초)"""
    for line in path.read_text().splitlines():
        if line.startswith('some'):
            f = dict(x.split('=') for x in line.split()[1:])
            return float(f['avg10']), int(f['total'])
    return 0.0, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--unit', required=True, help='작업 단위 이름(예: ssda-eval-1234.scope). app.slice 아래에서 찾음')
    ap.add_argument('--stop', type=float, default=20.0, help='이 값(%%) 이상이면 멈춤')
    ap.add_argument('--resume', type=float, default=8.0, help='이 값(%%) 이하이면 다시 돌림')
    ap.add_argument('--burst', type=float, default=0.7, help='직전 1초의 정체 비율이 이 값 이상으로 3회 이어지면 멈춤')
    ap.add_argument('--kill', type=float, default=38.0, help='멈춰도 세션 압력이 이 값(%%) 이상이고 작업 자체의 압력이 --kill-own 이상이면 작업을 끝냄')
    ap.add_argument('--kill-own', type=float, default=15.0)
    ap.add_argument('--interval', type=float, default=1.0)
    ap.add_argument('--sample', type=float, default=0, help='이 간격(초)마다 압력을 기록(0 이면 상태가 바뀔 때만)')
    ap.add_argument('--wait', type=float, default=60, help='작업 단위가 나타나기를 기다리는 시간(초)')
    ap.add_argument('--log', default=str(Path(__file__).resolve().parent.parent / 'logs' / 'pipeline' / 'psi_guard.log'))
    a = ap.parse_args()
    psi = SESSION / 'memory.pressure'
    cg = SESSION / 'app.slice' / a.unit
    logp = Path(a.log); logp.parent.mkdir(parents=True, exist_ok=True)

    def log(m):
        with open(logp, 'a', encoding='utf-8') as fp:
            fp.write(f"[{time.strftime('%F %T')}] {a.unit}: {m}\n")

    if str(cg) in Path('/proc/self/cgroup').read_text().replace('0::', '/sys/fs/cgroup'):
        log('감시 프로그램이 작업과 같은 단위에 있음. 다른 단위에서 실행할 것'); return 2
    t0 = time.time()
    while not cg.exists():
        if time.time() - t0 > a.wait:
            log(f'작업 단위가 나타나지 않음({a.wait:.0f}초)'); return 1
        time.sleep(0.2)
    frozen = False

    def set_frozen(v):
        nonlocal frozen
        try:
            (cg / 'cgroup.freeze').write_text('1' if v else '0')
            frozen = v
            return True
        except OSError as e:                       # 단위가 그사이 없어진 경우
            log(f'멈춤/재개 실패: {e}')
            return False

    def bye(*_):
        if cg.exists():
            set_frozen(False)
        log('감시 끝')
        sys.exit(0)

    signal.signal(signal.SIGTERM, bye); signal.signal(signal.SIGINT, bye)
    log(f'감시 시작(멈춤 {a.stop}% 이상, 재개 {a.resume}% 이하, 감시 대상 {psi})')
    _, last_total = read_psi(psi); last_t = time.time(); hot = 0; n_freeze = 0; since = 0.0; last_sample = time.time()
    while cg.exists():
        time.sleep(a.interval)
        try:
            avg10, total = read_psi(psi)
        except OSError:
            continue
        now = time.time()
        inst = (total - last_total) / 1e6 / max(now - last_t, 1e-3)       # 직전 구간에서 정체로 보낸 시간의 비율
        last_total, last_t = total, now
        hot = hot + 1 if inst >= a.burst else 0
        if not frozen and (avg10 >= a.stop or hot >= 3):
            if set_frozen(True):
                n_freeze += 1; since = now
                log(f'멈춤 {n_freeze}회째 — 압력 avg10 {avg10:.1f}%, 직전 정체 비율 {inst:.2f}')
        elif frozen and avg10 >= a.kill and now - since >= 4:
            try:
                own, _ = read_psi(cg / 'memory.pressure')
            except OSError:
                own = 0.0
            if own >= a.kill_own:
                log(f'작업을 끝냄 — 멈춘 뒤에도 세션 압력 avg10 {avg10:.1f}%, 작업 자체의 압력 {own:.1f}% (멈춤이 듣지 않는 읽기로 판단)')
                try:
                    (cg / 'cgroup.kill').write_text('1')
                except OSError as e:
                    log(f'끝내기 실패: {e}')
                time.sleep(2)
        elif frozen and avg10 <= a.resume and now - since >= 3:
            if set_frozen(False):
                log(f'재개 — 압력 avg10 {avg10:.1f}% (멈춘 시간 {now - since:.0f}초)')
            hot = 0
        elif frozen and now - since >= 300 and int(now - since) % 300 < a.interval:
            log(f'멈춘 지 {now - since:.0f}초: 압력 avg10 {avg10:.1f}% 가 내려가지 않음(다른 작업이 원인일 수 있음)')
        if a.sample and now - last_sample >= a.sample:
            last_sample = now
            log(f"압력 avg10 {avg10:.1f}%{' (멈춤 중)' if frozen else ''}")
    log(f'작업 단위가 끝남. 멈춤 {n_freeze}회')
    return 0


if __name__ == '__main__':
    sys.exit(main())
