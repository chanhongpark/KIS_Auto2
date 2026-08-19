# ⚡ KIS Auto Trader v2.0

> **한국투자증권(KIS) Open API 기반 알고리즘 주식 자동매매 & Streamlit 실시간 퀀트 관제 터미널**

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.30+-FF4B4B?style=flat&logo=streamlit&logoColor=white)
![KIS OpenAPI](https://img.shields.io/badge/KIS-OpenAPI-007ACC?style=flat)
![AWS EC2](https://img.shields.io/badge/AWS-EC2%20Ready-FF9900?style=flat&logo=amazon-aws&logoColor=white)

---

## 🌟 주요 기능 (Key Features)

- 🌅 **개장 전 자동 스크리닝 (월~금 08:30 KST)**:
  - 100개 대표 주도주 유니버스(코스피200 / 코스닥150 / 대표 ETF) 대상 기술적 지표 퀀트 분석
  - 이동평균선 골든크로스, 정배열, 거래량 급증(20일 이평 대비 1.3배 이상), RSI(14) 반등, 볼린저밴드 하단 지지 등을 종합 점수화하여 Top 5 매수 추천 산출
- 💼 **보유 자산 실시간 리스크 관리 & 스마트 매도 진단**:
  - 목표 익절률(+5%), 손절 기준(-3%), 데드크로스(5일선 하향 돌파), RSI 과열권 이탈 시 실시간 매도 알림
- ⚡ **시장가 / 지정가 원클릭 주문 제어**:
  - 미체결 없는 즉시 시장가 체결 또는 목표 단가를 수정한 지정가 주문 지원
- 📈 **Plotly 3단 대화형 기술적 분석 차트**:
  - 60일 일봉 캔들스틱 + 5/20/60일선 + 볼린저밴드 + 거래량/20일 거래량이평 + RSI(14)
- 🎛️ **다크모드 네온 글로우 5대 멀티페이지 관제 터미널**:
  1. `📊 Overview • 종합 관제`: 총자산/손익 메트릭, Top 3 매수 추천 및 긴급 매도 알림, 보유 주식 리스트
  2. `🎯 Alpha Screener • 매수 발굴`: 100종목 분석 결과 매수 추천 및 3단 인터랙티브 차트
  3. `💼 Portfolio & Risk • 매도 진단`: 보유 주식 현황 및 매도 시그널 감지 원클릭 매도
  4. `⚡ Execution • 주문/체결`: 실시간 접수 및 체결 내역 조회
  5. `⚙️ Settings • 시스템 설정`: 모의/실전 전환, 파라미터 튜닝, 100개 종목 Watchlist 실시간 편집
- ☁️ **AWS EC2 24시간 무중단 백그라운드 운용 (systemd 지원)**

---

## 📁 프로젝트 구조

```
KIS_Auto2/
├── app.py                  # Streamlit 5대 멀티페이지 대시보드
├── kis_api.py              # 한국투자증권 REST API 연동 클라이언트 (OAuth2, 시세, 주문, 잔고)
├── screener.py             # 100종목 퀀트 스크리닝 및 매수/매도 제안 엔진
├── scheduler.py            # 월~금 08:30 KST 백그라운드 크론 스케줄러
├── config.py               # 환경변수, 100개 종목 유니버스 및 런타임 설정 관리
├── settings.json           # 동적 전략 파라미터 및 Watchlist
├── requirements.txt        # 의존성 패키지 목록
├── EC2_DEPLOYMENT.md       # AWS EC2 무중단 배포 가이드
├── kis_trader.service      # systemd 서비스 템플릿
├── start.sh                # 실행 쉘 스크립트
├── .env.example            # 환경변수 템플릿
└── .gitignore              # 보안 제외 파일 목록
```

---

## 🚀 빠른 시작 (Quick Start)

### 1. 환경 설정
```bash
# 가상환경 생성 및 활성화
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt
```

### 2. `.env` 파일 설정
`.env.example`을 복사하여 `.env`를 생성하고 한국투자증권 API 키를 입력합니다.
```env
KIS_APP_KEY=your_app_key
KIS_APP_SECRET=your_app_secret
KIS_CANO=your_8_digit_account_no
KIS_ACNT_PRDT_CD=01
KIS_ACCOUNT_PWD=your_account_password
```

### 3. 대시보드 실행
```bash
streamlit run app.py
```
브라우저에서 `http://localhost:8501` 접속.

---

## ☁️ AWS EC2 배포 (24시간 무중단 자동매매)
자세한 배포 방법은 [EC2_DEPLOYMENT.md](file:///c:/Workspace/KIS_Auto2/EC2_DEPLOYMENT.md)를 참고하세요.
```bash
# systemd 서비스 시작 및 부팅 시 자동 시작 등록
sudo systemctl daemon-reload
sudo systemctl enable kis_trader
sudo systemctl start kis_trader
```

---

## ⚠️ 면책 조항 (Disclaimer)
본 프로그램은 알고리즘에 따른 기술적 분석 및 보조 매매 도구이며, 투자의 최종 결정과 책임은 전적으로 투자자 본인에게 있습니다.
