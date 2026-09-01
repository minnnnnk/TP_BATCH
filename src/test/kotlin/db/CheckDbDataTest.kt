package db

import org.jetbrains.exposed.v1.jdbc.selectAll
import org.jetbrains.exposed.v1.jdbc.transactions.transaction
import org.junit.jupiter.api.Test

class CheckDbDataTest {

    @Test
    fun `inspect current db state`() {
        transaction(DbConfig.database) {
            val providerCount = WeatherProviderTable.selectAll().count()
            val regionCount = RegionLocationTable.selectAll().count()
            val shortTermCount = ShortTermForecastTable.selectAll().count()
            val midTermCount = MidTermForecastTable.selectAll().count()

            println("=== DB 현황 통계 ===")
            println("1. weather_provider: $providerCount 건")
            println("2. region_location: $regionCount 건")
            println("3. short_term_forecast: $shortTermCount 건")
            println("4. mid_term_forecast: $midTermCount 건")

            println("\n=== 등록된 행정동 예시 (최대 5건) ===")
            RegionLocationTable.selectAll().limit(5).forEach { row ->
                println(" - [${row[RegionLocationTable.regionCode]}] ${row[RegionLocationTable.sido]} ${row[RegionLocationTable.sigungu]} ${row[RegionLocationTable.eupmyeondong]} (nx: ${row[RegionLocationTable.nx]}, ny: ${row[RegionLocationTable.ny]})")
            }

            println("\n=== 단기예보 예시 (최대 3건) ===")
            ShortTermForecastTable.selectAll().limit(3).forEach { row ->
                println(" - [${row[ShortTermForecastTable.regionCode]}] 예보시각: ${row[ShortTermForecastTable.fcstDatetime]}, 기온: ${row[ShortTermForecastTable.temp]}℃, 하늘: ${row[ShortTermForecastTable.sky]}, 강수: ${row[ShortTermForecastTable.pty]}, 강수확률: ${row[ShortTermForecastTable.pop]}%")
            }

            println("\n=== 중기예보 예시 (최대 3건) ===")
            MidTermForecastTable.selectAll().limit(3).forEach { row ->
                println(" - [${row[MidTermForecastTable.midTaRegId]}] 날짜: ${row[MidTermForecastTable.fcstDate]}, 최저/최고: ${row[MidTermForecastTable.minTemp]}℃ / ${row[MidTermForecastTable.maxTemp]}℃, 날씨(오전/오후): ${row[MidTermForecastTable.wfAm]} / ${row[MidTermForecastTable.wfPm]}")
            }
        }
    }
}
