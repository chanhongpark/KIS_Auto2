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
        st.caption(f"스크리닝 기준 시각: **{proposals.get('generated_at', '-')}** | 개별주식선물 파생수급 & 100점 만점 척도 적용 (60점 이상)")
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
        st.info("💡 오늘 매수 추천 기준(총점 60점 이상 & 수급 필수 게이트 충족)에 도달한 종목은 없습니다.")
        top_candidates = proposals.get("top_candidates", [])
        if top_candidates:
            st.markdown("---")
            st.subheader("👀 [관망 후보 Top 3] 상대 점수 상위 종목 (※ 매수 추천 아님)")
            st.caption("매수 조건(게이트 또는 컷오프)을 모두 만족하지는 못했으나, 분석 대상 종목 중 기술적/수급 점수가 가장 높았던 상위 3개 항목입니다. 주문 발주 대상이 아니며 단순 관망 및 시장 흐름 파악용입니다.")
            for idx, item in enumerate(top_candidates, 1):
                with st.container():
                    col_info, col_score = st.columns([3.5, 1.0])
                    with col_info:
                        st.markdown(f"#### {idx}위. {item['name']} <small style='color:#64748b'>({item['code']})</small>", unsafe_allow_html=True)
                        st.write(f"**현재가:** `{item['current_price']:,.0f}원` ({item.get('change_rate', 0.0):+.2f}%)")
                        
                        badges = [f"<span class='score-badge' style='background:#334155; color:#f1f5f9; font-weight:bold;'>종합 {item['score']}점</span>"]
                        if "trend_score" in item:
                            badges.append(f"<span class='score-badge'>추세 {item['trend_score']}/30</span>")
                        if "supply_score" in item:
                            badges.append(f"<span class='score-badge'>수급 {item['supply_score']}/25</span>")
                        if "momentum_score" in item:
                            badges.append(f"<span class='score-badge'>모멘텀 {item['momentum_score']}/25</span>")
                        if item.get("futures_score") is not None:
                            basis_tag = "콘탱고" if item.get("is_contango") else "백워데이션"
                            basis_val = item.get("market_basis", 0)
                            badges.append(f"<span class='score-badge' style='background:#064e3b; border:1px solid #059669; color:#34d399;'>선물 {item['futures_score']}/20 ({basis_tag} {basis_val:+,.0f}원)</span>")
                        elif item.get("has_futures") is False:
                            badges.append("<span class='score-badge' style='background:#1e293b; border:1px solid #475569; color:#94a3b8;'>선물미상장</span>")
                        st.markdown(" ".join(badges), unsafe_allow_html=True)
                        
                        disq = item.get("disqualify_reason")
                        if disq:
                            st.caption(f"⚠️ **미추천 사유:** <span style='color:#f87171;'>{disq}</span>", unsafe_allow_html=True)
                    with col_score:
                        st.metric("종합 점수", f"{item['score']}점")
                st.divider()
    else:
        for idx, item in enumerate(buy_list):
            with st.container():
                c1, c2, c3, c4 = st.columns([2.8, 2.3, 2.3, 2.0])
                with c1:
                    buy_tag = "🔄 추가매수" if item.get("code") in holding_codes else "🆕 신규매수"
                    st.markdown(f"### {buy_tag} {item['name']} <small style='color:#64748b'>({item['code']})</small>", unsafe_allow_html=True)
                    st.write(f"**현재가:** `{item['current_price']:,.0f}원` ({item['change_rate']:+.2f}%)")
                    
                    strat_disp = item.get("strategy_display_name", item.get("strategy", ""))
                    badges = [f"<span class='score-badge'>총점 {item['score']}점</span>"]
                    if strat_disp:
                        badges.append(f"<span class='score-badge' style='background:#1e293b; border:1px solid #3b82f6; color:#60a5fa;'>🎯 {strat_disp}</span>")
                    if "trend_score" in item:
                        badges.append(f"<span class='score-badge'>추세 {item['trend_score']}/30</span>")
                    if "supply_score" in item:
                        badges.append(f"<span class='score-badge'>수급 {item['supply_score']}/25</span>")
                    if "momentum_score" in item:
                        badges.append(f"<span class='score-badge'>모멘텀 {item['momentum_score']}/25</span>")
                    if item.get("futures_score") is not None:
                        basis_tag = "콘탱고" if item.get("is_contango") else "백워데이션"
                        basis_val = item.get("market_basis", 0)
                        badges.append(f"<span class='score-badge' style='background:#064e3b; border:1px solid #059669; color:#34d399;'>📊 선물 {item['futures_score']}/20 ({basis_tag} {basis_val:+,.0f}원)</span>")
                    elif item.get("has_futures") is False:
                        badges.append("<span class='score-badge' style='background:#1e293b; border:1px solid #475569; color:#94a3b8;'>선물미상장(환산)</span>")
                    if item.get("futures_warning"):
                        badges.append("<span class='score-badge' style='background:#450a0a; border:1px solid #ef4444; color:#f87171;'>🚨 선물역행주의</span>")
                    if item.get("w52_drop_rate") is not None:
                        badges.append(f"<span class='score-badge' style='color:#f87171;'>52주고가대비 {item['w52_drop_rate']:+.1f}%</span>")
                    st.markdown(" ".join(badges), unsafe_allow_html=True)
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
                            ord_dv = "02"
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
                                try:
                                    screener.position_tracker.record_buy(
                                        code=item["code"],
                                        name=item["name"],
                                        price=float(target_price),
                                        qty=order_qty,
                                        strategy=item.get("strategy_name", item.get("strategy", "momentum")),
                                        strategy_display_name=item.get("strategy_display_name")
                                    )
                                except Exception as e:
                                    screener.logger.warning(f"포지션 상태 기록 예외: {e}")

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
