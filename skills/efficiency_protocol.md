# ⚡ Protocolo de Eficiencia Extrema — Antigravity Quantum Efficiency v5.0
> **Scope:** GLOBAL | **Activación:** AUTOMÁTICA | Referencia completa en `policia/skills/efficiency_protocol.md`

## Reglas Clave (Resumen Bot)
1. **Zero-Waste**: Sin preámbulos, sin relleno, directo al código
2. **Smart Reads**: grep → view_file(rango) → edit. Máximo 2 archivos antes de actuar
3. **Parallel-First**: Todo en paralelo si no hay dependencias
4. **Cache Mental**: NO releer archivos ya conocidos en la conversación
5. **Edición Quirúrgica**: `replace_file_content` > reescritura total (>90% de los casos)

## Lecciones Aprendidas
- **Bybit `get_closed_pnl`**: mapeo manual en `params`
- **tickSize/qtyStep**: SIEMPRE `_format_step()` antes de enviar
- **EMA 100**: mínimo 120 velas (CANDLES_NEEDED=150)
- **Bybit klines**: reordenar ascending siempre
- **Leverage 110043**: ya configurado, ignorar
- **Render**: keep-alive cada 10 min (duerme a los 15)
- **Socket.IO**: handler después de `sio`
- **Logging Render**: `%(message)s` no `%message`

## Rutas Clave
- Dashboard: `dashboard/index.html`
- Motor: `execution_engine/executor.py`
- Estrategia: `strategy/market_scanner.py` + `strategy/ema_strategy.py`
- Config: `config/settings.py`
- Risk: `risk_management/risk_manager.py`

---
**ESTADO:** ACTIVO PERMANENTE | **VERSION:** 5.0
