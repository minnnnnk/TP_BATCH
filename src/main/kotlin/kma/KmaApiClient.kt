package kma

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
import java.time.Duration

/**
 * 기상청 API 허브 (apihub.kma.go.kr) 및 공공데이터포털 공통 HTTP 클라이언트
 */
class KmaApiClient(
    private val baseUrl: String = KmaConfig.baseUrl,
    private val apiKey: String = KmaConfig.apiKey,
) {
    private val httpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(10))
        .build()

    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

    class KmaApiException(val resultCode: String, val resultMsg: String) :
        RuntimeException("KMA API error [$resultCode]: $resultMsg")

    /**
     * KMA Open API 호출 및 items 역직렬화
     * @param path API 경로 (예: "/api/typ02/openApi/VilageFcstInfoService_2.0/getVilageFcst")
     * @param params 쿼리 파라미터
     */
    fun <T> fetchItems(path: String, params: Map<String, String>, itemSerializer: KSerializer<T>): List<T> {
        val root = requestJson(path, params)
        val body = root.jsonObject["response"]?.jsonObject?.get("body")?.jsonObject
        return extractItems(body, itemSerializer)
    }

    /**
     * HTTP 요청 수행 및 JsonObject 파싱
     */
    fun requestJson(path: String, params: Map<String, String>): JsonObject {
        val cleanBaseUrl = baseUrl.trimEnd('/')
        val cleanPath = if (path.startsWith("/")) path else "/$path"

        val queryParams = linkedMapOf<String, String>()
        if (apiKey.isNotBlank()) {
            if (cleanBaseUrl.contains("apihub.kma.go.kr")) {
                queryParams["authKey"] = apiKey
            } else {
                queryParams["serviceKey"] = apiKey
            }
        }
        queryParams["dataType"] = "JSON"
        queryParams.putAll(params)

        val queryString = queryParams.entries.joinToString("&") { (k, v) ->
            "$k=${URLEncoder.encode(v, StandardCharsets.UTF_8)}"
        }

        val fullUrl = "$cleanBaseUrl$cleanPath?$queryString"
        val request = HttpRequest.newBuilder(URI.create(fullUrl))
            .timeout(Duration.ofSeconds(15))
            .GET()
            .build()

        val response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
        check(response.statusCode() in 200..299) {
            "KMA API HTTP ${response.statusCode()} Error: ${response.body().take(500)}"
        }

        return parseJsonResponse(response.body())
    }

    /**
     * JSON 응답 유효성 및 헤더 검증
     */
    fun parseJsonResponse(responseBody: String): JsonObject {
        val root = json.parseToJsonElement(responseBody).jsonObject
        val header = root["response"]?.jsonObject?.get("header")?.jsonObject
        val resultCode = header?.get("resultCode")?.toString()?.trim('"')
        val resultMsg = header?.get("resultMsg")?.toString()?.trim('"') ?: "unknown"

        if (resultCode != null && resultCode != "00" && resultCode != "0000") {
            throw KmaApiException(resultCode, resultMsg)
        }
        return root
    }

    /**
     * items -> item 배열/객체 방어적 추출
     */
    fun <T> extractItems(body: JsonObject?, itemSerializer: KSerializer<T>): List<T> {
        val itemsElement = body?.get("items") ?: return emptyList()
        val itemsObject = itemsElement as? JsonObject ?: return emptyList()
        val itemElement = itemsObject["item"] ?: return emptyList()

        return when (itemElement) {
            is JsonArray -> itemElement.map { json.decodeFromJsonElement(itemSerializer, it) }
            is JsonObject -> listOf(json.decodeFromJsonElement(itemSerializer, itemElement))
            else -> emptyList()
        }
    }
}
