"""
KIS Auto Trading - Settings View
전략 파라미터 및 관심종목(Watchlist) 관리 뷰
"""
import time
import streamlit as st
import config

def render_settings():
    """7. 전략 및 시스템 설정 페이지"""
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
