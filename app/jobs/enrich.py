"""상세정보 보강 잡 (B-10): place -> detailIntro2 / detailCommon2 -> place_detail.

장소 1건당 API를 1~2회 부른다(소개정보 + 공통정보). 개발계정 한도로는 하루 수백 건이
한계라서, 일정 짜기에 직접 쓰이는 타입·지역부터 채우고 한도에 닿으면 멈춘다.
다음 실행은 아직 안 채운 장소부터 이어서 한다.

다시 조회하는 경우:
  - place_detail에 아직 없는 장소
  - place.source_modified_time이 바뀐 장소 (refresh가 수정분을 받아온 경우)
  - 개요 없이 받았던 장소를 개요 포함으로 다시 받을 때 (detailCommon2만 추가 조회)
"""
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor

from app import repository
from app.config import Settings
from app.detail_parser import build_detail_row
from app.jobs.ingest import make_client
from app.quota import QuotaExhausted
from app.tourapi.kor_service import KorServiceApi

log = logging.getLogger(__name__)

FLUSH_EVERY = 50  # 한도 소진/중단 시 잃는 양을 줄이려고 자주 저장한다
MAX_CONSECUTIVE_ERRORS = 10  # 연속 실패면 API 장애로 보고 멈춘다

_STORED_COMMON_COLUMNS = (
    "overview",
    "homepage",
    "lcls_systm1",
    "lcls_systm2",
    "lcls_systm3",
    "ldong_regn_cd",
    "ldong_signgu_cd",
)

_STALE = "d.source_modified_time IS DISTINCT FROM p.source_modified_time"

SELECT_TARGETS = """
SELECT p.content_id, p.content_type_id, p.title, p.cat1, p.cat2, p.cat3,
       p.area_code, p.source_modified_time,
       d.intro_raw, d.intro_fetched_at, d.common_fetched_at,
       d.overview, d.homepage, d.lcls_systm1, d.lcls_systm2, d.lcls_systm3,
       d.ldong_regn_cd, d.ldong_signgu_cd,
       (d.content_id IS NULL OR d.intro_fetched_at IS NULL OR {stale}) AS need_intro,
       (%(with_overview)s AND (d.content_id IS NULL OR d.common_fetched_at IS NULL OR {stale}))
           AS need_common
FROM place p
LEFT JOIN place_detail d ON d.content_id = p.content_id
WHERE p.content_type_id IS NOT NULL AND p.content_type_id <> ''
  AND (d.content_id IS NULL OR d.intro_fetched_at IS NULL OR {stale}
       OR (%(with_overview)s AND d.common_fetched_at IS NULL))
  AND (%(area)s::text IS NULL OR p.area_code = %(area)s::text)
  AND (%(ctype)s::text IS NULL OR p.content_type_id = %(ctype)s::text)
ORDER BY (d.content_id IS NOT NULL),
         array_position(%(types)s::text[], p.content_type_id::text) NULLS LAST,
         array_position(%(areas)s::text[], p.area_code::text) NULLS LAST,
         p.source_modified_time DESC NULLS LAST
LIMIT %(limit)s
""".format(stale=_STALE)

COUNT_TARGETS = """
SELECT count(*)
FROM place p
LEFT JOIN place_detail d ON d.content_id = p.content_id
WHERE p.content_type_id IS NOT NULL AND p.content_type_id <> ''
  AND (d.content_id IS NULL OR d.intro_fetched_at IS NULL OR {stale})
""".format(stale=_STALE)

SELECT_FOR_REPARSE = """
SELECT p.content_id, p.content_type_id, p.title, p.cat1, p.cat2, p.cat3,
       d.source_modified_time, d.intro_raw, d.intro_fetched_at, d.common_fetched_at,
       d.overview, d.homepage, d.lcls_systm1, d.lcls_systm2, d.lcls_systm3,
       d.ldong_regn_cd, d.ldong_signgu_cd
FROM place_detail d
JOIN place p ON p.content_id = d.content_id
WHERE d.content_id > %s
ORDER BY d.content_id
LIMIT %s
"""


def calls_per_place(with_overview: bool) -> int:
    return 2 if with_overview else 1


def count_pending_details(conn: PgConnection) -> int:
    with conn.cursor() as cur:
        cur.execute(COUNT_TARGETS)
        return int(cur.fetchone()[0])


def _stored_common(target: Dict[str, Any]) -> Dict[str, Any]:
    return {c: target.get(c) for c in _STORED_COMMON_COLUMNS}


def _select_targets(
    conn: PgConnection,
    settings: Settings,
    limit: int,
    with_overview: bool,
    area_code: Optional[str],
    content_type_id: Optional[str],
) -> List[Dict[str, Any]]:
    params = {
        "with_overview": with_overview,
        "area": area_code,
        "ctype": content_type_id,
        "types": list(settings.detail_priority_types),
        "areas": list(settings.detail_priority_areas),
        "limit": limit,
    }
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(SELECT_TARGETS, params)
        rows = [dict(r) for r in cur.fetchall()]
    conn.commit()
    return rows


def _fetch_one(api: KorServiceApi, target: Dict[str, Any], stats: Counter) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    intro_fetched_at = target.get("intro_fetched_at")
    common_fetched_at = target.get("common_fetched_at")

    if target["need_intro"]:
        intro = api.fetch_detail_intro(target["content_id"], target["content_type_id"])
        stats["api_calls"] += 1
        intro_fetched_at = now
    else:
        intro = target.get("intro_raw") or None

    if target["need_common"]:
        common = api.fetch_detail_common(target["content_id"]) or {}
        stats["api_calls"] += 1
        common_fetched_at = now
    else:
        common = _stored_common(target)

    row = build_detail_row(target, intro, common)
    row["intro_fetched_at"] = intro_fetched_at
    row["common_fetched_at"] = common_fetched_at
    return row


def enrich_details(
    conn: PgConnection,
    settings: Settings,
    limit: int,
    quota=None,
    with_overview: Optional[bool] = None,
    area_code: Optional[str] = None,
    content_type_id: Optional[str] = None,
) -> Dict[str, Any]:
    """상세정보를 조회해 place_detail을 채운다. 한도에 닿으면 저장하고 멈춘다."""
    if with_overview is None:
        with_overview = settings.detail_with_overview

    targets = _select_targets(conn, settings, limit, with_overview, area_code, content_type_id)
    stats: Counter = Counter()
    result: Dict[str, Any] = {"targets": len(targets), "with_overview": with_overview}
    if not targets:
        log.info("[enrich] 새로 채울 장소가 없습니다.")
        return result

    log.info(
        "[enrich] %s건 조회 시작 (장소당 호출 %s회, 우선 타입=%s, 우선 지역=%s)",
        len(targets),
        calls_per_place(with_overview),
        ",".join(settings.detail_priority_types) or "-",
        ",".join(settings.detail_priority_areas) or "-",
    )

    client = make_client(settings, settings.kor_service_base_url, quota)
    api = KorServiceApi(client)
    pending: List[Dict[str, Any]] = []
    consecutive_errors = 0
    stopped: Optional[str] = None
    try:
        for idx, target in enumerate(targets, start=1):
            try:
                row = _fetch_one(api, target, stats)
            except QuotaExhausted as exc:
                log.warning("[enrich] %s — 여기까지 저장하고 멈춥니다.", exc)
                stopped = "quota"
                break
            except Exception as exc:  # 한 건 실패로 전체를 멈추지 않는다
                stats["errors"] += 1
                consecutive_errors += 1
                log.warning("[enrich] contentId=%s 조회 실패: %s", target["content_id"], exc)
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    log.error("[enrich] %s건 연속 실패 — API 장애로 보고 멈춥니다.", consecutive_errors)
                    stopped = "errors"
                    break
                continue

            consecutive_errors = 0
            stats["status:" + row["parse_status"]] += 1
            pending.append(row)
            if len(pending) >= FLUSH_EVERY:
                stats["saved"] += repository.save_place_details(conn, pending, settings.chunk_size)
                pending = []
            if idx % 100 == 0:
                log.info("[enrich] %s/%s 진행", idx, len(targets))
    finally:
        client.close()

    stats["saved"] += repository.save_place_details(conn, pending, settings.chunk_size)
    result.update(dict(stats))
    result["stopped"] = stopped
    log.info(
        "[enrich] 저장 %s건, API 호출 %s회, 실패 %s건%s",
        stats["saved"],
        stats["api_calls"],
        stats["errors"],
        " (한도 소진으로 중단)" if stopped == "quota" else "",
    )
    return result


def reparse_details(conn: PgConnection, settings: Settings, batch: int = 1000) -> int:
    """저장된 원본으로 정제 컬럼만 다시 계산한다. API를 부르지 않는다.

    파서(detail_parser / indoor)를 고친 뒤 기존 데이터에 반영할 때 쓴다.
    """
    last_id = ""
    total = 0
    while True:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(SELECT_FOR_REPARSE, (last_id, batch))
            rows = [dict(r) for r in cur.fetchall()]
        if not rows:
            break
        rebuilt = []
        for r in rows:
            row = build_detail_row(r, r.get("intro_raw") or None, _stored_common(r))
            row["intro_fetched_at"] = r["intro_fetched_at"]
            row["common_fetched_at"] = r["common_fetched_at"]
            rebuilt.append(row)
        total += repository.save_place_details(conn, rebuilt, settings.chunk_size)
        last_id = rows[-1]["content_id"]
    log.info("[enrich --reparse] %s건 재계산", total)
    return total
