import os
import random
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Example: @YourChannel
# Leave empty if you don't want channel verification.
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "").strip()

DB_FILE = "giveaway.db"

DEFAULT_PRIZE = "📱 1000 × iPhone 17 Pro — Cosmic Orange"

DEFAULT_FRONT = (
    "🎁 <b>iPhone 17 Pro Giveaway</b>\n\n"
    "📱 Prize: <b>iPhone 17 Pro — Cosmic Orange</b>\n"
    "🏆 Giveaway: Fair & Transparent\n\n"
    "👇 Read the rules and join the giveaway."
)

DEFAULT_RULES = (
    "📜 <b>Giveaway Rules</b>\n\n"
    "1️⃣ One person may have only one entry.\n"
    "2️⃣ Duplicate or abusive entries may be removed.\n"
    "3️⃣ Referral links are unique to each participant.\n"
    "4️⃣ Channel membership may be required for verification.\n"
    "5️⃣ Winners will be selected from eligible verified participants.\n"
    "6️⃣ Winner eligibility will be checked before announcement.\n\n"
    "⚠️ This giveaway is not affiliated with Apple unless explicitly stated."
)

# =========================================================
# DATABASE
# =========================================================


def db():
    con = sqlite3.connect(DB_FILE, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    cur = con.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT DEFAULT '',
            username TEXT DEFAULT '',
            entry_id TEXT UNIQUE,
            referred_by INTEGER DEFAULT NULL,
            referrals INTEGER DEFAULT 0,
            verified INTEGER DEFAULT 0,
            blocked INTEGER DEFAULT 0,
            joined_at TEXT DEFAULT ''
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT DEFAULT '',
            status TEXT DEFAULT 'open',
            created_at TEXT DEFAULT ''
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS winners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            entry_id TEXT,
            selected_at TEXT DEFAULT ''
        )
        """
    )

    defaults = {
        "front": DEFAULT_FRONT,
        "rules": DEFAULT_RULES,
        "prize": DEFAULT_PRIZE,
        "giveaway_status": "ON",
        "usdt_address": "",
        "usdt_network": "",
    }

    for key, value in defaults.items():
        cur.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
            (key, value),
        )

    con.commit()
    con.close()


def get_setting(key):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    con.close()

    if row:
        return row["value"]

    return ""


def set_setting(key, value):
    con = db()
    con.execute(
        """
        INSERT INTO settings(key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        (key, value),
    )
    con.commit()
    con.close()


def make_entry_id(user_id):
    return f"IP17-{user_id % 1000000:06d}"


def add_user(user, referrer_id=None):
    con = db()
    cur = con.cursor()

    cur.execute(
        "SELECT * FROM users WHERE user_id=?",
        (user.id,),
    )

    existing = cur.fetchone()

    if existing:
        cur.execute(
            """
            UPDATE users
            SET first_name=?, username=?
            WHERE user_id=?
            """,
            (
                user.first_name or "",
                user.username or "",
                user.id,
            ),
        )
        con.commit()
        con.close()
        return existing["entry_id"]

    entry_id = make_entry_id(user.id)

    valid_referrer = None

    if referrer_id and referrer_id != user.id:
        cur.execute(
            "SELECT user_id FROM users WHERE user_id=?",
            (referrer_id,),
        )

        ref = cur.fetchone()

        if ref:
            valid_referrer = referrer_id

    now = datetime.now(timezone.utc).isoformat()

    cur.execute(
        """
        INSERT INTO users(
            user_id,
            first_name,
            username,
            entry_id,
            referred_by,
            referrals,
            verified,
            blocked,
            joined_at
        )
        VALUES (?, ?, ?, ?, ?, 0, 0, 0, ?)
        """,
        (
            user.id,
            user.first_name or "",
            user.username or "",
            entry_id,
            valid_referrer,
            now,
        ),
    )

    if valid_referrer:
        cur.execute(
            """
            UPDATE users
            SET referrals=referrals+1
            WHERE user_id=?
            """,
            (valid_referrer,),
        )

    con.commit()
    con.close()

    return entry_id


def get_user(user_id):
    con = db()
    cur = con.cursor()

    cur.execute(
        "SELECT * FROM users WHERE user_id=?",
        (user_id,),
    )

    row = cur.fetchone()
    con.close()

    return row


def set_verified(user_id, verified=True):
    con = db()

    con.execute(
        """
        UPDATE users
        SET verified=?
        WHERE user_id=?
        """,
        (1 if verified else 0, user_id),
    )

    con.commit()
    con.close()


def is_blocked(user_id):
    row = get_user(user_id)

    if not row:
        return False

    return bool(row["blocked"])


def set_blocked(user_id, blocked=True):
    con = db()

    con.execute(
        """
        UPDATE users
        SET blocked=?
        WHERE user_id=?
        """,
        (1 if blocked else 0, user_id),
    )

    con.commit()
    con.close()


# =========================================================
# KEYBOARDS
# =========================================================


def main_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🎁 Giveaway",
                    callback_data="giveaway",
                ),
                InlineKeyboardButton(
                    "🏆 Leaderboard",
                    callback_data="leaderboard",
                ),
            ],
            [
                InlineKeyboardButton(
                    "👥 Referrals",
                    callback_data="referrals",
                ),
                InlineKeyboardButton(
                    "🎟️ My Entry",
                    callback_data="entry",
                ),
            ],
            [
                InlineKeyboardButton(
                    "📊 My Stats",
                    callback_data="stats",
                ),
                InlineKeyboardButton(
                    "📜 Rules",
                    callback_data="rules",
                ),
            ],
            [
                InlineKeyboardButton(
                    "💬 Support",
                    callback_data="support",
                ),
            ],
        ]
    )


def giveaway_keyboard():
    buttons = [
        [
            InlineKeyboardButton(
                "🎁 Join Giveaway",
                callback_data="join",
            )
        ]
    ]

    if CHANNEL_USERNAME:
        buttons.append(
            [
                InlineKeyboardButton(
                    "📢 Open Channel",
                    url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}",
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                "🔙 Home",
                callback_data="home",
            )
        ]
    )

    return InlineKeyboardMarkup(buttons)


def admin_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📊 Statistics",
                    callback_data="admin_stats",
                ),
                InlineKeyboardButton(
                    "🏆 Pick Winner",
                    callback_data="admin_winner",
                ),
            ],
            [
                InlineKeyboardButton(
                    "💰 USDT Settings",
                    callback_data="admin_usdt",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Home",
                    callback_data="home",
                )
            ],
        ]
    )


# =========================================================
# BASIC HELPERS
# =========================================================


async def blocked_check(update):
    user = update.effective_user

    if not user:
        return True

    if is_blocked(user.id):
        if update.callback_query:
            await update.callback_query.answer(
                "🚫 You are blocked.",
                show_alert=True,
            )
        elif update.message:
            await update.message.reply_text(
                "🚫 You are blocked from using this bot."
            )

        return True

    return False


async def home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = get_setting("front")

    if update.callback_query:
        await update.callback_query.answer()

        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
        )

    elif update.message:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=main_keyboard(),
        )


# =========================================================
# /START
# =========================================================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    referrer_id = None

    if context.args:
        arg = context.args[0]

        if arg.startswith("ref_"):
            try:
                referrer_id = int(arg.replace("ref_", ""))
            except ValueError:
                referrer_id = None

    add_user(user, referrer_id)

    if await blocked_check(update):
        return

    await home(update, context)


# =========================================================
# GIVEAWAY
# =========================================================


async def giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await blocked_check(update):
        return

    prize = get_setting("prize")
    status = get_setting("giveaway_status")

    status_text = (
        "🟢 <b>OPEN</b>"
        if status == "ON"
        else "🔴 <b>CLOSED</b>"
    )

    text = (
        "🎁 <b>GIVEAWAY</b>\n\n"
        f"📱 <b>Prize:</b> {prize}\n"
        f"📌 <b>Status:</b> {status_text}\n\n"
        "Tap <b>Join Giveaway</b> to participate."
    )

    if update.callback_query:
        await update.callback_query.answer()

        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=giveaway_keyboard(),
        )


# =========================================================
# CHANNEL VERIFICATION
# =========================================================


async def check_channel_membership(bot, user_id):
    if not CHANNEL_USERNAME:
        return True

    try:
        member = await bot.get_chat_member(
            CHANNEL_USERNAME,
            user_id,
        )

        return member.status in (
            "member",
            "administrator",
            "creator",
        )

    except Exception:
        return False


# =========================================================
# JOIN
# =========================================================


async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if await blocked_check(update):
        return

    user = query.from_user

    status = get_setting("giveaway_status")

    if status != "ON":
        await query.answer(
            "🔴 Giveaway is currently closed.",
            show_alert=True,
        )
        return

    add_user(user)

    verified = await check_channel_membership(
        context.bot,
        user.id,
    )

    if not verified:
        await query.answer(
            "❌ Please join the required channel first.",
            show_alert=True,
        )

        buttons = []

        if CHANNEL_USERNAME:
            buttons.append(
                [
                    InlineKeyboardButton(
                        "📢 Join Channel",
                        url=(
                            "https://t.me/"
                            + CHANNEL_USERNAME.lstrip("@")
                        ),
                    )
                ]
            )

        buttons.append(
            [
                InlineKeyboardButton(
                    "✅ Verify Again",
                    callback_data="verify",
                )
            ]
        )

        buttons.append(
            [
                InlineKeyboardButton(
                    "🔙 Home",
                    callback_data="home",
                )
            ]
        )

        await query.edit_message_text(
            "📢 <b>Channel Verification</b>\n\n"
            "Please join the required channel and then tap "
            "<b>Verify Again</b>.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons),
        )

        return

    set_verified(user.id, True)

    row = get_user(user.id)

    await query.answer(
        "✅ Entry verified!",
        show_alert=True,
    )

    await query.edit_message_text(
        "🎉 <b>You are entered!</b>\n\n"
        f"🎟️ Entry ID: <code>{row['entry_id']}</code>\n\n"
        "Share your referral link to invite friends.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )


# =========================================================
# VERIFY
# =========================================================


async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if await blocked_check(update):
        return

    user = query.from_user

    verified = await check_channel_membership(
        context.bot,
        user.id,
    )

    if verified:
        set_verified(user.id, True)

        await query.answer(
            "✅ Verification successful!",
            show_alert=True,
        )

        await entry(update, context)

    else:
        await query.answer(
            "❌ Channel membership not found.",
            show_alert=True,
        )


# =========================================================
# MY ENTRY
# =========================================================


async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if await blocked_check(update):
        return

    user = query.from_user
    add_user(user)

    row = get_user(user.id)

    verified = (
        "✅ Verified"
        if row["verified"]
        else "❌ Not verified"
    )

    bot_username = context.bot.username

    referral_link = (
        f"https://t.me/{bot_username}?start=ref_{user.id}"
    )

    text = (
        "🎟️ <b>MY ENTRY</b>\n\n"
        f"🆔 Entry ID: <code>{row['entry_id']}</code>\n"
        f"📌 Status: {verified}\n\n"
        "🔗 <b>Your Referral Link:</b>\n"
        f"<code>{referral_link}</code>"
    )

    await query.answer()

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )


# =========================================================
# REFERRALS
# =========================================================


async def referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if await blocked_check(update):
        return

    user = query.from_user
    add_user(user)

    row = get_user(user.id)

    bot_username = context.bot.username

    referral_link = (
        f"https://t.me/{bot_username}?start=ref_{user.id}"
    )

    text = (
        "👥 <b>REFERRALS</b>\n\n"
        f"👤 Successful referrals: <b>{row['referrals']}</b>\n\n"
        "🔗 <b>Your referral link:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        "Share this link with your friends."
    )

    await query.answer()

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )


# =========================================================
# MY STATS
# =========================================================


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if await blocked_check(update):
        return

    user = query.from_user
    add_user(user)

    row = get_user(user.id)

    con = db()
    cur = con.cursor()

    cur.execute(
        """
        SELECT COUNT(*)
        FROM users
        WHERE verified=1
        AND blocked=0
        AND (
            referrals > ?
            OR (referrals = ? AND user_id < ?)
        )
        """,
        (
            row["referrals"],
            row["referrals"],
            user.id,
        ),
    )

    rank = cur.fetchone()[0] + 1

    con.close()

    text = (
        "📊 <b>MY STATS</b>\n\n"
        f"🎟️ Entry ID: <code>{row['entry_id']}</code>\n"
        f"👥 Referrals: <b>{row['referrals']}</b>\n"
        f"🏆 Rank: <b>#{rank}</b>\n"
        f"📌 Verified: "
        f"{'✅ Yes' if row['verified'] else '❌ No'}"
    )

    await query.answer()

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )


# =========================================================
# LEADERBOARD
# =========================================================


async def leaderboard(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if await blocked_check(update):
        return

    con = db()
    cur = con.cursor()

    cur.execute(
        """
        SELECT first_name, referrals
        FROM users
        WHERE verified=1
        AND blocked=0
        ORDER BY referrals DESC, user_id ASC
        LIMIT 10
        """
    )

    rows = cur.fetchall()
    con.close()

    if not rows:
        text = (
            "🏆 <b>LEADERBOARD</b>\n\n"
            "No verified participants yet."
        )
    else:
        lines = [
            "🏆 <b>LEADERBOARD</b>\n"
        ]

        medals = ["🥇", "🥈", "🥉"]

        for i, row in enumerate(rows, start=1):
            medal = medals[i - 1] if i <= 3 else f"{i}."

            name = row["first_name"] or "Participant"

            lines.append(
                f"{medal} {name} — "
                f"<b>{row['referrals']}</b> referrals"
            )

        text = "\n".join(lines)

    await query.answer()

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )


# =========================================================
# RULES
# =======================
# =========================================================
# RULES
# =========================================================

async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if await blocked_check(update):
        return

    await query.answer()

    await query.edit_message_text(
        get_setting("rules"),
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )


# =========================================================
# SUPPORT
# =========================================================

async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if await blocked_check(update):
        return

    context.user_data["support_mode"] = True

    await query.answer()

    await query.edit_message_text(
        "💬 <b>Support</b>\n\n"
        "Apna message yahan bhej dein.\n"
        "Admin ko aapka message support ticket ke through milega.\n\n"
        "❌ Cancel karne ke liye /start bhej dein.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )


async def support_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return

    user = update.effective_user

    if await blocked_check(update):
        return

    if not context.user_data.get("support_mode"):
        return

    message_text = update.message.text or ""

    if not message_text.strip():
        await update.message.reply_text(
            "Please text message bhejein."
        )
        return

    now = datetime.now(timezone.utc).isoformat()

    con = db()
    cur = con.cursor()

    cur.execute(
        """
        INSERT INTO tickets(
            user_id,
            message,
            status,
            created_at
        )
        VALUES (?, ?, 'open', ?)
        """,
        (
            user.id,
            message_text,
            now,
        ),
    )

    ticket_id = cur.lastrowid

    con.commit()
    con.close()

    context.user_data["support_mode"] = False

    await update.message.reply_text(
        "✅ <b>Support ticket created.</b>\n\n"
        f"🎫 Ticket: <code>T-{ticket_id}</code>\n"
        "Admin ko aapka message bhej diya gaya hai.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_keyboard(),
    )

    if ADMIN_ID:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "💬 <b>NEW SUPPORT TICKET</b>\n\n"
                f"🎫 Ticket: <code>T-{ticket_id}</code>\n"
                f"💬 Message:\n{message_text}\n\n"
                "Reply with:\n"
                f"<code>/reply {ticket_id} YOUR MESSAGE</code>"
            ),
            parse_mode=ParseMode.HTML,
        )


# =========================================================
# ADMIN
# =========================================================

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "⛔ Admin only."
        )
        return

    await update.message.reply_text(
        "🛠️ <b>ADMIN PANEL</b>\n\n"
        "Manage your giveaway from here.",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_keyboard(),
    )


async def admin_stats(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query.from_user.id != ADMIN_ID:
        await query.answer(
            "⛔ Admin only.",
            show_alert=True,
        )
        return

    con = db()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM users WHERE verified=1"
    )
    verified = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM users WHERE blocked=1"
    )
    blocked = cur.fetchone()[0]

    cur.execute(
        "SELECT COALESCE(SUM(referrals), 0) FROM users"
    )
    referrals_count = cur.fetchone()[0]

    cur.execute(
        "SELECT COUNT(*) FROM tickets WHERE status='open'"
    )
    open_tickets = cur.fetchone()[0]

    con.close()

    text = (
        "📊 <b>ADMIN STATISTICS</b>\n\n"
        f"👥 Total participants: <b>{total}</b>\n"
        f"✅ Verified: <b>{verified}</b>\n"
        f"👥 Total referrals: <b>{referrals_count}</b>\n"
        f"🚫 Blocked: <b>{blocked}</b>\n"
        f"💬 Open tickets: <b>{open_tickets}</b>"
    )

    await query.answer()

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=admin_keyboard(),
    )


# =========================================================
# ADMIN WINNER
# =========================================================

async def admin_winner(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query.from_user.id != ADMIN_ID:
        await query.answer(
            "⛔ Admin only.",
            show_alert=True,
        )
        return

    con = db()
    cur = con.cursor()

    cur.execute(
        """
        SELECT *
        FROM users
        WHERE verified=1
        AND blocked=0
        ORDER BY RANDOM()
        LIMIT 1
        """
    )

    winner = cur.fetchone()

    if not winner:
        con.close()

        await query.answer(
            "No verified participants available.",
            show_alert=True,
        )
        return

    now = datetime.now(timezone.utc).isoformat()

    cur.execute(
        """
        INSERT INTO winners(
            user_id,
            entry_id,
            selected_at
        )
        VALUES (?, ?, ?)
        """,
        (
            winner["user_id"],
            winner["entry_id"],
            now,
        ),
    )

    con.commit()
    con.close()

    text = (
        "🏆 <b>WINNER SELECTED</b>\n\n"
        f"🎟️ Entry ID: "
        f"<code>{winner['entry_id']}</code>\n\n"
        "⚠️ Verify eligibility before publicly announcing "
        "the winner."
    )

    await query.answer(
        "Winner selected.",
        show_alert=True,
    )

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=admin_keyboard(),
    )


# =========================================================
# USDT SETTINGS
# =========================================================

async def admin_usdt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query.from_user.id != ADMIN_ID:
        await query.answer(
            "⛔ Admin only.",
            show_alert=True,
        )
        return

    address = get_setting("usdt_address")
    network = get_setting("usdt_network")

    address_display = (
        f"<code>{address}</code>"
        if address
        else "<i>Not set</i>"
    )

    network_display = (
        network
        if network
        else "<i>Not set</i>"
    )

    text = (
        "💰 <b>USDT SETTINGS</b>\n\n"
        f"Address: {address_display}\n"
        f"Network: {network_display}\n\n"
        "Set/change with:\n"
        "<code>/setusdt ADDRESS NETWORK</code>\n\n"
        "⚠️ Never ask users for money in exchange "
        "for guaranteed giveaway winnings."
    )

    await query.answer()

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=admin_keyboard(),
    )


async def setusdt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "⛔ Admin only."
        )
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage:\n"
            "<code>/setusdt ADDRESS NETWORK</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    address = context.args[0]
    network = context.args[1]

    set_setting("usdt_address", address)
    set_setting("usdt_network", network)

    await update.message.reply_text(
        "✅ USDT settings updated successfully."
    )


# =========================================================
# ADMIN SETTINGS COMMANDS
# =========================================================

async def setfront(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.effective_user.id != ADMIN_ID:
        return

    text = update.message.text or ""
    content = text[len("/setfront"):].strip()

    if not content:
        await update.message.reply_text(
            "Usage:\n/setfront Your front notification"
        )
        return

    set_setting("front", content)

    await update.message.reply_text(
        "✅ Front notification updated."
    )


async def setprize(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.effective_user.id != ADMIN_ID:
        return

    content = " ".join(context.args).strip()

    if not content:
        await update.message.reply_text(
            "Usage:\n/setprize Your prize text"
        )
        return

    set_setting("prize", content)

    await update.message.reply_text(
        "✅ Prize updated."
    )


async def setrules(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.effective_user.id != ADMIN_ID:
        return

    text = update.message.text or ""
    content = text[len("/setrules"):].strip()

    if not content:
        await update.message.reply_text(
            "Usage:\n/setrules Your rules"
        )
        return

    set_setting("rules", content)

    await update.message.reply_text(
        "✅ Rules updated."
    )


async def giveaway_on(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.effective_user.id != ADMIN_ID:
        return

    set_setting("giveaway_status", "ON")

    await update.message.reply_text(
        "🟢 Giveaway is now OPEN."
    )


async def giveaway_off(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.effective_user.id != ADMIN_ID:
        return

    set_setting("giveaway_status", "OFF")

    await update.message.reply_text(
        "🔴 Giveaway is now CLOSED."
    )


# =========================================================
# ADMIN REPLY
# =========================================================

async def reply_ticket(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.effective_user.id != ADMIN_ID:
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage:\n/reply TICKET_ID message"
        )
        return

    try:
        ticket_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid ticket ID."
        )
        return

    reply_text = " ".join(context.args[1:]).strip()

    con = db()
    cur = con.cursor()

    cur.execute(
        """
        SELECT *
        FROM tickets
        WHERE ticket_id=?
        """,
        (ticket_id,),
    )

    ticket = cur.fetchone()

    if not ticket:
        con.close()

        await update.message.reply_text(
            "❌ Ticket not found."
        )
        return

    cur.execute(
        """
        UPDATE tickets
        SET status='closed'
        WHERE ticket_id=?
        """,
        (ticket_id,),
    )

    con.commit()
    con.close()

    try:
        await context.bot.send_message(
            chat_id=ticket["user_id"],
            text=(
                "💬 <b>Support Reply</b>\n\n"
                f"{reply_text}\n\n"
                f"🎫 Ticket: <code>T-{ticket_id}</code>"
            ),
            parse_mode=ParseMode.HTML,
        )

        await update.message.reply_text(
            "✅ Reply sent to the user."
        )

    except Exception:
        await update.message.reply_text(
            "❌ Could not deliver the reply."
        )


# =========================================================
# CALLBACK ROUTER
# =========================================================

async def callback_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not query:
        return

    data = query.data

    if data == "home":
        await home(update, context)

    elif data == "giveaway":
        await giveaway(update, context)

    elif data == "join":
        await join(update, context)

    elif data == "verify":
        await verify(update, context)

    elif data == "entry":
        await entry(update, context)

    elif data == "referrals":
        await referrals(update, context)

    elif data == "stats":
        await stats(update, context)

    elif data == "leaderboard":
        await leaderboard(update, context)

    elif data == "rules":
        await rules(update, context)

    elif data == "support":
        await support(update, context)

    elif data == "admin_stats":
        await admin_stats(update, context)

    elif data == "admin_winner":
        await admin_winner(update, context)

    elif data == "admin_usdt":
        await admin_usdt(update, context)

    else:
        await query.answer("Unknown action.")


# =========================================================
# RENDER HEALTH SERVER
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/plain",
        )
        self.end_headers()

        self.wfile.write(
            b"iPhone 17 Giveaway Bot is running."
        )

    def log_message(self, format, *args):
        return


def start_health_server():
    port = int(os.getenv("PORT", "10000"))

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler,
    )

    server.serve_forever()


# =========================================================
# MAIN
# =========================================================

def main():

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable is missing."
        )

    if not ADMIN_ID:
        raise RuntimeError(
            "ADMIN_ID environment variable is missing."
        )

    init_db()

    health_thread = threading.Thread(
        target=start_health_server,
        daemon=True,
    )

    health_thread.start()

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("admin", admin)
    )

    app.add_handler(
        CommandHandler("setusdt", setusdt)
    )

    app.add_handler(
        CommandHandler("setfront", setfront)
    )

    app.add_handler(
        CommandHandler("setprize", setprize)
    )

    app.add_handler(
        CommandHandler("setrules", setrules)
    )

    app.add_handler(
        CommandHandler("giveaway_on", giveaway_on)
    )

    app.add_handler(
        CommandHandler("giveaway_off", giveaway_off)
    )

    app.add_handler(
        CommandHandler("reply", reply_ticket)
    )

    app.add_handler(
        CallbackQueryHandler(callback_router)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            support_message,
        )
    )

    print("iPhone 17 Giveaway Bot is running...")

    app.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
