"""
KIS Auto Trading - Backtest View
FinanceDataReader 기반 과거 데이터 시뮬레이션 및 수익률 분석 뷰
"""
import time
import datetime
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from time_utils import today
from backtester import Backtester
import config

def render_backtest():
    """4. 백테스팅 페이지 (FinanceDataReader)"""
    st.title("🧪 Backtest • 알고리즘 백테스팅")
    st.caption("FinanceDataReader를 활용하여 구현된 종가 매수(15:15) 및 리스크 관리 전략을 과거 데이터로 검증합니다.")

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

            st.write("### 📈 포트폴리오 수익률 곡선 (Equity Curve vs KOSPI)")
            
            fig_bt = make_subplots(
                rows=2, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.06,
                row_heights=[0.7, 0.3],
                subplot_titles=("포트폴리오 누적 수익률 vs KOSPI 벤치마크", "Drawdown (낙폭)")
            )

            fig_bt.add_trace(
                go.Scatter(
                    x=pd.to_datetime(daily_eq["date"]),
                    y=daily_eq["return_pct"],
                    name="전략 포트폴리오",
                    line=dict(color="#38bdf8", width=2.5)
                ),
                row=1, col=1
            )

            if bench_df is not None and not bench_df.empty:
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

            st.divider()
            st.subheader(f"📋 백테스트 매매 상세 내역 (총 {len(trades_df)}건)")
            if not trades_df.empty:
                disp_trades = trades_df.copy()
                disp_trades["price"] = disp_trades["price"].apply(lambda x: f"{x:,.0f}원")
                disp_trades["amount"] = disp_trades["amount"].apply(lambda x: f"{x:,.0f}원")
                disp_trades["profit_krw"] = disp_trades["profit_krw"].apply(lambda x: f"{x:+,.0f}원" if x != 0 else "-")
                disp_trades["profit_pct"] = disp_trades["profit_pct"].apply(lambda x: f"{x:+.2f}%" if x != 0 else "-")

                st.dataframe(disp_trades, use_container_width=True)

                csv_data = trades_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📥 매매 내역 CSV 다운로드",
                    data=csv_data,
                    file_name=f"backtest_trades_{params.get('start')}_{params.get('end')}.csv",
                    mime="text/csv"
                )
            else:
                st.info("백테스트 기간 내 발생한 매매 내역이 없습니다.")
