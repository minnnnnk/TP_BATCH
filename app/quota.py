"""TourAPI 일일 호출 한도 관리.

개발계정은 서비스(KorService2, PhotoGalleryService1)마다 하루 호출 수가 정해져 있다.
한도를 넘기면 그날은 모든 호출이 실패하므로, 호출 전에 DB(api_call_quota)에
카운트를 올리고 상한에 닿으면 QuotaExhausted로 멈춘다.

카운트를 DB에 두는 이유는 수동 실행(CLI)과 스케줄러 실행이 같은 날 섞여도
합산되게 하기 위함이다. 한도는 한국 시간 자정에 초기화되므로 날짜도 KST 기준이다.
"""
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from psycopg2.extensions import connection as PgConnection

log = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

# 상한 미만일 때만 1 올린다. 상한에 닿았으면 UPDATE가 일어나지 않아 행이 반환되지 않는다.
ACQUIRE_SQL = """
INSERT INTO api_call_quota (usage_date, service, calls) VALUES (%s, %s, 1)
ON CONFLICT (usage_date, service) DO UPDATE
    SET calls = api_call_quota.calls + 1
    WHERE api_call_quota.calls < %s
RETURNING calls
"""

MARK_EXHAUSTED_SQL = """
INSERT INTO api_call_quota (usage_date, service, calls) VALUES (%s, %s, %s)
ON CONFLICT (usage_date, service) DO UPDATE
    SET calls = GREATEST(api_call_quota.calls, EXCLUDED.calls)
"""


class QuotaExhausted(RuntimeError):
    """오늘 호출 한도를 다 썼다. 잡은 여기서 멈추고 다음 날 이어서 하면 된다."""

    def __init__(self, service: str, detail: str = ""):
        message = "TourAPI 일일 호출 한도 소진: {0}".format(service)
        if detail:
            message += " ({0})".format(detail)
        super().__init__(message)
        self.service = service


def today_kst() -> date:
    return datetime.now(KST).date()


class DailyQuota:
    """서비스별 일일 호출 카운터.

    잡이 쓰는 커넥션과 섞이면 카운트 커밋이 잡의 미완료 트랜잭션까지 커밋해 버리므로,
    전용 커넥션을 넘겨받아 쓴다.
    """

    def __init__(self, conn: PgConnection, daily_limit: int):
        if daily_limit <= 0:
            raise ValueError("daily_limit은 1 이상이어야 합니다: {0}".format(daily_limit))
        self.conn = conn
        self.daily_limit = daily_limit

    def acquire(self, service: str) -> int:
        """호출 1회를 예약한다. 한도에 닿았으면 QuotaExhausted."""
        with self.conn.cursor() as cur:
            cur.execute(ACQUIRE_SQL, (today_kst(), service, self.daily_limit))
            row = cur.fetchone()
        self.conn.commit()
        if row is None:
            raise QuotaExhausted(service, "{0}회 사용".format(self.daily_limit))
        return int(row[0])

    def mark_exhausted(self, service: str) -> None:
        """서버가 한도 초과로 응답했을 때, 오늘은 더 부르지 않도록 카운터를 상한으로 올린다.

        같은 서비스키를 다른 배치(Kotlin TP_BATCH 등)와 같이 쓰면 이쪽 카운트보다
        먼저 서버 한도에 닿을 수 있다.
        """
        with self.conn.cursor() as cur:
            cur.execute(MARK_EXHAUSTED_SQL, (today_kst(), service, self.daily_limit))
        self.conn.commit()
        log.warning("[quota] %s: 서버가 한도 초과로 응답 — 오늘 남은 호출을 막습니다.", service)

    def used(self, service: str) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT calls FROM api_call_quota WHERE usage_date = %s AND service = %s",
                (today_kst(), service),
            )
            row = cur.fetchone()
        self.conn.commit()
        return int(row[0]) if row else 0

    def remaining(self, service: str) -> int:
        return max(0, self.daily_limit - self.used(service))
