"""TP_BATCH2 커맨드라인 진입점.

    python -m app.cli <command> [options]

명령:
    init-db        스키마 생성 (place / gallery / cursor / travel_spots)
    ingest-area    TourAPI 지역기반 관광정보 -> place
    ingest-gallery TourAPI 관광사진 -> place_gallery_image
    enrich         detailCommon2로 place.overview 채우기
    sync           place -> travel_spots (임베딩 포함)
    status         적재 현황 및 커서 확인
"""
import argparse
import logging
import sys

from app import repository
from app.config import load_settings
from app.db import connect, init_ingest_schema, init_vector_schema
from app.jobs.ingest import enrich_overview, ingest_area, ingest_gallery
from app.jobs.sync_spots import count_pending, sync_spots


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tp-batch2", description="TourAPI 수집 및 벡터 동기화 배치"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="디버그 로그 출력")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-db", help="스키마 생성")
    p_init.add_argument(
        "--with-vector",
        action="store_true",
        help="travel_spots(pgvector) 스키마까지 함께 생성",
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

    p_gallery = sub.add_parser("ingest-gallery", help="관광사진 갤러리 수집")
    p_gallery.add_argument("--max-pages", type=int, help="이번 실행에서 읽을 최대 페이지 수")
    p_gallery.add_argument("--restart", action="store_true", help="1페이지부터 다시 수집")

    p_enrich = sub.add_parser("enrich", help="place.overview 채우기 (detailCommon2)")
    p_enrich.add_argument(
        "--limit", type=int, default=200, help="이번 실행에서 조회할 장소 수 (기본 200)"
    )

    p_sync = sub.add_parser("sync", help="place -> travel_spots 동기화")
    p_sync.add_argument("--limit", type=int, help="이번 실행에서 처리할 장소 수")
    p_sync.add_argument("--batch-size", type=int, help="임베딩/적재 묶음 크기")
    p_sync.add_argument(
        "--dry-run", action="store_true", help="DB 변경 없이 매핑 결과만 출력"
    )

    sub.add_parser("status", help="적재 현황 확인")
    return parser


def _cmd_status(conn) -> None:
    print("=== 적재 현황 ===")
    for table in ("place", "place_gallery_image", "travel_spots"):
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

    if repository.table_exists(conn, "travel_spots"):
        print("\n=== 동기화 대기 ===")
        print("  {0:,} 건이 travel_spots로 동기화 대기 중".format(count_pending(conn)))


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    _configure_logging(args.verbose)
    settings = load_settings()

    with connect(settings) as conn:
        if args.command == "init-db":
            init_ingest_schema(conn)
            if args.with_vector:
                init_vector_schema(conn, settings.embedding_dimension)
        elif args.command == "ingest-area":
            init_ingest_schema(conn)
            ingest_area(
                conn,
                settings,
                area_code=args.area_code,
                content_type_id=args.content_type_id,
                max_pages=args.max_pages,
                restart=args.restart,
            )
        elif args.command == "ingest-gallery":
            init_ingest_schema(conn)
            ingest_gallery(
                conn, settings, max_pages=args.max_pages, restart=args.restart
            )
        elif args.command == "enrich":
            enrich_overview(conn, settings, limit=args.limit)
        elif args.command == "sync":
            # --dry-run은 매핑 결과만 보는 용도라 스키마도 건드리지 않는다.
            if not args.dry_run:
                init_vector_schema(conn, settings.embedding_dimension)
            sync_spots(
                conn,
                settings,
                limit=args.limit,
                batch_size=args.batch_size,
                dry_run=args.dry_run,
            )
        elif args.command == "status":
            _cmd_status(conn)

    return 0


if __name__ == "__main__":
    sys.exit(main())
