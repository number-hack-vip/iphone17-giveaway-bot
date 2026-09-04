import os
import asyncio
import sqlite3
import random
import string
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "")

DB = "giveaway.db"


# ================= DATABASE =================

def db():
    return sqlite3.connect(DB)


def init_db():
    con = db()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        entry_id TEXT UNIQUE,
        referred_by INTEGER DEFAULT 0,
        referrals INTEGER DEFAULT 0,
        verified INTEGER DEFAULT 0,
        blocked INTEGER DEFAULT 0,
        joined_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    con.commit()
    con.close()


def setting(key, default=""):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    con.close()
    return row[0] if row else default


def set_setting(key, value):
    con = db()
    cur = con.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
        (key, value)
    )
    con.commit()
    con.close()


def entry_id():
    return "IP17-" + "".join(
        random.choices(string.ascii_uppercase + string.digits, k=8)
    )


def add_user(user, referrer=0):
    con = db()
    cur = con.cursor()

    cur.execute("SELECT id FROM users WHERE id=?", (user.id,))
    exists = cur.fetchone()

    if not exists:
        eid = entry_id()

        cur.execute("""
        INSERT INTO users
        (id, username, first_name, entry_id, referred_by, joined_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user.id,
            user.username or "",
            user.first_name or "",
            eid,
            referrer,
            datetime.now().isoformat()
        ))

        if referrer and referrer != user.id:
            cur.execute(
                "UPDATE users SET referrals=referrals+1 WHERE id=?",
                (referrer,)
            )

    con.commit()
    con.close()


# ================= MENUS =================

def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎁 Giveaway", callback_data="giveaway"),
            InlineKeyboardButton("🎟️ My Entry", callback_data="entry")
        ],
        [
            InlineKeyboardButton("👥 Referrals", callback_data="referrals"),
            InlineKeyboardButton("📊 My Stats", callback_data="stats")
        ],
        [
            InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard"),
            InlineKeyboardButton("📜 Rules", callback_data="rules")
        ],
        [
            InlineKeyboardButton("💬 Support", callback_data="support")
        ]
    ])


def admin_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📈 Statistics", callback_data="admin_stats"),
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton("🔔 Set Notice", callback_data="admin_notice"),
            InlineKeyboardButton("🎁 Giveaway Settings", callback_data="admin_giveaway")
        ],
        [
            InlineKeyboardButton("💰 USDT Address", callback_data="admin_usdt"),
            InlineKeyboardButton("🏆 Select Winner", callback_data="admin_winner")
        ],
        [
            InlineKeyboardButton("🛑 Stop Giveaway", callback_data="admin_stop"),
            InlineKeyboardButton("▶️ Start Giveaway", callback_data="admin_start")
        ]
    ])


# ================= HOME =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    referrer = 0

    if context.args:
        value = context.args[0]
        if value.startswith("ref_"):
            try:
                referrer = int(value.replace("ref_", ""))
            except:
                referrer = 0

    add_user(user, referrer)

    if setting("giveaway_active", "1") != "1":
        await update.message.reply_text(
            "🛑 Giveaway is currently stopped.\n\n"
            "Please check again later."
        )
        return

    notice = setting(
        "notice",
        "🎉 Welcome to the iPhone 17 Pro Giveaway!\n\n"
        "Complete the required steps and get your entry."
    )

    await update.message.reply_text(
        notice,
        reply_markup=main_menu()
    )


# ================= GIVEAWAY =================

async def giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    text = setting(
        "giveaway_text",
        "🎁 iPhone 17 Pro Giveaway\n\n"
        "📱 Prize: iPhone 17 Pro – Cosmic Orange\n"
        "🏆 Winners: As announced in the official giveaway rules\n\n"
        "✅ Join the giveaway\n"
        "✅ Complete the required steps\n"
        "✅ Stay eligible until the giveaway ends"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🎁 Join Giveaway",
                callback_data="verify"
            )
        ]
    ]

    if CHANNEL_USERNAME:
        keyboard.insert(
            0,
            [
                InlineKeyboardButton(
                    "📢 Join Channel",
                    url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}"
                )
            ]
        )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ================= VERIFICATION =================

async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    user = query.from_user

    verified = True

    if CHANNEL_USERNAME:
        try:
            member = await context.bot.get_chat_member(
                CHANNEL_USERNAME,
                user.id
            )

            verified = member.status in [
                "member",
                "administrator",
                "creator"
            ]

        except:
            verified = False

    con = db()
    cur = con.cursor()

    if verified:
        cur.execute(
            "UPDATE users SET verified=1 WHERE id=?",
            (user.id,)
        )
        con.commit()

    con.close()

    if verified:
        await query.edit_message_text(
            "✅ Verification successful!\n\n"
            "🎉 Your giveaway entry is confirmed.\n\n"
            "🎟️ Tap My Entry to see your Entry ID.",
            reply_markup=main_menu()
        )
    else:
        await query.edit_message_text(
            "❌ Verification failed.\n\n"
            "Please join the required channel first and try again.",
            reply_markup=main_menu()
        )


# ================= ENTRY =================

async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    con = db()
    cur = con.cursor()

    cur.execute(
        "SELECT entry_id, verified FROM users WHERE id=?",
        (query.from_user.id,)
    )

    row = cur.fetchone()
    con.close()

    if not row:
        await query.edit_message_text(
            "Please press /start first.",
            reply_markup=main_menu()
        )
        return

    status = "✅ Verified" if row[1] else "⏳ Not verified"

    await query.edit_message_text(
        f"🎟️ Your Entry\n\n"
        f"Entry ID: `{row[0]}`\n"
        f"Status: {status}",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )


# ================= REFERRALS =================

async def referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    user = query.from_user

    con = db()
    cur = con.cursor()

    cur.execute(
        "SELECT referrals FROM users WHERE id=?",
        (user.id,)
    )

    row = cur.fetchone()
    con.close()

    count = row[0] if row else 0

    me = await context.bot.get_me()

    link = f"https://t.me/{me.username}?start=ref_{user.id}"

    await query.edit_message_text(
        f"👥 My Referrals\n\n"
        f"Total referrals: {count}\n\n"
        f"🔗 Your referral link:\n{link}\n\n"
        f"Share this link with your friends.",
        reply_markup=main_menu()
    )


# ================= STATS =================

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    con = db()
    cur = con.cursor()

    cur.execute("""
        SELECT entry_id, referrals, verified
        FROM users WHERE id=?
    """, (query.from_user.id,))

    row = cur.fetchone()
    con.close()

    if not row:
        await query.edit_message_text(
            "Please press /start first.",
            reply_markup=main_menu()
        )
        return

    await query.edit_message_text(
        f"📊 My Stats\n\n"
        f"🎟️ Entry ID: {row[0]}\n"
        f"👥 Referrals: {row[1]}\n"
        f"✅ Verified: {'Yes' if row[2] else 'No'}",
        reply_markup=main_menu()
    )


# ================= LEADERBOARD =================

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    con = db()
    cur = con.cursor()

    cur.execute("""
        SELECT first_name, username, referrals
        FROM users
        WHERE verified=1
        ORDER BY referrals DESC
        LIMIT 10
    """)

    rows = cur.fetchall()

    cur.execute("""
        SELECT COUNT(*) FROM users
        WHERE verified=1 AND referrals >
        (SELECT referrals FROM users WHERE id=?)
    """, (query.from_user.id,))

    rank = (cur.fetchone()[0] or 0) + 1

    con.close()

    text = "🏆 Leaderboard\n\n"

    if not rows:
        text += "No verified participants yet."
    else:
        for i, row in enumerate(rows, 1):
            name = row[0] or row[1] or "User"
            text += f"{i}. {name} — {row[2]} referrals\n"

        text += f"\n📍 Your Rank: #{rank}"

    await query.edit_message_text(
        text,
        reply_markup=main_menu()
    )


# ================= RULES =================

async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    text = setting(
        "rules",
        "📜 Giveaway Rules\n\n"
        "1. One genuine Telegram account per person.\n"
        "2. Duplicate or abusive entries may be removed.\n"
        "3. Eligibility must be maintained until the giveaway ends.\n"
        "4. Winners will be selected according to the published giveaway terms.\n"
        "5. No payment is required unless clearly stated in the official rules.\n\n"
        "⚠️ This giveaway is not affiliated with Apple Inc."
    )

    await query.edit_message_text(
        text,
        reply_markup=main_menu()
    )


# ================= SUPPORT =================

async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    context.user_data["support_mode"] = True

    await query.edit_message_text(
        "💬 Support\n\n"
        "Please send your message now.\n"
        "It will be forwarded to the admin."
    )


async def user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.user_data.get("support_mode"):
        return

    user = update.effective_user

    if user.id == ADMIN_ID:
        return

    msg = update.message

    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"💬 New Support Message\n\n"
            f"User ID: {user.id}\n"
            f"Username: @{user.username or 'none'}\n\n"
            f"Message:\n{msg.text}"
        )

        await msg.reply_text(
            "✅ Your message has been sent to the admin."
        )

    except:
        await msg.reply_text(
            "❌ Support is temporarily unavailable."
        )

    context.user_data["support_mode"] = False


# ================= ADMIN =================

def is_admin(user_id):
    return user_id == ADMIN_ID


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Access denied.")
        return

    await update.message.reply_text(
        "⚙️ Admin Panel",
        reply_markup=admin_menu()
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔ Access denied.")
        return

    data = query.data

    if data == "admin_stats":

        con = db()
        cur = con.cursor()

        cur.execute("SELECT COUNT(*) FROM users")
        total = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM users WHERE verified=1")
        verified = cur.fetchone()[0]

        cur.execute("SELECT COALESCE(SUM(referrals),0) FROM users")
        refs = cur.fetchone()[0]

        con.close()

        await query.edit_message_text(
            f"📈 Statistics\n\n"
            f"👤 Total participants: {total}\n"
            f"✅ Verified: {verified}\n"
            f"👥 Total referrals: {refs}",
            reply_markup=admin_menu()
        )

    elif data == "admin_start":
        set_setting("giveaway_active", "1")
        await query.edit_message_text(
            "▶️ Giveaway started.",
            reply_markup=admin_menu()
        )

    elif data == "admin_stop":
        set_setting("giveaway_active", "0")
        await query.edit_message_text(
            "🛑 Giveaway stopped.",
            reply_markup=admin_menu()
        )

    elif data == "admin_notice":

        context.user_data["admin_action"] = "notice"

        await query.edit_message_text(
            "🔔 Send the new front notification now."
        )

    elif data == "admin_giveaway":

        context.user_data["admin_action"] = "giveaway"

        await query.edit_message_text(
            "🎁 Send the new giveaway information now."
        )

    elif data == "admin_usdt":

        address = setting("usdt_address", "Not set")
        network = setting("usdt_network", "Not set")

        await query.edit_message_text(
            f"💰 USDT Address\n\n"
            f"Address: {address}\n"
            f"Network: {network}\n\n"
            f"Use /setusdt ADDRESS NETWORK to change it.",
            reply_markup=admin_menu()
        )

    elif data == "admin_winner":

        con = db()
        cur = con.cursor()

        cur.execute("""
            SELECT id, first_name, username, entry_id
            FROM users
            WHERE verified=1
            ORDER BY RANDOM()
            LIMIT 1
        """)

        winner = cur.fetchone()
        con.close()

        if winner:
            await query.edit_message_text(
                f"🏆 Selected Winner\n\n"
                f"Name: {winner[1]}\n"
                f"Username: @{winner[2] or 'none'}\n"
                f"Entry ID: {winner[3]}\n\n"
                f"⚠️ Publish the winner only after eligibility is checked.",
                reply_markup=admin_menu()
            )
        else:
            await query.edit_message_text(
                "No verified participants available.",
                reply_markup=admin_menu()
            )

    elif data == "admin_broadcast":

        context.user_data["admin_action"] = "broadcast"

        await query.edit_message_text(
            "📢 Send the broadcast message now."
        )


# ================= ADMIN TEXT =================

async def admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    action = context.user_data.get("admin_action")

    if action == "notice":

        set_setting("notice", update.message.text)

        await update.message.reply_text(
            "✅ Front notification updated."
        )

    elif action == "giveaway":

        set_setting("giveaway_text", update.message.text)

        await update.message.reply_text(
            "✅ Giveaway information updated."
        )

    elif action == "broadcast":

        con = db()
        cur = con.cursor()

        cur.execute("SELECT id FROM users WHERE blocked=0")
        users = cur.fetchall()

        con.close()

        sent = 0

        for row in users:
            try:
                await context.bot.send_message(
                    row[0],
                    update.message.text
                )
                sent += 1
            except:
                pass

        await update.message.reply_text(
            f"📢 Broadcast completed.\nSent: {sent}"
        )

    context.user_data["admin_action"] = None


# ================= USDT =================

async def setusdt(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Use:\n/setusdt YOUR_ADDRESS TRC20"
        )
        return

    address = context.args[0]
    network = context.args[1]

    set_setting("usdt_address", address)
    set_setting("usdt_network", network)

    await update.message.reply_text(
        "✅ USDT address updated.\n\n"
        f"Network: {network}\n"
        f"Address: {address}"
    )


# ================= STARTUP =================

def main():

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("setusdt", setusdt))

    app.add_handler(CallbackQueryHandler(
        admin_callback,
        pattern="^admin_"
    ))

    app.add_handler(CallbackQueryHandler(giveaway, pattern="^giveaway$"))
    app.add_handler(CallbackQueryHandler(verify, pattern="^verify$"))
    app.add_handler(CallbackQueryHandler(entry, pattern="^entry$"))
    app.add_handler(CallbackQueryHandler(referrals, pattern="^referrals$"))
    app.add_handler(CallbackQueryHandler(stats, pattern="^stats$"))
    app.add_handler(CallbackQueryHandler(leaderboard, pattern="^leaderboard$"))
    app.add_handler(CallbackQueryHandler(rules, pattern="^rules$"))
    app.add_handler(CallbackQueryHandler(support, pattern="^support$"))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            user_message
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            admin_text
        )
    )

    print("Bot is running...")

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
app.run_polling()

if __name__ == "__main__":
    main()
