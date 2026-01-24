import os
import json
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
            "historial_global": [], # Lista de dicts {timestamp, symbol, win, profit, side}
            "puntos_aprendizaje": 0,
            "correlacion_btc": {} # symbol -> correlation_factor
        }

    def save_memory(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        with open(self.file_path, "w") as f:
            json.dump(self.data, f, indent=4)

    def update_coin_stats(self, symbol, win, profit, side="N/A"):
        # Registrar en Historial Global con Timestamp
        entry = {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "win": win,
            "profit": profit,
            "side": side
        }
        if "historial_global" not in self.data:
            self.data["historial_global"] = []
        self.data["historial_global"].append(entry)
        
        # Limitar historial a últimas 1000 operaciones para no saturar JSON
        if len(self.data["historial_global"]) > 1000:
            self.data["historial_global"] = self.data["historial_global"][-1000:]

        if symbol not in self.data["monedas"]:
            self.data["monedas"][symbol] = {
                "operaciones": 0,
                "aciertos": 0,
                "ganancia_neta": 0.0,
                "puntos": 0
            }
        
        stats = self.data["monedas"][symbol]
        stats["operaciones"] += 1
        
        # Lógica de Aprendizaje (Módulo 8)
        if win:
            stats["aciertos"] += 1
            stats["puntos"] += 10
            self.data["puntos_aprendizaje"] += 10 # Puntos globales para el Dashboard
            # Si gana, se considera más "estable" en su tendencia
        else:
            stats["puntos"] -= 5
            self.data["puntos_aprendizaje"] = max(0, self.data["puntos_aprendizaje"] - 5)
            # Si pierde varias veces seguidas, se marcará el riesgo
            
        stats["ganancia_neta"] += profit
        
        # Clasificación (Módulo 5)
        if stats["operaciones"] > 5:
            win_rate = stats["aciertos"] / stats["operaciones"]
            if win_rate < 0.4:
                stats["categoria"] = "TRAICIONERA"
            elif win_rate > 0.6:
                stats["categoria"] = "ESTABLE"
            else:
                stats["categoria"] = "NEUTRAL"
        else:
            stats["categoria"] = "NUEVA"
            
        self.save_memory()

    def update_correlation(self, symbol, btc_move, coin_move):
        """
        Módulo 5: Guarda qué monedas siguen a BTC.
        Simplificando: si se mueven en la misma dirección, aumenta correlación.
        """
        if symbol not in self.data["correlacion_btc"]:
            self.data["correlacion_btc"][symbol] = 0.5 # Default neutral
            
        # Si ambas suben o ambas bajan
        if (btc_move > 0 and coin_move > 0) or (btc_move < 0 and coin_move < 0):
            self.data["correlacion_btc"][symbol] = min(1.0, self.data["correlacion_btc"][symbol] + 0.05)
        else:
            self.data["correlacion_btc"][symbol] = max(0.0, self.data["correlacion_btc"][symbol] - 0.05)
        
        self.save_memory()

    def get_ranked_pairs(self, available_pairs):
        """
        Módulo 8: Prioriza pares con mejores puntos y correlación estable.
        """
        ranking = []
        for symbol in available_pairs:
            score = self.get_coin_score(symbol)
            corr = self.data["correlacion_btc"].get(symbol, 0.5)
            # Penalizar traicioneras
            if symbol in self.data["monedas"] and self.data["monedas"][symbol].get("categoria") == "TRAICIONERA":
                score -= 20
                
            ranking.append({
                "symbol": symbol,
                "rank_score": score + (corr * 10)
            })
            
        # Ordenar por puntaje de mayor a menor
        ranking.sort(key=lambda x: x["rank_score"], reverse=True)
        return [item["symbol"] for item in ranking]

    def get_coin_score(self, symbol):
        if symbol in self.data["monedas"]:
            return self.data["monedas"][symbol]["puntos"]
        return 0

    def get_periodic_statistics(self, days=1):
        """
        Calcula estadísticas del historial para los últimos N días.
        """
        now = datetime.now()
        threshold = now - timedelta(days=days)
        
        relevant = []
        for op in self.data.get("historial_global", []):
            op_time = datetime.fromisoformat(op["timestamp"])
            if op_time > threshold:
                relevant.append(op)
        
        if not relevant:
            return None
            
        total = len(relevant)
        wins = sum(1 for op in relevant if op["win"])
        pnl = sum(op["profit"] for op in relevant)
        win_rate = (wins / total) * 100 if total > 0 else 0
        
        return {
            "total": total,
            "wins": wins,
            "losses": total - wins,
            "win_rate": win_rate,
            "pnl": pnl
        }

