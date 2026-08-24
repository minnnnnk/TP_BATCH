package tourapi

import java.io.File
import java.util.Properties

object TourApiConfig {

    val serviceKey: String by lazy { loadServiceKey() }

    private fun loadServiceKey(): String {
        System.getenv("TOUR_API_SERVICE_KEY")?.takeIf { it.isNotBlank() }?.let { return it }

        val secretsFile = File("secrets.properties")
        if (secretsFile.exists()) {
            val props = Properties().apply { secretsFile.inputStream().use { load(it) } }
            props.getProperty("tour.api.serviceKey")
                ?.takeIf { it.isNotBlank() && it != "YOUR_DECODING_SERVICE_KEY_HERE" }
                ?.let { return it }
        }

        error(
            "TourAPI 서비스키를 찾을 수 없습니다. " +
                "환경변수 TOUR_API_SERVICE_KEY를 설정하거나, " +
                "secrets.properties.example을 secrets.properties로 복사해 " +
                "tour.api.serviceKey 값을 채워주세요."
        )
    }
}
