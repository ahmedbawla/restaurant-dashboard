"""
Accounting expert agent — reads the dashboard codebase and recommends
one specific, high-value accounting feature for BART to implement.
"""

import base64

import anthropic
import requests

_TOOLS = [
    {
        "name": "read_file",
        "description": "Read a file's full contents from the repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to repo root"},
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
                "directory": {"type": "string", "description": "Directory path, or '' for all files"},
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
                "pattern": {"type": "string", "description": "Text or regex pattern"},
            },
            "required": ["pattern"],
        },
    },
]

_DB_SCHEMA = """
Database tables (PostgreSQL, all scoped by username):
- daily_sales: date, covers(INT), revenue, avg_check, food_cost, food_cost_pct
- hourly_sales: date, hour, covers, revenue
- daily_labor: date, dept, hours, labor_cost
- weekly_payroll: week_start, employee_name, dept, role, hourly_rate, regular_hours, overtime_hours, gross_pay
- expenses: date, category, vendor, amount, description
- cash_flow: date, inflow, outflow, net
- menu_items: name, category, price, cost, quantity_sold, total_revenue, gross_profit, margin_pct
- payroll_journal_summaries: period_start/end, gross_earnings, net_pay, total_tax_liability
""".strip()


def run_accountant(
    github_token: str,
    github_repo: str,
    anthropic_api_key: str,
    focus: str | None = None,
) -> dict:
    """
    Analyze the dashboard codebase from an accounting perspective and return
    a specific, implementable feature recommendation for BART.

    Returns {"full_analysis": str, "recommendation": str}
    """

    def _gh_headers(text_match: bool = False) -> dict:
        accept = (
            "application/vnd.github.text-match+json"
            if text_match
            else "application/vnd.github.v3+json"
        )
        return {"Authorization": f"token {github_token}", "Accept": accept}

    def read_file(path: str) -> str:
        url = f"https://api.github.com/repos/{github_repo}/contents/{path}"
        resp = requests.get(url, headers=_gh_headers(), timeout=15)
        if resp.status_code != 200:
            return f"Error {resp.status_code}: {resp.json().get('message', 'not found')}"
        data = resp.json()
        if isinstance(data, list):
            return "That path is a directory — use list_files."
        content = data.get("content", "")
        if data.get("encoding") == "base64":
            return base64.b64decode(content).decode("utf-8", errors="replace")[:8000]
        return content

    def list_files(directory: str) -> str:
        url = f"https://api.github.com/repos/{github_repo}/git/trees/HEAD?recursive=1"
        resp = requests.get(url, headers=_gh_headers(), timeout=15)
        if resp.status_code != 200:
            return f"Error fetching file tree: {resp.status_code}"
        files = [
            item["path"] for item in resp.json().get("tree", [])
            if item["type"] == "blob"
            and (not directory or item["path"].startswith(directory))
            and not any(p.startswith((".", "__pycache__")) for p in item["path"].split("/"))
        ]
        return "\n".join(files[:150])

    def search_code(pattern: str) -> str:
        url = f"https://api.github.com/search/code?q={requests.utils.quote(pattern)}+repo:{github_repo}"
        resp = requests.get(url, headers=_gh_headers(text_match=True), timeout=15)
        if resp.status_code != 200:
            return f"Search error {resp.status_code}"
        items = resp.json().get("items", [])
        if not items:
            return "No matches found."
        lines = []
        for item in items[:8]:
            frags = [m.get("fragment", "") for m in item.get("text_matches", [])]
            lines.append(f"{item['path']}:\n" + "\n".join(f"  {f.strip()}" for f in frags[:2]))
        return "\n\n".join(lines)

    def execute(name: str, inputs: dict) -> str:
        if name == "read_file":   return read_file(inputs["path"])
        if name == "list_files":  return list_files(inputs.get("directory", ""))
        if name == "search_code": return search_code(inputs["pattern"])
        return f"Unknown tool: {name}"

    focus_line = (
        f"\nThe owner specifically wants you to focus on: {focus}"
        if focus
        else "\nNo specific focus — identify the highest-value gap you find."
    )

    system = f"""You are a senior restaurant accountant and CFO advisor with 20+ years of experience working with independent restaurants and small chains. You think in terms of:

- P&L management: food cost %, labor cost %, prime cost (target <60%), EBITDA, net profit margins
- Cash flow: weekly cash position, burn rate, seasonal patterns, vendor payment timing
- Menu engineering: contribution margin, star/plow-horse/puzzle/dog matrix, menu mix analysis
- Payroll: overtime exposure, labor law compliance, department cost ratios
- Cost controls: variance analysis, purchase price vs. standard cost, waste tracking
- Tax and reporting: period close, accruals, QuickBooks reconciliation

You are reviewing a Streamlit restaurant analytics SaaS dashboard to identify the single most valuable accounting or financial improvement that would make a real difference to a restaurant owner or their accountant.
{focus_line}

{_DB_SCHEMA}

## Your process
1. List the files to understand the project structure
2. Read the most relevant page files (pages/, components/)
3. Search for specific metrics or patterns if needed
4. Think hard about what a restaurant accountant would want that isn't there yet

## What makes a good recommendation
Ask yourself: "Would a restaurant's CPA or bookkeeper find this genuinely useful?" Focus on:
- Early warning signals that prevent financial surprises
- Industry-standard metrics that are missing
- Calculations that save the owner time they currently do in a spreadsheet
- Visibility into where money is leaking

## Output format
Write a concise analysis (3-5 paragraphs) covering what you found and why your recommendation matters financially.

End with a line formatted EXACTLY like this:
RECOMMENDATION: <one or two sentences describing exactly what to build — name the page, the metric, and the visualization type>

The recommendation goes directly to a coding agent, so be specific:
✓ "Add a 13-week rolling cash flow forecast chart to the Spending page using a linear regression on the last 90 days of cash_flow.net, with a dotted projection line and a 'weeks of runway' KPI card"
✗ "Improve the cash flow section" (too vague)
✗ "Add more charts" (not actionable)"""

    client = anthropic.Anthropic(api_key=anthropic_api_key)
    messages = [
        {
            "role": "user",
            "content": "Analyze the dashboard codebase and give me your best accounting recommendation.",
        }
    ]

    def _serialize(block) -> dict:
        if block.type == "text":
            return {"type": "text", "text": block.text}
        if block.type == "tool_use":
            return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
        return {"type": block.type}

    resp = None
    for _ in range(20):
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
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
                    out = execute(block.name, block.input)
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": out[:8000],
                    })
            messages.append({"role": "user", "content": results})
        else:
            break

    # Extract the full response text
    full_text = ""
    if resp:
        for block in reversed(resp.content):
            if hasattr(block, "text") and block.text.strip():
                full_text = block.text.strip()
                break

    if not full_text:
        raise RuntimeError("Accounting agent produced no output.")

    # Pull out the RECOMMENDATION line to use as BART's focus
    recommendation = ""
    for line in full_text.splitlines():
        if line.strip().upper().startswith("RECOMMENDATION:"):
            recommendation = line.split(":", 1)[-1].strip()
            break

    if not recommendation:
        # Fall back to last non-empty paragraph
        paragraphs = [p.strip() for p in full_text.split("\n\n") if p.strip()]
        recommendation = paragraphs[-1] if paragraphs else full_text[:300]

    return {"full_analysis": full_text, "recommendation": recommendation}
