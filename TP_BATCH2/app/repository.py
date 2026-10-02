"""place / place_gallery_image / fetch_cursor 적재 계층.

Kotlin TourRepository.kt와 동일하게 content_id(= gal_content_id) 기준 upsert라,
같은 페이지를 다시 읽어도 중복 행이 생기지 않는다.
"""
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import execute_values

from app.tourapi.client import float_or_none, text_or_none

log = logging.getLogger(__name__)

PLACE_COLUMNS: Tuple[str, ...] = (
    "content_id",
    "content_type_id",
    "title",
    "addr1",
    "addr2",
    "area_code",
    "sigungu_code",
    "cat1",
    "cat2",
    "cat3",
    "first_image",
    "first_image2",
    "map_x",
    "map_y",
    "m_level",
    "tel",
    "zipcode",
    "source_created_time",
    "source_modified_time",
)

GALLERY_COLUMNS: Tuple[str, ...] = (
    "gal_content_id",
    "gal_content_type_id",
    "gal_title",
    "gal_web_image_url",
    "gal_photographer",
    "gal_photography_month",
    "gal_photography_location",
    "gal_search_keyword",
    "source_created_time",
    "source_modified_time",
)


def to_place_row(item: Dict[str, Any]) -> Optional[Tuple[Any, ...]]:
    """areaBasedList2 아이템을 place 컬럼 순서의 튜플로 변환한다.

    content_id가 없으면 저장할 수 없으므로 건너뛴다(Kotlin PlaceItemProcessor와 동일).
    """
    content_id = text_or_none(item.get("contentid"))
    if content_id is None:
        return None

    return (
        content_id,
        text_or_none(item.get("contenttypeid")),
        text_or_none(item.get("title")),
        text_or_none(item.get("addr1")),
        text_or_none(item.get("addr2")),
        text_or_none(item.get("areacode")),
        text_or_none(item.get("sigungucode")),
        text_or_none(item.get("cat1")),
        text_or_none(item.get("cat2")),
        text_or_none(item.get("cat3")),
        text_or_none(item.get("firstimage")),
        text_or_none(item.get("firstimage2")),
        float_or_none(item.get("mapx")),
        float_or_none(item.get("mapy")),
        text_or_none(item.get("mlevel")),
        text_or_none(item.get("tel")),
        text_or_none(item.get("zipcode")),
        text_or_none(item.get("createdtime")),
        text_or_none(item.get("modifiedtime")),
    )


def to_gallery_row(item: Dict[str, Any]) -> Optional[Tuple[Any, ...]]:
    gal_content_id = text_or_none(item.get("galContentId"))
    if gal_content_id is None:
        return None

    return (
        gal_content_id,
        text_or_none(item.get("galContentTypeId")),
        text_or_none(item.get("galTitle")),
        text_or_none(item.get("galWebImageUrl")),
        text_or_none(item.get("galPhotographer")),
        text_or_none(item.get("galPhotographyMonth")),
        text_or_none(item.get("galPhotographyLocation")),
        text_or_none(item.get("galSearchKeyword")),
        text_or_none(item.get("galCreatedtime")),
        text_or_none(item.get("galModifiedtime")),
    )


def _upsert(
    conn: PgConnection,
    table: str,
    columns: Sequence[str],
    conflict_column: str,
    rows: Sequence[Tuple[Any, ...]],
    page_size: int,
) -> int:
    if not rows:
        return 0

    updatable = [c for c in columns if c != conflict_column]
    sql = (
        "INSERT INTO {table} ({cols}) VALUES %s "
        "ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
    ).format(
        table=table,
        cols=", ".join(columns),
        conflict=conflict_column,
        updates=", ".join("{0} = EXCLUDED.{0}".format(c) for c in updatable),
    )

    with conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=page_size)
    conn.commit()
    return len(rows)


def save_place_items(
    conn: PgConnection, items: Sequence[Dict[str, Any]], chunk_size: int = 500
) -> int:
    rows = [r for r in (to_place_row(i) for i in items) if r is not None]
    saved = _upsert(conn, "place", PLACE_COLUMNS, "content_id", rows, chunk_size)
    skipped = len(items) - len(rows)
    if skipped:
        log.warning("content_id가 없어 건너뛴 항목: %s건", skipped)
    return saved


def save_gallery_items(
    conn: PgConnection, items: Sequence[Dict[str, Any]], chunk_size: int = 500
) -> int:
    rows = [r for r in (to_gallery_row(i) for i in items) if r is not None]
    return _upsert(
        conn, "place_gallery_image", GALLERY_COLUMNS, "gal_content_id", rows, chunk_size
    )


def save_overviews(
    conn: PgConnection, pairs: Sequence[Tuple[str, str]], chunk_size: int = 500
) -> int:
    """(content_id, overview) 목록을 place에 반영한다."""
    if not pairs:
        return 0
    sql = (
        "UPDATE place AS p SET overview = v.overview "
        "FROM (VALUES %s) AS v(content_id, overview) "
        "WHERE p.content_id = v.content_id"
    )
    with conn.cursor() as cur:
        execute_values(cur, sql, pairs, page_size=chunk_size)
    conn.commit()
    return len(pairs)


def get_last_page(conn: PgConnection, source: str) -> int:
    """마지막으로 완료된 페이지 번호. 기록이 없으면 0(= 처음부터)."""
    with conn.cursor() as cur:
        cur.execute("SELECT last_page FROM fetch_cursor WHERE source = %s", (source,))
        row = cur.fetchone()
    return int(row[0]) if row else 0


def save_cursor(
    conn: PgConnection, source: str, last_page: int, total_count: int
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO fetch_cursor (source, last_page, total_count) "
            "VALUES (%s, %s, %s) "
            "ON CONFLICT (source) DO UPDATE "
            "SET last_page = EXCLUDED.last_page, total_count = EXCLUDED.total_count",
            (source, last_page, total_count),
        )
    conn.commit()


def count_rows(conn: PgConnection, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM {0}".format(table))
        return int(cur.fetchone()[0])


def table_exists(conn: PgConnection, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL", (table,))
        return bool(cur.fetchone()[0])


def list_cursors(conn: PgConnection) -> List[Tuple[str, int, int]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT source, last_page, total_count FROM fetch_cursor ORDER BY source"
        )
        return [(r[0], int(r[1]), int(r[2])) for r in cur.fetchall()]
