"""환경 설정 로딩.

우선순위: 환경변수 > .env > (선택) 레거시 secrets.properties.

secrets.properties를 함께 읽는 이유는, 기존 Kotlin 배치(TP_BATCH)가 쓰던
설정 파일을 그대로 재사용해 같은 DB/서비스키로 붙일 수 있게 하기 위함이다.
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv

load_dotenv()

# Kotlin 배치의 secrets.properties 키 -> 이 프로젝트의 환경변수 키
_SECRETS_KEY_MAP = {
    "tour.api.serviceKey": "TOUR_API_SERVICE_KEY",
    "db.host": "DB_HOST",
    "db.port": "DB_PORT",
    "db.name": "DB_NAME",
    "db.user": "DB_USER",
    "db.password": "DB_PASSWORD",
}


def _load_secrets_properties() -> Dict[str, str]:
    path = os.getenv("SECRETS_PROPERTIES")
    if not path:
        return {}
    file = Path(path).expanduser()
    if not file.exists():
        return {}

    loaded: Dict[str, str] = {}
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env_key = _SECRETS_KEY_MAP.get(key.strip())
        if env_key and value.strip():
            loaded[env_key] = value.strip()
    return loaded


_SECRETS = _load_secrets_properties()


def _value(key: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(key)
    if value:
        return value
    value = _SECRETS.get(key)
    if value:
        return value
    return default


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

    @property
    def dsn(self) -> str:
        return "host={0} port={1} dbname={2} user={3} password={4}".format(
            self.db_host, self.db_port, self.db_name, self.db_user, self.db_password
        )


def load_settings() -> Settings:
    return Settings(
        tour_api_service_key=_required("TOUR_API_SERVICE_KEY"),
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
    )
