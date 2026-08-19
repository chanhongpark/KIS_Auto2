"""
Stock Screener & Signal Engine
개장 전 매수 후보 종목 발굴 및 보유 주식 매도 추천 분석
"""
import os
import json
import logging
import datetime
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

import config
from kis_api import KISApiClient

PROPOSALS_FILE = os.path.join(os.path.dirname(__file__), "proposals.json")

class StockScreener:
    def __init__(self, api_client: Optional[KISApiClient] = None):
        self.logger = logging.getLogger("Screener")
        self.api = api_client or KISApiClient()

    def calculate_technical_indicators(self, candles: List[Dict[str, Any]]) -> Optional[pd.DataFrame]:
        """일봉 캔들 데이터를 바탕으로 기술적 보조지표 계산"""
        if not candles or len(candles) < 20:
            return None

        df = pd.DataFrame(candles)
        df["close"] = pd.to_numeric(df["close"])
        df["open"] = pd.to_numeric(df["open"])
        df["high"] = pd.to_numeric(df["high"])
        df["low"] = pd.to_numeric(df["low"])
        df["volume"] = pd.to_numeric(df["volume"])

        # 이동평균선
        df["ma5"] = df["close"].rolling(window=5).mean()
        df["ma20"] = df["close"].rolling(window=20).mean()
        df["ma60"] = df["close"].rolling(window=min(60, len(df))).mean()

        # 거래량 이동평균
        df["vol_ma20"] = df["volume"].rolling(window=20).mean()

        # RSI (14)
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df["rsi14"] = 100 - (100 / (1 + rs))

        # 볼린저 밴드 (20, 2)
        df["bb_mid"] = df["ma20"]
        df["bb_std"] = df["close"].rolling(window=20).std()
        df["bb_upper"] = df["bb_mid"] + (df["bb_std"] * 2)
        df["bb_lower"] = df["bb_mid"] - (df["bb_std"] * 2)

        return df

    def evaluate_buy_signals(self, code: str, name: str) -> Optional[Dict[str, Any]]:
        """개별 종목의 매수 타당성 및 점수 분석"""
        candles = self.api.get_daily_chart(code, count=60)
        df = self.calculate_technical_indicators(candles)
        if df is None or len(df) < 20:
            return None

        last = df.iloc[-1]
        prev = df.iloc[-2]
        current_price = float(last["close"])

        score = 0
        reasons = []

        # 1. 이동평균 골든크로스 또는 정배열
        if prev["ma5"] <= prev["ma20"] and last["ma5"] > last["ma20"]:
            score += 35
            reasons.append("5일선이 20일선을 상향 돌파 (골든크로스 발생)")
        elif last["ma5"] > last["ma20"] and last["ma20"] > last["ma60"]:
            score += 25
            reasons.append("이동평균 정배열 지속 (5일 > 20일 > 60일)")
        elif last["close"] > last["ma20"]:
            score += 15
            reasons.append("20일 중기 이동평균선 상회 유지")

        # 2. 거래량 급증 확인
        if last["vol_ma20"] > 0 and last["volume"] >= last["vol_ma20"] * 1.3:
            score += 25
            vol_ratio = (last["volume"] / last["vol_ma20"] ) * 100
            reasons.append(f"20일 평균 거래량 대비 {vol_ratio:.0f}% 급증 (수급 유입)")

        # 3. RSI 지표 분석 (30~65 구간의 상승 반등)
        rsi = last["rsi14"]
        if 30 <= rsi <= 55 and rsi > prev["rsi14"]:
            score += 25
            reasons.append(f"RSI({rsi:.1f}) 저평가/반등 모멘텀 형성")
        elif 55 < rsi <= 68:
            score += 15
            reasons.append(f"RSI({rsi:.1f}) 건강한 상승 추세권")

        # 4. 볼린저 밴드 하단 반등
        if prev["close"] <= prev["bb_lower"] and last["close"] > last["bb_lower"]:
            score += 20
            reasons.append("볼린저 밴드 하단 지지 후 강력한 반등")

        # 종합 점수가 40점 이상인 경우 매수 후보로 추천
        if score >= 40:
            budget = float(config.CURRENT_SETTINGS.get("max_buy_budget_per_stock", 500000))
            qty = max(1, int(budget // current_price)) if current_price > 0 else 1
            total_est = qty * current_price

            return {
                "code": code,
                "name": name,
                "current_price": current_price,
                "change_rate": float(last.get("change_rate", 0.0)),
                "score": score,
                "reasons": reasons,
                "recommended_qty": qty,
                "estimated_amount": total_est,
                "rsi": round(float(rsi), 1) if not pd.isna(rsi) else None,
                "ma5": round(float(last["ma5"]), 0),
                "ma20": round(float(last["ma20"]), 0)
            }
        return None

    def evaluate_sell_signals(self, holding: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """보유 종목에 대한 매도 필요 여부 분석"""
        code = holding.get("code")
        name = holding.get("name")
        profit_rate = float(holding.get("profit_rate", 0.0))
        current_price = float(holding.get("current_price", 0.0))
        holding_qty = int(holding.get("quantity", 0))

        target_profit_rate = float(config.CURRENT_SETTINGS.get("target_profit_rate", 0.05)) * 100
        stop_loss_rate = float(config.CURRENT_SETTINGS.get("stop_loss_rate", -0.03)) * 100

        sell_reasons = []
        is_urgent = False

        # 1. 목표 익절률 달성 확인
        if profit_rate >= target_profit_rate:
            sell_reasons.append(f"🎯 목표 익절 수익률 달성 (+{profit_rate:.2f}% >= +{target_profit_rate:.1f}%)")

        # 2. 손절 기준치 도달 확인
        if profit_rate <= stop_loss_rate:
            sell_reasons.append(f"⚠️ 손절 기준선 도달 ({profit_rate:.2f}% <= {stop_loss_rate:.1f}%)")
            is_urgent = True

        # 3. 기술적 데드크로스 분석
        candles = self.api.get_daily_chart(code, count=30)
        df = self.calculate_technical_indicators(candles)
        if df is not None and len(df) >= 20:
            last = df.iloc[-1]
            prev = df.iloc[-2]
            if prev["ma5"] >= prev["ma20"] and last["ma5"] < last["ma20"]:
                sell_reasons.append("📉 5일선이 20일선을 하향 이탈 (데드크로스 발생)")
            if last["rsi14"] > 75:
                sell_reasons.append(f"🔥 RSI 과열권 도달 ({last['rsi14']:.1f}) 차익실현 권고")

        if sell_reasons:
            return {
                "code": code,
                "name": name,
                "holding_qty": holding_qty,
                "sell_qty": holding_qty,
                "avg_buy_price": holding.get("avg_buy_price", 0.0),
                "current_price": current_price,
                "profit_rate": profit_rate,
                "profit_loss": holding.get("profit_loss", 0.0),
                "reasons": sell_reasons,
                "is_urgent": is_urgent
            }
        return None

    def run_premarket_screening(self) -> Dict[str, Any]:
        """개장 전 전체 스크리닝 실행 및 제안서 생성"""
        self.logger.info("=== 개장 전 자동 종목 스크리닝 시작 ===")
        
        # 1. 매수 후보 종목 발굴
        watchlist = config.CURRENT_SETTINGS.get("watchlist", [])
        buy_proposals = []
        for stock in watchlist:
            code = stock.get("code")
            name = stock.get("name")
            try:
                res = self.evaluate_buy_signals(code, name)
                if res:
                    buy_proposals.append(res)
            except Exception as e:
                self.logger.warning(f"[{name}({code})] 스크리닝 중 예외: {e}")

        # 점수 높은 순으로 정렬 후 상위 5개 선정
        buy_proposals.sort(key=lambda x: x["score"], reverse=True)
        top_buy_proposals = buy_proposals[:5]

        # 2. 현재 보유 주식 매도 추천 분석
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

        # 결과 저장
        proposals_data = {
            "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "buy_proposals": top_buy_proposals,
            "sell_proposals": sell_proposals,
            "holdings_count": len(holdings),
            "status": "READY"
        }

        self.save_proposals(proposals_data)
        self.logger.info(f"스크리닝 완료: 매수 추천 {len(top_buy_proposals)}건, 매도 추천 {len(sell_proposals)}건")
        return proposals_data

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
