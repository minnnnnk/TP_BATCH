# TP_BATCH 추가 작업 계획 (TODO)

본 문서는 프로젝트의 안정적인 운영, RAG(검색 증강 생성) 품질 향상, 기상청 및 관광 데이터 파이프라인 확장을 위해 필요한 작업 목록을 정리한 문서입니다.

---

## 1. RAG 및 임베딩 품질 최적화 (우선순위: 높음)

- [ ] **임베딩 텍스트 토큰 잘림(Truncation) 방지 개선**
  - **파일**: `app/mapping.py` (`build_embedding_text`)
  - **내용**: 뒤쪽에 배치된 핵심 메타데이터(`태그`, `동행자`, `날씨/계절`)를 `설명(description)`보다 앞쪽에 배치하도록 순서 조정.
  - **내용**: `description`이 수천 자에 달할 경우 앞단만 안전하게 슬라이싱/요약하여 벡터 정보 손실 방지.
  - **먼저 확인**: 실제 입력 한도를 `SentenceTransformer("jhgan/ko-sroberta-multitask").max_seq_length`로 확인. 512가 아니라 128이면 300~400자도 넘치므로 자를 길이를 그에 맞춰 정한다.
  - **주의**: 순서를 바꾸면 TP_TRAVEL_AI의 `TravelService._build_embedding_text`도 같이 바꿔야 한다(두 형식이 같아야 함).

- [ ] **상세 개요문(`overview`) 데이터 보강 (Enrichment)** — 코드 준비 완료, 실행만 남음
  - **내용**: 현재 DB에 있는 49,824건의 장소 데이터는 대부분 `overview`가 비어 있어 RAG 시맨틱 검색 정확도가 낮을 수 있음.
  - **작업**: TourAPI 서비스키 등록 후 `python -m app.cli enrich --limit 500` 등을 단계적으로 실행하거나, `daily`에 맡겨 남은 한도만큼 매일 채운다.
  - **완료된 부분**: `enrich`가 `detailIntro2`/`detailCommon2` → `place_detail`(운영시간·휴무일·실내외·개요)로 바뀌었고, 상세정보가 채워지면 다음 `sync`에서 자동으로 재임베딩된다(`detail_version`). 이미 조회한 장소는 `place_detail`에 기록되어 같은 장소를 반복 조회하지 않는다.

- [ ] **추천 서버(`TP_TRAVEL_AI`)와의 질의 템플릿 정합성 점검** — 일부 완료
  - [x] 문서 임베딩 형식: 배치 `build_embedding_text`와 AI 서버 `_build_embedding_text`가 같은 구성(장소명 | 지역 | 카테고리 | 설명 | 태그 | 동행자 | 날씨/계절)임을 확인. 질의는 자연어 문장이라 형식을 맞출 대상이 아님.
  - [ ] 지역 필터: AI 서버는 `region ILIKE '%입력값%'`로 거르는데 배치는 `강원특별자치도 강릉시`처럼 저장한다. 사용자가 "강원도"로 입력하면 0건이 되므로 별칭 매핑 등 맞출 방법 결정 필요.

---

## 2. 외부 API 수집 배치 확장 (Ingestion)

- [ ] **한국관광공사 TourAPI 서비스키 등록 및 수집 테스트**
  - **파일**: `secrets-api.properties`
  - **내용**: 공공데이터포털(data.go.kr) 디코딩 인증키를 `tour.api.serviceKey`에 입력하고 `python -m app.cli ingest-area --dry-run`으로 수집 검증.
  - **참고**: `--dry-run`도 시작 시 DB에 접속하므로 DB 접속 정보가 먼저 설정되어 있어야 한다.

- [ ] **기상청(KMA) 데이터 수집 배치 모듈 구현** — `KMA_PROCESS` 브랜치에서 진행 중 (Kotlin)
  - **내용**: 기상청 API 허브(`apihub.kma.go.kr`)에서 수신한 데이터를 DB 테이블에 정기 적재하는 파이썬 배치 작성.
  - **대상 테이블**:
    - `forecast_zone` (단기예보구역 - `fct_shrt_reg.php` 연동)
    - `short_term_forecast` (단기예보 데이터 연동)
    - `region_location` (행정동 격자 nx, ny 매핑)
  - **현황**: `KMA_PROCESS` 브랜치에 Kotlin으로 2차 커밋까지 진행(지역 데이터 적재, 날씨 데이터 미적재). 이 브랜치는 Kotlin 소스 제거 전 커밋(`5890cef`)에서 갈라져 main(Python)에 그대로 합칠 수 없으므로, Python으로 옮길지 결정 필요.

---

## 3. 실행 환경 및 의존성 관리

- [ ] **임베딩 전용 의존성 패키지 설치**
  - **내용**: 실제 임베딩 및 동기화(`python -m app.cli sync`)를 수행하기 위해 PyTorch 및 SentenceTransformers 라이브러리 설치.
  ```powershell
  pip install -r requirements-embed.txt
  ```

- [x] **배치 자동화 및 스케줄러 설정**
  - `python -m app.cli daily`: refresh → gallery → enrich를 하루치 호출 한도 안에서 1회 실행.
  - `python -m app.cli schedule`: `daily`를 매일 `DAILY_CRON`(기본 04:00 KST)에 실행하는 상주 스케줄러(APScheduler). crontab으로 `daily`를 직접 걸어도 된다(README 참고).
  - 서비스별 일일 호출 수를 `api_call_quota`에 기록하고, `TOUR_API_DAILY_LIMIT`(기본 900)에 닿으면 멈춘다.
  - 기상 정보 수집은 2-2(KMA 배치)가 생기면 `daily`에 추가한다.

---

## 4. 데이터베이스 및 성능 튜닝

- [ ] **pgvector HNSW 인덱스 파라미터 튜닝**
  - **파일**: `app/db.py`
  - **내용**: 장소 데이터가 5만 건 이상 적재된 후 코사인 검색 속도 및 정확도(`ef_search`, `m`) 벤치마크 진행. 현재 `m = 16, ef_construction = 64` 고정, `ef_search`는 미설정.

- [ ] **동기화 증분(Incremental) 업데이트 검증** — 로직 구현 완료, 실데이터 검증 남음
  - **수집**: 전량 수집 후에는 `refresh`가 수정일 최신순으로 읽어 마지막 수정일시 이후 변경분만 받아온다.
  - **동기화**: `source_modified_time` 또는 `detail_version`이 바뀐 장소만 재임베딩한다.
  - **남은 작업**: 실제 운영 데이터로 변경된 장소만 선별되는지 모니터링.

---

## 5. 발견된 버그

- [ ] **결측 장소 때문에 `sync`가 중간에 멈춤**
  - **파일**: `app/jobs/sync_spots.py` (`PENDING_WHERE`, `if not mapped`)
  - **내용**: SQL은 이름·좌표 NULL만 거르고, 지역 정보 없음·좌표 0인 장소는 `map_place_row`에서 건너뛴다. 이 장소들은 `travel_spots`에 들어가지 않아 대기 목록 앞(`ORDER BY p.id`)에 계속 쌓이고, batch 크기(기본 500)만큼 쌓이면 "유효한 장소가 없어 중단"으로 끝난다. 해당 장소는 약 1,970건이라 실제로 발생할 수 있고, `status`의 동기화 대기 건수도 0이 되지 않는다.
  - **방향**: 매핑 제외 조건을 SQL에도 반영하거나, 제외한 장소를 기록해 다음 조회에서 빼기.

- [ ] **수집 도중 실패하면 그 실행에서 받은 페이지를 모두 버림**
  - **파일**: `app/tourapi/client.py` (`fetch_pages`)
  - **내용**: 중간 페이지에서 호출 한도(`QuotaExhausted`)나 오류로 예외가 나면, 앞서 받은 페이지도 저장되지 않고 커서도 그대로다. `daily`는 남은 한도에 맞춰 페이지 수를 줄이므로 영향이 적지만, `ingest-area`/`ingest-gallery`를 직접 돌릴 때는 발생한다.
  - **방향**: 예외 시 그때까지 받은 결과를 돌려주거나, 페이지 단위로 저장·커서 갱신.
