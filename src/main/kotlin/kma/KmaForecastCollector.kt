package kma

import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service

/**
 * 수집 결과 컨테이너 (DB Bulk Insert/Upsert 대상 데이터 및 통계)
 */
data class KmaBatchCollectionResult(
    val shortTermForecasts: List<ShortTermForecastRecord>,
    val midTermForecasts: List<MidTermForecastRecord>,
    val totalTargetRegions: Int,
    val uniqueGridsCount: Int,
    val uniqueMidZonesCount: Int,
    val baseDate: String,
    val baseTime: String,
    val tmFc: String,
)

/**
 * 전국 행정동별 기상청 단기/중기 예보 일괄 수집기
 *
 * - 격자 좌표 (nx, ny) 중복 호출 방지 최적화
 * - 중기 예보구역 (midTaRegId, midLandRegId) 중복 호출 방지 최적화
 * - 단기예보 4시간 단위 필터링 적용
 * - 수집된 레코드는 DB(short_term_forecast, mid_term_forecast)에 Bulk Upsert 가능한 규격으로 반환
 */
@Service
class KmaForecastCollector(
    private val apiService: KmaApiService = KmaApiService(),
) {
    private val log = LoggerFactory.getLogger(KmaForecastCollector::class.java)

    /**
     * 전국 대상 지역의 단기 및 중기 예보 전체 수집
     */
    fun collectAll(
        targetRegions: List<RegionLocationRecord>,
        intervalHours: Int = 4,
    ): KmaBatchCollectionResult {
        val (baseDate, baseTime) = KmaDateTimeHelper.getLatestVilageBaseDateTime()
        val tmFc = KmaDateTimeHelper.getLatestMidTermTmFc()

        val activeRegions = targetRegions.filter { it.isActive }
        log.info("🚀 전국 기상 예보 수집 시작 - 대상 행정동: {}건 (단기 발표: {} {}, 중기 발표: {})",
            activeRegions.size, baseDate, baseTime, tmFc)

        val shortTermRecords = collectShortTermForecasts(activeRegions, intervalHours, baseDate, baseTime)
        val midTermRecords = collectMidTermForecasts(activeRegions, tmFc)

        val uniqueGrids = activeRegions.map { it.nx to it.ny }.toSet().size
        val uniqueMidZones = activeRegions.map { it.midTaRegId to it.midLandRegId }.toSet().size

        log.info("✅ 전국 기상 예보 수집 완료 - 단기 레코드: {}건, 중기 레코드: {}건",
            shortTermRecords.size, midTermRecords.size)

        return KmaBatchCollectionResult(
            shortTermForecasts = shortTermRecords,
            midTermForecasts = midTermRecords,
            totalTargetRegions = activeRegions.size,
            uniqueGridsCount = uniqueGrids,
            uniqueMidZonesCount = uniqueMidZones,
            baseDate = baseDate,
            baseTime = baseTime,
            tmFc = tmFc,
        )
    }

    /**
     * 1) 단기예보 수집 (격자 좌표 nx, ny 단위 최적화 호출)
     *
     * 동일한 (nx, ny)를 갖는 여러 행정동은 API를 1회만 호출하고,
     * 응답 레코드들을 각 행정동의 regionCode로 복제/매핑합니다.
     */
    fun collectShortTermForecasts(
        regions: List<RegionLocationRecord>,
        intervalHours: Int = 4,
        baseDate: String? = null,
        baseTime: String? = null,
    ): List<ShortTermForecastRecord> {
        val (resolvedDate, resolvedTime) = if (baseDate != null && baseTime != null) {
            baseDate to baseTime
        } else {
            KmaDateTimeHelper.getLatestVilageBaseDateTime()
        }

        // 고유 격자 (nx, ny) 별로 그룹핑
        val gridGroups = regions.groupBy { it.nx to it.ny }
        val result = mutableListOf<ShortTermForecastRecord>()

        log.info("📍 단기예보 수집: 총 {}개 행정동 -> {}개 고유 격자로 압축 호출", regions.size, gridGroups.size)

        for ((grid, regionList) in gridGroups) {
            val (nx, ny) = grid
            try {
                // 격자 기준 대표 호출 (dummy regionCode 사용 후 아래에서 각 행정동으로 매핑)
                val baseRecords = apiService.fetchShortTermForecast(
                    regionCode = "",
                    nx = nx,
                    ny = ny,
                    baseDate = resolvedDate,
                    baseTime = resolvedTime,
                    intervalHours = intervalHours,
                )

                // 해당 격자를 공유하는 모든 행정동별로 레코드 생성
                for (region in regionList) {
                    for (rec in baseRecords) {
                        result.add(rec.copy(regionCode = region.regionCode))
                    }
                }
            } catch (e: Exception) {
                log.warn("⚠️ 단기예보 조회 실패 (nx: {}, ny: {}, 속한 행정동 {}개): {}",
                    nx, ny, regionList.size, e.message)
            }
        }

        return result
    }

    /**
     * 2) 중기예보 수집 (중기 구역 midTaRegId, midLandRegId 단위 최적화 호출)
     *
     * 동일한 중기 구역을 갖는 여러 행정동은 API를 1회만 호출하여
     * 중기예보 테이블(mid_term_forecast)에 저장할 레코드를 생성합니다.
     */
    fun collectMidTermForecasts(
        regions: List<RegionLocationRecord>,
        tmFc: String? = null,
    ): List<MidTermForecastRecord> {
        val resolvedTmFc = tmFc ?: KmaDateTimeHelper.getLatestMidTermTmFc()

        // 고유 중기 구역 (midTaRegId, midLandRegId) 별로 그룹핑
        val zoneGroups = regions.groupBy { it.midTaRegId to it.midLandRegId }
        val result = mutableListOf<MidTermForecastRecord>()

        log.info("📍 중기예보 수집: 총 {}개 행정동 -> {}개 고유 중기 구역으로 압축 호출", regions.size, zoneGroups.size)

        for ((zone, _) in zoneGroups) {
            val (midTaRegId, midLandRegId) = zone
            try {
                val records = apiService.fetchMidTermForecast(
                    midTaRegId = midTaRegId,
                    midLandRegId = midLandRegId,
                    tmFc = resolvedTmFc,
                )
                result.addAll(records)
            } catch (e: Exception) {
                log.warn("⚠️ 중기예보 조회 실패 (midTa: {}, midLand: {}): {}",
                    midTaRegId, midLandRegId, e.message)
            }
        }

        return result
    }
}
