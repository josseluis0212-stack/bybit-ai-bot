import requests
import sys

TOKEN = "8363627370:AAE-1MphxrahFrRkgOSjBn_KnUYEJBL4cb0"
URL = f"https://api.telegram.org/bot{TOKEN}/getUpdates"

response = requests.get(URL)
data = response.json()

if data.get("ok"):
    results = data.get("result", [])
    if results:
        # Get the latest message
        last_message = results[-1]
        chat_id = last_message["message"]["chat"]["id"]
        print(f"CHAT_ID_FOUND={chat_id}")
    else:
        print("NO_MESSAGES_FOUND. Please send a message to the bot first.")
else:
    print(f"ERROR: {data}")
