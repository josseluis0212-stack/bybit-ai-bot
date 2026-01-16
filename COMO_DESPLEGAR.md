# 🚀 GUÍA RÁPIDA: Subir Cambios a GitHub y Desplegar en Render

## ⚡ Problema Identificado
Los cambios que he hecho están en tu computadora local, pero **Render no los puede ver** porque no están en GitHub.

## 📋 Solución en 3 Pasos

### Paso 1️⃣: Subir a GitHub (Elige UNA opción)

#### **Opción A - VS Code (Recomendada)**
1. Abre VS Code en la carpeta `c:\Users\Usuario\Documents\policia\graviti bot`
2. Haz clic en el ícono de **Source Control** (rama de árbol) en la barra lateral izquierda
3. Verás una lista de archivos modificados
4. Haz clic en el **"+"** junto a cada archivo (o en "Stage All Changes")
5. Escribe un mensaje arriba: `v2.6 Premium - Alertas y Grid mejorados`
6. Haz clic en **"Commit"**
7. Haz clic en **"Sync Changes"** o **"Push"**

#### **Opción B - GitHub Desktop**
1. Descarga e instala GitHub Desktop: https://desktop.github.com/
2. Abre GitHub Desktop
3. Haz clic en **"Add an Existing Repository"**
4. Selecciona la carpeta: `c:\Users\Usuario\Documents\policia\graviti bot`
5. Verás los archivos modificados en la lista
6. Escribe un mensaje: `v2.6 Premium`
7. Haz clic en **"Commit to main"**
8. Haz clic en **"Push origin"**

### Paso 2️⃣: Desplegar en Render
1. Ve a tu panel de Render: https://dashboard.render.com/
2. Selecciona tu servicio `bit-ia-nuevo`
3. Haz clic en **"Manual Deploy"** (botón azul arriba a la derecha)
4. Selecciona **"Clear build cache & deploy"**
5. Espera 3-5 minutos a que termine el despliegue

### Paso 3️⃣: Verificar que Funciona
1. Abre Telegram
2. Deberías recibir el mensaje: **"🚀 BOT IA v2.6 Premium OPERATIVO"**
3. Si ves "v2.6 Premium", ¡funcionó! 🎉
4. Si NO ves "v2.6", repite el Paso 1 y 2

## 🔧 ¿Qué he mejorado en v2.6?

### ✅ Alertas Profesionales
- **Bot IA**: Ahora muestra Symbol, Dirección, Monto USDT, Leverage, Precio, SL y TP
- **Bot Grid**: Muestra Tendencia, Rango sugerido, Número de grids y análisis profesional

### ✅ Estadísticas D/W/M
- Al cerrar cada operación recibes: Win/Loss + PnL Real
- Reporte automático de rendimiento Diario, Semanal y Mensual

### ✅ Grid Imparable
- Ahora funciona con monedas nuevas (usa EMA 50 si no hay EMA 200)
- Filtros más permisivos para capturar tendencias emergentes

### ✅ Adiós "Error Desconocido"
- El bot ahora te dice el error REAL de Bybit (ej. saldo insuficiente, orden muy pequeña, etc.)

## 🆘 Si Tienes Problemas

Si después de seguir estos pasos sigues viendo errores:
1. Toma captura del mensaje de Telegram (debe decir "v2.6 Premium")
2. Toma captura de los logs de Render
3. Envíamelas y te ayudo a diagnosticar

---
**Nota**: Este archivo está en tu carpeta del bot para que lo consultes cuando quieras.
