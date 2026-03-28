---
name: Security & Risk Shield
description: Protocolos avanzados de ciberseguridad y gestión de riesgos técnicos para robots de trading.
---

# Skill: Security & Risk Shield

Esta skill implementa las capas de protección necesarias para operar en mercados financieros sin comprometer la seguridad de las claves o la estabilidad del capital.

## 🛡️ Capas de Seguridad (Bybit Bot)

### 1. Gestión Segura de Credenciales
- Uso obligatorio de archivos `.env` (no sincronizados a GitHub).
- Enmascaramiento de API Keys en logs y dashboards.
- Rotación periódica de secretos.

### 2. Protección de API & Dashboard
- Implementación de 'Sanitización' de entradas para evitar ataques XSS o Inyección SQL.
- Uso de CORS restringido para permitir solo el acceso desde el dominio de Render.

### 3. Gestión de Riesgo de Ejecución
- **Auto-Stop-Loss**: Verificación redundante de que cada posición tenga SL.
- **Panic Override**: El Botón de Pánico debe funcionar de forma aislada, sin depender del estado del bot para el cierre.
- **Leverage Caps**: Límites estrictos (hardcoded) de apalancamiento para evitar liquidaciones por errores de configuración.

## ⚙️ Auditoría Continua
- Registro de cada cambio de configuración crítico.
- Monitoreo de intentos de acceso no autorizados al endpoint de `/api`.
