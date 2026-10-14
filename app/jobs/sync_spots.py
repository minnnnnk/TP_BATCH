"""동기화 잡 (place -> travel_spots).

TP_BATCH2가 적재한 TourAPI 원본(place)을 TP_TRAVEL_AI가 추천에 쓰는
travel_spots 형태로 변환하고, ko-sroberta로 임베딩해 upsert 한다.

증분 기준은 source_content_id + source_modified_time + detail_version이다.
  - travel_spots에 아직 없는 장소
  - TourAPI 수정일시가 바뀐 장소 (metadata->>'source_modified_time' 비교)
  - place_detail(B-10)이 새로 채워지거나 바뀐 장소 (metadata->>'detail_version' 비교)
따라서 여러 번 돌려도 이미 임베딩한 장소를 다시 계산하지 않는다.
"""
import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor, execute_values

from app import repository
from app.config import Settings
from app.embedding import EmbeddingService, to_pgvector_literal
from app.mapping import map_place_row

log = logging.getLogger(__name__)

PLACE_SELECT_COLUMNS = """
    p.content_id, p.content_type_id, p.title, p.addr1, p.addr2,
    p.area_code, p.sigungu_code, p.cat1, p.cat2, p.cat3,
    p.first_image, p.first_image2, p.map_x, p.map_y,
    p.tel, p.zipcode, p.source_modified_time
"""

# place_detail(B-10) 값. 아직 안 채운 장소는 전부 NULL이다.
DETAIL_VERSION_SQL = "(extract(epoch FROM d.updated_at)::bigint)::text"
DETAIL_SELECT_COLUMNS = """
    d.overview, d.indoor_type, d.open_min, d.close_min, d.always_open,
    d.closed_weekdays, d.closed_on_holidays, d.closed_irregular, d.no_closure,
    d.use_time_text, d.rest_date_text, d.event_start_date, d.event_end_date,
    d.lcls_systm1, d.lcls_systm2,
    {version} AS detail_version
""".format(version=DETAIL_VERSION_SQL)
_DETAIL_NAMES = (
    "overview", "indoor_type", "open_min", "close_min", "always_open",
    "closed_weekdays", "closed_on_holidays", "closed_irregular", "no_closure",
    "use_time_text", "rest_date_text", "event_start_date", "event_end_date",
    "lcls_systm1", "lcls_systm2", "detail_version",
)
# dry-run에서 place_detail이 아직 없을 때 쓰는 자리 채움
DETAIL_NULL_COLUMNS = ", ".join("NULL AS {0}".format(n) for n in _DETAIL_NAMES)

SELECT_COLUMNS = PLACE_SELECT_COLUMNS + "," + DETAIL_SELECT_COLUMNS
DETAIL_JOIN = "LEFT JOIN place_detail d ON d.content_id = p.content_id"

# 아직 동기화되지 않았거나, TourAPI 수정일시나 상세정보가 달라진 장소만 고른다.
PENDING_WHERE = """
    p.title IS NOT NULL AND p.map_x IS NOT NULL AND p.map_y IS NOT NULL
    AND (
        t.source_content_id IS NULL
        OR COALESCE(t.metadata->>'source_modified_time', '')
           IS DISTINCT FROM COALESCE(p.source_modified_time, '')
        OR COALESCE(t.metadata->>'detail_version', '')
           IS DISTINCT FROM COALESCE({version}, '')
    )
""".format(version=DETAIL_VERSION_SQL)

SELECT_PENDING = """
SELECT {cols}
FROM place p
{join}
LEFT JOIN travel_spots t ON t.source_content_id = p.content_id
WHERE {where}
ORDER BY p.id
LIMIT %s
""".format(cols=SELECT_COLUMNS, join=DETAIL_JOIN, where=PENDING_WHERE)

# dry-run 전용: travel_spots가 아직 없어도 매핑을 확인할 수 있게 place만 읽는다.
SELECT_PLACE_SAMPLE = """
SELECT {cols}
FROM place p
{join}
WHERE p.title IS NOT NULL AND p.map_x IS NOT NULL AND p.map_y IS NOT NULL
ORDER BY p.id
LIMIT %s
"""

COUNT_PENDING = """
SELECT count(*)
FROM place p
{join}
LEFT JOIN travel_spots t ON t.source_content_id = p.content_id
WHERE {where}
""".format(join=DETAIL_JOIN, where=PENDING_WHERE)

UPSERT_SPOTS = """
INSERT INTO travel_spots
    (id, source_content_id, name, region, address, category,
     latitude, longitude, description, metadata, embedding, created_at, updated_at)
VALUES %s
ON CONFLICT (source_content_id) DO UPDATE SET
    name        = EXCLUDED.name,
    region      = EXCLUDED.region,
    address     = EXCLUDED.address,
    category    = EXCLUDED.category,
    latitude    = EXCLUDED.latitude,
    longitude   = EXCLUDED.longitude,
    description = EXCLUDED.description,
    metadata    = EXCLUDED.metadata,
    embedding   = EXCLUDED.embedding,
    updated_at  = now()
"""

VALUES_TEMPLATE = (
    "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector, now(), now())"
)


def count_pending(conn: PgConnection) -> int:
    with conn.cursor() as cur:
        cur.execute(COUNT_PENDING)
        return int(cur.fetchone()[0])


def _fetch_pending(conn: PgConnection, limit: int) -> List[Dict[str, Any]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(SELECT_PENDING, (limit,))
        return [dict(r) for r in cur.fetchall()]


def sync_spots(
    conn: PgConnection,
    settings: Settings,
    limit: Optional[int] = None,
    batch_size: Optional[int] = None,
    dry_run: bool = False,
) -> int:
    """place를 travel_spots로 동기화한다.

    :param limit: 이번 실행에서 처리할 최대 장소 수(None이면 남은 전부)
    :param batch_size: 한 번에 임베딩·적재할 묶음 크기
    :param dry_run: 임베딩/적재 없이 매핑 결과만 확인
    """
    if dry_run:
        return _dry_run(conn, min(limit or settings.chunk_size, settings.chunk_size))

    total_pending = count_pending(conn)
    if total_pending == 0:
        log.info("[sync] 동기화할 장소가 없습니다.")
        return 0

    target = total_pending if limit is None else min(limit, total_pending)
    chunk = batch_size or settings.chunk_size
    log.info("[sync] 대상 %s건 (전체 미동기화 %s건), batch=%s", target, total_pending, chunk)

    embedder = EmbeddingService(
        settings.embedding_model_name,
        settings.embedding_dimension,
        settings.embedding_device,
    )

    processed = 0
    skipped = 0
    while processed < target:
        take = min(chunk, target - processed)
        rows = _fetch_pending(conn, take)
        if not rows:
            break

        mapped: List[Tuple[Dict[str, Any], str]] = []
        for row in rows:
            result = map_place_row(row)
            if result is None:
                skipped += 1
                continue
            mapped.append(result)

        if not mapped:
            # 이번 묶음이 전부 좌표/이름 결측이면 더 진행해도 같은 행을 다시 읽게 되므로 중단한다.
            log.warning("[sync] 유효한 장소가 없어 중단합니다 (결측 %s건).", skipped)
            break

        texts = [text for _, text in mapped]
        vectors = embedder.embed_texts(texts, settings.embedding_batch_size)

        values = []
        for (spot, _), vector in zip(mapped, vectors):
            values.append(
                (
                    str(uuid.uuid4()),
                    spot["source_content_id"],
                    spot["name"],
                    spot["region"],
                    spot["address"],
                    spot["category"],
                    spot["latitude"],
                    spot["longitude"],
                    spot["description"],
                    json.dumps(spot["metadata"], ensure_ascii=False),
                    to_pgvector_literal(vector),
                )
            )

        with conn.cursor() as cur:
            execute_values(cur, UPSERT_SPOTS, values, template=VALUES_TEMPLATE)
        conn.commit()

        processed += len(rows)
        log.info("[sync] %s/%s 진행 (이번 묶음 %s건 적재)", processed, target, len(values))

    log.info("[sync] 완료 — 처리 %s건, 좌표/이름 결측으로 제외 %s건", processed, skipped)
    return processed


def _dry_run(conn: PgConnection, sample_size: int) -> int:
    """임베딩 없이 매핑 결과만 출력한다. DB는 읽기만 한다."""
    if repository.table_exists(conn, "place_detail"):
        sql = SELECT_PLACE_SAMPLE.format(cols=SELECT_COLUMNS, join=DETAIL_JOIN)
    else:
        log.info("[sync --dry-run] place_detail이 아직 없어 상세정보 없이 매핑합니다.")
        sql = SELECT_PLACE_SAMPLE.format(
            cols=PLACE_SELECT_COLUMNS + ", " + DETAIL_NULL_COLUMNS, join=""
        )
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, (sample_size,))
        rows = [dict(r) for r in cur.fetchall()]
    shown = 0
    for row in rows:
        result = map_place_row(row)
        if result is None:
            log.info("  [skip] content_id=%s (좌표/이름/지역 결측)", row.get("content_id"))
            continue
        spot, text = result
        meta = spot["metadata"]
        log.info(
            "  [ok] %s | %s | %s (%.5f, %.5f) 실내외=%s 운영=%s 휴무=%s",
            spot["name"],
            spot["region"],
            spot["category"],
            spot["latitude"],
            spot["longitude"],
            meta.get("indoor_type"),
            meta.get("opening_hours"),
            meta.get("closed_weekdays"),
        )
        log.info("       임베딩 원문: %s", text[:160] + ("..." if len(text) > 160 else ""))
        shown += 1
    log.info("[sync --dry-run] 매핑 성공 %s / 조회 %s건 (DB 변경 없음)", shown, len(rows))
    return shown
