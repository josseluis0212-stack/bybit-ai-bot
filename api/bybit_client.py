import logging
import json
import aiohttp
from pybit.unified_trading import HTTP
from config.settings import settings

logger = logging.getLogger(__name__)

class BybitClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BybitClient, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.session = HTTP(
            demo=settings.BYBIT_DEMO,
            api_key=settings.BYBIT_API_KEY,
            api_secret=settings.BYBIT_API_SECRET
        )
        
        if settings.PROXY_URL:
            self.session.client.proxies = {
                'http': settings.PROXY_URL,
                'https': settings.PROXY_URL
            }
            logger.info(f"Proxy configurado para Bybit (Sync): {settings.PROXY_URL[:15]}...")
            
        logger.info(f"BybitClient inicializado (Demo: {settings.BYBIT_DEMO})")

    def get_wallet_balance(self):
        try:
            response = self.session.get_wallet_balance(accountType="UNIFIED")
            return response
        except Exception as e:
            logger.error(f"Error obteniendo balance: {e}")
            return None

    def get_tickers(self, category="linear"):
        try:
            response = self.session.get_tickers(category=category)
            if response.get("retCode") == 0:
                list_tickers = response["result"]["list"]
                # Filtrar solo pares USDT
                usdt_pairs = [item for item in list_tickers if item['symbol'].endswith('USDT')]
                return usdt_pairs
            return None
        except Exception as e:
            logger.error(f"Error obteniendo tickers: {e}")
            return None

    async def get_klines_async(self, symbol, interval, limit=200):
        """Obtiene velas de forma asíncrona usando aiohttp para evitar agotar el pool de conexiones"""
        url = "https://api.bybit.com/v5/market/kline"
        if settings.BYBIT_DEMO:
            url = "https://api-demo.bybit.com/v5/market/kline"
            
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                kwargs = {"params": params, "timeout": 10}
                if settings.PROXY_URL:
                    kwargs["proxy"] = settings.PROXY_URL
                
                async with session.get(url, **kwargs) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    elif response.status == 403:
                        logger.error(f"⚠️ ERROR 403 (Forbidden) en klines {symbol}. El IP está bloqueado. Proxy configurado: {bool(settings.PROXY_URL)}")
                        return None
                    else:
                        # logger.warning(f"Error HTTP {response.status} en klines para {symbol}")
                        return None
        except Exception as e:
            # logger.error(f"Excepción en get_klines_async para {symbol}: {e}")
            return None
            
    def get_positions(self, category="linear", settleCoin="USDT"):
        try:
            response = self.session.get_positions(category=category, settleCoin=settleCoin)
            return response
        except Exception as e:
            logger.error(f"Error obteniendo posiciones: {e}")
            return None

    def get_active_positions(self, category="linear", settleCoin="USDT"):
        """Retorna solo las posiciones con size > 0"""
        response = self.get_positions(category, settleCoin)
        if response and response.get("retCode") == 0:
            return [p for p in response['result']['list'] if float(p['size']) > 0]
        return []

    def get_instruments_info(self, category="linear", symbol=None):
        try:
            params = {"category": category}
            if symbol:
                params["symbol"] = symbol
                
            response = self.session.get_instruments_info(**params)
            if response.get("retCode") == 0 and response["result"]["list"]:
                # Build an open dictionary
                info_dict = {}
                for item in response["result"]["list"]:
                    info_dict[item['symbol']] = {
                        "qtyStep": item["lotSizeFilter"]["qtyStep"],
                        "tickSize": item["priceFilter"]["tickSize"],
                        "minOrderQty": item["lotSizeFilter"]["minOrderQty"]
                    }
                return info_dict
            return None
        except Exception as e:
            logger.error(f"Error obteniendo instruments info: {e}")
            return None

    def set_leverage(self, symbol, leverage):
        try:
            response = self.session.set_leverage(
                category="linear",
                symbol=symbol,
                buyLeverage=str(leverage),
                sellLeverage=str(leverage)
            )
            return response
        except Exception as e:
            # Error 110043 means leverage not modified (already set to this)
            if "110043" not in str(e):
                logger.error(f"Error configurando apalancamiento en {symbol}: {e}")
            return None

    def get_closed_pnl(self, category="linear", limit=200, start_time=None, end_time=None):
        """
        Obtiene el historial de PnL cerrado.
        start_time / end_time: timestamps en milisegundos (opcionales) para filtrar por período.
        """
        try:
            params = {"category": category, "limit": limit}
            if start_time:
                params["startTime"] = int(start_time)
            if end_time:
                params["endTime"] = int(end_time)
            response = self.session.get_closed_pnl(**params)
            return response
        except Exception as e:
            logger.error(f"Error obteniendo historial de PnL: {e}")
            return None

    def place_order(self, symbol, side, order_type, qty, price=None, take_profit=None, stop_loss=None):
        try:
            order_params = {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": str(qty),
            }
            if price and order_type == "Limit":
                order_params["price"] = str(price)
            if take_profit:
                order_params["takeProfit"] = str(take_profit)
            if stop_loss:
                order_params["stopLoss"] = str(stop_loss)

            response = self.session.place_order(**order_params)
            if response and response.get("retCode") == 0:
                logger.info(f"Orden ejecutada: {symbol} {side} {qty}")
            else:
                logger.error(f"Error de Bybit al colocar orden en {symbol}: {response}")
            return response
        except Exception as e:
            logger.error(f"Excepción crítica al colocar orden en {symbol}: {e}")
            return {"retCode": -1, "retMsg": str(e), "result": {}}

    def set_trading_stop(self, symbol, stop_loss=None, take_profit=None):
        """Actualiza el SL o TP de una posición abierta."""
        try:
            params = {
                "category": "linear",
                "symbol": symbol,
                "stopLoss": str(stop_loss) if stop_loss else None,
                "takeProfit": str(take_profit) if take_profit else None,
                "positionIdx": 0 # Generalmente 0 para hedge mode OFF o modo unificado
            }
            # Limpiar Nones de los parámetros
            params = {k: v for k, v in params.items() if v is not None}
            response = self.session.set_trading_stop(**params)
            return response
        except Exception as e:
            logger.error(f"Error configurando trading stop en {symbol}: {e}")
            return None

bybit_client = BybitClient()
