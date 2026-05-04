import sys
import os
import json
from datetime import datetime

# Add the project root to the path
sys.path.append(r'c:\Users\Usuario\Documents\GitHub\bybit-ai-bot')

from api.bybit_client import bybit_client
from config.settings import settings

def main():
    print(f"Demo Mode: {settings.BYBIT_DEMO}")
    
    # Get wallet balance
    balance = bybit_client.get_wallet_balance()
    if balance and balance.get('retCode') == 0:
        list_data = balance.get('result', {}).get('list', [])
        if list_data:
            total_equity = list_data[0].get('totalEquity', '0')
            total_wallet_balance = list_data[0].get('totalWalletBalance', '0')
            print(f"Total Equity: {total_equity} USDT")
            print(f"Total Wallet Balance: {total_wallet_balance} USDT")
    else:
        print("Failed to get wallet balance.")
        
    # Get recent closed PNL
    print("\nRecent Closed PNL:")
    closed_pnl = bybit_client.get_closed_pnl(limit=50)
    if closed_pnl and closed_pnl.get('retCode') == 0:
        pnl_list = closed_pnl.get('result', {}).get('list', [])
        total_pnl = 0.0
        win_count = 0
        loss_count = 0
        
        if not pnl_list:
            print("No recent closed PnL records found.")
        else:
            for item in pnl_list:
                symbol = item.get('symbol')
                closed_pnl_val = float(item.get('closedPnl', 0))
                closed_size = item.get('closedSize')
                created_time = datetime.fromtimestamp(int(item.get('createdTime', 0))/1000).strftime('%Y-%m-%d %H:%M:%S')
                
                print(f"{created_time} | {symbol} | PnL: {closed_pnl_val:.4f} | Size: {closed_size}")
                total_pnl += closed_pnl_val
                if closed_pnl_val > 0:
                    win_count += 1
                else:
                    loss_count += 1
                    
            print("\nSummary:")
            print(f"Total trades in this batch: {len(pnl_list)}")
            print(f"Wins: {win_count}, Losses: {loss_count}")
            print(f"Total PnL in this batch: {total_pnl:.4f} USDT")
    else:
        print("Failed to get closed PnL.")

if __name__ == '__main__':
    main()
