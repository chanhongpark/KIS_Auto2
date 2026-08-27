"""
Stock Screener & Signal Engine
종가(15:15) 매수 후보 종목 발굴 및 실시간 리스크 관리(손절 최우선 / 분할 익절) 분석 엔진
실시간 라이브 트레이딩과 백테스터가 100% 동일한 신호 산출 함수를 공유합니다.
"""
import os
import json
import logging
import datetime
from typing import Dict, Any, List, Optional, Set
import pandas as pd
import numpy as np

import config
from kis_api import KISApiClient
from telegram_notifier import notifier
from time_utils import today, now_str, now

PROPOSALS_FILE = os.path.join(os.path.dirname(__file__), "proposals.json")

class StockScreener:
    def __init__(self, api_client: Optional[KISApiClient] = None):
        self.logger = logging.getLogger("Screener")
        self.api = api_client or KISApiClient()

    def calculate_technical_indicators(
        self,
        candles: List[Dict[str, Any]],
        is_intraday: bool = True
    ) -> Optional[pd.DataFrame]:
        """
        일봉 캔들 데이터를 바탕으로 기술적 보조지표 계산
        - 60영업일 이상 일봉 데이터 기준
        - 이동평균선: MA5, MA20, MA60
        - 거래량 이동평균: 전일까지 20일 거래량 단순 이동평균 (vol_ma20)
        - 장중 거래량 보정치: 15:15 누적 거래량 * (390분 / 375분) ≈ 누적 거래량 * 1.04
        - RSI(14)
        - 볼린저 밴드(20, 2): 20일 이평선 기준 ±2σ
        """
        if not candles or len(candles) < 20:
            return None

        df = pd.DataFrame(candles).copy()
        df["close"] = pd.to_numeric(df["close"])
        df["open"] = pd.to_numeric(df["open"])
        df["high"] = pd.to_numeric(df["high"])
        df["low"] = pd.to_numeric(df["low"])
        df["volume"] = pd.to_numeric(df["volume"])

        # 1. 이동평균선 (MA5, MA20, MA60)
        df["ma5"] = df["close"].rolling(window=5).mean()
        df["ma20"] = df["close"].rolling(window=20).mean()
        df["ma60"] = df["close"].rolling(window=min(60, len(df))).mean()

        # 2. 거래량 이동평균 (전일까지의 20일 거래량 단순 이동평균으로 산출하여 당일 봉 미완성 왜곡 방지)
        df["vol_ma20"] = df["volume"].shift(1).rolling(window=20).mean()

        # 3. 당일 거래량 보정치 계산 (15:15 장마감 직전 평가 시 1.04배 보정)
        df["adjusted_volume"] = df["volume"].astype(float).copy()
        if is_intraday and len(df) > 0:
            last_idx = df.index[-1]
            df.loc[last_idx, "adjusted_volume"] = float(df.loc[last_idx, "volume"]) * (390.0 / 375.0)

        # 4. RSI (14)
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df["rsi14"] = 100 - (100 / (1 + rs))

        # 5. 볼린저 밴드 (20, 2)
        df["bb_mid"] = df["ma20"]
        df["bb_std"] = df["close"].rolling(window=20).std()
        df["bb_upper"] = df["bb_mid"] + (df["bb_std"] * 2)
        df["bb_lower"] = df["bb_mid"] - (df["bb_std"] * 2)

        return df

    def evaluate_buy_signals_from_df(
        self,
        df: pd.DataFrame,
        code: str,
        name: str,
        held_codes: Optional[Set[str]] = None,
        budget: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        계산된 기술적 보조지표 DataFrame을 바탕으로 매수 점수 및 안전/수급 게이트 평가
        (라이브 스크리너 및 백테스터 공통 단일 원천 함수)
        """
        if df is None or len(df) < 20:
            return None

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
            # 윗꼬리가 전체 변동폭의 40% 이상이면 매물 출회 신호로 차단
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

        trend_score = min(30, raw_trend_score)

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
            # 거래량이 1.3배 이상이면서 4배(400%) 이상 폭증한 이상 급등일은 과열로 배제 (1.3배 ~ 4.0배 사이 유효)
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

        momentum_score = min(25, raw_momentum_score)

        # -------------------------------------------------------------
        # 4. 종합 진입 조건 판별
        # -------------------------------------------------------------
        total_score = trend_score + supply_score + momentum_score

        if total_score >= 45 and supply_gate_passed:
            # config 미정의 환경 방어 처리
            default_budget = 500000.0
            try:
                budget_val = budget if budget is not None else float(config.CURRENT_SETTINGS.get("max_buy_budget_per_stock", default_budget))
            except NameError:
                budget_val = budget if budget is not None else default_budget

            qty = max(1, int(budget_val // current_price)) if current_price > 0 else 1
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
                "ma60": round(float(last["ma60"]), 0) if not pd.isna(last["ma60"]) else 0.0
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

    def evaluate_buy_signals(
        self,
        code: str,
        name: str,
        held_codes: Optional[Set[str]] = None,
        is_intraday: bool = True
    ) -> Optional[Dict[str, Any]]:
        """라이브 환경에서 API 데이터 수집 후 공통 평가 함수 호출"""
        candles = self.api.get_daily_chart(code, count=65)

        realtime = self.api.get_stock_price(code)
        if realtime.get("rt_cd") == "0" and realtime.get("price", 0) > 0:
            today_str = today().strftime("%Y%m%d")
            if not candles or candles[-1].get("date") != today_str:
                candles.append({
                    "date": today_str,
                    "close": realtime["price"],
                    "open": realtime.get("stck_oprc", realtime["price"]),
                    "high": realtime.get("stck_hgpr", realtime["price"]),
                    "low": realtime.get("stck_lwpr", realtime["price"]),
                    "volume": realtime.get("acml_vol", 0),
                    "change_rate": realtime.get("prdy_ctrt", 0.0)
                })
            else:
                candles[-1].update({
                    "close": realtime["price"],
                    "open": realtime.get("stck_oprc", candles[-1].get("open", realtime["price"])),
                    "high": realtime.get("stck_hgpr", candles[-1].get("high", realtime["price"])),
                    "low": realtime.get("stck_lwpr", candles[-1].get("low", realtime["price"])),
                    "volume": realtime.get("acml_vol", candles[-1].get("volume", 0)),
                    "change_rate": realtime.get("prdy_ctrt", candles[-1].get("change_rate", 0.0))
                })

        df = self.calculate_technical_indicators(candles, is_intraday=is_intraday)
        return self.evaluate_buy_signals_from_df(df, code, name, held_codes=held_codes)

    def evaluate_sell_signals_from_df(
        self,
        holding: Dict[str, Any],
        df: Optional[pd.DataFrame] = None,
        is_recently_bought: bool = False,
        stop_loss_rate: Optional[float] = None,
        target_profit_rate: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        보유 종목의 수익률 및 지표 기반 매도 판단
        (라이브 스크리너 및 백테스터 공통 단일 원천 함수)
        """
        code = holding.get("code")
        name = holding.get("name")
        profit_rate = float(holding.get("profit_rate", 0.0))
        current_price = float(holding.get("current_price", 0.0))
        holding_qty = int(holding.get("quantity", holding.get("qty", 0)))
        avg_buy_price = float(holding.get("avg_buy_price", 0.0))
        profit_loss = float(holding.get("profit_loss", 0.0))

        sl_rate = (stop_loss_rate if stop_loss_rate is not None else float(config.CURRENT_SETTINGS.get("stop_loss_rate", -0.03))) * 100
        tp_rate = (target_profit_rate if target_profit_rate is not None else float(config.CURRENT_SETTINGS.get("target_profit_rate", 0.05))) * 100

        # 1. 긴급 손절 (2일 유예 무시, 100% 매도)
        if profit_rate <= sl_rate:
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
                "reasons": [f"🚨 긴급 손절 기준 도달 ({profit_rate:+.2f}% <= {sl_rate:.1f}%) - 자본 보호 즉시 전량 매도"],
                "is_urgent": True
            }

        # 2. 목표 익절 (2일 유예 무시, 50% 분할 익절)
        if profit_rate >= tp_rate:
            sell_qty = max(1, holding_qty // 2) if holding_qty > 1 else holding_qty
            sell_ratio = 0.5 if holding_qty > 1 else 1.0
            return {
                "code": code,
                "name": name,
                "holding_qty": holding_qty,
                "sell_qty": sell_qty,
                "sell_ratio": sell_ratio,
                "sell_type": "50% 분할익절" if sell_ratio == 0.5 else "전량익절",
                "avg_buy_price": avg_buy_price,
                "current_price": current_price,
                "profit_rate": profit_rate,
                "profit_loss": profit_loss,
                "reasons": [f"🎯 목표 익절 수익률 달성 (+{profit_rate:.2f}% >= +{tp_rate:.1f}%) - 50% 분할 익절 및 잔여분 트레일링 스탑"],
                "is_urgent": False
            }

        # 3. 2일 보유 유예 원칙
        if is_recently_bought:
            return None

        # 4. 일반 기술적 매도 신호 분석
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
            elif is_rsi_overheat:
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
                    "is_urgent": False
                }

        return None

    def _is_recently_bought(self, code: str, days: int = 2) -> bool:
        """매수일로부터 지정된 일수(days) 이내에 매수된 종목인지 확인"""
        try:
            end_date = today().strftime("%Y%m%d")
            start_date = (today() - datetime.timedelta(days=days)).strftime("%Y%m%d")
            orders = self.api.get_order_history(start_date=start_date, end_date=end_date)
            for order in orders:
                if order.get("code") == code and order.get("buy_sell") == "매수":
                    return True
        except Exception as e:
            self.logger.warning(f"[{code}] 최근 매수 여부 확인 중 예외: {e}")
        return False

    def evaluate_sell_signals(self, holding: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """라이브 환경에서 보유 종목 매도 분석 (공통 평가 함수 호출)"""
        code = holding.get("code")
        profit_rate = float(holding.get("profit_rate", 0.0))
        target_profit_rate = float(config.CURRENT_SETTINGS.get("target_profit_rate", 0.05)) * 100
        stop_loss_rate = float(config.CURRENT_SETTINGS.get("stop_loss_rate", -0.03)) * 100

        # 긴급 손절/목표 익절은 차트 로드 없이 즉시 반환
        if profit_rate <= stop_loss_rate or profit_rate >= target_profit_rate:
            return self.evaluate_sell_signals_from_df(
                holding=holding,
                df=None,
                is_recently_bought=False,
                stop_loss_rate=stop_loss_rate / 100,
                target_profit_rate=target_profit_rate / 100
            )

        # 2일 이내 매수 종목이면 기술적 분석 스킵
        is_recent = self._is_recently_bought(code, days=2)
        if is_recent:
            self.logger.info(f"[{holding.get('name')}({code})] 매수 후 2영업일 이내 종목으로 기술적 매도 제외")
            return None

        # 기술적 분석용 일봉 데이터 로드
        candles = self.api.get_daily_chart(code, count=60)
        realtime = self.api.get_stock_price(code)
        if realtime.get("rt_cd") == "0" and realtime.get("price", 0) > 0:
            today_str = today().strftime("%Y%m%d")
            if not candles or candles[-1].get("date") != today_str:
                candles.append({
                    "date": today_str,
                    "close": realtime["price"],
                    "open": realtime.get("stck_oprc", realtime["price"]),
                    "high": realtime.get("stck_hgpr", realtime["price"]),
                    "low": realtime.get("stck_lwpr", realtime["price"]),
                    "volume": realtime.get("acml_vol", 0),
                    "change_rate": realtime.get("prdy_ctrt", 0.0)
                })
            else:
                candles[-1].update({
                    "close": realtime["price"],
                    "open": realtime.get("stck_oprc", candles[-1].get("open", realtime["price"])),
                    "high": realtime.get("stck_hgpr", candles[-1].get("high", realtime["price"])),
                    "low": realtime.get("stck_lwpr", candles[-1].get("low", realtime["price"])),
                    "volume": realtime.get("acml_vol", candles[-1].get("volume", 0)),
                    "change_rate": realtime.get("prdy_ctrt", candles[-1].get("change_rate", 0.0))
                })

        df = self.calculate_technical_indicators(candles, is_intraday=True)
        return self.evaluate_sell_signals_from_df(
            holding=holding,
            df=df,
            is_recently_bought=is_recent,
            stop_loss_rate=stop_loss_rate / 100,
            target_profit_rate=target_profit_rate / 100
        )

    def run_closing_price_screening(self) -> Dict[str, Any]:
        """15:15 종가 매수 스크리닝 및 제안서 갱신"""
        self.logger.info("=== [15:15] 종가 매수 후보 발굴 및 스크리닝 시작 ===")
        balance = self.api.get_account_balance()
        holdings = balance.get("holdings", [])
        held_codes = {h.get("code") for h in holdings if h.get("code")}

        watchlist = config.CURRENT_SETTINGS.get("watchlist", [])
        buy_proposals = []
        for stock in watchlist:
            code = stock.get("code")
            name = stock.get("name")
            try:
                res = self.evaluate_buy_signals(code, name, held_codes=held_codes, is_intraday=True)
                if res:
                    buy_proposals.append(res)
            except Exception as e:
                self.logger.warning(f"[{name}({code})] 종가 스크리닝 중 예외: {e}")

        buy_proposals.sort(key=lambda x: x["score"], reverse=True)
        top_buy_proposals = buy_proposals[:5]

        sell_proposals = []
        for holding in holdings:
            try:
                sell_res = self.evaluate_sell_signals(holding)
                if sell_res:
                    sell_proposals.append(sell_res)
            except Exception as e:
                self.logger.warning(f"[{holding.get('name')}] 매도 분석 예외: {e}")

        proposals_data = {
            "generated_at": now_str(),
            "screening_type": "CLOSING_BUY_1515",
            "buy_proposals": top_buy_proposals,
            "sell_proposals": sell_proposals,
            "holdings_count": len(holdings),
            "status": "READY"
        }

        self.save_proposals(proposals_data)
        self.logger.info(f"15:15 종가 스크리닝 완료: 매수 추천 {len(top_buy_proposals)}건, 매도 추천 {len(sell_proposals)}건")
        self._notify_screening_summary(top_buy_proposals, sell_proposals, len(holdings))

        return proposals_data

    def run_premarket_screening(self) -> Dict[str, Any]:
        """개장 전/정기 스크리닝 (기본 호환용)"""
        return self.run_closing_price_screening()

    def check_market_open_stop_loss(self) -> List[Dict[str, Any]]:
        """09:00 시초가 갭하락 및 보유 종목 긴급 손절 감시"""
        self.logger.info("=== [09:00] 시초가 갭하락 및 긴급 손절 감시 시작 ===")
        balance = self.api.get_account_balance()
        holdings = balance.get("holdings", [])
        urgent_sells = []

        stop_loss_rate = float(config.CURRENT_SETTINGS.get("stop_loss_rate", -0.03)) * 100

        for holding in holdings:
            profit_rate = float(holding.get("profit_rate", 0.0))
            if profit_rate <= stop_loss_rate:
                sell_res = self.evaluate_sell_signals(holding)
                if sell_res:
                    urgent_sells.append(sell_res)
                    if config.CURRENT_SETTINGS.get("auto_execute_orders", False):
                        self.logger.warning(f"[{holding.get('name')}] 09:00 긴급 손절 시장가 매도 자동 발주")
                        self.api.order_stock(
                            code=holding.get("code"),
                            qty=int(holding.get("quantity", 0)),
                            buy_sell="매도",
                            order_type="00"
                        )

        if urgent_sells:
            self._notify_sell_recommendations(urgent_sells)

        return urgent_sells

    def check_sell_signals_now(self) -> Dict[str, Any]:
        """장중 실시간 매도 신호 재분석 및 제안서 갱신"""
        self.logger.info("=== 보유 주식 실시간 매도 신호 재분석 시작 ===")
        existing = self.load_proposals()
        buy_proposals = existing.get("buy_proposals", [])

        balance = self.api.get_account_balance()
        holdings = balance.get("holdings", [])
        sell_proposals = []
        for holding in holdings:
            try:
                sell_res = self.evaluate_sell_signals(holding)
                if sell_res:
                    sell_proposals.append(sell_res)
            except Exception as e:
                self.logger.warning(f"[{holding.get('name')}] 매도 분석 예외: {e}")

        proposals_data = {
            "generated_at": now_str(),
            "buy_proposals": buy_proposals,
            "sell_proposals": sell_proposals,
            "holdings_count": len(holdings),
            "status": "READY"
        }

        self.save_proposals(proposals_data)
        self.logger.info(f"실시간 매도 신호 재분석 완료: 매도 추천 {len(sell_proposals)}건")
        self._notify_sell_recommendations(sell_proposals)
        return proposals_data

    def execute_top_buy_orders(self) -> List[Dict[str, Any]]:
        """15:18 매수 추천 종목 시장가 주문 집행"""
        self.logger.info("=== [15:18] 종가 매수 추천 종목 주문 집행 시작 ===")
        proposals = self.load_proposals()
        buy_list = proposals.get("buy_proposals", [])

        if not buy_list:
            return []

        if not config.CURRENT_SETTINGS.get("auto_execute_orders", False):
            return []

        executed = []
        max_holdings = int(config.CURRENT_SETTINGS.get("max_holding_stocks", 5))
        balance = self.api.get_account_balance()
        current_holding_count = len(balance.get("holdings", []))

        for item in buy_list:
            if current_holding_count >= max_holdings and not item.get("is_additional_buy"):
                continue

            code = item.get("code")
            name = item.get("name")
            qty = int(item.get("recommended_qty", 0))

            if qty <= 0:
                continue

            try:
                self.logger.info(f"[{name}({code})] 15:18 종가 시장가 매수 발주 (수량: {qty}주)")
                res = self.api.order_stock(
                    code=code,
                    qty=qty,
                    buy_sell="매수",
                    order_type="00"
                )
                executed.append({"stock": item, "response": res})
                if not item.get("is_additional_buy"):
                    current_holding_count += 1
            except Exception as e:
                self.logger.error(f"[{name}({code})] 주문 집행 에러: {e}")

        return executed

    def _notify_sell_recommendations(self, sell_proposals: List[Dict[str, Any]]) -> None:
        """매도 추천 종목 텔레그램 알림 전송"""
        if not sell_proposals:
            return

        for sell_item in sell_proposals:
            try:
                notifier.send_sell_recommendation(
                    name=sell_item.get("name", ""),
                    code=sell_item.get("code", ""),
                    holding_qty=int(sell_item.get("holding_qty", 0)),
                    avg_buy_price=float(sell_item.get("avg_buy_price", 0)),
                    current_price=float(sell_item.get("current_price", 0)),
                    profit_rate=float(sell_item.get("profit_rate", 0)),
                    profit_loss=float(sell_item.get("profit_loss", 0)),
                    reasons=sell_item.get("reasons", []),
                    is_urgent=bool(sell_item.get("is_urgent", False))
                )
            except Exception as e:
                self.logger.warning(f"[{sell_item.get('name')}] 텔레그램 매도 알림 전송 실패: {e}")

    def _notify_screening_summary(
        self,
        buy_list: List[Dict[str, Any]],
        sell_list: List[Dict[str, Any]],
        holdings_count: int
    ) -> None:
        """스크리닝 요약 알림 전송"""
        try:
            notifier.send_daily_summary(
                buy_count=len(buy_list),
                sell_count=len(sell_list),
                holdings_count=holdings_count,
                buy_list=buy_list,
                sell_list=sell_list
            )
        except Exception as e:
            self.logger.warning(f"스크리닝 요약 알림 전송 실패: {e}")

    def save_proposals(self, data: dict) -> bool:
        try:
            with open(PROPOSALS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            self.logger.error(f"제안서 파일 저장 실패: {e}")
            return False

    @staticmethod
    def load_proposals() -> Dict[str, Any]:
        if os.path.exists(PROPOSALS_FILE):
            try:
                with open(PROPOSALS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "generated_at": "-",
            "buy_proposals": [],
            "sell_proposals": [],
            "holdings_count": 0,
            "status": "EMPTY"
        }
