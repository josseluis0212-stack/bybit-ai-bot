"""
Trade Recorder: Guarda cada operación del bot en el disco de red como archivos JSON.
Crea un archivo por operación abierta y lo archiva al cerrarse, con historial por fecha.
"""
import os
import json
import time
from datetime import datetime
from pathlib import Path
from app.logger import logger
from app.persistence.disk_manager import disk_manager


class TradeRecorder:
    """
    Registra operaciones de trading en el disco de red/local.
    
    Estructura de archivos:
    operaciones_bybit/
    ├── abiertas/
    │   └── {SYMBOL}_{SIDE}_{TIMESTAMP}.json
    └── historial/
        └── {YYYY-MM-DD}/
            └── {SYMBOL}_{SIDE}_{ESTADO}_{TIMESTAMP}.json
    """

    def _open_path(self, trade_id: str) -> str:
        """Ruta local del archivo de una operación abierta."""
        return os.path.join(disk_manager.ops_open_dir_local, f"{trade_id}.json")

    def _history_path(self, symbol: str, side: str, state: str) -> str:
        """Ruta local del archivo de historial por fecha."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        ts = int(time.time())
        date_dir = os.path.join(disk_manager.ops_hist_dir_local, date_str)
        os.makedirs(date_dir, exist_ok=True)
        return os.path.join(date_dir, f"{symbol}_{side}_{state}_{ts}.json")

    # ──────────────────────────────────────────────────────────────

    def record_open(self, trade_id: str, trade_data: dict):
        """
        Guarda una operación abierta en disco local Y en FTP.
        Se llama en el momento en que el bot ejecuta la orden de entrada.
        """
        record = {
            "trade_id":           trade_id,
            "symbol":             trade_data.get("symbol", ""),
            "strategy":           trade_data.get("strategy", ""),
            "side":               trade_data.get("side", ""),
            "apertura":           datetime.now().isoformat(),
            "apertura_ts":        int(time.time()),
            "precio_entrada":     trade_data.get("entry_price", 0),
            "precio_actual":      trade_data.get("entry_price", 0),
            "stop_loss":          trade_data.get("sl_price", 0),
            "take_profit_1":      trade_data.get("tp1_price", None),
            "take_profit_2":      trade_data.get("tp2_price", None),
            "profit_lock_price":  trade_data.get("profit_lock_price", 0),
            "tamanio_posicion":   trade_data.get("position_size", 0),
            "margen_usdt":        15.0,
            "apalancamiento":     10,
            "atr_entrada":        trade_data.get("atr", 0),
            "breakeven_activado": False,
            "trailing_activado":  False,
            "tp1_tocado":         False,
            "tp2_tocado":         False,
            "pnl_no_realizado":   0.0,
            "estado":             "ABIERTA",
            "notas":              []
        }
        local_path = self._open_path(trade_id)
        remote_path = f"{disk_manager.ops_open_dir}/{trade_id}.json"
        try:
            # Guardar local
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            # Subir al FTP en background (no bloquea el bot)
            disk_manager.write_json(remote_path, record, local_path)
            logger.info(f"[TRADE-RECORDER] 📂 Operación guardada: {trade_data.get('symbol')} {trade_data.get('side')}")
        except Exception as e:
            logger.error(f"[TRADE-RECORDER] Error guardando operación {trade_id}: {e}")


    def update_open(self, trade_id: str, updates: dict):
        """
        Actualiza el archivo JSON de una operación abierta.
        Llamado periódicamente para actualizar PnL, Trailing, Breakeven, etc.
        """
        path = self._open_path(trade_id)
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                record = json.load(f)
            record.update(updates)
            record["ultima_actualizacion"] = datetime.now().isoformat()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[TRADE-RECORDER] Error actualizando {trade_id}: {e}")

    def record_close(self, trade_id: str, symbol: str, side: str,
                     pnl: float, reason: str, extra: dict = None):
        """
        Cierra una operación: mueve el archivo de 'abiertas/' al historial por fecha.
        Incluye el PnL real, motivo de cierre y todos los parámetros de protección usados.
        """
        open_path = self._open_path(trade_id)
        
        # Leer el registro abierto
        record = {}
        if os.path.exists(open_path):
            try:
                with open(open_path, "r", encoding="utf-8") as f:
                    record = json.load(f)
            except Exception:
                pass

        # Enriquecer con datos de cierre
        estado = "GANADA" if pnl > 0 else ("PERDIDA" if pnl < 0 else "BREAKEVEN")
        record.update({
            "cierre":         datetime.now().isoformat(),
            "cierre_ts":      int(time.time()),
            "pnl_realizado":  round(pnl, 4),
            "motivo_cierre":  reason,
            "estado_final":   estado,
            "duracion_mins":  round((int(time.time()) - record.get("apertura_ts", int(time.time()))) / 60, 1),
        })
        if extra:
            record.update(extra)
        record["notas"].append(f"Cerrada por: {reason}. PnL: {pnl:.4f} USDT. Estado: {estado}")

        # Guardar en historial
        hist_path = self._history_path(symbol, side, estado)
        try:
            with open(hist_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            logger.info(f"[TRADE-RECORDER] 📊 Operación archivada: {symbol} {side} → {estado} ({pnl:+.4f} USDT)")
        except Exception as e:
            logger.error(f"[TRADE-RECORDER] Error archivando {trade_id}: {e}")

        # Eliminar de abiertas
        try:
            if os.path.exists(open_path):
                os.remove(open_path)
        except Exception as e:
            logger.error(f"[TRADE-RECORDER] Error eliminando archivo abierto {trade_id}: {e}")

    def get_all_open(self) -> list:
        """Retorna todos los registros de operaciones abiertas en disco."""
        trades = []
        open_dir = disk_manager.ops_open_dir_local
        if not open_dir or not os.path.exists(open_dir):
            return trades
        try:
            for fname in os.listdir(open_dir):
                if fname.endswith(".json"):
                    fpath = os.path.join(open_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            trades.append(json.load(f))
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"[TRADE-RECORDER] Error leyendo operaciones abiertas: {e}")
        return trades

    def get_history(self, date_str: str = None, limit: int = 50) -> list:
        """
        Retorna el historial de operaciones cerradas.
        Si date_str=None, retorna las últimas `limit` operaciones de todos los días.
        """
        trades = []
        hist_dir = disk_manager.ops_hist_dir_local
        if not hist_dir or not os.path.exists(hist_dir):
            return trades
        try:
            if date_str:
                date_dir = os.path.join(hist_dir, date_str)
                dirs = [date_dir] if os.path.exists(date_dir) else []
            else:
                dirs = sorted(
                    [os.path.join(hist_dir, d) for d in os.listdir(hist_dir)
                     if os.path.isdir(os.path.join(hist_dir, d))],
                    reverse=True
                )

            for d in dirs:
                for fname in sorted(os.listdir(d), reverse=True):
                    if fname.endswith(".json"):
                        try:
                            with open(os.path.join(d, fname), "r", encoding="utf-8") as f:
                                trades.append(json.load(f))
                            if len(trades) >= limit:
                                return trades
                        except Exception:
                            continue
        except Exception as e:
            logger.error(f"[TRADE-RECORDER] Error leyendo historial: {e}")
        return trades


# Instancia global
trade_recorder = TradeRecorder()
