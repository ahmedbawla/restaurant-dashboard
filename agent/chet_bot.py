"""
CHET — Chief accounting expert bot for TableMetrics.

Commands:
  /analyze [topic]   Deep accounting analysis of the dashboard + recommendation
  /recommend         Package current recommendation and make it available to BART
  /status            Show current pending recommendation
  /clearchat         Clear conversation history
  /help              Show this list
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
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from accountant import run_accountant

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN     = os.environ["CHET_BOT_TOKEN"]
OWNER_CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
GITHUB_TOKEN  = os.environ["GITHUB_TOKEN"]
GITHUB_REPO   = os.environ.get("GITHUB_REPO", "ahmedbawla/restaurant-dashboard")
GROUP_CHAT_ID = int(os.environ.get("TELEGRAM_GROUP_CHAT_ID", 0))

CHET_STATE_FILE = Path("/data/chet_state.json")
CHET_RECOMMENDATION_FILE = Path("/data/chet_recommendation.json")

_DB_SCHEMA = """
Database tables (PostgreSQL, all scoped by username):
- daily_sales: date, covers, revenue, avg_check, food_cost, food_cost_pct
- hourly_sales: date, hour, covers, revenue
- daily_labor: date, dept, hours, labor_cost
- weekly_payroll: week_start, employee_name, dept, role, hourly_rate, regular_hours, overtime_hours, gross_pay
- expenses: date, category, vendor, amount, description
- cash_flow: date, inflow, outflow, net
- menu_items: name, category, price, cost, quantity_sold, total_revenue, gross_profit, margin_pct
- payroll_journal_summaries: period_start/end, gross_earnings, net_pay, total_tax_liability
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


async def _send_reply(update: Update, text: str):
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
        html = _md_to_html(chunk)
        try:
            await update.message.reply_text(html, parse_mode="HTML")
        except Exception:
            await update.message.reply_text(chunk)


async def _post_to_group(app, text: str):
    if not GROUP_CHAT_ID:
        return
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
        html = _md_to_html(chunk)
        try:
            await app.bot.send_message(GROUP_CHAT_ID, html, parse_mode="HTML")
        except Exception:
            await app.bot.send_message(GROUP_CHAT_ID, chunk)


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


def _chat_execute_tool(name: str, inputs: dict) -> str:
    if name == "read_file":   return _chat_read_file(inputs["path"])
    if name == "list_files":  return _chat_list_files(inputs.get("directory", ""))
    if name == "search_code": return _chat_search(inputs["pattern"])
    return f"Unknown tool: {name}"


_CHAT_TOOLS = [
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


def _build_system(state: dict) -> str:
    pending = state.get("last_recommendation") or "none"
    return f"""You are CHET — Chief Accounting Expert for TableMetrics, a restaurant analytics SaaS platform.

You are a senior restaurant accountant and CFO advisor with 20+ years of experience. You think in terms of:
- P&L management: food cost %, labor cost %, prime cost (target <60%), EBITDA, net profit margins
- Cash flow: weekly position, burn rate, seasonal patterns, vendor payment timing
- Menu engineering: contribution margin, star/plow-horse/puzzle/dog matrix, menu mix
- Payroll: overtime exposure, labor law compliance, department cost ratios
- Cost controls: variance analysis, purchase price vs standard cost, waste tracking
- Tax and reporting: period close, accruals, QuickBooks reconciliation

You have READ-ONLY access to the dashboard codebase via GitHub API tools. Use them freely to understand what's built before answering questions.

Repo: {GITHUB_REPO}
Stack: Python, Streamlit, SQLAlchemy, PostgreSQL, Plotly, Pandas
Pages: Summary, Spending (QuickBooks), Payroll (Paychex), Inventory, Sales, Reports, Account

{_DB_SCHEMA}

## Your role
You are the accounting brain. You do NOT write code — that's BART's job.
Your job is to:
- Answer accounting and financial questions about the dashboard
- Identify gaps from an accountant's perspective
- Recommend specific features for BART to build

Current pending recommendation for BART: {pending}
Use /recommend to send your latest recommendation to BART.

## Response style
- Be concise. Max 3-4 short paragraphs or a tight bullet list.
- Use plain language, not formal documentation.
- Think like a restaurant owner's accountant, not a software developer.
- If asked about a specific page or metric, READ THE CODE FIRST before answering.
- If suggesting an improvement, be specific: name the page, metric, and chart type."""


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
        condensed = [
            {"role": "user", "content": f"[Earlier conversation summary]\n{summary}"},
            {"role": "assistant", "content": [{"type": "text", "text": "Got it, continuing with that context."}]},
        ]
        return condensed + keep
    except Exception:
        return keep


# ── Command handlers ──────────────────────────────────────────────────────────
async def cmd_analyze(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/analyze [topic] — deep accounting analysis of the dashboard with a recommendation for BART."""
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
        state["last_analysis"]      = result["full_analysis"]
        state["last_recommendation"] = result["recommendation"]
        _save(state)

        await _send_reply(
            update,
            f"🧮 *CHET Analysis:*\n\n"
            f"{result['full_analysis']}\n\n"
            f"---\n"
            f"Run */recommend* to send this to BART.",
        )
    except Exception as e:
        logger.exception("Analysis failed")
        await update.message.reply_text(f"❌ Analysis failed:\n{e}")


async def cmd_recommend(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/recommend — send current recommendation to BART via shared state and post to group."""
    if not _is_owner(update):
        return

    state = _load()
    rec = state.get("last_recommendation")
    if not rec:
        await update.message.reply_text("No recommendation yet. Run /analyze first.")
        return

    # Write to shared file so BART can pick it up with /pickup
    CHET_RECOMMENDATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHET_RECOMMENDATION_FILE.write_text(json.dumps({
        "recommendation": rec,
        "full_analysis": state.get("last_analysis", ""),
    }))

    # Post to group so both bots and user can see it
    await _post_to_group(
        ctx.application,
        f"🧮 *CHET → BART:*\n\n{rec}\n\nBART: run */pickup* to implement this.",
    )

    await update.message.reply_text(
        f"📤 Recommendation sent to BART:\n\n_{rec}_\n\n"
        f"Tell BART to run /pickup to implement it.",
        parse_mode="Markdown",
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return
    state = _load()
    rec  = state.get("last_recommendation") or "none"
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
        "/analyze — deep accounting analysis + recommendation for BART\n"
        "/analyze [topic] — same, focused on a specific area\n"
        "/recommend — send latest recommendation to BART\n"
        "/status — show current pending recommendation\n"
        "/clearchat — clear conversation history\n"
        "/help — this message\n\n"
        "_Ask me anything about restaurant finances, P&L, cash flow, payroll, or the dashboard._",
        parse_mode="Markdown",
    )


# ── Chat handler ──────────────────────────────────────────────────────────────
async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update):
        return

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
                system=_build_system(state),
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


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle a screenshot — passes it to Claude for accounting/UI feedback."""
    if not _is_owner(update):
        return

    await ctx.bot.send_chat_action(update.effective_chat.id, "typing")

    try:
        photo    = update.message.photo[-1]
        tg_file  = await ctx.bot.get_file(photo.file_id)
        img_bytes = await tg_file.download_as_bytearray()
        img_b64  = base64.b64encode(bytes(img_bytes)).decode()
        caption  = update.message.caption or (
            "Review this screenshot from an accounting perspective. "
            "What financial data is shown? Is it clear and useful for a restaurant owner? "
            "What's missing or could be improved?"
        )

        state   = _load()
        history = state.get("chat_history", [])

        vision_messages = history + [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64},
                    },
                    {"type": "text", "text": caption},
                ],
            }
        ]

        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=_build_system(state),
            tools=_CHAT_TOOLS,
            messages=vision_messages,
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

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    logger.info("CHET started, polling…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
