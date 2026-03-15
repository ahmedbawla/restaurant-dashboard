"""
Entry point — handles auth, global date range, and page routing.
Run with: python -m streamlit run app.py
"""

import calendar as _calendar
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

from auth import require_auth, render_sidebar_logout, seed_test_user
from components.theme import apply_professional_theme
from data import database as db
from data.loader import _has_toast_scraper_creds, _has_paychex_scraper_creds
from data.sync import sync_all, sync_simulated

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="TableMetrics",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_professional_theme()

# ── Run DB migrations on every startup (idempotent) ──────────────────────────
db.init_db()


# ── QuickBooks OAuth callback ─────────────────────────────────────────────────
# Intuit redirects back with ?code=...&state=...&realmId=...
# Handle this BEFORE the auth gate — user may arrive in a fresh session.
_qp = st.query_params

# DEBUG: log raw query params to DB so we can confirm whether Intuit's redirect
# is reaching this script with ?code=&state=&realmId= intact.
_raw_qp = dict(_qp)
if _raw_qp:
    try:
        _debug_state = _raw_qp.get("state", "")
        if _debug_state:
            try:
                from utils.oauth_quickbooks import decode_state as _ds
                _du, _ = _ds(_debug_state)
                _debug_msg = (
                    f"QP_DEBUG: keys={list(_raw_qp.keys())} "
                    f"error={repr(_raw_qp.get('error',''))} "
                    f"error_description={repr(_raw_qp.get('error_description',''))} "
                    f"realmId={repr(_raw_qp.get('realmId',''))}"
                )
                db.update_user(_du, last_sync_status=_debug_msg)
            except Exception:
                pass
    except Exception:
        pass
if "code" in _qp and "state" in _qp:
    from utils.oauth_quickbooks import decode_state, exchange_code
    _oauth_error = ""
    _qb_username = ""
    # Read all params BEFORE clearing them
    _qb_code     = _qp.get("code", "")
    _qb_state    = _qp.get("state", "")
    _qb_realm_id = _qp.get("realmId", "")
    st.query_params.clear()   # clear URL immediately — must happen before any rerun
    try:
        _qb_username, _nonce = decode_state(_qb_state)
        _tokens = exchange_code(_qb_code)
        if not _qb_realm_id or not _tokens.get("refresh_token"):
            _oauth_error = (
                f"Intuit did not return expected fields. "
                f"realmId={repr(_qb_realm_id)}, "
                f"refresh_token present={bool(_tokens.get('refresh_token'))}"
            )
        else:
            db.update_user(
                _qb_username,
                qb_realm_id        = _qb_realm_id,
                qb_refresh_token   = _tokens["refresh_token"],
                oauth_state        = None,
                use_simulated_data = False,
            )
            _refreshed_user = db.get_user(_qb_username)
            # Set user in session state — do NOT rerun, let the script continue.
            # st.rerun() on Streamlit Cloud can drop the new session state on cold starts.
            st.session_state["user"]              = dict(_refreshed_user)
            st.session_state["qb_just_connected"] = True
            st.session_state["_pending_set_cookie"] = True
    except Exception as _exc:
        _oauth_error = f"QuickBooks token exchange failed: {_exc}"
    if _oauth_error:
        # Write to DB so the error survives even if the session resets
        try:
            if _qb_username:
                db.update_user(_qb_username, last_sync_status=f"QB_OAUTH_ERROR: {_oauth_error}")
        except Exception:
            pass
        st.session_state["_sync_flash"] = [
            {"type": "error", "text": f"QuickBooks: {_oauth_error}"},
        ]
    # Do NOT st.rerun() — let the script continue so session_state["user"] is used
    # immediately by require_auth() on this same execution.

# ── Seed demo account once per session ───────────────────────────────────────
if "seeded" not in st.session_state:
    seed_test_user()
    st.session_state["seeded"] = True

# ── Auth gate ─────────────────────────────────────────────────────────────────
user     = require_auth()
username = user["username"]
render_sidebar_logout()

# ── Session cookie — set after auth renders correctly ─────────────────────────
if st.session_state.pop("_pending_set_cookie", None):
    from auth import _set_session_cookie
    _set_session_cookie(username)

# ── QB sync — fires on new connection OR whenever a QB-connected user logs in ─
_run_qb_sync = (
    st.session_state.pop("qb_just_connected", False)
    or st.session_state.pop("_trigger_qb_sync", False)
)
if _run_qb_sync:
    _fresh_user = db.get_user(username)
    if _fresh_user.get("qb_realm_id") and _fresh_user.get("qb_refresh_token"):
        from data.sync import sync_all as _sync_all
        with st.spinner("Syncing QuickBooks data…"):
            _qb_res = _sync_all(_fresh_user)
        _qb_err  = _qb_res.get("quickbooks", {}).get("error")
        _qb_rows = _qb_res.get("quickbooks", {}).get("rows", 0)
        if _qb_err:
            st.session_state["_sync_flash"] = [
                {"type": "error", "text": f"QuickBooks sync failed: {_qb_err}"},
            ]
        elif _qb_rows == 0:
            st.session_state["_sync_flash"] = [
                {"type": "warning", "text": "QuickBooks synced but returned 0 rows — check your date range in QB."},
            ]
        else:
            st.session_state["_sync_flash"] = [
                {"type": "success", "text": f"QuickBooks synced {_qb_rows} rows."},
            ]
        st.session_state["user"] = db.get_user(username)
        st.cache_data.clear()
        st.rerun()

# ── Global date range selector ────────────────────────────────────────────────
min_str, max_str = db.get_date_range(username)
min_d = date.fromisoformat(min_str)
max_d = date.fromisoformat(max_str)

def _parse_date_query(text: str):
    """Parse natural language into (start_date, end_date) or None."""
    import re
    import calendar as _cal

    t = text.strip().lower()
    today = date.today()

    MONTHS = {
        "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
        "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
        "jan":1,"feb":2,"mar":3,"apr":4,"jun":6,"jul":7,"aug":8,
        "sep":9,"sept":9,"oct":10,"nov":11,"dec":12,
    }

    def _mrange(y, m):
        return date(y, m, 1), date(y, m, _cal.monthrange(y, m)[1])

    # relative shorthands
    if "last month" in t:
        prev = (today.replace(day=1) - timedelta(days=1))
        return _mrange(prev.year, prev.month)
    if "this month" in t or "current month" in t:
        return _mrange(today.year, today.month)
    if "last year" in t:
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    if "this year" in t or "current year" in t:
        return date(today.year, 1, 1), today
    if "last week" in t:
        _end = today - timedelta(days=today.weekday() + 1)
        return _end - timedelta(days=6), _end
    if "this week" in t:
        return today - timedelta(days=today.weekday()), today

    # quarters: "q1 2025", "2025 q3", "first quarter 2025"
    _qm = re.search(r"q([1-4])\s*[,\s]*(\d{4})", t) or re.search(r"(\d{4})\s*q([1-4])", t)
    if _qm:
        _g = _qm.groups()
        _q, _y = (int(_g[0]), int(_g[1])) if len(_g[0]) == 1 else (int(_g[1]), int(_g[0]))
        _sm, _em = (_q - 1) * 3 + 1, _q * 3
        return date(_y, _sm, 1), date(_y, _em, _cal.monthrange(_y, _em)[1])
    for _wrd, _qn in {"first":1,"second":2,"third":3,"fourth":4,"1st":1,"2nd":2,"3rd":3,"4th":4}.items():
        if _wrd + " quarter" in t:
            _ym = re.search(r"\b(\d{4})\b", t)
            _y  = int(_ym.group(1)) if _ym else today.year
            _sm, _em = (_qn - 1) * 3 + 1, _qn * 3
            return date(_y, _sm, 1), date(_y, _em, _cal.monthrange(_y, _em)[1])

    # ranges: "jan to march 2025", "from feb 2024 to apr 2025", "jan 2025 - mar 2025"
    _rp = [
        r"(?:from\s+)?(\w+)\s+(\d{4})\s+(?:to|through|until|-)\s+(\w+)\s+(\d{4})",
        r"(?:from\s+)?(\w+)\s+to\s+(\w+)\s+(\d{4})",
        r"(?:from\s+)?(\w+)\s*-\s*(\w+)\s+(\d{4})",
    ]
    for _pat in _rp:
        _m = re.search(_pat, t)
        if _m:
            _g = _m.groups()
            if len(_g) == 4 and _g[0] in MONTHS and _g[2] in MONTHS:
                return date(int(_g[1]), MONTHS[_g[0]], 1), date(int(_g[3]), MONTHS[_g[2]], _cal.monthrange(int(_g[3]), MONTHS[_g[2]])[1])
            if len(_g) == 3 and _g[0] in MONTHS and _g[1] in MONTHS:
                _y = int(_g[2])
                return date(_y, MONTHS[_g[0]], 1), date(_y, MONTHS[_g[1]], _cal.monthrange(_y, MONTHS[_g[1]])[1])

    # single month + year: "february 2025", "feb of 2025"
    for _name, _num in MONTHS.items():
        if re.search(r"\b" + _name + r"\b", t):
            _ym = re.search(r"\b(\d{4})\b", t)
            _y  = int(_ym.group(1)) if _ym else today.year
            return _mrange(_y, _num)

    # year only: "2025", "in 2025"
    _ym = re.search(r"\b(20\d{2}|19\d{2})\b", t)
    if _ym:
        _y = int(_ym.group(1))
        return date(_y, 1, 1), date(_y, 12, 31)

    return None

with st.sidebar:
    st.divider()
    st.caption("ANALYSIS PERIOD")

    _view = st.selectbox(
        "View",
        ["Weekly", "Monthly", "Current Quarter", "Last Quarter", "Annual", "Custom"],
        key="date_view_select",
    )

    _today = date.today()

    if _view == "Weekly":
        # Last full 7 days of available data
        _start_d = max_d - timedelta(days=6)
        _end_d   = max_d

    elif _view == "Monthly":
        # Rolling 30 days ending today
        _start_d = _today - timedelta(days=30)
        _end_d   = _today

    elif _view == "Current Quarter":
        # Quarter that contains today, from its first day through its last day
        _cq      = (_today.month - 1) // 3 + 1
        _cq_sm   = (_cq - 1) * 3 + 1
        _cq_em   = _cq * 3
        _start_d = date(_today.year, _cq_sm, 1)
        _end_d   = date(_today.year, _cq_em,
                        _calendar.monthrange(_today.year, _cq_em)[1])

    elif _view == "Last Quarter":
        _cur_q = (_today.month - 1) // 3 + 1
        if _cur_q == 1:
            _start_d = date(_today.year - 1, 10, 1)
            _end_d   = date(_today.year - 1, 12, 31)
        else:
            _pq      = _cur_q - 1
            _sm      = (_pq - 1) * 3 + 1
            _em      = _pq * 3
            _start_d = date(_today.year, _sm, 1)
            _end_d   = date(_today.year, _em,
                            _calendar.monthrange(_today.year, _em)[1])

    elif _view == "Annual":
        # Rolling 365 days ending today
        _start_d = _today - timedelta(days=365)
        _end_d   = _today

    else:  # Custom
        _nl_input = st.text_input(
            "Describe a date range",
            placeholder="e.g. february 2025, q1 2025, jan to march 2025…",
            key="nl_date_input",
        )
        _nl_result = _parse_date_query(_nl_input) if _nl_input.strip() else None
        if _nl_result:
            _start_d, _end_d = _nl_result
            st.caption(f"📅 {_start_d.strftime('%b %d, %Y')} → {_end_d.strftime('%b %d, %Y')}")
        elif _nl_input.strip():
            st.warning("Couldn't parse that. Try: *february 2025*, *q1 2025*, *jan to march 2025*, *last month*…")
            _start_d, _end_d = max_d - timedelta(days=6), max_d
        else:
            _start_d, _end_d = max_d - timedelta(days=6), max_d

    if True:
        # Clamp to the range of data we actually have
        _start_d = max(min_d, _start_d)
        _end_d   = min(max_d, _end_d)
        if _start_d > _end_d:
            st.caption("No data available for this period — showing most recent data.")
            _start_d = _end_d = max_d

    st.session_state["start_date"] = _start_d.isoformat()
    st.session_state["end_date"]   = _end_d.isoformat()

    # ── Data controls ─────────────────────────────────────────────────────────
    st.divider()
    _uses_scraper = (
        not user.get("use_simulated_data") and
        (_has_toast_scraper_creds(user) or _has_paychex_scraper_creds(user))
    )
    last_sync   = user.get("last_sync_at")
    last_status = user.get("last_sync_status") or ""

    if last_sync:
        st.caption(f"Last sync: {str(last_sync)[:16]} UTC")
        if last_status not in ("ok", "demo"):
            st.warning("Last sync had errors — check Account settings.")
    else:
        st.caption("No data synced yet.")

    if _uses_scraper:
        st.caption("Portal sync (Toast/Paychex) runs nightly via GitHub Actions.")

    # Sync Now is always available — errors surface as messages
    if st.button("Sync Now", use_container_width=True, key="sidebar_sync"):
        with st.spinner("Syncing…"):
            _res = sync_all(user)
        _msgs = []
        for _s, _r in _res.items():
            if _r["error"]:
                if "No " in _r["error"] and "credentials configured" in _r["error"]:
                    _msgs.append({"type": "info", "text": f"{_s}: not connected — go to Account Settings to add credentials."})
                else:
                    _msgs.append({"type": "error", "text": f"{_s}: {_r['error']}"})
            elif _r["rows"] == 0:
                _msgs.append({"type": "warning", "text": f"{_s}: sync succeeded but returned 0 rows."})
        real_rows = sum(r["rows"] for r in _res.values())
        if all(r["error"] and "credentials configured" in (r["error"] or "") for r in _res.values()):
            _msgs = [{"type": "info", "text": "No integrations connected. Go to Account Settings to connect Toast, Paychex, or QuickBooks — or use Load Demo Data to preview the dashboard."}]
        elif not any(r["error"] for r in _res.values()):
            _msgs.append({"type": "success", "text": f"Synced {real_rows} rows."})
        st.session_state["_sync_flash"] = _msgs
        st.session_state["user"] = db.get_user(username)
        st.cache_data.clear()
        st.rerun()

    if username == "test":
        if st.button("Load Demo Data", use_container_width=True, key="sidebar_demo"):
            with st.spinner("Loading demo data…"):
                sync_simulated(user)
            st.session_state["_sync_flash"] = [{"type": "success", "text": "Demo data loaded."}]
            st.session_state["user"] = db.get_user(username)
            st.cache_data.clear()
            st.rerun()

    # Display any flash messages from previous sync/demo action
    for _msg in st.session_state.pop("_sync_flash", []):
        getattr(st, _msg["type"])(_msg["text"])

# ── Navigation ────────────────────────────────────────────────────────────────
_pages = [
    st.Page("pages/summary.py",      title="Summary",          icon="🏠"),
    st.Page("pages/1_Spending.py",   title="Spending",         icon="💳"),
    st.Page("pages/2_Payroll.py",    title="Payroll",          icon="👥"),
    st.Page("pages/3_Inventory.py",  title="Inventory",        icon="🥩"),
    st.Page("pages/4_Sales.py",      title="Sales",            icon="📈"),
    st.Page("pages/5_Reports.py",    title="Reports",          icon="📄"),
    st.Page("pages/6_Account.py",    title="Account Settings", icon="⚙️"),
]
# AI Assistant page (pages/7_Chat.py) exists but is not exposed in nav yet
pg = st.navigation(_pages)
pg.run()
