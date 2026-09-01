"""
KIS Auto Trader - Streamlit Control Center
한국투자증권 API 기반 주식 자동매매 & 제어 대시보드
15:15 종가 매수 및 실시간 리스크 관리(손절 최우선 / 분할 익절) & FDR 백테스팅
"""
import time
import streamlit as st

import config
from kis_api import KISApiClient
from screener import StockScreener
from scheduler import start_scheduler
from time_utils import now_str
from ui import (
    apply_custom_styles,
    render_dashboard,
    render_screener,
    render_backtest,
    render_settings
)

# 페이지 기본 설정
st.set_page_config(
    page_title="KIS Auto Trader",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 테마 CSS 적용
apply_custom_styles()

# 세션 상태에 활성 페이지 저장 (기본값: dashboard)
if "nav_page" not in st.session_state or st.session_state["nav_page"] not in ["dashboard", "screener", "backtest", "settings"]:
    st.session_state["nav_page"] = "dashboard"

# 1회 스케줄러 및 API 초기화 (세션 상태 보존)
@st.cache_resource
def init_system():
    scheduler = start_scheduler()
    api = KISApiClient()
    token_ok = api.get_access_token()
    if not token_ok:
        st.warning("⚠️ KIS API 토큰 발급에 실패했습니다. 네트워크 연결 및 API 설정을 확인하세요.")
    return scheduler, api

scheduler, api = init_system()
screener = StockScreener(api)

# 실시간 매도 신호 감지 fragment (독립적으로 60초마다 실행)
@st.fragment(run_every=60)
def realtime_detection_fragment():
    last_check = st.session_state.get("last_realtime_check", 0.0)
    now_ts = time.time()
    if now_ts - last_check >= 300:
        st.session_state["last_realtime_check"] = now_ts
        with st.spinner("🔄 5분 주기 매도 신호 자동 체크 중..."):
            updated = screener.check_sell_signals_now()
            st.session_state["last_check_time"] = now_str("%H:%M:%S")
            st.success(f"🔄 자동 체크 완료: {len(updated.get('sell_proposals', []))}건의 매도 신호 감지")
            time.sleep(1)
            st.rerun()
    else:
        st.caption("⏳ 5분 주기로 실시간 감시가 실행됩니다.")

# ==============================================================================
# 심플 & 통합 사이드바 (Consolidated Navigation)
# ==============================================================================
with st.sidebar:
    st.markdown("""
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
            <div style="background: linear-gradient(135deg, #0284c7, #6366f1); padding: 8px; border-radius: 10px; display: flex; align-items: center; justify-content: center;">
                <span style="font-size: 1.3rem;">⚡</span>
            </div>
            <div>
                <div style="font-size: 1.15rem; font-weight: 800; color: #f8fafc; letter-spacing: -0.02em;">KIS AUTO TERMINAL</div>
                <div style="font-size: 0.7rem; color: #64748b; font-weight: 600; letter-spacing: 0.05em;">ALGORITHMIC TRADING SYSTEM</div>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    is_mock = config.CURRENT_SETTINGS.get("mock_trading", True)
    if is_mock:
        st.markdown("<div class='badge-mock'><span class='status-dot dot-mock'></span>VTS SIMULATION ACTIVE</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='badge-real'><span class='status-dot dot-real'></span>LIVE TRADING ACTIVE</div>", unsafe_allow_html=True)
        
    st.markdown(f"""
        <div class="sidebar-account-box">
            <div style="font-size: 0.72rem; color: #64748b; font-weight: 600;">ACTIVE ACCOUNT</div>
            <div style="font-size: 0.88rem; font-weight: 700; color: #e2e8f0; font-family: monospace;">{config.CANO}-{config.ACNT_PRDT_CD}</div>
            <div style="font-size: 0.72rem; color: #94a3b8; margin-top: 4px;">⏰ 종가 매수: 매일 15:15 KST</div>
        </div>
    """, unsafe_allow_html=True)

    # 4대 핵심 통합 네비게이션 메뉴
    st.markdown("<div class='nav-header'>🧭 NAVIGATION • 메인 메뉴</div>", unsafe_allow_html=True)
    main_menu = [
        ("dashboard", "📊 자산 & 포트폴리오 (Dashboard)"),
        ("screener", "🎯 15:15 종가 스크리닝 (Screener)"),
        ("backtest", "🧪 퀀트 백테스터 (Backtester)"),
        ("settings", "⚙️ 시스템 환경설정 (Settings)")
    ]

    for key, label in main_menu:
        is_active = (st.session_state["nav_page"] == key)
        if st.button(
            label,
            key=f"nav_btn_{key}",
            type="primary" if is_active else "secondary",
            width="stretch"
        ):
            st.session_state["nav_page"] = key
            st.rerun()

    st.caption("KIS Auto Trading Engine v2.5 • Unified Terminal")

# 계좌 및 제안서 데이터 조회
balance_data = api.get_account_balance()
summary = balance_data.get("summary", {})
holdings = balance_data.get("holdings", [])
proposals = screener.load_proposals()

# 매도 추천에서 이미 매도 완료된 종목 제외
holding_codes = {h["code"] for h in holdings}
if proposals.get("sell_proposals"):
    proposals["sell_proposals"] = [
        s for s in proposals["sell_proposals"]
        if s.get("code") in holding_codes
    ]

# 통합 페이지 라우팅
nav_page = st.session_state["nav_page"]

if nav_page == "dashboard":
    render_dashboard(api, screener, summary, holdings, proposals, holding_codes, realtime_detection_fragment)
elif nav_page == "screener":
    render_screener(api, screener, proposals, holding_codes)
elif nav_page == "backtest":
    render_backtest()
elif nav_page == "settings":
    render_settings()
