import sqlite3
import pandas as pd
from datetime import datetime, timedelta

def analyze_trades(db_path):
    # If using SQLAlchemy, let's just use sqlite3 for simplicity in the script
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"Tablas encontradas: {tables}")
    
    try:
        df = pd.read_sql_query("SELECT * FROM trades", conn)
        print(f"Total de operaciones registradas: {len(df)}")
        
        if len(df) > 0:
            # Basic stats
            if 'status' in df.columns:
                print("\nEstado de las operaciones:")
                print(df['status'].value_counts())
            
            if 'close_reason' in df.columns:
                print("\nRazones de cierre:")
                print(df['close_reason'].value_counts())
                
            if 'pnl_usdt' in df.columns:
                print(f"\nPnL Total USDT: {df['pnl_usdt'].sum():.2f}")
                print(f"PnL Promedio por trade: {df['pnl_usdt'].mean():.2f}")
            
            # Daily, Weekly, Monthly stats
            if 'close_time' in df.columns and df['close_time'].notnull().any():
                df['close_time'] = pd.to_datetime(df['close_time'])
                
                # Daily
                daily = df.set_index('close_time').resample('D')['pnl_usdt'].sum()
                print("\nEstadísticas Diarias (Últimos 7 días):")
                print(daily.tail(7))
                
                # Weekly
                weekly = df.set_index('close_time').resample('W')['pnl_usdt'].sum()
                print("\nEstadísticas Semanales:")
                print(weekly.tail(4))
                
                # Monthly
                monthly = df.set_index('close_time').resample('M')['pnl_usdt'].sum()
                print("\nEstadísticas Mensuales:")
                print(monthly.tail(3))
            
            # Analizar perdedoras (STOP LOSS)
            losing_trades = df[df['close_reason'] == 'STOP LOSS']
            print(f"\nOperaciones liquidadas por STOP LOSS: {len(losing_trades)}")
            if len(losing_trades) > 0:
                print("Símbolos con más pérdidas:")
                print(losing_trades['symbol'].value_counts().head(5))

    except Exception as e:
        print(f"Error al analizar la base de datos: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    db_path = r'c:\Users\Usuario\Documents\GitHub\bybit-ai-bot\database\trading_bot.db'
    analyze_trades(db_path)
