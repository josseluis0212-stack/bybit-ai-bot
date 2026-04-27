---
title: Bybit AI Bot Institutional v5.3
emoji: 📈
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# Bybit AI Bot Institutional v5.3 (Quantum Evolution)

Sistema avanzado de trading algorítmico para Bybit optimizado para Hugging Face Spaces.

## 🚀 Despliegue en Hugging Face
1. Crea un nuevo **Space** en Hugging Face.
2. Selecciona **Docker** como SDK.
3. Conecta este repositorio de GitHub.
4. Configura los **Secrets** en la configuración del Space (API Keys, etc.).

## ⚙️ Configuración Requerida (Secrets)
- `BYBIT_API_KEY`
- `BYBIT_API_SECRET`
- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`
- `IS_TESTNET` (true/false)

## 💎 Características v5.3
- **Estrategia SMC:** Order Blocks + Liquidity Sweeps.
- **Filtro HTF:** Bias institucional matemático.
- **Eficiencia:** Post-Only y Breakeven+ dinámico.
