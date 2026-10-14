"""한국관광공사_관광사진 정보_GW (PhotoGalleryService1)
https://www.data.go.kr/data/15101914/openapi.do
"""
from app.tourapi.client import FetchResult, TourApiClient


class GalleryImageApi:
    def __init__(self, client: TourApiClient):
        self.client = client

    def fetch_gallery_images(
        self,
        num_of_rows: int = 100,
        start_page: int = 1,
        max_pages: int = 20,
    ) -> FetchResult:
        """관광사진갤러리 목록 조회 (galleryList1)."""
        return self.client.fetch_pages(
            "galleryList1", {"arrange": "C"}, num_of_rows, start_page, max_pages
        )
