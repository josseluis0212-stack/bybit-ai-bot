# Historial de Cambios - Bybit AI Bot

## 2026-04-22

### Estrategia V9 (Guardada)
- **Estrategia:** Hyper-Quant Ultra V9 - Precision Scalper
- **Timeframes:** 15m (Bias) + 1m (Execution)
- **Indicadores:** EMA (100, 20), RSI (14), ATR (14)
- **Entry:** SMC Sweep + FVG o Pullback EMA 20
- **Risk:** SL 1.5x ATR, TP 3.0x ATR (Ratio ~2:1)

### Configuración Actual
- **Monedas analizadas:** 100 (ordenadas por volumen)
- **Volumen mínimo:** 330,000 USDT
- **Máximo operaciones:** 10 simultáneas
- **Margen por trade:** $20
- **Apalancamiento:** 10x
- **Cooldown tras pérdida:** 30 minutos
- **Break-even:** 1.5:1 RR

### Archivos Guardados en history/
- `strategy_v9.py` - Estrategia V9 completa
- `executor_current.py` - Motor de ejecución actual
- `settings_current.py` - Configuración actual

### Archivos Modificados
- `config/settings.py` - MAX_CONCURRENT_TRADES = 10
- `strategy/market_scanner.py` - Filtro volumen mínimo 330k + top 100
- `execution_engine/executor.py` - Código de ejecución

### Documentación
- `AGENTS.md` - Creado con configuración y estructura del proyecto

---

## Notas
- Usar `git add . && git commit -m "mensaje" && git push origin main` para guardar cambios
- Para sobrescribir remoto: `git push origin main --force`
