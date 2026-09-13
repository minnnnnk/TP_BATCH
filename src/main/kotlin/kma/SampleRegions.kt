package kma

/**
 * 전국 17개 주요 시/도 대표 행정동 데이터 (KMA_DATABASE_DESIGN.md 규격)
 * - 단기 격자(nx, ny), 중기 기온 지점(midTaRegId), 중기 육상 구역(midLandRegId) 매핑
 */
object SampleRegions {

    val NATIONWIDE_REGIONS: List<RegionLocationRecord> = listOf(
        // 1. 서울특별시 종로구 청운동
        RegionLocationRecord(
            regionCode = "1111051500",
            regId = "11B10101",
            sido = "서울특별시", sigungu = "종로구", eupmyeondong = "청운동",
            nx = 60, ny = 127,
            midTaRegId = "11B10101", midLandRegId = "11B00000"
        ),
        // 2. 서울특별시 강남구 역삼1동 (동일 midTa/midLand 공유, 동일/인접 nx, ny)
        RegionLocationRecord(
            regionCode = "1168064000",
            regId = "11B10101",
            sido = "서울특별시", sigungu = "강남구", eupmyeondong = "역삼1동",
            nx = 61, ny = 125,
            midTaRegId = "11B10101", midLandRegId = "11B00000"
        ),
        // 3. 부산광역시 해운대구 우제1동
        RegionLocationRecord(
            regionCode = "2635051000",
            regId = "11H20201",
            sido = "부산광역시", sigungu = "해운대구", eupmyeondong = "우제1동",
            nx = 99, ny = 75,
            midTaRegId = "11H20201", midLandRegId = "11H20000"
        ),
        // 4. 대구광역시 중구 동성동
        RegionLocationRecord(
            regionCode = "2711053000",
            regId = "11H10701",
            sido = "대구광역시", sigungu = "중구", eupmyeondong = "동성동",
            nx = 89, ny = 90,
            midTaRegId = "11H10701", midLandRegId = "11H10000"
        ),
        // 5. 인천광역시 중구 연안동
        RegionLocationRecord(
            regionCode = "2811051000",
            regId = "11B20201",
            sido = "인천광역시", sigungu = "중구", eupmyeondong = "연안동",
            nx = 54, ny = 124,
            midTaRegId = "11B20201", midLandRegId = "11B00000"
        ),
        // 6. 광주광역시 동구 충장동
        RegionLocationRecord(
            regionCode = "2911051500",
            regId = "11F20501",
            sido = "광주광역시", sigungu = "동구", eupmyeondong = "충장동",
            nx = 58, ny = 74,
            midTaRegId = "11F20501", midLandRegId = "11F20000"
        ),
        // 7. 대전광역시 중구 은행선화동
        RegionLocationRecord(
            regionCode = "3014053000",
            regId = "11C20401",
            sido = "대전광역시", sigungu = "중구", eupmyeondong = "은행선화동",
            nx = 67, ny = 100,
            midTaRegId = "11C20401", midLandRegId = "11C20000"
        ),
        // 8. 울산광역시 남구 삼산동
        RegionLocationRecord(
            regionCode = "3114057000",
            regId = "11H20101",
            sido = "울산광역시", sigungu = "남구", eupmyeondong = "삼산동",
            nx = 102, ny = 84,
            midTaRegId = "11H20101", midLandRegId = "11H20000"
        ),
        // 9. 세종특별자치시 보람동
        RegionLocationRecord(
            regionCode = "3611056000",
            regId = "11C20404",
            sido = "세종특별자치시", sigungu = "세종시", eupmyeondong = "보람동",
            nx = 66, ny = 103,
            midTaRegId = "11C20404", midLandRegId = "11C20000"
        ),
        // 10. 경기도 수원시 팔달구 매산동
        RegionLocationRecord(
            regionCode = "4111553000",
            regId = "11B20601",
            sido = "경기도", sigungu = "수원시 팔달구", eupmyeondong = "매산동",
            nx = 60, ny = 120,
            midTaRegId = "11B20601", midLandRegId = "11B00000"
        ),
        // 11. 강원특별자치도 강릉시 중앙동
        RegionLocationRecord(
            regionCode = "4215053000",
            regId = "11D20501",
            sido = "강원특별자치도", sigungu = "강릉시", eupmyeondong = "중앙동",
            nx = 92, ny = 131,
            midTaRegId = "11D20501", midLandRegId = "11D20000"
        ),
        // 12. 충청북도 청주시 상당구 중앙동
        RegionLocationRecord(
            regionCode = "4311151000",
            regId = "11C10301",
            sido = "충청북도", sigungu = "청주시 상당구", eupmyeondong = "중앙동",
            nx = 69, ny = 107,
            midTaRegId = "11C10301", midLandRegId = "11C10000"
        ),
        // 13. 충청남도 천안시 동남구 중앙동
        RegionLocationRecord(
            regionCode = "4413151000",
            regId = "11C20101",
            sido = "충청남도", sigungu = "천안시 동남구", eupmyeondong = "중앙동",
            nx = 63, ny = 110,
            midTaRegId = "11C20101", midLandRegId = "11C20000"
        ),
        // 14. 전북특별자치도 전주시 완산구 중앙동
        RegionLocationRecord(
            regionCode = "4511151000",
            regId = "11F10201",
            sido = "전북특별자치도", sigungu = "전주시 완산구", eupmyeondong = "중앙동",
            nx = 63, ny = 89,
            midTaRegId = "11F10201", midLandRegId = "11F10000"
        ),
        // 15. 전라남도 여수시 중앙동
        RegionLocationRecord(
            regionCode = "4613054000",
            regId = "11F20401",
            sido = "전라남도", sigungu = "여수시", eupmyeondong = "중앙동",
            nx = 73, ny = 66,
            midTaRegId = "11F20401", midLandRegId = "11F20000"
        ),
        // 16. 경상북도 포항시 북구 중앙동
        RegionLocationRecord(
            regionCode = "4711352000",
            regId = "11H10201",
            sido = "경상북도", sigungu = "포항시 북구", eupmyeondong = "중앙동",
            nx = 102, ny = 94,
            midTaRegId = "11H10201", midLandRegId = "11H10000"
        ),
        // 17. 제주특별자치도 제주시 일도1동
        RegionLocationRecord(
            regionCode = "5011051000",
            regId = "11G00201",
            sido = "제주특별자치도", sigungu = "제주시", eupmyeondong = "일도1동",
            nx = 52, ny = 38,
            midTaRegId = "11G00201", midLandRegId = "11G00000"
        ),
    )
}
