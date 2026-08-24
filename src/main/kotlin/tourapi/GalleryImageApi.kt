package tourapi

import kotlinx.serialization.Serializable

/**
 * 한국관광공사_관광사진 정보_GW (PhotoGalleryService1)
 * https://www.data.go.kr/data/15101914/openapi.do
 */
class GalleryImageApi(
    private val client: TourApiClient = TourApiClient(BASE_URL),
) {
    companion object {
        const val BASE_URL = "https://apis.data.go.kr/B551011/PhotoGalleryService1"
    }

    /**
     * 관광사진갤러리 목록 조회 (galleryList1).
     *
     * @param numOfRows 페이지당 결과 수
     * @param startPage 시작 페이지 (이전 실행의 커서를 이어받을 때 사용)
     * @param maxPages 최대 조회 페이지 수 (개발계정 일일 호출 한도 보호용 안전장치)
     */
    fun fetchGalleryImages(
        numOfRows: Int = 100,
        startPage: Int = 1,
        maxPages: Int = 20,
    ): TourFetchResult<GalleryImageItem> {
        val baseParams = mapOf("arrange" to "C") // 수정일순
        return client.fetchPages("galleryList1", baseParams, numOfRows, startPage, maxPages, GalleryImageItem.serializer())
    }
}

@Serializable
data class GalleryImageItem(
    val galContentId: String? = null,
    val galContentTypeId: String? = null,
    val galTitle: String? = null,
    val galWebImageUrl: String? = null,
    val galPhotographer: String? = null,
    val galPhotographyMonth: String? = null,
    val galPhotographyLocation: String? = null,
    val galSearchKeyword: String? = null,
    val galCreatedtime: String? = null,
    val galModifiedtime: String? = null,
)
