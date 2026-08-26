"""
Telegram Notification Module
매수 성공 및 매도 추천 알림을 텔레그램 봇으로 전송
"""
import os
import logging
import requests
from typing import Optional, Dict, Any, List

import config

logger = logging.getLogger("TelegramNotifier")


class TelegramNotifier:
    """텔레그램 봇을 통한 주문/신호 알림 전송 클래스"""

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or config.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or config.TELEGRAM_CHAT_ID
        self.api_base = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None

    @property
    def is_enabled(self) -> bool:
        """봇 토큰과 채팅 ID가 모두 설정되었는지 확인"""
        return bool(self.bot_token and self.chat_id)

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        텔레그램 메시지 전송

        Args:
            text: 전송할 메시지 본문
            parse_mode: HTML 또는 Markdown (기본: HTML)

        Returns:
            bool: 전송 성공 여부
        """
        # 설정에서 텔레그램 알림 활성화 여부 확인
        if not config.get_setting("telegram_enabled", False):
            logger.info("텔레그램 알림이 비활성화되어 있습니다. (설정 > 텔레그램 알림 활성화 필요)")
            return False

        if not self.is_enabled:
            logger.warning("텔레그램 봇 토큰 또는 채팅 ID가 설정되지 않아 알림을 전송하지 않습니다.")
            return False

        if not text:
            return False

        # 텔레그램 메시지 최대 길이 (4096자) 제한
        if len(text) > 4000:
            text = text[:4000] + "\n\n... (메시지가 길어 일부만 표시됩니다)"

        url = f"{self.api_base}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()
            if resp.status_code == 200 and data.get("ok"):
                logger.info("텔레그램 알림 전송 성공")
                return True
            else:
                logger.error(f"텔레그램 알림 전송 실패: HTTP {resp.status_code} - {data.get('description', '알 수 없는 오류')}")
                return False
        except requests.exceptions.SSLError as e:
            logger.error(f"텔레그램 SSL 인증 오류: {e}")
            return False
        except requests.exceptions.ConnectionError as e:
            logger.error(f"텔레그램 연결 실패: {e}")
            return False
        except Exception as e:
            logger.error(f"텔레그램 알림 전송 중 예외 발생: {e}")
            return False

    def send_buy_success(
        self,
        name: str,
        code: str,
        qty: int,
        price: float,
        order_no: str = "",
        order_type: str = "시장가"
    ) -> bool:
        """매수 주문 성공 알림 전송"""
        total_amount = qty * price
        text = (
            "🟢 <b>종가 매수 주문 성공</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>종목:</b> {name} ({code})\n"
            f"🔢 <b>수량:</b> {qty:,}주\n"
            f"💰 <b>주문가:</b> {price:,.0f}원\n"
            f"💵 <b>총 주문액:</b> {total_amount:,.0f}원\n"
            f"📋 <b>주문 유형:</b> {order_type}\n"
        )
        if order_no:
            text += f"🆔 <b>주문 번호:</b> {order_no}\n"
        text += "━━━━━━━━━━━━━━━━━━\n"
        text += f"⏰ {self._now_str()}"

        return self.send_message(text)

    def send_sell_recommendation(
        self,
        name: str,
        code: str,
        holding_qty: int,
        avg_buy_price: float,
        current_price: float,
        profit_rate: float,
        profit_loss: float,
        reasons: List[str],
        is_urgent: bool = False
    ) -> bool:
        """매도 추천 알림 전송"""
        icon = "🚨" if is_urgent else "⚠️"
        title = "긴급 손절 알림" if is_urgent else "매도 추천 신호"
        text = (
            f"{icon} <b>{title}</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>종목:</b> {name} ({code})\n"
            f"📦 <b>보유 수량:</b> {holding_qty:,}주\n"
            f"💹 <b>평균 매입가:</b> {avg_buy_price:,.0f}원\n"
            f"📊 <b>현재가:</b> {current_price:,.0f}원\n"
            f"📈 <b>수익률:</b> {profit_rate:+.2f}%\n"
            f"💵 <b>평가 손익:</b> {profit_loss:+,.0f}원\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📝 <b>매도 사유:</b>\n"
        )
        for reason in reasons:
            text += f"• {reason}\n"
        text += "━━━━━━━━━━━━━━━━━━\n"
        text += f"⏰ {self._now_str()}"

        return self.send_message(text)

    def send_sell_success(
        self,
        name: str,
        code: str,
        qty: int,
        price: float,
        order_no: str = "",
        order_type: str = "시장가"
    ) -> bool:
        """매도 주문 성공 알림 전송"""
        total_amount = qty * price
        text = (
            "🔴 <b>매도 주문 성공</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>종목:</b> {name} ({code})\n"
            f"🔢 <b>수량:</b> {qty:,}주\n"
            f"💰 <b>주문가:</b> {price:,.0f}원\n"
            f"💵 <b>총 매도액:</b> {total_amount:,.0f}원\n"
            f"📋 <b>주문 유형:</b> {order_type}\n"
        )
        if order_no:
            text += f"🆔 <b>주문 번호:</b> {order_no}\n"
        text += "━━━━━━━━━━━━━━━━━━\n"
        text += f"⏰ {self._now_str()}"

        return self.send_message(text)

    def send_daily_summary(
        self,
        buy_count: int,
        sell_count: int,
        holdings_count: int,
        buy_list: Optional[List[Dict[str, Any]]] = None,
        sell_list: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """일일 스크리닝 요약 알림 전송 (15:15 종가 매수 및 매도 현황)"""
        text = (
            "📊 <b>15:15 종가 스크리닝 요약</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"🟢 <b>종가 매수 추천:</b> {buy_count}건\n"
            f"🔴 <b>매도 신호 감지:</b> {sell_count}건\n"
            f"📦 <b>현재 보유 종목:</b> {holdings_count}개\n"
        )

        if buy_list:
            text += "\n<b>🟢 종가 매수 추천 종목:</b>\n"
            for item in buy_list[:5]:
                buy_tag = "🔄 추가매수" if item.get("is_additional_buy") else "🆕 신규매수"
                score = item.get("score", 0)
                t_score = item.get("trend_score", 0)
                s_score = item.get("supply_score", 0)
                m_score = item.get("momentum_score", 0)
                text += (
                    f"• {buy_tag} <b>{item.get('name', '')}</b> ({item.get('code', '')})\n"
                    f"  💰 {item.get('current_price', 0):,.0f}원 | 🎯 총 {score}점 (추세 {t_score}/수급 {s_score}/모멘텀 {m_score})\n"
                )

        if sell_list:
            text += "\n<b>🔴 매도 추천 종목:</b>\n"
            for item in sell_list[:5]:
                urgent_tag = "🚨 [긴급]" if item.get("is_urgent") else "⚠️"
                sell_type = item.get("sell_type", "매도")
                text += (
                    f"• {urgent_tag} <b>{item.get('name', '')}</b> ({item.get('code', '')}) "
                    f"| {sell_type} | 수익률 {item.get('profit_rate', 0):+.2f}%\n"
                )

        text += "━━━━━━━━━━━━━━━━━━\n"
        text += f"⏰ {self._now_str()}"

        return self.send_message(text)

    def send_test_message(self) -> bool:
        """테스트 메시지 전송 (연결 확인용)"""
        text = (
            "✅ <b>텔레그램 알림 테스트</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "KIS Auto Trader 시스템에서 보낸 테스트 메시지입니다.\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"⏰ {self._now_str()}"
        )
        return self.send_message(text)

    @staticmethod
    def _now_str() -> str:
        """현재 시각 문자열 반환 (KST)"""
        from time_utils import now_str
        return now_str()


# 모듈 레벨 싱글톤 인스턴스
notifier = TelegramNotifier()