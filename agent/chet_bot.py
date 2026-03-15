"""
CHET — Chief Accounting Expert for TableMetrics.

Commands:
  /analyze [topic]   Deep accounting analysis + recommendation for BART
  /recommend         Send current recommendation to BART via shared state
  /status            Show current pending recommendation
  /clearchat         Clear conversation history
  /help              Show this list

Group chat:
  Send any message in the group → CHET and BART discuss it autonomously.
  CHET goes first and last; BART responds in the middle using his own token.
  After the discussion, CHET saves a recommendation. Tell BART /pickup to implement.
"""

import asyncio
import base64
import html as _html_lib
import json
import logging
import os
import re as _re_msg
from pathlib import Path

import anthropic
import psycopg2
import psycopg2.extras
import requests as _requests
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from accountant import run_accountant

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN      = os.environ["CHET_BOT_TOKEN"]
BART_BOT_TOKEN = os.environ.get("BART_BOT_TOKEN", "")
OWNER_CHAT_ID  = int(os.environ["TELEGRAM_CHAT_ID"])
ANTHROPIC_KEY  = os.environ["ANTHROPIC_API_KEY"]
GITHUB_TOKEN   = os.environ["GITHUB_TOKEN"]
DATABASE_URL   = os.environ.get("DATABASE_URL", "")
GITHUB_REPO    = os.environ.get("GITHUB_REPO", "ahmedbawla/restaurant-dashboard")
GROUP_CHAT_ID  = int(os.environ.get("TELEGRAM_GROUP_CHAT_ID", 0))

# In-memory chat history (resets on redeploy — acceptable for a chat assistant)
_CHAT_HISTORY: list = []
_LAST_RECOMMENDATION: str = ""

_DB_SCHEMA = """
Database tables (PostgreSQL, all scoped by username):
- daily_sales: date, covers, revenue, avg_check, food_cost, food_cost_pct
- hourly_sales: date, hour, covers, revenue
- daily_labor: date, dept, hours, labor_cost
- weekly_payroll: week_start, employee_name, dept, role, hourly_rate,
  regular_hours, overtime_hours, gross_pay
- expenses: date, category, vendor, amount, description
- cash_flow: date, inflow, outflow, net
- menu_items: name, category, price, cost, quantity_sold,
  total_revenue, gross_profit, margin_pct
- payroll_journal_summaries: period_start/end, gross_earnings, net_pay,
  total_tax_liability
""".strip()


# ── DB helpers for recommendation passing ─────────────────────────────────────
def _db_conn():
    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    # psycopg2 uses postgresql:// but also accepts postgres://
    return psycopg2.connect(url.replace("postgresql://", "postgres://", 1))


def _db_ensure_table():
    """Create chet_recommendations table if it doesn't exist."""
    try:
        with _db_conn() as conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chet_recommendations (
                    id SERIAL PRIMARY KEY,
                    recommendation TEXT NOT NULL,
                    full_discussion TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    consumed BOOLEAN DEFAULT FALSE
                )
            """)
            conn.commit()
    except Exception as e:
        logger.warning(f"Could not ensure chet_recommendations table: {e}")


def _db_save_recommendation(recommendation: str, full_discussion: str = ""):
    try:
        _db_ensure_table()
        with _db_conn() as conn, conn.cursor() as cur:
            # Mark all previous as consumed so only one is pending at a time
            cur.execute("UPDATE chet_recommendations SET consumed = TRUE WHERE consumed = FALSE")
            cur.execute(
                "INSERT INTO chet_recommendations (recommendation, full_discussion) VALUES (%s, %s)",
                (recommendation, full_discussion),
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to save recommendation to DB: {e}")


def _db_get_pending() -> tuple[str, int] | None:
    """Return (recommendation_text, row_id) or None if nothing pending."""
    try:
        _db_ensure_table()
        with _db_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, recommendation FROM chet_recommendations WHERE consumed = FALSE ORDER BY created_at DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row:
                return row[1], row[0]
    except Exception as e:
        logger.error(f"Failed to read recommendation from DB: {e}")
    return None


def _db_consume(rec_id: int):
    try:
        with _db_conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE chet_recommendations SET consumed = TRUE WHERE id = %s", (rec_id,))
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to consume recommendation: {e}")


def _is_owner(update: Update) -> bool:
    return update.effective_user and update.effective_user.id == OWNER_CHAT_ID


# ── Formatting ────────────────────────────────────────────────────────────────
def _md_to_html(text: str) -> str:
    text = _html_lib.escape(text)
    text = _re_msg.sub(
        r"```(?:\w*\n)?(.*?)```",
        lambda m: f"<pre>{m.group(1).rstrip()}</pre>",
        text, flags=_re_msg.DOTALL,
    )
    text = _re_msg.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
    text = _re_msg.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return text


def _chunk(text: str) -> list[str]:
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
    return chunks


async def _send_reply(update: Update, text: str):
    for chunk in _chunk(text):
        html = _md_to_html(chunk)
        try:
            await update.message.reply_text(html, parse_mode="HTML")
        except Exception:
            await update.message.reply_text(chunk)


async def _post_to_group(app, text: str):
    """Post as CHET to the group."""
    if not GROUP_CHAT_ID:
        return
    for chunk in _chunk(text):
        html = _md_to_html(chunk)
        try:
            await app.bot.send_message(GROUP_CHAT_ID, html, parse_mode="HTML")
        except Exception:
            await app.bot.send_message(GROUP_CHAT_ID, chunk)


async def _post_as_bart(text: str):
    """Post to the group using BART's bot token so the message comes from BART."""
    if not BART_BOT_TOKEN or not GROUP_CHAT_ID:
        return
    for chunk in _chunk(text):
        html = _md_to_html(chunk)
        try:
            _requests.post(
                f"https://api.telegram.org/bot{BART_BOT_TOKEN}/sendMessage",
                json={"chat_id": GROUP_CHAT_ID, "text": html, "parse_mode": "HTML"},
                timeout=10,
            )
        except Exception:
            try:
                _requests.post(
                    f"https://api.telegram.org/bot{BART_BOT_TOKEN}/sendMessage",
                    json={"chat_id": GROUP_CHAT_ID, "text": chunk},
                    timeout=10,
                )
            except Exception:
                pass


# ── GitHub helpers ────────────────────────────────────────────────────────────
def _gh_headers(text_match: bool = False) -> dict:
    accept = (
        "application/vnd.github.text-match+json"
        if text_match
        else "application/vnd.github.v3+json"
    )
    return {"Authorization": f"token {GITHUB_TOKEN}", "Accept": accept}


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
        msg = resp.json().get("message", "") if resp.content else ""
        return f"Error fetching file tree: HTTP {resp.status_code} — {msg}"
    files = [
        item["path"] for item in resp.json().get("tree", [])
        if item["type"] == "blob"
        and (not directory or item["path"].startswith(directory))
        and not any(p.startswith((".", "__pycache__")) for p in item["path"].split("/"))
    ]
    return "\n".join(files[:200])


def _chat_search(pattern: str) -> str:
    url = f"https://api.github.com/search/code?q={_requests.utils.quote(pattern)}+repo:{GITHUB_REPO}"
    headers = {**_gh_headers(), "Accept": "application/vnd.github.text-match+json"}
    resp = _requests.get(url, headers=headers, timeout=15)
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


def _execute_tool(name: str, inputs: dict) -> str:
    if name == "read_file":   return _chat_read_file(inputs["path"])
    if name == "list_files":  return _chat_list_files(inputs.get("directory", ""))
    if name == "search_code": return _chat_search(inputs["pattern"])
    return f"Unknown tool: {name}"


_TOOLS = [
    {
        "name": "read_file",
        "description": "Read a file's full contents from the repository.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "list_files",
        "description": "List all files in the repo or a subdirectory.",
        "input_schema": {
            "type": "object",
            "properties": {"directory": {"type": "string"}},
            "required": ["directory"],
        },
    },
    {
        "name": "search_code",
        "description": "Search for a text pattern across all files in the repo.",
        "input_schema": {
            "type": "object",
            "properties": {"pattern": {"type": "string"}},
            "required": ["pattern"],
        },
    },
]

# ── System prompts ────────────────────────────────────────────────────────────

_FILE_MAP = """
Known repo files (use these exact paths with read_file):
- app.py, auth.py
- pages/1_Spending.py  (QuickBooks expenses)
- pages/2_Payroll.py   (Paychex labour)
- pages/3_Inventory.py
- pages/4_Sales.py
- pages/5_Reports.py
- pages/6_Account.py
- pages/summary.py
- data/database.py
- utils/sms.py
- agent/runner.py, agent/bot.py, agent/chet_bot.py, agent/accountant.py
""".strip()

_CHET_DISCUSSION_SYSTEM = f"""You are CHET, a restaurant accountant advising the owner in a group chat with BART (developer).

Expertise: P&L, food cost %, labour %, prime cost, cash flow, menu engineering, payroll, QuickBooks.

{_FILE_MAP}

{_DB_SCHEMA}

Rules:
- Read the relevant file before commenting on it
- Max 5-6 lines per response — give the main point only, no padding
- Do NOT write code
- Final turn: one RECOMMENDATION: line naming the page, metric, and chart type"""

_BART_DISCUSSION_SYSTEM = f"""You are BART, a full-stack developer in a group chat with CHET (accountant) and the owner.

Stack: Python, Streamlit, SQLAlchemy, PostgreSQL, Plotly, Pandas.

{_FILE_MAP}

{_DB_SCHEMA}

Rules:
- Read the relevant file before saying what's built or missing
- Max 5-6 lines per response — be direct
- Say easy / hard / already done — no long explanations"""


def _build_discussion_messages(
    speaker: str,
    shared_history: list,
    is_final_turn: bool,
) -> list:
    """Format the shared conversation history into a Claude messages array."""
    labels = {"user": "Owner", "chet": "CHET", "bart": "BART"}

    conv_lines = []
    for msg in shared_history:
        conv_lines.append(f"{labels[msg['speaker']]}: {msg['content']}")

    conv_text = "\n\n".join(conv_lines)

    final_note = ""
    if is_final_turn and speaker == "chet":
        final_note = (
            "\n\nThis is your final turn. "
            "Summarise what you and BART agreed on, then state ONE specific recommendation "
            "starting with 'RECOMMENDATION:' — name the page, the metric, and the chart type."
        )

    return [
        {
            "role": "user",
            "content": (
                f"Conversation so far:\n\n{conv_text}"
                f"{final_note}\n\n"
                f"Your turn to respond:"
            ),
        }
    ]


# ── Discussion engine ─────────────────────────────────────────────────────────

def _run_discussion_turn_sync(
    speaker: str,
    shared_history: list,
    is_final_turn: bool,
) -> str:
    """Blocking Claude call for one discussion turn. Run via run_in_executor."""
    system = _CHET_DISCUSSION_SYSTEM if speaker == "chet" else _BART_DISCUSSION_SYSTEM
    messages = _build_discussion_messages(speaker, shared_history, is_final_turn)

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    resp = None

    def _serialize(block) -> dict:
        if block.type == "text":
            return {"type": "text", "text": block.text}
        if block.type == "tool_use":
            return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
        return {"type": block.type}

    for _ in range(15):
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system,
            tools=_TOOLS,
            messages=messages,
        )
        if resp.stop_reason == "end_turn":
            messages.append({"role": "assistant", "content": [_serialize(b) for b in resp.content]})
            break
        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": [_serialize(b) for b in resp.content]})
            results = []
            for block in resp.content:
                if block.type == "tool_use":
                    out = _execute_tool(block.name, block.input)
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": out[:8000]})
            messages.append({"role": "user", "content": results})
        else:
            break

    reply = ""
    if resp:
        for block in reversed(resp.content):
            if hasattr(block, "text") and block.text.strip():
                reply = block.text.strip()
                break
    return reply or f"({speaker.upper()} had nothing to add.)"


async def _run_discussion_turn(speaker: str, shared_history: list, is_final_turn: bool) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _run_discussion_turn_sync, speaker, shared_history, is_final_turn
    )


async def orchestrate_group_discussion(app, user_message: str, chat_id: int):
    """
    Run a CHET → BART → CHET discussion.
    Posts to chat_id as CHET; uses BART's token for BART's turn.
    Saves CHET's final recommendation to the shared DB.
    """
    shared_history = [{"speaker": "user", "content": user_message}]

    async def _post_chet(text: str):
        for chunk in _chunk(text):
            html = _md_to_html(chunk)
            try:
                await app.bot.send_message(chat_id, html, parse_mode="HTML")
            except Exception:
                await app.bot.send_message(chat_id, chunk)

    async def _post_bart(text: str):
        if not BART_BOT_TOKEN:
            await _post_chet(f"[BART] {text}")
            return
        for chunk in _chunk(text):
            html = _md_to_html(chunk)
            try:
                _requests.post(
                    f"https://api.telegram.org/bot{BART_BOT_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": html, "parse_mode": "HTML"},
                    timeout=10,
                )
            except Exception:
                _requests.post(
                    f"https://api.telegram.org/bot{BART_BOT_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": chunk},
                    timeout=10,
                )

    # ── Round 1: CHET opens ──────────────────────────────────────────────────
    await app.bot.send_chat_action(chat_id, "typing")
    chet_r1 = await _run_discussion_turn("chet", shared_history, is_final_turn=False)
    shared_history.append({"speaker": "chet", "content": chet_r1})
    await _post_chet(f"🧮 *CHET:*\n\n{chet_r1}")
    await asyncio.sleep(2)

    # ── BART responds ────────────────────────────────────────────────────────
    await app.bot.send_chat_action(chat_id, "typing")
    bart_r1 = await _run_discussion_turn("bart", shared_history, is_final_turn=False)
    shared_history.append({"speaker": "bart", "content": bart_r1})
    await _post_bart(f"🤖 *BART:*\n\n{bart_r1}")
    await asyncio.sleep(2)

    # ── Round 2: CHET closes with recommendation ─────────────────────────────
    await app.bot.send_chat_action(chat_id, "typing")
    chet_r2 = await _run_discussion_turn("chet", shared_history, is_final_turn=True)
    shared_history.append({"speaker": "chet", "content": chet_r2})
    await _post_chet(f"🧮 *CHET:*\n\n{chet_r2}")

    # ── Extract and save recommendation ──────────────────────────────────────
    recommendation = ""
    for line in chet_r2.splitlines():
        if line.strip().upper().startswith("RECOMMENDATION:"):
            recommendation = line.split(":", 1)[-1].strip()
            break
    if not recommendation:
        paragraphs = [p.strip() for p in chet_r2.split("\n\n") if p.strip()]
        recommendation = paragraphs[-1] if paragraphs else chet_r2[:300]

    full_discussion = "\n\n".join(m["speaker"] + ": " + m["content"] for m in shared_history)
    _db_save_recommendation(recommendation, full_discussion)

    global _LAST_RECOMMENDATION
    _LAST_RECOMMENDATION = recommendation

    await _post_chet("📋 Recommendation saved. Tell *BART* to run */pickup* to implement it.")


# ── System prompt for private CHET chat ──────────────────────────────────────
def _build_chat_system() -> str:
    pending = _LAST_RECOMMENDATION or "none"
    return f"""You are CHET, a restaurant accountant advising the TableMetrics dashboard owner.

{_FILE_MAP}

{_DB_SCHEMA}

Pending BART recommendation: {pending}

Rules:
- Read code before answering questions about the dashboard
- Keep every response to 5-10 lines max — main point only, no padding
- Think like the owner's accountant: practical, direct, numbers-focused"""


_DETAIL_WORDS = {"detail", "details", "detailed", "explain", "elaborate", "more", "why", "how", "example", "walk", "show", "breakdown", "break"}

def _wants_detail(user_text: str) -> bool:
    return bool(set(user_text.lower().split()) & _DETAIL_WORDS)


async def _condense(client, reply: str, user_text: str) -> str:
    if _wants_detail(user_text) or len(reply) < 280:
        return reply
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=120,
            system="Summarize in 2-3 short sentences. Keep specific facts, numbers, file names. No intro phrases.",
            messages=[{"role": "user", "content": reply}],
        )
        return resp.content[0].text.strip()
    except Exception:
        return reply


# ── History management ────────────────────────────────────────────────────────
async def _trim_history(client, history: list) -> list:
    if len(history) <= 30:
        return history
    to_summarize = history[:-20]
    keep = history[-20:]
    text_parts = []
    for msg in to_summarize:
        role = msg["role"].upper()
        content = msg["content"]
        if isinstance(content, str):
            text_parts.append(f"{role}: {content}")
        elif isinstance(content, list):
            texts = [
                b["text"] for b in content
                if isinstance(b, dict) and b.get("type") == "text" and b.get("text", "").strip()
            ]
            if texts:
                text_parts.append(f"{role}: " + " ".join(texts))
    if not text_parts:
        return keep
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system="Summarize this accounting conversation in 3-5 bullet points. Focus on decisions, features discussed, and key context. Plain text only.",
            messages=[{"role": "user", "content": "\n\n".join(text_parts)}],
        )
        summary = resp.content[0].text.strip()
        return [
            {"role": "user", "content": f"[Earlier conversation summary]\n{summary}"},
            {"role": "assistant", "content": [{"type": "text", "text": "Got it, continuing with that context."}]},
        ] + keep
    except Exception:
        return keep


# ── Command handlers ──────────────────────────────────────────────────────────
async def cmd_discuss(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/discuss [topic] — trigger full CHET→BART→CHET autonomous discussion in the group."""
    if not _is_owner(update):
        return
    if not GROUP_CHAT_ID:
        await update.message.reply_text("TELEGRAM_GROUP_CHAT_ID is not set.")
        return
    topic = " ".join(ctx.args) if ctx.args else "What accounting features should we add to the dashboard?"
    await update.message.reply_text("🧮 Starting CHET ↔ BART discussion… (~2 min)")
    try:
        await orchestrate_group_discussion(ctx.application, topic, chat_id=update.effective_chat.id)
    except Exception as e:
        logger.exception("Group discussion failed")
        await update.message.reply_text(f"❌ Discussion failed: {e}")


async def cmd_analyze(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/analyze [topic] — deep accounting analysis + recommendation for BART."""
    if not _is_owner(update):
        return
    focus = " ".join(ctx.args) if ctx.args else None
    hint  = f" (focus: {focus})" if focus else ""
    await update.message.reply_text(f"🧮 Analyzing the dashboard{hint}… 1-2 minutes.")
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: run_accountant(
                github_token=GITHUB_TOKEN,
                github_repo=GITHUB_REPO,
                anthropic_api_key=ANTHROPIC_KEY,
                focus=focus,
            ),
        )
        global _LAST_RECOMMENDATION
        _LAST_RECOMMENDATION = result["recommendation"]
        await _send_reply(
            update,
            f"🧮 *CHET Analysis:*\n\n{result['full_analysis']}\n\n---\nRun */recommend* to send this to BART.",
        )
    except Exception as e:
        logger.exception("Analysis failed")
        await update.message.reply_text(f"❌ Analysis failed:\n{e}")


async def cmd_recommend(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/recommend — send current recommendation to BART via the database."""
    if not _is_owner(update):
        return
    rec = _LAST_RECOMMENDATION
    if not rec:
        await update.message.reply_text("No recommendation yet. Run /analyze first or have a group discussion.")
        return
    _db_save_recommendation(rec)
    await _post_to_group(
        ctx.application,
        f"🧮 *CHET → BART:*\n\n{rec}\n\nBART: run */pickup* to implement this.",
    )
    await update.message.reply_text(
        f"📤 Sent to BART:\n\n_{rec}_\n\nTell BART to run /pickup.",
        parse_mode="Markdown",
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    pending = _db_get_pending()
    if pending:
        rec_text, _ = pending
        status = f"Pending (not yet picked up by BART):\n_{rec_text}_"
    elif _LAST_RECOMMENDATION:
        status = f"Last recommendation (already sent or consumed):\n_{_LAST_RECOMMENDATION}_"
    else:
        status = "none"
    await update.message.reply_text(
        f"📋 *CHET Status*\n\n{status}",
        parse_mode="Markdown",
    )


async def cmd_clearchat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    global _CHAT_HISTORY
    _CHAT_HISTORY = []
    await update.message.reply_text("💬 Conversation cleared.")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    await update.message.reply_text(
        "🧮 *CHET — Accounting Expert*\n\n"
        "*Group chat:*\n"
        "Just talk — CHET responds as your accounting advisor\n"
        "Mention 'Bart' to get BART's dev perspective\n"
        "/discuss [topic] — full autonomous CHET↔BART discussion\n\n"
        "*Private chat:*\n"
        "Just talk — ask anything about restaurant finances or the dashboard\n"
        "/analyze [topic] — deep analysis + recommendation for BART\n"
        "/recommend — send latest recommendation to BART (/pickup to implement)\n"
        "/status — show pending recommendation\n"
        "/clearchat — clear conversation history",
        parse_mode="Markdown",
    )


# ── Private chat handler ──────────────────────────────────────────────────────
async def handle_private_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    if update.effective_chat.id == GROUP_CHAT_ID:
        return  # handled separately

    global _CHAT_HISTORY
    _CHAT_HISTORY.append({"role": "user", "content": update.message.text})

    await ctx.bot.send_chat_action(update.effective_chat.id, "typing")

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        _CHAT_HISTORY = await _trim_history(client, _CHAT_HISTORY)
        resp = None

        def _serialize(block) -> dict:
            if block.type == "text":
                return {"type": "text", "text": block.text}
            if block.type == "tool_use":
                return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
            return {"type": block.type}

        for _ in range(25):
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                system=_build_chat_system(),
                tools=_TOOLS,
                messages=_CHAT_HISTORY,
            )
            if resp.stop_reason == "end_turn":
                _CHAT_HISTORY.append({"role": "assistant", "content": [_serialize(b) for b in resp.content]})
                break
            if resp.stop_reason == "tool_use":
                _CHAT_HISTORY.append({"role": "assistant", "content": [_serialize(b) for b in resp.content]})
                await ctx.bot.send_chat_action(update.effective_chat.id, "typing")
                results = []
                for block in resp.content:
                    if block.type == "tool_use":
                        out = _execute_tool(block.name, block.input)
                        results.append({"type": "tool_result", "tool_use_id": block.id, "content": out[:8000]})
                _CHAT_HISTORY.append({"role": "user", "content": results})
            else:
                break

        reply = "No response."
        if resp:
            for block in reversed(resp.content):
                if hasattr(block, "text") and block.text.strip():
                    reply = block.text.strip()
                    break

        reply = await _condense(client, reply, update.message.text or "")
        await _send_reply(update, reply)

    except Exception as e:
        logger.exception("Chat handler failed")
        await update.message.reply_text(f"❌ Error: {e}")


# ── Group chat handler ────────────────────────────────────────────────────────
async def handle_group_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """CHET responds to all owner messages in the group as an accounting advisor.
    BART is silent unless explicitly mentioned — the owner triggers BART by name.
    To kick off a full CHET→BART→CHET discussion, use /discuss [topic].
    """
    if not _is_owner(update):
        return
    if update.effective_chat.type not in ("group", "supergroup"):
        return

    user_message = update.message.text
    if not user_message or user_message.startswith("/"):
        return

    # Only respond when @mentioned or when user replies to a CHET message
    reply_msg = update.message.reply_to_message
    is_reply_to_me = (
        reply_msg is not None
        and reply_msg.from_user is not None
        and reply_msg.from_user.id == ctx.bot.id
    )
    mentioned = [
        user_message[e.offset : e.offset + e.length].lower()
        for e in (update.message.entities or [])
        if e.type == "mention"
    ]
    is_mentioned = f"@{ctx.bot.username}".lower() in mentioned
    if not is_mentioned and not is_reply_to_me:
        return

    await handle_private_message(update, ctx)


# ── Photo handler ─────────────────────────────────────────────────────────────
async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    await ctx.bot.send_chat_action(update.effective_chat.id, "typing")
    try:
        photo     = update.message.photo[-1]
        tg_file   = await ctx.bot.get_file(photo.file_id)
        img_bytes = await tg_file.download_as_bytearray()
        img_b64   = base64.b64encode(bytes(img_bytes)).decode()
        caption   = update.message.caption or (
            "Review this screenshot from an accounting perspective. "
            "What financial data is shown? Is it clear and useful for a restaurant owner? "
            "What's missing?"
        )
        global _CHAT_HISTORY
        client  = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=_build_chat_system(),
            tools=_TOOLS,
            messages=_CHAT_HISTORY + [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}},
                        {"type": "text", "text": caption},
                    ],
                }
            ],
        )
        reply = "No response."
        for block in reversed(resp.content):
            if hasattr(block, "text") and block.text.strip():
                reply = block.text.strip()
                break
        _CHAT_HISTORY.append({"role": "user", "content": f"[Screenshot shared] {caption}"})
        _CHAT_HISTORY.append({"role": "assistant", "content": [{"type": "text", "text": reply}]})
        await _send_reply(update, reply)
    except Exception as e:
        logger.exception("Photo handler failed")
        await update.message.reply_text(f"❌ Error: {e}")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    for cmd, handler in [
        ("discuss",   cmd_discuss),
        ("analyze",   cmd_analyze),
        ("recommend", cmd_recommend),
        ("status",    cmd_status),
        ("clearchat", cmd_clearchat),
        ("help",      cmd_help),
        ("start",     cmd_help),
    ]:
        app.add_handler(CommandHandler(cmd, handler))

    # Group messages → discussion; private messages → Q&A chat
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Chat(GROUP_CHAT_ID) if GROUP_CHAT_ID else filters.NOTHING,
        handle_group_message,
    ))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_private_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    logger.info("CHET started, polling…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
