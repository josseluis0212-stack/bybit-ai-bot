---
name: Order Flow Profiling & CVD
description: Capacidad técnica para el análisis de microestructura de mercado, incluyendo Desequilibrio de Órdenes (OFI) y Delta Acumulado (CVD).
---

# Skill: Order Flow Profiling & CVD

Esta skill otorga al bot la capacidad de leer la "cinta" y el libro de órdenes para anticipar movimientos de precio de alta probabilidad antes de que se reflejen en las velas OHLC.

## 📊 Componentes Técnicos

### 1. Order Flow Imbalance (OFI)
El bot debe calcular el cambio neto en la profundidad de las órdenes a nivel 2.
- **Fórmula**: `OFI = ΔBidSize - ΔAskSize`.
- **Uso**: Un OFI positivo fuerte indica presión de compra institucional inminente.

### 2. Cumulative Volume Delta (CVD)
Análisis de órdenes de mercado ejecutadas (agresivas).
- **Delta Divergence**: Si el precio marca un nuevo máximo pero el CVD está bajando, existe una divergencia bajista (Agotamiento).
- **Absorption**: Si el CVD sube agresivamente pero el precio no se mueve, las órdenes de mercado están siendo absorbidas por órdenes limitadas contrarias.

### 3. Footprint Chart Integration
- Visualización de volumen negociado por cada tick de precio dentro de una vela.
- **POC del Footprint**: El nivel de precio exacto con mayor volumen en la vela actual.

## 🛠️ Implementación Recomendada
Integrar WebSockets de alta velocidad para recibir `orderbook` y `trades` en tiempo real de Bybit.
- **Bucket Size**: 1 segundo o por Volumen (Velas de Volumen Constante).
