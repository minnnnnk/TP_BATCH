"""TourAPI 수집 잡 (TourAPI -> place / place_gallery_image).

개발계정 일일 호출 한도 때문에 한 번에 전량을 못 가져오므로,
fetch_cursor에 마지막 페이지를 기록해두고 다음 실행에서 이어받는다.
(Kotlin 배치의 FetchCursorTable과 같은 테이블/같은 의미)
"""
import logging
from typing import Optional

from psycopg2.extensions import connection as PgConnection

from app import repository
from app.config import Settings
from app.tourapi.client import TourApiClient
from app.tourapi.gallery import GalleryImageApi
from app.tourapi.kor_service import KorServiceApi

log = logging.getLogger(__name__)

SOURCE_AREA = "areaBasedList2"
SOURCE_GALLERY = "galleryList1"


def ingest_area(
    conn: PgConnection,
    settings: Settings,
    area_code: Optional[str] = None,
    content_type_id: Optional[str] = None,
    max_pages: Optional[int] = None,
    restart: bool = False,
) -> int:
    """지역기반 관광정보를 수집해 place에 upsert 한다."""
    client = TourApiClient(
        settings.kor_service_base_url,
        settings.tour_api_service_key,
        settings.mobile_app,
        settings.request_timeout_sec,
    )
    api = KorServiceApi(client)

    # 조건별로 페이지 번호 체계가 달라지므로 커서 키도 조건별로 나눈다.
    source_key = SOURCE_AREA
    if area_code:
        source_key += ":area={0}".format(area_code)
    if content_type_id:
        source_key += ":type={0}".format(content_type_id)

    start_page = 1 if restart else repository.get_last_page(conn, source_key) + 1
    pages = max_pages if max_pages is not None else settings.max_pages
    log.info(
        "[ingest-area] source=%s, %s페이지부터 최대 %s페이지 수집",
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
        log.info("[ingest-area] 새로 가져온 항목이 없습니다. (커서 유지)")
        return 0

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


def ingest_gallery(
    conn: PgConnection,
    settings: Settings,
    max_pages: Optional[int] = None,
    restart: bool = False,
) -> int:
    """관광사진 갤러리를 수집해 place_gallery_image에 upsert 한다."""
    client = TourApiClient(
        settings.photo_gallery_base_url,
        settings.tour_api_service_key,
        settings.mobile_app,
        settings.request_timeout_sec,
    )
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


def enrich_overview(
    conn: PgConnection, settings: Settings, limit: int = 200
) -> int:
    """overview가 비어 있는 place를 detailCommon2로 채운다.

    장소 1건당 API 1회라 호출 비용이 크다. 기본값을 작게 두고 --limit으로 조절한다.
    설명문이 임베딩 품질을 좌우하므로, 추천 정확도를 올리려면 이 잡을 여러 번 나눠 돌린다.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT content_id FROM place "
            "WHERE overview IS NULL OR overview = '' "
            "ORDER BY id LIMIT %s",
            (limit,),
        )
        content_ids = [r[0] for r in cur.fetchall()]

    if not content_ids:
        log.info("[enrich] overview가 비어 있는 장소가 없습니다.")
        return 0

    client = TourApiClient(
        settings.kor_service_base_url,
        settings.tour_api_service_key,
        settings.mobile_app,
        settings.request_timeout_sec,
    )
    api = KorServiceApi(client)

    pairs = []
    try:
        for idx, content_id in enumerate(content_ids, start=1):
            try:
                detail = api.fetch_detail_common(content_id)
            except Exception as exc:  # 한 건 실패로 전체를 멈추지 않는다
                log.warning("[enrich] contentId=%s 조회 실패: %s", content_id, exc)
                continue
            overview = (detail or {}).get("overview")
            if overview:
                pairs.append((content_id, str(overview).strip()))
            if idx % 50 == 0:
                log.info("[enrich] %s/%s 조회", idx, len(content_ids))
    finally:
        client.close()

    updated = repository.save_overviews(conn, pairs, settings.chunk_size)
    log.info("[enrich] %s건 overview 갱신 (조회 %s건)", updated, len(content_ids))
    return updated
