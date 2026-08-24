package db

import org.jetbrains.exposed.v1.core.dao.id.LongIdTable

/**
 * 국문 관광정보(KorService2 areaBasedList2) 적재 테이블.
 * `3 데이터베이스 설계.md`의 PLACE 엔티티 — place_embedding.place_id가 이 테이블의 id를 참조한다.
 */
object PlaceTable : LongIdTable("place") {
    val contentId = varchar("content_id", 20).uniqueIndex()
    val contentTypeId = varchar("content_type_id", 10).nullable()
    val title = varchar("title", 500).nullable()
    val addr1 = varchar("addr1", 500).nullable()
    val addr2 = varchar("addr2", 500).nullable()
    val areaCode = varchar("area_code", 10).nullable()
    val sigunguCode = varchar("sigungu_code", 10).nullable()
    val cat1 = varchar("cat1", 20).nullable()
    val cat2 = varchar("cat2", 20).nullable()
    val cat3 = varchar("cat3", 20).nullable()
    val firstImage = varchar("first_image", 1000).nullable()
    val firstImage2 = varchar("first_image2", 1000).nullable()
    val mapX = double("map_x").nullable()
    val mapY = double("map_y").nullable()
    val mLevel = varchar("m_level", 10).nullable()
    val tel = text("tel").nullable()
    val zipcode = varchar("zipcode", 10).nullable()
    val sourceCreatedTime = varchar("source_created_time", 20).nullable()
    val sourceModifiedTime = varchar("source_modified_time", 20).nullable()
}

/**
 * 관광사진(PhotoGalleryService1 galleryList1) 적재 테이블.
 * gal_content_id는 place.content_id와 별개의 ID 체계라 지금은 PLACE와 FK로 엮지 않는다.
 */
object PlaceGalleryImageTable : LongIdTable("place_gallery_image") {
    val galContentId = varchar("gal_content_id", 20).uniqueIndex()
    val galContentTypeId = varchar("gal_content_type_id", 10).nullable()
    val galTitle = varchar("gal_title", 500).nullable()
    val galWebImageUrl = varchar("gal_web_image_url", 1000).nullable()
    val galPhotographer = varchar("gal_photographer", 200).nullable()
    val galPhotographyMonth = varchar("gal_photography_month", 20).nullable()
    val galPhotographyLocation = varchar("gal_photography_location", 500).nullable()
    val galSearchKeyword = varchar("gal_search_keyword", 1000).nullable()
    val sourceCreatedTime = varchar("source_created_time", 20).nullable()
    val sourceModifiedTime = varchar("source_modified_time", 20).nullable()
}
