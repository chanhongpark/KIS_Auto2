"""
KIS Auto Trading Core Package
순환 참조(Circular Import) 방지를 위해 하위 모듈들을 Eager import 하지 않고 지연 로딩(PEP 562)합니다.
"""

def __getattr__(name: str):
    if name in (
        "KISError", "KISApiError", "KISAuthError", "KISRateLimitError",
        "KISOrderError", "StrategyError", "StorageError"
    ):
        from core import exceptions
        return getattr(exceptions, name)
    if name == "exceptions":
        from core import exceptions
        return exceptions
    if name in ("safe_load_json", "atomic_save_json"):
        from core import storage
        return getattr(storage, name)
    if name == "storage":
        from core import storage
        return storage
    if name == "calculate_technical_indicators":
        from core import indicators
        return getattr(indicators, name)
    if name == "indicators":
        from core import indicators
        return indicators
    if name in ("PositionTracker", "POSITIONS_STATE_FILE", "COOLDOWN_FILE"):
        from core import position_tracker
        return getattr(position_tracker, name)
    if name == "position_tracker":
        from core import position_tracker
        return position_tracker
    if name in (
        "get_market_regime", "calculate_position_size",
        "evaluate_buy_signals_from_df", "evaluate_sell_signals_from_df"
    ):
        from core import strategy
        return getattr(strategy, name)
    if name == "strategy":
        from core import strategy
        return strategy
    raise AttributeError(f"module 'core' has no attribute '{name}'")

__all__ = [
    "exceptions",
    "storage",
    "indicators",
    "position_tracker",
    "strategy",
    "KISError",
    "KISApiError",
    "KISAuthError",
    "KISRateLimitError",
    "KISOrderError",
    "StrategyError",
    "StorageError",
    "safe_load_json",
    "atomic_save_json",
    "calculate_technical_indicators",
    "PositionTracker",
    "POSITIONS_STATE_FILE",
    "COOLDOWN_FILE",
    "get_market_regime",
    "calculate_position_size",
    "evaluate_buy_signals_from_df",
    "evaluate_sell_signals_from_df",
]
