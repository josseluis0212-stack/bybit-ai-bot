FROM python:3.11-slim

WORKDIR /app

# Copy the entire space repository into the Docker container
COPY . .

RUN apt-get update && apt-get install -y git build-essential gcc python3-dev && rm -rf /var/lib/apt/lists/*

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app/bybit-ai-bot

# Run the unified bot
CMD ["python", "-m", "app.main"]
