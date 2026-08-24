package batch

import org.slf4j.LoggerFactory
import org.springframework.batch.item.Chunk
import org.springframework.batch.item.ItemWriter
import org.springframework.stereotype.Component

/** 아직 DB에는 넣지 않는 단계 — 변환된 레코드를 로그로만 확인한다. */
@Component
class PlaceItemWriter : ItemWriter<PlaceRecord> {

    private val log = LoggerFactory.getLogger(PlaceItemWriter::class.java)

    override fun write(chunk: Chunk<out PlaceRecord>) {
        log.info("[PlaceItemWriter] DB 저장 준비 완료 {}건 (실제 insert는 아직 하지 않음)", chunk.size())
        chunk.items.forEach { log.info("  -> {} / {}", it.contentId, it.title) }
    }
}
