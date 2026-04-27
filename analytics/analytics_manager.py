import pandas as pd
from datetime import datetime, timedelta, timezone
import logging
from api.bybit_client import bybit_client

logger = logging.getLogger(__name__)

class AnalyticsManager:
    def __init__(self):
        # Fecha de reinicio por defecto: Inicio del día de hoy (UTC)
        now = datetime.now(timezone.utc)
        self.reset_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

    def reset_date_now(self):
        self.reset_date = datetime.now(timezone.utc)
        logger.info(f"AnalyticsManager: Reset date actualizado a {self.reset_date}")

    # ─────────────────────────────────────────────
    # Helpers internos
    # ─────────────────────────────────────────────
    def _fetch_trades(self, start_dt: datetime = None, end_dt: datetime = None) -> pd.DataFrame | None:
        """
        Descarga el historial de PnL cerrado desde Bybit.
        Bybit limita el rango de tiempo a 7 días si se usa startTime/endTime.
        Hacemos múltiples peticiones si el rango es mayor.
        """
        now_utc = datetime.now(timezone.utc)
        effective_start = max(start_dt or self.reset_date, self.reset_date)
        effective_end   = end_dt or now_utc

        all_trades = []
        current_start = effective_start

        while current_start < effective_end:
            # Intervalo máximo de 7 días menos 1 minuto para seguridad
            next_limit = current_start + timedelta(days=7)
            current_end = min(next_limit, effective_end)
            
            start_ms = int(current_start.timestamp() * 1000)
            end_ms   = int(current_end.timestamp() * 1000)

            response = bybit_client.get_closed_pnl(
                limit=200,
                start_time=start_ms,
                end_time=end_ms
            )

            if response and response.get("retCode") == 0:
                batch = response["result"].get("list", [])
                all_trades.extend(batch)
            else:
                logger.warning(f"Error parcial en _fetch_trades: {response}")
            
            current_start = current_end + timedelta(seconds=1)

        if not all_trades:
            return None

        df = pd.DataFrame(all_trades)
        df["closedPnl"]   = pd.to_numeric(df["closedPnl"],   errors="coerce")
        df["updatedTime"] = pd.to_datetime(pd.to_numeric(df["updatedTime"]), unit="ms", utc=True)
        return df

    def _build_report_message(self, df: pd.DataFrame, title: str) -> str:
        """Genera un mensaje HTML formateado con todas las estadísticas del período."""
        if df is None or df.empty:
            return f"📊 <b>{title}</b>\n\nSin operaciones cerradas en este período."

        total   = len(df)
        wins_df = df[df["closedPnl"] > 0]
        loss_df = df[df["closedPnl"] <= 0]
        wins    = len(wins_df)
        losses  = len(loss_df)

        win_rate      = (wins / total) * 100
        total_pnl     = df["closedPnl"].sum()
        best_trade    = df["closedPnl"].max()
        worst_trade   = df["closedPnl"].min()
        gross_profit  = wins_df["closedPnl"].sum() if not wins_df.empty else 0
        gross_loss    = abs(loss_df["closedPnl"].sum()) if not loss_df.empty else 0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")
        pf_str        = f"{profit_factor:.2f}" if profit_factor != float("inf") else "∞"

        pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
        wr_emoji  = "🏆" if win_rate >= 55 else ("⚠️" if win_rate >= 40 else "🔻")

        msg  = f"📊 <b>{title}</b>\n\n"
        msg += f"<b>Operaciones totales:</b> {total}\n"
        msg += f"✅ <b>Ganadoras:</b> {wins}\n"
        msg += f"❌ <b>Perdedoras:</b> {losses}\n"
        msg += f"{wr_emoji} <b>Win Rate:</b> {win_rate:.1f}%\n\n"
        msg += f"{pnl_emoji} <b>PnL Neto:</b> {total_pnl:+.2f} USDT\n"
        msg += f"💰 <b>Mejor trade:</b> +{best_trade:.2f} USDT\n"
        msg += f"💸 <b>Peor trade:</b> {worst_trade:.2f} USDT\n"
        msg += f"📐 <b>Profit Factor:</b> {pf_str}\n"

        # Si tiene más de 1 día de datos, agregar desglose diario
        if (df["updatedTime"].max() - df["updatedTime"].min()).days >= 1:
            daily = df.set_index("updatedTime").resample("D")["closedPnl"].sum()
            msg += "\n📅 <b>Desglose diario:</b>\n"
            for date, pnl in daily.items():
                emoji = "🟢" if pnl >= 0 else "🔴"
                msg += f"  {emoji} {date.strftime('%d/%m')}: {pnl:+.2f} USDT\n"

        return msg.strip()

    # ─────────────────────────────────────────────
    # Reportes periódicos
    # ─────────────────────────────────────────────
    def get_periodic_report(self, period: str = "diario") -> str:
        """
        Genera el reporte para el período especificado:
          - 'diario'   → Día de HOY (UTC)
          - 'semanal'  → Semana ISO actual (lunes a hoy)
          - 'mensual'  → Mes actual (1ro a hoy)
        """
        now = datetime.now(timezone.utc)

        if period == "diario":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            title = f"REPORTE DIARIO — {now.strftime('%d/%m/%Y')}"
        elif period == "semanal":
            # Inicio de la semana ISO (lunes)
            start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            end_str = now.strftime("%d/%m")
            start_str = start.strftime("%d/%m")
            title = f"REPORTE SEMANAL — {start_str} al {end_str}"
        else:  # mensual
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            title = f"REPORTE MENSUAL — {now.strftime('%B %Y').upper()}"

        df = self._fetch_trades(start_dt=start, end_dt=now)
        return self._build_report_message(df, title)

    def get_full_report(self) -> str:
        """Reporte acumulado desde reset_date hasta ahora (para el mensaje de salud)."""
        now = datetime.now(timezone.utc)
        df = self._fetch_trades(start_dt=self.reset_date, end_dt=now)
        return self._build_report_message(df, "RESUMEN ACUMULADO")

    def get_summary_n_trades(self, n: int = 10) -> str | None:
        """Resumen de las últimas N operaciones cerradas."""
        df = self._fetch_trades()
        if df is None or df.empty:
            return None

        last_n = df.tail(n)
        pnl_n  = last_n["closedPnl"].sum()
        wins   = len(last_n[last_n["closedPnl"] > 0])
        losses = len(last_n) - wins
        wr     = (wins / len(last_n)) * 100

        msg  = f"📈 <b>ÚLTIMAS {len(last_n)} OPERACIONES</b>\n\n"
        msg += f"✅ Ganadoras: {wins}   ❌ Perdedoras: {losses}\n"
        msg += f"🎯 Win Rate: {wr:.1f}%\n"
        msg += f"💵 Resultado: {pnl_n:+.2f} USDT"
        return msg

    # ─────────────────────────────────────────────
    # Dashboard API Statistics
    # ─────────────────────────────────────────────
    def get_dashboard_stats(self) -> dict:
        """Retorna estadísticas clave para ser consumidas por la API del dashboard."""
        now = datetime.now(timezone.utc)
        
        # Rangos
        start_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Descargar trades acumulados
        df_full = self._fetch_trades(start_dt=self.reset_date, end_dt=now)
        
        stats = {
            "daily": {"pnl": 0.0, "wr": 0.0, "count": 0},
            "weekly": {"pnl": 0.0, "wr": 0.0, "count": 0},
            "monthly": {"pnl": 0.0, "wr": 0.0, "count": 0},
            "total": {"pnl": 0.0, "wr": 0.0, "count": 0}
        }

        if df_full is not None and not df_full.empty:
            def calc_sub_stats(sub_df):
                if sub_df.empty: return {
                    "pnl": 0.0, "wr": 0.0, "count": 0, "wins": 0, "losses": 0,
                    "best": 0.0, "worst": 0.0, "pf": 0.0, "rr": "1:0.0"
                }
                pnl = float(sub_df["closedPnl"].sum())
                wins_df = sub_df[sub_df["closedPnl"] > 0]
                loss_df = sub_df[sub_df["closedPnl"] <= 0]
                wins = len(wins_df)
                losses = len(loss_df)
                wr = (wins / len(sub_df)) * 100
                best = float(sub_df["closedPnl"].max())
                worst = float(sub_df["closedPnl"].min())
                
                gross_profit = float(wins_df["closedPnl"].sum()) if not wins_df.empty else 0.0
                gross_loss = float(abs(loss_df["closedPnl"].sum())) if not loss_df.empty else 0.0
                pf = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
                
                return {
                    "pnl": pnl, "wr": wr, "count": len(sub_df), "wins": wins, "losses": losses,
                    "best": best, "worst": worst, "pf": pf, "rr": "1:2.1" # Hardcoded RR for now or calculate from TP/SL
                }

            # Total
            stats["total"] = calc_sub_stats(df_full)
            
            # Diario
            df_day = df_full[df_full["updatedTime"] >= start_day]
            stats["daily"] = calc_sub_stats(df_day)
            
            # Semanal
            df_week = df_full[df_full["updatedTime"] >= start_week]
            stats["weekly"] = calc_sub_stats(df_week)
            
            # Mensual
            df_month = df_full[df_full["updatedTime"] >= start_month]
            stats["monthly"] = calc_sub_stats(df_month)

        return stats

    def get_combined_periodic_report(self) -> str:
        """Genera un reporte que combina todas las temporalidades (para el trigger de 10 trades)."""
        daily_msg   = self.get_periodic_report("diario")
        weekly_msg  = self.get_periodic_report("semanal")
        monthly_msg = self.get_periodic_report("mensual")
        
        combined = f"🎯 <b>HIT DE 10 OPERACIONES ALCANZADO</b> 🎯\n\n"
        combined += f"{daily_msg}\n\n"
        combined += f"{weekly_msg}\n\n"
        combined += f"{monthly_msg}\n\n"
        combined += "🚀 Sigamos operando con disciplina institucional."
        return combined

    # Mantener compatibilidad con código existente
    def get_performance_stats(self) -> str:
        return self.get_full_report()

analytics_manager = AnalyticsManager()
