# TP_BATCH 추가 작업 계획 (TODO)

본 문서는 프로젝트의 안정적인 운영, RAG(검색 증강 생성) 품질 향상, 기상청 및 관광 데이터 파이프라인 확장을 위해 필요한 작업 목록을 정리한 문서입니다.

---

## 1. RAG 및 임베딩 품질 최적화 (우선순위: 높음)

- [ ] **임베딩 텍스트 토큰 잘림(Truncation) 방지 개선**
  - **파일**: `app/mapping.py` (`build_embedding_text`)
  - **내용**: `ko-sroberta`의 512 토큰 제한을 고려하여, 뒤쪽에 배치된 핵심 메타데이터(`태그`, `동행자`, `날씨/계절`)를 `설명(description)`보다 앞쪽에 배치하도록 순서 조정.
  - **내용**: `description`이 수천 자에 달할 경우 앞단 300~400자 수준으로 안전하게 슬라이싱/요약하여 벡터 정보 손실 방지.

- [ ] **상세 개요문(`overview`) 데이터 보강 (Enrichment)**
  - **내용**: 현재 DB에 있는 49,824건의 장소 데이터는 대부분 `overview`가 비어 있어 RAG 시맨틱 검색 정확도가 낮을 수 있음.
  - **작업**: TourAPI 서비스키 등록 후 `python -m app.cli enrich --limit 500` 등을 단계적으로 실행하여 상세 설명 확보.

- [ ] **추천 서버(`TP_TRAVEL_AI`)와의 질의 템플릿 정합성 점검**
  - **내용**: 배치에서 생성하는 임베딩 텍스트 형식과 사용자 질문을 임베딩하는 AI 추천 서버의 포맷이 일치하는지 비교 검증.

---

## 2. 외부 API 수집 배치 확장 (Ingestion)

- [ ] **한국관광공사 TourAPI 서비스키 등록 및 수집 테스트**
  - **파일**: `secrets-api.properties`
  - **내용**: 공공데이터포털(data.go.kr) 디코딩 인증키를 `tour.api.serviceKey`에 입력하고 `python -m app.cli ingest-area --dry-run`으로 수집 검증.

- [ ] **기상청(KMA) 데이터 수집 배치 모듈 구현**
  - **내용**: 기상청 API 허브(`apihub.kma.go.kr`)에서 수신한 데이터를 DB 테이블에 정기 적재하는 파이썬 배치 작성.
  - **대상 테이블**:
    - `forecast_zone` (단기예보구역 - `fct_shrt_reg.php` 연동)
    - `short_term_forecast` (단기예보 데이터 연동)
    - `region_location` (행정동 격자 nx, ny 매핑)

---

## 3. 실행 환경 및 의존성 관리

- [ ] **임베딩 전용 의존성 패키지 설치**
  - **내용**: 실제 임베딩 및 동기화(`python -m app.cli sync`)를 수행하기 위해 PyTorch 및 SentenceTransformers 라이브러리 설치.
  ```powershell
  pip install -r requirements-embed.txt
  ```

- [ ] **배치 자동화 및 스케줄러 설정**
  - **내용**: Windows 작업 스케줄러 또는 Linux Crontab, Celery 등을 활용해 매일 주기적으로 신규 데이터 및 기상 정보 수집 자동화.

---

## 4. 데이터베이스 및 성능 튜닝

- [ ] **pgvector HNSW 인덱스 파라미터 튜닝**
  - **파일**: `app/db.py`
  - **내용**: 장소 데이터가 5만 건 이상 적재된 후 코사인 검색 속도 및 정확도(`ef_search`, `m`) 벤치마크 진행.

- [ ] **동기화 증분(Incremental) 업데이트 검증**
  - **내용**: `place.source_modified_time` 변경 감지 로직이 변경된 장소만 효율적으로 선별하여 재임베딩하는지 모니터링.
