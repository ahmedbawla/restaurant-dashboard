"""
TableMetrics Client Bot — daily card delivery for restaurant owners.

Commands (after login):
  /card        Send your daily report card right now
  /logout      Log out of your account
  /help        Show this list

On first contact (/start):
  - If the user has no password yet  → prompted to create one (+ confirm)
  - If the user already has a password → prompted to enter it

Once authenticated, the user can only access their own data.
Daily card is pushed every morning at 7 AM UTC.
"""

import asyncio
import logging
import os
from datetime import timedelta

import psycopg2
import bcrypt
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
BOT_TOKEN    = os.environ["CLIENT_BOT_TOKEN"]
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Conversation states
WAIT_USERNAME     = 1
WAIT_PASSWORD     = 2   # existing user: enter password
WAIT_NEW_PASSWORD = 3   # new user: create password
WAIT_CONFIRM_PW   = 4   # new user: confirm password


# ── DB ─────────────────────────────────────────────────────────────────────────
def _conn():
    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url)


def _lookup_user(username: str):
    """Return (restaurant_name, email, password_hash) or None if not found."""
    with _conn() as db:
        with db.cursor() as cur:
            cur.execute(
                "SELECT restaurant_name, email, password_hash "
                "FROM users WHERE username = %s",
                (username,),
            )
            return cur.fetchone()


def _set_password(username: str, password: str):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with _conn() as db:
        with db.cursor() as cur:
            cur.execute(
                "UPDATE users SET password_hash = %s WHERE username = %s",
                (hashed, username),
            )
        db.commit()


def _verify_password(stored_hash: str, password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), stored_hash.encode())
    except Exception:
        return False


def _save_chat_id(username: str, chat_id: int):
    with _conn() as db:
        with db.cursor() as cur:
            cur.execute(
                "UPDATE users SET telegram_chat_id = %s WHERE username = %s",
                (chat_id, username),
            )
        db.commit()


# ── Auth helpers ───────────────────────────────────────────────────────────────
def _get_auth(ctx: ContextTypes.DEFAULT_TYPE):
    return ctx.user_data.get("authenticated_as")


def _require_auth(ctx: ContextTypes.DEFAULT_TYPE):
    return _get_auth(ctx) is not None


# ── /start — welcome + login / setup flow ─────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome to TableMetrics*\n\n"
        "TableMetrics gives restaurant owners a daily snapshot of their business — "
        "revenue, covers, average check, labour costs, and smart alerts — "
        "delivered straight to Telegram every morning at 7 AM.\n\n"
        "Please enter your *username* to continue:",
        parse_mode="Markdown",
    )
    return WAIT_USERNAME


async def got_username(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip().lower()
    row = _lookup_user(username)

    if not row:
        await update.message.reply_text(
            "❌ Username not found. Please check your username and try /start again."
        )
        return ConversationHandler.END

    restaurant_name, email, password_hash = row
    ctx.user_data["pending_username"]      = username
    ctx.user_data["pending_restaurant"]    = restaurant_name

    if not password_hash:
        # First time — user needs to create a password
        await update.message.reply_text(
            f"Welcome, *{restaurant_name}*! 🎉\n\n"
            "It looks like this is your first time here.\n"
            "Please create a *password* for your account:",
            parse_mode="Markdown",
        )
        return WAIT_NEW_PASSWORD
    else:
        await update.message.reply_text(
            f"Logging in as *{restaurant_name}*.\n\nEnter your *password*:",
            parse_mode="Markdown",
        )
        return WAIT_PASSWORD


# ── Returning user: enter existing password ────────────────────────────────────
async def got_password(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    username = ctx.user_data.get("pending_username", "")

    row = _lookup_user(username)
    if not row or not row[2]:
        await update.message.reply_text("Something went wrong. Please try /start again.")
        ctx.user_data.clear()
        return ConversationHandler.END

    _, restaurant_name, password_hash = row
    if not _verify_password(password_hash, password):
        await update.message.reply_text(
            "❌ Incorrect password. Please try /start again."
        )
        ctx.user_data.clear()
        return ConversationHandler.END

    return await _finish_login(update, ctx, username, restaurant_name)


# ── New user: create password ──────────────────────────────────────────────────
async def got_new_password(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    if len(password) < 6:
        await update.message.reply_text(
            "Password must be at least 6 characters. Please try again:"
        )
        return WAIT_NEW_PASSWORD

    ctx.user_data["pending_password"] = password
    await update.message.reply_text("Please *confirm* your password:")
    return WAIT_CONFIRM_PW


async def got_confirm_password(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    confirm  = update.message.text.strip()
    password = ctx.user_data.get("pending_password", "")
    username = ctx.user_data.get("pending_username", "")

    if confirm != password:
        await update.message.reply_text(
            "❌ Passwords don't match. Please enter your new password again:"
        )
        ctx.user_data.pop("pending_password", None)
        return WAIT_NEW_PASSWORD

    try:
        _set_password(username, password)
    except Exception as e:
        logger.error(f"Failed to set password for {username}: {e}")
        await update.message.reply_text("Failed to save password. Please try /start again.")
        ctx.user_data.clear()
        return ConversationHandler.END

    ctx.user_data.pop("pending_password", None)
    restaurant_name = ctx.user_data.get("pending_restaurant", username)
    await update.message.reply_text("✅ Password set successfully!")
    return await _finish_login(update, ctx, username, restaurant_name)


# ── Shared login completion ────────────────────────────────────────────────────
async def _finish_login(update: Update, ctx: ContextTypes.DEFAULT_TYPE, username: str, restaurant_name: str):
    ctx.user_data["authenticated_as"] = username
    ctx.user_data["restaurant_name"]  = restaurant_name
    ctx.user_data.pop("pending_username", None)
    ctx.user_data.pop("pending_restaurant", None)

    try:
        _save_chat_id(username, update.effective_chat.id)
    except Exception as e:
        logger.warning(f"Could not save chat_id for {username}: {e}")

    await update.message.reply_text(
        f"✅ Logged in as *{restaurant_name}*!\n\n"
        "Here's what you can do:\n"
        "• /card — get your daily report right now\n"
        "• /logout — sign out\n"
        "• /help — show this list\n\n"
        "Your daily report will also arrive automatically every morning at 7 AM 🕖",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("Cancelled. Type /start to try again.")
    return ConversationHandler.END


# ── /logout ────────────────────────────────────────────────────────────────────
async def cmd_logout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _require_auth(ctx):
        await update.message.reply_text("You're not logged in. Type /start to log in.")
        return
    name = ctx.user_data.get("restaurant_name", "")
    ctx.user_data.clear()
    await update.message.reply_text(
        f"👋 Logged out{' — ' + name if name else ''}. Type /start to log in again."
    )


# ── /help ──────────────────────────────────────────────────────────────────────
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _require_auth(ctx):
        await update.message.reply_text("You're not logged in yet. Type /start to begin.")
        return
    name = ctx.user_data.get("restaurant_name", "")
    await update.message.reply_text(
        f"*TableMetrics* — {name}\n\n"
        "• /card — your daily report card (PNG)\n"
        "• /logout — sign out\n"
        "• /help — show this list",
        parse_mode="Markdown",
    )


# ── Card generation ────────────────────────────────────────────────────────────
async def _deliver_card(chat_id: int, username: str, application: Application):
    from card import fetch_card_data, generate_card_html, render_png_async

    data     = fetch_card_data(username)
    html     = generate_card_html(data)
    png_path = f"/tmp/tablemetrics_{username}.png"
    await render_png_async(html, png_path)

    yest    = data["today"] - timedelta(days=1)
    caption = (
        f"Daily report · {data['restaurant_name']} · "
        + yest.strftime("%B") + " " + str(yest.day) + ", " + str(yest.year)
    )
    with open(png_path, "rb") as f:
        await application.bot.send_photo(chat_id=chat_id, photo=f, caption=caption)


async def cmd_card(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    username = _get_auth(ctx)
    if not username:
        await update.message.reply_text("You need to log in first. Type /start to begin.")
        return

    status = await update.message.reply_text("Generating your daily report…")
    try:
        await _deliver_card(update.effective_chat.id, username, ctx.application)
        await status.delete()
    except Exception as e:
        logger.exception(f"Card failed for {username}")
        await status.edit_text(f"Failed to generate report: {e}")


# ── Catch-all ──────────────────────────────────────────────────────────────────
async def msg_catch_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _require_auth(ctx):
        await update.message.reply_text("Please log in first. Type /start to begin.")


# ── Scheduled 7 AM delivery ───────────────────────────────────────────────────
async def _scheduled_delivery(application: Application):
    logger.info("Running scheduled 7 AM card delivery")
    try:
        with _conn() as db:
            with db.cursor() as cur:
                cur.execute(
                    "SELECT username, telegram_chat_id FROM users "
                    "WHERE telegram_chat_id IS NOT NULL AND username IS NOT NULL"
                )
                rows = cur.fetchall()
    except Exception as e:
        logger.error(f"Scheduled delivery DB error: {e}")
        return

    for username, chat_id in rows:
        try:
            await _deliver_card(int(chat_id), username, application)
            logger.info(f"Delivered card to {username} (chat {chat_id})")
        except Exception as e:
            logger.error(f"Failed delivery for {username}: {e}")


# ── Entry point ────────────────────────────────────────────────────────────────
def main():
    async def post_init(application: Application):
        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(
            lambda: asyncio.create_task(_scheduled_delivery(application)),
            "cron", hour=7, minute=0,
        )
        scheduler.start()
        logger.info("Client bot scheduler started — daily delivery at 07:00 UTC")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    login_conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            WAIT_USERNAME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, got_username)],
            WAIT_PASSWORD:     [MessageHandler(filters.TEXT & ~filters.COMMAND, got_password)],
            WAIT_NEW_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_new_password)],
            WAIT_CONFIRM_PW:   [MessageHandler(filters.TEXT & ~filters.COMMAND, got_confirm_password)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_chat=False,
        per_user=True,
    )

    app.add_handler(login_conv)
    app.add_handler(CommandHandler("card",   cmd_card))
    app.add_handler(CommandHandler("logout", cmd_logout))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg_catch_all))

    logger.info("TableMetrics client bot starting…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
