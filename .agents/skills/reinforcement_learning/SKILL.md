---
name: Reinforcement Learning Optimizations
description: Optimización de estrategias y parámetros técnicos mediante aprendizaje por refuerzo y algoritmos probabilísticos.
---

# Skill: Reinforcement Learning Optimizations (RLO)

Esta skill dota al bot con la capacidad de auto-ajuste de parámetros (Hyperparameter Tuning) basado en los resultados de operaciones pasadas.

## 📈 Lógica de Aprendizaje

### 1. Recompensa (Reward)
- **Positive Reward (+1)**: Operación en Take Profit (TP).
- **Negative Reward (-2)**: Operación en Stop Loss (SL).
- **Neutral (0)**: Operación cerrada en breakeven o neutral.

### 2. Estados de Mercado (State)
- **Varianza**: Volatilidad de las últimas 24h.
- **Tendencia**: EMA 200 (BULL/BEAR).
- **Regime**: Normal/Chaotic.

### 3. Agente de Optimización (DQN / PPO)
- Ajusta dinámicamente el `min_iss` y el `margin_per_trade` para reflejar la probabilidad de acierto del mercado actual.
- **Aprendizaje Continuo**: El bot no es estático, evoluciona junto con el mercado.

## 🚀 Implementación Técnica Recomendada
- Uso de `Gym` de OpenAI para simulaciones (backtesting) con el agente de RL en local antes de aplicar los cambios en Bybit.
- **Factor de Exploración (Epsilon)**: 0.1 (Explora nuevas combinaciones de parámetros un 10% del tiempo).
