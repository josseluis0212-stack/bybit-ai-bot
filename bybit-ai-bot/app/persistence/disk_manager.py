"""
Disk Manager v2: Gestión del disco de red via FTP (Router ETB)
El disco USB Lexar está conectado al router ETB y expuesto via FTP en 192.168.2.7
"""
import os
import io
import time
import json
import shutil
import threading
import ftplib
from pathlib import Path
from datetime import datetime
from app.logger import logger
from app.config import Config


class FTPDiskManager:
    """
    Maneja el acceso al disco Lexar via FTP (192.168.2.7:21).
    Si el FTP no está disponible, usa almacenamiento local como fallback.
    """

    def __init__(self):
        self.ftp_host     = Config.NETWORK_DISK_IP        # 192.168.2.7
        self.ftp_port     = int(os.getenv("NETWORK_DISK_PORT", "21"))
        self.ftp_user     = Config.NETWORK_DISK_USER      # usuario FTP
        self.ftp_pass     = Config.NETWORK_DISK_PASS      # contraseña FTP
        self.local_fallback = Config.STORAGE_DIR

        self._available   = False
        self._lock        = threading.Lock()
        self._monitor_thread = None
        self._on_disconnect_cb = None
        self._on_reconnect_cb  = None

        # Rutas en el disco (se crean como carpetas vía FTP)
        self.base_dir     = "bibyt"
        self.ops_open_dir = "bibyt/operaciones_bybit/abiertas"
        self.ops_hist_dir = "bibyt/operaciones_bybit/historial"
        self.logs_dir     = "bibyt/logs"
        self.memory_dir   = "bibyt/memoria"

        # Rutas locales de fallback (espejo)
        self._local_base     = os.path.join(self.local_fallback, "bibyt")
        self._local_ops_open = os.path.join(self._local_base, "operaciones_bybit", "abiertas")
        self._local_ops_hist = os.path.join(self._local_base, "operaciones_bybit", "historial")
        self._local_logs     = os.path.join(self._local_base, "logs")
        self._local_memory   = os.path.join(self._local_base, "memoria")

    # ──────────────────────────────────────────────────────────────
    # Compatibilidad con trade_recorder y state_snapshot (rutas locales)
    # ──────────────────────────────────────────────────────────────
    @property
    def ops_open_dir_local(self): return self._local_ops_open
    @property
    def ops_hist_dir_local(self): return self._local_ops_hist
    @property
    def logs_dir_local(self):     return self._local_logs
    @property
    def memory_dir_local(self):   return self._local_memory

    # ──────────────────────────────────────────────────────────────
    # Inicialización
    # ──────────────────────────────────────────────────────────────

    def initialize(self) -> bool:
        """Conecta al FTP y crea la estructura de carpetas."""
        # Siempre crear carpetas locales primero (fallback siempre disponible)
        for d in [self._local_ops_open, self._local_ops_hist,
                  self._local_logs, self._local_memory]:
            os.makedirs(d, exist_ok=True)

        logger.info(f"[DISK] Conectando al disco FTP en {self.ftp_host}:{self.ftp_port}...")
        self._available = self._test_connection()

        if self._available:
            logger.info(f"[DISK] ✅ Disco FTP disponible en {self.ftp_host}. Creando estructura...")
            self._create_remote_dirs()
        else:
            logger.warning(f"[DISK] ⚠️ Disco FTP no disponible. Usando almacenamiento local en {self._local_base}")

        self._start_monitor()
        return self._available

    def _get_ftp(self) -> ftplib.FTP:
        """Crea una conexión FTP nueva (stateless, thread-safe)."""
        ftp = ftplib.FTP()
        ftp.connect(self.ftp_host, self.ftp_port, timeout=8)
        ftp.login(self.ftp_user, self.ftp_pass)
        ftp.set_pasv(True)
        return ftp

    def _test_connection(self) -> bool:
        """Verifica si el FTP responde."""
        try:
            ftp = self._get_ftp()
            ftp.quit()
            return True
        except Exception as e:
            logger.warning(f"[DISK] FTP no disponible: {e}")
            return False

    def _create_remote_dirs(self):
        """Crea la estructura de carpetas en el disco FTP."""
        dirs = [
            self.base_dir,
            "bybit-bot/operaciones_bybit",
            self.ops_open_dir,
            self.ops_hist_dir,
            self.logs_dir,
            self.memory_dir,
        ]
        try:
            ftp = self._get_ftp()
            for d in dirs:
                try:
                    ftp.mkd(d)
                except ftplib.error_perm:
                    pass  # Ya existe
            ftp.quit()
            logger.info("[DISK] Estructura de carpetas creada en el disco FTP.")
        except Exception as e:
            logger.error(f"[DISK] Error creando carpetas en FTP: {e}")

    # ──────────────────────────────────────────────────────────────
    # Operaciones de archivo (write/read/list/delete)
    # ──────────────────────────────────────────────────────────────

    def write_json(self, remote_path: str, data: dict, local_path: str = None):
        """
        Escribe un JSON en el disco FTP Y en local (doble copia).
        Si el FTP no está disponible, solo escribe en local.
        """
        content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")

        # Siempre escribir localmente
        if local_path:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, "wb") as f:
                f.write(content)

        # Intentar escribir en FTP
        if self._available:
            try:
                ftp = self._get_ftp()
                # Crear directorio padre si no existe
                parent = "/".join(remote_path.split("/")[:-1])
                if parent:
                    try: ftp.mkd(parent)
                    except: pass
                ftp.storbinary(f"STOR {remote_path}", io.BytesIO(content))
                ftp.quit()
            except Exception as e:
                logger.error(f"[DISK] Error escribiendo en FTP {remote_path}: {e}")

    def read_json(self, remote_path: str, local_path: str = None) -> dict:
        """Lee un JSON del disco FTP. Si falla, intenta desde local."""
        # Intentar leer del FTP primero
        if self._available:
            try:
                ftp = self._get_ftp()
                buf = io.BytesIO()
                ftp.retrbinary(f"RETR {remote_path}", buf.write)
                ftp.quit()
                return json.loads(buf.getvalue().decode("utf-8"))
            except Exception:
                pass

        # Fallback a archivo local
        if local_path and os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def list_files(self, remote_dir: str, local_dir: str = None) -> list:
        """Lista archivos JSON en una carpeta del FTP o en local."""
        files = []
        if self._available:
            try:
                ftp = self._get_ftp()
                names = ftp.nlst(remote_dir)
                ftp.quit()
                return [n.split("/")[-1] for n in names if n.endswith(".json")]
            except Exception:
                pass

        # Fallback local
        if local_dir and os.path.exists(local_dir):
            return [f for f in os.listdir(local_dir) if f.endswith(".json")]
        return []

    def delete_file(self, remote_path: str, local_path: str = None):
        """Elimina un archivo del FTP y del local."""
        if self._available:
            try:
                ftp = self._get_ftp()
                ftp.delete(remote_path)
                ftp.quit()
            except Exception:
                pass
        if local_path and os.path.exists(local_path):
            try: os.remove(local_path)
            except: pass

    def mkdir_remote(self, remote_path: str):
        """Crea una carpeta en el FTP."""
        if self._available:
            try:
                ftp = self._get_ftp()
                try: ftp.mkd(remote_path)
                except: pass
                ftp.quit()
            except Exception:
                pass

    # ──────────────────────────────────────────────────────────────
    # Monitor de conexión
    # ──────────────────────────────────────────────────────────────

    def _start_monitor(self):
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="FTPDiskMonitor"
        )
        self._monitor_thread.start()

    def _monitor_loop(self):
        while True:
            time.sleep(30)
            was = self._available
            now = self._test_connection()
            if was and not now:
                self._available = False
                logger.error("[DISK] 🔴 Disco FTP DESCONECTADO. Usando almacenamiento local.")
                if self._on_disconnect_cb:
                    try: self._on_disconnect_cb()
                    except: pass
            elif not was and now:
                self._available = True
                logger.info("[DISK] 🟢 Disco FTP RECONECTADO. Sincronizando datos locales...")
                self._sync_local_to_ftp()
                if self._on_reconnect_cb:
                    try: self._on_reconnect_cb()
                    except: pass

    def _sync_local_to_ftp(self):
        """Sube archivos locales al FTP cuando vuelve la conexión."""
        try:
            ftp = self._get_ftp()
            for local_dir, remote_dir in [
                (self._local_ops_open, self.ops_open_dir),
                (self._local_memory,   self.memory_dir),
            ]:
                if not os.path.exists(local_dir): continue
                for fname in os.listdir(local_dir):
                    if not fname.endswith(".json"): continue
                    local_path  = os.path.join(local_dir, fname)
                    remote_path = f"{remote_dir}/{fname}"
                    try:
                        with open(local_path, "rb") as f:
                            ftp.storbinary(f"STOR {remote_path}", f)
                        logger.info(f"[DISK] Sincronizado al disco: {fname}")
                    except Exception as e:
                        logger.error(f"[DISK] Error sincronizando {fname}: {e}")
            ftp.quit()
        except Exception as e:
            logger.error(f"[DISK] Error en sincronización: {e}")

    def on_disconnect(self, cb): self._on_disconnect_cb = cb
    def on_reconnect(self,  cb): self._on_reconnect_cb  = cb
    def is_available(self) -> bool: return self._available

    def get_status(self) -> dict:
        return {
            "connected":   self._available,
            "protocol":    "FTP",
            "ftp_host":    self.ftp_host,
            "ftp_port":    self.ftp_port,
            "ftp_user":    self.ftp_user,
            "local_base":  self._local_base,
        }


# Instancia global
disk_manager = FTPDiskManager()
