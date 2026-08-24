package db

import org.jetbrains.exposed.v1.core.eq
import org.jetbrains.exposed.v1.jdbc.SchemaUtils
import org.jetbrains.exposed.v1.jdbc.batchUpsert
import org.jetbrains.exposed.v1.jdbc.selectAll
import org.jetbrains.exposed.v1.jdbc.transactions.transaction
import org.jetbrains.exposed.v1.jdbc.upsert
import tourapi.GalleryImageItem
import tourapi.TourAreaItem

object TourRepository {

    /** 마지막으로 완료된 페이지 번호. 기록이 없으면 0(=처음부터 시작). */
    fun getLastPage(source: String): Int = transaction(DbConfig.database) {
        SchemaUtils.createMissingTablesAndColumns(FetchCursorTable)
        FetchCursorTable.selectAll()
            .where { FetchCursorTable.sourceKey eq source }
            .singleOrNull()
            ?.get(FetchCursorTable.lastPage) ?: 0
    }

    fun saveCursor(source: String, lastPage: Int, totalCount: Int) {
        transaction(DbConfig.database) {
            SchemaUtils.createMissingTablesAndColumns(FetchCursorTable)
            FetchCursorTable.upsert(FetchCursorTable.sourceKey) {
                it[FetchCursorTable.sourceKey] = source
                it[FetchCursorTable.lastPage] = lastPage
                it[FetchCursorTable.totalCount] = totalCount
            }
        }
    }

    fun saveAreaItems(items: List<TourAreaItem>) {
        val valid = items.filter { !it.contentid.isNullOrBlank() }
        if (valid.isEmpty()) return
        transaction(DbConfig.database) {
            SchemaUtils.createMissingTablesAndColumns(PlaceTable)
            PlaceTable.batchUpsert(valid, PlaceTable.contentId) { item ->
                this[PlaceTable.contentId] = item.contentid!!
                this[PlaceTable.contentTypeId] = item.contenttypeid
                this[PlaceTable.title] = item.title
                this[PlaceTable.addr1] = item.addr1
                this[PlaceTable.addr2] = item.addr2
                this[PlaceTable.areaCode] = item.areacode
                this[PlaceTable.sigunguCode] = item.sigungucode
                this[PlaceTable.cat1] = item.cat1
                this[PlaceTable.cat2] = item.cat2
                this[PlaceTable.cat3] = item.cat3
                this[PlaceTable.firstImage] = item.firstimage
                this[PlaceTable.firstImage2] = item.firstimage2
                this[PlaceTable.mapX] = item.mapx?.toDoubleOrNull()
                this[PlaceTable.mapY] = item.mapy?.toDoubleOrNull()
                this[PlaceTable.mLevel] = item.mlevel
                this[PlaceTable.tel] = item.tel
                this[PlaceTable.zipcode] = item.zipcode
                this[PlaceTable.sourceCreatedTime] = item.createdtime
                this[PlaceTable.sourceModifiedTime] = item.modifiedtime
            }
        }
    }

    fun saveGalleryItems(items: List<GalleryImageItem>) {
        val valid = items.filter { !it.galContentId.isNullOrBlank() }
        if (valid.isEmpty()) return
        transaction(DbConfig.database) {
            SchemaUtils.createMissingTablesAndColumns(PlaceGalleryImageTable)
            PlaceGalleryImageTable.batchUpsert(valid, PlaceGalleryImageTable.galContentId) { item ->
                this[PlaceGalleryImageTable.galContentId] = item.galContentId!!
                this[PlaceGalleryImageTable.galContentTypeId] = item.galContentTypeId
                this[PlaceGalleryImageTable.galTitle] = item.galTitle
                this[PlaceGalleryImageTable.galWebImageUrl] = item.galWebImageUrl
                this[PlaceGalleryImageTable.galPhotographer] = item.galPhotographer
                this[PlaceGalleryImageTable.galPhotographyMonth] = item.galPhotographyMonth
                this[PlaceGalleryImageTable.galPhotographyLocation] = item.galPhotographyLocation
                this[PlaceGalleryImageTable.galSearchKeyword] = item.galSearchKeyword
                this[PlaceGalleryImageTable.sourceCreatedTime] = item.galCreatedtime
                this[PlaceGalleryImageTable.sourceModifiedTime] = item.galModifiedtime
            }
        }
    }
}
