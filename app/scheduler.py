"""B-08 스케줄러: daily 잡을 매일 정해진 시각(한국 시간)에 돌린다.

    python -m app.cli schedule            # 포그라운드로 상주 (DAILY_CRON, 기본 매일 04:00)
    python -m app.cli schedule --run-now  # 띄우자마자 한 번 돌리고 이후 스케줄대로

호출 한도는 한국 시간 자정에 초기화되므로, 새벽에 돌리면 하루치 한도를 온전히 쓴다.
상주 프로세스를 두기 어렵다면 cron/launchd에서 'python -m app.cli daily'를 불러도
똑같이 동작한다 (README 참고). 어느 쪽이든 겹쳐 실행되면 DB 잠금으로 한쪽만 돈다.
"""
import logging
from datetime import datetime

from app.config import Settings
from app.jobs.daily import run_daily
from app.quota import KST

log = logging.getLogger(__name__)

TIMEZONE = "Asia/Seoul"


def _run_daily_safely(settings: Settings) -> None:
    # 예외가 스케줄러 밖으로 새면 다음 실행까지 막히지는 않지만 로그가 묻히므로 여기서 남긴다.
    try:
        run_daily(settings)
    except Exception:
        log.exception("[schedule] daily 실행 실패 — 다음 예정 시각에 다시 시도합니다.")


def run_scheduler(settings: Settings, run_now: bool = False) -> None:
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError as exc:
        raise RuntimeError(
            "APScheduler가 설치되어 있지 않습니다. 'pip install -r requirements.txt'를 실행하세요."
        ) from exc

    scheduler = BlockingScheduler(timezone=TIMEZONE)
    trigger = CronTrigger.from_crontab(settings.daily_cron, timezone=TIMEZONE)
    scheduler.add_job(
        _run_daily_safely,
        trigger,
        args=[settings],
        id="daily",
        max_instances=1,
        coalesce=True,  # 맥이 잠들어 여러 번 놓쳤어도 깨어나면 한 번만 돈다
        misfire_grace_time=3 * 3600,
    )
    if run_now:
        scheduler.add_job(_run_daily_safely, args=[settings], id="daily-now", max_instances=1)

    next_run = trigger.get_next_fire_time(None, datetime.now(KST))
    log.info("[schedule] daily 등록: '%s' (다음 실행 %s). 종료는 Ctrl+C", settings.daily_cron, next_run)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("[schedule] 종료")
