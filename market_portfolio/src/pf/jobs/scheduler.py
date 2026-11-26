"""매일 배치 스케줄러 (market-jobs 컨테이너의 주 프로세스).

  PF_DAILY_AT=07:15   실행 시각 (기본 07:15)
  PF_TZ=Asia/Seoul    시간대 (미국 장 마감 = 한국 06:00, 서머타임 05:00)

- 컨테이너 시작 시 오늘 배치 기록이 없으면 바로 한 번 실행한다 (재부팅·재배포 후 빈 화면 방지).
- 대기는 최대 5분씩 끊어서 한다 — 맥미니 잠자기·시계 보정 뒤에도 실행 시각을 놓치지 않게.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pf.jobs.run import daily, last_status

CHUNK = 300


def next_run(now: datetime, at: str) -> datetime:
    hh, mm = (int(x) for x in at.split(":"))
    t = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return t if t > now else t + timedelta(days=1)


def ran_today(now: datetime, at: str) -> bool:
    """오늘 실행 시각 이후에 끝난 배치가 있는가."""
    st = last_status()
    if not st or "finished_at" not in st:
        return False
    done = datetime.fromisoformat(st["finished_at"]).astimezone(now.tzinfo)
    hh, mm = (int(x) for x in at.split(":"))
    today_slot = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if now < today_slot:
        today_slot -= timedelta(days=1)
    return done >= today_slot


TZ = ZoneInfo(os.environ.get("PF_TZ", "Asia/Seoul"))


def log(msg: str) -> None:
    """로그 시각도 실행 시간대(KST)로 — 컨테이너 기본 UTC와 섞이지 않게."""
    print(f"{datetime.now(TZ).isoformat(timespec='seconds')} {msg}", flush=True)


def main() -> int:
    tz = TZ
    at = os.environ.get("PF_DAILY_AT", "07:15")
    log(f"scheduler 시작 — 매일 {at} ({tz.key})")
    if not ran_today(datetime.now(tz), at):
        log("최근 실행 시각 이후 배치 기록 없음 → 지금 실행")
        daily()
    while True:
        target = next_run(datetime.now(tz), at)
        log(f"다음 실행 {target.isoformat(timespec='minutes')}")
        while (left := (target - datetime.now(tz)).total_seconds()) > 0:
            time.sleep(min(left, CHUNK))
        daily()


if __name__ == "__main__":
    sys.exit(main())
