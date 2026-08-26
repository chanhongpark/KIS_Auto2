"""
Backtesting Engine for KIS Auto Trading Strategy
FinanceDataReader 기반 과거 데이터 시뮬레이션
StockScreener(screener.py)의 매수/매도 평가 함수(evaluate_buy_signals_from_df, evaluate_sell_signals_from_df)를 100% 동일하게 직접 호출하여 실행합니다.
"""
import logging
import datetime
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
import FinanceDataReader as fdr

from screener import StockScreener
import config

logger = logging.getLogger("Backtester")

class Backtester:
    def __init__(
        self,
        start_date: str,
        end_date: str,
        universe: Optional[List[Dict[str, str]]] = None,
        initial_capital: float = 10000000.0,
        budget_per_stock: float = 1000000.0,
        max_holdings: int = 5,
        target_profit_rate: float = 0.05,
        stop_loss_rate: float = -0.03,
        fee_rate: float = 0.0015,       # 매수/매도 수수료 (0.15%)
        tax_rate: float = 0.0020        # 매도 시 거래세 (0.20%)
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.universe = universe or config.CURRENT_SETTINGS.get("watchlist", [])
        self.initial_capital = initial_capital
        self.budget_per_stock = budget_per_stock
        self.max_holdings = max_holdings
        self.target_profit_rate = target_profit_rate
        self.stop_loss_rate = stop_loss_rate
        self.fee_rate = fee_rate
        self.tax_rate = tax_rate
        self.screener = StockScreener()

    def fetch_universe_data(self, progress_callback=None) -> Dict[str, pd.DataFrame]:
        """유니버스 전 종목에 대해 백테스트 시작일 이전 100영업일부터의 일봉 데이터 다운로드"""
        data_map = {}
        start_dt = pd.to_datetime(self.start_date) - datetime.timedelta(days=120)
        start_str = start_dt.strftime("%Y-%m-%d")

        total = len(self.universe)
        for idx, item in enumerate(self.universe):
            code = item.get("code")
            name = item.get("name", code)
            try:
                df = fdr.DataReader(code, start_str, self.end_date)
                if df is not None and not df.empty and len(df) >= 60:
                    df = df.reset_index()
                    rename_cols = {}
                    for col in df.columns:
                        col_lower = str(col).lower()
                        if "date" in col_lower or "날짜" in col_lower:
                            rename_cols[col] = "date"
                        elif "close" in col_lower or "종가" in col_lower:
                            rename_cols[col] = "close"
                        elif "open" in col_lower or "시가" in col_lower:
                            rename_cols[col] = "open"
                        elif "high" in col_lower or "고가" in col_lower:
                            rename_cols[col] = "high"
                        elif "low" in col_lower or "저가" in col_lower:
                            rename_cols[col] = "low"
                        elif "volume" in col_lower or "거래량" in col_lower:
                            rename_cols[col] = "volume"
                    df = df.rename(columns=rename_cols)
                    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y%m%d")
                    data_map[code] = {
                        "name": name,
                        "df": df
                    }
            except Exception as e:
                logger.warning(f"[{name}({code})] 백테스트 데이터 수집 실패: {e}")

            if progress_callback:
                progress_callback(min(1.0, (idx + 1) / total * 0.4))

        return data_map

    def run(self, progress_callback=None) -> Dict[str, Any]:
        """screener.py의 공통 알고리즘 함수를 사용하여 백테스팅 실행"""
        logger.info(f"=== [Backtester] 백테스트 시작: {self.start_date} ~ {self.end_date} ===")
        universe_data = self.fetch_universe_data(progress_callback=progress_callback)

        if not universe_data:
            return {"error": "백테스트 유니버스 데이터를 불러오지 못했습니다."}

        all_dates = set()
        for code, info in universe_data.items():
            df = info["df"]
            df_filtered = df[df["date"] >= self.start_date.replace("-", "")]
            all_dates.update(df_filtered["date"].tolist())

        trading_dates = sorted(list(all_dates))
        if not trading_dates:
            return {"error": "지정된 기간 내 거래일 데이터가 존재하지 않습니다."}

        cash = self.initial_capital
        holdings = {}  # code -> {qty, avg_buy_price, buy_date, holding_days, name}
        trade_history = []
        daily_equity = []

        total_days = len(trading_dates)

        for day_idx, current_date in enumerate(trading_dates):
            # -------------------------------------------------------------
            # 1. 보유 종목 매도 & 리스크 관리 (screener.py 동일 로직 호출)
            # -------------------------------------------------------------
            to_remove = []
            for code, pos in list(holdings.items()):
                pos["holding_days"] += 1
                stock_info = universe_data.get(code)
                if not stock_info:
                    continue

                df_stock = stock_info["df"]
                sub_df = df_stock[df_stock["date"] <= current_date]
                if sub_df.empty:
                    continue

                current_row = sub_df.iloc[-1]
                close_price = float(current_row["close"])
                high_price = float(current_row["high"])
                low_price = float(current_row["low"])
                avg_price = pos["avg_buy_price"]

                # 당일 최고/최저/종가 수익률 산출
                low_profit_rate = (low_price - avg_price) / avg_price * 100
                high_profit_rate = (high_price - avg_price) / avg_price * 100
                close_profit_rate = (close_price - avg_price) / avg_price * 100

                holding_dict = {
                    "code": code,
                    "name": pos["name"],
                    "quantity": pos["qty"],
                    "avg_buy_price": avg_price,
                    "current_price": close_price,
                    "profit_rate": close_profit_rate,
                    "profit_loss": (close_price - avg_price) * pos["qty"]
                }

                # 장중 저가/고가 기준 긴급 손절 / 목표 익절 우선 감지
                sell_signal = None
                sell_price = close_price

                # [1] 긴급 손절 (일중 저가가 손절선 터치 시)
                if low_profit_rate <= self.stop_loss_rate * 100:
                    holding_dict["profit_rate"] = low_profit_rate
                    sell_signal = self.screener.evaluate_sell_signals_from_df(
                        holding=holding_dict,
                        df=None,
                        is_recently_bought=False,
                        stop_loss_rate=self.stop_loss_rate,
                        target_profit_rate=self.target_profit_rate
                    )
                    sell_price = min(close_price, avg_price * (1 + self.stop_loss_rate))

                # [2] 목표 익절 (일중 고가가 목표 익절선 터치 시)
                elif high_profit_rate >= self.target_profit_rate * 100:
                    holding_dict["profit_rate"] = high_profit_rate
                    sell_signal = self.screener.evaluate_sell_signals_from_df(
                        holding=holding_dict,
                        df=None,
                        is_recently_bought=False,
                        stop_loss_rate=self.stop_loss_rate,
                        target_profit_rate=self.target_profit_rate
                    )
                    sell_price = max(close_price, avg_price * (1 + self.target_profit_rate))

                # [3] 기술적 매도 (RSI 과열 및 데드크로스)
                else:
                    candles = sub_df.tail(65).to_dict("records")
                    df_tech = self.screener.calculate_technical_indicators(candles, is_intraday=False)
                    is_recently_bought = (pos["holding_days"] < 2)
                    sell_signal = self.screener.evaluate_sell_signals_from_df(
                        holding=holding_dict,
                        df=df_tech,
                        is_recently_bought=is_recently_bought,
                        stop_loss_rate=self.stop_loss_rate,
                        target_profit_rate=self.target_profit_rate
                    )
                    sell_price = close_price

                # 매도 신호 발생 시 주문 정산
                if sell_signal:
                    sell_qty = sell_signal.get("sell_qty", pos["qty"])
                    sell_type = sell_signal.get("sell_type", "매도")
                    sell_reason = " • ".join(sell_signal.get("reasons", []))

                    gross_amt = sell_qty * sell_price
                    fee_tax = gross_amt * (self.fee_rate + self.tax_rate)
                    net_amt = gross_amt - fee_tax
                    cash += net_amt

                    profit_krw = net_amt - (sell_qty * avg_price * (1 + self.fee_rate))
                    profit_pct = (profit_krw / (sell_qty * avg_price)) * 100

                    trade_history.append({
                        "date": current_date,
                        "code": code,
                        "name": pos["name"],
                        "action": "SELL",
                        "sell_type": sell_type,
                        "price": sell_price,
                        "qty": sell_qty,
                        "amount": net_amt,
                        "profit_krw": profit_krw,
                        "profit_pct": profit_pct,
                        "holding_days": pos["holding_days"],
                        "reason": sell_reason
                    })

                    pos["qty"] -= sell_qty
                    if pos["qty"] <= 0:
                        to_remove.append(code)

            for code in to_remove:
                if code in holdings:
                    del holdings[code]

            # -------------------------------------------------------------
            # 2. 15:15 종가 매수 스크리닝 (screener.py 동일 로직 호출)
            # -------------------------------------------------------------
            available_slots = self.max_holdings - len(holdings)
            if available_slots > 0 and cash >= self.budget_per_stock:
                held_codes = set(holdings.keys())
                buy_candidates = []

                for code, stock_info in universe_data.items():
                    df_stock = stock_info["df"]
                    sub_df = df_stock[df_stock["date"] <= current_date]
                    if len(sub_df) < 25:
                        continue

                    candles = sub_df.tail(65).to_dict("records")
                    df_tech = self.screener.calculate_technical_indicators(candles, is_intraday=False)
                    
                    # screener.py의 공통 evaluate_buy_signals_from_df 직접 호출!
                    buy_eval = self.screener.evaluate_buy_signals_from_df(
                        df=df_tech,
                        code=code,
                        name=stock_info["name"],
                        held_codes=held_codes,
                        budget=self.budget_per_stock
                    )

                    if buy_eval:
                        buy_candidates.append(buy_eval)

                # 점수 높은 순으로 정렬 후 상위 슬롯 매수 집행
                buy_candidates.sort(key=lambda x: x["score"], reverse=True)
                for cand in buy_candidates[:available_slots]:
                    code = cand["code"]
                    if code in holdings:
                        continue
                    buy_price = cand["current_price"]
                    if buy_price <= 0:
                        continue

                    max_buy_amt = min(self.budget_per_stock, cash)
                    buy_qty = int(max_buy_amt // (buy_price * (1 + self.fee_rate)))
                    if buy_qty <= 0:
                        continue

                    total_cost = buy_qty * buy_price * (1 + self.fee_rate)
                    cash -= total_cost

                    holdings[code] = {
                        "name": cand["name"],
                        "qty": buy_qty,
                        "avg_buy_price": buy_price,
                        "buy_date": current_date,
                        "holding_days": 0
                    }

                    reasons_str = " • ".join(cand.get("reasons", []))
                    trade_history.append({
                        "date": current_date,
                        "code": code,
                        "name": cand["name"],
                        "action": "BUY",
                        "sell_type": cand.get("buy_type", "신규매수"),
                        "price": buy_price,
                        "qty": buy_qty,
                        "amount": total_cost,
                        "profit_krw": 0.0,
                        "profit_pct": 0.0,
                        "holding_days": 0,
                        "reason": f"🎯 종가 매수 점수 {cand['score']}점 (추세 {cand['trend_score']}/수급 {cand['supply_score']}/모멘텀 {cand['momentum_score']}) | {reasons_str}"
                    })

            # -------------------------------------------------------------
            # 3. 당일 평가 총자산(Equity) 기록
            # -------------------------------------------------------------
            stock_eval = 0.0
            for code, pos in holdings.items():
                stock_info = universe_data.get(code)
                if stock_info:
                    df_stock = stock_info["df"]
                    day_rows = df_stock[df_stock["date"] == current_date]
                    if not day_rows.empty:
                        c_p = float(day_rows.iloc[0]["close"])
                        stock_eval += pos["qty"] * c_p
                    else:
                        stock_eval += pos["qty"] * pos["avg_buy_price"]

            tot_equity = cash + stock_eval
            daily_equity.append({
                "date": current_date,
                "equity": tot_equity,
                "cash": cash,
                "stock_eval": stock_eval,
                "holding_count": len(holdings)
            })

            if progress_callback:
                progress_callback(0.4 + (day_idx + 1) / total_days * 0.6)

        # -----------------------------------------------------------------
        # 4. 종합 성과 지표(Metrics) 계산
        # -----------------------------------------------------------------
        eq_df = pd.DataFrame(daily_equity)
        if eq_df.empty:
            return {"error": "시뮬레이션 결과 데이터가 비어 있습니다."}

        eq_df["return_pct"] = (eq_df["equity"] - self.initial_capital) / self.initial_capital * 100
        eq_df["peak"] = eq_df["equity"].cummax()
        eq_df["drawdown"] = (eq_df["equity"] - eq_df["peak"]) / eq_df["peak"] * 100

        final_equity = float(eq_df.iloc[-1]["equity"])
        total_return_pct = (final_equity - self.initial_capital) / self.initial_capital * 100
        mdd_pct = float(eq_df["drawdown"].min())

        days_total = max(1, (pd.to_datetime(self.end_date) - pd.to_datetime(self.start_date)).days)
        years = days_total / 365.25
        cagr_pct = ((final_equity / self.initial_capital) ** (1 / years) - 1) * 100 if final_equity > 0 and years > 0 else 0.0

        sell_trades = [t for t in trade_history if t["action"] == "SELL"]
        win_trades = [t for t in sell_trades if t["profit_krw"] > 0]
        loss_trades = [t for t in sell_trades if t["profit_krw"] <= 0]

        win_rate = (len(win_trades) / len(sell_trades) * 100) if sell_trades else 0.0
        total_win_amt = sum([t["profit_krw"] for t in win_trades])
        total_loss_amt = abs(sum([t["profit_krw"] for t in loss_trades]))
        profit_factor = (total_win_amt / total_loss_amt) if total_loss_amt > 0 else (999.0 if total_win_amt > 0 else 0.0)

        benchmark_df = None
        try:
            kospi = fdr.DataReader("KS11", self.start_date, self.end_date).reset_index()
            if not kospi.empty:
                kospi["date"] = pd.to_datetime(kospi["Date"]).dt.strftime("%Y%m%d")
                k_start = float(kospi.iloc[0]["Close"])
                kospi["benchmark_return"] = (kospi["Close"] - k_start) / k_start * 100
                benchmark_df = kospi[["date", "Close", "benchmark_return"]].rename(columns={"Close": "kospi_close"})
        except Exception as e:
            logger.warning(f"KOSPI 벤치마크 데이터 로드 실패: {e}")

        return {
            "summary": {
                "initial_capital": self.initial_capital,
                "final_equity": final_equity,
                "total_return_pct": total_return_pct,
                "cagr_pct": cagr_pct,
                "mdd_pct": mdd_pct,
                "total_trades": len(trade_history),
                "sell_trades_count": len(sell_trades),
                "win_rate": win_rate,
                "win_count": len(win_trades),
                "loss_count": len(loss_trades),
                "profit_factor": profit_factor,
                "total_profit_krw": final_equity - self.initial_capital
            },
            "daily_equity": eq_df,
            "trade_history": pd.DataFrame(trade_history),
            "benchmark_df": benchmark_df
        }
