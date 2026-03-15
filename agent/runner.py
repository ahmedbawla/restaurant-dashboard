"""
Autonomous coding agent — uses Claude Sonnet to improve the dashboard.
Clones the repo, makes 1-2 targeted changes, pushes to a new branch.
"""

import re as _re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import anthropic

TOOLS = [
    {
        "name": "read_file",
        "description": "Read a file's contents from the repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to repo root"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_files",
        "description": "List files in a directory of the repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Directory relative to repo root. Use '.' for root.",
                },
            },
            "required": ["directory"],
        },
    },
    {
        "name": "search_code",
        "description": (
            "Search for a text or regex pattern across all Python files in the repository. "
            "Use this to find where a function is called, where a variable is set, etc. "
            "Much faster than reading every file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Text or regex pattern to search for"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "patch_file",
        "description": (
            "Make a targeted edit to an existing file by replacing old_string with new_string. "
            "PREFERRED over write_file for edits to existing files — safer and more token-efficient. "
            "old_string must appear exactly once in the file. "
            "Syntax is validated automatically after patching."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to repo root"},
                "old_string": {
                    "type": "string",
                    "description": "Exact text to find and replace (must be unique in the file — include surrounding lines if needed)",
                },
                "new_string": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Write or overwrite a file with full content. "
            "Use for new files or when a full rewrite is necessary. "
            "For edits to existing files, prefer patch_file instead. "
            "Syntax is validated automatically after writing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to repo root"},
                "content": {"type": "string", "description": "Full file content"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "git",
        "description": "Run a git command in the repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "args": {
                    "type": "string",
                    "description": "git arguments e.g. 'status' or 'diff HEAD'",
                },
            },
            "required": ["args"],
        },
    },
]

_DB_SCHEMA = """
## Database schema (PostgreSQL via SQLAlchemy — all tables scoped by `username`)

users: username(PK TEXT), password_hash, email, restaurant_name, use_simulated_data(BOOL),
  toast_api_key, toast_guid, toast_username, toast_password_enc, toast_refresh_token,
  paychex_client_id, paychex_client_secret, paychex_company_id, paychex_username,
  paychex_password_enc, paychex_refresh_token,
  qb_client_id, qb_client_secret, qb_realm_id, qb_refresh_token, qb_banking_scope(BOOL),
  phone_number, remember_token, remember_token_expires, last_sync_at, last_sync_status

daily_sales(PK: username+date): date(TEXT), covers(INT), revenue(FLOAT),
  avg_check(FLOAT), food_cost(FLOAT), food_cost_pct(FLOAT)

hourly_sales(PK: username+date+hour): date(TEXT), hour(INT), covers(INT), revenue(FLOAT)

menu_items(PK: username+name): name, category, price(FLOAT), cost(FLOAT),
  quantity_sold(INT), total_revenue(FLOAT), total_cost(FLOAT),
  gross_profit(FLOAT), margin_pct(FLOAT)

daily_labor(PK: username+date+dept): date(TEXT), dept(TEXT), hours(FLOAT), labor_cost(FLOAT)

weekly_payroll(PK: username+week_start+employee_id): week_start(TEXT), week_end,
  employee_id, employee_name, dept, role, hourly_rate(FLOAT), employment_type,
  regular_hours(FLOAT), overtime_hours(FLOAT), total_hours(FLOAT), gross_pay(FLOAT)

expenses(PK: id SERIAL): date(TEXT), category, vendor, amount(FLOAT), description

cash_flow(PK: username+date): date(TEXT), inflow(FLOAT), outflow(FLOAT), net(FLOAT)

payroll_journal_summaries(PK: id SERIAL): period_start, period_end, headcount(INT),
  total_hours(FLOAT), gross_earnings(FLOAT), net_pay(FLOAT), total_tax_liability(FLOAT)

Query helpers (all return pd.DataFrame, accept username + optional start_date/end_date):
  from data.database import (get_daily_sales, get_hourly_sales, get_menu_items,
    get_daily_labor, get_weekly_payroll, get_expenses, get_cash_flow, get_payroll_summary)
""".strip()


def _git(args: str, cwd: str) -> str:
    result = subprocess.run(
        f"git {args}",
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return (result.stdout + result.stderr).strip()[:3000]


def _validate_python(full_path: str) -> str | None:
    """Returns error string if the file has a syntax error, None if valid."""
    result = subprocess.run(
        ["python", "-m", "py_compile", full_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return (result.stderr or result.stdout).strip()
    return None


def run_agent(
    github_token: str,
    github_repo: str,
    anthropic_api_key: str,
    focus: str | None = None,
) -> dict:
    """
    Clone repo, run Claude Sonnet to make improvements, push to a new branch.
    Returns {"branch": str, "summary": str, "files": list[str]}.
    """
    branch = f"agent/{datetime.now(timezone.utc).strftime('%Y-%m-%d-%H%M')}"
    repo_url = f"https://x-access-token:{github_token}@github.com/{github_repo}.git"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Clone
        subprocess.run(
            ["git", "clone", repo_url, tmpdir],
            check=True, capture_output=True, text=True,
        )
        _git("config user.email 'agent@dashboard.bot'", tmpdir)
        _git("config user.name 'Dashboard Agent'", tmpdir)
        _git(f"checkout -b {branch}", tmpdir)

        # ── Gather context for system prompt ────────────────────────────────
        git_log = _git("log --oneline -10", tmpdir)

        notes_path = Path(tmpdir) / "AGENT_NOTES.md"
        if notes_path.exists():
            notes_raw = notes_path.read_text(encoding="utf-8")[:3000]
            notes_section = f"\n\n## Your persistent notes (AGENT_NOTES.md)\n{notes_raw}"
        else:
            notes_section = (
                "\n\n## Your persistent notes (AGENT_NOTES.md)\n"
                "File does not exist yet. After your commit, create it with write_file "
                "to save observations for future runs: bugs found, things tried, "
                "patterns to avoid, feature ideas, known issues, etc."
            )

        # ── Tool implementations ─────────────────────────────────────────────
        def read_file(path: str) -> str:
            full = Path(tmpdir) / path
            if not full.exists():
                return f"File not found: {path}"
            if full.stat().st_size > 60_000:
                return f"File too large to read in full ({full.stat().st_size} bytes)."
            try:
                return full.read_text(encoding="utf-8")
            except Exception as e:
                return f"Error: {e}"

        def list_files(directory: str) -> str:
            full = Path(tmpdir) / directory
            if not full.exists():
                return f"Directory not found: {directory}"
            lines = []
            for p in sorted(full.rglob("*")):
                if not p.is_file():
                    continue
                rel = str(p.relative_to(tmpdir))
                if any(part.startswith((".", "__pycache__")) for part in Path(rel).parts):
                    continue
                lines.append(rel)
            return "\n".join(lines[:150])

        def search_code(pattern: str) -> str:
            try:
                regex = _re.compile(pattern, _re.IGNORECASE)
            except _re.error:
                regex = _re.compile(_re.escape(pattern), _re.IGNORECASE)
            matches = []
            for p in sorted(Path(tmpdir).rglob("*.py")):
                rel = str(p.relative_to(tmpdir))
                if any(part.startswith((".", "__pycache__")) for part in Path(rel).parts):
                    continue
                try:
                    lines = p.read_text(encoding="utf-8").splitlines()
                except Exception:
                    continue
                file_matches = [
                    f"  {i}: {line.rstrip()}"
                    for i, line in enumerate(lines, 1)
                    if regex.search(line)
                ]
                if file_matches:
                    matches.append(f"{rel}:\n" + "\n".join(file_matches[:10]))
                if len(matches) >= 20:
                    break
            return "\n\n".join(matches) if matches else "No matches found."

        def patch_file(path: str, old_string: str, new_string: str) -> str:
            full = Path(tmpdir) / path
            if not full.exists():
                return f"File not found: {path}"
            content = full.read_text(encoding="utf-8")
            count = content.count(old_string)
            if count == 0:
                return (
                    f"Error: old_string not found in {path}. "
                    "Check exact whitespace and indentation."
                )
            if count > 1:
                return (
                    f"Error: old_string found {count} times in {path}. "
                    "Make it more specific by including more surrounding lines."
                )
            full.write_text(content.replace(old_string, new_string, 1), encoding="utf-8")
            return f"Patched: {path}"

        def write_file(path: str, content: str) -> str:
            full = Path(tmpdir) / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")
            return f"Written: {path}"

        def execute(name: str, inputs: dict) -> str:
            if name == "read_file":
                return read_file(inputs["path"])
            if name == "list_files":
                return list_files(inputs["directory"])
            if name == "search_code":
                return search_code(inputs["pattern"])
            if name == "patch_file":
                result = patch_file(inputs["path"], inputs["old_string"], inputs["new_string"])
                if result.startswith("Patched:") and inputs["path"].endswith(".py"):
                    err = _validate_python(str(Path(tmpdir) / inputs["path"]))
                    if err:
                        return f"{result}\n\n⚠️ SYNTAX ERROR — fix this before committing:\n{err}"
                return result
            if name == "write_file":
                result = write_file(inputs["path"], inputs["content"])
                if inputs["path"].endswith(".py"):
                    err = _validate_python(str(Path(tmpdir) / inputs["path"]))
                    if err:
                        return f"{result}\n\n⚠️ SYNTAX ERROR — fix this before committing:\n{err}"
                return result
            if name == "git":
                return _git(inputs["args"], tmpdir)
            return f"Unknown tool: {name}"

        # ── Run Claude ───────────────────────────────────────────────────────
        client = anthropic.Anthropic(api_key=anthropic_api_key)
        focus_line = (
            f"\nFocus area: {focus}" if focus
            else "\nNo specific focus — choose the most impactful improvement you find."
        )

        system = f"""You are a senior full-stack developer and co-owner of a Streamlit restaurant analytics dashboard (SaaS product). You genuinely care about making the best possible product for clients.

The app is built with: Python, Streamlit, SQLAlchemy, Supabase/PostgreSQL, Plotly, Pandas.
Pages: Summary, Spending (QuickBooks OAuth), Payroll (Paychex PDF/CSV), Inventory, Sales, Reports, Account.
Auth: username stored in st.session_state["username"]. Test account username = "test".
{focus_line}

{_DB_SCHEMA}

## Recent git history (last 10 commits — do not repeat these)
{git_log}
{notes_section}

## Deployment workflow (CRITICAL — follow exactly)
New features and experimental improvements MUST be gated behind `username == "test"` so the test account gets the change first. Only bug fixes that affect all users (data errors, crashes, broken layouts) should be applied globally.

Pattern for test-only features:
```python
username = st.session_state.get("username", "")
if username == "test":
    # new feature here
```

The owner reviews your branch on the test account, then runs /deploy to release to all users.

## Your task — AUTONOMOUS mode, no human is watching
You are running fully autonomously. There is no human reading your intermediate messages.
DO NOT write any text response until AFTER you have successfully run `git commit`.
Any text you write before committing is wasted — skip it entirely.

Steps (use tools for all of these — do not describe them, just do them):
1. Call list_files(".")
2. Use search_code() to find relevant patterns, then read_file() on the target file(s)
3. Call patch_file() for targeted edits OR write_file() only if a full rewrite is truly needed
4. If patch_file/write_file reports a SYNTAX ERROR, fix it immediately before proceeding
5. Call git("add -A && git commit -m 'agent: <short description>'")
6. ONLY NOW write your summary (3-5 sentences: what changed, why, which account to test on)
7. Optionally update AGENT_NOTES.md with observations useful for future runs

If you reach step 5 without having called patch_file or write_file and git, you have failed. Start over from step 3.

## Rules
- Change at most 2 source files per run (AGENT_NOTES.md updates don't count toward this limit)
- Never touch: auth.py, data/database.py, config.json, or any file containing secrets
- All Python must be syntactically valid — fix any SYNTAX ERROR before committing
- Keep changes small and focused — this is reviewed before deploying to clients
- Think like a product partner: prioritize changes that make the dashboard more useful, accurate, and polished for restaurant owners
- Do NOT push — the bot handles pushing after you finish"""

        messages = [
            {
                "role": "user",
                "content": "Begin. Use tools only — no text until after git commit.",
            }
        ]

        def _serialize(block) -> dict:
            """Minimal serialization — only the fields the API actually needs."""
            if block.type == "text":
                return {"type": "text", "text": block.text}
            if block.type == "tool_use":
                return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
            return {"type": block.type}

        resp = None
        for _ in range(40):
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=8096,
                system=system,
                tools=TOOLS,
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
                        out = execute(block.name, block.input)
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": out,
                        })
                messages.append({"role": "user", "content": results})
            else:
                # max_tokens or any other stop reason — don't add to messages, just stop
                break

        # Verify something was actually committed before pushing
        diff_check = _git("diff HEAD~1 HEAD --name-only 2>/dev/null || echo 'no-commits'", tmpdir)
        if not diff_check.strip() or diff_check.strip() == "no-commits":
            raise RuntimeError("Agent did not commit any changes. The branch is empty.")

        # ── Descriptive branch name ──────────────────────────────────────────
        commit_msg = _git("log -1 --format=%s", tmpdir)
        slug_src = commit_msg.lower()
        if slug_src.startswith("agent: "):
            slug_src = slug_src[7:]
        slug = _re.sub(r"[^a-z0-9]+", "-", slug_src).strip("-")[:40]
        new_branch = f"agent/{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-{slug}"
        _git(f"branch -m {branch} {new_branch}", tmpdir)
        branch = new_branch

        # Push branch
        result = subprocess.run(
            f"git push origin {branch}",
            shell=True, cwd=tmpdir,
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git push failed:\n{result.stderr.strip()}")

        # Extract summary from final message
        summary = "Agent completed — no summary provided."
        if resp:
            for block in reversed(resp.content):
                if hasattr(block, "text") and block.text.strip():
                    summary = block.text.strip()
                    break

        # Record which files were changed so /promote knows what to operate on
        changed_files = [
            f.strip() for f in diff_check.splitlines()
            if f.strip() and f.strip().endswith(".py")
            and not f.strip() == "AGENT_NOTES.md"
        ]

        return {"branch": branch, "summary": summary, "files": changed_files}
