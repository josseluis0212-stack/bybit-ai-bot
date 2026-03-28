---
name: Trading Quantum Institutional
description: Capacidad avanzada para el análisis de mercados financieros usando Smart Money Concepts (SMC), Perfil de Volumen (POC/VWAP) e Integración de Sentimiento (NLP).
---

# Trading Quantum Institutional Skill

Esta skill documenta los métodos de grado institucional para el análisis y ejecución automatizada en mercados de criptomonedas y forex.

## 💎 Estratégias Core

### 1. Smart Money Concepts (SMC)
- **Order Blocks (OB)**: Identificación de huellas institucionales en velas de alto desplazamiento con volumen relativo > 1.5x.
- **Fair Value Gaps (FVG)**: Detección de ineficiencias de precio (Imbalance) que actúan como imanes de retroceso.
- **Liquidity Sweeps**: Reconocimiento de barridos de máximos/mínimos previos (Inducement) antes de un movimiento real.

### 2. Quantum Volume Profile
- **Point of Control (POC)**: Nivel de precio con el mayor volumen negociado en un periodo (Fair Value institucional).
- **Value Area (VA)**: Rango donde ocurre el 70% del volumen. Las desviaciones fuera de la VA son oportunidades de regresión a la media.
- **VWAP (Volume Weighted Average Price)**: Ancla psicológica y algorítmica. Comprar por debajo (Discount) y vender por encima (Premium) en tendencias alineadas.

### 3. Machine Learning & NLP Sentiment (Propuesta Futura)
- **FinBERT Integration**: Procesamiento de noticias y tweets financieros para ajustar el sesgo (Bias) del bot.
- **XGBoost Classifier**: Utilizar las métricas de SMC como features para predecir la probabilidad de éxito de un setup antes de entrar.

## 🛠️ Implementación Técnica Recomendada
- **Lenguaje**: Python 3.10+
- **Librerías**: Pandas, NumPy, TA-Lib (filtros técnicos), aiohttp (ejecución asíncrona).
- **Infraestructura**: Despliegue en Cloud (Render/AWS) con sistema de Auto-Ping para evitar latencia y modo sleep.

## 🛡️ Gestión de Riesgo
- **Stop Loss Estructural**: Colocación detrás del último fractal validado.
- **Trailing Stop dinámico**: Asegurar beneficios tras un Break of Structure (BOS).
- **Filtro de Caos**: Desactivación durante eventos de alta volatilidad no estructural (Desviación Estándar > 2.5 sigma).
