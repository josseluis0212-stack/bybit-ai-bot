# 🧠 Núcleo de Memoria a Largo Plazo (Antigravity v4.1)

Este archivo es el registro persistente de las decisiones estratégicas, preferencias del usuario y lecciones aprendidas durante la operación del bot en la nube.

## ⚙️ Perfil del Usuario
- **Estrategia Preferida**: Institutional SMC Quantum v4.1.
- **Riesgo por Operación**: 2% (Apalancamiento x5).
- **Temporalidad Core**: 15m (Análisis) | 1H (HTF Bias).
- **Paridad Primaria**: USDT (Spot/Futures).

## 📜 Historial de Decisiones Estratégicas
- **[2026-03-28]**: Implementación de **Institutional SMC Quantum v4.0**. Se añadió el Point of Control (POC) y Volume Weighted Average Price (VWAP) para filtrar ruido.
- **[2026-03-28]**: Transición a **Antigravity Edition v4.1**. Se activó el Dashboard con pestañas de Analítica e Historial, y se añadió el **Botón de Pánico** de emergencia.
- **[2026-03-28]**: Creación de la **Biblioteca de Skills Avanzadas** (Order Flow, Sentiment, RL) para futuras expansiones.

## 💡 Lecciones Aprendidas (Insights)
- *Filtro de Caos*: La desviación estándar de 2.5x sobre la media móvil de 100 periodos es efectiva para evitar entradas en momentos de manipulación institucional.
- *POC Mirroring*: El precio tiende a gravitar hacia el POC de las últimas 24h el 70% de las veces; las entradas tipo 'Sniper' deben buscarse exclusivamente fuera del POC (zonas de desequilibrio).

## 📌 Notas de Configuración
- Render Instance: `bybit-ai-bot-kr6d`.
- Database: SQLite (`database/trading_bot.db`).
- Notificaciones: Telegram activo para reportes periódicos.
