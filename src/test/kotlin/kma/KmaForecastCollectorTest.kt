package kma

import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.DisplayName
import org.junit.jupiter.api.Test
import java.time.LocalDateTime

class KmaForecastCollectorTest {

    // 테스트용 모의 KmaApiService (20개 4시간 단위 시점 모의 반환)
    private val mockApiService = object : KmaApiService() {
        override fun fetchShortTermForecast(
            regionCode: String,
            nx: Int,
            ny: Int,
            baseDate: String,
            baseTime: String,
            numOfRows: Int,
            intervalHours: Int,
        ): List<ShortTermForecastRecord> {
            val records = mutableListOf<ShortTermForecastRecord>()
            val hours = listOf("0000", "0400", "0800", "1200", "1600", "2000")
            val dates = listOf("20260901", "20260902", "20260903", "20260904")

            for (d in dates) {
                for (h in hours) {
                    if (records.size < 20) {
                        records.add(
                            ShortTermForecastRecord(
                                regionCode = regionCode,
                                providerCode = "KMA",
                                baseDatetime = "2026-09-01 20:00:00",
                                fcstDatetime = "${d.substring(0, 4)}-${d.substring(4, 6)}-${d.substring(6, 8)} ${h.substring(0, 2)}:00:00",
                                temp = 22.0,
                                sky = "CLEAR",
                                pty = "NONE",
                                pop = 10,
                                pcp = "강수없음",
                                reh = 60,
                                wsd = 2.5,
                                vec = 180,
                            )
                        )
                    }
                }
            }
            return records
        }

        override fun fetchMidTermForecast(
            midTaRegId: String,
            midLandRegId: String,
            tmFc: String,
        ): List<MidTermForecastRecord> {
            return (3..10).map { day ->
                MidTermForecastRecord(
                    midTaRegId = midTaRegId,
                    midLandRegId = midLandRegId,
                    providerCode = "KMA",
                    baseDatetime = "2026-09-01 18:00:00",
                    fcstDate = "2026-09-0$day",
                    minTemp = 20.0,
                    maxTemp = 28.0,
                    wfAm = "맑음",
                    wfPm = "구름많음",
                    popAm = 10,
                    popPm = 20,
                )
            }
        }
    }

    private val collector = KmaForecastCollector(apiService = mockApiService)

    @Test
    @DisplayName("1. [DateTime 헬퍼] 단기/중기 예보 최신 유효 발표시각 계산 테스트")
    fun testDateTimeHelper() {
        // 단기예보 21:00 시점 -> 당일 20:00 발표
        val t1 = LocalDateTime.of(2026, 9, 1, 21, 0)
        val (d1, b1) = KmaDateTimeHelper.getLatestVilageBaseDateTime(t1)
        assertEquals("20260901", d1)
        assertEquals("2000", b1)

        // 단기예보 02:10 시점 (02:15 이전) -> 전날 23:00 발표
        val t2 = LocalDateTime.of(2026, 9, 2, 2, 10)
        val (d2, b2) = KmaDateTimeHelper.getLatestVilageBaseDateTime(t2)
        assertEquals("20260901", d2)
        assertEquals("2300", b2)

        // 중기예보 19:30 시점 -> 당일 18:00 발표
        val tmFc1 = KmaDateTimeHelper.getLatestMidTermTmFc(t1)
        assertEquals("202609011800", tmFc1)

        // 중기예보 05:00 시점 -> 전날 18:00 발표
        val tmFc2 = KmaDateTimeHelper.getLatestMidTermTmFc(t2)
        assertEquals("202609011800", tmFc2)
    }

    @Test
    @DisplayName("2. [단기예보 최적화] 동일 격자(nx, ny) 공유 행정동에 대한 중복 호출 방지 및 매핑 테스트")
    fun testGridOptimizationMapping() {
        // Given: 서울 종로구 내 동일 격자(nx: 60, ny: 127)를 공유하는 3개 행정동
        val targetRegions = listOf(
            RegionLocationRecord(regionCode = "1111051500", sido = "서울특별시", sigungu = "종로구", eupmyeondong = "청운동", nx = 60, ny = 127, midTaRegId = "11B10101", midLandRegId = "11B00000"),
            RegionLocationRecord(regionCode = "1111053000", sido = "서울특별시", sigungu = "종로구", eupmyeondong = "사직동", nx = 60, ny = 127, midTaRegId = "11B10101", midLandRegId = "11B00000"),
            RegionLocationRecord(regionCode = "1111054000", sido = "서울특별시", sigungu = "종로구", eupmyeondong = "삼청동", nx = 60, ny = 127, midTaRegId = "11B10101", midLandRegId = "11B00000"),
        )

        // When: 4시간 단위 단기예보 수집 실행
        val records = collector.collectShortTermForecasts(
            regions = targetRegions,
            intervalHours = 4,
            baseDate = "20260901",
            baseTime = "2000",
        )

        // Then: 3개 행정동 모두에게 각각의 regionCode가 매핑된 레코드 생성 확인
        val byRegion = records.groupBy { it.regionCode }
        assertEquals(3, byRegion.keys.size, "3개 행정동 모두에 대해 예보 레코드가 매핑되어야 합니다.")
        assertTrue(byRegion.containsKey("1111051500"))
        assertTrue(byRegion.containsKey("1111053000"))
        assertTrue(byRegion.containsKey("1111054000"))

        // 각 행정동마다 4시간 단위(20개 시점)의 예보 데이터가 생성되었는지 확인
        val count1 = byRegion["1111051500"]!!.size
        val count2 = byRegion["1111053000"]!!.size
        val count3 = byRegion["1111054000"]!!.size
        assertEquals(count1, count2)
        assertEquals(count2, count3)
        assertEquals(20, count1)

        // 모든 레코드의 시각이 4의 배수인지 검증
        records.forEach { r ->
            val hour = r.fcstDatetime.substring(11, 13).toInt()
            assertEquals(0, hour % 4)
        }
    }

    @Test
    @DisplayName("3. [전국 일괄 수집] 주요 거점 행정동(서울, 부산, 제주) 대상 일괄 수집 및 DB 적재 준비 검증")
    fun testCollectAllNationwideSample() {
        val sampleTargets = listOf(
            SampleRegions.NATIONWIDE_REGIONS.first { it.sido == "서울특별시" }, // 서울 종로
            SampleRegions.NATIONWIDE_REGIONS.first { it.sido == "부산광역시" }, // 부산 해운대
            SampleRegions.NATIONWIDE_REGIONS.first { it.sido == "제주특별자치도" }, // 제주 일도1동
        )

        val result = collector.collectAll(sampleTargets, intervalHours = 4)

        println("📊 [전국 수집 결과]")
        println("  - 대상 행정동 수: ${result.totalTargetRegions}개")
        println("  - 고유 격자 수 (API 단기 호출 수): ${result.uniqueGridsCount}개")
        println("  - 고유 중기 구역 수 (API 중기 호출 수): ${result.uniqueMidZonesCount}개")
        println("  - 생성된 단기예보 DB 레코드 수: ${result.shortTermForecasts.size}건 (지역당 ${result.shortTermForecasts.size / result.totalTargetRegions}건)")
        println("  - 생성된 중기예보 DB 레코드 수: ${result.midTermForecasts.size}건 (구역당 ${result.midTermForecasts.size / result.uniqueMidZonesCount}건)")

        assertEquals(3, result.totalTargetRegions)
        assertEquals(3, result.uniqueGridsCount)
        assertEquals(3, result.uniqueMidZonesCount)
        assertEquals(60, result.shortTermForecasts.size) // 3개 지역 x 20개 시점 = 60건
        assertEquals(24, result.midTermForecasts.size) // 3개 구역 x 8일(D+3~D+10) = 24건
    }
}
