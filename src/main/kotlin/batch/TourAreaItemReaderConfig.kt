package batch

import org.springframework.batch.core.configuration.annotation.StepScope
import org.springframework.batch.item.ItemReader
import org.springframework.batch.item.support.ListItemReader
import org.springframework.beans.factory.annotation.Value
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import tourapi.KorServiceApi
import tourapi.TourAreaItem

/**
 * areaBasedList2를 페이지 단위로 호출해 List로 모은 뒤 ListItemReader로 감싼다.
 * 개발계정 일일 호출 한도 보호용으로 [areaMaxPages]까지만 순회한다.
 * (지금 단계는 DB 커서를 쓰지 않으므로 매 실행 1페이지부터 다시 훑는다.)
 */
@Configuration
class TourAreaItemReaderConfig(
    private val korServiceApi: KorServiceApi,
    @param:Value("\${tour.batch.area-max-pages:20}") private val areaMaxPages: Int,
) {

    @Bean
    @StepScope
    fun tourAreaItemReader(): ItemReader<TourAreaItem> {
        val result = korServiceApi.fetchAreaBasedList(maxPages = areaMaxPages)
        return ListItemReader(result.items)
    }
}
