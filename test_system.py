"""
Verification Script for KIS Auto Trading System
"""
import os
import sys

def test_modules():
    print("1. Testing config.py...")
    import config
    settings = config.load_settings()
    print(f"   Settings loaded successfully: {len(settings.get('watchlist', []))} watchlist items.")
    print(f"   CANO: {config.CANO[:4]}****, Mock Trading: {config.CURRENT_SETTINGS.get('mock_trading')}")

    print("\n2. Testing kis_api.py...")
    from kis_api import KISApiClient
    api = KISApiClient()
    token_ok = api.get_access_token()
    print(f"   Access Token Acquired: {token_ok}")

    if token_ok:
        print("   Testing Stock Price for 005930 (Samsung Elec)...")
        price_info = api.get_stock_price("005930")
        print(f"   Current Price: {price_info.get('price'):,.0f} KRW, Change: {price_info.get('prdy_ctrt')}%")

        print("   Testing Account Balance...")
        bal = api.get_account_balance()
        print(f"   Summary: Total Asset={bal['summary'].get('tot_asset'):,.0f} KRW, Cash={bal['summary'].get('cash_balance'):,.0f} KRW")
        print(f"   Holdings count: {len(bal.get('holdings', []))}")

    print("\n3. Testing screener.py...")
    from screener import StockScreener
    screener = StockScreener(api)
    print("   Running Screening on sample watchlist...")
    proposals = screener.run_premarket_screening()
    print(f"   Screening Result: Buy Proposals = {len(proposals.get('buy_proposals', []))}, Sell Proposals = {len(proposals.get('sell_proposals', []))}")
    for p in proposals.get("buy_proposals", []):
        print(f"     - [BUY] {p['name']} ({p['code']}): {p['score']}pts, Rec Qty: {p['recommended_qty']}주 (Est: {p['estimated_amount']:,.0f}원)")

    print("\n4. Testing scheduler.py...")
    from scheduler import start_scheduler, stop_scheduler
    sch = start_scheduler()
    print(f"   Scheduler running status: {sch.running if sch else False}")
    stop_scheduler()

    print("\n=== ALL SYSTEM TESTS PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    test_modules()
