import pandas as pd
from database.db_manager import db_manager
from database.models import Trade
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class StatsCalculator:
    def get_summary_stats(self, days=None):
        """
        Calcula estadísticas generales desde la base de datos de operaciones cerradas.
        Si 'days' es proporcionado, filtra por los últimos N días.
        """
        session = db_manager.Session()
        try:
            query = session.query(Trade).filter(Trade.status == "CLOSED")
            
            if days:
                since_date = datetime.utcnow() - timedelta(days=days)
                query = query.filter(Trade.close_time >= since_date)
            
            trades = query.all()
            
            if not trades:
                return {
                    "total_trades": 0,
                    "winning_trades": 0,
                    "losing_trades": 0,
                    "win_rate": 0.0,
                    "total_pnl": 0.0,
                    "profit_factor": 0.0,
                    "best_trade": 0.0,
                    "worst_trade": 0.0,
                    "period": days if days else "Total"
                }
            
            # Convertir a DataFrame para cálculos rápidos
            df = pd.DataFrame([{
                'pnl_usdt': t.pnl_usdt,
                'pnl_pct': t.pnl_pct,
                'symbol': t.symbol
            } for t in trades])
            
            total_trades = len(df)
            winning_df = df[df['pnl_usdt'] > 0]
            losing_df = df[df['pnl_usdt'] <= 0]
            
            win_rate = (len(winning_df) / total_trades) * 100 if total_trades > 0 else 0
            
            gross_profit = winning_df['pnl_usdt'].sum() if not winning_df.empty else 0
            gross_loss = abs(losing_df['pnl_usdt'].sum()) if not losing_df.empty else 0
            profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
            
            total_pnl = df['pnl_usdt'].sum()
            best_trade = df['pnl_usdt'].max()
            worst_trade = df['pnl_usdt'].min()
            
            return {
                "total_trades": total_trades,
                "winning_trades": len(winning_df),
                "losing_trades": len(losing_df),
                "win_rate": win_rate,
                "total_pnl": total_pnl,
                "profit_factor": profit_factor,
                "best_trade": best_trade,
                "worst_trade": worst_trade,
                "period": days if days else "Total"
            }
        except Exception as e:
            logger.error(f"Error calculando estadísticas: {e}")
            return None
        finally:
            session.close()

    def format_stats_message(self, stats):
        if not stats or stats["total_trades"] == 0:
            period_label = f"Últimos {stats['period']} días" if stats and stats['period'] != "Total" else "Total"
            return f"📊 <b>Estadísticas ({period_label})</b>\nNo hay operaciones cerradas aún."
            
        period_label = {1: "Diario", 7: "Semanal", 30: "Mensual"}.get(stats['period'], "Total")
        
        return f"""
📊 <b>REPORTE {period_label.upper()}</b> 📊

<b>Operaciones:</b> {stats['total_trades']}
<b>Ganadoras ✅:</b> {stats['winning_trades']}
<b>Perdedoras ❌:</b> {stats['losing_trades']}
<b>Win Rate:</b> {stats['win_rate']:.2f}%

<b>PnL Total:</b> {stats['total_pnl']:.2f} USDT
<b>Profit Factor:</b> {stats['profit_factor']:.2f}
<b>Mejor Trade:</b> {stats['best_trade']:.2f} USDT
<b>Peor Trade:</b> {stats['worst_trade']:.2f} USDT
"""

stats_calculator = StatsCalculator()
