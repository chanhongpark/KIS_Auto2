"""
KIS Auto Trading - Strategy & Signal Evaluation Engine
15:15 종가 매수 신호(안전 게이트/수급 게이트/점수 카테고리 캡) 및
실시간 리스크 관리(손절 최우선 / 50% 분할 익절 / 트레일링 스탑 / 타임컷 / ATR 동적 손절) 평가 엔진
라이브 스크리너와 백테스터가 100% 동일하게 공유하는 단일 원천(Single Source of Truth) 모듈
"""
import logging
from typing import Dict, Any, Optional, Set, List
import pandas as pd
import numpy as np

logger = logging.getLogger("Strategy")

def get_market_regime(
    candles_or_df: Optional[pd.DataFrame],
    ma_period: int = 20
) -> Dict[str, Any]:
    """
    시장 국면 판단: 지수 20일 이동평균선 대비 현재 지수 위치 및 단기 추세 기반
    """
    if candles_or_df is None or len(candles_or_df) < 20:
        return {"regime": "NORMAL", "below_ma20": False, "downtrend": False, "ma20": 0.0, "current": 0.0}

    df = candles_or_df.copy()
    if isinstance(df, list):
        df = pd.DataFrame(df)

    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["ma"] = df["close"].rolling(window=ma_period, min_periods=1).mean()
    df["ma5"] = df["close"].rolling(window=5, min_periods=1).mean()

    last_close = float(df.iloc[-1]["close"])
    last_ma = float(df.iloc[-1]["ma"]) if not pd.isna(df.iloc[-1]["ma"]) else last_close
    below_ma20 = last_close < last_ma

    downtrend = False
    if len(df) >= 2:
        prev_ma5 = float(df.iloc[-2]["ma5"]) if not pd.isna(df.iloc[-2]["ma5"]) else 0
        prev_ma20 = float(df.iloc[-2]["ma"]) if not pd.isna(df.iloc[-2]["ma"]) else 0
        last_ma5 = float(df.iloc[-1]["ma5"]) if not pd.isna(df.iloc[-1]["ma5"]) else 0
        last_ma20 = float(df.iloc[-1]["ma"]) if not pd.isna(df.iloc[-1]["ma"]) else 0
        if prev_ma5 >= prev_ma20 and last_ma5 < last_ma20:
            downtrend = True

    regime = "WEAK" if (below_ma20 or downtrend) else "NORMAL"
    return {
        "regime": regime,
        "below_ma20": below_ma20,
        "downtrend": downtrend,
        "ma20": last_ma,
        "current": last_close
    }

def calculate_position_size(
    current_price: float,
    budget_val: float,
    atr_val: float = 0.0,
    settings: Optional[Dict[str, Any]] = None
) -> int:
    """
    변동성 조절 포지션 사이징 (ATR 기반 리스크 균등 분할) 또는 예산 기반 수량 계산
    """
    if current_price <= 0:
        return 1

    settings = settings or {}
    volatility_sizing = settings.get("volatility_sizing_enabled", True)

    if volatility_sizing and atr_val > 0:
        risk_per_trade = float(settings.get("risk_per_trade", 0.01))
        atr_stop_multiple = float(settings.get("atr_stop_multiple", 2.0))
        max_holdings = int(settings.get("max_holding_stocks", 5))
        total_equity = budget_val * max_holdings
        risk_amt = total_equity * risk_per_trade
        stop_dist = atr_stop_multiple * atr_val
        if stop_dist > 0:
            vol_qty = int(risk_amt // stop_dist)
            max_cap_qty = int(budget_val // current_price)
            return max(1, min(max_cap_qty, vol_qty))

    return max(1, int(budget_val // current_price))

def evaluate_buy_signals_from_df(
    df: Optional[pd.DataFrame],
    code: str,
    name: str,
    held_codes: Optional[Set[str]] = None,
    budget: Optional[float] = None,
    market_regime: Optional[Dict[str, Any]] = None,
    settings: Optional[Dict[str, Any]] = None,
    is_in_cooldown: bool = False
) -> Optional[Dict[str, Any]]:
    """
    계산된 기술적 보조지표 DataFrame을 바탕으로 매수 점수 및 안전/수급 게이트 평가
    """
    if df is None or len(df) < 20:
        return None

    settings = settings or {}
    held_codes = held_codes or set()
    is_additional_buy = code in held_codes

    last = df.iloc[-1]
    prev = df.iloc[-2]
    current_price = float(last["close"])
    open_price = float(last.get("open", current_price))
    high_price = float(last.get("high", current_price))
    low_price = float(last.get("low", current_price))

    reasons = []

    # -------------------------------------------------------------
    # [시장 국면 필터] 약세 국면 시 매수 점수 컷오프 상향 또는 전면 차단
    # -------------------------------------------------------------
    regime = (market_regime or {}).get("regime", "NORMAL")
    if settings.get("market_regime_filter_enabled", True) and regime == "WEAK":
        if settings.get("market_regime_block_weak", False):
            logger.info(f"[{name}({code})] 약세 시장 국면 - 신규 진입 전면 차단")
            return None
        reasons.append("⚠️ 약세 시장 국면 - 매수 점수 컷오프 상향 적용")

    # -------------------------------------------------------------
    # [손절 쿨다운] 손절 청산 종목 재매수 금지
    # -------------------------------------------------------------
    if is_in_cooldown:
        logger.info(f"[{name}({code})] 손절 쿨다운 기간 내 - 재매수 차단")
        return None

    # -------------------------------------------------------------
    # [안전 게이트 1] 이격도 과열 방지 필터 (단기 상투 차단)
    # -------------------------------------------------------------
    ma5_val = float(last["ma5"]) if not pd.isna(last["ma5"]) else current_price
    ma20_val = float(last["ma20"]) if not pd.isna(last["ma20"]) else current_price

    # 5일선 대비 3% 초과 또는 20일선 대비 6% 초과 시 고점 추격 매수로 판정하여 즉시 배제
    if ma5_val > 0 and (current_price / ma5_val) > 1.03:
        return None
    if ma20_val > 0 and (current_price / ma20_val) > 1.06:
        return None

    # -------------------------------------------------------------
    # [안전 게이트 2] 캔들 형태 필터 (윗꼬리 매물 출회 차단)
    # -------------------------------------------------------------
    total_range = high_price - low_price
    if total_range > 0:
        upper_shadow = high_price - max(open_price, current_price)
        if (upper_shadow / total_range) >= 0.40:
            return None

    # -------------------------------------------------------------
    # 1. 추세군 점수 산출 (그룹 상한: 최대 30점)
    # -------------------------------------------------------------
    raw_trend_score = 0
    if prev["ma5"] <= prev["ma20"] and last["ma5"] > last["ma20"]:
        raw_trend_score += 20
        reasons.append("📈 5일선-20일선 골든크로스 발생 (+20점)")
    if last["ma5"] > last["ma20"] and last["ma20"] > last["ma60"]:
        raw_trend_score += 15
        reasons.append("📊 이동평균 정배열 지속 (MA5 > MA20 > MA60) (+15점)")
    if last["close"] > last["ma20"]:
        raw_trend_score += 10
        reasons.append("🟢 20일선 상회 유지 (종가 > MA20) (+10점)")

    cap_trend = int(settings.get("score_cap_trend", 40))
    trend_score = min(min(30, cap_trend), raw_trend_score)

    # -------------------------------------------------------------
    # 2. 수급군 점수 및 필수 게이트 검증 (그룹 상한: 최대 25점, 필수 게이트)
    # -------------------------------------------------------------
    vol_ma20 = float(last["vol_ma20"]) if not pd.isna(last["vol_ma20"]) else 0.0
    adj_volume = float(last["adjusted_volume"]) if not pd.isna(last["adjusted_volume"]) else float(last["volume"])

    supply_gate_passed = False
    supply_score = 0
    vol_ratio = 0.0

    if vol_ma20 > 0:
        vol_ratio = (adj_volume / vol_ma20) * 100
        # 거래량이 1.3배 이상이면서 4배(400%) 이하 사이만 유효
        if 1.3 <= (adj_volume / vol_ma20) <= 4.0:
            supply_gate_passed = True
            supply_score = 25
            reasons.append(f"⚡ 당일 보정 거래량({adj_volume:,.0f}주)이 20일 평균({vol_ma20:,.0f}주) 대비 {vol_ratio:.0f}% 급증 (수급 게이트 통과, +25점)")
        else:
            supply_gate_passed = False
            supply_score = 0

    # -------------------------------------------------------------
    # 3. 모멘텀/반등군 점수 산출 (그룹 상한: 최대 25점)
    # -------------------------------------------------------------
    raw_momentum_score = 0
    rsi = float(last["rsi14"]) if not pd.isna(last["rsi14"]) else 50.0
    prev_rsi = float(prev["rsi14"]) if not pd.isna(prev["rsi14"]) else 50.0

    if 30 <= rsi <= 55 and rsi > prev_rsi:
        raw_momentum_score += 15
        reasons.append(f"🔥 RSI({rsi:.1f}) 30~55 구간 저평가 반등 모멘텀 (+15점)")
    elif 55 < rsi <= 68:
        raw_momentum_score += 10
        reasons.append(f"🚀 RSI({rsi:.1f}) 55~68 상승 탄력 유지 (+10점)")

    if prev["close"] <= prev["bb_lower"] and last["close"] > last["bb_lower"]:
        raw_momentum_score += 15
        reasons.append("🛡️ 볼린저 하단 밴드 터치 후 지지 반등 (+15점)")

    cap_mom = int(settings.get("score_cap_momentum", 30))
    momentum_score = min(min(25, cap_mom), raw_momentum_score)

    # -------------------------------------------------------------
    # 4. 종합 진입 조건 판별 (시장 국면별 컷오프 적용)
    # -------------------------------------------------------------
    total_score = trend_score + supply_score + momentum_score

    if settings.get("market_regime_filter_enabled", True) and regime == "WEAK":
        buy_threshold = float(settings.get("market_regime_cutoff_weak", 70))
    else:
        buy_threshold = float(settings.get("market_regime_cutoff_normal", settings.get("buy_score_threshold", 45)))

    if total_score >= buy_threshold and supply_gate_passed:
        default_budget = float(settings.get("max_buy_budget_per_stock", 500000.0))
        budget_val = budget if budget is not None else default_budget
        atr_val = float(last["atr"]) if "atr" in last and not pd.isna(last["atr"]) else 0.0

        qty = calculate_position_size(current_price, budget_val, atr_val=atr_val, settings=settings)
        total_est = qty * current_price

        result = {
            "code": code,
            "name": name,
            "current_price": current_price,
            "change_rate": float(last.get("change_rate", 0.0)),
            "score": total_score,
            "trend_score": trend_score,
            "supply_score": supply_score,
            "momentum_score": momentum_score,
            "supply_gate_passed": supply_gate_passed,
            "adjusted_volume": adj_volume,
            "vol_ma20": vol_ma20,
            "vol_ratio": round(vol_ratio, 1),
            "reasons": reasons,
            "recommended_qty": qty,
            "estimated_amount": total_est,
            "rsi": round(float(rsi), 1) if not pd.isna(rsi) else None,
            "ma5": round(ma5_val, 0),
            "ma20": round(ma20_val, 0),
            "ma60": round(float(last["ma60"]), 0) if not pd.isna(last["ma60"]) else 0.0,
            "atr": round(atr_val, 0),
            "market_regime": regime,
            "buy_threshold": buy_threshold
        }

        if is_additional_buy:
            result["is_additional_buy"] = True
            result["buy_type"] = "추가매수"
            result["reasons"] = ["📌 현재 보유 종목 추가매수 추천"] + reasons
        else:
            result["is_additional_buy"] = False
            result["buy_type"] = "신규매수"

        return result

    return None

def evaluate_sell_signals_from_df(
    holding: Dict[str, Any],
    df: Optional[pd.DataFrame] = None,
    is_recently_bought: bool = False,
    stop_loss_rate: Optional[float] = None,
    target_profit_rate: Optional[float] = None,
    settings: Optional[Dict[str, Any]] = None,
    is_partial_sold: bool = False,
    highest_price: Optional[float] = None,
    holding_days: int = 0
) -> Optional[Dict[str, Any]]:
    """
    보유 종목의 수익률 및 지표 기반 매도 판단
    """
    settings = settings or {}
    code = holding.get("code")
    name = holding.get("name", code)
    profit_rate = float(holding.get("profit_rate", 0.0))
    current_price = float(holding.get("current_price", 0.0))
    holding_qty = int(holding.get("quantity", holding.get("qty", 0)))
    avg_buy_price = float(holding.get("avg_buy_price", 0.0))
    profit_loss = float(holding.get("profit_loss", 0.0))

    sl_rate = (stop_loss_rate if stop_loss_rate is not None else float(settings.get("stop_loss_rate", -0.03))) * 100
    tp_rate = (target_profit_rate if target_profit_rate is not None else float(settings.get("target_profit_rate", 0.05))) * 100

    # -------------------------------------------------------------
    # ATR 동적 손절 (변동성 기반 손절가) 계산
    # -------------------------------------------------------------
    atr_stop_price = None
    atr_stop_rate = None
    if settings.get("atr_stop_loss_enabled", True) and df is not None and len(df) >= 20:
        last = df.iloc[-1]
        atr_val = float(last["atr"]) if "atr" in last and not pd.isna(last["atr"]) else 0.0
        if atr_val > 0 and avg_buy_price > 0:
            atr_multiple = float(settings.get("atr_stop_loss_multiple", 2.0))
            atr_stop_price = avg_buy_price - (atr_multiple * atr_val)

            atr_stop_rate = ((atr_stop_price - avg_buy_price) / avg_buy_price) * 100
            min_pct = float(settings.get("atr_stop_loss_min_pct", -0.05)) * 100
            max_pct = float(settings.get("atr_stop_loss_max_pct", -0.01)) * 100
            atr_stop_rate = max(min_pct, min(max_pct, atr_stop_rate))
            atr_stop_price = avg_buy_price * (1 + atr_stop_rate / 100)

            if settings.get("atr_stop_loss_use_low_break", True):
                low_price = float(last.get("low", current_price))
                if low_price < atr_stop_price:
                    atr_stop_price = low_price
                    atr_stop_rate = ((low_price - avg_buy_price) / avg_buy_price) * 100

    effective_sl_rate = sl_rate
    if atr_stop_rate is not None and atr_stop_rate > sl_rate:
        effective_sl_rate = atr_stop_rate

    # 1. 긴급 손절 (2일 유예 무시, 100% 매도)
    if profit_rate <= effective_sl_rate:
        sl_reason = f"🚨 긴급 손절 기준 도달 ({profit_rate:+.2f}% <= {effective_sl_rate:.1f}%)"
        if atr_stop_rate is not None and atr_stop_rate > sl_rate:
            sl_reason += f" [ATR 동적 손절: 진입가-{settings.get('atr_stop_loss_multiple', 2.0)}×ATR]"
        else:
            sl_reason += " - 자본 보호 즉시 전량 매도"

        return {
            "code": code,
            "name": name,
            "holding_qty": holding_qty,
            "sell_qty": holding_qty,
            "sell_ratio": 1.0,
            "sell_type": "전량 긴급손절",
            "avg_buy_price": avg_buy_price,
            "current_price": current_price,
            "profit_rate": profit_rate,
            "profit_loss": profit_loss,
            "reasons": [sl_reason],
            "is_urgent": True,
            "atr_stop_price": atr_stop_price,
            "atr_stop_rate": atr_stop_rate
        }

    # 2. 1차 익절 완료 종목의 최고가 추적 트레일링 스탑 (Trailing Stop)
    if is_partial_sold:
        high_benchmark = highest_price if highest_price is not None and highest_price > 0 else max(avg_buy_price, current_price)
        trailing_pct = float(settings.get("trailing_stop_pct", 0.035))
        trailing_stop_price = high_benchmark * (1 - trailing_pct)

        if current_price <= trailing_stop_price:
            return {
                "code": code,
                "name": name,
                "holding_qty": holding_qty,
                "sell_qty": holding_qty,
                "sell_ratio": 1.0,
                "sell_type": "트레일링 스탑 전량익절",
                "avg_buy_price": avg_buy_price,
                "current_price": current_price,
                "profit_rate": profit_rate,
                "profit_loss": profit_loss,
                "reasons": [f"🏆 최고가({high_benchmark:,.0f}원) 대비 -{trailing_pct*100:.1f}% 하락 도달 - 잔여 수량 전량 익절 (+{profit_rate:.2f}%)"],
                "is_urgent": False
            }
        return None

    # 3. 1차 목표 익절 (2일 유예 무시, 50% 분할 익절)
    if profit_rate >= tp_rate and not is_partial_sold:
        sell_qty = max(1, holding_qty // 2) if holding_qty > 1 else holding_qty
        sell_ratio = 0.5 if holding_qty > 1 else 1.0
        return {
            "code": code,
            "name": name,
            "holding_qty": holding_qty,
            "sell_qty": sell_qty,
            "sell_ratio": sell_ratio,
            "sell_type": "50% 1차익절" if sell_ratio == 0.5 else "전량익절",
            "avg_buy_price": avg_buy_price,
            "current_price": current_price,
            "profit_rate": profit_rate,
            "profit_loss": profit_loss,
            "reasons": [f"🎯 목표 익절 수익률 달성 (+{profit_rate:.2f}% >= +{tp_rate:.1f}%) - 50% 1차 익절 및 잔여분 트레일링 스탑"],
            "is_urgent": False,
            "is_partial_take": True
        }

    # 4. 2일 보유 유예 원칙
    if is_recently_bought:
        return None

    # 5. 타임컷 (Time-based Exit / 기간 만료 청산)
    time_stop_days = int(settings.get("time_stop_days", 6))
    time_stop_min_profit = float(settings.get("time_stop_min_profit", 0.02)) * 100
    if settings.get("time_stop_enabled", True) and holding_days >= time_stop_days:
        if profit_rate < time_stop_min_profit:
            return {
                "code": code,
                "name": name,
                "holding_qty": holding_qty,
                "sell_qty": holding_qty,
                "sell_ratio": 1.0,
                "sell_type": "타임컷 청산 (기간 만료)",
                "avg_buy_price": avg_buy_price,
                "current_price": current_price,
                "profit_rate": profit_rate,
                "profit_loss": profit_loss,
                "reasons": [f"⏳ {holding_days}영업일 경과 및 목표수익 미달({profit_rate:+.2f}% < {time_stop_min_profit:.1f}%) - 자금 회수 타임컷 청산"],
                "is_urgent": False
            }

    # 6. 일반 기술적 매도 신호 분석
    if df is not None and len(df) >= 20:
        last = df.iloc[-1]
        prev = df.iloc[-2]

        sell_reasons = []
        is_deadcross = False
        is_rsi_overheat = False

        if prev["ma5"] >= prev["ma20"] and last["ma5"] < last["ma20"]:
            is_deadcross = True
            sell_reasons.append("📉 5일선이 20일선을 하향 이탈 (데드크로스 발생) - 전량 청산 권고")

        rsi_val = float(last["rsi14"]) if not pd.isna(last["rsi14"]) else 0.0
        if rsi_val > 75:
            is_rsi_overheat = True
            sell_reasons.append(f"🔥 RSI 과열권 도달 ({rsi_val:.1f} > 75) - 50% 분할 차익실현 권고")

        if is_deadcross:
            return {
                "code": code,
                "name": name,
                "holding_qty": holding_qty,
                "sell_qty": holding_qty,
                "sell_ratio": 1.0,
                "sell_type": "전량 청산 (데드크로스)",
                "avg_buy_price": avg_buy_price,
                "current_price": current_price,
                "profit_rate": profit_rate,
                "profit_loss": profit_loss,
                "reasons": sell_reasons,
                "is_urgent": False
            }
        elif is_rsi_overheat and not is_partial_sold:
            sell_qty = max(1, holding_qty // 2) if holding_qty > 1 else holding_qty
            sell_ratio = 0.5 if holding_qty > 1 else 1.0
            return {
                "code": code,
                "name": name,
                "holding_qty": holding_qty,
                "sell_qty": sell_qty,
                "sell_ratio": sell_ratio,
                "sell_type": "50% 분할익절 (RSI 과열)" if sell_ratio == 0.5 else "전량익절",
                "avg_buy_price": avg_buy_price,
                "current_price": current_price,
                "profit_rate": profit_rate,
                "profit_loss": profit_loss,
                "reasons": sell_reasons,
                "is_urgent": False,
                "is_partial_take": True
            }

    return None
