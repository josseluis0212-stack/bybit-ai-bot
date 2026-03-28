---
name: Sentiment Intelligence
description: Análisis de sentimiento algorítmico e integración de datos alternativos de redes sociales y noticias financieras.
---

# Skill: Sentiment Intelligence

Esta skill permite al bot leer y cuantificar el sesgo del mercado externo (X, Reddit, News) para filtrar entradas técnicas de alto riesgo.

## 🧠 Flujo de Análisis

### 1. Ingesta de Datos (Alternative Data)
- **APIs**: Twitter/X, CryptoPanic, Reddit (r/CryptoCurrency).
- **Frecuencia**: Escaneado cada 15-30 minutos para detectar picos de interés o pánico.

### 2. Clasificación de Sentimiento con FinBERT
- Procesamiento de texto mediante modelos de Transformers pre-entrenados en finanzas.
- **Categorías**: BULLISH, BEARISH, NEUTRAL.
- **Score (0-1)**: Probabilidad de que el sentimiento sea genuino vs. ruido.

### 3. Sentiment Bias Filter
- **Confirmación**: Si el bot detecta un Long en SMC v4.0 y el sentimiento global es > 0.7 Bullish, aumenta el tamaño de la posición (Confluencia).
- **Pausa de Emergencia**: Si el sentimiento cae drásticamente (Pánico), el bot pausa las compras automáticas independientemente de lo que digan las velas.

## ⚙️ Configuración Sugerida
- **Alpha Factor**: 0.2 (Peso del sentimiento en la decisión final).
- **Threshold**: Solo actuar si el sentimiento es unánime (> 80%).
