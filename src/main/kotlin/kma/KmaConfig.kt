package kma

import java.io.File
import java.util.Properties

/**
 * 기상청 API 허브 (apihub.kma.go.kr) 및 공공데이터포털 기상 API 설정 로더
 */
object KmaConfig {

    private const val DEFAULT_API_BASE_URL = "https://apihub.kma.go.kr"

    val apiKey: String by lazy { loadApiKey() }

    val baseUrl: String by lazy { loadBaseUrl() }

    private fun loadApiKey(): String {
        // 1. 환경변수 우선 조회
        System.getenv("KMA_API_KEY")?.takeIf { it.isNotBlank() }?.let { return it }
        System.getenv("KMA_AUTH_KEY")?.takeIf { it.isNotBlank() }?.let { return it }

        // 2. secrets.properties 조회
        val secretsFile = File("secrets.properties")
        if (secretsFile.exists()) {
            val props = Properties().apply { secretsFile.inputStream().use { load(it) } }
            props.getProperty("kma.api.authKey")
                ?.takeIf { it.isNotBlank() && it != "YOUR_KMA_AUTH_KEY_HERE" }
                ?.let { return it }
            props.getProperty("kma.api.serviceKey")
                ?.takeIf { it.isNotBlank() && it != "YOUR_KMA_SERVICE_KEY_HERE" }
                ?.let { return it }
        }

        return ""
    }

    private fun loadBaseUrl(): String {
        return System.getenv("KMA_BASE_URL")?.takeIf { it.isNotBlank() } ?: DEFAULT_API_BASE_URL
    }
}
