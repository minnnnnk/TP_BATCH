"""DB 연결 및 스키마 관리.

place / place_gallery_image / fetch_cursor는 기존 Kotlin 배치(TP_BATCH)가 Exposed로 만든
테이블과 **완전히 동일한 스키마**를 사용한다. 두 배치를 번갈아 돌려도 같은 데이터가
쌓이도록 하기 위함이다. 그래서 이 배치가 새로 채우는 값은 place에 컬럼을 덧붙이지 않고
별도 테이블(place_detail, place_embedding)에 둔다. 설계 설명은 docs/SCHEMA.md 참고.
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

# B-10 장소 메타데이터. place와 1:1 (content_id).
# detailIntro2(운영시간·휴무일 등)와 detailCommon2(개요·신분류코드)의 원본과, 그것을
# 정제한 값을 함께 둔다. 원본(*_text, intro_raw)을 남기는 이유:
#   - 파서를 고치면 API를 다시 부르지 않고 재계산할 수 있다 (enrich --reparse)
#   - 정제하지 못한 문장('매월 첫째 수요일', '점포별 상이')을 LLM 단계(C-13)가 읽을 수 있다
# 시각은 자정 기준 '분'이다(09:00 -> 540). 자정을 넘기면 1440 이상(익일 02:00 -> 1560).
DDL_PLACE_DETAIL = """
CREATE TABLE IF NOT EXISTS place_detail (
    content_id           VARCHAR(20) PRIMARY KEY
                         REFERENCES place (content_id) ON DELETE CASCADE,
    content_type_id      VARCHAR(10),

    overview             TEXT,
    homepage             TEXT,
    lcls_systm1          VARCHAR(10),
    lcls_systm2          VARCHAR(10),
    lcls_systm3          VARCHAR(10),
    ldong_regn_cd        VARCHAR(10),
    ldong_signgu_cd      VARCHAR(10),

    use_time_text        TEXT,
    rest_date_text       TEXT,
    parking_text         TEXT,
    use_fee_text         TEXT,
    intro_raw            JSONB   NOT NULL DEFAULT '{}'::jsonb,

    open_min             SMALLINT,
    close_min            SMALLINT,
    always_open          BOOLEAN NOT NULL DEFAULT FALSE,
    hours_detail         JSONB   NOT NULL DEFAULT '{}'::jsonb,
    closed_weekdays      TEXT[]  NOT NULL DEFAULT '{}',
    closed_on_holidays   BOOLEAN NOT NULL DEFAULT FALSE,
    closed_irregular     BOOLEAN NOT NULL DEFAULT FALSE,
    no_closure           BOOLEAN NOT NULL DEFAULT FALSE,
    event_start_date     DATE,
    event_end_date       DATE,
    indoor_type          VARCHAR(10),
    indoor_source        VARCHAR(20),

    parse_status         VARCHAR(10) NOT NULL,
    source_modified_time VARCHAR(20),
    intro_fetched_at     TIMESTAMPTZ,
    common_fetched_at    TIMESTAMPTZ,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_place_detail_indoor_type ON place_detail (indoor_type);
CREATE INDEX IF NOT EXISTS ix_place_detail_parse_status ON place_detail (parse_status);
CREATE INDEX IF NOT EXISTS ix_place_detail_closed_weekdays
    ON place_detail USING gin (closed_weekdays);
"""

# 배치 운영용: 서비스별 일일 호출 수(app.quota)와 잡 실행 이력(daily / schedule).
DDL_BATCH_OPS = """
CREATE TABLE IF NOT EXISTS api_call_quota (
    usage_date  DATE        NOT NULL,
    service     VARCHAR(50) NOT NULL,
    calls       INTEGER     NOT NULL DEFAULT 0,
    PRIMARY KEY (usage_date, service)
);

CREATE TABLE IF NOT EXISTS batch_job_run (
    id          BIGSERIAL PRIMARY KEY,
    job         VARCHAR(50) NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status      VARCHAR(10) NOT NULL DEFAULT 'running',
    stats       JSONB       NOT NULL DEFAULT '{}'::jsonb,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS ix_batch_job_run_job_started ON batch_job_run (job, started_at DESC);
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

# 장소 임베딩(B-11이 채운다). place와 1:N — 모델을 바꿔 비교할 수 있게 모델명을 키에 넣었다.
# 단, embedding 컬럼 차원은 하나라서 차원이 다른 모델은 같은 테이블에 넣을 수 없다.
# text_hash(임베딩 원문의 SHA-256)가 같으면 다시 계산하지 않는다.
DDL_PLACE_EMBEDDING = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS place_embedding (
    content_id  VARCHAR(20)  NOT NULL REFERENCES place (content_id) ON DELETE CASCADE,
    model_name  VARCHAR(100) NOT NULL,
    embedding   VECTOR(%(dim)s) NOT NULL,
    source_text TEXT         NOT NULL,
    text_hash   CHAR(64)     NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (content_id, model_name)
);
CREATE INDEX IF NOT EXISTS idx_place_embedding_hnsw
    ON place_embedding USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
"""


def init_ingest_schema(conn: PgConnection) -> None:
    """수집·정제 단계 스키마 생성 (place / gallery / cursor / place_detail / 운영 테이블)."""
    with conn.cursor() as cur:
        cur.execute(DDL_PLACE)
        cur.execute(DDL_PLACE_GALLERY_IMAGE)
        cur.execute(DDL_FETCH_CURSOR)
        cur.execute(DDL_PLACE_DETAIL)
        cur.execute(DDL_BATCH_OPS)
    conn.commit()
    log.debug("수집 스키마 준비 완료 (place / place_gallery_image / fetch_cursor / place_detail)")


def init_vector_schema(conn: PgConnection, dimension: int) -> None:
    """벡터 스키마 생성 (travel_spots + 확장 컬럼, place_embedding)."""
    with conn.cursor() as cur:
        cur.execute(DDL_TRAVEL_SPOTS % {"dim": int(dimension)})
        cur.execute(DDL_PLACE_EMBEDDING % {"dim": int(dimension)})
    conn.commit()
    log.info("벡터 스키마 준비 완료 (travel_spots, place_embedding, dim=%s)", dimension)


# 같은 잡이 겹쳐 돌면(스케줄러 + 수동 실행) 호출 한도를 두 배로 쓰게 되므로 막는다.
# 세션 단위 잠금이라 커넥션이 닫히면 자동으로 풀린다.
def try_job_lock(conn: PgConnection, name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (name,))
        locked = bool(cur.fetchone()[0])
    conn.commit()
    return locked
