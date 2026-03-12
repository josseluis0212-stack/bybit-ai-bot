import logging
import json
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
            api_secret=settings.BYBIT_API_SECRET,
        )
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
            
    def get_positions(self, category="linear", settleCoin="USDT"):
        try:
            response = self.session.get_positions(category=category, settleCoin=settleCoin)
            return response
        except Exception as e:
            logger.error(f"Error obteniendo posiciones: {e}")
            return None

    def get_instruments_info(self, category="linear"):
        if hasattr(self, '_instruments_info') and getattr(self, '_instruments_info_category', None) == category:
            return self._instruments_info
            
        try:
            response = self.session.get_instruments_info(category=category)
            if response.get("retCode") == 0:
                self._instruments_info = {}
                self._instruments_info_category = category
                for item in response["result"]["list"]:
                    if item['symbol'].endswith('USDT'):
                        self._instruments_info[item['symbol']] = {
                            "qtyStep": item["lotSizeFilter"]["qtyStep"],
                            "tickSize": item["priceFilter"]["tickSize"]
                        }
                return self._instruments_info
            return None
        except Exception as e:
            logger.error(f"Error obteniendo instruments info: {e}")
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
            logger.info(f"Orden ejecutada: {symbol} {side} {qty}")
            return response
        except Exception as e:
            logger.error(f"Error al colocar orden en {symbol}: {e}")
            return None

bybit_client = BybitClient()
