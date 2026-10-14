"""장소 실내/실외 판정 (B-10).

비 오는 날 추천(C-12 날씨 필터)에서 실외 장소를 거르기 위한 값이다.
TourAPI에 '실내 여부' 필드는 없으므로 분류코드로 추정한다. 근거가 강한 순서로 본다.

  1. 신분류체계 lclsSystm (detailCommon2) — 2025년 개편 후 등록·수정된 장소는 이것만 있다
  2. 구분류 cat1~3 (place) — 기존 장소. 신규 장소는 비어 있다(전체의 약 57%)
  3. 관광타입 중 확실한 것 (음식점·숙박·문화시설은 실내)
  4. 장소명 키워드 ('박물관', '해수욕장' ...)
  5. 나머지 관광타입 (쇼핑·레포츠·여행코스)

결과: indoor / outdoor / mixed(실내외 겸용·시장·테마파크 등) / None(판단 불가)
"""
from typing import Dict, Optional, Sequence, Tuple

INDOOR = "indoor"
OUTDOOR = "outdoor"
MIXED = "mixed"

# 신분류체계: 3단계(8자리) > 2단계(4자리) > 1단계(2자리) 순으로 가장 구체적인 규칙을 쓴다.
# 코드표: lclsSystmCode2 (lclsSystmListYn=Y)
LCLS_RULES: Dict[str, str] = {
    "AC": INDOOR,  # 숙박
    "AC05": OUTDOOR,  # 캠핑(야영장·오토캠핑·카라반·글램핑)
    "C01": MIXED,  # 추천코스
    "EV01": OUTDOOR,  # 축제
    "EV02": INDOOR,  # 공연
    "EV03": INDOOR,  # 행사(전시회·박람회)
    "EV030300": MIXED,  # 스포츠경기
    "EV030400": MIXED,  # 기타행사
    "EX01": MIXED,  # 전통체험
    "EX02": INDOOR,  # 공예체험
    "EX03": OUTDOOR,  # 농·산·어촌 체험
    "EX04": MIXED,  # 산사체험
    "EX05": INDOOR,  # 웰니스(온천·찜질방·스파)
    "EX050400": MIXED,  # 힐링명상
    "EX050700": OUTDOOR,  # 자연치유
    "EX06": MIXED,  # 산업관광
    "EX07": MIXED,  # 유람선·기타체험
    "FD": INDOOR,  # 음식
    "HS": OUTDOOR,  # 역사관광(고궁·성곽·사찰·유적)
    "HS040200": MIXED,  # 안보관광시설
    "LS": OUTDOOR,  # 레저스포츠
    "LS010100": MIXED,  # 인라인(실내 포함)
    "LS010900": MIXED,  # 스케이트
    "LS011200": MIXED,  # 사격장
    "LS011300": MIXED,  # 암벽등반
    "LS020700": MIXED,  # 수영
    "LS04": MIXED,  # 복합레저스포츠
    "NA": OUTDOOR,  # 자연관광
    "NA030100": MIXED,  # 동굴 — 비는 피할 수 있다
    "SH": INDOOR,  # 쇼핑
    "SH06": MIXED,  # 시장
    "VE01": OUTDOOR,  # 랜드마크(타워·다리·분수·등대)
    "VE010100": MIXED,  # 랜드마크 건물
    "VE02": OUTDOOR,  # 테마공원·동물원
    "VE020200": MIXED,  # 워터파크
    "VE020400": INDOOR,  # 수족관·아쿠아리움
    "VE020500": MIXED,  # 천문대
    "VE03": OUTDOOR,  # 도시공원
    "VE04": OUTDOOR,  # 골목길·마을·둘레길
    "VE05": MIXED,  # 관광단지·리조트
    "VE06": INDOOR,  # 공연장·영화관
    "VE07": INDOOR,  # 박물관·기념관·전시관·과학관·미술관
    "VE08": INDOOR,  # 연회장
    "VE09": INDOOR,  # 문화원·도서관·학교
    "VE10": MIXED,  # 경기장·스포츠센터
    "VE11": INDOOR,  # 공항·역·터미널
    "VE12": INDOOR,  # 서점·카지노·기타문화시설
}

# 구분류(cat1/cat2/cat3)
CAT_RULES: Dict[str, str] = {
    "A01": OUTDOOR,  # 자연
    "A0201": OUTDOOR,  # 역사관광지
    "A0202": MIXED,  # 휴양관광지
    "A02020300": INDOOR,  # 온천/욕장/스파
    "A02020400": INDOOR,  # 이색찜질방
    "A02020600": OUTDOOR,  # 테마공원
    "A02020700": OUTDOOR,  # 공원
    "A0203": MIXED,  # 체험관광지
    "A0204": INDOOR,  # 산업관광지
    "A0205": OUTDOOR,  # 건축/조형물
    "A0206": INDOOR,  # 문화시설
    "A03": OUTDOOR,  # 레포츠
    "A04": INDOOR,  # 쇼핑
    "A04010100": MIXED,  # 5일장
    "A04010200": MIXED,  # 상설시장
    "A05": INDOOR,  # 음식
    "B02": INDOOR,  # 숙박
    "C01": MIXED,  # 추천코스
}

# 관광타입: 분류코드가 없을 때. 강한 것은 키워드보다 먼저, 약한 것은 키워드 다음에 본다.
STRONG_TYPE_RULES: Dict[str, str] = {"14": INDOOR, "32": INDOOR, "39": INDOOR}
WEAK_TYPE_RULES: Dict[str, str] = {"38": INDOOR, "28": OUTDOOR, "25": MIXED}

# 장소명 키워드. 실내 > 겸용 > 실외 순으로 본다 ('부산시립미술관'이 '산'에 걸리지 않도록).
INDOOR_KEYWORDS = (
    "박물관", "미술관", "전시관", "기념관", "과학관", "체험관", "홍보관", "문화관", "역사관",
    "아쿠아리움", "수족관", "도서관", "공연장", "극장", "영화관", "갤러리", "아트홀",
    "백화점", "아울렛", "쇼핑몰", "면세점", "찜질방", "스파", "실내",
)
MIXED_KEYWORDS = ("시장", "거리", "마을", "테마파크", "랜드", "월드", "리조트", "동굴")
OUTDOOR_KEYWORDS = (
    "해수욕장", "해변", "해안", "폭포", "계곡", "오름", "수목원", "휴양림", "공원", "둘레길",
    "올레", "산성", "저수지", "호수", "등대", "전망대", "숲", "습지", "포구", "항구", "캠핑",
    "야영장", "골프", "유적", "고분", "왕릉", "서원", "향교", "사찰", "고택", "생가",
)
# 한 글자 접미사는 이름 끝에 올 때만 본다 ('구담봉', '단양 도담삼봉', '영탑사', '혼불문학관')
INDOOR_SUFFIXES = ("관",)
OUTDOOR_SUFFIXES = ("산", "봉", "섬", "길", "사", "암", "곶", "령")
# '사'로 끝나지만 절이 아닌 이름
NOT_TEMPLE_SUFFIXES = ("행사", "회사", "여행사", "공사", "조사")
# 쇼핑(38)은 매장 이름에 '골프', '캠핑' 같은 업종명이 들어가므로 실외 키워드를 보지 않는다
NO_OUTDOOR_KEYWORD_TYPES = ("38",)


def _lookup(rules: Dict[str, str], codes: Sequence[Optional[str]]) -> Optional[str]:
    """3단계 코드부터 앞자리를 줄여가며 가장 구체적인 규칙을 찾는다."""
    for code in reversed([c for c in codes if c]):
        for length in range(len(code), 1, -1):
            if code[:length] in rules:
                return rules[code[:length]]
    return None


def _strip_title(title: str) -> str:
    # '영탑사(당진)', '청사포 [다릿돌전망대]' -> 괄호 꼬리 제거
    for opener, closer in (("(", ")"), ("[", "]")):
        if title.endswith(closer) and opener in title:
            title = title[: title.rfind(opener)]
    return title.strip()


def classify_by_title(title: Optional[str], allow_outdoor: bool = True) -> Optional[str]:
    if not title:
        return None
    name = _strip_title(title)
    if any(k in name for k in INDOOR_KEYWORDS) or name.endswith(INDOOR_SUFFIXES):
        return INDOOR
    if any(k in name for k in MIXED_KEYWORDS):
        return MIXED
    if not allow_outdoor:
        return None
    if any(k in name for k in OUTDOOR_KEYWORDS):
        return OUTDOOR
    if name.endswith(OUTDOOR_SUFFIXES) and not name.endswith(NOT_TEMPLE_SUFFIXES):
        return OUTDOOR
    return None


def classify_indoor(
    content_type_id: Optional[str],
    lcls_codes: Sequence[Optional[str]] = (),
    cat_codes: Sequence[Optional[str]] = (),
    title: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """(판정값, 근거) — 근거는 lcls_systm / cat / content_type / keyword / None."""
    ctype = str(content_type_id or "")

    value = _lookup(LCLS_RULES, lcls_codes)
    if value:
        return value, "lcls_systm"
    value = _lookup(CAT_RULES, cat_codes)
    if value:
        return value, "cat"
    if ctype in STRONG_TYPE_RULES:
        return STRONG_TYPE_RULES[ctype], "content_type"
    value = classify_by_title(title, allow_outdoor=ctype not in NO_OUTDOOR_KEYWORD_TYPES)
    if value:
        return value, "keyword"
    if ctype in WEAK_TYPE_RULES:
        return WEAK_TYPE_RULES[ctype], "content_type"
    return None, None
