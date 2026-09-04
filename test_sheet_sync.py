"""
Google Sheets 연동 및 동기화 테스트 스크립트
"""
import os
import sys

def test_google_sheet_connection():
    print("=== Google Sheet 연동 테스트 시작 ===")
    from google_sheet_manager import GoogleSheetManager, get_sheet_manager
    
    mgr = get_sheet_manager()
    print(f"1. GSPREAD_AVAILABLE: {mgr.enabled}")
    print(f"2. Spreadsheet Name: {mgr.sheet_name}")
    print(f"3. Spreadsheet Key: {mgr.sheet_key}")
    print(f"4. Connected: {mgr.is_connected}")
    
    if mgr.is_connected:
        print(f"   스프레드시트 제목: {mgr.spreadsheet.title}")
        print("   워크시트 목록:", [ws.title for ws in mgr.spreadsheet.worksheets()])
        
        # Settings 동기화 테스트
        import config
        test_settings = config.load_settings()
        sync_ok = mgr.sync_settings_to_sheet(test_settings)
        print(f"5. Settings 동기화 결과: {sync_ok}")
        
        # PositionsState 동기화 테스트
        pos_test = {
            "005930": {
                "name": "삼성전자",
                "avg_buy_price": 75000,
                "highest_price": 78000,
                "is_partial_sold": False,
                "updated_at": "2026-09-04 21:30:00"
            }
        }
        pos_ok = mgr.sync_positions_state_to_sheet(pos_test)
        print(f"6. PositionsState 동기화 결과: {pos_ok}")
        
        # Cooldown 동기화 테스트
        cd_test = {"000660": "20260910"}
        cd_ok = mgr.sync_cooldown_to_sheet(cd_test)
        print(f"7. Cooldown 동기화 결과: {cd_ok}")
        
    else:
        print("[NOTICE] 구글 시트에 연결되지 않았습니다 (GCP 키 권한 또는 시트 공유 설정을 확인하세요).")
        print("         로컬 JSON 모드로 안전하게 폴백 동작합니다.")

if __name__ == "__main__":
    test_google_sheet_connection()
