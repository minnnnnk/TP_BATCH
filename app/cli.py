"""TP_BATCH2 커맨드라인 진입점.

    python -m app.cli <command> [options]

명령:
    init-db        스키마 생성 (place / gallery / cursor / place_detail / 운영 테이블)
    ingest-area    TourAPI 지역기반 관광정보 -> place (전량 수집, 커서로 이어받기)
    ingest-gallery TourAPI 관광사진 -> place_gallery_image
    refresh        최근 수정된 장소만 place에 반영 (일일 갱신)
    enrich         detailIntro2/detailCommon2 -> place_detail (운영시간·휴무일·실내외, B-10)
    sync           place (+ place_detail) -> travel_spots (임베딩 포함)
    daily          refresh -> gallery -> enrich 를 하루치 한도 안에서 실행 (B-08)
    schedule       daily를 매일 정해진 시각에 실행하는 상주 스케줄러 (B-08)
    status         적재 현황, 상세정보 보강 현황, 오늘 호출 수, 최근 실행 이력
"""
import argparse
import logging
import sys
from contextlib import contextmanager
from typing import Iterator

from app import repository
from app.config import Settings, load_settings
from app.db import connect, init_ingest_schema, init_vector_schema
from app.jobs.enrich import count_pending_details, enrich_details, reparse_details
from app.jobs.ingest import ingest_area, ingest_gallery, refresh_places
from app.jobs.sync_spots import count_pending, sync_spots
from app.quota import DailyQuota, QuotaExhausted, today_kst


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tp-batch2", description="TourAPI 수집·정제 및 벡터 동기화 배치"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="디버그 로그 출력")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-db", help="스키마 생성")
    p_init.add_argument(
        "--with-vector",
        action="store_true",
        help="travel_spots / place_embedding(pgvector) 스키마까지 함께 생성",
    )

    p_area = sub.add_parser("ingest-area", help="지역기반 관광정보 수집")
    p_area.add_argument("--area-code", help='지역코드 (예: "32"=강원). 생략 시 전국')
    p_area.add_argument(
        "--content-type-id", help='관광타입ID (예: "12"=관광지, "39"=음식점)'
    )
    p_area.add_argument("--max-pages", type=int, help="이번 실행에서 읽을 최대 페이지 수")
    p_area.add_argument(
        "--restart", action="store_true", help="커서를 무시하고 1페이지부터 다시 수집"
    )
    p_area.add_argument(
        "--dry-run", action="store_true", help="DB 저장 없이 API 수집 데이터만 콘솔에 출력"
    )

    p_gallery = sub.add_parser("ingest-gallery", help="관광사진 갤러리 수집")
    p_gallery.add_argument("--max-pages", type=int, help="이번 실행에서 읽을 최대 페이지 수")
    p_gallery.add_argument("--restart", action="store_true", help="1페이지부터 다시 수집")

    p_refresh = sub.add_parser("refresh", help="최근 수정된 장소만 반영")
    p_refresh.add_argument("--max-pages", type=int, help="최대 페이지 수 (기본 DAILY_REFRESH_MAX_PAGES)")

    p_enrich = sub.add_parser("enrich", help="상세정보 보강 (운영시간·휴무일·실내외)")
    p_enrich.add_argument(
        "--limit", type=int, default=200, help="이번 실행에서 조회할 장소 수 (기본 200)"
    )
    p_enrich.add_argument("--area-code", help="이 지역코드만 (예: 32)")
    p_enrich.add_argument("--content-type-id", help="이 관광타입만 (예: 39)")
    p_enrich.add_argument(
        "--no-overview",
        action="store_true",
        help="개요·신분류코드(detailCommon2)는 건너뛰고 소개정보만 (장소당 호출 1회)",
    )
    p_enrich.add_argument(
        "--reparse",
        action="store_true",
        help="API 호출 없이 저장된 원문으로 정제 값만 다시 계산 (파서 수정 후)",
    )

    p_sync = sub.add_parser("sync", help="place -> travel_spots 동기화")
    p_sync.add_argument("--limit", type=int, help="이번 실행에서 처리할 장소 수")
    p_sync.add_argument("--batch-size", type=int, help="임베딩/적재 묶음 크기")
    p_sync.add_argument(
        "--dry-run", action="store_true", help="DB 변경 없이 매핑 결과만 출력"
    )

    sub.add_parser("daily", help="일일 배치 1회 실행 (refresh -> gallery -> enrich)")

    p_schedule = sub.add_parser("schedule", help="daily를 매일 실행하는 상주 스케줄러")
    p_schedule.add_argument(
        "--run-now", action="store_true", help="시작하자마자 한 번 실행하고 이후 스케줄대로"
    )

    sub.add_parser("status", help="적재 현황 확인")
    return parser


@contextmanager
def _quota(settings: Settings) -> Iterator[DailyQuota]:
    """호출 카운트 전용 커넥션 (잡 트랜잭션과 커밋이 섞이지 않게)."""
    with connect(settings) as quota_conn:
        yield DailyQuota(quota_conn, settings.tour_api_daily_limit)


def _cmd_status(conn, settings: Settings) -> None:
    print("=== 적재 현황 ===")
    for table in ("place", "place_gallery_image", "place_detail", "travel_spots", "place_embedding"):
        if repository.table_exists(conn, table):
            print("  {0:<20} {1:>10,} 건".format(table, repository.count_rows(conn, table)))
        else:
            print("  {0:<20} {1:>10}".format(table, "(없음)"))

    if repository.table_exists(conn, "fetch_cursor"):
        cursors = repository.list_cursors(conn)
        print("\n=== 수집 커서 ===")
        if not cursors:
            print("  (기록 없음 — 아직 수집 전)")
        for source, last_page, total in cursors:
            print("  {0:<40} last_page={1:<6} total_count={2:,}".format(source, last_page, total))

    if repository.table_exists(conn, "place_detail"):
        print("\n=== 상세정보 보강 (B-10) ===")
        print("  아직 조회 안 한(또는 원본이 바뀐) 장소: {0:,} 건".format(count_pending_details(conn)))
        with conn.cursor() as cur:
            cur.execute("SELECT parse_status, count(*) FROM place_detail GROUP BY 1 ORDER BY 2 DESC")
            parsed = ", ".join("{0} {1:,}".format(s, n) for s, n in cur.fetchall())
            cur.execute(
                "SELECT COALESCE(indoor_type, '판정불가'), count(*) FROM place_detail GROUP BY 1 ORDER BY 2 DESC"
            )
            indoor = ", ".join("{0} {1:,}".format(s, n) for s, n in cur.fetchall())
        print("  정제 상태: {0}".format(parsed or "-"))
        print("  실내외:    {0}".format(indoor or "-"))

    if repository.table_exists(conn, "travel_spots"):
        print("\n=== 동기화 대기 ===")
        if repository.column_exists(conn, "travel_spots", "source_content_id") and repository.table_exists(
            conn, "place_detail"
        ):
            print("  {0:,} 건이 travel_spots로 동기화 대기 중".format(count_pending(conn)))
        else:
            print("  (sync를 아직 한 번도 실행하지 않음 — travel_spots.source_content_id 없음)")

    if repository.table_exists(conn, "api_call_quota"):
        print("\n=== 오늘({0}) TourAPI 호출 수 / 한도 {1} ===".format(today_kst(), settings.tour_api_daily_limit))
        with conn.cursor() as cur:
            cur.execute(
                "SELECT service, calls FROM api_call_quota WHERE usage_date = %s ORDER BY service",
                (today_kst(),),
            )
            rows = cur.fetchall()
        for service, calls in rows:
            print("  {0:<24} {1:>5}".format(service, calls))
        if not rows:
            print("  (오늘 호출 없음)")

    if repository.table_exists(conn, "batch_job_run"):
        runs = repository.list_job_runs(conn)
        print("\n=== 최근 실행 ===")
        if not runs:
            print("  (기록 없음)")
        for run_id, job, started, finished, status, stats, error in runs:
            print(
                "  #{0} {1:<6} {2:%Y-%m-%d %H:%M} {3:<8} {4}".format(
                    run_id, job, started, status, (stats or {}).get("quota_used", "")
                )
            )
            if error:
                print("      error: {0}".format(error.splitlines()[0][:150]))


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    _configure_logging(args.verbose)
    settings = load_settings()

    if args.command == "daily":
        from app.jobs.daily import run_daily

        result = run_daily(settings)
        return 1 if result.get("skipped") == "locked" else 0
    if args.command == "schedule":
        from app.scheduler import run_scheduler

        run_scheduler(settings, run_now=args.run_now)
        return 0

    with connect(settings) as conn:
        if args.command == "init-db":
            init_ingest_schema(conn)
            if args.with_vector:
                init_vector_schema(conn, settings.embedding_dimension)
        elif args.command == "ingest-area":
            if args.dry_run:
                # --dry-run은 서비스키 확인용이라 스키마도, 호출 카운트(api_call_quota)도 건드리지 않는다.
                ingest_area(
                    conn,
                    settings,
                    area_code=args.area_code,
                    content_type_id=args.content_type_id,
                    max_pages=args.max_pages,
                    dry_run=True,
                )
            else:
                init_ingest_schema(conn)
                with _quota(settings) as quota:
                    ingest_area(
                        conn,
                        settings,
                        area_code=args.area_code,
                        content_type_id=args.content_type_id,
                        max_pages=args.max_pages,
                        restart=args.restart,
                        quota=quota,
                    )
        elif args.command == "ingest-gallery":
            init_ingest_schema(conn)
            with _quota(settings) as quota:
                ingest_gallery(
                    conn, settings, max_pages=args.max_pages, restart=args.restart, quota=quota
                )
        elif args.command == "refresh":
            init_ingest_schema(conn)
            with _quota(settings) as quota:
                refresh_places(conn, settings, max_pages=args.max_pages, quota=quota)
        elif args.command == "enrich":
            init_ingest_schema(conn)
            if args.reparse:
                reparse_details(conn, settings)
            else:
                with _quota(settings) as quota:
                    enrich_details(
                        conn,
                        settings,
                        limit=args.limit,
                        quota=quota,
                        with_overview=False if args.no_overview else None,
                        area_code=args.area_code,
                        content_type_id=args.content_type_id,
                    )
        elif args.command == "sync":
            # --dry-run은 매핑 결과만 보는 용도라 스키마도 건드리지 않는다.
            if not args.dry_run:
                init_ingest_schema(conn)
                init_vector_schema(conn, settings.embedding_dimension)
            sync_spots(
                conn,
                settings,
                limit=args.limit,
                batch_size=args.batch_size,
                dry_run=args.dry_run,
            )
        elif args.command == "status":
            _cmd_status(conn, settings)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except QuotaExhausted as exc:
        logging.getLogger(__name__).warning("%s — 내일 다시 실행하세요.", exc)
        sys.exit(2)
