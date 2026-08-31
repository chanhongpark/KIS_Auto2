"""
KIS Auto Trading - Configuration Module
환경 변수, API 인증 정보 및 전략/스크리닝 설정 관리
Atomic JSON 저장 및 스레드 안전 설정 로드 지원
"""
import os
import json
import logging
import threading
from typing import Any, Dict, Optional
from core.storage import safe_load_json, atomic_save_json

# 로깅 기본 설정 (KST 기준)
class KSTFormatter(logging.Formatter):
    """한국 표준시(KST) 기준으로 로그 타임스탬프를 출력하는 Formatter"""
    def formatTime(self, record, datefmt=None):
        from time_utils import now
        dt = now()
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime('%Y-%m-%d %H:%M:%S')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] (%(name)s) %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
for handler in logging.getLogger().handlers:
    handler.setFormatter(KSTFormatter(fmt='%(asctime)s [%(levelname)s] (%(name)s) %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
logger = logging.getLogger("Config")

# .env 로드
ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(ENV_PATH):
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and k not in os.environ:
                        os.environ[k] = v
    except Exception as e:
        logger.warning(f".env 로드 실패: {e}")

# KIS API 계정 정보
APP_KEY = os.getenv("KIS_APP_KEY", "")
APP_SECRET = os.getenv("KIS_APP_SECRET", "")
CANO = os.getenv("KIS_CANO", "")
ACNT_PRDT_CD = os.getenv("KIS_ACNT_PRDT_CD", "01")
ACCOUNT_PWD = os.getenv("KIS_ACCOUNT_PWD", "")

# 텔레그램 알림 설정
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# API 엔드포인트 URL
URL_BASE_MOCK = "https://openapivts.koreainvestment.com:29443"
URL_BASE_REAL = "https://openapi.koreainvestment.com:9443"

# 설정 파일 경로
SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "settings.json")

# 기본 전략 및 시스템 파라미터
DEFAULT_SETTINGS: Dict[str, Any] = {
    "mock_trading": True,                    # 모의투자 여부 (True: 모의, False: 실전)
    "target_profit_rate": 0.05,             # 목표 익절 수익률 (+5%)
    "stop_loss_rate": -0.03,                # 손절 수익률 (-3%)
    "max_buy_budget_per_stock": 500000,     # 1종목당 최대 매수 한도 (원)
    "max_holding_stocks": 5,                # 최대 보유 종목 수
    "premarket_time": "08:30",              # 개장 전 자동 스크리닝 시각 (KST)
    "auto_execute_orders": False,           # 주문 완전 자동화 여부 (False: UI 원클릭 승인)
    "telegram_enabled": False,              # 텔레그램 알림 활성화 여부 (기본: OFF)

    # --- 스크리닝 점수 카테고리별 상한 (Cap) ---
    "score_cap_trend": 40,                  # 추세군(이동평균) 최대 점수 상한
    "score_cap_momentum": 30,               # 모멘텀군(RSI, 볼린저) 최대 점수 상한
    "score_cap_volume": 25,                 # 거래량군 최대 점수 상한
    "buy_score_threshold": 45,              # 매수 추천 최소 종합 점수 (45점 이상 추천)

    # --- 실시간 봉 반영 설정 ---
    "use_realtime_candle": False,           # 실시간 현재가를 일봉에 반영할지 여부 (False: 완성봉만 사용)

    # --- 분할 매도 및 트레일링 스탑 설정 ---
    "partial_sell_ratio": 0.5,              # 1차 익절 시 매도 비율 (50%)
    "trailing_stop_pct": 0.035,             # 1차 익절 후 최고가 대비 트레일링 스탑 비율 (3.5%)
    "rsi_overbought_sell": False,           # RSI 과열 시 전량 매도 여부 (False: 분할 매도만)

    # --- 타임컷 (Time-based Exit / 기간 청산) ---
    "time_stop_enabled": True,              # 타임컷 청산 활성화
    "time_stop_days": 6,                    # 타임컷 보유 일수 (6영업일)
    "time_stop_min_profit": 0.02,           # 타임컷 기준 최소 수익률 (+2%)

    # --- 1일 최대 신규 매수 제한 ---
    "max_daily_buy_count": 2,               # 1일 최대 신규 매수 종목 수 (집단 갭하락 리스크 방어)

    # --- 변동성 조절 포지션 사이징 ---
    "volatility_sizing_enabled": True,      # ATR 기반 변동성 조절 포지션 사이징 활성화
    "atr_period": 14,                       # ATR 계산 기간
    "risk_per_trade": 0.01,                 # 1회 거래당 리스크 비율 (계좌 대비 1%)
    "atr_stop_multiple": 2.0,               # ATR 기반 손절 배수 (2배 ATR)
    "max_position_ratio": 0.3,              # 1종목당 최대 포지션 비율 (계좌 대비 30%)
    "min_position_ratio": 0.05,             # 1종목당 최소 포지션 비율 (계좌 대비 5%)

    # --- 시장 국면 필터 (Market Regime Filter) ---
    "market_regime_filter_enabled": True,   # 시장 국면 필터 활성화
    "market_regime_ma_period": 20,          # 시장 국면 판단 이동평균 기간 (20일)
    "market_regime_cutoff_normal": 45,      # 정상 국면 매수 점수 컷오프
    "market_regime_cutoff_weak": 70,        # 약세 국면 매수 점수 컷오프 (상향)
    "market_regime_block_weak": False,       # 약세 국면 신규 진입 전면 차단 여부

    # --- 손절 종목 쿨다운 (Cool-down) ---
    "cooldown_enabled": True,               # 손절 종목 쿨다운 활성화
    "cooldown_days": 4,                     # 손절 후 재매수 금지 기간 (거래일 기준 3~5일)

    # --- ATR 동적 손절 (변동성 기반 손절가) ---
    "atr_stop_loss_enabled": True,          # ATR 기반 동적 손절 활성화
    "atr_stop_loss_multiple": 2.0,          # ATR 손절 배수 (진입가 - 2×ATR)
    "atr_stop_loss_min_pct": -0.05,         # ATR 손절 최소 허용 손실률 (-5% 하한)
    "atr_stop_loss_max_pct": -0.01,         # ATR 손절 최대 허용 손실률 (-1% 상한)
    "atr_stop_loss_use_low_break": True,    # 당일 저가 이탈 시 손절 적용 여부
    "watchlist": [
        {"code": "005930", "name": "삼성전자", "market": "KOSPI"},
        {"code": "000660", "name": "SK하이닉스", "market": "KOSPI"},
        {"code": "373220", "name": "LG에너지솔루션", "market": "KOSPI"},
        {"code": "207940", "name": "삼성바이오로직스", "market": "KOSPI"},
        {"code": "005380", "name": "현대차", "market": "KOSPI"},
        {"code": "000270", "name": "기아", "market": "KOSPI"},
        {"code": "068270", "name": "셀트리온", "market": "KOSPI"},
        {"code": "035420", "name": "NAVER", "market": "KOSPI"},
        {"code": "105560", "name": "KB금융", "market": "KOSPI"},
        {"code": "055550", "name": "신한지주", "market": "KOSPI"},
        {"code": "005490", "name": "POSCO홀딩스", "market": "KOSPI"},
        {"code": "012330", "name": "현대모비스", "market": "KOSPI"},
        {"code": "006400", "name": "삼성SDI", "market": "KOSPI"},
        {"code": "051910", "name": "LG화학", "market": "KOSPI"},
        {"code": "028260", "name": "삼성물산", "market": "KOSPI"},
        {"code": "086790", "name": "하나금융지주", "market": "KOSPI"},
        {"code": "035720", "name": "카카오", "market": "KOSPI"},
        {"code": "012450", "name": "한화에어로스페이스", "market": "KOSPI"},
        {"code": "267260", "name": "HD현대일렉트릭", "market": "KOSPI"},
        {"code": "329180", "name": "HD현대중공업", "market": "KOSPI"},
        {"code": "034020", "name": "두산에너빌리티", "market": "KOSPI"},
        {"code": "196170", "name": "알테오젠", "market": "KOSDAQ"},
        {"code": "247540", "name": "에코프로비엠", "market": "KOSDAQ"},
        {"code": "086520", "name": "에코프로", "market": "KOSDAQ"},
        {"code": "028300", "name": "HLB", "market": "KOSDAQ"},
        {"code": "066570", "name": "LG전자", "market": "KOSPI"},
        {"code": "009150", "name": "삼성전기", "market": "KOSPI"},
        {"code": "018260", "name": "삼성에스디에스", "market": "KOSPI"},
        {"code": "032830", "name": "삼성생명", "market": "KOSPI"},
        {"code": "000810", "name": "삼성화재", "market": "KOSPI"},
        {"code": "316140", "name": "우리금융지주", "market": "KOSPI"},
        {"code": "138040", "name": "메리츠금융지주", "market": "KOSPI"},
        {"code": "003670", "name": "포스코퓨처엠", "market": "KOSPI"},
        {"code": "042700", "name": "한미반도체", "market": "KOSPI"},
        {"code": "010130", "name": "고려아연", "market": "KOSPI"},
        {"code": "047810", "name": "한국항공우주", "market": "KOSPI"},
        {"code": "064350", "name": "현대로템", "market": "KOSPI"},
        {"code": "010140", "name": "삼성중공업", "market": "KOSPI"},
        {"code": "042660", "name": "한화오션", "market": "KOSPI"},
        {"code": "259960", "name": "크래프톤", "market": "KOSPI"},
        {"code": "352820", "name": "하이브", "market": "KOSPI"},
        {"code": "000100", "name": "유한양행", "market": "KOSPI"},
        {"code": "128940", "name": "한미약품", "market": "KOSPI"},
        {"code": "326030", "name": "SK바이오팜", "market": "KOSPI"},
        {"code": "302440", "name": "SK바이오사이언스", "market": "KOSPI"},
        {"code": "096770", "name": "SK이노베이션", "market": "KOSPI"},
        {"code": "010950", "name": "S-Oil", "market": "KOSPI"},
        {"code": "011200", "name": "HMM", "market": "KOSPI"},
        {"code": "003490", "name": "대한항공", "market": "KOSPI"},
        {"code": "086280", "name": "현대글로비스", "market": "KOSPI"},
        {"code": "034730", "name": "SK", "market": "KOSPI"},
        {"code": "003550", "name": "LG", "market": "KOSPI"},
        {"code": "241560", "name": "두산밥캣", "market": "KOSPI"},
        {"code": "454910", "name": "두산로보틱스", "market": "KOSPI"},
        {"code": "015760", "name": "한국전력", "market": "KOSPI"},
        {"code": "030200", "name": "KT", "market": "KOSPI"},
        {"code": "017670", "name": "SK텔레콤", "market": "KOSPI"},
        {"code": "033780", "name": "KT&G", "market": "KOSPI"},
        {"code": "051900", "name": "LG생활건강", "market": "KOSPI"},
        {"code": "090430", "name": "아모레퍼시픽", "market": "KOSPI"},
        {"code": "097950", "name": "CJ제일제당", "market": "KOSPI"},
        {"code": "006800", "name": "미래에셋증권", "market": "KOSPI"},
        {"code": "071050", "name": "한국금융지주", "market": "KOSPI"},
        {"code": "024110", "name": "기업은행", "market": "KOSPI"},
        {"code": "039490", "name": "키움증권", "market": "KOSPI"},
        {"code": "403870", "name": "HPSP", "market": "KOSDAQ"},
        {"code": "058470", "name": "리노공업", "market": "KOSDAQ"},
        {"code": "039030", "name": "이오테크닉스", "market": "KOSDAQ"},
        {"code": "095610", "name": "테스", "market": "KOSDAQ"},
        {"code": "067310", "name": "하나마이크론", "market": "KOSDAQ"},
        {"code": "000990", "name": "DB하이텍", "market": "KOSPI"},
        {"code": "036540", "name": "SFA반도체", "market": "KOSDAQ"},
        {"code": "041510", "name": "에스엠", "market": "KOSDAQ"},
        {"code": "035900", "name": "JYP Ent.", "market": "KOSDAQ"},
        {"code": "122870", "name": "와이지엔터테인먼트", "market": "KOSDAQ"},
        {"code": "263750", "name": "펄어비스", "market": "KOSDAQ"},
        {"code": "293490", "name": "카카오게임즈", "market": "KOSDAQ"},
        {"code": "251270", "name": "넷마블", "market": "KOSPI"},
        {"code": "036570", "name": "엔씨소프트", "market": "KOSPI"},
        {"code": "000080", "name": "하이트진로", "market": "KOSPI"},
        {"code": "004020", "name": "현대제철", "market": "KOSPI"},
        {"code": "047050", "name": "포스코인터내셔널", "market": "KOSPI"},
        {"code": "086900", "name": "메디톡스", "market": "KOSDAQ"},
        {"code": "145020", "name": "휴젤", "market": "KOSDAQ"},
        {"code": "214150", "name": "클래시스", "market": "KOSDAQ"},
        {"code": "068760", "name": "셀트리온제약", "market": "KOSDAQ"},
        {"code": "000250", "name": "삼천당제약", "market": "KOSDAQ"},
        {"code": "237690", "name": "에스티팜", "market": "KOSDAQ"},
        {"code": "141080", "name": "리가켐바이오", "market": "KOSDAQ"},
        {"code": "277810", "name": "레인보우로보틱스", "market": "KOSDAQ"},
        {"code": "348370", "name": "엔켐", "market": "KOSDAQ"},
        {"code": "066970", "name": "엘앤에프", "market": "KOSPI"},
        {"code": "005420", "name": "코스모신소재", "market": "KOSPI"},
        {"code": "450080", "name": "에코프로머티", "market": "KOSPI"},
        {"code": "011070", "name": "LG이노텍", "market": "KOSPI"},
        {"code": "034220", "name": "LG디스플레이", "market": "KOSPI"},
        {"code": "069500", "name": "KODEX 200", "market": "ETF"},
        {"code": "122630", "name": "KODEX 레버리지", "market": "ETF"},
        {"code": "233740", "name": "KODEX 코스닥150레버리지", "market": "ETF"},
        {"code": "114800", "name": "KODEX 인버스", "market": "ETF"}
    ]
}

_config_lock = threading.Lock()

def load_settings() -> Dict[str, Any]:
    """settings.json에서 설정을 로드하거나 없으면 기본값 생성"""
    with _config_lock:
        saved = safe_load_json(SETTINGS_FILE, default=None)
        if saved is not None and isinstance(saved, dict):
            res = DEFAULT_SETTINGS.copy()
            res.update(saved)
            return res
        # 기본값 파일 저장
        atomic_save_json(SETTINGS_FILE, DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()

def save_settings(new_settings: Dict[str, Any]) -> bool:
    """settings.json 파일에 설정 저장"""
    with _config_lock:
        ok = atomic_save_json(SETTINGS_FILE, new_settings)
        if ok:
            CURRENT_SETTINGS.clear()
            CURRENT_SETTINGS.update(new_settings)
        return ok

# 현재 활성화된 런타임 설정
CURRENT_SETTINGS: Dict[str, Any] = load_settings()

def get_setting(key: str, default: Any = None) -> Any:
    return CURRENT_SETTINGS.get(key, default)

def get_url_base() -> str:
    is_mock = CURRENT_SETTINGS.get("mock_trading", True)
    return URL_BASE_MOCK if is_mock else URL_BASE_REAL
