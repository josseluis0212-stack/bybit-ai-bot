# Alternativas de Nube Gratuita (24/7)

Si Oracle Cloud no permitió el registro, aquí tienes las dos mejores alternativas profesionales:

## Opción A: Google Cloud (Siempre Gratis)
Google ofrece una computadora pequeña que es **gratis para siempre** en ciertas regiones de EE.UU.

1. **Registro**: Ve a [Google Cloud Free Tier](https://cloud.google.com/free).
2. **Crédito de Regalo**: Te dan $300 USD para usar en los primeros 90 días, pero después la instancia `e2-micro` sigue siendo gratis.
3. **Configuración**:
   - Crea un proyecto nuevo.
   - Ve a **Compute Engine** > **VM Instances**.
   - Haz clic en **Create Instance**.
   - **Región**: Elige `us-central1` (Iowa), `us-east1` (South Carolina) o `us-west1` (Oregon). **Solo estas son gratis**.
   - **Machine Type**: Busca `e2-micro` (2 vCPU, 1 GB RAM). Dirá "Free tier eligible".
   - **Boot Disk**: Elige "Ubuntu 22.04 LTS".
   - **Firewall**: Marca "Allow HTTP traffic" y "Allow HTTPS traffic".

## Opción B: AWS - Amazon Web Services (12 Meses Gratis)
Amazon te da un servidor más potente que el de Google, pero solo por **1 año**.

1. **Registro**: Ve a [AWS Free Tier](https://aws.amazon.com/free/).
2. **Configuración**:
   - Ve a **EC2** > **Launch Instance**.
   - **Nombre**: `Bot-Trading-Bybit`.
   - **AMI**: Selecciona "Ubuntu Server 22.04 LTS" (Free tier eligible).
   - **Instance Type**: Selecciona `t2.micro` (o `t3.micro` si está disponible en tu región).
   - **Key Pair**: Crea uno nuevo y descarga el archivo `.pem`.
   - **Network Settings**: Asegúrate de permitir tráfico SSH y HTTP.

---

### ⚠️ Nota Importante sobre la Tarjeta
Todas las nubes profesionales (Google, AWS, Azure, Oracle) **siempre** piden una tarjeta para verificar que no eres un bot. No cobran por el uso gratuito, pero es un requisito de seguridad obligatorio.

**¿Cuál de estas dos prefieres intentar ahora?**
- **Google Cloud**: Es gratis para siempre, pero el servidor es un poco más débil.
- **AWS**: Es gratis por 1 año y el servidor es más rápido.
