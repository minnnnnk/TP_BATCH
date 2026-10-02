"""한국관광공사_국문 관광정보 서비스_GW (KorService2)
https://www.data.go.kr/data/15101578/openapi.do
"""
import logging
from typing import Any, Dict, List, Optional

from app.tourapi.client import FetchResult, TourApiClient

log = logging.getLogger(__name__)


class KorServiceApi:
    def __init__(self, client: TourApiClient):
        self.client = client

    def fetch_area_based_list(
        self,
        area_code: Optional[str] = None,
        content_type_id: Optional[str] = None,
        num_of_rows: int = 100,
        start_page: int = 1,
        max_pages: int = 20,
    ) -> FetchResult:
        """지역기반 관광정보 목록 조회 (areaBasedList2).

        :param area_code: 지역코드(예: "1"=서울). None이면 전국.
        :param content_type_id: 관광타입ID(예: "12"=관광지, "39"=음식점). None이면 전체.
        :param start_page: 시작 페이지(이전 실행의 커서를 이어받을 때 사용)
        :param max_pages: 최대 조회 페이지 수(일일 호출 한도 보호용 안전장치)
        """
        base_params: Dict[str, str] = {"arrange": "C"}  # 수정일순
        if area_code:
            base_params["areaCode"] = area_code
        if content_type_id:
            base_params["contentTypeId"] = content_type_id

        return self.client.fetch_pages(
            "areaBasedList2", base_params, num_of_rows, start_page, max_pages
        )

    def fetch_detail_common(self, content_id: str) -> Optional[Dict[str, Any]]:
        """공통정보 조회 (detailCommon2).

        areaBasedList2 응답에는 상세 설명(overview)이 없어서, 임베딩 품질을 위해
        이 API로 따로 채워 넣는다. 장소 1건당 호출 1회라 호출 비용이 크다.
        """
        result = self.client.fetch_page(
            "detailCommon2",
            {"contentId": content_id, "numOfRows": "1", "pageNo": "1"},
        )
        items: List[Dict[str, Any]] = result.items
        return items[0] if items else None
