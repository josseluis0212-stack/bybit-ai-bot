# 🧠 Protocolo de Eficiencia Cuántica (Antigravity Skill)

Este documento define el estándar de operación para optimizar el consumo de recursos (tokens), simplificar la lógica y acelerar el desarrollo del bot de trading.

## 1. 🚀 Optimización de Tokens (Ahorro de Energía)
*   **Lectura Focalizada:** Antes de realizar cambios, leer solo las líneas necesarias usando `view_file` con `StartLine` y `EndLine`.
*   **Ediciones Modulares:** Priorizar `replace_file_content` sobre reescrituras totales. Si un archivo es >200 líneas, usar chunks precisos.
*   **Caché de Contexto:** Consultar `long_term_memory.md` y este protocolo antes de cada tarea para evitar redundancia en investigación.

## 2. ⚡ Simplificación de Procesos
*   **Encadenamiento de Comandos:** Usar `;` para ejecutar múltiples comandos de Git o sistema en una sola llamada de herramienta.
*   **Validación Local Previa:** Antes de subir a Render, verificar sintaxis localmente si es posible.
*   **Automatización de Diagnóstico:** Usar scripts de `policia/` (ej: `verify_scanner.py`) para chequeos rápidos en lugar de análisis manual extenso.

## 3. 💾 Persistencia de Conocimiento
*   **Documentación Activa:** Cada bug crítico resuelto (ej: error de argumentos en Bybit API) debe quedar registrado en este protocolo como "Lección Aprendida".
*   **Mapeo de Rutas:** Guardar rutas absolutas de archivos clave para evitar `list_dir` innecesarios.
    - Dashboard: `dashboard/index.html`
    - Motor: `execution_engine/executor.py`
    - Estrategia: `strategy/market_scanner.py`

## 4. 🛠️ Lecciones Aprendidas (Cache de Errores)
*   **[2026-04-27] Error de API Bybit:** `get_closed_pnl` no soporta `symbol` por defecto en la clase base; requiere mapeo manual en `params`.
*   **[2026-04-27] Logging en Render:** Evitar placeholders tipo `%message`; usar `%(message)s` para compatibilidad total con Python logging.
*   **[2026-04-27] Socket.IO:** Siempre inicializar el handler después del objeto `sio` para evitar errores de referencia circular.

---
**ESTADO:** ACTIVO | **VERSION:** 1.0
**ORDEN:** Aplicar estos principios en cada interacción futura para maximizar la velocidad de respuesta.
