# Usar una imagen base de Python ligera
FROM python:3.12-slim

# Establecer el directorio de trabajo
WORKDIR /app

# Copiar los archivos de requerimientos e instalarlos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código del bot
COPY . .

# Exponer el puerto del dashboard
EXPOSE 5000

# Comando para ejecutar el bot
CMD ["python", "main.py"]
