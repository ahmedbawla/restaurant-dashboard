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


# ── Developer chat handler ────────────────────────────────────────────────────
import base64
import requests as _requests

_DEV_SYSTEM = f"""You are a senior full-stack developer and the primary expert on this Streamlit restaurant dashboard codebase (repo: {GITHUB_REPO}).

When answering questions, READ THE ACTUAL CODE using your tools before responding — never guess at implementation details.
You have read-only access to the repository via the GitHub API.

The app is built with: Python, Streamlit, SQLAlchemy, Supabase/PostgreSQL, Plotly, Pandas.
Pages: Summary, Spending (QuickBooks OAuth), Payroll (Paychex PDF/CSV), Inventory, Sales, Reports, Account.
There is also an autonomous coding agent in the agent/ directory (that's you).

Help the developer:
- Debug issues by reading the relevant code
- Explain how specific features are implemented
- Suggest improvements with specific code references
- Understand data flow and architecture
- Review recent changes (use git log/diff via list_files on .git or read CHANGELOG)

Be precise — cite file names and line numbers when relevant.
Keep answers concise but technically complete.
If asked to make a change, explain exactly what to edit and where, or suggest using /focus + /run."""

_CHAT_TOOLS = [
    {
        "name": "read_file",
        "description": "Read a file's full contents from the repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to repo root, e.g. 'pages/2_Payroll.py'"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_files",
        "description": "List all files in the repo or a subdirectory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Subdirectory to filter by, or '' for all files"},
            },
            "required": ["directory"],
        },
    },
    {
        "name": "search_code",
        "description": "Search for a text pattern across all files in the repo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Text or regex pattern to search for"},
            },
            "required": ["pattern"],
        },
    },
]

def _gh_headers():
    return {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

def _chat_read_file(path: str) -> str:
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    resp = _requests.get(url, headers=_gh_headers(), timeout=15)
    if resp.status_code != 200:
        return f"Error {resp.status_code}: {resp.json().get('message', 'not found')}"
    data = resp.json()
    if isinstance(data, list):
        return "That path is a directory. Use list_files instead."
    content = data.get("content", "")
    if data.get("encoding") == "base64":
        return base64.b64decode(content).decode("utf-8", errors="replace")
    return content

def _chat_list_files(directory: str) -> str:
    url = f"https://api.github.com/repos/{GITHUB_REPO}/git/trees/HEAD?recursive=1"
    resp = _requests.get(url, headers=_gh_headers(), timeout=15)
    if resp.status_code != 200:
        return f"Error fetching file tree: {resp.status_code}"
    files = [
        item["path"] for item in resp.json().get("tree", [])
        if item["type"] == "blob" and (not directory or item["path"].startswith(directory))
        and not any(p.startswith((".", "__pycache__")) for p in item["path"].split("/"))
    ]
    return "\n".join(files[:200])

def _chat_search(pattern: str) -> str:
    url = f"https://api.github.com/search/code?q={_requests.utils.quote(pattern)}+repo:{GITHUB_REPO}"
    resp = _requests.get(url, headers=_gh_headers(), timeout=15)
    if resp.status_code != 200:
        return f"Search error {resp.status_code}"
    items = resp.json().get("items", [])
    if not items:
        return "No matches found."
    lines = []
    for item in items[:10]:
        frags = [m.get("fragment", "") for m in item.get("text_matches", [])]
        lines.append(f"**{item['path']}**\n" + "\n".join(f"  …{f.strip()}…" for f in frags[:2]))
    return "\n\n".join(lines)

def _chat_execute_tool(name: str, inputs: dict) -> str:
    if name == "read_file":   return _chat_read_file(inputs["path"])
    if name == "list_files":  return _chat_list_files(inputs.get("directory", ""))
    if name == "search_code": return _chat_search(inputs["pattern"])
    return f"Unknown tool: {name}"

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return

    import anthropic as _anthropic

    state   = _load()
    history = state.get("chat_history", [])
    history.append({"role": "user", "content": update.message.text})
    if len(history) > 40:
        history = history[-40:]

    await ctx.bot.send_chat_action(update.effective_chat.id, "typing")

    try:
        client = _anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        resp   = None

        for _ in range(15):
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                system=_DEV_SYSTEM,
                tools=_CHAT_TOOLS,
                messages=history,
            )
            history.append({"role": "assistant", "content": resp.content})

            if resp.stop_reason == "end_turn":
                break

            if resp.stop_reason == "tool_use":
                await ctx.bot.send_chat_action(update.effective_chat.id, "typing")
                results = []
                for block in resp.content:
                    if block.type == "tool_use":
                        out = _chat_execute_tool(block.name, block.input)
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": out[:8000],
                        })
                history.append({"role": "user", "content": results})

        reply = "No response."
        if resp:
            for block in reversed(resp.content):
                if hasattr(block, "text") and block.text.strip():
                    reply = block.text.strip()
                    break

        # Telegram message limit is 4096 chars
        if len(reply) > 4000:
            reply = reply[:3997] + "…"

        state["chat_history"] = history
        _save(state)

        # Try Markdown first; fall back to plain text if Telegram rejects it
        try:
            await update.message.reply_text(reply, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(reply)

    except Exception as e:
        logger.exception("Chat handler failed")
        await update.message.reply_text(f"❌ Error: {e}")


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
