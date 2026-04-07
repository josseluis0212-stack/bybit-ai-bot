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
            if response.get("retCode") == 10003:
                logger.error("🚫 Llave API Inválida (Err 10003). Asegúrate de que las llaves correspondan al entorno (Demo/Real).")
            return response
        except Exception as e:
            if "401" in str(e):
                logger.error(f"❌ Error 401: No Autorizado (Sugerencia: Revisa que BYBIT_DEMO sea {settings.BYBIT_DEMO})")
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

    def close_all_positions(self, category="linear"):
        """Cierra todas las posiciones abiertas a precio de mercado para el reset."""
        try:
            positions = self.get_positions(category=category)
            if positions and positions.get("retCode") == 0:
                for pos in positions["result"]["list"]:
                    if float(pos["size"]) > 0:
                        symbol = pos["symbol"]
                        side = "Sell" if pos["side"] == "Buy" else "Buy"
                        self.place_order(
                            symbol=symbol,
                            side=side,
                            order_type="Market",
                            qty=pos["size"],
                            reduce_only=True
                        )
                        logger.info(f"💣 Posición cerrada (RESET): {symbol} {pos['size']}")
            return True
        except Exception as e:
            logger.error(f"Error cerrando todas las posiciones: {e}")
            return False

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

    def place_order(self, symbol, side, order_type, qty, price=None, take_profit=None, stop_loss=None, **kwargs):
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
            
            # Soporte para reduceOnly y otros parámetros extra
            for key, value in kwargs.items():
                # Convertir CamelCase si es necesario para la API de Bybit
                api_key = "reduceOnly" if key == "reduce_only" else key
                order_params[api_key] = value

            response = self.session.place_order(**order_params)
            logger.info(f"Orden ejecutada: {symbol} {side} {qty}")
            return response
        except Exception as e:
            logger.error(f"Error al colocar orden en {symbol}: {e}")
            return None

    def set_trading_stop(self, symbol, take_profit=None, stop_loss=None):
        try:
            params = {
                "category": "linear",
                "symbol": symbol,
                "tpTriggerBy": "LastPrice",
                "slTriggerBy": "LastPrice"
            }
            if take_profit: params["takeProfit"] = str(take_profit)
            if stop_loss: params["stopLoss"] = str(stop_loss)
            
            response = self.session.set_trading_stop(**params)
            return response
        except Exception as e:
            logger.error(f"Error ajustando stop en {symbol}: {e}")
            return None

bybit_client = BybitClient()
