import os
import sqlite3
import random
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# =========================================================
# SETTINGS
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "").replace("@", "")

DB_NAME = "giveaway.db"

# =========================================================
# RENDER HEALTH SERVER
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"iPhone 17 Giveaway Bot is running!")

    def log_message(self, format, *args):
        pass


def start_health_server():
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print("Health server started on port", port)
    server.serve_forever()


# =========================================================
# DATABASE
# =========================================================

def db():
    return sqlite3.connect(DB_NAME)


def init_db():
    con = db()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            referrer INTEGER DEFAULT NULL,
            referrals INTEGER DEFAULT 0,
            verified INTEGER DEFAULT 0,
            blocked INTEGER DEFAULT 0,
            entry_id TEXT UNIQUE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    defaults = {
        "giveaway_title": "🎁 iPhone 17 Pro Giveaway",
        "prize": "📱 iPhone 17 Pro — Cosmic Orange",
        "instructions": (
            "🎉 Welcome to the iPhone 17 Pro Giveaway!\n\n"
            "Complete the required steps and verify your entry.\n\n"
            "No payment is required to participate."
        ),
        "rules": (
            "📜 Giveaway Rules\n\n"
            "1. One account = one entry.\n"
            "2. Duplicate/fake entries may be removed.\n"
            "3. Referrals must be genuine users.\n"
            "4. Winner eligibility will be checked before announcement.\n"
            "5. This giveaway is not affiliated with Apple Inc."
        ),
        "usdt_address": "Not set",
        "usdt_network": "TRC20",
        "support": "💬 Contact the giveaway admin through this bot."
    }

    for key, value in defaults.items():
        cur.execute(
            "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
            (key, value)
        )

    con.commit()
    con.close()


def get_setting(key):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    con.close()
    return row[0] if row else ""


def set_setting(key, value):
    con = db()
    cur = con.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
        (key, value)
    )
    con.commit()
    con.close()


# =========================================================
# USER FUNCTIONS
# =========================================================

def add_user(user, referrer=None):
    con = db()
    cur = con.cursor()

    cur.execute("SELECT id FROM users WHERE id=?", (user.id,))
    exists = cur.fetchone()

    if not exists:
        entry_id = "IP17-" + "".join(
            random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=8)
        )

        cur.execute("""
            INSERT INTO users
            (id, username, first_name, referrer, entry_id)
            VALUES (?, ?, ?, ?, ?)
        """, (
            user.id,
            user.username or "",
            user.first_name or "",
            referrer,
            entry_id
        ))

        if referrer and referrer != user.id:
            cur.execute(
                "UPDATE users SET referrals=referrals+1 WHERE id=?",
                (referrer,)
            )

    con.commit()
    con.close()


def get_user(user_id):
    con = db()
    cur = con.cursor()
    cur.execute(
        "SELECT id, username, first_name, referrals, verified, blocked, entry_id "
        "FROM users WHERE id=?",
        (user_id,)
    )
    row = cur.fetchone()
    con.close()
    return row


def verify_user(user_id):
    con = db()
    cur = con.cursor()
    cur.execute(
        "UPDATE users SET verified=1 WHERE id=?",
        (user_id,)
    )
    con.commit()
    con.close()


def total_users():
    con = db()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    n = cur.fetchone()[0]
    con.close()
    return n


def verified_users():
    con = db()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE verified=1")
    n = cur.fetchone()[0]
    con.close()
    return n


# =========================================================
# MAIN MENU
# =========================================================

def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎁 Giveaway", callback_data="giveaway"),
            InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")
        ],
        [
            InlineKeyboardButton("👥 Referrals", callback_data="referrals"),
            InlineKeyboardButton("🎟️ My Entry", callback_data="entry")
        ],
        [
            InlineKeyboardButton("📊 My Stats", callback_data="stats"),
            InlineKeyboardButton("📜 Rules", callback_data="rules")
        ],
        [
            InlineKeyboardButton("💬 Support", callback_data="support")
        ]
    ])


# =========================================================
# START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    referrer = None

    if context.args:
        try:
            referrer = int(context.args[0])
        except:
            referrer = None

    add_user(user, referrer)

    text = (
        "🍊 <b>iPhone 17 Pro Giveaway</b>\n\n"
        "📱 <b>Prize:</b> iPhone 17 Pro — Cosmic Orange\n\n"
        "🎉 Welcome!\n"
        "Tap the buttons below to participate.\n\n"
        "⚠️ No payment is required to enter."
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )


# =========================================================
# GIVEAWAY
# =========================================================

async def giveaway(update, context):

    query = update.callback_query
    await query.answer()

    text = (
        "🎁 <b>iPhone 17 Pro Giveaway</b>\n\n"
        f"{get_setting('prize')}\n\n"
        f"{get_setting('instructions')}"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🎟️ Join Giveaway",
                callback_data="join"
            )
        ],
        [
            InlineKeyboardButton(
                "✅ Verify Entry",
                callback_data="verify"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Back",
                callback_data="home"
            )
        ]
    ]

    if CHANNEL_USERNAME:
        keyboard.insert(
            0,
            [
                InlineKeyboardButton(
                    "📢 Join Official Channel",
                    url=f"https://t.me/{CHANNEL_USERNAME}"
                )
            ]
        )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================================================
# JOIN
# =========================================================

async def join(update, context):

    query = update.callback_query
    await query.answer()

    user = get_user(query.from_user.id)

    if not user:
        add_user(query.from_user)
        user = get_user(query.from_user.id)

    await query.edit_message_text(
        "🎟️ <b>Your giveaway entry has been created!</b>\n\n"
        f"🆔 Entry ID: <code>{user[6]}</code>\n\n"
        "Now complete the required steps and tap "
        "<b>Verify Entry</b>.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ Verify Entry",
                    callback_data="verify"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Back",
                    callback_data="home"
                )
            ]
        ])
    )


# =========================================================
# VERIFY
# =========================================================

async def verify(update, context):

    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if CHANNEL_USERNAME:

        try:
            member = await context.bot.get_chat_member(
                f"@{CHANNEL_USERNAME}",
                user_id
            )

            if member.status in ["left", "kicked"]:
                await query.edit_message_text(
                    "❌ <b>Verification failed.</b>\n\n"
                    "Please join the official channel first.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(
                                "📢 Join Channel",
                                url=f"https://t.me/{CHANNEL_USERNAME}"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "🔄 Check Again",
                                callback_data="verify"
                            )
                        ]
                    ])
                )
                return

        except Exception:
            pass

    verify_user(user_id)

    user = get_user(user_id)

    await query.edit_message_text(
        "✅ <b>Entry Verified!</b>\n\n"
        f"🎟️ Entry ID: <code>{user[6]}</code>\n"
        f"👥 Referrals: {user[3]}\n\n"
        "Good luck! 🍀",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )


# =========================================================
# ENTRY
# =========================================================

async def entry(update, context):

    query = update.callback_query
    await query.answer()

    user = get_user(query.from_user.id)

    if not user:
        add_user(query.from_user)
        user = get_user(query.from_user.id)

    status = "✅ Verified" if user[4] else "⏳ Not verified"

    await query.edit_message_text(
        "🎟️ <b>My Entry</b>\n\n"
        f"🆔 Entry ID: <code>{user[6]}</code>\n"
        f"📌 Status: {status}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 Back",
                    callback_data="home"
                )
            ]
        ])
    )


# =========================================================
# REFERRALS
# =========================================================

async def referrals(update, context):

    query = update.callback_query
    await query.answer()

    user = get_user(query.from_user.id)

    if not user:
        add_user(query.from_user)
        user = get_user(query.from_user.id)

    me = await context.bot.get_me()

    link = f"https://t.me/{me.username}?start={query.from_user.id}"

    await query.edit_message_text(
        "👥 <b>My Referrals</b>\n\n"
        f"👤 Successful referrals: <b>{user[3]}</b>\n\n"
        "🔗 Your personal referral link:\n"
        f"<code>{link}</code>\n\n"
        "Share this link with your friends.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 Back",
                    callback_data="home"
                )
            ]
        ])
    )


# =========================================================
# STATS
# =========================================================

async def stats(update, context):

    query = update.callback_query
    await query.answer()

    user = get_user(query.from_user.id)

    if not user:
        add_user(query.from_user)
        user = get_user(query.from_user.id)

    rank_con = db()
    cur = rank_con.cursor()

    cur.execute("""
        SELECT COUNT(*) + 1
        FROM users
        WHERE referrals > ?
    """, (user[3],))

    rank = cur.fetchone()[0]
    rank_con.close()

    status = "Verified ✅" if user[4] else "Not verified ⏳"

    await query.edit_message_text(
        "📊 <b>My Stats</b>\n\n"
        f"🎟️ Entry: <code>{user[6]}</code>\n"
        f"👥 Referrals: <b>{user[3]}</b>\n"
        f"🏆 Rank: <b>#{rank}</b>\n"
        f"📌 Status: {status}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 Back",
                    callback_data="home"
                )
            ]
        ])
    )


# =========================================================
# LEADERBOARD
# =========================================================

async def leaderboard(update, context):

    query = update.callback_query
    await query.answer()

    con = db()
    cur = con.cursor()

    cur.execute("""
        SELECT first_name, username, referrals
        FROM users
        WHERE blocked=0
        ORDER BY referrals DESC
        LIMIT 10
    """)

    rows = cur.fetchall()
    con.close()

    text = "🏆 <b>Leaderboard</b>\n\n"

    if not rows:
        text += "No participants yet."
    else:
        medals = ["🥇", "🥈", "🥉"]

        for i, row in enumerate(rows, 1):
            name = row[0] or "User"
            refs = row[2]

            medal = medals[i - 1] if i <= 3 else f"{i}."

            text += f"{medal} {name} — {refs} referrals\n"

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 Back",
                    callback_data="home"
                )
            ]
        ])
    )


# =========================================================
# RULES
# =========================================================

async def rules(update, context):

    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        get_setting("rules"),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 Back",
                    callback_data="home"
                )
            ]
        ])
    )


# =========================================================
# SUPPORT
# =========================================================

async def support(update, context):

    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        get_setting("support"),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 Back",
                    callback_data="home"
                )
            ]
        ])
    )


# =========================================================
# HOME
# =========================================================

async def home(update, context):

    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "🏠 <b>iPhone 17 Pro Giveaway</b>\n\n"
        "Choose an option below:",
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )


# =========================================================
# ADMIN PANEL
# =========================================================

def admin_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📊 Statistics",
                callback_data="admin_stats"
            )
        ],
        [
            InlineKeyboardButton(
                "🏆 Pick Winner",
                callback_data="admin_winner"
            )
        ],
        [
            InlineKeyboardButton(
                "💰 USDT Address",
                callback_data="admin_usdt"
            )
        ]
    ])


async def admin(update, context):

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only.")
        return

    await update.message.reply_text(
        "👑 <b>Admin Panel</b>",
        parse_mode="HTML",
        reply_markup=admin_keyboard()
    )


# =========================================================
# ADMIN CALLBACKS
# =========================================================

async def admin_stats(update, context):

    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    await query.edit_message_text(
        "📊 <b>Giveaway Statistics</b>\n\n"
        f"👥 Total participants: <b>{total_users()}</b>\n"
        f"✅ Verified participants: <b>{verified_users()}</b>\n",
        parse_mode="HTML",
        reply_markup=admin_keyboard()
    )


async def admin_winner(update, context):

    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    con = db()
    cur = con.cursor()

    cur.execute("""
        SELECT id, first_name, username, entry_id
        FROM users
        WHERE verified=1 AND blocked=0
        ORDER BY RANDOM()
        LIMIT 1
    """)

    winner = cur.fetchone()
    con.close()

    if not winner:
        text = "❌ No verified participants available."
    else:
        text = (
            "🏆 <b>Random Winner Selected</b>\n\n"
            f"👤 Name: {winner[1]}\n"
            f"🆔 Entry ID: <code>{winner[3]}</code>\n\n"
            "⚠️ Verify eligibility before publicly announcing the winner."
        )

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=admin_keyboard()
    )


async def admin_usdt(update, context):

    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    address = get_setting("usdt_address")
    network = get_setting("usdt_network")

    await query.edit_message_text(
        "💰 <b>USDT Settings</b>\n\n"
        f"Address: <code>{address}</code>\n"
        f"Network: <b>{network}</b>\n\n"
        "To change it use:\n"
        "<code>/setusdt ADDRESS NETWORK</code>",
        parse_mode="HTML",
        reply_markup=admin_keyboard()
    )


# =========================================================
# SET USDT
# =========================================================

async def setusdt(update, context):

    if update.effective_user.id != ADMIN_ID:
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Use:\n"
            "<code>/setusdt ADDRESS TRC20</code>",
            parse_mode="HTML"
        )
        return

    address = context.args[0]
    network = context.args[1]

    set_setting("usdt_address", address)
    set_setting("usdt_network", network)

    await update.message.reply_text(
        "✅ USDT address updated successfully."
    )


# =========================================================
# CALLBACK ROUTER
# =========================================================

async def callback_router(update, context):

    query = update.callb
