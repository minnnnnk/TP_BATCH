"""TourAPI 공통 호출 클라이언트.

TourAPI 응답은 결과가 없을 때 "items": "" (빈 문자열)를 내려주거나,
결과가 1건일 때 "item"이 배열이 아닌 단일 객체로 내려오는 경우가 있어
스키마를 고정해 파싱하면 쉽게 깨진다. 그래서 dict를 직접 순회하며
방어적으로 파싱한다. (Kotlin TourApiClient.kt와 동일한 전략)
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

Item = Dict[str, Any]


class TourApiError(RuntimeError):
    """TourAPI가 resultCode != 0000으로 응답한 경우."""

    def __init__(self, result_code: str, result_msg: str):
        super().__init__("TourAPI error [{0}]: {1}".format(result_code, result_msg))
        self.result_code = result_code
        self.result_msg = result_msg


@dataclass
class FetchResult:
    """여러 페이지를 순회한 결과.

    exhausted가 False면 max_pages 한도에 걸려 아직 남은 데이터가 있다는 뜻이다.
    호출부는 last_page_fetched를 저장해뒀다가 다음 실행에서 start_page로 이어붙인다.
    """

    items: List[Item] = field(default_factory=list)
    last_page_fetched: int = 0
    total_count: int = 0
    exhausted: bool = False


class TourApiClient:
    def __init__(
        self,
        base_url: str,
        service_key: str,
        mobile_app: str = "TP_BATCH2",
        timeout_sec: int = 20,
    ):
        self.base_url = base_url.rstrip("/")
        self.service_key = service_key
        self.mobile_app = mobile_app
        self.timeout_sec = timeout_sec

        # 공공데이터포털은 순간적인 5xx/타임아웃이 잦아 재시도를 붙인다.
        retry = Retry(
            total=4,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
        )
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def close(self) -> None:
        self.session.close()

    def fetch_page(self, operation: str, params: Dict[str, str]) -> FetchResult:
        """단일 페이지 조회."""
        root = self._request_json(operation, params)
        body = (root.get("response") or {}).get("body") or {}

        total_count = _to_int(body.get("totalCount"), 0)
        items = _extract_items(body)
        return FetchResult(items=items, total_count=total_count)

    def fetch_pages(
        self,
        operation: str,
        base_params: Dict[str, str],
        num_of_rows: int,
        start_page: int,
        max_pages: int,
    ) -> FetchResult:
        """start_page부터 최대 max_pages 페이지까지 순회한다.

        개발계정 일일 호출 한도가 있어 한 번에 전량을 가져올 수 없으므로,
        한도에 걸리면 중단하고 어디까지 읽었는지를 결과에 남긴다.
        """
        collected: List[Item] = []
        total_count = 0
        last_page_fetched = start_page - 1

        for offset in range(max_pages):
            page_no = start_page + offset
            params = dict(base_params)
            params["numOfRows"] = str(num_of_rows)
            params["pageNo"] = str(page_no)

            page = self.fetch_page(operation, params)
            total_count = page.total_count
            if not page.items:
                break

            collected.extend(page.items)
            last_page_fetched = page_no
            log.info(
                "  page %s: %s건 누적 (전체 %s건)", page_no, len(collected), total_count
            )

            if page_no * num_of_rows >= total_count:
                return FetchResult(collected, last_page_fetched, total_count, True)

        return FetchResult(collected, last_page_fetched, total_count, False)

    def _request_json(self, operation: str, params: Dict[str, str]) -> Dict[str, Any]:
        query = {
            "serviceKey": self.service_key,
            "MobileOS": "ETC",
            "MobileApp": self.mobile_app,
            "_type": "json",
        }
        query.update(params)

        url = "{0}/{1}".format(self.base_url, operation)
        response = self.session.get(url, params=query, timeout=self.timeout_sec)
        if not (200 <= response.status_code < 300):
            raise RuntimeError(
                "TourAPI HTTP {0} 응답: {1}".format(
                    response.status_code, response.text[:500]
                )
            )

        try:
            root = response.json()
        except ValueError:
            # 키 오류/한도 초과 시 XML 에러 문서가 내려오는 경우가 있다.
            raise RuntimeError(
                "TourAPI 응답을 JSON으로 읽을 수 없습니다: {0}".format(response.text[:500])
            )

        header = (root.get("response") or {}).get("header") or {}
        result_code = header.get("resultCode")
        result_msg = header.get("resultMsg", "unknown")
        if result_code is not None and str(result_code) != "0000":
            raise TourApiError(str(result_code), str(result_msg))
        return root


def _extract_items(body: Dict[str, Any]) -> List[Item]:
    items = body.get("items")
    if not isinstance(items, dict):  # 결과 없음: "" 으로 내려온다
        return []
    item = items.get("item")
    if isinstance(item, list):
        return [i for i in item if isinstance(i, dict)]
    if isinstance(item, dict):  # 1건일 때 단일 객체
        return [item]
    return []


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def text_or_none(value: Any) -> Optional[str]:
    """빈 문자열은 None으로 정규화한다(TourAPI는 누락값을 ""로 준다)."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def float_or_none(value: Any) -> Optional[float]:
    text = text_or_none(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None
