"""
KIS Auto Trading - Settings View
전략 파라미터, 시장 국면 프리셋(BULL/VOLATILE/BEAR/AUTO) 및 관심종목(Watchlist) 관리 뷰
프리셋 변경 시 폼 입력값 실시간 동기화 지원
"""
import time
import streamlit as st
import config

def render_settings():
    """7. 전략 및 시스템 설정 페이지"""
    st.title("⚙️ Strategy & System Settings • 전략 파라미터 및 환경 설정")

    # -------------------------------------------------------------
    # [상단: 시장 국면 프리셋 선택기]
    # -------------------------------------------------------------
    st.markdown("### 🎯 시장 국면별 원클릭 프리셋 (Market Regime Preset)")
    
    preset_options = {
        "AUTO": "🤖 지수 연동 자동 감지 (AUTO - KOSPI 국면에 맞춰 실시간 스위칭)",
        "BULL": "🔥 상승장 모드 (Bull - 목표익절 +8%, 20일선 트레일링, 손절 -5.0%, 타임컷 12일)",
        "VOLATILE": "⚡ 변동성/횡보장 모드 (Volatile - 목표익절 +5%, 트레일링 3.5%, 손절 -3.5%, 타임컷 6일)",
        "BEAR": "🛡️ 하락장/방어 모드 (Bear - 목표익절 +3%, 칼손절 -2.5%, 컷오프 70점, 타임컷 3일)",
        "CUSTOM": "🛠️ 사용자 직접 커스텀 설정 (Custom)"
    }
    
    current_mode = config.CURRENT_SETTINGS.get("regime_preset_mode", "AUTO")
    current_idx = list(preset_options.keys()).index(current_mode) if current_mode in preset_options else 0

    selected_mode_key = st.radio(
        "전략 운영 모드 선택 (선택 시 아래 설정 항목에 해당 프리셋 기본값이 즉시 반영됩니다)",
        options=list(preset_options.keys()),
        format_func=lambda x: preset_options[x],
        index=current_idx,
        horizontal=False,
        key="regime_preset_radio"
    )

    # -------------------------------------------------------------
    # 프리셋 선택에 따른 UI 표시용 설정값 계산 (실시간 동기화)
    # -------------------------------------------------------------
    display_settings = config.CURRENT_SETTINGS.copy()
    if selected_mode_key in config.MARKET_REGIME_PRESETS:
        preset_vals = config.MARKET_REGIME_PRESETS[selected_mode_key]
        for k, v in preset_vals.items():
            if k not in ["name", "description"]:
                display_settings[k] = v
        st.info(f"**선택된 프리셋 안내:** {preset_vals.get('description', '')}\n\n👉 *아래 폼에 **{preset_vals.get('name')}**의 권장 파라미터가 자동으로 입력되었습니다. 확인 후 하단 [설정 저장] 버튼을 누르시면 적용됩니다.*")
    elif selected_mode_key == "AUTO":
        st.info("💡 **지수 연동 자동 감지(AUTO) 모드**: 코스피 지수의 20일/60일 이동평균선 위치와 기울기를 실시간 분석하여 **상승장(BULL) / 횡보장(VOLATILE) / 하락장(BEAR)** 파라미터를 실시간 자동 전환합니다.")
    else:
        st.info("🛠️ **사용자 직접 커스텀 설정**: 원하시는 모든 파라미터를 자유롭게 수정하여 저장할 수 있습니다.")

    st.divider()

    with st.form("settings_form_page"):
        f_mock = st.toggle("모의투자 모드 활성화 (체크 해제 시 실전투자)", value=display_settings.get("mock_trading", True))
        f_telegram = st.toggle("텔레그램 알림 활성화 (기본: OFF)", value=display_settings.get("telegram_enabled", False))
        if f_telegram:
            st.caption("⚠️ 텔레그램 알림을 활성화하면 매수/매도 이벤트가 텔레그램으로 전송됩니다. api.telegram.org에 접속 가능해야 합니다.")
        else:
            st.caption("텔레그램 알림이 꺼져 있습니다. 켜려면 위 토글을 활성화하세요.")
        
        c_p1, c_p2 = st.columns(2)
        with c_p1:
            f_profit = st.number_input(
                "목표 익절 수익률 (예: 0.08 = +8%)",
                min_value=0.01,
                max_value=1.00,
                value=float(display_settings.get("target_profit_rate", 0.08)),
                step=0.01
            )
            f_budget = st.number_input(
                "1종목당 최대 매수 예산 (원)",
                min_value=10000,
                max_value=100000000,
                value=int(display_settings.get("max_buy_budget_per_stock", 500000)),
                step=50000
            )
        with c_p2:
            f_loss = st.number_input(
                "손절 기준 수익률 (예: -0.05 = -5%)",
                min_value=-0.50,
                max_value=-0.01,
                value=float(display_settings.get("stop_loss_rate", -0.05)),
                step=0.01
            )
            f_time = st.text_input(
                "종가 매수 스크리닝 시각 (KST)",
                value=display_settings.get("premarket_time", "15:15")
            )

        st.divider()
        st.write("**🛡️ 시장 국면 필터 (Market Regime Filter)**")
        c_r1, c_r2 = st.columns(2)
        with c_r1:
            f_regime_enabled = st.toggle("시장 국면 필터 활성화", value=display_settings.get("market_regime_filter_enabled", True))
            f_regime_block = st.toggle("약세 국면 신규 진입 전면 차단", value=display_settings.get("market_regime_block_weak", False))
        with c_r2:
            f_regime_cutoff_normal = st.number_input("정상/상승 국면 매수 점수 컷오프", min_value=0, max_value=100, value=int(display_settings.get("market_regime_cutoff_normal", 45)), step=1)
            f_regime_cutoff_weak = st.number_input("약세/하락 국면 매수 점수 컷오프", min_value=0, max_value=100, value=int(display_settings.get("market_regime_cutoff_weak", 70)), step=1)
        st.caption("약세 국면(지수가 20일 이동평균선 아래)에서는 매수 점수 컷오프를 상향(45→70)하거나 신규 진입을 차단합니다.")

        st.divider()
        st.write("**⏳ 타임컷 (Time-based Exit / 기간 만료 청산)**")
        c_t1, c_t2 = st.columns(2)
        with c_t1:
            f_time_stop_enabled = st.toggle("타임컷 청산 활성화", value=display_settings.get("time_stop_enabled", True))
            f_time_stop_days = st.number_input("타임컷 보유 일수 (영업일 기준)", min_value=1, max_value=30, value=int(display_settings.get("time_stop_days", 12)), step=1)
        with c_t2:
            f_time_stop_min_profit = st.number_input("타임컷 기준 최소 수익률 (예: 0.02 = +2%)", min_value=0.0, max_value=0.20, value=float(display_settings.get("time_stop_min_profit", 0.02)), step=0.005)
        st.caption("지정된 영업일이 경과하도록 최소 수익률에 도달하지 못한 비주도주는 자금 회수를 위해 기계적으로 청산합니다.")

        st.divider()
        st.write("**🧊 손절 종목 재매수 쿨다운 (Cool-down)**")
        c_c1, c_c2 = st.columns(2)
        with c_c1:
            f_cooldown_enabled = st.toggle("손절 쿨다운 활성화", value=display_settings.get("cooldown_enabled", True))
        with c_c2:
            f_cooldown_days = st.number_input("손절 후 재매수 금지 기간 (거래일 기준)", min_value=1, max_value=20, value=int(display_settings.get("cooldown_days", 4)), step=1)
        st.caption("손절 청산된 종목은 단기 역추세 위험이 있으므로 지정된 거래일 동안 신규 매수 추천에서 배제됩니다.")

        st.divider()
        st.write("**📈 변동성 기반 ATR 동적 손절 (ATR Stop Loss)**")
        c_a1, c_a2 = st.columns(2)
        with c_a1:
            f_atr_stop_enabled = st.toggle("ATR 동적 손절 활성화", value=display_settings.get("atr_stop_loss_enabled", True))
            f_atr_stop_multiple = st.number_input("ATR 손절 배수 (진입가 - N×ATR)", min_value=1.0, max_value=5.0, value=float(display_settings.get("atr_stop_loss_multiple", 2.2)), step=0.1)
        with c_a2:
            f_atr_stop_min_pct = st.number_input("ATR 손절 최소 허용 손실률 (하한, 예: -0.055 = -5.5%)", min_value=-0.20, max_value=-0.01, value=float(display_settings.get("atr_stop_loss_min_pct", -0.055)), step=0.005)
            f_atr_stop_max_pct = st.number_input("ATR 손절 최대 허용 손실률 (상한, 예: -0.035 = -3.5%)", min_value=-0.10, max_value=-0.005, value=float(display_settings.get("atr_stop_loss_max_pct", -0.035)), step=0.005)
        st.caption("종목별 일일 변동성(ATR)을 반영하여 손절 폭을 유연하게 산출하며, 하한/상한 범위를 벗어나지 않도록 클리핑합니다.")

        st.divider()
        st.write("**🛡️ 1일 최대 신규 매수 종목 수 제한**")
        f_max_daily_buy = st.number_input("1일 최대 신규 매수 종목 수 (집단 갭하락 리스크 방어)", min_value=1, max_value=10, value=int(display_settings.get("max_daily_buy_count", 3)), step=1)
        st.caption("하루에 너무 많은 종목이 동시에 매수되어 시장 급락 시 포트폴리오 전체가 타격을 입는 현상을 방지합니다.")

        st.divider()
        st.write("**📊 변동성 조절 포지션 사이징 (Volatility Sizing)**")
        c_v1, c_v2 = st.columns(2)
        with c_v1:
            f_vol_sizing_enabled = st.toggle("변동성 기반 포지션 사이징 활성화", value=display_settings.get("volatility_sizing_enabled", True))
            f_risk_per_trade = st.number_input("1회 거래당 리스크 비율 (계좌 대비)", min_value=0.001, max_value=0.10, value=float(display_settings.get("risk_per_trade", 0.01)), step=0.005)
        with c_v2:
            f_atr_stop_mult = st.number_input("포지션 사이징 ATR 손절 배수", min_value=1.0, max_value=5.0, value=float(display_settings.get("atr_stop_multiple", 2.2)), step=0.5)
            f_max_pos_ratio = st.number_input("1종목당 최대 포지션 비율", min_value=0.05, max_value=1.0, value=float(display_settings.get("max_position_ratio", 0.3)), step=0.05)
        st.caption("변동성(ATR)이 큰 고변동성 종목은 매수 수량을 줄이고, 저변동성 종목은 늘려 종목당 손실 위험 금액을 균등화합니다.")

        st.divider()
        st.write("**🎯 스크리닝 점수 카테고리별 상한 (Score Cap)**")
        c_s1, c_s2, c_s3 = st.columns(3)
        with c_s1:
            f_cap_trend = st.number_input("추세군(이동평균) 최대 점수", min_value=10, max_value=60, value=int(display_settings.get("score_cap_trend", 40)), step=5)
        with c_s2:
            f_cap_mom = st.number_input("모멘텀군(RSI, 볼린저) 최대 점수", min_value=10, max_value=50, value=int(display_settings.get("score_cap_momentum", 30)), step=5)
        with c_s3:
            f_cap_vol = st.number_input("거래량군 최대 점수", min_value=10, max_value=50, value=int(display_settings.get("score_cap_volume", 25)), step=5)
        st.caption("특정 한 가지 지표만으로 점수가 과도하게 높아지는 현상을 방지하기 위해 카테고리별 점수 상한을 제한합니다.")

        st.divider()
        st.write("**🕯️ 15:15 종가 스크리닝 실시간 봉 옵션**")
        f_realtime_candle = st.toggle("실시간 현재가를 일봉에 반영 (True: 실시간 15:15 캔들 합성, False: 전일 완성봉)", value=display_settings.get("use_realtime_candle", False))
        st.caption("15:15 시점에 당일 형성 중인 실시간 현재가/거래량을 일봉의 마지막 봉으로 합성하여 평가할지 결정합니다.")

        st.divider()
        st.write("**📈 분할 매도 및 트레일링 스탑 상세 설정**")
        c_m1, c_m2 = st.columns(2)
        with c_m1:
            f_partial_ratio = st.number_input("1차 익절 시 매도 비율 (0.5 = 50%)", min_value=0.1, max_value=1.0, value=float(display_settings.get("partial_sell_ratio", 0.5)), step=0.1)
            f_trailing_pct = st.number_input("1차 익절 후 최고가 대비 트레일링 스탑 비율 (예: 0.06 = 6.0%)", min_value=0.01, max_value=0.20, value=float(display_settings.get("trailing_stop_pct", 0.06)), step=0.005)
        with c_m2:
            f_max_holdings = st.number_input("최대 동시 보유 종목 수", min_value=1, max_value=30, value=int(display_settings.get("max_holding_stocks", 5)), step=1)
            f_rsi_overbought_sell = st.toggle("RSI 75 초과 시 전량 매도 (체크 해제 시 50% 분할 매도)", value=display_settings.get("rsi_overbought_sell", False))
        st.caption("1차 익절 달성 시 설정한 비율만큼 먼저 차익을 실현하고, 잔여 수량은 20일선 또는 최고가 대비 설정 비율 하락 시까지 수익을 극대화합니다.")

        save_btn = st.form_submit_button("💾 설정 저장하기 (Save Settings)", use_container_width=True)
        if save_btn:
            new_settings = {
                "mock_trading": f_mock,
                "regime_preset_mode": selected_mode_key,
                "telegram_enabled": f_telegram,
                "target_profit_rate": f_profit,
                "stop_loss_rate": f_loss,
                "max_buy_budget_per_stock": f_budget,
                "premarket_time": f_time,
                "max_holding_stocks": f_max_holdings,
                "score_cap_trend": f_cap_trend,
                "score_cap_momentum": f_cap_mom,
                "score_cap_volume": f_cap_vol,
                "use_realtime_candle": f_realtime_candle,
                "partial_sell_ratio": f_partial_ratio,
                "trailing_stop_pct": f_trailing_pct,
                "rsi_overbought_sell": f_rsi_overbought_sell,
                "time_stop_enabled": f_time_stop_enabled,
                "time_stop_days": f_time_stop_days,
                "time_stop_min_profit": f_time_stop_min_profit,
                "max_daily_buy_count": f_max_daily_buy,
                "volatility_sizing_enabled": f_vol_sizing_enabled,
                "risk_per_trade": f_risk_per_trade,
                "atr_stop_multiple": f_atr_stop_mult,
                "max_position_ratio": f_max_pos_ratio,
                "market_regime_filter_enabled": f_regime_enabled,
                "market_regime_cutoff_normal": f_regime_cutoff_normal,
                "market_regime_cutoff_weak": f_regime_cutoff_weak,
                "market_regime_block_weak": f_regime_block,
                "cooldown_enabled": f_cooldown_enabled,
                "cooldown_days": f_cooldown_days,
                "atr_stop_loss_enabled": f_atr_stop_enabled,
                "atr_stop_loss_multiple": f_atr_stop_multiple,
                "atr_stop_loss_min_pct": f_atr_stop_min_pct,
                "atr_stop_loss_max_pct": f_atr_stop_max_pct
            }
            if config.save_settings(new_settings):
                st.success(f"✅ 전략 및 시스템 설정이 성공적으로 저장되었습니다! (운영 모드: {preset_options[selected_mode_key]})")
                time.sleep(0.8)
                st.rerun()
            else:
                st.error("❌ 설정 저장에 실패했습니다.")

    # -------------------------------------------------------------
    # [하단: 관심종목(Watchlist) 관리]
    # -------------------------------------------------------------
    st.divider()
    st.markdown("### 📋 관심종목 유니버스 (Watchlist)")
    
    current_wl = config.CURRENT_SETTINGS.get("watchlist", [])
    st.write(f"현재 등록된 종목 수: **{len(current_wl)}개**")

    cols = st.columns(4)
    for idx, item in enumerate(current_wl):
        col = cols[idx % 4]
        with col:
            st.markdown(
                f"<div style='background:#1e293b; padding:8px 12px; border-radius:6px; margin-bottom:6px; border:1px solid #334155;'>"
                f"<strong style='color:#38bdf8;'>{item.get('name')}</strong> "
                f"<span style='color:#94a3b8; font-size:0.85em;'>({item.get('code')})</span>"
                f"<span style='float:right; font-size:0.75em; color:#cbd5e1; background:#0f172a; padding:2px 6px; border-radius:4px;'>{item.get('market', 'KOSPI')}</span>"
                f"</div>",
                unsafe_allow_html=True
            )
