import json
import os

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
            "historial_diario": [],
            "puntos_aprendizaje": 0
        }

    def save_memory(self):
        with open(self.file_path, "w") as f:
            json.dump(self.data, f, indent=4)

    def update_coin_stats(self, symbol, win, profit):
        if symbol not in self.data["monedas"]:
            self.data["monedas"][symbol] = {
                "operaciones": 0,
                "aciertos": 0,
                "ganancia_neta": 0.0,
                "puntos": 0
            }
        
        stats = self.data["monedas"][symbol]
        stats["operaciones"] += 1
        if win:
            stats["aciertos"] += 1
            stats["puntos"] += 10
        else:
            stats["puntos"] -= 5
        stats["ganancia_neta"] += profit
        self.save_memory()

    def get_coin_score(self, symbol):
        if symbol in self.data["monedas"]:
            return self.data["monedas"][symbol]["puntos"]
        return 0
