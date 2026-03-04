import pandas as pd
from database.db_manager import db_manager
from database.models import Trade
import logging

logger = logging.getLogger(__name__)

class StatsCalculator:
    def get_summary_stats(self):
        """
        Calcula estadísticas generales desde la base de datos de operaciones cerradas.
        """
        session = db_manager.Session()
        try:
            trades = session.query(Trade).filter(Trade.status == "CLOSED").all()
            
            if not trades:
                return {
                    "total_trades": 0,
                    "win_rate": 0.0,
                    "total_pnl": 0.0,
                    "profit_factor": 0.0,
                    "best_trade": 0.0,
                    "worst_trade": 0.0
                }
            
            # Convertir a DataFrame para cálculos rápidos
            df = pd.DataFrame([{
                'pnl_usdt': t.pnl_usdt,
                'pnl_pct': t.pnl_pct,
                'symbol': t.symbol
            } for t in trades])
            
            total_trades = len(df)
            winning_trades = df[df['pnl_usdt'] > 0]
            losing_trades = df[df['pnl_usdt'] <= 0]
            
            win_rate = (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0
            
            gross_profit = winning_trades['pnl_usdt'].sum() if not winning_trades.empty else 0
            gross_loss = abs(losing_trades['pnl_usdt'].sum()) if not losing_trades.empty else 0
            profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
            
            total_pnl = df['pnl_usdt'].sum()
            best_trade = df['pnl_usdt'].max()
            worst_trade = df['pnl_usdt'].min()
            
            return {
                "total_trades": total_trades,
                "win_rate": win_rate,
                "total_pnl": total_pnl,
                "profit_factor": profit_factor,
                "best_trade": best_trade,
                "worst_trade": worst_trade
            }
        except Exception as e:
            logger.error(f"Error calculando estadísticas: {e}")
            return None
        finally:
            session.close()

    def format_stats_message(self, stats):
        if not stats or stats["total_trades"] == 0:
            return "📊 <b>Estadísticas</b>\nNo hay operaciones cerradas aún."
            
        return f"""
📊 <b>REPORTE DE ESTADÍSTICAS</b> 📊

<b>Operaciones Totales:</b> {stats['total_trades']}
<b>Win Rate:</b> {stats['win_rate']:.2f}%
<b>Profit Factor:</b> {stats['profit_factor']:.2f}

<b>PnL Total:</b> {stats['total_pnl']:.2f} USDT
<b>Mejor Trade:</b> {stats['best_trade']:.2f} USDT
<b>Peor Trade:</b> {stats['worst_trade']:.2f} USDT
"""

stats_calculator = StatsCalculator()
