package kma

import db.DbConfig
import db.KmaRepository
import db.MidTermForecastTable
import db.ShortTermForecastTable
import org.jetbrains.exposed.v1.jdbc.selectAll
import org.jetbrains.exposed.v1.jdbc.transactions.transaction
import org.junit.jupiter.api.Test
import kotlin.test.assertTrue

class KmaDatabaseSaveIntegrationTest {

    @Test
    fun `test full pipeline - save regions, collect forecasts and save to DB`() {
        // 1. 전국 행정동 마스터 기본 데이터 DB 저장
        val initialRegions = SampleRegions.NATIONWIDE_REGIONS
        KmaRepository.saveRegions(initialRegions)

        // 2. DB에서 활성 행정동 조회
        val activeRegions = KmaRepository.getActiveRegions()
        assertTrue(activeRegions.isNotEmpty(), "Active regions must not be empty")
        println("📍 DB에서 조회된 활성 행정동: ${activeRegions.size}건")

        // 3. 기상청 예보 수집 (서울 및 부산 등 2개 지역으로 테스트 수집)
        val testRegions = activeRegions.take(2)
        val collector = KmaForecastCollector()
        val result = collector.collectAll(testRegions, intervalHours = 4)

        println("📊 수집된 단기예보: ${result.shortTermForecasts.size}건")
        println("📊 수집된 중기예보: ${result.midTermForecasts.size}건")

        // 4. DB에 단기 및 중기예보 Bulk Upsert 저장
        if (result.shortTermForecasts.isNotEmpty()) {
            KmaRepository.saveShortTermForecasts(result.shortTermForecasts)
        }
        if (result.midTermForecasts.isNotEmpty()) {
            KmaRepository.saveMidTermForecasts(result.midTermForecasts)
        }

        // 5. DB에 정상 적재되었는지 검증
        transaction(DbConfig.database) {
            val shortTermCount = ShortTermForecastTable.selectAll().count()
            val midTermCount = MidTermForecastTable.selectAll().count()
            println("🎉 DB 확인 완료 - short_term_forecast 건수: $shortTermCount, mid_term_forecast 건수: $midTermCount")
            assertTrue(shortTermCount > 0 || midTermCount > 0, "Forecast records should be saved in DB")
        }
    }
}
