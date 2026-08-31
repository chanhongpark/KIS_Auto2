"""
KIS Auto Trading - Configuration Module
환경 변수, API 인증 정보 및 전략/스크리닝 설정 관리
시장 국면별 3대 프리셋(BULL, VOLATILE, BEAR) 및 지수 연동 자동 감지(AUTO) 지원
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

# ==============================================================================
# 시장 국면별 3대 프리셋 정의 (Market Regime Presets)
# ==============================================================================
MARKET_REGIME_PRESETS: Dict[str, Dict[str, Any]] = {
    "BULL": {
        "name": "🔥 상승장 모드 (Bull Trend)",
        "description": "추세 추종 및 이익 극대화 (목표익절 +8%~+10%, 20일선 트레일링, ATR 2.2배 손절 -5.0%, 타임컷 12일)",
        "target_profit_rate": 0.08,
        "stop_loss_rate": -0.05,
        "trailing_stop_pct": 0.06,
        "time_stop_days": 12,
        "time_stop_min_profit": 0.02,
        "buy_score_threshold": 45,
        "market_regime_cutoff_normal": 45,
        "market_regime_cutoff_weak": 70,
        "max_daily_buy_count": 3,
        "atr_stop_loss_multiple": 2.2,
        "atr_stop_loss_min_pct": -0.055,
        "atr_stop_loss_max_pct": -0.035
    },
    "VOLATILE": {
        "name": "⚡ 변동성/횡보장 모드 (Volatile)",
        "description": "박스권 순환매 & 빠른 차익 실현 (목표익절 +5%, 트레일링 3.5%, 손절 -3.5%, 타임컷 6일)",
        "target_profit_rate": 0.05,
        "stop_loss_rate": -0.035,
        "trailing_stop_pct": 0.035,
        "time_stop_days": 6,
        "time_stop_min_profit": 0.02,
        "buy_score_threshold": 55,
        "market_regime_cutoff_normal": 55,
        "market_regime_cutoff_weak": 70,
        "max_daily_buy_count": 2,
        "atr_stop_loss_multiple": 2.0,
        "atr_stop_loss_min_pct": -0.045,
        "atr_stop_loss_max_pct": -0.025
    },
    "BEAR": {
        "name": "🛡️ 하락장/방어 모드 (Bear Defense)",
        "description": "원금 보존 & 타이트한 초긴급 방어 (목표익절 +3%, 트레일링 2.0%, 칼손절 -2.5%, 컷오프 70점, 타임컷 3일)",
        "target_profit_rate": 0.03,
        "stop_loss_rate": -0.025,
        "trailing_stop_pct": 0.02,
        "time_stop_days": 3,
        "time_stop_min_profit": 0.01,
        "buy_score_threshold": 70,
        "market_regime_cutoff_normal": 70,
        "market_regime_cutoff_weak": 75,
        "max_daily_buy_count": 1,
        "atr_stop_loss_multiple": 1.5,
        "atr_stop_loss_min_pct": -0.035,
        "atr_stop_loss_max_pct": -0.020
    }
}

# 기본 전략 및 시스템 파라미터
DEFAULT_SETTINGS: Dict[str, Any] = {
    "mock_trading": True,                    # 모의투자 여부 (True: 모의, False: 실전)
    "regime_preset_mode": "AUTO",            # 국면 모드: 'AUTO'(지수 자동감지), 'BULL', 'VOLATILE', 'BEAR', 'CUSTOM'
    "target_profit_rate": 0.08,             # 목표 익절 수익률 (+8.0%)
    "stop_loss_rate": -0.05,                # 손절 수익률 (-5.0%)
    "max_buy_budget_per_stock": 500000,     # 1종목당 최대 매수 한도 (원)
    "max_holding_stocks": 5,                # 최대 보유 종목 수
    "premarket_time": "15:15",              # 종가 매수 스크리닝 시각 (KST)
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
    "trailing_stop_pct": 0.06,              # 1차 익절 후 최고가 대비 트레일링 스탑 비율 (6.0%)
    "rsi_overbought_sell": False,           # RSI 과열 시 전량 매도 여부 (False: 분할 매도만)

    # --- 타임컷 (Time-based Exit / 기간 청산) ---
    "time_stop_enabled": True,              # 타임컷 청산 활성화
    "time_stop_days": 12,                   # 타임컷 보유 일수 (12영업일)
    "time_stop_min_profit": 0.02,           # 타임컷 기준 최소 수익률 (+2%)

    # --- 1일 최대 신규 매수 제한 ---
    "max_daily_buy_count": 2,               # 1일 최대 신규 매수 종목 수 (집단 갭하락 리스크 방어)

    # --- 변동성 조절 포지션 사이징 ---
    "volatility_sizing_enabled": True,      # ATR 기반 변동성 조절 포지션 사이징 활성화
    "atr_period": 14,                       # ATR 계산 기간
    "risk_per_trade": 0.01,                 # 1회 거래당 리스크 비율 (계좌 대비 1%)
    "atr_stop_multiple": 2.2,               # ATR 기반 손절 배수 (2.2배 ATR)
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
    "cooldown_days": 4,                     # 손절 후 재매수 금지 기간 (거래일 기준 4일)

    # --- ATR 동적 손절 (변동성 기반 손절가) ---
    "atr_stop_loss_enabled": True,          # ATR 기반 동적 손절 활성화
    "atr_stop_loss_multiple": 2.2,          # ATR 손절 배수 (진입가 - 2.2×ATR)
    "atr_stop_loss_min_pct": -0.055,        # ATR 손절 최소 허용 손실률 (-5.5% 하한)
    "atr_stop_loss_max_pct": -0.035,        # ATR 손절 최대 허용 손실률 (-3.5% 상한)
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
        {"code": "010130", "name": "고려아연", "market": "KOSPI"},
        {"code": "003670", "name": "포스코퓨처엠", "market": "KOSPI"},
        {"code": "032830", "name": "삼성생명", "market": "KOSPI"},
        {"code": "012450", "name": "한화에어로스페이스", "market": "KOSPI"},
        {"code": "011200", "name": "HMM", "market": "KOSPI"},
        {"code": "066570", "name": "LG전자", "market": "KOSPI"},
        {"code": "009150", "name": "삼성전기", "market": "KOSPI"},
        {"code": "010950", "name": "S-Oil", "market": "KOSPI"},
        {"code": "034020", "name": "두산에너빌리티", "market": "KOSPI"},
        {"code": "018260", "name": "삼성에스디에스", "market": "KOSPI"},
        {"code": "003550", "name": "LG", "market": "KOSPI"},
        {"code": "033780", "name": "KT&G", "market": "KOSPI"},
        {"code": "000810", "name": "삼성화재", "market": "KOSPI"},
        {"code": "017670", "name": "SK텔레콤", "market": "KOSPI"},
        {"code": "030200", "name": "KT", "market": "KOSPI"},
        {"code": "090430", "name": "아모레퍼시픽", "market": "KOSPI"},
        {"code": "015760", "name": "한국전력", "market": "KOSPI"},
        {"code": "024110", "name": "기업은행", "market": "KOSPI"},
        {"code": "316140", "name": "우리금융지주", "market": "KOSPI"},
        {"code": "000100", "name": "유한양행", "market": "KOSPI"},
        {"code": "071050", "name": "한국금융지주", "market": "KOSPI"},
        {"code": "003490", "name": "대한항공", "market": "KOSPI"},
        {"code": "034730", "name": "SK", "market": "KOSPI"},
        {"code": "096770", "name": "SK이노베이션", "market": "KOSPI"},
        {"code": "326030", "name": "SK바이오팜", "market": "KOSPI"},
        {"code": "329180", "name": "HD현대중공업", "market": "KOSPI"},
        {"code": "042660", "name": "한화오션", "market": "KOSPI"},
        {"code": "010140", "name": "삼성중공업", "market": "KOSPI"},
        {"code": "047810", "name": "한국항공우주", "market": "KOSPI"},
        {"code": "086280", "name": "현대글로비스", "market": "KOSPI"},
        {"code": "042700", "name": "한미반도체", "market": "KOSPI"},
        {"code": "259960", "name": "크래프톤", "market": "KOSPI"},
        {"code": "352820", "name": "하이브", "market": "KOSPI"},
        {"code": "247540", "name": "에코프로비엠", "market": "KOSDAQ"},
        {"code": "086520", "name": "에코프로", "market": "KOSDAQ"},
        {"code": "028300", "name": "HLB", "market": "KOSDAQ"},
        {"code": "058470", "name": "리노공업", "market": "KOSDAQ"},
        {"code": "277810", "name": "레인보우로보틱스", "market": "KOSDAQ"},
        {"code": "196170", "name": "알테오젠", "market": "KOSDAQ"},
        {"code": "068760", "name": "셀트리온제약", "market": "KOSDAQ"},
        {"code": "214150", "name": "클래시스", "market": "KOSDAQ"},
        {"code": "293490", "name": "카카오게임즈", "market": "KOSDAQ"},
        {"code": "035900", "name": "JYP Ent.", "market": "KOSDAQ"},
        {"code": "041510", "name": "에스엠", "market": "KOSDAQ"},
        {"code": "263750", "name": "펄어비스", "market": "KOSDAQ"},
        {"code": "039030", "name": "이오테크닉스", "market": "KOSDAQ"},
        {"code": "036540", "name": "SFA반도체", "market": "KOSDAQ"},
        {"code": "241560", "name": "두산테스나", "market": "KOSDAQ"},
        {"code": "095610", "name": "테스", "market": "KOSDAQ"},
        {"code": "000080", "name": "하이트진로", "market": "KOSPI"},
        {"code": "000250", "name": "삼천당제약", "market": "KOSDAQ"},
        {"code": "000990", "name": "DB하이텍", "market": "KOSPI"},
        {"code": "004020", "name": "현대제철", "market": "KOSPI"},
        {"code": "005420", "name": "코스모화학", "market": "KOSPI"},
        {"code": "006800", "name": "미래에셋증권", "market": "KOSPI"},
        {"code": "011070", "name": "LG이노텍", "market": "KOSPI"},
        {"code": "034220", "name": "LG디스플레이", "market": "KOSPI"},
        {"code": "036570", "name": "엔씨소프트", "market": "KOSPI"},
        {"code": "039490", "name": "키움증권", "market": "KOSPI"},
        {"code": "047050", "name": "포스코인터내셔널", "market": "KOSPI"},
        {"code": "051900", "name": "LG생활건강", "market": "KOSPI"},
        {"code": "064350", "name": "현대로템", "market": "KOSPI"},
        {"code": "066970", "name": "엘앤에프", "market": "KOSDAQ"},
        {"code": "067310", "name": "하나마이크론", "market": "KOSDAQ"},
        {"code": "086900", "name": "메디톡스", "market": "KOSDAQ"},
        {"code": "097950", "name": "CJ제일제당", "market": "KOSPI"},
        {"code": "122870", "name": "와이지엔터테인먼트", "market": "KOSDAQ"},
        {"code": "128940", "name": "한미약품", "market": "KOSPI"},
        {"code": "138040", "name": "메리츠금융지주", "market": "KOSPI"},
        {"code": "141080", "name": "레고켐바이오", "market": "KOSDAQ"},
        {"code": "145020", "name": "휴젤", "market": "KOSDAQ"},
        {"code": "237690", "name": "에스티팜", "market": "KOSDAQ"},
        {"code": "251270", "name": "넷마블", "market": "KOSPI"},
        {"code": "267260", "name": "HD현대일렉트릭", "market": "KOSPI"},
        {"code": "302440", "name": "SK바이오사이언스", "market": "KOSPI"},
        {"code": "348370", "name": "엔켐", "market": "KOSDAQ"},
        {"code": "403870", "name": "HPSP", "market": "KOSDAQ"},
        {"code": "450080", "name": "두산로보틱스", "market": "KOSPI"},
        {"code": "454910", "name": "두산밥캣", "market": "KOSPI"},
        {"code": "069500", "name": "KODEX 200", "market": "ETF"},
        {"code": "122630", "name": "KODEX 레버리지", "market": "ETF"},
        {"code": "233740", "name": "KODEX 코스닥150레버리지", "market": "ETF"},
        {"code": "114800", "name": "KODEX 인버스", "market": "ETF"}
    ]
}

_settings_lock = threading.Lock()
_cached_settings: Optional[Dict[str, Any]] = None

def load_settings() -> Dict[str, Any]:
    global _cached_settings
    with _settings_lock:
        if _cached_settings is not None:
            return _cached_settings

        loaded = safe_load_json(SETTINGS_FILE, default=None)
        if loaded is None or not isinstance(loaded, dict) or not loaded:
            _cached_settings = DEFAULT_SETTINGS.copy()
            atomic_save_json(SETTINGS_FILE, _cached_settings)
            return _cached_settings

        merged = DEFAULT_SETTINGS.copy()
        merged.update(loaded)
        _cached_settings = merged
        return _cached_settings

def save_settings(new_settings: Dict[str, Any]) -> bool:
    global _cached_settings
    with _settings_lock:
        merged = DEFAULT_SETTINGS.copy()
        merged.update(new_settings)
        ok = atomic_save_json(SETTINGS_FILE, merged)
        if ok:
            _cached_settings = merged
        return ok

def get_effective_settings_for_regime(detected_regime: str, base_settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    현재 설정 모드에 따른 최종 유효 전략 파라미터 반환:
    - regime_preset_mode == 'AUTO': 감지된 국면(BULL/VOLATILE/BEAR)의 프리셋을 로드 후 사용자 오버라이드 적용
    - regime_preset_mode in ('BULL', 'VOLATILE', 'BEAR'): 해당 고정 프리셋 적용 후 오버라이드 적용
    - regime_preset_mode == 'CUSTOM': 사용자 설정 우선
    """
    current = load_settings().copy()
    user_settings = (base_settings or {}).copy()
    mode = user_settings.get("regime_preset_mode", current.get("regime_preset_mode", "AUTO"))

    resolved = current.copy()
    target_preset_key = None
    if mode == "AUTO":
        target_preset_key = detected_regime.upper()
    elif mode in MARKET_REGIME_PRESETS:
        target_preset_key = mode

    if target_preset_key and target_preset_key in MARKET_REGIME_PRESETS:
        preset_values = MARKET_REGIME_PRESETS[target_preset_key]
        for k, v in preset_values.items():
            if k not in ["name", "description"]:
                resolved[k] = v
        resolved["_active_regime_name"] = preset_values["name"]

    resolved.update(user_settings)
    return resolved

CURRENT_SETTINGS = load_settings()

def get_setting(key: str, default: Any = None) -> Any:
    return CURRENT_SETTINGS.get(key, default)

def get_url_base() -> str:
    return URL_BASE_MOCK if CURRENT_SETTINGS.get("mock_trading", True) else URL_BASE_REAL
