# 만기매칭형(존속기한형) ETF 수급 및 상장좌수 트래커 - 개발 명세서 (Technical Specification)

이 문서는 본 프로젝트의 아키텍처, 데이터 파이프라인 흐름, 핵심 연산 로직 및 향후 확장(Scale-up)을 위한 기술적 가이드라인을 정의합니다.

---

## 1. 프로젝트 개요 (Project Overview)
본 시스템은 한국 주식시장에 상장된 **만기매칭형(Target-Maturity) 크레딧 채권 ETF**의 실시간 상장좌수(Shares Outstanding) 및 자금 유출입(Fund Flow)을 추적하고, 이를 잔존 듀레이션(Duration) 버킷별, 종목별로 분석하는 자동화 대시보드입니다. 

- **핵심 목표:** 가격 등락으로 인한 평가 손익(Capital Gain/Loss)의 착시를 제거하고, 실제 시장에서 ETF로 밀려 들어오고 나가는 **'실물 상장좌수 증감(Creation/Redemption)'**과 **'실질 자금 순유입액(Real Net Flow)'**을 동시에 추적합니다.
- **주요 기술 스택:** Python 3, SQLite3, Pandas, Streamlit, Plotly, Windows Task Scheduler

---

## 2. 시스템 아키텍처 (System Architecture)

본 시스템은 크게 4개의 모듈로 분리되어 있으며, 상호 독립적으로 작동하도록 설계되었습니다.

### 2.1. 데이터 수집기 (`src/collector.py`)
- **역할:** 시장 데이터의 동적 탐색 및 실시간 상장좌수 수집
- **주요 로직 (Dynamic Discovery & Exact Shares Extraction):**
  1. 네이버 금융 라이브 API(`etfItemList.nhn`)를 호출해 상장된 전체 ETF(약 1,150여 개) 리스트를 메모리에 로드합니다.
  2. 정규식(`r'(\d{2})-(\d{2})'`)을 사용해 종목명에 만기 연월이 포함된 '존속기한형 ETF'만 100% 자동으로 필터링합니다.
  3. 필터링된 ETF 중 **순자산(AUM) 기준 상위 10개**를 동적으로 선정합니다.
  4. 네이버 금융 종목 메인 페이지 HTML을 직접 스크래핑(`fetch_exact_shares_naver()`)하여 **단 1좌의 오차도 없는 100% 실시간 상장주식수(상장좌수)**를 추출합니다.
  5. 네이버 차트 API(`fchart.stock.naver.com`)를 호출하여 과거 시계열 데이터와 결합한 후 DB에 저장합니다.

### 2.2. 데이터베이스 매니저 (`src/db_manager.py`)
- **역할:** SQLite 기반 로컬 데이터 웨어하우스 관리 (`data/tracker.db`)
- **주요 테이블 스키마:**
  - `etf_master`: 동적으로 탐색된 ETF 유니버스 (티커, 종목명, 목표 만기일, 자산군). 수집기가 돌 때마다 `UPSERT` 방식으로 자동 갱신됩니다.
  - `daily_etf_raw`: 일별 원천 데이터 (`date`, `ticker`, `shares_outstanding`, `nav`, `aum`). 복합 키 `(date, ticker)`로 일별 스냅샷을 영구 보존합니다.
  - `duration_flow_daily`: 가공된 데이터 (잔존 듀레이션, 상장좌수 변동량 `net_shares_change`, 순유입액 `net_fund_flow`, 3일/5일 이동평균).

### 2.3. 데이터 연산 프로세서 (`src/processor.py`)
- **역할:** 핵심 비즈니스 로직(Fund Flow, Shares Change 및 Duration) 연산
- **핵심 공식 (Core Formulas):**
  - **상장좌수 변동(Net Shares Change):** `오늘 상장좌수 - 어제 상장좌수`
  - **순유입액(Net Fund Flow):** `(오늘 상장좌수 - 어제 상장좌수) × 어제 NAV`
    *(어제 종가 기준으로 오늘 좌수가 늘어났다면, 그만큼의 현금이 지정참가회사(LP)를 통해 설정(Creation)되었다고 간주함)*
  - **잔존 듀레이션(Duration):** `(ETF 목표 만기일 - 연산 당일 날짜) ÷ 365.25`
  - **버킷 분류(Bucketing):** 잔존 듀레이션을 기준(0.5Y 이하, 1.0Y 구간, 1.5Y 구간, 2.0Y 이상)으로 범주화하여 거시적 분석 레이어를 제공합니다.

### 2.4. 시각화 대시보드 (`app.py`)
- **역할:** Streamlit 기반 인터랙티브 UI 및 분석 뷰 제공
- **구조:** 종목(Ticker) 중심 뷰 & 상장좌수 트래킹 강화
  - 사이드바 필터를 통해 특정 기간 내 데이터를 동적으로 슬라이싱(Slicing) 및 랭킹 정렬(AUM순, 만기순)합니다.
  - 상단 KPI 카드로 **'기간 내 상장좌수 변동'**과 **'총 순유입액'**을 동시 노출합니다.
  - 현황 요약 테이블에서 `현재 상장좌수(좌)`와 `기간 내 좌수 변동(좌)`을 직관적으로 표출합니다.

---

## 3. 백그라운드 자동화 파이프라인 (Automation Pipeline)
서버를 띄우지 않는 로컬 PC 환경에서도 365일 무인 동작하도록 Windows 배치 스크립트 기반 자동화가 구축되어 있습니다.

- **`run_daily_sync.bat`**: UI를 띄우지 않고 `collector`와 `processor`만 백그라운드에서 순차 실행하는 Headless 스크립트.
- **`setup_task_scheduler.bat`**: 위 동기화 스크립트를 윈도우 작업 스케줄러(Task Scheduler)에 등록하여, 매일 한국 증시 마감 후인 **오후 4시(16:00)**에 자동 실행되도록 세팅합니다.
- **`run_tracker.bat`**: 사용자가 분석을 원할 때 Streamlit 웹 브라우저를 띄워주는 런처입니다.

---

## 4. 향후 추가 개발 및 확장 포인트 (Scale-up Guide)

본 시스템은 모듈화가 잘 되어 있어 기능 추가가 용이합니다. 다음은 향후 고도화 시 참고할 가이드라인입니다.

### 4.1. 크레딧 스프레드(Credit Spread) 데이터 연동
- **목표:** 자금 유입(Fund Flow) 및 상장좌수 증감과 크레딧 스프레드 축소/확대 간의 상관관계(Correlation) 분석.
- **개발 방안:**
  - `src/collector.py`에 K-Bond(금융투자협회) 또는 Koscom API 연동 모듈을 추가하여 '신용등급별(AA-, A+ 등) 회사채 시장 금리'를 일별로 수집합니다.
  - 무위험 지표금리(국고채 3년물 등)와의 차이(Spread)를 계산하여 `daily_market_macro` 테이블(신설)에 적재합니다.

### 4.2. 펀드 유니버스 동적 탐색 튜닝
- 현재 `collector.py`의 `discover_maturity_matching_etfs()` 함수는 펀드명 내 `YY-MM` 정규식과 특정 키워드(회사채, 은행채 등)를 기반으로 Asset Class를 분류하고 있습니다.
- 향후 새로운 자산군(예: '여전채', '미국채')이 상장될 경우, 해당 함수 내부의 `if/elif` 키워드 매칭 로직에 단어만 한 줄 추가해 주면 DB 테이블 스키마 변경 없이 완벽하게 자동 편입됩니다.

### 4.3. 투자자별(기관/외인) 매매동향 파싱
- 네이버 `sise_invest.naver` 웹 크롤링을 통해 일별 기관/외인 순매수 추이를 `daily_etf_raw`에 추가 컬럼으로 적재하여 수급의 주체(Who) 분석을 확장할 수 있습니다.
