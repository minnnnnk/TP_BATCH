package batch

import db.KmaRepository
import kma.KmaForecastCollector
import kma.SampleRegions
import org.slf4j.LoggerFactory
import org.springframework.batch.core.Job
import org.springframework.batch.core.Step
import org.springframework.batch.core.job.builder.JobBuilder
import org.springframework.batch.core.repository.JobRepository
import org.springframework.batch.core.step.builder.StepBuilder
import org.springframework.batch.core.step.tasklet.Tasklet
import org.springframework.batch.repeat.RepeatStatus
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.transaction.PlatformTransactionManager

@Configuration
class KmaWeatherJobConfig(
    private val kmaForecastCollector: KmaForecastCollector,
) {
    private val log = LoggerFactory.getLogger(KmaWeatherJobConfig::class.java)

    /**
     * 기상청 예보 수집 배치 Job
     * 1단계: 단기예보 전수 수집 및 DB 적재 (완료 후) -> 2단계: 중기예보 전수 수집 및 DB 적재 순차 실행
     */
    @Bean
    fun kmaWeatherJob(
        jobRepository: JobRepository,
        shortTermForecastStep: Step,
        midTermForecastStep: Step,
    ): Job = JobBuilder("kmaWeatherJob", jobRepository)
        .start(shortTermForecastStep)
        .next(midTermForecastStep)
        .build()

    /**
     * 1단계 Step: 단기예보 전수 수집 및 DB 적재 (short_term_forecast)
     */
    @Bean
    fun shortTermForecastStep(
        jobRepository: JobRepository,
        transactionManager: PlatformTransactionManager,
    ): Step = StepBuilder("shortTermForecastStep", jobRepository)
        .tasklet(shortTermForecastTasklet(), transactionManager)
        .build()

    @Bean
    fun shortTermForecastTasklet(): Tasklet = Tasklet { _, _ ->
        log.info("🚀 [Step 1: 단기예보] 전국 행정동 단기예보 일괄 수집 및 DB 적재 시작")

        // 1. 등록된 활성 행정동 조회 (없을 경우 기본 전국 대표 샘플 등록)
        var activeRegions = KmaRepository.getActiveRegions()
        if (activeRegions.isEmpty()) {
            log.info("ℹ️ DB에 등록된 행정동이 없어 전국 대표 행정동 17개소를 초기 등록합니다.")
            KmaRepository.saveRegions(SampleRegions.NATIONWIDE_REGIONS)
            activeRegions = KmaRepository.getActiveRegions()
        }

        log.info("📍 [Step 1] 대상 행정동: {}건 (4시간 단위 페이징 수집)", activeRegions.size)

        // 2. 단기예보 4시간 단위(00, 04, 08, 12, 16, 20시) & 페이징(numOfRows, pageNo) 수집
        val shortTermRecords = kmaForecastCollector.collectShortTermForecasts(
            regions = activeRegions,
            intervalHours = 4
        )

        // 3. 단기예보 테이블(short_term_forecast)에 Bulk Upsert
        if (shortTermRecords.isNotEmpty()) {
            KmaRepository.saveShortTermForecasts(shortTermRecords)
            log.info("✅ [Step 1: 단기예보 완료] 총 {}건 DB(short_term_forecast) 적재 완료", shortTermRecords.size)
        } else {
            log.warn("⚠️ [Step 1: 단기예보] 수집된 단기예보 레코드가 없습니다.")
        }

        RepeatStatus.FINISHED
    }

    /**
     * 2단계 Step: 중기예보 전수 수집 및 DB 적재 (mid_term_forecast)
     * (단기예보 적재가 100% 완료된 후 실행됨)
     */
    @Bean
    fun midTermForecastStep(
        jobRepository: JobRepository,
        transactionManager: PlatformTransactionManager,
    ): Step = StepBuilder("midTermForecastStep", jobRepository)
        .tasklet(midTermForecastTasklet(), transactionManager)
        .build()

    @Bean
    fun midTermForecastTasklet(): Tasklet = Tasklet { _, _ ->
        log.info("🚀 [Step 2: 중기예보] 전국 예보구역 중기예보(3~10일) 일괄 수집 및 DB 적재 시작")

        val activeRegions = KmaRepository.getActiveRegions()
        log.info("📍 [Step 2] 대상 행정동: {}건 (중기 예보구역 기준)", activeRegions.size)

        // 1. 중기예보(기온 + 육상날씨 결합 D+3~D+10) 수집
        val midTermRecords = kmaForecastCollector.collectMidTermForecasts(
            regions = activeRegions
        )

        // 2. 중기예보 테이블(mid_term_forecast)에 Bulk Upsert
        if (midTermRecords.isNotEmpty()) {
            KmaRepository.saveMidTermForecasts(midTermRecords)
            log.info("✅ [Step 2: 중기예보 완료] 총 {}건 DB(mid_term_forecast) 적재 완료", midTermRecords.size)
        } else {
            log.warn("⚠️ [Step 2: 중기예보] 수집된 중기예보 레코드가 없습니다.")
        }

        RepeatStatus.FINISHED
    }
}
