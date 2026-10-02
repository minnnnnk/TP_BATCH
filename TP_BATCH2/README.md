# TP_BATCH2 — TourAPI 수집 & 벡터 동기화 배치 (Python)

한국관광공사 TourAPI에서 관광 데이터를 수집해 PostgreSQL에 적재하고,
그것을 **TP_TRAVEL_AI**(FastAPI 추천 서버)가 바로 쓸 수 있는 `travel_spots`
(pgvector 768차원)로 변환·임베딩하는 배치입니다.

기존 Kotlin 배치(**TP_BATCH**)와 **같은 테이블·같은 upsert 키**를 사용하므로,
둘을 번갈아 돌려도 데이터가 중복되거나 어긋나지 않습니다.

```text
TourAPI ──ingest-area──▶  place                (원본, content_id UNIQUE)
        ──ingest-gallery─▶ place_gallery_image  (관광사진)
                           │
                           │ enrich  (detailCommon2 → place.overview)
                           ▼
                        sync  (매핑 + ko-sroberta 임베딩)
                           ▼
                        travel_spots ──▶ TP_TRAVEL_AI  POST /api/v1/travel/recommend
```

---

## 설치

```bash
cd TP_BATCH2
python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt          # 수집 잡만 돌릴 때 (가볍다)
pip install -r requirements-embed.txt    # sync 잡까지 돌릴 때 (torch 포함)
```

> Python 3.9 이상에서 동작합니다. torch/sentence-transformers를 쓰는 `sync` 잡은
> 3.11 이상 권장(`brew install python@3.11`).

## 설정

`.env.example`을 `.env`로 복사해 채웁니다.

```bash
cp .env.example .env
```

기존 Kotlin 배치의 `secrets.properties`를 재사용하려면 서비스키/DB를 다시 적지 말고
경로만 지정하면 됩니다.

```dotenv
SECRETS_PROPERTIES=/path/to/Mini_Project_1/secrets.properties
```

**임베딩 설정은 TP_TRAVEL_AI와 반드시 동일해야 합니다.** 모델이 다르면 같은 테이블에
서로 비교할 수 없는 벡터가 섞여 추천 결과가 망가집니다.
(`jhgan/ko-sroberta-multitask`, 768차원 — 차원이 다르면 `sync`가 즉시 실패합니다.)

---

## 사용법

```bash
python -m app.cli <command> [options]
```

| 명령 | 설명 |
|---|---|
| `init-db` | 스키마 생성. `--with-vector`면 `travel_spots`까지 |
| `ingest-area` | 지역기반 관광정보 → `place` |
| `ingest-gallery` | 관광사진 → `place_gallery_image` |
| `enrich` | `detailCommon2`로 `place.overview` 채우기 |
| `sync` | `place` → `travel_spots` (매핑 + 임베딩) |
| `status` | 적재 건수, 수집 커서, 동기화 대기 건수 |

### 처음부터 끝까지

```bash
python -m app.cli init-db --with-vector
python -m app.cli ingest-area --max-pages 20      # 여러 번 나눠 실행 (커서 자동 이어받기)
python -m app.cli sync --limit 1000               # 임베딩은 시간이 걸리니 나눠서
python -m app.cli status
```

### 자주 쓰는 옵션

```bash
# 강원도(32) 관광지(12)만 수집
python -m app.cli ingest-area --area-code 32 --content-type-id 12

# 커서 무시하고 1페이지부터 다시
python -m app.cli ingest-area --restart

# DB 변경 없이 매핑 결과만 눈으로 확인 (임베딩 모델도 로딩하지 않음)
python -m app.cli sync --dry-run

# 설명문 품질 올리기 (장소 1건당 API 1회 — 한도 주의)
python -m app.cli enrich --limit 500
```

---

## 재실행 안전성

- **수집**: `fetch_cursor` 테이블에 마지막 페이지를 기록합니다. 개발계정 일일 호출
  한도(1,000건) 때문에 한 번에 전량을 못 가져오므로, 여러 번 나눠 실행하면
  중단 지점부터 이어서 수집합니다. 커서 키는 조건별로 분리됩니다
  (`areaBasedList2:area=32:type=12`).
- **적재**: 모두 `content_id` / `gal_content_id` 기준 upsert라 같은 페이지를 다시 읽어도
  중복 행이 생기지 않습니다.
- **동기화**: `travel_spots.source_content_id`(신규 nullable 컬럼)와 TourAPI 수정일시를
  비교해, 아직 없거나 원본이 바뀐 장소만 처리합니다. 이미 임베딩한 장소를 다시
  계산하지 않습니다.

## TP_TRAVEL_AI 연동 시 주의

`sync`는 `travel_spots`에 `source_content_id` 컬럼을 추가합니다(nullable이라 기존 AI 코드는
수정 없이도 동작). AI 쪽 ORM에서도 이 값을 다루려면 `app/models/travel.py`에 한 줄만 추가하면 됩니다.

```python
source_content_id = Column(String(20), unique=True, nullable=True, index=True)
```

또한 두 프로젝트가 **같은 DB를 보도록** `.env`의 접속 정보를 맞춰야 합니다.
TP_TRAVEL_AI의 기본값은 `localhost/vector_db`라 그대로 두면 서로 다른 DB를 보게 됩니다.

## 필드 매핑

| travel_spots | 출처 |
|---|---|
| `name` | `place.title` |
| `region` | `addr1` 앞 두 토큰 (없으면 `area_code` 표) — 예: `강원특별자치도 강릉시` |
| `category` | `content_type_id` + `cat1`/`cat3` → 자연/문화·역사/맛집/카페/액티비티/쇼핑/숙박/축제·공연 |
| `latitude` / `longitude` | `map_y` / `map_x` |
| `description` | `overview`가 있으면 본문으로, 없으면 이름·지역·카테고리·주소·연락처로 합성 |
| `metadata` | 원본 코드값, 태그, 전화, 이미지 URL, 권장 체류시간, 날씨 적합성 |
| `embedding` | 위 항목을 AI 서버와 **같은 형식**으로 조립한 문장을 ko-sroberta로 임베딩 |

이름·좌표·지역 중 하나라도 없는 장소는 경로 최적화에 쓸 수 없어 동기화에서 제외됩니다.
실제 수집 데이터 51,324건 기준 49,272건(96%)이 변환되고, 2,052건이 제외됩니다
(주소·지역코드 모두 없음 1,953 / 좌표 없음 80 / 좌표가 0,0 19).

`description` 품질이 추천 정확도를 좌우합니다. `areaBasedList2` 응답에는 상세 설명이
없으므로, 정확도를 올리려면 `enrich`를 나눠 돌려 `overview`를 채운 뒤 `sync`를 다시
실행하는 것을 권장합니다(수정일시가 그대로여도 overview가 채워지면 재동기화 대상이
되도록 하려면 `--restart` 대신 해당 장소의 `travel_spots` 행을 지우면 됩니다).

## 구조

```text
TP_BATCH2/
├── app/
│   ├── cli.py            # 커맨드라인 진입점
│   ├── config.py         # .env / 환경변수 / secrets.properties 로딩
│   ├── db.py             # 연결 + 스키마 DDL (Kotlin 배치와 동일 스키마)
│   ├── repository.py     # place / gallery / cursor upsert
│   ├── mapping.py        # place → travel_spots 필드 매핑
│   ├── embedding.py      # ko-sroberta 임베딩 (지연 로딩)
│   ├── tourapi/
│   │   ├── client.py     # 공통 호출·방어적 파싱·재시도·페이지 순회
│   │   ├── kor_service.py# areaBasedList2 / detailCommon2
│   │   └── gallery.py    # galleryList1
│   └── jobs/
│       ├── ingest.py     # 수집 잡 + overview 보강
│       └── sync_spots.py # 동기화 잡
├── requirements.txt
└── requirements-embed.txt
```
