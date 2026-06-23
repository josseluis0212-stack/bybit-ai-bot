FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Set PYTHONPATH so 'from app.xxx import' works from the /app working directory
ENV PYTHONPATH=/app

RUN chmod +x start.sh

CMD ["bash", "start.sh"]
