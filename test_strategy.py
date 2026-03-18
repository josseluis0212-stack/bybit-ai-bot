import asyncio
from strategy.market_scanner import market_scanner

async def main():
    print("--- PRUEBA DE SCANNER DE MERCADO Y ESTRATEGIA ---")
    
    # 1. Probar carga de velas individuales
    print("\n1. Obteniendo datos para BTCUSDT...")
    df = await market_scanner.get_klines_as_df('BTCUSDT')
    if df is not None and not df.empty:
        print(f"[OK] Se obtuvieron {len(df)} velas de 15m para BTCUSDT.")
        print("Última vela (timestamp, close):", df.iloc[-1]['timestamp'], df.iloc[-1]['close'])
    else:
        print("[ERROR] No se obtuvieron datos.")
        
    # 2. Probar el Scanner Completo (Escaneo GLOBAL)
    print("\n2. Iniciando Escaneo GLOBAL de todos los pares USDT de Bybit...")
    signals = await market_scanner.scan_market()
    
    if signals:
        print(f"\n[OK] Se encontraron {len(signals)} señales:")
        for s in signals:
            print(f" -> {s['symbol']}: {s['signal']} @ {s['entry_price']} | SL: {s['sl']:.4f} TP: {s['tp']:.4f}")
    else:
        print("\n[OK] El escaneo finalizó, pero no se encontraron señales en este momento.")

if __name__ == '__main__':
    asyncio.run(main())
