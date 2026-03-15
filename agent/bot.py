"""
Telegram bot — control the coding agent from your phone.

Commands:
  /run              Trigger the agent now
  /deploy           Merge latest agent branch to main and push live
  /reject           Delete the latest agent branch
  /status           Show pending branch + last run summary
  /focus [topic]    Tell the agent what to work on next
  /help             Show this list
"""

import asyncio
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from runner import run_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN     = os.environ["TELEGRAM_BOT_TOKEN"]
OWNER_CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
GITHUB_TOKEN  = os.environ["GITHUB_TOKEN"]
GITHUB_REPO   = os.environ.get("GITHUB_REPO", "ahmedbawla/restaurant-dashboard")

STATE_FILE = Path("/tmp/agent_state.json")


# ── State persistence ─────────────────────────────────────────────────────────
def _load() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"focus": None, "last_branch": None, "last_summary": "No agent run yet."}


def _save(state: dict):
    STATE_FILE.write_text(json.dumps(state))


def _is_owner(update: Update) -> bool:
    return update.effective_chat.id == OWNER_CHAT_ID


# ── Command handlers ──────────────────────────────────────────────────────────
async def cmd_run(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    state = _load()
    await update.message.reply_text("🤖 Agent running… this takes 2–5 minutes.")
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: run_agent(
                github_token=GITHUB_TOKEN,
                github_repo=GITHUB_REPO,
                anthropic_api_key=ANTHROPIC_KEY,
                focus=state["focus"],
            ),
        )
        state["last_branch"]  = result["branch"]
        state["last_summary"] = result["summary"]
        _save(state)
        await update.message.reply_text(
            f"✅ *Done!*\n\nBranch: `{result['branch']}`\n\n"
            f"{result['summary']}\n\n"
            f"/deploy to push live · /reject to discard",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.exception("Agent run failed")
        await update.message.reply_text(f"❌ Agent failed:\n{e}")


async def cmd_deploy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    state = _load()
    branch = state.get("last_branch")
    if not branch:
        await update.message.reply_text("Nothing to deploy. Run /run first.")
        return

    repo_url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"
    await update.message.reply_text(f"🚀 Merging `{branch}` into main…", parse_mode="Markdown")

    def _do():
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "clone", repo_url, tmpdir], check=True, capture_output=True)
            subprocess.run("git config user.email 'agent@dashboard.bot'", shell=True, cwd=tmpdir)
            subprocess.run("git config user.name 'Dashboard Agent'", shell=True, cwd=tmpdir)
            subprocess.run(f"git fetch origin {branch}", shell=True, cwd=tmpdir, check=True)
            subprocess.run(
                f"git merge --no-ff origin/{branch} -m 'Deploy: {branch}'",
                shell=True, cwd=tmpdir, check=True, capture_output=True,
            )
            subprocess.run("git push origin main", shell=True, cwd=tmpdir, check=True)

    try:
        await asyncio.get_event_loop().run_in_executor(None, _do)
        state["last_branch"] = None
        _save(state)
        await update.message.reply_text(
            f"✅ Deployed! `{branch}` is now live on main.\n"
            "Streamlit Cloud will redeploy automatically.",
            parse_mode="Markdown",
        )
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode() if e.stderr else str(e)
        await update.message.reply_text(f"❌ Deploy failed:\n{err[:500]}")


async def cmd_reject(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    state = _load()
    branch = state.get("last_branch")
    if not branch:
        await update.message.reply_text("Nothing to reject.")
        return

    repo_url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"

    def _do():
        subprocess.run(
            f"git push {repo_url} --delete {branch}",
            shell=True, check=True, capture_output=True,
        )

    try:
        await asyncio.get_event_loop().run_in_executor(None, _do)
        state["last_branch"] = None
        _save(state)
        await update.message.reply_text(
            f"🗑️ Rejected — branch `{branch}` deleted.", parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Could not delete branch: {e}")


async def cmd_focus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    state = _load()
    state["focus"] = " ".join(ctx.args) if ctx.args else None
    _save(state)
    if state["focus"]:
        await update.message.reply_text(
            f"🎯 Next run will focus on: *{state['focus']}*", parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("Focus cleared — agent will choose freely next run.")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    state = _load()
    branch  = state.get("last_branch") or "none"
    focus   = state.get("focus")       or "none (agent chooses)"
    summary = state.get("last_summary", "No run yet.")
    await update.message.reply_text(
        f"📋 *Status*\n\n"
        f"Pending branch: `{branch}`\n"
        f"Focus: {focus}\n\n"
        f"*Last summary:*\n{summary}",
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    await update.message.reply_text(
        "🤖 *Dashboard Agent*\n\n"
        "/run — trigger agent now\n"
        "/deploy — merge latest changes to main & go live\n"
        "/reject — delete latest agent branch\n"
        "/status — show pending branch & last summary\n"
        "/focus [topic] — set what agent works on next\n"
        "  e.g. `/focus improve the payroll charts`\n"
        "/help — this message\n\n"
        "_Runs automatically every night at 2 AM UTC_",
        parse_mode="Markdown",
    )


# ── Chat handler ─────────────────────────────────────────────────────────────
_CHAT_SYSTEM = """You are an AI assistant for a restaurant owner who uses the TableMetrics dashboard.
The dashboard has these sections: Sales & Revenue, Payroll (Paychex), Spending & Expenses (QuickBooks), Inventory, and Reports.

Help the owner:
- Understand their restaurant metrics and what they mean
- Make business decisions (staffing, pricing, cost control)
- Interpret numbers they paste or describe to you
- Answer general restaurant management questions

Be concise and practical. You don't have live access to their database, but they can paste numbers and you'll analyze them.
If they ask you to make a code change or improvement, tell them to use /focus followed by /run instead."""

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return

    state = _load()
    history = state.get("chat_history", [])
    user_text = update.message.text

    await ctx.bot.send_chat_action(update.effective_chat.id, "typing")

    history.append({"role": "user", "content": user_text})
    # Keep last 30 messages to stay within token limits
    if len(history) > 30:
        history = history[-30:]

    import anthropic as _anthropic
    client = _anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    resp = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=_CHAT_SYSTEM,
        messages=history,
    )
    reply = resp.content[0].text

    history.append({"role": "assistant", "content": reply})
    state["chat_history"] = history
    _save(state)

    await update.message.reply_text(reply)


async def cmd_clearchat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    state = _load()
    state["chat_history"] = []
    _save(state)
    await update.message.reply_text("💬 Conversation cleared.")


# ── Nightly run ───────────────────────────────────────────────────────────────
async def nightly_run(app: Application):
    state = _load()
    logger.info("Nightly agent run starting")
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: run_agent(
                github_token=GITHUB_TOKEN,
                github_repo=GITHUB_REPO,
                anthropic_api_key=ANTHROPIC_KEY,
                focus=state["focus"],
            ),
        )
        state["last_branch"]  = result["branch"]
        state["last_summary"] = result["summary"]
        _save(state)
        await app.bot.send_message(
            OWNER_CHAT_ID,
            f"🌙 *Nightly run complete!*\n\n"
            f"Branch: `{result['branch']}`\n\n"
            f"{result['summary']}\n\n"
            f"/deploy to push live · /reject to discard",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.exception("Nightly run failed")
        await app.bot.send_message(OWNER_CHAT_ID, f"❌ Nightly run failed:\n{e}")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    async def post_init(application: Application):
        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(
            lambda: asyncio.create_task(nightly_run(application)),
            "cron", hour=2, minute=0,
        )
        scheduler.start()
        logger.info("Scheduler started")

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    for cmd, handler in [
        ("run",    cmd_run),
        ("deploy", cmd_deploy),
        ("reject", cmd_reject),
        ("focus",  cmd_focus),
        ("status", cmd_status),
        ("help",   cmd_help),
        ("start",    cmd_help),
        ("clearchat", cmd_clearchat),
    ]:
        app.add_handler(CommandHandler(cmd, handler))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started, polling…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
