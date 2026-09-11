import io
import requests
import time
import json
import os
import uuid
import threading
import random
import re
import html
import pyotp
import copy
import tempfile
import logging
import hashlib
import websocket   # pip: websocket-client — for Live Socket Panel
import ssl
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin, urlparse, quote, parse_qs

# ==========================================
# Logging Setup (replaces print() calls)
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# ==========================================
# Configuration (Token & Owner ID)
# ==========================================
# ─── SECURITY FIX ────────────────────────────────────────────────────────────
# The token will be loaded from the environment variable — NEVER put it in source code
# write. .env file or Replit Secrets in BOT_TOKEN set.
# Example: export BOT_TOKEN="your_token_yahan"
# ─────────────────────────────────────────────────────────────────────────────
TOKEN = os.getenv("BOT_TOKEN", "8647996726:AAHFWr1HnNfvwHElAJ3naDw3G0LopdPWNLY")  # Set BOT_TOKEN in the environment; never hardcode the token
if not TOKEN:
    raise RuntimeError(
        "❌ BOT_TOKEN environment variable is not set!\n"
        "   Replit Secrets or .env in BOT_TOKEN add.\n"
        "   New token: @BotFather → /token"
    )
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"
FILE_URL = f"https://api.telegram.org/file/bot{TOKEN}/"

OWNER_ID = 8671935587  # 👑 fayaz78613 — Owner Telegram ID
# Add trusted Telegram user IDs here to make them admins from the script.
# Example: ADMIN_IDS = [123456789, 987654321]
# OWNER_ID is always an admin and cannot be removed from the bot menu.
ADMIN_IDS = [8671935587, 8671935587]
BOT_USERNAME = "@jamaliking5_Bot"
DB_FILE = "nigga.json"
SUPPORT_URL = "https://t.me/fayaz78613"

# ==========================================
# PAK EDITION — Currency & Payment Config
# ==========================================
# ✅ Auto Mode providers (Nexa / VoltX / Stex) are enabled.
#    Individual providers remain OFF until enabled from the Auto Mode menu.
THIRD_PARTY_PROVIDERS = True


DEV_CREDIT = "DEVELOPED BY @fayaz78613"
DEV_CREDIT_HTML = "⚔️ <b>DEVELOPED BY fayaz78613</b> ⚔️"

COUNTRY_EDITION  = "PAKISTAN"
CURRENCY_CODE    = "PAK"          
CURRENCY_SYMBOL  = "PKR"            
CURRENCY_NAME    = "Pakstan Rupia"

# ✅ ALLOWED WITHDRAWAL METHODS — no accounts will be approved except these
#    Pak wallets  : Jazz cash Easypaisa
#    USDT crypto  : TRC20 (Tron) and BEP20 (BNB Smart Chain)
PAK_WALLET_LIST   = ["Jazzcash", "Easypaisa"]
CRYPTO_LIST      = ["USDT TRC20", "USDT BEP20"]
PAK_PAYMENT_METHODS = PAK_WALLET_LIST + CRYPTO_LIST

PAK_ALLOWED_METHODS = {
    # PAK mobile wallets
    "Jazzcash": "Easypaisa",
    "Jazzcash": "Easypaisa",
    # USDT crypto
    "usdt trc20": "USDT TRC20",
    "usdt-trc20": "USDT TRC20",
    "trc20": "USDT TRC20",
    "usdt (trc20)": "USDT TRC20",
    "usdt bep20": "USDT BEP20",
    "usdt-bep20": "USDT BEP20",
    "bep20": "USDT BEP20",
    "usdt (bep20)": "USDT BEP20",
}

def is_allowed_method(method):
    return str(method or "").strip().lower() in PAK_ALLOWED_METHODS

def clean_method_name(method):
    """'easy paisa' -> 'Easypaisa', 'trc20' -> 'USDT TRC20', otherwise None."""
    return PAK_ALLOWED_METHODS.get(str(method or "").strip().lower())

def is_crypto_method(method):
    return clean_method_name(method) in CRYPTO_LIST

def method_currency(method):
    """Is method of payout currency: USD (crypto) or PAK (wallet)."""
    return "USD" if is_crypto_method(method) else "PAK"

def allowed_methods_text():
    return " • ".join(PAK_PAYMENT_METHODS)

# ==========================================
# 💱 DUAL CURRENCY ENGINE (PAK base + USD/USDT)
# ==========================================
DEFAULT_USD_RATE = 290     # 1 USD = To PKR  (will be change in admin panel)

def usd_rate():
    try:
        r = float(bot_settings.get("usd_rate", DEFAULT_USD_RATE))
        return r if r > 0 else DEFAULT_USD_RATE
    except Exception:
        return DEFAULT_USD_RATE

def pkr_to_usd(amount):
    try:
        return round(float(amount) / usd_rate(), 4)
    except Exception:
        return 0.0

def usd_to_pkr(amount):
    try:
        return round(float(amount) * usd_rate(), 4)
    except Exception:
        return 0.0

def fmt_usd(amount):
    try:
        return "$" + ("%.4f" % float(amount)).rstrip("0").rstrip(".")
    except Exception:
        return "$0"

def fmt_dual(pkr_amount):
    """'290 PKR (~$1.00)' — both currencies together."""
    return f"{fmt_money(pkr_amount)} (~{fmt_usd(pkr_to_usd(pkr_amount))})"

def parse_money_input(raw):
    """Parse the rate entered by the administrator.
       '2' / '2 pkr' / '2PKR'  -> PKR
       '$0.05' / '0.05 usd' / '0.05$' / '0.05 usdt' -> USD
       return (ok, pkr_value, currency, original_value)"""
    t = str(raw or "").strip().lower().replace(",", "")
    is_usd = ("$" in t) or ("usd" in t) or ("usdt" in t) or ("dollar" in t)
    num = re.sub(r"[^0-9.]", "", t)
    if num.count(".") > 1 or num in ("", "."):
        return False, 0.0, "PKR", 0.0
    try:
        val = float(num)
    except Exception:
        return False, 0.0, "PKR", 0.0
    if val < 0:
        return False, 0.0, "PKR", 0.0
    if is_usd:
        return True, round(usd_to_pkr(val), 4), "USD", val
    return True, round(val, 4), "PKR", val

# ==========================================
# 📍 RANGE (batch) WISE RATE
# ==========================================
def _clean_num_key(num):
    return str(num or "").replace("+", "").replace(" ", "").replace("-", "").strip()

def get_number_rate(num_str):
    """which range/batch of number is us the range's per-OTP rate (PKR) do.
       the range's your if no rate exists to global otp_reward."""
    target = _clean_num_key(num_str)
    if target:
        try:
            for b_id, b_data in number_batches.items():
                if b_data.get("rate_pkr") in (None, ""):
                    continue
                for n_obj in b_data.get("numbers", []):
                    stored = _clean_num_key(n_obj.get("num", ""))
                    if not stored:
                        continue
                    if stored == target or (
                        len(stored) >= 8 and len(target) >= 8 and
                        abs(len(stored) - len(target)) <= 3 and
                        (stored.endswith(target[-8:]) or target.endswith(stored[-8:]))
                    ):
                        return float(b_data.get("rate_pkr") or 0.0)
        except Exception as _e:
            logger.warning(f"get_number_rate error: {_e}")
    try:
        return float(bot_settings.get("otp_reward", 0.0))
    except Exception:
        return 0.0

def range_rate_text(b_data):
    """Return the configured rate for one uploaded range."""
    r = b_data.get("rate_pkr")
    if r in (None, ""):
        return f"{fmt_money(bot_settings.get('otp_reward', 0.0))} (default)"
    return fmt_money(r)


def country_rate_text(service, country):
    """Return the rate label for a country in the selected service.

    If all local batches for the country use the same rate, show that exact
    rate. If multiple rates exist, show a range/varies label rather than
    misleading users; the actual matched number rate remains authoritative.
    """
    rates = []
    for b_data in number_batches.values():
        if b_data.get("service") != service or b_data.get("country") != country:
            continue
        if not b_data.get("numbers"):
            continue
        raw = b_data.get("rate_pkr")
        try:
            rates.append(float(raw) if raw not in (None, "") else float(bot_settings.get("otp_reward", 0.0)))
        except Exception:
            continue
    if not rates:
        return fmt_money(bot_settings.get("otp_reward", 0.0))
    unique = sorted(set(round(r, 6) for r in rates))
    if len(unique) == 1:
        return fmt_money(unique[0])
    return f"{fmt_money(unique[0])}–{fmt_money(unique[-1])}"

def fmt_money(amount):
    """same Pakistani format everywhere: 290 -> '290 PKR'"""
    try:
        a = float(amount)
        txt = str(int(a)) if a == int(a) else ("%.2f" % a)
    except Exception:
        txt = str(amount)
    return f"{txt} {CURRENCY_SYMBOL}"

def normalize_pak_mobile(raw):
    """Normalize Pakistan mobile number to 01XXXXXXXXX format."""
    d = re.sub(r"\D", "", str(raw or ""))
    if d.startswith("0092"):
        d = d[5:]
    elif d.startswith("92") and len(d) >= 12:
        d = d[3:]
    elif d.startswith("92") and len(d) >= 12:
        d = d[2:]
    elif d.startswith("0"):
        d = d[1:]
    if len(d) == 10 and d.startswith("1"):
        return "0" + d
    return None

# Backward-compatible alias for old callers/configurations.
normalize_pak_mobile = normalize_pak_mobile

def validate_pak_account(method, raw):
    """Pakistan wallet validation — JAZZCASH / EASYPAISA."
    return (ok: bool, cleaned_value: str, error_text: str)"""
    val = str(raw or "").strip()

    # 🚫 No method other than these 4 will be approved
    if not is_allowed_method(method):
        return False, "", (
            "❌ This withdrawal method is not allowed!\n\n"
            f"✅ Only these accounts can be used:\n<b>{allowed_methods_text()}</b>\n\n"
            "📝 Withdrawal Please restart and select a method from the list."
        )

    # 🪙 Crypto: USDT TRC20 / BEP20 address
    if is_crypto_method(method):
        addr = val.replace(" ", "")
        m_name = clean_method_name(method)
        if m_name == "USDT TRC20":
            if re.fullmatch(r"T[1-9A-HJ-NP-Za-km-z]{33}", addr):
                return True, addr, ""
            return False, "", (
                "❌ Incorrect USDT TRC20 address!\n\n"
                "🪙 <b>TRC20 (Tron)</b> address starts with <code>T</code> and has 34 characters.\n"
                "<i>Example: TQn9Y2khDD95J42FQtQTdwVVRZqiP1RGxg</i>\n\n"
                "📝 Send again:"
            )
        if re.fullmatch(r"0x[a-fA-F0-9]{40}", addr):
            return True, addr, ""
        return False, "", (
            "❌ Incorrect USDT BEP20 address!\n\n"
            "🪙 <b>BEP20 (BNB Smart Chain)</b> address starts with <code>0x</code> and has 42 characters.\n"
            "<i>Example: 0x71C7656EC7ab88b098defB751B7401B5f6d8976F</i>\n\n"
            "📝 Send again:"
        )

    num = normalize_pak_mobile(val)
    if num:
        return True, num, ""
    return False, "", (
        "❌ Incorrect number!\n\n"
        f"📱 Send the Pakistan mobile number for <b>{clean_method_name(method)}</b>:\n"
        "• <code>01712345678</code>\n"
        "• <code>+923241392902</code>\n\n"
        "⚠️ Bank account / IBAN is not accepted.\n\n"
        "📝 Send again:"
    )

def pak_account_prompt(method):
    m = clean_method_name(method) or method
    if is_crypto_method(method):
        if m == "USDT TRC20":
            return ("🪙 Send your <b>USDT TRC20</b> wallet address:\n"
                    "<i>Example: TQn9Y2khDD95J42FQtQTdwVVRZqiP1RGxg</i>")
        return ("🪙 Send your <b>USDT BEP20</b> wallet address:\n"
                "<i>Example: 0x71C7656EC7ab88b098defB751B7401B5f6d8976F</i>")
    return (f"📱 Send your <b>{m}</b> account number:\n"
            "<i>Example: 01712345678</i>\n"
            "<i>(the wallet number where you want the payment)</i>")


# Backward-compatible alias for existing callers.
pak_account_prompt = pak_account_prompt

# ==========================================
# Premium Emoji Database
# ==========================================
PEM = {
    "ok": '<tg-emoji emoji-id="5352694861990501856">✅</tg-emoji>',
    "no": '<tg-emoji emoji-id="6267000941547885720">❌</tg-emoji>',
    "warn": '<tg-emoji emoji-id="5336944168944047463">⚠️</tg-emoji>',
    "admin": '<tg-emoji emoji-id="5353032893096567467">📊</tg-emoji>',
    "user": '<tg-emoji emoji-id="5352861489541714456">👤</tg-emoji>',
    "file": '<tg-emoji emoji-id="5352721946054268944">📁</tg-emoji>',
    "rocket": '<tg-emoji emoji-id="5352597830089347330">🚀</tg-emoji>',
    "graph": '<tg-emoji emoji-id="5352877703043258544">📊</tg-emoji>',
    "money": '<tg-emoji emoji-id="5348469219761626211">💸</tg-emoji>',
    "gift": '<tg-emoji emoji-id="5420396762189831222">🎁</tg-emoji>',
    "msg": '<tg-emoji emoji-id="5337302974806922068">💬</tg-emoji>',
    "gear": '<tg-emoji emoji-id="5420155432272438703">⚙️</tg-emoji>',
    "link": '<tg-emoji emoji-id="5420517437885943844">🔗</tg-emoji>',
    "trash": '<tg-emoji emoji-id="5422557736330106570">🗑</tg-emoji>',
    "upload": '<tg-emoji emoji-id="5353001161878182134">📤</tg-emoji>',
    "world": '<tg-emoji emoji-id="5336972142066047577">🌐</tg-emoji>',
    "lock": '<tg-emoji emoji-id="5353022963132174959">🔐</tg-emoji>',
    "phone": '<tg-emoji emoji-id="4969841369850840381">📱</tg-emoji>',
    "num": '<tg-emoji emoji-id="5352862640592949843">🔢</tg-emoji>',
    "pin": '<tg-emoji emoji-id="5352922460897452503">📍</tg-emoji>',
    "star": '<tg-emoji emoji-id="5352552689983067014">✨</tg-emoji>',
    "hi": '<tg-emoji emoji-id="5353027129250453493">👋</tg-emoji>'
}

GLOBAL_BODY_EMOJIS = {
    # ── Navigation / Status ──────────────────────────────────────────────────
    "✅": "5352694861990501856", "❌": "5420130255174145507",
    "⚠️": "5336944168944047463", "🔥": "5337267511261960341",
    "🌟": "5337102391244263212", "✨": "5352552689983067014",
    "➖": "5870818207383686839", "➕": "5420323438508155202",
    "➡️": "6319061296704656261", "🔄": "6264896248659056036",
    "⌛": "4958503072801228000", "⏳": "6285092198497129798",
    "🕓": "5336983442125001376", "🔴": "6267237615720731788",

    # ── Users and People ────────────────────────────────────────────────────────
    "👤": "5352861489541714456", "👥": "4972130076318500235",
    "👋": "5353027129250453493", "👇": "5406745015365943482",
    "👨‍⚖️": "5334763399299506604", "😒": "5334763399299506604",
    "😔": "6120863614149596295", "🫂": "5420145051336485498",

    # ── Numbers / Statistics ──────────────────────────────────────────────────────
    "1️⃣": "5877664071720898423", "2️⃣": "5877223446731034464",
    "3️⃣": "5879546817879740639", "4️⃣": "5879844832775507443",
    "5️⃣": "5879657954453491518", "6️⃣": "5877556203617259178",
    "7️⃣": "5879611822209765566", "8️⃣": "5879971663159758717",
    "9️⃣": "5877752470737784316",
    "🔢": "5352862640592949843", "🆔": "5352862640592949843",
    "📊": "5353032893096567467", "📈": "5352877703043258544",

    # ── Files and Data ─────────────────────────────────────────────────────────
    "📁": "5352721946054268944", "📦": "5352721946054268944",
    "📂": "5257969839313526622", "📤": "5353001161878182134",
    "📝": "5192739271886282680", "🧾": "5192739271886282680",
    "📅": "5352585194295564660", "📋": "6267008582294705964",
    "💾": "5197269100878907942", "📛": "6325731252066325108",

    # ── Communication ────────────────────────────────────────────────────────
    "💬": "5337302974806922068", "🎙": "5355102594886833928",
    "📢": "5789428375261023681", "📌": "5318986077455795572",
    "📍": "5352922460897452503",

    # ── Security / Tech ──────────────────────────────────────────────────────
    "🔑": "6282760761399841824", "🔐": "5337255927735163754",
    "🔗": "5420517437885943844", "⚙️": "5420155432272438703",
    "🛡": "5190447043545438788", "🚫": "5334807341109908955",
    "🌐": "6266794310671275367", "🔒": "6282846669335702032",

    # ── Money / Business ─────────────────────────────────────────────────────
    "💸": "5348469219761626211", "🏦": "5348469219761626211",
    "💰": "5190576863226933563", "💎": "5352838545826420397",
    "💳": "5190899075968441286", "🎁": "5420396762189831222",
    "🤝": "5192805934073685937",

    # ── Services / Apps ──────────────────────────────────────────────────────
    "🚀": "5352597830089347330", "🍏": "5337132498965010628",
    "📱": "5337132498965010628",
    "🌍": "5780471598922337683",

    # ── UI / Misc ────────────────────────────────────────────────────────────
    "🗑": "5422557736330106570", "🟢": "5192812028632274956",
    "👀": "5190645917711114179", "🕹": "5193100774988617665",
    "🧪": "5190781475468915802", "🎨": "5190751148704833975",
    "💡": "5422439311196834318", "🎯": "5276032951342088188",
}

DEFAULT_CUSTOM_MESSAGES = {
    "start": {
        "text": (
            "╔═══════════╗\n"
            "       📊 NUMBER BOT\n"
            "╚═══════════╝\n"
            "🚀 Welcome to Number & OTP Service\n"
            "━━━━━━━━━━━━\n"
            "✅ Choose an option below\n"
            "to continue using the bot.\n"
            "━━━━━━━━━━━━\n"
            "💎 Premium OTP Service\n"
            "⚔️ <b>DEVELOPED BY fayaz78613</b> ⚔️"
        ),
        "buttons": []
    },
    "get_number": {"text": f"{PEM['pin']} Select a service:", "buttons": []},
    "select_country": {"text": f"📌 Select a country for {{service}}:", "buttons": []},
    "search_number": {"text": f"{PEM['num']} <b>Search number</b>\n\nTo search numbers enter 3 to 9 digits (e.g.: 92, 923241392902, 1712345):", "buttons": []},
    "traffic": {"text": f"{PEM['graph']} <b>Traffic details</b>\n\n{PEM['ok']} Available numbers: {{avail}}\n{PEM['rocket']} Assigned numbers: {{assigned}}", "buttons": []},
    "refer": {"text": f"➖➖➖➖➖➖➖\n« {PEM['gift']} Refer and earn »\n➖➖➖➖➖➖➖\n{PEM['link']} Your link:\n<code>{{ref_link}}</code>\n➖➖➖➖➖➖➖\n{PEM['user']} Total referrals: <b>{{total_ref}}</b>\n➖➖➖➖➖➖➖\n{PEM['money']} Per referral: <b>{{ref_reward}} PKR</b>\n➖➖➖➖➖➖➖", "buttons": []},
    "withdrawal": {"text": "➖➖➖➖➖➖➖\n《 😒 Withdrawal 》\n➖➖➖➖➖➖➖\n👋 Total OTP: {total_otp}\n➖➖➖➖➖➖➖\n🫂 Total referrals: {total_ref}\n➖➖➖➖➖➖➖\n📅 Balance: {bal} PKR  (~{bal_usd})\n➖➖➖➖➖➖➖\n🔐 Minimum: {min_w} PKR\n➖➖➖➖➖➖➖\n💵 1 USD = {usd_rate} PKR\n➖➖➖➖➖➖➖\nSelect payment method:", "buttons": []},
    "support": {"text": f"{PEM['msg']} Contact us for any help:", "buttons": []}
}

# ==========================================
# Database Mode (Local JSON Only)
# ==========================================
logger.info("Running in Local Mode")

bot_settings = {
    "admins": [OWNER_ID],
    "panels": [], 
    "fw_groups": [{"chat_id": "", "buttons": []}],   # 🛡 OTP forward group
    "otp_link": "https://t.me/+rJxxSYDwi5ZlY2Vk",       # 🔗 OTP group join link
    "withdraw_on": True,
    "min_withdraw": 500.0,        # 🇵🇰 500 PKR minimum (can be changed from admin panel)
    "otp_reward": 1.0,            # 🇵🇰 default per OTP reward in PKR (range-specific rate takes priority)
    "usd_rate": 290.0,            # 💵 1 USD = how many PKR (for USDT withdrawal + USD rate)
    "auto_backup": True,          # 🛡️ backup zip to owner every 6 hours
    "refer_reward": 0.50,          # 🇵🇰 per refer reward in PKR
    "cooldown": 10,
    "num_req": 3,
    "num_share": 1, 
    "support_link": SUPPORT_URL,    # 💬 Support group
    "w_methods": list(PAK_PAYMENT_METHODS),
    "w_group": "",                     # 💸 Withdrawal requests group
    
    "fj_on": True,                                      # 🔒 Force join enabled
    "fj_channels": [
    {"chat_id": "@yourchannel", "type": "channel", "title": "YOUR NAME 1",
     "invite_link": "https://t.me/yourlink", "is_private": False},
    {"chat_id": "@yourchannel", "type": "channel", "title": "YOUR NAME 2",
     "invite_link": "https://t.me/yourlink", "is_private": False},
    {"chat_id": "@yourchannel", "type": "channel", "title": "YOUR NAME 3",
     "invite_link": "https://t.me/yourlink", "is_private": False},
    {"chat_id": "@yourchannel", "type": "channel", "title": "YOUR NAME 4",
     "invite_link": "https://t.me/yourlink", "is_private": False},
    {"chat_id": "@yourgroup", "type": "group", "title": "YOUR NAME 5",
     "invite_link": "https://t.me/yourlink", "is_private": False},
    {"chat_id": "@yourgroup", "type": "group", "title": "YOUR NAME 6",
     "invite_link": "https://t.me/yourlink", "is_private": False},
  ],
    # 🚫 Third-party providers - permanently disabled (THIRD_PARTY_PROVIDERS = False)
    "nexa_on": False,
    "voltx_on": False,
    "stex_on": False,
    "nexa_keys": [], 
    "search_countries": [],
    "nexa_search_countries": [],
    "voltx_search_countries": [],
    "stex_search_countries": [],
    "nexa_services": {},
    "voltx_keys": [],
    "voltx_services": {},
    "stex_keys": [],
    "stex_services": {},
    "premium_flags": {
        "92": {"char": "🇵🇰", "iso": "PK", "name": "Pakistan", "id": "5913705895375672082"},
        "1": {"char": "🇺🇸", "iso": "US", "name": "United States", "id": "5913463998522592692"},
        "880": {"char": "🇧🇩", "iso": "BD", "name": "Bangladesh", "id": "5911365056594973179"},
        "91": {"char": "🇮🇳", "iso": "IN", "name": "India", "id": "5913754823643107921"},
        "44": {"char": "🇬🇧", "iso": "GB", "name": "United Kingdom", "id": "5913443365499703513"}
    },
    "premium_apps": {
        "FACEBOOK": {"char": "🚫", "id": "5334807341109908955", "name": "Facebook"},
        "WHATSAPP": {"char": "🚫", "id": "5334759662677957452", "name": "WhatsApp"}
    },
    "custom_messages": DEFAULT_CUSTOM_MESSAGES.copy(),
    "sys_emoji_overrides": {}
}

bot_settings.setdefault("ui_emojis", {})
bot_settings.setdefault("otp_forward", {})
bot_settings["otp_forward"].setdefault("emoji_positions", {
    "before_flag": "", "before_service": "", "before_number": "", "before_time": "", "before_otp": ""
})
bot_settings["otp_forward"].setdefault("channel_link", "https://t.me/+rJxxSYDwi5ZlY2Vk")
bot_settings["otp_forward"].setdefault("number_link", "https://t.me/+TLo1Z_Pm4cdjMmY0")
bot_settings["otp_forward"].setdefault("button_emojis", {
    "channel": "5420517437885943844", "otp": "5353022963132174959", "number_bot": "5337132498965010628"
})


# Force-join channels of default snapshot (migration for)
_DEFAULT_FJ_CHANNELS = [dict(x) for x in bot_settings["fj_channels"]]

# Thread lock for safe DB writes
_db_save_lock = threading.Lock()

number_batches = {}
used_numbers_list = []
nexa_assigned_numbers = {}
NEXA_BASE_URL = "https://nexaotpservice.com"      # ✅ Correct Nexa domain - HTTPS is required
voltx_assigned_numbers = {}
VOLTX_BASE_URL = "https://api.2oo9.cloud/MXS47FLFX0U/tnevs/@public/api"   # ✅ VoltX CDN path
stex_assigned_numbers = {}
STEX_BASE_URL = "https://api.2oo9.cloud/MXS47FLFX0U/tness/@public/api"    # ✅ Stex CDN path (tness != tnevs)
total_uploaded_stats = 0
total_assigned_stats = 0
_stats_lock = threading.Lock()       # Thread-safe stats counter
_data_lock = threading.Lock()        # Thread-safe lock for shared dicts (nexa/voltx/stex assigned numbers, processed_otps)
_traffic_lock = threading.Lock()     # Thread-safe lock for recent_traffic list
processed_otps = {}  # {unique_id: timestamp}  - time-based deduplication
SEEN_OTPS_FILE = "seen_otps.json"
# Shared HTTP sessions for background threads (persistent connections = faster)
_nexa_session = requests.Session()
_voltx_session = requests.Session()
_stex_session = requests.Session()
recent_traffic = []
user_banned_cache = {}
_banned_cache_lock = threading.Lock()  # Thread-safe banned cache access
otp_received_numbers = set()

# Per-service warmup flags - set to True when a service is turned on or a key is added during runtime.
# global_sms_listener checks these so old OTPs are never delivered on first poll after enable.
_service_warmup_needed = {"nexa": False, "voltx": False, "stex": False}

# Active HTTP sessions for Auto Captcha Panels
panel_sessions = {}
_OTP_RECV_MAX = 50000  # Max OTP received numbers to keep in memory

# 🌟 Nexa Number Allocation Helper (mirrors VoltX and Stex pattern)
def try_nexa_get_number(query, chat_id, allow_auto=True):
    """Try to allocate a number from Nexa. Returns (num_str, api_key) or (None, None).
    allow_auto=False -> if Nexa has no matching configured range, skip immediately
    (used when at least one panel has services configured by the admin)."""
    global total_assigned_stats

    if not bot_settings.get("nexa_on", False):
        return None, None

    nexa_keys = bot_settings.get("nexa_keys", [])
    if not nexa_keys:
        return None, None

    nexa_srvs = bot_settings.get("nexa_services", {})
    has_nexa_srvs = any(
        rng
        for countries in nexa_srvs.values()
        for ranges in countries.values()
        for rng in ranges
    )
    clean_q = query.replace("X", "").replace("x", "")

    # Range-match check
    nexa_has_match = any(
        rng.replace("X", "").replace("x", "").startswith(clean_q) or
        clean_q.startswith(rng.replace("X", "").replace("x", ""))
        for countries in nexa_srvs.values()
        for ranges in countries.values()
        for rng in ranges
    )

    # Panel isolation rules:
    #   - Nexa configured but no match -> cannot serve this prefix
    #   - Nexa unconfigured AND allow_auto=False -> another panel owns this prefix -> skip
    if has_nexa_srvs and not nexa_has_match:
        return None, None
    if not has_nexa_srvs and not allow_auto:
        return None, None

    t_len = 12
    if query.startswith("92"): t_len = 12
    elif query.startswith("1") and len(query) < 12: t_len = 11
    search_range = query + ("X" * (t_len - len(query))) if len(query) < t_len else query

    payloads = [
        {"range": search_range, "format": "normal"},
        {"range": search_range},
        {"prefix": query},
    ]

    for _ in range(bot_settings.get("num_req", 1)):
        for api_key in nexa_keys:
            for payload in payloads:
                try:
                    headers = {"X-API-Key": api_key}
                    res = _nexa_session.post(
                        f"{NEXA_BASE_URL}/api/v1/numbers/get",
                        json=payload, headers=headers, timeout=10
                    )
                    resp = res.json()
                    if resp.get("success") and (resp.get("number") or resp.get("phone_number")):
                        num_str = str(resp.get("number") or resp.get("phone_number", "")).replace("+", "")
                        # FIX: Nexa multiple number_id field names support do
                        number_id = (resp.get("number_id") or resp.get("id") or
                                     resp.get("sms_id") or resp.get("num_id") or resp.get("phone_id"))
                        if not num_str:
                            continue
                        # ✅ Range validation: reject number that does not match the requested prefix
                        if not num_str.startswith(clean_q):
                            logger.warning(f"Nexa returned wrong range: {num_str} (expected: {clean_q})")
                            continue
                        with _data_lock:
                            nexa_assigned_numbers[num_str] = chat_id
                        with _stats_lock:
                            total_assigned_stats += 1
                        if number_id:
                            threading.Thread(
                                target=poll_otp_with_status,
                                args=(number_id, num_str, chat_id, api_key),
                                daemon=True
                            ).start()
                        return num_str, api_key
                    elif not resp.get("success") and resp.get("code") == 401:
                        break  # Invalid API key - skip remaining payloads for this key
                except Exception as e:
                    logger.warning(f"Nexa getnum error: {e}")
                    continue
    return None, None


# 🌟 Unified panel-fetch helper (Nexa -> VoltX -> Stex with strict isolation)
def _fetch_number_via_panels(query, chat_id):
    """Try all enabled panels in order (Nexa -> VoltX -> Stex).
    Enforces strict per-panel isolation: if the admin configured ranges/services
    in any panel, only the panel(s) where that prefix was configured may serve it.
    If no panel has any services configured at all, all panels run in free/auto mode.
    Returns (num_str, panel_name) or (None, None)."""

    _nexa_srvs = bot_settings.get("nexa_services", {})
    _voltx_srvs = bot_settings.get("voltx_services", {})
    _stex_srvs  = bot_settings.get("stex_services", {})

    # Are ANY services/ranges configured by the admin across all panels?
    _any_configured = (
        any(rng for c in _nexa_srvs.values()  for rl in c.values() for rng in rl) or
        any(rng for c in _voltx_srvs.values() for rl in c.values() for rng in rl) or
        any(rng for c in _stex_srvs.values()  for rl in c.values() for rng in rl)
    )
    # allow_auto=True only when NO panel has any configuration (pure auto mode)
    allow_auto = not _any_configured

    # Try Nexa (only if ON)
    if bot_settings.get("nexa_on", False):
        num, _key = try_nexa_get_number(query, chat_id, allow_auto=allow_auto)
        if num:
            return num, "Nexa"

    # Try VoltX (only if ON)
    if bot_settings.get("voltx_on", False):
        num, _key = try_voltx_get_number(query, chat_id, allow_auto=allow_auto)
        if num:
            return num, "VoltX"

    # Try Stex (only if ON)
    if bot_settings.get("stex_on", False):
        num, _key = try_stex_get_number(query, chat_id, allow_auto=allow_auto)
        if num:
            return num, "Stex"

    return None, None


# 🌟 VoltX Number Allocation Helper (used in both Search & GET NUMBER flows)
def _try_mauthapi_get_number(query, chat_id, base_url, keys_setting, services_setting,
                              assigned_dict, poll_fn, getnum_payload_extra=None,
                              extra_num_field=None, allow_auto=True):
    """Shared number allocation helper for VoltX and Stex (same mauthapi platform).
    getnum_payload_extra: extra POST body fields (e.g. {"m":"n","range":""} for VoltX).
    extra_num_field: extra number key to try before 'number' (e.g. 'phone_number'/'national_number')."""
    global total_assigned_stats
    api_keys = bot_settings.get(keys_setting, [])
    if not api_keys:
        return None, None
    ranges_to_try = []
    services_all = bot_settings.get(services_setting, {})
    has_services = any(
        ranges
        for countries in services_all.values()
        for ranges in countries.values()
    )
    for srv, countries in services_all.items():
        for cnt, ranges in countries.items():
            for rng in ranges:
                rng_prefix = rng.replace("X", "").replace("x", "")
                if query.startswith(rng_prefix) or rng_prefix.startswith(query):
                    ranges_to_try.append(rng)
    # If no matching ranges found:
    # - If panel has services configured but none match → can't serve this prefix
    # - If allow_auto=False (another panel owns this range) → skip entirely
    # - Otherwise (no services anywhere) → auto-range mode
    if not ranges_to_try:
        if has_services or not allow_auto:
            return None, None
        auto_range = query + ("XXX" if len(query) >= 4 else "X" * (7 - len(query)))
        ranges_to_try.append(auto_range)
    for _ in range(bot_settings.get("num_req", 1)):
        for api_key in api_keys:
            for rng in ranges_to_try:
                try:
                    headers = {"mauthapi": api_key, "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
                    rid_value = rng.replace("X", "").replace("x", "")
                    payload = {"rid": rid_value}
                    if getnum_payload_extra:
                        payload.update(getnum_payload_extra)
                    _ms = _voltx_session if base_url == VOLTX_BASE_URL else _stex_session
                    res = _ms.post(f"{base_url}/getnum", json=payload, headers=headers, timeout=15)
                    data = res.json()
                    meta = data.get("meta", {})
                    if meta.get("code") == 200 and data.get("data"):
                        num_data = data["data"]
                        num_str = str(
                            num_data.get("no_plus_number") or
                            num_data.get("full_number") or
                            (num_data.get(extra_num_field) if extra_num_field else None) or
                            num_data.get("number") or ""
                        ).replace("+", "").replace(" ", "")
                        if num_str and not num_str.startswith(rid_value[:len(query)]):
                            logger.warning(f"{keys_setting} returned wrong range: {num_str} (expected: {rid_value})")
                            continue
                        if num_str:
                            with _data_lock:
                                assigned_dict[num_str] = chat_id
                            with _stats_lock:
                                total_assigned_stats += 1
                            threading.Thread(target=poll_fn, args=(num_str, chat_id, api_key), daemon=True).start()
                            return num_str, api_key
                except Exception as e:
                    logger.warning(f"{keys_setting} getnum error: {e}")
                    continue
    return None, None


def try_voltx_get_number(query, chat_id, allow_auto=True):
    """Allocate a number from VoltX — thin wrapper around _try_mauthapi_get_number."""
    return _try_mauthapi_get_number(
        query, chat_id, VOLTX_BASE_URL, "voltx_keys", "voltx_services",
        voltx_assigned_numbers, voltx_poll_otp,
        # FIX: "range": "" removed — rid is already in the payload, empty range caused a conflict
        getnum_payload_extra={"m": "n"},
        extra_num_field="phone_number",
        allow_auto=allow_auto
    )

# 🌟 VoltX Owner Lookup Helper (used in panel_monitor, global_sms_listener)
def _find_assigned_owner(assigned_dict, clean_num):
    """Find owner_id for a number in any assigned_numbers dict. Returns owner_id or None."""
    for n, owner in assigned_dict.items():
        clean_n = str(n).replace("+", "").replace(" ", "").replace("-", "").strip()
        if clean_n == clean_num:
            return owner
        # Fuzzy suffix match — only when lengths differ by ≤3 digits (country-code prefix).
        # Guard prevents false matches between unrelated numbers sharing last 8 digits.
        if (len(clean_n) >= 8 and len(clean_num) >= 8 and
                abs(len(clean_n) - len(clean_num)) <= 3 and
                (clean_n.endswith(clean_num[-8:]) or
                 clean_num.endswith(clean_n[-8:]))):
            return owner
    return None


# 🌟 Stex Number Allocation Helper (used in both Search & GET NUMBER flows)
def try_stex_get_number(query, chat_id, allow_auto=True):
    """Allocate a number from Stex SMS — thin wrapper around _try_mauthapi_get_number."""
    return _try_mauthapi_get_number(
        query, chat_id, STEX_BASE_URL, "stex_keys", "stex_services",
        stex_assigned_numbers, stex_poll_otp,
        extra_num_field="national_number",
        allow_auto=allow_auto
    )


# 🌟 sAjaxSource (AJAX/DataTable) and Fallback HTML Parser Helper Function
def fetch_cpt_panel_cdrs(p, session, check_url):
    res = session.get(check_url, timeout=15, allow_redirects=True)
    html_text = res.text
    
    # Check if session expired - verify by URL redirect to login page OR login form presence
    final_url = res.url.lower()
    # FIX: only last path segment check, 'login' word poore URL in not dhundho
    last_path = final_url.split('?')[0].rstrip('/').split('/')[-1]
    is_login_page = last_path in ('login', 'signin', 'sign-in', 'log-in', 'auth')
    if not is_login_page:
        # Also check if page has a login form (username + password inputs)
        soup_check = BeautifulSoup(html_text, 'html.parser')
        login_form = soup_check.find("input", {"type": "password"})
        # FIX: multiple sign-in phrases check, single string on depend mat do
        login_phrases = ["sign in to your account", "please sign in", "please login", "log in to continue"]
        page_lower = html_text.lower()
        has_login_phrase = any(phrase in page_lower for phrase in login_phrases)
        if login_form and has_login_phrase:
            is_login_page = True
    if is_login_page:
        raise Exception("Session expired")
        
    soup = BeautifulSoup(html_text, 'html.parser')
    s_ajax_source = ""
    for script in soup.find_all("script"):
        script_text = script.string or ""
        match = re.search(r'sAjaxSource":\s*"([^"]+)"', script_text)
        if match:
            s_ajax_source = match.group(1)
            break
            
    results = []
    
    n_col_name = p.get("num_col_name", "number").lower()
    m_col_name = p.get("msg_col_name", "message").lower()
    n_idx = int(p.get("num_col_idx", 2)) - 1 if p.get("num_col_idx") is not None else 1
    m_idx = int(p.get("msg_col_idx", 3)) - 1 if p.get("msg_col_idx") is not None else 2

    # FIX: DataTables panels (sAjaxSource those) in data table of <thead>/header row
    # They are present only in the HTML, only the ROWS come from ajax — previously this header
    # only non-ajax (HTML fallback) path in use is tha. therefore jin panels in
    # visible column order manually-configured num_col_idx/msg_col_idx (default 2/3)
    # from match not does tha (such as extra "Range" column with: Date, Range,
    # Number, CLI, SMS, Currency, Payout — Number=3, SMS=5), the data of those panels either
    # "couldn't parse OTP data" gives tha or incorrect column (CLI/Currency) from junk parse
    # previously did. Now here also try from the visible <table> header of the same page —
    # match get go to use do, otherwise configured/default index on fallback do.
    _header_tables = soup.find_all('table')
    for _t in _header_tables:
        _rows = _t.find_all('tr')
        if _rows:
            _hn_idx, _hm_idx = _find_header_column_indices(_rows, n_col_name, m_col_name, n_idx, m_idx)
            if (_hn_idx, _hm_idx) != (n_idx, m_idx):
                n_idx, m_idx = _hn_idx, _hm_idx
            break

    # 5.1 If sAjaxSource AJAX link is found
    if s_ajax_source:
        baseUrl = p.get("login_url", "").split("/client")[0].split("/login")[0].strip()
        if not baseUrl.startswith("http"):
            baseUrl = "http://" + baseUrl
            
        full_ajax_url = ""
        if s_ajax_source.startswith("http"):
            full_ajax_url = s_ajax_source
        elif s_ajax_source.startswith("/"):
            full_ajax_url = f"{baseUrl}{s_ajax_source}"
        else:
            last_slash_idx = check_url.rfind("/")
            current_dir = check_url[:last_slash_idx]
            full_ajax_url = f"{current_dir}/{s_ajax_source}"

        # FIX: Kai DataTables panels sSortDir_0=desc to IGNORE by always
        # din of first page (iDisplayStart=0, only 25 records) return do
        # are — that is the oldest records, not the newest. As days pass
        # in records increase are (such as 1000+, or 5000+ high-volume panels
        # in), the bot keeps seeing the same old 25 records and misses new SMS
        # panel in after arrival also kabhi fetch hi not is ("panel in
        # SMS arrived, bot in not arrived" of real root cause). Fix: bada
        # request iDisplayLength (20000 — also safe for high-volume panels
        # margin, din in 5000-10000 OTP those panels to also cover does is)
        # so that din of all records a single request in aa jaayein, chahe
        # panel sorting is ignored. (Do alag requests bhejna panel of
        # would trigger our "15 second interval" anti-spam guard —
        # therefore single request in hi all some request are.)
        if "iDisplayLength" not in full_ajax_url:
            query_params = "sEcho=1&iColumns=7&iDisplayStart=0&iDisplayLength=20000&sSearch=&iSortingCols=1&iSortCol_0=0&sSortDir_0=desc"
            divider = "&" if "?" in full_ajax_url else "?"
            full_ajax_url += f"{divider}{query_params}"

        ajax_headers = {
            "Referer": check_url,
            "X-Requested-With": "XMLHttpRequest"
        }
        
        ajax_res = session.get(full_ajax_url, headers=ajax_headers, timeout=30)
        data_dict = ajax_res.json()
        rows = data_dict.get("aaData", [])

        # FIX: if panel of has also more records than requested are available
        # (edge case — like 20000+ in one day), even then we silently
        # sabse old data mat keep. if rows count total from less is,
        # issue this warning so that the owner knows the limit should be increased.
        try:
            _total_recs = int(data_dict.get("iTotalDisplayRecords") or data_dict.get("iTotalRecords") or 0)
            if _total_recs and len(rows) < _total_recs:
                logger.warning(
                    f"Panel '{p.get('name')}' has {_total_recs} records today but only "
                    f"{len(rows)} fetched — consider raising iDisplayLength further."
                )
        except (TypeError, ValueError):
            pass

        for row_val in rows:
            if not isinstance(row_val, list):
                continue
                
            if len(row_val) < max(n_idx, m_idx) + 1:
                continue
                
            num_val = row_val[n_idx] if (0 <= n_idx < len(row_val)) else (row_val[1] if len(row_val) > 1 else "")
            msg_val = row_val[m_idx] if (0 <= m_idx < len(row_val)) else (row_val[2] if len(row_val) > 2 else "")

            # Extract datetime → item_id so that different timestamps = different records
            # Step 1: before full timestamp dhundho (date + time a single column in)
            datetime_val = ""
            for col in row_val:
                col_str = str(col).strip()
                if re.search(r'\d{4}[-/]\d{2}[-/]\d{2}', col_str) and re.search(r'\d{2}:\d{2}:\d{2}', col_str):
                    datetime_val = col_str
                    break
            # Step 2: if full timestamp not received, date + time alag columns from combine do
            if not datetime_val:
                date_part = ""
                time_part = ""
                for col in row_val:
                    col_str = str(col).strip()
                    if not date_part:
                        m = re.search(r'\d{4}[-/]\d{2}[-/]\d{2}', col_str)
                        if m: date_part = m.group()
                    if not time_part:
                        m = re.search(r'\d{2}:\d{2}:\d{2}', col_str)
                        if m: time_part = m.group()
                datetime_val = f"{date_part} {time_part}".strip()
            
            # FIX: nn literal → real newlines
            msg_val = re.sub(r'(?<!\n)nn(?!\n)', '\n', str(msg_val))
            clean_num = re.sub(r'\D', '', str(num_val))
            # FIX: pure 8-digit = likely YYYYMMDD date, skip
            if clean_num and 5 <= len(clean_num) <= 18 and not re.match(r'^\d{8}$', clean_num):
                otp = extract_otp_code(msg_val)
                if otp and len(msg_val) > 4:
                    results.append({"number": clean_num, "message": msg_val, "otp": otp, "item_id": datetime_val})
                    
    else:
        # 5.2 Backup logic to read from direct HTML table
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            if not rows: continue
            
            final_n_idx, final_m_idx = _find_header_column_indices(rows, n_col_name, m_col_name, n_idx, m_idx)

            for row in rows:
                cols = row.find_all(['td', 'th'])
                if all(c.name == 'th' for c in cols): continue
                
                if len(cols) > max(final_n_idx, final_m_idx):
                    num_text = cols[final_n_idx].get_text(separator=" ", strip=True)
                    msg_text = cols[final_m_idx].get_text(separator=" ", strip=True)

                    # Extract datetime → item_id (HTML table path)
                    # Step 1: Full timestamp a single column in
                    datetime_val = ""
                    for col in cols:
                        col_text = col.get_text(separator=" ", strip=True)
                        if re.search(r'\d{4}[-/]\d{2}[-/]\d{2}', col_text) and re.search(r'\d{2}:\d{2}:\d{2}', col_text):
                            datetime_val = col_text
                            break
                    # Step 2: Date + time in separate columns → combine them
                    if not datetime_val:
                        date_part = ""
                        time_part = ""
                        for col in cols:
                            col_text = col.get_text(separator=" ", strip=True)
                            if not date_part:
                                m = re.search(r'\d{4}[-/]\d{2}[-/]\d{2}', col_text)
                                if m: date_part = m.group()
                            if not time_part:
                                m = re.search(r'\d{2}:\d{2}:\d{2}', col_text)
                                if m: time_part = m.group()
                        datetime_val = f"{date_part} {time_part}".strip()
                    
                    clean_num = re.sub(r'\D', '', num_text)
                    # FIX: nn literal → real newlines in msg_text
                    msg_text = re.sub(r'(?<!\n)nn(?!\n)', '\n', msg_text)
                    # FIX: pure 8-digit = YYYYMMDD date, skip
                    if clean_num and 5 <= len(clean_num) <= 18 and not re.match(r'^\d{8}$', clean_num):
                        otp = extract_otp_code(msg_text)
                        if otp and len(msg_text) > 4:
                            results.append({"number": clean_num, "message": msg_text, "otp": otp, "item_id": datetime_val})
                            
    return results, html_text

# Track active number sessions to expire them automatically
user_active_sessions = {}

def load_db():
    global number_batches, used_numbers_list, total_uploaded_stats, total_assigned_stats, recent_traffic, otp_received_numbers, nexa_assigned_numbers, voltx_assigned_numbers, stex_assigned_numbers
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding='utf-8') as f:
                raw_content = f.read()
            if not raw_content.strip():
                logger.warning("DB file is empty, starting fresh.")
                return
            data = json.loads(raw_content)
            saved_settings = data.get("bot_settings", {})
            for key, val in saved_settings.items():
                if key == "custom_messages":
                    for m_key, m_val in val.items():
                        bot_settings["custom_messages"][m_key] = m_val
                else:
                    bot_settings[key] = val

            # OTP Forward Manager defaults — preserve reference links after loading old DB data.
            bot_settings.setdefault("otp_forward", {})
            bot_settings["otp_forward"].setdefault("channel_link", "https://t.me/jamalipanel")
            bot_settings["otp_forward"].setdefault("number_link", "https://t.me/+TLo1Z_Pm4cdjMmY0")
            bot_settings["otp_forward"].setdefault("emoji_positions", {
                "before_flag": "", "before_service": "", "before_number": "", "before_time": "", "before_otp": ""
            })
            bot_settings["otp_forward"].setdefault("button_emojis", {
                "channel": "5420517437885943844", "otp": "5353022963132174959", "number_bot": "5337132498965010628"
            })

            for m_key, m_val in DEFAULT_CUSTOM_MESSAGES.items():
                if m_key not in bot_settings["custom_messages"]:
                    bot_settings["custom_messages"][m_key] = m_val
                    
            number_batches = data.get("number_batches", {})
            used_numbers_list = data.get("used_numbers_list", [])
            total_uploaded_stats = data.get("total_uploaded_stats", 0)
            total_assigned_stats = data.get("total_assigned_stats", 0)
            recent_traffic = data.get("recent_traffic", [])
            nexa_assigned_numbers = data.get("nexa_assigned_numbers", {})
            voltx_assigned_numbers = data.get("voltx_assigned_numbers", {})
            stex_assigned_numbers = data.get("stex_assigned_numbers", {})
            otp_received_numbers = set(data.get("otp_received_numbers", []))
            # Enforce the requested support destination even when an old DB exists.
            bot_settings["support_link"] = SUPPORT_URL

            # Migrate old fj_channels format (plain strings) to new dict format
            migrated = False
            new_fj = []
            for entry in bot_settings.get("fj_channels", []):
                if isinstance(entry, str):
                    new_fj.append({"chat_id": entry, "type": "channel", "title": entry, "invite_link": "", "is_private": False})
                    migrated = True
                else:
                    new_fj.append(entry)
            if migrated:
                bot_settings["fj_channels"] = new_fj

            # 🇵🇰 Migrate old settings and normalize them to PAKISTAN PKR methods
            pak_migrated = False
            # Keep only the allowed 4 methods — remove the rest (jazzcash/easypaisa/Paytm/Bank/UPaisa)
            old_methods = bot_settings.get("w_methods", [])
            fixed_methods, seen = [], set()
            for m in old_methods:
                cm = clean_method_name(m)
                if cm and cm not in seen:
                    fixed_methods.append(cm); seen.add(cm)
            if not fixed_methods:
                fixed_methods = list(PAK_PAYMENT_METHODS)
            # 🪙 One-time: add USDT methods to the old DB
            if not bot_settings.get("crypto_methods_added"):
                for cm2 in CRYPTO_LIST:
                    if cm2 not in fixed_methods:
                        fixed_methods.append(cm2)
                bot_settings["crypto_methods_added"] = True
                pak_migrated = True
            if fixed_methods != list(old_methods):
                bot_settings["w_methods"] = fixed_methods
                pak_migrated = True
            # Reset old PKR/Rupia messages to the Pakistan PKR defaults
            cm = bot_settings.get("custom_messages", {})
            for m_key in cm:
                if isinstance(cm[m_key], dict) and "text" in cm[m_key]:
                    txt = cm[m_key]["text"]
                    bad = ("pkr" in txt or "PKR" in txt or "INR" in txt or "USDT" in txt)
                    if bad and m_key in DEFAULT_CUSTOM_MESSAGES:
                        cm[m_key]["text"] = DEFAULT_CUSTOM_MESSAGES[m_key]["text"]
                        pak_migrated = True
            # 🔧 One-time: seed AR TECH config (only fills empty fields)
            if not bot_settings.get("ar_config_seeded"):
                if not bot_settings.get("w_group"):
                    bot_settings["w_group"] = None
                if not bot_settings.get("fw_groups"):
                    bot_settings["fw_groups"] = [{"chat_id": "", "buttons": []}]
                if not bot_settings.get("fj_channels"):
                    bot_settings["fj_channels"] = list(_DEFAULT_FJ_CHANNELS)
                    bot_settings["fj_on"] = True
                if not bot_settings.get("support_link"):
                    bot_settings["support_link"] = SUPPORT_URL
                if not bot_settings.get("otp_link"):
                    bot_settings["otp_link"] = ""
                if OWNER_ID not in bot_settings.get("admins", []):
                    bot_settings.setdefault("admins", []).append(OWNER_ID)
                # AR TECH rates
                bot_settings["min_withdraw"] = 100.0
                bot_settings["otp_reward"] = 1.0
                bot_settings["refer_reward"] = 1.0
                bot_settings["usd_rate"] = DEFAULT_USD_RATE
                bot_settings["cooldown"] = 10
                bot_settings["num_req"] = 3
                bot_settings["num_share"] = 1
                # old generic start message -> AR TECH branded
                st = cm.get("start", {})
                if isinstance(st, dict) and "NUMBER BOT" in str(st.get("text", "")):
                    cm["start"]["text"] = DEFAULT_CUSTOM_MESSAGES["start"]["text"]
                bot_settings["ar_config_seeded"] = True
                pak_migrated = True

            if pak_migrated:
                bot_settings["custom_messages"] = cm
                save_local_db()
                logger.info("Migrated payment settings to Pakistan PKR methods")

            # 🚫 Third-party providers always OFF (only own panel + txt system)
            if not THIRD_PARTY_PROVIDERS:
                for _k in ("nexa_on", "voltx_on", "stex_on"):
                    if bot_settings.get(_k):
                        bot_settings[_k] = False

            logger.info("Local DB loaded successfully")
        except Exception as e:
            logger.error(f"Error loading local DB: {e}")

def save_local_db():
    with _db_save_lock:
        try:
            local_data = {
                "bot_settings": copy.deepcopy(bot_settings),
                "number_batches": copy.deepcopy(number_batches),
                "used_numbers_list": list(used_numbers_list),
                "total_uploaded_stats": total_uploaded_stats,
                "total_assigned_stats": total_assigned_stats,
                "recent_traffic": list(recent_traffic),
                "nexa_assigned_numbers": dict(nexa_assigned_numbers),
                "voltx_assigned_numbers": dict(voltx_assigned_numbers),
                "stex_assigned_numbers": dict(stex_assigned_numbers),
                "otp_received_numbers": list(otp_received_numbers) if otp_received_numbers else []
            }
            # Atomic write: write to temp file first, then rename
            dir_name = os.path.dirname(os.path.abspath(DB_FILE))
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding='utf-8') as f:
                    json.dump(local_data, f, indent=4)
                # Atomic rename (safe on Linux)
                os.replace(tmp_path, DB_FILE)
            except Exception as e:
                # Clean up temp file on failure
                try: os.unlink(tmp_path)
                except Exception as unlink_err:
                    logger.warning(f"Temp file cleanup error: {unlink_err}")
                raise
        except Exception as e:
            logger.warning(f"DB save error: {e}")

load_db()


def _apply_script_admin_ids():
    """Merge ADMIN_IDS from this script with admins stored in bot_data.json."""
    merged = []
    for raw_id in [OWNER_ID, *bot_settings.get("admins", []), *ADMIN_IDS]:
        try:
            admin_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if admin_id not in merged:
            merged.append(admin_id)
    bot_settings["admins"] = merged


_apply_script_admin_ids()

# ==========================================
# 2FA Persistence (FIX: was in-memory only)
# ==========================================
TFA_DB_FILE = "2fa_saved.json"

def _load_2fa_saved():
    """Load persisted 2FA secrets from disk into user_2fa_saved."""
    global user_2fa_saved
    try:
        if os.path.exists(TFA_DB_FILE):
            with open(TFA_DB_FILE, "r", encoding="utf-8") as f:
                raw = f.read().strip()
            if raw:
                loaded = json.loads(raw)
                # Keys are stored as strings in JSON; keep as-is (int chat_id will be converted on access)
                user_2fa_saved = {int(k): v for k, v in loaded.items()} if isinstance(loaded, dict) else {}
    except Exception as e:
        logger.warning(f"2fa_saved load error: {e} — starting fresh")
        user_2fa_saved = {}

def _save_2fa_saved():
    """Atomically persist user_2fa_saved to disk."""
    try:
        snapshot = {str(k): v for k, v in user_2fa_saved.items()}
        dir_name = os.path.dirname(os.path.abspath(TFA_DB_FILE)) or "."
        with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False,
                                        suffix=".tmp", encoding="utf-8") as tf:
            tmp_path = tf.name
            json.dump(snapshot, tf, ensure_ascii=False)
        os.replace(tmp_path, TFA_DB_FILE)
    except Exception as e:
        logger.warning(f"2fa_saved save error: {e}")

user_states = {}
temp_data = {}
user_cooldowns = {}
pending_withdrawals = {}

user_2fa_saved = {}  # {chat_id: [{"name": "Instagram", "key": "ABCDEF123456"}, ...]}
_load_2fa_saved()   # FIX: load persisted 2FA secrets on startup

def _cleanup_stale_sessions():
    """Remove stale entries from in-memory dicts to prevent memory leaks."""
    now = time.time()
    # user_cooldowns: keep only last 10 minutes
    stale_cd = [k for k, v in list(user_cooldowns.items()) if now - v > 600]
    for k in stale_cd: user_cooldowns.pop(k, None)
    # user_states/temp_data: evict oldest by insertion order (max 5000 entries)
    if len(user_states) > 5000:
        for k in list(user_states.keys())[:2000]:
            user_states.pop(k, None)
    if len(temp_data) > 5000:
        for k in list(temp_data.keys())[:2000]:
            temp_data.pop(k, None)
    # pending_withdrawals: keep only last 500
    if len(pending_withdrawals) > 500:
        old_keys = list(pending_withdrawals.keys())[:-500]
        for k in old_keys: pending_withdrawals.pop(k, None)
    # user_2fa_saved grows unbounded — evict oldest 500 when over 2000
    if len(user_2fa_saved) > 2000:
        for k in list(user_2fa_saved.keys())[:500]:
            user_2fa_saved.pop(k, None)

def _cleanup_loop():
    """Background thread: memory cleanup every 5 minute in."""
    while True:
        time.sleep(300)
        try:
            _cleanup_stale_sessions()
        except Exception as e:
            logger.warning(f"_cleanup_stale_sessions error: {e}")

def _show_2fa_list(chat_id, msg_id):
    saved = user_2fa_saved.get(chat_id, [])
    _reset_btn_counter()
    if not saved:
        txt = (
            f"━━━━━━━━━━━━━━━\n"
            f"《 📋 <b>MY 2FA ADDED</b> 》\n"
            f"━━━━━━━━━━━━━━━\n"
            f"😔 No 2FA saved yet.\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 First, use <b>Generate 2FA Code</b>,\n"
            f"your code will be saved automatically.\n"
            f"━━━━━━━━━━━━━━━"
        )
        kb = {"inline_keyboard": [
            [{"text": "Generate 2FA Code", "icon_custom_emoji_id": "5353022963132174959", "callback_data": "gen_2fa", "style": _rs()}],
            [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "cancel_2fa", "style": _rs()}]
        ]}
    else:
        txt = (
            f"━━━━━━━━━━━━━━━\n"
            f"《 📋 <b>MY 2FA ADDED</b> 》\n"
            f"━━━━━━━━━━━━━━━\n"
            f"✅ You have <b>{len(saved)}</b> 2FA code(s) saved.\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💡 To recover any account,\n"
            f"code generate do or secret key dekhen.\n"
            f"━━━━━━━━━━━━━━━"
        )
        list_kb = []
        for i, entry in enumerate(saved):
            list_kb.append([
                {"text": f"{entry['name']}", "icon_custom_emoji_id": "5353022963132174959", "callback_data": f"gen_saved_2fa_{i}", "style": _rs()},
                {"text": "Del", "icon_custom_emoji_id": "5422557736330106570", "callback_data": f"del_2fa_{i}", "style": _rs()}
            ])
        list_kb.append([{"text": "Add New", "icon_custom_emoji_id": "5352552689983067014", "callback_data": "gen_2fa", "style": _rs()}])
        list_kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "cancel_2fa", "style": _rs()}])
        kb = {"inline_keyboard": list_kb}
    edit_message(chat_id, msg_id, render_body_text(txt), reply_markup=kb)

# ==========================================
# Telegram API & Helpers
# ==========================================
tg_session = requests.Session() # 🌟 Keep-Alive Connection (Makes bot 10x faster)
_tg_adapter = requests.adapters.HTTPAdapter(max_retries=2, pool_connections=4, pool_maxsize=20)
tg_session.mount("https://", _tg_adapter)
tg_session.mount("http://", _tg_adapter)

def api_call(method, payload=None):
    # Final defense: sanitize any keyboard even if a future/direct caller bypasses send_message().
    if isinstance(payload, dict) and "reply_markup" in payload:
        safe_markup = _sanitize_reply_markup(payload.get("reply_markup"))
        payload = dict(payload)
        if safe_markup:
            payload["reply_markup"] = safe_markup
        else:
            payload.pop("reply_markup", None)
    url = f"{BASE_URL}/{method}"
    try:
        if payload is None and "?" in method:
            # GET request (e.g. getUpdates?timeout=50)
            res = tg_session.get(url, timeout=40)
        else:
            res = tg_session.post(url, json=payload, timeout=15)
        try:
            return res.json()
        except ValueError:
            logger.warning(f"Telegram API non-JSON response [{method}]: {res.status_code} {res.text[:100]}")
            return {}
    except requests.exceptions.ConnectionError as e:
        # FIX: session.close() in a multi-threaded context is DANGEROUS —
        # other threads may be mid-request on the same session object.
        # HTTPAdapter(max_retries=2) already handles reconnects automatically.
        logger.warning(f"Telegram connection error [{method}]: {e}")
        return {}
    except Exception as e:
        logger.warning(f"Telegram API call failed [{method}]: {e}")
        return {}

UI_TRANSLATIONS = {
    "Only": "only", "only": "only", "send": "send", "Send": "send",
    "Try again": "try again", "try again": "try again",
    "please wait": "please wait", "Today's rate": "Today's rate",
    "for": "for", "send to": "send to", "already added": "already added",
    "could not be done": "could not be done", "can do": "can do",
    "do": "do", "create": "create", "find out": "find out",
    # Do not prefix these words with hyphens; that corrupted Join, Link, and Inline.
    "how": "how", "in": "in", "is": "is", "not": "not",
}

def _localize_ui_text(text):
    result = str(text) if text is not None else ""
    for source, target in sorted(UI_TRANSLATIONS.items(), key=lambda item: len(item[0]), reverse=True):
        result = result.replace(source, target)
    return result

def _apply_text_overrides(text) -> str:
    """Apply Bangla UI localization and current emoji overrides to outgoing text."""
    localized_text = _localize_ui_text(text)
    overrides = bot_settings.get("sys_emoji_overrides", {})
    if not overrides or not localized_text:
        return localized_text
    id_map = _build_id_override_map(overrides)
    if not id_map:
        return localized_text
    def _replace_eid(m):
        eid = m.group(1)
        return f'emoji-id="{id_map.get(eid, eid)}"'
    return re.sub(r'emoji-id="(\d+)"', _replace_eid, localized_text)

def _sanitize_reply_markup(reply_markup):
    """Remove malformed keyboard buttons before sending to Telegram.

    Telegram rejects any inline/reply keyboard button whose text is empty. This
    can happen when an optional custom button is loaded from old configuration.
    Buttons with a URL/callback but no visible label are not usable, so they are
    safely skipped instead of breaking OTP delivery.
    """
    if not isinstance(reply_markup, dict):
        return reply_markup
    cleaned = copy.deepcopy(reply_markup)
    for keyboard_key in ("inline_keyboard", "keyboard"):
        rows = cleaned.get(keyboard_key)
        if not isinstance(rows, list):
            continue
        valid_rows = []
        for row in rows:
            if not isinstance(row, list):
                continue
            valid_buttons = []
            for button in row:
                if not isinstance(button, dict):
                    continue
                label = button.get("text")
                if label is None or not str(label).strip():
                    logger.warning("Skipped empty keyboard button before Telegram send")
                    continue
                valid_buttons.append(button)
            if valid_buttons:
                valid_rows.append(valid_buttons)
        cleaned[keyboard_key] = valid_rows
        if not valid_rows:
            cleaned.pop(keyboard_key, None)
    return cleaned or None


def send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {"chat_id": chat_id, "text": _apply_text_overrides(text), "parse_mode": parse_mode, "disable_web_page_preview": True}
    if reply_markup:
        safe_markup = _sanitize_reply_markup(_apply_emoji_overrides(reply_markup))
        if safe_markup:
            payload["reply_markup"] = safe_markup
    return api_call("sendMessage", payload)
def edit_message(chat_id, message_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": _apply_text_overrides(text), "parse_mode": parse_mode, "disable_web_page_preview": True}
    if reply_markup:
        safe_markup = _sanitize_reply_markup(_apply_emoji_overrides(reply_markup))
        if safe_markup:
            payload["reply_markup"] = safe_markup
    resp = api_call("editMessageText", payload)
    if not resp or not resp.get("ok"):
        # Re-editing the same menu is harmless; Telegram reports it as 400.
        if resp and resp.get("error_code") == 400 and "message is not modified" in str(resp.get("description", "")).lower():
            logger.debug("editMessageText skipped: message content was already current")
            return resp
        raise RuntimeError(f"editMessageText failed: {resp}")
    return resp

def _paced_edit(chat_id, msg_id, text, target_gap):
    """Subtracts the time editMessageText will take from target_gap and sleeps —
    isse network latency chahe less be or more, animation of real-world rhythm always
    remains the same (any extra 'lag'/stutter does not accumulate).

    Rate-limit (429) is received, notify Telegram 'retry_after' for the retry_after duration once
    again try does is, taki animation beech in break na go."""
    t0 = time.monotonic()
    resp = edit_message(chat_id, msg_id, text, parse_mode="HTML")
    if resp and resp.get("error_code") == 429:
        retry_after = resp.get("parameters", {}).get("retry_after", 1)
        time.sleep(retry_after + 0.05)
        edit_message(chat_id, msg_id, text, parse_mode="HTML")
    elapsed = time.monotonic() - t0
    remaining = target_gap - elapsed
    if remaining > 0:
        time.sleep(remaining)


def send_typing_animation(chat_id, first_name):
    """Premium 2-phase boot animation — latency-compensated, so suitable for slow networks
    on also animation smooth/consistent remains is, kahin intermittently of (lag) not runs.

    Phase-1 — Loading bar (4 frames):
        ⏳ → ⚡ 30% → ⚡ 60% → ✅ 100%

    Phase-2 — Terminal typing below the bar (3 lines × 3 steps):
        Each line: 35% partial → 70% partial → bold+premium-emoji final

    Timing is paced with a monotonic clock (see _paced_edit) rather than a plain
    time.sleep() after each edit, so the on-screen rhythm stays constant even if
    a single Telegram API call is briefly slow."""

    safe_name = html.escape(str(first_name))

    # ── Premium emoji (falls back to the plain unicode glyph for non-premium
    #    Telegram users — the alt text below MUST stay the matching emoji). ──
    _PEM_HOURGLASS = '<tg-emoji emoji-id="6266992763930158001">⏳</tg-emoji>'
    _PEM_BOLT      = '<tg-emoji emoji-id="6267107057304868214">⚡</tg-emoji>'
    _PEM_CHECK     = '<tg-emoji emoji-id="6266994443262367483">✅</tg-emoji>'

    # ── Phase 1: Animated Loading Bar ────────────────────────────────────────
    _BAR_FRAMES = [
        (f"{_PEM_HOURGLASS} <b>Booting OTP System...</b>", "░░░░░░░░░░", " 0%"),
        (f"{_PEM_BOLT} <b>Booting OTP System...</b>",      "▓▓▓░░░░░░░", "30%"),
        (f"{_PEM_BOLT} <b>Booting OTP System...</b>",      "▓▓▓▓▓▓░░░░", "60%"),
        (f"{_PEM_CHECK} <b>System Ready!</b>",              "▓▓▓▓▓▓▓▓▓▓", "100%"),
    ]

    resp = send_message(chat_id, render_body_text(f"{_PEM_HOURGLASS} <b>Booting OTP System...</b>\n░░░░░░░░░░  0%"))
    if not resp or not resp.get("ok"):
        return None
    msg_id = resp["result"]["message_id"]

    for lbl, bar, pct in _BAR_FRAMES[1:]:
        _paced_edit(chat_id, msg_id, render_body_text(f"{lbl}\n{bar} {pct}"), target_gap=0.30)

    time.sleep(0.20)   # Brief pause before terminal starts

    # ── Phase 2: Terminal Typing Animation (bar stays on top as prefix) ───────
    _PREFIX = f"{_PEM_CHECK} <b>System Ready!</b>\n▓▓▓▓▓▓▓▓▓▓ 100%\n\n"

    _LINES = [
        (
            "┌──[ ROOT@FREE-OTP ]──────────────",
            "<b>┌──[ ROOT@FREE-OTP ]──────────────</b>",
        ),
        (
            "├─▶ ACCESS GRANTED ✔",
            '<b>├─<tg-emoji emoji-id="6301055479539828724">▶</tg-emoji>'
            ' ACCESS GRANTED <tg-emoji emoji-id="6266781064992134926">✔</tg-emoji></b>',
        ),
        (
            f"└─▶ Hey {safe_name}, Welcome to Free OTP Bot!",
            f'<b>└─<tg-emoji emoji-id="6264896248659056036">▶</tg-emoji>'
            f' Hey {safe_name}, Welcome to Free OTP Bot!</b>',
        ),
    ]

    completed_fmt = []
    for plain_line, fmt_line in _LINES:
        n = len(plain_line)
        for chunk in (0.35, 0.70):
            cut = max(1, int(n * chunk))
            parts = completed_fmt[:]
            parts.append(plain_line[:cut] + "▌")
            _paced_edit(chat_id, msg_id, _PREFIX + "\n".join(parts), target_gap=0.38)
        completed_fmt.append(fmt_line)
        _paced_edit(chat_id, msg_id, _PREFIX + "\n".join(completed_fmt), target_gap=0.30)

    return msg_id

# FIX: if user "Check Joined" or /start repeatedly (double-tap) dabaye to do
# animation a single chat on TAKRA jaate the (both your-your message bhej/edit
# when doing that) — this causes the 'message appearing here-and-there / half-visible' bug
# was occurring. The per-chat guard now ensures: only one welcome animation per user at a time
# animation can run, duplicate trigger silently ignore be goes.
_active_welcomes = set()
_active_welcomes_lock = threading.Lock()

def _welcome_user(chat_id, first_name):
    """/start and check_fj for both shared welcome flow.
    Duplicate code in one place — if the flow changes then change only here."""
    with _active_welcomes_lock:
        if chat_id in _active_welcomes:
            return  # already an animation is running for this chat — skip
        _active_welcomes.add(chat_id)
    try:
        get_user(chat_id)
        _process_pending_referral(chat_id)
        send_typing_animation(chat_id, first_name)
        safe_name = html.escape(str(first_name))
        # Start message editable from admin panel (Edit Messages → START)
        c_msg = bot_settings.get("custom_messages", {}).get("start", {})
        final_card = c_msg.get("text") or DEFAULT_CUSTOM_MESSAGES["start"]["text"]
        final_card = final_card.replace("{name}", safe_name).replace("{first_name}", safe_name)
        if DEV_CREDIT not in final_card:
            final_card += f"\n{DEV_CREDIT_HTML}"
        send_message(chat_id, render_body_text(final_card), reply_markup=main_menu(chat_id))
    finally:
        with _active_welcomes_lock:
            _active_welcomes.discard(chat_id)

def delete_message(chat_id, message_id):
    return api_call("deleteMessage", {"chat_id": chat_id, "message_id": message_id})

def answer_callback(callback_id, text="", show_alert=False):
    api_call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text, "show_alert": show_alert})

def send_document(chat_id, filename, text_content):
    url = f"{BASE_URL}/sendDocument"
    files = {'document': (filename, text_content)}
    data = {'chat_id': chat_id}
    try:
        tg_session.post(url, data=data, files=files, timeout=30)
    except Exception as e:
        logger.warning(f"send_document error: {e}")

# 🌟 Local User List for Broadcasts
all_known_users = set()
_users_set_lock = threading.Lock()  # Thread-safe users set access

def sync_users_list():
    global all_known_users
    try:
        if os.path.exists("users_list.json"):
            with open("users_list.json", "r") as f:
                all_known_users = set(json.load(f))
        if not all_known_users and local_users_db:
            all_known_users = set(str(k) for k in local_users_db.keys())
            with open("users_list.json", "w") as f:
                json.dump(list(all_known_users), f)
    except Exception as e:
        logger.warning(f"sync_users_list error: {e}")

def _save_users_list():
    try:
        fd, tmp_path = tempfile.mkstemp(dir=".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(list(all_known_users), f)
            os.replace(tmp_path, "users_list.json")
        except Exception:
            try: os.unlink(tmp_path)
            except Exception: pass
            raise
    except Exception as e:
        logger.warning(f"_save_users_list error: {e}")

def register_user_local(uid):
    uid_str = str(uid)
    # FIX: Read-check-write must ALL be inside the same lock to prevent race condition
    # where two threads both see "not in set" and both add+save simultaneously.
    with _users_set_lock:
        if uid_str not in all_known_users:
            all_known_users.add(uid_str)
            threading.Thread(target=_save_users_list, daemon=True).start()


# ==========================================
# 🌟 Local User Database (Firebase-Free Mode)
# ==========================================
USERS_DB_FILE = "users_db.json"
WITHDRAWALS_DB_FILE = "withdrawals_db.json"
local_users_db = {}
local_withdrawals_db = {}
_users_db_lock = threading.Lock()  # Thread-safe user DB access
_users_save_event = threading.Event()

def _request_users_db_save():
    """Coalesce frequent user changes into one background disk write."""
    _users_save_event.set()

def _users_db_save_worker():
    while True:
        _users_save_event.wait(timeout=1.0)
        if _users_save_event.is_set():
            _users_save_event.clear()
            time.sleep(0.25)  # collect bursts of balance/OTP updates
            try:
                _save_local_users_db()
            except Exception as e:
                logger.warning(f"Debounced users DB save error: {e}")

def _load_local_users_db():
    global local_users_db, local_withdrawals_db
    try:
        if os.path.exists(USERS_DB_FILE):
            with open(USERS_DB_FILE, "r", encoding="utf-8") as f:
                raw = f.read()
            if raw.strip():
                local_users_db = json.loads(raw)
    except Exception as e:
        logger.warning(f"users_db load error: {e} — starting fresh")
        local_users_db = {}
    try:
        if os.path.exists(WITHDRAWALS_DB_FILE):
            with open(WITHDRAWALS_DB_FILE, "r", encoding="utf-8") as f:
                raw = f.read()
            if raw.strip():
                local_withdrawals_db = json.loads(raw)
    except Exception as e:
        logger.warning(f"withdrawals_db load error: {e} — starting fresh")
        local_withdrawals_db = {}

def _save_local_users_db():
    try:
        with _users_db_lock:
            snapshot = copy.deepcopy(local_users_db)
        dir_name = os.path.dirname(os.path.abspath(USERS_DB_FILE))
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2)
            os.replace(tmp_path, USERS_DB_FILE)
        except Exception:
            try: os.unlink(tmp_path)
            except Exception: pass
            raise
    except Exception as e:
        logger.warning(f"_save_local_users_db error: {e}")

_withdrawals_db_lock = threading.Lock()  # Thread-safe withdrawals DB access

def _save_local_withdrawals_db():
    try:
        with _withdrawals_db_lock:
            snapshot = dict(local_withdrawals_db)
        dir_name = os.path.dirname(os.path.abspath(WITHDRAWALS_DB_FILE))
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2)
            os.replace(tmp_path, WITHDRAWALS_DB_FILE)
        except Exception:
            try: os.unlink(tmp_path)
            except Exception: pass
            raise
    except Exception as e:
        logger.warning(f"_save_local_withdrawals_db error: {e}")

_load_local_users_db()
# One saver replaces thousands of short-lived save threads under load.
threading.Thread(target=_users_db_save_worker, daemon=True, name="users-db-saver").start()
# Start sync AFTER local_users_db is loaded — fixes race condition
threading.Thread(target=sync_users_list, daemon=True).start()

def _new_user_dict(user_id):
    """Default user record — defined in one place, used in three places. Duplicate removed."""
    return {"user_id": int(user_id), "balance": 0.0, "total_refers": 0, "total_otps": 0, "banned": False, "verified": False}

def _get_local_user(user_id):
    uid = str(user_id)
    with _users_db_lock:
        if uid not in local_users_db:
            local_users_db[uid] = _new_user_dict(user_id)
            _request_users_db_save()
        return dict(local_users_db[uid])

def _update_local_user(user_id, updates):
    uid = str(user_id)
    with _users_db_lock:
        if uid not in local_users_db:
            local_users_db[uid] = _new_user_dict(user_id)
        local_users_db[uid].update(updates)
    _request_users_db_save()

def _increment_local_user(user_id, field, amount):
    uid = str(user_id)
    with _users_db_lock:
        if uid not in local_users_db:
            local_users_db[uid] = _new_user_dict(user_id)
        local_users_db[uid][field] = local_users_db[uid].get(field, 0) + amount
    _request_users_db_save()

def _save_local_withdrawal(req_id, data):
    local_withdrawals_db[req_id] = data
    local_withdrawals_db[req_id]["timestamp"] = time.time()
    threading.Thread(target=_save_local_withdrawals_db, daemon=True).start()

def _update_local_withdrawal(req_id, updates):
    if req_id in local_withdrawals_db:
        local_withdrawals_db[req_id].update(updates)
        threading.Thread(target=_save_local_withdrawals_db, daemon=True).start()

def broadcast_copymessage(from_chat_id, msg_id):
    success = 0
    failed = 0
    users = list(all_known_users)
    
    # 🌟 Dedicated Connection Pool for Broadcast (Fixes Port Exhaustion & Network Lag)
    b_session = requests.Session()
    url = f"{BASE_URL}/copyMessage"
    
    try:
        for user_id in users:
            payload = {"chat_id": user_id, "from_chat_id": from_chat_id, "message_id": msg_id}
            try:
                res = b_session.post(url, json=payload, timeout=5).json()
                if res.get("ok"): success += 1
                else: failed += 1
            except Exception as e:
                failed += 1
            time.sleep(0.035) # Safe speed (28 msgs/sec) to prevent Telegram Ban
    finally:
        b_session.close()
        
    send_message(from_chat_id, render_body_text(f"📢 <b>Broadcast Completed!</b>\n✅ Success: {success}\n❌ Failed: {failed}\n👥 Total Sent: {len(users)}"))


def broadcast_text_message(txt):
    """Broadcast a plain text/HTML message to all known users (sendMessage API)."""
    b_session = requests.Session()
    url = f"{BASE_URL}/sendMessage"
    rendered_txt = _apply_text_overrides(txt)
    success, failed = 0, 0
    try:
        for u_id in list(all_known_users):
            try:
                res = b_session.post(url, json={"chat_id": u_id, "text": rendered_txt, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=5).json()
                if res.get("ok"): success += 1
                else: failed += 1
            except Exception:
                failed += 1
            time.sleep(0.035)
    finally:
        b_session.close()
    logger.info(f"Broadcast: {success} sent, {failed} failed")

_STYLES = ["primary", "success", "danger"]

# Thread-local counter: each thread (request) has its OWN independent cycle.
# This prevents 500 concurrent worker threads from scrambling each other's button colors.
_tl = threading.local()

def _reset_btn_counter():
    """Reset THIS thread's counter to 0 (primary). Call at start of every keyboard builder."""
    _tl.i = 0

def _get_service_emoji_id(srv, apps_db):
    """Service name (WHATSAPP, TELEGRAM, ...) for premium-emoji id find.
    Nexa/VoltX/Stex: the exact same lookup was duplicated in three places — now it is shared."""
    emoji_id = "5257969839313526622"  # default/fallback icon
    for app_key, app_data in apps_db.items():
        if srv.upper() == app_key or srv.upper() in app_key or app_key in srv.upper():
            if "id" in app_data:
                emoji_id = app_data["id"]
                break
    return emoji_id

def _download_telegram_txt_document(chat_id, doc):
    """Upload did went .txt document Telegram from download by text content return does is.
    If the format is wrong, send an error to the user and None return does is (caller to only
    `if content is None: return` to do so). the exact same in three places getFile/download
    logic was duplicated — now shared helper."""
    if not doc["file_name"].endswith(".txt"):
        send_message(chat_id, render_body_text(f"{PEM['no']} Please upload a .txt file only."))
        return None
    file_id = doc["file_id"]
    try:
        file_info = tg_session.get(f"{BASE_URL}/getFile?file_id={file_id}", timeout=15).json()
    except ValueError:
        send_message(chat_id, render_body_text(f"{PEM['no']} Could not download file (invalid response). Try again."))
        return None
    if not file_info.get("ok") or not file_info.get("result", {}).get("file_path"):
        send_message(chat_id, render_body_text(f"{PEM['no']} Could not get file path from Telegram. Try again."))
        return None
    file_path = file_info["result"]["file_path"]
    return tg_session.get(f"{FILE_URL}{file_path}", timeout=30).text

_NUMBER_COL_ALIASES = ("number", "mobile", "phone", "msisdn", "num", "recipient", "to")
_MESSAGE_COL_ALIASES = ("message", "sms", "text", "content", "msg", "body")

def _find_header_column_indices(rows, n_col_name, m_col_name, default_n_idx, default_m_idx):
    """HTML table of first row (header) in column-name from number/message column of
    real index find. not mile to caller of diye gaye default index use are.
    Two places (AJAX-backup path and Auto Captcha panel path) this exact same header-scan
    logic was duplicated — now shared.

    FIX: Many panels write the column header as "SMS", not "Message" — and
    the number column as "Mobile"/"Phone" also write sakte are. before only exact
    n_col_name/m_col_name (that panel-config in set is, default "number"/"message")
    would match — if the panel header text was different (like "SMS"), it would match
    fail becomes and ghalat column select becomes (because of this "Connected, but
    couldn't parse OTP data!" gets tha, jabki panel in data correct tha).
    # Give priority to the configured name, then try known aliases.
    are — so that a header like 'SMS' will also be detected as equivalent to 'message'."""
    final_n_idx, final_m_idx = default_n_idx, default_m_idx
    if not rows:
        return final_n_idx, final_m_idx
    header_cells = rows[0].find_all(['th', 'td'])
    header_texts = [cell.get_text(strip=True).lower() for cell in header_cells]

    n_candidates = [n_col_name] + [a for a in _NUMBER_COL_ALIASES if a != n_col_name]
    m_candidates = [m_col_name] + [a for a in _MESSAGE_COL_ALIASES if a != m_col_name]

    for candidate in n_candidates:
        matched = [i for i, c_text in enumerate(header_texts) if candidate in c_text]
        if matched:
            final_n_idx = matched[0]
            break

    for candidate in m_candidates:
        matched = [i for i, c_text in enumerate(header_texts) if candidate in c_text]
        if matched:
            final_m_idx = matched[0]
            break

    return final_n_idx, final_m_idx

def _rs():
    """Return next style (primary→success→danger→...) for THIS thread. Auto-inits if needed."""
    if not hasattr(_tl, 'i'):
        _tl.i = 0
    s = _STYLES[_tl.i % 3]
    _tl.i += 1
    return s

def render_body_text(text):
    if not text: return str(text)
    parts = re.split(r'(<tg-emoji.*?</tg-emoji>)', str(text))
    for i in range(len(parts)):
        if not parts[i].startswith('<tg-emoji'):
            for normal_emj, prem_id in GLOBAL_BODY_EMOJIS.items():
                if normal_emj in parts[i]:
                    parts[i] = parts[i].replace(normal_emj, f'<tg-emoji emoji-id="{prem_id}">{normal_emj}</tg-emoji>')
    # _apply_text_overrides handles override replacement (same logic, no duplication)
    return _apply_text_overrides("".join(parts))

def extract_premium_html(msg):
    text = msg.get("text", msg.get("caption", ""))
    entities = msg.get("entities", msg.get("caption_entities", []))
    if not entities: return text
    try:
        b_text = text.encode('utf-16-take')
        c_entities = [e for e in entities if e.get("type") == "custom_emoji"]
        c_entities.sort(key=lambda x: x["offset"], reverse=True)
        for ent in c_entities:
            offset = ent["offset"] * 2
            length = ent["length"] * 2
            eid = ent["custom_emoji_id"]
            emoji_char = b_text[offset:offset+length].decode('utf-16-take')
            html_tag = f'<tg-emoji emoji-id="{eid}">{emoji_char}</tg-emoji>'
            replacement = html_tag.encode('utf-16-take')
            b_text = b_text[:offset] + replacement + b_text[offset+length:]
        return b_text.decode('utf-16-take')
    except Exception as e:
        return text 

# ==========================================
# 🌍 ALL-COUNTRY dial code table (fallback when not present in premium_flags)
#    Calling code -> ISO-2. Flag itself regional-indicator letters from becomes is,
#    so every country gets the correct flag and ISO.
# ==========================================
DIAL_CODES = {
    "1242": "BS", "1246": "BB", "1264": "AI", "1268": "AG", "1284": "VG",
    "1340": "VI", "1345": "KY", "1441": "BM", "1473": "GD", "1649": "TC",
    "1664": "MS", "1670": "MP", "1671": "GU", "1684": "AS", "1721": "SX",
    "1758": "LC", "1767": "DM", "1784": "VC", "1787": "PR", "1809": "DO",
    "1829": "DO", "1849": "DO", "1868": "TT", "1869": "KN", "1876": "JM",
    "1939": "PR", "1": "US",
    "20": "EG", "211": "SS", "212": "MA", "213": "DZ", "216": "TN",
    "218": "LY", "220": "GM", "221": "SN", "222": "MR", "223": "ML",
    "224": "GN", "225": "CI", "226": "BF", "227": "the", "228": "TG",
    "229": "BJ", "230": "MU", "231": "LR", "232": "SL", "233": "GH",
    "234": "NG", "235": "TD", "236": "CF", "237": "CM", "238": "CV",
    "239": "ST", "240": "GQ", "241": "GA", "242": "CG", "243": "CD",
    "244": "AO", "245": "GW", "246": "IO", "247": "AC", "248": "SC",
    "249": "SD", "250": "RW", "251": "ET", "252": "SO", "253": "DJ",
    "254": "of", "255": "TZ", "256": "UG", "257": "BI", "258": "MZ",
    "260": "ZM", "261": "MG", "262": "RE", "263": "ZW", "264": "NA",
    "265": "MW", "266": "LS", "267": "BW", "268": "SZ", "269": "KM",
    "27": "ZA", "290": "SH", "291": "ER", "297": "AW", "298": "FO",
    "299": "GL", "30": "GR", "31": "NL", "32": "BE", "33": "FR",
    "34": "ES", "350": "GI", "351": "PT", "352": "LU", "353": "IE",
    "354": "IS", "355": "AL", "356": "MT", "357": "CY", "358": "FI",
    "359": "BG", "36": "HU", "370": "LT", "371": "LV", "372": "EE",
    "373": "MD", "374": "AM", "375": "BY", "376": "AD", "377": "MC",
    "378": "SM", "380": "UA", "381": "RS", "382": "ME", "383": "XK",
    "385": "HR", "386": "SI", "387": "BA", "389": "MK", "39": "IT",
    "40": "RO", "41": "CH", "420": "CZ", "421": "SK", "423": "LI",
    "43": "AT", "44": "GB", "45": "DK", "46": "from", "47": "NO",
    "48": "PL", "49": "give", "500": "FK", "501": "BZ", "502": "GT",
    "503": "SV", "504": "HN", "505": "NI", "506": "CR", "507": "PA",
    "508": "PM", "509": "HT", "51": "on", "52": "MX", "53": "CU",
    "54": "AR", "55": "BR", "56": "CL", "57": "CO", "58": "VE",
    "590": "GP", "591": "BO", "592": "GY", "593": "EC", "594": "GF",
    "595": "PY", "596": "MQ", "597": "SR", "598": "UY", "599": "CW",
    "60": "MY", "61": "AU", "62": "ID", "63": "PH", "64": "NZ",
    "65": "SG", "66": "TH", "670": "TL", "672": "NF", "673": "BN",
    "674": "NR", "675": "PG", "676": "TO", "677": "SB", "678": "VU",
    "679": "FJ", "680": "PW", "681": "WF", "682": "CK", "683": "NU",
    "685": "WS", "686": "of", "687": "NC", "688": "TV", "689": "PF",
    "690": "TK", "691": "FM", "692": "MH", "7": "RU", "81": "JP",
    "82": "KR", "84": "VN", "86": "CN", "850": "KP", "852": "HK",
    "853": "MO", "855": "KH", "856": "LA", "880": "BD", "886": "TW",
    "90": "TR", "91": "IN", "92": "PK", "93": "AF", "94": "LK",
    "95": "MM", "960": "MV", "961": "LB", "962": "that", "963": "SY",
    "964": "IQ", "965": "KW", "966": "SA", "967": "this", "968": "OM",
    "970": "PS", "971": "AE", "972": "IL", "973": "BH", "974": "QA",
    "975": "BT", "976": "MN", "977": "NP", "98": "IR", "992": "TJ",
    "993": "TM", "994": "AZ", "995": "GE", "996": "KG", "998": "UZ",
    "379": "VA",              # 🇻🇦 Vatican City (its own dedicated code)
    "76": "KZ", "77": "KZ",   # 🇰🇿 Kazakhstan mobile prefixes (overlaps with Russia's +7,
                               #     specific 2-digit prefix before match is to Kazakhstan correct will arrive)
}
_DIAL_CODES_SORTED = sorted(DIAL_CODES.keys(), key=len, reverse=True)

def iso_to_flag_emoji(iso2):
    """ISO-2 (e.g. 'NG') -> real unicode flag emoji, regional indicator letters from."""
    iso2 = str(iso2 or "").strip().upper()
    if len(iso2) != 2 or not iso2.isalpha():
        return "🌍"
    return chr(0x1F1E6 + ord(iso2[0]) - 65) + chr(0x1F1E6 + ord(iso2[1]) - 65)

def match_country_code(clean_num):
    """Match the calling code from the start of a number (without +) — premium_flags +
       DIAL_CODES both in from, longest (specific) match jeetay ga.
       Returns (code, iso) or (None, None)."""
    all_codes = set(bot_settings.get("premium_flags", {}).keys()) | set(DIAL_CODES.keys())
    for code in sorted(all_codes, key=len, reverse=True):
        if clean_num.startswith(code):
            pf = bot_settings.get("premium_flags", {}).get(code)
            iso = pf.get("iso") if pf else DIAL_CODES.get(code)
            return code, iso
    return None, None

def format_display_number(num):
    """+2347020521799 -> +234-7020521799 (calling code of after hyphen, jaisa panels dikhate are)."""
    clean = str(num or "").replace("+", "").replace(" ", "")
    code, _ = match_country_code(clean)
    if code and len(clean) > len(code):
        return f"+{code}-{clean[len(code):]}"
    return f"+{clean}"

def get_flag_info_from_num(num):
    clean = num.replace("+", "").replace(" ", "")
    sorted_codes = sorted(bot_settings.get("premium_flags", {}).keys(), key=len, reverse=True)
    for code in sorted_codes:
        if clean.startswith(code):
            data = bot_settings.get("premium_flags", {}).get(code)
            if not data:
                continue
            return data.get("char", "🌍"), data.get("iso", "XX"), data.get("id")
    # 🌍 ALL-COUNTRY fallback — from the dial-code table (no custom emoji id, plain unicode flag)
    code, iso = match_country_code(clean)
    if iso:
        return iso_to_flag_emoji(iso), iso, None
    return "🌍", "XX", None

def get_flag_and_code(num):
    char, iso, _ = get_flag_info_from_num(num)
    return char, iso

def _get_cc_from_iso(iso):
    """Return country-code digits for a given ISO-2 code (e.g. 'MG' → '261'), or None."""
    for code, data in bot_settings.get("premium_flags", {}).items():
        if data.get("iso") == iso:
            return code
    return None

def _get_cc_from_num(num_str):
    """Return country-code digits embedded at the start of num_str, or None."""
    clean = str(num_str).replace("+", "").replace(" ", "")
    sorted_codes = sorted(bot_settings.get("premium_flags", {}).keys(), key=len, reverse=True)
    for code in sorted_codes:
        if clean.startswith(code):
            return code
    return None

def get_flag_info_html(num_or_iso):
    if len(num_or_iso) == 2:
        for code, data in bot_settings.get("premium_flags", {}).items():
            if data.get("iso") == num_or_iso:
                eid = data.get("id")
                char = data.get("char")
                if eid: return f'<tg-emoji emoji-id="{eid}">{char}</tg-emoji>'
                return char
        return "🌍"
        
    char, _, eid = get_flag_info_from_num(num_or_iso)
    if eid:
        return f'<tg-emoji emoji-id="{eid}">{char}</tg-emoji>'
    return char

_MASK_EMOJI = '<tg-emoji emoji-id="6228781436330054904">⭐</tg-emoji>'

def mask_number(num, user_id=None):
    clean = num.replace("+", "").replace(" ", "")
    if user_id:
        tag = f'<a href="tg://user?id={user_id}">USER</a>'
    else:
        tag = " 𝗣𝗔𝗞"
    if len(clean) > 6: return f"{clean[:4]}『🇵🇰 𝗣𝗔𝗞 🇵🇰』{clean[-3:]}"
    elif len(clean) > 2: return f"{clean[:1]}『🇵🇰 𝗣𝗔𝗞 🇵🇰』{clean[-1:]}"
    return clean

# ==========================================
# 🌟 ADVANCED SERVICE & LANGUAGE DETECTION
# ==========================================

SERVICE_SMS_KEYWORDS = {
    # 🟢 Social Media & Chat (Added Arabic Keywords)
    "whatsapp": ["whatsapp", "wa", "wap", "w/a", "whatsapp business", "wa.me", "wa code", "wh", "whatsapp", "whatsapp", "whatsapp", "whatsapp", "whatsapp", "whatsapp", "whatsapp", "whatsapp", "whatsapp", "whatsapp", "vatsap", "uotsap", "votsap", "vats app", "whatsapp", "whatsapp", "whatsapp", "whatsapp", "whatsapp", "whatsapp", "whatsapp", "whatsapp", "whatsapp", "whatsapp", "whatsapp", "whatsapp", "whatsapp", "whatsapp", "whatsapp", "whatsapp"],
    "facebook": ["facebook", "fb", "meta", "fbook", "fb code", "facebook code", "facebook", "facebook"],
    "instagram": ["instagram", "insta", "ig", "ig code", "instagram code", "instagram", "instagram"],
    "telegram": ["telegram", "tg", "tele", "telegram code", "tg code", "t.me", "telegram", "telegram"],
    "tiktok": ["tiktok", "tik tok", "tikvideo", "tiktok code", "tik code", "tik tok"],
    "snapchat": ["snapchat", "snap", "snap code", "snap chat"],
    "twitter": ["twitter", "x.com", "x code", "twitter code", "twitter"],
    "discord": ["discord", "discord code", "discord"],
    "viber": ["viber", "viber code", "viber"],
    "line": ["line", "line code", "line verification", "line"],
    "wechat": ["wechat", "we chat", "wechat code", "we chat"],
    "signal": ["signal", "signal code", "signal"],
    "linkedin": ["linkedin", "linked in", "linked in"],
    "imo": ["imo", "imo code", "imo verification", "imo"],
    "kakaotalk": ["kakao", "kakaotalk", "kakao"],
    "qq": ["qq", "tencent qq"],
    "vk": ["vk", "vkontakte"],

    # 🔵 Tech & Mail
    "google": ["google", "gmail", "youtube", "g-", "google voice", "google", "google"],
    "microsoft": ["microsoft", "ms", "outlook", "live.com", "hotmail"],
    "apple": ["apple", "icloud", "itunes", "apple id"],
    "yahoo": ["yahoo", "yahoo code", "ymail"],
    "protonmail": ["proton", "protonmail"],
    
    # 💰 Crypto & Trading
    "binance": ["binance", "bnb", "binances"],
    "coinbase": ["coinbase"],
    "okx": ["okx", "okex"],
    "kucoin": ["kucoin"],
    "bybit": ["bybit"],
    "huobi": ["huobi", "htx"],
    "mexc": ["mexc"],
    "trustwallet": ["trust wallet", "trustwallet"],

    # 🇵🇰 Pakistani Wallets, Banks & Apps
    "easypaisa": ["easypaisa", "easy paisa", "easypaisa code", "telenor microfinance", "tmb"],
    "jazzcash": ["jazzcash", "jazz cash", "jazzcash code", "mobilink microfinance"],
    "sadapay": ["sadapay", "sada pay"],
    "nayapay": ["nayapay", "new pay"],
    "upaisa": ["upaisa", "u paisa", "ufone wallet"],
    "raast": ["raast", "raast id", "raast payment"],
    "hbl": ["hbl", "habib bank", "hbl konnect"],
    "meezan": ["meezan", "meezan bank"],
    "ubl": ["ubl", "united bank", "ubl omni", "ubl digital"],
    "mcb": ["mcb", "mcb bank", "mcb live"],
    "alfalah": ["alfalah", "bank alfalah"],
    "askari": ["askari", "askari bank"],
    "faysal": ["faysal", "faysal bank"],
    "jsbank": ["js bank", "jsbank", "zindagi"],
    "allied": ["allied bank", "abl"],
    "nbp": ["nbp", "national bank of pakistan"],
    "jazz": ["jazz", "jazz world", "mobilink"],
    "zong": ["zong", "my zong", "zong pk"],
    "telenor": ["telenor", "my telenor", "telenor pk"],
    "ufone": ["ufone", "my ufone"],
    "ptcl": ["ptcl", "ptcl code"],
    "bykea": ["bykea", "by kea"],
    "careem": ["careem", "careem code", "careem pay"],
    "indrive": ["indrive", "in drive"],
    "nadra": ["nadra", "pak id", "pakid"],
    "olx": ["olx", "olx pakistan"],
    "cheetay": ["cheetay"],
    "krave": ["krave mart", "kravemart"],
    "airlift": ["airlift"],

    # 💳 Finance & Wallets (International)
    "paytm": ["paytm", "paytm code", "paytm otp"],
    "phonepe": ["phonepe", "phone on", "phonepe code"],
    "gpay": ["gpay", "google pay", "googlepay"],
    "upi": ["upi", "upi code", "upi otp"],
    "paypal": ["paypal", "pay pal"],
    "cashapp": ["cash app", "cashapp"],
    "wise": ["wise", "transferwise"],

    # 🛒 E-commerce & Delivery
    "amazon": ["amazon", "amzn", "amazon code"],
    "ebay": ["ebay"],
    "aliexpress": ["aliexpress", "ali express"],
    "alibaba": ["alibaba"],
    "daraz": ["daraz", "daraz code"],
    "foodpanda": ["foodpanda", "food panda"],
    "uber": ["uber", "uber code", "uber verification", "uber eats"],
    "pathao": ["pathao", "pathao ride"],

    # 🎮 Gaming & Entertainment
    "netflix": ["netflix", "netflix code"],
    "spotify": ["spotify", "spotify code"],
    "steam": ["steam", "steam guard"],
    "epicgames": ["epic games", "epicgames"],
    "roblox": ["roblox", "roblox code"],
    "riotgames": ["riot", "riot games", "valorant", "league of legends"],
    "garena": ["garena", "free fire", "freefire"],
    "playstation": ["playstation", "psn"],

    # 🎲 Betting & Casino
    "1xbet": ["1xbet", "1x bet"],
    "melbet": ["melbet", "melbet code"],
    "linebet": ["linebet"],
    "bet365": ["bet365"],
    "megapari": ["megapari"],

    # ❤️ Dating
    "tinder": ["tinder", "tinder code"],
    "bumble": ["bumble"],
    "badoo": ["badoo"],

    # 📲 OTP Providers / SMS Gateways (PAK + INTL)
    "gro5me": ["gro5me", "gro 5 me", "groSMS", "gro sms", "grow5me", "gro5"],
    "textlocal": ["textlocal", "text local"],
    "msg91": ["msg91", "msg 91"],
    "2factor": ["2factor", "2 factor"],
    "kaleyra": ["kaleyra"],
    "valueFirst": ["valuefirst", "value first"],
    "smscountry": ["smscountry", "sms country"],
    "smsjust": ["smsjust", "sms just"],
    "exotel": ["exotel"],
    "alertsms": ["alertsms", "alert sms"],
    # 🇵🇰 Pakistani SMS gateways / masks
    "veevotech": ["veevotech", "veevo tech"],
    "bulksmspk": ["bulksms", "bulk sms pk", "smspk"],
    "branded": ["branded sms", "brandedsms"],
}

def _kw_match(kw, text_lower):
    """Keyword to text in match do.
    Short keywords (<=3 pure-alpha chars) for word-boundary (\b) use do
    so that 'wa' 'swap' in or 'wh' 'which' in incorrect match na be.
    Special chars those keywords (w/a, t.me, wa.me, g-) for simple 'in' check."""
    if len(kw) <= 3 and kw.isalpha():
        return bool(re.search(r'\b' + re.escape(kw) + r'\b', text_lower))
    return kw in text_lower

def detect_service(text):
    """SMS/OTP message text from service detect do.
    Word-boundary matching for short keywords — avoids false positives."""
    text_lower = str(text).lower()
    for service_key, keywords in SERVICE_SMS_KEYWORDS.items():
        for kw in keywords:
            if _kw_match(kw, text_lower):
                return service_key.upper()
    return None

# Set of known service keys for fast lookup
_KNOWN_SERVICE_KEYS = None
def _get_known_service_keys():
    global _KNOWN_SERVICE_KEYS
    if _KNOWN_SERVICE_KEYS is None:
        _KNOWN_SERVICE_KEYS = {k.upper() for k in SERVICE_SMS_KEYWORDS}
    return _KNOWN_SERVICE_KEYS

def get_service_info_html(service_text, msg_text=""):
    s = str(service_text).upper().strip()
    m = str(msg_text).lower().strip()
    apps = bot_settings.get("premium_apps", {})

    # if s already one known service key is (such as "INSTAGRAM", "WHATSAPP")
    # so DO NOT override msg_text AT ALL — the caller has already detected correctly.
    # Scan msg_text only when s is unknown or generic.
    known_keys = _get_known_service_keys()
    detected_service = s
    if s not in known_keys and m:
        for service_key, keywords in SERVICE_SMS_KEYWORDS.items():
            for kw in keywords:
                if _kw_match(kw, m):
                    detected_service = service_key.upper()
                    break
            if detected_service != s:
                break

    clean_s = re.sub(r'[^\w\s]', '', detected_service).strip()
    
    for app_name, data in apps.items():
        if app_name == detected_service or app_name == clean_s or app_name in detected_service or detected_service in app_name:
            full_name = data.get("name", app_name.title())
            char = data.get("char", "📱")
            eid = data.get("id")
            if eid: return full_name, f'<tg-emoji emoji-id="{eid}">{char}</tg-emoji>'
            return full_name, char
            
    if len(detected_service) > 20:
        return "Message", "💬"
        
    return detected_service.title(), "📱"

def detect_language(text):
    if not text: return "#EN"
    text_str = str(text)

    # 1. Accurate alphabet detection using Unicode Block (100% Accurate for scripts)
    if any('\u0600' <= c <= '\u06ff' for c in text_str): return "#AR" # Arabic / Persian / Urdu
    if any('\u0980' <= c <= '\u09ff' for c in text_str): return "#BN" # Bengali
    if any('\u0900' <= c <= '\u097f' for c in text_str): return "#HI" # Hindi / Marathi / Nepali
    if any('\u0a00' <= c <= '\u0a7f' for c in text_str): return "#PA" # Punjabi (Gurmukhi)
    if any('\u0a80' <= c <= '\u0aff' for c in text_str): return "#GU" # Gujarati
    if any('\u0b00' <= c <= '\u0b7f' for c in text_str): return "#OR" # Odia
    if any('\u0b80' <= c <= '\u0bff' for c in text_str): return "#TA" # Tamil
    if any('\u0c00' <= c <= '\u0c7f' for c in text_str): return "#TE" # Telugu
    if any('\u0c80' <= c <= '\u0cff' for c in text_str): return "#KN" # Kannada
    if any('\u0d00' <= c <= '\u0d7f' for c in text_str): return "#ML" # Malayalam
    if any('\u0d80' <= c <= '\u0dff' for c in text_str): return "#SI" # Sinhala
    if any('\u0e00' <= c <= '\u0e7f' for c in text_str): return "#TH" # Thai
    if any('\u0e80' <= c <= '\u0eff' for c in text_str): return "#LO" # Lao
    if any('\u0f00' <= c <= '\u0fff' for c in text_str): return "#BO" # Tibetan
    if any('\u1000' <= c <= '\u109f' for c in text_str): return "#MY" # Burmese (Myanmar)
    if any('\u1200' <= c <= '\u137f' for c in text_str): return "#AM" # Amharic (Ethiopic)
    if any('\u1780' <= c <= '\u17ff' for c in text_str): return "#KM" # Khmer
    if any('\u10a0' <= c <= '\u10ff' for c in text_str): return "#of" # Georgian
    if any('\u0530' <= c <= '\u058f' for c in text_str): return "#HY" # Armenian
    if any('\u0590' <= c <= '\u05ff' for c in text_str): return "#HE" # Hebrew
    if any('\u0370' <= c <= '\u03ff' for c in text_str): return "#EL" # Greek
    if any('\u0400' <= c <= '\u04ff' for c in text_str): return "#RU" # Russian / Ukrainian (Cyrillic)
    if any('\u4e00' <= c <= '\u9fff' for c in text_str): return "#ZH" # Chinese
    if any(('\u3040' <= c <= '\u309f') or ('\u30a0' <= c <= '\u30ff') for c in text_str): return "#JA" # Japanese
    if any('\uac00' <= c <= '\ud7af' for c in text_str): return "#to" # Korean

    # 2. Language detection using OTP Keywords (Latin script languages)
    text_lower = text_str.lower()
    
    # Asian / Pacific
    if any(w in text_lower for w in ["kode verifikasi", "jangan bagikan", "rahasia"]): return "#ID" # Indonesian
    if any(w in text_lower for w in ["kod pengesahan", "jangan kongsi"]): return "#MS" # Malay
    if any(w in text_lower for w in ["ma cua ban", "khong chia from", "ma xac minh"]): return "#VN" # Vietnamese
    if any(w in text_lower for w in ["ang iyong code", "huwag ibahagi"]): return "#TL" # Tagalog / Filipino
    
    # European / Americas
    if any(w in text_lower for w in ["codigo", "tu codigo", "verificacion", "no compartas"]): return "#ES" # Spanish
    if any(w in text_lower for w in ["seu codigo", "codigo give verificacao", "nao compartilhe"]): return "#PT" # Portuguese
    if any(w in text_lower for w in ["code secret", "the partagez pas", "votre code"]): return "#FR" # French
    if any(w in text_lower for w in ["dein code", "bestaetigungscode", "nicht teilen"]): return "#give" # German
    if any(w in text_lower for w in ["il tuo codice", "codice di verifica", "non condividere"]): return "#IT" # Italian
    if any(w in text_lower for w in ["twoj kod", "nie udostepniaj", "kod weryfikacyjny"]): return "#PL" # Polish
    if any(w in text_lower for w in ["dogrulama kodu", "paylasmayin", "onay kodu"]): return "#TR" # Turkish
    if any(w in text_lower for w in ["jouw code", "verificatiecode", "niet delen"]): return "#NL" # Dutch
    if any(w in text_lower for w in ["din kod", "verifieringskod", "dela inte"]): return "#SV" # Swedish
    if any(w in text_lower for w in ["bekraeftelseskode", "del ikke"]): return "#DA" # Danish
    if any(w in text_lower for w in ["bekreftelseskode", "ikke del"]): return "#NO" # Norwegian
    if any(w in text_lower for w in ["vahvistuskoodi", "ala jaa"]): return "#FI" # Finnish
    if any(w in text_lower for w in ["vas kod", "overovaci kod", "nesdilejte"]): return "#CS" # Czech
    if any(w in text_lower for w in ["overovaci kod", "nezdielajte"]): return "#SK" # Slovak
    if any(w in text_lower for w in ["ellenorzo kod", "the oszd meg"]): return "#HU" # Hungarian
    if any(w in text_lower for w in ["codul tau", "codul give verificare", "nu partaja"]): return "#RO" # Romanian
    if any(w in text_lower for w in ["kontrolni kod", "kod za potvrdu", "the delite"]): return "#HR" # Croatian/Serbian
    if any(w in text_lower for w in ["kod za potvurzhdenie", "the spodelyajte"]): return "#BG" # Bulgarian
    if any(w in text_lower for w in ["vash kod", "kod pidtverdzhenia"]): return "#UK" # Ukrainian
    
    # African
    if any(w in text_lower for w in ["msimbo wako", "usishiriki"]): return "#SW" # Swahili
    if any(w in text_lower for w in ["verifikasiekode", "moenie deel nie"]): return "#AF" # Afrikaans
    
    # 3. Default if none of the above matches
    return "#EN"

def parse_chat_id(text):
    text = text.strip()
    if text.startswith("-100") or (text.startswith("-") and text[1:].isdigit()):
        return text
    if "t.me/" in text:
        parts = [p for p in text.split("/") if p]
        username = parts[-1] if parts else ""
        if username and not username.startswith("+"): return "@" + username if not username.startswith("@") else username
    if text.startswith("@"):
        return text
    return "@" + text

def is_admin(user_id):
    return user_id in bot_settings["admins"] or user_id == OWNER_ID

def _get_fj_chat_id(entry):
    if isinstance(entry, dict):
        return entry.get("chat_id", "")
    return entry

def _get_fj_info(entry):
    if isinstance(entry, dict):
        return entry
    return {"chat_id": entry, "type": "channel", "title": str(entry), "invite_link": "", "is_private": False}

def auto_detect_chat(chat_id_raw):
    res = api_call("getChat", {"chat_id": chat_id_raw})
    if not res.get("ok"):
        return None
    chat = res["result"]
    chat_type = chat.get("type", "")
    title = chat.get("title", str(chat_id_raw))
    username = chat.get("username", "")
    is_private = not bool(username)
    if chat_type in ["supergroup", "group"]:
        detected_type = "group"
    else:
        detected_type = "channel"
    invite_link = ""
    if is_private:
        link_res = api_call("exportChatInviteLink", {"chat_id": chat_id_raw})
        if link_res.get("ok"):
            invite_link = link_res["result"]
    else:
        invite_link = f"https://t.me/{username}"
    return {
        "chat_id": str(chat.get("id", chat_id_raw)),
        "type": detected_type,
        "title": title,
        "invite_link": invite_link,
        "is_private": is_private
    }

def check_force_join(user_id):
    if not bot_settings["fj_on"] or not bot_settings["fj_channels"]: return True
    if is_admin(user_id): return True
    for entry in bot_settings["fj_channels"]:
        ch = _get_fj_chat_id(entry)
        res = api_call("getChatMember", {"chat_id": ch, "user_id": user_id})
        if res.get("ok") and res.get("result", {}).get("status", "left") not in ["left", "kicked"]: continue
        else: return False
    return True

def send_force_join_msg(chat_id):
    _reset_btn_counter()
    kb = []
    for entry in bot_settings["fj_channels"]:
        info = _get_fj_info(entry)
        ch_type = info.get("type", "channel")
        title = info.get("title", "")
        invite_link = info.get("invite_link", "")
        ch_id = info.get("chat_id", "")
        if invite_link:
            url = invite_link
        elif str(ch_id).startswith("@"):
            url = f"https://t.me/{ch_id.replace('@', '')}"
        else:
            url = f"https://t.me/{ch_id}"
        type_label = "Channel" if ch_type == "channel" else "Group"
        btn_text = f"Join {type_label}: {title}" if title else f"Join {type_label}"
        kb.append([{"text": btn_text, "icon_custom_emoji_id": "5789428375261023681", "url": url, "style": _rs()}])
    kb.append([{"text": "Check Joined", "icon_custom_emoji_id": "5352694861990501856", "callback_data": "check_fj", "style": _rs()}])
    send_message(chat_id, render_body_text(f"{PEM['warn']} <b>Please join our channels/groups to use the bot!</b>"), reply_markup={"inline_keyboard": kb})

def is_user_banned(user_id):
    if is_admin(user_id): return False
    with _banned_cache_lock:
        cached = user_banned_cache.get(user_id)
    if cached and time.time() - cached['time'] < 60:
        return cached['banned']
    local_u = _get_local_user(user_id)
    banned = local_u.get("banned", False)
    with _banned_cache_lock:
        # FIX: Evict 500 oldest entries instead of clearing all — thread-safe & preserves hot entries
        if len(user_banned_cache) > 2000:
            oldest = sorted(user_banned_cache, key=lambda k: user_banned_cache[k]['time'])[:500]
            for k in oldest:
                user_banned_cache.pop(k, None)
        user_banned_cache[user_id] = {'banned': banned, 'time': time.time()}
    return banned

# ==========================================
# Captcha Auto Login & Parsing Core
# ==========================================
def extract_otp_code(text):
    # NOTE: 'nn' → '\n' replacement is intentionally NOT done here.
    # Callers (parse_panel_response) already handle it in context.
    # Doing it here would corrupt words like "running", "connection", "announcement".
    clean_text = re.sub(r'[\u200B-\u200D\uFEFF]', '', str(text))

    # 1. Multi-part OTPs (e.g. 123-456 or 809-761 or 12-34-56)
    multi_part = re.search(r'(\d{3}[-\s]+\d{3})|(\d{2}[-\s]+\d{2}[-\s]+\d{2})', clean_text)
    if multi_part:
        return multi_part.group(0).replace(" ", "")

    # 2. Keyword-based extraction
    otp_keywords = ['code', 'is', 'otp', 'pin', 'verification', 'auth', 'ramz', 'your code']
    keywords_pattern = '|'.join(otp_keywords)
    keyword_match = re.search(rf'(?:{keywords_pattern})\s*(?:is|:|-|=)?\s*([a-z0-9]{{4,10}})', clean_text, re.I)
    if keyword_match and keyword_match.group(1).isdigit():
        return keyword_match.group(1)

    keyword_match_rev = re.search(rf'([a-z0-9]{{4,10}})\s*(?:is your|is the|code)', clean_text, re.I)
    if keyword_match_rev and keyword_match_rev.group(1).isdigit():
        return keyword_match_rev.group(1)

    # 3. Google OTP
    g_match = re.search(r'G-(\d{6})', clean_text, re.IGNORECASE)
    if g_match: return g_match.group(1)

    # 4. Digit sequences fallback — prefer 6-digit (most common OTP length)
    # Filter out year-like 4-digit numbers (1990-2099) to avoid false positives
    digit_matches = re.findall(r'(?<!\d)\d{4,8}(?!\d)', clean_text)
    if digit_matches:
        six_digit = [d for d in digit_matches if len(d) == 6]
        if six_digit:
            return six_digit[0]
        non_year = [d for d in digit_matches if not (len(d) == 4 and 1990 <= int(d) <= 2099)]
        return non_year[0] if non_year else digit_matches[0]

    return None


# ==========================================
# 📡 CR API SUPPORT  (http://<host>/crapi/<user>/viewstats)
#    Response format:
#    {"status":"success","total":25,
#     "data":[{"dt":"2025-03-16 21:38:27","num":"84966570308","cli":"msverify",
#              "message":"Use verification code 705516 ...","payout":"0.01"}]}
#    Error format: {"status":"error","msg":"Not Authorized"}
# ==========================================

def is_cr_api_url(url):
    u = str(url or "").lower()
    return "/crapi/" in u or "viewstats" in u

def cr_api_error(response_text):
    """if If the CR API returned an error, return its message; otherwise return ''.."""
    try:
        data = json.loads(response_text)
    except Exception:
        return ""
    if isinstance(data, dict) and str(data.get("status", "")).lower() == "error":
        return str(data.get("msg") or data.get("message") or "Unknown error")
    return ""

def parse_cr_array_response(rows):
    """CR API of ARRAY format (such as tempnumbers.net/agent):
       [["Bybit","263782047056","Your verification code is 892178 ...","2026-08-16 03:31:23"], ...]
       Each row: [cli, number, message, datetime] — order may be slightly different too
       itself identify leta is."""
    results = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 2:
            continue
        num, msg_text, dt_val, cli = "", "", "", ""
        for cell in row:
            if isinstance(cell, (dict, list)) or cell is None:
                continue
            v = str(cell).strip()
            if not v:
                continue
            # datetime column
            if not dt_val and re.match(r'^\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}', v):
                dt_val = v
                continue
            digits = re.sub(r'\D', '', v)
            # number column: only digits, 5-18 length
            if not num and digits == re.sub(r'[\s+\-()]', '', v) and 5 <= len(digits) <= 18:
                num = digits
                continue
            # longest text = message, chhota alpha text = cli (SenderID)
            if len(v) > 25:
                if len(v) > len(msg_text):
                    msg_text = v
            elif not cli and re.search(r'[A-Za-z]', v):
                cli = v
        if not num or not msg_text:
            continue
        otp = extract_otp_code(msg_text) or ""
        results.append({
            "number": num,
            "message": msg_text,
            "otp": otp,
            "item_id": f"{dt_val}|{num}|{otp}" if dt_val else "",
            "cli": cli,
            "payout": "",
        })
    return results


def parse_cr_api_response(response_text, p_config=None):
    """CR API's own parser — directly extracts num / message / cli / dt / payout.
       Returns [] if this CR format not is."""
    try:
        data = json.loads(response_text)
    except Exception:
        return []
    # Format B: directly array of arrays  [[cli, num, message, dt], ...]
    if isinstance(data, list):
        return parse_cr_array_response(data)
    if not isinstance(data, dict):
        return []
    if str(data.get("status", "")).lower() == "error":
        return []
    rows = data.get("data")
    if not isinstance(rows, list):
        return []
    # data inside also array-of-arrays may is
    if rows and isinstance(rows[0], list):
        return parse_cr_array_response(rows)

    results = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        lk = {str(k).lower(): v for k, v in row.items()}
        if "num" not in lk and "number" not in lk:
            continue
        raw_num = lk.get("num", lk.get("number", ""))
        clean_num = re.sub(r'\D', '', str(raw_num))
        msg_text = str(lk.get("message", lk.get("msg", "")) or "").strip()
        if not clean_num or not (5 <= len(clean_num) <= 18):
            continue
        if not msg_text:
            continue
        otp = extract_otp_code(msg_text) or ""
        dt_val = str(lk.get("dt", "") or "").strip()
        # item_id = timestamp + number + otp  -> a single second of do SMS also alag rahenge
        # (stale-check only start that datetime parse does is)
        item_id = f"{dt_val}|{clean_num}|{otp}" if dt_val else ""
        results.append({
            "number": clean_num,
            "message": msg_text,
            "otp": otp,
            "item_id": item_id,
            "cli": str(lk.get("cli", "") or "").strip(),
            "payout": str(lk.get("payout", "") or "").strip(),
        })
    return results

def clean_api_token(token):
    """Token from hidden spaces / newlines / zero-width chars removed do."""
    t = str(token or "")
    for ch in ("\u200b", "\u200c", "\u200d", "\ufeff", "\xa0"):
        t = t.replace(ch, "")
    return t.strip().strip('"').strip("'")


def cr_api_post_fetch(p, timeout=12):
    """CR API POST fallback — documentation says GET and POST are both supported.
       Kabhi kabhi token GET query in breaks is (== / + / special chars) and
       If the token breaks in the GET query, the POST request uses the same token.
       Returns raw response text or ''."""
    try:
        url = (p.get("full_api_url") or p.get("api_url") or "").strip()
        if not url:
            return ""
        base = url.split("?")[0]
        token = clean_api_token(p.get("token", ""))
        if not token and "?" in url:
            # if the token is already in the URL, extract it from there
            try:
                q = parse_qs(url.split("?", 1)[1])
                token = clean_api_token((q.get("token") or q.get("key") or [""])[0])
            except Exception:
                token = ""
        if not token:
            return ""
        try:
            rec = int(p.get("records", 0) or 200)
        except (TypeError, ValueError):
            rec = 200
        rec = max(1, min(200, rec))
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                                 '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        res = requests.post(base, data={"token": token, "records": rec},
                            headers=headers, timeout=timeout)
        return res.text or ""
    except Exception as e:
        logger.warning(f"cr_api_post_fetch error: {e}")
        return ""


def cr_api_add_records(url, records=200):
    """CR API URL on records=<n> add (max 200) if already na be."""
    try:
        if not is_cr_api_url(url):
            return url
        if re.search(r'[?&]records=', url):
            return url
        try:
            n = int(records)
        except (TypeError, ValueError):
            n = 200
        n = max(1, min(200, n))
        sep = '&' if '?' in url else '?'
        return f"{url}{sep}records={n}"
    except Exception:
        return url


def parse_panel_response(response_text, p_config=None, max_results=None):
    results = []
    p_type = p_config.get("type", "API Panel") if p_config else "API Panel"
    
    n_col_name = p_config.get("num_col_name", "number").lower() if p_config else "number"
    m_col_name = p_config.get("msg_col_name", "message").lower() if p_config else "message"
    def _safe_col_idx(val, default):
        try:
            return max(0, int(val) - 1)
        except (TypeError, ValueError):
            return default
    n_idx = _safe_col_idx(p_config.get("num_col_idx"), 1) if p_config else 1
    m_idx = _safe_col_idx(p_config.get("msg_col_idx"), 2) if p_config else 2

    if p_type == "Auto Captcha Panel":
        try:
            soup = BeautifulSoup(response_text, 'html.parser')
            tables = soup.find_all('table')
            
            for table in tables:
                rows = table.find_all('tr')
                if not rows: continue
                
                # 🌟 Option 1 + Smart HTML Detection: Find correct position using column name and user-given serial
                final_n_idx, final_m_idx = _find_header_column_indices(rows, n_col_name, m_col_name, n_idx, m_idx)

                for row in rows:
                    cols = row.find_all(['td', 'th'])
                    
                    # Will not take data from header rows (where all th exist)
                    if all(c.name == 'th' for c in cols): continue
                    
                    if len(cols) > max(final_n_idx, final_m_idx):
                        # Extract text from HTML table
                        num_text = cols[final_n_idx].get_text(separator=" ", strip=True)
                        msg_text = cols[final_m_idx].get_text(separator=" ", strip=True)
                        
                        clean_num = re.sub(r'\D', '', num_text)
                        
                        # Ensure number is actually 5-18 digits (to avoid random text)
                        if clean_num and 5 <= len(clean_num) <= 18:
                            otp = extract_otp_code(msg_text)
                            if otp and len(msg_text) > 4:
                                results.append({"number": clean_num, "message": msg_text, "otp": otp, "item_id": ""})
        except Exception as e:
            logger.warning(f"parse_panel HTML table error: {e}")
    else:
        # 📡 CR API format (status/data/num/message) — check this first
        cr_rows = parse_cr_api_response(response_text, p_config)
        if cr_rows:
            return cr_rows[:max_results] if max_results else cr_rows

        try:
            data = json.loads(response_text)
            temp_results = []
            
            def process_item(item):
                pot_nums_list = []
                pot_msg = None
                explicit_otp = ""
                item_id = ""   # FIX: list items for also define do (NameError prevent)
                values = []
                
                if isinstance(item, dict):
                    # 1. First try searching by known JSON Key (e.g.: num, phone, sms)
                    lower_keys = {str(k).lower(): v for k, v in item.items()}
                    for k in ["number", "num", "phone", "msisdn", "sender"]:
                        if k in lower_keys:
                            clean_val = re.sub(r'\D', '', str(lower_keys[k]))
                            if 5 <= len(clean_val) <= 18:
                                if clean_val not in pot_nums_list: pot_nums_list.append(clean_val)
                    for k in ["message", "msg", "sms", "content", "text", "message_text", "sms_text", "full_message"]:
                        if k in lower_keys:
                            val = str(lower_keys[k])
                            if len(val) > 4:
                                pot_msg = val
                                break
                    # Panels that mask the code inside the message and provide it in a separate field
                    for k in ["otp_code", "otp", "code", "pin"]:
                        if k in lower_keys and str(lower_keys[k] or "").strip().isdigit():
                            explicit_otp = str(lower_keys[k]).strip()
                            break
                    # Extract panel's own message/record ID for reliable deduplication
                    item_id = ""
                    for k in ["id", "sms_id", "msg_id", "message_id", "record_id", "row_id", "cdr_id"]:
                        if k in lower_keys and lower_keys[k] is not None:
                            item_id = str(lower_keys[k]).strip()
                            break
                    values = list(item.values())
                elif isinstance(item, list):
                    # PRIMARY: Configured column indices from directly extract do
                    # n_idx / m_idx above define became are (panel config from or default 1/2)
                    if len(item) > max(n_idx, m_idx):
                        raw_n = item[n_idx]
                        raw_m = item[m_idx]
                        cn = re.sub(r'\D', '', str(raw_n))
                        if 5 <= len(cn) <= 18:
                            pot_nums_list.append(cn)
                        m_clean = re.sub(r'(?<!\n)nn(?!\n)', '\n', str(raw_m))
                        if len(m_clean) > 2:
                            pot_msg = m_clean
                        # Timestamp column from item_id extract do (deduplication for)
                        for col in item:
                            col_str = str(col).strip()
                            if re.match(r'^\d{4}[-/]\d{2}[-/]\d{2}(\s+\d{2}:\d{2}(:\d{2})?)?$', col_str):
                                item_id = col_str
                                break
                    values = item  # Blind scan also will work fallback for

                # 2. Blind Scan (fallback / extra columns for)
                for v in values:
                    if isinstance(v, (dict, list)) or v is None: continue
                    v_str = str(v).strip()
                    
                    # Number Detection: 7 to 18 digits
                    clean_v = re.sub(r'\D', '', v_str)
                    if 7 <= len(clean_v) <= 18 and not re.search(r'[a-zA-Z]', v_str):
                        # Logic to skip Date/Time/IP
                        # FIX: separator that date (2026-06-26) + separator-less date (20260626) + YYYYMMDD format both skip
                        is_date = (re.search(r'\d{4}[-/]\d{2}[-/]\d{2}', v_str) or
                                   re.search(r'\d{2}:\d{2}:\d{2}', v_str) or
                                   re.match(r'^\d{8}$', clean_v) or  # pure 8-digit = likely date YYYYMMDD
                                   "." in v_str)
                        # FIX: timestamp like "2026-06-26 06:02:46" — skip combined datetime with a space
                        if not is_date and not re.search(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}', v_str):
                            if clean_v not in pot_nums_list:
                                pot_nums_list.append(clean_v)
                    
                    # Message Detection: more than 4 characters and not just numbers
                    if len(v_str) > 4 and not v_str.isdigit():
                        # FIX: datetime strings (e.g. "2026-06-26 11:36:01") to message mat samjho
                        _is_datetime_str = bool(
                            re.match(r'^\d{4}[-/]\d{2}[-/]\d{2}(\s+\d{2}:\d{2}(:\d{2})?)?$', v_str) or
                            re.match(r'^\d{2}:\d{2}:\d{2}$', v_str)
                        )
                        if _is_datetime_str:
                            # Timestamp to item_id for use do (deduplication for)
                            if not item_id:
                                item_id = v_str
                            continue
                        # FIX: 'nn' literal to real newlines in convert do (some panels nn bhejte are \n of place)
                        v_str_clean = re.sub(r'(?<!\n)nn(?!\n)', '\n', v_str)
                        # FIX: before OTP-those messages prefer do, lekin if pot_msg currently None is
                        # and any also non-date string received be, use it (strict OTP check remove)
                        has_otp = bool(extract_otp_code(v_str_clean))
                        if has_otp:
                            if pot_msg is None or len(v_str_clean) > len(pot_msg):
                                pot_msg = v_str_clean
                        elif pot_msg is None and len(v_str_clean) > 10:
                            # Fallback: OTP not received, but long string — maybe it's a message
                            pot_msg = v_str_clean
                                
                # 🌟 3. Multiple Numbers Logic (User Priority > Longest Number > First Number)
                pot_num = None
                if pot_nums_list:
                    matched_user_num = None
                    for n in pot_nums_list:
                        # Check if this number exists in user assigned number list
                        if n in nexa_assigned_numbers or any(n in str(key) for key in nexa_assigned_numbers.keys()):
                            matched_user_num = n
                            break
                    
                    if matched_user_num:
                        pot_num = matched_user_num
                    else:
                        # FIX: Instead of taking the second number blindly — take the longest number (real phone numbers tend to be longer)
                        # and 8-digit pure numbers (YYYYMMDD dates) reject
                        valid_nums = [n for n in pot_nums_list if not (len(n) == 8 and re.match(r'^\d{8}$', n))]
                        if valid_nums:
                            pot_num = max(valid_nums, key=len)  # longest = most likely phone number
                        elif pot_nums_list:
                            pot_num = pot_nums_list[0]
                            
                if pot_num and (pot_msg or explicit_otp):
                    otp = explicit_otp if explicit_otp else extract_otp_code(pot_msg)
                    if otp:
                        temp_results.append({"number": pot_num, "message": pot_msg or "", "otp": otp, "item_id": item_id})
                        
            def traverse_json(node, depth=0):
                # Guard against deeply nested or circular-like JSON (max 10 levels)
                if depth > 10:
                    return
                # max_results early-exit: test connection for only N records needed
                if max_results and len(temp_results) >= max_results:
                    return
                if isinstance(node, list):
                    if len(node) > 0 and not isinstance(node[0], (dict, list)):
                        # It's a flat list representing one record
                        process_item(node)
                    else:
                        for child in node:
                            if max_results and len(temp_results) >= max_results:
                                break
                            if isinstance(child, (dict, list)):
                                traverse_json(child, depth + 1)
                elif isinstance(node, dict):
                    prev_len = len(temp_results)
                    process_item(node)
                    # BUG FIX: if is dict the itself one valid record produce did,
                    # then nested values to alag records samajh of process MAT do.
                    # Those are sub-fields, not independent records — this makes them "all over the place"
                    # those wrong records mix be disabled will be.
                    if len(temp_results) == prev_len:
                        # Dict did not provide any record → records may be in nested values
                        for val in node.values():
                            if max_results and len(temp_results) >= max_results:
                                break
                            if isinstance(val, (dict, list)):
                                traverse_json(val, depth + 1)

            traverse_json(data)
            
            # Remove duplicates — also include item_id so that same num+otp are distinguished
            # alag timestamps (alag requests) those records merge na be jaayein
            seen = set()
            for r in temp_results:
                uid = f"{r['number']}_{r['otp']}_{r.get('item_id', '')}"
                if uid not in seen:
                    seen.add(uid)
                    results.append(r)
        except Exception as e:
            logger.warning(f"parse_panel_response error: {e}")
        
    return results

# 🌟 SPA / JSON-API Login Fallback 🌟
# some panels (such as Teleroutex) like old PHP panels server-rendered HTML
# login form not sent — their login page is a React/Vue SPA that the browser
# in JavaScript from render is. Raw HTML in any <form> tag hi not gets,
# therefore old form-scraping logic always "No login form found" give do fail
# becomes tha, chahe username/password exactly correct be.
#
# This fallback is for those panels: when no form is found, it directly sends their JSON
# login API (that panel of frontend background in use does is) on POST
# bhejta is and mile became JWT/token to session of Authorization header in
# set gives is so that after of requests also authenticated rahen.
def _attempt_spa_json_login(login_url, initial_res, username, password, session, idx):
    """Returns (True, None) on success, (False, reason) on failure."""
    parsed = urlparse(login_url)
    same_origin = f"{parsed.scheme}://{parsed.netloc}"

    # 1. API base candidates. Kai panels your real backend one alag subdomain
    #    (for example server.example.com) are hosted on — this hints in the CSP header
    #    the 'connect-src' directive is read. Fallback: same origin.
    api_bases = []
    csp = initial_res.headers.get("Content-Security-Policy", "") or initial_res.headers.get("content-security-policy", "")
    if csp:
        m = re.search(r"connect-src([^;]+)", csp, re.I)
        if m:
            for tok in m.group(1).split():
                if tok.startswith("http"):
                    api_bases.append(tok.strip().rstrip("/"))
    if same_origin not in api_bases:
        api_bases.append(same_origin)

    login_paths = ["/api/user/login", "/api/auth/login", "/user/login", "/auth/login", "/api/login", "/login"]
    # 'identifier' before try do (Teleroutex such as panels ise username/email
    # for both use do are), fir common variants.
    payload_variants = [
        {"identifier": username, "password": password},
        {"username": username, "password": password},
        {"email": username, "password": password},
    ]

    last_reason = "No login form found"
    for base in api_bases:
        for path in login_paths:
            url = base.rstrip("/") + path
            for payload in payload_variants:
                try:
                    res = session.post(url, json=payload, timeout=12)
                except Exception:
                    continue
                if res.status_code not in (200, 201):
                    continue
                try:
                    body = res.json()
                except Exception:
                    continue

                # Token to some common jagahon on dhoondo:
                # {data:{doc:{token}}}, {data:{token}}, {token}, {doc:{token}}
                token = None
                for path_getter in (
                    lambda b: b.get("data", {}).get("doc", {}).get("token"),
                    lambda b: b.get("data", {}).get("token"),
                    lambda b: b.get("doc", {}).get("token"),
                    lambda b: b.get("token"),
                ):
                    try:
                        token = path_getter(body)
                    except Exception:
                        token = None
                    if token:
                        break

                success_flag = body.get("success") is True or str(body.get("status", "")).lower() == "success"
                if token or success_flag:
                    if token:
                        session.headers.update({"Authorization": f"Bearer {token}"})
                    panel_sessions[idx] = session
                    return True, {"token": token, "api_base": base}

                # incorrect credentials or capture the reason when a validation error occurs
                msg = body.get("data", {}).get("message") if isinstance(body.get("data"), dict) else body.get("message")
                if msg:
                    last_reason = str(msg)[:60]

    return False, last_reason


def _extract_base_url(login_url):
    """Extract base URL from Login URL — remove /login /signin /auth etc.
    e.g. http://panel.com/ints/login → http://panel.com/ints"""
    base = login_url
    for seg in ['/login', '/signin', '/auth', '/sign-in', '/log-in']:
        if seg in base.lower():
            base = base[:base.lower().index(seg)]
            break
    return base.rstrip('/')


# 🌟 Advanced Automated Background Captcha Solver 🌟
def attempt_auto_login(p, idx):
    login_url = p.get("login_url", "").strip()
    if not login_url.startswith("http"):
        login_url = "http://" + login_url
        
    # Only append /login if URL doesn't already contain a login-related path
    login_keywords = ['/login', '/signin', '/auth', '/sign-in', '/log-in', '.php', '.asp', '.html', '.htm', '.jsp']
    url_lower = login_url.lower()
    has_login_path = any(kw in url_lower for kw in login_keywords)
    if not has_login_path:
        login_url = f"{login_url.rstrip('/')}/login"
        
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(max_retries=2)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    })
    
    try:
        res = session.get(login_url, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        all_text = res.text
        
        # 1. SOLVE CAPTCHA (Exact bot 3.py logic)
        captcha_match = re.search(r'(\d+\s*[\+\-\*]\s*\d+)\s*[=\?:]', all_text)
        if not captcha_match:
            captcha_match = re.search(r'what is\s*(\d+\s*[\+\-\*]\s*\d+)', all_text, re.I)
        if not captcha_match:
            elements = soup.find_all(["label", "div", "span", "p", "strong"])
            for el in elements:
                txt = el.get_text(separator=" ", strip=True)
                if any(op in txt for op in ["+", "-", "*"]):
                    m = re.search(r'(\d+\s*[\+\-\*]\s*\d+)', txt)
                    if m:
                        captcha_match = m
                        break
                        
        captcha_found = captcha_match is not None
        captcha_text = captcha_match.group(1) if captcha_match else ""
        answer = ""
        if captcha_found:
            m2 = re.search(r'(\d+)\s*([\+\-\*])\s*(\d+)', captcha_text)
            if m2:
                a, op, b = int(m2.group(1)), m2.group(2), int(m2.group(3))
                if op == '+': answer = str(a + b)
                elif op == '-': answer = str(a - b)
                elif op == '*': answer = str(a * b)
                else: answer = "0"
            else:
                answer = "0"

        # 2. FIND FORM
        form = soup.find("form")
        if not form:
            # Old HTML-form assumption failed — it might be a SPA
            # panel (such as Teleroutex) whose login form is generated by JavaScript
            # render is. Uske JSON login API on try do.
            ok, info = _attempt_spa_json_login(login_url, res, p.get("username", ""), p.get("password", ""), session, idx)
            if ok:
                p["login_status"] = "✅ Active & Fetching"
                p["retry_wait"] = 90
                if isinstance(info, dict):
                    if info.get("token"):
                        p["auth_token"] = info["token"]
                    if info.get("api_base"):
                        p["api_base"] = info["api_base"]
                return True
            reason = info if isinstance(info, str) else "No login form found"
            p["login_status"] = f"❌ Login Failed ({reason[:40]})"
            p["retry_wait"] = 90
            return False
            
        action = form.get("action")
        post_url = urljoin(login_url, action) if action else login_url

        form_data = {}
        for hidden in form.find_all("input", type="hidden"):
            name = hidden.get("name")
            if name: form_data[name] = hidden.get("value") or ""
        
        user_input = form.find("input", {"name": re.compile(r"user|email|id", re.I)}) or \
                     form.find("input", {"type": "text", "placeholder": re.compile(r"user|email", re.I)}) or \
                     form.find("input", {"type": "text"})
                     
        pass_input = form.find("input", {"name": re.compile(r"pass", re.I)}) or \
                     form.find("input", {"type": "password"})
                     
        captcha_input = form.find("input", {"placeholder": re.compile(r"answer|ans|code|verification|value|captcha", re.I)}) or \
                        form.find("input", {"name": re.compile(r"ans|captcha|ver|code", re.I)})
        
        user_field = user_input.get("name") if user_input else "username"
        pass_field = pass_input.get("name") if pass_input else "password"
        captcha_field = captcha_input.get("name") if captcha_input else "answer"

        form_data[user_field] = p.get("username", "")
        form_data[pass_field] = p.get("password", "")
        # Only send captcha answer if captcha was actually detected on the page
        if captcha_found and captcha_field and answer:
            form_data[captcha_field] = answer

        # 3. SUBMIT — Referer header is required for some panels (otherwise you get 403)
        session.headers.update({'Referer': login_url})
        login_req = session.post(post_url, data=form_data, allow_redirects=False, timeout=15)
        
        # 403 = panel failed Referer/auth check — immediately report it
        if login_req.status_code == 403:
            p["login_status"] = "❌ Login Failed (403 Forbidden — check the Panel URL)"
            p["retry_wait"] = 90
            return False

        # 4. VERIFY using redirect Location
        location = login_req.headers.get("Location", "")
        
        # SUCCESS: any also redirect that login page on back not goes
        # (some panels 'agent/' on redirect do are, some 'client/', some 'dashboard/')
        _login_slugs = ['login', 'signin', 'sign-in', 'log-in', 'auth']
        _is_login_redirect = any(slug in location.lower() for slug in _login_slugs)
        if location and not _is_login_redirect:
            # Detect panel section (agent/client) — for auto-constructing the CDR URL
            for _sec in ('agent', 'client'):
                if _sec in location.lower():
                    p["panel_section"] = _sec
                    break
            # Follow redirect to establish session
            dash_url = urljoin(post_url, location)
            session.get(dash_url, timeout=10)
            panel_sessions[idx] = session
            p["login_status"] = "✅ Active & Fetching"
            p["retry_wait"] = 90  # Reset to normal retry
            return True
        
        # If redirected to ./ or login page - check error message
        if location:
            err_url = urljoin(post_url, location)
            err_res = session.get(err_url, allow_redirects=True, timeout=10)
            err_text = err_res.text
        else:
            err_text = login_req.text
        
        err_soup = BeautifulSoup(err_text, 'html.parser')
        error_el = err_soup.find("font") or err_soup.find("div", class_="error") or err_soup.find("span", class_="error")
        error_msg = error_el.get_text(strip=True) if error_el else ""
        
        # Handle specific error types
        if 'session invalid' in error_msg.lower() or 'try after' in error_msg.lower():
            # FIX: "try after X minute" from parse the actual wait time
            wait_seconds = 120  # default fallback
            m_wait = re.search(r'try after\s*(\d+)\s*(minute|min|second|sec)', error_msg, re.I)
            if m_wait:
                n = int(m_wait.group(1))
                unit = m_wait.group(2).lower()
                wait_seconds = n * 60 if 'min' in unit else n
                wait_seconds += 15  # buffer
            p["login_status"] = f"❌ Panel Locked ({error_msg})"
            p["retry_wait"] = wait_seconds
            p["last_login_attempt"] = time.time()  # lockout start time record do
            return False
        elif 'captcha' in error_msg.lower():
            p["login_status"] = f"❌ Captcha Failed (Retrying...)"
            p["retry_wait"] = 90
            return False
        elif 'invalid' in error_msg.lower() or 'password' in error_msg.lower():
            p["login_status"] = f"❌ Wrong Username/Password"
            p["retry_wait"] = 90
            return False
        else:
            # Unknown failure - try alternate verification
            msg_link = p.get("msg_link", "").strip()
            if not msg_link.startswith("http") and msg_link != "":
                msg_link = "http://" + msg_link
            if not msg_link:
                _sec = p.get("panel_section", "client")
                check_url = f"{_extract_base_url(login_url)}/{_sec}/SMSCDRStats"
            else:
                check_url = msg_link
            
            check_res = session.get(check_url, timeout=10)
            if 'login' not in check_res.url.lower().split('/')[-1] and check_res.status_code == 200:
                panel_sessions[idx] = session
                p["login_status"] = "✅ Active & Fetching"
                p["retry_wait"] = 90
                return True
            else:
                reason = error_msg if error_msg else (f"Math: {captcha_text} = {answer}" if captcha_found else "Login page returned")
                p["login_status"] = f"❌ Login Failed ({reason[:40]})"
                p["retry_wait"] = 90
                return False
            
    except Exception as e:
        p["login_status"] = f"❌ Error: {str(e)[:20]}"
        
    return False

def _build_api_urls(p):
    """Build the list of URLs + headers to try for an API Panel from its config.
    Extracted to avoid duplicate code between panel_monitor_thread and test_p_conn_."""
    full_url = p.get("full_api_url", "").strip()
    url = p.get("api_url", "").strip()
    token = clean_api_token(p.get("token", ""))
    # Encode the token that goes into the URL — otherwise characters like '=' '+' '/' will cause issues
    # query todte are and panel 'Not Authorized' give gives is
    q_token = quote(token, safe="")
    token_header = p.get("token_header", "").strip()
    urls_to_try = []
    if full_url:
        urls_to_try.append(full_url)
    elif token_header and token:
        urls_to_try.append(url)
    else:
        if "{token}" in url or "{key}" in url:
            urls_to_try.append(url.replace("{token}", q_token).replace("{key}", q_token))
        elif "token=" in url or "key=" in url:
            urls_to_try.append(url)
        else:
            if token:
                sep = '&' if '?' in url else '?'
                urls_to_try.append(f"{url}{sep}token={q_token}")       # encoded (safest)
                urls_to_try.append(f"{url}{sep}token={token}")         # raw — some panels request it like this
                urls_to_try.append(f"{url}{sep}key={q_token}&start=0")
                urls_to_try.append(f"{url}{sep}key={q_token}")
            urls_to_try.append(url)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    if token_header and token:
        headers[token_header] = token
    # 📡 CR API: add records param (default 200, max 200)
    _rec = p.get("records", 0) or 200
    urls_to_try = [cr_api_add_records(u, _rec) for u in urls_to_try]
    return urls_to_try, headers

def quick_panel_test(p):
    """Check a new API panel by adding it and fetching once.
       Returns (ok, count, error_text, samples)."""
    try:
        urls_to_try, headers = _build_api_urls(p)
        last_raw = ""
        for try_url in urls_to_try:
            if not try_url:
                continue
            try:
                res = tg_session.get(try_url, headers=headers, timeout=12)
                last_raw = res.text or ""
                err = cr_api_error(last_raw)
                if err:
                    # Not Authorized — maybe the token is breaking in the GET query, try POST
                    post_raw = cr_api_post_fetch(p)
                    if post_raw and not cr_api_error(post_raw):
                        rows = parse_panel_response(post_raw, p) or legacy_parse_panel_response(post_raw, p)
                        if rows:
                            p["use_post"] = True
                            return True, len(rows), "", rows[:2]
                    return False, 0, (f"{err}\n\n<i>Token panel the accept not did (GET + POST both try kiye). "
                                      f"Confirm the token with the administrator — make sure there are no spaces and it wasn't copied partially?</i>"), []
                rows = parse_panel_response(last_raw, p)
                if not rows:
                    rows = legacy_parse_panel_response(last_raw, p)
                if rows:
                    return True, len(rows), "", rows[:2]
            except Exception as e:
                last_raw = str(e)
        # 🔁 GET failed — now try POST (docs: both GET and POST supported)
        post_raw = cr_api_post_fetch(p)
        if post_raw:
            post_err = cr_api_error(post_raw)
            if not post_err:
                rows = parse_panel_response(post_raw, p) or legacy_parse_panel_response(post_raw, p)
                if rows:
                    p["use_post"] = True     # forward from POST hi use will be
                    return True, len(rows), "", rows[:2]
            last_raw = post_raw

        if last_raw and last_raw.strip():
            return False, 0, f"Response received lekin any OTP record parse not was.\nRaw: {last_raw[:150]}", []
        return False, 0, "Panel from any response not aya (URL/internet check do).", []
    except Exception as e:
        return False, 0, str(e), []


def _pnl_key(p_type):
    return {"API Panel": "api", "Auto Captcha Panel": "cpt", "Live Socket Panel": "sock"}.get(p_type, "api")

def _pnl_type_from_key(key):
    return {"api": "API Panel", "cpt": "Auto Captcha Panel", "sock": "Live Socket Panel"}.get(key, "API Panel")


# ==========================================
# 🔌 LIVE SOCKET PANEL (WebSocket / Socket.IO) — direct OTP from website
#    Reference: user of standalone websocket script (Telethon + websockets asyncio).
#    Synchronize it here websocket-client + existing threading model in convert
#    It uses the synchronized websocket-client and existing threading model,
#    and OTPs pass through the same _process_panel_otps() pipeline as API/CR panels.
# ==========================================
socket_panel_threads = {}   # idx -> True (thread already running; do not start it again)
socket_panel_locks = threading.Lock()

def _socket_extract_otp(text):
    m = re.search(r"\b\d{3,6}(?:[- ]\d{2,6})?\b", str(text or ""))
    return m.group(0).replace(" ", "").replace("-", "") if m else (extract_otp_code(text) or "")


def _socket_ping_loop(ws, interval_ms, stop_evt):
    """every interval on socket.io ping ('3') bhejta remains is jab until socket khula is."""
    interval = max(5, (interval_ms or 25000) / 1000)
    while not stop_evt.is_set():
        time.sleep(interval)
        if stop_evt.is_set():
            break
        try:
            ws.send("3")
        except Exception:
            break


def quick_socket_test(ws_url, timeout=10):
    """Socket.IO endpoint to one time connect by handshake confirm does is.
       Returns (ok, info_text)."""
    try:
        ws = websocket.create_connection(ws_url, timeout=timeout, sslopt={"cert_reqs": ssl.CERT_NONE})
        try:
            ws.settimeout(timeout)
            first = ws.recv()
            if first and first.startswith("0") and "{" in first:
                return True, "Socket.IO handshake OK — connected."
            if first:
                return True, f"Connected, raw response: {str(first)[:120]}"
            return False, "Empty response from socket."
        finally:
            try:
                ws.close()
            except Exception:
                pass
    except Exception as e:
        return False, str(e)


def _socket_panel_loop(idx):
    """A persistent connect+reconnect loop for a Live Socket Panel — its own dedicated thread."""
    while True:
        try:
            if idx < 0 or idx >= len(bot_settings.get("panels", [])):
                return  # panel was deleted — end the thread
            p = bot_settings["panels"][idx]
            if p.get("type") != "Live Socket Panel":
                return
            if p.get("status") != "ON":
                time.sleep(3)
                continue
            ws_url = p.get("ws_url", "").strip()
            if not ws_url:
                time.sleep(5)
                continue

            ws = websocket.create_connection(ws_url, timeout=15, sslopt={"cert_reqs": ssl.CERT_NONE})
            logger.info(f"🔌 Socket Panel '{p.get('name','?')}' connected.")
            p["login_status"] = "✅ Connected & Listening"
            save_local_db()

            stop_evt = threading.Event()
            ping_thread = None
            ws.settimeout(60)
            joined_ns = False

            try:
                while True:
                    if idx >= len(bot_settings.get("panels", [])) or bot_settings["panels"][idx].get("status") != "ON":
                        break
                    try:
                        message = ws.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    if not message:
                        break

                    if message.startswith("0") and "{" in message:
                        ping_interval = 25000
                        try:
                            data = json.loads(message[1:])
                            ping_interval = data.get("pingInterval", 25000)
                        except Exception:
                            pass
                        ws.send("40/livesms,")
                        stop_evt = threading.Event()
                        ping_thread = threading.Thread(target=_socket_ping_loop, args=(ws, ping_interval, stop_evt), daemon=True)
                        ping_thread.start()
                        continue

                    if message.startswith("40") and not joined_ns:
                        joined_ns = True
                        continue

                    if message.startswith("42/livesms,"):
                        try:
                            json_str = message[message.find("["):]
                            data = json.loads(json_str)
                            if isinstance(data, list) and len(data) > 1 and isinstance(data[1], dict):
                                sms = data[1]
                                number = re.sub(r"\D", "", str(sms.get("recipient", "") or ""))
                                msg_text = str(sms.get("message", "") or "")
                                if number and msg_text:
                                    otp = _socket_extract_otp(msg_text)
                                    item = {
                                        "number": number,
                                        "message": msg_text,
                                        "otp": otp,
                                        "item_id": f"{number}|{otp}|{hashlib.md5(msg_text.encode('utf-8','ignore')).hexdigest()[:10]}",
                                        "cli": str(sms.get("originator", "") or ""),
                                        "payout": "",
                                    }
                                    p["needs_warmup"] = False  # socket = only new pushes, no backlog — no warmup needed
                                    _process_panel_otps(idx, p, [item])
                        except Exception as e:
                            logger.warning(f"Socket Panel parse error: {e}")
            finally:
                stop_evt.set()
                try:
                    ws.close()
                except Exception:
                    pass

        except Exception as e:
            try:
                if 0 <= idx < len(bot_settings.get("panels", [])):
                    bot_settings["panels"][idx]["login_status"] = f"🔄 Reconnecting... ({str(e)[:60]})"
                    save_local_db()
            except Exception:
                pass
            logger.warning(f"Socket Panel {idx} connection error: {e}. Retrying in 5s...")

        time.sleep(5)


def _start_socket_panel_thread(idx):
    """Idempotent — only one thread is started per panel."""
    with socket_panel_locks:
        if socket_panel_threads.get(idx):
            return
        socket_panel_threads[idx] = True
    threading.Thread(target=_socket_panel_loop, args=(idx,), daemon=True).start()


def _find_otp_owners(clean_num):
    """Find all bot users who own this phone number.
    Extracted to avoid duplicate code between panel_monitor_thread and global_sms_listener.
    Returns: list of chat_ids (may be multiple if num_share > 1)."""
    owners = []
    # 1. Active Sessions — fastest, in-memory
    for uid, session_data in list(user_active_sessions.items()):
        for act_num in session_data.get("nums", []):
            act_clean = str(act_num).replace("+", "").replace(" ", "").replace("-", "").strip()
            if act_clean == clean_num or (
                len(act_clean) >= 8 and len(clean_num) >= 8 and
                abs(len(act_clean) - len(clean_num)) <= 3 and
                (act_clean.endswith(clean_num[-8:]) or clean_num.endswith(act_clean[-8:]))
            ):
                owners.append(uid)
                break
    # 2. number_batches used_by — persistent, survives bot restarts
    if not owners:
        for b_id, b_data in number_batches.items():
            for n_obj in b_data.get("numbers", []):
                stored_clean = str(n_obj.get("num", "")).replace("+", "").replace(" ", "").replace("-", "").strip()
                if stored_clean == clean_num or (
                    len(stored_clean) >= 8 and len(clean_num) >= 8 and
                    abs(len(stored_clean) - len(clean_num)) <= 3 and
                    (stored_clean.endswith(clean_num[-8:]) or clean_num.endswith(stored_clean[-8:]))
                ):
                    for used_uid in n_obj.get("used_by", []):
                        if used_uid not in owners:
                            owners.append(used_uid)
                    if owners:
                        break
            if owners:
                break
    # 3. Nexa assigned numbers
    if not owners:
        for nexa_n, n_owner in nexa_assigned_numbers.items():
            clean_nexa = str(nexa_n).replace("+", "").replace(" ", "").replace("-", "").strip()
            if clean_nexa == clean_num or (
                len(clean_nexa) >= 8 and len(clean_num) >= 8 and
                abs(len(clean_nexa) - len(clean_num)) <= 3 and
                (clean_nexa.endswith(clean_num[-8:]) or clean_num.endswith(clean_nexa[-8:]))
            ):
                owners.append(n_owner)
    # 4. VoltX assigned numbers
    if not owners:
        vx_owner = _find_assigned_owner(voltx_assigned_numbers, clean_num)
        if vx_owner:
            owners.append(vx_owner)
    # 5. Stex assigned numbers
    if not owners:
        sx_owner = _find_assigned_owner(stex_assigned_numbers, clean_num)
        if sx_owner:
            owners.append(sx_owner)
    return list(set(owners))

_RATE_LIMIT_PHRASES = [
    "too many times", "too many requests", "rate limit", "try again in",
    "slow down", "429", "access denied", "you've accessed"
]

def _is_rate_limited_response(text):
    """Legacy text-only helper retained for compatibility.

    Do not use this to classify a normal API response: words such as
    ``rate`` may legitimately occur inside a successful JSON payload.
    HTTP status codes should be used by callers instead.
    """
    if not text:
        return False
    lower = text.lower()
    return any(phrase in lower for phrase in _RATE_LIMIT_PHRASES)


def _rate_limit_backoff_seconds(response, default=2, maximum=60):
    """Return a bounded retry delay from a 429 response.

    Prefer the standard Retry-After header, then parse explicit phrases such as
    ``Try again in 1 seconds`` from the response body. If neither is present,
    use a short default delay rather than a fixed 10-second wait.
    """
    retry_after = str(response.headers.get("Retry-After", "")).strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", retry_after):
        return max(1, min(maximum, int(float(retry_after))))

    candidates = [retry_after]
    candidates.append(str(getattr(response, "text", "") or ""))

    patterns = (
        r"(?i)\bretry[-_ ]?after\s*[:=]?\s*(\d+(?:\.\d+)?)",
        r"(?i)\btry\s+again\s+in\s+(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|s)?",
    )
    for source in candidates:
        for pattern in patterns:
            match = re.search(pattern, source)
            if match:
                try:
                    return max(1, min(maximum, int(float(match.group(1)))))
                except (TypeError, ValueError):
                    pass
    return max(1, min(maximum, int(default)))

_owner_alert_last_sent = {}

def _response_has_candidate_records(raw_text, panel=None):
    """Return True only when a response appears to contain actual records.

    A logged-in panel can return a complete page/table with zero SMS rows. That
    is a healthy empty poll and must not be reported as a parser failure.
    """
    text = str(raw_text or "")
    if not text.strip():
        return False
    try:
        body = json.loads(text)
        if isinstance(body, dict):
            for key in ("data", "records", "results", "rows", "messages"):
                value = body.get(key)
                if isinstance(value, list) and value:
                    return True
                if isinstance(value, dict):
                    for subkey in ("docs", "records", "rows", "results", "data"):
                        subvalue = value.get(subkey)
                        if isinstance(subvalue, list) and subvalue:
                            return True
            return False
        return isinstance(body, list) and bool(body)
    except Exception:
        pass
    try:
        soup = BeautifulSoup(text, "html.parser")
        rows = soup.find_all("tr")
        # One header row is normal; two or more rows indicate actual data.
        if len(rows) >= 2:
            return True
        # Common card/list layouts used by panel pages.
        for selector in ("[data-number]", ".sms-row", ".message-row", ".record-row"):
            if soup.select_one(selector):
                return True
    except Exception:
        pass
    return False

def _notify_owner_panel_issue(alert_key, message, cooldown=3600):
    """Owner to panel of specific problem of about once (cooldown inside not again) report.
    Isse silent failures (such as 'panel from data get remaining is lekin OTP parse/deliver not happening')
    after this, the owner will see it immediately; previously it was hidden only in the log file."""
    now = time.time()
    last = _owner_alert_last_sent.get(alert_key, 0)
    if now - last < cooldown:
        return
    _owner_alert_last_sent[alert_key] = now
    try:
        send_message(OWNER_ID, render_body_text(f"⚠️ <b>Panel Alert</b>\n{message}"))
    except Exception as e:
        logger.warning(f"Owner panel-alert send failed: {e}")


def _fetch_api_panel_data(idx, p):
    """Fetch data from one API panel. Returns parsed list or [] on failure."""
    now = time.time()

    # Rate-limit backoff check: if API the recently rate-limit did is then skip do
    rate_limit_until = p.get("rate_limit_until", 0)
    if now < rate_limit_until:
        wait_left = int(rate_limit_until - now)
        logger.info(f"Panel {idx} rate-limited — skipping for {wait_left}s more")
        return []

    # 🔁 If Test Connection set POST mode, then use POST only
    if p.get("use_post"):
        post_raw = cr_api_post_fetch(p, timeout=8)
        if post_raw and not cr_api_error(post_raw):
            rows = parse_panel_response(post_raw, p) or legacy_parse_panel_response(post_raw, p)
            if rows:
                p["_zero_yield_streak"] = 0
                return rows

    urls_to_try, headers = _build_api_urls(p)
    for try_url in urls_to_try:
        try:
            res = tg_session.get(try_url, headers=headers, timeout=8)  # use persistent session

            # Only HTTP 429 is treated as rate limiting. Do not inspect body
            # keywords: successful JSON may contain words such as "rate".
            if res.status_code == 429:
                backoff = _rate_limit_backoff_seconds(res, default=2)
                p["rate_limit_until"] = time.time() + backoff
                logger.warning(f"Panel {idx} rate-limited by API — backing off {backoff}s. Response: {res.text[:120]!r}")
                return []

            _cr_err = cr_api_error(res.text)
            if _cr_err:
                p["login_status"] = f"❌ API Error: {_cr_err}"
                _notify_owner_panel_issue(
                    f"cr_api_err_{idx}_{_cr_err[:20]}",
                    f"<b>{p.get('name', 'API Panel')}</b> of API error give remaining is:\n"
                    f"<code>{html.escape(_cr_err)}</code>\n\n"
                    f"Check the token — until then OTPs will not arrive from this panel.")
                return []

            parsed_data = parse_panel_response(res.text, p)
            if not parsed_data and res.text and res.text.strip():
                # 🔁 Fallback: lenient parser from the old script
                parsed_data = legacy_parse_panel_response(res.text, p)
                if parsed_data:
                    logger.info(f"Panel {idx}: legacy parser the {len(parsed_data)} records extracted")
            if parsed_data:
                full_url = p.get("full_api_url", "")
                token = p.get("token", "").strip()
                url = p.get("api_url", "").strip()
                if not full_url and try_url != url and token and not p.get("token_header", ""):
                    p["api_url"] = try_url.replace(token, "{token}")
                    save_local_db()
                p.pop("rate_limit_until", None)  # Successful fetch — reset the backoff
                p["_zero_yield_streak"] = 0
                return parsed_data
            else:
                # Response received (200 OK, without a rate limit) lekin one also record parse not was.
                # if this repeatedly is happening, then column-mapping / JSON-format mismatch may
                # is — earlier this used to hide only in the log, now will notify the OWNER.
                _has_candidate_records = _response_has_candidate_records(res.text, p)
                if _has_candidate_records:
                    p["_zero_yield_streak"] = p.get("_zero_yield_streak", 0) + 1
                    if p["_zero_yield_streak"] >= 5:
                        _notify_owner_panel_issue(
                            f"api_zero_yield_{idx}",
                            f"<b>{p.get('name', 'API Panel')}</b> still returned a response, but "
                            f"no OTP/number could be parsed after 5+ attempts.\n"
                            f"Check the Number/Message column name or serial — the panel's "
                            f"response format may not match."
                        )
        except Exception as e:
            logger.warning(f"Panel URL probe error: {e}")
            continue
    return []


def _fetch_json_api_panel_data(p, sess):
    """SPA/JSON-API panels (like Teleroutex) data fetch — HTML table
    scrape karne of place directly panel of live JSON API from records lete are."""
    api_base = p.get("api_base", "").rstrip("/")
    if not api_base:
        return [], ""

    # ── SAFETY BLOCK: never use /sample endpoint ───────────────────
    # /sample = public live demo feed (shows everyone's 1.9M+ SMS — this
    # your data not is). only /api/message-data-record use do jisme
    # only logged-in client (JWT token) of your data appears.
    data_path = p.get("api_data_path", "/api/message-data-record")
    if "sample" in data_path.lower():
        data_path = "/api/message-data-record"
    # Ensure path always starts with /
    if not data_path.startswith("/"):
        data_path = "/" + data_path
    # ────────────────────────────────────────────────────────────────────────

    # Panel of configured username (double-check filter for)
    panel_username = p.get("username", "").strip().lower()

    url = f"{api_base}{data_path}?pageSize=50&page=1&sortBy=createdAt_descending"
    res = sess.get(url, timeout=15)
    if res.status_code == 401:
        raise Exception("Session expired")
    try:
        body = res.json()
    except Exception:
        return [], res.text
    docs = (body.get("data") or {}).get("docs", [])
    if not isinstance(docs, list):
        return [], res.text
    results = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue

        # ── FIX 1: Process only records with "Success" cause ───────────
        # Failed/Error records do not contain OTP — skip them
        cause = str(doc.get("cause", "Success")).strip()
        if cause.lower() not in ("success", ""):
            continue
        # ────────────────────────────────────────────────────────────────────

        # ── FIX 2: Double-check — only records for our account ──────────────
        # Server-side JWT filtering on rely do are, lekin if
        # if a record from another client ever appears — block it.
        if panel_username:
            client_info = doc.get("client") or {}
            if isinstance(client_info, dict):
                rec_user = str(client_info.get("username", "")).strip().lower()
                if rec_user and rec_user != panel_username:
                    # This record belongs to another client — skip (live/sample safety)
                    continue
        # ────────────────────────────────────────────────────────────────────

        num_val = doc.get("number", "")
        msg_val = doc.get("message", "")
        clean_num = re.sub(r"\D", "", str(num_val))
        if not (clean_num and 5 <= len(clean_num) <= 18 and not re.match(r"^\d{8}$", clean_num)):
            continue
        msg_clean = re.sub(r"(?<!\n)nn(?!\n)", "\n", str(msg_val))
        otp = extract_otp_code(msg_clean)
        if otp and len(msg_clean) > 4:
            # FIX: createdAt to _id (MongoDB ObjectId hex) from before try do.
            # createdAt is a parseable datetime string — _is_stale_otp uses it
            # correct age check can do. MongoDB _id hex string of timestamp
            # _parse_item_datetime_epoch parse not do can (stale check skip).
            # Dedup for both kaam do are (both unique are), lekin stale
            # detection for createdAt behtar is.
            item_id = str(doc.get("createdAt") or doc.get("_id") or doc.get("id") or "")
            results.append({"number": clean_num, "message": msg_clean, "otp": otp, "item_id": item_id})
    return results, res.text


def _fetch_captcha_panel_data(idx, p):
    """Fetch data from one Auto Captcha panel. Returns list, or None if skip to do be."""
    now = time.time()
    # Captcha panels: 10s minimum between fetches (was 30s — reduced for faster delivery)
    if now - p.get("last_fetch_time", 0) < 10:
        return None

    sess = panel_sessions.get(idx)
    if not sess:
        retry_wait = p.get("retry_wait", 90)
        # FIX: if a buggy error-parse because of retry_wait too many set becomes
        # (such as incorrect "try after X minute" parsing), panel always for atka na remaining.
        # Never wait more than 30 minutes — if it exceeds that, enforce a cap.
        if retry_wait > 1800:
            retry_wait = 1800
            p["retry_wait"] = 1800
        if now - p.get("last_login_attempt", 0) < retry_wait:
            return None
        p["last_login_attempt"] = now
        success = attempt_auto_login(p, idx)
        save_local_db()
        if not success:
            p["last_fetch_time"] = now
            # Login keeps failing — tell the OWNER, otherwise panel silently
            # "OTP not being sent" will appear without any reason of.
            p["_login_fail_streak"] = p.get("_login_fail_streak", 0) + 1
            if p["_login_fail_streak"] >= 3:
                _notify_owner_panel_issue(
                    f"cpt_login_fail_{idx}",
                    f"<b>{p.get('name', 'Auto Captcha Panel')}</b> in repeatedly login fail is happening.\n"
                    f"Status: {p.get('login_status', 'Unknown')}\n"
                    f"Therefore this panel is not sending OTPs to the group — check Username/Password/Login URL."
                )
            return None
        p["_login_fail_streak"] = 0
        sess = panel_sessions.get(idx)

    try:
        if p.get("api_base"):
            parsed_data, res_text = _fetch_json_api_panel_data(p, sess)
        else:
            msg_link = p.get("msg_link", "").strip()
            if not msg_link.startswith("http") and msg_link != "":
                msg_link = "http://" + msg_link
            if not msg_link:
                _lu = p.get("login_url", "").strip()
                if not _lu.startswith("http"):
                    _lu = "http://" + _lu
                _sec = p.get("panel_section", "client")  # agent/client — detected from login redirect
                msg_link = f"{_extract_base_url(_lu)}/{_sec}/SMSCDRStats"
            parsed_data, res_text = fetch_cpt_panel_cdrs(p, sess, msg_link)
            if not parsed_data and res_text and res_text.strip():
                # 🔁 Fallback: old-script style lenient HTML parser
                parsed_data = legacy_parse_panel_response(res_text, p)
                if parsed_data:
                    logger.info(f"Panel {idx}: legacy HTML parser the {len(parsed_data)} rows extracted")
        p["login_status"] = "✅ Active & Fetching"
        p["last_fetch_time"] = time.time()
        if parsed_data:
            p["_zero_yield_streak"] = 0
        elif res_text and res_text.strip() and _response_has_candidate_records(res_text, p):
            # FIX: JSON API panels (such as Teleroutex) for zero-yield streak
            # do not count — an empty response there is NORMAL (no new SMS).
            # Zero-yield warning only HTML table panels for meaningful is
            # (wrong column mapping of sign). JSON API panels in docs==[] be
            # just "no pending OTP right now" — not a configuration error.
            if p.get("api_base"):
                p["_zero_yield_streak"] = 0  # Reset — normal for JSON API panel
            else:
                # HTML table panel: Page found but not a single OTP/number parsed —
                # column-mapping or table-structure mismatch may is.
                p["_zero_yield_streak"] = p.get("_zero_yield_streak", 0) + 1
                if p["_zero_yield_streak"] >= 5:
                    _notify_owner_panel_issue(
                        f"cpt_zero_yield_{idx}",
                        f"<b>{p.get('name', 'Auto Captcha Panel')}</b> of page load is happening lekin "
                        f"any also OTP/number parse not be pa remaining (5+ time).\n"
                        f"Number/Message Column Name or Serial check — from the panel's table format "
                        f"match not do remaining."
                    )
        return parsed_data
    except Exception as e:
        p["login_status"] = "❌ Session Expired (Retrying...)"
        if idx in panel_sessions:
            del panel_sessions[idx]
        p["last_fetch_time"] = time.time()
        save_local_db()
        return None


def _process_panel_otps(idx, p, parsed_data):
    """Panel from received parsed_data process do and OTPs deliver do."""
    panel_needs_warmup = p.get("needs_warmup", True)  # Default True = safe (skip until first successful poll)

    limit = p.get("records", 0)
    if p.get("type") != "Auto Captcha Panel" and limit > 0:
        parsed_data = parsed_data[:limit]

    for item in parsed_data:
        try:
            num = item["number"]
            otp = item["otp"]
            msg_text = item["message"]

            item_id = item.get("item_id", "")
            panel_key = p.get("name", str(idx))
            if item_id:
                # FIX: Check the panel's own timestamp (item_id) — if OTP
                # already 25 ghante from old is, to isse kabhi deliver not
                # do so, even if bot the first time hi seen be (dedup memory
                # is independent — this checks the "real age of the content").
                if _is_stale_otp(item_id):
                    _add_to_processed(f"PANEL_{panel_key}_{item_id}")
                    continue
                # Item ID that panel: every unique record once hi will arrive (25h window)
                unique_id = f"PANEL_{panel_key}_{item_id}"
                dedup_window = 90000  # 25 hours — do not deliver the same record again
            else:
                # Item ID not: only 10 second spam guard.
                # Panel polls every 1-2s — 10s window delivers the same record
                # delivers it once. After 10s same code = new SMS → deliver immediately.
                unique_id = f"{num}_{otp}"
                dedup_window = 10    # 10 second — only to prevent tight-loop spam

            clean_api_num = str(num).replace("+", "").replace(" ", "").replace("-", "").strip()
            owners = _find_otp_owners(clean_api_num)

            # ── WARMUP GATE ─────────────────────────────────────────────────
            # Panel's first successful poll — ALWAYS skip old OTPs.
            # Whether owner or not — no delivery during warmup.
            # Mark-as-processed is NECESSARY — otherwise after warmup the same OTP
            # "new" lagega and again deliver be jaayega.
            warmup_num_otp_key = f"WARMUP_{num}_{otp}"
            if panel_needs_warmup:
                if item_id:
                    # item_id that: normal key 25h window from mark do
                    _add_to_processed(unique_id)
                # ALWAYS also mark WARMUP_{num}_{otp} — whether item_id exists or not.
                # this backup protection is: if item_id parsing inconsistent be
                # (one fetch in received, other in not), then also old OTP block will remain.
                _add_to_processed(warmup_num_otp_key)
                continue  # ALWAYS skip — no owner exception

            # ── DEDUP GATE ──────────────────────────────────────────────────
            # Non-item_id entries: WARMUP_ check (25h) — block old OTP.
            # For item_id entries: WARMUP_ check only when the item_id is empty (inconsistent parsing).
            # If item_id exists (new SMS, different item_id), WARMUP_ will not block —
            # otherwise same number on truly new OTP also 25h for disabled becomes.
            if not item_id and _is_processed(warmup_num_otp_key, window=90000):
                continue
            # For item_id records: 25h window. Non-item_id: 10s window (allow the same code)
            if _is_processed(unique_id, window=dedup_window):
                continue

            # New OTP — MARK first, then deliver (prevent race condition)
            _add_to_processed(unique_id)
            # Non-item_id panels for WARMUP_ key also 25h set.
            # Not for item_id panels — so a new OTP with a different item_id is not blocked.
            if not item_id:
                _add_to_processed(warmup_num_otp_key)

            # ── DELIVERY ────────────────────────────────────────────────────
            char, iso = get_flag_and_code(num)
            # 📡 The `cli` coming from the CR API (SenderID: Google / msverify / WhatsApp) is the most
            # useful service hint — if not detected from the message, this will be used.
            _svc_hint = str(item.get("cli", "") or "").strip() or p.get("name", "Panel")
            app_full_name, prem_app_html = get_service_info_html(_svc_hint, msg_text)
            current_time = time.time()
            display_num = f"+{num}" if not str(num).startswith("+") else str(num)
            lang = detect_language(msg_text)

            _prune_traffic(current_time)
            with _traffic_lock:
                recent_traffic.append({
                    "service": app_full_name, "iso": iso,
                    "flag": char, "number": num, "time": current_time
                })
            save_local_db()

            first_owner = owners[0] if owners else None
            reward = get_number_rate(display_num)

            # GROUP: every new unique OTP should go into a group — FULL number + flag
            group_msg = format_otp_group_message(
                app_full_name, prem_app_html, get_flag_info_html(display_num), display_num, otp, lang
            )

            # FIX: Each group send in its own try-except — if one fails, the others and user delivery should not be blocked
            fw_groups = bot_settings.get("fw_groups", [])
            if not fw_groups:
                # OTP received and parse also happened, but no forwarding group is configured
                # is — this is the most common reason "OTP arrives but does not go into the group".
                _notify_owner_panel_issue(
                    "no_fw_groups",
                    "OTP get remaining is and parse is happening, lekin any <b>OTP Group</b> add not is "
                    "therefore that kahin forward not happening.\n"
                    "Admin Panel → Add the group in OTP Groups."
                )
            for fw in fw_groups:
                try:
                    _reset_btn_counter()
                    kb = build_otp_group_keyboard(otp)
                    res_fw = send_message(fw["chat_id"], group_msg, reply_markup={"inline_keyboard": kb})
                    if not (res_fw and res_fw.get("ok")):
                        logger.warning(f"Panel group send failed ({fw.get('chat_id')}): {res_fw}")
                        _notify_owner_panel_issue(
                            f"fw_send_fail_{fw.get('chat_id')}",
                            f"OTP Group (<code>{fw.get('chat_id')}</code>) in message bhejna fail is happening.\n"
                            f"Reason: {res_fw}\n"
                            f"Group ID correct is and bot us group in admin/member is, verify do."
                        )
                except Exception as e:
                    logger.warning(f"Panel group delivery error ({fw.get('chat_id')}): {e}")

            # BOT USER: if number of owner is to use also deliver do
            # FIX: Each owner in its own try-except — if one fails, other owners should not be blocked
            for owner_id in owners:
                try:
                    inbox_msg = render_body_text(
                        f"╔═══════════════╗\n"
                        f"║ {prem_app_html} {get_flag_info_html(display_num)} {display_num} {lang} ║\n"
                        f"╚═══════════════╝")
                    _reset_btn_counter()
                    reward = float(get_number_rate(display_num) or 0.0)
                    reward_label = f"{reward:g}"
                    inbox_kb = [[{"text": str(otp), "icon_custom_emoji_id": "5352694861990501856",
                                   "copy_text": {"text": str(otp)}, "style": _rs()}]]
                    inbox_kb.append([{"text": f"Added {reward_label} tk",
                                      "icon_custom_emoji_id": "5420396762189831222",
                                      "callback_data": "ignore", "style": "primary"}])
                    if reward > 0:
                        update_balance(owner_id, reward)
                    send_message(owner_id, inbox_msg, reply_markup={"inline_keyboard": inbox_kb})
                    _increment_local_user(owner_id, "total_otps", 1)
                except Exception as e:
                    logger.warning(f"Panel user delivery error ({owner_id}): {e}")

            try:
                with _data_lock:
                    otp_received_numbers.add(clean_api_num)
            except Exception as e:
                logger.warning(f"panel_monitor otp_received error: {e}")

        except Exception as e:
            logger.warning(f"_process_panel_otps item error: {e}")

    if panel_needs_warmup:
        p["needs_warmup"] = False
        save_local_db()
        logger.info(f"Panel warmup done — old OTPs skipped.")


def _eagerly_warmup_panel(idx, p):
    """When a panel turns ON, fetch immediately and mark all existing OTPs.
    This prevents old OTPs from being delivered; another thread also performs warmup.
    If fetching fails, needs_warmup=True remains — the first panel_monitor_thread iteration
    will perform warmup as a fallback."""
    try:
        time.sleep(0.5)  # callback complete hone do
        # Guard: if monitor the is during already warmup complete do gave,
        # so skip eager warmup — avoid double-processing in race condition.
        if not p.get("needs_warmup", True):
            logger.info(f"Eager warmup skipped — monitor already warmed up.")
            return
        if p.get("type") == "Auto Captcha Panel":
            data = _fetch_captcha_panel_data(idx, p)
        elif p.get("api_url") or p.get("full_api_url"):
            data = _fetch_api_panel_data(idx, p)
        else:
            data = None
        if data:
            # _process_panel_otps needs_warmup=True dekh do all mark karega, deliver not karega
            _process_panel_otps(idx, p, data)
            logger.info(f"Eager warmup done for panel: {len(data)} OTPs pre-marked.")
        # no data arrived: leave needs_warmup=True — panel_monitor_thread will handle it
    except Exception as e:
        logger.warning(f"Eager warmup error for panel '{p.get('name')}': {e}")



# ==========================================
# 🛡️ DATA SAFETY — BACKUP / RESTORE / AUTO BACKUP
#    all user data (balance, OTP count, numbers, settings) one zip in.
# ==========================================
BACKUP_DIR = "backups"
AUTO_BACKUP_HOURS = 6          # every 6 hours, send it to the owner to auto backup zip

BACKUP_FILES = [
    DB_FILE,                   # active main DB (settings + ranges + numbers)
    USERS_DB_FILE,             # users_db.json  (balance, OTP count, refer)
    WITHDRAWALS_DB_FILE,       # withdrawals_db.json
    "users_list.json",         # broadcast list
    TFA_DB_FILE,               # 2fa_saved.json
    SEEN_OTPS_FILE,            # seen_otps.json
]
# Older versions used bot_data.json for the same settings/ranges database.
# Restore accepts both names and always writes the content to the active DB_FILE.
BACKUP_ALIASES = {
    DB_FILE: ("bot_data.json", "bot_data.json.bak"),
}

def _flush_all_data_to_disk():
    """Memory of all data before disk on write, then backup take."""
    for fn in (save_local_db, _save_local_users_db, _save_users_list,
               _save_2fa_saved, _save_processed_otps):
        try:
            fn()
        except Exception as e:
            logger.warning(f"backup flush error ({getattr(fn, '__name__', fn)}): {e}")

def create_backup_zip():
    """all data files of zip build (bytes in). Returns (filename, bytes)."""
    _flush_all_data_to_disk()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    buf = io.BytesIO()
    included, total_users = [], 0
    try:
        total_users = len(local_users_db)
    except Exception:
        pass
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for fpath in BACKUP_FILES:
            try:
                candidates = (fpath,) + tuple(BACKUP_ALIASES.get(fpath, ()))
                source_path = next((candidate for candidate in candidates if os.path.exists(candidate)), None)
                if source_path:
                    z.write(source_path, os.path.basename(source_path))
                    included.append(os.path.basename(source_path))
            except Exception as e:
                logger.warning(f"backup add error {fpath}: {e}")
        manifest = {
            "bot": "PAK OTP EARN — Pakistan Edition",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "owner_id": OWNER_ID,
            "files": included,
            "total_users": total_users,
            "total_ranges": len(number_batches),
            "total_numbers": sum(len(b.get("numbers", [])) for b in number_batches.values()),
        }
        z.writestr("backup_info.json", json.dumps(manifest, indent=2))
    buf.seek(0)
    return f"DB_BACKUP_{stamp}.zip", buf.read(), manifest

def _save_backup_copy(fname, data_bytes):
    """Server on also one copy keep (last 10 backups)."""
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        with open(os.path.join(BACKUP_DIR, fname), "wb") as f:
            f.write(data_bytes)
        files = sorted(os.listdir(BACKUP_DIR))
        for old in files[:-10]:
            try:
                os.remove(os.path.join(BACKUP_DIR, old))
            except Exception as e:
                logger.warning(f"old backup delete error: {e}")
    except Exception as e:
        logger.warning(f"backup copy error: {e}")

def send_backup_to(chat_id, note=""):
    """Backup zip build and bhej do."""
    try:
        fname, data_bytes, manifest = create_backup_zip()
        _save_backup_copy(fname, data_bytes)
        caption = (f"🛡️ <b>BACKUP READY</b>\\n"
                   f"👤 Users: <b>{manifest['total_users']}</b>\\n"
                   f"📁 Ranges: <b>{manifest['total_ranges']}</b>\n"
                   f"🔢 Numbers: <b>{manifest['total_numbers']}</b>\n"
                   f"🕓 {manifest['created_at']}")
        if note:
            caption += f"\n{note}"
        send_document(chat_id, fname, data_bytes)
        send_message(chat_id, render_body_text(caption))
        return True
    except Exception as e:
        logger.warning(f"send_backup error: {e}")
        try:
            send_message(chat_id, render_body_text(f"❌ Backup failed: {html.escape(str(e))}"))
        except Exception:
            pass
        return False

def restore_backup_zip(data_bytes):
    """Restore all data from the zip. before safety backup, then validate, then apply.
       Returns (ok, message)."""
    try:
        buf = io.BytesIO(data_bytes)
        with zipfile.ZipFile(buf, "r") as z:
            names = z.namelist()
            valid = {}
            for fpath in BACKUP_FILES:
                base = os.path.basename(fpath)
                candidates = (base,) + tuple(BACKUP_ALIASES.get(fpath, ()))
                source_name = next((candidate for candidate in candidates if candidate in names), None)
                if source_name:
                    raw = z.read(source_name).decode("utf-8", "ignore")
                    if raw.strip():
                        json.loads(raw)          # validate — catch bad JSON early
                    valid[fpath] = raw
            if not valid:
                return False, "Zip in any valid data file not received."

        # Restore from before current data of safety backup
        try:
            sf, sb, _ = create_backup_zip()
            _save_backup_copy("PRE_RESTORE_" + sf, sb)
        except Exception as e:
            logger.warning(f"pre-restore backup error: {e}")

        for fpath, raw in valid.items():
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(raw)

        # Live reload — no restart required. If the uploaded ZIP has no main
        # database, preserve the currently loaded ranges instead of reloading
        # an empty/missing DB and turning the range count into zero.
        try:
            if DB_FILE in valid:
                load_db()
            else:
                logger.warning("Restore ZIP had no main database; live number ranges were preserved.")
            _load_local_users_db()
            sync_users_list()
            _load_2fa_saved()
            _load_processed_otps()
            user_cache.clear()
        except Exception as e:
            logger.warning(f"post-restore reload error: {e}")

        restored_names = ", ".join(os.path.basename(k) for k in valid)
        range_note = "Main database/ranges restored." if DB_FILE in valid else "WARNING: main database missing; ranges were not replaced."
        return True, f"{len(valid)} files restore be gayin: {restored_names}. {range_note}"
    except zipfile.BadZipFile:
        return False, "this valid zip file not is."
    except json.JSONDecodeError as e:
        return False, f"Zip inside kharab JSON is: {e}"
    except Exception as e:
        return False, str(e)

def backup_menu_keyboard():
    _reset_btn_counter()
    return {"inline_keyboard": [
        [{"text": "DOWNLOAD BACKUP", "icon_custom_emoji_id": "5352694861990501856", "callback_data": "bk_download", "style": _rs()}],
        [{"text": "RESTORE BACKUP", "icon_custom_emoji_id": "5451882707599940970", "callback_data": "bk_restore", "style": _rs()}],
        [{"text": f"AUTO BACKUP: {'ON' if bot_settings.get('auto_backup', True) else 'OFF'}",
          "icon_custom_emoji_id": "5190899075968441286", "callback_data": "bk_toggle_auto", "style": _rs()}],
        [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": _rs()}]
    ]}

def auto_backup_thread():
    """every AUTO_BACKUP_HOURS hours, send it to the owner to backup zip bhej do."""
    time.sleep(120)   # wait briefly after startup
    while True:
        try:
            if bot_settings.get("auto_backup", True):
                send_backup_to(OWNER_ID, note="⚙️ <i>Auto backup</i>")
        except Exception as e:
            logger.warning(f"auto_backup_thread error: {e}")
        time.sleep(AUTO_BACKUP_HOURS * 3600)


# ==========================================
# 🔁 LEGACY PANEL CONNECT (old working script method)
#    If the new strict parser fails, this fallback runs.
# ==========================================

def legacy_parse_panel_response(response_text, p_config=None):
    """Old script parser — more lenient:
       • Accepts HTML table rows even without OTP
       • Traverses every node in JSON to find number+message"""
    results = []
    p_type = p_config.get("type", "API Panel") if p_config else "API Panel"
    n_col_name = p_config.get("num_col_name", "number").lower() if p_config else "number"
    m_col_name = p_config.get("msg_col_name", "message").lower() if p_config else "message"
    try:
        n_idx = int(p_config.get("num_col_idx", 1)) - 1 if p_config and p_config.get("num_col_idx") else 1
    except (TypeError, ValueError):
        n_idx = 1
    try:
        m_idx = int(p_config.get("msg_col_idx", 2)) - 1 if p_config and p_config.get("msg_col_idx") else 2
    except (TypeError, ValueError):
        m_idx = 2

    if p_type == "Auto Captcha Panel":
        try:
            soup = BeautifulSoup(response_text, 'html.parser')
            for table in soup.find_all('table'):
                rows = table.find_all('tr')
                if not rows:
                    continue
                final_n_idx, final_m_idx = n_idx, m_idx
                for i, cell in enumerate(rows[0].find_all(['th', 'td'])):
                    c_text = cell.get_text(strip=True).lower()
                    if n_col_name in c_text: final_n_idx = i
                    if m_col_name in c_text: final_m_idx = i
                for row in rows:
                    cols = row.find_all(['td', 'th'])
                    if cols and all(c.name == 'th' for c in cols):
                        continue
                    if len(cols) > max(final_n_idx, final_m_idx):
                        num_text = cols[final_n_idx].get_text(separator=" ", strip=True)
                        msg_text = cols[final_m_idx].get_text(separator=" ", strip=True)
                        clean_num = re.sub(r'\D', '', num_text)
                        if clean_num and 5 <= len(clean_num) <= 18:
                            msg_text = str(msg_text).strip()
                            if msg_text and len(msg_text) > 2:
                                otp = extract_otp_code(msg_text) or ""
                                results.append({"number": clean_num, "message": msg_text,
                                                "otp": otp, "item_id": ""})
        except Exception as e:
            logger.warning(f"legacy_parse HTML error: {e}")
    else:
        cr_rows = parse_cr_api_response(response_text, p_config)
        if cr_rows:
            return cr_rows

        try:
            data = json.loads(response_text)
            temp_results = []

            def process_item(item):
                pot_nums_list = []
                pot_msg = None
                values = []
                if isinstance(item, dict):
                    lower_keys = {str(k).lower(): v for k, v in item.items()}
                    for k in ["number", "num", "phone", "msisdn", "sender"]:
                        if k in lower_keys:
                            clean_val = re.sub(r'\D', '', str(lower_keys[k]))
                            if 5 <= len(clean_val) <= 18 and clean_val not in pot_nums_list:
                                pot_nums_list.append(clean_val)
                    for k in ["message", "msg", "sms", "content", "text"]:
                        if k in lower_keys:
                            val = str(lower_keys[k])
                            if len(val) > 4:
                                pot_msg = val
                                break
                    values = list(item.values())
                elif isinstance(item, list):
                    values = item

                for v in values:
                    if isinstance(v, (dict, list)) or v is None:
                        continue
                    v_str = str(v).strip()
                    clean_v = re.sub(r'\D', '', v_str)
                    if 7 <= len(clean_v) <= 18 and not re.search(r'[a-zA-Z]', v_str):
                        if (not re.search(r'\d{4}[-/]\d{2}[-/]\d{2}', v_str)
                                and not re.search(r'\d{2}:\d{2}:\d{2}', v_str) and "." not in v_str):
                            if clean_v not in pot_nums_list:
                                pot_nums_list.append(clean_v)
                    if len(v_str) > 4 and not v_str.isdigit():
                        if re.search(r'\d{4}[-/]\d{2}[-/]\d{2}', v_str) or re.search(r'^\d{2}:\d{2}(:\d{2})?$', v_str):
                            continue
                        if pot_msg is None or len(v_str) > len(pot_msg):
                            pot_msg = v_str

                pot_num = None
                if pot_nums_list:
                    if len(pot_nums_list) >= 2:
                        pot_num = pot_nums_list[1]
                    else:
                        pot_num = pot_nums_list[0]
                if pot_num and pot_msg:
                    otp = extract_otp_code(pot_msg) or ""
                    temp_results.append({"number": pot_num, "message": pot_msg,
                                         "otp": otp, "item_id": ""})

            def traverse_json(node):
                if isinstance(node, list):
                    if len(node) > 0 and not isinstance(node[0], (dict, list)):
                        process_item(node)
                    for child in node:
                        if isinstance(child, (dict, list)):
                            traverse_json(child)
                elif isinstance(node, dict):
                    process_item(node)
                    for val in node.values():
                        if isinstance(val, (dict, list)):
                            traverse_json(val)

            traverse_json(data)
            seen = set()
            for r in temp_results:
                uid = f"{r['number']}_{hashlib.md5(str(r['message']).encode('utf-8', 'ignore')).hexdigest()[:12]}"
                if uid not in seen:
                    seen.add(uid)
                    results.append(r)
        except Exception as e:
            logger.warning(f"legacy_parse JSON error: {e}")
    return results


def legacy_build_api_urls(p):
    """old script that simple URL builder + browser User-Agent."""
    full_url = p.get("full_api_url", "").strip()
    url = p.get("api_url", "").strip()
    token = clean_api_token(p.get("token", ""))
    urls_to_try = []
    if full_url:
        urls_to_try.append(full_url)
    else:
        if "{token}" in url or "{key}" in url:
            urls_to_try.append(url.replace("{token}", quote(token, safe="")).replace("{key}", quote(token, safe="")))
        elif "token=" in url or "key=" in url:
            urls_to_try.append(url)
        else:
            sep = '&' if '?' in url else '?'
            if token:
                urls_to_try.append(f"{url}{sep}token={token}")
                urls_to_try.append(f"{url}{sep}key={token}&start=0")
                urls_to_try.append(f"{url}{sep}key={token}")
            urls_to_try.append(url)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                             '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    tok_hdr = p.get("token_header", "").strip()
    if tok_hdr and token:
        headers[tok_hdr] = token
    _rec = p.get("records", 0) or 200
    urls_to_try = [cr_api_add_records(u, _rec) for u in urls_to_try]
    return urls_to_try, headers


def legacy_panel_connect(p, idx=None):
    """Old working script connect — plain requests, no cache-busting/rate-limit layer.
       Returns (parsed_list, raw_text)."""
    parsed, raw_text = [], ""
    try:
        if p.get("type") == "Auto Captcha Panel":
            sess = panel_sessions.get(idx) if idx is not None else None
            if not sess and idx is not None:
                if attempt_auto_login(p, idx):
                    sess = panel_sessions.get(idx)
            if not sess:
                return [], ""
            login_url = p.get("login_url", "").strip()
            if login_url and not login_url.startswith("http"):
                login_url = "http://" + login_url
            msg_link = p.get("msg_link", "").strip()
            if msg_link and not msg_link.startswith("http"):
                msg_link = "http://" + msg_link
            check_url = msg_link if msg_link else f"{login_url.split('/login')[0]}/client/SMSCDRStats"
            res = sess.get(check_url, timeout=15, allow_redirects=True)
            raw_text = res.text
            parsed = legacy_parse_panel_response(raw_text, p)
        else:
            urls_to_try, headers = legacy_build_api_urls(p)
            for try_url in urls_to_try:
                if not try_url:
                    continue
                try:
                    res = requests.get(try_url, headers=headers, timeout=10)
                    raw_text = res.text
                    parsed = legacy_parse_panel_response(raw_text, p)
                    if parsed:
                        break
                except Exception as e:
                    logger.warning(f"legacy_panel_connect try failed: {e}")
    except Exception as e:
        logger.warning(f"legacy_panel_connect error: {e}")
    return parsed, raw_text


def panel_monitor_thread():
    """Poll all panels in PARALLEL threads — a slow panel should not block others.
    Delivery delay: ~1-2 seconds (was up to minutes when panels ran sequentially).
    Each on the panelrforms its own warmup (needs_warmup flag) — no global first_run."""
    # Startup on all panels of warmup set.
    # Isse if any panel first time timeout also happens, that also warmup miss not karega.
    for p in bot_settings.get("panels", []):
        p["last_fetch_time"] = 0
        p["needs_warmup"] = True  # first successful poll hone until old OTPs skip

    def _fetch_one(args):
        """Single panel fetch — runs in parallel in ThreadPoolExecutor."""
        idx, p = args
        p_type = p.get("type", "API Panel")
        if p_type == "Auto Captcha Panel":
            data = _fetch_captcha_panel_data(idx, p)
        elif p.get("api_url") or p.get("full_api_url"):
            # Per-panel rate limit: do not poll the same panel again within 5 seconds
            if time.time() - p.get("last_fetch_time", 0) < 5:
                return idx, p, None
            # FIX: set last_fetch_time FIRST — to prevent double-poll race condition
            p["last_fetch_time"] = time.time()
            data = _fetch_api_panel_data(idx, p)
        else:
            return idx, p, None
        return idx, p, data

    with ThreadPoolExecutor(max_workers=30) as executor:
        while True:
            try:
                active = [(idx, p) for idx, p in enumerate(bot_settings.get("panels", []))
                          if p.get("status") == "ON"]

                if active:
                    futures = {executor.submit(_fetch_one, args): args for args in active}
                    for future in list(futures.keys()):
                        try:
                            idx, p, parsed_data = future.result(timeout=8)
                            if parsed_data:
                                _process_panel_otps(idx, p, parsed_data)
                        except Exception as e:
                            logger.warning(f"panel_monitor fetch/process error: {e}")

            except Exception as e:
                logger.warning(f"panel_monitor_thread error: {e}")

            _save_processed_otps()
            # Periodic memory cleanup (every ~5 minutes)
            if not hasattr(_cleanup_stale_sessions, '_last') or time.time() - _cleanup_stale_sessions._last > 300:
                _cleanup_stale_sessions()
                _cleanup_stale_sessions._last = time.time()
            time.sleep(1)  # Check every 1 second (was 5s — 5x faster)

# ==========================================
# User Management
# ==========================================
# 🌟 Local User Cache
user_cache = {}

def get_user(user_id):
    uid = int(user_id) if str(user_id).lstrip("-").isdigit() else user_id
    if uid in user_cache: return user_cache[uid]
    data = _get_local_user(uid)
    # FIX: Evict oldest 200 entries instead of clearing all — preserves recently active users
    if len(user_cache) > 1000:
        for k in list(user_cache.keys())[:200]:
            user_cache.pop(k, None)
    user_cache[uid] = data
    return data

def update_balance(user_id, amount):
    _increment_local_user(user_id, "balance", float(amount))
    # Invalidate user_cache so stale balance is not returned
    user_cache.pop(user_id, None)
    user_cache.pop(str(user_id), None)

# ==========================================
# UI Keyboards & Menu Builders
# ==========================================

# ── give-duplicated helpers ──────────────────────────────────────────────────

def _parse_btn_from_text(text, entities):
    """Parse 'BtnText - https://url' with optional custom_emoji from entities or emoji ID prefix.
    Formats supported:
      Button Text - https://link.com
      6228781436330054904 Button Text - https://link.com   (numeric emoji ID prefix)
      [premium emoji] Button Text - https://link.com       (actual premium emoji in message)
    """
    if "-" not in text:
        return None
    parts = text.split("-", 1)
    btn_text = parts[0].strip()
    btn_url  = parts[1].strip()
    emoji_id = None
    emoji_char = ""

    # 1. Check for numeric emoji ID prefix (e.g. "6228781436330054904 Button Text")
    id_match = re.match(r'^(\d{15,20})\s+(.*)', btn_text)
    if id_match:
        emoji_id = id_match.group(1)
        btn_text = id_match.group(2).strip()
    else:
        # 2. Check for actual premium emoji sent in message entities
        for ent in entities:
            if ent.get("type") == "custom_emoji":
                emoji_id   = ent.get("custom_emoji_id")
                offset     = ent.get("offset", 0)
                length     = ent.get("length", 0)
                b_text     = text.encode('utf-16-take')
                emoji_char = b_text[offset*2:(offset+length)*2].decode('utf-16-take')
                break
        if emoji_char:
            btn_text = btn_text.replace(emoji_char, "").strip()

    btn_data = {"text": btn_text, "url": btn_url, "style": _rs()}
    if emoji_id:
        btn_data["icon_custom_emoji_id"] = emoji_id
    return btn_data


def _build_2fa_code_txt(entry_name, code, remaining_time):
    """Return the formatted 2FA code message text."""
    return (
        f"━━━━━━━━━━━━━━━\n"
        f"<< 🔐 <b>2FA CODE</b> >>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📛 <b>NAME:</b> {entry_name}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🔐 <b>CODE:</b> <code>{code}</code>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🕓 <b>EXPIRES IN:</b> {remaining_time}s\n"
        f"━━━━━━━━━━━━━━━"
    )


def _build_2fa_code_kb(code, secret):
    """Return the inline keyboard for a 2FA code display."""
    _reset_btn_counter()
    return [[{"text": "Click to copy", "icon_custom_emoji_id": "5353022963132174959", "copy_text": {"text": code}, "style": _rs()}],
            [{"text": "Refresh", "icon_custom_emoji_id": "5420155432272438703", "callback_data": f"ref_2fa_{secret}", "style": _rs()},
             {"text": "New Code", "icon_custom_emoji_id": "5352552689983067014", "callback_data": "gen_2fa", "style": _rs()}],
            [{"text": "How to Use", "icon_custom_emoji_id": "6282760761399841824", "callback_data": f"how_2fa_{secret}", "style": _rs()}],
            [{"text": "MY 2FA ADDED", "icon_custom_emoji_id": "5337255927735163754", "callback_data": "my_2fa_list", "style": _rs()}],
            [{"text": "Close", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": _rs()}]]


def _show_2fa_menu(chat_id, msg_id=None):
    """Show (or edit-to-show) the 2FA ONLINE main menu."""
    saved_count = len(user_2fa_saved.get(chat_id, []))
    saved_line  = f"\n📋 <b>Saved 2FA:</b> {saved_count} account(s)" if saved_count > 0 else ""
    txt = (
        f"━━━━━━━━━━━━━━━\n"
        f"《 🔐 <b>2FA ONLINE</b> 》\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🔑 Enter your <b>2FA Secret Key</b> to generate an instant code.\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💾 The code will be saved so you can recover it later.{saved_line}\n"
        f"━━━━━━━━━━━━━━━"
    )
    _reset_btn_counter()
    kb = [[{"text": "Generate 2FA Code", "icon_custom_emoji_id": "5353022963132174959", "callback_data": "gen_2fa", "style": _rs()}],
          [{"text": "MY 2FA ADDED", "icon_custom_emoji_id": "5337255927735163754", "callback_data": "my_2fa_list", "style": _rs()}],
          [{"text": "Close", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": _rs()}]]
    if msg_id:
        edit_message(chat_id, msg_id, render_body_text(txt), reply_markup={"inline_keyboard": kb})
    else:
        send_message(chat_id, render_body_text(txt), reply_markup={"inline_keyboard": kb})

def get_cancel_kb():
    _reset_btn_counter()
    return {"inline_keyboard": [[{"text": "Close", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": _rs()}]]}

def main_menu(user_id):
    _reset_btn_counter()
    kb = [
        [
            {"text": "GET NUMBER", "icon_custom_emoji_id": "5337132498965010628", "style": _rs()},
            {"text": "Search Number", "icon_custom_emoji_id": "5463352748751753567", "style": _rs()}
        ],
        [
            {"text": "TRAFFIC", "icon_custom_emoji_id": "5353032893096567467", "style": _rs()},
            {"text": "2FA ONLINE", "icon_custom_emoji_id": "5337255927735163754", "style": _rs()}
        ],
        [
            {"text": "Refer", "icon_custom_emoji_id": "5420396762189831222", "style": _rs()},
            {"text": "WITHDRAWAL", "icon_custom_emoji_id": "5352585194295564660", "style": _rs()}
        ],
        [
            {"text": "SUPPORT", "icon_custom_emoji_id": "5420145051336485498", "style": _rs()}
        ]
    ]
    if is_admin(user_id):
        kb.append([{"text": "Admin Panel", "icon_custom_emoji_id": "5420155432272438703", "style": _rs()}])
    return {"keyboard": kb, "resize_keyboard": True}

def get_admin_text():
    users_count = len(all_known_users) # 🌟 Zero Cost User Count!
    total_files = len(number_batches)
    available_nums = sum(len(b["numbers"]) for b in number_batches.values())

    txt = f"""
{PEM['admin']} <b>ADMIN CONTROL PANEL</b> {PEM['admin']}
━━━━━━━━━━━━━━━━━━

{PEM['graph']} <b>DATABASE OVERVIEW</b>
— — — — — — — — — —
{PEM['user']} Users      » {users_count}
{PEM['file']} Files      » {total_files}
{PEM['num']} Numbers    » {total_uploaded_stats}
{PEM['ok']} Assigned   » {total_assigned_stats}
{PEM['rocket']} Available  » {available_nums}

{PEM['graph']} <b>STOCK LEVEL</b>
— — — — — — — — — —
[██████░░░░░░░░░] {available_nums} free
━━━━━━━━━━━━━━━━━━
{DEV_CREDIT_HTML}
"""
    return render_body_text(txt)

def admin_panel_keyboard():
    _reset_btn_counter()
    return {"inline_keyboard": [
        [{"text": "LEADER BOARD SYSTEM", "icon_custom_emoji_id": "5353032893096567467", "callback_data": "lb_main", "style": _rs()}],
        [{"text": "Upload Number", "icon_custom_emoji_id": "5353001161878182134", "callback_data": "upload_num", "style": _rs()},
         {"text": "Delete files", "icon_custom_emoji_id": "5422557736330106570", "callback_data": "delete_files", "style": _rs()}],
        [{"text": "Broadcast", "icon_custom_emoji_id": "5789428375261023681", "callback_data": "broadcast_msg", "style": _rs()},
         {"text": "System", "icon_custom_emoji_id": "5420155432272438703", "callback_data": "system_settings", "style": _rs()}],
        [{"text": "Used (OTP Received)", "icon_custom_emoji_id": "5352694861990501856", "callback_data": "show_used", "style": _rs()},
         {"text": "Unused (No OTP)", "icon_custom_emoji_id": "5352597830089347330", "callback_data": "show_unused", "style": _rs()}],
        [{"text": "Close", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": _rs()}]
    ]}

def system_settings_keyboard():
    _reset_btn_counter()
    return {"inline_keyboard": [
        # Auto Mode appears only when THIRD_PARTY_PROVIDERS = True
        *([[{"text": "Auto Mode", "icon_custom_emoji_id": "6088898792495520717", "callback_data": "auto_mode", "style": _rs()}]] if THIRD_PARTY_PROVIDERS else []),
        [{"text": "Force Join System", "icon_custom_emoji_id": "5420517437885943844", "callback_data": "manage_fj", "style": _rs()},
         {"text": "Admin Management", "icon_custom_emoji_id": "5420145051336485498", "callback_data": "manage_admins", "style": _rs()}],
        [{"text": "OTP Group", "icon_custom_emoji_id": "5190447043545438788", "callback_data": "manage_otp_groups", "style": _rs()},
         {"text": "User Management", "icon_custom_emoji_id": "5193063022226086560", "callback_data": "user_management", "style": _rs()}],
        [{"text": "Panel MANAGEMENT", "icon_custom_emoji_id": "5336879280578138635", "callback_data": "manage_panels", "style": _rs()},
         {"text": "Subscription", "icon_custom_emoji_id": "5190899075968441286", "callback_data": "dummy_alert", "style": _rs()}],
        [{"text": "BOT CONTROL", "icon_custom_emoji_id": "5193100774988617665", "callback_data": "currently_control", "style": _rs()},
         {"text": "Premium Emoji", "icon_custom_emoji_id": "5352552689983067014", "callback_data": "manage_emojis", "style": _rs()}],
        [{"text": "Menu Design", "icon_custom_emoji_id": "5190751148704833975", "callback_data": "menu_design_list", "style": _rs()},
         {"text": "Test", "icon_custom_emoji_id": "5190781475468915802", "callback_data": "test_message_flow", "style": _rs()}],
        [{"text": "OTP Forward Manager", "icon_custom_emoji_id": "5190447043545438788", "callback_data": "otp_forward_manager", "style": _rs()}],
        [{"text": "BACKUP & RESTORE", "icon_custom_emoji_id": "5451882707599940970", "callback_data": "backup_menu", "style": _rs()}],
        [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "back_to_admin", "style": _rs()}]
    ]}


# ═══════════════════════════════════════════════════════════════════════════════
# ██  SYSTEM EMOJI MANAGER  ─  All Button & Message Emojis  ██
# ═══════════════════════════════════════════════════════════════════════════════

# ── Static registry: every unique (button_text, orig_emoji_id) in the bot ────
_SYS_BTN_EMOJIS = [
    ("Generate 2FA Code",      "5353022963132174959"),
    ("Back",                   "5267490665117275176"),
    ("Add New",                "5352552689983067014"),
    ("Check Joined",           "5352694861990501856"),
    ("New Code",               "5352552689983067014"),
    ("MY 2FA ADDED",           "5337255927735163754"),
    ("Close",                  "5420130255174145507"),
    ("GET NUMBER",             "5337132498965010628"),
    ("Search Number",          "5463352748751753567"),
    ("TRAFFIC",                "5353032893096567467"),
    ("2FA ONLINE",             "5337255927735163754"),
    ("Refer",                  "5420396762189831222"),
    ("WITHDRAWAL",             "5352585194295564660"),
    ("SUPPORT",                "5420145051336485498"),
    ("Admin Panel",            "5420155432272438703"),
    ("LEADER BOARD SYSTEM",    "5353032893096567467"),
    ("Upload Number",          "5353001161878182134"),
    ("Delete files",           "5422557736330106570"),
    ("Broadcast",              "5789428375261023681"),
    ("System",                 "5420155432272438703"),
    ("Used (OTP Received)",    "5352694861990501856"),
    ("Unused (No OTP)",        "5352597830089347330"),
    ("Auto Mode",              "4969841369850840381"),
    ("Force Join System",      "5420517437885943844"),
    ("Admin Management",       "5420145051336485498"),
    ("OTP Group",              "5190447043545438788"),
    ("User Management",        "5193063022226086560"),
    ("Panel MANAGEMENT",       "5336879280578138635"),
    ("Subscription",           "5190899075968441286"),
    ("BOT CONTROL",           "5193100774988617665"),
    ("Premium Emoji",          "5352552689983067014"),
    ("Menu Design",            "5190751148704833975"),
    ("Test",                   "5190781475468915802"),
    ("Manage Balance",         "5190576863226933563"),
    ("Ban/Unban User",         "5334807341109908955"),
    ("User Profile",           "5352861489541714456"),
    ("Edit /start Menu",       "5395444784611480792"),
    ("Edit GET NUMBER",        "5337132498965010628"),
    ("Edit Search Number",     "5463352748751753567"),
    ("Edit Select Country",    "5336972142066047577"),
    ("Edit TRAFFIC",           "5353032893096567467"),
    ("Edit Refer",             "5420396762189831222"),
    ("Edit WITHDRAWAL",        "5352585194295564660"),
    ("Edit SUPPORT",           "5420145051336485498"),
    ("Reset Defaults",         "5192812028632274956"),
    ("Back to Menus",          "5267490665117275176"),
    ("All Uploading System",   "5353001161878182134"),
    ("All Deleting System",    "5422557736330106570"),
    ("All Downloading System", "5257969839313526622"),
    ("Upload Flags (TXT)",     "5353001161878182134"),
    ("Download Flags",         "5257969839313526622"),
    ("Upload Services (TXT)",  "5353001161878182134"),
    ("Download Services",      "5257969839313526622"),
    ("Delete All Flags",       "5422557736330106570"),
    ("Delete All Services",    "5422557736330106570"),
    ("Add Channel / Group",    "5420323438508155202"),
    ("Add Admin",              "5420323438508155202"),
    ("Edit OTP Button Link",   "5420517437885943844"),
    ("Add Forward Group",      "5420323438508155202"),
    ("Nexa Panel Control",      "6282760761399841824"),
    ("VoltX Panel Control",    "6282760761399841824"),
    ("Stex Panel Control",     "6282760761399841824"),
    ("W. METHODS",             "5190899075968441286"),
    ("BACK",                   "5267490665117275176"),
    ("Add Method",             "5420323438508155202"),
    ("Add New Provider",       "5420323438508155202"),
    ("Back to Providers",      "5267490665117275176"),
    ("Refresh",                "5420155432272438703"),
    ("Add Country Code",       "5420323438508155202"),
    ("Try Again",              "5420323438508155202"),
    ("CLOSE",                  "5420130255174145507"),
    ("Contact support",        "5337302974806922068"),
    ("Remove country code",    "6206108815075579644"),
    ("Add country code",       "6206375377925839184"),
    ("Change Number",          "5420155432272438703"),
    ("Number Expired",         "5336997731481193790"),
    ("Download TXT",           "5257969839313526622"),
    ("Top Referrers",          "5420145051336485498"),
    ("Top OTP Receivers",      "5353001161878182134"),
    ("Withdrawal History",     "5348469219761626211"),
    ("Back to Admin",          "5267490665117275176"),
    ("Add New Service",        "5420323438508155202"),
    ("Back to System",         "5267490665117275176"),
    ("Next Page",              "6264699552041801361"),
    # ── Previously missing entries (added after full audit) ──────────────────
    ("OTP Code (copy)",        "5474525960143385880"),   # OTP value copy button
    ("Full Message",           "5303138782004924588"),   # Full message copy button
    ("Test Connection",        "5276032951342088188"),   # Provider test connection
    ("Delete Provider",        "5336944168944047463"),   # Delete panel provider
    ("COOLDOWN",               "5337172996211648018"),   # currently cooldown setting
    ("NUM/SHARE",              "5352862640592949843"),   # currently num/share + range copy
    ("MIN WITHDRAW",           "5352877703043258544"),   # currently min withdraw setting
    ("Explore Range",          "5190645917711114179"),   # Traffic explore service range
    ("Manage Services / COPY LINK / Set Records", "5192739271886282680"),  # Nexa/VoltX/Stex service manage + refer copy link + panel records
    # ── Full keyboard audit — all remaining buttons now covered ───────────────
    ("Add Country",            "5420323438508155202"),   # Nexa/VoltX/Stex add country
    ("Add Inline Button",      "5420323438508155202"),   # Menu design + forward group add button
    ("Add Range",              "5420323438508155202"),   # Nexa/VoltX/Stex add range
    ("APPROVE",                "5352694861990501856"),   # Withdrawal approve button
    ("Cancel",                 "5420130255174145507"),   # Generic cancel button
    ("Click to copy",          "5353022963132174959"),   # 2FA code copy button
    ("COPY LINK",              "5192739271886282680"),   # Refer link copy button
    ("Del",                    "5422557736330106570"),   # 2FA list delete button
    ("Delete Entire Country",  "5422557736330106570"),   # Nexa/VoltX/Stex delete country
    ("Delete Entire Group",    "5422557736330106570"),   # Forward group delete
    ("Delete Service",         "5422557736330106570"),   # Nexa/VoltX/Stex delete service
    ("Edit Body (Text)",       "5395444784611480792"),   # Menu design edit text
    ("Edit Inline Buttons",    "5420155432272438703"),   # Menu design edit buttons
    ("Full API (URL+Token)",   "5420517437885943844"),   # Panel full API url+token set
    ("Group Not Found",        "5420130255174145507"),   # OTP group not found fallback
    ("How to Use",             "6282760761399841824"),   # 2FA how to use guide
    ("Next",                   "6264699552041801361"),   # Pagination next page
    ("Panel Not Found",        "5420130255174145507"),   # Panel not found fallback
    ("REJECT",                 "5420130255174145507"),   # Withdrawal reject button
    ("Replace",                "5395444784611480792"),   # System emoji replace button
    ("Search Country",         "5336972142066047577"),   # Nexa/VoltX/Stex search country
    ("Set API URL",            "5420517437885943844"),   # Panel set API URL
    ("Set Token",              "5353022963132174959"),   # Panel set token
    ("View/Del Keys",          "5422557736330106570"),   # Nexa/VoltX/Stex view/delete keys
    # ── Dynamic toggle buttons (auto_mode + fj_settings) ─────────────────────
    ("Nexa ON",                "6237529876690113625"),   # Auto Mode — Nexa enabled indicator
    ("Nexa OFF",               "6267000941547885720"),   # Auto Mode — Nexa disabled indicator
    ("VoltX ON",               "6237529876690113625"),   # Auto Mode — VoltX enabled indicator
    ("VoltX OFF",              "6267000941547885720"),   # Auto Mode — VoltX disabled indicator
    ("Stex ON",                "6237529876690113625"),   # Auto Mode — Stex enabled indicator
    ("Stex OFF",               "6267000941547885720"),   # Auto Mode — Stex disabled indicator
    ("STATUS: ON",             "5352694861990501856"),   # Force Join — status ON indicator
    ("STATUS: OFF",            "5318840353510408444"),   # Force Join — status OFF indicator
    ("Group: (Forward Group)", "5193063022226086560"),   # OTP Groups — dynamic group entry
    ("Owner: (Admin)",         "5353032893096567467"),   # Admin list — owner row indicator
]

# ── Static registry: PEM dict, GLOBAL_BODY_EMOJIS, and hardcoded tg-emoji ───
# Each entry: (label, orig_emoji_id, char, usage_example)
_SYS_MSG_EMOJIS = [
    # ─── PEM Dict (lines 55-78) ───────────────────────────────────────────────
    ("PEM:ok",      "5352694861990501856", "✅",  'PEM["ok"] — success messages'),
    ("PEM:no",      "6267000941547885720", "❌",  'PEM["no"] — error messages'),
    ("PEM:warn",    "5336944168944047463", "⚠️",  'PEM["warn"] — warning messages'),
    ("PEM:admin",   "5353032893096567467", "📊",  'PEM["admin"] — admin panel header'),
    ("PEM:user",    "5352861489541714456", "👤",  'PEM["user"] — user profile'),
    ("PEM:file",    "5352721946054268944", "📁",  'PEM["file"] — file references'),
    ("PEM:rocket",  "5352597830089347330", "🚀",  'PEM["rocket"] — unused phone numbers'),
    ("PEM:graph",   "5352877703043258544", "📊",  'PEM["graph"] — statistics/graph'),
    ("PEM:money",   "5348469219761626211", "💸",  'PEM["money"] — account balance/money'),
    ("PEM:gift",    "5420396762189831222", "🎁",  'PEM["gift"] — referral rewards'),
    ("PEM:msg",     "5337302974806922068", "💬",  'PEM["msg"] — message/support'),
    ("PEM:gear",    "5420155432272438703", "⚙️",  'PEM["gear"] — system settings header'),
    ("PEM:link",    "5420517437885943844", "🔗",  'PEM["link"] — force-join links'),
    ("PEM:trash",   "5422557736330106570", "🗑",  'PEM["trash"] — delete actions'),
    ("PEM:upload",  "5353001161878182134", "📤",  'PEM["upload"] — upload prompts'),
    ("PEM:world",   "5336972142066047577", "🌐",  'PEM["world"] — country selector'),
    ("PEM:lock",    "5353022963132174959", "🔐",  'PEM["lock"] — two-factor authentication/security'),
    ("PEM:phone",   "4969841369850840381", "📱",  'PEM["phone"] — automatic mode header'),
    ("PEM:num",     "5352862640592949843", "🔢",  'PEM["num"] — search for number prompt'),
    ("PEM:pin",     "5352922460897452503", "📍",  'PEM["pin"] — select service prompt'),
    ("PEM:star",    "5352552689983067014", "✨",  'PEM["star"] — emoji management header'),
    ("PEM:hi",      "5353027129250453493", "👋",  'PEM["hi"] — welcome screen/main menu'),
    # ─── GLOBAL_BODY_EMOJIS (lines 80-139) — automatically replace in message text ────
    ("GBE:✅",       "5352694861990501856", "✅",  'GLOBAL_BODY_EMOJIS — rendered in all message body text'),
    ("GBE:❌",       "5420130255174145507", "❌",  'GLOBAL_BODY_EMOJIS — rendered in all message body text'),
    ("GBE:⚠️",       "5336944168944047463", "⚠️",  'GLOBAL_BODY_EMOJIS — rendered in all message body text'),
    ("GBE:🔥",       "5337267511261960341", "🔥",  'GLOBAL_BODY_EMOJIS — rendered in all message body text'),
    ("GBE:🌟",       "5337102391244263212", "🌟",  'GLOBAL_BODY_EMOJIS — rendered in all message body text'),
    ("GBE:✨",       "5352552689983067014", "✨",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:➖",       "5870818207383686839", "➖",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:➕",       "5420323438508155202", "➕",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:➡️",       "6319061296704656261", "➡️",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🔄",       "6264896248659056036", "🔄",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:⌛",       "4958503072801228000", "⌛",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:⏳",       "6285092198497129798", "⏳",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🕓",       "5336983442125001376", "🕓",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🔴",       "6267237615720731788", "🔴",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:👤",       "5352861489541714456", "👤",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:👥",       "4972130076318500235", "👥",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:👋",       "5353027129250453493", "👋",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:👇",       "5406745015365943482", "👇",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:😒",       "5334763399299506604", "😒",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:😔",       "6120863614149596295", "😔",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🫂",       "5420145051336485498", "🫂",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:1️⃣",       "5877664071720898423", "1️⃣",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:2️⃣",       "5877223446731034464", "2️⃣",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:3️⃣",       "5879546817879740639", "3️⃣",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:4️⃣",       "5879844832775507443", "4️⃣",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:5️⃣",       "5879657954453491518", "5️⃣",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:6️⃣",       "5877556203617259178", "6️⃣",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:7️⃣",       "5879611822209765566", "7️⃣",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:8️⃣",       "5879971663159758717", "8️⃣",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:9️⃣",       "5877752470737784316", "9️⃣",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🔢",       "5352862640592949843", "🔢",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:📊",       "5353032893096567467", "📊",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:📈",       "5352877703043258544", "📈",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:📁",       "5352721946054268944", "📁",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:📂",       "5257969839313526622", "📂",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:📤",       "5353001161878182134", "📤",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:📝",       "5192739271886282680", "📝",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:📅",       "5352585194295564660", "📅",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:📋",       "6267008582294705964", "📋",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:💾",       "5197269100878907942", "💾",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:📛",       "6325731252066325108", "📛",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:💬",       "5337302974806922068", "💬",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🎙",       "5355102594886833928", "🎙",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:📢",       "5789428375261023681", "📢",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:📌",       "5318986077455795572", "📌",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:📍",       "5352922460897452503", "📍",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🔑",       "6282760761399841824", "🔑",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🔐",       "5337255927735163754", "🔐",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🔗",       "5420517437885943844", "🔗",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:⚙️",       "5420155432272438703", "⚙️",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🛡",       "5190447043545438788", "🛡",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🚫",       "5334807341109908955", "🚫",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🌐",       "6266794310671275367", "🌐",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🔒",       "6282846669335702032", "🔒",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:💸",       "5348469219761626211", "💸",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:💰",       "5190576863226933563", "💰",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:💎",       "5352838545826420397", "💎",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:💳",       "5190899075968441286", "💳",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🎁",       "5420396762189831222", "🎁",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🤝",       "5192805934073685937", "🤝",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🚀",       "5352597830089347330", "🚀",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🍏",       "5337132498965010628", "🍏",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🌍",       "5780471598922337683", "🌍",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🗑",       "5422557736330106570", "🗑",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🟢",       "5192812028632274956", "🟢",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:👀",       "5190645917711114179", "👀",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🕹",       "5193100774988617665", "🕹",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🧪",       "5190781475468915802", "🧪",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🎨",       "5190751148704833975", "🎨",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:💡",       "5422439311196834318", "💡",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    ("GBE:🎯",       "5276032951342088188", "🎯",  'GLOBAL_BODY_EMOJIS — rendered in all body text'),
    # ─── Hardcoded Telegram emoji in message strings ────────────────────────────────
    ("HC:start_📊",  "6264778055454036969", "📊",  '/start text — NUMBER BOT header icon'),
    ("HC:start_🚀",  "5258332798409783582", "🚀",  '/start text — Welcome rocket'),
    ("HC:start_✅",  "6071001861341580968", "✅",  '/start text — Choose option below'),
    ("HC:start_💎",  "6073231507713954071", "💎",  '/start text — Premium OTP Service'),
    ("HC:otp_⏳",    "6266992763930158001", "⏳",  'OTP flow — hourglass (polling)'),
    ("HC:otp_⚡",    "6267107057304868214", "⚡",  'OTP flow — bolt (fast)'),
    ("HC:otp_✅",    "6266994443262367483", "✅",  'OTP flow — check (received)'),
    ("HC:otp_▶1",   "6301055479539828724", "▶",   'OTP result — ACCESS GRANTED arrow'),
    ("HC:otp_✔",    "6266781064992134926", "✔",   'OTP result — ACCESS GRANTED tick'),
    ("HC:otp_▶2",   "6264896248659056036", "▶",   'OTP result — separator arrow'),
    ("HC:mask_⭐",   "6228781436330054904", "⭐",  '_MASK_EMOJI — number masking star'),
    ("HC:2fa_👉",    "5416117059207572332", "👉",  '2FA guide — pointing finger'),
    ("HC:am_✅ON",   "6266827283135207188", "✅",  'Auto Mode — ON indicator'),
    ("HC:am_🔴OFF",  "6267237615720731788", "🔴",  'Auto Mode — OFF indicator'),
    ("HC:am_⚡",     "6318566568011764192", "⚡",  'Auto Mode — header bolt icon'),
    ("HC:panel_🔹",  "6282760761399841824", "🔹",  'Panel control — Nexa/VoltX/Stex header'),
]


# ── Helper: build {orig_id: new_id} map — ONLY for msg_N overrides ────────────
def _build_id_override_map(overrides: dict) -> dict:
    """Convert msg_N overrides to {orig_id: new_id} map for message TEXT replacement.
    btn_N entries are intentionally excluded here — buttons are matched by TEXT
    (see _build_btn_text_override_map) so that changing one button's emoji does NOT
    accidentally change other buttons that share the same emoji ID."""
    id_map = {}
    for key, new_id in overrides.items():
        if key.startswith("msg_"):
            try:
                idx = int(key[4:])
                if 0 <= idx < len(_SYS_MSG_EMOJIS):
                    orig_id = _SYS_MSG_EMOJIS[idx][1]
                    id_map[orig_id] = new_id
            except ValueError:
                id_map[key] = new_id
        elif not key.startswith("btn_"):
            # Legacy plain orig_id key — for backward compatibility
            id_map[key] = new_id
    return id_map

# ── Helper: build {btn_text_lower: new_id} map — ONLY for btn_N overrides ─────
def _build_btn_text_override_map(overrides: dict) -> dict:
    """Build a {button_text_lower: new_id} map for button keyboard overrides.
    Matching by button TEXT instead of emoji ID ensures that changing one specific
    button's emoji only affects that button — even when multiple buttons share
    the same original emoji ID."""
    text_map = {}
    for key, new_id in overrides.items():
        if key.startswith("btn_"):
            try:
                idx = int(key[4:])
                if 0 <= idx < len(_SYS_BTN_EMOJIS):
                    btn_text = _SYS_BTN_EMOJIS[idx][0]
                    text_map[btn_text.lower().strip()] = new_id
            except ValueError:
                pass
    return text_map

# ── Helper: build {orig_id: new_id} ID-only fallback — ONLY for btn_N overrides ─
def _build_btn_id_fallback_map(overrides: dict) -> dict:
    """ID-based fallback map for btn_N overrides.

    Some buttons have text that is DYNAMIC at runtime — for example the OTP value,
    'COOLDOWN: 30s', 'Explore WhatsApp Range', 'NUM/SHARE: 5', etc.
    Inka actual button text _SYS_BTN_EMOJIS of registered label from match
    not does, therefore text_map lookup fail becomes is.

    this fallback un buttons for kaam does is:
    — includes only those orig_ids that have in _SYS_BTN_EMOJIS
      exactly ONE entry (unique ID) — this avoids any ambiguity
      and one button of change any and button to affect not does.
    — shared IDs that have multiple entries (e.g. Back, Add New, etc.) are EXCLUDED
      they are excluded because all of their buttons use static text, and
      the text_map has already handled them."""
    id_count = Counter(orig_id for _, orig_id in _SYS_BTN_EMOJIS)
    id_map = {}
    for key, new_id in overrides.items():
        if key.startswith("btn_"):
            try:
                idx = int(key[4:])
                if 0 <= idx < len(_SYS_BTN_EMOJIS):
                    orig_id = _SYS_BTN_EMOJIS[idx][1]
                    # Only unique-ID entries — shared IDs handled by text_map
                    if id_count[orig_id] == 1:
                        id_map[orig_id] = new_id
            except ValueError:
                pass
    return id_map

# ── Keyboard emoji override ──────────────────────────────────────────────────
def _apply_emoji_overrides(reply_markup: dict) -> dict:
    """Replace icon_custom_emoji_id values in ANY keyboard type with admin overrides.
    Handles both InlineKeyboardMarkup ('inline_keyboard') and
    ReplyKeyboardMarkup ('keyboard') so main_menu buttons are also overridden.

    Three-layer lookup — STRICT separation: btn_N overrides ONLY affect buttons,
    msg_N overrides ONLY affect message text (handled in _apply_text_overrides).

    Layer 1 — Text match (btn_N):
        Static-text buttons matched by their exact registered label.
        Changing btn_1 (Back) changes ALL 'Back' buttons but NOTHING else.

    Layer 2 — ID fallback (btn_N, unique-ID only):
        Dynamic-text buttons (OTP code showing actual OTP, 'COOLDOWN: 30s',
        'Explore X Range', etc.) whose runtime text ≠ registered label.
        Only applied when the emoji ID is unique in _SYS_BTN_EMOJIS —
        guarantees one btn_N change never bleeds into another button type.

    Layer 3 — Legacy plain-key (backward compatibility only, no btn_/msg_ prefix):
        Old overrides saved before the btn_N/msg_N system was introduced."""
    overrides = bot_settings.get("sys_emoji_overrides", {})
    if not overrides:
        return reply_markup

    # Layer 1: text-based map  {btn_text_lower: new_id}  — btn_N only
    text_map      = _build_btn_text_override_map(overrides)
    # Layer 2: ID-based fallback {orig_id: new_id} — btn_N, unique IDs only
    id_fallback   = _build_btn_id_fallback_map(overrides)
    # Layer 3: legacy plain-key overrides (neither btn_ nor msg_ prefix)
    id_legacy     = {k: v for k, v in overrides.items()
                     if not k.startswith("btn_") and not k.startswith("msg_")}

    if not text_map and not id_fallback and not id_legacy:
        return reply_markup

    rm = copy.deepcopy(reply_markup)

    def _patch_btn(btn):
        btn_text_lower = btn.get("text", "").lower().strip()
        # Layer 1: static text match — most precise
        if btn_text_lower and btn_text_lower in text_map:
            btn["icon_custom_emoji_id"] = text_map[btn_text_lower]
            return
        eid = btn.get("icon_custom_emoji_id")
        if not eid:
            return
        # Layer 2: ID fallback — dynamic-text buttons with unique orig_id
        if id_fallback and eid in id_fallback:
            btn["icon_custom_emoji_id"] = id_fallback[eid]
            return
        # Layer 3: legacy plain-key fallback (backward compat)
        if id_legacy and eid in id_legacy:
            btn["icon_custom_emoji_id"] = id_legacy[eid]

    # InlineKeyboardMarkup
    for row in rm.get("inline_keyboard", []):
        for btn in row:
            _patch_btn(btn)
    # ReplyKeyboardMarkup (main_menu and similar reply keyboards)
    for row in rm.get("keyboard", []):
        for btn in row:
            _patch_btn(btn)
    return rm

# ─────────────────────────────────────────────────────────────────────────────
def get_user_management_text():
    # 🌟 Fast & Free User Management Stats!
    total = len(all_known_users)
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    txt = f"""➖➖➖➖➖➖➖➖
《 👋 USER VIEW 》
➖➖➖➖➖➖➖➖
📊 LIVE STATISTICS:
➖➖➖➖➖➖➖➖
🫂 TOTAL USERS: {total}
✅ VERIFIED USERS: (Hidden to save database cost)
🚫 BANNED USERS: (Hidden to save database cost)
➖➖➖➖➖➖➖➖
⌛ UPDATED: {now_str}"""
    return render_body_text(txt)

def user_management_keyboard():
    _reset_btn_counter()
    return {"inline_keyboard": [
        [{"text": "Manage Balance", "icon_custom_emoji_id": "5190576863226933563", "callback_data": "um_manage_balance", "style": _rs()},
         {"text": "Ban/Unban User", "icon_custom_emoji_id": "5334807341109908955", "callback_data": "um_ban_unban", "style": _rs()}],
        [{"text": "User Profile", "icon_custom_emoji_id": "5352861489541714456", "callback_data": "um_user_profile", "style": _rs()}],
        [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": _rs()}]
    ]}

def menu_design_list_keyboard():
    _reset_btn_counter()
    return {"inline_keyboard": [
        [{"text": "Edit /start Menu", "icon_custom_emoji_id": "5395444784611480792", "callback_data": "md_edit_start", "style": _rs()}],
        [{"text": "Edit GET NUMBER", "icon_custom_emoji_id": "5337132498965010628", "callback_data": "md_edit_get_number", "style": _rs()},
         {"text": "Edit Search Number", "icon_custom_emoji_id": "5463352748751753567", "callback_data": "md_edit_search_number", "style": _rs()}],
        [{"text": "Edit Select Country", "icon_custom_emoji_id": "5336972142066047577", "callback_data": "md_edit_select_country", "style": _rs()}],
        [{"text": "Edit TRAFFIC", "icon_custom_emoji_id": "5353032893096567467", "callback_data": "md_edit_traffic", "style": _rs()},
         {"text": "Edit Refer", "icon_custom_emoji_id": "5420396762189831222", "callback_data": "md_edit_refer", "style": _rs()}],
        [{"text": "Edit WITHDRAWAL", "icon_custom_emoji_id": "5352585194295564660", "callback_data": "md_edit_withdrawal", "style": _rs()},
         {"text": "Edit SUPPORT", "icon_custom_emoji_id": "5420145051336485498", "callback_data": "md_edit_support", "style": _rs()}],
        [{"text": "Reset Defaults", "icon_custom_emoji_id": "5192812028632274956", "callback_data": "md_reset_defaults", "style": _rs()}],
        [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": _rs()}]
    ]}

def menu_edit_options_keyboard(menu_key):
    _reset_btn_counter()
    return {"inline_keyboard": [
        [{"text": "Edit Body (Text)", "icon_custom_emoji_id": "5395444784611480792", "callback_data": f"md_text_{menu_key}", "style": _rs()}],
        [{"text": "Edit Inline Buttons", "icon_custom_emoji_id": "5420155432272438703", "callback_data": f"md_btns_{menu_key}", "style": _rs()}],
        [{"text": "Back to Menus", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "menu_design_list", "style": _rs()}]
    ]}

def menu_buttons_list_keyboard(menu_key):
    _reset_btn_counter()
    kb = []
    btns = bot_settings["custom_messages"].get(menu_key, {}).get("buttons", [])
    for idx, btn in enumerate(btns):
        kb.append([{"text": f"Del: {btn['text']}", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"md_delbtn_{menu_key}_{idx}", "style": _rs()}])
    kb.append([{"text": "Add Inline Button", "icon_custom_emoji_id": "5420323438508155202", "callback_data": f"md_addbtn_{menu_key}", "style": _rs()}])
    kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"md_edit_{menu_key}", "style": _rs()}])
    return {"inline_keyboard": kb}

def emoji_save_type_keyboard():
    """Choose where a single extracted Premium Emoji should be saved."""
    return {"inline_keyboard": [
        [{"text": "Save as FLAG", "icon_custom_emoji_id": "5336972142066047577", "callback_data": "emoji_save_flag", "style": "primary"}],
        [{"text": "Save as APP", "icon_custom_emoji_id": "5337132498965010628", "callback_data": "emoji_save_app", "style": "success"}],
        [{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_emojis", "style": "danger"}],
    ]}


def emoji_settings_keyboard():
    _reset_btn_counter()
    return {"inline_keyboard": [
        [{"text": "All Uploading System", "icon_custom_emoji_id": "5353001161878182134", "callback_data": "emoji_upload_menu", "style": _rs()}],
        [{"text": "All Deleting System",  "icon_custom_emoji_id": "5422557736330106570", "callback_data": "emoji_delete_menu",  "style": _rs()}],
        [{"text": "All Downloading System","icon_custom_emoji_id": "5257969839313526622", "callback_data": "emoji_download_menu","style": _rs()}],
        [{"text": "Add Single Emoji", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "add_single_emoji", "style": "success"}],
        [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": _rs()}]
    ]}
def emoji_upload_keyboard():
    _reset_btn_counter()
    return {"inline_keyboard": [
        [{"text": "Upload Flags (TXT)",    "icon_custom_emoji_id": "5353001161878182134", "callback_data": "up_flags_txt", "style": _rs()}],
        [{"text": "Upload Services (TXT)", "icon_custom_emoji_id": "5353001161878182134", "callback_data": "up_apps_txt",  "style": _rs()}],
        [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_emojis", "style": _rs()}]
    ]}

def emoji_delete_keyboard():
    _reset_btn_counter()
    return {"inline_keyboard": [
        [{"text": "Delete All Flags",    "icon_custom_emoji_id": "5422557736330106570", "callback_data": "del_all_flags", "style": _rs()}],
        [{"text": "Delete All Services", "icon_custom_emoji_id": "5422557736330106570", "callback_data": "del_all_apps",  "style": _rs()}],
        [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_emojis", "style": _rs()}]
    ]}

def emoji_download_keyboard():
    _reset_btn_counter()
    return {"inline_keyboard": [
        [{"text": "Download Flags",        "icon_custom_emoji_id": "5257969839313526622", "callback_data": "dl_flags_txt",    "style": _rs()}],
        [{"text": "Download Services",     "icon_custom_emoji_id": "5257969839313526622", "callback_data": "dl_apps_txt",     "style": _rs()}],
        [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_emojis", "style": _rs()}]
    ]}


# 🌟 Generates a downloadable .txt of saved premium flag/app emojis,
# in the exact format the upload-parser (wait_for_flag_txt / wait_for_app_txt) expects.
def generate_emoji_txt(mode):
    lines = []
    if mode == "flags":
        for code, info in bot_settings.get("premium_flags", {}).items():
            char = info.get("char", "")
            iso = info.get("iso", "")
            name = info.get("name", "")
            eid = info.get("id", "")
            if not (char and eid):
                continue
            json_part = json.dumps({"emoji": char, "id": eid}, ensure_ascii=False)
            lines.append(f"({code}) ({iso}) {name} {char} {json_part}")
    elif mode == "apps":
        for app_key, info in bot_settings.get("premium_apps", {}).items():
            char = info.get("char", "")
            eid = info.get("id", "")
            name = info.get("name", app_key)
            if not (char and eid):
                continue
            json_part = json.dumps({"emoji": char, "id": eid}, ensure_ascii=False)
            lines.append(f"{name} {char} {json_part}")
    return "\n".join(lines)

def fj_settings_keyboard():
    _reset_btn_counter()
    status_text = 'ON' if bot_settings['fj_on'] else 'OFF'
    status_icon = "5352694861990501856" if bot_settings['fj_on'] else "5318840353510408444"
    kb = [[{"text": f"STATUS: {status_text}", "icon_custom_emoji_id": status_icon, "callback_data": "toggle_fj", "style": _rs()}]]
    for idx, entry in enumerate(bot_settings["fj_channels"]):
        info = _get_fj_info(entry)
        ch_type = info.get("type", "channel")
        title = info.get("title", str(info.get("chat_id", "")))
        is_priv = info.get("is_private", False)
        type_tag = "Channel" if ch_type == "channel" else "Group"
        priv_tag = "Private" if is_priv else "Public"
        btn_label = f"{title} [{type_tag} | {priv_tag}]"
        kb.append([{"text": btn_label, "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"del_fj_{idx}", "style": _rs()}])
    kb.append([{"text": "Add Channel / Group", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "add_fj", "style": _rs()}])
    kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": _rs()}])
    return {"inline_keyboard": kb}

def admin_settings_keyboard():
    _reset_btn_counter()
    kb = []
    for idx, adm in enumerate(bot_settings["admins"]):
        text_btn = f"Owner: {adm}" if adm == OWNER_ID else f"Delete: {adm}"
        icon_id = "5353032893096567467" if adm == OWNER_ID else "5420130255174145507"
        # FIX: use the actual admin ID instead of idx — when the list shifted the wrong admin was deleted
        cb_data = "ignore" if adm == OWNER_ID else f"del_adm_{adm}"
        kb.append([{"text": text_btn, "icon_custom_emoji_id": icon_id, "callback_data": cb_data, "style": _rs()}])
    kb.append([{"text": "Add Admin", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "add_adm", "style": _rs()}])
    kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": _rs()}])
    return {"inline_keyboard": kb}

def otp_groups_list_keyboard():
    _reset_btn_counter()
    kb = [[{"text": "Edit OTP Button Link", "icon_custom_emoji_id": "5420517437885943844", "callback_data": "edit_otp_link", "style": _rs()}]]
    for idx, fg in enumerate(bot_settings["fw_groups"]):
        kb.append([{"text": f"Group: {fg['chat_id']}", "icon_custom_emoji_id": "5193063022226086560", "callback_data": f"manage_fw_{idx}", "style": _rs()}])
    kb.append([{"text": "Add Forward Group", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "add_fw", "style": _rs()}])
    kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": _rs()}])
    return {"inline_keyboard": kb}

def otp_forward_manager_keyboard():
    return {"inline_keyboard": [
        [{"text": "Set Channel Link", "icon_custom_emoji_id": "5420517437885943844", "callback_data": "set_channel_link", "style": "primary"},
         {"text": "Set Number Link", "icon_custom_emoji_id": "5337132498965010628", "callback_data": "set_number_link", "style": "primary"}],
        [{"text": "Message Emojis", "icon_custom_emoji_id": "5352552689983067014", "callback_data": "otp_message_emojis", "style": "success"}],
        [{"text": "Button Emojis", "icon_custom_emoji_id": "5352552689983067014", "callback_data": "otp_button_emojis", "style": "success"}],
        [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": "danger"}]
    ]}

def otp_message_emoji_keyboard():
    labels = [
        ("🇺🇳 Before Flag", "before_flag"),
        ("📱 Before Service", "before_service"),
        ("📞 Before Number", "before_number"),
        ("🕒 Before Time", "before_time"),
        ("🔐 Before OTP", "before_otp"),
    ]
    rows = []
    current = bot_settings.get("otp_forward", {}).get("emoji_positions", {}) or {}
    for label, key in labels:
        status = "✅" if current.get(key) else "➕"
        rows.append([{"text": f"{status} {label}", "callback_data": f"set_otp_msg_emoji_{key}", "style": "primary"}])
    rows.append([{"text": "Clear All", "icon_custom_emoji_id": "5422557736330106570", "callback_data": "clear_otp_msg_emojis", "style": "danger"}])
    rows.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "otp_forward_manager", "style": "danger"}])
    return {"inline_keyboard": rows}

def otp_button_emoji_keyboard():
    labels = [
        ("🔗 Channel", "channel"),
        ("🔐 OTP Copy", "otp"),
        ("📱 Number Bot", "number_bot"),
    ]
    rows = []
    current = bot_settings.get("otp_forward", {}).get("button_emojis", {}) or {}
    for label, key in labels:
        status = "✅" if current.get(key) else "➕"
        rows.append([{"text": f"{status} {label}", "callback_data": f"set_otp_btn_emoji_{key}", "style": "primary"}])
    rows.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "otp_forward_manager", "style": "danger"}])
    return {"inline_keyboard": rows}

def auto_mode_keyboard():
    _reset_btn_counter()
    nexa_on  = bot_settings.get("nexa_on", False)
    voltx_on = bot_settings.get("voltx_on", False)
    stex_on  = bot_settings.get("stex_on", False)
    # ON  emoji: green indicator  | OFF emoji: red indicator
    ON_EMOJI  = "6237529876690113625"
    OFF_EMOJI = "6267000941547885720"
    return {"inline_keyboard": [
        [{"text": "Nexa Panel Control",  "icon_custom_emoji_id": "6282760761399841824", "callback_data": "nexa_control",  "style": _rs()},
         {"text": "Nexa ON"  if nexa_on  else "Nexa OFF",  "icon_custom_emoji_id": ON_EMOJI if nexa_on  else OFF_EMOJI, "callback_data": "toggle_nexa",  "style": _rs()}],
        [{"text": "VoltX Panel Control", "icon_custom_emoji_id": "6282760761399841824", "callback_data": "voltx_control", "style": _rs()},
         {"text": "VoltX ON" if voltx_on else "VoltX OFF", "icon_custom_emoji_id": ON_EMOJI if voltx_on else OFF_EMOJI, "callback_data": "toggle_voltx", "style": _rs()}],
        [{"text": "Stex Panel Control",  "icon_custom_emoji_id": "6282760761399841824", "callback_data": "stex_control",  "style": _rs()},
         {"text": "Stex ON"  if stex_on  else "Stex OFF",  "icon_custom_emoji_id": ON_EMOJI if stex_on  else OFF_EMOJI, "callback_data": "toggle_stex",  "style": _rs()}],
        [{"text": "Back",  "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": _rs()}]
    ]}

def _panel_control_keyboard(panel_name):
    """Shared API panel control keyboard for Nexa, VoltX, Stex.
    panel_name: display name e.g. 'Nexa', 'VoltX', 'Stex' — lowercase used for callback IDs."""
    p = panel_name.lower()
    _reset_btn_counter()
    return {"inline_keyboard": [
        [{"text": f"Add {panel_name} Key", "icon_custom_emoji_id": "5420323438508155202", "callback_data": f"add_{p}_key", "style": _rs()},
         {"text": "View/Del Keys", "icon_custom_emoji_id": "5422557736330106570", "callback_data": f"view_{p}_keys", "style": _rs()}],
        [{"text": f"Manage {panel_name} Services", "icon_custom_emoji_id": "5192739271886282680", "callback_data": f"manage_{p}_srv", "style": _rs()}],
        [{"text": "Search Country", "icon_custom_emoji_id": "5336972142066047577", "callback_data": f"{p}_search_country", "style": _rs()}],
        [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "auto_mode", "style": _rs()}]
    ]}


def specific_fw_group_keyboard(idx):
    _reset_btn_counter()
    if idx < 0 or idx >= len(bot_settings.get("fw_groups", [])):
        return {"inline_keyboard": [[{"text": "Group Not Found", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "manage_otp_groups", "style": "danger"}]]}
    group = bot_settings["fw_groups"][idx]
    kb = []
    for b_idx, btn in enumerate(group.get("buttons", [])):
        kb.append([{"text": f"Del: {btn['text']}", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"del_fwbtn_{idx}_{b_idx}", "style": _rs()}])
    
    kb.append([{"text": "Add Inline Button", "icon_custom_emoji_id": "5420323438508155202", "callback_data": f"add_fwbtn_{idx}", "style": _rs()}])
    kb.append([{"text": "Delete Entire Group", "icon_custom_emoji_id": "5422557736330106570", "callback_data": f"del_fw_{idx}", "style": _rs()}])
    kb.append([{"text": "Back to Groups", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_otp_groups", "style": _rs()}])
    return {"inline_keyboard": kb}

def currently_control_keyboard():
    _reset_btn_counter()
    w_status = "ON" if bot_settings["withdraw_on"] else "OFF"
    sup_status = "ON" if bot_settings.get("support_link") else "OFF"
    grp_status = "ON" if bot_settings.get("w_group") else "OFF"
    return {"inline_keyboard": [
        [{"text": f"WITHDRAW: {w_status}", "icon_custom_emoji_id": "5348469219761626211", "callback_data": "currently_toggle_w", "style": _rs()}],
        [{"text": f"MIN WITHDRAW: {bot_settings['min_withdraw']}", "icon_custom_emoji_id": "5352877703043258544", "callback_data": "currently_min_w", "style": _rs()},
         {"text": f"OTP REWARD: {bot_settings['otp_reward']}", "icon_custom_emoji_id": "5190576863226933563", "callback_data": "currently_otp_r", "style": _rs()}],
        [{"text": f"REFER REWARD: {bot_settings['refer_reward']}", "icon_custom_emoji_id": "5420396762189831222", "callback_data": "currently_ref_r", "style": _rs()},
         {"text": f"COOLDOWN: {bot_settings['cooldown']}s", "icon_custom_emoji_id": "5337172996211648018", "callback_data": "currently_cool", "style": _rs()}],
        [{"text": f"NUM/REQ: {bot_settings['num_req']}", "icon_custom_emoji_id": "5337132498965010628", "callback_data": "currently_num_req", "style": _rs()},
         {"text": f"NUM/SHARE: {bot_settings['num_share']}", "icon_custom_emoji_id": "5352862640592949843", "callback_data": "currently_num_share", "style": _rs()}],
        [{"text": f"USD RATE: 1$ = {bot_settings.get('usd_rate', DEFAULT_USD_RATE)} pkr", "icon_custom_emoji_id": "5348469219761626211", "callback_data": "now_usd_rate", "style": _rs()}],
        [{"text": f"SUPPORT LINK: {sup_status}", "icon_custom_emoji_id": "5420145051336485498", "callback_data": "currently_sup_link", "style": _rs()},
         {"text": "W. METHODS", "icon_custom_emoji_id": "5190899075968441286", "callback_data": "manage_w_methods", "style": _rs()}],
        [{"text": f"W. GROUP: {'ON' if bot_settings.get('w_group') else 'OFF'}", "icon_custom_emoji_id": "5420517437885943844", "callback_data": "currently_w_group", "style": _rs()},
         {"text": "BACK", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": _rs()}]
    ]}

def w_methods_keyboard():
    _reset_btn_counter()
    kb = []
    for idx, m in enumerate(bot_settings["w_methods"]):
        kb.append([{"text": f"Delete: {m}", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"del_wm_{idx}", "style": _rs()}])
    kb.append([{"text": "Add Method", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "add_wm", "style": _rs()}])
    kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "currently_control", "style": _rs()}])
    return {"inline_keyboard": kb}

def typed_panels_list_keyboard(p_type):
    _reset_btn_counter()
    kb = []
    for idx, p in enumerate(bot_settings["panels"]):
        if p.get("type", "API Panel") != p_type: continue
        action_text = f"Turn OFF {p['name']}" if p['status'] == 'ON' else f"Turn ON {p['name']}"
        action_icon = "5318840353510408444" if p['status'] == 'ON' else "5192812028632274956"
        icon_id = "5420155432272438703" 
        kb.append([
            {"text": action_text, "icon_custom_emoji_id": action_icon, "callback_data": f"tog_pnl_{idx}", "style": _rs()},
            {"text": f"{p['name']}", "icon_custom_emoji_id": icon_id, "callback_data": f"conf_pnl_{idx}", "style": _rs()}
        ])
    add_cb = f"add_{_pnl_key(p_type)}_panel"
    kb.append([{"text": "Add New Provider", "icon_custom_emoji_id": "5420323438508155202", "callback_data": add_cb, "style": _rs()}])
    kb.append([{"text": "Delete Provider", "icon_custom_emoji_id": "5336944168944047463", "callback_data": f"list_del_{_pnl_key(p_type)}", "style": _rs()}])
    kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_panels", "style": _rs()}])
    return {"inline_keyboard": kb}

def panel_config_keyboard(idx):
    _reset_btn_counter()
    if idx < 0 or idx >= len(bot_settings.get("panels", [])):
        return {"inline_keyboard": [[{"text": "Panel Not Found", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "manage_panels", "style": "danger"}]]}
    p = bot_settings["panels"][idx]
    
    kb = []
    action_text = "Turn OFF" if p['status'] == 'ON' else "Turn ON"
    action_icon = "5318840353510408444" if p['status'] == 'ON' else "5192812028632274956"
    kb.append([{"text": action_text, "icon_custom_emoji_id": action_icon, "callback_data": f"tog_pnl_{idx}", "style": _rs()}])
    
    if p["type"] == "API Panel":
        rec_count_text = "All (Unlimited)" if p.get('records', 0) == 0 else str(p.get('records'))
        kb.append([{"text": "Set API URL", "icon_custom_emoji_id": "5420517437885943844", "callback_data": f"set_p_api_{idx}", "style": _rs()}])
        kb.append([{"text": "Set Token", "icon_custom_emoji_id": "5353022963132174959", "callback_data": f"set_p_tok_{idx}", "style": _rs()}])
        token_hdr = p.get("token_header", "")
        hdr_text = f"Token Header: {token_hdr}" if token_hdr else "Set Token Header (Optional)"
        kb.append([{"text": hdr_text, "icon_custom_emoji_id": "5353022963132174959", "callback_data": f"set_p_tokh_{idx}", "style": _rs()}])
        kb.append([{"text": "Full API (URL+Token)", "icon_custom_emoji_id": "5420517437885943844", "callback_data": f"set_p_fapi_{idx}", "style": _rs()}])
        kb.append([{"text": f"Set Records Count: {rec_count_text}", "icon_custom_emoji_id": "5192739271886282680", "callback_data": f"set_p_rec_{idx}", "style": _rs()}])
    elif p["type"] == "Live Socket Panel":
        kb.append([{"text": "Set WebSocket URL", "icon_custom_emoji_id": "5420517437885943844", "callback_data": f"set_p_wsurl_{idx}", "style": _rs()}])

    kb.append([{"text": "Test Connection", "icon_custom_emoji_id": "5276032951342088188", "callback_data": f"test_p_conn_{idx}", "style": _rs()}])
        
    back_data = f"manage_{_pnl_key(p.get('type', 'API Panel'))}_panels"
    kb.append([{"text": "Back to Providers", "icon_custom_emoji_id": "5267490665117275176", "callback_data": back_data, "style": _rs()}])
    return {"inline_keyboard": kb}

def build_traffic_ui():
    current_time = time.time()
    _prune_traffic(current_time)
    
    stats = {}
    with _traffic_lock:
        _traffic_snapshot = list(recent_traffic)
    for t in _traffic_snapshot:
        srv = t.get("service", "Unknown")
        iso = t.get("iso", "XX")
        flag = t.get("flag", "🌍")
        
        if srv not in stats:
            stats[srv] = {}
        if iso not in stats[srv]:
            stats[srv][iso] = {"count": 0, "flag": flag}
        stats[srv][iso]["count"] += 1
        
    txt = "╔═════════════════╗\n║  📈 <b>NETWORK TRAFFIC</b>\n╚═════════════════╝\n\n"
    
    _reset_btn_counter()
    kb = []
    if not stats:
        txt += "<i>No recent traffic found in the last hour...</i>\n"
    else:
        srv_totals = []
        for srv, countries in stats.items():
            total = sum(c["count"] for c in countries.values())
            srv_totals.append((srv, total, countries))
        
        srv_totals.sort(key=lambda x: x[1], reverse=True)
        
        for srv, total, countries in srv_totals:
            app_full_name, prem_app_html = get_service_info_html(srv)
            txt += f"[ {prem_app_html} <b>{app_full_name}</b> ]\n│\n"
            
            c_list = sorted(countries.items(), key=lambda x: x[1]["count"], reverse=True)
            c_list = c_list[:7] 
            
            for i, (iso, c_data) in enumerate(c_list):
                prem_flag_html = get_flag_info_html(iso)
                count = c_data["count"]
                
                c_name = iso
                for code, fdata in bot_settings.get("premium_flags", {}).items():
                    if fdata.get("iso") == iso:
                        c_name = fdata.get("name", iso)
                        break
                        
                txt += f"├ {prem_flag_html} <b>{c_name} ({iso})</b>\n"
                txt += f"│ ╰ Success: {count}\n"
                if i < len(c_list) - 1:
                    txt += "│\n"
            txt += "\n"
        
        # 🌟 FIX: [:3] limit removed, now all services will show buttons below!
        for srv, _, _ in srv_totals: 
            safe_srv = srv[:20] 
            # To show full name nicely in button
            app_full_name, _ = get_service_info_html(safe_srv, safe_srv)
            kb.append([{"text": f"Explore {app_full_name} Range", "icon_custom_emoji_id": "5190645917711114179", "callback_data": f"exp_rng_{safe_srv}", "style": _rs()}])
            
    txt = render_body_text(txt)
    kb.append([{"text": "Refresh", "icon_custom_emoji_id": "5420155432272438703", "callback_data": "refresh_traffic", "style": _rs()}])
    _add_close_btn(kb)
    
    return txt, {"inline_keyboard": kb}

# ==========================================
# OTP Deduplication Persistence
# ==========================================
_seen_otps_save_lock = threading.Lock()

def _save_processed_otps():
    with _seen_otps_save_lock:
        try:
            with _data_lock:
                items = dict(processed_otps)
            cutoff = time.time() - 90000
            items = {k: v for k, v in items.items() if v > cutoff}
            tmp_path = SEEN_OTPS_FILE + ".tmp"
            
            # Windows fix: আগের temp ফাইল থাকলে ডিলিট
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except:
                    pass
            
            with open(tmp_path, "w") as f:
                json.dump(items, f)
            
            # Windows fix: আগের main ফাইল থাকলে ডিলিট, তারপর rename
            if os.path.exists(SEEN_OTPS_FILE):
                os.remove(SEEN_OTPS_FILE)
            os.rename(tmp_path, SEEN_OTPS_FILE)
            
        except Exception as e:
            logger.warning(f"OTP save error: {e}")

def _load_processed_otps():
    global processed_otps
    try:
        with open(SEEN_OTPS_FILE, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            cutoff = time.time() - 90000  # 25h — matches the save
            new_dict = {k: v for k, v in data.items() if v > cutoff}
        else:
            # Old format (list) — assign a one-hour-old timestamp
            new_dict = {uid: time.time() - 3600 for uid in data}
        with _data_lock:
            processed_otps = new_dict
        logger.info(f"Loaded {len(new_dict)} previously seen OTP IDs — old OTPs will be skipped.")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        with _data_lock:
            processed_otps = {}
        if not isinstance(e, FileNotFoundError):
            logger.warning(f"seen_otps.json parse error: {e} — starting fresh")

def _add_to_processed(unique_id):
    with _data_lock:
        processed_otps[unique_id] = time.time()
        # 25 ghante from old entries remove (save/load cutoff with match)
        if len(processed_otps) > 20000:
            cutoff = time.time() - 90000
            old_keys = [k for k, v in processed_otps.items() if v < cutoff]
            for k in old_keys:
                del processed_otps[k]
            # if currently also too many, to oldest 10000 remove
            if len(processed_otps) > 20000:
                sorted_keys = sorted(processed_otps, key=lambda k: processed_otps[k])
                for k in sorted_keys[:10000]:
                    del processed_otps[k]

def _is_processed(unique_id, window=90000):
    """True if this unique_id was processed within the last `window` seconds (default 25 hours).
    The 25-hour window covers panels retaining 24 hours of OTP history plus a one-hour margin.
    Old OTPs will never be delivered again."""
    with _data_lock:
        ts = processed_otps.get(unique_id)
        if ts is None:
            return False
        return (time.time() - ts) < window

# ==========================================
# OTP Age Guard — extract the OTP's real age from the panel's own timestamp (item_id)
# ==========================================
# FIX: Old dedup only checked "don't send a previously seen OTP again" —
# lekin if any OTP that panel in 25+ ghante old is, bot the first time seen
# (restart, panel lag, number reuse or history replay because of), to that "new"
# it was treated as new and delivered, even though it was actually an old OTP.
# Now item_id (the panel's date/time column) is parsed to check the actual age.
# it is — if the OTP is older than 25 hours, then it should NEVER be sent to the group/user
# deliver not will be, chahe dedup memory in first time hi show remaining be.
OTP_MAX_AGE_SECONDS = 90000  # 25 ghante

_DT_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%fZ",   # ISO 8601 with ms + Z  (such as Teleroutex createdAt)
    "%Y-%m-%dT%H:%M:%SZ",      # ISO 8601 without ms + Z
    "%Y-%m-%dT%H:%M:%S.%f",    # ISO 8601 with ms, no Z
)

def _parse_item_datetime_epoch(dt_str):
    """item_id in aya datetime string to epoch seconds in convert does is.
    If parsing fails it returns None (the age-check is skipped in that case —
    hum only CONFIRMED old OTPs to block do are, kabhi false-positive not)."""
    if not dt_str:
        return None
    s = str(dt_str).strip()
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(s, fmt).timestamp()
        except (ValueError, TypeError):
            continue
    # item_id inside datetime chhupa be (such as "2025-03-16 21:38:27|84966570308|705516")
    m = re.search(r'\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}(:\d{2})?', s)
    if m:
        head = m.group(0)
        if len(head) == 16:      # seconds missing
            head += ":00"
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(head, fmt).timestamp()
            except (ValueError, TypeError):
                continue
    return None

def _is_stale_otp(item_id, max_age=OTP_MAX_AGE_SECONDS):
    """True if item_id of your timestamp bataye of OTP already max_age from old is.
    The panel record's timestamp can also be in the future (clock drift) — in that case
    Only confirmed old OTPs are blocked; false positives are never treated as stale."""
    epoch = _parse_item_datetime_epoch(item_id)
    if epoch is None:
        return False
    age = time.time() - epoch
    return age > max_age

# ==========================================
# Shared Helper Functions (deduplication)
# ==========================================
def _process_pending_referral(chat_id):
    u_data = _get_local_user(chat_id)
    if u_data.get("referred_by") and not u_data.get("ref_paid"):
        inviter = u_data["referred_by"]
        _update_local_user(chat_id, {"ref_paid": True})
        reward = bot_settings.get("refer_reward", 0.2)
        update_balance(inviter, reward)
        _increment_local_user(inviter, "total_refers", 1)
        ref_msg = (
            f"{PEM['gift']} <b>New Referral !</b>\n"
            f"------------------\n"
            f"🔥 <b>You Received {reward} PKR</b>\n"
            f"------------------\n"
            f"{PEM['user']} <b>From User ID:</b> <code>{chat_id}</code>"
        )
        send_message(inviter, render_body_text(ref_msg))

def _get_all_numbers_set():
    all_nums = set()
    for b in number_batches.values():
        for n in b["numbers"]:
            all_nums.add(n["num"].replace("+", "").strip())
    for n in used_numbers_list:
        all_nums.add(n.replace("+", "").strip())
    return all_nums

def _record_and_deliver_otp(owner_id, num_str, app_name, msg_text, otp, clean_num_key, caller_tag=""):
    """Shared helper: record traffic + save DB + deliver OTP to user + mark otp_received.
    Used by poll_otp_with_status, _poll_mauthapi_otp_single, _poll_mauthapi_otps, global_sms_listener."""
    char, iso = get_flag_and_code(num_str)
    app_full_name, prem_app_html = get_service_info_html(app_name, msg_text)
    current_time = time.time()
    _prune_traffic(current_time)
    with _traffic_lock:
        recent_traffic.append({"service": app_full_name, "iso": iso, "flag": char, "number": num_str, "time": current_time})
    save_local_db()
    _deliver_otp_to_user(owner_id, num_str, app_full_name, prem_app_html, iso, otp, msg_text)
    try:
        clean_key = str(clean_num_key).replace("+", "").replace(" ", "").replace("-", "").strip()
        with _data_lock:
            otp_received_numbers.add(clean_key)
    except Exception as e:
        logger.warning(f"otp_received_numbers error [{caller_tag}]: {e}")



# ===== OTP Group Inline Buttons (Channel + OTP + Number Bot) =====
def build_otp_group_keyboard(otp):
    """Build OTP group keyboard using admin-configurable custom emoji IDs."""
    forward = bot_settings.get("otp_forward", {}) or {}
    channel_link = str(
        forward.get("channel_link") or bot_settings.get("otp_link") or ""
    ).strip()
    number_link = str(
        forward.get("number_link") or f"https://t.me/{str(BOT_USERNAME).lstrip('@')}"
    ).strip()
    btn_emojis = forward.get("button_emojis", {}) or {}

    channel_emoji = str(btn_emojis.get("channel", "5420517437885943844") or "5420517437885943844")
    otp_emoji = str(btn_emojis.get("otp", "5353022963132174959") or "5353022963132174959")
    number_emoji = str(btn_emojis.get("number_bot", "5337132498965010628") or "5337132498965010628")

    kb = []
    first_row = []
    if channel_link:
        first_row.append({
            "text": "Channel",
            "icon_custom_emoji_id": channel_emoji,
            "url": channel_link,
            "style": "success"
        })
    first_row.append({
        "text": str(otp),
        "icon_custom_emoji_id": otp_emoji,
        "copy_text": {"text": str(otp)},
        "style": "primary"
    })
    kb.append(first_row)

    if number_link:
        kb.append([{
            "text": "Number Bot",
            "icon_custom_emoji_id": number_emoji,
            "url": number_link,
            "style": "success"
        }])
    return kb

def format_otp_group_message(service_code, service_emoji_html, flag_emoji_html, number, otp, lang):
    if not lang:
        lang = "#EN"
    if not str(lang).startswith("#"):
        lang = "#" + str(lang)
    masked = mask_number(number)
    msg = f"╔═══════════════╗\n║ {service_emoji_html} {flag_emoji_html} {masked} {lang} ║\n╚═══════════════╝"
    return render_body_text(msg)

def _make_otp_kb(otp_code):
    """OTP copy-button keyboard helper — single definition used everywhere."""
    return [[{"text": str(otp_code), "icon_custom_emoji_id": "5474525960143385880",
              "copy_text": {"text": str(otp_code)}, "style": _rs()}]]

def _deliver_otp_to_user(owner_id, num_str, app_full_name, prem_app_html, iso, otp_code, msg_text):
    _reset_btn_counter()
    display_num = f"+{num_str}" if not str(num_str).startswith("+") else str(num_str)
    lang = detect_language(msg_text)
    reward = get_number_rate(num_str)
    # Do group delivery first — group will not be blocked because owner_id is None
    # The FULL number and correct country flag are also sent to the group
    group_msg = format_otp_group_message(
        app_full_name, prem_app_html, get_flag_info_html(display_num), display_num, otp_code, lang
    )
    # ✅ Deliver to OTP Group (Forward Groups) — owner not required
    for fw in bot_settings.get("fw_groups", []):
        try:
            _reset_btn_counter()
            kb = build_otp_group_keyboard(otp_code)
            res_fw = send_message(fw["chat_id"], group_msg, reply_markup={"inline_keyboard": kb})
            if res_fw and res_fw.get("ok"):
                logger.debug(f"OTP forwarded to group {fw.get('chat_id')}")
            else:
                logger.warning(f"FW Group send failed ({fw.get('chat_id')}): {res_fw}")
        except Exception as e:
            logger.warning(f"FW Group delivery error ({fw.get('chat_id')}): {e}")
    # ✅ Deliver to user's personal chat — only when owner is found
    if not owner_id:
        return
    display_msg = render_body_text(
        f"╔═══════════════╗\n"
        f"║ {prem_app_html} {get_flag_info_html(display_num)} {display_num} {lang} ║\n"
        f"╚═══════════════╝")
    _reset_btn_counter()
    reward = float(get_number_rate(num_str) or 0.0)
    reward_label = f"{reward:g}"
    inbox_kb = [[{"text": str(otp_code), "icon_custom_emoji_id": "5352694861990501856",
                   "copy_text": {"text": str(otp_code)}, "style": _rs()}]]
    inbox_kb.append([{"text": f"Added {reward_label} tk",
                      "icon_custom_emoji_id": "5420396762189831222",
                      "callback_data": "ignore", "style": "primary"}])
    if reward > 0:
        update_balance(owner_id, reward)
        logger.debug(f"OTP reward {reward} credited to user {owner_id}")
    try:
        send_message(owner_id, display_msg, reply_markup={"inline_keyboard": inbox_kb})
        logger.debug(f"OTP delivered to user {owner_id}: {otp_code}")
    except Exception as e:
        logger.warning(f"User OTP delivery error ({owner_id}): {e}")
    _increment_local_user(owner_id, "total_otps", 1)

# ==========================================
# Message Handler
# ==========================================

def _alert_group_gone(call):
    answer_callback(call["id"], "❌ Group not found!", show_alert=True)

_PANEL_SC_CFG = {
    "nexa":  {"key": "nexa_search_countries",  "del_cb": "del_sc_",    "add_cb": "add_search_country",     "back_cb": "nexa_control",  "label": "Nexa"},
    "voltx": {"key": "voltx_search_countries", "del_cb": "del_vxsc_",  "add_cb": "add_vx_search_country",  "back_cb": "voltx_control", "label": "VoltX"},
    "stex":  {"key": "stex_search_countries",  "del_cb": "del_stxsc_", "add_cb": "add_stx_search_country", "back_cb": "stex_control",  "label": "Stex"},
}

def _show_panel_search_countries(panel, chat_id, msg_id):
    """Show allowed search countries UI for a panel (nexa/voltx/stex)."""
    cfg = _PANEL_SC_CFG[panel]
    _reset_btn_counter()
    kb = []
    for idx, c in enumerate(bot_settings.get(cfg["key"], [])):
        kb.append([{"text": f"Delete {c}", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"{cfg['del_cb']}{idx}", "style": _rs()}])
    kb.append([{"text": "Add Country Code", "icon_custom_emoji_id": "5420323438508155202", "callback_data": cfg["add_cb"], "style": _rs()}])
    kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": cfg["back_cb"], "style": _rs()}])
    edit_message(chat_id, msg_id, render_body_text(
        f"🌍 <b>{cfg['label']} Allowed Search Countries:</b>\n"
        f"Only these country codes will be allowed in Search Number for {cfg['label']}."),
        reply_markup={"inline_keyboard": kb})


def _alert_panel_gone(call):
    answer_callback(call["id"], "❌ Panel not found! List may have changed.", show_alert=True)

def _err_panel_gone(chat_id):
    send_message(chat_id, render_body_text("❌ Panel not found! It may have been deleted."))

def _set_panel_temp(chat_id, msg_id, idx):
    panels = bot_settings.get("panels", [])
    if idx < 0 or idx >= len(panels):
        _err_panel_gone(chat_id)
        return
    temp_data[chat_id] = {"msg_id": msg_id, "p_idx": idx, "p_name": panels[idx]["name"]}

def _add_close_btn(kb):
    kb.append([{"text": "Close", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": _rs()}])

def _append_custom_btns(kb, c_msg):
    for b in c_msg.get("buttons", []):
        b_copy = b.copy()
        b_copy["style"] = _rs()
        kb.append([b_copy])

def _prune_traffic(current_time):
    with _traffic_lock:
        recent_traffic[:] = [t for t in recent_traffic if current_time - t.get("time", 0) <= 3600]

def _find_flag_emoji_id(c, flags_db, default="5780471598922337683"):
    # ✅ FIX: First check direct dial code key (e.g. "91", "880", "1")
    if c in flags_db and "id" in flags_db[c]:
        return flags_db[c]["id"]
    c_upper = c.upper()
    for flag_data in flags_db.values():
        iso = flag_data.get("iso", "").upper()
        name = flag_data.get("name", "").upper()
        if c_upper == iso or c_upper == name or c_upper in name or name in c_upper:
            if "id" in flag_data:
                return flag_data["id"]
    return default

def _save_panel_field(chat_id, msg, field, value):
    if not _td_has(chat_id, "p_idx", "msg_id"):
        _err_panel_gone(chat_id)
        user_states.pop(chat_id, None)
        temp_data.pop(chat_id, None)
        return
    idx = _td(chat_id, "p_idx", -1)
    edit_msg_id = _td(chat_id, "msg_id", msg["message_id"])
    if idx < 0 or idx >= len(bot_settings["panels"]):
        _err_panel_gone(chat_id)
    else:
        bot_settings["panels"][idx][field] = value
        save_local_db()
        delete_message(chat_id, msg["message_id"])
        _show_panel_cfg(chat_id, edit_msg_id, idx)
    user_states.pop(chat_id, None)
    temp_data.pop(chat_id, None)


# ==========================================
# Shared UI Helpers (deduplication)
# ==========================================
def _show_fj_panel(chat_id, msg_id):
    edit_message(chat_id, msg_id, render_body_text(f"{PEM['link']} <b>FORCE JOIN SYSTEM</b>\nManage channels/groups below:"), reply_markup=fj_settings_keyboard())

def _show_admin_panel(chat_id, msg_id):
    edit_message(chat_id, msg_id, render_body_text(f"{PEM['user']} <b>ADMIN MANAGEMENT</b>\nManage your bot admins below:"), reply_markup=admin_settings_keyboard())

def _show_otp_groups_panel(chat_id, msg_id):
    edit_message(chat_id, msg_id, render_body_text("🛡 <b>OTP GROUP MANAGEMENT</b>\nManage settings below:"), reply_markup=otp_groups_list_keyboard())

def _show_currently_panel(chat_id, msg_id, extra=""):
    txt = "🕹 <b>BOT CONTROL PANEL</b>"
    if extra: txt += f"\n\n{extra}"
    edit_message(chat_id, msg_id, render_body_text(txt), reply_markup=currently_control_keyboard())

def _show_w_methods(chat_id, msg_id):
    edit_message(chat_id, msg_id, render_body_text("💳 <b>WITHDRAWAL METHODS</b>\n\nManage your withdrawal methods below:"), reply_markup=w_methods_keyboard())

def _show_panel_cfg(chat_id, edit_msg_id, idx):
    """Refresh panel config display after a field update."""
    if idx < 0 or idx >= len(bot_settings["panels"]):
        _err_panel_gone(chat_id)
        return
    p = bot_settings["panels"][idx]
    if p["type"] == "Auto Captcha Panel":
        text = (f"⚙️ <b>Configure {p['name']}</b>\n\n<b>Type:</b> {p['type']}\n"
                f"<b>Status:</b> {'🟢 Monitoring' if p['status'] == 'ON' else '🔴 Stopped'}\n"
                f"<b>Login Status:</b> {p.get('login_status', 'Unknown')}\n"
                f"<b>Login URL:</b> <code>{p.get('login_url', 'None')}</code>\n"
                f"<b>User:</b> <code>{p.get('username', 'None')}</code>")
    else:
        hdr_info = f"\n<b>Token Header:</b> <code>{p.get('token_header')}</code>" if p.get('token_header') else ""
        text = (f"⚙️ <b>Configure {p['name']}</b>\n\n<b>Type:</b> {p['type']}\n"
                f"<b>Status:</b> {'🟢 Monitoring' if p['status'] == 'ON' else '🔴 Stopped'}\n"
                f"<b>API URL:</b> <code>{p.get('api_url', 'None')}</code>\n"
                f"<b>Token:</b> <code>{p.get('token', 'None')}</code>{hdr_info}\n"
                f"<b>Full API URL:</b> <code>{p.get('full_api_url', 'None')}</code>")
    edit_message(chat_id, edit_msg_id, render_body_text(text), reply_markup=panel_config_keyboard(idx))


def _err_invalid_id(chat_id):
    send_message(chat_id, render_body_text("❌ Invalid ID!"), reply_markup=get_cancel_kb())

def _show_2fa_name_input(chat_id, msg_id):
    """Helper: 2FA naam input screen. Duplicate code remove."""
    txt = (
        f"━━━━━━━━━━━━━━━\n"
        f"《 📛 <b>ENTER THE CODE NAME</b> 》\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📝 What name do you want to give this 2FA code?\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👇 Type and send the name:"
    )
    _reset_btn_counter()
    kb = {"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "cancel_2fa", "style": _rs()}]]}
    edit_message(chat_id, msg_id, render_body_text(txt), reply_markup=kb)


def _make_fw_btn(btn, kb):
    b = {"text": btn["text"], "url": btn["url"], "style": _rs()}
    if "icon_custom_emoji_id" in btn: b["icon_custom_emoji_id"] = btn["icon_custom_emoji_id"]
    return b

def _build_services_keyboard(c_msg_key="get_number"):
    """Helper: GET NUMBER screen for services list keyboard banata is. Duplicate code remove."""
    local_srvs = set([b["service"] for b in number_batches.values() if b["numbers"]])
    nexa_srvs = set(bot_settings.get("nexa_services", {}).keys())
    voltx_srvs = set(bot_settings.get("voltx_services", {}).keys())
    stex_srvs = set(bot_settings.get("stex_services", {}).keys())
    all_services = local_srvs.union(nexa_srvs).union(voltx_srvs).union(stex_srvs)
    c_msg = bot_settings["custom_messages"].get(c_msg_key, {})
    # Keep the GET NUMBER service screen's original heading even if an old
    # bot_data.json contains a shortened/custom value such as "Get N".
    if c_msg_key == "get_number":
        txt = render_body_text(f"{PEM['pin']} Select a service:")
    else:
        txt = render_body_text(c_msg.get("text", f"{PEM['pin']} Select Service"))
    apps_db = bot_settings.get("premium_apps", {})
    _reset_btn_counter()
    kb = []
    for s in sorted(all_services):
        emoji_id = _get_service_emoji_id(s, apps_db)
        kb.append([{"text": s, "icon_custom_emoji_id": emoji_id, "callback_data": f"g_s_{s}", "style": _rs()}])
    _append_custom_btns(kb, c_msg)
    _add_close_btn(kb)
    return all_services, txt, kb


def _search_and_recycle_local(query, chat_id):
    """Search local number_batches for numbers matching prefix query.
    If all matching numbers are already used by this user, recycle them (reset shares/used_by).
    Returns list of (batch_id, index) tuples for available numbers."""
    found_indices = []
    for b_id, b_data in number_batches.items():
        for idx, n_obj in enumerate(b_data["numbers"]):
            if n_obj["num"].replace("+", "").startswith(query) and chat_id not in n_obj.get("used_by", []):
                found_indices.append((b_id, idx))
    if not found_indices:
        has_matching = False
        for b_id, b_data in number_batches.items():
            for n_obj in b_data["numbers"]:
                if n_obj["num"].replace("+", "").startswith(query):
                    has_matching = True
                    n_obj["shares"] = 0
                    n_obj["used_by"] = []
        if has_matching:
            for b_id, b_data in number_batches.items():
                for idx, n_obj in enumerate(b_data["numbers"]):
                    if n_obj["num"].replace("+", "").startswith(query):
                        found_indices.append((b_id, idx))
    return found_indices


def handle_message(msg):
    global total_assigned_stats
    global total_uploaded_stats
    chat_id = msg["chat"]["id"]
    chat_type = msg["chat"].get("type", "private")
    
    if chat_type != "private":
        return
        
    text = msg.get("text", "") or ""
    register_user_local(chat_id) # 🌟 Save User locally for Free Broadcasts!

    if is_user_banned(chat_id):
        send_message(chat_id, render_body_text("🚫 <b>You are banned from using this bot!</b>\nIf you think this is a mistake, please contact support."))
        return
    
    # --- REFERRAL FIX: Save inviter BEFORE Force Join ---
    if text.startswith("/start"):
        parts = text.split()
        if len(parts) > 1 and parts[1].isdigit():
            inviter = int(parts[1])
            if inviter != chat_id:
                u_data = _get_local_user(chat_id)
                if not u_data.get("referred_by"):
                    _update_local_user(chat_id, {"referred_by": inviter, "ref_paid": False})
                        
    if not check_force_join(chat_id):
        send_force_join_msg(chat_id)
        return
        
    MAIN_MENU_CMDS = ["GET NUMBER", "Search Number", "TRAFFIC", "Refer", "WITHDRAWAL", "SUPPORT", "Admin Panel", "2FA ONLINE"]
    
    is_main_cmd = False
    if text in MAIN_MENU_CMDS or text.startswith("/start"):
        if chat_id in user_states: user_states.pop(chat_id, None)
        if chat_id in temp_data: temp_data.pop(chat_id, None)
        is_main_cmd = True
    
    if chat_id in user_states and not is_main_cmd:
        state = user_states[chat_id]
        
        # 🌟 Auto Captcha Panel Setup Flow — same sequence as Pix_number_bot_fadrin.py
        if state == "wait_for_cpanel_url" and text:
            if chat_id not in temp_data or "p_data" not in temp_data.get(chat_id, {}):
                user_states.pop(chat_id, None)
                send_message(chat_id, render_body_text("❌ The session has ended. Please try again."))
                return
            login_url = text.strip()
            if not login_url.startswith(("http://", "https://")):
                login_url = "http://" + login_url
            temp_data[chat_id]["p_data"]["login_url"] = login_url
            user_states[chat_id] = "wait_for_cpanel_user"
            send_message(chat_id, render_body_text(
                "2️⃣ <b>Username</b>\n➡️ Enter Panel Username:"
            ), reply_markup=get_cancel_kb())
            return

        elif state == "wait_for_cpanel_user" and text:
            if chat_id not in temp_data or "p_data" not in temp_data.get(chat_id, {}):
                user_states.pop(chat_id, None)
                send_message(chat_id, render_body_text("❌ The session has ended. Please try again."))
                return
            temp_data[chat_id]["p_data"]["username"] = text.strip()
            user_states[chat_id] = "wait_for_cpanel_pass"
            send_message(chat_id, render_body_text(
                "3️⃣ <b>Password</b>\n➡️ Enter Panel Password:"
            ), reply_markup=get_cancel_kb())
            return

        elif state == "wait_for_cpanel_pass" and text:
            if chat_id not in temp_data or "p_data" not in temp_data.get(chat_id, {}):
                user_states.pop(chat_id, None)
                send_message(chat_id, render_body_text("❌ The session has ended. Please try again."))
                return
            temp_data[chat_id]["p_data"]["password"] = text.strip()
            user_states[chat_id] = "wait_for_cpanel_msg_link"
            send_message(chat_id, render_body_text(
                "4️⃣ <b>Message Received URL</b>\n"
                "➡️ Send the link where panel SMS/OTP data is shown:\n"
                "<code>https://example.com/client/SMSCDRStats</code>"
            ), reply_markup=get_cancel_kb())
            return

        elif state == "wait_for_cpanel_msg_link" and text:
            if chat_id not in temp_data or "p_data" not in temp_data.get(chat_id, {}):
                user_states.pop(chat_id, None)
                send_message(chat_id, render_body_text("❌ The session has ended. Please try again."))
                return
            msg_link = text.strip()
            if msg_link.lower() in ("auto", "skip", "none", "-"):
                temp_data[chat_id]["p_data"].pop("msg_link", None)
            else:
                if not msg_link.startswith(("http://", "https://")):
                    msg_link = "http://" + msg_link
                temp_data[chat_id]["p_data"]["msg_link"] = msg_link
            user_states[chat_id] = "wait_for_cpanel_num_col_name"
            send_message(chat_id, render_body_text(
                "5️⃣ <b>Number Column Name</b>\n"
                "➡️ Enter the Number column name, e.g. <code>number</code> or <code>phone</code>:"
            ), reply_markup=get_cancel_kb())
            return

        elif state == "wait_for_cpanel_num_col_name" and text:
            if chat_id not in temp_data or "p_data" not in temp_data.get(chat_id, {}):
                user_states.pop(chat_id, None)
                send_message(chat_id, render_body_text("❌ The session has ended. Please try again."))
                return
            col_name = text.strip()
            if col_name.lower() in ("auto", "skip", "none", "-"):
                temp_data[chat_id]["p_data"].pop("num_col_name", None)
            else:
                temp_data[chat_id]["p_data"]["num_col_name"] = col_name
            user_states[chat_id] = "wait_for_cpanel_num_col_idx"
            send_message(chat_id, render_body_text(
                "6️⃣ <b>Number Column Serial</b>\n"
                "➡️ Enter the visible Number column number, e.g. <code>3</code>:"
            ), reply_markup=get_cancel_kb())
            return

        elif state == "wait_for_cpanel_num_col_idx" and text:
            if chat_id not in temp_data or "p_data" not in temp_data.get(chat_id, {}):
                user_states.pop(chat_id, None)
                send_message(chat_id, render_body_text("❌ The session has ended. Please try again."))
                return
            col_value = text.strip()
            if col_value.lower() in ("auto", "skip", "none", "-"):
                temp_data[chat_id]["p_data"].pop("num_col_idx", None)
            elif col_value.isdigit() and 1 <= int(col_value) <= 100:
                temp_data[chat_id]["p_data"]["num_col_idx"] = int(col_value)
            else:
                send_message(chat_id, render_body_text(
                    "❌ Please enter a valid Number column serial, such as <code>3</code>."
                ), reply_markup=get_cancel_kb())
                return
            user_states[chat_id] = "wait_for_cpanel_msg_col_name"
            send_message(chat_id, render_body_text(
                "7️⃣ <b>Message Column Name</b>\n"
                "➡️ Enter the SMS/Message column name, e.g. <code>message</code> or <code>sms</code>:"
            ), reply_markup=get_cancel_kb())
            return

        elif state == "wait_for_cpanel_msg_col_name" and text:
            if chat_id not in temp_data or "p_data" not in temp_data.get(chat_id, {}):
                user_states.pop(chat_id, None)
                send_message(chat_id, render_body_text("❌ The session has ended. Please try again."))
                return
            col_name = text.strip()
            if col_name.lower() in ("auto", "skip", "none", "-"):
                temp_data[chat_id]["p_data"].pop("msg_col_name", None)
            else:
                temp_data[chat_id]["p_data"]["msg_col_name"] = col_name
            user_states[chat_id] = "wait_for_cpanel_msg_col_idx"
            send_message(chat_id, render_body_text(
                "8️⃣ <b>Message Column Serial</b>\n"
                "➡️ Enter the visible SMS/Message column number, e.g. <code>5</code>:"
            ), reply_markup=get_cancel_kb())
            return

        elif state == "wait_for_cpanel_msg_col_idx" and text:
            if chat_id not in temp_data or "p_data" not in temp_data.get(chat_id, {}):
                user_states.pop(chat_id, None)
                send_message(chat_id, render_body_text("❌ The session has ended. Please try again."))
                return
            col_value = text.strip()
            if col_value.lower() in ("auto", "skip", "none", "-"):
                temp_data[chat_id]["p_data"].pop("msg_col_idx", None)
            elif col_value.isdigit() and 1 <= int(col_value) <= 100:
                temp_data[chat_id]["p_data"]["msg_col_idx"] = int(col_value)
            else:
                send_message(chat_id, render_body_text(
                    "❌ Please enter a valid Message column serial, such as <code>5</code>."
                ), reply_markup=get_cancel_kb())
                return
            temp_data[chat_id]["p_data"]["login_status"] = "⏳ Pending Auto-Login..."
            temp_data[chat_id]["p_data"]["needs_warmup"] = True
            bot_settings["panels"].append(temp_data[chat_id]["p_data"])
            save_local_db()
            # Auto Captcha panel starts with status="ON" — spawn an eager warmup
            new_panel_idx = len(bot_settings["panels"]) - 1
            threading.Thread(target=_eagerly_warmup_panel, args=(new_panel_idx, bot_settings["panels"][-1]), daemon=True).start()

            send_message(chat_id, render_body_text(f"{PEM['ok']} <b>Auto Captcha Panel Added Successfully!</b>\nBot will now automatically login and detect settings in background."), reply_markup=main_menu(chat_id))
            
            msg_id = temp_data[chat_id]["msg_id"]
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": "manage_cpt_panels", "id": "internal"})
            
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return

        # --- User Management Flows ---
        elif state == "wait_for_um_bal_uid" and text:
            target_uid_str = text.strip()
            if not target_uid_str.isdigit():
                send_message(chat_id, render_body_text("❌ Invalid ID! Please send a numeric User ID."), reply_markup=get_cancel_kb())
                return
            target_uid = int(target_uid_str)
            user_data = _get_local_user(target_uid)
            current_bal = user_data.get('balance', 0.0)
            temp_data[chat_id]["target_uid"] = target_uid
            user_states[chat_id] = "wait_for_um_bal_amt"
            send_message(chat_id, render_body_text(f"✅ User found!\n💰 Current Balance: {current_bal} pkr\n\n📝 Send the amount to ADD (e.g. 50) or REMOVE (e.g. -50):"), reply_markup=get_cancel_kb())
            return

        elif state == "wait_for_um_bal_amt" and text:
            try:
                amt = float(text.strip())
                target_uid = temp_data[chat_id]["target_uid"]
                old_bal = _get_local_user(target_uid).get('balance', 0.0)
                update_balance(target_uid, amt)
                new_bal = _get_local_user(target_uid).get('balance', 0.0)
                send_message(chat_id, render_body_text(f"{PEM['ok']} Balance updated!\n{PEM['user']} User: <code>{target_uid}</code>\n💰 Old: {old_bal} pkr → New: {new_bal} pkr"), reply_markup=main_menu(chat_id))
                
                if amt >= 0:
                    notif_text = f"{PEM['gift']} <b>Balance Added!</b>\n➖➖➖➖➖➖➖\n💰 <b>Amount:</b> +{amt} pkr\n💰 <b>New Balance:</b> {new_bal} pkr\n➖➖➖➖➖➖➖\n👨‍⚖️ <b>By Admin</b>"
                else:
                    notif_text = f"{PEM['warn']} <b>Balance Removed!</b>\n➖➖➖➖➖➖➖\n💰 <b>Amount:</b> {amt} pkr\n💰 <b>New Balance:</b> {new_bal} pkr\n➖➖➖➖➖➖➖\n👨‍⚖️ <b>By Admin</b>"
                send_message(target_uid, render_body_text(notif_text))
                user_states.pop(chat_id, None)
                temp_data.pop(chat_id, None)
            except ValueError:
                send_message(chat_id, render_body_text("❌ Invalid amount! Please send a number."), reply_markup=get_cancel_kb())
            return

        elif state == "wait_for_um_ban_uid" and text:
            target_uid_str = text.strip()
            if not target_uid_str.isdigit():
                _err_invalid_id(chat_id)
                return
            target_uid = int(target_uid_str)
            user_data = _get_local_user(target_uid)
            current_status = user_data.get("banned", False)
            new_status = not current_status
            _update_local_user(target_uid, {"banned": new_status})
            
            user_banned_cache[target_uid] = {'banned': new_status, 'time': time.time()}
            
            status_text = "BANNED 🚫" if new_status else "UNBANNED ✅"
            send_message(chat_id, render_body_text(f"✅ User {target_uid} has been {status_text}!"), reply_markup=main_menu(chat_id))
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return

        elif state == "wait_for_um_prof_uid" and text:
            target_uid_str = text.strip()
            if not target_uid_str.isdigit():
                _err_invalid_id(chat_id)
                return
            target_uid = int(target_uid_str)
            data = _get_local_user(target_uid)
            is_verified = True if data.get('total_otps', 0) > 0 else data.get('verified', False)
            prof_text = f"""➖➖➖➖➖➖➖➖
👤 <b>USER PROFILE</b>
➖➖➖➖➖➖➖➖
🆔 ID: <code>{target_uid}</code>
💰 Balance: {data.get('balance', 0.0)} PKR
🤝 Total Refers: {data.get('total_refers', 0)}
🔐 Total OTPs: {data.get('total_otps', 0)}
✅ Verified: {is_verified}
🚫 Banned: {data.get('banned', False)}
➖➖➖➖➖➖➖➖"""
            _reset_btn_counter()
            kb = {"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "user_management", "style": _rs()}]]}
            send_message(chat_id, render_body_text(prof_text), reply_markup=kb)
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return

        # --- Menu Design Flow ---
        elif state == "wait_for_menu_text" and text:
            try:
                menu_key = temp_data[chat_id]["menu_key"]
                formatted_html_text = extract_premium_html(msg)
                
                bot_settings["custom_messages"][menu_key]["text"] = formatted_html_text
                save_local_db()
                
                delete_message(chat_id, msg["message_id"])
                
                preview_text = render_body_text(formatted_html_text)
                success_text = f"{PEM['ok']} <b>Message Body Updated successfully!</b>\n\n🎨 <b>Editing: {menu_key.upper()}</b>\n\nPreview of current Text:\n{preview_text}"
                edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text(success_text), reply_markup=menu_edit_options_keyboard(menu_key))
            except Exception as e:
                send_message(chat_id, render_body_text(f"❌ Error saving text: {e}"))
            finally:
                if chat_id in user_states: user_states.pop(chat_id, None)
                if chat_id in temp_data: temp_data.pop(chat_id, None)
            return
            
        elif state == "wait_for_menu_btn" and text:
            try:
                menu_key = temp_data[chat_id]["menu_key"]
                btn_data = _parse_btn_from_text(text, msg.get("entities", []))
                if btn_data is not None:
                    bot_settings["custom_messages"][menu_key]["buttons"].append(btn_data)
                    save_local_db()
                    delete_message(chat_id, msg["message_id"])
                    edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text(f"{PEM['gear']} <b>Edit Inline Buttons: {menu_key.upper()}</b>"), reply_markup=menu_buttons_list_keyboard(menu_key))
                else:
                    send_message(chat_id, render_body_text(f"{PEM['no']} Invalid format. Use <code>Button Text - https://link.com</code>"))
            except Exception as e:
                logger.warning(f"Error: {e}")
            finally:
                if chat_id in user_states: user_states.pop(chat_id, None)
                if chat_id in temp_data: temp_data.pop(chat_id, None)
            return

        elif state == "wait_for_emoji_extract":
            # Extract exactly one Telegram Premium/Custom Emoji from the message entity.
            entities = msg.get("entities") or msg.get("caption_entities") or []
            source_text = msg.get("text", msg.get("caption", "")) or ""
            custom_emoji_id = None
            emoji_text = ""
            for ent in entities:
                if ent.get("type") == "custom_emoji" and ent.get("custom_emoji_id"):
                    custom_emoji_id = str(ent.get("custom_emoji_id"))
                    offset = int(ent.get("offset", 0))
                    length = int(ent.get("length", 0))
                    try:
                        raw = source_text.encode("utf-16-le")
                        emoji_text = raw[offset * 2:(offset + length) * 2].decode("utf-16-le")
                    except Exception:
                        emoji_text = ""
                    break
            if custom_emoji_id:
                old = temp_data.get(chat_id, {})
                temp_data[chat_id] = {
                    "msg_id": old.get("msg_id"),
                    "emoji_id": custom_emoji_id,
                    "emoji_char": emoji_text or "✨",
                }
                user_states[chat_id] = "wait_for_emoji_details"
                send_message(chat_id, render_body_text(
                    f"{PEM['ok']} Premium Emoji ID পাওয়া গেছে: <code>{html.escape(custom_emoji_id)}</code>\n\n"
                    "এই Emoji কোথায় save করবেন নির্বাচন করুন:"
                ), reply_markup=emoji_save_type_keyboard())
            else:
                send_message(chat_id, render_body_text(
                    f"{PEM['no']} কোনো Premium/Custom Emoji পাওয়া যায়নি। Telegram Premium Custom Emoji পাঠান।"
                ), reply_markup=get_cancel_kb())
            return

        elif state == "wait_for_emoji_details" and text:
            parts = [part.strip() for part in text.split("|")]
            mode = parts[0].upper() if parts else ""
            emoji_id = temp_data.get(chat_id, {}).get("emoji_id")
            emoji_char = temp_data.get(chat_id, {}).get("emoji_char", "✨")
            saved = False
            result_text = ""
            if not emoji_id:
                user_states.pop(chat_id, None)
                temp_data.pop(chat_id, None)
                send_message(chat_id, render_body_text(f"{PEM['no']} Emoji session expired. Please try again."), reply_markup=emoji_settings_keyboard())
                return
            if mode == "FLAG" and len(parts) == 4 and parts[1].isdigit() and parts[2]:
                code, iso, name = parts[1], parts[2].upper(), parts[3]
                if code in bot_settings.get("premium_flags", {}):
                    result_text = f"{PEM['warn']} Flag code <code>{html.escape(code)}</code> already exists. Existing emoji was kept."
                else:
                    bot_settings.setdefault("premium_flags", {})[code] = {
                        "char": emoji_char, "iso": iso, "name": name, "id": emoji_id
                    }
                    saved = True
                    result_text = f"{PEM['ok']} <b>Flag Emoji Saved</b>\n\nCode: <code>{html.escape(code)}</code>\nName: <b>{html.escape(name)}</b>"
            elif mode == "APP" and len(parts) == 2 and parts[1]:
                name = parts[1]
                app_key = name.upper()
                if app_key in bot_settings.get("premium_apps", {}):
                    result_text = f"{PEM['warn']} App <code>{html.escape(name)}</code> already exists. Existing emoji was kept."
                else:
                    bot_settings.setdefault("premium_apps", {})[app_key] = {
                        "char": emoji_char, "id": emoji_id, "name": name.title()
                    }
                    saved = True
                    result_text = f"{PEM['ok']} <b>App Emoji Saved</b>\n\nName: <b>{html.escape(name)}</b>"
            else:
                send_message(chat_id, render_body_text(
                    f"{PEM['no']} Invalid format.\n\n"
                    "Flag: <code>FLAG | 92 | PAK | Pakistan</code>\n"
                    "App: <code>APP | WhatsApp</code>"
                ), reply_markup=get_cancel_kb())
                return
            if saved:
                save_local_db()
            send_message(chat_id, render_body_text(result_text), reply_markup=emoji_settings_keyboard())
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return

        elif state == "wait_for_test_service" and text:
            temp_data[chat_id]["service"] = text.strip()
            user_states[chat_id] = "wait_for_test_number"
            send_message(chat_id, render_body_text("📝 Send the Number (e.g. +8801712345678):"), reply_markup=get_cancel_kb())
            return
            
        elif state == "wait_for_test_number" and text:
            temp_data[chat_id]["number"] = text.strip()
            user_states[chat_id] = "wait_for_test_otp"
            send_message(chat_id, render_body_text("📝 Send the OTP (e.g. 556677):"), reply_markup=get_cancel_kb())
            return
            
        elif state == "wait_for_test_otp" and text:
            temp_data[chat_id]["otp"] = text.strip()
            user_states[chat_id] = "wait_for_test_lang"
            send_message(chat_id, render_body_text("📝 Send the Language (e.g. EN, AR):"), reply_markup=get_cancel_kb())
            return
            
        elif state == "wait_for_test_lang" and text:
            lang = text.strip().upper()
            if not lang.startswith("#"):
                lang = "#" + lang
                
            srv = temp_data[chat_id]["service"]
            num = temp_data[chat_id]["number"]
            otp = temp_data[chat_id]["otp"]
            
            masked = mask_number(num)
            prem_flag_html = get_flag_info_html(num)
            char, iso = get_flag_and_code(num)
            app_full_name, prem_app_html = get_service_info_html(srv)
            
            msg_text = format_otp_group_message(srv, prem_app_html, prem_flag_html, num, otp, lang)
            
            for fw in bot_settings.get("fw_groups", []):
                _reset_btn_counter()
                kb = build_otp_group_keyboard(otp)
                send_message(fw["chat_id"], msg_text, reply_markup={"inline_keyboard": kb})
                
            send_message(chat_id, render_body_text(f"{PEM['ok']} Test message formatted and sent to all Forward Groups!"), reply_markup=main_menu(chat_id))
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return


        elif state in ["wait_for_flag_txt", "wait_for_app_txt"] and "document" in msg:
            doc = msg["document"]
            content = _download_telegram_txt_document(chat_id, doc)
            if content is None:
                return
            
            mode = "flags" if state == "wait_for_flag_txt" else "apps"
            count = 0
            
            if mode == "flags":
                for line in content.splitlines():
                    json_match = re.search(r'(\{.*\})', line)
                    if json_match:
                        try:
                            data = json.loads(json_match.group(1))
                            char = data.get("emoji")
                            eid = data.get("id")
                            
                            prefix_str = line[:json_match.start()].strip()
                            code_match = re.search(r'\((\d+)\)', prefix_str)
                            iso_match = re.search(r'\(([A-Za-z]+)\)', prefix_str)
                            
                            if code_match and iso_match and char and eid:
                                code = code_match.group(1)
                                iso = iso_match.group(1).upper()
                                name = prefix_str.replace(f"({code})", "").replace(f"({iso_match.group(1)})", "").replace(char, "").strip()
                                bot_settings["premium_flags"][code] = {"char": char, "iso": iso, "name": name, "id": eid}
                                count += 1
                        except Exception as e:
                            logger.warning(f"Error: {e}")
            else:
                for line in content.splitlines():
                    json_match = re.search(r'(\{.*\})', line)
                    if json_match:
                        try:
                            data = json.loads(json_match.group(1))
                            char = data.get("emoji")
                            eid = data.get("id")
                            
                            name_part = line[:json_match.start()].strip()
                            name = name_part.replace(char, '').strip() if char else name_part
                            
                            if char and eid and name:
                                bot_settings["premium_apps"][name.upper()] = {"char": char, "id": eid, "name": name}
                                count += 1
                        except Exception as e:
                            logger.warning(f"Error: {e}")
            
            save_local_db()
            send_message(chat_id, render_body_text(f"{PEM['ok']} Successfully loaded {count} Emojis!"), reply_markup=emoji_settings_keyboard())
            user_states.pop(chat_id, None)
            if chat_id in temp_data: temp_data.pop(chat_id, None)
            return

        elif state == "wait_for_broadcast":
            msg_id = msg["message_id"]
            send_message(chat_id, render_body_text(f"{PEM['ok']} Broadcast started..."))
            threading.Thread(target=broadcast_copymessage, args=(chat_id, msg_id)).start()
            user_states.pop(chat_id, None)
            if chat_id in temp_data: temp_data.pop(chat_id, None)
            return

        elif state == "wait_for_backup_zip" and "document" in msg:
            if chat_id != OWNER_ID:
                user_states.pop(chat_id, None); return
            doc = msg["document"]
            if not str(doc.get("file_name", "")).lower().endswith(".zip"):
                send_message(chat_id, render_body_text("❌ Only send a <b>.zip</b> backup file."))
                return
            send_message(chat_id, render_body_text("⏳ Restoring, please wait..."))
            try:
                fi = tg_session.get(f"{BASE_URL}/getFile?file_id={doc['file_id']}", timeout=20).json()
                fpath = fi.get("result", {}).get("file_path")
                if not fpath:
                    send_message(chat_id, render_body_text("❌ File could not be downloaded. Please try again."))
                    user_states.pop(chat_id, None); return
                content = tg_session.get(f"{FILE_URL}{fpath}", timeout=60).content
                ok_r, info = restore_backup_zip(content)
            except Exception as e:
                ok_r, info = False, str(e)
            user_states.pop(chat_id, None)
            if ok_r:
                send_message(chat_id, render_body_text(
                    f"{PEM['ok']} <b>RESTORE COMPLETE!</b>\n\n{html.escape(info)}\n\n"
                    f"👤 Users: <b>{len(local_users_db)}</b>\n"
                    f"📁 Ranges: <b>{len(number_batches)}</b>\n\n"
                    f"<i>No restart needed — the data has been loaded live.</i>"))
            else:
                send_message(chat_id, render_body_text(f"❌ <b>Restore Failed!</b>\n{html.escape(str(info))}"))
            return

        elif state == "wait_for_txt" and "document" in msg:
            if not is_admin(chat_id):     # 🔒 only admins can add ranges/numbers
                send_message(chat_id, render_body_text("❌ Only ADMIN can add numbers!"))
                user_states.pop(chat_id, None); temp_data.pop(chat_id, None); return
            doc = msg["document"]
            file_content = _download_telegram_txt_document(chat_id, doc)
            if file_content is None:
                return

            temp_data[chat_id] = {"numbers": file_content.splitlines(), "filename": doc["file_name"]}
            user_states[chat_id] = "wait_for_service"
            send_message(chat_id, render_body_text(f"{PEM['ok']} File received.\n\n📌 Enter the service name (e.g., WHATSAPP):"), reply_markup=get_cancel_kb())
            return

        elif state == "wait_for_service" and text:
            if not is_admin(chat_id):
                user_states.pop(chat_id, None); temp_data.pop(chat_id, None); return
            temp_data[chat_id]["service"] = text.upper()
            user_states[chat_id] = "wait_for_country"
            send_message(chat_id, render_body_text(f"{PEM['ok']} Service set.\n\n🌍 Enter the country name (e.g., YEMEN):"), reply_markup=get_cancel_kb())
            return

        elif state == "wait_for_country" and text:
            if not is_admin(chat_id):
                user_states.pop(chat_id, None); temp_data.pop(chat_id, None); return
            temp_data[chat_id]["country"] = text.upper()
            user_states[chat_id] = "wait_for_range_rate"
            rate_txt = (f"{PEM['ok']} Country set.\n\n"
                        f"💰 <b>Send the per-OTP rate for this range:</b>\n"
                        f"• For PKR just the number — <code>2</code> or <code>0.50 PKR</code>\n"
                        f"• For USD — <code>$0.05</code> or <code>0.05 USD</code>\n\n"
                        f"💵 Today's rate: 1 USD = {bot_settings.get('usd_rate', DEFAULT_USD_RATE)} pkr\n"
                        f"<i>(To skip send 0 — then the default reward will apply)</i>")
            send_message(chat_id, render_body_text(rate_txt), reply_markup=get_cancel_kb())
            return

        elif state == "wait_for_range_rate" and text:
            if not is_admin(chat_id):
                user_states.pop(chat_id, None); temp_data.pop(chat_id, None); return
            ok_rate, rate_pkr, rate_cur, rate_val = parse_money_input(text)
            if not ok_rate:
                send_message(chat_id, render_body_text(
                    "❌ Wrong rate!\n\n"
                    "📝 Send like this: <code>2</code> (PKR) or <code>$0.05</code> (USD):"),
                    reply_markup=get_cancel_kb())
                return
            country = temp_data[chat_id]["country"]
            service = temp_data[chat_id]["service"]
            raw_numbers = temp_data[chat_id]["numbers"]
            
            clean_nums = []
            for num in raw_numbers:
                num = num.strip()
                if num:
                    if not num.startswith('+'): num = '+' + num
                    clean_nums.append(num)
            
            batch_id = str(uuid.uuid4())[:8]
            number_batches[batch_id] = {"filename": temp_data[chat_id]["filename"], "service": service, "country": country,
                                        "rate_pkr": (rate_pkr if rate_pkr > 0 else None),
                                        "rate_cur": rate_cur, "rate_input": rate_val,
                                        "added_by": chat_id, "added_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                        "numbers": [{"num": n, "shares": 0, "used_by": []} for n in clean_nums]}
            with _stats_lock:
                total_uploaded_stats += len(clean_nums)
            save_local_db()
            
            if not clean_nums:
                send_message(chat_id, render_body_text(f"{PEM['no']} No valid numbers found in file!"), reply_markup=main_menu(chat_id))
                user_states.pop(chat_id, None); temp_data.pop(chat_id, None); return
            app_full_name, prem_app_html = get_service_info_html(service)
            prem_flag_html = get_flag_info_html(clean_nums[0]) if clean_nums else f"{PEM['world']} "
            
            rate_line = fmt_dual(rate_pkr) if rate_pkr > 0 else "Default reward"
            broadcast_txt = f"➖➖➖➖➖➖➖➖\n《 NEW NUMBERS 》\n➖➖➖➖➖➖➖➖\n{prem_flag_html} {country} {prem_app_html} {service}\n➖➖➖➖➖➖➖➖\n📤 Total Added: <b>{len(clean_nums)}</b>\n💰 Per OTP: <b>{rate_line}</b>\n➖➖➖➖➖➖➖➖\nUse /start to get your numbers!"
            broadcast_txt = render_body_text(broadcast_txt)
            
            send_message(chat_id, render_body_text(
                f"{PEM['ok']} Range added!\n\n"
                f"📁 <b>Range:</b> {temp_data[chat_id]['filename']}\n"
                f"🌍 <b>Country:</b> {country}   📱 <b>Service:</b> {service}\n"
                f"🔢 <b>Numbers:</b> {len(clean_nums)}\n"
                f"💰 <b>Per OTP rate:</b> {rate_line}\n\n"
                f"Starting broadcast..."))
            
            threading.Thread(target=broadcast_text_message, args=(broadcast_txt,)).start()
            
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return

        elif state == "wait_for_add_nexa_key" and text:
            bot_settings["nexa_keys"].append(text.strip())
            save_local_db()
            _service_warmup_needed["nexa"] = True  # Skip old OTPs for newly added key
            delete_message(chat_id, msg["message_id"])
            edit_message(chat_id, _td(chat_id, "msg_id", msg["message_id"]), render_body_text(f"✅ Nexa API Key Added! Total Keys: {len(bot_settings.get('nexa_keys', []))}"), reply_markup=_panel_control_keyboard("Nexa"))
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return

        elif state == "wait_for_add_sc" and text:
            code = text.strip().replace("+", "")
            if "nexa_search_countries" not in bot_settings: bot_settings["nexa_search_countries"] = []
            if code not in bot_settings["nexa_search_countries"]:
                bot_settings["nexa_search_countries"].append(code)
            save_local_db()
            delete_message(chat_id, msg["message_id"])
            _show_panel_search_countries("nexa", chat_id, _td(chat_id, "msg_id", msg["message_id"]))
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return

        elif state == "wait_nx_srv_name" and text:
            srv = text.strip().upper()
            if "nexa_services" not in bot_settings: bot_settings["nexa_services"] = {}
            if srv not in bot_settings["nexa_services"]: bot_settings["nexa_services"][srv] = {}
            save_local_db()
            delete_message(chat_id, msg["message_id"])
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": temp_data[chat_id]["msg_id"]}, "data": "manage_nexa_srv", "id": "internal"})
            user_states.pop(chat_id, None)
            if chat_id in temp_data: temp_data.pop(chat_id, None)
            return

        elif state == "wait_nx_cnt_name" and text:
            cnt = text.strip()
            srv = temp_data.get(chat_id, {}).get("srv")
            if not srv or srv not in bot_settings.get("nexa_services", {}):
                send_message(chat_id, render_body_text("❌ The session has expired. Please start again."))
                user_states.pop(chat_id, None); temp_data.pop(chat_id, None)
                return
            if cnt not in bot_settings["nexa_services"][srv]: bot_settings["nexa_services"][srv][cnt] = []
            save_local_db()
            delete_message(chat_id, msg["message_id"])
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": temp_data[chat_id]["msg_id"]}, "data": f"nx_srv_{srv}", "id": "internal"})
            user_states.pop(chat_id, None)
            if chat_id in temp_data: temp_data.pop(chat_id, None)
            return

        elif state == "wait_nx_addr" and text:
            srv = temp_data.get(chat_id, {}).get("srv")
            cnt = temp_data.get(chat_id, {}).get("cnt")
            if not srv or not cnt or srv not in bot_settings.get("nexa_services", {}):
                send_message(chat_id, render_body_text("❌ The session has expired. Please start again."))
                user_states.pop(chat_id, None); temp_data.pop(chat_id, None)
                return
            new_range = text.strip().replace("+", "")
            
            if new_range not in bot_settings["nexa_services"][srv][cnt]:
                bot_settings["nexa_services"][srv][cnt].append(new_range)
                
                if "nexa_search_countries" not in bot_settings:
                    bot_settings["nexa_search_countries"] = []
                nexa_prefix = new_range.replace("X", "").replace("x", "")
                if nexa_prefix and nexa_prefix not in bot_settings["nexa_search_countries"]:
                    bot_settings["nexa_search_countries"].append(nexa_prefix)
                    
                save_local_db()
                
            delete_message(chat_id, msg["message_id"])
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": temp_data[chat_id]["msg_id"]}, "data": f"nx_cnt_{srv}_{cnt}", "id": "internal"})
            user_states.pop(chat_id, None)
            if chat_id in temp_data: temp_data.pop(chat_id, None)
            return

        # VoltX state handlers
        elif state == "wait_for_add_voltx_key" and text:
            bot_settings["voltx_keys"].append(text.strip())
            save_local_db()
            _service_warmup_needed["voltx"] = True  # Skip old OTPs for newly added key
            delete_message(chat_id, msg["message_id"])
            edit_message(chat_id, _td(chat_id, "msg_id", msg["message_id"]), render_body_text(f"✅ VoltX API Key Added! Total Keys: {len(bot_settings.get('voltx_keys', []))}"), reply_markup=_panel_control_keyboard("VoltX"))
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return

        elif state == "wait_vx_srv_name" and text:
            srv = text.strip().upper()
            if "voltx_services" not in bot_settings: bot_settings["voltx_services"] = {}
            if srv not in bot_settings["voltx_services"]: bot_settings["voltx_services"][srv] = {}
            save_local_db()
            delete_message(chat_id, msg["message_id"])
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": temp_data[chat_id]["msg_id"]}, "data": "manage_voltx_srv", "id": "internal"})
            user_states.pop(chat_id, None)
            if chat_id in temp_data: temp_data.pop(chat_id, None)
            return

        elif state == "wait_vx_cnt_name" and text:
            cnt = text.strip()
            srv = temp_data[chat_id]["srv"]
            if cnt not in bot_settings["voltx_services"][srv]: bot_settings["voltx_services"][srv][cnt] = []
            save_local_db()
            delete_message(chat_id, msg["message_id"])
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": temp_data[chat_id]["msg_id"]}, "data": f"vx_srv_{srv}", "id": "internal"})
            user_states.pop(chat_id, None)
            if chat_id in temp_data: temp_data.pop(chat_id, None)
            return

        elif state == "wait_vx_addr" and text:
            srv, cnt = temp_data[chat_id]["srv"], temp_data[chat_id]["cnt"]
            new_range = text.strip()
            if new_range not in bot_settings["voltx_services"][srv][cnt]:
                bot_settings["voltx_services"][srv][cnt].append(new_range)
                if "voltx_search_countries" not in bot_settings:
                    bot_settings["voltx_search_countries"] = []
                prefix = new_range.replace("X", "").replace("x", "")
                if prefix and prefix not in bot_settings["voltx_search_countries"]:
                    bot_settings["voltx_search_countries"].append(prefix)
                save_local_db()
            delete_message(chat_id, msg["message_id"])
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": temp_data[chat_id]["msg_id"]}, "data": f"vx_cnt_{srv}_{cnt}", "id": "internal"})
            user_states.pop(chat_id, None)
            if chat_id in temp_data: temp_data.pop(chat_id, None)
            return

        elif state == "wait_for_add_vxsc" and text:
            code = text.strip().replace("+", "")
            if "voltx_search_countries" not in bot_settings: bot_settings["voltx_search_countries"] = []
            if code not in bot_settings["voltx_search_countries"]:
                bot_settings["voltx_search_countries"].append(code)
            save_local_db()
            delete_message(chat_id, msg["message_id"])
            _show_panel_search_countries("voltx", chat_id, _td(chat_id, "msg_id", msg["message_id"]))
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return

        # Stex state handlers
        elif state == "wait_for_add_stex_key" and text:
            bot_settings["stex_keys"].append(text.strip())
            save_local_db()
            _service_warmup_needed["stex"] = True  # Skip old OTPs for newly added key
            delete_message(chat_id, msg["message_id"])
            edit_message(chat_id, _td(chat_id, "msg_id", msg["message_id"]), render_body_text(f"✅ Stex API Key Added! Total Keys: {len(bot_settings.get('stex_keys', []))}"), reply_markup=_panel_control_keyboard("Stex"))
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return

        elif state == "wait_stx_srv_name" and text:
            srv = text.strip().upper()
            if "stex_services" not in bot_settings: bot_settings["stex_services"] = {}
            if srv not in bot_settings["stex_services"]: bot_settings["stex_services"][srv] = {}
            save_local_db()
            delete_message(chat_id, msg["message_id"])
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": temp_data[chat_id]["msg_id"]}, "data": "manage_stex_srv", "id": "internal"})
            user_states.pop(chat_id, None)
            if chat_id in temp_data: temp_data.pop(chat_id, None)
            return

        elif state == "wait_stx_cnt_name" and text:
            cnt = text.strip()
            srv = temp_data[chat_id]["srv"]
            if cnt not in bot_settings["stex_services"][srv]: bot_settings["stex_services"][srv][cnt] = []
            save_local_db()
            delete_message(chat_id, msg["message_id"])
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": temp_data[chat_id]["msg_id"]}, "data": f"stx_srv_{srv}", "id": "internal"})
            user_states.pop(chat_id, None)
            if chat_id in temp_data: temp_data.pop(chat_id, None)
            return

        elif state == "wait_stx_addr" and text:
            srv, cnt = temp_data[chat_id]["srv"], temp_data[chat_id]["cnt"]
            new_range = text.strip()
            if new_range not in bot_settings["stex_services"][srv][cnt]:
                bot_settings["stex_services"][srv][cnt].append(new_range)
                if "stex_search_countries" not in bot_settings:
                    bot_settings["stex_search_countries"] = []
                prefix = new_range.replace("X", "").replace("x", "")
                if prefix and prefix not in bot_settings["stex_search_countries"]:
                    bot_settings["stex_search_countries"].append(prefix)
                save_local_db()
            delete_message(chat_id, msg["message_id"])
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": temp_data[chat_id]["msg_id"]}, "data": f"stx_cnt_{srv}_{cnt}", "id": "internal"})
            user_states.pop(chat_id, None)
            if chat_id in temp_data: temp_data.pop(chat_id, None)
            return

        elif state == "wait_for_add_stxsc" and text:
            code = text.strip().replace("+", "")
            if "stex_search_countries" not in bot_settings: bot_settings["stex_search_countries"] = []
            if code not in bot_settings["stex_search_countries"]:
                bot_settings["stex_search_countries"].append(code)
            save_local_db()
            delete_message(chat_id, msg["message_id"])
            _show_panel_search_countries("stex", chat_id, _td(chat_id, "msg_id", msg["message_id"]))
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return

        elif state == "wait_for_add_wm" and text:
            new_m = clean_method_name(text)
            if not new_m:
                send_message(chat_id, render_body_text(
                    "❌ This method is not allowed!\n\n"
                    f"✅ Only these 4 can be added:\n<b>{allowed_methods_text()}</b>\n\n"
                    "📝 Send again:"), reply_markup=get_cancel_kb())
                return
            if new_m in bot_settings["w_methods"]:
                send_message(chat_id, render_body_text(f"⚠️ <b>{new_m}</b> is already added!"))
            else:
                bot_settings["w_methods"].append(new_m)
            save_local_db()
            delete_message(chat_id, msg["message_id"])
            edit_message(chat_id, _td(chat_id, "msg_id", msg["message_id"]), render_body_text("💳 <b>WITHDRAWAL METHODS</b>\n\nManage your withdrawal methods below:"), reply_markup=w_methods_keyboard())
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return

        elif state == "wait_for_add_fj" and text:
            raw_input = text.strip()
            # Handle private invite links (https://t.me/+xxx or https://t.me/joinchat/xxx)
            if "t.me/+" in raw_input or "t.me/joinchat/" in raw_input:
                # For private invite links, we need the numeric chat_id
                # Admin must also provide numeric ID for private chats
                delete_message(chat_id, msg["message_id"])
                edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text("⚠️ <b>Private invite link detected!</b>\n\nSend a numeric ID for the private channel/group (e.g. <code>-1001234567890</code>)\n\nHow to find the ID:\n1. Forward any message from the Channel/Group\n2. Forward it to @userinfobot\n3. It will give you the ID"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_fj", "style": _rs()}]]})
                return
            parsed_id = parse_chat_id(raw_input)
            detected = auto_detect_chat(parsed_id)
            if detected:
                bot_settings["fj_channels"].append(detected)
                save_local_db()
                delete_message(chat_id, msg["message_id"])
                type_label = "Channel" if detected["type"] == "channel" else "Group"
                priv_label = "Private" if detected["is_private"] else "Public"
                edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text(f"✅ <b>Successfully Added!</b>\n\n{type_label} | {priv_label}\n📌 Title: <b>{detected['title']}</b>\n🆔 ID: <code>{detected['chat_id']}</code>\n🔗 Link: {detected.get('invite_link', 'N/A')}"), reply_markup=fj_settings_keyboard())
            else:
                delete_message(chat_id, msg["message_id"])
                edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text("❌ <b>Error!</b> Bot is not an admin in this channel/group or the ID is invalid.\n\nMake sure:\n1. Add the bot to the channel/group\n2. Make the bot an admin\n3. Then try again"), reply_markup={"inline_keyboard": [[{"text": "Try Again", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "add_fj", "style": _rs()}, {"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_fj", "style": _rs()}]]})
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return
            
        elif state == "wait_for_add_adm" and text:
            raw_admin_id = text.strip()
            result_text = ""
            if not raw_admin_id.isdigit():
                result_text = "❌ Invalid User ID. Please send numbers only."
            else:
                new_admin_id = int(raw_admin_id)
                if new_admin_id == OWNER_ID:
                    result_text = "⚠️ Owner ID is already protected as an admin."
                elif new_admin_id in bot_settings.get("admins", []):
                    result_text = "⚠️ This User ID is already an admin."
                else:
                    bot_settings.setdefault("admins", []).append(new_admin_id)
                    save_local_db()
                    result_text = f"✅ Admin added successfully: <code>{new_admin_id}</code>"
            delete_message(chat_id, msg["message_id"])
            panel_msg_id = _td(chat_id, "msg_id", msg["message_id"])
            edit_message(chat_id, panel_msg_id, render_body_text(
                f"{result_text}\n\n👥 <b>ADMIN MANAGEMENT</b>\nManage your bot admins below:"
            ), reply_markup=admin_settings_keyboard())
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return

        elif state == "wait_for_add_fw_id" and text:
            bot_settings["fw_groups"].append({"chat_id": text.strip(), "buttons": []})
            save_local_db()
            delete_message(chat_id, msg["message_id"])
            edit_message(chat_id, _td(chat_id, "msg_id", msg["message_id"]), render_body_text("🛡 <b>OTP GROUP MANAGEMENT</b>\nManage settings below:"), reply_markup=otp_groups_list_keyboard())
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return
            
        elif state == "wait_for_add_fw_btn" and text:
            fw_idx = _td(chat_id, "fw_idx", -1)
            if fw_idx < 0 or fw_idx >= len(bot_settings.get("fw_groups", [])):
                send_message(chat_id, render_body_text("❌ Group not found!"))
                user_states.pop(chat_id, None); temp_data.pop(chat_id, None); return
            btn_data = _parse_btn_from_text(text, msg.get("entities", []))
            if btn_data is not None:
                bot_settings["fw_groups"][fw_idx]["buttons"].append(btn_data)
            save_local_db()
            delete_message(chat_id, msg["message_id"])
            edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text(f"🛡 <b>Manage Group:</b> {bot_settings['fw_groups'][fw_idx]['chat_id']}"), reply_markup=specific_fw_group_keyboard(fw_idx))
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return
            
        elif state == "wait_for_otp_link" and text:
            bot_settings["otp_link"] = text.strip()
            save_local_db()
            delete_message(chat_id, msg["message_id"])
            edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text("🛡 <b>OTP GROUP MANAGEMENT</b>\nManage settings below:"), reply_markup=otp_groups_list_keyboard())
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return

        # ===== OTP Forward Manager states =====
        elif state == "wait_for_channel_link" and text:
            bot_settings.setdefault("otp_forward", {})["channel_link"] = text.strip()
            save_local_db()
            delete_message(chat_id, msg["message_id"])
            edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text("✅ Channel Link updated!"), reply_markup=otp_forward_manager_keyboard())
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return
        elif state == "wait_for_number_link" and text:
            bot_settings.setdefault("otp_forward", {})["number_link"] = text.strip()
            save_local_db()
            delete_message(chat_id, msg["message_id"])
            edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text("✅ Number Link updated!"), reply_markup=otp_forward_manager_keyboard())
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return
        elif state in ("wait_for_otp_msg_emoji", "wait_for_otp_btn_emoji"):
            emoji_id = None
            emoji_char = ""
            source = msg.get("text", msg.get("caption", "")) or text or ""
            entities = msg.get("entities") or msg.get("caption_entities") or []
            for ent in entities:
                if ent.get("type") == "custom_emoji" and ent.get("custom_emoji_id"):
                    emoji_id = str(ent.get("custom_emoji_id"))
                    offset = int(ent.get("offset", 0))
                    length = int(ent.get("length", 0))
                    raw = source.encode("utf-16-le")
                    try:
                        emoji_char = raw[offset * 2:(offset + length) * 2].decode("utf-16-le")
                    except Exception:
                        emoji_char = ""
                    break

            target = temp_data.get(chat_id, {}).get("emoji_target", "")
            if not emoji_id or not target:
                send_message(chat_id, render_body_text("❌ একটি Premium/Custom Emoji পাঠান। সাধারণ emoji দিলে Custom Emoji ID পাওয়া যাবে না।"), reply_markup=get_cancel_kb())
                return

            tag = f'<tg-emoji emoji-id="{html.escape(emoji_id)}">{html.escape(emoji_char or "✨")}</tg-emoji>'
            forward = bot_settings.setdefault("otp_forward", {})
            if state == "wait_for_otp_msg_emoji":
                forward.setdefault("emoji_positions", {})[target] = tag
                title = target.replace("before_", "").replace("_", " ").title()
                success = f"✅ OTP Group Message Emoji updated!\n\nPosition: <b>{title}</b>\nEmoji ID: <code>{html.escape(emoji_id)}</code>"
                kb = otp_message_emoji_keyboard()
            else:
                forward.setdefault("button_emojis", {})[target] = emoji_id
                title = target.replace("_", " ").title()
                success = f"✅ OTP Group Button Emoji updated!\n\nButton: <b>{title}</b>\nEmoji ID: <code>{html.escape(emoji_id)}</code>"
                kb = otp_button_emoji_keyboard()
            save_local_db()
            delete_message(chat_id, msg["message_id"])
            edit_message(chat_id, temp_data[chat_id]["msg_id"], render_body_text(success), reply_markup=kb)
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return

        elif state == "wait_for_panel_name" and text:
            p_name = text.strip()
            t_key = temp_data[chat_id].get("add_type", "api")
            msg_id = temp_data[chat_id]["msg_id"]
            delete_message(chat_id, msg["message_id"])
            
            if t_key == "logc":
                user_states[chat_id] = "wait_for_cpanel_url"
                temp_data[chat_id] = {"msg_id": msg_id, "p_data": {
                    "name": p_name, "type": "Auto Captcha Panel", "status": "ON", "records": 0, "login_status": "⏳ Pending First Login"
                }}
                edit_message(chat_id, msg_id, render_body_text("1️⃣ <b>Login URL</b>\n➡️ Enter the Panel Login Link:"), reply_markup=get_cancel_kb())
                return
            elif t_key == "sock":
                user_states[chat_id] = "wait_for_new_sock_url"
                temp_data[chat_id] = {"msg_id": msg_id, "p_data": {
                    "name": p_name, "type": "Live Socket Panel", "status": "ON",
                    "ws_url": "", "login_status": "⏳ Connecting..."
                }}
                edit_message(chat_id, msg_id, render_body_text(
                    f"1️⃣ <b>WebSocket URL</b>\n\n"
                    f"➡️ Send the full WebSocket link for <b>{html.escape(p_name)}</b> (including token):\n"
                    f"<code>wss://ivasms.qzz.io:2087/socket.io/?token=...&user=...&EIO=4&transport=websocket</code>\n\n"
                    f"<i>Website/panel of WebSocket URL usually developer/support from is read.</i>"),
                    reply_markup=get_cancel_kb())
                return
            else:
                # 📡 API Panel wizard: Name -> API URL -> Token -> auto connect
                user_states[chat_id] = "wait_for_new_p_url"
                temp_data[chat_id] = {"msg_id": msg_id, "p_data": {
                    "name": p_name, "type": "API Panel", "status": "ON",
                    "api_url": "", "token": "", "records": 0, "needs_warmup": True
                }}
                edit_message(chat_id, msg_id, render_body_text(
                    f"1️⃣ <b>API URL</b>\n\n"
                    f"➡️ Send the API link for <b>{html.escape(p_name)}</b>:\n"
                    f"<code>http://51.77.216.195/crapi/mait/viewstats</code>\n\n"
                    f"<i>Do not include the token now — it will be asked in the next step.\n"
                    f"if your complete link with the token is available, send it.</i>"),
                    reply_markup=get_cancel_kb())
                return

        elif state == "wait_for_new_sock_url" and text:
            ws_url = text.strip()
            p_data = temp_data[chat_id].get("p_data", {})
            msg_id = _td(chat_id, "msg_id", msg["message_id"])
            p_data["ws_url"] = ws_url
            delete_message(chat_id, msg["message_id"])

            bot_settings["panels"].append(p_data)
            new_idx = len(bot_settings["panels"]) - 1
            save_local_db()

            edit_message(chat_id, msg_id, render_body_text(
                "⏳ <b>Connecting...</b>\n<i>Checking the WebSocket handshake.</i>"))

            ok, info = quick_socket_test(ws_url)
            if ok:
                p_data["status"] = "ON"
                p_data["login_status"] = "✅ Connected & Listening"
                save_local_db()
                _start_socket_panel_thread(new_idx)
                res_txt = (f"✅ <b>SOCKET PANEL CONNECTED!</b>\n"
                           f"━━━━━━━━━━━━\n"
                           f"📡 <b>Name:</b> {html.escape(str(p_data.get('name','')))}\n"
                           f"🔌 <b>Status:</b> ON — Live OTP catching started\n"
                           f"<i>{html.escape(info)}</i>")
            else:
                p_data["status"] = "OFF"
                p_data["login_status"] = "❌ Connection Failed"
                save_local_db()
                res_txt = (f"⚠️ <b>Panel was added, but did not connect.</b>\n"
                           f"━━━━━━━━━━━━\n"
                           f"<b>reason:</b> {html.escape(str(info)[:250])}\n\n"
                           f"<i>WebSocket URL check by Test Connection again chalayein.</i>")
            send_message(chat_id, render_body_text(res_txt))
            _show_panel_cfg(chat_id, msg_id, new_idx)
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return

        elif state == "wait_for_new_p_url" and text:
            p_url = text.strip()
            if not p_url.startswith("http"):
                p_url = "http://" + p_url
            temp_data[chat_id]["p_data"]["api_url"] = p_url
            msg_id = _td(chat_id, "msg_id", msg["message_id"])
            delete_message(chat_id, msg["message_id"])
            user_states[chat_id] = "wait_for_new_p_token"
            edit_message(chat_id, msg_id, render_body_text(
                f"2️⃣ <b>API TOKEN</b>\n\n"
                f"✅ URL saved: <code>{html.escape(p_url)}</code>\n\n"
                f"➡️ Now send your <b>token</b>:\n"
                f"<code>hYuwoskkkaw28kssx==</code>\n\n"
                f"<i>Token URL in hi laga was is? To <b>none</b> bhej dein.</i>"),
                reply_markup=get_cancel_kb())
            return

        elif state == "wait_for_new_p_token" and text:
            p_data = temp_data[chat_id].get("p_data", {})
            msg_id = _td(chat_id, "msg_id", msg["message_id"])
            tok = text.strip()
            p_data["token"] = "" if tok.lower() in ("none", "no", "-") else tok
            delete_message(chat_id, msg["message_id"])

            bot_settings["panels"].append(p_data)
            new_idx = len(bot_settings["panels"]) - 1
            save_local_db()

            edit_message(chat_id, msg_id, render_body_text(
                "⏳ <b>Connecting...</b>\n<i>Checking data from panel.</i>"))

            ok, cnt, err, samples = quick_panel_test(p_data)
            if ok:
                p_data["status"] = "ON"
                save_local_db()
                res_txt = (f"✅ <b>PANEL CONNECTED!</b>\n"
                           f"━━━━━━━━━━━━\n"
                           f"📡 <b>Name:</b> {html.escape(str(p_data.get('name','')))}\n"
                           f"📥 <b>Records found:</b> {cnt}\n"
                           f"🟢 <b>Status:</b> ON — OTP has started arriving\n")
                for sm in samples:
                    res_txt += (f"━━━━━━━━━━━━\n"
                                f"📱 <code>{html.escape(str(sm.get('number','')))}</code>\n"
                                f"🔐 OTP: <code>{html.escape(str(sm.get('otp','') or '-'))}</code>\n")
            else:
                p_data["status"] = "OFF"
                save_local_db()
                res_txt = (f"⚠️ <b>Panel was added, but did not connect.</b>\n"
                           f"━━━━━━━━━━━━\n"
                           f"<b>reason:</b> {html.escape(str(err)[:250])}\n\n"
                           f"<i>URL / Token check by Test Connection again chalayein.\n"
                           f"correct hone on panel to Turn ON do dein.</i>")
            send_message(chat_id, render_body_text(res_txt))
            _show_panel_cfg(chat_id, msg_id, new_idx)
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return

        elif state == "wait_for_p_wsurl" and text:
            _save_panel_field(chat_id, msg, "ws_url", text.strip())
            if _td_has(chat_id, "p_idx"):
                _pidx = _td(chat_id, "p_idx", -1)
                if _pidx >= 0:
                    bot_settings["panels"][_pidx]["login_status"] = "🔄 Reconnecting..."
                    save_local_db()
            return

        elif state == "wait_for_p_api" and text:
            _save_panel_field(chat_id, msg, "api_url", text.strip())
            return

        elif state == "wait_for_p_tok" and text:
            _save_panel_field(chat_id, msg, "token", text.strip())
            return

        elif state == "wait_for_p_tokheader" and text:
            idx = _td(chat_id, "p_idx", -1)
            if idx < 0 or idx >= len(bot_settings["panels"]):
                _err_panel_gone(chat_id)
            else:
                val = text.strip()
                if val.lower() == "none":
                    bot_settings["panels"][idx].pop("token_header", None)
                else:
                    bot_settings["panels"][idx]["token_header"] = val
                save_local_db()
                delete_message(chat_id, msg["message_id"])
                _show_panel_cfg(chat_id, _td(chat_id, "msg_id", msg["message_id"]), idx)
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return

        elif state == "wait_for_p_fapi" and text:
            _save_panel_field(chat_id, msg, "full_api_url", text.strip())
            return

        elif state == "wait_for_p_rec" and text:
            if text.isdigit():
                idx = temp_data[chat_id]["p_idx"]
                if idx < 0 or idx >= len(bot_settings["panels"]):
                    _err_panel_gone(chat_id)
                else:
                    bot_settings["panels"][idx]["records"] = int(text)
                    save_local_db()
                    delete_message(chat_id, msg["message_id"])
                    _show_panel_cfg(chat_id, temp_data[chat_id]["msg_id"], idx)
                user_states.pop(chat_id, None)
                temp_data.pop(chat_id, None)
            else:
                send_message(chat_id, render_body_text("❌ Please enter a valid number! Try again."))
            return

        elif state == "set_currently":
            msg_id = _td(chat_id, "msg_id", msg["message_id"])
            key = _td(chat_id, "key", "")
            if not key:
                user_states.pop(chat_id, None); temp_data.pop(chat_id, None); return
            try:
                if key in ["min_withdraw", "otp_reward", "refer_reward", "usd_rate"]: bot_settings[key] = float(text)
                elif key in ["cooldown", "num_req", "num_share"]: bot_settings[key] = int(text)
                else: bot_settings[key] = text
                save_local_db()
                delete_message(chat_id, msg["message_id"])
                _show_currently_panel(chat_id, msg_id)
            except Exception as e:
                delete_message(chat_id, msg["message_id"])
                _show_currently_panel(chat_id, msg_id, "❌ Invalid value!")
            user_states.pop(chat_id, None)
            temp_data.pop(chat_id, None)
            return

        elif state == "wait_for_search" and text:
            query = text.strip().replace("+", "")
            if not query.isdigit() or len(query) < 3 or len(query) > 9:
                send_message(chat_id, render_body_text("❌ Please enter a valid 3 to 9 digit number!"))
                return
                
            wait_msg = send_message(chat_id, render_body_text("⌛ <i>Processing... Finding Number...</i>"))
            wait_msg_id = wait_msg.get("result", {}).get("message_id") if isinstance(wait_msg, dict) else None
            
            # 🌟 1. First search number from Local (for any country)
            found_indices = _search_and_recycle_local(query, chat_id)

            fetched_nums = []
            if not found_indices:
                # 🌟 2. If not found in Local, then check if can get from Nexa/VoltX/Stex
                allowed_countries = (
                    bot_settings.get("nexa_search_countries", []) +
                    bot_settings.get("voltx_search_countries", []) +
                    bot_settings.get("stex_search_countries", [])
                )
                
                is_nexa_allowed = False
                if not allowed_countries:
                    is_nexa_allowed = True
                else:
                    clean_allowed = [c.replace("X", "").replace("x", "") for c in allowed_countries]
                    if any(query.startswith(c) or c.startswith(query) for c in clean_allowed if c):
                        is_nexa_allowed = True
                    
                if not is_nexa_allowed:
                    if wait_msg_id: delete_message(chat_id, wait_msg_id)
                    send_message(chat_id, render_body_text("❌ <b>This country code is not available for search.</b>\n\nPlease try a different number prefix."), reply_markup=main_menu(chat_id))
                    user_states.pop(chat_id, None)
                    if chat_id in temp_data: temp_data.pop(chat_id, None)
                    return
                    
                if wait_msg_id: edit_message(chat_id, wait_msg_id, render_body_text("⌛ <i>Processing... Finding Number via API...</i>"))
                # 🌟 Try all panels with strict isolation (Nexa → VoltX → Stex)
                _api_num, _api_panel = _fetch_number_via_panels(query, chat_id)
                if _api_num:
                    fetched_nums.append(_api_num)
                    save_local_db()
                else:
                    if wait_msg_id: delete_message(chat_id, wait_msg_id)
                    send_message(chat_id, render_body_text("❌ Number out of stock!"), reply_markup=main_menu(chat_id))
                    user_states.pop(chat_id, None)
                    if chat_id in temp_data: temp_data.pop(chat_id, None)
                    return
            else:
                random.shuffle(found_indices)
                for b_id, idx in found_indices:
                    if len(fetched_nums) >= bot_settings.get("num_req", 1): break
                    if b_id not in number_batches: continue
                    nb = number_batches[b_id]["numbers"]
                    if idx < 0 or idx >= len(nb): continue
                    n_obj = nb[idx]
                    num_str = n_obj["num"]
                    
                    fetched_nums.append(num_str)
                    
                    n_obj["shares"] += 1
                    n_obj["used_by"].append(chat_id)
                    with _stats_lock:
                        total_assigned_stats += 1
                    
                    if n_obj["shares"] >= bot_settings.get("num_share", 1):
                        if num_str not in used_numbers_list:
                            used_numbers_list.append(num_str)
                save_local_db()
                
            if wait_msg_id: edit_message(chat_id, wait_msg_id, render_body_text("✅ Number Found!"))
            _sess_msg = {"nums": fetched_nums, "service": "", "country": "",
                         "ctx": "search", "query": query,
                         "cc_codes": _build_cc_codes(fetched_nums), "cc_state": [True] * len(fetched_nums),
                         "msg_id": wait_msg_id or 0}
            user_active_sessions[chat_id] = _sess_msg
            kb = _rebuild_num_kb(chat_id)
            num_text = render_body_text(_build_num_text(chat_id))
            if wait_msg_id:
                try:
                    edit_message(chat_id, wait_msg_id, num_text, reply_markup={"inline_keyboard": kb})
                except Exception:
                    msg_res = send_message(chat_id, num_text, reply_markup={"inline_keyboard": kb})
                    if msg_res and msg_res.get("ok") and msg_res.get("result"):
                        user_active_sessions[chat_id]["msg_id"] = msg_res["result"]["message_id"]
            else:
                msg_res = send_message(chat_id, num_text, reply_markup={"inline_keyboard": kb})
                if msg_res and msg_res.get("ok") and msg_res.get("result"):
                    user_active_sessions[chat_id]["msg_id"] = msg_res["result"]["message_id"]
            if chat_id in user_states: user_states.pop(chat_id, None)
            if chat_id in temp_data: temp_data.pop(chat_id, None)
            return
            
        elif state == "wait_for_withdraw_amount" and text:
            msg_id_to_edit = temp_data[chat_id].get("msg_id")
            try:
                amount = float(text.strip())
                bal = _td(chat_id, "balance", 0.0)
                min_w = bot_settings.get('min_withdraw', 100.0)
                
                if amount < min_w:
                    if msg_id_to_edit: edit_message(chat_id, msg_id_to_edit, render_body_text(f"❌ Minimum withdrawal is {min_w} PKR!\n💰 Balance: {bal} PKR\n\n📝 Enter again:"), reply_markup=get_cancel_kb())
                    return
                if amount > bal:
                    if msg_id_to_edit: edit_message(chat_id, msg_id_to_edit, render_body_text(f"❌ You don't have enough balance!\n💰 Balance: {bal} PKR\n\n📝 Enter again:"), reply_markup=get_cancel_kb())
                    return
                    
                temp_data[chat_id]["amount"] = amount
                user_states[chat_id] = "wait_for_withdraw_number"
                if msg_id_to_edit:
                    _mm = temp_data[chat_id]['method']
                    _amt_line = (f"✅ Amount: {fmt_money(amount)}"
                                 + (f"  →  <b>{fmt_usd(pkr_to_usd(amount))} USDT</b>" if is_crypto_method(_mm) else f" (~{fmt_usd(pkr_to_usd(amount))})"))
                    edit_message(chat_id, msg_id_to_edit, render_body_text(_amt_line + "\n\n" + pak_account_prompt(_mm)), reply_markup=get_cancel_kb())
            except ValueError:
                if msg_id_to_edit: edit_message(chat_id, msg_id_to_edit, render_body_text("❌ Invalid amount!\n\n📝 Please send a valid number:"), reply_markup=get_cancel_kb())
            return
            
        elif state == "wait_for_2fa_name" and text:
            msg_id_to_edit = temp_data.get(chat_id, {}).get("msg_id")
            delete_message(chat_id, msg.get("message_id"))

            if not msg_id_to_edit:
                send_message(chat_id, render_body_text("❌ Error: Message not found. Try again."))
                user_states.pop(chat_id, None)
                if chat_id in temp_data: temp_data.pop(chat_id, None)
                return

            name = text.strip()[:30]
            temp_data[chat_id]["2fa_name"] = name
            user_states[chat_id] = "wait_for_2fa_key"

            ask_key_txt = (
                f"━━━━━━━━━━━━━━━\n"
                f"《 🔑 <b>ENTER 2FA KEY</b> 》\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📛 <b>NAME:</b> {name}\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📝 Now send your <b>2FA Secret Key</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"💡 <b>Where can I find the secret key?</b>\n"
                f"App/website on 2FA setup of time that <b>32-digit key</b> or <b>QR code</b> of below likha is, that copy by send.\n"
                f"━━━━━━━━━━━━━━━"
            )
            _reset_btn_counter()
            cancel_kb = {"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "back_to_2fa_name", "style": _rs()}]]}
            edit_message(chat_id, msg_id_to_edit, render_body_text(ask_key_txt), reply_markup=cancel_kb)
            return

        elif state == "wait_for_2fa_key" and text:
            msg_id_to_edit = temp_data.get(chat_id, {}).get("msg_id")
            delete_message(chat_id, msg.get("message_id"))

            if not msg_id_to_edit:
                send_message(chat_id, render_body_text("❌ Error: Message not found. Try again."))
                user_states.pop(chat_id, None)
                if chat_id in temp_data: temp_data.pop(chat_id, None)
                return

            entry_name = temp_data.get(chat_id, {}).get("2fa_name", "My Account")

            try:
                secret = text.strip().replace(" ", "")
                totp = pyotp.TOTP(secret)
                code = totp.now()
                remaining_time = 30 - (int(time.time()) % 30)

                # Save to user's 2FA list
                if chat_id not in user_2fa_saved:
                    user_2fa_saved[chat_id] = []
                # Avoid duplicate keys
                existing_keys = [e["key"] for e in user_2fa_saved[chat_id]]
                if secret not in existing_keys:
                    user_2fa_saved[chat_id].append({"name": entry_name, "key": secret})
                    _save_2fa_saved()  # FIX: persist new 2FA entry to disk

                success_txt = _build_2fa_code_txt(entry_name, code, remaining_time)
                kb = _build_2fa_code_kb(code, secret)

                edit_message(chat_id, msg_id_to_edit, render_body_text(success_txt), reply_markup={"inline_keyboard": kb})
                user_states.pop(chat_id, None)
                if chat_id in temp_data: temp_data.pop(chat_id, None)
            except Exception as e:
                logger.warning(f"2FA key validation error: {e}")
                error_txt = (
                    f"━━━━━━━━━━━━━━━\n"
                    f"《 🔑 <b>ENTER 2FA KEY</b> 》\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"📛 <b>NAME:</b> {entry_name}\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"📝 <b>Send the 2FA Secret Key</b>\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"❌ <b>Invalid Secret Key! Please try again.</b>\n"
                    f"━━━━━━━━━━━━━━━"
                )
                _reset_btn_counter()
                cancel_kb = {"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "back_to_2fa_name", "style": _rs()}]]}
                edit_message(chat_id, msg_id_to_edit, render_body_text(error_txt), reply_markup=cancel_kb)
            return

        elif state == "wait_for_withdraw_number":
            # 🇵🇰 Account / USDT address validation
            if not _td_has(chat_id, "method", "amount"):
                send_message(chat_id, render_body_text("❌ Session expired. Please start withdrawal again."))
                user_states.pop(chat_id, None); temp_data.pop(chat_id, None); return
            msg_id_to_edit = _td(chat_id, "msg_id")
            method = clean_method_name(_td(chat_id, "method", "Easypaisa")) or _td(chat_id, "method", "Easypaisa")
            amount = _td(chat_id, "amount", 0)
            ok_acc, clean_acc, acc_err = validate_pak_account(method, text)
            if not ok_acc:
                if msg_id_to_edit:
                    edit_message(chat_id, msg_id_to_edit, render_body_text(acc_err), reply_markup=get_cancel_kb())
                else:
                    send_message(chat_id, render_body_text(acc_err), reply_markup=get_cancel_kb())
                return
            temp_data[chat_id]["number"] = clean_acc

            # 🪙 No account title needed for crypto — direct request
            if is_crypto_method(method):
                submit_withdrawal_request(chat_id, msg, method, amount, clean_acc, "-", msg_id_to_edit)
                return

            user_states[chat_id] = "wait_for_withdraw_title"
            ask_title = (f"✅ Account: <code>{clean_acc}</code>\n\n"
                         f"👤 Now send the <b>Account Title</b> (the name under which the {method} account is registered):\n"
                         "<i>Example: Muhammad Ali</i>")
            if msg_id_to_edit:
                edit_message(chat_id, msg_id_to_edit, render_body_text(ask_title), reply_markup=get_cancel_kb())
            else:
                send_message(chat_id, render_body_text(ask_title), reply_markup=get_cancel_kb())
            return

        elif state == "wait_for_withdraw_title":
            if not _td_has(chat_id, "method", "amount", "number"):
                send_message(chat_id, render_body_text("❌ Session expired. Please start withdrawal again."))
                user_states.pop(chat_id, None); temp_data.pop(chat_id, None); return
            msg_id_to_edit = _td(chat_id, "msg_id")
            method = _td(chat_id, "method", "Easypaisa")
            amount = _td(chat_id, "amount", 0)
            number = _td(chat_id, "number", "")
            acc_title = str(text or "").strip()[:60]
            if len(acc_title) < 3:
                warn_t = "❌ Account title is too short!\n\n📝 Send the full name (example: Muhammad Ali):"
                if msg_id_to_edit:
                    edit_message(chat_id, msg_id_to_edit, render_body_text(warn_t), reply_markup=get_cancel_kb())
                else:
                    send_message(chat_id, render_body_text(warn_t), reply_markup=get_cancel_kb())
                return
            submit_withdrawal_request(chat_id, msg, method, amount, number, acc_title, msg_id_to_edit)
            return

    # --- Regular Commands ---
    if text.startswith("/backup") and chat_id == OWNER_ID:
        send_message(chat_id, render_body_text("⏳ Backup is being created..."))
        send_backup_to(chat_id)
        return

    elif text.startswith("/restore") and chat_id == OWNER_ID:
        user_states[chat_id] = "wait_for_backup_zip"
        send_message(chat_id, render_body_text(
            "♻️ <b>RESTORE</b>\n\n📤 Send the backup <b>.zip</b> file."), reply_markup=get_cancel_kb())
        return

    elif text.startswith("/start"):
        first_name = msg.get("from", {}).get("first_name", "User")
        _welcome_user(chat_id, first_name)
            
    elif text == "TRAFFIC":
        txt, markup = build_traffic_ui()
        send_message(chat_id, txt, reply_markup=markup)
        
    elif text == "Refer":
        u_data = get_user(chat_id)
        ref_link = f"https://t.me/{BOT_USERNAME.lstrip('@').strip()}?start={chat_id}"
        c_msg = bot_settings["custom_messages"].get("refer", {})
        
        raw_txt = c_msg.get("text", f"{PEM['gift']} Refer").replace("{ref_link}", ref_link).replace("{total_ref}", str(u_data.get('total_refers', 0))).replace("{ref_reward}", str(bot_settings['refer_reward']))
        txt = render_body_text(raw_txt)
        
        _reset_btn_counter()
        kb = [[{"text": "COPY LINK", "icon_custom_emoji_id": "5192739271886282680", "copy_text": {"text": ref_link}, "style": _rs()}]]
        _append_custom_btns(kb, c_msg)
        kb.append([{"text": "CLOSE", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": _rs()}])
        
        send_message(chat_id, txt, reply_markup={"inline_keyboard": kb})

    elif text == "WITHDRAWAL":
        if not bot_settings["withdraw_on"]:
            send_message(chat_id, render_body_text(f"{PEM['no']} Withdrawals are currently disabled."))
            return
        
        u_data = get_user(chat_id)
        bal = u_data.get('balance', 0.0)
        
        c_msg = bot_settings["custom_messages"].get("withdrawal", {})
        raw_txt = c_msg.get("text", "Withdrawal").replace("{bal_usd}", fmt_usd(pkr_to_usd(bal))).replace("{usd_rate}", str(bot_settings.get("usd_rate", DEFAULT_USD_RATE))).replace("{bal}", str(bal)).replace("{total_otp}", str(u_data.get('total_otps', 0))).replace("{total_ref}", str(u_data.get('total_refers', 0))).replace("{min_w}", str(bot_settings['min_withdraw']))
        txt = render_body_text(raw_txt)
        
        _reset_btn_counter()
        kb = []
        for mi, m in enumerate(bot_settings["w_methods"]):
            cm = clean_method_name(m)
            if not cm:      # allowed 4 of besides some also menu me not will appear
                continue
            kb.append([{"text": cm, "icon_custom_emoji_id": "5190899075968441286", "callback_data": f"sel_wm_{cm}", "style": _rs()}])
        
        _append_custom_btns(kb, c_msg)
        _add_close_btn(kb)
        send_message(chat_id, txt, reply_markup={"inline_keyboard": kb})

    elif text == "Admin Panel" and is_admin(chat_id):
        send_message(chat_id, get_admin_text(), reply_markup=admin_panel_keyboard())

    elif text == "GET NUMBER":
        all_services, txt, kb = _build_services_keyboard("get_number")
        if not all_services:
            send_message(chat_id, render_body_text(f"{PEM['no']} <b>No Service Available Right Now</b>"), reply_markup=main_menu(chat_id))
        else:
            send_message(chat_id, txt, reply_markup={"inline_keyboard": kb})

    elif text == "Search Number":
        user_states[chat_id] = "wait_for_search"
        c_msg = bot_settings["custom_messages"].get("search_number", {})
        txt = render_body_text(c_msg.get("text", f"{PEM['num']} Search Number"))
        _reset_btn_counter()
        kb = []
        _append_custom_btns(kb, c_msg)
        _add_close_btn(kb)
        send_message(chat_id, txt, reply_markup={"inline_keyboard": kb})

    elif text == "2FA ONLINE" or text == "🔐 2FA ONLINE":
        _show_2fa_menu(chat_id)

    elif text == "SUPPORT":
        c_msg = bot_settings["custom_messages"].get("support", {})
        txt = render_body_text(c_msg.get("text", f"{PEM['msg']} Support"))
        if not txt.strip(): txt = render_body_text(f"{PEM['msg']} Support")
        _reset_btn_counter()
        kb = []
        sup_link = SUPPORT_URL
        if sup_link:
            kb.append([{"text": "Contact support", "icon_custom_emoji_id": "5337302974806922068", "url": sup_link, "style": _rs()}])
        for b in c_msg.get("buttons", []):
            b_copy = b.copy()
            b_copy["style"] = _rs()
            kb.append([b_copy])
        _add_close_btn(kb)
        send_message(chat_id, txt, reply_markup={"inline_keyboard": kb} if kb else None)

def _build_cc_codes(nums):
    """Build a parallel list of country-code strings for each number in nums."""
    codes = []
    for num in nums:
        _, iso, _ = get_flag_info_from_num(num)
        codes.append(_get_cc_from_iso(iso) or _get_cc_from_num(num))
    return codes


def _rebuild_num_kb(chat_id):
    """Rebuild the number-display inline keyboard from user_active_sessions, honouring cc_state."""
    session = user_active_sessions.get(chat_id, {})
    nums      = session.get("nums", [])
    service   = session.get("service", "")
    country   = session.get("country", "")
    ctx       = session.get("ctx", "regular")
    cc_codes  = session.get("cc_codes", [])
    cc_state  = session.get("cc_state", [True] * len(nums))
    query     = session.get("query", "")

    _reset_btn_counter()
    kb = []

    # ── number rows ────────────────────────────────────────────────
    any_cc_added = False
    has_any_cc   = False
    for i, num in enumerate(nums):
        raw = str(num).lstrip("+")
        _, iso, flag_eid = get_flag_info_from_num(raw)
        flag_emoji_id = flag_eid or "5780471598922337683"
        cc    = cc_codes[i] if i < len(cc_codes) else None
        added = cc_state[i] if i < len(cc_state) else False

        if cc:
            has_any_cc = True
        if added and cc:
            any_cc_added = True

        # Strip any existing CC from raw so we never get double-prepend
        local_raw = raw[len(cc):] if (cc and raw.startswith(str(cc))) else raw

        if added and cc:
            display_num = f"+{cc}{local_raw}"
        else:
            display_num = local_raw  # no + when CC not added

        kb.append([{"text": display_num, "icon_custom_emoji_id": flag_emoji_id,
                    "copy_text": {"text": display_num}, "style": _rs()}])

    # ── single CC toggle button below ALL numbers ───────────────────
    if has_any_cc:
        if any_cc_added:
            kb.append([{"text": "Remove country code", "icon_custom_emoji_id": "6206108815075579644",
                        "callback_data": "rem_cc_all", "style": _rs()}])
        else:
            kb.append([{"text": "Add country code", "icon_custom_emoji_id": "6206375377925839184",
                        "callback_data": "add_cc_all", "style": _rs()}])

    # ── action row ─────────────────────────────────────────────────
    if ctx == "regular":
        change_cb  = f"c_n_{service}_{country}"
        c_msg_key  = "get_number"
        last_btn_meta = {"text": "Back", "icon_custom_emoji_id": "5267490665117275176",
                         "callback_data": f"g_s_{service}"}
    else:  # search
        change_cb  = f"c_n_s_{query}_{service or ''}"
        c_msg_key  = "search_number"
        last_btn_meta = {"text": "Close", "icon_custom_emoji_id": "5420130255174145507",
                         "callback_data": "close_msg"}

    kb.append([
        {"text": "Change Number", "icon_custom_emoji_id": "5420155432272438703",
         "callback_data": change_cb, "style": _rs()},
        {"text": "OTP Group", "icon_custom_emoji_id": "5190447043545438788",
         "url": bot_settings.get("otp_link", ""), "style": _rs()}
    ])
    _append_custom_btns(kb, bot_settings["custom_messages"].get(c_msg_key, {}))
    # Assign style AFTER Change Number & OTP Group so visual order matches color rotation
    last_btn = {**last_btn_meta, "style": _rs()}
    kb.append([last_btn])

    return kb

def _build_num_text(chat_id):
    """Number display message body: Country + Waiting for OTP (premium emoji, no numbers in text)."""
    session = user_active_sessions.get(chat_id, {})
    nums = session.get("nums", [])

    if not nums:
        return "📱 Number Ready"

    first_raw = str(nums[0]).lstrip("+")
    _, iso, _ = get_flag_info_from_num(first_raw)
    flag_html = get_flag_info_html(first_raw)

    # Country full name from premium_flags
    c_name = iso
    for _code, _fdata in bot_settings.get("premium_flags", {}).items():
        if _fdata.get("iso") == iso:
            c_name = _fdata.get("name", iso)
            break

    world_pem = PEM.get("world", "🌐")
    wait_pem  = '<tg-emoji emoji-id="6264896248659056036">🔄</tg-emoji>'

    return (
        f"{world_pem} <b>Country:</b> {flag_html} <b>{c_name} ({iso})</b>\n"
        f"\n"
        f"{wait_pem} <b>Waiting for OTP</b>"
    )

def expire_previous_number(chat_id):
    if chat_id in user_active_sessions:
        prev_data = user_active_sessions[chat_id]
        prev_msg_id = prev_data["msg_id"]
        nums = prev_data["nums"]
        
        # Remove from ALL panel systems so no more messages go to inbox
        for num in nums:
            if num in nexa_assigned_numbers:
                del nexa_assigned_numbers[num]
            if num in voltx_assigned_numbers:
                del voltx_assigned_numbers[num]
            if num in stex_assigned_numbers:
                del stex_assigned_numbers[num]
        save_local_db()
        
        # Edit previous message and add Expired button
        _reset_btn_counter()
        kb = [[{"text": "Number Expired", "icon_custom_emoji_id": "5336997731481193790", "callback_data": "ignore", "style": _rs()}]]
        try:
            edit_message(chat_id, prev_msg_id, render_body_text(f"{PEM['no']} <b>Number Expired</b>"), reply_markup={"inline_keyboard": kb})
        except Exception as e:
            logger.warning(f"Error expiring number message: {e}")
        del user_active_sessions[chat_id]

# ==========================================
# Callback Query Handler
# ==========================================
def handle_callback(call):
    try:
        _handle_callback_inner(call)
    except Exception as e:
        # Always answer callback to stop button loading even on error
        try: answer_callback(call.get("id", ""), f"⚠️ Error: {str(e)[:40]}")
        except Exception as answer_err:
            logger.warning(f"Error: {answer_err}")
        logger.warning(f"Callback error ({call.get('data','')}): {e}")

def _safe_int(val, default=-1):
    """Safe int conversion — returns default on error."""
    try:
        return int(val)
    except (ValueError, IndexError, TypeError):
        return default

def _td(chat_id, key, default=None):
    """Safe temp_data access — returns default if missing."""
    return temp_data.get(chat_id, {}).get(key, default)

def _td_has(chat_id, *keys):
    """Check temp_data has chat_id and all given keys."""
    d = temp_data.get(chat_id, {})
    return all(k in d for k in keys)


def _withdrawal_group_ids():
    """Return only the original default withdrawal group."""
    value = str(bot_settings.get("w_group") or "").strip()
    return [value] if value else []


def submit_withdrawal_request(chat_id, msg, method, amount, number, acc_title, msg_id_to_edit=None):
    """Create withdrawal request — single flow for both PKR wallet and USDT."""
    method = clean_method_name(method) or method
    crypto = is_crypto_method(method)
    usd_amt = pkr_to_usd(amount)
    req_id = f"W_{str(uuid.uuid4())[:6].upper()}"

    first_name = msg.get("from", {}).get("first_name", "User")
    last_name = msg.get("from", {}).get("last_name", "")
    full_name = f"{first_name} {last_name}".strip()

    update_balance(chat_id, -amount)
    pending_withdrawals[req_id] = {"user_id": chat_id, "amount": amount, "usd_amount": usd_amt,
                                   "method": method, "number": number, "full_name": full_name,
                                   "acc_title": acc_title, "currency": method_currency(method)}
    _save_local_withdrawal(req_id, {"user_id": str(chat_id), "amount": amount, "usd_amount": usd_amt,
                                    "method": method, "number": number, "acc_title": acc_title,
                                    "currency": method_currency(method), "status": "pending"})

    if crypto:
        pay_line = (f"🪙 <b>PAY:</b> <b>{fmt_usd(usd_amt)} USDT</b> ({method.split()[-1]})\n"
                    f"💳 <b>BALANCE CUT:</b> {fmt_money(amount)}\n"
                    f"🔗 <b>ADDRESS:</b> <code>{number}</code>")
    else:
        pay_line = (f"💳 <b>PAY:</b> <b>{fmt_money(amount)}</b> (~{fmt_usd(usd_amt)})\n"
                    f"🏦 <b>METHOD:</b> {method}\n"
                    f"📱 <b>ACCOUNT:</b> <code>{number}</code>\n"
                    f"👤 <b>TITLE:</b> <code>{acc_title}</code>")

    admin_msg = (f"🎙 <b>NEW WITHDRAWAL REQUEST</b>\n\n"
                 f"👤 <b>USER:</b> <a href='tg://user?id={chat_id}'>{full_name}</a>\n"
                 f"{pay_line}\n\n"
                 f"🧾 <b>REQ ID:</b> {req_id}\n👨‍⚖️ <b>PROCESSED BY ADMIN</b>")
    _reset_btn_counter()
    wd_kb = {"inline_keyboard": [[
        {"text": "APPROVE", "icon_custom_emoji_id": "5352694861990501856", "callback_data": f"wapp_{req_id}", "style": _rs()},
        {"text": "REJECT", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"wrej_{req_id}", "style": _rs()}]]}
    rendered_admin_msg = render_body_text(admin_msg)

    # Privacy: owner/admin DMs receive the full account number; withdrawal
    # The original w_group receives only a masked copy.
    masked_number = mask_number(number, user_id=chat_id) if len(str(number)) >= 7 else str(number)
    if crypto:
        group_pay_line = (f"🪙 <b>PAY:</b> <b>{fmt_usd(usd_amt)} USDT</b> ({method.split()[-1]})\n"
                          f"💳 <b>BALANCE CUT:</b> {fmt_money(amount)}\n"
                          f"🔗 <b>ADDRESS:</b> <code>{masked_number}</code>")
    else:
        group_pay_line = (f"💳 <b>PAY:</b> <b>{fmt_money(amount)}</b> (~{fmt_usd(usd_amt)})\n"
                          f"🏦 <b>METHOD:</b> {method}\n"
                          f"📱 <b>ACCOUNT:</b> <code>{masked_number}</code>\n"
                          f"👤 <b>TITLE:</b> <code>{acc_title}</code>")
    group_msg = (f"🎙 <b>NEW WITHDRAWAL REQUEST</b>\n\n"
                 f"👤 <b>USER:</b> <a href='tg://user?id={chat_id}'>{html.escape(str(full_name))}</a>\n"
                 f"{group_pay_line}\n\n"
                 f"🧾 <b>REQ ID:</b> {req_id}\n👨‍⚖️ <b>PROCESSED BY ADMIN</b>")
    rendered_group_msg = render_body_text(group_msg)

    sent_messages = []
    for group_id in _withdrawal_group_ids():
        try:
            res = send_message(group_id, rendered_group_msg, reply_markup=wd_kb)
            if res.get("ok") and res.get("result") and "message_id" in res["result"]:
                sent_messages.append({"chat_id": group_id, "message_id": res["result"]["message_id"], "is_group": True})
            else:
                for adm_id in bot_settings.get("admins", []):
                    try:
                        send_message(adm_id, render_body_text(
                            f"⚠️ Sending message to W.GROUP (<code>{html.escape(str(group_id))}</code>) failed! Check the Group ID."))
                    except Exception as e:
                        logger.warning(f"Error: {e}")
        except Exception as e:
            logger.warning(f"Error: {e}")

    for adm_id in bot_settings.get("admins", []):
        if adm_id != chat_id:
            try:
                res = send_message(adm_id, rendered_admin_msg, reply_markup=wd_kb)
                if res.get("ok") and res.get("result") and "message_id" in res["result"]:
                    sent_messages.append({"chat_id": adm_id, "message_id": res["result"]["message_id"], "is_group": False})
            except Exception as e:
                logger.warning(f"Error: {e}")
    pending_withdrawals[req_id]["sent_messages"] = sent_messages

    _reset_btn_counter()
    kb = {"inline_keyboard": [[{"text": "Close", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": _rs()}]]}
    if crypto:
        got_line = (f"🪙 <b>You get:</b> {fmt_usd(usd_amt)} USDT\n"
                    f"💰 <b>Deducted:</b> {fmt_money(amount)}\n"
                    f"🔗 <b>Address:</b> <code>{number}</code>")
    else:
        got_line = (f"💰 <b>Amount:</b> {fmt_money(amount)}\n"
                    f"📱 <b>Account:</b> <code>{number}</code>\n"
                    f"👤 <b>Title:</b> {acc_title}")
    success_text = (f"{PEM['ok']} Your withdrawal request has been submitted!\n\n"
                    f"🧾 <b>Req ID:</b> {req_id}\n"
                    f"🏦 <b>Method:</b> {method}\n"
                    f"{got_line}\n"
                    f"━━━━━━━━━━━━\n{DEV_CREDIT_HTML}")

    if msg_id_to_edit:
        edit_message(chat_id, msg_id_to_edit, render_body_text(success_text), reply_markup=kb)
    else:
        send_message(chat_id, render_body_text(success_text), reply_markup=kb)

    user_states.pop(chat_id, None)
    temp_data.pop(chat_id, None)


def _handle_callback_inner(call):
    global total_assigned_stats
    chat_id = call["message"]["chat"]["id"]
    chat_type = call["message"]["chat"].get("type", "private")
    data = call.get("data", "")

    # 🌟 Button Loading Fix: Give Response to Telegram immediately when button pressed, so button does not get stuck!
    # ✅ FIX: Skip auto-answer when: recursive internal call, or handler calls answer_callback explicitly with text/show_alert
    _skip_auto_answer = (
        call.get("id") == "internal" or
        data.startswith(("test_p_conn_", "c_n_", "g_c_")) or
        data in {"toggle_nexa", "toggle_voltx", "toggle_stex", "check_fj"} or
        data.startswith(("del_b_", "del_nxa_", "del_sc_", "del_vxsc_", "del_vx_",
                         "del_stxsc_", "del_stx_", "del_adm_", "del_fwbtn_", "del_fw_",
                         "del_2fa_", "del_fj_", "del_wm_",
                         "nx_dr_", "vx_dr_", "stx_dr_", "wapp_", "wrej_"))
    )
    if not _skip_auto_answer:
        try: threading.Thread(target=answer_callback, args=(call["id"],)).start()
        except Exception as e:
            logger.warning(f"Error: {e}")

    if chat_type != "private" and not (data.startswith("wapp_") or data.startswith("wrej_")):
        return

    msg_id = call["message"]["message_id"]

    if chat_type == "private":
        if is_user_banned(chat_id):
            answer_callback(call["id"], "🚫 You are banned from using this bot!", show_alert=True)
            return

        if not check_force_join(chat_id) and data != "check_fj":
            send_force_join_msg(chat_id)
            return

    if data == "check_fj":
        if check_force_join(chat_id):
            # FIX: Immediately "answer" the callback — otherwise the button
            # on loading-spinner animation khatam hone until (3-4 sec) atka
            # Previously, an impatient user could tap repeatedly and start
            # multiple animations, causing the message to appear in different places
            # and partially render. The spinner now stops immediately.
            answer_callback(call["id"], "✅ Verified! Starting...")
            delete_message(chat_id, msg_id)
            first_name = call.get("from", {}).get("first_name", "User")
            _welcome_user(chat_id, first_name)
        else:
            answer_callback(call["id"], "❌ You haven't joined all channels yet!", show_alert=True)
        return

    if data == "close_msg":
        if chat_id in user_states: user_states.pop(chat_id, None)
        if chat_id in temp_data: temp_data.pop(chat_id, None)
        answer_callback(call["id"])
        delete_message(chat_id, msg_id)
        send_message(chat_id, render_body_text(f"{PEM['hi']} Main Menu:"), reply_markup=main_menu(chat_id))
        
    elif data == "cancel_2fa":
        if chat_id in user_states: user_states.pop(chat_id, None)
        if chat_id in temp_data: temp_data.pop(chat_id, None)
        _show_2fa_menu(chat_id, msg_id)
        answer_callback(call["id"])

    elif data == "back_to_2fa_name":
        user_states[chat_id] = "wait_for_2fa_name"
        prev_msg = temp_data.get(chat_id, {}).get("msg_id", msg_id)
        temp_data[chat_id] = {"msg_id": prev_msg}
        _show_2fa_name_input(chat_id, msg_id)
        answer_callback(call["id"])

    elif data == "gen_2fa":
        user_states[chat_id] = "wait_for_2fa_name"
        temp_data[chat_id] = {"msg_id": msg_id}
        _show_2fa_name_input(chat_id, msg_id)
        answer_callback(call["id"])

    elif data.startswith("ref_2fa_"):
        secret = data.replace("ref_2fa_", "")
        try:
            totp = pyotp.TOTP(secret)
            code = totp.now()
            remaining_time = 30 - (int(time.time()) % 30)
            # Find name from saved list
            entry_name = next((e["name"] for e in user_2fa_saved.get(chat_id, []) if e["key"] == secret), "My Account")
            success_txt = _build_2fa_code_txt(entry_name, code, remaining_time)
            kb = _build_2fa_code_kb(code, secret)
            edit_message(chat_id, msg_id, render_body_text(success_txt), reply_markup={"inline_keyboard": kb})
        except Exception as e:
            answer_callback(call["id"], "❌ Error refreshing code!", show_alert=True)

    elif data.startswith("how_2fa_"):
        secret = data.replace("how_2fa_", "")
        cur_text = call["message"].get("text", call["message"].get("caption", ""))
        m = re.search(r"CODE:\s*([0-9]{4,8})", cur_text)
        code = m.group(1) if m else "------"
        entry_name = next((e["name"] for e in user_2fa_saved.get(chat_id, []) if e["key"] == secret), "My Account")

        guide_txt = (
            f"━━━━━━━━━━━━━━━\n"
            f"《 🔑 <b>HOW TO USE 2FA CODE</b> 》\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📛 <b>Account:</b> {entry_name}\n"
            f"🔐 <b>Current Code:</b> <code>{code}</code>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"<b>Step-by-Step Guide:</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"1️⃣ <b>Open the app/website</b> where you need to log in\n"
            f"   (Instagram, Facebook, Gmail, etc.)\n"
            f"━━━━━━━━━━━━━━━\n"
            f"2️⃣ <b>Email + Password</b> and enter to log in\n"
            f"━━━━━━━━━━━━━━━\n"
            f"3️⃣ After login the screen will appear:\n"
            f"   <i>\"Enter your 6-digit code\" or</i>\n"
            f"   <i>\"Go to your authentication app\"</i>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"4️⃣ In that code box <b>paste the above code</b>:\n"
            f"   <tg-emoji emoji-id=\"5416117059207572332\">👉</tg-emoji> <code>{code}</code>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"5️⃣ Press the <b>Continue / Verify</b> button ✅\n"
            f"━━━━━━━━━━━━━━━\n"
            f"⚠️ <b>Important:</b> This code is valid for only <b>30 seconds</b>!\n"
            f"Code expire hone on <b>Refresh</b> button from new code lein.\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💾 <b>For recovery:</b> \"MY 2FA ADDED\" in\n"
            f"your secret key is saved — you can generate codes at any time.\n"
            f"━━━━━━━━━━━━━━━"
        )
        _reset_btn_counter()
        guide_kb = {"inline_keyboard": [
            [{"text": "Click to copy", "icon_custom_emoji_id": "5353022963132174959", "copy_text": {"text": code}, "style": _rs()}],
            [{"text": "MY 2FA ADDED", "icon_custom_emoji_id": "5337255927735163754", "callback_data": "my_2fa_list", "style": _rs()}],
            [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"ref_2fa_{secret}", "style": _rs()}]
        ]}
        edit_message(chat_id, msg_id, render_body_text(guide_txt), reply_markup=guide_kb)
        try: answer_callback(call["id"])
        except Exception as e:
            logger.warning(f"Error: {e}")

    elif data == "my_2fa_list":
        _show_2fa_list(chat_id, msg_id)
        try: answer_callback(call["id"])
        except Exception as e:
            logger.warning(f"Error: {e}")

    elif data.startswith("gen_saved_2fa_"):
        try:
            idx = int(data.replace("gen_saved_2fa_", ""))
            saved = user_2fa_saved.get(chat_id, [])
            if idx < 0 or idx >= len(saved):
                answer_callback(call["id"], "❌ Entry not found!", show_alert=True)
                return
            entry = saved[idx]
            secret = entry["key"]
            entry_name = entry["name"]
            totp = pyotp.TOTP(secret)
            code = totp.now()
            remaining_time = 30 - (int(time.time()) % 30)

            success_txt = _build_2fa_code_txt(entry_name, code, remaining_time)
            kb = _build_2fa_code_kb(code, secret)
            edit_message(chat_id, msg_id, render_body_text(success_txt), reply_markup={"inline_keyboard": kb})
            try: answer_callback(call["id"])
            except Exception as e:
                logger.warning(f"Error: {e}")
        except Exception as e:
            answer_callback(call["id"], "❌ Error generating code!", show_alert=True)

    elif data.startswith("del_2fa_"):
        try:
            idx = int(data.replace("del_2fa_", ""))
            saved = user_2fa_saved.get(chat_id, [])
            if idx < 0 or idx >= len(saved):
                answer_callback(call["id"], "❌ Entry not found!", show_alert=True)
                return
            del_name = saved[idx]["name"]
            user_2fa_saved[chat_id].pop(idx)
            _save_2fa_saved()  # FIX: persist deletion to disk
            answer_callback(call["id"], f"🗑 '{del_name}' has been deleted!", show_alert=True)
            _show_2fa_list(chat_id, msg_id)
        except Exception as e:
            answer_callback(call["id"], "❌ Error!", show_alert=True)

    elif data == "cancel_currently_edit":
        if chat_id in user_states: user_states.pop(chat_id, None)
        if chat_id in temp_data: temp_data.pop(chat_id, None)
        _show_currently_panel(chat_id, msg_id)
        
    elif data == "dummy_alert":
        answer_callback(call["id"], "This feature will be added later!", show_alert=True)
        
    elif data == "refresh_traffic":
        txt, markup = build_traffic_ui()
        edit_message(chat_id, msg_id, txt, reply_markup=markup)
        answer_callback(call["id"], "✅ Traffic Refreshed!", show_alert=False)

    elif data.startswith("exp_rng_"):
        srv_query = data.replace("exp_rng_", "")
        
        country_stats = {}
        current_time = time.time()
        with _traffic_lock:
            traffic_snapshot = list(recent_traffic)
        for t in traffic_snapshot:
            if current_time - t.get("time", 0) <= 3600:
                if t.get("service", "").startswith(srv_query):
                    iso = t.get("iso", "XX")
                    flag = t.get("flag", "🌍")
                    if iso not in country_stats:
                        country_stats[iso] = {"count": 0, "flag": flag}
                    country_stats[iso]["count"] += 1
        
        if not country_stats:
            answer_callback(call["id"], "❌ No recent traffic found for this service!", show_alert=True)
            return
            
        _reset_btn_counter()
        kb = []
        for iso, c_data in sorted(country_stats.items(), key=lambda x: x[1]["count"], reverse=True):
            count = c_data["count"]
            c_name = iso
            emoji_id = "5780471598922337683"
            for code, fdata in bot_settings.get("premium_flags", {}).items():
                if fdata.get("iso") == iso:
                    c_name = fdata.get("name", iso)
                    if "id" in fdata: emoji_id = fdata["id"]
                    break
            
            btn_text = f"{c_name} ({iso}) - {count} OTP"
            kb.append([{"text": btn_text, "icon_custom_emoji_id": emoji_id, "callback_data": f"exp_c_{srv_query}_{iso}", "style": _rs()}])
            
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "refresh_traffic", "style": _rs()}])
        
        app_full_name, prem_app_html = get_service_info_html(srv_query)
        edit_message(chat_id, msg_id, render_body_text(f"📊 <b>Explore Service: {prem_app_html} {app_full_name}</b>\n\nSelect a country to view available ranges:"), reply_markup={"inline_keyboard": kb})
        answer_callback(call["id"])

    elif data.startswith("exp_c_"):
        # rpartition splits at the LAST "_" so service names with underscores survive intact
        _sfx = data[len("exp_c_"):]; srv_query, _, iso_query = _sfx.rpartition("_")
        
        nums = []
        current_time = time.time()
        with _traffic_lock:
            traffic_snapshot = list(recent_traffic)
        for t in traffic_snapshot:
            if current_time - t.get("time", 0) <= 3600:
                if t.get("service", "").startswith(srv_query) and t.get("iso") == iso_query:
                    num = t.get("number", "").replace("+", "").strip()
                    if num: nums.append(num)
        
        if not nums:
            answer_callback(call["id"], "❌ No recent numbers found for this country!", show_alert=True)
            return
            
        # Only take range from Nexa Services (not Search Countries, as those only have country codes)
        known_ranges = set()
        for s_name, c_dict in bot_settings.get("nexa_services", {}).items():
            for c_name, r_list in c_dict.items():
                for r in r_list:
                    known_ranges.add(r)
                    
        sorted_known = sorted(list(known_ranges), key=len, reverse=True)
        
        r_counts = Counter()
        for num in nums:
            matched = False
            for r in sorted_known:
                if num.startswith(r):
                    r_counts[r] += 1
                    matched = True
                    break
            if not matched:
                if len(num) >= 7:
                    r_counts[num[:7]] += 1
                else:
                    r_counts[num] += 1
                    
        r_list = r_counts.most_common(12)
        
        _reset_btn_counter()
        kb = []
        for r, count in r_list:
            kb.append([{"text": f"{r} ({count})", "icon_custom_emoji_id": "5352862640592949843", "copy_text": {"text": r}, "style": _rs()}])
            
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"exp_rng_{srv_query}", "style": _rs()}])
        
        app_full_name, prem_app_html = get_service_info_html(srv_query)
        prem_flag_html = get_flag_info_html(iso_query)
        
        edit_message(chat_id, msg_id, render_body_text(f"📊 <b>Ranges for {prem_app_html} {app_full_name} - {prem_flag_html} {iso_query}</b>\n\nClick on any range to copy it."), reply_markup={"inline_keyboard": kb})
        answer_callback(call["id"])

    # --- User Management Flows Integration ---
    elif data == "user_management":
        edit_message(chat_id, msg_id, get_user_management_text(), reply_markup=user_management_keyboard())

    elif data == "um_manage_balance":
        user_states[chat_id] = "wait_for_um_bal_uid"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the User ID to Manage Balance:"), reply_markup=get_cancel_kb())
        
    elif data == "um_ban_unban":
        user_states[chat_id] = "wait_for_um_ban_uid"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the User ID to Ban or Unban:"), reply_markup=get_cancel_kb())

    elif data == "um_user_profile":
        user_states[chat_id] = "wait_for_um_prof_uid"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the User ID to View Profile:"), reply_markup=get_cancel_kb())

    # --- Menu Design Integration ---
    elif data == "menu_design_list":
        edit_message(chat_id, msg_id, render_body_text(f"🎨 <b>Menu Design Editor</b>\n\nSelect a menu block to edit its Body Text and Inline Buttons. You can use Premium Emojis too!"), reply_markup=menu_design_list_keyboard())

    elif data == "md_reset_defaults":
        bot_settings["custom_messages"] = DEFAULT_CUSTOM_MESSAGES.copy()
        save_local_db()
        answer_callback(call["id"], "✅ Reset to Premium Defaults!", show_alert=True)

    elif data.startswith("md_edit_"):
        answer_callback(call["id"])
        if chat_id in user_states: user_states.pop(chat_id, None)
        if chat_id in temp_data: temp_data.pop(chat_id, None)
        key = data.replace("md_edit_", "")
        cm_text = render_body_text(bot_settings["custom_messages"].get(key, {}).get("text", "..."))
        try:
            edit_message(chat_id, msg_id, render_body_text(f"🎨 <b>Editing: {key.upper()}</b>\n\nPreview of current Text:\n{cm_text}"), reply_markup=menu_edit_options_keyboard(key))
        except Exception as e:
            logger.warning(f"Error: {e}")

    elif data.startswith("md_text_"):
        key = data.replace("md_text_", "")
        user_states[chat_id] = "wait_for_menu_text"
        temp_data[chat_id] = {"msg_id": msg_id, "menu_key": key}
        edit_message(chat_id, msg_id, render_body_text(f"📝 <b>Edit Body: {key.upper()}</b>\n\nSend the new text. You can use Premium Emojis directly here.\n(Use standard HTML like <b>bold</b>, <i>italic</i> for formatting)"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"md_edit_{key}", "style": _rs()}]]})

    elif data.startswith("md_btns_"):
        answer_callback(call["id"]) 
        if chat_id in user_states: user_states.pop(chat_id, None) 
        if chat_id in temp_data: temp_data.pop(chat_id, None)
        key = data.replace("md_btns_", "")
        try:
            edit_message(chat_id, msg_id, render_body_text(f"⚙️ <b>Edit Inline Buttons: {key.upper()}</b>"), reply_markup=menu_buttons_list_keyboard(key))
        except Exception as e:
            logger.warning(f"Error: {e}")

    elif data.startswith("md_addbtn_"):
        key = data.replace("md_addbtn_", "")
        user_states[chat_id] = "wait_for_menu_btn"
        temp_data[chat_id] = {"msg_id": msg_id, "menu_key": key}
        edit_message(chat_id, msg_id, render_body_text(f"➕ <b>Add Button: {key.upper()}</b>\n\nSend custom button in this format:\n<code>Button Text - https://link.com</code>\n\n<i>(Only normal Emojis supported here!)</i>"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"md_btns_{key}", "style": _rs()}]]})

    elif data.startswith("md_delbtn_"):
        after_prefix = data[len("md_delbtn_"):]
        key, b_idx_str = after_prefix.rsplit("_", 1)
        b_idx = int(b_idx_str)
        if key in bot_settings["custom_messages"] and b_idx < len(bot_settings["custom_messages"][key].get("buttons", [])):
            del bot_settings["custom_messages"][key]["buttons"][b_idx]
            save_local_db()
            answer_callback(call["id"], "✅ Button Deleted!", show_alert=True)
            edit_message(chat_id, msg_id, render_body_text(f"⚙️ <b>Edit Inline Buttons: {key.upper()}</b>"), reply_markup=menu_buttons_list_keyboard(key))
        else:
            answer_callback(call["id"], "❌ Button not found!", show_alert=True)

    elif data.startswith("sel_wm_"):
        method = data.replace("sel_wm_", "")
        if not is_allowed_method(method):
            answer_callback(call["id"], f"❌ This method is not allowed!\n✅ Only: {allowed_methods_text()}", show_alert=True)
            return
        method = clean_method_name(method)
        bal = get_user(chat_id).get('balance', 0.0)
        min_w = bot_settings.get('min_withdraw', 100.0)
        
        if bal < min_w:
            answer_callback(call["id"], f"❌ Insufficient balance!\nMinimum {fmt_money(min_w)} required.\nYour balance: {fmt_money(bal)}", show_alert=True)
            return
        
        answer_callback(call["id"], f"💳 Method: {method} selected!\n💰 Balance: {fmt_money(bal)} (~{fmt_usd(pkr_to_usd(bal))})\n\nNow enter the amount below.", show_alert=True)
        temp_data[chat_id] = {"method": method, "balance": bal, "msg_id": msg_id}
        user_states[chat_id] = "wait_for_withdraw_amount"
        _ask = (f"💳 Method: <b>{method}</b>\n"
                f"💰 Available Balance: <b>{fmt_dual(bal)}</b>\n"
                f"🔒 Minimum: <b>{fmt_dual(min_w)}</b>\n"
                + ("🪙 <i>USDT rate: 1 USD = " + str(bot_settings.get('usd_rate', DEFAULT_USD_RATE)) + " pkr</i>\n" if is_crypto_method(method) else "")
                + f"\n📝 Send the amount in PKR (example: {int(float(min_w))}):")
        try:
            edit_message(chat_id, msg_id, render_body_text(_ask), reply_markup=get_cancel_kb())
        except Exception as e:
            send_message(chat_id, render_body_text(_ask), reply_markup=get_cancel_kb())

    elif data == "test_message_flow":
        user_states[chat_id] = "wait_for_test_service"
        temp_data[chat_id] = {}
        edit_message(chat_id, msg_id, render_body_text("🧪 <b>Test Mode</b>\n\n📝 Send the Service Name (e.g., IG):"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": _rs()}]]})

    elif data == "manage_emojis":
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['star']} <b>Premium Emoji Management</b>\n\nSelect a category below:"), reply_markup=emoji_settings_keyboard())

    elif data == "add_single_emoji":
        user_states[chat_id] = "wait_for_emoji_extract"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text(
            "📝 <b>Add Single Premium Emoji</b>\n\n"
            "Send exactly one Telegram Premium/Custom Emoji.\n"
            "After receiving it, choose whether to save it as a Country Flag or Service App."
        ), reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_emojis", "style": "danger"}]]})

    elif data == "emoji_save_flag":
        if not temp_data.get(chat_id, {}).get("emoji_id"):
            answer_callback(call["id"], "Emoji session expired. Start again.", show_alert=True)
            return
        temp_data[chat_id]["save_mode"] = "FLAG"
        edit_message(chat_id, msg_id, render_body_text(
            "📌 <b>Save as FLAG</b>\n\n"
            "Send: <code>FLAG | 92 | PAK | Pakstan</code>"
        ), reply_markup=get_cancel_kb())

    elif data == "emoji_save_app":
        if not temp_data.get(chat_id, {}).get("emoji_id"):
            answer_callback(call["id"], "Emoji session expired. Start again.", show_alert=True)
            return
        temp_data[chat_id]["save_mode"] = "APP"
        edit_message(chat_id, msg_id, render_body_text(
            "📌 <b>Save as APP</b>\n\n"
            "Send: <code>APP | WhatsApp</code>"
        ), reply_markup=get_cancel_kb())

    elif data == "emoji_upload_menu":
        edit_message(chat_id, msg_id, render_body_text(f"📤 <b>All Uploading System</b>\n\nSelect what you want to upload:"), reply_markup=emoji_upload_keyboard())

    elif data == "emoji_delete_menu":
        edit_message(chat_id, msg_id, render_body_text(f"🗑 <b>All Deleting System</b>\n\nSelect what you want to delete:"), reply_markup=emoji_delete_keyboard())

    elif data == "emoji_download_menu":
        edit_message(chat_id, msg_id, render_body_text(f"📥 <b>All Downloading System</b>\n\nSelect what you want to download:"), reply_markup=emoji_download_keyboard())

    elif data == "up_flags_txt":
        user_states[chat_id] = "wait_for_flag_txt"
        edit_message(chat_id, msg_id, render_body_text("📂 Please upload the <b>Flag Emojis</b> <code>.txt</code> file."), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "emoji_upload_menu", "style": _rs()}]]})

    elif data == "up_apps_txt":
        user_states[chat_id] = "wait_for_app_txt"
        edit_message(chat_id, msg_id, render_body_text("📂 Please upload the <b>Service Apps</b> <code>.txt</code> file."), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "emoji_upload_menu", "style": _rs()}]]})

    elif data == "dl_flags_txt":
        content = generate_emoji_txt("flags")
        if content:
            send_document(chat_id, "Flag_Emojis.txt", content)
            answer_callback(call["id"], "✅ Downloaded!")
        else:
            answer_callback(call["id"], "❌ No Flag Emojis found!", show_alert=True)

    elif data == "dl_apps_txt":
        content = generate_emoji_txt("apps")
        if content:
            send_document(chat_id, "Service_Apps.txt", content)
            answer_callback(call["id"], "✅ Downloaded!")
        else:
            answer_callback(call["id"], "❌ No App Emojis found!", show_alert=True)

    elif data == "del_all_flags":
        bot_settings["premium_flags"] = {}
        save_local_db()
        answer_callback(call["id"], "✅ All Premium Flags Deleted Successfully!", show_alert=True)
        edit_message(chat_id, msg_id, render_body_text(f"🗑 <b>All Deleting System</b>\n\nSelect what you want to delete:"), reply_markup=emoji_delete_keyboard())

    elif data == "del_all_apps":
        bot_settings["premium_apps"] = {}
        save_local_db()
        answer_callback(call["id"], "✅ All Service Emojis Deleted Successfully!", show_alert=True)
        edit_message(chat_id, msg_id, render_body_text(f"🗑 <b>All Deletion System</b>\n\nSelect what you want to delete:"), reply_markup=emoji_delete_keyboard())


    elif data == "broadcast_msg":
        user_states[chat_id] = "wait_for_broadcast"
        edit_message(chat_id, msg_id, render_body_text("📢 <b>Broadcast Mode</b>\n\nSend the message you want to broadcast (Text, Photo, Video, File etc)."), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "back_to_admin", "style": _rs()}]]})

    elif data == "upload_num":
        if not is_admin(chat_id):
            answer_callback(call["id"], "❌ Only ADMIN can add numbers/range!", show_alert=True)
            return
        user_states[chat_id] = "wait_for_txt"
        edit_message(chat_id, msg_id, render_body_text("📂 Please upload the numbers in a <b>.txt</b> file."), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "back_to_admin", "style": _rs()}]]})

    elif data == "delete_files":
        _reset_btn_counter()
        kb = []
        for b_id, b_data in number_batches.items():
            _r = b_data.get("rate_pkr")
            _rt = f" • {fmt_money(_r)}" if _r else ""
            kb.append([{"text": f"{b_data['filename']} ({len(b_data['numbers'])}){_rt}", "icon_custom_emoji_id": "5422557736330106570", "callback_data": f"del_b_{b_id}", "style": _rs()}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "back_to_admin", "style": _rs()}])
        txt = "🗑 Select a file to delete:" if len(kb) > 1 else f"{PEM['no']} No files found."
        edit_message(chat_id, msg_id, render_body_text(txt), reply_markup={"inline_keyboard": kb})

    elif data.startswith("del_b_"):
        b_id = data.split("del_b_")[1]
        if b_id in number_batches:
            del number_batches[b_id]
            save_local_db()
            answer_callback(call["id"], "✅ File deleted!", show_alert=True)
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": "delete_files", "id": "internal"})

    elif data == "show_used":
        all_nums = _get_all_numbers_set()
        otp_used = [n for n in all_nums if n in otp_received_numbers]
        _reset_btn_counter()
        kb = {"inline_keyboard": [[{"text": "Download TXT", "icon_custom_emoji_id": "5257969839313526622", "callback_data": "dl_used", "style": _rs()}], [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "back_to_admin", "style": _rs()}]]}
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['ok']} <b>Used Numbers (OTP Received):</b> {len(otp_used)}"), reply_markup=kb)

    elif data == "show_unused":
        all_nums = _get_all_numbers_set()
        otp_unused = [n for n in all_nums if n not in otp_received_numbers]
        _reset_btn_counter()
        kb = {"inline_keyboard": [[{"text": "Download TXT", "icon_custom_emoji_id": "5257969839313526622", "callback_data": "dl_unused", "style": _rs()}], [{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "back_to_admin", "style": _rs()}]]}
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['rocket']} <b>Unused Numbers (No OTP):</b> {len(otp_unused)}"), reply_markup=kb)

    elif data == "dl_used":
        all_nums = _get_all_numbers_set()
        otp_used = [n for n in all_nums if n in otp_received_numbers]
        if not otp_used:
            answer_callback(call["id"], "No OTP received numbers found!", show_alert=True)
            return
        content = "\n".join(otp_used).encode('utf-8')
        send_document(chat_id, "used_otp_numbers.txt", content)
        answer_callback(call["id"])

    elif data == "dl_unused":
        all_nums = _get_all_numbers_set()
        otp_unused = [n for n in all_nums if n not in otp_received_numbers]
        if not otp_unused:
            answer_callback(call["id"], "All numbers have received OTP!", show_alert=True)
            return
        content = "\n".join(otp_unused).encode('utf-8')
        send_document(chat_id, "unused_no_otp_numbers.txt", content)
        answer_callback(call["id"])

    elif data == "lb_main":
        txt = f"━━━━━━━━━━━━━━━\n《 {PEM['admin']} <b>LEADER BOARD MENU</b> 》\n━━━━━━━━━━━━━━━\n<i>Select a category to view the top performers or history.</i>\n━━━━━━━━━━━━━━━"
        _reset_btn_counter()
        kb = [
            [{"text": "Top Referrers", "icon_custom_emoji_id": "5420145051336485498", "callback_data": "lb_top_refs", "style": _rs()}],
            [{"text": "Top OTP Receivers", "icon_custom_emoji_id": "5353001161878182134", "callback_data": "lb_top_otps", "style": _rs()}],
            [{"text": "Withdrawal History", "icon_custom_emoji_id": "5348469219761626211", "callback_data": "lb_w_history", "style": _rs()}],
            [{"text": "Back to Admin", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "back_to_admin", "style": _rs()}]
        ]
        edit_message(chat_id, msg_id, render_body_text(txt), reply_markup={"inline_keyboard": kb})

    elif data.startswith("lb_"):
        sub = data.replace("lb_", "")
        edit_message(chat_id, msg_id, render_body_text("⌛ <i>Fetching Data...</i>"))
        
        num_map = {"1": "1️⃣", "2": "2️⃣", "3": "3️⃣", "4": "4️⃣", "5": "5️⃣", "6": "6️⃣", "7": "7️⃣", "8": "8️⃣", "9": "9️⃣", "0": "0️⃣"}
        def get_p_num(n): return "".join([num_map.get(c, c) for c in str(n)])
        
        try:
            if sub == "top_refs":
                title, field, limit_n, icon = "TOP 5 REFERRERS", "total_refers", 5, PEM.get('user', '👥')
                res_txt = ""
                count = 1
                sorted_users = sorted(local_users_db.items(), key=lambda x: x[1].get(field, 0), reverse=True)[:limit_n]
                for uid, d in sorted_users:
                    if d.get(field, 0) > 0:
                        p = "└" if count == limit_n else "├"
                        res_txt += f"{p} {get_p_num(count)} <a href='tg://user?id={uid}'>{uid}</a> ➔ <b>{d.get(field,0)}</b>\n"
                        count += 1
                if not res_txt: res_txt = "└ <i>No data found.</i>\n"

            elif sub == "top_otps":
                title, field, limit_n, icon = "TOP 5 OTP RECEIVERS", "total_otps", 5, PEM.get('msg', '📩')
                res_txt = ""
                count = 1
                sorted_users = sorted(local_users_db.items(), key=lambda x: x[1].get(field, 0), reverse=True)[:limit_n]
                for uid, d in sorted_users:
                    if d.get(field, 0) > 0:
                        p = "└" if count == limit_n else "├"
                        res_txt += f"{p} {get_p_num(count)} <a href='tg://user?id={uid}'>{uid}</a> ➔ <b>{d.get(field,0)}</b>\n"
                        count += 1
                if not res_txt: res_txt = "└ <i>No data found.</i>\n"

            elif sub == "w_history":
                title, limit_n, icon = "LAST 10 WITHDRAWALS", 10, PEM.get('money', '💸')
                res_txt = ""
                count = 1
                sorted_ws = sorted(local_withdrawals_db.items(), key=lambda x: x[1].get("timestamp", 0), reverse=True)[:limit_n]
                for wid, d in sorted_ws:
                    s = str(d.get('status','Pending')).lower()
                    stat_icon = PEM.get('ok','✅') if s in ["approved","success"] else PEM.get('no','❌') if s=="rejected" else "⏳"
                    uid = d.get('user_id','User')
                    p = "└" if count == limit_n else "├"
                    res_txt += f"{p} {get_p_num(count)} <a href='tg://user?id={uid}'>{uid}</a> ➔ <b>{d.get('amount',0)}PKR</b> {stat_icon}\n"
                    count += 1
                if not res_txt: res_txt = "└ <i>No history found.</i>\n"

            final_msg = f"━━━━━━━━━━━━━━━\n{icon} <b>{title}</b>\n━━━━━━━━━━━━━━━\n{res_txt}━━━━━━━━━━━━━━━"
            _reset_btn_counter()
            kb = [[{"text": "Refresh", "icon_custom_emoji_id": "5420155432272438703", "callback_data": data, "style": _rs()}, {"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "lb_main", "style": _rs()}]]
            edit_message(chat_id, msg_id, render_body_text(final_msg), reply_markup={"inline_keyboard": kb})

        except Exception as e:
            edit_message(chat_id, msg_id, render_body_text(f"❌ Error: {e}"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "lb_main", "style": _rs()}]]})

    elif data == "back_to_admin":
        if chat_id in user_states: user_states.pop(chat_id, None)
        if chat_id in temp_data: temp_data.pop(chat_id, None)
        edit_message(chat_id, msg_id, get_admin_text(), reply_markup=admin_panel_keyboard())
        
    elif data == "system_settings":
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['gear']} <b>System Settings</b>\nManage advanced bot configurations below:"), reply_markup=system_settings_keyboard())

    # ===== OTP Forward Manager =====
    elif data == "otp_forward_manager":
        edit_message(chat_id, msg_id, render_body_text("⚙️ <b>OTP FORWARD MANAGER</b>\n\nCustomize OTP forward settings below:"), reply_markup=otp_forward_manager_keyboard())
    elif data == "set_channel_link":
        user_states[chat_id] = "wait_for_channel_link"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the new Channel Link (e.g. https://t.me/yourchannel):"), reply_markup=get_cancel_kb())
    elif data == "set_number_link":
        user_states[chat_id] = "wait_for_number_link"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the new Number Link (e.g. https://t.me/yourbot):"), reply_markup=get_cancel_kb())
    elif data == "otp_message_emojis":
        edit_message(chat_id, msg_id, render_body_text("🎨 <b>OTP GROUP MESSAGE EMOJIS</b>\n\nএকটি একটি করে যেই লাইনের আগে Premium Emoji দিতে চান সেটি নির্বাচন করুন। তারপর শুধু একটি Premium/Custom Emoji পাঠান।"), reply_markup=otp_message_emoji_keyboard())
    elif data == "otp_button_emojis":
        edit_message(chat_id, msg_id, render_body_text("🎨 <b>OTP GROUP BUTTON EMOJIS</b>\n\nChannel, OTP Copy এবং Number Bot button-এর emoji আলাদাভাবে সেট করতে পারবেন।"), reply_markup=otp_button_emoji_keyboard())
    elif data.startswith("set_otp_msg_emoji_"):
        target = data.replace("set_otp_msg_emoji_", "", 1)
        allowed = {"before_flag", "before_service", "before_number", "before_time", "before_otp"}
        if target not in allowed:
            answer_callback(call["id"], "Invalid emoji position", show_alert=True)
        else:
            user_states[chat_id] = "wait_for_otp_msg_emoji"
            temp_data[chat_id] = {"msg_id": msg_id, "emoji_target": target}
            title = target.replace("before_", "").replace("_", " ").title()
            edit_message(chat_id, msg_id, render_body_text(f"🎨 <b>Set Emoji: {title}</b>\n\nএখন একটি Premium/Custom Emoji পাঠান।\nশুধু এই position-এই emoji save হবে।"), reply_markup=get_cancel_kb())
    elif data.startswith("set_otp_btn_emoji_"):
        target = data.replace("set_otp_btn_emoji_", "", 1)
        allowed = {"channel", "otp", "number_bot"}
        if target not in allowed:
            answer_callback(call["id"], "Invalid button", show_alert=True)
        else:
            user_states[chat_id] = "wait_for_otp_btn_emoji"
            temp_data[chat_id] = {"msg_id": msg_id, "emoji_target": target}
            title = target.replace("_", " ").title()
            edit_message(chat_id, msg_id, render_body_text(f"🎨 <b>Set Button Emoji: {title}</b>\n\nএখন একটি Premium/Custom Emoji পাঠান।\nশুধু এই button-এই emoji save হবে."), reply_markup=get_cancel_kb())
    elif data == "clear_otp_msg_emojis":
        bot_settings.setdefault("otp_forward", {}).setdefault("emoji_positions", {})
        for key in bot_settings["otp_forward"]["emoji_positions"]:
            bot_settings["otp_forward"]["emoji_positions"][key] = ""
        save_local_db()
        edit_message(chat_id, msg_id, render_body_text("✅ OTP Group message prefix emojis cleared."), reply_markup=otp_message_emoji_keyboard())

    elif data == "backup_menu":
        if chat_id != OWNER_ID:
            answer_callback(call["id"], "❌ Only OWNER can take backup!", show_alert=True)
            return
        edit_message(chat_id, msg_id, render_body_text(
            "🛡️ <b>BACKUP &amp; RESTORE</b>\n\n"
            "• <b>DOWNLOAD BACKUP</b> — all data (users, balance, OTP count, ranges, settings) in a zip\n"
            "• <b>RESTORE BACKUP</b> — upload the same zip to restore everything\n"
            "• <b>AUTO BACKUP</b> — every 6 hours it will automatically send you a zip\n\n"
            "<i>Bot update karne from before always backup take lein.</i>"), reply_markup=backup_menu_keyboard())

    elif data == "bk_download":
        if chat_id != OWNER_ID:
            answer_callback(call["id"], "❌ Only OWNER!", show_alert=True)
            return
        answer_callback(call["id"], "⏳ Backup is being created...")
        send_backup_to(chat_id)

    elif data == "bk_restore":
        if chat_id != OWNER_ID:
            answer_callback(call["id"], "❌ Only OWNER!", show_alert=True)
            return
        user_states[chat_id] = "wait_for_backup_zip"
        answer_callback(call["id"])
        send_message(chat_id, render_body_text(
            "♻️ <b>RESTORE</b>\n\n📤 Now send the backup <b>.zip</b> file.\n\n"
            "⚠️ <i>Current data will be replaced (a safety backup will be automatically created).</i>"),
            reply_markup=get_cancel_kb())

    elif data == "bk_toggle_auto":
        if chat_id != OWNER_ID:
            answer_callback(call["id"], "❌ Only OWNER!", show_alert=True)
            return
        bot_settings["auto_backup"] = not bot_settings.get("auto_backup", True)
        save_local_db()
        edit_message(chat_id, msg_id, render_body_text("🛡️ <b>BACKUP &amp; RESTORE</b>"), reply_markup=backup_menu_keyboard())

    elif data == "auto_mode" and not THIRD_PARTY_PROVIDERS:
        answer_callback(call["id"],
            "🚫 Third-party providers (Nexa / VoltX / Stex) are disabled.\n\n"
            "✅ The bot only uses its own panel and .txt uploaded numbers.",
            show_alert=True)

    elif data in ("toggle_nexa", "toggle_voltx", "toggle_stex") and not THIRD_PARTY_PROVIDERS:
        answer_callback(call["id"], "🚫 This system is disabled — only own panel and txt numbers work.", show_alert=True)

    elif data == "auto_mode":
        nexa_cnt  = len(bot_settings.get('nexa_keys', []))
        voltx_cnt = len(bot_settings.get('voltx_keys', []))
        stex_cnt  = len(bot_settings.get('stex_keys', []))
        nexa_on   = bot_settings.get("nexa_on", False)
        voltx_on  = bot_settings.get("voltx_on", False)
        stex_on   = bot_settings.get("stex_on", False)
        _on_txt  = '<tg-emoji emoji-id="6266827283135207188">✅</tg-emoji> ON'
        _off_txt = '<tg-emoji emoji-id="6267237615720731788">🔴</tg-emoji> OFF'
        edit_message(chat_id, msg_id, render_body_text(
            '➖➖➖➖➖➖➖\n'
            '  <tg-emoji emoji-id="6318566568011764192">⚡</tg-emoji>  <b>AUTO MODE</b>  <tg-emoji emoji-id="6318566568011764192">⚡</tg-emoji>\n'
            '➖➖➖➖➖➖➖\n\n'
            f'<b>Nexa</b>   »  Keys: <b>{nexa_cnt}</b>   {_on_txt if nexa_on else _off_txt}\n'
            f'<b>VoltX</b>  »  Keys: <b>{voltx_cnt}</b>  {_on_txt if voltx_on else _off_txt}\n'
            f'<b>Stex</b>   »  Keys: <b>{stex_cnt}</b>   {_on_txt if stex_on else _off_txt}\n\n'
            '➖➖➖➖➖➖➖'
        ), reply_markup=auto_mode_keyboard())

    elif data == "toggle_nexa":
        bot_settings["nexa_on"] = not bot_settings.get("nexa_on", False)
        save_local_db()
        if bot_settings["nexa_on"]:
            _service_warmup_needed["nexa"] = True  # Skip old OTPs on first poll after enable
        state = "✅ ON" if bot_settings["nexa_on"] else "🔴 OFF"
        answer_callback(call["id"], f"Nexa is now {state}", show_alert=False)
        handle_callback({"message": call["message"], "data": "auto_mode", "id": "internal"})

    elif data == "toggle_voltx":
        bot_settings["voltx_on"] = not bot_settings.get("voltx_on", False)
        save_local_db()
        if bot_settings["voltx_on"]:
            _service_warmup_needed["voltx"] = True  # Skip old OTPs on first poll after enable
        state = "✅ ON" if bot_settings["voltx_on"] else "🔴 OFF"
        answer_callback(call["id"], f"VoltX is now {state}", show_alert=False)
        handle_callback({"message": call["message"], "data": "auto_mode", "id": "internal"})

    elif data == "toggle_stex":
        bot_settings["stex_on"] = not bot_settings.get("stex_on", False)
        save_local_db()
        if bot_settings["stex_on"]:
            _service_warmup_needed["stex"] = True  # Skip old OTPs on first poll after enable
        state = "✅ ON" if bot_settings["stex_on"] else "🔴 OFF"
        answer_callback(call["id"], f"Stex is now {state}", show_alert=False)
        handle_callback({"message": call["message"], "data": "auto_mode", "id": "internal"})

    elif data in ("nexa_control", "voltx_control", "stex_control") and not THIRD_PARTY_PROVIDERS:
        answer_callback(call["id"], "🚫 Third-party provider system is down.", show_alert=True)

    elif data == "nexa_control":
        edit_message(chat_id, msg_id, render_body_text(f'<tg-emoji emoji-id="6282760761399841824">🔹</tg-emoji> <b>Nexa</b>\n\nTotal API Keys: {len(bot_settings.get("nexa_keys", []))}\nManage your Nexa API Keys below:'), reply_markup=_panel_control_keyboard("Nexa"))

    elif data == "add_nexa_key":
        user_states[chat_id] = "wait_for_add_nexa_key"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the new Nexa API Key (e.g. nxa_...):"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "nexa_control", "style": _rs()}]]})

    elif data == "view_nexa_keys":
        _reset_btn_counter()
        kb = []
        for idx, key in enumerate(bot_settings.get("nexa_keys", [])):
            safe_name = key[:10] + "..." if len(key)>10 else key
            kb.append([{"text": f"Delete {safe_name}", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"del_nxa_{idx}", "style": _rs()}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "nexa_control", "style": _rs()}])
        edit_message(chat_id, msg_id, render_body_text("🗑 <b>Select Nexa Key to Delete:</b>"), reply_markup={"inline_keyboard": kb})

    elif data.startswith("del_nxa_"):
        idx = _safe_int(data.split("_")[2] if len(data.split("_")) > 2 else -1)
        if 0 <= idx < len(bot_settings.get("nexa_keys", [])):
            del bot_settings["nexa_keys"][idx]
            save_local_db()
            answer_callback(call["id"], "✅ Nexa Key Deleted!", show_alert=True)
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": "view_nexa_keys", "id": "internal"})
        else:
            answer_callback(call["id"], "❌ Key not found!", show_alert=True)

    elif data == "nexa_search_country":
        _show_panel_search_countries("nexa", chat_id, msg_id)

    elif data == "add_search_country":
        user_states[chat_id] = "wait_for_add_sc"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the Country Code (e.g. 880 or 92):"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "nexa_search_country", "style": _rs()}]]})

    elif data.startswith("del_sc_"):
        idx = _safe_int(data.split("_")[2] if len(data.split("_")) > 2 else -1)
        if 0 <= idx < len(bot_settings.get("nexa_search_countries", [])):
            del bot_settings["nexa_search_countries"][idx]
            save_local_db()
            answer_callback(call["id"], "✅ Country Deleted!", show_alert=True)
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": "nexa_search_country", "id": "internal"})
        else:
            answer_callback(call["id"], "❌ Country not found!", show_alert=True)

    elif data == "manage_nexa_srv":
        _reset_btn_counter()
        kb = []
        srvs = bot_settings.get("nexa_services", {})
        apps_db = bot_settings.get("premium_apps", {})
        for si, srv in enumerate(srvs):
            emoji_id = _get_service_emoji_id(srv, apps_db)
            kb.append([{"text": f"{srv}", "icon_custom_emoji_id": emoji_id, "callback_data": f"nx_srv_{srv}", "style": _rs()}])
        kb.append([{"text": "Add New Service", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "nx_add_srv", "style": _rs()}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "nexa_control", "style": _rs()}])
        edit_message(chat_id, msg_id, render_body_text("📦 <b>Nexa Services Manager</b>\nManage your API-based dynamic services below:"), reply_markup={"inline_keyboard": kb})

    elif data == "nx_add_srv":
        user_states[chat_id] = "wait_nx_srv_name"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Enter Service Name (e.g. TELEGRAM):"), reply_markup=get_cancel_kb())

    elif data.startswith("nx_srv_"):
        srv = data.replace("nx_srv_", "")
        _reset_btn_counter()
        kb = []
        countries = bot_settings["nexa_services"].get(srv, {})
        flags_db = bot_settings.get("premium_flags", {})
        for ci, c in enumerate(countries):
            emoji_id = _find_flag_emoji_id(c, flags_db)
            kb.append([{"text": f"{c} ({len(countries[c])} Ranges)", "icon_custom_emoji_id": emoji_id, "callback_data": f"nx_cnt_{srv}_{c}", "style": _rs()}])
        kb.append([{"text": "Add Country", "icon_custom_emoji_id": "5420323438508155202", "callback_data": f"nx_add_cnt_{srv}", "style": _rs()}])
        kb.append([{"text": "Delete Service", "icon_custom_emoji_id": "5422557736330106570", "callback_data": f"nx_del_srv_{srv}", "style": _rs()}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_nexa_srv", "style": _rs()}])
        edit_message(chat_id, msg_id, render_body_text(f"📂 <b>Service: {srv}</b>\nManage countries for this service:"), reply_markup={"inline_keyboard": kb})

    elif data.startswith("nx_add_cnt_"):
        srv = data.replace("nx_add_cnt_", "")
        user_states[chat_id] = "wait_nx_cnt_name"
        temp_data[chat_id] = {"msg_id": msg_id, "srv": srv}
        edit_message(chat_id, msg_id, render_body_text(f"🌍 Enter Country Name for <b>{srv}</b> (e.g. PAK, SAUDI):"), reply_markup=get_cancel_kb())

    elif data.startswith("nx_cnt_"):
        _sfx = data[len("nx_cnt_"):]; srv, _, cnt = _sfx.partition("_")
        ranges = bot_settings["nexa_services"][srv].get(cnt, [])
        
        _reset_btn_counter()
        kb = []
        row = []
        for ri, r in enumerate(ranges):
            row.append({"text": f"Delete {r}", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"nx_dr_{srv}_{cnt}_{r}", "style": _rs()})
            if len(row) == 2:
                kb.append(row)
                row = []
        if row: kb.append(row)
        
        kb.append([{"text": "Add Range", "icon_custom_emoji_id": "5420323438508155202", "callback_data": f"nx_addr_{srv}_{cnt}", "style": _rs()}])
        kb.append([{"text": "Delete Entire Country", "icon_custom_emoji_id": "5422557736330106570", "callback_data": f"nx_del_cnt_{srv}_{cnt}", "style": _rs()}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"nx_srv_{srv}", "style": _rs()}])
        
        txt = f"📍 <b>Service: {srv} | Country: {cnt}</b>\n\n<b>Total Ranges:</b> {len(ranges)}\n<i>Click on a range below to delete it, or add a new one.</i>"
        edit_message(chat_id, msg_id, render_body_text(txt), reply_markup={"inline_keyboard": kb})

    elif data.startswith("nx_addr_"):
        _sfx = data[len("nx_addr_"):]; srv, _, cnt = _sfx.partition("_")
        user_states[chat_id] = "wait_nx_addr"
        temp_data[chat_id] = {"msg_id": msg_id, "srv": srv, "cnt": cnt}
        edit_message(chat_id, msg_id, render_body_text(f"📝 Send the new Range for <b>{cnt}</b> (e.g. 88017):"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"nx_cnt_{srv}_{cnt}", "style": _rs()}]]})

    elif data.startswith("nx_dr_"):
        _sfx = data[len("nx_dr_"):]; srv, _, _rest = _sfx.partition("_"); cnt, _, rng = _rest.partition("_")
        if rng in bot_settings["nexa_services"].get(srv, {}).get(cnt, []):
            bot_settings["nexa_services"][srv][cnt].remove(rng)
            save_local_db()
            answer_callback(call["id"], f"✅ Range {rng} deleted!", show_alert=True)
        handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": f"nx_cnt_{srv}_{cnt}", "id": "internal"})

    elif data.startswith("nx_del_srv_"):
        srv = data.replace("nx_del_srv_", "")
        if srv in bot_settings["nexa_services"]: del bot_settings["nexa_services"][srv]
        save_local_db()
        handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": "manage_nexa_srv", "id": "internal"})

    elif data.startswith("nx_del_cnt_"):
        _sfx = data[len("nx_del_cnt_"):]; srv, _, cnt = _sfx.partition("_")
        if cnt in bot_settings["nexa_services"].get(srv, {}): del bot_settings["nexa_services"][srv][cnt]
        save_local_db()
        handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": f"nx_srv_{srv}", "id": "internal"})

    # ==========================================
    # VoltX Control Callbacks
    # ==========================================
    elif data == "voltx_control":
        edit_message(chat_id, msg_id, render_body_text(f'<tg-emoji emoji-id="6282760761399841824">🔹</tg-emoji> <b>VoltX</b>\n\nTotal API Keys: {len(bot_settings.get("voltx_keys", []))}\nManage your VoltX API Keys below:'), reply_markup=_panel_control_keyboard("VoltX"))

    elif data == "add_voltx_key":
        user_states[chat_id] = "wait_for_add_voltx_key"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the new VoltX API Key (mauthapi key):"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "voltx_control", "style": _rs()}]]})

    elif data == "view_voltx_keys":
        _reset_btn_counter()
        kb = []
        for idx, key in enumerate(bot_settings.get("voltx_keys", [])):
            safe_name = key[:10] + "..." if len(key) > 10 else key
            kb.append([{"text": f"Delete {safe_name}", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"del_vx_{idx}", "style": _rs()}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "voltx_control", "style": _rs()}])
        edit_message(chat_id, msg_id, render_body_text("🗑 <b>Select VoltX Key to Delete:</b>"), reply_markup={"inline_keyboard": kb})

    elif data.startswith("del_vxsc_"):
        idx = _safe_int(data.split("_")[2] if len(data.split("_")) > 2 else -1)
        if 0 <= idx < len(bot_settings.get("voltx_search_countries", [])):
            del bot_settings["voltx_search_countries"][idx]
            save_local_db()
            answer_callback(call["id"], "✅ Country Deleted!", show_alert=True)
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": "voltx_search_country", "id": "internal"})
        else:
            answer_callback(call["id"], "❌ Country not found!", show_alert=True)

    elif data.startswith("del_vx_"):
        idx = _safe_int(data.split("_")[2] if len(data.split("_")) > 2 else -1)
        if 0 <= idx < len(bot_settings.get("voltx_keys", [])):
            del bot_settings["voltx_keys"][idx]
            save_local_db()
            answer_callback(call["id"], "✅ VoltX Key Deleted!", show_alert=True)
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": "view_voltx_keys", "id": "internal"})
        else:
            answer_callback(call["id"], "❌ Key not found!", show_alert=True)

    elif data == "voltx_search_country":
        _show_panel_search_countries("voltx", chat_id, msg_id)

    elif data == "add_vx_search_country":
        user_states[chat_id] = "wait_for_add_vxsc"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the Country Code (e.g. 880 or 92):"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "voltx_search_country", "style": _rs()}]]})

    elif data == "manage_voltx_srv":
        _reset_btn_counter()
        kb = []
        srvs = bot_settings.get("voltx_services", {})
        apps_db = bot_settings.get("premium_apps", {})
        for si, srv in enumerate(srvs):
            emoji_id = _get_service_emoji_id(srv, apps_db)
            kb.append([{"text": f"{srv}", "icon_custom_emoji_id": emoji_id, "callback_data": f"vx_srv_{srv}", "style": _rs()}])
        kb.append([{"text": "Add New Service", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "vx_add_srv", "style": _rs()}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "voltx_control", "style": _rs()}])
        edit_message(chat_id, msg_id, render_body_text("📦 <b>VoltX Services Manager</b>\\nManage your API-based dynamic services below:"), reply_markup={"inline_keyboard": kb})

    elif data == "vx_add_srv":
        user_states[chat_id] = "wait_vx_srv_name"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Enter Service Name (e.g. WHATSAPP, FACEBOOK):"), reply_markup=get_cancel_kb())

    elif data.startswith("vx_srv_"):
        srv = data.replace("vx_srv_", "")
        _reset_btn_counter()
        kb = []
        countries = bot_settings["voltx_services"].get(srv, {})
        flags_db = bot_settings.get("premium_flags", {})
        for ci, c in enumerate(countries):
            emoji_id = _find_flag_emoji_id(c, flags_db)
            kb.append([{"text": f"{c} ({len(countries[c])} Ranges)", "icon_custom_emoji_id": emoji_id, "callback_data": f"vx_cnt_{srv}_{c}", "style": _rs()}])
        kb.append([{"text": "Add Country", "icon_custom_emoji_id": "5420323438508155202", "callback_data": f"vx_add_cnt_{srv}", "style": _rs()}])
        kb.append([{"text": "Delete Service", "icon_custom_emoji_id": "5422557736330106570", "callback_data": f"vx_del_srv_{srv}", "style": _rs()}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_voltx_srv", "style": _rs()}])
        edit_message(chat_id, msg_id, render_body_text(f"📂 <b>Service: {srv}</b>\\nManage countries for this service:"), reply_markup={"inline_keyboard": kb})

    elif data.startswith("vx_add_cnt_"):
        srv = data.replace("vx_add_cnt_", "")
        user_states[chat_id] = "wait_vx_cnt_name"
        temp_data[chat_id] = {"msg_id": msg_id, "srv": srv}
        edit_message(chat_id, msg_id, render_body_text(f"🌍 Enter Country Name for <b>{srv}</b> (e.g. PAK, SAUDI):"), reply_markup=get_cancel_kb())

    elif data.startswith("vx_cnt_"):
        _sfx = data[len("vx_cnt_"):]; srv, _, cnt = _sfx.partition("_")
        ranges = bot_settings["voltx_services"][srv].get(cnt, [])
        _reset_btn_counter()
        kb = []
        row = []
        for ri, r in enumerate(ranges):
            row.append({"text": f"Del {r}", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"vx_dr_{srv}_{cnt}_{r}", "style": _rs()})
            if len(row) == 2:
                kb.append(row)
                row = []
        if row: kb.append(row)
        kb.append([{"text": "Add Range", "icon_custom_emoji_id": "5420323438508155202", "callback_data": f"vx_addr_{srv}_{cnt}", "style": _rs()}])
        kb.append([{"text": "Delete Entire Country", "icon_custom_emoji_id": "5422557736330106570", "callback_data": f"vx_del_cnt_{srv}_{cnt}", "style": _rs()}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"vx_srv_{srv}", "style": _rs()}])
        txt = f"📍 <b>Service: {srv} | Country: {cnt}</b>\\n\\n<b>Total Ranges:</b> {len(ranges)}\\n<i>Click on a range below to delete it, or add a new one.</i>"
        edit_message(chat_id, msg_id, render_body_text(txt), reply_markup={"inline_keyboard": kb})

    elif data.startswith("vx_addr_"):
        _sfx = data[len("vx_addr_"):]; srv, _, cnt = _sfx.partition("_")
        user_states[chat_id] = "wait_vx_addr"
        temp_data[chat_id] = {"msg_id": msg_id, "srv": srv, "cnt": cnt}
        edit_message(chat_id, msg_id, render_body_text(f"📝 Send the new Range for <b>{cnt}</b> (e.g. 88017):"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"vx_cnt_{srv}_{cnt}", "style": _rs()}]]})

    elif data.startswith("vx_dr_"):
        _sfx = data[len("vx_dr_"):]; srv, _, _rest = _sfx.partition("_"); cnt, _, rng = _rest.partition("_")
        if rng in bot_settings["voltx_services"].get(srv, {}).get(cnt, []):
            bot_settings["voltx_services"][srv][cnt].remove(rng)
            save_local_db()
            answer_callback(call["id"], f"✅ Range {rng} deleted!", show_alert=True)
        handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": f"vx_cnt_{srv}_{cnt}", "id": "internal"})

    elif data.startswith("vx_del_srv_"):
        srv = data.replace("vx_del_srv_", "")
        if srv in bot_settings["voltx_services"]: del bot_settings["voltx_services"][srv]
        save_local_db()
        handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": "manage_voltx_srv", "id": "internal"})

    elif data.startswith("vx_del_cnt_"):
        _sfx = data[len("vx_del_cnt_"):]; srv, _, cnt = _sfx.partition("_")
        if cnt in bot_settings["voltx_services"].get(srv, {}): del bot_settings["voltx_services"][srv][cnt]
        save_local_db()
        handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": f"vx_srv_{srv}", "id": "internal"})

    # ==========================================
    # Stex Control Callbacks
    # ==========================================
    elif data == "stex_control":
        edit_message(chat_id, msg_id, render_body_text(f'<tg-emoji emoji-id="6282760761399841824">🔹</tg-emoji> <b>Stex</b>\\n\\nTotal API Keys: {len(bot_settings.get("stex_keys", []))}\\nManage your Stex API Keys below:'), reply_markup=_panel_control_keyboard("Stex"))

    elif data == "add_stex_key":
        user_states[chat_id] = "wait_for_add_stex_key"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the new Stex API Key (api-key):"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "stex_control", "style": _rs()}]]})

    elif data == "view_stex_keys":
        _reset_btn_counter()
        kb = []
        for idx, key in enumerate(bot_settings.get("stex_keys", [])):
            safe_name = key[:10] + "..." if len(key) > 10 else key
            kb.append([{"text": f"Delete {safe_name}", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"del_stx_{idx}", "style": _rs()}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "stex_control", "style": _rs()}])
        edit_message(chat_id, msg_id, render_body_text("🗑 <b>Select Stex Key to Delete:</b>"), reply_markup={"inline_keyboard": kb})

    elif data.startswith("del_stxsc_"):
        idx = _safe_int(data.split("_")[2] if len(data.split("_")) > 2 else -1)
        if 0 <= idx < len(bot_settings.get("stex_search_countries", [])):
            del bot_settings["stex_search_countries"][idx]
            save_local_db()
            answer_callback(call["id"], "✅ Country Deleted!", show_alert=True)
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": "stex_search_country", "id": "internal"})
        else:
            answer_callback(call["id"], "❌ Country not found!", show_alert=True)

    elif data.startswith("del_stx_"):
        idx = _safe_int(data.split("_")[2] if len(data.split("_")) > 2 else -1)
        if 0 <= idx < len(bot_settings.get("stex_keys", [])):
            del bot_settings["stex_keys"][idx]
            save_local_db()
            answer_callback(call["id"], "✅ Stex Key Deleted!", show_alert=True)
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": "view_stex_keys", "id": "internal"})
        else:
            answer_callback(call["id"], "❌ Key not found!", show_alert=True)

    elif data == "stex_search_country":
        _show_panel_search_countries("stex", chat_id, msg_id)

    elif data == "add_stx_search_country":
        user_states[chat_id] = "wait_for_add_stxsc"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the Country Code (e.g. 880 or 92):"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "stex_search_country", "style": _rs()}]]})

    elif data == "manage_stex_srv":
        _reset_btn_counter()
        kb = []
        srvs = bot_settings.get("stex_services", {})
        apps_db = bot_settings.get("premium_apps", {})
        for si, srv in enumerate(srvs):
            emoji_id = _get_service_emoji_id(srv, apps_db)
            kb.append([{"text": f"{srv}", "icon_custom_emoji_id": emoji_id, "callback_data": f"stx_srv_{srv}", "style": _rs()}])
        kb.append([{"text": "Add New Service", "icon_custom_emoji_id": "5420323438508155202", "callback_data": "stx_add_srv", "style": _rs()}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "stex_control", "style": _rs()}])
        edit_message(chat_id, msg_id, render_body_text("📦 <b>Stex Services Manager</b>\\nManage your API-based dynamic services below:"), reply_markup={"inline_keyboard": kb})

    elif data == "stx_add_srv":
        user_states[chat_id] = "wait_stx_srv_name"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Enter Service Name (e.g. WHATSAPP, FACEBOOK):"), reply_markup=get_cancel_kb())

    elif data.startswith("stx_srv_"):
        srv = data.replace("stx_srv_", "")
        _reset_btn_counter()
        kb = []
        countries = bot_settings["stex_services"].get(srv, {})
        flags_db = bot_settings.get("premium_flags", {})
        for ci, c in enumerate(countries):
            emoji_id = _find_flag_emoji_id(c, flags_db)
            kb.append([{"text": f"{c} ({len(countries[c])} Ranges)", "icon_custom_emoji_id": emoji_id, "callback_data": f"stx_cnt_{srv}_{c}", "style": _rs()}])
        kb.append([{"text": "Add Country", "icon_custom_emoji_id": "5420323438508155202", "callback_data": f"stx_add_cnt_{srv}", "style": _rs()}])
        kb.append([{"text": "Delete Service", "icon_custom_emoji_id": "5422557736330106570", "callback_data": f"stx_del_srv_{srv}", "style": _rs()}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_stex_srv", "style": _rs()}])
        edit_message(chat_id, msg_id, render_body_text(f"📂 <b>Service: {srv}</b>\\nManage countries for this service:"), reply_markup={"inline_keyboard": kb})

    elif data.startswith("stx_add_cnt_"):
        srv = data.replace("stx_add_cnt_", "")
        user_states[chat_id] = "wait_stx_cnt_name"
        temp_data[chat_id] = {"msg_id": msg_id, "srv": srv}
        edit_message(chat_id, msg_id, render_body_text(f"🌍 Enter Country Name for <b>{srv}</b> (e.g. PAK, SAUDI):"), reply_markup=get_cancel_kb())

    elif data.startswith("stx_cnt_"):
        # rpartition: service name may contain "_"; country code sits at the right end
        _sfx = data[len("stx_cnt_"):]; srv, _, cnt = _sfx.rpartition("_")
        ranges = bot_settings["stex_services"][srv].get(cnt, [])
        _reset_btn_counter()
        kb = []
        row = []
        for ri, r in enumerate(ranges):
            row.append({"text": f"Del {r}", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"stx_dr_{srv}_{cnt}_{r}", "style": _rs()})
            if len(row) == 2:
                kb.append(row)
                row = []
        if row: kb.append(row)
        kb.append([{"text": "Add Range", "icon_custom_emoji_id": "5420323438508155202", "callback_data": f"stx_addr_{srv}_{cnt}", "style": _rs()}])
        kb.append([{"text": "Delete Entire Country", "icon_custom_emoji_id": "5422557736330106570", "callback_data": f"stx_del_cnt_{srv}_{cnt}", "style": _rs()}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"stx_srv_{srv}", "style": _rs()}])
        txt = f"📍 <b>Service: {srv} | Country: {cnt}</b>\n\n<b>Total Ranges:</b> {len(ranges)}\n<i>Click on a range below to delete it, or add a new one.</i>"
        edit_message(chat_id, msg_id, render_body_text(txt), reply_markup={"inline_keyboard": kb})

    elif data.startswith("stx_addr_"):
        _sfx = data[len("stx_addr_"):]; srv, _, cnt = _sfx.rpartition("_")
        user_states[chat_id] = "wait_stx_addr"
        temp_data[chat_id] = {"msg_id": msg_id, "srv": srv, "cnt": cnt}
        edit_message(chat_id, msg_id, render_body_text(f"📝 Send the new Range for <b>{cnt}</b> (e.g. 88017):"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"stx_cnt_{srv}_{cnt}", "style": _rs()}]]})

    elif data.startswith("stx_dr_"):
        # Split from right: range never has "_", then country, leaving service (may have "_") on the left
        _sfx = data[len("stx_dr_"):]; _left, _, rng = _sfx.rpartition("_"); srv, _, cnt = _left.rpartition("_")
        if rng in bot_settings["stex_services"].get(srv, {}).get(cnt, []):
            bot_settings["stex_services"][srv][cnt].remove(rng)
            save_local_db()
            answer_callback(call["id"], f"✅ Range {rng} deleted!", show_alert=True)
        handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": f"stx_cnt_{srv}_{cnt}", "id": "internal"})

    elif data.startswith("stx_del_srv_"):
        srv = data.replace("stx_del_srv_", "")
        if srv in bot_settings["stex_services"]: del bot_settings["stex_services"][srv]
        save_local_db()
        handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": "manage_stex_srv", "id": "internal"})

    elif data.startswith("stx_del_cnt_"):
        _sfx = data[len("stx_del_cnt_"):]; srv, _, cnt = _sfx.rpartition("_")
        if cnt in bot_settings["stex_services"].get(srv, {}): del bot_settings["stex_services"][srv][cnt]
        save_local_db()
        handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": f"stx_srv_{srv}", "id": "internal"})

    elif data == "manage_fj":
        _show_fj_panel(chat_id, msg_id)

    elif data == "toggle_fj":
        bot_settings["fj_on"] = not bot_settings["fj_on"]
        save_local_db()
        _show_fj_panel(chat_id, msg_id)

    elif data == "add_fj":
        user_states[chat_id] = "wait_for_add_fj"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 <b>Add Channel or Group</b>\n\n✅ Bot must already be an admin in the channel/group!\n\nSend one of:\n• Username: <code>@channelname</code>\n• Public Link: <code>https://t.me/channelname</code>\n• Numeric ID: <code>-1001234567890</code>\n\n🔄 Bot will auto-detect Channel/Group and Private/Public!"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_fj", "style": _rs()}]]})

    elif data.startswith("del_fj_"):
        idx = _safe_int(data.split("_")[2] if len(data.split("_")) > 2 else -1)
        if 0 <= idx < len(bot_settings["fj_channels"]):
            removed = bot_settings["fj_channels"][idx]
            info = _get_fj_info(removed)
            del bot_settings["fj_channels"][idx]
            save_local_db()
            answer_callback(call["id"], f"✅ {info.get('title', 'Item')} deleted!", show_alert=True)
            _show_fj_panel(chat_id, msg_id)
        else:
            answer_callback(call["id"], "❌ Item not found!", show_alert=True)

    elif data == "manage_admins":
        _show_admin_panel(chat_id, msg_id)

    elif data == "add_adm":
        user_states[chat_id] = "wait_for_add_adm"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the User ID of the new Admin:"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_admins", "style": _rs()}]]})

    elif data.startswith("del_adm_"):
        # FIX: ID-based deletion — wrong admin was deleted when index shifted
        adm_id = _safe_int(data.split("_")[2] if len(data.split("_")) > 2 else -1)
        if adm_id in bot_settings["admins"] and adm_id != OWNER_ID:
            bot_settings["admins"].remove(adm_id)
            save_local_db()
            answer_callback(call["id"], "✅ Admin deleted!", show_alert=True)
            _show_admin_panel(chat_id, msg_id)
        else:
            answer_callback(call["id"], "❌ Admin not found!", show_alert=True)

    elif data == "manage_otp_groups":
        _show_otp_groups_panel(chat_id, msg_id)

    elif data == "add_fw":
        user_states[chat_id] = "wait_for_add_fw_id"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the Group ID/Username to forward messages to:"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_otp_groups", "style": _rs()}]]})

    elif data.startswith("manage_fw_"):
        idx = _safe_int(data.split("_")[2] if len(data.split("_")) > 2 else -1)
        if 0 <= idx < len(bot_settings["fw_groups"]):
            grp_id = bot_settings["fw_groups"][idx]["chat_id"]
            edit_message(chat_id, msg_id, render_body_text(f"🛡 <b>Manage Group:</b> {grp_id}"), reply_markup=specific_fw_group_keyboard(idx))
        else:
            _alert_group_gone(call)

    elif data.startswith("add_fwbtn_"):
        idx = _safe_int(data.split("_")[2] if len(data.split("_")) > 2 else -1)
        if not (0 <= idx < len(bot_settings["fw_groups"])):
            _alert_group_gone(call)
            return
        user_states[chat_id] = "wait_for_add_fw_btn"
        temp_data[chat_id] = {"msg_id": msg_id, "fw_idx": idx}
        edit_message(chat_id, msg_id, render_body_text(
            "📝 <b>Add Inline Button</b>\n\n"
            "➖➖➖➖➖➖➖\n"
            "📌 <b>Format (without emoji):</b>\n"
            "<code>Button Text - https://link.com</code>\n\n"
            "📌 <b>Format (with premium emoji ID):</b>\n"
            "<code>6228781436330054904 Button Text - https://link.com</code>\n"
            "➖➖➖➖➖➖➖\n"
            "💡 <b>Examples:</b>\n"
            "<code>Join Channel - https://t.me/mychannel</code>\n"
            "<code>6228781436330054904 Join VIP - https://t.me/vip</code>\n"
            "➖➖➖➖➖➖➖\n"
            "⚠️ First write the Emoji ID, then the button text, then <code> - </code>, then the link."
        ), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"manage_fw_{idx}", "style": _rs()}]]})

    elif data.startswith("del_fwbtn_"):
        parts = data.split("_")
        idx   = _safe_int(parts[2] if len(parts) > 2 else -1)
        b_idx = _safe_int(parts[3] if len(parts) > 3 else -1)
        if 0 <= idx < len(bot_settings["fw_groups"]):
            if 0 <= b_idx < len(bot_settings["fw_groups"][idx]["buttons"]):
                del bot_settings["fw_groups"][idx]["buttons"][b_idx]
                save_local_db()
                answer_callback(call["id"], "✅ Button deleted!", show_alert=True)
                edit_message(chat_id, msg_id, render_body_text(f"🛡 <b>Manage Group:</b> {bot_settings['fw_groups'][idx]['chat_id']}"), reply_markup=specific_fw_group_keyboard(idx))
            else:
                answer_callback(call["id"], "❌ Button not found!", show_alert=True)
        else:
            _alert_group_gone(call)

    elif data.startswith("del_fw_"):
        idx = _safe_int(data.split("_")[2] if len(data.split("_")) > 2 else -1)
        if 0 <= idx < len(bot_settings["fw_groups"]):
            del bot_settings["fw_groups"][idx]
            save_local_db()
            answer_callback(call["id"], "✅ Group deleted!", show_alert=True)
            _show_otp_groups_panel(chat_id, msg_id)
        else:
            _alert_group_gone(call)

    elif data == "edit_otp_link":
        user_states[chat_id] = "wait_for_otp_link"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the new OTP Group Link:"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_otp_groups", "style": _rs()}]]})

    elif data == "manage_panels":
        api_count = len([p for p in bot_settings["panels"] if p.get("type") == "API Panel"])
        cpt_count = len([p for p in bot_settings["panels"] if p.get("type", "API Panel") == "Auto Captcha Panel"])
        sock_count = len([p for p in bot_settings["panels"] if p.get("type") == "Live Socket Panel"])
        text = f"{PEM['gear']} <b>Panel Management</b>\n\nSelect which type of panel system you want to manage:"
        _reset_btn_counter()
        kb = {"inline_keyboard": [
            [{"text": f"Manage API Panels ({api_count})", "icon_custom_emoji_id": "5336972142066047577", "callback_data": "manage_api_panels", "style": _rs()}],
            [{"text": f"Manage Auto Captcha Panels ({cpt_count})", "icon_custom_emoji_id": "5353022963132174959", "callback_data": "manage_cpt_panels", "style": _rs()}],
            [{"text": f"Manage Live Socket Panels ({sock_count})", "icon_custom_emoji_id": "5330691748267580565", "callback_data": "manage_socket_panels", "style": _rs()}],
            [{"text": "Back to System", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "system_settings", "style": _rs()}]
        ]}
        edit_message(chat_id, msg_id, render_body_text(text), reply_markup=kb)

    elif data in ["manage_api_panels", "manage_cpt_panels", "manage_socket_panels"]:
        p_type = {"manage_api_panels": "API Panel", "manage_cpt_panels": "Auto Captcha Panel",
                  "manage_socket_panels": "Live Socket Panel"}[data]
        p_list = [p for p in bot_settings["panels"] if p.get("type", "API Panel") == p_type]
        icon = f"{PEM['world']} API" if p_type == 'API Panel' else (f"{PEM['lock']} Auto Captcha" if p_type == 'Auto Captcha Panel' else "🔌 Live Socket")

        text = f"{icon} <b>{p_type}s Management</b>\n\n👀 <b>Active Monitors:</b> {len(p_list)}\n\n🟢 <b>Available Providers:</b>\n"
        for p in p_list:
            status = "Monitoring" if p['status'] == 'ON' else "Stopped"
            login_state = p.get('login_status', '')
            if p['type'] in ('Auto Captcha Panel', 'Live Socket Panel'):
                conf = f" {login_state}" if login_state else f"{PEM['ok']} Configured"
            else:
                conf = f"{PEM['ok']} Configured" if p.get('api_url') else f"{PEM['no']} Not Configured"
            text += f"• {p['name']}: {PEM['ok'] if p['status']=='ON' else PEM['no']} {status} | {conf}\n"
        edit_message(chat_id, msg_id, render_body_text(text), reply_markup=typed_panels_list_keyboard(p_type))

    elif data in ["add_api_panel", "add_cpt_panel", "add_sock_panel"]:
        user_states[chat_id] = "wait_for_panel_name"
        p_type = {"add_api_panel": "api", "add_cpt_panel": "logc", "add_sock_panel": "sock"}[data]
        temp_data[chat_id] = {"msg_id": msg_id, "add_type": p_type}
        back_key = {"api": "api", "logc": "cpt", "sock": "sock"}[p_type]
        edit_message(chat_id, msg_id, render_body_text("📝 Please send the name of the New Provider:"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"manage_{back_key}_panels", "style": _rs()}]]})

    elif data in ["list_del_api", "list_del_cpt", "list_del_sock"]:
        p_type = _pnl_type_from_key(data.replace("list_del_", ""))
        _reset_btn_counter()
        kb = []
        for idx, p in enumerate(bot_settings["panels"]):
            if p.get("type", "API Panel") == p_type:
                kb.append([{"text": f"Delete {p['name']}", "icon_custom_emoji_id": "5420130255174145507", "callback_data": f"do_del_pnl_{idx}", "style": _rs()}])
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"manage_{_pnl_key(p_type)}_panels", "style": _rs()}])
        edit_message(chat_id, msg_id, render_body_text(f"{PEM['trash']} <b>Select a Provider to Delete:</b>"), reply_markup={"inline_keyboard": kb})

    elif data.startswith("do_del_pnl_"):
        idx = _safe_int(data.split("_")[3] if len(data.split("_")) > 3 else -1)
        if 0 <= idx < len(bot_settings["panels"]):
            p_type = bot_settings["panels"][idx].get("type", "API Panel")
            # Also clean up panel_sessions for this and higher indices
            if idx in panel_sessions:
                del panel_sessions[idx]
            # Shift panel_sessions keys down for indices above deleted one
            new_sessions = {}
            for k, v in panel_sessions.items():
                if k > idx:
                    new_sessions[k - 1] = v
                elif k < idx:
                    new_sessions[k] = v
            panel_sessions.clear()
            panel_sessions.update(new_sessions)
            socket_panel_threads.pop(idx, None)
            del bot_settings["panels"][idx]
            save_local_db()
            answer_callback(call["id"], "✅ Provider Deleted!", show_alert=True)
            handle_callback({"message": {"chat": {"id": chat_id}, "message_id": msg_id}, "data": f"manage_{_pnl_key(p_type)}_panels", "id": "internal"})
        else:
            answer_callback(call["id"], "❌ Panel not found! May have already been deleted.", show_alert=True)

    elif data.startswith("tog_pnl_"):
        idx = _safe_int(data.split("_")[2] if len(data.split("_")) > 2 else -1)
        if not (0 <= idx < len(bot_settings["panels"])):
            _alert_panel_gone(call)
            return
        p = bot_settings["panels"][idx]
        new_status = "ON" if p["status"] == "OFF" else "OFF"
        if new_status == "ON":
            p["needs_warmup"] = True  # Set warmup first — eliminate race condition
        p["status"] = new_status      # after in status flip do
        save_local_db()
        if new_status == "ON":
            if p.get("type") == "Live Socket Panel":
                p["needs_warmup"] = False  # socket = only new pushes, backlog not
                _start_socket_panel_thread(idx)
            else:
                # immediately background thread in existing OTPs mark do (panel_monitor_thread from before)
                threading.Thread(target=_eagerly_warmup_panel, args=(idx, p), daemon=True).start()

        _show_panel_cfg(chat_id, msg_id, idx)

    elif data.startswith("conf_pnl_"):
        idx = _safe_int(data.split("_")[2] if len(data.split("_")) > 2 else -1)
        if not (0 <= idx < len(bot_settings["panels"])):
            _alert_panel_gone(call)
            return
        _show_panel_cfg(chat_id, msg_id, idx)

    elif data.startswith("set_p_wsurl_"):
        idx = int(data.split("_")[-1])
        _set_panel_temp(chat_id, msg_id, idx)
        user_states[chat_id] = "wait_for_p_wsurl"
        edit_message(chat_id, msg_id, render_body_text("🔗 Please send the new WebSocket URL:"), reply_markup=get_cancel_kb())

    elif data.startswith("set_p_api_"):
        idx = _safe_int(data.split("_")[3] if len(data.split("_")) > 3 else -1)
        if idx < 0 or idx >= len(bot_settings["panels"]):
            _alert_panel_gone(call)
            return
        user_states[chat_id] = "wait_for_p_api"
        _set_panel_temp(chat_id, msg_id, idx)
        edit_message(chat_id, msg_id, render_body_text("📝 Send the API URL for this provider:"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"conf_pnl_{idx}", "style": _rs()}]]})

    elif data.startswith("set_p_tok_"):
        idx = _safe_int(data.split("_")[3] if len(data.split("_")) > 3 else -1)
        if idx < 0 or idx >= len(bot_settings["panels"]):
            _alert_panel_gone(call)
            return
        user_states[chat_id] = "wait_for_p_tok"
        _set_panel_temp(chat_id, msg_id, idx)
        edit_message(chat_id, msg_id, render_body_text("📝 Send the Token for this provider:"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"conf_pnl_{idx}", "style": _rs()}]]})

    elif data.startswith("set_p_tokh_"):
        idx = _safe_int(data.split("_")[3] if len(data.split("_")) > 3 else -1)
        if idx < 0 or idx >= len(bot_settings["panels"]):
            _alert_panel_gone(call)
            return
        user_states[chat_id] = "wait_for_p_tokheader"
        _set_panel_temp(chat_id, msg_id, idx)
        edit_message(chat_id, msg_id, render_body_text("📝 Send the <b>Header Name</b> for token authentication.\n\n<b>Example:</b> <code>mauthapi</code> (for VoltX SMS)\n\nWhen set, the token will be sent as an HTTP header instead of a URL parameter.\n\nType <code>none</code> to remove and use URL parameter mode."), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"conf_pnl_{idx}", "style": _rs()}]]})

    elif data.startswith("set_p_fapi_"):
        idx = _safe_int(data.split("_")[3] if len(data.split("_")) > 3 else -1)
        if idx < 0 or idx >= len(bot_settings["panels"]):
            _alert_panel_gone(call)
            return
        user_states[chat_id] = "wait_for_p_fapi"
        _set_panel_temp(chat_id, msg_id, idx)
        edit_message(chat_id, msg_id, render_body_text("📝 Send the FULL API URL (Example: http://api.com/get?key=YOUR_TOKEN&start=0):"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"conf_pnl_{idx}", "style": _rs()}]]})

    elif data.startswith("set_p_rec_"):
        idx = _safe_int(data.split("_")[3] if len(data.split("_")) > 3 else -1)
        if idx < 0 or idx >= len(bot_settings["panels"]):
            _alert_panel_gone(call)
            return
        user_states[chat_id] = "wait_for_p_rec"
        _set_panel_temp(chat_id, msg_id, idx)
        edit_message(chat_id, msg_id, render_body_text("📝 Send the number of records to fetch (e.g. 10).\nType <code>0</code> for Unlimited:"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": f"conf_pnl_{idx}", "style": _rs()}]]})

    elif data.startswith("test_p_conn_"):
        idx = _safe_int(data.split("_")[3] if len(data.split("_")) > 3 else -1)
        if idx < 0 or idx >= len(bot_settings["panels"]):
            _alert_panel_gone(call)
            return
        p = bot_settings["panels"][idx]
        wait_msg = send_message(chat_id, render_body_text("⏳ Testing connection. Please wait..."))
        wait_msg_id = wait_msg.get("result", {}).get("message_id") if wait_msg else None
        answer_callback(call["id"])

        # 🔌 Live Socket Panel — separate test path (WebSocket handshake, not HTTP)
        if p["type"] == "Live Socket Panel":
            ok, info = quick_socket_test(p.get("ws_url", ""))
            if wait_msg_id: delete_message(chat_id, wait_msg_id)
            if ok:
                p["login_status"] = "✅ Connected & Listening"
                if p["status"] != "ON":
                    p["status"] = "ON"
                save_local_db()
                _start_socket_panel_thread(idx)
                send_message(chat_id, render_body_text(
                    f"✅ <b>Connected!</b>\n<i>{html.escape(str(info))}</i>\n\n"
                    f"🔌 Panel is ON — live OTP catching has started."))
            else:
                p["login_status"] = "❌ Connection Failed"
                save_local_db()
                send_message(chat_id, render_body_text(
                    f"⚠️ <b>Could not connect.</b>\n\n<b>Reason:</b> {html.escape(str(info)[:250])}\n\n"
                    f"<i>WebSocket URL check by again try do.</i>"))
            _show_panel_cfg(chat_id, msg_id, idx)
            return

        try:
            parsed = []
            raw_text = ""
            
            if p["type"] == "Auto Captcha Panel":
                sess = panel_sessions.get(idx)
                if not sess:
                    # FIX: Lockout period check — Test Connection will not lock the panel anymore
                    now = time.time()
                    retry_wait = p.get("retry_wait", 90)
                    last_attempt = p.get("last_login_attempt", 0)
                    time_since = now - last_attempt
                    if time_since < retry_wait:
                        remaining = int(retry_wait - time_since)
                        if wait_msg_id: delete_message(chat_id, wait_msg_id)
                        locked_status = p.get("login_status", "Panel Locked")
                        send_message(chat_id, render_body_text(
                            f"🔒 <b>Panel Locked — Please wait!</b>\n\n"
                            f"Status: {html.escape(str(locked_status))}\n"
                            f"⏳ <b>{remaining}s</b> until auto-retry.\n\n"
                            f"<i>Test Connection after login succeeds.</i>"
                        ))
                        return
                    success = attempt_auto_login(p, idx)
                    if not success:
                        if wait_msg_id: delete_message(chat_id, wait_msg_id)
                        send_message(chat_id, render_body_text(f"❌ <b>Auto Login Failed!</b>\nReason: {html.escape(str(p.get('login_status', 'Unknown')))}"))
                        return
                    sess = panel_sessions.get(idx)
                    
                # 🌟 FIX: Use JSON fetcher for SPA/JSON-API panels (such as Teleroutex)
                # api_base set hone of matlab = this JSON API panel is (HTML table not)
                if p.get("api_base"):
                    parsed, raw_text = _fetch_json_api_panel_data(p, sess)
                else:
                    _lu = p.get("login_url", "").strip()
                    if not _lu.startswith("http"): _lu = "http://" + _lu
                    msg_link = p.get("msg_link", "").strip()
                    if msg_link and not msg_link.startswith("http"): msg_link = "http://" + msg_link
                    _sec = p.get("panel_section", "client")
                    check_url = msg_link if msg_link else f"{_extract_base_url(_lu)}/{_sec}/SMSCDRStats"
                    parsed, raw_text = fetch_cpt_panel_cdrs(p, sess, check_url)
                
            else:
                full_url = p.get("full_api_url", "").strip()
                url = p.get("api_url", "").strip()
                token = p.get("token", "").strip()
                if not full_url and not url:
                    if wait_msg_id: delete_message(chat_id, wait_msg_id)
                    send_message(chat_id, render_body_text("❌ Please Set API URL or Full API URL first!"))
                    return
                
                urls_to_try, headers = _build_api_urls(p)
                parsed = []
                raw_text = ""
                for try_url in urls_to_try:
                    try:
                        res = tg_session.get(try_url, headers=headers, timeout=10)
                        raw_text = res.text
                        # Only HTTP 429 is treated as rate limiting. A normal
                        # JSON body may contain words such as "rate".
                        if res.status_code == 429:
                            backoff = _rate_limit_backoff_seconds(res, default=2)
                            if wait_msg_id: delete_message(chat_id, wait_msg_id)
                            send_message(chat_id, render_body_text(
                                f"⚠️ <b>API Rate Limited!</b>\n\n"
                                f"The API temporarily blocked requests because there were too many requests.\n"
                                f"<i>Try again after {backoff} seconds.</i>\n\n"
                                f"<b>Raw:</b> <code>{html.escape(raw_text[:200])}</code>"
                            ))
                            return
                        # max_results=3: parse only the top 3, entire list not
                        parsed = parse_panel_response(raw_text, p, max_results=3)
                        if parsed:
                            if not full_url and try_url != url and token and not p.get("token_header", ""):
                                p["api_url"] = try_url.replace(token, "{token}")
                                save_local_db()
                            break
                    except Exception as e:
                        logger.warning(f"API URL test attempt failed: {e}")
                 
            # 📡 Show the CR API's own error (Not Authorized etc.) directly
            _cr_err = cr_api_error(raw_text)
            if _cr_err and not parsed:
                if wait_msg_id: delete_message(chat_id, wait_msg_id)
                send_message(chat_id, render_body_text(
                    f"❌ <b>API returned an error!</b>\n\n"
                    f"📝 <b>Reason:</b> <code>{html.escape(_cr_err)}</code>\n\n"
                    f"<i>The token is incorrect or has expired — obtain a new token from your panel administrator.</i>"))
                return

            # 🔁 CR API POST fallback (docs: both GET and POST supported)
            if not parsed:
                _post_raw = cr_api_post_fetch(p)
                if _post_raw and not cr_api_error(_post_raw):
                    _rows = parse_panel_response(_post_raw, p, max_results=3) or legacy_parse_panel_response(_post_raw, p)
                    if _rows:
                        parsed = _rows[:3]
                        raw_text = _post_raw
                        p["use_post"] = True
                        save_local_db()

            # 🔁 If the new (strict) method fails, try the old working script connection
            used_legacy = False
            if not parsed:
                l_parsed, l_raw = legacy_panel_connect(p, idx)
                if l_parsed:
                    parsed = l_parsed
                    raw_text = l_raw or raw_text
                    used_legacy = True
                elif l_raw and not raw_text:
                    raw_text = l_raw

            if wait_msg_id: delete_message(chat_id, wait_msg_id)

            if parsed:
                total = min(3, len(parsed))
                if used_legacy:
                    send_message(chat_id, render_body_text(
                        "✅ <b>Connected (Legacy Mode)</b>\n"
                        "<i>The new parser could not extract data, the old method worked — "
                        "OTPs will arrive from here.</i>"))
                send_message(chat_id, render_body_text(
                    f"✅ <b>Connection Successful!</b>\n"
                    f"🎯 Top <b>{total}</b> messages — real format:"
                ))
                for i, sample in enumerate(parsed[:3]):
                    num = sample['number']
                    msg = sample['message']
                    otp = sample['otp']
                    detected_app = detect_service(msg)
                    app_name = detected_app if detected_app else p.get("name", "Unknown")
                    app_full_name, prem_app_html = get_service_info_html(app_name, msg)
                    display_num = f"+{num}" if not str(num).startswith("+") else str(num)
                    char, iso = get_flag_and_code(num)
                    lang = detect_language(msg)
                    masked = mask_number(display_num)
                    otp_msg = render_body_text(
                        f"{get_flag_info_html(display_num)} #{iso} ♦ {masked} ✅ {otp}"
                    )
                    _reset_btn_counter()
                    kb = [
                        [{"text": f"{otp}", "icon_custom_emoji_id": "5474525960143385880", "copy_text": {"text": otp}, "style": _rs()}]
                    ]
                    send_message(chat_id, otp_msg, reply_markup={"inline_keyboard": kb})
            else:
                if p["type"] == "Auto Captcha Panel":
                    # 🌟 FIX: Separate error message for JSON API panel (such as Teleroutex)
                    if p.get("api_base"):
                        # SPA/JSON API panel — means no OTP records found:
                        # Either no new SMS has arrived, or the filter blocked them all
                        send_message(chat_id, render_body_text(
                            f"✅ <b>Connection Successful!</b>\n\n"
                            f"🔗 API: <code>{html.escape(p.get('api_base',''))}/api/message-data-record</code>\n"
                            f"👤 User: <code>{html.escape(p.get('username',''))}</code>\n\n"
                            f"⚠️ <b>No OTP message found at the moment.</b>\n"
                            f"<i>New SMS arriving at the panel will automatically appear in the group.</i>"
                        ))
                    else:
                        try:
                            soup = BeautifulSoup(raw_text, 'html.parser')
                            tables = soup.find_all('table')
                            if tables:
                                full_table_data = "🔍 FULL TABLE DATA (A-Z)\n" + "="*50 + "\n\n"
                                for t_idx, table in enumerate(tables):
                                    full_table_data += f"--- Table {t_idx+1} ---\n"
                                    rows = table.find_all('tr')
                                    for r_idx, row in enumerate(rows):
                                        cols = row.find_all(['th', 'td'])
                                        col_texts = [f"[{c_idx+1}] {c.get_text(separator=' ', strip=True)}" for c_idx, c in enumerate(cols)]
                                        full_table_data += f"Row {r_idx+1}: {' | '.join(col_texts)}\n"
                                    full_table_data += "\n" + "="*50 + "\n"
                                send_document(chat_id, f"Full_Panel_Data_{idx}.txt", full_table_data.encode('utf-8'))
                                fail_txt = f"⚠️ <b>Connected, but couldn't parse OTP data!</b>\n\n<i>I have sent the complete (A-Z) data of that link in a Text File. Open the file and check the correct Column Number (e.g.: [1], [3]) then update in panel.</i>"
                                send_message(chat_id, render_body_text(fail_txt))
                            else:
                                send_message(chat_id, render_body_text(f"⚠️ <b>Connected, but no HTML Table found!</b>\nMake sure the message link is correct."))
                        except Exception as e:
                            send_message(chat_id, render_body_text(f"❌ <b>Error parsing HTML:</b> {html.escape(str(e))}"))
                else:
                    # Show raw excerpt for debugging — only replace 'nn' if no real newlines present
                    excerpt = raw_text[:600] if raw_text else ""
                    if '\n' not in excerpt:
                        debug_raw = re.sub(r'(?<![a-zA-Z])nn(?![a-zA-Z])', '\n', excerpt)
                    else:
                        debug_raw = excerpt
                    safe_html = html.escape(str(debug_raw)[:400])
                    
                    # Helpful diagnosis: check do of report kya problem is
                    diagnosis = ""
                    if not raw_text:
                        diagnosis = "❌ API returned no data (empty response)."
                    else:
                        try:
                            test_data = json.loads(raw_text)
                            if isinstance(test_data, list) and test_data:
                                first = test_data[0]
                                if isinstance(first, list):
                                    p_num_idx = int(p.get("num_col_idx", 2)) - 1
                                    p_msg_idx = int(p.get("msg_col_idx", 3)) - 1
                                    cols = len(first)
                                    diagnosis = (
                                        f"✅ JSON parse: OK ({len(test_data)} rows, {cols} columns per row)\n"
                                        f"• Number column {p.get('num_col_idx',2)} (index {p_num_idx}): "
                                        f"<code>{html.escape(str(first[p_num_idx]) if p_num_idx < cols else 'OUT OF RANGE')}</code>\n"
                                        f"• Message column {p.get('msg_col_idx',3)} (index {p_msg_idx}): "
                                        f"<code>{html.escape(str(first[p_msg_idx])[:80] if p_msg_idx < cols else 'OUT OF RANGE')}</code>\n"
                                        f"• OTP found: <code>{html.escape(str(extract_otp_code(str(first[p_msg_idx]).replace('nn',chr(10))) or 'NOT FOUND'))}</code>"
                                    )
                                elif isinstance(first, dict):
                                    diagnosis = f"✅ JSON parse: OK ({len(test_data)} records, dict format)\n⚠️ OTP/Number fields not found — check key names."
                                else:
                                    diagnosis = f"⚠️ JSON parse: OK but format unknown ({type(first).__name__})"
                            elif isinstance(test_data, dict):
                                diagnosis = f"⚠️ JSON is an object (list expected) — check the API response structure."
                            else:
                                diagnosis = f"⚠️ JSON parse: OK but empty list received."
                        except Exception as je:
                            diagnosis = f"❌ JSON parse failed: <code>{html.escape(str(je)[:100])}</code>\n⚠️ API is not returning JSON — check URL/Token."
                    
                    send_message(chat_id, render_body_text(
                        f"⚠️ <b>Connected, but couldn't parse OTP data.</b>\n\n"
                        f"<b>Diagnosis:</b>\n{diagnosis}\n\n"
                        f"<b>Raw Data (excerpt):</b>\n<code>{safe_html}...</code>"
                    ))
        except Exception as e:
            if wait_msg_id: delete_message(chat_id, wait_msg_id)
            send_message(chat_id, render_body_text(f"❌ <b>Connection Failed!</b>\nError: {html.escape(str(e))}"))

    elif data == "currently_control":
        if chat_id in user_states: user_states.pop(chat_id, None)
        if chat_id in temp_data: temp_data.pop(chat_id, None)
        _show_currently_panel(chat_id, msg_id)

    elif data == "currently_toggle_w":
        bot_settings["withdraw_on"] = not bot_settings["withdraw_on"]
        save_local_db()
        _show_currently_panel(chat_id, msg_id)

    elif data == "manage_w_methods":
        _show_w_methods(chat_id, msg_id)

    elif data == "add_wm":
        user_states[chat_id] = "wait_for_add_wm"
        temp_data[chat_id] = {"msg_id": msg_id}
        edit_message(chat_id, msg_id, render_body_text("📝 Send the name of the new Withdrawal Method:"), reply_markup={"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "manage_w_methods", "style": _rs()}]]})

    elif data.startswith("del_wm_"):
        if not is_admin(chat_id):
            answer_callback(call["id"], "❌ Admin only!", show_alert=True)
            return
        idx = _safe_int(data.split("_")[2] if len(data.split("_")) > 2 else -1)
        if 0 <= idx < len(bot_settings["w_methods"]):
            del bot_settings["w_methods"][idx]
            save_local_db()
            answer_callback(call["id"], "✅ Method deleted!", show_alert=True)
            _show_w_methods(chat_id, msg_id)
        else:
            answer_callback(call["id"], "❌ Method not found!", show_alert=True)

    elif data.startswith("currently_"):
        if not is_admin(chat_id):
            answer_callback(call["id"], "❌ Admin only!", show_alert=True)
            return
        key = data.replace("currently_", "")
        key_map = {"min_w": "min_withdraw", "otp_r": "otp_reward", "ref_r": "refer_reward", "cool": "cooldown", "num_req": "num_req", "num_share": "num_share", "sup_link": "support_link", "w_group": "w_group", "usd_rate": "usd_rate"}
        if key in key_map:
            temp_data[chat_id] = {"msg_id": msg_id, "key": key_map[key]}
            user_states[chat_id] = "set_currently"
            _reset_btn_counter()
            cancel_kb = {"inline_keyboard": [[{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "cancel_currently_edit", "style": _rs()}]]}
            edit_message(chat_id, msg_id, render_body_text(f"📝 Please send the new value for <code>{key_map[key]}</code>:"), reply_markup=cancel_kb)
            answer_callback(call["id"])

    elif data.startswith("g_s_"):
        service = data.split("g_s_")[1]
        local_cnts = set([b["country"] for b in number_batches.values() if b["service"] == service and b["numbers"]])
        nexa_cnts = set(bot_settings.get("nexa_services", {}).get(service, {}).keys())
        voltx_cnts = set(bot_settings.get("voltx_services", {}).get(service, {}).keys())
        stex_cnts = set(bot_settings.get("stex_services", {}).get(service, {}).keys())
        all_countries = local_cnts.union(nexa_cnts).union(voltx_cnts).union(stex_cnts)
        
        c_msg = bot_settings["custom_messages"].get("select_country", {})
        raw_txt = c_msg.get("text", "📌 Select a country for {service}:").replace("{service}", service)
        txt = render_body_text(raw_txt)
        
        flags_db = bot_settings.get("premium_flags", {})
        _reset_btn_counter()
        kb = []
        DEFAULT_GLOBE = "5780471598922337683"
        for ci, c in enumerate(all_countries):
            # Step 1: Name / ISO / direct dial-code matching via _find_flag_emoji_id
            emoji_id = _find_flag_emoji_id(c, flags_db)

            # Step 2: Direct key upgrade (if c is a dial code and _find missed it)
            if emoji_id == DEFAULT_GLOBE and c in flags_db:
                emoji_id = flags_db[c].get("id", DEFAULT_GLOBE)

            # Step 3: Fallback — actual numbers in local batches (dial-code prefix match)
            if emoji_id == DEFAULT_GLOBE:
                for b_id, b_data in number_batches.items():
                    if b_data["service"] == service and b_data["country"] == c and b_data["numbers"]:
                        first_num = b_data["numbers"][0]["num"].replace("+", "").replace(" ", "")
                        _, _, num_eid = get_flag_info_from_num(first_num)
                        if num_eid:
                            emoji_id = num_eid
                            break

            # Step 4: Fallback — API service ranges (strip X's → dial-code prefix match)
            if emoji_id == DEFAULT_GLOBE:
                sorted_flag_codes = sorted(flags_db.keys(), key=len, reverse=True)
                for svc_ranges in [
                    bot_settings.get("nexa_services", {}).get(service, {}),
                    bot_settings.get("voltx_services", {}).get(service, {}),
                    bot_settings.get("stex_services", {}).get(service, {}),
                ]:
                    if c not in svc_ranges:
                        continue
                    for rng in svc_ranges[c]:
                        rng_clean = rng.replace("X", "").replace("x", "")
                        for code in sorted_flag_codes:
                            if rng_clean.startswith(code) and "id" in flags_db[code]:
                                emoji_id = flags_db[code]["id"]
                                break
                        if emoji_id != DEFAULT_GLOBE:
                            break
                    if emoji_id != DEFAULT_GLOBE:
                        break

            # Show the country/range OTP rate beside the country name.
            # The OTP listener still resolves the exact matched number's rate.
            country_label = f"{c} {country_rate_text(service, c)}"
            kb.append([{"text": country_label, "icon_custom_emoji_id": emoji_id, "callback_data": f"g_c_{service}_{c}", "style": _rs()}])
        
        _append_custom_btns(kb, c_msg)
            
        kb.append([{"text": "Back", "icon_custom_emoji_id": "5267490665117275176", "callback_data": "get_number_menu", "style": _rs()}])
        edit_message(chat_id, msg_id, txt, reply_markup={"inline_keyboard": kb})
        answer_callback(call["id"])

    elif data == "get_number_menu":
        all_services, txt, kb = _build_services_keyboard("get_number")
        if not all_services:
            answer_callback(call["id"], "❌ No Service Available Right Now", show_alert=True)
            return
        edit_message(chat_id, msg_id, txt, reply_markup={"inline_keyboard": kb})
        answer_callback(call["id"])

    elif data.startswith("g_c_") or data.startswith("c_n_"):
        # 1. Global cooldown check (for all number methods)
        now = time.time()
        if now - user_cooldowns.get(chat_id, 0) < bot_settings["cooldown"]:
            answer_callback(call["id"], f"⌛ Please wait {int(bot_settings['cooldown'] - (now - user_cooldowns.get(chat_id, 0)))}s.", show_alert=True)
            return
        
        # Cooldown update
        user_cooldowns[chat_id] = now
        
        # Expire previous number
        expire_previous_number(chat_id)

        # If coming from search number (old path — should not reach here now)
        if data.startswith("c_n_s_"):
            parts_s = data.split("_")
            query = parts_s[3]
            _svc = parts_s[4] if len(parts_s) > 4 else ""
            service_from_cb = _svc if _svc else None
            
            allowed_countries = (
                bot_settings.get("nexa_search_countries", []) +
                bot_settings.get("voltx_search_countries", []) +
                bot_settings.get("stex_search_countries", [])
            )
            if allowed_countries:
                clean_allowed = [c.replace("X", "").replace("x", "") for c in allowed_countries]
                if not any(query.startswith(c) or c.startswith(query) for c in clean_allowed if c):
                    answer_callback(call["id"], "❌ This country code is not allowed for search!", show_alert=True)
                    return
                
            edit_message(chat_id, msg_id, render_body_text("⌛ <i>Processing... Finding Number...</i>"))
            wait_msg_id = msg_id
            
            found_indices = _search_and_recycle_local(query, chat_id)

            fetched_nums = []
            if not found_indices:
                # 🌟 Try all panels with strict isolation (Nexa → VoltX → Stex)
                _api_num, _api_panel = _fetch_number_via_panels(query, chat_id)
                if _api_num:
                    fetched_nums.append(_api_num)
                    save_local_db()
                else:
                    answer_callback(call["id"], "❌ Number out of stock!", show_alert=True)
                    delete_message(chat_id, wait_msg_id)
                    return
            else:
                random.shuffle(found_indices)
                for b_id, idx in found_indices:
                    if len(fetched_nums) >= bot_settings.get("num_req", 1): break
                    if b_id not in number_batches: continue
                    nb = number_batches[b_id]["numbers"]
                    if idx < 0 or idx >= len(nb): continue
                    n_obj = nb[idx]
                    num_str = n_obj["num"]
                    fetched_nums.append(num_str)
                    n_obj["shares"] += 1
                    n_obj["used_by"].append(chat_id)
                    with _stats_lock:
                        total_assigned_stats += 1
                    if n_obj["shares"] >= bot_settings.get("num_share", 1):
                        if num_str not in used_numbers_list:
                            used_numbers_list.append(num_str)
                save_local_db()
                
            user_active_sessions[chat_id] = {"msg_id": wait_msg_id, "nums": fetched_nums,
                                             "service": service_from_cb or "", "country": "",
                                             "ctx": "search", "query": query,
                                             "cc_codes": _build_cc_codes(fetched_nums), "cc_state": [True] * len(fetched_nums)}
            kb = _rebuild_num_kb(chat_id)
            num_text = render_body_text(_build_num_text(chat_id))
            try:
                edit_message(chat_id, wait_msg_id, num_text, reply_markup={"inline_keyboard": kb})
            except Exception:
                msg_res = send_message(chat_id, num_text, reply_markup={"inline_keyboard": kb})
                if msg_res and msg_res.get("ok") and msg_res.get("result"):
                    user_active_sessions[chat_id]["msg_id"] = msg_res["result"]["message_id"]
            try: answer_callback(call["id"])
            except Exception as e:
                logger.warning(f"Error: {e}")
            return

        # If coming from upload or service
        _cb_sfx = data[4:]  # strip "g_c_" or "c_n_" prefix
        service, _, country = _cb_sfx.partition("_")

        if not service or not country:
            answer_callback(call["id"], "❌ Invalid selection!", show_alert=True)
            return

        available_indices = []
        # Check Local Stock First
        for b_id, b_data in number_batches.items():
            if b_data["service"] == service and b_data["country"] == country:
                for idx, n_obj in enumerate(b_data["numbers"]):
                    if chat_id not in n_obj.get("used_by", []):
                        available_indices.append((b_id, idx))

        # Recycle: if no available numbers, reset all matching numbers
        if not available_indices:
            has_matching = False
            for b_id, b_data in number_batches.items():
                if b_data["service"] == service and b_data["country"] == country:
                    for n_obj in b_data["numbers"]:
                        has_matching = True
                        n_obj["shares"] = 0
                        n_obj["used_by"] = []
            if has_matching:
                for b_id, b_data in number_batches.items():
                    if b_data["service"] == service and b_data["country"] == country:
                        for idx, n_obj in enumerate(b_data["numbers"]):
                            available_indices.append((b_id, idx))

        # IF NO LOCAL STOCK, fetch directly from panel API (strict service+country isolation)
        _api_num = None
        if not available_indices:
            # Try Nexa (only if ON and service+country configured in Nexa)
            if bot_settings.get("nexa_on", False):
                _ns = bot_settings.get("nexa_services", {}).get(service, {}).get(country, [])
                if _ns:
                    _rng = random.choice(_ns)
                    _api_num, _ = try_nexa_get_number(_rng, chat_id, allow_auto=True)
            # Try VoltX (only if ON and service+country configured in VoltX)
            if not _api_num and bot_settings.get("voltx_on", False):
                _vs = bot_settings.get("voltx_services", {}).get(service, {}).get(country, [])
                if _vs:
                    _rng = random.choice(_vs)
                    _api_num, _ = try_voltx_get_number(_rng.replace("X", "").replace("x", ""), chat_id, allow_auto=True)
            # Try Stex (only if ON and service+country configured in Stex)
            if not _api_num and bot_settings.get("stex_on", False):
                _ss = bot_settings.get("stex_services", {}).get(service, {}).get(country, [])
                if _ss:
                    _rng = random.choice(_ss)
                    _api_num, _ = try_stex_get_number(_rng.replace("X", "").replace("x", ""), chat_id, allow_auto=True)
            if not _api_num:
                answer_callback(call["id"], "❌ Number out of stock or range missing!", show_alert=True)
                if data.startswith("c_n_"): delete_message(chat_id, msg_id)
                return

        random.shuffle(available_indices)
        
        # If API number fetched directly, use it; otherwise pick from local stock
        fetched_nums = [_api_num] if _api_num else []
        for b_id, idx in available_indices:
            if len(fetched_nums) >= bot_settings.get("num_req", 1): break
            if b_id not in number_batches: continue
            nb = number_batches[b_id]["numbers"]
            if idx < 0 or idx >= len(nb): continue
            n_obj = nb[idx]
            
            fetched_nums.append(n_obj["num"])
            with _data_lock:
                n_obj["shares"] += 1
                n_obj["used_by"].append(chat_id)
                if n_obj["shares"] >= bot_settings.get("num_share", 1):
                    if n_obj["num"] not in used_numbers_list:
                        used_numbers_list.append(n_obj["num"])
            with _stats_lock:
                total_assigned_stats += 1
        save_local_db()

        if not fetched_nums:
            answer_callback(call["id"], "❌ You have already taken all numbers or stock is empty!", show_alert=True)
            if data.startswith("c_n_"): delete_message(chat_id, msg_id)
            return

        _sess_reg = {"msg_id": msg_id, "nums": fetched_nums, "service": service, "country": country,
                     "ctx": "regular", "cc_codes": _build_cc_codes(fetched_nums), "cc_state": [True] * len(fetched_nums)}
        user_active_sessions[chat_id] = _sess_reg
        kb = _rebuild_num_kb(chat_id)
        text_numbers = render_body_text(_build_num_text(chat_id))
        try:
            edit_message(chat_id, msg_id, text_numbers, reply_markup={"inline_keyboard": kb})
        except Exception as e:
            msg_res = send_message(chat_id, text_numbers, reply_markup={"inline_keyboard": kb})
            if msg_res and msg_res.get("ok") and msg_res.get("result"):
                user_active_sessions[chat_id]["msg_id"] = msg_res["result"]["message_id"]
        try: answer_callback(call["id"])
        except Exception as e:
            logger.warning(f"Error: {e}")

    elif data.startswith("add_cc_") or data.startswith("rem_cc_"):
        # ── Country Code toggle ────────────────────────────────────
        session = user_active_sessions.get(chat_id, {})
        if not session:
            answer_callback(call["id"], "❌ Session expired. Please get a new number.", show_alert=True)
            return

        nums     = session.get("nums", [])
        cc_state = list(session.get("cc_state", [True] * len(nums)))
        # pad if needed
        while len(cc_state) < len(nums):
            cc_state.append(True)

        suffix = data.split("_")[-1]
        if suffix == "all":
            # Toggle all numbers at once
            new_val = data.startswith("add_cc_")
            cc_state = [new_val] * len(cc_state)
        else:
            try:
                idx = int(suffix)
            except Exception:
                answer_callback(call["id"]); return
            if data.startswith("add_cc_"):
                if idx < len(cc_state): cc_state[idx] = True
            else:
                if idx < len(cc_state): cc_state[idx] = False

        session["cc_state"] = cc_state
        user_active_sessions[chat_id] = session

        kb = _rebuild_num_kb(chat_id)
        num_text = render_body_text(_build_num_text(chat_id))
        try:
            edit_message(chat_id, session["msg_id"], num_text, reply_markup={"inline_keyboard": kb})
        except Exception as e:
            logger.warning(f"CC toggle edit error: {e}")
        try: answer_callback(call["id"])
        except Exception: pass

    elif data.startswith("wapp_") or data.startswith("wrej_"):
        # Admin check (need to check User ID)
        user_id_clicked = call.get("from", {}).get("id", 0)
        if not is_admin(user_id_clicked):
            answer_callback(call["id"], "🚫 Only Bot Admins can process withdrawals!", show_alert=True)
            return
            
        action = "APPROVE" if data.startswith("wapp_") else "REJECT"
        req_id = data.replace("wapp_", "").replace("wrej_", "")
        
        if req_id in pending_withdrawals:
            req_data = pending_withdrawals[req_id]
            u_id, amt = req_data["user_id"], req_data["amount"]
            num = req_data["number"]
            full_name = req_data.get("full_name", u_id)
            
            status_text = "APPROVED" if action == "APPROVE" else "REJECTED"
            emoji_icon_id = "6266967801580231067" if action == "APPROVE" else "6267237615720731788"
            _mth = req_data.get('method', '')
            full_num = str(num)
            masked_num = mask_number(full_num, user_id=u_id) if len(full_num) >= 7 else full_num

            def _build_status_text(display_num):
                if is_crypto_method(_mth):
                    _pay = (f"🪙 <b>PAY:</b> <b>{fmt_usd(req_data.get('usd_amount', pkr_to_usd(amt)))} USDT</b> ({str(_mth).split()[-1]})\n"
                            f"💳 <b>BALANCE CUT:</b> {fmt_money(amt)}\n"
                            f"🔗 <b>ADDRESS:</b> <code>{html.escape(str(display_num))}</code>")
                else:
                    # Exact request serial: PAY -> METHOD -> ACCOUNT -> TITLE.
                    _pay = (f"💳 <b>PAY:</b> <b>{fmt_money(amt)}</b> (~{fmt_usd(req_data.get('usd_amount', pkr_to_usd(amt)))})\n"
                            f"🏦 <b>METHOD:</b> {html.escape(str(_mth))}\n"
                            f"📱 <b>ACCOUNT:</b> <code>{html.escape(str(display_num))}</code>\n"
                            f"👤 <b>TITLE:</b> <code>{html.escape(str(req_data.get('acc_title', '-')))}</code>")
                return (f"🎙 <b>WITHDRAWAL {status_text}</b>\n\n"
                        f"👤 <b>USER:</b> <a href='tg://user?id={u_id}'>{html.escape(str(full_name))}</a>\n"
                        f"{_pay}\n\n"
                        f"🧾 <b>REQ ID:</b> {html.escape(str(req_id))}\n"
                        f"👨‍⚖️ <b>PROCESSED BY ADMIN</b>")

            rendered_full_text = render_body_text(_build_status_text(full_num))
            rendered_group_text = render_body_text(_build_status_text(masked_num))
            _reset_btn_counter()
            status_kb = {"inline_keyboard": [[{"text": status_text, "icon_custom_emoji_id": emoji_icon_id, "callback_data": "ignore", "style": "success" if action == "APPROVE" else "danger"}]]}

            # Preserve privacy on status updates: group copies stay masked;
            # owner/admin copies retain the full account number.
            group_ids = set(_withdrawal_group_ids())
            for sm in req_data.get("sent_messages", []):
                try:
                    is_group = sm.get("is_group")
                    if is_group is None:
                        is_group = str(sm.get("chat_id")) in group_ids
                    edit_message(
                        sm["chat_id"], sm["message_id"],
                        rendered_group_text if is_group else rendered_full_text,
                        reply_markup=status_kb,
                    )
                except Exception as e:
                    logger.warning(f"Error: {e}")
            # Also edit the current message where admin clicked, preserving its visibility.
            try:
                current_is_group = str(chat_id) in group_ids
                edit_message(chat_id, msg_id, rendered_group_text if current_is_group else rendered_full_text, reply_markup=status_kb)
            except Exception as e:
                logger.warning(f"Error: {e}")
            
            safe_uid = int(u_id) if str(u_id).lstrip("-").isdigit() else u_id
            if action == "REJECT":
                update_balance(safe_uid, amt)
                try:
                    send_message(safe_uid, render_body_text(f"❌ Your {fmt_money(amt)} withdrawal request has been rejected. The balance has been returned."))
                except Exception as _e:
                    logger.warning(f"Withdrawal reject notify failed for {u_id}: {_e}")
            else:
                try:
                    send_message(safe_uid, render_body_text(f"{PEM['ok']} you of {fmt_money(amt)} withdrawal <b>{req_data['method']}</b> on successfully send do di runs!"))
                except Exception as _e:
                    logger.warning(f"Withdrawal approve notify failed for {u_id}: {_e}")
            
            _update_local_withdrawal(req_id, {"status": "approved" if action == "APPROVE" else "rejected"})
                
            del pending_withdrawals[req_id]
        else:
            answer_callback(call["id"], "❌ Request already processed!", show_alert=True)

# ==========================================
# Polling Loop
# ==========================================
def poll_otp_with_status(number_id, num_str, owner_id, api_key):
    headers = {"X-API-Key": api_key}
    first_iter = True  # mark old OTPs on the first iteration but do not deliver them
    for _ in range(150): # 150 * 2 seconds = 5 Minutes Polling
        try:
            res = _nexa_session.get(f"{NEXA_BASE_URL}/api/v1/numbers/{number_id}/sms", headers=headers, timeout=10)
            try:
                data = res.json()
            except Exception:
                logger.warning(f"Nexa OTP poll: invalid JSON response — {res.text[:120]!r}")
                first_iter = False
                time.sleep(2)
                continue
            # Nexa returns either flat {success, otp, message} or {success, count, data:[{otp, message,...}]}
            sms_list = []
            if data.get("success"):
                if data.get("otp"):
                    # Flat format: {success:true, otp:"...", message:"..."}
                    sms_list = [{"otp": data.get("otp"), "message": data.get("message", ""),
                                 "service": data.get("service", ""), "app_name": data.get("app_name", "")}]
                elif isinstance(data.get("data"), list) and data["data"]:
                    # List format: {success:true, data:[{otp, sms/message, app_name,...}]}
                    sms_list = data["data"]
                elif isinstance(data.get("sms"), list) and data["sms"]:
                    sms_list = data["sms"]
            for sms_item in sms_list:
                otp = str(sms_item.get("otp") or sms_item.get("code") or "")
                msg_text = str(sms_item.get("message") or sms_item.get("sms") or sms_item.get("text") or f"Your code is {otp}")
                if not otp:
                    continue

                # Find OTP with dash or large OTP from full message
                extracted_otp = extract_otp_code(msg_text)
                if extracted_otp and len(extracted_otp) > len(otp):
                    otp = extracted_otp

                # Detect service/app from full message
                app_name = sms_item.get("service") or sms_item.get("app_name") or sms_item.get("app") or "Nexa Service"
                detected_app = detect_service(msg_text)
                if detected_app:
                    app_name = detected_app

                # ── AGE GUARD ────────────────────────────────────────────────
                # Nexa per-number poller: old records may appear.
                # 25h from old OTP kabhi deliver not to do.
                ts_str = str(
                    sms_item.get("received_at") or sms_item.get("created_at") or
                    sms_item.get("sms_time") or sms_item.get("date") or
                    sms_item.get("timestamp") or sms_item.get("createdAt") or ""
                )
                if ts_str and _is_stale_otp(ts_str):
                    continue  # 25h old — skip
                # ─────────────────────────────────────────────────────────────

                unique_id = f"POLL_{number_id}_{otp}"
                if _is_processed(unique_id):
                    continue
                _add_to_processed(unique_id)

                # ── WARMUP GATE ─────────────────────────────────────────────
                # The OTP in the API response was also old.
                # Mark do (dedup for) lekin deliver exactly mat do.
                if first_iter:
                    continue

                # If owner_id=None, still deliver to the group — only the user DM will be skipped
                _record_and_deliver_otp(owner_id, num_str, app_name, msg_text, otp, num_str, "poll_otp_nexa")
                break
        except Exception as e:
            logger.warning(f"poll_otp_with_status iteration error: {e}")
        first_iter = False  # first iteration of after warmup khatam
        time.sleep(2)

def _poll_mauthapi_otp_single(prefix, base_url, default_name, num_str, owner_id, api_key):
    """Shared per-number OTP poller for VoltX and Stex (same mauthapi platform).
    prefix: 'VX' for VoltX, 'STX' for Stex — used for processed_otps deduplication."""
    headers = {"mauthapi": api_key, "User-Agent": "Mozilla/5.0"}
    clean_target = str(num_str).replace("+", "").replace(" ", "").replace("-", "").strip()
    first_iter = True  # mark old OTPs on the first iteration but do not deliver them

    for _ in range(300):  # 300 * 2s = 10 min polling
        try:
            _ms2 = _voltx_session if base_url == VOLTX_BASE_URL else _stex_session
            res = _ms2.get(f"{base_url}/success-otp", headers=headers, timeout=6)
            try:
                data = res.json()
            except Exception:
                logger.warning(f"{prefix} OTP poll: invalid JSON — {res.text[:120]!r}")
                first_iter = False
                time.sleep(2)
                continue
            resp_data = data.get("data", {})
            if isinstance(resp_data, dict):
                otps_list = resp_data.get("otps", [])
            elif isinstance(resp_data, list):
                otps_list = resp_data
            else:
                otps_list = data if isinstance(data, list) else []
            if not isinstance(otps_list, list):
                first_iter = False  # reset warmup on an empty or incorrect response as well
                time.sleep(2)
                continue
            for otp_entry in otps_list:
                # FIX: VoltX/Stex multiple number field names support do
                entry_num = str(
                    otp_entry.get("no_plus_number") or
                    otp_entry.get("full_number") or
                    otp_entry.get("phone_number") or
                    otp_entry.get("number") or ""
                ).replace("+", "").replace(" ", "").replace("-", "").strip()
                if not entry_num:
                    continue
                if entry_num == clean_target or \
                   (len(entry_num) >= 8 and entry_num.endswith(clean_target[-8:])) or \
                   (len(clean_target) >= 8 and clean_target.endswith(entry_num[-8:])):
                    msg_text = otp_entry.get("message", otp_entry.get("sms", otp_entry.get("msg", "")))
                    if not msg_text:
                        continue
                    extracted_otp = extract_otp_code(msg_text)
                    if not extracted_otp:
                        continue
                    otp_id = otp_entry.get("otp_id", "")

                    # ── AGE GUARD ────────────────────────────────────────────
                    # Old records may also appear in the per-number poller.
                    # 25h from old OTP kabhi deliver not to do.
                    ts_str = str(
                        otp_entry.get("received_at") or otp_entry.get("created_at") or
                        otp_entry.get("sms_time") or otp_entry.get("date") or
                        otp_entry.get("timestamp") or otp_entry.get("createdAt") or ""
                    )
                    if ts_str and _is_stale_otp(ts_str):
                        continue  # 25h old — skip
                    # ─────────────────────────────────────────────────────────

                    unique_id = f"{prefix}_{otp_id}" if otp_id else f"{prefix}_{clean_target}_{extracted_otp}"
                    if _is_processed(unique_id):
                        continue
                    _add_to_processed(unique_id)

                    # ── WARMUP GATE ─────────────────────────────────────────
                    # first iteration: that OTP already API in tha that "old" is.
                    # Mark do (dedup for) lekin deliver exactly mat do.
                    if first_iter:
                        continue

                    # If owner_id=None, still deliver to the group — only the user DM will be skipped
                    app_name = detect_service(msg_text) or default_name
                    _record_and_deliver_otp(owner_id, num_str, app_name, msg_text, extracted_otp, clean_target, f"{prefix}_poll")
                    return  # OTP found, stop polling
        except Exception as e:
            logger.warning(f"{prefix}_poll_otp iteration error: {e}")
        first_iter = False  # first iteration of after warmup khatam
        time.sleep(2)


def voltx_poll_otp(num_str, owner_id, api_key):
    """VoltX per-number OTP poller — thin wrapper around _poll_mauthapi_otp_single."""
    _poll_mauthapi_otp_single("VX", VOLTX_BASE_URL, "VoltX SMS", num_str, owner_id, api_key)


def stex_poll_otp(num_str, owner_id, api_key):
    """Stex per-number OTP poller — thin wrapper around _poll_mauthapi_otp_single."""
    _poll_mauthapi_otp_single("STX", STEX_BASE_URL, "Stex SMS", num_str, owner_id, api_key)

def _poll_mauthapi_otps(api_keys, base_url, prefix, default_name, first_run):
    """Shared helper for Stex and VoltX global SMS listeners.
    Both use the same mauthapi platform — same header, same response envelope.
    prefix: 'STX' for Stex, 'VX' for VoltX (used to deduplicate processed OTP IDs)."""
    for api_key in api_keys:
        try:
            headers = {"mauthapi": api_key, "User-Agent": "Mozilla/5.0"}
            _ms3 = _voltx_session if base_url == VOLTX_BASE_URL else _stex_session
            res = _ms3.get(f"{base_url}/success-otp", headers=headers, timeout=10)
            try:
                data = res.json()
            except Exception:
                logger.warning(f"global_sms {prefix}: invalid JSON — {res.text[:120]!r}")
                continue
            resp_data = data.get("data", {})
            if isinstance(resp_data, dict):
                otps_list = resp_data.get("otps", [])
            elif isinstance(resp_data, list):
                otps_list = resp_data
            else:
                otps_list = []
            for item in otps_list:
                # FIX: VoltX/Stex multiple number field names support do (global listener)
                num = str(
                    item.get("no_plus_number") or
                    item.get("full_number") or
                    item.get("phone_number") or
                    item.get("number") or ""
                ).replace("+", "")
                msg_text = str(item.get("message", item.get("sms", item.get("msg", ""))))
                app_name = detect_service(msg_text) or default_name
                otp = extract_otp_code(msg_text) or "CODE"
                otp_id = item.get("otp_id", "")

                # ── AGE GUARD ────────────────────────────────────────────────
                # API response in old records also remain are. 25h from more
                # Never deliver old OTP — even if the dedup window has expired
                # whether the old record was removed or the bot was restarted.
                ts_str = str(
                    item.get("received_at") or item.get("created_at") or
                    item.get("sms_time") or item.get("date") or
                    item.get("timestamp") or item.get("createdAt") or ""
                )
                if ts_str and _is_stale_otp(ts_str):
                    continue  # 25h old — skip, do not deliver
                # ─────────────────────────────────────────────────────────────

                if otp_id:
                    unique_id = f"{prefix}_{otp_id}"
                    dedup_window = 604800  # 7 days — otp_id records remain in the API for a long time
                    # 25h window of place 7 din: old OTP dedup expiry of after again deliver
                    # That will not happen. Age guard is above — a new actual OTP will arrive within 25h.
                    warmup_id = None      # item_id based: a separate warmup key is not needed
                else:
                    unique_id = f"{prefix}_{num}_{otp}"
                    dedup_window = 10    # 10 seconds — only to stop tight-loop spam
                    warmup_id = f"WARMUP_{unique_id}"  # 25h warmup protection key
                # Non-item_id: first WARMUP_ check (25h) — block old OTPs
                if warmup_id and _is_processed(warmup_id, window=90000):
                    continue
                if not _is_processed(unique_id, window=dedup_window) and num:
                    _add_to_processed(unique_id)
                    if first_run:
                        # Also mark the WARMUP_ key on the first run (25-hour protection)
                        if warmup_id:
                            _add_to_processed(warmup_id)
                        continue
                    # Set warmup_id for non-first-run deliveries as well
                    # (25h protection — ensure same OTP is not delivered again after 10s window expires)
                    if warmup_id:
                        _add_to_processed(warmup_id)
                    clean_api_num = str(num).replace("+", "").replace(" ", "").replace("-", "").strip()
                    # FIX: if no owner, still deliver to group (owner_id=None → group delivers, user skips)
                    found_owners = _find_otp_owners(clean_api_num)
                    owner_id = found_owners[0] if found_owners else None
                    _record_and_deliver_otp(owner_id, num, app_name, msg_text, otp, clean_api_num, f"global_sms_{prefix}")
                    # FIX: enforce _OTP_RECV_MAX on otp_received_numbers (VoltX/Stex global listener)
                    with _data_lock:
                        if len(otp_received_numbers) > _OTP_RECV_MAX:
                            keep = set(list(otp_received_numbers)[10000:])
                            otp_received_numbers.clear()
                            otp_received_numbers.update(keep)
        except Exception as e:
            logger.warning(f"global_sms {prefix} key loop error: {e}")
            continue


def _poll_nexa_global_otps(api_keys, warmup):
    """Nexa global SMS listener — same warmup/dedup/deliver shape as
    _poll_mauthapi_otps; extract them here so the global_sms_listener logic
    inside again (duplicate) na write pade. only Nexa of response-shape/endpoint
    fallback (sms/latest → sms/recent) is different, rest dedup/warmup/delivery pattern is the same."""
    for api_key in api_keys:
        try:
            headers = {"X-API-Key": api_key}
            try:
                res = _nexa_session.get(f"{NEXA_BASE_URL}/api/v1/sms/latest", headers=headers, timeout=10)
                data = res.json()
            except Exception as e:
                logger.warning(f"Nexa sms/latest fetch error: {e}")
                try:
                    res = _nexa_session.get(f"{NEXA_BASE_URL}/api/v1/sms/recent", headers=headers, timeout=10)
                    data = res.json()
                except Exception as e2:
                    logger.warning(f"Nexa sms/recent also failed: {e2}")
                    data = {}
            if not (data.get("success") and "data" in data):
                continue
            raw_items = data["data"]
            # Handle both list and dict responses
            if isinstance(raw_items, dict):
                raw_items = list(raw_items.values()) if raw_items else []
            for item in (raw_items if isinstance(raw_items, list) else []):
                num = str(item.get("number", "")).replace("+", "")
                # Handle both 'sms' and 'message' field names
                msg_text = str(item.get("sms") or item.get("message") or item.get("text") or "")

                # 🌟 Fix to detect service/app from full message
                app_name = item.get("app_name", "Unknown")
                detected_app = detect_service(msg_text)
                if detected_app:
                    app_name = detected_app

                otp = extract_otp_code(msg_text) or "CODE"
                sms_id = item.get("id", "")

                # ── AGE GUARD ────────────────────────────────────────────────
                # API in old records remain are. 25h from old OTP kabhi
                # do not deliver — even if dedup expires or bot restarts.
                ts_str = str(
                    item.get("received_at") or item.get("created_at") or
                    item.get("sms_time") or item.get("date") or
                    item.get("timestamp") or item.get("createdAt") or ""
                )
                if ts_str and _is_stale_otp(ts_str):
                    continue  # older than 25h — skip
                # ─────────────────────────────────────────────────────────────

                if sms_id:
                    unique_id = f"NEXA_{num}_{sms_id}"
                    dedup_window = 604800  # 7 days — sms_id records remain in API
                    warmup_id = None      # id-based: a separate warmup key is not needed
                else:
                    unique_id = f"NEXA_{num}_{otp}"
                    dedup_window = 10    # 10 seconds — only to stop tight-loop spam
                    warmup_id = f"WARMUP_{unique_id}"  # 25h warmup protection key

                # Non-id: first WARMUP_ check (25h) — block old OTPs
                if warmup_id and _is_processed(warmup_id, window=90000):
                    continue

                if not _is_processed(unique_id, window=dedup_window) and num:
                    _add_to_processed(unique_id)

                    # Warmup pass: also mark the WARMUP_ key (25-hour protection), but do not deliver
                    if warmup:
                        if warmup_id:
                            _add_to_processed(warmup_id)
                        continue
                    # Set warmup_id for non-warmup deliveries as well
                    # (25h protection — ensure same OTP is not delivered again after 10s window expires)
                    if warmup_id:
                        _add_to_processed(warmup_id)

                    clean_api_num = str(num).replace("+", "").replace(" ", "").replace("-", "").strip()
                    # FIX: if no owner, still deliver to group (owner_id=None → group delivers, user skips)
                    found_owners = _find_otp_owners(clean_api_num)
                    owner_id = found_owners[0] if found_owners else None
                    _record_and_deliver_otp(owner_id, num, app_name, msg_text, otp, clean_api_num, "global_sms_nexa")
                    with _data_lock:
                        if len(otp_received_numbers) > _OTP_RECV_MAX:
                            # first aaye 10000 removed do (oldest entries)
                            keep = set(list(otp_received_numbers)[10000:])
                            otp_received_numbers.clear()
                            otp_received_numbers.update(keep)
        except Exception as e:
            logger.warning(f"global_sms nexa key loop error: {e}")
            continue


def global_sms_listener():
    first_run = True
    while True:
        # Per-service effective warmup: True on bot startup OR when toggled ON / key added mid-run
        nexa_warmup  = first_run or _service_warmup_needed.get("nexa",  False)
        voltx_warmup = first_run or _service_warmup_needed.get("voltx", False)
        stex_warmup  = first_run or _service_warmup_needed.get("stex",  False)

        try:
            # Nexa listener — only poll if toggled ON (shared helper — see _poll_nexa_global_otps)
            _poll_nexa_global_otps(
                bot_settings.get("nexa_keys", []) if bot_settings.get("nexa_on", False) else [],
                nexa_warmup
            )

            # 🌟 Stex + VoltX SMS Global Listeners (shared helper — same API platform)
            _poll_mauthapi_otps(
                bot_settings.get("stex_keys", []) if bot_settings.get("stex_on", False) else [],
                STEX_BASE_URL, "STX", "Stex SMS", stex_warmup
            )
            _poll_mauthapi_otps(
                bot_settings.get("voltx_keys", []) if bot_settings.get("voltx_on", False) else [],
                VOLTX_BASE_URL, "VX", "VoltX SMS", voltx_warmup
            )

        except Exception as e:
            logger.warning(f"global_sms_listener error: {e}")

        # After each poll cycle: reset per-service warmup flags that were just consumed
        if nexa_warmup:
            _service_warmup_needed["nexa"] = False
            if first_run:
                logger.info("Nexa warmup done — old OTPs skipped.")
            else:
                logger.info("Nexa re-enabled warmup done — old OTPs skipped.")
        if stex_warmup:
            _service_warmup_needed["stex"] = False
            if not first_run:
                logger.info("Stex re-enabled warmup done — old OTPs skipped.")
        if voltx_warmup:
            _service_warmup_needed["voltx"] = False
            if not first_run:
                logger.info("VoltX re-enabled warmup done — old OTPs skipped.")

        if first_run:
            first_run = False
            logger.info("Nexa/VoltX/Stex startup warmup done — old OTPs skipped.")
        _save_processed_otps()
        time.sleep(1)  # Check every 1 second (was 5s — faster Nexa/VoltX/Stex delivery)

def flush_old_updates():
    """Skip all pending Telegram updates so old messages are not reprocessed on restart."""
    try:
        res = api_call("getUpdates?offset=-1&timeout=0")
        if res and res.get("ok") and res.get("result") and len(res["result"]) > 0:
            last_id = res["result"][-1].get("update_id", 0)
            if last_id:
                api_call(f"getUpdates?offset={last_id + 1}&timeout=0")
            logger.info(f"Flushed old Telegram updates (last_id={last_id})")
        else:
            logger.info("No pending Telegram updates to flush.")
    except Exception as e:
        logger.warning(f"Could not flush old updates: {e}")

def _panel_session_cleanup():
    """Background thread: close & remove stale panel_sessions every 10 minutes."""
    while True:
        time.sleep(600)
        try:
            # Use index-based keys (0, 1, 2...) matching panel_sessions dict structure
            active_indices = set(range(len(bot_settings.get("panels", []))))
            stale = [k for k in list(panel_sessions.keys()) if k not in active_indices]
            for k in stale:
                sess = panel_sessions.pop(k, None)
                if sess:
                    try: sess.close()
                    except Exception as close_err:
                        logger.warning(f"panel_session close error for key {k}: {close_err}")
            if stale:
                logger.info(f"Cleaned {len(stale)} stale panel session(s).")
        except Exception as e:
            logger.warning(f"panel_session_cleanup error: {e}")

def main():
    global BOT_USERNAME
    res = api_call("getMe")
    if res.get("ok"): BOT_USERNAME = res["result"]["username"]
    logger.info(f"Bot is starting... @{BOT_USERNAME}")
    
    # 🧹 Load previously seen OTP IDs so old OTPs are never resent after restart
    _load_processed_otps()
    
    # 🧹 Flush old updates BEFORE starting background threads
    flush_old_updates()
    
    threading.Thread(target=panel_monitor_thread, daemon=True).start()
    # 🔌 Live Socket Panels — those that are already ON, connect them automatically at boot
    for _sidx, _sp in enumerate(bot_settings.get("panels", [])):
        if _sp.get("type") == "Live Socket Panel" and _sp.get("status") == "ON":
            _start_socket_panel_thread(_sidx)
    threading.Thread(target=auto_backup_thread, daemon=True).start()   # 🛡️ automatic backup
    threading.Thread(target=global_sms_listener, daemon=True).start()
    threading.Thread(target=_panel_session_cleanup, daemon=True).start()
    threading.Thread(target=_cleanup_loop, daemon=True).start()
    logger.info("Background APIs & Global SMS Listener Started!")
    
    # 🌟 PRO-LEVEL FAST SYSTEM: 50 Workers Pool (memory safe)
    executor = ThreadPoolExecutor(max_workers=50)
    
    offset = None
    while True:
        try:
            offset_param = f"&offset={offset}" if offset is not None else ""
            updates = api_call(f"getUpdates?timeout=30{offset_param}")
            if updates and updates.get("ok") and "result" in updates and isinstance(updates["result"], list):
                for update in updates["result"]:
                    offset = update.get("update_id", (offset or 1) - 1) + 1
                    if "message" in update:
                        try:
                            executor.submit(handle_message, update["message"])
                        except Exception as submit_err:
                            logger.warning(f"Executor submit error (message): {submit_err}")
                    elif "callback_query" in update:
                        try:
                            executor.submit(handle_callback, update["callback_query"])
                        except Exception as submit_err:
                            logger.warning(f"Executor submit error (callback): {submit_err}")
            elif updates and not updates.get("ok"):
                # Telegram API error (e.g. 409 Conflict - bot running twice)
                err_code = updates.get("error_code", 0)
                err_desc = updates.get("description", "Unknown error")
                logger.warning(f"Telegram API error {err_code}: {err_desc}")
                if err_code == 409:
                    logger.error("CONFLICT: Another bot instance is running! Shutting down.")
                    break
                time.sleep(5)
        except Exception as e:
            logger.error(f"Main polling error: {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()    
