# Alternativas de Nube SIN TARJETA (24/7)

Si no puedes usar una tarjeta, estas son las mejores opciones para que el bot no se detenga:

## Opción 1: Koyeb (La mejor opción sin tarjeta)
Koyeb es una plataforma moderna que permite subir el bot usando Docker (el archivo que ya creamos).

1. **Registro**: Ve a [Koyeb.com](https://www.koyeb.com/).
2. **Plan**: Elige el plan **"Hobby"**. Normalmente no pide tarjeta si te registras con GitHub o si tu ubicación no está marcada como riesgo.
3. **Ventaja**: Permite ejecutar procesos continuos.
4. **Cómo subirlo**: Usaremos el botón "Deploy with GitHub".

## Opción 2: Render + Ping (Truco para mantenerlo despierto)
Render es muy fácil de usar y **nunca** pide tarjeta para el plan gratuito. El problema es que se "duerme" si nadie entra a la web.

1. **Registro**: Ve a [Render.com](https://render.com/).
2. **Truco**: Usaremos un servicio gratuito llamado `cron-job.org` para que "llame" a la web del bot cada 5 minutos. Esto engaña a Render y hace que el bot **nunca se duerma**.
3. **Cómo subirlo**: Conectas tu cuenta de GitHub y listo.

## Opción 3: PythonAnywhere (Limitado pero seguro)
Es la opción más clásica para Python. No pide tarjeta.

1. **Registro**: Ve a [PythonAnywhere.com](https://www.pythonanywhere.com/).
2. **Limitación**: El plan gratuito solo permite una web. Tendríamos que modificar un poco el bot para que el "escaneo" de monedas ocurra dentro de la web, lo cual es un poco más lento.

---

### 💡 Mi recomendación:
Intenta primero con **Koyeb**. Si te deja registrarte sin tarjeta, es la opción más profesional y potente para tu bot.

**¿Cuál quieres intentar primero?**
1. Intentar con **Koyeb**.
2. Intentar con **Render** (y yo te enseño el truco del ping).
