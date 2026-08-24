package tourapi

import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.jsonObject
import java.net.URI
import java.net.URLEncoder
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.nio.charset.StandardCharsets

/**
 * TourAPI 공통 호출 클라이언트.
 *
 * TourAPI 응답은 결과가 없을 때 "items": "" (빈 문자열)를 내려주거나,
 * 결과가 1건일 때 "item"이 배열이 아닌 단일 객체로 내려오는 경우가 있어
 * 정적 데이터클래스 디코딩만으로는 깨지기 쉽다. 그래서 JsonElement를
 * 직접 순회하며 방어적으로 파싱한다.
 */
class TourApiClient(private val baseUrl: String) {

    private val httpClient = HttpClient.newHttpClient()
    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

    class TourApiException(val resultCode: String, val resultMsg: String) :
        RuntimeException("TourAPI error [$resultCode]: $resultMsg")

    /**
     * @param operation 예: "areaBasedList2", "galleryImage2"
     * @param params serviceKey/MobileOS/MobileApp/_type을 제외한 나머지 쿼리 파라미터
     */
    fun <T> fetchItems(operation: String, params: Map<String, String>, itemSerializer: KSerializer<T>): TourApiPage<T> {
        val root = requestJson(operation, params)
        val body = root.jsonObject["response"]?.jsonObject?.get("body")?.jsonObject

        val totalCount = body?.get("totalCount")?.toString()?.trim('"')?.toIntOrNull() ?: 0
        val items = extractItems(body, itemSerializer)
        return TourApiPage(items = items, totalCount = totalCount)
    }

    /**
     * `startPage`부터 최대 `maxPages` 페이지까지 순회하며 가져온다.
     * 개발계정 일일 호출 한도 보호용으로, 전체를 다 못 가져오면 [TourFetchResult.exhausted]가 false로
     * 돌아오고 [TourFetchResult.lastPageFetched]에 어디까지 가져왔는지 남는다.
     * 호출부는 이 값을 저장해뒀다가 다음 실행에서 `startPage`로 이어붙이면 된다.
     */
    fun <T> fetchPages(
        operation: String,
        baseParams: Map<String, String>,
        numOfRows: Int,
        startPage: Int,
        maxPages: Int,
        itemSerializer: KSerializer<T>,
    ): TourFetchResult<T> {
        val result = mutableListOf<T>()
        var totalCount = 0
        var lastPageFetched = startPage - 1
        for (offset in 0 until maxPages) {
            val pageNo = startPage + offset
            val params = baseParams + mapOf("numOfRows" to numOfRows.toString(), "pageNo" to pageNo.toString())
            val page = fetchItems(operation, params, itemSerializer)
            totalCount = page.totalCount
            if (page.items.isEmpty()) break
            result += page.items
            lastPageFetched = pageNo
            if (pageNo.toLong() * numOfRows >= totalCount) {
                return TourFetchResult(result, lastPageFetched, totalCount, exhausted = true)
            }
        }
        return TourFetchResult(result, lastPageFetched, totalCount, exhausted = false)
    }

    private fun requestJson(operation: String, params: Map<String, String>): JsonObject {
        val allParams = linkedMapOf(
            "serviceKey" to TourApiConfig.serviceKey,
            "MobileOS" to "ETC",
            "MobileApp" to "Mini_Project_1",
            "_type" to "json",
        )
        allParams.putAll(params)

        val query = allParams.entries.joinToString("&") { (key, value) ->
            "$key=${URLEncoder.encode(value, StandardCharsets.UTF_8)}"
        }
        val uri = URI.create("$baseUrl/$operation?$query")

        val request = HttpRequest.newBuilder(uri).GET().build()
        val response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))

        check(response.statusCode() in 200..299) {
            "TourAPI HTTP ${response.statusCode()} 응답: ${response.body().take(500)}"
        }

        val root = json.parseToJsonElement(response.body()).jsonObject
        val header = root["response"]?.jsonObject?.get("header")?.jsonObject
        val resultCode = header?.get("resultCode")?.toString()?.trim('"')
        val resultMsg = header?.get("resultMsg")?.toString()?.trim('"') ?: "unknown"
        if (resultCode != null && resultCode != "0000") {
            throw TourApiException(resultCode, resultMsg)
        }
        return root
    }

    private fun <T> extractItems(body: JsonObject?, itemSerializer: KSerializer<T>): List<T> {
        val itemsElement = body?.get("items") ?: return emptyList()
        val itemsObject = itemsElement as? JsonObject ?: return emptyList() // "" when empty
        val itemElement = itemsObject["item"] ?: return emptyList()

        return when (itemElement) {
            is JsonArray -> itemElement.map { json.decodeFromJsonElement(itemSerializer, it) }
            is JsonObject -> listOf(json.decodeFromJsonElement(itemSerializer, itemElement))
            else -> emptyList()
        }
    }
}

data class TourApiPage<T>(val items: List<T>, val totalCount: Int)

data class TourFetchResult<T>(
    val items: List<T>,
    val lastPageFetched: Int,
    val totalCount: Int,
    val exhausted: Boolean,
)
