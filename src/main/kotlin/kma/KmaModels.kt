package kma

import kotlinx.serialization.Serializable

// ===================================================================
// 1. Raw API Response DTOs
// ===================================================================

@Serializable
data class KmaForecastZoneDto(
    val regId: String? = null,
    val regName: String? = null,
    val regEn: String? = null,
    val regUp: String? = null,
    val regSp: String? = null,
    val lat: String? = null,
    val lon: String? = null,
    val stnId: String? = null,
)

@Serializable
data class KmaWarningZoneDto(
    val warningAreaCode: String? = null,
    val wrnZoneCd: String? = null,
    val wrnZoneName: String? = null,
    val areaCode: String? = null,
    val areaName: String? = null,
    val korName: String? = null,
    val engName: String? = null,
    val regId: String? = null,
    val regName: String? = null,
) {
    val resolvedZoneCd: String?
        get() = warningAreaCode?.takeIf { it.isNotBlank() }
            ?: wrnZoneCd?.takeIf { it.isNotBlank() }
            ?: areaCode?.takeIf { it.isNotBlank() }
            ?: regId?.takeIf { it.isNotBlank() }

    val resolvedZoneName: String?
        get() = korName?.takeIf { it.isNotBlank() }
            ?: wrnZoneName?.takeIf { it.isNotBlank() }
            ?: areaName?.takeIf { it.isNotBlank() }
            ?: regName?.takeIf { it.isNotBlank() }
}

@Serializable
data class KmaVilageFcstItemDto(
    val baseDate: String? = null,
    val baseTime: String? = null,
    val category: String? = null,
    val fcstDate: String? = null,
    val fcstTime: String? = null,
    val fcstValue: String? = null,
    val nx: Int? = null,
    val ny: Int? = null,
)

@Serializable
data class KmaMidTaItemDto(
    val regId: String? = null,
    val taMin3: Double? = null, val taMax3: Double? = null,
    val taMin4: Double? = null, val taMax4: Double? = null,
    val taMin5: Double? = null, val taMax5: Double? = null,
    val taMin6: Double? = null, val taMax6: Double? = null,
    val taMin7: Double? = null, val taMax7: Double? = null,
    val taMin8: Double? = null, val taMax8: Double? = null,
    val taMin9: Double? = null, val taMax9: Double? = null,
    val taMin10: Double? = null, val taMax10: Double? = null,
)

@Serializable
data class KmaMidLandItemDto(
    val regId: String? = null,
    val rnSt3Am: Int? = null, val rnSt3Pm: Int? = null, val wf3Am: String? = null, val wf3Pm: String? = null,
    val rnSt4Am: Int? = null, val rnSt4Pm: Int? = null, val wf4Am: String? = null, val wf4Pm: String? = null,
    val rnSt5Am: Int? = null, val rnSt5Pm: Int? = null, val wf5Am: String? = null, val wf5Pm: String? = null,
    val rnSt6Am: Int? = null, val rnSt6Pm: Int? = null, val wf6Am: String? = null, val wf6Pm: String? = null,
    val rnSt7Am: Int? = null, val rnSt7Pm: Int? = null, val wf7Am: String? = null, val wf7Pm: String? = null,
    val rnSt8: Int? = null, val wf8: String? = null,
    val rnSt9: Int? = null, val wf9: String? = null,
    val rnSt10: Int? = null, val wf10: String? = null,
)


// ===================================================================
// 2. KMA_DATABASE_DESIGN.md 스키마 매핑 레코드 모델
// ===================================================================

/**
 * 1) weather_provider (기관 마스터)
 */
data class WeatherProviderRecord(
    val providerCode: String = "KMA",
    val providerName: String = "기상청 API 허브",
    val apiBaseUrl: String = "https://apihub.kma.go.kr",
    val isActive: Boolean = true,
)

/**
 * 2) forecast_zone (예보구역 마스터)
 */
data class ForecastZoneRecord(
    val regId: String,
    val providerCode: String = "KMA",
    val regName: String,
    val regEn: String? = null,
    val regUp: String? = null,
    val regSp: String? = null,
    val lat: Double? = null,
    val lon: Double? = null,
    val stnId: Int? = null,
)

/**
 * 3) warning_zone (특보구역 마스터)
 */
data class WarningZoneRecord(
    val wrnZoneCd: String,
    val providerCode: String = "KMA",
    val wrnZoneName: String,
)

/**
 * 4) region_location (행정동 지역 마스터)
 */
data class RegionLocationRecord(
    val regionCode: String,
    val providerCode: String = "KMA",
    val regId: String? = null,
    val wrnZoneCd: String? = null,
    val sido: String,
    val sigungu: String? = null,
    val eupmyeondong: String? = null,
    val nx: Int,
    val ny: Int,
    val midTaRegId: String,
    val midLandRegId: String,
    val isActive: Boolean = true,
)

/**
 * 5) short_term_forecast (단기예보 - 최신 갱신형)
 */
data class ShortTermForecastRecord(
    val regionCode: String,
    val providerCode: String = "KMA",
    val baseDatetime: String,
    val fcstDatetime: String,
    val temp: Double? = null,
    val sky: String? = null,
    val pty: String? = null,
    val pop: Int? = null,
    val pcp: String? = null,
    val reh: Int? = null,
    val wsd: Double? = null,
    val vec: Int? = null,
    val version: Int = 1,
)

/**
 * 6) mid_term_forecast (중기예보 - 최신 갱신형)
 */
data class MidTermForecastRecord(
    val midTaRegId: String,
    val midLandRegId: String,
    val providerCode: String = "KMA",
    val baseDatetime: String,
    val fcstDate: String,
    val minTemp: Double? = null,
    val maxTemp: Double? = null,
    val wfAm: String? = null,
    val wfPm: String? = null,
    val popAm: Int? = null,
    val popPm: Int? = null,
    val version: Int = 1,
)
