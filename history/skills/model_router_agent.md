# Skill: Model Router Agent

## Rol
**Gateway Controller** - Gestionar múltiples modelos de lenguaje y conmutar automáticamente cuando uno se queda sin créditos.

## Agentes que Controlas

| Modelo | API Endpoint | Créditos iniciales | Costo por tarea | Prioridad |
|--------|--------------|--------------------|-----------------|-----------|
| GPT-4 | openai/gpt-4 | 100 | 1 crédito | 1 (alta) |
| Claude-3 | anthropic/claude-3 | 50 | 0.8 crédito | 2 |
| Gemini-Pro | google/gemini-pro | 200 | 0.5 crédito | 3 |
| Llama-3-local | localhost:8000 | ∞ (ilimitado) | 0 | 4 (fallback) |

## Variables de Estado

```python
model_credits = {
    "gpt-4": 100,
    "claude-3": 50,
    "gemini-pro": 200,
    "llama-3-local": float('inf')
}

model_in_use = "gpt-4"  # empieza con el mejor
tasks_executed = 0
total_credits_consumed = 0
```

## Lógica de Conmutación

### 1. Selección de Modelo
- Usar siempre el modelo de mayor prioridad con créditos disponibles
- Si el modelo actual se queda sin créditos, conmutar al siguiente de mayor prioridad

### 2. Verificación de Créditos
```python
def can_use_model(model_name):
    credits = model_credits.get(model_name, 0)
    if credits == float('inf'):
        return True
    return credits > 0
```

### 3. Conmutación Automática
```python
def switch_to_best_available():
    priorities = [("gpt-4", 1), ("claude-3", 2), ("gemini-pro", 3), ("llama-3-local", 4)]
    
    for model, _ in sorted(priorities, key=lambda x: x[1]):
        if can_use_model(model):
            model_in_use = model
            return model
    
    return "llama-3-local"  # fallback final
```

### 4. Ejecución de Tarea
```python
def execute_task(task_fn, *args, **kwargs):
    global tasks_executed, total_credits_consumed
    
    model = model_in_use
    cost = get_model_cost(model)
    
    if model_credits[model] < cost:
        model = switch_to_best_available()
    
    result = task_fn(*args, **kwargs)
    
    # Actualizar créditos
    if model_credits[model] != float('inf'):
        model_credits[model] -= cost
        total_credits_consumed += cost
    
    tasks_executed += 1
    return result
```

## Funciones Auxiliarias

```python
def get_model_cost(model_name):
    costs = {"gpt-4": 1, "claude-3": 0.8, "gemini-pro": 0.5, "llama-3-local": 0}
    return costs.get(model_name, 1)

def get_status():
    return {
        "model_in_use": model_in_use,
        "credits": model_credits,
        "tasks_executed": tasks_executed,
        "total_consumed": total_credits_consumed
    }

def reset_credits():
    global model_credits
    model_credits = {
        "gpt-4": 100,
        "claude-3": 50,
        "gemini-pro": 200,
        "llama-3-local": float('inf')
    }
```
