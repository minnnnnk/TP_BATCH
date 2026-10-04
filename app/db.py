"""DB 연결 및 스키마 관리.

기존 Kotlin 배치(TP_BATCH)가 Exposed로 만든 테이블과 **완전히 동일한 스키마**를
사용한다. 두 배치를 번갈아 돌려도 같은 데이터가 쌓이도록 하기 위함이다.
"""
import logging
from contextlib import contextmanager
from typing import Iterator

import psycopg2
from psycopg2.extensions import connection as PgConnection

from app.config import Settings

log = logging.getLogger(__name__)


@contextmanager
def connect(settings: Settings) -> Iterator[PgConnection]:
    conn = psycopg2.connect(settings.dsn)
    try:
        yield conn
    finally:
        conn.close()


# Kotlin: db/PlaceTable.kt (PlaceTable)
# overview는 Kotlin 배치에 없는 컬럼이다. areaBasedList2 응답에는 상세 설명이
# 없어서, detailCommon2로 따로 채워 넣기 위해 추가했다(enrich 잡).
# nullable이라 기존 배치의 createMissingTablesAndColumns와도 충돌하지 않는다.
DDL_PLACE = """
CREATE TABLE IF NOT EXISTS place (
    id                   BIGSERIAL PRIMARY KEY,
    content_id           VARCHAR(20)  NOT NULL,
    content_type_id      VARCHAR(10),
    title                VARCHAR(500),
    addr1                VARCHAR(500),
    addr2                VARCHAR(500),
    area_code            VARCHAR(10),
    sigungu_code         VARCHAR(10),
    cat1                 VARCHAR(20),
    cat2                 VARCHAR(20),
    cat3                 VARCHAR(20),
    first_image          VARCHAR(1000),
    first_image2         VARCHAR(1000),
    map_x                DOUBLE PRECISION,
    map_y                DOUBLE PRECISION,
    m_level              VARCHAR(10),
    tel                  TEXT,
    zipcode              VARCHAR(10),
    source_created_time  VARCHAR(20),
    source_modified_time VARCHAR(20)
);
CREATE UNIQUE INDEX IF NOT EXISTS place_content_id_unique ON place (content_id);
ALTER TABLE place ADD COLUMN IF NOT EXISTS overview TEXT;
"""

# Kotlin: db/PlaceTable.kt (PlaceGalleryImageTable)
DDL_PLACE_GALLERY_IMAGE = """
CREATE TABLE IF NOT EXISTS place_gallery_image (
    id                       BIGSERIAL PRIMARY KEY,
    gal_content_id           VARCHAR(20)  NOT NULL,
    gal_content_type_id      VARCHAR(10),
    gal_title                VARCHAR(500),
    gal_web_image_url        VARCHAR(1000),
    gal_photographer         VARCHAR(200),
    gal_photography_month    VARCHAR(20),
    gal_photography_location VARCHAR(500),
    gal_search_keyword       VARCHAR(1000),
    source_created_time      VARCHAR(20),
    source_modified_time     VARCHAR(20)
);
CREATE UNIQUE INDEX IF NOT EXISTS place_gallery_image_gal_content_id_unique
    ON place_gallery_image (gal_content_id);
"""

# Kotlin: db/FetchCursorTable.kt
DDL_FETCH_CURSOR = """
CREATE TABLE IF NOT EXISTS fetch_cursor (
    source      VARCHAR(50) PRIMARY KEY,
    last_page   INTEGER NOT NULL DEFAULT 0,
    total_count INTEGER NOT NULL DEFAULT 0
);
"""

# TP_TRAVEL_AI의 travel_spots 테이블(app/models/travel.py)에 맞춘 DDL.
# AI 서버가 먼저 떠서 만들어 놨다면 CREATE는 건너뛰고 ALTER만 적용된다.
#
# source_content_id: place.content_id를 그대로 보관해 재실행 시 중복 없이
#   upsert하기 위한 컬럼. nullable이라 AI 쪽 ORM 코드는 수정 없이도 동작한다.
DDL_TRAVEL_SPOTS = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS travel_spots (
    id          UUID PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    region      VARCHAR(100) NOT NULL,
    address     VARCHAR(500),
    category    VARCHAR(100) NOT NULL,
    latitude    DOUBLE PRECISION NOT NULL,
    longitude   DOUBLE PRECISION NOT NULL,
    description TEXT NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding   VECTOR(%(dim)s) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE travel_spots ADD COLUMN IF NOT EXISTS source_content_id VARCHAR(20);
CREATE UNIQUE INDEX IF NOT EXISTS travel_spots_source_content_id_unique
    ON travel_spots (source_content_id);

CREATE INDEX IF NOT EXISTS ix_travel_spots_name   ON travel_spots (name);
CREATE INDEX IF NOT EXISTS ix_travel_spots_region ON travel_spots (region);
CREATE INDEX IF NOT EXISTS ix_travel_spots_category ON travel_spots (category);
CREATE INDEX IF NOT EXISTS idx_travel_spots_name_trgm
    ON travel_spots USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_travel_spots_desc_trgm
    ON travel_spots USING gin (description gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_travel_spots_embedding_hnsw
    ON travel_spots USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
"""


def init_ingest_schema(conn: PgConnection) -> None:
    """수집 단계(place / gallery / cursor) 스키마 생성."""
    with conn.cursor() as cur:
        cur.execute(DDL_PLACE)
        cur.execute(DDL_PLACE_GALLERY_IMAGE)
        cur.execute(DDL_FETCH_CURSOR)
    conn.commit()
    log.info("수집 스키마 준비 완료 (place / place_gallery_image / fetch_cursor)")


def init_vector_schema(conn: PgConnection, dimension: int) -> None:
    """동기화 대상(travel_spots) 스키마 생성 및 확장 컬럼 추가."""
    with conn.cursor() as cur:
        cur.execute(DDL_TRAVEL_SPOTS % {"dim": int(dimension)})
    conn.commit()
    log.info("벡터 스키마 준비 완료 (travel_spots, dim=%s)", dimension)
