"""place(TourAPI 원본) -> travel_spots(추천용) 필드 매핑.

TP_TRAVEL_AI의 TravelSpot 모델이 기대하는 형태
(name / region / category / latitude / longitude / description / metadata)로
TourAPI 코드값을 사람이 읽는 값으로 풀어준다.
"""
from typing import Any, Dict, List, Optional, Tuple

from app.detail_parser import format_minutes

# 지역코드 -> 시도명 (areaCode)
AREA_CODE_TO_NAME = {
    "1": "서울특별시",
    "2": "인천광역시",
    "3": "대전광역시",
    "4": "대구광역시",
    "5": "광주광역시",
    "6": "부산광역시",
    "7": "울산광역시",
    "8": "세종특별자치시",
    "31": "경기도",
    "32": "강원특별자치도",
    "33": "충청북도",
    "34": "충청남도",
    "35": "경상북도",
    "36": "경상남도",
    "37": "전북특별자치도",
    "38": "전라남도",
    "39": "제주특별자치도",
}

# 관광타입ID -> 원본 타입명 (contentTypeId)
CONTENT_TYPE_TO_NAME = {
    "12": "관광지",
    "14": "문화시설",
    "15": "축제공연행사",
    "25": "여행코스",
    "28": "레포츠",
    "32": "숙박",
    "38": "쇼핑",
    "39": "음식점",
}

# 대분류 -> 사람이 읽는 이름 (cat1)
CAT1_TO_NAME = {
    "A01": "자연",
    "A02": "인문(문화/예술/역사)",
    "A03": "레포츠",
    "A04": "쇼핑",
    "A05": "음식",
    "B02": "숙박",
    "C01": "추천코스",
}

# TP_TRAVEL_AI가 쓰는 카테고리 체계
# (자연 / 힐링 / 카페 / 액티비티 / 문화·역사 / 맛집 / 실내 / 축제 / 쇼핑 / 숙박)
CAFE_CAT3 = {"A05020900"}  # 카페/전통찻집

# 실내 위주라 비 오는 날에도 무난한 카테고리
INDOOR_CATEGORIES = {"문화/역사", "카페", "맛집", "쇼핑", "숙박", "실내"}

# 카테고리별 권장 체류 시간(분) — route_planner의 stay_duration_min으로 쓰인다
STAY_MINUTES = {
    "자연": 90,
    "문화/역사": 80,
    "액티비티": 120,
    "카페": 60,
    "맛집": 60,
    "쇼핑": 70,
    "축제/공연": 100,
    "숙박": 0,
    "여행코스": 120,
    "관광지": 80,
}
DEFAULT_STAY_MINUTES = 80


def resolve_region(addr1: Optional[str], area_code: Optional[str]) -> Optional[str]:
    """'강원특별자치도 강릉시' 형태의 지역명을 만든다.

    주소가 가장 정확하므로 addr1의 앞 두 토큰을 우선 사용하고,
    주소가 없을 때만 areaCode 표를 쓴다.
    """
    if addr1:
        tokens = addr1.split()
        if len(tokens) >= 2:
            return " ".join(tokens[:2])
        if tokens:
            return tokens[0]

    if area_code:
        return AREA_CODE_TO_NAME.get(str(area_code))
    return None


# 신분류체계 대분류(lclsSystm1) -> 카테고리. 2025년 이후 등록·수정된 장소는 cat1~3가 비어 있어
# (전체의 약 57%) 관광지(12)가 모두 '관광지'로 뭉뚱그려지므로, enrich가 받아 둔 신분류로 가른다.
LCLS1_TO_CATEGORY = {
    "NA": "자연",
    "HS": "문화/역사",
    "VE": "문화/역사",
    "EX": "액티비티",
    "LS": "액티비티",
}
# 대분류만으로 어긋나는 중분류
LCLS2_TO_CATEGORY = {
    "VE02": "액티비티",  # 테마파크·워터파크·동물원
    "VE03": "자연",  # 도시공원
}
CAFE_LCLS2 = "FD05"  # 카페/찻집


def resolve_category(
    content_type_id: Optional[str],
    cat1: Optional[str],
    cat3: Optional[str],
    lcls1: Optional[str] = None,
    lcls2: Optional[str] = None,
) -> str:
    """contentTypeId + 분류코드를 TP_TRAVEL_AI 카테고리로 환산한다."""
    ctype = str(content_type_id) if content_type_id else None

    if ctype == "39":
        return "카페" if cat3 in CAFE_CAT3 or lcls2 == CAFE_LCLS2 else "맛집"
    if ctype == "28":
        return "액티비티"
    if ctype == "14":
        return "문화/역사"
    if ctype == "15":
        return "축제/공연"
    if ctype == "38":
        return "쇼핑"
    if ctype == "32":
        return "숙박"
    if ctype == "25":
        return "여행코스"
    if ctype == "12":
        # 관광지 안에 자연(A01)과 인문(A02)이 섞여 있어 cat1로 한 번 더 가른다.
        if cat1 == "A01":
            return "자연"
        if cat1 == "A02":
            return "문화/역사"
        return LCLS2_TO_CATEGORY.get(lcls2 or "") or LCLS1_TO_CATEGORY.get(lcls1 or "", "관광지")

    if cat1 == "A01":
        return "자연"
    if cat1 == "A02":
        return "문화/역사"
    if cat1 == "A03":
        return "액티비티"
    return "관광지"


def build_description(row: Dict[str, Any], region: Optional[str], category: str) -> str:
    """임베딩 원문이 될 설명문.

    areaBasedList2에는 상세 설명이 없어서, overview(enrich 잡이 place_detail에 채움)가
    있으면 그것을 본문으로 쓰고 없으면 메타데이터로 최소한의 문장을 합성한다.
    """
    title = row.get("title") or "이름 미상"
    parts: List[str] = []

    head = "{0}은(는) {1} 위치한 {2}입니다.".format(
        title, (region + "에") if region else "국내에", category
    )
    parts.append(head)

    overview = (row.get("overview") or "").strip()
    if overview:
        parts.append(overview)

    addr = row.get("addr1")
    if addr:
        addr_full = addr if not row.get("addr2") else "{0} {1}".format(addr, row["addr2"])
        parts.append("주소: {0}".format(addr_full))

    if row.get("tel"):
        parts.append("문의: {0}".format(row["tel"]))

    return " ".join(parts)


def build_metadata(row: Dict[str, Any], category: str) -> Dict[str, Any]:
    """TravelSpot.metadata(JSONB)에 들어갈 여행 속성.

    동행자/계절은 TourAPI에 근거 데이터가 없으므로 임의로 좁히지 않고
    넓게 두었다. 추천 단계에서 가중치로만 쓰이므로 과하게 단정하는 것보다 안전하다.
    """
    tags: List[str] = []
    content_type_name = CONTENT_TYPE_TO_NAME.get(str(row.get("content_type_id") or ""))
    cat1_name = CAT1_TO_NAME.get(row.get("cat1") or "")
    if content_type_name:
        tags.append(content_type_name)
    if cat1_name and cat1_name not in tags:
        tags.append(cat1_name)
    if row.get("first_image"):
        tags.append("사진있음")

    # 실내외 판정(place_detail.indoor_type)이 있으면 그것을, 없으면 카테고리로 추정한다.
    indoor_type = row.get("indoor_type")
    weather: List[str] = ["맑음", "흐림"]
    if indoor_type == "indoor" or (indoor_type is None and category in INDOOR_CATEGORIES):
        weather.append("비오는날_실내")

    metadata = {
        "source": "TourAPI",
        "source_content_id": row.get("content_id"),
        "content_type_id": row.get("content_type_id"),
        "content_type_name": content_type_name,
        "cat1": row.get("cat1"),
        "cat2": row.get("cat2"),
        "cat3": row.get("cat3"),
        "area_code": row.get("area_code"),
        "sigungu_code": row.get("sigungu_code"),
        "zipcode": row.get("zipcode"),
        "phone": row.get("tel"),
        "image_url": row.get("first_image"),
        "thumbnail_url": row.get("first_image2"),
        "tags": tags,
        "companion_types": ["혼자", "커플", "가족", "친구"],
        "best_seasons": ["사계절"],
        "weather_suitability": weather,
        "estimated_stay_min": STAY_MINUTES.get(category, DEFAULT_STAY_MINUTES),
        "source_modified_time": row.get("source_modified_time"),
    }
    if row.get("detail_version"):
        metadata.update(build_detail_metadata(row))
    return metadata


def build_detail_metadata(row: Dict[str, Any]) -> Dict[str, Any]:
    """place_detail(B-10) 값을 RAG 필터(C-12)가 쓰기 좋은 형태로 옮긴다.

    시각은 사람이 읽는 'HH:MM'과 비교용 분(min)을 함께 둔다. 자정을 넘기면 '26:00'처럼 표기한다.
    정제 못 한 원문(use_time_text / rest_date_text)도 넘겨 LLM이 참고하게 한다.
    """
    event = None
    if row.get("event_start_date") or row.get("event_end_date"):
        event = {
            "start": row["event_start_date"].isoformat() if row.get("event_start_date") else None,
            "end": row["event_end_date"].isoformat() if row.get("event_end_date") else None,
        }
    hours = None
    if row.get("open_min") is not None:
        hours = {
            "open": format_minutes(row["open_min"]),
            "close": format_minutes(row["close_min"]),
            "open_min": row["open_min"],
            "close_min": row["close_min"],
            "always_open": bool(row.get("always_open")),
        }
    return {
        "indoor_type": row.get("indoor_type"),
        "opening_hours": hours,
        "closed_weekdays": list(row.get("closed_weekdays") or []),
        "closed_on_holidays": bool(row.get("closed_on_holidays")),
        "closed_irregular": bool(row.get("closed_irregular")),
        "no_closure": bool(row.get("no_closure")),
        "use_time_text": row.get("use_time_text"),
        "rest_date_text": row.get("rest_date_text"),
        "event_period": event,
        "detail_version": row.get("detail_version"),
    }


def build_embedding_text(
    name: str, region: Optional[str], category: str, description: str, metadata: Dict[str, Any]
) -> str:
    """임베딩 입력 문장.

    TP_TRAVEL_AI의 TravelService._build_embedding_text와 같은 형식으로 맞춘다.
    형식이 어긋나면 질의 벡터와 문서 벡터의 분포가 달라져 유사도가 떨어진다.
    """
    parts = [
        "장소명: {0}".format(name),
        "지역: {0}".format(region or "미상"),
        "카테고리: {0}".format(category),
        "설명: {0}".format(description),
    ]
    tags = metadata.get("tags") or []
    if tags:
        parts.append("태그: {0}".format(", ".join(tags)))
    companions = metadata.get("companion_types") or []
    if companions:
        parts.append("동행자: {0}".format(", ".join(companions)))
    weather = metadata.get("weather_suitability") or []
    if weather:
        parts.append("날씨/계절: {0}".format(", ".join(weather)))
    return " | ".join(parts)


def map_place_row(row: Dict[str, Any]) -> Optional[Tuple[Dict[str, Any], str]]:
    """place 한 행을 travel_spots 삽입용 dict + 임베딩 원문으로 변환한다.

    좌표나 이름이 없으면 경로 최적화에 쓸 수 없으므로 None을 돌려 건너뛴다.
    """
    name = (row.get("title") or "").strip()
    latitude = row.get("map_y")
    longitude = row.get("map_x")
    if not name or latitude is None or longitude is None:
        return None
    # TourAPI가 좌표 미상일 때 0을 넣어주는 경우가 있어 함께 걸러낸다.
    if float(latitude) == 0.0 or float(longitude) == 0.0:
        return None

    region = resolve_region(row.get("addr1"), row.get("area_code"))
    if not region:
        return None

    category = resolve_category(
        row.get("content_type_id"),
        row.get("cat1"),
        row.get("cat3"),
        row.get("lcls_systm1"),
        row.get("lcls_systm2"),
    )
    description = build_description(row, region, category)
    metadata = build_metadata(row, category)

    address = row.get("addr1")
    if address and row.get("addr2"):
        address = "{0} {1}".format(address, row["addr2"])

    spot = {
        "source_content_id": row.get("content_id"),
        "name": name[:255],
        "region": region[:100],
        "address": address[:500] if address else None,
        "category": category[:100],
        "latitude": float(latitude),
        "longitude": float(longitude),
        "description": description,
        "metadata": metadata,
    }
    return spot, build_embedding_text(name, region, category, description, metadata)
