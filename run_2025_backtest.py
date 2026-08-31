"""
Run backtest for 2025-01-01 to 2025-12-31 and analyze performance vs KOSPI 100
"""
import os
import sys
import json
import pandas as pd
import numpy as np
import FinanceDataReader as fdr

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from backtester import Backtester
import config

def run_analysis():
    print("=== [2025 Backtest Analysis] Starting Simulation ===")
    start_date = "2025-01-01"
    end_date = "2025-12-31"

    universe = config.CURRENT_SETTINGS.get("watchlist", [])
    print(f"Universe size: {len(universe)} stocks")

    tester = Backtester(
        start_date=start_date,
        end_date=end_date,
        universe=universe,
        initial_capital=10000000.0,
        budget_per_stock=1000000.0,
        max_holdings=5,
        target_profit_rate=0.08,
        stop_loss_rate=-0.05,
        fee_rate=0.0015,
        tax_rate=0.0020
    )

    res = tester.run()

    if "error" in res:
        print(f"Error: {res['error']}")
        return

    summary = res["summary"]
    daily_eq = res["daily_equity"]
    trades_df = res["trade_history"]

    output_lines = []
    output_lines.append("="*60)
    output_lines.append(" [Strategy Performance Summary (2025 Full Year)]")
    output_lines.append(f" Initial Capital: {summary['initial_capital']:,.0f} KRW")
    output_lines.append(f" Final Equity: {summary['final_equity']:,.0f} KRW")
    output_lines.append(f" Total Profit/Loss: {summary['total_profit_krw']:+,.0f} KRW")
    output_lines.append(f" Total Return: {summary['total_return_pct']:+.2f}%")
    output_lines.append(f" CAGR: {summary['cagr_pct']:+.2f}%")
    output_lines.append(f" Max Drawdown (MDD): {summary['mdd_pct']:.2f}%")
    output_lines.append(f" Total Trades: {summary['total_trades']} (Closed Trades: {summary['sell_trades_count']})")
    output_lines.append(f" Win Rate: {summary['win_rate']:.1f}% ({summary['win_count']} Wins / {summary['loss_count']} Losses)")
    output_lines.append(f" Profit Factor: {summary['profit_factor']:.2f}")
    output_lines.append("="*60)

    # 1. KOSPI (KS11)
    k_ret, k_mdd = 0.0, 0.0
    try:
        kospi = fdr.DataReader("KS11", start_date, end_date)
        if not kospi.empty:
            k_start = float(kospi.iloc[0]["Close"])
            k_end = float(kospi.iloc[-1]["Close"])
            k_ret = (k_end - k_start) / k_start * 100
            k_mdd = ((kospi["Close"] - kospi["Close"].cummax()) / kospi["Close"].cummax()).min() * 100
            output_lines.append(f"\n [KOSPI Index (KS11)]")
            output_lines.append(f" Start: {k_start:,.2f} -> End: {k_end:,.2f}")
            output_lines.append(f" Return: {k_ret:+.2f}%")
            output_lines.append(f" MDD: {k_mdd:.2f}%")
    except Exception as e:
        output_lines.append(f"KOSPI index error: {e}")

    # 2. KOSPI 200 (069500)
    kd_ret, kd_mdd = 0.0, 0.0
    try:
        kodex200 = fdr.DataReader("069500", start_date, end_date)
        if not kodex200.empty:
            kd_start = float(kodex200.iloc[0]["Close"])
            kd_end = float(kodex200.iloc[-1]["Close"])
            kd_ret = (kd_end - kd_start) / kd_start * 100
            kd_mdd = ((kodex200["Close"] - kodex200["Close"].cummax()) / kodex200["Close"].cummax()).min() * 100
            output_lines.append(f"\n [KOSPI 200 (KODEX 200)]")
            output_lines.append(f" Start: {kd_start:,.0f} -> End: {kd_end:,.0f}")
            output_lines.append(f" Return: {kd_ret:+.2f}%")
            output_lines.append(f" MDD: {kd_mdd:.2f}%")
    except Exception as e:
        output_lines.append(f"KODEX 200 error: {e}")

    # 3. KOSPI 100 (KS100)
    try:
        ks100 = fdr.DataReader("KS100", start_date, end_date)
        if not ks100.empty:
            ks100_start = float(ks100.iloc[0]["Close"])
            ks100_end = float(ks100.iloc[-1]["Close"])
            ks100_ret = (ks100_end - ks100_start) / ks100_start * 100
            ks100_mdd = ((ks100["Close"] - ks100["Close"].cummax()) / ks100["Close"].cummax()).min() * 100
            output_lines.append(f"\n [KOSPI 100 Index (KS100)]")
            output_lines.append(f" Start: {ks100_start:,.2f} -> End: {ks100_end:,.2f}")
            output_lines.append(f" Return: {ks100_ret:+.2f}%")
            output_lines.append(f" MDD: {ks100_mdd:.2f}%")
    except Exception as e:
        output_lines.append(f"KS100 error: {e}")

    # 4. Sell Type Breakdown
    if not trades_df.empty:
        sells = trades_df[trades_df["action"] == "SELL"]
        output_lines.append("\n" + "="*60)
        output_lines.append(" [Trades Breakdown by Exit Type]")
        type_group = sells.groupby("sell_type").agg(
            Count=("profit_krw", "count"),
            Total_Profit_KRW=("profit_krw", "sum"),
            Avg_Return_Pct=("profit_pct", "mean"),
            Avg_Hold_Days=("holding_days", "mean")
        )
        output_lines.append(type_group.to_string())

        output_lines.append("\n" + "="*60)
        output_lines.append(" [Top 5 Profit vs Top 5 Loss Stocks]")
        stock_group = sells.groupby("name").agg(
            Trades=("profit_krw", "count"),
            Total_Profit_KRW=("profit_krw", "sum"),
            Avg_Return_Pct=("profit_pct", "mean")
        ).sort_values(by="Total_Profit_KRW", ascending=False)
        output_lines.append("\n-- Top 5 Stocks --")
        output_lines.append(stock_group.head(5).to_string())
        output_lines.append("\n-- Worst 5 Stocks --")
        output_lines.append(stock_group.tail(5).to_string())

    full_text = "\n".join(output_lines)
    print(full_text)

    # Save to file
    with open("backtest_2025_result.txt", "w", encoding="utf-8") as f:
        f.write(full_text)

if __name__ == "__main__":
    run_analysis()
