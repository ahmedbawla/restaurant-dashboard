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
if "code" in _qp and "state" in _qp:
    from utils.oauth_quickbooks import decode_state, exchange_code
    _oauth_error = ""
    try:
        _qb_username, _nonce = decode_state(_qp["state"])
        _stored = db.get_user(_qb_username)
        if _stored and _stored.get("oauth_state") == _nonce:
            _tokens   = exchange_code(_qp["code"])
            _realm_id = _qp.get("realmId", "")
            db.update_user(
                _qb_username,
                qb_realm_id        = _realm_id,
                qb_refresh_token   = _tokens["refresh_token"],
                oauth_state        = None,
                use_simulated_data = False,
                qb_banking_scope   = True,  # SCOPES now always includes banking
            )
            _refreshed_user = db.get_user(_qb_username)
            st.session_state["user"] = dict(_refreshed_user)
            st.session_state["qb_just_connected"] = True
            from auth import _set_session_cookie
            _set_session_cookie(_qb_username)
        else:
            _oauth_error = "OAuth state mismatch — please try connecting again."
    except Exception as _exc:
        _oauth_error = f"QuickBooks connection failed: {_exc}"
    st.query_params.clear()
    if _oauth_error:
        st.session_state["oauth_error"] = _oauth_error
    st.rerun()

# ── Seed demo account once per session ───────────────────────────────────────
if "seeded" not in st.session_state:
    seed_test_user()
    st.session_state["seeded"] = True

# ── Auth gate ─────────────────────────────────────────────────────────────────
user     = require_auth()
username = user["username"]
render_sidebar_logout()

# ── QB post-connect sync ──────────────────────────────────────────────────────
if st.session_state.pop("qb_just_connected", False):
    from data.sync import sync_all as _sync_all
    with st.spinner("QuickBooks connected — syncing your data now…"):
        _qb_res = _sync_all(db.get_user(username))
    _qb_err  = _qb_res.get("quickbooks", {}).get("error")
    _qb_rows = _qb_res.get("quickbooks", {}).get("rows", 0)
    if _qb_err:
        st.session_state["_sync_flash"] = [
            {"type": "error", "text": f"QuickBooks sync failed: {_qb_err}"},
        ]
    elif _qb_rows == 0:
        st.session_state["_sync_flash"] = [
            {"type": "warning", "text": "QuickBooks connected but no data was returned."},
        ]
    else:
        st.session_state["_sync_flash"] = [
            {"type": "success", "text": f"QuickBooks connected and synced {_qb_rows} rows."},
        ]
    st.session_state["user"] = db.get_user(username)
    st.cache_data.clear()
    st.rerun()

# ── Global date range selector ────────────────────────────────────────────────
min_str, max_str = db.get_date_range(username)
min_d = date.fromisoformat(min_str)
max_d = date.fromisoformat(max_str)

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
        _default_start = max(min_d, max_d - timedelta(days=89))
        _picked = st.date_input(
            "Date Range",
            value=(_default_start, max_d),
            min_value=min_d,
            max_value=max_d,
            key="global_date_range",
        )
        if isinstance(_picked, (list, tuple)) and len(_picked) == 2:
            _start_d, _end_d = _picked[0], _picked[1]
        else:
            _start_d, _end_d = _default_start, max_d

    if _view != "Custom":
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
pg = st.navigation([
    st.Page("pages/summary.py",      title="Summary",          icon="🏠"),
    st.Page("pages/1_Spending.py",   title="Spending",         icon="💳"),
    st.Page("pages/2_Payroll.py",    title="Payroll",          icon="👥"),
    st.Page("pages/3_Inventory.py",  title="Inventory",        icon="🥩"),
    st.Page("pages/4_Sales.py",      title="Sales",            icon="📈"),
    st.Page("pages/5_Reports.py",    title="Reports",          icon="📄"),
    st.Page("pages/6_Account.py",    title="Account Settings", icon="⚙️"),
])
pg.run()
