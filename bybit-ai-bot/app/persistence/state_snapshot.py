"""
State Snapshot: Guarda y recupera el estado completo del bot en el disco.
Al apagar, serializa toda la memoria del engine.
Al encender, carga el estado y restaura operaciones abiertas.
"""
import os
import json
import time
from datetime import datetime
from app.logger import logger
from app.persistence.disk_manager import disk_manager


STATE_FILENAME = "estado_bot.json"


class StateSnapshot:
    """
    Gestiona la memoria persistente del bot.

    El archivo 'estado_bot.json' en el disco de red contiene:
    - Operaciones abiertas (trade_state completo del engine)
    - Cooldowns activos
    - Timestamp del último guardado
    - Versión del bot para compatibilidad futura
    """

    def _state_path(self) -> str:
        mem_dir = disk_manager.memory_dir_local
        if not mem_dir:
            mem_dir = os.path.join(disk_manager.local_fallback, "bibyt", "memoria")
            os.makedirs(mem_dir, exist_ok=True)
        return os.path.join(mem_dir, STATE_FILENAME)

    # ──────────────────────────────────────────────────────────────

    def save(self, trade_state: dict, cooldowns: dict):
        """
        Guarda el estado completo del engine en el disco.
        Se llama al apagar el bot (señal SIGTERM o stop manual).
        """
        snapshot = {
            "version":       "1.0",
            "guardado_en":   datetime.now().isoformat(),
            "guardado_ts":   int(time.time()),
            "trade_state":   self._serialize_trade_state(trade_state),
            "cooldowns":     {k: v for k, v in cooldowns.items()},
            "disk_source":   "network" if disk_manager.is_available() else "local",
        }

        path = self._state_path()
        # Backup del archivo anterior
        if os.path.exists(path):
            backup = path.replace(".json", "_backup.json")
            try:
                import shutil
                shutil.copy2(path, backup)
            except Exception:
                pass

        try:
            local_path = self._state_path()
            remote_path = f"{disk_manager.memory_dir}/{STATE_FILENAME}"
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
            # Subir al FTP también
            disk_manager.write_json(remote_path, snapshot, local_path)
            logger.info(f"[STATE] 💾 Estado guardado: {len(trade_state)} operaciones activas.")
        except Exception as e:
            logger.error(f"[STATE] Error guardando estado: {e}")


    def load(self) -> dict:
        """
        Carga el estado guardado del disco al encender el bot.
        Retorna un dict con 'trade_state' y 'cooldowns', o vacío si no hay nada.
        """
        path = self._state_path()
        if not os.path.exists(path):
            logger.info("[STATE] No hay estado previo guardado. Iniciando desde cero.")
            return {"trade_state": {}, "cooldowns": {}}

        try:
            with open(path, "r", encoding="utf-8") as f:
                snapshot = json.load(f)

            ts = snapshot.get("guardado_ts", 0)
            age_mins = (time.time() - ts) / 60
            trade_count = len(snapshot.get("trade_state", {}))

            logger.info(
                f"[STATE] 🔄 Estado recuperado del disco. "
                f"Guardado hace {age_mins:.0f} minutos. "
                f"{trade_count} operaciones activas."
            )

            # Filtrar cooldowns expirados
            now = time.time()
            valid_cooldowns = {
                k: v for k, v in snapshot.get("cooldowns", {}).items()
                if v > now
            }

            return {
                "trade_state": self._deserialize_trade_state(snapshot.get("trade_state", {})),
                "cooldowns":   valid_cooldowns,
                "snapshot_ts": ts,
            }

        except Exception as e:
            logger.error(f"[STATE] Error cargando estado: {e}. Iniciando desde cero.")
            return {"trade_state": {}, "cooldowns": {}}

    def clear(self):
        """Borra el estado guardado (se usa al hacer RESET manual del bot)."""
        path = self._state_path()
        try:
            if os.path.exists(path):
                os.remove(path)
                logger.info("[STATE] 🗑️ Estado persistente eliminado.")
        except Exception as e:
            logger.error(f"[STATE] Error eliminando estado: {e}")

    # ──────────────────────────────────────────────────────────────
    # Serialización / Deserialización
    # ──────────────────────────────────────────────────────────────

    def _serialize_trade_state(self, trade_state: dict) -> dict:
        """
        Convierte el trade_state del engine a un formato JSON serializable.
        Elimina objetos no serializables como asyncio.Lock.
        """
        serialized = {}
        for symbol, trade in trade_state.items():
            if not isinstance(trade, dict):
                continue
            safe_trade = {}
            for k, v in trade.items():
                # Excluir locks de asyncio y otros objetos no serializables
                if k == "lock":
                    continue
                try:
                    json.dumps(v)  # Test de serializabilidad
                    safe_trade[k] = v
                except (TypeError, ValueError):
                    safe_trade[k] = str(v)
            serialized[symbol] = safe_trade
        return serialized

    def _deserialize_trade_state(self, raw: dict) -> dict:
        """
        Restaura el trade_state. Las operaciones recuperadas se marcan
        para que el RecoveryEngine las verifique contra el exchange.
        """
        restored = {}
        for symbol, trade in raw.items():
            # Marcar como recuperada para que el engine la valide
            trade["recovered_from_disk"] = True
            # Asegurar que los campos críticos tengan valores válidos
            trade.setdefault("filled", True)
            trade.setdefault("remaining_size", trade.get("position_size", 0))
            trade.setdefault("trailing_active", False)
            trade.setdefault("profit_lock_active", False)
            restored[symbol] = trade
        return restored

    def get_snapshot_info(self) -> dict:
        """Retorna metadata del último snapshot para el dashboard."""
        path = self._state_path()
        if not os.path.exists(path):
            return {"exists": False}
        try:
            stat = os.stat(path)
            with open(path, "r", encoding="utf-8") as f:
                snap = json.load(f)
            return {
                "exists":      True,
                "guardado_en": snap.get("guardado_en", ""),
                "operaciones": len(snap.get("trade_state", {})),
                "size_kb":     round(stat.st_size / 1024, 1),
                "disk_source": snap.get("disk_source", "unknown"),
            }
        except Exception:
            return {"exists": True, "error": "No se pudo leer"}


# Instancia global
state_snapshot = StateSnapshot()
