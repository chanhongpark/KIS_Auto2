"""
KIS Auto Trader - Streamlit Control Center (Page Navigation)
한국투자증권 API 기반 주식 자동매매 & 제어 대시보드
"""
import os
import time
import datetime
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config
from kis_api import KISApiClient
from screener import StockScreener
from scheduler import start_scheduler

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

# 사이드바 구성 (럭셔리 퀀트 터미널)
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
            <div style="font-size: 0.72rem; color: #94a3b8; margin-top: 4px;">⏰ 스케줄: 매일 {config.CURRENT_SETTINGS.get('premarket_time', '08:30')} KST</div>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("<div class='nav-header'>NAVIGATION WORKSPACE</div>", unsafe_allow_html=True)
    
    # 5대 메뉴 버튼 리스트 (인터랙티브 카드 스타일)
    menu_items = [
        ("overview", "📊 Overview • 종합 관제"),
        ("screener", "🎯 Alpha Screener • 매수 발굴"),
        ("portfolio", "💼 Portfolio & Risk • 매도 진단"),
        ("execution", "⚡ Execution • 주문/체결"),
        ("settings", "⚙️ Settings • 시스템 설정")
    ]

    for key, label in menu_items:
        is_active = (st.session_state["nav_page"] == key)
        if st.button(
            label,
            key=f"nav_btn_{key}",
            type="primary" if is_active else "secondary",
            use_container_width=True
        ):
            st.session_state["nav_page"] = key
            st.rerun()

    st.divider()
    st.markdown("<div class='nav-header'>QUICK ACTIONS</div>", unsafe_allow_html=True)
    if st.button("🔄 계좌 잔고 동기화", use_container_width=True, key="btn_quick_sync"):
        st.rerun()

    if st.button("🔍 100종목 즉시 스크리닝", use_container_width=True, key="btn_quick_screen"):
        with st.spinner("100개 종목 퀀트 지표 분석 중..."):
            screener.run_premarket_screening()
            st.success("스크리닝 완료!")
            time.sleep(1)
            st.rerun()

    st.caption("KIS Auto Trading Engine v2.0 • Ultra Low-Latency")

# 계좌 및 제안서 데이터 조회
balance_data = api.get_account_balance()
summary = balance_data.get("summary", {})
holdings = balance_data.get("holdings", [])
proposals = screener.load_proposals()

# ==============================================================================
# 1. 종합 대시보드 페이지
# ==============================================================================
if st.session_state["nav_page"] == "overview":
    st.title("🏠 종합 자산 및 매매 모니터링")
    st.caption(f"서버 시각: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (KST)")

    # 상단 요약 카드
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
        st.subheader("🌅 오늘의 Top 매수 추천 종목")
        buy_list = proposals.get("buy_proposals", [])
        if not buy_list:
            st.info("현재 추천된 매수 종목이 없습니다. 사이드바에서 스크리닝을 실행해 보세요.")
        else:
            for b in buy_list[:3]:
                st.markdown(f"**[{b['name']} ({b['code']})]** 현재가: `{b['current_price']:,.0f}원` | 점수: `{b['score']}점` | 추천: `{b['recommended_qty']}주`")
                st.caption(", ".join(b.get("reasons", [])))

    with c_right:
        st.subheader("🚨 매도 추천 알림")
        sell_list = proposals.get("sell_proposals", [])
        if not sell_list:
            st.success("현재 매도가 시급한 보유 종목이 없습니다.")
        else:
            for s in sell_list:
                st.warning(f"**[{s['name']} ({s['code']})]** 수익률: **{s['profit_rate']:+.2f}%** | 보유: {s['holding_qty']}주\n- {', '.join(s.get('reasons', []))}")

    st.divider()
    st.subheader("📦 현재 보유 주식 요약")
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

# ==============================================================================
# 2. 개장 전 매수 추천 페이지
# ==============================================================================
elif st.session_state["nav_page"] == "screener":
    st.title("🎯 Alpha Screener • 매수 추천")
    st.caption(f"100종목 퀀트 분석 기준: **{proposals.get('generated_at', '-')}** (월~금 08:30 KST)")

    buy_list = proposals.get("buy_proposals", [])
    if not buy_list:
        st.info("현재 추천된 매수 종목이 없습니다. 사이드바에서 스크리닝을 실행해 주세요.")
    else:
        for idx, item in enumerate(buy_list):
            with st.container():
                c1, c2, c3, c4 = st.columns([2.8, 2.2, 2.5, 2.0])
                with c1:
                    st.markdown(f"### {item['name']} <small style='color:#64748b'>({item['code']})</small>", unsafe_allow_html=True)
                    st.write(f"**현재가:** `{item['current_price']:,.0f}원` ({item['change_rate']:+.2f}%)")
                    st.write(f"**신호 점수:** `{item['score']}점` | **RSI:** `{item.get('rsi')}`")
                    reasons_text = " • ".join(item.get("reasons", []))
                    st.caption(reasons_text)
                
                with c2:
                    # 주문 유형 선택 (기본: 시장가)
                    ord_type = st.radio(
                        "주문 유형",
                        ["시장가", "지정가"],
                        horizontal=True,
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
                    else:
                        target_price = int(item['current_price'])
                        st.caption("⚡ 시장가 즉시 체결")

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
                        is_limit = (ord_type == "지정가")
                        ord_dv = "00" if is_limit else "01"
                        order_prc = int(target_price) if is_limit else 0
                        
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
                                time.sleep(1.5)
                                st.rerun()
                            else:
                                st.error(f"❌ 주문 실패: {res.get('msg1')}")

                # 매수 후보 상세보기 (차트 및 주요 지표)
                with st.expander(f"📈 {item['name']} 차트 및 지표 상세 분석"):
                    with st.spinner(f"{item['name']} 차트 데이터 로드 중..."):
                        candles = api.get_daily_chart(item["code"], count=60)
                        df_tech = screener.calculate_technical_indicators(candles)
                        
                        if df_tech is not None and not df_tech.empty:
                            fig = make_subplots(
                                rows=3, cols=1,
                                shared_xaxes=True,
                                vertical_spacing=0.04,
                                row_heights=[0.55, 0.20, 0.25],
                                subplot_titles=(f"{item['name']} 일봉 캔들 & 이동평균선 & 볼린저밴드", "거래량 & 20일 거래량 이평", "RSI (14)")
                            )

                            # 캔들스틱 차트
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

                            # 거래량 차트
                            colors = ["#ef4444" if row["close"] >= row["open"] else "#3b82f6" for _, row in df_tech.iterrows()]
                            fig.add_trace(go.Bar(x=df_tech["date"], y=df_tech["volume"], marker_color=colors, name="거래량"), row=2, col=1)
                            fig.add_trace(go.Scatter(x=df_tech["date"], y=df_tech["vol_ma20"], line=dict(color="#fbbf24", width=1.5), name="20일 거래량이평"), row=2, col=1)

                            # RSI 차트
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

                            latest = df_tech.iloc[-1]
                            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
                            with m_col1:
                                st.metric("RSI(14)", f"{latest['rsi14']:.1f}", delta=f"{latest['rsi14']-df_tech.iloc[-2]['rsi14']:+.1f}")
                            with m_col2:
                                vol_ratio = (latest['volume'] / (latest['vol_ma20'] + 1e-9)) * 100
                                st.metric("20일 평균대비 거래량", f"{vol_ratio:.0f}%")
                            with m_col3:
                                st.metric("20일선", f"{latest['ma20']:,.0f}원")
                            with m_col4:
                                st.metric("볼린저 하단", f"{latest['bb_lower']:,.0f}원")
                        else:
                            st.warning("차트 데이터를 불러올 수 없습니다.")
                st.divider()

# ==============================================================================
# 3. 보유 종목 & 매도 관리 페이지
# ==============================================================================
elif st.session_state["nav_page"] == "portfolio":
    st.title("💼 Portfolio & Risk • 보유 종목 및 매도 진단")

    # 매도 추천 긴급/주의 종목
    sell_list = proposals.get("sell_proposals", [])
    if sell_list:
        st.warning(f"⚠️ **{len(sell_list)}건**의 매도 시그널이 감지되었습니다.")
        for s_idx, s_item in enumerate(sell_list):
            with st.expander(f"🚨 [매도 신호] {s_item['name']} ({s_item['code']}) • 수익률 {s_item['profit_rate']:+.2f}%", expanded=True):
                sc1, sc2, sc3, sc4 = st.columns([2.5, 2.0, 2.0, 2.0])
                with sc1:
                    st.write(f"**보유량:** `{s_item['holding_qty']:,}주` | **평단가:** `{s_item['avg_buy_price']:,.0f}원`")
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
                    sell_qty = st.number_input(
                        "매도 수량(주)",
                        min_value=1,
                        max_value=s_item["holding_qty"],
                        value=s_item["holding_qty"],
                        key=f"sell_qty_{s_item['code']}_{s_idx}"
                    )
                    st.write(f"예상 매도액: **{sell_qty * sell_target_price:,.0f}원**")

                with sc4:
                    st.write("")
                    st.write("")
                    if st.button(f"🚨 매도 ({sell_ord_type})", key=f"btn_sell_{s_item['code']}_{s_idx}", type="primary", use_container_width=True):
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
                                time.sleep(1.5)
                                st.rerun()
                            else:
                                st.error(f"❌ 매도 실패: {res.get('msg1')}")
        st.divider()

    # 전체 보유 종목 테이블
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

# ==============================================================================
# 4. 당일 주문 및 체결 내역 페이지
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
# 5. 전략 및 시스템 설정 페이지
# ==============================================================================
elif st.session_state["nav_page"] == "settings":
    st.title("⚙️ Strategy & System Settings • 전략 파라미터 및 환경 설정")
    
    with st.form("settings_form_page"):
        f_mock = st.toggle("모의투자 모드 활성화 (체크 해제 시 실전투자)", value=config.CURRENT_SETTINGS.get("mock_trading", True))
        
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
                "개장 전 자동 스크리닝 시각 (KST)",
                value=config.CURRENT_SETTINGS.get("premarket_time", "08:30")
            )

        st.divider()
        st.write(f"**관심/스크리닝 유니버스 종목 관리 (현재 {len(config.CURRENT_SETTINGS.get('watchlist', []))}개 종목)**")
        wl = config.CURRENT_SETTINGS.get("watchlist", [])
        wl_text = "\n".join([f"{w.get('code')},{w.get('name')},{w.get('market', 'KOSPI')}" for w in wl])
        f_wl_raw = st.text_area(
            "종목코드,종목명,시장 (줄단위 입력)",
            value=wl_text,
            height=300
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

            new_settings = {
                "mock_trading": f_mock,
                "target_profit_rate": f_profit,
                "stop_loss_rate": f_loss,
                "max_buy_budget_per_stock": f_budget,
                "premarket_time": f_time,
                "watchlist": new_wl
            }
            config.save_settings(new_settings)
            config.CURRENT_SETTINGS = new_settings
            st.success("✅ 설정이 저장되었습니다!")
            time.sleep(1)
            st.rerun()
