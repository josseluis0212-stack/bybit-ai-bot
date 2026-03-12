"""
Test en vivo: Envia mensaje a Telegram y escanea los TOP 5 mercados.
"""
import asyncio
import sys
import logging

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

async def main():
    from config.settings import settings
    from api.bybit_client import bybit_client
    from notifications.telegram_bot import telegram_notifier
    from strategy.market_scanner import market_scanner
    from strategy.base_strategy import strategy

    # =========================================================
    # PRUEBA 1: TELEGRAM
    # =========================================================
    logger.info("=== PRUEBA 1: ENVIANDO MENSAJE A TELEGRAM ===")
    msg = (
        "<b>BOT DE TRADING PRO - TEST EN VIVO</b>\n\n"
        "<b>Estado:</b> Conectado y operativo\n"
        "<b>Modo:</b> Demo (Bybit Testnet)\n"
        "<b>Estrategia:</b> Trend-Pullback (EMA 200/21 + RSI 14 + ATR)\n"
        "<b>Apalancamiento:</b> 5x\n"
        "<b>Capital/Trade:</b> 100 USDT\n"
        "<b>Max Trades:</b> 10 simultaneos\n\n"
        "Iniciando escaneo de mercados..."
    )
    ok = await telegram_notifier.send_message(msg)
    if ok:
        logger.info("[OK] Mensaje enviado a Telegram correctamente.")
    else:
        logger.error("[ERROR] Fallo al enviar mensaje a Telegram. Revisa .env")

    # =========================================================
    # PRUEBA 2: BALANCE EN BYBIT DEMO
    # =========================================================
    logger.info("=== PRUEBA 2: BALANCE EN BYBIT DEMO ===")
    balance = bybit_client.get_wallet_balance()
    balance_usdt = 0.0
    if balance and balance.get('retCode') == 0:
        coins = balance['result']['list'][0]['coin']
        usdt = next((c for c in coins if c['coin'] == 'USDT'), None)
        if usdt:
            balance_usdt = float(usdt['walletBalance'])
            logger.info(f"[OK] Balance USDT en Bybit Demo: {balance_usdt:.2f} USDT")
        else:
            logger.warning("[WARN] No se encontro coin USDT. La cuenta demo puede estar vacia.")
    else:
        logger.error(f"[ERROR] No se pudo obtener el balance: {balance}")

    # =========================================================
    # PRUEBA 3: ESCANEO DE TODOS LOS MERCADOS
    # =========================================================
    logger.info("=== PRUEBA 3: ESCANEANDO TODOS LOS MERCADOS ===")
    tickers = bybit_client.get_tickers()
    signals_found = []

    if tickers:
        logger.info(f"Total pares encontrados: {len(tickers)}")
        logger.info("\nAnalizando estrategia en todos los mercados...")
        for item in tickers:
            sym = item['symbol']
            df = await market_scanner.get_klines_as_df(sym)
            if df is not None and not df.empty:
                sig = strategy.analyze(sym, df)
                if sig:
                    logger.info(f"  *** SENAL ENCONTRADA: {sig['signal']} en {sym} @ {sig['entry_price']:.4f} | SL:{sig['sl']:.4f} TP:{sig['tp']:.4f}")
                    signals_found.append(sig)
                else:
                    logger.info(f"  {sym}: Sin senal en este momento.")
            await asyncio.sleep(0.3)
    else:
        logger.error("[ERROR] No se pudieron cargar los tickers de Bybit.")

    # =========================================================
    # REPORTE FINAL POR TELEGRAM
    # =========================================================
    logger.info("=== ENVIANDO REPORTE FINAL A TELEGRAM ===")
    if signals_found:
        sigs_txt = ""
        for s in signals_found:
            sigs_txt += f"\n<b>{s['symbol']}</b>: {s['signal']} @ {s['entry_price']:.4f}"
        reporte = (
            f"<b>RESULTADO DEL ESCANEO (Todos)</b>\n\n"
            f"<b>Senales encontradas:</b> {len(signals_found)}"
            f"{sigs_txt}\n\n"
            f"<b>Balance Demo:</b> {balance_usdt:.2f} USDT"
        )
    else:
        reporte = (
            f"<b>RESULTADO DEL ESCANEO (Todos)</b>\n\n"
            f"Sin senales de entrada en este momento.\n"
            f"El mercado no cumple las condiciones de la estrategia Trend-Pullback.\n\n"
            f"<b>Balance Demo:</b> {balance_usdt:.2f} USDT\n"
            f"<b>Estado:</b> Bot monitoreando activamente..."
        )
    await telegram_notifier.send_message(reporte)
    logger.info("[LISTO] Prueba completada. Revisa Telegram para ver los mensajes.")

if __name__ == '__main__':
    asyncio.run(main())
