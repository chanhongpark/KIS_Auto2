"""
KIS Auto Trading - Consolidated Dashboard & Portfolio Views
자산 개요, 포트폴리오 리스크 매트릭스, 주문/체결 내역, 실현 손익 분석을 탭(Tab)으로 통합
"""
import time
import datetime
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from time_utils import now_str, today
from telegram_notifier import notifier
from ui.styles import render_interactive_stock_chart

def render_overview_tab(api, screener, summary, holdings, proposals, holding_codes):
    """자산 개요 탭 (Overview)"""
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
        st.subheader("🌅 15:15 종가 매수 추천 Top")
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
        st.subheader("🚨 매도 & 리스크 알림")
        sell_list = proposals.get("sell_proposals", [])
        if not sell_list:
            st.success("현재 매도가 시급한 보유 종목이 없습니다.")
        else:
            for s in sell_list:
                urgent_badge = "🚨 [긴급 손절]" if s.get("is_urgent") else "⚠️ [매도 신호]"
                sell_type = s.get("sell_type", "매도")
                st.warning(f"**{urgent_badge} [{s['name']} ({s['code']})]** {sell_type} | 수익률: **{s['profit_rate']:+.2f}%** | 매도수량: {s['sell_qty']}주\n- {', '.join(s.get('reasons', []))}")

    st.divider()
    st.subheader("📦 현재 보유 주식 요약 & 인터랙티브 차트")
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
        st.dataframe(h_df, width="stretch")

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

def render_risk_tab(api, screener, holdings, proposals, realtime_detection_fragment):
    """포지션 & 리스크 관리 탭 (Risk Matrix)"""
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
                    btn_text = "🚨 긴급 매도" if is_urgent else f"⚡ 매도 ({sell_ord_type})"
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
        st.dataframe(h_df, width="stretch")

def render_execution_tab(api):
    """주문/체결 내역 탭 (Execution)"""
    if st.button("🔄 당일 체결 내역 새로고침", key="btn_refresh_orders_tab"):
        st.rerun()

    orders = api.get_order_history()
    if not orders:
        st.info("금일 전송된 주문 내역이 없습니다.")
    else:
        o_df = pd.DataFrame(orders)
        st.dataframe(o_df, width="stretch")

def render_performance_tab(api):
    """실현/미실현 손익 분석 탭 (Performance)"""
    col_date1, col_date2, col_date3 = st.columns([1.5, 1.5, 1])
    with col_date1:
        start_date = st.date_input(
            "조회 시작일",
            value=today() - datetime.timedelta(days=30),
            max_value=today(),
            key="perf_start_date"
        )
    with col_date2:
        end_date = st.date_input(
            "조회 종료일",
            value=today(),
            max_value=today(),
            key="perf_end_date"
        )
    with col_date3:
        st.write("")
        st.write("")
        if st.button("🔍 조회", key="btn_perf_search", type="primary", use_container_width=True):
            st.rerun()

    if start_date > end_date:
        st.error("⚠️ 시작일이 종료일보다 늦을 수 없습니다.")
    else:
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")

        with st.spinner("매매 이력 및 손익 분석 중..."):
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
            st.dataframe(pbs_df, width="stretch")

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
                height=350,
                yaxis_title="실현 손익 (원)",
                margin=dict(l=20, r=20, t=40, b=20)
            )
            st.plotly_chart(fig_profit, use_container_width=True)
        else:
            st.info("선택 기간 내 매도 완료된 종목이 없습니다.")

def render_dashboard(api, screener, summary, holdings, proposals, holding_codes, realtime_detection_fragment):
    """통합 자산 & 포트폴리오 메인 뷰 (4개 서브 탭)"""
    st.title("📊 자산 & 포트폴리오 관제")
    st.caption(f"서버 시각: {now_str()} (KST) | 계좌: {api.cano}-{api.acnt_prdt_cd}")

    tab1, tab2, tab3, tab4 = st.tabs([
        "🏠 자산 요약 (Overview)",
        "🛡️ 포지션 & 리스크 관리",
        "⚡ 주문/체결 내역 (Execution)",
        "📜 실현 손익 분석 (Performance)"
    ])

    with tab1:
        render_overview_tab(api, screener, summary, holdings, proposals, holding_codes)
    with tab2:
        render_risk_tab(api, screener, holdings, proposals, realtime_detection_fragment)
    with tab3:
        render_execution_tab(api)
    with tab4:
        render_performance_tab(api)
