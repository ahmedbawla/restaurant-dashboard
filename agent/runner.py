"""
Autonomous coding agent — uses Claude Sonnet to improve the dashboard.
Clones the repo, makes 1-2 targeted changes, pushes to a new branch.
"""

import os
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
        "name": "write_file",
        "description": "Write or overwrite a file to implement an improvement.",
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


def run_agent(
    github_token: str,
    github_repo: str,
    anthropic_api_key: str,
    focus: str | None = None,
) -> dict:
    """
    Clone repo, run Claude Sonnet to make improvements, push to a new branch.
    Returns {"branch": str, "summary": str}.
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

        def write_file(path: str, content: str) -> str:
            full = Path(tmpdir) / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")
            return f"Written: {path}"

        def execute(name: str, inputs: dict) -> str:
            if name == "read_file":  return read_file(inputs["path"])
            if name == "list_files": return list_files(inputs["directory"])
            if name == "write_file": return write_file(inputs["path"], inputs["content"])
            if name == "git":        return _git(inputs["args"], tmpdir)
            return f"Unknown tool: {name}"

        # ── Run Claude ───────────────────────────────────────────────────────
        client = anthropic.Anthropic(api_key=anthropic_api_key)
        focus_line = f"\nFocus area: {focus}" if focus else \
                     "\nNo specific focus — choose the most impactful improvement you find."

        system = f"""You are a senior full-stack developer and co-owner of a Streamlit restaurant analytics dashboard (SaaS product). You genuinely care about making the best possible product for clients.

The app is built with: Python, Streamlit, SQLAlchemy, Supabase/PostgreSQL, Plotly, Pandas.
Pages: Summary, Spending (QuickBooks OAuth), Payroll (Paychex PDF/CSV), Inventory, Sales, Reports, Account.
Auth: username stored in st.session_state["username"]. Test account username = "test".
{focus_line}

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
2. Call read_file() on the relevant page(s)
3. Call write_file() with the complete updated file content
4. Call git("add -A && git commit -m 'agent: <short description>'")
5. ONLY NOW write your summary text (3-5 sentences: what changed, why, test on which account)

If you reach step 5 without having called write_file and git, you have failed. Start over from step 3.

## Rules
- Change at most 2 files per run
- Never touch: auth.py, data/database.py, config.json, or any file containing secrets
- All Python must be syntactically valid — read the full file before editing, write the complete updated file
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

        # Push branch — use check=True so a failed push surfaces as an error
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
        ]

        return {"branch": branch, "summary": summary, "files": changed_files}
