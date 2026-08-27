"""
KIS Auto Trader - Streamlit Control Center (Page Navigation)
한국투자증권 API 기반 주식 자동매매 & 제어 대시보드
15:15 종가 매수 및 실시간 리스크 관리(손절 최우선 / 분할 익절) & FinanceDataReader 백테스팅
"""
import os
import time
import datetime
from typing import Optional, Dict, Any, List
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config
from kis_api import KISApiClient
from screener import StockScreener
from scheduler import start_scheduler
from telegram_notifier import notifier
from time_utils import now_str, today
from backtester import Backtester

# 페이지 기본 설정
st.set_page_config(
    page_title="KIS Auto Trader",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Luxury Modern Terminal UI
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@300;400;500;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, sans-serif;
    }
    
    /* 사이드바 배경 및 테두리 */
    [data-testid="stSidebar"] {
        background-color: #0b0f19;
        border-right: 1px solid #1e293b;
    }
    
    /* 기본 사이드바 버튼 (비활성 메뉴) */
    [data-testid="stSidebar"] .stButton > button[kind="secondary"] {
        background-color: #111827 !important;
        border: 1px solid #1f2937 !important;
        color: #94a3b8 !important;
        border-radius: 10px !important;
        padding: 12px 16px !important;
        font-size: 0.92rem !important;
        font-weight: 500 !important;
        text-align: left !important;
        justify-content: flex-start !important;
        display: flex !important;
        width: 100% !important;
        margin-bottom: 6px !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    
    [data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {
        background-color: #1e293b !important;
        border-color: #38bdf8 !important;
        color: #f8fafc !important;
        transform: translateX(4px) !important;
    }
    
    /* 활성(Selected) 메뉴 버튼 */
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, rgba(14, 165, 233, 0.2), rgba(99, 102, 241, 0.25)) !important;
        border: 1px solid #38bdf8 !important;
        color: #38bdf8 !important;
        box-shadow: 0 0 15px rgba(56, 189, 248, 0.2) !important;
        border-radius: 10px !important;
        padding: 12px 16px !important;
        font-size: 0.92rem !important;
        font-weight: 700 !important;
        text-align: left !important;
        justify-content: flex-start !important;
        display: flex !important;
        width: 100% !important;
        margin-bottom: 6px !important;
    }
    
    /* 상태 배지 */
    .badge-mock {
        background: linear-gradient(135deg, rgba(245, 158, 11, 0.15), rgba(217, 119, 6, 0.25));
        color: #fbbf24;
        border: 1px solid rgba(245, 158, 11, 0.4);
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        padding: 4px 10px;
        border-radius: 20px;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }
    .badge-real {
        background: linear-gradient(135deg, rgba(239, 68, 68, 0.15), rgba(185, 28, 28, 0.25));
        color: #f87171;
        border: 1px solid rgba(239, 68, 68, 0.4);
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        padding: 4px 10px;
        border-radius: 20px;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }
    
    .status-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        display: inline-block;
    }
    .dot-mock { background-color: #fbbf24; box-shadow: 0 0 8px #fbbf24; }
    .dot-real { background-color: #f87171; box-shadow: 0 0 8px #f87171; }
    
    .sidebar-account-box {
        background-color: #111827;
        border: 1px solid #1f2937;
        border-radius: 10px;
        padding: 12px 14px;
        margin-top: 10px;
        margin-bottom: 15px;
    }

    .nav-header {
        font-size: 0.72rem;
        font-weight: 700;
        color: #64748b;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        margin-bottom: 10px;
    }

    .score-badge {
        background: rgba(30, 41, 59, 0.8);
        border: 1px solid #334155;
        border-radius: 6px;
        padding: 4px 8px;
        font-size: 0.8rem;
        font-weight: 600;
        color: #38bdf8;
        display: inline-block;
        margin-right: 4px;
    }

    .timeline-container {
        background: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 12px;
        padding: 14px 18px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# 세션 상태에 활성 페이지 저장
if "nav_page" not in st.session_state:
    st.session_state["nav_page"] = "overview"

# 1회 스케줄러 시작 (세션 상태 보존)
@st.cache_resource
def init_system():
    scheduler = start_scheduler()
    api = KISApiClient()
    api.get_access_token()
    return scheduler, api

scheduler, api = init_system()
screener = StockScreener(api)

# 실시간 매도 신호 감지 fragment (페이지 전체 refresh 없이 독립적으로 60초마다 실행)
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

# 사이드바 구성
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

    # 1. 원클릭 즉시 실행 퀵 커맨드 (최상단 배치)
    st.markdown("<div class='nav-header'>⚡ QUICK COMMANDS • 즉시 실행</div>", unsafe_allow_html=True)
    if st.button("🔄 실시간 잔고 동기화 (Sync)", use_container_width=True, key="btn_quick_sync"):
        st.rerun()

    if st.button("🎯 15:15 종가 알파 스크리닝", use_container_width=True, key="btn_quick_screen"):
        with st.spinner("거래량 1.04배 보정 및 캡 점수 기반 종가 매수 스크리닝 중..."):
            screener.run_closing_price_screening()
            st.success("15:15 종가 스크리닝 완료!")
            time.sleep(1)
            st.rerun()

    if st.button("🚨 09:00 시초 손절 긴급 스캔", use_container_width=True, key="btn_quick_stoploss"):
        with st.spinner("시초가 갭하락 및 보유 종목 긴급 손절 감시 중..."):
            sells = screener.check_market_open_stop_loss()
            st.success(f"시초가 감시 완료: 긴급 손절 {len(sells)}건")
            time.sleep(1)
            st.rerun()

    st.divider()

    # 2. 실시간 매매 관제 (Core Trading)
    st.markdown("<div class='nav-header'>🚀 CORE TRADING • 실시간 관제</div>", unsafe_allow_html=True)
    live_menu = [
        ("overview", "📊 Overview • 종합 자산 관제"),
        ("screener", "🎯 15:15 종가 매수 • 스크리닝 & 발주"),
        ("portfolio", "💼 Risk Matrix • 보유 자산 & 리스크"),
        ("execution", "⚡ Order Book • 실시간 주문/체결")
    ]
    for key, label in live_menu:
        is_active = (st.session_state["nav_page"] == key)
        if st.button(
            label,
            key=f"nav_btn_{key}",
            type="primary" if is_active else "secondary",
            use_container_width=True
        ):
            st.session_state["nav_page"] = key
            st.rerun()

    # 3. 퀀트 연구 및 분석 (Quant Lab)
    st.markdown("<div class='nav-header' style='margin-top: 14px;'>📈 QUANT LAB • 성과 분석 & 검증</div>", unsafe_allow_html=True)
    lab_menu = [
        ("history", "📜 Performance • 실현 손익 분석"),
        ("backtest", "🧪 Backtester • 전략 시뮬레이터")
    ]
    for key, label in lab_menu:
        is_active = (st.session_state["nav_page"] == key)
        if st.button(
            label,
            key=f"nav_btn_{key}",
            type="primary" if is_active else "secondary",
            use_container_width=True
        ):
            st.session_state["nav_page"] = key
            st.rerun()

    # 4. 시스템 환경 설정 (Configuration)
    st.markdown("<div class='nav-header' style='margin-top: 14px;'>⚙️ SYSTEM • 환경 설정</div>", unsafe_allow_html=True)
    is_active = (st.session_state["nav_page"] == "settings")
    if st.button(
        "⚙️ Engine Config • 시스템 설정",
        key="nav_btn_settings",
        type="primary" if is_active else "secondary",
        use_container_width=True
    ):
        st.session_state["nav_page"] = "settings"
        st.rerun()

    st.caption("KIS Auto Trading Engine v2.5 • 15:15 Closing-Buy")

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

def render_interactive_stock_chart(api_client, screener_engine, code: str, name: str, avg_buy_price: Optional[float] = None, profit_rate: Optional[float] = None):
    """보유 종목 및 추천 종목의 실시간 캔들 차트, 이동평균선, 볼린저밴드, 거래량, RSI 시각화 렌더러"""
    with st.spinner(f"📈 {name}({code}) 실시간 일봉 차트 및 보조지표 로드 중..."):
        candles = api_client.get_daily_chart(code, count=65)
        realtime = api_client.get_stock_price(code)
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

        df_tech = screener_engine.calculate_technical_indicators(candles, is_intraday=True)
        if df_tech is not None and not df_tech.empty:
            fig = make_subplots(
                rows=3, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.04,
                row_heights=[0.55, 0.20, 0.25],
                subplot_titles=(
                    f"{name} ({code}) 일봉 캔들 & 이동평균선 & 볼린저밴드",
                    "거래량 & 20일 거래량 이평",
                    "RSI (14)"
                )
            )

            # 1. 캔들스틱
            fig.add_trace(
                go.Candlestick(
                    x=df_tech["date"],
                    open=df_tech["open"],
                    high=df_tech["high"],
                    low=df_tech["low"],
                    close=df_tech["close"],
                    name="캔들",
                    increasing_line_color="#ef4444",
                    decreasing_line_color="#3b82f6"
                ),
                row=1, col=1
            )
            fig.add_trace(go.Scatter(x=df_tech["date"], y=df_tech["ma5"], line=dict(color="#f59e0b", width=1.5), name="5일선"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_tech["date"], y=df_tech["ma20"], line=dict(color="#10b981", width=2), name="20일선"), row=1, col=1)
            if "ma60" in df_tech:
                fig.add_trace(go.Scatter(x=df_tech["date"], y=df_tech["ma60"], line=dict(color="#8b5cf6", width=1.5), name="60일선"), row=1, col=1)

            fig.add_trace(go.Scatter(x=df_tech["date"], y=df_tech["bb_upper"], line=dict(color="rgba(148, 163, 184, 0.5)", dash="dot", width=1), name="BB상단", showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_tech["date"], y=df_tech["bb_lower"], line=dict(color="rgba(148, 163, 184, 0.5)", dash="dot", width=1), fill="tonexty", fillcolor="rgba(148, 163, 184, 0.05)", name="BB하단", showlegend=False), row=1, col=1)

            # 매입평균가 기준선
            if avg_buy_price and avg_buy_price > 0:
                ann_text = f"매입평단가: {avg_buy_price:,.0f}원 ({profit_rate:+.2f}%)" if profit_rate is not None else f"매입평단가: {avg_buy_price:,.0f}원"
                fig.add_hline(
                    y=avg_buy_price,
                    line_dash="dash",
                    line_color="#fbbf24",
                    line_width=2,
                    annotation_text=ann_text,
                    annotation_position="top right",
                    annotation_font_color="#fbbf24",
                    row=1, col=1
                )

            # 2. 거래량 차트
            colors = ["#ef4444" if row["close"] >= row["open"] else "#3b82f6" for _, row in df_tech.iterrows()]
            fig.add_trace(go.Bar(x=df_tech["date"], y=df_tech["volume"], marker_color=colors, name="거래량"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_tech["date"], y=df_tech["vol_ma20"], line=dict(color="#fbbf24", width=1.5), name="전일 20일 거래량이평"), row=2, col=1)

            # 3. RSI 차트
            fig.add_trace(go.Scatter(x=df_tech["date"], y=df_tech["rsi14"], line=dict(color="#06b6d4", width=2), name="RSI(14)"), row=3, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="#ef4444", row=3, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="#3b82f6", row=3, col=1)

            fig.update_layout(
                height=560,
                template="plotly_dark",
                xaxis_rangeslider_visible=False,
                margin=dict(l=20, r=20, t=40, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig, use_container_width=True)

            latest = df_tech.iloc[-1]
            m1, m2, m3, m4, m5 = st.columns(5)
            with m1:
                st.metric("현재가", f"{latest['close']:,.0f}원", delta=f"{latest.get('change_rate', 0):+.2f}%")
            with m2:
                rsi_val = latest['rsi14']
                prev_rsi = df_tech.iloc[-2]['rsi14'] if len(df_tech) >= 2 else rsi_val
                st.metric("RSI(14)", f"{rsi_val:.1f}", delta=f"{rsi_val - prev_rsi:+.1f}")
            with m3:
                vol_ratio = (latest['volume'] / (latest['vol_ma20'] + 1e-9)) * 100 if latest.get('vol_ma20') else 0
                st.metric("20일 평균대비 거래량", f"{vol_ratio:.0f}%")
            with m4:
                st.metric("20일선 (중기)", f"{latest['ma20']:,.0f}원")
            with m5:
                st.metric("볼린저 하단 (지지선)", f"{latest['bb_lower']:,.0f}원")
        else:
            st.warning("차트 데이터를 불러올 수 없습니다.")

# ==============================================================================
# 1. 종합 대시보드 페이지
# ==============================================================================
if st.session_state["nav_page"] == "overview":
    st.title("🏠 종합 자산 및 매매 모니터링")
    st.caption(f"서버 시각: {now_str()} (KST)")

    st.markdown("""
        <div class="timeline-container">
            <div style="font-size: 0.78rem; font-weight: 700; color: #38bdf8; margin-bottom: 8px;">⏱️ 일일 5단계 운영 타임라인</div>
            <div style="display: flex; gap: 10px; font-size: 0.75rem; color: #cbd5e1; flex-wrap: wrap;">
                <span><b>09:00</b> 시초가 손절 감시</span> ➔
                <span><b>09:05~15:15</b> 실시간 익절/손절 감시</span> ➔
                <span style="color: #38bdf8; font-weight: 700;"><b>15:15</b> 거래량 1.04배 종가 평가</span> ➔
                <span><b>15:18</b> 상위종목 시장가 매수</span> ➔
                <span><b>15:30</b> 장마감 정산</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(label="총 평가 자산", value=f"{summary.get('tot_asset', 0):,.0f} 원")
    with col2:
        st.metric(label="주문 가능 예수금", value=f"{summary.get('cash_balance', 0):,.0f} 원")
    with col3:
        st.metric(label="보유 주식 평가금", value=f"{summary.get('stock_eval_amt', 0):,.0f} 원")
    with col4:
        pfls = summary.get('total_profit_loss', 0)
        st.metric(label="총 평가 손익", value=f"{pfls:+,.0f} 원", delta=f"{pfls:+,.0f} 원")

    st.divider()

    c_left, c_right = st.columns([1, 1])
    with c_left:
        st.subheader("🌅 15:15 종가 매수 추천 Top 종목")
        buy_list = proposals.get("buy_proposals", [])
        if not buy_list:
            st.info("현재 매수 조건을 통과한 추천 종목이 없습니다. (총점 45점 이상 & 수급 필수 게이트 충족 필요)")
        else:
            for b in buy_list[:3]:
                buy_tag = "🔄 추가매수" if b.get("code") in holding_codes else "🆕 신규매수"
                t_sc = b.get("trend_score", 0)
                s_sc = b.get("supply_score", 0)
                m_sc = b.get("momentum_score", 0)
                st.markdown(f"**{buy_tag} [{b['name']} ({b['code']})]** 현재가: `{b['current_price']:,.0f}원` | **총점: `{b['score']}점`** (추세 {t_sc}/수급 {s_sc}/모멘텀 {m_sc})")
                st.caption(f"⚡ 보정 거래량: {b.get('adjusted_volume', 0):,.0f}주 (20일평균 대비 {b.get('vol_ratio', 0)}%)")
                st.caption(" • ".join(b.get("reasons", [])))

    with c_right:
        st.subheader("🚨 매도 & 리스크 관리 알림")
        sell_list = proposals.get("sell_proposals", [])
        if not sell_list:
            st.success("현재 매도가 시급한 보유 종목이 없습니다.")
        else:
            for s in sell_list:
                urgent_badge = "🚨 [긴급 손절]" if s.get("is_urgent") else "⚠️ [매도 신호]"
                sell_type = s.get("sell_type", "매도")
                st.warning(f"**{urgent_badge} [{s['name']} ({s['code']})]** {sell_type} | 수익률: **{s['profit_rate']:+.2f}%** | 매도수량: {s['sell_qty']}주\n- {', '.join(s.get('reasons', []))}")

    st.divider()
    st.subheader("📦 현재 보유 주식 요약 & 실시간 차트")
    if not holdings:
        st.info("현재 계좌에 보유 중인 주식이 없습니다.")
    else:
        h_df = pd.DataFrame(holdings)[["name", "code", "quantity", "avg_buy_price", "current_price", "profit_rate", "profit_loss", "eval_amount"]].copy()
        h_df.columns = ["종목명", "코드", "보유수량", "매입평균가", "현재가", "수익률(%)", "평가손익(원)", "평가금액(원)"]
        h_df["매입평균가"] = h_df["매입평균가"].apply(lambda x: f"{x:,.0f}")
        h_df["현재가"] = h_df["현재가"].apply(lambda x: f"{x:,.0f}")
        h_df["수익률(%)"] = h_df["수익률(%)"].apply(lambda x: f"{x:+.2f}%")
        h_df["평가손익(원)"] = h_df["평가손익(원)"].apply(lambda x: f"{x:+,.0f}")
        h_df["평가금액(원)"] = h_df["평가금액(원)"].apply(lambda x: f"{x:,.0f}")
        st.dataframe(h_df, use_container_width=True)

        # 보유 종목 차트 선택 뷰어
        st.markdown("#### 📈 보유 종목 인터랙티브 차트 분석")
        holding_options = [f"{h['name']} ({h['code']}) | 평단가: {h['avg_buy_price']:,.0f}원 | 수익률: {h['profit_rate']:+.2f}%" for h in holdings]
        selected_idx = st.selectbox(
            "차트를 확인할 보유 종목을 선택하세요",
            range(len(holdings)),
            format_func=lambda i: holding_options[i],
            key="overview_holding_chart_select"
        )

        selected_h = holdings[selected_idx]
        with st.expander(f"📊 {selected_h['name']} ({selected_h['code']}) 실시간 차트 & 지표 상세", expanded=True):
            render_interactive_stock_chart(
                api_client=api,
                screener_engine=screener,
                code=selected_h["code"],
                name=selected_h["name"],
                avg_buy_price=float(selected_h.get("avg_buy_price", 0)),
                profit_rate=float(selected_h.get("profit_rate", 0))
            )

# ==============================================================================
# 2. 15:15 종가 매수 스크리닝 & 발주 페이지
# ==============================================================================
elif st.session_state["nav_page"] == "screener":
    col_t1, col_t2 = st.columns([3.2, 1.3])
    with col_t1:
        st.title("🎯 15:15 종가 매수 • 스크리닝 & 발주")
        st.caption(f"스크리닝 기준 시각: **{proposals.get('generated_at', '-')}** | 거래량 1.04배 보정치 & 캡 점수 적용 (45점 이상)")
    with col_t2:
        st.write("")
        if st.button("🔄 즉시 종가 스크리닝 실행", key="btn_run_screener_page", type="primary", use_container_width=True):
            with st.spinner("유니버스 종목 분석 및 종가 매수 스크리닝 중..."):
                screener.run_closing_price_screening()
                st.success("✅ 종가 스크리닝 완료!")
                time.sleep(1)
                st.rerun()

    buy_list = proposals.get("buy_proposals", [])
    if not buy_list:
        st.info("현재 추천된 매수 종목이 없습니다. 상단의 **[🔄 즉시 종가 스크리닝 실행]** 버튼을 누르거나 15:15 자동 스케줄을 기다려주세요. (총점 45점 이상 & 수급 필수 게이트 충족 종목 표시)")
    else:
        for idx, item in enumerate(buy_list):
            with st.container():
                c1, c2, c3, c4 = st.columns([2.8, 2.3, 2.3, 2.0])
                with c1:
                    buy_tag = "🔄 추가매수" if item.get("code") in holding_codes else "🆕 신규매수"
                    st.markdown(f"### {buy_tag} {item['name']} <small style='color:#64748b'>({item['code']})</small>", unsafe_allow_html=True)
                    st.write(f"**현재가:** `{item['current_price']:,.0f}원` ({item['change_rate']:+.2f}%)")
                    
                    t_sc = item.get("trend_score", 0)
                    s_sc = item.get("supply_score", 0)
                    m_sc = item.get("momentum_score", 0)
                    st.markdown(f"""
                        <span class="score-badge">총점 {item['score']}점</span>
                        <span class="score-badge">추세 {t_sc}/30</span>
                        <span class="score-badge">수급 {s_sc}/25</span>
                        <span class="score-badge">모멘텀 {m_sc}/25</span>
                    """, unsafe_allow_html=True)
                    st.caption(f"⚡ 보정 거래량: {item.get('adjusted_volume', 0):,.0f}주 (전일20일평균 대비 {item.get('vol_ratio', 0)}%)")
                    reasons_text = " • ".join(item.get("reasons", []))
                    st.caption(reasons_text)
                
                with c2:
                    ord_type = st.radio(
                        "주문 유형",
                        ["시장가", "지정가", "LOC (종가조건부)"],
                        horizontal=False,
                        key=f"buy_type_{item['code']}_{idx}",
                        label_visibility="collapsed"
                    )
                    
                    if ord_type == "지정가":
                        target_price = st.number_input(
                            "지정가(원)",
                            min_value=100,
                            max_value=10000000,
                            value=int(item['current_price']),
                            step=100,
                            key=f"buy_price_{item['code']}_{idx}"
                        )
                        st.caption("🎯 지정한 가격에 즉시 호가 제출")
                    elif ord_type == "LOC (종가조건부)":
                        target_price = st.number_input(
                            "LOC 상한가(원)",
                            min_value=100,
                            max_value=10000000,
                            value=int(item['current_price']),
                            step=100,
                            key=f"buy_price_{item['code']}_{idx}"
                        )
                        st.caption("🛡️ 종가가 상한가 이하일 때만 종가로 자동 체결")
                    else:
                        target_price = int(item['current_price'])
                        st.caption("⚡ 종가 시장가 즉시 체결")

                with c3:
                    rec_qty = item.get("recommended_qty", 1)
                    order_qty = st.number_input(
                        "수량(주)",
                        min_value=1,
                        max_value=10000,
                        value=rec_qty,
                        key=f"buy_qty_{item['code']}_{idx}"
                    )
                    est_amt = order_qty * target_price
                    st.write(f"예상 주문액: **{est_amt:,.0f}원**")
                
                with c4:
                    st.write("")
                    st.write("")
                    btn_label = f"⚡ 매수 ({ord_type})"
                    if st.button(btn_label, key=f"btn_buy_{item['code']}_{idx}", type="primary", use_container_width=True):
                        if ord_type == "지정가":
                            ord_dv = "00"
                            order_prc = int(target_price)
                        elif ord_type == "LOC (종가조건부)":
                            ord_dv = "51"  # 장마감 단일가 LOC (조건부지정가: 02, LOC: 51)
                            order_prc = int(target_price)
                        else:
                            ord_dv = "01"
                            order_prc = 0
                        
                        with st.spinner(f"{item['name']} {order_qty}주 {ord_type} 주문 전송 중..."):
                            res = api.order_cash(
                                stock_code=item["code"],
                                qty=order_qty,
                                price=order_prc,
                                buy_sell="BUY",
                                ord_dv=ord_dv
                            )
                            if res.get("rt_cd") == "0":
                                st.success(f"✅ 주문 완료 (No. {res.get('order_no')})")
                                notifier.send_buy_success(
                                    name=item["name"],
                                    code=item["code"],
                                    qty=order_qty,
                                    price=target_price,
                                    order_no=res.get("order_no", ""),
                                    order_type=ord_type
                                )
                                time.sleep(1.5)
                                st.rerun()
                            else:
                                st.error(f"❌ 주문 실패: {res.get('msg1')}")

                with st.expander(f"📈 {item['name']} 차트 및 지표 상세 분석"):
                    with st.spinner(f"{item['name']} 차트 데이터 로드 중..."):
                        candles = api.get_daily_chart(item["code"], count=65)
                        df_tech = screener.calculate_technical_indicators(candles, is_intraday=True)
                        
                        if df_tech is not None and not df_tech.empty:
                            fig = make_subplots(
                                rows=3, cols=1,
                                shared_xaxes=True,
                                vertical_spacing=0.04,
                                row_heights=[0.55, 0.20, 0.25],
                                subplot_titles=(f"{item['name']} 일봉 캔들 & 이동평균선 & 볼린저밴드", "거래량 & 20일 거래량 이평", "RSI (14)")
                            )

                            fig.add_trace(
                                go.Candlestick(
                                    x=df_tech["date"],
                                    open=df_tech["open"],
                                    high=df_tech["high"],
                                    low=df_tech["low"],
                                    close=df_tech["close"],
                                    name="캔들",
                                    increasing_line_color="#ef4444",
                                    decreasing_line_color="#3b82f6"
                                ),
                                row=1, col=1
                            )
                            fig.add_trace(go.Scatter(x=df_tech["date"], y=df_tech["ma5"], line=dict(color="#f59e0b", width=1.5), name="5일선"), row=1, col=1)
                            fig.add_trace(go.Scatter(x=df_tech["date"], y=df_tech["ma20"], line=dict(color="#10b981", width=2), name="20일선"), row=1, col=1)
                            if "ma60" in df_tech:
                                fig.add_trace(go.Scatter(x=df_tech["date"], y=df_tech["ma60"], line=dict(color="#8b5cf6", width=1.5), name="60일선"), row=1, col=1)

                            fig.add_trace(go.Scatter(x=df_tech["date"], y=df_tech["bb_upper"], line=dict(color="rgba(148, 163, 184, 0.5)", dash="dot", width=1), name="BB상단", showlegend=False), row=1, col=1)
                            fig.add_trace(go.Scatter(x=df_tech["date"], y=df_tech["bb_lower"], line=dict(color="rgba(148, 163, 184, 0.5)", dash="dot", width=1), fill="tonexty", fillcolor="rgba(148, 163, 184, 0.05)", name="BB하단", showlegend=False), row=1, col=1)

                            colors = ["#ef4444" if row["close"] >= row["open"] else "#3b82f6" for _, row in df_tech.iterrows()]
                            fig.add_trace(go.Bar(x=df_tech["date"], y=df_tech["volume"], marker_color=colors, name="거래량"), row=2, col=1)
                            fig.add_trace(go.Scatter(x=df_tech["date"], y=df_tech["vol_ma20"], line=dict(color="#fbbf24", width=1.5), name="전일 20일 거래량이평"), row=2, col=1)

                            fig.add_trace(go.Scatter(x=df_tech["date"], y=df_tech["rsi14"], line=dict(color="#06b6d4", width=2), name="RSI(14)"), row=3, col=1)
                            fig.add_hline(y=70, line_dash="dash", line_color="#ef4444", row=3, col=1)
                            fig.add_hline(y=30, line_dash="dash", line_color="#3b82f6", row=3, col=1)

                            fig.update_layout(
                                height=550,
                                template="plotly_dark",
                                xaxis_rangeslider_visible=False,
                                margin=dict(l=20, r=20, t=40, b=20),
                                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                            )
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.warning("차트 데이터를 불러올 수 없습니다.")
                st.divider()

# ==============================================================================
# 3. 보유 종목 & 매도 리스크 관리 페이지
# ==============================================================================
elif st.session_state["nav_page"] == "portfolio":
    st.title("💼 Portfolio & Risk • 실시간 매도 및 리스크 관리")
    st.caption("손절 최우선 원칙 (-3% 즉시 전량 매도) | 목표 익절 (+5% 50% 분할 익절) | 2영업일 유예 원칙 적용")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        realtime_on = st.toggle(
            "🔄 실시간 감지 (5분 간격)",
            value=st.session_state.get("realtime_detect_on", False),
            key="realtime_detect_toggle"
        )
    with col_btn2:
        if st.button("⚡ 즉시 체크", key="btn_immediate_check", use_container_width=True):
            with st.spinner("보유 주식 매도 신호 즉시 분석 중..."):
                updated = screener.check_sell_signals_now()
                st.session_state["last_check_time"] = now_str()
                st.success(f"✅ 매도 신호 재분석 완료: {len(updated.get('sell_proposals', []))}건 감지")
                time.sleep(1)
                st.rerun()

    if realtime_on:
        st.session_state["realtime_detect_on"] = True
        st.info("🔄 실시간 감지가 활성화되었습니다. 5분마다 보유 주식 매도 신호를 자동 체크합니다.")
        realtime_detection_fragment()
    else:
        st.session_state["realtime_detect_on"] = False

    last_check_time = st.session_state.get("last_check_time")
    if last_check_time:
        st.caption(f"⏰ 마지막 매도 신호 체크: {last_check_time}")

    st.divider()

    sell_list = proposals.get("sell_proposals", [])
    if sell_list:
        st.warning(f"⚠️ **{len(sell_list)}건**의 매도 시그널이 감지되었습니다.")
        for s_idx, s_item in enumerate(sell_list):
            is_urgent = s_item.get("is_urgent", False)
            sell_type = s_item.get("sell_type", "매도")
            header_icon = "🚨 [긴급 손절]" if is_urgent else "⚠️ [매도 신호]"
            
            with st.expander(f"{header_icon} {s_item['name']} ({s_item['code']}) • {sell_type} • 수익률 {s_item['profit_rate']:+.2f}%", expanded=True):
                sc1, sc2, sc3, sc4 = st.columns([2.5, 2.0, 2.0, 2.0])
                with sc1:
                    st.write(f"**보유량:** `{s_item['holding_qty']:,}주` | **권고 매도량:** `{s_item.get('sell_qty', s_item['holding_qty']):,}주`")
                    st.write(f"**현재가:** `{s_item['current_price']:,.0f}원` | **평가손익:** `{s_item['profit_loss']:+,.0f}원`")
                    for r in s_item.get("reasons", []):
                        st.caption(f"• {r}")
                
                with sc2:
                    sell_ord_type = st.radio(
                        "매도 유형",
                        ["시장가", "지정가"],
                        horizontal=True,
                        key=f"sell_type_{s_item['code']}_{s_idx}",
                        label_visibility="collapsed"
                    )
                    if sell_ord_type == "지정가":
                        sell_target_price = st.number_input(
                            "지정 매도가",
                            min_value=100,
                            max_value=10000000,
                            value=int(s_item['current_price']),
                            step=100,
                            key=f"sell_prc_{s_item['code']}_{s_idx}"
                        )
                    else:
                        sell_target_price = int(s_item['current_price'])
                        st.caption("⚡ 시장가 즉시 매도")

                with sc3:
                    default_qty = s_item.get("sell_qty", s_item["holding_qty"])
                    sell_qty = st.number_input(
                        "매도 수량(주)",
                        min_value=1,
                        max_value=s_item["holding_qty"],
                        value=default_qty,
                        key=f"sell_qty_{s_item['code']}_{s_idx}"
                    )
                    st.write(f"예상 매도액: **{sell_qty * sell_target_price:,.0f}원**")

                with sc4:
                    st.write("")
                    st.write("")
                    btn_text = f"🚨 긴급 매도" if is_urgent else f"⚡ 매도 ({sell_ord_type})"
                    if st.button(btn_text, key=f"btn_sell_{s_item['code']}_{s_idx}", type="primary", use_container_width=True):
                        is_sell_limit = (sell_ord_type == "지정가")
                        sell_ord_dv = "00" if is_sell_limit else "01"
                        sell_prc_val = int(sell_target_price) if is_sell_limit else 0

                        with st.spinner(f"{s_item['name']} {sell_qty}주 {sell_ord_type} 매도 주문 전송 중..."):
                            res = api.order_cash(
                                stock_code=s_item["code"],
                                qty=sell_qty,
                                price=sell_prc_val,
                                buy_sell="SELL",
                                ord_dv=sell_ord_dv
                            )
                            if res.get("rt_cd") == "0":
                                st.success(f"✅ 매도 완료 (No. {res.get('order_no')})")
                                notifier.send_sell_success(
                                    name=s_item["name"],
                                    code=s_item["code"],
                                    qty=sell_qty,
                                    price=sell_target_price,
                                    order_no=res.get("order_no", ""),
                                    order_type=sell_ord_type
                                )
                                time.sleep(1.5)
                                st.rerun()
                            else:
                                st.error(f"❌ 매도 실패: {res.get('msg1')}")
        st.divider()

    if not holdings:
        st.info("현재 계좌에 보유 중인 주식이 없습니다.")
    else:
        st.write("### 📦 전체 보유 주식 목록")
        h_df = pd.DataFrame(holdings)[["name", "code", "quantity", "avg_buy_price", "current_price", "profit_rate", "profit_loss", "eval_amount"]].copy()
        h_df.columns = ["종목명", "코드", "보유수량", "매입평균가", "현재가", "수익률(%)", "평가손익(원)", "평가금액(원)"]
        h_df["매입평균가"] = h_df["매입평균가"].apply(lambda x: f"{x:,.0f}")
        h_df["현재가"] = h_df["현재가"].apply(lambda x: f"{x:,.0f}")
        h_df["수익률(%)"] = h_df["수익률(%)"].apply(lambda x: f"{x:+.2f}%")
        h_df["평가손익(원)"] = h_df["평가손익(원)"].apply(lambda x: f"{x:+,.0f}")
        h_df["평가금액(원)"] = h_df["평가금액(원)"].apply(lambda x: f"{x:,.0f}")
        st.dataframe(h_df, use_container_width=True)

        st.markdown("#### 📈 보유 종목 인터랙티브 차트 및 리스크 진단")
        holding_options_port = [f"{h['name']} ({h['code']}) | 평단가: {h['avg_buy_price']:,.0f}원 | 수익률: {h['profit_rate']:+.2f}%" for h in holdings]
        selected_port_idx = st.selectbox(
            "차트를 확인할 보유 종목을 선택하세요",
            range(len(holdings)),
            format_func=lambda i: holding_options_port[i],
            key="portfolio_holding_chart_select"
        )

        selected_port_h = holdings[selected_port_idx]
        with st.expander(f"📊 {selected_port_h['name']} ({selected_port_h['code']}) 실시간 차트 & 지표 상세", expanded=True):
            render_interactive_stock_chart(
                api_client=api,
                screener_engine=screener,
                code=selected_port_h["code"],
                name=selected_port_h["name"],
                avg_buy_price=float(selected_port_h.get("avg_buy_price", 0)),
                profit_rate=float(selected_port_h.get("profit_rate", 0))
            )

# ==============================================================================
# 4. 백테스팅 페이지 (FinanceDataReader)
# ==============================================================================
elif st.session_state["nav_page"] == "backtest":
    st.title("🧪 Backtest • 알고리즘 백테스팅")
    st.caption("FinanceDataReader를 활용하여 구현된 종가 매수(15:15) 및 리스크 관리 전략을 과거 데이터로 검증합니다.")

    # 백테스팅 파라미터 폼
    with st.expander("⚙️ 백테스팅 설정 파라미터", expanded=True):
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            bt_start = st.date_input(
                "시작일자",
                value=today() - datetime.timedelta(days=180),
                max_value=today() - datetime.timedelta(days=10)
            )
            bt_capital = st.number_input(
                "초기 투자 원금 (원)",
                min_value=1000000,
                max_value=1000000000,
                value=10000000,
                step=1000000
            )
            bt_max_hold = st.number_input(
                "최대 보유 종목 수",
                min_value=1,
                max_value=20,
                value=5,
                step=1
            )
            bt_target_profit = st.number_input(
                "목표 익절 수익률 (예: 0.05 = +5%)",
                min_value=0.01,
                max_value=0.50,
                value=0.05,
                step=0.01
            )

        with col_b2:
            bt_end = st.date_input(
                "종료일자",
                value=today(),
                max_value=today()
            )
            bt_budget = st.number_input(
                "1종목당 최대 매수 예산 (원)",
                min_value=100000,
                max_value=100000000,
                value=1000000,
                step=100000
            )
            bt_stop_loss = st.number_input(
                "손절 기준 수익률 (예: -0.03 = -3%)",
                min_value=-0.50,
                max_value=-0.01,
                value=-0.03,
                step=0.01
            )
            universe_mode = st.selectbox(
                "백테스트 유니버스 선택",
                ["관심종목 100개 전체 (Watchlist)", "대형 우량주 10개 (Top 10)", "직접 입력"]
            )

        # 유니버스 구성
        if universe_mode == "관심종목 100개 전체 (Watchlist)":
            bt_universe = config.CURRENT_SETTINGS.get("watchlist", [])
        elif universe_mode == "대형 우량주 10개 (Top 10)":
            bt_universe = [
                {"code": "005930", "name": "삼성전자"},
                {"code": "000660", "name": "SK하이닉스"},
                {"code": "373220", "name": "LG에너지솔루션"},
                {"code": "207940", "name": "삼성바이오로직스"},
                {"code": "005380", "name": "현대차"},
                {"code": "000270", "name": "기아"},
                {"code": "068270", "name": "셀트리온"},
                {"code": "035420", "name": "NAVER"},
                {"code": "105560", "name": "KB금융"},
                {"code": "055550", "name": "신한지주"}
            ]
        else:
            custom_codes_raw = st.text_input("종목코드 입력 (쉼표로 구분)", value="005930,000660,035420,005380")
            bt_universe = [{"code": c.strip(), "name": c.strip()} for c in custom_codes_raw.split(",") if c.strip()]

        st.caption(f"선택된 유니버스 종목 수: **{len(bt_universe)}개**")

        btn_run_bt = st.button("🚀 백테스팅 실행", type="primary", use_container_width=True)

    # 백테스팅 실행 처리
    if btn_run_bt:
        if bt_start >= bt_end:
            st.error("⚠️ 시작일이 종료일보다 앞서야 합니다.")
        else:
            prog_bar = st.progress(0, text="데이터 다운로드 및 백테스팅 준비 중...")
            
            def update_progress(val):
                prog_bar.progress(int(val * 100), text=f"백테스팅 시뮬레이션 진행 중... ({int(val * 100)}%)")

            tester = Backtester(
                start_date=bt_start.strftime("%Y-%m-%d"),
                end_date=bt_end.strftime("%Y-%m-%d"),
                universe=bt_universe,
                initial_capital=float(bt_capital),
                budget_per_stock=float(bt_budget),
                max_holdings=int(bt_max_hold),
                target_profit_rate=float(bt_target_profit),
                stop_loss_rate=float(bt_stop_loss)
            )

            with st.spinner("과거 데이터 기반 전략 시뮬레이션 계산 중..."):
                bt_result = tester.run(progress_callback=update_progress)
                prog_bar.progress(100, text="백테스팅 완료!")
                st.session_state["bt_result"] = bt_result
                st.session_state["bt_params"] = {
                    "start": bt_start.strftime("%Y-%m-%d"),
                    "end": bt_end.strftime("%Y-%m-%d"),
                    "initial": bt_capital,
                    "universe_count": len(bt_universe)
                }
                time.sleep(0.5)
                st.rerun()

    # 백테스팅 결과 표시
    if "bt_result" in st.session_state:
        res = st.session_state["bt_result"]
        if "error" in res:
            st.error(f"❌ {res['error']}")
        else:
            summary_bt = res["summary"]
            daily_eq = res["daily_equity"]
            trades_df = res["trade_history"]
            bench_df = res.get("benchmark_df")
            params = st.session_state.get("bt_params", {})

            st.divider()
            st.subheader(f"📊 백테스팅 성과 결과 ({params.get('start')} ~ {params.get('end')})")

            # 핵심 성과 지표 카드
            m1, m2, m3, m4, m5, m6 = st.columns(6)
            with m1:
                ret = summary_bt["total_return_pct"]
                st.metric("누적 수익률", f"{ret:+.2f}%", delta=f"{ret:+.2f}%")
            with m2:
                cagr = summary_bt["cagr_pct"]
                st.metric("연평균 수익률 (CAGR)", f"{cagr:+.2f}%")
            with m3:
                mdd = summary_bt["mdd_pct"]
                st.metric("최대 낙폭 (MDD)", f"{mdd:.2f}%", delta=f"{mdd:.2f}%", delta_color="inverse")
            with m4:
                win_r = summary_bt["win_rate"]
                st.metric("매매 승률 (Win Rate)", f"{win_r:.1f}%")
            with m5:
                pf = summary_bt["profit_factor"]
                pf_str = f"{pf:.2f}" if pf < 100 else "999+"
                st.metric("손익비 (Profit Factor)", pf_str)
            with m6:
                st.metric("총 실현/평가손익", f"{summary_bt['total_profit_krw']:+,.0f}원")

            # 인터랙티브 차트 (자산 곡선 vs 벤치마크 & 낙폭)
            st.write("### 📈 포트폴리오 수익률 곡선 (Equity Curve vs KOSPI)")
            
            fig_bt = make_subplots(
                rows=2, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.06,
                row_heights=[0.7, 0.3],
                subplot_titles=("포트폴리오 누적 수익률 vs KOSPI 벤치마크", "Drawdown (낙폭)")
            )

            # 포트폴리오 수익률
            fig_bt.add_trace(
                go.Scatter(
                    x=pd.to_datetime(daily_eq["date"]),
                    y=daily_eq["return_pct"],
                    name="전략 포트폴리오",
                    line=dict(color="#38bdf8", width=2.5)
                ),
                row=1, col=1
            )

            # KOSPI 벤치마크
            if bench_df is not None and not bench_df.empty:
                # 거래일 매칭
                merged_bench = pd.merge(daily_eq, bench_df, on="date", how="left")
                fig_bt.add_trace(
                    go.Scatter(
                        x=pd.to_datetime(merged_bench["date"]),
                        y=merged_bench["benchmark_return"],
                        name="KOSPI 지수",
                        line=dict(color="#94a3b8", width=1.5, dash="dot")
                    ),
                    row=1, col=1
                )

            # 낙폭 차트 (Drawdown)
            fig_bt.add_trace(
                go.Scatter(
                    x=pd.to_datetime(daily_eq["date"]),
                    y=daily_eq["drawdown"],
                    name="Drawdown",
                    fill="tozeroy",
                    fillcolor="rgba(239, 68, 68, 0.2)",
                    line=dict(color="#ef4444", width=1.5)
                ),
                row=2, col=1
            )

            fig_bt.update_layout(
                height=600,
                template="plotly_dark",
                margin=dict(l=20, r=20, t=40, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_bt, use_container_width=True)

            # 일별 자산 및 보유 종목 수 현황
            col_eq1, col_eq2 = st.columns([1, 1])
            with col_eq1:
                st.write("### 💼 자산 구성 추이 (현금 vs 주식)")
                fig_comp = go.Figure()
                fig_comp.add_trace(go.Scatter(
                    x=pd.to_datetime(daily_eq["date"]),
                    y=daily_eq["cash"],
                    name="현금 잔고",
                    stackgroup="one",
                    line=dict(color="#10b981")
                ))
                fig_comp.add_trace(go.Scatter(
                    x=pd.to_datetime(daily_eq["date"]),
                    y=daily_eq["stock_eval"],
                    name="주식 평가액",
                    stackgroup="one",
                    line=dict(color="#6366f1")
                ))
                fig_comp.update_layout(
                    template="plotly_dark",
                    height=350,
                    margin=dict(l=20, r=20, t=30, b=20),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig_comp, use_container_width=True)

            with col_eq2:
                st.write("### 🎯 승패 비율 및 거래 통계")
                win_cnt = summary_bt["win_count"]
                loss_cnt = summary_bt["loss_count"]
                if win_cnt + loss_cnt > 0:
                    fig_pie = go.Figure(go.Pie(
                        labels=["익절/수익 매도", "손절/손실 매도"],
                        values=[win_cnt, loss_cnt],
                        hole=0.4,
                        marker_colors=["#10b981", "#ef4444"]
                    ))
                    fig_pie.update_layout(
                        template="plotly_dark",
                        height=350,
                        margin=dict(l=20, r=20, t=30, b=20)
                    )
                    st.plotly_chart(fig_pie, use_container_width=True)
                else:
                    st.info("청산된 거래 내역이 없습니다.")

            # 매매 이력 상세 테이블
            st.divider()
            st.subheader(f"📋 백테스트 매매 상세 내역 (총 {len(trades_df)}건)")
            if not trades_df.empty:
                disp_trades = trades_df.copy()
                disp_trades["price"] = disp_trades["price"].apply(lambda x: f"{x:,.0f}원")
                disp_trades["amount"] = disp_trades["amount"].apply(lambda x: f"{x:,.0f}원")
                disp_trades["profit_krw"] = disp_trades["profit_krw"].apply(lambda x: f"{x:+,.0f}원" if x != 0 else "-")
                disp_trades["profit_pct"] = disp_trades["profit_pct"].apply(lambda x: f"{x:+.2f}%" if x != 0 else "-")

                st.dataframe(disp_trades, use_container_width=True)

                # CSV 다운로드 버튼
                csv_data = trades_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📥 매매 내역 CSV 다운로드",
                    data=csv_data,
                    file_name=f"backtest_trades_{params.get('start')}_{params.get('end')}.csv",
                    mime="text/csv"
                )
            else:
                st.info("백테스트 기간 내 발생한 매매 내역이 없습니다.")

# ==============================================================================
# 5. 당일 주문 및 체결 내역 페이지
# ==============================================================================
elif st.session_state["nav_page"] == "execution":
    st.title("⚡ Execution • 실시간 주문 및 체결 내역")
    if st.button("🔄 주문 내역 갱신", key="btn_refresh_orders_pg"):
        st.rerun()

    orders = api.get_order_history()
    if not orders:
        st.info("금일 전송된 주문 내역이 없습니다.")
    else:
        o_df = pd.DataFrame(orders)
        st.dataframe(o_df, use_container_width=True)

# ==============================================================================
# 6. 매매 이력 & 수익 분석 페이지
# ==============================================================================
elif st.session_state["nav_page"] == "history":
    st.title("📜 History & Profit • 매매 이력 및 수익 분석")
    st.caption(f"서버 시각: {now_str()} (KST)")

    col_date1, col_date2, col_date3 = st.columns([1.5, 1.5, 1])
    with col_date1:
        start_date = st.date_input(
            "조회 시작일",
            value=today() - datetime.timedelta(days=30),
            max_value=today()
        )
    with col_date2:
        end_date = st.date_input(
            "조회 종료일",
            value=today(),
            max_value=today()
        )
    with col_date3:
        st.write("")
        st.write("")
        if st.button("🔍 조회", key="btn_history_search", type="primary", use_container_width=True):
            st.rerun()

    if start_date > end_date:
        st.error("⚠️ 시작일이 종료일보다 늦을 수 없습니다.")
    else:
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")

        with st.spinner("매매 이력 조회 중..."):
            result = api.get_trade_history_with_profit(start_str, end_str)
            balance_data = api.get_account_balance()
            holdings_data = balance_data.get("holdings", [])
            unrealized_profit = 0.0
            unrealized_by_stock = {}
            for h in holdings_data:
                code = h["code"]
                profit = h.get("profit_loss", 0.0)
                unrealized_profit += profit
                unrealized_by_stock[code] = {
                    "name": h.get("name", ""),
                    "code": code,
                    "quantity": h.get("quantity", 0),
                    "avg_buy_price": h.get("avg_buy_price", 0),
                    "current_price": h.get("current_price", 0),
                    "profit_loss": profit,
                    "profit_rate": h.get("profit_rate", 0)
                }

        orders = result["orders"]
        realized_profit = result["realized_profit"]
        buy_total = result["buy_total"]
        sell_total = result["sell_total"]
        buy_count = result["buy_count"]
        sell_count = result["sell_count"]
        profit_by_stock = result["profit_by_stock"]
        total_profit = realized_profit + unrealized_profit

        st.subheader("📊 손익 요약")
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1:
            st.metric("실현 손익", f"{realized_profit:+,.0f} 원", delta=f"{realized_profit:+,.0f} 원")
        with col2:
            st.metric("미실현 손익(평가)", f"{unrealized_profit:+,.0f} 원", delta=f"{unrealized_profit:+,.0f} 원")
        with col3:
            st.metric("총 손익", f"{total_profit:+,.0f} 원", delta=f"{total_profit:+,.0f} 원")
        with col4:
            st.metric("총 매수 금액", f"{buy_total:,.0f} 원")
        with col5:
            st.metric("총 매도 금액", f"{sell_total:,.0f} 원")
        with col6:
            st.metric("매수/매도 건수", f"{buy_count}건 / {sell_count}건")

        st.divider()

        st.subheader("💼 미실현 손익 (현재 보유 종목 평가)")
        if unrealized_by_stock:
            u_df = pd.DataFrame([
                {
                    "종목명": v["name"],
                    "코드": v["code"],
                    "보유수량": v["quantity"],
                    "매입평균가(원)": v["avg_buy_price"],
                    "현재가(원)": v["current_price"],
                    "평가손익(원)": v["profit_loss"],
                    "수익률(%)": v["profit_rate"]
                }
                for v in unrealized_by_stock.values()
            ])
            u_df["매입평균가(원)"] = u_df["매입평균가(원)"].apply(lambda x: f"{x:,.0f}")
            u_df["현재가(원)"] = u_df["현재가(원)"].apply(lambda x: f"{x:,.0f}")
            u_df["평가손익(원)"] = u_df["평가손익(원)"].apply(lambda x: f"{x:+,.0f}")
            u_df["수익률(%)"] = u_df["수익률(%)"].apply(lambda x: f"{x:+.2f}%")
            st.dataframe(u_df, use_container_width=True)

            fig_unreal = go.Figure(go.Bar(
                x=[v["name"] for v in unrealized_by_stock.values()],
                y=[v["profit_loss"] for v in unrealized_by_stock.values()],
                marker_color=["#ef4444" if v["profit_loss"] >= 0 else "#3b82f6" for v in unrealized_by_stock.values()],
                text=[f"{v['profit_loss']:+,.0f}" for v in unrealized_by_stock.values()],
                textposition="outside"
            ))
            fig_unreal.update_layout(
                title="보유 종목별 미실현 손익",
                template="plotly_dark",
                height=400,
                yaxis_title="평가손익 (원)",
                margin=dict(l=20, r=20, t=50, b=20)
            )
            st.plotly_chart(fig_unreal, use_container_width=True)
        else:
            st.info("현재 보유 중인 종목이 없습니다.")

        st.divider()

        sold_stocks = {k: v for k, v in profit_by_stock.items() if v["sell_qty"] > 0}
        if sold_stocks:
            st.subheader("📈 종목별 실현 손익")
            pbs_df = pd.DataFrame([
                {
                    "종목명": v["name"],
                    "코드": k,
                    "매수금액(원)": v["buy_amount"],
                    "매도금액(원)": v["sell_amount"],
                    "매수수량": v["buy_qty"],
                    "매도수량": v["sell_qty"],
                    "실현손익(원)": v["profit"]
                }
                for k, v in sold_stocks.items()
            ])
            pbs_df["매수금액(원)"] = pbs_df["매수금액(원)"].apply(lambda x: f"{x:,.0f}")
            pbs_df["매도금액(원)"] = pbs_df["매도금액(원)"].apply(lambda x: f"{x:,.0f}")
            pbs_df["실현손익(원)"] = pbs_df["실현손익(원)"].apply(lambda x: f"{x:+,.0f}")
            st.dataframe(pbs_df, use_container_width=True)

            fig_profit = go.Figure(go.Bar(
                x=[v["name"] for v in sold_stocks.values()],
                y=[v["profit"] for v in sold_stocks.values()],
                marker_color=["#ef4444" if v["profit"] >= 0 else "#3b82f6" for v in sold_stocks.values()],
                text=[f"{v['profit']:+,.0f}" for v in sold_stocks.values()],
                textposition="outside"
            ))
            fig_profit.update_layout(
                title="종목별 실현 손익",
                template="plotly_dark",
                height=400,
                yaxis_title="실현 손익 (원)",
                margin=dict(l=20, r=20, t=50, b=20)
            )
            st.plotly_chart(fig_profit, use_container_width=True)
        else:
            st.info("선택 기간 내 매도 완료된 종목이 없습니다.")

        st.divider()

        st.subheader("📋 매매 이력 상세")
        if not orders:
            st.info("선택 기간 내 매매 이력이 없습니다.")
        else:
            h_df = pd.DataFrame(orders)
            display_cols = ["order_date", "order_time", "name", "code", "buy_sell", "order_qty", "order_price", "ccld_qty", "ccld_price", "status"]
            h_df = h_df[[c for c in display_cols if c in h_df.columns]].copy()
            h_df.columns = ["주문일", "주문시각", "종목명", "코드", "구분", "주문수량", "주문가", "체결수량", "체결가", "상태"]
            h_df["주문가"] = h_df["주문가"].apply(lambda x: f"{x:,.0f}")
            h_df["체결가"] = h_df["체결가"].apply(lambda x: f"{x:,.0f}")
            h_df["체결금액(원)"] = h_df["체결수량"] * h_df["체결가"].str.replace(",", "").astype(float)
            h_df["체결금액(원)"] = h_df["체결금액(원)"].apply(lambda x: f"{x:,.0f}")
            st.dataframe(h_df, use_container_width=True)

            buy_count_total = len([o for o in orders if o["buy_sell"] == "매수"])
            sell_count_total = len([o for o in orders if o["buy_sell"] == "매도"])
            if buy_count_total + sell_count_total > 0:
                fig_pie = go.Figure(go.Pie(
                    labels=["매수", "매도"],
                    values=[buy_count_total, sell_count_total],
                    hole=0.4,
                    marker_colors=["#ef4444", "#3b82f6"]
                ))
                fig_pie.update_layout(
                    title="매수/매도 건수 비율",
                    template="plotly_dark",
                    height=350
                )
                st.plotly_chart(fig_pie, use_container_width=True)

# ==============================================================================
# 7. 전략 및 시스템 설정 페이지
# ==============================================================================
elif st.session_state["nav_page"] == "settings":
    st.title("⚙️ Strategy & System Settings • 전략 파라미터 및 환경 설정")
    
    with st.form("settings_form_page"):
        f_mock = st.toggle("모의투자 모드 활성화 (체크 해제 시 실전투자)", value=config.CURRENT_SETTINGS.get("mock_trading", True))
        f_telegram = st.toggle("텔레그램 알림 활성화 (기본: OFF)", value=config.CURRENT_SETTINGS.get("telegram_enabled", False))
        if f_telegram:
            st.caption("⚠️ 텔레그램 알림을 활성화하면 매수/매도 이벤트가 텔레그램으로 전송됩니다. api.telegram.org에 접속 가능해야 합니다.")
        else:
            st.caption("텔레그램 알림이 꺼져 있습니다. 켜려면 위 토글을 활성화하세요.")
        
        c_p1, c_p2 = st.columns(2)
        with c_p1:
            f_profit = st.number_input(
                "목표 익절 수익률 (예: 0.05 = +5%)",
                min_value=0.01,
                max_value=1.00,
                value=float(config.CURRENT_SETTINGS.get("target_profit_rate", 0.05)),
                step=0.01
            )
            f_budget = st.number_input(
                "1종목당 최대 매수 예산 (원)",
                min_value=10000,
                max_value=100000000,
                value=int(config.CURRENT_SETTINGS.get("max_buy_budget_per_stock", 500000)),
                step=50000
            )
        with c_p2:
            f_loss = st.number_input(
                "손절 기준 수익률 (예: -0.03 = -3%)",
                min_value=-0.50,
                max_value=-0.01,
                value=float(config.CURRENT_SETTINGS.get("stop_loss_rate", -0.03)),
                step=0.01
            )
            f_time = st.text_input(
                "종가 매수 스크리닝 시각 (KST)",
                value=config.CURRENT_SETTINGS.get("premarket_time", "15:15")
            )

        st.divider()
        st.write("**🛡️ 시장 국면 필터 (Market Regime Filter)**")
        c_r1, c_r2 = st.columns(2)
        with c_r1:
            f_regime_enabled = st.toggle("시장 국면 필터 활성화", value=config.CURRENT_SETTINGS.get("market_regime_filter_enabled", True))
            f_regime_block = st.toggle("약세 국면 신규 진입 전면 차단", value=config.CURRENT_SETTINGS.get("market_regime_block_weak", False))
        with c_r2:
            f_regime_cutoff_normal = st.number_input("정상 국면 매수 점수 컷오프", min_value=0, max_value=100, value=int(config.CURRENT_SETTINGS.get("market_regime_cutoff_normal", 45)), step=1)
            f_regime_cutoff_weak = st.number_input("약세 국면 매수 점수 컷오프", min_value=0, max_value=100, value=int(config.CURRENT_SETTINGS.get("market_regime_cutoff_weak", 70)), step=1)
        st.caption("약세 국면(지수가 20일 이동평균선 아래)에서는 매수 점수 컷오프를 상향(45→70)하거나 신규 진입을 차단합니다.")

        st.divider()
        st.write("**⏳ 손절 종목 쿨다운 (Cool-down)**")
        c_c1, c_c2 = st.columns(2)
        with c_c1:
            f_cooldown_enabled = st.toggle("손절 쿨다운 활성화", value=config.CURRENT_SETTINGS.get("cooldown_enabled", True))
        with c_c2:
            f_cooldown_days = st.number_input("쿨다운 기간 (거래일)", min_value=1, max_value=10, value=int(config.CURRENT_SETTINGS.get("cooldown_days", 4)), step=1)
        st.caption("손절 청산된 종목은 쿨다운 기간 동안 재매수를 금지하여 단기 횡보장 휩쏘 비용을 절감합니다.")

        st.divider()
        st.write("**📉 ATR 동적 손절 (변동성 기반 손절가)**")
        c_a1, c_a2 = st.columns(2)
        with c_a1:
            f_atr_enabled = st.toggle("ATR 동적 손절 활성화", value=config.CURRENT_SETTINGS.get("atr_stop_loss_enabled", True))
            f_atr_multiple = st.number_input("ATR 배수", min_value=0.5, max_value=5.0, value=float(config.CURRENT_SETTINGS.get("atr_stop_loss_multiple", 2.0)), step=0.1)
        with c_a2:
            f_atr_min = st.number_input("최소 손절률 (소수)", min_value=-0.20, max_value=-0.001, value=float(config.CURRENT_SETTINGS.get("atr_stop_loss_min_pct", -0.05)), step=0.01)
            f_atr_max = st.number_input("최대 손절률 (소수)", min_value=-0.20, max_value=-0.001, value=float(config.CURRENT_SETTINGS.get("atr_stop_loss_max_pct", -0.01)), step=0.01)
        f_atr_lowbreak = st.toggle("당일 저가가 손절선 이탈 시 손절", value=config.CURRENT_SETTINGS.get("atr_stop_loss_use_low_break", True))
        st.caption("진입가 - (2 × ATR)을 손절선으로 사용하여 고정 -3% 대신 정상적인 시장 노이즈에 털리는 현상을 방지합니다.")

        st.divider()
        st.write("**🛡️ 1일 최대 신규 매수 & 트레일링 스탑 & 타임컷**")
        c_tr1, c_tr2 = st.columns(2)
        with c_tr1:
            f_max_daily_buy = st.number_input(
                "1일 최대 신규 매수 종목 수",
                min_value=1,
                max_value=10,
                value=int(config.CURRENT_SETTINGS.get("max_daily_buy_count", 2)),
                step=1
            )
            f_trailing_stop_pct = st.number_input(
                "1차 익절 후 고점 대비 트레일링 스탑 비율 (예: 0.035 = 3.5%)",
                min_value=0.01,
                max_value=0.20,
                value=float(config.CURRENT_SETTINGS.get("trailing_stop_pct", 0.035)),
                step=0.005
            )
        with c_tr2:
            f_time_stop_enabled = st.toggle("타임컷(보유기간 만료) 청산 활성화", value=config.CURRENT_SETTINGS.get("time_stop_enabled", True))
            f_time_stop_days = st.number_input("타임컷 보유 일수 (거래일)", min_value=2, max_value=30, value=int(config.CURRENT_SETTINGS.get("time_stop_days", 6)), step=1)
            f_time_stop_min_profit = st.number_input("타임컷 기준 최소 수익률", min_value=-0.10, max_value=0.10, value=float(config.CURRENT_SETTINGS.get("time_stop_min_profit", 0.02)), step=0.01)

        st.divider()
        st.write(f"**📋 관심/스크리닝 유니버스 종목 관리 (현재 {len(config.CURRENT_SETTINGS.get('watchlist', []))}개 종목)**")
        wl = config.CURRENT_SETTINGS.get("watchlist", [])
        wl_text = "\n".join([f"{w.get('code')},{w.get('name')},{w.get('market', 'KOSPI')}" for w in wl])
        f_wl_raw = st.text_area(
            "종목코드,종목명,시장 (줄단위 입력/수정)",
            value=wl_text,
            height=250,
            help="한 줄에 한 종목씩 '코드,종목명,시장(KOSPI/KOSDAQ/ETF)' 형식으로 입력하세요."
        )

        submitted = st.form_submit_button("💾 설정 저장 및 즉시 적용", type="primary")
        if submitted:
            new_wl = []
            for line in f_wl_raw.strip().split("\n"):
                parts = [p.strip() for p in line.split(",") if p.strip()]
                if len(parts) >= 2:
                    new_wl.append({
                        "code": parts[0],
                        "name": parts[1],
                        "market": parts[2] if len(parts) > 2 else "KOSPI"
                    })

            new_settings = config.CURRENT_SETTINGS.copy()
            new_settings.update({
                "mock_trading": f_mock,
                "telegram_enabled": f_telegram,
                "target_profit_rate": f_profit,
                "stop_loss_rate": f_loss,
                "max_buy_budget_per_stock": f_budget,
                "premarket_time": f_time,
                "watchlist": new_wl,
                "market_regime_filter_enabled": f_regime_enabled,
                "market_regime_block_weak": f_regime_block,
                "market_regime_cutoff_normal": f_regime_cutoff_normal,
                "market_regime_cutoff_weak": f_regime_cutoff_weak,
                "cooldown_enabled": f_cooldown_enabled,
                "cooldown_days": f_cooldown_days,
                "atr_stop_loss_enabled": f_atr_enabled,
                "atr_stop_loss_multiple": f_atr_multiple,
                "atr_stop_loss_min_pct": f_atr_min,
                "atr_stop_loss_max_pct": f_atr_max,
                "atr_stop_loss_use_low_break": f_atr_lowbreak,
                "max_daily_buy_count": f_max_daily_buy,
                "trailing_stop_pct": f_trailing_stop_pct,
                "time_stop_enabled": f_time_stop_enabled,
                "time_stop_days": f_time_stop_days,
                "time_stop_min_profit": f_time_stop_min_profit
            })
            config.save_settings(new_settings)
            config.CURRENT_SETTINGS = new_settings
            st.success("✅ 설정이 성공적으로 저장 및 적용되었습니다!")
            time.sleep(1)
            st.rerun()

    # 간편 종목 추가/삭제 툴바
    st.divider()
    st.subheader("⚡ 간편 종목 추가 및 삭제")
    col_add, col_del = st.columns(2)
    with col_add:
        with st.form("quick_add_stock_form"):
            st.write("##### ➕ 관심종목 빠른 추가")
            add_code = st.text_input("종목코드 (6자리)", placeholder="예: 005930")
            add_name = st.text_input("종목명", placeholder="예: 삼성전자")
            add_market = st.selectbox("시장 구분", ["KOSPI", "KOSDAQ", "ETF"])
            add_btn = st.form_submit_button("추가하기")
            if add_btn:
                if add_code and add_name:
                    cur_wl = config.CURRENT_SETTINGS.get("watchlist", [])
                    if any(w.get("code") == add_code.strip() for w in cur_wl):
                        st.warning(f"이미 등록된 종목코드입니다: {add_code}")
                    else:
                        cur_wl.append({
                            "code": add_code.strip(),
                            "name": add_name.strip(),
                            "market": add_market
                        })
                        config.CURRENT_SETTINGS["watchlist"] = cur_wl
                        config.save_settings(config.CURRENT_SETTINGS)
                        st.success(f"✅ {add_name}({add_code}) 종목이 추가되었습니다!")
                        time.sleep(1)
                        st.rerun()
                else:
                    st.error("종목코드와 종목명을 모두 입력해주세요.")

    with col_del:
        with st.form("quick_del_stock_form"):
            st.write("##### 🗑️ 관심종목 선택 삭제")
            cur_wl = config.CURRENT_SETTINGS.get("watchlist", [])
            del_options = [f"{w.get('name')} ({w.get('code')}) [{w.get('market', 'KOSPI')}]" for w in cur_wl]
            selected_del = st.multiselect("삭제할 종목 선택", del_options)
            del_btn = st.form_submit_button("선택 종목 삭제", type="primary")
            if del_btn:
                if selected_del:
                    del_codes = {opt.split("(")[1].split(")")[0].strip() for opt in selected_del if "(" in opt}
                    new_wl = [w for w in cur_wl if w.get("code") not in del_codes]
                    config.CURRENT_SETTINGS["watchlist"] = new_wl
                    config.save_settings(config.CURRENT_SETTINGS)
                    st.success(f"✅ {len(del_codes)}개 종목이 삭제되었습니다!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("삭제할 종목을 1개 이상 선택해주세요.")
