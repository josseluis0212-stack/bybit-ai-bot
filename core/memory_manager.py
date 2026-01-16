import json
import os
import time
from datetime import datetime, timedelta
class MemoryManager:
    def __init__(self, file_path="data/memoria_bot.json"):
        self.file_path = file_path
        self.data = self._load_memory()
    def _load_memory(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, "r") as f:
                return json.load(f)
        return {
            "monedas": {},
            "historial_trades": [], # Lista de todas las operaciones
            "puntos_aprendizaje": 0
        }
    def save_memory(self):
        # Asegurar que el directorio existe
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        with open(self.file_path, "w") as f:
            json.dump(self.data, f, indent=4)
    def update_coin_stats(self, symbol, win, profit):
        if symbol not in self.data["monedas"]:
            self.data["monedas"][symbol] = {
                "operaciones": 0, "aciertos": 0, "ganancia_neta": 0.0, "puntos": 0
            }
        
        stats = self.data["monedas"][symbol]
        stats["operaciones"] += 1
        stats["ganancia_neta"] += profit
        
        if win:
            stats["aciertos"] += 1
            stats["puntos"] += 10
        else:
            stats["puntos"] -= 5
            
        self.save_memory()
    def registrar_trade(self, symbol, side, pnl):
        """Guarda la operación en el historial permanente"""
        trade = {
            "symbol": symbol,
            "side": side,
            "pnl": float(pnl),
            "timestamp": time.time(),
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.data["historial_trades"].append(trade)
        # Mantener solo los últimos 1000 trades para no llenar el disco
        if len(self.data["historial_trades"]) > 1000:
            self.data["historial_trades"] = self.data["historial_trades"][-1000:]
        
        self.save_memory()
    def get_estadisticas(self, dias=1):
        """Calcula PnL y Winrate de los últimos X días"""
        now = time.time()
        limite = now - (dias * 86400)
        
        trades_periodo = [t for t in self.data["historial_trades"] if t["timestamp"] >= limite]
        
        if not trades_periodo:
            return {"pnl": 0.0, "wins": 0, "total": 0, "winrate": 0}
            
        total_pnl = sum(t["pnl"] for t in trades_periodo)
        wins = sum(1 for t in trades_periodo if t["pnl"] > 0)
        total = len(trades_periodo)
        winrate = (wins / total * 100) if total > 0 else 0
        
        return {
            "pnl": round(total_pnl, 2),
            "wins": wins,
            "total": total,
            "winrate": round(winrate, 1)
        }
    def get_coin_score(self, symbol):
        if symbol in self.data["monedas"]:
            return self.data["monedas"][symbol]["puntos"]
        return 0
