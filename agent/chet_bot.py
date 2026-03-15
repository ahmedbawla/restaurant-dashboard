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
BOT_TOKEN     = os.environ["CHET_BOT_TOKEN"]
BART_BOT_TOKEN = os.environ.get("BART_BOT_TOKEN", "")
OWNER_CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
GITHUB_TOKEN  = os.environ["GITHUB_TOKEN"]
GITHUB_REPO   = os.environ.get("GITHUB_REPO", "ahmedbawla/restaurant-dashboard")
GROUP_CHAT_ID = int(os.environ.get("TELEGRAM_GROUP_CHAT_ID", 0))

CHET_STATE_FILE          = Path("/data/chet_state.json")
CHET_RECOMMENDATION_FILE = Path("/data/chet_recommendation.json")

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


# ── State ─────────────────────────────────────────────────────────────────────
def _load() -> dict:
    if CHET_STATE_FILE.exists():
        try:
            return json.loads(CHET_STATE_FILE.read_text())
        except Exception:
            pass
    return {"chat_history": [], "last_analysis": None, "last_recommendation": None}


def _save(state: dict):
    CHET_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHET_STATE_FILE.write_text(json.dumps(state))


def _is_owner(update: Update) -> bool:
    return update.effective_user.id == OWNER_CHAT_ID


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
        return f"Error fetching file tree: {resp.status_code}"
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

_CHET_DISCUSSION_SYSTEM = f"""You are CHET, a senior restaurant accountant and CFO advisor in a group discussion with BART (the developer) and the restaurant owner.

Your expertise: P&L management, food cost %, labor cost %, prime cost, cash flow forecasting, menu engineering, payroll compliance, variance analysis, QuickBooks reconciliation.

The dashboard (Python, Streamlit, PostgreSQL, Plotly) has these pages: Summary, Spending (QuickBooks), Payroll (Paychex), Inventory, Sales, Reports, Account.

{_DB_SCHEMA}

You have read-only access to the codebase via tools. Read the relevant files before making suggestions so you know what's already built.

## Your role in this discussion
- Bring the accountant's perspective: what financial data is missing, what calculations would help restaurant owners catch problems early
- Ask BART specific questions about feasibility
- Keep each response to 2-3 concise paragraphs
- Do NOT write code — that is BART's job
- In your FINAL turn: state one clear, specific recommendation for BART to implement"""

_BART_DISCUSSION_SYSTEM = f"""You are BART, a senior full-stack developer in a group discussion with CHET (the accountant) and the restaurant owner.

You work on the TableMetrics restaurant dashboard (Python, Streamlit, SQLAlchemy, PostgreSQL, Plotly, Pandas).
Pages: Summary, Spending (QuickBooks), Payroll (Paychex), Inventory, Sales, Reports, Account.

{_DB_SCHEMA}

You have read-only access to the codebase via tools. READ THE CODE before assessing what's built vs missing.

## Your role in this discussion
- Assess the feasibility of CHET's accounting suggestions
- Tell CHET what's already built and what's genuinely missing
- Propose specific implementation approaches (page name, chart type, calculation)
- Ask CHET clarifying questions about the accounting requirements
- Keep each response to 2-3 concise paragraphs
- Be direct: say whether something is easy, hard, or already done"""


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

async def _run_discussion_turn(
    speaker: str,
    shared_history: list,
    is_final_turn: bool,
) -> str:
    """Run one turn of the CHET↔BART discussion. Returns the agent's response text."""
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
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": out[:8000],
                    })
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


async def orchestrate_group_discussion(app, user_message: str):
    """
    Run a CHET → BART → CHET discussion in the group chat.
    CHET posts via its own account; BART posts via BART's bot token.
    Saves CHET's final recommendation to shared state.
    """
    shared_history = [{"speaker": "user", "content": user_message}]

    # ── Round 1: CHET opens ──────────────────────────────────────────────────
    await app.bot.send_chat_action(GROUP_CHAT_ID, "typing")
    chet_r1 = await asyncio.get_event_loop().run_in_executor(
        None, lambda: asyncio.run(_run_discussion_turn("chet", shared_history, is_final_turn=False))
    )
    shared_history.append({"speaker": "chet", "content": chet_r1})
    await _post_to_group(app, f"🧮 *CHET:*\n\n{chet_r1}")
    await asyncio.sleep(2)

    # ── Round 1: BART responds ───────────────────────────────────────────────
    bart_r1 = await asyncio.get_event_loop().run_in_executor(
        None, lambda: asyncio.run(_run_discussion_turn("bart", shared_history, is_final_turn=False))
    )
    shared_history.append({"speaker": "bart", "content": bart_r1})
    await _post_as_bart(f"🤖 *BART:*\n\n{bart_r1}")
    await asyncio.sleep(2)

    # ── Round 2: CHET closes with recommendation ─────────────────────────────
    await app.bot.send_chat_action(GROUP_CHAT_ID, "typing")
    chet_r2 = await asyncio.get_event_loop().run_in_executor(
        None, lambda: asyncio.run(_run_discussion_turn("chet", shared_history, is_final_turn=True))
    )
    shared_history.append({"speaker": "chet", "content": chet_r2})
    await _post_to_group(app, f"🧮 *CHET:*\n\n{chet_r2}")

    # ── Extract and save recommendation ──────────────────────────────────────
    recommendation = ""
    for line in chet_r2.splitlines():
        if line.strip().upper().startswith("RECOMMENDATION:"):
            recommendation = line.split(":", 1)[-1].strip()
            break
    if not recommendation:
        paragraphs = [p.strip() for p in chet_r2.split("\n\n") if p.strip()]
        recommendation = paragraphs[-1] if paragraphs else chet_r2[:300]

    CHET_RECOMMENDATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHET_RECOMMENDATION_FILE.write_text(json.dumps({
        "recommendation": recommendation,
        "full_discussion": [m["speaker"] + ": " + m["content"] for m in shared_history],
    }))

    state = _load()
    state["last_recommendation"] = recommendation
    _save(state)

    await _post_to_group(
        app,
        f"---\n📋 Recommendation saved. Tell *BART* to run */pickup* to implement it.",
    )


# ── System prompt for private CHET chat ──────────────────────────────────────
def _build_chat_system(state: dict) -> str:
    pending = state.get("last_recommendation") or "none"
    return f"""You are CHET, a senior restaurant accountant and CFO advisor for TableMetrics, a restaurant analytics SaaS.

Your expertise: P&L, food cost %, labor %, prime cost, cash flow, menu engineering, payroll, variance analysis, QuickBooks.

Dashboard stack: Python, Streamlit, SQLAlchemy, PostgreSQL, Plotly, Pandas.
Pages: Summary, Spending (QuickBooks), Payroll (Paychex), Inventory, Sales, Reports, Account.

{_DB_SCHEMA}

READ CODE via tools before answering questions about the dashboard. Never guess what's built.

Current pending recommendation for BART: {pending}

Response style: concise, plain language, max 3-4 paragraphs. Think like a restaurant owner's accountant."""


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
        state = _load()
        state["last_analysis"]       = result["full_analysis"]
        state["last_recommendation"] = result["recommendation"]
        _save(state)
        await _send_reply(
            update,
            f"🧮 *CHET Analysis:*\n\n{result['full_analysis']}\n\n---\nRun */recommend* to send this to BART.",
        )
    except Exception as e:
        logger.exception("Analysis failed")
        await update.message.reply_text(f"❌ Analysis failed:\n{e}")


async def cmd_recommend(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/recommend — send current recommendation to BART via shared state."""
    if not _is_owner(update):
        return
    state = _load()
    rec = state.get("last_recommendation")
    if not rec:
        await update.message.reply_text("No recommendation yet. Run /analyze first or have a group discussion.")
        return
    CHET_RECOMMENDATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHET_RECOMMENDATION_FILE.write_text(json.dumps({
        "recommendation": rec,
        "full_analysis": state.get("last_analysis", ""),
    }))
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
    state = _load()
    rec = state.get("last_recommendation") or "none"
    await update.message.reply_text(
        f"📋 *CHET Status*\n\nLast recommendation:\n_{rec}_",
        parse_mode="Markdown",
    )


async def cmd_clearchat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    state = _load()
    state["chat_history"] = []
    _save(state)
    await update.message.reply_text("💬 Conversation cleared.")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    await update.message.reply_text(
        "🧮 *CHET — Accounting Expert*\n\n"
        "*Private chat:*\n"
        "Just talk — ask me anything about restaurant finances or the dashboard\n"
        "/analyze — deep analysis + recommendation for BART\n"
        "/analyze [topic] — same, focused on a specific area\n"
        "/recommend — send latest recommendation to BART\n"
        "/status — show current pending recommendation\n"
        "/clearchat — clear conversation history\n\n"
        "*Group chat:*\n"
        "Send any message → CHET and BART discuss it and produce a recommendation\n"
        "Then tell BART /pickup to implement it",
        parse_mode="Markdown",
    )


# ── Private chat handler ──────────────────────────────────────────────────────
async def handle_private_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    if update.effective_chat.id == GROUP_CHAT_ID:
        return  # handled separately

    state   = _load()
    history = state.get("chat_history", [])
    history.append({"role": "user", "content": update.message.text})

    await ctx.bot.send_chat_action(update.effective_chat.id, "typing")

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        history = await _trim_history(client, history)
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
                system=_build_chat_system(state),
                tools=_TOOLS,
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
                        out = _execute_tool(block.name, block.input)
                        results.append({"type": "tool_result", "tool_use_id": block.id, "content": out[:8000]})
                history.append({"role": "user", "content": results})
            else:
                break

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


# ── Group chat handler ────────────────────────────────────────────────────────
async def handle_group_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Triggered when the owner sends a message to the group — starts the discussion."""
    if not _is_owner(update):
        return
    if not GROUP_CHAT_ID or update.effective_chat.id != GROUP_CHAT_ID:
        return

    user_message = update.message.text
    if not user_message or user_message.startswith("/"):
        return

    await update.message.reply_text("🧮 Starting discussion between CHET and BART… (~2 min)")

    try:
        await orchestrate_group_discussion(ctx.application, user_message)
    except Exception as e:
        logger.exception("Group discussion failed")
        await _post_to_group(ctx.application, f"❌ Discussion failed: {e}")


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
        state   = _load()
        history = state.get("chat_history", [])
        client  = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=_build_chat_system(state),
            tools=_TOOLS,
            messages=history + [
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
        history.append({"role": "user", "content": f"[Screenshot shared] {caption}"})
        history.append({"role": "assistant", "content": [{"type": "text", "text": reply}]})
        state["chat_history"] = history
        _save(state)
        await _send_reply(update, reply)
    except Exception as e:
        logger.exception("Photo handler failed")
        await update.message.reply_text(f"❌ Error: {e}")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    for cmd, handler in [
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
