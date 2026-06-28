import asyncio
from app.exchange.bybit_client import AsyncBybitClient
from app.strategy.antigravity_v13_pro import evaluate_antigravity_v13
from app.strategy.supertrend_regime import evaluate_supertrend_regime

async def run_backtest():
    client = AsyncBybitClient()
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    
    print("Iniciando Backtest Rápido...")
    print("===============================")
    for sym in symbols:
        print(f"\nEvaluando {sym}...")
        
        # Test Antigravity
        try:
            ag_res = await evaluate_antigravity_v13(client, sym)
            print(f"[AntigravityV13] {sym}: Señal -> {ag_res.get('signal')}")
            if ag_res.get("signal") != "NONE":
                print(f"   Detalles: {ag_res}")
        except Exception as e:
            print(f"[AntigravityV13] Error en {sym}: {e}")
            
        # Test SuperTrend
        try:
            st_res = await evaluate_supertrend_regime(client, sym)
            print(f"[SuperTrendRegime] {sym}: Señal -> {st_res.get('signal')}")
            if st_res.get("signal") != "NONE":
                print(f"   Detalles: {st_res}")
        except Exception as e:
            print(f"[SuperTrendRegime] Error en {sym}: {e}")

    await client.close()

if __name__ == "__main__":
    asyncio.run(run_backtest())
