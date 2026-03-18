# Guía para Mantener el Bot 24/7 en la Nube (Hugging Face / Render)

Debido a que estás usando el **Plan Gratuito** de plataformas como **Hugging Face Spaces** o **Render**, tu bot se "duerme" (suspende) automáticamente si nadie está viendo el Dashboard durante un tiempo. Por eso parece que "deja de funcionar" cuando apagas tu PC.

Para que funcione siempre (incluso con tu PC apagada), sigue estos pasos:

### 1. Obtén tu URL de la plataforma
- **Si es Hugging Face (Spaces):** La URL suele ser algo como `https://<usuario>-<nombre-del-espacio>.hf.space`
- **Si es Render:** `https://bybit-ai-bot-kr6d.onrender.com`

### 2. Configura UptimeRobot (Gratis)
1. Ve a [UptimeRobot.com](https://uptimerobot.com/) y crea una cuenta gratuita.
2. Haz clic en **"Add New Monitor"**.
3. Configura lo siguiente:
   - **Monitor Type**: HTTP(s)
   - **Friendly Name**: Trading Bot Keep-Alive
   - **URL (or IP)**: Inserta aquí la URL de tu Space o Render.
   - **Monitoring Interval**: Every 5 minutes.
4. Haz clic en **"Create Monitor"**.

### ¿Qué hace esto?
UptimeRobot visitará tu bot cada 5 minutos. Render detectará este "tráfico" y **nunca suspenderá la instancia**, permitiendo que el bucle de trading siga funcionando 24/7 sin que tengas que dejar tu PC encendida.

---

> [!TIP]
> Si prefieres algo más profesional y sin depender de servicios externos, puedes cambiar el plan de Render de **"Free"** a **"Starter"** ($7 USD/mes) o usar un **"Background Worker"**, pero la solución de UptimeRobot es la mejor forma de hacerlo 100% gratis.
