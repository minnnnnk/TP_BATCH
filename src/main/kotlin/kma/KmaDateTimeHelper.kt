package kma

import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

/**
 * 기상청 단기 및 중기 예보 API 호출을 위한 최신 유효 발표 시각 계산 헬퍼
 */
object KmaDateTimeHelper {

    // 기상청 단기예보 발표 시각 (1일 8회, 각 시각 15분 이후 API 배포 완료)
    private val VILAGE_FCST_BASE_HOURS = intArrayOf(23, 20, 17, 14, 11, 8, 5, 2)

    /**
     * 현재 시각 기준 가장 최신의 유효한 단기예보 발표일자(YYYYMMDD)와 발표시각(HHMM) 반환
     */
    fun getLatestVilageBaseDateTime(now: LocalDateTime = LocalDateTime.now()): Pair<String, String> {
        val currentHour = now.hour
        val currentMinute = now.minute

        for (h in VILAGE_FCST_BASE_HOURS) {
            // 발표 시각 15분 이후부터 안정적으로 데이터 조회 가능
            if (currentHour > h || (currentHour == h && currentMinute >= 15)) {
                val baseDate = now.format(DateTimeFormatter.ofPattern("yyyyMMdd"))
                val baseTime = String.format("%02d00", h)
                return baseDate to baseTime
            }
        }

        // 새벽 02:15 이전인 경우 -> 전날 23:00 발표분 사용
        val yesterday = now.minusDays(1)
        val baseDate = yesterday.format(DateTimeFormatter.ofPattern("yyyyMMdd"))
        return baseDate to "2300"
    }

    /**
     * 현재 시각 기준 가장 최신의 유효한 중기예보 발표시각(tmFc: YYYYMMDDHH00) 반환
     * (기상청 중기예보는 매일 06:00, 18:00 2회 발표)
     */
    fun getLatestMidTermTmFc(now: LocalDateTime = LocalDateTime.now()): String {
        val currentHour = now.hour

        return when {
            currentHour >= 18 -> {
                val date = now.format(DateTimeFormatter.ofPattern("yyyyMMdd"))
                "${date}1800"
            }
            currentHour >= 6 -> {
                val date = now.format(DateTimeFormatter.ofPattern("yyyyMMdd"))
                "${date}0600"
            }
            else -> {
                // 새벽 06:00 이전인 경우 -> 전날 18:00 발표분 사용
                val yesterday = now.minusDays(1).format(DateTimeFormatter.ofPattern("yyyyMMdd"))
                "${yesterday}1800"
            }
        }
    }
}
