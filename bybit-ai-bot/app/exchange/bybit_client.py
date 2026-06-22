import hmac
import hashlib
import time
import urllib.parse
import aiohttp
import json
import asyncio
from app.config import Config
from app.logger import logger

class AsyncBybitClient:
    def __init__(self):
        self.api_key = Config.API_KEY
        self.secret_key = Config.SECRET_KEY
        self.base_url = Config.REST_URL
        self._session = None
        self._contract_precisions = {}
        
    async def get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
        
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
        
    @staticmethod
    def _format_number(value: float, precision: int = 8) -> str:
        formatted = f"{value:.{precision}f}"
        if '.' in formatted:
            formatted = formatted.rstrip('0').rstrip('.')
        return formatted

    def _generate_signature(self, timestamp: str, recv_window: str, payload: str) -> str:
        param_str = timestamp + self.api_key + recv_window + payload
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            param_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    async def _request(self, method: str, endpoint: str, params: dict = None, signed: bool = True, max_retries: int = 3):
        url = f"{self.base_url}{endpoint}"
        session = await self.get_session()
        
        for attempt in range(max_retries):
            headers = {"Content-Type": "application/json"}
            payload = ""
            
            if method.upper() == "GET" and params:
                # Bybit requires alphabetical sort sometimes, but urllib handles standard. 
                # According to Bybit docs, for GET, payload is sorted query string.
                str_params = {k: str(v) for k, v in params.items()}
                sorted_params = sorted(str_params.items())
                query_string = urllib.parse.urlencode(sorted_params)
                url_with_params = f"{url}?{query_string}"
                if signed:
                    payload = query_string
            else:
                url_with_params = url
                if params and method.upper() == "POST":
                    payload = json.dumps(params)
                else:
                    payload = ""

            if signed:
                timestamp = str(int(time.time() * 1000))
                recv_window = "10000"
                sig = self._generate_signature(timestamp, recv_window, payload)
                headers["X-BAPI-API-KEY"] = self.api_key
                headers["X-BAPI-TIMESTAMP"] = timestamp
                headers["X-BAPI-RECV-WINDOW"] = recv_window
                headers["X-BAPI-SIGN"] = sig

            try:
                if method.upper() == "GET":
                    async with session.get(url_with_params, headers=headers, timeout=10) as resp:
                        text = await resp.text()
                        if not text:
                            raise ValueError(f"Empty response from Bybit. Status: {resp.status}")
                        res_json = json.loads(text)
                elif method.upper() == "POST":
                    async with session.post(url_with_params, headers=headers, data=payload, timeout=10) as resp:
                        text = await resp.text()
                        if not text:
                            raise ValueError(f"Empty response from Bybit. Status: {resp.status}")
                        res_json = json.loads(text)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                # Bybit uses retCode 0 for success
                if not isinstance(res_json, dict):
                    raise ValueError(f"Bybit returned non-dict JSON: {res_json}")
                    
                if res_json.get("retCode") == 0:
                    return {"success": True, "data": res_json.get("result"), "msg": res_json.get("retMsg"), "code": 0}
                else:
                    err_msg = res_json.get("retMsg", "Unknown error")
                    code = res_json.get("retCode")
                    logger.error(f"Bybit API Error on {url}: {err_msg} | Code: {code}")
                    return {"success": False, "data": None, "msg": err_msg, "code": code}
                    
            except Exception as e:
                logger.error(f"Bybit API Request Exception (Attempt {attempt+1}/{max_retries}): {e}")
                
            if attempt < max_retries - 1:
                await asyncio.sleep(1 * (attempt + 1))
                
        return {"success": False, "data": None, "msg": "Max retries exceeded"}

    async def get_klines(self, symbol: str, interval: str = "5m", limit: int = 100) -> list:
        bybit_interval = interval.replace("m", "")
        # Map 5m to 5 for Bybit
        params = {"category": "linear", "symbol": symbol.replace("-", "").upper(), "interval": bybit_interval, "limit": limit}
        res = await self._request("GET", "/v5/market/kline", params=params, signed=False)
        raw = res.get("data", {}).get("list", [])
        if not raw:
            return []

        parsed = []
        for k in raw:
            try:
                # Bybit v5 kline format: [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
                parsed.append({
                    "open":   float(k[1]),
                    "high":   float(k[2]),
                    "low":    float(k[3]),
                    "close":  float(k[4]),
                    "volume": float(k[5]),
                    "time":   int(k[0]),
                })
            except Exception as e:
                continue
        # Bybit returns newest first, we usually need oldest first for indicators
        parsed.reverse()
        return parsed

    async def get_positions(self, symbol: str = None):
        params = {"category": "linear", "settleCoin": "USDT"}
        if symbol:
            params["symbol"] = symbol.replace("-", "").upper()
        res = await self._request("GET", "/v5/position/list", params=params, signed=True)
        if not res or not res.get("success"):
            logger.error(f"Failed to get positions: {res}")
            return []
        
        # Convert to BingX-like format for compatibility
        bybit_pos = res.get("data", {}).get("list", [])
        bingx_pos = []
        for p in bybit_pos:
            side = p.get("positionIdx")
            pos_side = "LONG" if side == 1 else ("SHORT" if side == 2 else "BOTH")
            bingx_pos.append({
                "symbol": p.get("symbol"),
                "positionSide": pos_side,
                "positionAmt": float(p.get("size") or 0.0),
                "entryPrice": float(p.get("avgPrice") or 0.0),
                "markPrice": float(p.get("markPrice") or 0.0),
                "unrealizedProfit": float(p.get("unrealisedPnl") or 0.0)
            })
        return bingx_pos

    async def get_ticker(self, symbol: str) -> dict:
        params = {"category": "linear", "symbol": symbol.replace("-", "").upper()}
        res = await self._request("GET", "/v5/market/tickers", params=params, signed=False)
        list_data = res.get("data", {}).get("list", [])
        if list_data:
            t = list_data[0]
            return {
                "lastPrice": float(t.get("lastPrice", 0)),
                "askPrice": float(t.get("ask1Price", 0)),
                "bidPrice": float(t.get("bid1Price", 0))
            }
        return {}

    async def set_leverage(self, symbol: str, side: str, leverage: int):
        # Bybit sets leverage for both sides at once if in Hedge Mode
        params = {
            "category": "linear",
            "symbol": symbol.replace("-", "").upper(),
            "buyLeverage": str(int(leverage)),
            "sellLeverage": str(int(leverage))
        }
        res = await self._request("POST", "/v5/position/set-leverage", params=params, signed=True)
        # 110043 means leverage not modified
        if res.get("success") or res.get("code") == 110043:
            return True
        return False

    async def set_margin_type(self, symbol: str, margin_type: str = "ISOLATED"):
        tradeMode = 1 if margin_type.upper() == "ISOLATED" else 0
        params = {
            "category": "linear",
            "symbol": symbol.replace("-", "").upper(),
            "tradeMode": tradeMode,
            "buyLeverage": "10",
            "sellLeverage": "10"
        }
        res = await self._request("POST", "/v5/position/switch-isolated", params=params, signed=True)
        if res.get("success") or res.get("code") == 110026: # 110026 = already isolated
            return True
        return False

    async def get_contract_precisions(self):
        if not self._contract_precisions:
            res = await self._request("GET", "/v5/market/instruments-info", params={"category": "linear"}, signed=False)
            if res and res.get("data") and "list" in res["data"]:
                for c in res["data"]["list"]:
                    # count decimal places
                    qty_step = c.get("lotSizeFilter", {}).get("qtyStep", "1")
                    price_step = c.get("priceFilter", {}).get("tickSize", "1")
                    
                    qty_prec = len(qty_step.split(".")[1]) if "." in qty_step else 0
                    price_prec = len(price_step.split(".")[1]) if "." in price_step else 0
                    
                    self._contract_precisions[c["symbol"]] = {
                        "qty": qty_prec,
                        "price": price_prec
                    }
        return self._contract_precisions

    async def place_order(self, symbol: str, side: str, position_side: str, order_type: str, quantity: float, price: float = None, stop_price: float = None, post_only: bool = False, reduce_only: bool = False, attached_sl: float = None):
        await self.get_contract_precisions()
        prec = self._contract_precisions.get(symbol.replace("-", "").upper(), {"qty": 3, "price": 4})

        formatted_qty = self._format_number(float(quantity), precision=prec["qty"])
        if not formatted_qty or float(formatted_qty) <= 0:
            return {"success": False, "msg": "Formatted quantity is 0.", "code": 109400}

        # Mapping BingX inputs to Bybit
        bybit_side = "Buy" if side.upper() == "BUY" else "Sell"
        bybit_pos_idx = 1 if position_side.upper() == "LONG" else 2 # 1=Long, 2=Short, 0=One-Way
        
        b_type = "Limit" if order_type.upper() == "LIMIT" else "Market"

        params = {
            "category": "linear",
            "symbol": symbol.replace("-", "").upper(),
            "side": bybit_side,
            "orderType": b_type,
            "qty": formatted_qty,
            "positionIdx": bybit_pos_idx,
            "timeInForce": "PostOnly" if post_only else "GTC",
            "reduceOnly": reduce_only
        }
        
        if attached_sl is not None:
            params["stopLoss"] = self._format_number(float(attached_sl), precision=prec["price"])
            
        if price is not None:
            params["price"] = self._format_number(float(price), precision=prec["price"])
            
        if stop_price is not None:
            # STOP_MARKET or TAKE_PROFIT_MARKET
            if order_type.upper() == "STOP_MARKET":
                params["triggerPrice"] = self._format_number(float(stop_price), precision=prec["price"])
                params["orderType"] = "Market"
                params["stopOrderType"] = "StopLoss"
                params["triggerDirection"] = 2 if bybit_side == "Sell" else 1 # logic varies, but Bybit auto-detects based on price if not strict
            elif order_type.upper() == "TAKE_PROFIT_MARKET":
                params["triggerPrice"] = self._format_number(float(stop_price), precision=prec["price"])
                params["orderType"] = "Market"
                params["stopOrderType"] = "TakeProfit"
                params["triggerDirection"] = 1 if bybit_side == "Sell" else 2
                
        res = await self._request("POST", "/v5/order/create", params=params, signed=True)
        return res

    async def cancel_all_orders(self, symbol: str):
        sym = symbol.replace("-", "").upper()
        # Cancel regular orders
        params_normal = {"category": "linear", "symbol": sym, "orderFilter": "Order"}
        res_normal = await self._request("POST", "/v5/order/cancel-all", params=params_normal, signed=True)
        
        # Cancel conditional orders (SL/TP)
        params_stop = {"category": "linear", "symbol": sym, "orderFilter": "StopOrder"}
        res_stop = await self._request("POST", "/v5/order/cancel-all", params=params_stop, signed=True)
        
        return res_normal.get("success", False) or res_stop.get("success", False)

    async def cancel_order(self, symbol: str, order_id: str):
        params = {
            "category": "linear",
            "symbol": symbol.replace("-", "").upper(),
            "orderId": order_id
        }
        res = await self._request("POST", "/v5/order/cancel", params=params, signed=True)
        return res

    async def get_balance(self, asset: str = "USDT") -> float:
        params = {"accountType": "UNIFIED", "coin": asset}
        res = await self._request("GET", "/v5/account/wallet-balance", params=params, signed=True)
        if res.get("success") and res.get("data") and res["data"].get("list"):
            coins = res["data"]["list"][0].get("coin", [])
            for c in coins:
                if c["coin"] == asset:
                    return float(c.get("equity", 0.0))
        return 0.0

    async def ensure_hedge_mode(self) -> bool:
        params = {"category": "linear", "mode": 3} # 3 is Hedge Mode in v5 (1 is Merged Single, 0 is One-Way)
        # Only pass symbol if required, but v5 requires coin or symbol. We can pass coin=USDT.
        params["coin"] = "USDT"
        res = await self._request("POST", "/v5/position/switch-mode", params=params, signed=True)
        # 110025 means already hedge mode
        if res.get("success") or res.get("code") == 110025:
            return True
        return False

    async def get_open_orders(self, symbol: str) -> list:
        params_normal = {"category": "linear", "symbol": symbol.replace("-", "").upper(), "orderFilter": "Order"}
        params_stop = {"category": "linear", "symbol": symbol.replace("-", "").upper(), "orderFilter": "StopOrder"}
        
        import asyncio
        res_normal, res_stop = await asyncio.gather(
            self._request("GET", "/v5/order/realtime", params=params_normal, signed=True),
            self._request("GET", "/v5/order/realtime", params=params_stop, signed=True)
        )
        
        orders = []
        if res_normal and res_normal.get("success"):
            orders.extend(res_normal.get("data", {}).get("list", []))
        if res_stop and res_stop.get("success"):
            orders.extend(res_stop.get("data", {}).get("list", []))
            
        return orders

    async def get_top_volume_symbols(self, limit: int = 80) -> list:
        res = await self._request("GET", "/v5/market/tickers", params={"category": "linear"}, signed=False)
        tickers = res.get("data", {}).get("list", [])
        usdt_pairs = [t for t in tickers if t["symbol"].endswith("USDT")]
        usdt_pairs.sort(key=lambda x: float(x.get("turnover24h", 0)), reverse=True)
        return [t["symbol"] for t in usdt_pairs[:limit]]

    async def get_income(self, limit: int = 1000) -> list:
        params = {"category": "linear", "limit": 100}
        res = await self._request("GET", "/v5/position/closed-pnl", params=params, signed=True)
        return res.get("data", {}).get("list", [])

