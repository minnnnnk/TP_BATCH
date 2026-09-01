package kma

import org.springframework.stereotype.Service
import java.time.LocalDate
import java.time.format.DateTimeFormatter

/**
 * 기상청 API 허브 데이터를 조회하여 KMA_DATABASE_DESIGN.md 규격 레코드로 변환하는 서비스
 */
@Service
open class KmaApiService(
    private val client: KmaApiClient = KmaApiClient(),
) {

    companion object {
        // 단기예보 및 구역코드 API 경로 (API 허브 typ02 기준)
        const val PATH_FCST_ZONE = "/api/typ02/openApi/FcstZoneInfoService/getFcstZoneCd"
        const val PATH_WRN_ZONE = "/api/typ02/openApi/WthrWrnInfoService/getWthrWrnList"
        const val PATH_VILAGE_FCST = "/api/typ02/openApi/VilageFcstInfoService_2.0/getVilageFcst"

        // 중기예보 API 경로
        const val PATH_MID_TA = "/api/typ02/openApi/MidFcstInfoService/getMidTa"
        const val PATH_MID_LAND = "/api/typ02/openApi/MidFcstInfoService/getMidLandFcst"
    }

    /**
     * 1) 예보구역 마스터 단일/페이지 조회 (`forecast_zone`)
     *
     * @param regId 특정 예보구역 코드 (생략 시 전체 조회)
     * @param numOfRows 한 페이지 결과 수 (기본값: 1000)
     * @param pageNo 페이지 번호 (기본값: 1)
     */
    open fun fetchForecastZones(
        regId: String? = null,
        numOfRows: Int = 1000,
        pageNo: Int = 1,
    ): List<ForecastZoneRecord> {
        val params = mutableMapOf(
            "numOfRows" to numOfRows.toString(),
            "pageNo" to pageNo.toString()
        )
        if (!regId.isNullOrBlank()) {
            params["regId"] = regId
        }

        val items = client.fetchItems(PATH_FCST_ZONE, params, KmaForecastZoneDto.serializer())

        return items.mapNotNull { dto ->
            val id = dto.regId?.takeIf { it.isNotBlank() } ?: return@mapNotNull null
            ForecastZoneRecord(
                regId = id,
                providerCode = "KMA",
                regName = dto.regName ?: "",
                regEn = dto.regEn,
                regUp = dto.regUp,
                regSp = dto.regSp,
                lat = dto.lat?.toDoubleOrNull(),
                lon = dto.lon?.toDoubleOrNull(),
                stnId = dto.stnId?.toIntOrNull(),
            )
        }
    }

    /**
     * 1-1) 북한을 제외한 대한민국 전역의 모든 예보구역 마스터 일괄 수집 (페이징 전체 순회)
     *
     * - 기상청 구역코드 중 북한 지역 코드 (11I~11P: 황해도, 평안도, 함경도, 자강도, 량강도 등) 제외
     * - 대한민국 전역 (11A~11H 및 해상 등) 대상
     */
    fun fetchAllSouthKoreaForecastZones(pageSize: Int = 1000): List<ForecastZoneRecord> {
        val result = mutableListOf<ForecastZoneRecord>()
        var pageNo = 1

        while (true) {
            val pageRecords = fetchForecastZones(numOfRows = pageSize, pageNo = pageNo)
            if (pageRecords.isEmpty()) break

            val southKoreaRecords = pageRecords.filter { isSouthKoreaZone(it.regId, it.regUp, it.regName) }
            result.addAll(southKoreaRecords)

            if (pageRecords.size < pageSize) break
            pageNo++
        }

        return result
    }

    /**
     * 대한민국 예보구역 여부 판별 (북한 구역 제외)
     */
    fun isSouthKoreaZone(regId: String, regUp: String?, regName: String): Boolean {
        // 북한 지역 코드 Prefix (11I: 황해도, 11J: 평안남도, 11K: 평안북도, 11L: 함경남도, 11M: 함경북도, 11N: 자강도, 11O: 양강도 등)
        val northKoreaPrefixes = listOf("11I", "11J", "11K", "11L", "11M", "11N", "11O", "11P")
        if (northKoreaPrefixes.any { regId.startsWith(it, ignoreCase = true) }) {
            return false
        }
        if (regUp != null && northKoreaPrefixes.any { regUp.startsWith(it, ignoreCase = true) }) {
            return false
        }

        // 북한 주요 도시/행정구역명 추가 방어 필터링
        val northKoreaCities = listOf("평양", "개성", "신의주", "함흥", "청진", "나선", "남포", "해주", "사리원", "강계", "혜산", "원산")
        if (northKoreaCities.any { regName.startsWith(it) }) {
            return false
        }

        return true
    }

    /**
     * 2) 특보구역 마스터 조회 (`warning_zone`)
     */
    fun fetchWarningZones(numOfRows: Int = 1000, pageNo: Int = 1): List<WarningZoneRecord> {
        val params = mapOf("numOfRows" to numOfRows.toString(), "pageNo" to pageNo.toString())
        val items = client.fetchItems(PATH_WRN_ZONE, params, KmaWarningZoneDto.serializer())

        return items.mapNotNull { dto ->
            val wrnZoneCd = dto.wrnZoneCd?.takeIf { it.isNotBlank() } ?: return@mapNotNull null
            WarningZoneRecord(
                wrnZoneCd = wrnZoneCd,
                providerCode = "KMA",
                wrnZoneName = dto.wrnZoneName ?: "",
            )
        }
    }

    /**
     * 3) 단기예보 조회 및 변환 (`short_term_forecast`)
     *
     * numOfRows와 pageNo를 증가시키며 모든 페이지의 예보 데이터를 수집합니다.
     * 기상청 getVilageFcst 응답 항목을 (fcstDate, fcstTime)별로 피벗/그룹핑하여 short_term_forecast 레코드로 매핑합니다.
     * @param intervalHours 수집 간격 (시간 단위, 기본값 4: 00시, 04시, 08시, 12시, 16시, 20시)
     */
    open fun fetchShortTermForecast(
        regionCode: String,
        nx: Int,
        ny: Int,
        baseDate: String,
        baseTime: String,
        numOfRows: Int = 1000,
        intervalHours: Int = 4,
    ): List<ShortTermForecastRecord> {
        val allItems = mutableListOf<KmaVilageFcstItemDto>()
        var pageNo = 1

        while (true) {
            val params = mapOf(
                "numOfRows" to numOfRows.toString(),
                "pageNo" to pageNo.toString(),
                "base_date" to baseDate,
                "base_time" to baseTime,
                "nx" to nx.toString(),
                "ny" to ny.toString(),
            )

            val items = client.fetchItems(PATH_VILAGE_FCST, params, KmaVilageFcstItemDto.serializer())
            if (items.isEmpty()) break
            allItems.addAll(items)

            if (items.size < numOfRows) break
            pageNo++
        }

        return transformVilageFcstItems(regionCode, baseDate, baseTime, allItems, intervalHours)
    }

    /**
     * 단기예보 DTO 목록 -> ShortTermForecastRecord 목록 변환 (피벗 및 시간 간격 필터링)
     * @param intervalHours 예보 시간 간격 필터 (기본 4: 00시, 04시, 08시, 12시, 16시, 20시 등, 1 이하일 경우 전체 수집)
     */
    fun transformVilageFcstItems(
        regionCode: String,
        baseDate: String,
        baseTime: String,
        items: List<KmaVilageFcstItemDto>,
        intervalHours: Int = 4,
    ): List<ShortTermForecastRecord> {
        val baseDatetime = formatDateTime(baseDate, baseTime)

        // (fcstDate, fcstTime) 별로 그룹핑
        val grouped = items.groupBy { (it.fcstDate ?: "") to (it.fcstTime ?: "") }

        return grouped.filterKeys { (date, time) ->
            if (date.isBlank() || time.isBlank()) return@filterKeys false
            if (intervalHours > 1) {
                val hour = time.take(2).toIntOrNull() ?: return@filterKeys false
                hour % intervalHours == 0
            } else {
                true
            }
        }.map { (key, catItems) ->
            val (fcstDate, fcstTime) = key
            val fcstDatetime = formatDateTime(fcstDate, fcstTime)

            val catMap = catItems.associate { (it.category ?: "") to (it.fcstValue ?: "") }

            ShortTermForecastRecord(
                regionCode = regionCode,
                providerCode = "KMA",
                baseDatetime = baseDatetime,
                fcstDatetime = fcstDatetime,
                temp = catMap["TMP"]?.toDoubleOrNull(),
                sky = mapSky(catMap["SKY"]),
                pty = mapPty(catMap["PTY"]),
                pop = catMap["POP"]?.toIntOrNull(),
                pcp = catMap["PCP"],
                reh = catMap["REH"]?.toIntOrNull(),
                wsd = catMap["WSD"]?.toDoubleOrNull(),
                vec = catMap["VEC"]?.toIntOrNull(),
                version = 1,
            )
        }.sortedBy { it.fcstDatetime }
    }

    /**
     * 4) 중기예보 조회 및 결합 (`mid_term_forecast`)
     *
     * 중기기온(getMidTa)과 중기육상(getMidLandFcst)을 조회하여 D+3 ~ D+10 일자별로 조인합니다.
     */
    open fun fetchMidTermForecast(
        midTaRegId: String,
        midLandRegId: String,
        tmFc: String, // 발표시각 예: 202609010600 (YYYYMMDD0600)
    ): List<MidTermForecastRecord> {
        val taParams = mapOf("regId" to midTaRegId, "tmFc" to tmFc)
        val landParams = mapOf("regId" to midLandRegId, "tmFc" to tmFc)

        val taItems = client.fetchItems(PATH_MID_TA, taParams, KmaMidTaItemDto.serializer())
        val landItems = client.fetchItems(PATH_MID_LAND, landParams, KmaMidLandItemDto.serializer())

        val taDto = taItems.firstOrNull()
        val landDto = landItems.firstOrNull()

        return transformMidTermForecast(midTaRegId, midLandRegId, tmFc, taDto, landDto)
    }

    /**
     * 중기 기온 DTO + 중기 육상 DTO -> MidTermForecastRecord 목록 변환 (D+3 ~ D+10)
     */
    fun transformMidTermForecast(
        midTaRegId: String,
        midLandRegId: String,
        tmFc: String,
        taDto: KmaMidTaItemDto?,
        landDto: KmaMidLandItemDto?,
    ): List<MidTermForecastRecord> {
        val baseDateStr = tmFc.take(8)
        val baseTimeStr = tmFc.substring(8, 12)
        val baseDatetime = formatDateTime(baseDateStr, baseTimeStr)
        val baseDate = LocalDate.parse(baseDateStr, DateTimeFormatter.ofPattern("yyyyMMdd"))

        val records = mutableListOf<MidTermForecastRecord>()

        for (day in 3..10) {
            val targetDate = baseDate.plusDays(day.toLong()).format(DateTimeFormatter.ISO_LOCAL_DATE)

            val minTemp = when (day) {
                3 -> taDto?.taMin3
                4 -> taDto?.taMin4
                5 -> taDto?.taMin5
                6 -> taDto?.taMin6
                7 -> taDto?.taMin7
                8 -> taDto?.taMin8
                9 -> taDto?.taMin9
                10 -> taDto?.taMin10
                else -> null
            }

            val maxTemp = when (day) {
                3 -> taDto?.taMax3
                4 -> taDto?.taMax4
                5 -> taDto?.taMax5
                6 -> taDto?.taMax6
                7 -> taDto?.taMax7
                8 -> taDto?.taMax8
                9 -> taDto?.taMax9
                10 -> taDto?.taMax10
                else -> null
            }

            val (wfAm, wfPm, popAm, popPm) = when (day) {
                3 -> Tuple4(landDto?.wf3Am, landDto?.wf3Pm, landDto?.rnSt3Am, landDto?.rnSt3Pm)
                4 -> Tuple4(landDto?.wf4Am, landDto?.wf4Pm, landDto?.rnSt4Am, landDto?.rnSt4Pm)
                5 -> Tuple4(landDto?.wf5Am, landDto?.wf5Pm, landDto?.rnSt5Am, landDto?.rnSt5Pm)
                6 -> Tuple4(landDto?.wf6Am, landDto?.wf6Pm, landDto?.rnSt6Am, landDto?.rnSt6Pm)
                7 -> Tuple4(landDto?.wf7Am, landDto?.wf7Pm, landDto?.rnSt7Am, landDto?.rnSt7Pm)
                8 -> Tuple4(landDto?.wf8, landDto?.wf8, landDto?.rnSt8, landDto?.rnSt8)
                9 -> Tuple4(landDto?.wf9, landDto?.wf9, landDto?.rnSt9, landDto?.rnSt9)
                10 -> Tuple4(landDto?.wf10, landDto?.wf10, landDto?.rnSt10, landDto?.rnSt10)
                else -> Tuple4(null, null, null, null)
            }

            records.add(
                MidTermForecastRecord(
                    midTaRegId = midTaRegId,
                    midLandRegId = midLandRegId,
                    providerCode = "KMA",
                    baseDatetime = baseDatetime,
                    fcstDate = targetDate,
                    minTemp = minTemp,
                    maxTemp = maxTemp,
                    wfAm = wfAm,
                    wfPm = wfPm,
                    popAm = popAm,
                    popPm = popPm,
                    version = 1,
                )
            )
        }

        return records
    }

    private data class Tuple4(val wfAm: String?, val wfPm: String?, val popAm: Int?, val popPm: Int?)

    private fun mapSky(skyCode: String?): String? = when (skyCode) {
        "1" -> "CLEAR"       // 맑음
        "3" -> "CLOUDY"      // 구름많음
        "4" -> "OVERCAST"    // 흐림
        else -> skyCode
    }

    private fun mapPty(ptyCode: String?): String? = when (ptyCode) {
        "0" -> "NONE"        // 없음
        "1" -> "RAIN"        // 비
        "2" -> "RAIN_SNOW"   // 비/눈
        "3" -> "SNOW"        // 눈
        "4" -> "SHOWER"      // 소나기
        else -> ptyCode
    }

    private fun formatDateTime(date: String, time: String): String {
        // date: YYYYMMDD, time: HHMM
        if (date.length == 8 && time.length >= 4) {
            val y = date.substring(0, 4)
            val m = date.substring(4, 6)
            val d = date.substring(6, 8)
            val h = time.substring(0, 2)
            val min = time.substring(2, 4)
            return "$y-$m-$d $h:$min:00"
        }
        return "$date $time"
    }
}
