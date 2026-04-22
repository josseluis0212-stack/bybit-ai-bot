# AGENTS.md - Configuración de OpenCode

## Configuración del Bot

- **Monedas analizadas:** 100 (por volumen)
- **Volumen mínimo:** 330,000 USDT
- **Máximo operaciones simultáneas:** 10
- **Margen por operación:** $20
- **Apalancamiento:** 10x

## Comandos Git

```bash
# Commit y push
git add . && git commit -m "mensaje" && git push origin main

# Force push (peligroso)
git push origin main --force
```

## Estructura del Proyecto

```
bybit-ai-bot/
├── config/settings.py      # Config principal
├── strategy/
│   ├── market_scanner.py  # Escaneo de mercado
│   └── base_strategy.py # Lógica de señales
├── execution_engine/
│   └── executor.py      # Ejecución de trades
├── api/bybit_client.py  # Cliente API
└── risk_management/     # Gestión de riesgo
```