# 만기매칭형 ETF 듀레이션별 수급(Fund Flow) 트래커

상위 만기매칭형 ETF의 상장좌수(Shares) 및 NAV 변동을 추적하여, 가격 평가 손익을 배제한 **실질 자금 순유입액(Fund Flow)**을 계산하고 이를 **잔존 듀레이션 버킷별**로 집계하여 채권 시장 패시브 수급 시그널로 활용하는 트레이딩 데스크 대시보드입니다.

---

## 🛠️ 주요 기능

1. **ETF 유니버스 마스터 관리**: 만기매칭형 ETF 종목 정보 및 타겟 만기 청산일 지정 (`config/etf_universe.json`)
2. **실시간 KRX / 네이버 금융 라이브 데이터 수집**: `pykrx` 및 네이버 금융 스크래핑을 통한 일별 상장좌수, NAV, AUM 자동 수집
3. **실질 순유입액 & 잔존 듀레이션 산출**: 
   $$\text{Net Fund Flow}_t = (\text{Shares}_t - \text{Shares}_{t-1}) \times \text{NAV}_{t-1}$$
   $$\text{Duration}_t = \frac{\text{Target Date} - \text{Current Date}}{365.25}$$
4. **듀레이션 버킷 및 이동평균**: `0.5Y 이하`, `1.0Y 구간`, `1.5Y 구간`, `2.0Y 이상` 버킷 분류 및 3일/5일 이동평균 유입액 처리
5. **Streamlit 다크모드 트레이딩 대시보드**: Plotly 기반 듀레이션 버킷별 수급 차트, 개별 ETF 좌수/수급 연동 차트, 최근 5일 요약 테이블 제공

---

## 📂 프로젝트 구조

```text
c:/Users/Check/Downloads/만기매칭형 ETF/
├── config/
│   └── etf_universe.json       # 10개 만기매칭형 ETF 종목 및 만기일 정의
├── data/
│   └── tracker.db              # SQLite 데이터베이스
├── src/
│   ├── __init__.py
│   ├── db_manager.py           # DB 관리 및 CRUD 모듈
│   ├── collector.py            # PyKRX / 네이버 금융 데이터 수집기
│   └── processor.py            # Fund Flow 및 듀레이션 산출 로직
├── app.py                      # Streamlit 메인 대시보드
├── requirements.txt            # 의존성 라이브러리
└── README.md
```

---

## 🚀 실행 방법

### 1. 패키지 설치
```bash
pip install -r requirements.txt
```

### 2. 데이터베이스 초기화 및 데이터 수집
```bash
python -m src.db_manager
python -m src.collector
python -m src.processor
```

### 3. Streamlit 대시보드 실행
```bash
streamlit run app.py
```
