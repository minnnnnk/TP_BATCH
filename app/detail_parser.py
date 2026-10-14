"""detailIntro2 / detailCommon2 응답 -> place_detail 행 (B-10 장소 메타데이터 정제).

TourAPI의 운영시간·휴무일은 사람이 쓴 자유 텍스트라 형식이 제각각이다.

    '10:00~17:00', '11:00-22:00', '상시 개방', '홈페이지 참조',
    '- 평일 09:00~18:00- 주말 09:00~17:00',
    '-11:00~20:00<br>- 준비시간 15:00~16:00<br>- 마지막 주문 19:30',
    '매주 일요일~월요일 / 법정공휴일', '매월 첫째, 셋째 수요일 / 법정공휴일'

확실히 읽히는 것만 구조화하고 원문(*_text)은 그대로 남겨, 애매한 경우는 LLM 단계(C-13)가
원문을 보고 판단하게 한다. 특히 휴무 요일은 '매주'가 확실할 때만 채운다.
잘못 채우면 멀쩡히 여는 장소가 추천에서 빠지기 때문이다.
"""
import html
import re
from datetime import date
from typing import Any, Dict, List, Optional, Set

from app.indoor import classify_indoor

MINUTES_PER_DAY = 1440

# 관광타입마다 같은 의미의 필드 이름이 다르다. (None = 그 타입에는 없는 항목)
#   15(축제) usetimefestival은 이름과 달리 '이용요금'이다. 운영시간은 playtime.
#   32(숙박)은 체크인/아웃만 있고 운영시간 개념이 없다.
INTRO_FIELDS: Dict[str, Dict[str, Optional[str]]] = {
    "12": {"use_time": "usetime", "rest_date": "restdate", "parking": "parking", "use_fee": None},
    "14": {"use_time": "usetimeculture", "rest_date": "restdateculture", "parking": "parkingculture", "use_fee": "usefee"},
    "15": {"use_time": "playtime", "rest_date": None, "parking": None, "use_fee": "usetimefestival"},
    "25": {"use_time": None, "rest_date": None, "parking": None, "use_fee": None},
    "28": {"use_time": "usetimeleports", "rest_date": "restdateleports", "parking": "parkingleports", "use_fee": "usefeeleports"},
    "32": {"use_time": None, "rest_date": None, "parking": "parkinglodging", "use_fee": None},
    "38": {"use_time": "opentime", "rest_date": "restdateshopping", "parking": "parkingshopping", "use_fee": None},
    "39": {"use_time": "opentimefood", "rest_date": "restdatefood", "parking": "parkingfood", "use_fee": None},
}

WEEKDAY_CODES = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
_KOR_WEEKDAY = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}

# ── 텍스트 정리 ────────────────────────────────────────────
_BR = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t 　]+")


def clean_text(value: Any) -> Optional[str]:
    """HTML 태그/엔티티를 걷어내고 줄 단위로 정리한다. 빈 값은 None."""
    if value is None:
        return None
    text = html.unescape(str(value))
    text = _BR.sub("\n", text)
    text = _TAG.sub("", text)
    lines = [_SPACES.sub(" ", line).strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    return text or None


# ── 운영시간 ──────────────────────────────────────────────
# '09:00', '9:00', '09시', '10시 30분'
_TIME = r"(\d{1,2})\s*(?::|시\s*)(\d{2})?(?:\s*분)?"
_RANGE = re.compile(
    _TIME + r"\s*(?:~|∼|〜|-|–|부터)\s*(익일|다음\s*날|새벽)?\s*" + _TIME
)
_LAST_ORDER = re.compile(
    r"(마지막\s*주문|라스트\s*오더|L\.?\s*O\.?|주문\s*마감|입장\s*마감|매표\s*마감|발권\s*마감|입장\s*시간\s*마감)"
    r"\s*[:：]?\s*(?:은|는)?\s*" + _TIME,
    re.IGNORECASE,
)
_BREAK_WORDS = ("휴게", "준비", "브레이크", "break", "점심시간", "중식시간", "휴식")
_ALWAYS_WORDS = ("상시", "24시간", "연중 개방", "연중개방", "제한 없음", "제한없음", "자유 관람", "자유관람", "항시")


def _to_minutes(hour: str, minute: Optional[str]) -> Optional[int]:
    h = int(hour)
    m = int(minute) if minute else 0
    if h > 30 or m >= 60:  # '26:00'(익일 2시) 정도까지만 시각으로 인정
        return None
    return h * 60 + m


def format_minutes(value: Optional[int]) -> Optional[str]:
    """540 -> '09:00', 1560 -> '26:00' (자정을 넘긴 시각은 24를 더해 표기)."""
    if value is None:
        return None
    return "{0:02d}:{1:02d}".format(value // 60, value % 60)


def _label_before(text: str, start: int, prev_end: int) -> str:
    """시간 구간 바로 앞의 짧은 설명('평일', '3월~10월', '준비시간')을 뽑는다."""
    label = text[prev_end:start]
    label = label.split("\n")[-1]
    label = re.sub(r"^[\s\-–·•*※()\[\]]+|[\s:：()\[\]\-–]+$", "", label)
    return label[-20:].strip()


def parse_opening_hours(text: Optional[str]) -> Dict[str, Any]:
    """운영시간 텍스트 -> 대표 개장/폐장 시각 + 상세 구간.

    대표 시각은 영업 구간들의 가장 이른 시작 ~ 가장 늦은 끝이다(평일/주말, 하절기/동절기를
    합친 범위). '이 시각에 열려 있나'를 거르는 용도라 넓게 잡는 쪽이 안전하다.
    시각은 자정 기준 분이며, 자정을 넘기면 1440 이상이 된다(18:00~02:00 -> 1080~1560).
    """
    result: Dict[str, Any] = {
        "open_min": None,
        "close_min": None,
        "always_open": False,
        "detail": {},
        "status": "empty",
    }
    if not text:
        return result

    ranges: List[Dict[str, Any]] = []
    breaks: List[Dict[str, Any]] = []
    prev_end = 0
    for m in _RANGE.finditer(text):
        open_min = _to_minutes(m.group(1), m.group(2))
        close_min = _to_minutes(m.group(4), m.group(5))
        if open_min is None or close_min is None:
            continue
        if m.group(3) or close_min <= open_min:
            close_min += MINUTES_PER_DAY
        label = _label_before(text, m.start(), prev_end)
        prev_end = m.end()
        entry = {"open_min": open_min, "close_min": close_min, "label": label}
        if any(word in label.lower() for word in _BREAK_WORDS):
            breaks.append(entry)
        else:
            ranges.append(entry)

    last_orders = []
    for m in _LAST_ORDER.finditer(text):
        minutes = _to_minutes(m.group(2), m.group(3))
        if minutes is not None:
            last_orders.append(minutes)

    detail: Dict[str, Any] = {}
    if ranges:
        detail["ranges"] = ranges
    if breaks:
        detail["breaks"] = breaks
    if last_orders:
        detail["last_order_min"] = max(last_orders)
    result["detail"] = detail

    if ranges:
        result["open_min"] = min(r["open_min"] for r in ranges)
        result["close_min"] = max(r["close_min"] for r in ranges)
        result["status"] = "parsed"
    elif any(word in text for word in _ALWAYS_WORDS):
        result["always_open"] = True
        result["open_min"] = 0
        result["close_min"] = MINUTES_PER_DAY
        result["status"] = "parsed"
    else:
        result["status"] = "unparsed"
    return result


# ── 휴무일 ────────────────────────────────────────────────
_NO_CLOSURE = re.compile(r"연중\s*무휴|무휴|휴무\s*(?:일\s*)?없|휴관\s*(?:일\s*)?없|쉬는\s*날\s*없|^없음$")
_IRREGULAR = re.compile(r"첫째|둘째|셋째|넷째|다섯째|마지막|격주|짝수|홀수|\d\s*(?:번째|째)|매월|매달|경우|다음\s*날|익일|전날")
_HOLIDAY = re.compile(r"공휴일|국경일|명절|설날|설\s*연휴|설\s*당일|설[·ㆍ,\s]*추석|추석|신정|구정|1월\s*1일|성탄절|크리스마스")
# 괄호 안이 조건/예외('공휴일인 경우 다음날', '공휴일 제외')면 요일 판정에서 뺀다.
_PAREN = re.compile(r"\(([^()]*)\)")
_CONDITIONAL = re.compile(r"경우|제외|다음\s*날|익일|전날|공휴일|명절|추석|설")
# 새 항목이 시작되는 쉼표에서만 자른다. ('토, 일요일'은 한 항목으로 둔다)
_ITEM_SPLIT = re.compile(
    r"[/\n※;]|,\s*(?=매|격주|첫째|둘째|셋째|넷째|다섯째|마지막|법정|공휴|국경|명절|설|추석|신정|구정|1월)"
)
_DAY_RANGE = re.compile(
    r"(?<![가-힣0-9])([월화수목금토일])(?:요일)?\s*[~\-–]\s*([월화수목금토일])(?:요일)?(?![가-힣])"
)
# '월요일', 또는 목록/끝에 놓인 한 글자 요일('매주 월, 화', '토·일요일')
_DAY = re.compile(
    r"(?<![가-힣0-9])([월화수목금토일])"
    r"(?=요일|\s*[·ㆍ,~\-/]\s*[월화수목금토일]|\s*$|\s+(?:휴무|휴관|휴업|휴점|정기))"
)


def _expand_day_range(start: str, end: str) -> Set[int]:
    a, b = _KOR_WEEKDAY[start], _KOR_WEEKDAY[end]
    days = set()
    i = a
    while True:  # '일요일~월요일'처럼 주를 넘기는 범위도 처리
        days.add(i)
        if i == b:
            break
        i = (i + 1) % 7
    return days


def _strip_conditional_parens(text: str) -> str:
    def repl(m: "re.Match") -> str:
        inner = m.group(1)
        return " " if _CONDITIONAL.search(inner) else " {0} ".format(inner)

    return _PAREN.sub(repl, text)


def parse_closed_days(text: Optional[str]) -> Dict[str, Any]:
    """휴무일 텍스트 -> 매주 쉬는 요일 / 공휴일 휴무 / 불규칙 휴무 / 연중무휴."""
    result: Dict[str, Any] = {
        "weekdays": [],
        "holidays": False,
        "irregular": False,
        "no_closure": False,
        "status": "empty",
    }
    if not text:
        return result

    weekly: Set[int] = set()
    for item in _ITEM_SPLIT.split(text):
        item = item.strip()
        if not item:
            continue
        if _HOLIDAY.search(item):
            result["holidays"] = True
        main = _strip_conditional_parens(item)
        if _NO_CLOSURE.search(main):
            result["no_closure"] = True
        if _IRREGULAR.search(main):
            result["irregular"] = True
            continue

        days: Set[int] = set()
        for m in _DAY_RANGE.finditer(main):
            days |= _expand_day_range(m.group(1), m.group(2))
        for m in _DAY.finditer(main):
            days.add(_KOR_WEEKDAY[m.group(1)])
        if "주말" in main:
            days |= {5, 6}
        weekly |= days

    result["weekdays"] = [WEEKDAY_CODES[i] for i in sorted(weekly)]
    found = weekly or result["holidays"] or result["irregular"] or result["no_closure"]
    result["status"] = "parsed" if found else "unparsed"
    return result


# ── 행 조립 ──────────────────────────────────────────────
def _yyyymmdd(value: Any) -> Optional[date]:
    text = clean_text(value)
    if not text or not re.fullmatch(r"\d{8}", text):
        return None
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None


def compact_intro(intro: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """빈 값을 뺀 detailIntro2 원본. 타입별 기타 필드(대표메뉴 등)는 여기서 꺼내 쓴다."""
    if not intro:
        return {}
    return {
        k: v
        for k, v in intro.items()
        if k not in ("contentid", "contenttypeid") and v not in (None, "")
    }


def _overall_status(has_intro: bool, hours: Dict[str, Any], closed: Dict[str, Any]) -> str:
    if not has_intro:
        return "no_data"
    states = {hours["status"], closed["status"]} - {"empty"}
    if not states:
        return "empty"
    if states == {"parsed"}:
        return "parsed"
    if "parsed" in states:
        return "partial"
    return "unparsed"


def build_detail_row(
    place: Dict[str, Any],
    intro: Optional[Dict[str, Any]],
    common: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """place 한 행 + API 원본(소개/공통정보) -> place_detail 컬럼 dict.

    intro는 detailIntro2 아이템(또는 저장해 둔 intro_raw), common은 detailCommon2 아이템
    (또는 저장해 둔 공통정보 컬럼)이다. 원본만 있으면 언제든 다시 계산할 수 있게
    API 호출과 분리해 두었다 (enrich --reparse).
    """
    content_type_id = str(place.get("content_type_id") or "")
    fields = INTRO_FIELDS.get(content_type_id, {})
    raw = compact_intro(intro)
    common = common or {}

    def pick(key: str) -> Optional[str]:
        name = fields.get(key)
        return clean_text(raw.get(name)) if name else None

    use_time_text = pick("use_time")
    rest_date_text = pick("rest_date")
    hours = parse_opening_hours(use_time_text)
    closed = parse_closed_days(rest_date_text)

    lcls = (
        clean_text(common.get("lclsSystm1") or common.get("lcls_systm1")),
        clean_text(common.get("lclsSystm2") or common.get("lcls_systm2")),
        clean_text(common.get("lclsSystm3") or common.get("lcls_systm3")),
    )
    indoor_type, indoor_source = classify_indoor(
        content_type_id=content_type_id,
        lcls_codes=lcls,
        cat_codes=(place.get("cat1"), place.get("cat2"), place.get("cat3")),
        title=place.get("title"),
    )

    return {
        "content_id": place["content_id"],
        "content_type_id": content_type_id or None,
        "overview": clean_text(common.get("overview")),
        "homepage": clean_text(common.get("homepage")),
        "lcls_systm1": lcls[0],
        "lcls_systm2": lcls[1],
        "lcls_systm3": lcls[2],
        "ldong_regn_cd": clean_text(common.get("lDongRegnCd") or common.get("ldong_regn_cd")),
        "ldong_signgu_cd": clean_text(common.get("lDongSignguCd") or common.get("ldong_signgu_cd")),
        "use_time_text": use_time_text,
        "rest_date_text": rest_date_text,
        "parking_text": pick("parking"),
        "use_fee_text": pick("use_fee"),
        "intro_raw": raw,
        "open_min": hours["open_min"],
        "close_min": hours["close_min"],
        "always_open": hours["always_open"],
        "hours_detail": hours["detail"],
        "closed_weekdays": closed["weekdays"],
        "closed_on_holidays": closed["holidays"],
        "closed_irregular": closed["irregular"],
        "no_closure": closed["no_closure"],
        "event_start_date": _yyyymmdd(raw.get("eventstartdate")),
        "event_end_date": _yyyymmdd(raw.get("eventenddate")),
        "indoor_type": indoor_type,
        "indoor_source": indoor_source,
        "parse_status": _overall_status(bool(raw), hours, closed),
        "source_modified_time": place.get("source_modified_time"),
    }
