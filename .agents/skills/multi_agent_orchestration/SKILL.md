---
name: Multi-Agent Orchestration & Parallel Execution
description: Capacidad para dividir tareas complejas en sub-tareas, despacharlas en paralelo (Scatter-Gather) a múltiples hilos o sub-agentes, y sintetizar los resultados rápidamente.
---

# Skill: Multi-Agent Orchestration

Esta skill permite al bot actuar como un "Controlador" o "Manager", delegando tareas y operando a extrema velocidad sin bloqueos secuenciales.

## 🤖 Patrones de Orquestación (Agentic Patterns)

### 1. Scatter-Gather (Ejecución en Paralelo)
- **Uso**: Escaneo rápido de mercado o recolección masiva de datos web.
- **Implementación**: En Python, usar `asyncio.gather()` o `concurrent.futures.ThreadPoolExecutor` para disparar N llamadas API o búsquedas simultáneas.
- **Síntesis**: Un "Reducer Agent" recopila los N resultados y los combina en una única respuesta o decisión.

### 2. Hierarchical Worker-Manager
- **Uso**: Proyectos complejos (ej. escribir una nueva estrategia de trading mientras se revisa la base de datos).
- **Implementación**: El Agent Manager subdivide el Promt inicial en una lista de Tareas (Task Tree). Los Workers resuelven nodo por nodo.

### 3. Multi-Intent Threading
- Si el usuario envía un request con 3 órdenes (ej: "esanea monedas, busca skills y guarda esto"), el agente debe ser capaz de procesar las 3 de manera concurrente, en lugar de secuencial.

## ⚡ Incremento de Velocidad
El objetivo principal de esta skill es reducir la latencia (espera del usuario) al mínimo, demostrando una eficiencia "Anti-Gravedad" extrema.
