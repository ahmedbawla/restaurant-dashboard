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

STATE_FILE = Path("/data/agent_state.json")


# ── State persistence ─────────────────────────────────────────────────────────
def _load() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"focus": None, "last_branch": None, "last_summary": "No agent run yet."}


def _save(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
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


async def cmd_promote(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/promote — remove test gates from agent branch, then deploy to all users."""
    if not _is_owner(update):
        return

    import anthropic as _anthropic

    state  = _load()
    branch = state.get("last_branch")
    if not branch:
        await update.message.reply_text("Nothing to promote. Run /run first.")
        return

    repo_url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"
    await update.message.reply_text(
        f"🔓 Promoting `{branch}` — removing test gates…", parse_mode="Markdown"
    )

    def _do():
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "clone", repo_url, tmpdir], check=True, capture_output=True)
            subprocess.run("git config user.email 'agent@dashboard.bot'", shell=True, cwd=tmpdir)
            subprocess.run("git config user.name 'Dashboard Agent'", shell=True, cwd=tmpdir)
            subprocess.run(f"git fetch origin {branch}", shell=True, cwd=tmpdir, check=True)
            subprocess.run(f"git checkout {branch}", shell=True, cwd=tmpdir, check=True, capture_output=True)

            # Find files changed on this branch vs main
            result = subprocess.run(
                "git diff --name-only origin/main",
                shell=True, cwd=tmpdir, capture_output=True, text=True,
            )
            changed = [f.strip() for f in result.stdout.splitlines() if f.strip().endswith(".py")]

            if not changed:
                raise RuntimeError("No changed Python files found on this branch.")

            # Use Claude to remove test gates from each changed file
            client = _anthropic.Anthropic(api_key=ANTHROPIC_KEY)
            promoted_any = False

            for filepath in changed:
                full = Path(tmpdir) / filepath
                if not full.exists():
                    continue
                original = full.read_text(encoding="utf-8")

                # Skip if no test gate present
                if 'username == "test"' not in original and "username == 'test'" not in original:
                    continue

                resp = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=8096,
                    system=(
                        "You are a code editor. You will be given a Python file that has features "
                        "gated behind `if username == \"test\":` blocks. "
                        "Your job: remove the test gate conditionals so the features run for ALL users. "
                        "Keep the feature code exactly as-is — just remove the `if username == \"test\":` "
                        "wrapper and de-indent the block one level. "
                        "Also remove any `username = st.session_state.get(\"username\", \"\")` lines "
                        "that were only used for the test gate. "
                        "Return ONLY the complete updated file content, no explanation, no markdown fences."
                    ),
                    messages=[{"role": "user", "content": f"File: {filepath}\n\n{original}"}],
                )
                promoted = resp.content[0].text if resp.content else None
                if promoted and promoted.strip() != original.strip():
                    full.write_text(promoted, encoding="utf-8")
                    promoted_any = True

            if not promoted_any:
                raise RuntimeError("No test-gated code found in changed files — use /deploy instead.")

            subprocess.run("git add -A", shell=True, cwd=tmpdir, check=True)
            subprocess.run(
                f"git commit -m 'promote: remove test gates from {branch}'",
                shell=True, cwd=tmpdir, check=True, capture_output=True,
            )

            # Merge promoted branch into main
            subprocess.run("git checkout main", shell=True, cwd=tmpdir, check=True, capture_output=True)
            subprocess.run(
                "git merge --no-ff HEAD@{1} -m 'Promote to all users'",
                shell=True, cwd=tmpdir, check=True, capture_output=True,
            )
            result = subprocess.run(
                "git push origin main",
                shell=True, cwd=tmpdir, capture_output=True, text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip())

    try:
        await asyncio.get_event_loop().run_in_executor(None, _do)
        state["last_branch"] = None
        _save(state)
        await update.message.reply_text(
            "✅ Promoted! Test gates removed — feature is now live for all users.\n"
            "Streamlit Cloud will redeploy automatically.",
        )
    except Exception as e:
        err = str(e).replace(GITHUB_TOKEN, "***")
        await update.message.reply_text(f"❌ Promote failed:\n{err[:500]}")


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
        result = subprocess.run(
            f"git push {repo_url} --delete {branch}",
            shell=True, capture_output=True, text=True,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout).strip().replace(GITHUB_TOKEN, "***")
            raise RuntimeError(err)

    try:
        await asyncio.get_event_loop().run_in_executor(None, _do)
        state["last_branch"] = None
        _save(state)
        await update.message.reply_text(
            f"🗑️ Rejected — branch `{branch}` deleted.", parse_mode="Markdown"
        )
    except RuntimeError as e:
        # Branch may already be gone — clear state anyway
        state["last_branch"] = None
        _save(state)
        await update.message.reply_text(f"❌ Could not delete branch:\n{e}\n\nState cleared.")


async def cmd_do(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/do [optional hint] — extract intent from chat history and run the coding agent."""
    if not _is_owner(update):
        return

    import anthropic as _anthropic

    state   = _load()
    history = state.get("chat_history", [])
    hint    = " ".join(ctx.args) if ctx.args else ""

    # Ask Claude to distil the conversation into a single focused task
    await update.message.reply_text("🧠 Extracting task from our conversation…")
    try:
        client = _anthropic.Anthropic(api_key=ANTHROPIC_KEY)

        # Build a text-only history for extraction — no tool_use or tool_result blocks.
        # Any message that is purely tool calls (no text) is dropped entirely.
        clean_history = []
        for msg in history:
            content = msg["content"]
            if isinstance(content, str):
                clean_history.append(msg)
            elif isinstance(content, list):
                # Drop tool_result messages entirely
                if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                    continue
                # Keep only text blocks — strip out any tool_use blocks
                texts = [
                    b["text"] for b in content
                    if isinstance(b, dict) and b.get("type") == "text" and b.get("text", "").strip()
                ]
                if texts:
                    clean_history.append({"role": msg["role"], "content": "\n".join(texts)})

        extraction_prompt = (
            "Based on the conversation so far, write ONE concise sentence describing "
            "the single most specific code change to implement next. "
            "Start with a verb. Max 20 words. No preamble.\n"
            + (f"Extra hint from owner: {hint}" if hint else "")
        )
        summary_resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=100,
            system="You extract clear, actionable task descriptions from developer conversations.",
            messages=clean_history + [{"role": "user", "content": extraction_prompt}],
        )
        focus = ""
        for block in summary_resp.content:
            if hasattr(block, "text") and block.text.strip():
                focus = block.text.strip()
                break
    except Exception as e:
        await update.message.reply_text(f"❌ Could not extract task: {e}")
        return

    if not focus:
        await update.message.reply_text("❌ Couldn't determine what to implement. Try /focus [description] then /run.")
        return

    await update.message.reply_text(
        f"🎯 Task: *{focus}*\n\n🤖 Agent starting… this takes 2–5 minutes.",
        parse_mode="Markdown",
    )

    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: run_agent(
                github_token=GITHUB_TOKEN,
                github_repo=GITHUB_REPO,
                anthropic_api_key=ANTHROPIC_KEY,
                focus=focus,
            ),
        )
        state["last_branch"]  = result["branch"]
        state["last_summary"] = result["summary"]
        state["focus"]        = None
        _save(state)
        await _send_reply(update,
            f"✅ Done!\n\nBranch: `{result['branch']}`\n\n"
            f"{result['summary']}\n\n"
            f"/deploy to push live · /reject to discard"
        )
    except Exception as e:
        logger.exception("Agent run failed in /do")
        await update.message.reply_text(f"❌ Agent failed:\n{e}")


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
        "/do — implement whatever we just discussed in chat\n"
        "/do [hint] — same, with extra direction\n"
        "/run — trigger agent freely (uses /focus if set)\n"
        "/deploy — deploy branch as-is (test-gated features stay test-only)\n"
        "/promote — remove test gates & deploy to ALL users\n"
        "/reject — delete latest agent branch\n"
        "/status — show pending branch & last summary\n"
        "/focus [topic] — manually set what agent works on\n"
        "/clearchat — clear conversation history\n"
        "/help — this message\n\n"
        "_Runs automatically every night at 2 AM UTC_",
        parse_mode="Markdown",
    )


# ── Developer chat handler ────────────────────────────────────────────────────
import base64
import requests as _requests


async def _send_reply(update: Update, text: str):
    """Split a long reply on blank lines and send as separate Telegram messages."""
    # Split into paragraphs, group into chunks ≤ 1000 chars
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks, current = [], ""
    for para in paragraphs:
        if len(current) + len(para) + 2 > 1000 and current:
            chunks.append(current.strip())
            current = para
        else:
            current = (current + "\n\n" + para).strip() if current else para
    if current:
        chunks.append(current.strip())

    for chunk in chunks:
        try:
            await update.message.reply_text(chunk, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(chunk)

_DEV_SYSTEM = f"""You are a senior full-stack developer and co-owner of a Streamlit restaurant analytics dashboard (repo: {GITHUB_REPO}).

READ THE ACTUAL CODE using your tools before answering — never guess.
You have read-only access via the GitHub API.

Stack: Python, Streamlit, SQLAlchemy, Supabase/PostgreSQL, Plotly, Pandas.
Pages: Summary, Spending (QuickBooks), Payroll (Paychex), Inventory, Sales, Reports, Account.

## Response style — CRITICAL
- Be concise. Max 3-4 short paragraphs or a tight bullet list.
- Use plain language, not formal documentation.
- Break your answer into short sections separated by blank lines — NOT one long block.
- If listing improvements, use numbered bullets: 1. 2. 3. — one idea per line.
- Never pad with intros like "Great question!" or summaries restating what you just said.
- If asked to make a change, say the file + line + exactly what to edit, then suggest /focus + /run."""

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

        def _serialize(block) -> dict:
            if block.type == "text":
                return {"type": "text", "text": block.text}
            if block.type == "tool_use":
                return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
            return {"type": block.type}

        for _ in range(15):
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                system=_DEV_SYSTEM,
                tools=_CHAT_TOOLS,
                messages=history,
            )

            if resp.stop_reason == "end_turn":
                history.append({"role": "assistant", "content": [_serialize(b) for b in resp.content]})
                break

            if resp.stop_reason == "tool_use":
                history.append({"role": "assistant", "content": [_serialize(b) for b in resp.content]})
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
            else:
                break  # max_tokens or unknown — stop cleanly

        reply = "No response."
        if resp:
            for block in reversed(resp.content):
                if hasattr(block, "text") and block.text.strip():
                    reply = block.text.strip()
                    break

        state["chat_history"] = history
        _save(state)
        await _send_reply(update, reply)

    except Exception as e:
        logger.exception("Chat handler failed")
        await update.message.reply_text(f"❌ Error: {e}")


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle a screenshot sent by the owner — passes it to Claude as a vision input."""
    if not _is_owner(update):
        return

    import anthropic as _anthropic

    await ctx.bot.send_chat_action(update.effective_chat.id, "typing")

    try:
        # Download the highest-res version of the photo
        photo = update.message.photo[-1]
        tg_file = await ctx.bot.get_file(photo.file_id)
        img_bytes = await tg_file.download_as_bytearray()
        img_b64 = base64.b64encode(bytes(img_bytes)).decode()

        caption = update.message.caption or "What do you think of this screenshot? Give detailed UI/UX feedback and suggest specific improvements."

        state   = _load()
        history = state.get("chat_history", [])

        # Build a vision message — NOT saved to persistent history (too large)
        vision_messages = history + [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": img_b64,
                        },
                    },
                    {"type": "text", "text": caption},
                ],
            }
        ]

        client = _anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=_DEV_SYSTEM,
            tools=_CHAT_TOOLS,
            messages=vision_messages,
        )

        reply = "No response."
        for block in reversed(resp.content):
            if hasattr(block, "text") and block.text.strip():
                reply = block.text.strip()
                break

        # Save a placeholder in history so context flows naturally
        history.append({"role": "user", "content": f"[Screenshot shared] {caption}"})
        history.append({"role": "assistant", "content": [b.model_dump() for b in resp.content]})
        if len(history) > 40:
            history = history[-40:]
        state["chat_history"] = history
        _save(state)
        await _send_reply(update, reply)

    except Exception as e:
        logger.exception("Photo handler failed")
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
        ("run",       cmd_run),
        ("do",        cmd_do),
        ("deploy",    cmd_deploy),
        ("promote",   cmd_promote),
        ("reject",    cmd_reject),
        ("focus",     cmd_focus),
        ("status",    cmd_status),
        ("help",      cmd_help),
        ("start",     cmd_help),
        ("clearchat", cmd_clearchat),
    ]:
        app.add_handler(CommandHandler(cmd, handler))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    logger.info("Bot started, polling…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
