"""TourAPI 수집 잡 (TourAPI -> place / place_gallery_image).

개발계정 일일 호출 한도 때문에 한 번에 전량을 못 가져오므로,
fetch_cursor에 마지막 페이지를 기록해두고 다음 실행에서 이어받는다.
(Kotlin 배치의 FetchCursorTable과 같은 테이블/같은 의미)

전량 수집이 끝난 뒤에는 refresh_places로 최근 수정분만 따라잡는다.
"""
import logging
from typing import Any, Dict, Optional

from psycopg2.extensions import connection as PgConnection

from app import repository
from app.config import Settings
from app.tourapi.client import TourApiClient
from app.tourapi.gallery import GalleryImageApi
from app.tourapi.kor_service import KorServiceApi

log = logging.getLogger(__name__)

SOURCE_AREA = "areaBasedList2"
SOURCE_GALLERY = "galleryList1"


def make_client(settings: Settings, base_url: str, quota=None) -> TourApiClient:
    return TourApiClient(
        base_url,
        settings.tour_api_service_key,
        settings.mobile_app,
        settings.request_timeout_sec,
        quota=quota,
    )


def ingest_area(
    conn: Optional[PgConnection],
    settings: Settings,
    area_code: Optional[str] = None,
    content_type_id: Optional[str] = None,
    max_pages: Optional[int] = None,
    restart: bool = False,
    dry_run: bool = False,
    quota=None,
) -> int:
    """지역기반 관광정보를 수집해 place에 upsert 한다 (dry_run 시 DB 삽입 없음)."""
    if not settings.tour_api_service_key:
        raise RuntimeError(
            "TourAPI 서비스키가 설정되지 않았습니다. .env 또는 secrets.properties에 "
            "TOUR_API_SERVICE_KEY (tour.api.serviceKey)를 설정하세요."
        )

    client = make_client(settings, settings.kor_service_base_url, quota)
    api = KorServiceApi(client)

    # 조건별로 페이지 번호 체계가 달라지므로 커서 키도 조건별로 나눈다.
    source_key = SOURCE_AREA
    if area_code:
        source_key += ":area={0}".format(area_code)
    if content_type_id:
        source_key += ":type={0}".format(content_type_id)

    if dry_run or conn is None:
        start_page = 1
        pages = max_pages or 1
    else:
        start_page = 1 if restart else repository.get_last_page(conn, source_key) + 1
        pages = max_pages if max_pages is not None else settings.max_pages

    log.info(
        "[ingest-area%s] source=%s, %s페이지부터 %s페이지 수집 시작",
        " (dry-run)" if dry_run else "",
        source_key,
        start_page,
        pages,
    )

    try:
        result = api.fetch_area_based_list(
            area_code=area_code,
            content_type_id=content_type_id,
            num_of_rows=settings.num_of_rows,
            start_page=start_page,
            max_pages=pages,
        )
    finally:
        client.close()

    if not result.items:
        log.info("[ingest-area] 새로 가져온 항목이 없습니다.")
        return 0

    if dry_run or conn is None:
        log.info("[ingest-area --dry-run] API 수신 성공: 총 %s건 수신 (전체 %s건 중)", len(result.items), result.total_count)
        for i, item in enumerate(result.items[:5], 1):
            log.info("  [%s] contentid=%s | title=%s | addr=%s | coords=(%s, %s)",
                     i, item.get("contentid"), item.get("title"), item.get("addr1"), item.get("mapy"), item.get("mapx"))
        if len(result.items) > 5:
            log.info("  ... 외 %s건 추가 수신됨 (DB 삽입 없이 테스트 완료)", len(result.items) - 5)
        return len(result.items)

    saved = repository.save_place_items(conn, result.items, settings.chunk_size)
    repository.save_cursor(
        conn, source_key, result.last_page_fetched, result.total_count
    )

    log.info(
        "[ingest-area] %s건 upsert 완료 (page %s까지, 전체 %s건, %s)",
        saved,
        result.last_page_fetched,
        result.total_count,
        "수집 완료" if result.exhausted else "남은 페이지 있음 — 다시 실행하면 이어서 수집",
    )
    return saved


def refresh_places(
    conn: PgConnection,
    settings: Settings,
    max_pages: Optional[int] = None,
    quota=None,
) -> Dict[str, Any]:
    """최근 수정된 장소만 따라잡는다 (B-08 일일 갱신).

    전국 목록을 수정일 최신순(arrange=C)으로 앞에서부터 읽고, DB에 있는 가장 최근
    수정일시(watermark)보다 오래된 항목이 나오면 멈춘다. 보통 하루 1~3페이지면 끝난다.
    수정일시가 바뀐 장소는 place_detail과 어긋나므로 다음 enrich에서 다시 조회된다.

    한계: 목록 API는 '표출 중'인 장소만 주므로, TourAPI에서 내려간 장소는 지워지지 않는다.
    """
    watermark = repository.max_place_modified_time(conn)
    pages = max_pages if max_pages is not None else settings.daily_refresh_max_pages
    log.info("[refresh] 기준 수정일시 %s 이후 변경분 조회 (최대 %s페이지)", watermark, pages)

    client = make_client(settings, settings.kor_service_base_url, quota)
    api = KorServiceApi(client)
    saved = 0
    pages_read = 0
    caught_up = False
    try:
        for page_no in range(1, pages + 1):
            page = api.fetch_recent_page(page_no, settings.num_of_rows)
            pages_read = page_no
            if not page.items:
                caught_up = True
                break
            saved += repository.save_place_items(conn, page.items, settings.chunk_size)
            oldest = min(str(i.get("modifiedtime") or "") for i in page.items)
            if watermark and oldest <= watermark:
                caught_up = True
                break
    finally:
        client.close()

    log.info(
        "[refresh] %s페이지, %s건 upsert (%s)",
        pages_read,
        saved,
        "최신 상태" if caught_up else "변경분이 더 남음 — 다음 실행에서 이어서",
    )
    return {"pages": pages_read, "upserted": saved, "caught_up": caught_up}


def gallery_done(conn: PgConnection, settings: Settings) -> bool:
    """갤러리 커서가 마지막 페이지까지 갔는지."""
    for source, last_page, total in repository.list_cursors(conn):
        if source == SOURCE_GALLERY:
            return total > 0 and last_page * settings.num_of_rows >= total
    return False


def ingest_gallery(
    conn: PgConnection,
    settings: Settings,
    max_pages: Optional[int] = None,
    restart: bool = False,
    quota=None,
) -> int:
    """관광사진 갤러리를 수집해 place_gallery_image에 upsert 한다."""
    client = make_client(settings, settings.photo_gallery_base_url, quota)
    api = GalleryImageApi(client)

    start_page = 1 if restart else repository.get_last_page(conn, SOURCE_GALLERY) + 1
    pages = max_pages if max_pages is not None else settings.max_pages
    log.info(
        "[ingest-gallery] %s페이지부터 최대 %s페이지 수집", start_page, pages
    )

    try:
        result = api.fetch_gallery_images(
            num_of_rows=settings.num_of_rows,
            start_page=start_page,
            max_pages=pages,
        )
    finally:
        client.close()

    if not result.items:
        log.info("[ingest-gallery] 새로 가져온 항목이 없습니다. (커서 유지)")
        return 0

    saved = repository.save_gallery_items(conn, result.items, settings.chunk_size)
    repository.save_cursor(
        conn, SOURCE_GALLERY, result.last_page_fetched, result.total_count
    )
    log.info(
        "[ingest-gallery] %s건 upsert 완료 (page %s까지, 전체 %s건, %s)",
        saved,
        result.last_page_fetched,
        result.total_count,
        "수집 완료" if result.exhausted else "남은 페이지 있음",
    )
    return saved
