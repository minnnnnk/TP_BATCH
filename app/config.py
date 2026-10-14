"""환경 설정 로딩.

우선순위: 환경변수 > .env > (선택) 레거시 secrets.properties.

secrets.properties를 함께 읽는 이유는, 기존 Kotlin 배치(TP_BATCH)가 쓰던
설정 파일을 그대로 재사용해 같은 DB/서비스키로 붙일 수 있게 하기 위함이다.
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

# 시크릿 파일 키 매핑 (Kotlin 형식 및 표준 환경변수 형식 모두 지원)
_SECRETS_KEY_MAP = {
    "tour.api.serviceKey": "TOUR_API_SERVICE_KEY",
    "TOUR_API_SERVICE_KEY": "TOUR_API_SERVICE_KEY",
    "kma.api.authKey": "KMA_API_AUTH_KEY",
    "KMA_API_AUTH_KEY": "KMA_API_AUTH_KEY",
    "db.host": "DB_HOST",
    "db.port": "DB_PORT",
    "db.name": "DB_NAME",
    "db.user": "DB_USER",
    "db.password": "DB_PASSWORD",
    "DB_HOST": "DB_HOST",
    "DB_PORT": "DB_PORT",
    "DB_NAME": "DB_NAME",
    "DB_USER": "DB_USER",
    "DB_PASSWORD": "DB_PASSWORD",
}


def _parse_properties_file(file: Path) -> Dict[str, str]:
    if not file.exists():
        return {}
    loaded: Dict[str, str] = {}
    try:
        for line in file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env_key = _SECRETS_KEY_MAP.get(key.strip())
            if env_key and value.strip():
                loaded[env_key] = value.strip()
    except Exception as e:
        pass
    return loaded


def _load_all_secrets() -> Dict[str, str]:
    """DB 정보와 API 키를 분리된 시크릿 파일에서 각각 읽어온다.

    우선순위:
    1. secrets-api.properties (API 키 전용 시크릿 파일)
    2. secrets.properties (기존 레거시 또는 DB 시크릿 파일)
    3. 환경변수 API_SECRETS_FILE / SECRETS_PROPERTIES 명시 경로
    """
    secrets: Dict[str, str] = {}
    root = Path(__file__).resolve().parent.parent

    # 1. DB 설정 파일 로드
    secrets.update(_parse_properties_file(root / "secrets.properties"))
    secrets.update(_parse_properties_file(root / "secrets-db.properties"))

    # 2. 분리된 API 키 전용 파일 로드 (접근 격리)
    api_secrets_env = os.getenv("API_SECRETS_FILE")
    if api_secrets_env:
        secrets.update(_parse_properties_file(Path(api_secrets_env).expanduser()))
    else:
        secrets.update(_parse_properties_file(root / "secrets-api.properties"))
        secrets.update(_parse_properties_file(root / "api_keys.properties"))

    # 3. 사용자 지정 통합 시크릿 파일
    custom_path = os.getenv("SECRETS_PROPERTIES")
    if custom_path:
        secrets.update(_parse_properties_file(Path(custom_path).expanduser()))

    return secrets


_SECRETS = _load_all_secrets()


def _value(key: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(key)
    if value:
        return value
    value = _SECRETS.get(key)
    if value:
        return value
    return default


def _csv(key: str, default: str = "") -> Tuple[str, ...]:
    raw = _value(key, default) or ""
    return tuple(v.strip() for v in raw.split(",") if v.strip())


def _bool(key: str, default: bool) -> bool:
    raw = _value(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "y", "on")


def _required(key: str) -> str:
    value = _value(key)
    if not value:
        raise RuntimeError(
            "필수 설정이 없습니다: {0}. .env 파일 또는 환경변수를 확인하세요 "
            "(.env.example 참고).".format(key)
        )
    return value


@dataclass(frozen=True)
class Settings:
    # TourAPI
    tour_api_service_key: str
    kor_service_base_url: str
    photo_gallery_base_url: str
    mobile_app: str
    request_timeout_sec: int

    # DB
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str

    # Batch
    num_of_rows: int
    max_pages: int
    chunk_size: int

    # Embedding (place -> travel_spots 동기화용)
    embedding_model_name: str
    embedding_dimension: int
    embedding_device: str
    embedding_batch_size: int

    # 일일 호출 한도 / 스케줄 (daily, schedule)
    tour_api_daily_limit: int  # 서비스(KorService2, PhotoGalleryService1)별 하루 상한
    daily_cron: str  # 한국 시간 기준 crontab 표현식
    daily_refresh_max_pages: int  # 최근 수정분 갱신에 쓸 최대 페이지 수
    daily_gallery_max_pages: int

    # 상세정보 보강 (enrich, B-10)
    detail_with_overview: bool  # detailCommon2(개요·신분류코드)도 함께 받을지 — 장소당 호출 2회
    detail_priority_types: Tuple[str, ...]  # 먼저 채울 관광타입 (예: 12,14,39)
    detail_priority_areas: Tuple[str, ...]  # 먼저 채울 지역코드 (예: 32,39)

    @property
    def dsn(self) -> str:
        return "host={0} port={1} dbname={2} user={3} password={4}".format(
            self.db_host, self.db_port, self.db_name, self.db_user, self.db_password
        )


def load_settings() -> Settings:
    return Settings(
        tour_api_service_key=_value("TOUR_API_SERVICE_KEY", ""),
        kor_service_base_url=_value(
            "KOR_SERVICE_BASE_URL", "https://apis.data.go.kr/B551011/KorService2"
        ),
        photo_gallery_base_url=_value(
            "PHOTO_GALLERY_BASE_URL",
            "https://apis.data.go.kr/B551011/PhotoGalleryService1",
        ),
        mobile_app=_value("TOUR_API_MOBILE_APP", "TP_BATCH2"),
        request_timeout_sec=int(_value("TOUR_API_TIMEOUT_SEC", "20")),
        db_host=_required("DB_HOST"),
        db_port=int(_value("DB_PORT", "5432")),
        db_name=_required("DB_NAME"),
        db_user=_required("DB_USER"),
        db_password=_required("DB_PASSWORD"),
        num_of_rows=int(_value("BATCH_NUM_OF_ROWS", "100")),
        max_pages=int(_value("BATCH_MAX_PAGES", "20")),
        chunk_size=int(_value("BATCH_CHUNK_SIZE", "500")),
        embedding_model_name=_value("EMBEDDING_MODEL_NAME", "jhgan/ko-sroberta-multitask"),
        embedding_dimension=int(_value("EMBEDDING_DIMENSION", "768")),
        embedding_device=_value("EMBEDDING_DEVICE", "cpu"),
        embedding_batch_size=int(_value("EMBEDDING_BATCH_SIZE", "64")),
        # 개발계정 1,000건 중 수동 테스트·다른 배치 몫으로 100건을 남겨 둔다.
        tour_api_daily_limit=int(_value("TOUR_API_DAILY_LIMIT", "900")),
        daily_cron=_value("DAILY_CRON", "0 4 * * *"),
        daily_refresh_max_pages=int(_value("DAILY_REFRESH_MAX_PAGES", "10")),
        daily_gallery_max_pages=int(_value("DAILY_GALLERY_MAX_PAGES", "70")),
        detail_with_overview=_bool("DETAIL_WITH_OVERVIEW", True),
        # 일정 짜기에 직접 쓰이는 타입(관광지·문화시설·음식점·레포츠·쇼핑)을 먼저 채운다.
        detail_priority_types=_csv("DETAIL_PRIORITY_TYPES", "12,14,39,28,38"),
        detail_priority_areas=_csv("DETAIL_PRIORITY_AREAS", ""),
    )
