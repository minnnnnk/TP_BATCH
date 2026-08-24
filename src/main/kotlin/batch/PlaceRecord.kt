package batch

/**
 * areaBasedList2 응답(TourAreaItem)을 place 테이블 컬럼 형태로 다듬은,
 * DB insert 준비가 끝난 레코드. 아직 실제 저장(Writer)은 하지 않는다.
 */
data class PlaceRecord(
    val contentId: String,
    val contentTypeId: String?,
    val title: String?,
    val addr1: String?,
    val addr2: String?,
    val areaCode: String?,
    val sigunguCode: String?,
    val cat1: String?,
    val cat2: String?,
    val cat3: String?,
    val firstImage: String?,
    val firstImage2: String?,
    val mapX: Double?,
    val mapY: Double?,
    val mLevel: String?,
    val tel: String?,
    val zipcode: String?,
    val sourceCreatedTime: String?,
    val sourceModifiedTime: String?,
)
