# TP_BATCH — TourAPI 수집·정제 & 벡터 동기화 배치 (Python)

한국관광공사 TourAPI에서 관광 데이터를 수집해 PostgreSQL에 적재하고,
운영시간·휴무일·실내외 같은 추천용 메타데이터로 정제한 뒤,
**TP_TRAVEL_AI**(FastAPI 추천 서버)가 바로 쓸 수 있는 `travel_spots`
(pgvector 768차원)로 변환·임베딩하는 배치입니다.

```text
TourAPI ──ingest-area / refresh──▶ place                (원본, content_id UNIQUE)
        ──ingest-gallery─────────▶ place_gallery_image  (관광사진)
                                   │
                                   │ enrich  (detailIntro2 + detailCommon2)
                                   ▼
                                place_detail  (운영시간·휴무일·실내외·개요, B-10)
                                   │
                                   │ sync  (매핑 + ko-sroberta 임베딩)
                                   ▼
                                travel_spots ──▶ TP_TRAVEL_AI  POST /api/v1/travel/recommend

daily = refresh → ingest-gallery → enrich 를 하루 호출 한도 안에서 실행 (B-08)
schedule = daily를 매일 새벽(기본 04:00 KST)에 실행하는 상주 스케줄러
```

테이블 설계(PLACE / PLACE_DETAIL / PLACE_EMBEDDING)는 [docs/SCHEMA.md](docs/SCHEMA.md)에 정리했습니다.

---

## 설치

```bash
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt          # 수집·정제·스케줄 잡 (가볍다)
pip install -r requirements-embed.txt    # sync 잡까지 돌릴 때 (torch 포함)
pip install -r requirements-dev.txt      # 테스트 (pytest)
```

> Python 3.9 이상에서 동작합니다. torch/sentence-transformers를 쓰는 `sync` 잡은
> 3.11 이상 권장.

## 설정

`.env.example`을 참고하여 `.env`를 생성하거나, 루트의 `secrets.properties`를 활용합니다.
루트에 `secrets.properties`가 존재하면 자동으로 DB 및 API 설정을 읽어옵니다.

```bash
cp .env.example .env
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
| `init-db` | 스키마 생성. `--with-vector`면 `travel_spots`, `place_embedding`까지 |
| `ingest-area` | 지역기반 관광정보 → `place` (전량 수집, 커서로 이어받기) |
| `ingest-gallery` | 관광사진 → `place_gallery_image` |
| `refresh` | 최근 수정된 장소만 `place`에 반영 (보통 1~3회 호출) |
| `enrich` | `detailIntro2`·`detailCommon2` → `place_detail` (운영시간·휴무일·실내외·개요) |
| `sync` | `place` + `place_detail` → `travel_spots` (매핑 + 임베딩) |
| `daily` | `refresh` → `ingest-gallery` → `enrich`를 하루 한도 안에서 1회 실행 |
| `schedule` | `daily`를 매일 정해진 시각에 실행하는 상주 스케줄러 |
| `status` | 적재 건수, 수집 커서, 상세정보 보강 현황, 오늘 호출 수, 최근 실행 이력 |

### 처음부터 끝까지

```bash
python -m app.cli init-db --with-vector
python -m app.cli ingest-area --max-pages 20      # 여러 번 나눠 실행 (커서 자동 이어받기)
python -m app.cli enrich --limit 400              # 상세정보 (장소당 호출 2회)
python -m app.cli sync --limit 1000               # 임베딩은 시간이 걸리니 나눠서
python -m app.cli status
```

전량 수집이 끝난 뒤에는 `daily`(또는 `schedule`) 하나만 돌리면 됩니다.

### 자주 쓰는 옵션

```bash
# 강원도(32) 관광지(12)만 수집
python -m app.cli ingest-area --area-code 32 --content-type-id 12

# 커서 무시하고 1페이지부터 다시
python -m app.cli ingest-area --restart

# 강원도 음식점만 상세정보 채우기
python -m app.cli enrich --area-code 32 --content-type-id 39 --limit 300

# 개요 없이 운영시간·휴무일만 빠르게 (장소당 호출 1회 — 2배 많은 장소를 채운다)
python -m app.cli enrich --no-overview --limit 800

# 파서를 고친 뒤 기존 데이터에 반영 (API 호출 없음)
python -m app.cli enrich --reparse

# DB 변경 없이 매핑 결과만 눈으로 확인 (임베딩 모델도 로딩하지 않음)
python -m app.cli sync --dry-run
```

---

## 일일 배치와 스케줄러 (B-08)

`daily`는 하루치 호출 한도 안에서 세 단계를 차례로 돕니다. 한 단계가 실패해도 다음 단계는 돌고,
결과는 `batch_job_run`에 남아 `status`로 확인합니다.

1. **refresh** — 전국 목록을 수정일 최신순으로 읽다가, DB에 있는 가장 최근 수정일시보다 오래된
   항목이 나오면 멈춥니다. 수정된 장소는 다음 `enrich`에서 상세정보도 다시 조회됩니다.
2. **gallery** — 관광사진을 끝까지 받을 때까지 이어서 수집 (다 받으면 건너뜀).
3. **enrich** — KorService2에 남은 한도를 전부 상세정보 보강에 씁니다.

### 실행 방법 (둘 중 하나)

```bash
# A. 상주 스케줄러 (APScheduler). 기본 매일 04:00 KST, DAILY_CRON으로 변경
nohup python -m app.cli schedule --run-now >> logs/schedule.log 2>&1 &

# B. cron에서 하루 한 번 daily 호출 (crontab -e)
0 4 * * * cd /path/to/TP_BATCH && venv/bin/python -m app.cli daily >> logs/daily.log 2>&1
```

두 방식이 겹쳐 실행돼도 DB 잠금(advisory lock)으로 한쪽만 돕니다.
맥이 잠자기 중이라 실행 시각을 놓치면 스케줄러는 깨어난 뒤 3시간 안에 한 번 실행합니다.

### 호출 한도

- 개발계정은 서비스(KorService2, PhotoGalleryService1)마다 하루 1,000회입니다. 이 배치는
  `TOUR_API_DAILY_LIMIT`(기본 **900**)까지만 쓰고, 호출할 때마다 `api_call_quota`에 카운트를 올립니다.
  수동 실행(CLI)과 스케줄 실행이 같은 날 섞여도 합산됩니다.
- 한도에 닿거나 서버가 한도 초과로 응답하면 그때까지 받은 것을 저장하고 멈춥니다.
- 같은 서비스키를 Kotlin 배치도 쓰면 그쪽 호출은 카운트에 잡히지 않으니 한도를 낮춰 두세요.
- 상세정보는 장소당 2회라 하루 약 450곳입니다. 전체 약 5만 곳을 채우려면 **개발계정으로는 100일 이상**
  걸리므로, 운영계정 트래픽 증설을 신청하거나 `DETAIL_PRIORITY_AREAS`로 시범 지역부터 채우세요.

---

## 상세정보 정제 (B-10)

`enrich`는 장소마다 `detailIntro2`(운영시간·휴무일·주차·요금)와 `detailCommon2`(개요·신분류코드)를
받아 `place_detail`에 저장합니다. 원문과 정제값을 같이 저장하므로, 해석하지 못한 문장은 원문 그대로
LLM 단계(C-13)에 넘길 수 있습니다.

| 원문 예 | 정제 결과 |
|---|---|
| `10:00~17:00` | `open_min=600, close_min=1020` |
| `- 3월~10월 10:00~17:00- 11월~2월 10:00~16:00` | 가장 넓은 범위 10:00~17:00, 구간별 라벨은 `hours_detail` |
| `-11:00~20:00<br>- 준비시간 15:00~16:00<br>- 마지막 주문 19:30` | 11:00~20:00, `breaks`, `last_order_min` |
| `상시 개방` | `always_open=true` |
| `매주 일요일~월요일 / 법정공휴일` | `closed_weekdays={MON,SUN}`, `closed_on_holidays=true` |
| `매월 첫째, 셋째 수요일` | 요일은 비워 두고 `closed_irregular=true` |
| `홈페이지 참조`, `점포별 상이` | `parse_status=unparsed` (원문만 보관) |

실내외(`indoor_type`)는 신분류코드 → 구분류 → 관광타입 → 장소명 키워드 순으로 판정합니다
(규칙: `app/indoor.py`). 2025년 이후 등록·수정된 장소(약 57%)는 구분류(cat1~3)가 비어 있어
신분류코드(`lcls_systm*`)가 유일한 분류 근거이므로, `enrich`를 개요 포함으로 돌리는 것을 권장합니다.

---

## 재실행 안전성

- **수집**: `fetch_cursor` 테이블에 마지막 페이지를 기록합니다. 일일 호출 한도 때문에 한 번에
  전량을 못 가져오므로, 여러 번 나눠 실행하면 중단 지점부터 이어서 수집합니다. 커서 키는
  조건별로 분리됩니다 (`areaBasedList2:area=32:type=12`).
- **적재**: 모두 `content_id` / `gal_content_id` 기준 upsert라 같은 페이지를 다시 읽어도
  중복 행이 생기지 않습니다.
- **상세정보**: 아직 없는 장소와, `place.source_modified_time`이 바뀐 장소만 조회합니다.
  50건마다 저장하므로 중간에 멈춰도 그때까지는 남습니다.
- **동기화**: `travel_spots.source_content_id`(신규 nullable 컬럼)와 TourAPI 수정일시,
  상세정보 버전(`place_detail.updated_at`)을 비교해, 아직 없거나 원본·상세정보가 바뀐 장소만
  처리합니다. 이미 임베딩한 장소를 다시 계산하지 않습니다.

## TP_TRAVEL_AI 연동 시 주의

`sync`는 `travel_spots`에 `source_content_id` 컬럼을 추가합니다(nullable이라 기존 AI 코드는
수정 없이도 동작). AI 쪽 ORM에서도 이 값을 다루려면 `app/models/travel.py`에 한 줄만 추가하면 됩니다.

```python
source_content_id = Column(String(20), unique=True, nullable=True, index=True)
```

또한 두 프로젝트가 **같은 DB를 보도록** `.env`의 접속 정보를 맞춰야 합니다.
TP_TRAVEL_AI의 기본값은 `localhost/vector_db`라 그대로 두면 서로 다른 DB를 보게 됩니다.

상세정보가 있는 장소는 `metadata`에 아래 키가 추가됩니다 (C-12 필터용).

```json
{
  "indoor_type": "outdoor",
  "opening_hours": {"open": "09:00", "close": "18:00", "open_min": 540, "close_min": 1080, "always_open": false},
  "closed_weekdays": ["MON"],
  "closed_on_holidays": false,
  "closed_irregular": false,
  "no_closure": false,
  "use_time_text": "[3~10월] 09:00~18:00 [11월~2월] 10:00~17:00",
  "rest_date_text": "매주 월요일",
  "event_period": null,
  "detail_version": "1791892274"
}
```

## 필드 매핑

| travel_spots | 출처 |
|---|---|
| `name` | `place.title` |
| `region` | `addr1` 앞 두 토큰 (없으면 `area_code` 표) — 예: `강원특별자치도 강릉시` |
| `category` | `content_type_id` + `cat1`/`cat3`(없으면 신분류 `lcls_systm1/2`) → 자연/문화·역사/맛집/카페/액티비티/쇼핑/숙박/축제·공연 |
| `latitude` / `longitude` | `map_y` / `map_x` |
| `description` | `place_detail.overview`가 있으면 본문으로, 없으면 이름·지역·카테고리·주소·연락처로 합성 |
| `metadata` | 원본 코드값, 태그, 전화, 이미지 URL, 권장 체류시간, 날씨 적합성(실내외 반영), 운영시간·휴무일 |
| `embedding` | 위 항목을 AI 서버와 **같은 형식**으로 조립한 문장을 ko-sroberta로 임베딩 |

이름·좌표·지역 중 하나라도 없는 장소는 경로 최적화에 쓸 수 없어 동기화에서 제외됩니다.
실제 수집 데이터 51,324건 기준 49,272건(96%)이 변환되고, 2,052건이 제외됩니다
(주소·지역코드 모두 없음 1,953 / 좌표 없음 80 / 좌표가 0,0 19).

`description` 품질이 추천 정확도를 좌우합니다. `areaBasedList2` 응답에는 상세 설명이 없으므로
`enrich`로 개요를 채우면, 다음 `sync`에서 해당 장소가 자동으로 다시 임베딩됩니다.

## 테스트

```bash
python -m pytest            # 운영시간·휴무일 파서, 실내외 판정, 매핑 (실제 API 응답 문장 기준)
```

## 구조

```text
TP_BATCH/
├── app/
│   ├── cli.py            # 커맨드라인 진입점
│   ├── config.py         # .env / 환경변수 / secrets.properties 로딩
│   ├── db.py             # 연결 + 스키마 DDL (Kotlin 배치와 동일 스키마 + place_detail 등)
│   ├── repository.py     # place / gallery / cursor / place_detail upsert, 실행 이력
│   ├── quota.py          # 서비스별 일일 호출 한도
│   ├── detail_parser.py  # 운영시간·휴무일 파서, place_detail 행 조립 (B-10)
│   ├── indoor.py         # 실내외 판정 규칙 (B-10)
│   ├── mapping.py        # place(+detail) → travel_spots 필드 매핑
│   ├── embedding.py      # ko-sroberta 임베딩 (지연 로딩)
│   ├── scheduler.py      # daily 상주 스케줄러 (B-08)
│   ├── tourapi/
│   │   ├── client.py     # 공통 호출·방어적 파싱·재시도·한도 검사·페이지 순회
│   │   ├── kor_service.py# areaBasedList2 / detailCommon2 / detailIntro2
│   │   └── gallery.py    # galleryList1
│   └── jobs/
│       ├── ingest.py     # 수집 잡 + 최근 수정분 갱신(refresh)
│       ├── enrich.py     # 상세정보 보강 잡 (B-10)
│       ├── daily.py      # 일일 배치 (B-08)
│       └── sync_spots.py # 동기화 잡
├── docs/SCHEMA.md        # 테이블 설계
├── tests/                # pytest
├── requirements.txt
├── requirements-embed.txt
└── requirements-dev.txt
```
