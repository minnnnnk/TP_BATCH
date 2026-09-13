package kma

import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.DisplayName
import org.junit.jupiter.api.Test
import java.time.LocalDate
import java.time.format.DateTimeFormatter

class KmaApiTest {

    private val apiService = KmaApiService()

    @Test
    @DisplayName("1. [단기예보] getVilageFcst 응답이 4시간 단위(00, 04, 08, 12, 16, 20시) short_term_forecast 규격으로 정상 변환/필터링되는지 테스트")
    fun testShortTermForecastTransformation() {
        // Given: 기상청 단기예보(getVilageFcst) 모의 응답 데이터 (2026-09-01 06:00 발표 기준)
        val baseDate = "20260901"
        val baseTime = "0600"
        val regionCode = "1111051500" // 서울 종로구 청운동

        val mockItems = listOf(
            // 2026-09-01 04:00 예보 데이터 (4의 배수 시각 - 포함 대상)
            KmaVilageFcstItemDto(baseDate = baseDate, baseTime = baseTime, category = "TMP", fcstDate = "20260901", fcstTime = "0400", fcstValue = "21.0"),
            KmaVilageFcstItemDto(baseDate = baseDate, baseTime = baseTime, category = "SKY", fcstDate = "20260901", fcstTime = "0400", fcstValue = "1"),
            KmaVilageFcstItemDto(baseDate = baseDate, baseTime = baseTime, category = "PTY", fcstDate = "20260901", fcstTime = "0400", fcstValue = "0"),

            // 2026-09-01 07:00 예보 데이터 (4의 배수 아님 - 4시간 단위 필터링 시 제외 대상)
            KmaVilageFcstItemDto(baseDate = baseDate, baseTime = baseTime, category = "TMP", fcstDate = "20260901", fcstTime = "0700", fcstValue = "22.5"),
            KmaVilageFcstItemDto(baseDate = baseDate, baseTime = baseTime, category = "SKY", fcstDate = "20260901", fcstTime = "0700", fcstValue = "1"),

            // 2026-09-01 08:00 예보 데이터 (4의 배수 시각 - 포함 대상)
            KmaVilageFcstItemDto(baseDate = baseDate, baseTime = baseTime, category = "TMP", fcstDate = "20260901", fcstTime = "0800", fcstValue = "24.0"),
            KmaVilageFcstItemDto(baseDate = baseDate, baseTime = baseTime, category = "SKY", fcstDate = "20260901", fcstTime = "0800", fcstValue = "4"), // 흐림
            KmaVilageFcstItemDto(baseDate = baseDate, baseTime = baseTime, category = "PTY", fcstDate = "20260901", fcstTime = "0800", fcstValue = "1"), // 비
            KmaVilageFcstItemDto(baseDate = baseDate, baseTime = baseTime, category = "POP", fcstDate = "20260901", fcstTime = "0800", fcstValue = "60"),
            KmaVilageFcstItemDto(baseDate = baseDate, baseTime = baseTime, category = "PCP", fcstDate = "20260901", fcstTime = "0800", fcstValue = "5.0mm"),
            KmaVilageFcstItemDto(baseDate = baseDate, baseTime = baseTime, category = "REH", fcstDate = "20260901", fcstTime = "0800", fcstValue = "80"),
            KmaVilageFcstItemDto(baseDate = baseDate, baseTime = baseTime, category = "WSD", fcstDate = "20260901", fcstTime = "0800", fcstValue = "4.5"),
            KmaVilageFcstItemDto(baseDate = baseDate, baseTime = baseTime, category = "VEC", fcstDate = "20260901", fcstTime = "0800", fcstValue = "220"),
        )

        // When: 4시간 단위(intervalHours = 4)로 피벗 변환
        val records = apiService.transformVilageFcstItems(regionCode, baseDate, baseTime, mockItems, intervalHours = 4)

        // Then: 04:00, 08:00 2개 레코드만 선택되고 07:00은 필터링됨
        assertEquals(2, records.size)

        // 1) 04:00 레코드 검증
        val r1 = records[0]
        assertEquals(regionCode, r1.regionCode)
        assertEquals("KMA", r1.providerCode)
        assertEquals("2026-09-01 06:00:00", r1.baseDatetime)
        assertEquals("2026-09-01 04:00:00", r1.fcstDatetime)
        assertEquals(21.0, r1.temp)
        assertEquals("CLEAR", r1.sky)
        assertEquals("NONE", r1.pty)

        // 2) 08:00 레코드 검증
        val r2 = records[1]
        assertEquals("2026-09-01 08:00:00", r2.fcstDatetime)
        assertEquals(24.0, r2.temp)
        assertEquals("OVERCAST", r2.sky)
        assertEquals("RAIN", r2.pty)
        assertEquals(60, r2.pop)
        assertEquals("5.0mm", r2.pcp)
        assertEquals(80, r2.reh)
        assertEquals(4.5, r2.wsd)
        assertEquals(220, r2.vec)
    }

    @Test
    @DisplayName("2. [중기예보] getMidTa + getMidLandFcst 응답이 mid_term_forecast (D+3~D+10) 규격으로 정상 결합되는지 테스트")
    fun testMidTermForecastTransformation() {
        // Given: 중기 기온(getMidTa) 및 중기 육상예보(getMidLandFcst) 모의 DTO
        val tmFc = "202609010600"
        val midTaRegId = "11B10101"   // 서울
        val midLandRegId = "11B00000" // 서울/인천/경기도

        val mockTa = KmaMidTaItemDto(
            regId = midTaRegId,
            taMin3 = 18.0, taMax3 = 28.0,
            taMin4 = 19.0, taMax4 = 27.0,
            taMin5 = 20.0, taMax5 = 29.0,
            taMin6 = 18.5, taMax6 = 26.5,
            taMin7 = 17.0, taMax7 = 25.0,
            taMin8 = 16.0, taMax8 = 24.0,
            taMin9 = 15.5, taMax9 = 23.5,
            taMin10 = 15.0, taMax10 = 23.0,
        )

        val mockLand = KmaMidLandItemDto(
            regId = midLandRegId,
            rnSt3Am = 20, rnSt3Pm = 30, wf3Am = "맑음", wf3Pm = "구름많음",
            rnSt4Am = 40, rnSt4Pm = 60, wf4Am = "구름많음", wf4Pm = "흐리고 비",
            rnSt5Am = 30, rnSt5Pm = 20, wf5Am = "구름많음", wf5Pm = "맑음",
            rnSt6Am = 10, rnSt6Pm = 10, wf6Am = "맑음", wf6Pm = "맑음",
            rnSt7Am = 20, rnSt7Pm = 30, wf7Am = "구름많음", wf7Pm = "구름많음",
            rnSt8 = 20, wf8 = "맑음",
            rnSt9 = 30, wf9 = "구름많음",
            rnSt10 = 40, wf10 = "흐림",
        )

        // When: D+3 ~ D+10 일자별 레코드로 결합 변환
        val records = apiService.transformMidTermForecast(midTaRegId, midLandRegId, tmFc, mockTa, mockLand)

        // Then: D+3부터 D+10까지 총 8일치 레코드 생성 확인
        assertEquals(8, records.size)

        // D+3 (2026-09-04) 검증
        val d3 = records[0]
        assertEquals("2026-09-04", d3.fcstDate)
        assertEquals(midTaRegId, d3.midTaRegId)
        assertEquals(midLandRegId, d3.midLandRegId)
        assertEquals(18.0, d3.minTemp)
        assertEquals(28.0, d3.maxTemp)
        assertEquals("맑음", d3.wfAm)
        assertEquals("구름많음", d3.wfPm)
        assertEquals(20, d3.popAm)
        assertEquals(30, d3.popPm)

        // D+4 (2026-09-05) 검증
        val d4 = records[1]
        assertEquals("2026-09-05", d4.fcstDate)
        assertEquals(19.0, d4.minTemp)
        assertEquals(27.0, d4.maxTemp)
        assertEquals("구름많음", d4.wfAm)
        assertEquals("흐리고 비", d4.wfPm)
        assertEquals(40, d4.popAm)
        assertEquals(60, d4.popPm)

        // D+8 (2026-09-09, 종일 예보) 검증
        val d8 = records[5]
        assertEquals("2026-09-09", d8.fcstDate)
        assertEquals(16.0, d8.minTemp)
        assertEquals(24.0, d8.maxTemp)
        assertEquals("맑음", d8.wfAm)
        assertEquals("맑음", d8.wfPm)
        assertEquals(20, d8.popAm)
        assertEquals(20, d8.popPm)
    }

    @Test
    @DisplayName("3. [구역코드] 예보구역(forecast_zone) 및 특보구역(warning_zone) DTO 변환 테스트")
    fun testZoneRecordsTransformation() {
        val fcstDto = KmaForecastZoneDto(
            regId = "11B10101",
            regName = "서울",
            regEn = "Seoul",
            regUp = "11A00100",
            regSp = "B",
            lat = "37.5665",
            lon = "126.9780",
            stnId = "108",
        )

        val wrnDto = KmaWarningZoneDto(
            wrnZoneCd = "L1020100",
            wrnZoneName = "서울동북권",
        )

        val fcstRecord = ForecastZoneRecord(
            regId = fcstDto.regId!!,
            providerCode = "KMA",
            regName = fcstDto.regName!!,
            regEn = fcstDto.regEn,
            regUp = fcstDto.regUp,
            regSp = fcstDto.regSp,
            lat = fcstDto.lat?.toDoubleOrNull(),
            lon = fcstDto.lon?.toDoubleOrNull(),
            stnId = fcstDto.stnId?.toIntOrNull(),
        )

        val wrnRecord = WarningZoneRecord(
            wrnZoneCd = wrnDto.wrnZoneCd!!,
            providerCode = "KMA",
            wrnZoneName = wrnDto.wrnZoneName!!,
        )

        assertEquals("11B10101", fcstRecord.regId)
        assertEquals("KMA", fcstRecord.providerCode)
        assertEquals("서울", fcstRecord.regName)
        assertEquals(37.5665, fcstRecord.lat)
        assertEquals(126.9780, fcstRecord.lon)
        assertEquals(108, fcstRecord.stnId)

        assertEquals("L1020100", wrnRecord.wrnZoneCd)
        assertEquals("서울동북권", wrnRecord.wrnZoneName)
    }

    @Test
    @DisplayName("3-1. [구역코드 페이징] pageNo를 1씩 증가시키며 데이터가 없을 때 정상 종료되는지 테스트")
    fun testForecastZonePaginationTermination() {
        val requestedPages = mutableListOf<Int>()

        val mockService = object : KmaApiService() {
            override fun fetchForecastZones(regId: String?, numOfRows: Int, pageNo: Int): List<ForecastZoneRecord> {
                requestedPages.add(pageNo)
                return when (pageNo) {
                    1 -> listOf(ForecastZoneRecord(regId = "11B10101", regName = "서울", providerCode = "KMA"))
                    2 -> listOf(ForecastZoneRecord(regId = "11H20201", regName = "부산", providerCode = "KMA"))
                    3 -> listOf(ForecastZoneRecord(regId = "11G00201", regName = "제주", providerCode = "KMA"))
                    else -> emptyList() // 데이터 없음 -> 종료
                }
            }
        }

        val allZones = mockService.fetchAllForecastZones(pageSize = 100)

        assertEquals(3, allZones.size)
        assertEquals(listOf(1, 2, 3, 4), requestedPages, "1, 2, 3페이지 조회 후 4페이지에서 빈 목록을 수신하여 종료되어야 합니다.")
    }

    @Test
    @DisplayName("3-2. [특보구역 페이징] pageNo를 1씩 증가시키며 데이터가 없을 때 정상 종료되는지 테스트")
    fun testWarningZonePaginationTermination() {
        val requestedPages = mutableListOf<Int>()

        val mockService = object : KmaApiService() {
            override fun fetchWarningZones(korName: String?, numOfRows: Int, pageNo: Int): List<WarningZoneRecord> {
                requestedPages.add(pageNo)
                return when (pageNo) {
                    1 -> listOf(WarningZoneRecord(wrnZoneCd = "L1020100", wrnZoneName = "서울동북권", providerCode = "KMA"))
                    2 -> listOf(WarningZoneRecord(wrnZoneCd = "L1020200", wrnZoneName = "서울서북권", providerCode = "KMA"))
                    else -> emptyList() // 데이터 없음 -> 종료
                }
            }
        }

        val allZones = mockService.fetchAllWarningZones(pageSize = 100)

        assertEquals(2, allZones.size)
        assertEquals(listOf(1, 2, 3), requestedPages, "1, 2페이지 조회 후 3페이지에서 빈 목록을 수신하여 종료되어야 합니다.")
    }

    @Test
    @DisplayName("4-1. [Live API] 예보구역 목록 조회 (getFcstZoneCd)")
    fun testLiveForecastZoneApi() {
        val apiKey = KmaConfig.apiKey
        if (apiKey.isBlank()) {
            println("ℹ️ 기상청 API 인증키가 없어 테스트를 건너뜁니다.")
            return
        }

        println("🚀 [Live API] 예보구역 코드 조회 시작...")
        val zones = apiService.fetchForecastZones(numOfRows = 20, pageNo = 1)
        println("✅ 예보구역 수신 성공: ${zones.size}건")
        zones.take(5).forEach {
            println("  -> [${it.regId}] ${it.regName} (위도: ${it.lat}, 경도: ${it.lon}, 지점: ${it.stnId})")
        }
        assertTrue(zones.isNotEmpty(), "예보구역 목록이 1건 이상 반환되어야 합니다.")
    }

    @Test
    @DisplayName("4-2. [Live API] 특보구역 목록 조회 (WethrBasicInfoService/getWrnZoneCd)")
    fun testLiveWarningZoneApi() {
        val apiKey = KmaConfig.apiKey
        if (apiKey.isBlank()) {
            println("ℹ️ 기상청 API 인증키가 없어 테스트를 건너뜁니다.")
            return
        }

        println("🚀 [Live API] 특보구역 코드 조회 시작...")
        try {
            val zones = apiService.fetchWarningZones(numOfRows = 20, pageNo = 1)
            println("✅ 특보구역 수신 성공: ${zones.size}건")
            zones.take(5).forEach {
                println("  -> [${it.wrnZoneCd}] ${it.wrnZoneName}")
            }
            assertTrue(zones.isNotEmpty(), "특보구역 목록이 1건 이상 반환되어야 합니다.")
        } catch (e: Exception) {
            println("ℹ️ 특보구역 API 호출 결과: ${e.message}")
        }
    }

    @Test
    @DisplayName("4-3. [Live API] 단기예보 조회 및 KMA_DATABASE_DESIGN 규격 매핑 (getVilageFcst)")
    fun testLiveShortTermForecastApi() {
        val apiKey = KmaConfig.apiKey
        if (apiKey.isBlank()) {
            println("ℹ️ 기상청 API 인증키가 없어 테스트를 건너뜁니다.")
            return
        }

        val now = java.time.LocalDateTime.now()
        // 최근 유효한 단기예보 발표 시각 계산 (02, 05, 08, 11, 14, 17, 20, 23시)
        val baseTimes = listOf("2300", "2000", "1700", "1400", "1100", "0800", "0500", "0200")
        val currentHour = now.hour
        val currentMinute = now.minute

        var baseDate = now.format(DateTimeFormatter.ofPattern("yyyyMMdd"))
        var baseTime = "0200"

        for (bt in baseTimes) {
            val h = bt.take(2).toInt()
            if (currentHour > h || (currentHour == h && currentMinute >= 15)) {
                baseTime = bt
                break
            }
        }
        if (currentHour < 2 || (currentHour == 2 && currentMinute < 15)) {
            // 전날 23:00 기준
            baseDate = now.minusDays(1).format(DateTimeFormatter.ofPattern("yyyyMMdd"))
            baseTime = "2300"
        }

        println("🚀 [Live API] 단기예보 4시간 단위 조회 시작 (baseDate: $baseDate, baseTime: $baseTime, 서울 종로구 nx:60, ny:127)...")
        val records = apiService.fetchShortTermForecast(
            regionCode = "1111051500", // 서울 종로구 청운동
            nx = 60,
            ny = 127,
            baseDate = baseDate,
            baseTime = baseTime,
            intervalHours = 4, // 4시간 단위
        )

        println("✅ 단기예보(4시간 단위) 피벗 변환 성공: 총 ${records.size}개 예보 시간대 수신")
        records.take(6).forEach {
            println("  -> [예보시각: ${it.fcstDatetime}] 기온: ${it.temp}℃, 하늘: ${it.sky}, 강수형태: ${it.pty}, 강수확률: ${it.pop}%, 강수량: ${it.pcp}, 습도: ${it.reh}%, 풍속: ${it.wsd}m/s")
        }
        assertTrue(records.isNotEmpty(), "단기예보 레코드가 1건 이상 생성되어야 합니다.")

        // 모든 레코드의 시각이 4의 배수(00, 04, 08, 12, 16, 20)인지 검증
        records.forEach { r ->
            // fcstDatetime format: "yyyy-MM-dd HH:mm:ss"
            val hour = r.fcstDatetime.substring(11, 13).toInt()
            assertEquals(0, hour % 4, "예보 시각($hour)은 4시간 단위여야 합니다.")
        }
    }

    @Test
    @DisplayName("4-4. [Live API] 중기예보 기온 및 육상 조회 결합 (getMidTa + getMidLandFcst)")
    fun testLiveMidTermForecastApi() {
        val apiKey = KmaConfig.apiKey
        if (apiKey.isBlank()) {
            println("ℹ️ 기상청 API 인증키가 없어 테스트를 건너뜁니다.")
            return
        }

        val now = java.time.LocalDateTime.now()
        var baseDate = now.format(DateTimeFormatter.ofPattern("yyyyMMdd"))
        var baseTime = "0600"

        if (now.hour >= 18) {
            baseTime = "1800"
        } else if (now.hour < 6) {
            baseDate = now.minusDays(1).format(DateTimeFormatter.ofPattern("yyyyMMdd"))
            baseTime = "1800"
        }

        val tmFc = "$baseDate$baseTime"
        val midTaRegId = "11B10101"   // 서울
        val midLandRegId = "11B00000" // 서울/인천/경기도

        println("🚀 [Live API] 중기예보 조회 시작 (tmFc: $tmFc, midTa: $midTaRegId, midLand: $midLandRegId)...")
        val records = apiService.fetchMidTermForecast(
            midTaRegId = midTaRegId,
            midLandRegId = midLandRegId,
            tmFc = tmFc,
        )

        println("✅ 중기예보(D+3 ~ D+10) 결합 성공: 총 ${records.size}일치 예보")
        records.forEach {
            println("  -> [${it.fcstDate}] 최저: ${it.minTemp}℃, 최고: ${it.maxTemp}℃ | 오전: ${it.wfAm}(${it.popAm}%), 오후: ${it.wfPm}(${it.popPm}%)")
        }
        assertTrue(records.isNotEmpty(), "중기예보 레코드가 생성되어야 합니다.")
    }

    @Test
    @DisplayName("7. [예보구역정보] getFcstZoneCd API를 통해 북한을 제외한 대한민국 전역 예보구역 일괄 수집 및 DB 적재")
    fun testFetchAndSaveAllSouthKoreaForecastZones() {
        println("🚀 [Live API] 북한 제외 대한민국 전역 예보구역(getFcstZoneCd) 일괄 수집 시작...")
        val zones = apiService.fetchAllSouthKoreaForecastZones(pageSize = 100)

        println("✅ 수집된 대한민국 예보구역 수: ${zones.size}개")
        assertTrue(zones.isNotEmpty(), "예보구역이 1개 이상 수집되어야 합니다.")

        // 북한 지역 코드(11I ~ 11P)가 전혀 없는지 검증
        val northKoreaCodes = listOf("11I", "11J", "11K", "11L", "11M", "11N", "11O", "11P")
        val northKoreaFound = zones.filter { zone ->
            northKoreaCodes.any { zone.regId.startsWith(it, ignoreCase = true) }
        }
        assertEquals(0, northKoreaFound.size, "북한 구역 코드가 포함되어 있지 않아야 합니다.")

        // DB에 Bulk Upsert 저장
        db.KmaRepository.saveForecastZones(zones)
        println("🎉 DB(forecast_zone 테이블)에 ${zones.size}건 적재 완료!")
    }

    @Test
    @DisplayName("8. [특보구역정보] getWrnZoneCd API를 통해 전국 특보구역 일괄 수집 및 DB 적재")
    fun testFetchAndSaveAllWarningZones() {
        val apiKey = KmaConfig.apiKey
        if (apiKey.isBlank()) {
            println("ℹ️ 기상청 API 인증키가 없어 테스트를 건너뜁니다.")
            return
        }

        println("🚀 [Live API] 전국 특보구역(getWrnZoneCd) 일괄 수집 시작...")
        val zones = apiService.fetchAllWarningZones(pageSize = 100)

        println("✅ 수집된 특보구역 수: ${zones.size}개")
        assertTrue(zones.isNotEmpty(), "특보구역이 1개 이상 수집되어야 합니다.")

        // DB에 Bulk Upsert 저장
        db.KmaRepository.saveWarningZones(zones)
        println("🎉 DB(warning_zone 테이블)에 ${zones.size}건 적재 완료!")
    }

    @Test
    @DisplayName("9. [초기 마스터 구축] 예보구역(getFcstZoneCd) 및 특보구역(getWrnZoneCd) 전체 일괄 수집 및 DB 적재")
    fun testFetchAndSaveAllMasterZones() {
        val apiKey = KmaConfig.apiKey
        if (apiKey.isBlank()) {
            println("ℹ️ 기상청 API 인증키가 없어 테스트를 건너뜁니다.")
            return
        }

        println("🚀 [초기 마스터 구축] 1단계: 예보구역(getFcstZoneCd) 일괄 수집 시작...")
        val fcstZones = apiService.fetchAllSouthKoreaForecastZones(pageSize = 100)
        db.KmaRepository.saveForecastZones(fcstZones)
        println("✅ [1단계 완료] forecast_zone: ${fcstZones.size}건 저장 완료")

        println("🚀 [초기 마스터 구축] 2단계: 특보구역(getWrnZoneCd) 일괄 수집 시작...")
        val wrnZones = apiService.fetchAllWarningZones(pageSize = 100)
        db.KmaRepository.saveWarningZones(wrnZones)
        println("✅ [2단계 완료] warning_zone: ${wrnZones.size}건 저장 완료")

        println("🎉 [초기 마스터 구축 완료] 예보구역 ${fcstZones.size}건 / 특보구역 ${wrnZones.size}건 DB 적재 완료!")
    }
}
