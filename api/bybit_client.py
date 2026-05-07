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
            try:
                self.session.client.proxies = {
                    'http': settings.PROXY_URL,
                    'https': settings.PROXY_URL
                }
                logger.info(f"Proxy configurado para Bybit (Sync)")
            except Exception as e:
                logger.warning(f"Error configurando proxy: {e}")

        logger.info(f"BybitClient inicializado (Demo: {settings.BYBIT_DEMO})")

    def get_wallet_balance(self):
        try:
            response = self.session.get_wallet_balance(accountType="UNIFIED")
            return response
        except Exception as e:
            logger.error(f"Error obteniendo balance: {e}")
            return None

    def get_klines(self, symbol, interval="5", limit=100):
        try:
            response = self.session.get_kline(
                category="linear",
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            if response and response.get("retCode") != 0:
                logger.warning(f"Bybit Error klines {symbol}: {response.get('retMsg')}")
            return response
        except Exception as e:
            logger.error(f"Excepcion en klines {symbol}: {e}")
            return None

    def get_tickers(self, category="linear"):
        try:
            response = self.session.get_tickers(category=category)
            if response.get("retCode") == 0:
                list_tickers = response["result"]["list"]
                # Filtrar solo pares USDT (según preferencia del usuario)
                usdt_pairs = [item for item in list_tickers if item['symbol'].endswith('USDT')]
                return usdt_pairs
            return None
        except Exception as e:
            logger.error(f"Error obteniendo tickers: {e}")
            return None

    async def get_klines_async(self, symbol, interval, limit=200):
        """Obtiene velas de forma asíncrona usando aiohttp"""
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
                kwargs = {"params": params, "timeout": 15}
                if settings.PROXY_URL:
                    kwargs["proxy"] = settings.PROXY_URL

                async with session.get(url, **kwargs) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    elif response.status == 403:
                        logger.warning(f"ERROR 403 - IP bloqueada por Bybit. Necesitas proxy.")
                        return None
                    elif response.status == 401:
                        logger.warning(f"ERROR 401 - Credenciales inválidas o expiradas.")
                        return None
                    else:
                        logger.warning(f"HTTP {response.status} para {symbol}")
                        return None
        except aiohttp.ClientConnectorError:
            logger.warning(f"Conexión fallida para {symbol}. Revisa el proxy.")
            return None
        except Exception as e:
            logger.warning(f"Error en klines {symbol}: {type(e).__name__}")
            return None
            
    def get_positions(self, category="linear", settleCoin="USDT"):
        try:
            response = self.session.get_positions(category=category, settleCoin=settleCoin)
            return response
        except Exception as e:
            logger.error(f"Error obteniendo posiciones: {e}")
            return None

    def get_active_positions(self, category="linear"):
        """Retorna solo las posiciones con size > 0 (USDT y USDC)"""
        all_active = []
        for coin in ["USDT", "USDC"]:
            try:
                response = self.get_positions(category, settleCoin=coin)
                if response and response.get("retCode") == 0:
                    all_active.extend([p for p in response['result']['list'] if float(p['size']) > 0])
            except:
                pass
        return all_active

    def get_open_orders(self, category="linear", symbol=None):
        try:
            params = {"category": category}
            if symbol:
                params["symbol"] = symbol
            else:
                params["settleCoin"] = "USDT"
            
            response = self.session.get_open_orders(**params)
            if response and response.get("retCode") == 0:
                return response["result"]["list"]
            return []
        except Exception as e:
            logger.error(f"Error obteniendo open orders: {e}")
            return []

    def cancel_order(self, symbol, order_id, category="linear"):
        try:
            return self.session.cancel_order(category=category, symbol=symbol, orderId=order_id)
        except Exception as e:
            logger.error(f"Error cancelando order {order_id} de {symbol}: {e}")
            return None

    def cancel_all_orders(self, category="linear", symbol=None):
        try:
            params = {"category": category}
            if symbol:
                params["symbol"] = symbol
            else:
                params["settleCoin"] = "USDT"
            return self.session.cancel_all_orders(**params)
        except Exception as e:
            logger.error(f"Error cancelando todas las órdenes: {e}")
            return None

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

    def get_closed_pnl(self, category="linear", limit=200, start_time=None, end_time=None, symbol=None):
        """
        Obtiene el historial de PnL cerrado.
        start_time / end_time: timestamps en milisegundos (opcionales) para filtrar por período.
        """
        try:
            params = {"category": category, "limit": limit}
            if symbol:
                params["symbol"] = symbol
            if start_time:
                params["startTime"] = int(start_time)
            if end_time:
                params["endTime"] = int(end_time)
            response = self.session.get_closed_pnl(**params)
            return response
        except Exception as e:
            logger.error(f"Error obteniendo historial de PnL: {e}")
            return None

    def place_order(self, symbol, side, order_type, qty, price=None, take_profit=None, stop_loss=None, reduce_only=False, time_in_force="GTC"):
        try:
            order_params = {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": str(qty),
                "reduceOnly": reduce_only,
                "timeInForce": time_in_force
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

    def set_trading_stop(self, symbol, stop_loss=None, take_profit=None, trailing_stop=None):
        """Actualiza el SL o TP de una posición abierta."""
        try:
            params = {
                "category": "linear",
                "symbol": symbol,
                "positionIdx": 0 # Generalmente 0 para hedge mode OFF o modo unificado
            }
            if stop_loss is not None:
                params["stopLoss"] = str(stop_loss)
            if take_profit is not None:
                params["takeProfit"] = str(take_profit)
            if trailing_stop is not None:
                params["trailingStop"] = str(trailing_stop)

            response = self.session.set_trading_stop(**params)
            return response
        except Exception as e:
            logger.error(f"Error configurando trading stop en {symbol}: {e}")
            return None

    def get_funding_rate(self, symbol):
        """Obtiene la tasa de financiación actual del símbolo."""
        try:
            response = self.session.get_tickers(category="linear", symbol=symbol)
            if response and response.get("retCode") == 0 and response["result"]["list"]:
                return float(response["result"]["list"][0].get("fundingRate", 0))
            return 0.0
        except Exception as e:
            logger.error(f"Error obteniendo funding rate para {symbol}: {e}")
            return 0.0

bybit_client = BybitClient()
