# Deployment Guide for Render / GitHub

1. **Commit and Push:**
   Push this entire `trading-bot-pro` repository to your GitHub account (private repo recommended).

2. **Render Setup:**
   - Go to [dashboard.render.com](https://dashboard.render.com/)
   - Click "New" -> "Background Worker"
   - Connect your GitHub account and select your `trading-bot-pro` repository.
   
3. **Configuration in Render:**
   - **Name:** Bybit-Bot
   - **Environment:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python main.py`
   
4. **Environment Variables:**
   Add these inside Render (Environment tab):
   ```
   BYBIT_API_KEY=y6QnvcTNEhBmWiPrbg
   BYBIT_API_SECRET=bYeLqDOUd8JJXrTatrwVDALGuXfxYBpsRVsj
   BYBIT_DEMO=True
   TELEGRAM_BOT_TOKEN=8363627370:AAE-1MphxrahFrRkgOSjBn_KnUYEJBL4cb0
   TELEGRAM_CHAT_ID=7840645929
   LEVERAGE=5
   TRADE_AMOUNT_USDT=50
   MAX_CONCURRENT_TRADES=10
   ```

5. **Deploy!**
   Click "Save/Deploy". The worker will build and start scanning markets 24/7.
