package batch

import org.springframework.batch.item.ItemProcessor
import org.springframework.stereotype.Component
import tourapi.TourAreaItem

/** TourAreaItem(API 응답)을 PlaceRecord(DB insert 준비 완료 형태)로 변환한다. */
@Component
class PlaceItemProcessor : ItemProcessor<TourAreaItem, PlaceRecord> {

    override fun process(item: TourAreaItem): PlaceRecord? {
        val contentId = item.contentid?.takeIf { it.isNotBlank() } ?: return null
        return PlaceRecord(
            contentId = contentId,
            contentTypeId = item.contenttypeid,
            title = item.title,
            addr1 = item.addr1,
            addr2 = item.addr2,
            areaCode = item.areacode,
            sigunguCode = item.sigungucode,
            cat1 = item.cat1,
            cat2 = item.cat2,
            cat3 = item.cat3,
            firstImage = item.firstimage,
            firstImage2 = item.firstimage2,
            mapX = item.mapx?.toDoubleOrNull(),
            mapY = item.mapy?.toDoubleOrNull(),
            mLevel = item.mlevel,
            tel = item.tel,
            zipcode = item.zipcode,
            sourceCreatedTime = item.createdtime,
            sourceModifiedTime = item.modifiedtime,
        )
    }
}
