import os
from pybit.unified_trading import HTTP
from dotenv import load_dotenv
load_dotenv()
class BybitClient:
    def __init__(self, testnet=False, demo=True):
        self.api_key = os.getenv("BYBIT_API_KEY")
        self.api_secret = os.getenv("BYBIT_API_SECRET")
        self.testnet = testnet
        self.demo = demo
        
        # Para Demo Trading, testnet debe ser False y demo debe ser True
        self.session = HTTP(
            testnet=self.testnet,
            demo=self.demo,
            api_key=self.api_key,
            api_secret=self.api_secret,
        )
        mode = "Demo Trading" if self.demo else ("Testnet" if self.testnet else "Mainnet")
        print(f"Conectado a Bybit {mode}")
    def get_balance(self, coin="USDT"):
        try:
            response = self.session.get_wallet_balance(
                accountType="UNIFIED",
                coin=coin,
            )
            if response['retCode'] == 0:
                balance = response['result']['list'][0]['coin'][0]['walletBalance']
                return float(balance)
            else:
                print(f"Error obteniendo balance: {response['retMsg']}")
                return 0.0
        except Exception as e:
            print(f"Excepción al obtener balance: {e}")
            return 0.0
    def get_kline(self, category="linear", symbol="BTCUSDT", interval="D", limit=100):
        try:
            response = self.session.get_kline(
                category=category,
                symbol=symbol,
                interval=interval,
                limit=limit,
            )
            if response['retCode'] == 0:
                return response['result']['list']
            else:
                print(f"Error obteniendo kline: {response['retMsg']}")
                return []
        except Exception as e:
            print(f"Excepción al obtener kline: {e}")
            return []
    def place_order(self, symbol, side, order_type, qty, price=None, sl=None, tp=None):
        try:
            # Asegurar apalancamiento antes de operar
            self.set_leverage(symbol, 5)
            
            params = {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": str(qty),
                "timeInForce": "GTC",
            }
            if price:
                params["price"] = str(price)
            if sl:
                params["stopLoss"] = str(sl)
            if tp:
                params["takeProfit"] = str(tp)
                
            response = self.session.place_order(**params)
            return response
        except Exception as e:
            print(f"Excepción al colocar orden: {e}")
            return None
    def get_active_positions(self):
        try:
            response = self.session.get_positions(category="linear", settleCoin="USDT")
            if response['retCode'] == 0:
                # Filtrar solo posiciones con tamaño > 0
                positions = [p for p in response['result']['list'] if float(p['size']) > 0]
                return positions
            return []
        except Exception as e:
            print(f"Error obteniendo posiciones: {e}")
            return []
    def set_leverage(self, symbol, leverage):
        try:
            self.session.set_leverage(
                category="linear",
                symbol=symbol,
                buyLeverage=str(leverage),
                sellLeverage=str(leverage)
            )
        except Exception:
            # A veces falla si ya tiene ese apalancamiento, lo ignoramos
            pass
    def get_all_symbols(self):
        try:
            response = self.session.get_instruments_info(category="linear")
            if response['retCode'] == 0:
                # Filtrar solo USDT perpetuos
                symbols = [i['symbol'] for i in response['result']['list'] if i['quoteCoin'] == 'USDT' and i['status'] == 'Trading']
                return symbols
            return []
        except Exception as e:
            print(f"Error obteniendo símbolos: {e}")
            return []
