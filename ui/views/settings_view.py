"""
KIS Auto Trading - Settings View
전략 파라미터, 시장 국면 프리셋(BULL/VOLATILE/BEAR/AUTO) 및 관심종목(Watchlist) 관리 뷰
프리셋 변경 시 폼 입력값 실시간 동기화 지원
전략별 설정 스키마(settings_schema) 기반 동적 폼 렌더링
"""
import time
from typing import Dict, Any, List
import streamlit as st
import config
from core.strategy import list_strategies, get_strategy_settings_schema, get_strategy_specific_settings_keys


def _render_schema_item(
    item: Dict[str, Any],
    current_value: Any,
    key_prefix: str = ""
) -> Any:
    """
    설정 스키마 항목을 Streamlit 위젯으로 렌더링하고 사용자 입력값 반환.
    """
    key = item["key"]
    label = item.get("label", key)
    desc = item.get("description", "")
    item_type = item.get("type", "number")
    widget_key = f"{key_prefix}_{key}"

    if item_type == "toggle":
        val = st.toggle(label, value=bool(current_value), key=widget_key)
        if desc:
            st.caption(desc)
        return val

    elif item_type == "number":
        min_v = item.get("min")
        max_v = item.get("max")
        step = item.get("step", 1)

        # Streamlit number_input는 value/min_value/max_value/step이 모두 동일 타입이어야 함
        # 정수형 설정이면 int로, 실수형 설정이면 float로 통일
        default_val = item.get("default", 0)
        current_val = current_value if current_value is not None else default_val

        # 정수형 판단: default가 int이고 step이 int이면 정수형으로 처리
        is_int_type = isinstance(default_val, int) and isinstance(step, int) and not isinstance(default_val, bool)

        if is_int_type:
            val = st.number_input(
                label,
                min_value=int(min_v) if min_v is not None else None,
                max_value=int(max_v) if max_v is not None else None,
                value=int(current_val),
                step=int(step),
                key=widget_key
            )
        else:
            val = st.number_input(
                label,
                min_value=float(min_v) if min_v is not None else None,
                max_value=float(max_v) if max_v is not None else None,
                value=float(current_val),
                step=float(step),
                key=widget_key
            )
        if desc:
            st.caption(desc)
        return val

    elif item_type == "text":
        val = st.text_input(label, value=str(current_value) if current_value is not None else str(item.get("default", "")), key=widget_key)
        if desc:
            st.caption(desc)
        return val

    elif item_type == "select":
        options = item.get("options", [])
        option_values = [o[0] for o in options]
        option_labels = [o[1] for o in options]
        current_idx = option_values.index(current_value) if current_value in option_values else 0
        val = st.selectbox(
            label,
            options=option_values,
            format_func=lambda x: option_labels[option_values.index(x)] if x in option_values else x,
            index=current_idx,
            key=widget_key
        )
        if desc:
            st.caption(desc)
        return val

    return current_value


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
        st.write("**🧩 매수/매도 전략 선택 (Strategy Plugin)**")
        strategies = list_strategies()
        strategy_options = {s["name"]: f"{s['display_name']} - {s.get('description', '')}" for s in strategies}
        current_strategy = display_settings.get("strategy_name", "momentum")
        if current_strategy not in strategy_options:
            current_strategy = strategies[0]["name"] if strategies else "momentum"
        f_strategy = st.selectbox(
            "전략 선택 (플러그인 전략)",
            options=list(strategy_options.keys()),
            format_func=lambda x: strategy_options.get(x, x),
            index=list(strategy_options.keys()).index(current_strategy) if current_strategy in strategy_options else 0
        )
        st.caption("매수/매도 신호를 생성하는 전략 알고리즘을 선택합니다. 전략별로 서로 다른 매수/매도 규칙과 설정 항목이 적용됩니다.")
        st.divider()

        # =============================================================
        # 전략별 설정 스키마 기반 동적 폼 렌더링
        # =============================================================
        schema = get_strategy_settings_schema(f_strategy)
        strategy_specific_keys = get_strategy_specific_settings_keys(f_strategy)

        # 전략별 고유 설정 값 로드 (저장된 값 또는 스키마 기본값)
        saved_strategy_settings = config.get_strategy_settings(f_strategy)
        # 전략 고유 설정만 병합 (공통 설정은 프리셋/전역 설정에서 관리)
        strategy_display = display_settings.copy()
        for k, v in saved_strategy_settings.items():
            if k in strategy_specific_keys:
                strategy_display[k] = v

        # 공통 설정 (category='common') - 시장 국면 프리셋에서 관리
        common_items = [item for item in schema if item.get("category", "common") == "common"]
        # 전략 고유 설정 (category='strategy') - 전략별로 독립 저장
        strategy_items = [item for item in schema if item.get("category", "common") == "strategy"]

        # --- 공통 설정 렌더링 ---
        if common_items:
            st.write("**📋 공통 설정 (Common Settings)**")
            st.caption("모든 전략이 공유하는 공통 파라미터입니다. 시장 국면 프리셋(BULL/VOLATILE/BEAR)에 따라 자동 조정됩니다.")

            # 공통 설정을 카테고리별로 그룹화하여 표시
            common_groups = {
                "익절/손절": ["target_profit_rate", "stop_loss_rate", "trailing_stop_pct", "partial_sell_ratio", "rsi_overbought_sell"],
                "타임컷": ["time_stop_enabled", "time_stop_days", "time_stop_min_profit"],
                "시장 국면 필터": ["market_regime_filter_enabled", "market_regime_cutoff_normal", "market_regime_cutoff_weak", "market_regime_block_weak"],
                "쿨다운": ["cooldown_enabled", "cooldown_days"],
                "ATR 동적 손절": ["atr_stop_loss_enabled", "atr_stop_loss_multiple", "atr_stop_loss_min_pct", "atr_stop_loss_max_pct", "atr_stop_loss_use_low_break"],
                "포지션 사이징": ["volatility_sizing_enabled", "risk_per_trade", "atr_stop_multiple", "max_position_ratio", "min_position_ratio"],
                "스크리닝 점수": ["score_cap_trend", "score_cap_momentum", "score_cap_volume", "buy_score_threshold"],
                "매수 제한": ["max_daily_buy_count", "max_buy_budget_per_stock", "max_holding_stocks"],
                "기타": ["use_realtime_candle"]
            }

            common_values: Dict[str, Any] = {}
            for group_name, group_keys in common_groups.items():
                group_items = [item for item in common_items if item["key"] in group_keys]
                if not group_items:
                    continue
                st.markdown(f"**{group_name}**")
                cols = st.columns(2)
                for i, item in enumerate(group_items):
                    col = cols[i % 2]
                    with col:
                        key = item["key"]
                        current_val = strategy_display.get(key, item.get("default"))
                        # selected_mode_key를 키에 포함하여 프리셋 변경 시 위젯이 새로 생성되도록 함
                        common_values[key] = _render_schema_item(item, current_val, key_prefix=f"common_{f_strategy}_{selected_mode_key}")
                st.divider()

        # --- 전략 고유 설정 렌더링 ---
        if strategy_items:
            st.write(f"**🎯 {strategy_options.get(f_strategy, f_strategy)} 전략 고유 설정 (Strategy-specific Settings)**")
            st.caption("이 전략만의 고유 파라미터입니다. 전략별로 독립적으로 저장되며, 다른 전략으로 전환해도 유지됩니다.")

            strategy_values: Dict[str, Any] = {}
            cols = st.columns(2)
            for i, item in enumerate(strategy_items):
                col = cols[i % 2]
                with col:
                    key = item["key"]
                    current_val = strategy_display.get(key, item.get("default"))
                    # selected_mode_key를 키에 포함하여 프리셋 변경 시 위젯이 새로 생성되도록 함
                    strategy_values[key] = _render_schema_item(item, current_val, key_prefix=f"strategy_{f_strategy}_{selected_mode_key}")
            st.divider()

        # --- 시스템 설정 (전략과 무관한 전역 설정) ---
        st.write("**⚙️ 시스템 설정 (System Settings)**")
        f_mock = st.toggle("모의투자 모드 활성화 (체크 해제 시 실전투자)", value=display_settings.get("mock_trading", True))
        f_telegram = st.toggle("텔레그램 알림 활성화 (기본: OFF)", value=display_settings.get("telegram_enabled", False))
        if f_telegram:
            st.caption("⚠️ 텔레그램 알림을 활성화하면 매수/매도 이벤트가 텔레그램으로 전송됩니다. api.telegram.org에 접속 가능해야 합니다.")
        else:
            st.caption("텔레그램 알림이 꺼져 있습니다. 켜려면 위 토글을 활성화하세요.")
        f_time = st.text_input(
            "종가 매수 스크리닝 시각 (KST)",
            value=display_settings.get("premarket_time", "15:15")
        )
        st.divider()

        save_btn = st.form_submit_button("💾 설정 저장하기 (Save Settings)", width="stretch")
        if save_btn:
            # 1. 전역 설정 저장 (공통 설정 + 시스템 설정)
            global_settings = {
                "mock_trading": f_mock,
                "regime_preset_mode": selected_mode_key,
                "strategy_name": f_strategy,
                "telegram_enabled": f_telegram,
                "premarket_time": f_time,
            }

            # 공통 설정 값을 전역 설정에 병합
            if common_items:
                for item in common_items:
                    key = item["key"]
                    if key in common_values:
                        global_settings[key] = common_values[key]

            # 2. 전략별 고유 설정 저장
            strategy_specific_settings: Dict[str, Any] = {}
            if strategy_items:
                for item in strategy_items:
                    key = item["key"]
                    if key in strategy_values:
                        strategy_specific_settings[key] = strategy_values[key]

            # 3. 저장
            ok = config.save_strategy_settings(
                strategy_name=f_strategy,
                strategy_settings=strategy_specific_settings,
                global_settings=global_settings
            )

            if ok:
                st.success(f"✅ 전략 및 시스템 설정이 성공적으로 저장되었습니다! (운영 모드: {preset_options[selected_mode_key]}, 전략: {strategy_options.get(f_strategy, f_strategy)})")
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
