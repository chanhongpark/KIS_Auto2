"""
KIS API Client Module
한국투자증권 Open API (국내주식 시세, 계좌 잔고, 매수/매도 주문)
HTTP Session 커넥션 풀링(Keep-Alive) 및 전역 동기화 Rate Limiter 적용
"""
import os
import time
import logging
import datetime
import threading
from typing import Dict, Any, List, Optional
import requests
from requests.adapters import HTTPAdapter

import config
from time_utils import now, today
from core.storage import safe_load_json, atomic_save_json
from core.exceptions import KISApiError, KISAuthError, KISRateLimitError, KISOrderError

class _GlobalRateLimiter:
    """모든 KISApiClient 인스턴스가 공유하는 전역 초당 호출 제한기"""
    def __init__(self, delay: float = 0.15):
        self.delay = delay
        self._last_call_time = 0.0
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            elapsed = time.time() - self._last_call_time
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
            self._last_call_time = time.time()

_rate_limiter = _GlobalRateLimiter(0.15)


class KISApiClient:
    _shared_session: Optional[requests.Session] = None
    _session_lock = threading.Lock()

    def __init__(self):
        self.logger = logging.getLogger("KISApi")
        self.app_key = config.APP_KEY
        self.app_secret = config.APP_SECRET
        self.cano = config.CANO
        self.acnt_prdt_cd = config.ACNT_PRDT_CD
        self.account_pwd = config.ACCOUNT_PWD

        self.access_token: Optional[str] = None
        self.token_expired_at: Optional[datetime.datetime] = None
        self._token_lock = threading.RLock()

        # 토큰 파일 로드
        self._load_token_file()

    @classmethod
    def get_session(cls) -> requests.Session:
        """연결 재사용을 위한 싱글톤 requests.Session 반환"""
        with cls._session_lock:
            if cls._shared_session is None:
                s = requests.Session()
                adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=0)
                s.mount("https://", adapter)
                s.mount("http://", adapter)
                cls._shared_session = s
            return cls._shared_session

    @property
    def is_mock(self) -> bool:
        return config.CURRENT_SETTINGS.get("mock_trading", True)

    @property
    def url_base(self) -> str:
        return config.URL_BASE_MOCK if self.is_mock else config.URL_BASE_REAL

    @property
    def token_file(self) -> str:
        prefix = "token_kis_mock.json" if self.is_mock else "token_kis_real.json"
        return os.path.join(os.path.dirname(__file__), prefix)

    def _rate_limit(self):
        _rate_limiter.wait()

    def _request_with_retry(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
        timeout: float = 8.0
    ) -> requests.Response:
        """429 Too Many Requests 및 일시적 네트워크 장애에 대한 지수 백오프 재시도 요청"""
        session = self.get_session()
        last_resp = None

        for attempt in range(1, max_retries + 1):
            self._rate_limit()
            try:
                conn_timeout = min(timeout, 3.0)
                read_timeout = timeout
                if method.upper() == "GET":
                    resp = session.get(url, headers=headers, params=params, timeout=(conn_timeout, read_timeout))
                else:
                    resp = session.post(url, headers=headers, json=json_data, timeout=(conn_timeout, read_timeout))

                if resp.status_code == 200:
                    return resp

                last_resp = resp
                if resp.status_code in (429, 500, 502, 503, 504):
                    wait_sec = attempt * 0.5
                    self.logger.warning(f"[{method}] {url} HTTP {resp.status_code} 감지 - {wait_sec:.1f}초 후 재시도 ({attempt}/{max_retries})")
                    time.sleep(wait_sec)
                else:
                    return resp
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                wait_sec = attempt * 0.5
                self.logger.warning(f"[{method}] {url} 통신 예외 ({e}) - {wait_sec:.1f}초 후 재시도 ({attempt}/{max_retries})")
                time.sleep(wait_sec)
            except Exception as e:
                self.logger.error(f"[{method}] {url} 요청 중 예외: {e}")
                raise KISApiError(f"HTTP 요청 예외: {e}")

        return last_resp if last_resp is not None else requests.Response()

    def _load_token_file(self):
        with self._token_lock:
            data = safe_load_json(self.token_file, default={})
            if data:
                self.access_token = data.get("access_token")
                exp_str = data.get("token_expired_at")
                if exp_str:
                    try:
                        self.token_expired_at = datetime.datetime.fromisoformat(exp_str)
                        if self.token_expired_at.tzinfo is None:
                            self.token_expired_at = self.token_expired_at.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=9)))
                    except Exception:
                        self.token_expired_at = None

    def _save_token_file(self):
        with self._token_lock:
            data = {
                "access_token": self.access_token,
                "token_expired_at": self.token_expired_at.isoformat() if self.token_expired_at else ""
            }
            atomic_save_json(self.token_file, data)

    def is_token_valid(self) -> bool:
        if not self.access_token or not self.token_expired_at:
            return False
        return now() < (self.token_expired_at - datetime.timedelta(minutes=10))

    def get_access_token(self) -> bool:
        """OAuth2 Access Token 발급"""
        if self.is_token_valid():
            return True

        with self._token_lock:
            if self.is_token_valid():
                return True

            url = f"{self.url_base}/oauth2/tokenP"
            body = {
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret
            }
            headers = {"content-type": "application/json; charset=utf-8"}

            try:
                self._rate_limit()
                session = self.get_session()
                res = session.post(url, headers=headers, json=body, timeout=(3, 5))
                if res.status_code == 200:
                    data = res.json()
                    self.access_token = data.get("access_token")
                    expires_in = int(data.get("expires_in", 86400))
                    self.token_expired_at = now() + datetime.timedelta(seconds=expires_in)
                    self._save_token_file()
                    self.logger.info(f"[{'모의' if self.is_mock else '실전'}] 토큰 발급 성공 (만료: {self.token_expired_at})")
                    return True
                else:
                    self.logger.error(f"토큰 발급 실패 ({res.status_code}): {res.text}")
                    return False
            except requests.exceptions.ConnectTimeout:
                self.logger.error(f"토큰 발급 연결 타임아웃: {url} (네트워크 연결 불가)")
                return False
            except requests.exceptions.ReadTimeout:
                self.logger.error(f"토큰 발급 응답 타임아웃: {url} (API 서버 응답 없음)")
                return False
            except requests.exceptions.ConnectionError as e:
                self.logger.error(f"토큰 발급 연결 실패: {url} - {e}")
                return False
            except Exception as e:
                self.logger.error(f"토큰 발급 요청 예외: {e}")
                return False

    def _ensure_token(self):
        if not self.is_token_valid():
            self.get_access_token()

    def _get_headers(self, tr_id: str, hashkey: Optional[str] = None) -> Dict[str, str]:
        self._ensure_token()
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P"
        }
        if hashkey:
            headers["hashkey"] = hashkey
        return headers

    def get_hashkey(self, body: Dict[str, Any]) -> Optional[str]:
        """주문용 HashKey 생성"""
        url = f"{self.url_base}/uapi/hashkey"
        headers = {
            "content-type": "application/json; charset=utf-8",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        try:
            self._rate_limit()
            session = self.get_session()
            res = session.post(url, headers=headers, json=body, timeout=(3, 5))
            if res.status_code == 200:
                return res.json().get("HASH")
        except Exception as e:
            self.logger.warning(f"Hashkey 생성 실패: {e}")
        return None

    def get_stock_price(self, stock_code: str) -> Dict[str, Any]:
        """국내 주식 현재가 시세 조회"""
        url = f"{self.url_base}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = self._get_headers("FHKST01010100")
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code
        }
        try:
            res = self._request_with_retry("GET", url, headers=headers, params=params, timeout=6)
            data = res.json()
            output = data.get("output", {})
            if output:
                return {
                    "rt_cd": data.get("rt_cd", "0"),
                    "msg1": data.get("msg1", ""),
                    "code": stock_code,
                    "price": float(output.get("stck_prpr", 0)),
                    "stck_prpr": float(output.get("stck_prpr", 0)),
                    "stck_oprc": float(output.get("stck_oprc", 0)),
                    "stck_hgpr": float(output.get("stck_hgpr", 0)),
                    "stck_lwpr": float(output.get("stck_lwpr", 0)),
                    "prdy_vrss": float(output.get("prdy_vrss", 0)),
                    "prdy_ctrt": float(output.get("prdy_ctrt", 0)),
                    "acml_vol": int(output.get("acml_vol", 0)),
                    "d250_hgpr": float(output.get("d250_hgpr", 0)),
                    "d250_hgpr_vrss_prpr_rate": float(output.get("d250_hgpr_vrss_prpr_rate", 0)),
                    "raw": output
                }
            return data
        except Exception as e:
            self.logger.error(f"[{stock_code}] 시세 조회 에러: {e}")
            return {"rt_cd": "-1", "msg1": str(e), "price": 0.0}

    def get_daily_chart(self, stock_code: str, period: str = "D", count: int = 60) -> List[Dict[str, Any]]:
        """일별 차트/시세 데이터 조회 (OHLCV)"""
        end_date = today().strftime("%Y%m%d")
        start_date = (today() - datetime.timedelta(days=count * 2)).strftime("%Y%m%d")

        url = f"{self.url_base}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        headers = self._get_headers("FHKST03010100")
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": period,
            "FID_ORG_ADJ_PRC": "0"
        }
        try:
            res = self._request_with_retry("GET", url, headers=headers, params=params, timeout=7)
            data = res.json()
            output2 = data.get("output2", [])
            results = []
            for item in output2[:count]:
                try:
                    results.append({
                        "date": item.get("stck_bsop_date"),
                        "close": float(item.get("stck_clpr", 0)),
                        "open": float(item.get("stck_oprc", 0)),
                        "high": float(item.get("stck_hgpr", 0)),
                        "low": float(item.get("stck_lwpr", 0)),
                        "volume": int(item.get("acml_vol", 0)),
                        "change_rate": float(item.get("prdy_ctrt", 0)) if "prdy_ctrt" in item else 0.0
                    })
                except (ValueError, TypeError):
                    continue
            results.reverse()
            return results
        except Exception as e:
            self.logger.error(f"[{stock_code}] 차트 조회 에러: {e}")
            return []

    def get_account_balance(self) -> Dict[str, Any]:
        """계좌 잔고 및 보유 종목 조회 (TTTC8434R / VTTC8434R)"""
        url = f"{self.url_base}/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = "VTTC8434R" if self.is_mock else "TTTC8434R"
        headers = self._get_headers(tr_id)
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        try:
            res = self._request_with_retry("GET", url, headers=headers, params=params, timeout=7)
            data = res.json()
            output1 = data.get("output1", [])
            output2 = data.get("output2", [{}])

            holdings = []
            for item in output1:
                qty = int(item.get("hldg_qty", 0))
                if qty > 0:
                    holdings.append({
                        "code": item.get("pdno"),
                        "name": item.get("prdt_name"),
                        "quantity": qty,
                        "available_qty": int(item.get("ord_psbl_qty", 0)),
                        "avg_buy_price": float(item.get("pchs_avg_pric", 0)),
                        "current_price": float(item.get("prpr", 0)),
                        "eval_amount": float(item.get("evlu_amt", 0)),
                        "profit_loss": float(item.get("evlu_pfls_amt", 0)),
                        "profit_rate": float(item.get("evlu_pfls_rt", 0)),
                    })

            summary = {}
            if output2:
                o2 = output2[0]
                stock_eval_amt = sum(h["eval_amount"] for h in holdings)
                summary = {
                    "tot_asset": float(o2.get("tot_evlu_amt", 0)),
                    "cash_balance": float(o2.get("dnca_tot_amt", 0)),
                    "stock_eval_amt": stock_eval_amt,
                    "total_profit_loss": float(o2.get("evlu_pfls_smtl_amt", 0)),
                    "net_asset": float(o2.get("nass_amt", 0))
                }
            elif holdings:
                stock_eval_amt = sum(h["eval_amount"] for h in holdings)
                total_profit_loss = sum(h["profit_loss"] for h in holdings)
                summary = {
                    "tot_asset": stock_eval_amt,
                    "cash_balance": 0,
                    "stock_eval_amt": stock_eval_amt,
                    "total_profit_loss": total_profit_loss,
                    "net_asset": stock_eval_amt
                }

            return {
                "rt_cd": data.get("rt_cd", "0"),
                "msg1": data.get("msg1", ""),
                "holdings": holdings,
                "summary": summary
            }
        except Exception as e:
            self.logger.error(f"계좌 잔고 조회 에러: {e}")
            return {
                "rt_cd": "-1",
                "msg1": str(e),
                "holdings": [],
                "summary": {"tot_asset": 0, "cash_balance": 0, "stock_eval_amt": 0, "total_profit_loss": 0, "net_asset": 0}
            }

    def order_cash(
        self,
        stock_code: str,
        qty: int,
        price: int = 0,
        buy_sell: str = "BUY",
        ord_dv: str = "01"
    ) -> Dict[str, Any]:
        """국내주식 현금 주문 (매수 / 매도)"""
        if qty <= 0:
            return {"rt_cd": "-1", "msg1": "주문 수량은 1주 이상이어야 합니다."}

        url = f"{self.url_base}/uapi/domestic-stock/v1/trading/order-cash"
        if buy_sell.upper() in ("BUY", "매수"):
            tr_id = "VTTC0012U" if self.is_mock else "TTTC0012U"
        else:
            tr_id = "VTTC0011U" if self.is_mock else "TTTC0011U"

        body = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "PDNO": stock_code,
            "ORD_DVSN": ord_dv,
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price) if ord_dv not in ("01", "00") and price > 0 else "0" if ord_dv == "01" else str(price)
        }

        try:
            headers = self._get_headers(tr_id, hashkey=self.get_hashkey(body))
            res = self._request_with_retry("POST", url, headers=headers, json_data=body, timeout=8)
            data = res.json()
            self.logger.info(f"주문 결과 [{buy_sell}] {stock_code} {qty}주 -> rt_cd={data.get('rt_cd')}, msg={data.get('msg1')}")
            return {
                "rt_cd": data.get("rt_cd", "0"),
                "msg1": data.get("msg1", ""),
                "order_no": data.get("output", {}).get("ODNO", ""),
                "raw": data
            }
        except Exception as e:
            self.logger.error(f"주문 전송 실패: {e}")
            return {"rt_cd": "-1", "msg1": str(e)}

    def order_stock(
        self,
        code: str,
        qty: int,
        buy_sell: str = "매수",
        order_type: str = "01",
        price: int = 0
    ) -> Dict[str, Any]:
        """order_cash의 친화적 래퍼 메서드"""
        action = "BUY" if buy_sell in ("매수", "BUY") else "SELL"
        return self.order_cash(
            stock_code=code,
            qty=qty,
            price=price,
            buy_sell=action,
            ord_dv=order_type
        )

    def get_order_history(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """주문 및 체결 내역 조회 (TTTC8001R / VTTC8001R)"""
        url = f"{self.url_base}/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
        tr_id = "VTTC8001R" if self.is_mock else "TTTC8001R"
        headers = self._get_headers(tr_id)
        start_str = start_date or today().strftime("%Y%m%d")
        end_str = end_date or today().strftime("%Y%m%d")
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "INQR_STRT_DT": start_str,
            "INQR_END_DT": end_str,
            "SLL_BUY_DVSN_CD": "00",
            "INQR_DVSN": "00",
            "PDNO": "",
            "CCLD_DVSN": "00",
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "INQR_DVSN_3": "00",
            "INQR_DVSN_1": "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
        try:
            res = self._request_with_retry("GET", url, headers=headers, params=params, timeout=7)
            data = res.json()
            output1 = data.get("output1", [])
            orders = []
            for item in output1:
                orders.append({
                    "order_no": item.get("odno"),
                    "code": item.get("pdno"),
                    "name": item.get("prdt_name"),
                    "buy_sell": "매수" if item.get("sll_buy_dvsn_cd") == "02" else "매도",
                    "order_qty": int(item.get("ord_qty", 0)),
                    "order_price": float(item.get("ord_unpr", 0)),
                    "ccld_qty": int(item.get("tot_ccld_qty", 0)),
                    "ccld_price": float(item.get("avg_prvs", 0)),
                    "order_time": item.get("ord_tmd"),
                    "order_date": item.get("ord_dt", ""),
                    "status": "체결완료" if int(item.get("ord_qty", 0)) == int(item.get("tot_ccld_qty", 0)) and int(item.get("ord_qty", 0)) > 0 else "미체결/부분체결"
                })
            return orders
        except Exception as e:
            self.logger.error(f"주문내역 조회 에러: {e}")
            return []

    def get_trade_history_with_profit(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        """매수/매도 이력 조회 및 실현 손익 계산 (FIFO 선입선출 매칭)"""
        orders = self.get_order_history(start_date, end_date)
        if not orders:
            return {
                "orders": [],
                "realized_profit": 0.0,
                "buy_total": 0.0,
                "sell_total": 0.0,
                "buy_count": 0,
                "sell_count": 0,
                "profit_by_stock": {}
            }

        orders.sort(key=lambda o: (
            o.get("order_date", "") or "",
            o.get("order_time", "") or ""
        ))

        buy_total = 0.0
        sell_total = 0.0
        buy_count = 0
        sell_count = 0
        stock_orders = {}

        for o in orders:
            code = o["code"]
            if code not in stock_orders:
                stock_orders[code] = []
            stock_orders[code].append({
                "buy_sell": o["buy_sell"],
                "qty": o.get("ccld_qty", 0),
                "price": o.get("ccld_price", 0)
            })

            ccld_qty = o.get("ccld_qty", 0)
            ccld_price = o.get("ccld_price", 0)
            amount = ccld_qty * ccld_price

            if o["buy_sell"] == "매수":
                buy_total += amount
                buy_count += 1
            else:
                sell_total += amount
                sell_count += 1

        realized_profit = 0.0
        realized_buy_total = 0.0
        realized_sell_total = 0.0
        profit_by_stock = {}

        for code, stock_orders_list in stock_orders.items():
            stock_name = ""
            for o in orders:
                if o["code"] == code:
                    stock_name = o["name"]
                    break

            buy_queue = []
            sell_amount = 0.0
            sell_qty = 0
            buy_amount_matched = 0.0
            buy_qty_matched = 0

            for so in stock_orders_list:
                if so["buy_sell"] == "매수":
                    buy_queue.append(so)
                else:
                    sell_qty_remaining = so["qty"]
                    sell_amount += so["qty"] * so["price"]
                    sell_qty += so["qty"]

                    while sell_qty_remaining > 0 and buy_queue:
                        buy_order = buy_queue[0]
                        match_qty = min(buy_order["qty"], sell_qty_remaining)
                        buy_amount_matched += match_qty * buy_order["price"]
                        buy_qty_matched += match_qty
                        sell_qty_remaining -= match_qty
                        buy_order["qty"] -= match_qty
                        if buy_order["qty"] <= 0:
                            buy_queue.pop(0)

            if sell_qty > 0:
                profit = sell_amount - buy_amount_matched
                profit_by_stock[code] = {
                    "name": stock_name,
                    "buy_amount": buy_amount_matched,
                    "sell_amount": sell_amount,
                    "buy_qty": buy_qty_matched,
                    "sell_qty": sell_qty,
                    "profit": profit
                }
                realized_profit += profit
                realized_buy_total += buy_amount_matched
                realized_sell_total += sell_amount
            else:
                profit_by_stock[code] = {
                    "name": stock_name,
                    "buy_amount": 0.0,
                    "sell_amount": 0.0,
                    "buy_qty": 0,
                    "sell_qty": 0,
                    "profit": 0.0
                }

        return {
            "orders": orders,
            "realized_profit": realized_profit,
            "buy_total": realized_buy_total,
            "sell_total": realized_sell_total,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "profit_by_stock": profit_by_stock
        }

    def get_unrealized_profit(self) -> Dict[str, Any]:
        """현재 보유 종목의 미실현 손익(평가손익) 계산"""
        balance = self.get_account_balance()
        holdings = balance.get("holdings", [])
        unrealized_profit = 0.0
        unrealized_by_stock = {}

        for h in holdings:
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

        return {
            "unrealized_profit": unrealized_profit,
            "unrealized_by_stock": unrealized_by_stock
        }
