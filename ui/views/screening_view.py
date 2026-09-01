"""
KIS Auto Trading - Screening & Order View
15:15 종가 매수 스크리닝 및 원클릭/LOC 주문 발주 뷰
"""
import time
import streamlit as st
from telegram_notifier import notifier
from ui.styles import render_interactive_stock_chart

def render_screener(api, screener, proposals, holding_codes):
    """2. 15:15 종가 매수 스크리닝 & 발주 페이지"""
    col_t1, col_t2 = st.columns([3.2, 1.3])
    with col_t1:
        st.title("🎯 15:15 종가 매수 • 스크리닝 & 발주")
        st.caption(f"스크리닝 기준 시각: **{proposals.get('generated_at', '-')}** | 거래량 1.04배 보정치 & 캡 점수 적용 (45점 이상)")
    with col_t2:
        st.write("")
        if st.button("🔄 즉시 종가 스크리닝 실행", key="btn_run_screener_page", type="primary", width="stretch"):
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
                    if st.button(btn_label, key=f"btn_buy_{item['code']}_{idx}", type="primary", width="stretch"):
                        if ord_type == "지정가":
                            ord_dv = "00"
                            order_prc = int(target_price)
                        elif ord_type == "LOC (종가조건부)":
                            ord_dv = "51"
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
                    render_interactive_stock_chart(
                        api_client=api,
                        screener_engine=screener,
                        code=item["code"],
                        name=item["name"]
                    )
                st.divider()
