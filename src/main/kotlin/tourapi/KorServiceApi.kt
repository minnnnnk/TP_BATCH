package tourapi

import kotlinx.serialization.Serializable
import org.springframework.stereotype.Component

/**
 * 한국관광공사_국문 관광정보 서비스_GW (KorService2)
 * https://www.data.go.kr/data/15101578/openapi.do
 */
@Component
class KorServiceApi(
    private val client: TourApiClient = TourApiClient(BASE_URL),
) {
    companion object {
        const val BASE_URL = "https://apis.data.go.kr/B551011/KorService2"
    }

    /**
     * 지역기반 관광정보 목록 조회 (areaBasedList2).
     *
     * @param areaCode 지역코드 (예: "1"=서울). null이면 전국.
     * @param contentTypeId 관광타입ID (예: "12"=관광지, "14"=문화시설, "39"=음식점). null이면 전체.
     * @param numOfRows 페이지당 결과 수
     * @param startPage 시작 페이지 (이전 실행의 커서를 이어받을 때 사용)
     * @param maxPages 최대 조회 페이지 수 (전국 데이터가 26만 건에 달하고, 개발계정 일일 호출 한도가
     *   1,000건이므로 무제한 순회를 막기 위한 안전장치)
     */
    fun fetchAreaBasedList(
        areaCode: String? = null,
        contentTypeId: String? = null,
        numOfRows: Int = 100,
        startPage: Int = 1,
        maxPages: Int = 20,
    ): TourFetchResult<TourAreaItem> {
        val baseParams = buildMap {
            put("arrange", "C") // 수정일순
            areaCode?.let { put("areaCode", it) }
            contentTypeId?.let { put("contentTypeId", it) }
        }
        return client.fetchPages("areaBasedList2", baseParams, numOfRows, startPage, maxPages, TourAreaItem.serializer())
    }
}

@Serializable
data class TourAreaItem(
    val contentid: String? = null,
    val contenttypeid: String? = null,
    val title: String? = null,
    val addr1: String? = null,
    val addr2: String? = null,
    val areacode: String? = null,
    val sigungucode: String? = null,
    val cat1: String? = null,
    val cat2: String? = null,
    val cat3: String? = null,
    val firstimage: String? = null,
    val firstimage2: String? = null,
    val mapx: String? = null,
    val mapy: String? = null,
    val mlevel: String? = null,
    val tel: String? = null,
    val zipcode: String? = null,
    val createdtime: String? = null,
    val modifiedtime: String? = null,
)
