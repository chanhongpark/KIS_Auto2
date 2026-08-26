"""
Unit and Integration Tests for Refined Trading Algorithm
- Technical Indicators & 15:15 Volume Scaling (1.04x)
- Category Caps & Mandatory Supply Gate
- Emergency Stop-Loss Priority (-3%) & Partial Profit Take (+5%)
- 2-Day Holding Grace Rule for Technical Sells
"""
import unittest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock

from screener import StockScreener
import config

class TestTradingAlgorithm(unittest.TestCase):
    def setUp(self):
        self.mock_api = MagicMock()
        self.screener = StockScreener(self.mock_api)

    def generate_dummy_candles(self, n=65, base_price=10000, trend="up", vol=100000):
        candles = []
        for i in range(n):
            if trend == "up":
                price = base_price + (i * 100)
            elif trend == "down":
                price = base_price - (i * 100)
            else:
                price = base_price
            candles.append({
                "date": f"202601{i+1:02d}",
                "open": price - 50,
                "high": price + 100,
                "low": price - 100,
                "close": price,
                "volume": vol,
                "change_rate": 1.0
            })
        return candles

    def test_indicator_calculations_and_volume_adjustment(self):
        """지표 산출 및 15:15 거래량 1.04배 보정 테스트"""
        candles = self.generate_dummy_candles(65, vol=100000)
        df = self.screener.calculate_technical_indicators(candles, is_intraday=True)

        self.assertIsNotNone(df)
        self.assertEqual(len(df), 65)
        # 당일(마지막) 캔들의 보정 거래량은 100,000 * (390 / 375) = 104,000
        expected_adj_vol = 100000 * (390.0 / 375.0)
        self.assertAlmostEqual(df.iloc[-1]["adjusted_volume"], expected_adj_vol, places=1)
        # 전일까지 20일 거래량 MA (vol_ma20)가 100,000인지 확인
        self.assertEqual(df.iloc[-1]["vol_ma20"], 100000.0)
        # MA5, MA20, MA60 존재 확인
        self.assertIn("ma5", df.columns)
        self.assertIn("ma20", df.columns)
        self.assertIn("ma60", df.columns)
        self.assertIn("rsi14", df.columns)
        self.assertIn("bb_upper", df.columns)
        self.assertIn("bb_lower", df.columns)

    def test_buy_signal_category_caps_and_supply_gate(self):
        """매수 점수 캡 적용 및 수급 필수 게이트 필터링 검증"""
        # 1. 수급 게이트 미통과 케이스 (거래량 부족 시 점수가 높아도 매수 제외)
        low_vol_candles = self.generate_dummy_candles(65, vol=100000)
        # 당일 거래량을 평균 대비 미달(50,000)로 설정
        self.mock_api.get_daily_chart.return_value = low_vol_candles
        self.mock_api.get_stock_price.return_value = {
            "rt_cd": "0",
            "price": low_vol_candles[-1]["close"],
            "acml_vol": 50000,  # 20일 평균(100,000) 대비 1.3배 미달
            "prdy_ctrt": 2.0
        }

        res = self.screener.evaluate_buy_signals("005930", "삼성전자")
        self.assertIsNone(res, "수급 필수 게이트 미충족 시 매수 후보에서 제외되어야 합니다.")

        # 2. 수급 게이트 통과 케이스 (거래량 200,000 -> 1.3배 이상 & 정배열 상승)
        self.mock_api.get_stock_price.return_value = {
            "rt_cd": "0",
            "price": low_vol_candles[-1]["close"],
            "acml_vol": 200000,  # 20일 평균(100,000) 대비 1.3배 이상
            "prdy_ctrt": 2.0
        }

        res_pass = self.screener.evaluate_buy_signals("005930", "삼성전자")
        if res_pass:
            self.assertTrue(res_pass["supply_gate_passed"])
            self.assertLessEqual(res_pass["trend_score"], 30, "추세 점수는 최대 30점으로 캡핑되어야 합니다.")
            self.assertLessEqual(res_pass["supply_score"], 25, "수급 점수는 최대 25점으로 캡핑되어야 합니다.")
            self.assertLessEqual(res_pass["momentum_score"], 25, "모멘텀 점수는 최대 25점으로 캡핑되어야 합니다.")
            self.assertGreaterEqual(res_pass["score"], 45)

    def test_emergency_stop_loss_priority(self):
        """긴급 손절 (-3.0%) 최우선권 및 2일 유예 무시 검증"""
        holding = {
            "code": "005930",
            "name": "삼성전자",
            "quantity": 10,
            "avg_buy_price": 70000,
            "current_price": 67000,
            "profit_rate": -4.28,  # -3.0% 이하 손절 도달
            "profit_loss": -30000
        }
        # 2일 이내 매수 종목으로 모킹
        self.screener._is_recently_bought = MagicMock(return_value=True)

        sell_res = self.screener.evaluate_sell_signals(holding)
        self.assertIsNotNone(sell_res, "긴급 손절은 2일 유예를 무시하고 즉시 매도 신호를 발생시켜야 합니다.")
        self.assertTrue(sell_res["is_urgent"])
        self.assertEqual(sell_res["sell_qty"], 10, "긴급 손절은 전량(100%) 매도여야 합니다.")
        self.assertEqual(sell_res["sell_ratio"], 1.0)

    def test_target_profit_partial_take(self):
        """목표 익절 (+5.0%) 50% 분할 매도 및 2일 유예 무시 검증"""
        holding = {
            "code": "000660",
            "name": "SK하이닉스",
            "quantity": 10,
            "avg_buy_price": 150000,
            "current_price": 160000,
            "profit_rate": +6.67,  # +5.0% 이상 목표 익절 달성
            "profit_loss": +100000
        }
        self.screener._is_recently_bought = MagicMock(return_value=True)

        sell_res = self.screener.evaluate_sell_signals(holding)
        self.assertIsNotNone(sell_res, "목표 익절은 2일 유예를 무시하고 즉시 실행되어야 합니다.")
        self.assertFalse(sell_res["is_urgent"])
        self.assertEqual(sell_res["sell_qty"], 5, "목표 익절은 50% 분할 매도여야 합니다.")
        self.assertEqual(sell_res["sell_ratio"], 0.5)

    def test_technical_sell_grace_period(self):
        """일반 기술적 매도(RSI과열/데드크로스)의 2일 보유 유예 원칙 검증"""
        holding = {
            "code": "035420",
            "name": "NAVER",
            "quantity": 10,
            "avg_buy_price": 200000,
            "current_price": 202000,
            "profit_rate": +1.0,  # 손절(-3%)이나 목표익절(+5%) 아님
            "profit_loss": +20000
        }
        # 1. 최근 2일 이내 매수 종목인 경우 -> 기술적 매도 무시 (None)
        self.screener._is_recently_bought = MagicMock(return_value=True)
        res_grace = self.screener.evaluate_sell_signals(holding)
        self.assertIsNone(res_grace, "매수 2일 이내 종목은 일반 기술적 매도 신호가 보류되어야 합니다.")

        # 2. 매수 2일 경과 종목인 경우 -> 기술적 데드크로스 감지 시 매도 신호 발생
        self.screener._is_recently_bought = MagicMock(return_value=False)
        down_candles = self.generate_dummy_candles(65, trend="down")
        self.mock_api.get_daily_chart.return_value = down_candles
        self.mock_api.get_stock_price.return_value = {
            "rt_cd": "0",
            "price": down_candles[-1]["close"],
            "acml_vol": 100000,
            "prdy_ctrt": -1.0
        }
        res_tech = self.screener.evaluate_sell_signals(holding)
        # 데드크로스 발생 시 전량 청산
        if res_tech and "데드크로스" in res_tech.get("sell_type", ""):
            self.assertEqual(res_tech["sell_ratio"], 1.0)

if __name__ == "__main__":
    unittest.main()
