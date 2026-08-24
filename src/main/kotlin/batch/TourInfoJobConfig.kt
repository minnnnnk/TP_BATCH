package batch

import org.springframework.batch.core.Job
import org.springframework.batch.core.Step
import org.springframework.batch.core.job.builder.JobBuilder
import org.springframework.batch.core.repository.JobRepository
import org.springframework.batch.core.step.builder.StepBuilder
import org.springframework.batch.item.ItemProcessor
import org.springframework.batch.item.ItemReader
import org.springframework.batch.item.ItemWriter
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.transaction.PlatformTransactionManager
import tourapi.TourAreaItem

@Configuration
class TourInfoJobConfig {

    @Bean
    fun tourInfoJob(
        jobRepository: JobRepository,
        fetchAreaBasedListStep: Step,
    ): Job = JobBuilder("tourInfoJob", jobRepository)
        .start(fetchAreaBasedListStep)
        .build()

    @Bean
    fun fetchAreaBasedListStep(
        jobRepository: JobRepository,
        transactionManager: PlatformTransactionManager,
        tourAreaItemReader: ItemReader<TourAreaItem>,
        placeItemProcessor: ItemProcessor<TourAreaItem, PlaceRecord>,
        placeItemWriter: ItemWriter<PlaceRecord>,
    ): Step = StepBuilder("fetchAreaBasedListStep", jobRepository)
        .chunk<TourAreaItem, PlaceRecord>(100, transactionManager)
        .reader(tourAreaItemReader)
        .processor(placeItemProcessor)
        .writer(placeItemWriter)
        .build()
}
