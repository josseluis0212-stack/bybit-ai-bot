#!/bin/bash

# Load environment variables
if [ -f /app/.env ]; then
  export $(cat /app/.env | grep -v '^#' | xargs)
fi

echo "Starting bybit-ai-bot..."
cd /app/bybit-ai-bot
# Assuming main.py is the entry point
python main.py &
BOT1_PID=$!

echo "Starting supertrend_ema_bot..."
cd /app/supertrend_ema_bot
# Assuming main.py is the entry point
python main.py &
BOT2_PID=$!

echo "Both bots started. Waiting for processes..."
# Wait for both processes to keep the container running
wait $BOT1_PID $BOT2_PID
