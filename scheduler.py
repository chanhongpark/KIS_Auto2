"""
Scheduler Module
매일 개장 전(08:30 KST) 자동 스크리닝 및 제안서 갱신 백그라운드 태스크
APScheduler 및 Python 표준 threading Fallback 지원
"""
import os
import sys
import time
import logging
import datetime
import threading

import config
from screener import StockScreener
from time_utils import now

logger = logging.getLogger("Scheduler")

_scheduler = None
_thread_running = False
_worker_thread = None

def job_premarket_screening():
    """개장 전 실행되는 정기 스크리닝 작업"""
    logger.info(f"[정기 스케줄 실행] {now()} 개장 전 종목 스크리닝 시작")
    try:
        screener = StockScreener()
        proposals = screener.run_premarket_screening()
        logger.info(f"[정기 스케줄 완료] 매수 추천 {len(proposals.get('buy_proposals', []))}건, 매도 추천 {len(proposals.get('sell_proposals', []))}건")
    except Exception as e:
        logger.error(f"[정기 스케줄 에러] 스크리닝 실행 실패: {e}")

class SimpleFallbackScheduler:
    def __init__(self):
        self.running = False
        self._thread = None

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("내장 스레드 스케줄러가 백그라운드에서 동작합니다.")

    def shutdown(self, wait=False):
        self.running = False

    def _loop(self):
        last_run_day = None
        while self.running:
            now_dt = now()
            time_str = config.CURRENT_SETTINGS.get("premarket_time", "08:30")
            try:
                target_h, target_m = map(int, time_str.split(":"))
            except Exception:
                target_h, target_m = 8, 30

            # 월~금(0~4) 개장 전 시간 체크
            if now_dt.weekday() < 5:
                if (now_dt.hour == target_h and now_dt.minute == target_m) and last_run_day != now_dt.date():
                    last_run_day = now_dt.date()
                    job_premarket_screening()
            time.sleep(30)

def start_scheduler():
    """백그라운드 스케줄러 시작 (APScheduler 또는 내장 스케줄러 사용)"""
    global _scheduler
    if _scheduler is not None and getattr(_scheduler, "running", False):
        logger.info("스케줄러가 이미 실행 중입니다.")
        return _scheduler

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        _scheduler = BackgroundScheduler(timezone="Asia/Seoul")
        time_str = config.CURRENT_SETTINGS.get("premarket_time", "08:30")
        try:
            hour, minute = map(int, time_str.split(":"))
        except Exception:
            hour, minute = 8, 30

        trigger = CronTrigger(
            day_of_week="mon-fri",
            hour=hour,
            minute=minute,
            timezone="Asia/Seoul"
        )
        _scheduler.add_job(job_premarket_screening, trigger, id="premarket_screening", replace_existing=True)
        _scheduler.start()
        logger.info(f"APScheduler 시작됨: 매주 월~금 {hour:02d}:{minute:02d} KST 실행 예정")
    except ImportError:
        logger.warning("APScheduler 미설치로 내장 Fallback 스케줄러를 구동합니다.")
        _scheduler = SimpleFallbackScheduler()
        _scheduler.start()

    return _scheduler

def stop_scheduler():
    """스케줄러 중지"""
    global _scheduler
    if _scheduler and getattr(_scheduler, "running", False):
        _scheduler.shutdown(wait=False)
        logger.info("스케줄러 중지됨")

if __name__ == "__main__":
    print("Starting standalone scheduler runner...")
    job_premarket_screening()
    s = start_scheduler()
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        stop_scheduler()
