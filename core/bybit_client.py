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
        self.symbol_info_cache = {}
        self.leverage_cache = {} # symbol -> leverage_value

    def get_symbol_info(self, symbol):
        if symbol in self.symbol_info_cache:
            return self.symbol_info_cache[symbol]
        
        try:
            response = self.session.get_instruments_info(category="linear", symbol=symbol)
            if response['retCode'] == 0:
                info = response['result']['list'][0]
                self.symbol_info_cache[symbol] = {
                    'qtyStep': float(info['lotSizeFilter']['qtyStep']),
                    'minOrderQty': float(info['lotSizeFilter']['minOrderQty']),
                    'tickSize': float(info['priceFilter']['tickSize'])
                }
                return self.symbol_info_cache[symbol]
        except Exception as e:
            print(f"Error obteniendo info de {symbol}: {e}")
        return None

    def adjust_qty(self, symbol, qty):
        info = self.get_symbol_info(symbol)
        if not info: return qty
        
        step = info['qtyStep']
        # Redondear hacia abajo al paso más cercano usando decimal-like math
        adjusted = float(round((qty // step) * step, 10))
        final_qty = max(adjusted, info['minOrderQty'])
        return final_qty

    def adjust_price(self, symbol, price):
        info = self.get_symbol_info(symbol)
        if not info: return price
        
        tick = info['tickSize']
        adjusted = round(price // tick * tick, 8)
        return adjusted

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
            # 1. Ajustar precisión ANTES de nada
            qty_adj = self.adjust_qty(symbol, qty)
            if price: price = self.adjust_price(symbol, price)
            if sl: sl = self.adjust_price(symbol, sl)
            if tp: tp = self.adjust_price(symbol, tp)

            params = {
                "category": "linear",
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": str(qty_adj),
                "timeInForce": "GTC",
            }
            if price: params["price"] = str(price)
            if sl: params["stopLoss"] = str(sl)
            if tp: params["takeProfit"] = str(tp)
            
            # 2. Log de depuración técnica (Consola)
            print(f"📦 [DEBUG] Enviando orden {symbol} {side}: Qty={params['qty']}, Price={params.get('price', 'MKT')}, SL={params.get('stopLoss', 'N/A')}")
            
            # 3. Intentar colocar orden
            response = self.session.place_order(**params)
            
            if response and response['retCode'] != 0:
                error_msg = response.get('retMsg', 'Error de API sin mensaje')
                print(f"❌ Bybit API Error ({symbol}): {response['retCode']} - {error_msg}")
                return {"retCode": response['retCode'], "retMsg": error_msg}
            
            if not response:
                return {"retCode": -1, "retMsg": "Error: Respuesta vacía de Bybit (Conexión)"}
                
            return response

        except Exception as e:
            err_msg = str(e)
            print(f"Excepción al colocar orden en {symbol}: {err_msg}")
            return {"retCode": -1, "retMsg": f"Error Sistémico: {err_msg}"}

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
        # 1. Verificar si ya está en caché con ese valor
        if self.leverage_cache.get(symbol) == leverage:
            return
            
        try:
            self.session.set_leverage(
                category="linear",
                symbol=symbol,
                buyLeverage=str(leverage),
                sellLeverage=str(leverage)
            )
            self.leverage_cache[symbol] = leverage
            print(f"✅ Apalancamiento ajustado a {leverage}x para {symbol}")
        except Exception as e:
            # A veces falla si ya tiene ese apalancamiento o por modo UTA, marcamos en caché para no insistir
            msg = str(e)
            if "not modified" in msg.lower() or "same leverage" in msg.lower():
                self.leverage_cache[symbol] = leverage
            else:
                print(f"⚠️ Error ajustando apalancamiento en {symbol}: {e}")

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

    def get_last_closed_pnl(self, symbol):
        try:
            response = self.session.get_closed_pnl(category="linear", symbol=symbol, limit=1)
            if response['retCode'] == 0 and response['result']['list']:
                return response['result']['list'][0]
            return None
        except Exception as e:
            print(f"Error obteniendo PnL cerrado para {symbol}: {e}")
            return None
