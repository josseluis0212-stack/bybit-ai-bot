import os
import sys
import time
sys.path.append(os.getcwd())
from api.bybit_client import bybit_client

def analyze():
    now = int(time.time() * 1000)
    last_hour = now - (60 * 60 * 1000)
    resp = bybit_client.get_closed_pnl(limit=50, start_time=last_hour)
    
    if not resp or resp.get("retCode") != 0:
        print(f"Error Bybit: {resp}")
        return

    trades = resp['result']['list']
    print(f"--- ANALISIS DE ULTIMA HORA ({len(trades)} trades) ---")
    total_pnl = 0
    for t in trades:
        pnl = float(t['closedPnl'])
        total_pnl += pnl
        print(f"{t['symbol']} | PnL: {pnl:+.4f} | OrderType: {t.get('orderType', 'N/A')} | Reason: {t.get('execType', 'N/A')}")
    
    print("-" * 30)
    print(f"TOTAL PNL REAL (BYBIT): {total_pnl:+.2f} USDT")
    print(f"RENTABILIDAD: {'POSITIVA ✅' if total_pnl > 0 else 'NEGATIVA ❌'}")

if __name__ == "__main__":
    analyze()
