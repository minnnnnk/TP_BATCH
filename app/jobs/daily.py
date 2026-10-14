"""일일 배치 (B-08): 스케줄러나 cron이 하루 한 번 부르는 진입점.

순서와 이유:
  1. refresh  — 최근 수정된 장소만 받아온다. 보통 1~3회 호출이라 가장 먼저.
  2. gallery  — 관광사진을 끝까지 받을 때까지 이어서 수집 (별도 서비스라 한도도 따로).
  3. enrich   — KorService2에 남은 한도를 모두 상세정보 보강(B-10)에 쓴다.

각 단계는 독립적이라 한 단계가 실패해도 다음 단계는 돈다.
결과는 batch_job_run에 남으므로 'status' 명령으로 확인할 수 있다.
"""
import logging
from typing import Any, Callable, Dict, List

from app import repository
from app.config import Settings
from app.db import connect, init_ingest_schema, try_job_lock
from app.jobs.enrich import calls_per_place, enrich_details
from app.jobs.ingest import gallery_done, ingest_gallery, refresh_places
from app.quota import DailyQuota, QuotaExhausted
from app.tourapi.client import service_name

log = logging.getLogger(__name__)

JOB_NAME = "daily"
LOCK_NAME = "tp_batch2:daily"


def run_daily(settings: Settings) -> Dict[str, Any]:
    kor = service_name(settings.kor_service_base_url)
    gallery = service_name(settings.photo_gallery_base_url)

    with connect(settings) as conn, connect(settings) as quota_conn:
        init_ingest_schema(conn)
        if not try_job_lock(conn, LOCK_NAME):
            log.warning("[daily] 다른 daily가 실행 중이라 건너뜁니다.")
            return {"skipped": "locked"}

        quota = DailyQuota(quota_conn, settings.tour_api_daily_limit)
        run_id = repository.start_job_run(conn, JOB_NAME)
        stats: Dict[str, Any] = {}
        errors: List[str] = []

        def step(name: str, fn: Callable[[], Any]) -> None:
            try:
                stats[name] = fn()
            except QuotaExhausted as exc:
                log.warning("[daily] %s: %s", name, exc)
                stats[name] = {"stopped": "quota"}
            except Exception as exc:
                conn.rollback()
                log.exception("[daily] %s 실패", name)
                errors.append("{0}: {1}".format(name, exc))
                stats[name] = {"error": str(exc)}

        log.info("[daily] 시작 (서비스별 한도 %s회)", settings.tour_api_daily_limit)

        step("refresh", lambda: refresh_places(conn, settings, quota=quota))

        # 갤러리 수집은 페이지를 모았다가 끝에 한 번에 저장하므로, 도중에 한도에 걸리면
        # 받은 것을 잃는다. 남은 한도 안에서만 페이지를 요청한다.
        gallery_pages = min(settings.daily_gallery_max_pages, quota.remaining(gallery))
        if gallery_done(conn, settings):
            stats["gallery"] = {"skipped": "done"}
        elif gallery_pages <= 0:
            stats["gallery"] = {"skipped": "quota"}
        else:
            step(
                "gallery",
                lambda: ingest_gallery(conn, settings, max_pages=gallery_pages, quota=quota),
            )

        per_place = calls_per_place(settings.detail_with_overview)
        budget = quota.remaining(kor) // per_place
        if budget <= 0:
            stats["enrich"] = {"skipped": "quota"}
        else:
            step("enrich", lambda: enrich_details(conn, settings, limit=budget, quota=quota))

        stats["quota_used"] = {kor: quota.used(kor), gallery: quota.used(gallery)}
        status = "success" if not errors else ("failed" if len(errors) >= 3 else "partial")
        repository.finish_job_run(conn, run_id, status, stats, "\n".join(errors) or None)
        log.info("[daily] 종료 (%s) 호출 수 %s", status, stats["quota_used"])
        return stats
