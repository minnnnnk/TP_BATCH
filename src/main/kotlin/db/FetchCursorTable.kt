package db

import org.jetbrains.exposed.v1.core.Table

/**
 * TourAPI 페이지네이션 진행 상황을 기록하는 테이블.
 * 개발계정 일일 호출 한도(1,000건) 때문에 한 번에 전체 데이터를 못 가져오므로,
 * 배치를 여러 번(여러 날) 나눠 돌릴 때 이전 실행이 어디까지 가져왔는지 이어받기 위함.
 */
object FetchCursorTable : Table("fetch_cursor") {
    val sourceKey = varchar("source", 50)
    val lastPage = integer("last_page").default(0)
    val totalCount = integer("total_count").default(0)

    override val primaryKey = PrimaryKey(sourceKey)
}
