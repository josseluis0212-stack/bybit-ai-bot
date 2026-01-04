# Guía de Despliegue: Bot IA en Oracle Cloud (24/7 Gratis)

Esta guía te ayudará a poner tu bot en funcionamiento permanente sin costo.

## Paso 1: Registro en Oracle Cloud
1. Ve a [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/).
2. Haz clic en **"Start for free"**.
3. Completa el registro. **Importante**: Necesitarás una tarjeta de crédito/débito para verificar tu identidad. No te cobrarán nada, es solo para evitar bots.

## Paso 2: Crear la Instancia (Servidor)
Una vez dentro de tu panel de Oracle:
1. Ve a **Compute** > **Instances**.
2. Haz clic en **Create Instance**.
3. **Nombre**: Ponle `Bot-Trading-IA`.
4. **Image and Shape**:
   - Haz clic en **Edit**.
   - En **Image**, selecciona **Ubuntu 22.04** (es la más estable).
   - En **Shape**, selecciona **Ampere (Arm)**. Si está disponible, elige **4 OCPUs y 24 GB de RAM** (es el máximo gratuito). Si no, usa la opción por defecto de AMD.
5. **Networking**: Deja todo por defecto, pero asegúrate de que diga "Assign a public IPv4 address".
6. **SSH Keys**: Haz clic en **Save Private Key**. **¡NO PIERDAS ESTE ARCHIVO!** Lo necesitaremos para entrar al servidor.
7. Haz clic en **Create**.

## Paso 3: Abrir Puertos (Para ver el Dashboard)
Para que puedas entrar a la web del bot desde tu casa:
1. En la página de tu instancia, haz clic en la **Subnet** (en la sección de Primary VNIC).
2. Haz clic en **Default Security List**.
3. Haz clic en **Add Ingress Rules**.
4. Configura así:
   - **Source CIDR**: `0.0.0.0/0`
   - **IP Protocol**: `TCP`
   - **Destination Port Range**: `5000`
   - **Description**: `Dashboard Bot`
5. Haz clic en **Add Ingress Rules**.

## Paso 4: Conectar y Ejecutar
Cuando la instancia diga **"Running"**, avísame y te daré los comandos finales para subir el código y encender el bot.

---
> [!TIP]
> Si tienes problemas con el registro de la tarjeta, asegúrate de que tenga habilitadas las compras internacionales. Oracle hace un cargo de prueba de ~1 USD que se devuelve de inmediato.
