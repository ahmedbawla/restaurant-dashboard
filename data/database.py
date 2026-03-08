"""
PostgreSQL read/write layer via SQLAlchemy.
All pages query through this module.

Connection URL priority:
  1. st.secrets["database"]["url"]  (Streamlit Cloud)
  2. DATABASE_URL environment variable  (GitHub Actions / local dev)
"""

import os
from datetime import date, timedelta

import bcrypt
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def _get_db_url() -> str:
    try:
        import streamlit as st
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
        if "database" in st.secrets and "url" in st.secrets["database"]:
            return st.secrets["database"]["url"]
    except Exception:
        pass
    url = os.environ.get("DATABASE_URL", "")
    if url:
        return url
    raise RuntimeError(
        "No database URL found. Add DATABASE_URL to Streamlit Cloud secrets."
    )


def get_engine():
    url = _get_db_url()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(url, pool_pre_ping=True)


# ---------------------------------------------------------------------------
# Cache helper — transparent when running outside Streamlit (e.g. sync.py)
# ---------------------------------------------------------------------------

def _streamlit_cache(ttl: int = 300):
    """Applies st.cache_data(ttl=ttl) when in Streamlit context, no-op otherwise."""
    try:
        import streamlit as st
        return st.cache_data(ttl=ttl)
    except Exception:
        return lambda f: f


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

# Business tables with their composite PK columns (username-scoped)
_TABLE_PKS = {
    "daily_sales":    "username, date",
    "hourly_sales":   "username, date, hour",
    "menu_items":     "username, name",
    "daily_labor":    "username, date, dept",
    "weekly_payroll": "username, week_start, employee_id",
    "cash_flow":      "username, date",
}


def init_db() -> None:
    """Create all tables and run idempotent migrations."""
    engine = get_engine()

    # ── Step 1: Create tables (single transaction) ────────────────────────────
    with engine.begin() as conn:

        # --- users table ---
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                username              TEXT PRIMARY KEY,
                password_hash         TEXT NOT NULL,
                email                 TEXT,
                restaurant_name       TEXT NOT NULL DEFAULT '',
                use_simulated_data    BOOLEAN NOT NULL DEFAULT TRUE,
                toast_api_key         TEXT,
                toast_client_secret   TEXT,
                toast_refresh_token   TEXT,
                toast_guid            TEXT,
                paychex_client_id     TEXT,
                paychex_client_secret TEXT,
                paychex_refresh_token TEXT,
                paychex_company_id    TEXT,
                qb_client_id          TEXT,
                qb_client_secret      TEXT,
                qb_realm_id           TEXT,
                qb_refresh_token      TEXT,
                toast_username        TEXT,
                toast_password_enc    TEXT,
                paychex_username      TEXT,
                paychex_password_enc  TEXT,
                created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))

        # --- business tables ---
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS daily_sales (
                date          TEXT,
                covers        INTEGER,
                revenue       DOUBLE PRECISION,
                avg_check     DOUBLE PRECISION,
                food_cost     DOUBLE PRECISION,
                food_cost_pct DOUBLE PRECISION,
                username      TEXT NOT NULL DEFAULT 'test'
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS hourly_sales (
                date     TEXT,
                hour     INTEGER,
                covers   INTEGER,
                revenue  DOUBLE PRECISION,
                username TEXT NOT NULL DEFAULT 'test'
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS menu_items (
                name          TEXT,
                category      TEXT,
                price         DOUBLE PRECISION,
                cost          DOUBLE PRECISION,
                quantity_sold INTEGER,
                total_revenue DOUBLE PRECISION,
                total_cost    DOUBLE PRECISION,
                gross_profit  DOUBLE PRECISION,
                margin_pct    DOUBLE PRECISION,
                username      TEXT NOT NULL DEFAULT 'test'
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS daily_labor (
                date       TEXT,
                dept       TEXT,
                hours      DOUBLE PRECISION,
                labor_cost DOUBLE PRECISION,
                username   TEXT NOT NULL DEFAULT 'test'
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS weekly_payroll (
                week_start      TEXT,
                week_end        TEXT,
                employee_id     TEXT,
                employee_name   TEXT,
                dept            TEXT,
                role            TEXT,
                hourly_rate     DOUBLE PRECISION,
                employment_type TEXT,
                regular_hours   DOUBLE PRECISION,
                overtime_hours  DOUBLE PRECISION,
                total_hours     DOUBLE PRECISION,
                gross_pay       DOUBLE PRECISION,
                username        TEXT NOT NULL DEFAULT 'test'
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS expenses (
                id          SERIAL PRIMARY KEY,
                date        TEXT,
                category    TEXT,
                vendor      TEXT,
                amount      DOUBLE PRECISION,
                description TEXT,
                username    TEXT NOT NULL DEFAULT 'test'
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS cash_flow (
                date     TEXT,
                inflow   DOUBLE PRECISION,
                outflow  DOUBLE PRECISION,
                net      DOUBLE PRECISION,
                username TEXT NOT NULL DEFAULT 'test'
            )
        """))

    # ── Step 2: Column migrations (each in its own transaction so one failure
    #            doesn't block the rest) ────────────────────────────────────────

    # Add username column to pre-existing tables that may be missing it
    for tbl in list(_TABLE_PKS.keys()) + ["expenses"]:
        try:
            with engine.begin() as conn:
                conn.execute(text(
                    f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS username TEXT NOT NULL DEFAULT 'test'"
                ))
        except Exception:
            pass  # column already exists with correct type

    # Add email column to users table
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT"
        ))

    # Add oauth_state column (stores CSRF nonce during OAuth flow)
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_state TEXT"
        ))

    # Add toast_client_secret column (legacy, kept for backward compat)
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS toast_client_secret TEXT"
        ))

    # Add toast_refresh_token column (OAuth 2.0 Authorization Code flow)
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS toast_refresh_token TEXT"
        ))

    # Add paychex_refresh_token column (OAuth 2.0 Authorization Code flow)
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS paychex_refresh_token TEXT"
        ))

    # Add portal login credential columns for scraper-based access
    for col in ("toast_username", "toast_password_enc", "paychex_username", "paychex_password_enc"):
        with engine.begin() as conn:
            conn.execute(text(
                f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} TEXT"
            ))

    # Add sync tracking columns
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_sync_at TIMESTAMPTZ"
        ))
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_sync_status TEXT"
        ))

    # Track whether the QB refresh token includes the banking scope.
    # Set True by the OAuth callback; reset False on disconnect.
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS qb_banking_scope BOOLEAN NOT NULL DEFAULT FALSE"
        ))

    # One-time migration: clear stale simulated data written by the old
    # loader.py fallback (before the fix that made sync_all raise on missing creds).
    # Uses a flag column so this runs exactly once.
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS sim_fallback_cleared BOOLEAN NOT NULL DEFAULT FALSE"
        ))
    _tables_to_wipe = ["daily_sales", "hourly_sales", "menu_items",
                       "daily_labor", "weekly_payroll", "expenses", "cash_flow"]
    try:
        with engine.begin() as conn:
            rows = conn.execute(text(
                "SELECT username FROM users WHERE sim_fallback_cleared = FALSE"
            )).fetchall()
            for (uname,) in rows:
                for _tbl in _tables_to_wipe:
                    conn.execute(text(f"DELETE FROM {_tbl} WHERE username = :u"), {"u": uname})
                conn.execute(text(
                    "UPDATE users SET sim_fallback_cleared = TRUE, "
                    "last_sync_at = NULL, last_sync_status = NULL "
                    "WHERE username = :u"
                ), {"u": uname})
    except Exception:
        pass  # non-fatal — will retry next startup

    # ── Step 3: Composite PKs (each in its own transaction) ───────────────────
    for tbl, pk_cols in _TABLE_PKS.items():
        try:
            with engine.begin() as conn:
                conn.execute(text(f"""
                    DO $$
                    DECLARE v_pk TEXT;
                    BEGIN
                        SELECT constraint_name INTO v_pk
                        FROM information_schema.table_constraints
                        WHERE table_name='{tbl}' AND constraint_type='PRIMARY KEY';

                        IF v_pk IS NOT NULL AND NOT EXISTS (
                            SELECT 1 FROM information_schema.key_column_usage
                            WHERE constraint_name=v_pk AND column_name='username'
                        ) THEN
                            EXECUTE 'ALTER TABLE {tbl} DROP CONSTRAINT ' || v_pk;
                            ALTER TABLE {tbl} ADD PRIMARY KEY ({pk_cols});
                        ELSIF v_pk IS NULL THEN
                            ALTER TABLE {tbl} ADD PRIMARY KEY ({pk_cols});
                        END IF;
                    END $$;
                """))
        except Exception:
            pass  # PK already correct

    # ── Step 4: Index ─────────────────────────────────────────────────────────
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_expenses_username ON expenses(username)"
        ))


# ---------------------------------------------------------------------------
# User auth
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_user(
    username: str,
    plain_password: str,
    restaurant_name: str,
    use_simulated_data: bool = True,
    email: str | None = None,
    **api_keys,
) -> None:
    """Insert a new user. Raises ValueError if username is already taken."""
    pw_hash = hash_password(plain_password)
    engine = get_engine()
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO users (
                    username, password_hash, email, restaurant_name, use_simulated_data,
                    toast_api_key, toast_guid,
                    paychex_client_id, paychex_client_secret, paychex_company_id,
                    qb_client_id, qb_client_secret, qb_realm_id, qb_refresh_token
                ) VALUES (
                    :username, :password_hash, :email, :restaurant_name, :use_simulated_data,
                    :toast_api_key, :toast_guid,
                    :paychex_client_id, :paychex_client_secret, :paychex_company_id,
                    :qb_client_id, :qb_client_secret, :qb_realm_id, :qb_refresh_token
                )
            """), {
                "username": username,
                "password_hash": pw_hash,
                "email": email,
                "restaurant_name": restaurant_name,
                "use_simulated_data": use_simulated_data,
                "toast_api_key": api_keys.get("toast_api_key"),
                "toast_guid": api_keys.get("toast_guid"),
                "paychex_client_id": api_keys.get("paychex_client_id"),
                "paychex_client_secret": api_keys.get("paychex_client_secret"),
                "paychex_company_id": api_keys.get("paychex_company_id"),
                "qb_client_id": api_keys.get("qb_client_id"),
                "qb_client_secret": api_keys.get("qb_client_secret"),
                "qb_realm_id": api_keys.get("qb_realm_id"),
                "qb_refresh_token": api_keys.get("qb_refresh_token"),
            })
    except IntegrityError:
        raise ValueError(f"Username '{username}' is already taken.")


def get_user(username: str) -> dict | None:
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT * FROM users WHERE username = :u"),
            {"u": username},
        )
        row = result.mappings().first()
        return dict(row) if row else None


def authenticate_user(username: str, plain_password: str) -> dict | None:
    user = get_user(username)
    if user and verify_password(plain_password, user["password_hash"]):
        return user
    return None


def update_user(username: str, **fields) -> None:
    """Update allowed user fields in-place."""
    allowed = {
        "email", "restaurant_name", "password_hash",
        "toast_api_key", "toast_client_secret", "toast_guid",
        "toast_username", "toast_password_enc",
        "paychex_client_id", "paychex_client_secret", "paychex_company_id",
        "paychex_username", "paychex_password_enc",
        "qb_realm_id", "qb_refresh_token", "oauth_state", "qb_banking_scope",
        "use_simulated_data",
        "last_sync_at", "last_sync_status",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(f"UPDATE users SET {set_clause} WHERE username = :username"),
            {**updates, "username": username},
        )


def user_has_data(username: str) -> bool:
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT COUNT(*) FROM daily_sales WHERE username = :u"),
            {"u": username},
        )
        return (result.scalar() or 0) > 0


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def clear_user_data(username: str) -> None:
    """Delete all business data rows for a user (leaves user account intact)."""
    tables = ["daily_sales", "hourly_sales", "menu_items",
              "daily_labor", "weekly_payroll", "expenses", "cash_flow"]
    engine = get_engine()
    with engine.begin() as conn:
        for tbl in tables:
            conn.execute(text(f"DELETE FROM {tbl} WHERE username = :u"), {"u": username})
    update_user(username, last_sync_at=None, last_sync_status=None)


def upsert_df(df: pd.DataFrame, table: str, username: str) -> int:
    """Delete user's existing rows then append new rows (full per-user refresh)."""
    df = df.copy()
    df["username"] = username
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {table} WHERE username = :u"), {"u": username})
        df.to_sql(table, conn, if_exists="append", index=False)
    return len(df)


# ---------------------------------------------------------------------------
# Read helpers — cached for Streamlit, uncached for sync.py
# ---------------------------------------------------------------------------

def _query(sql: str, params: dict | None = None) -> pd.DataFrame:
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql_query(text(sql), conn, params=params or {})


def _date_clauses(start_date: str | None, end_date: str | None, col: str = "date") -> tuple[str, dict]:
    """Return (extra WHERE clauses string, extra params dict) for date filtering."""
    clauses, params = [], {}
    if start_date:
        clauses.append(f"{col} >= :start_date")
        params["start_date"] = start_date
    if end_date:
        clauses.append(f"{col} <= :end_date")
        params["end_date"] = end_date
    return (" AND " + " AND ".join(clauses)) if clauses else "", params


@_streamlit_cache(ttl=600)
def get_date_range(username: str) -> tuple[str, str]:
    """Return (min_date, max_date) ISO strings across ALL of the user's data tables.

    Checks daily_sales, expenses, daily_labor, and cash_flow so that the date
    picker reflects the earliest and latest data available from any source,
    not just Toast POS sales.
    """
    result = _query(
        """
        SELECT MIN(d) AS min_d, MAX(d) AS max_d FROM (
            SELECT date AS d FROM daily_sales  WHERE username = :u
            UNION ALL
            SELECT date AS d FROM expenses     WHERE username = :u
            UNION ALL
            SELECT date AS d FROM daily_labor  WHERE username = :u
            UNION ALL
            SELECT date AS d FROM cash_flow    WHERE username = :u
        ) t
        """,
        {"u": username},
    )
    today          = date.today().isoformat()
    fallback_start = (date.today() - timedelta(days=89)).isoformat()
    if not result.empty and result.iloc[0]["min_d"]:
        return str(result.iloc[0]["min_d"]), str(result.iloc[0]["max_d"])
    return fallback_start, today


@_streamlit_cache(ttl=300)
def get_daily_sales(
    username: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    extra, params = _date_clauses(start_date, end_date)
    return _query(
        f"SELECT * FROM daily_sales WHERE username = :u{extra} ORDER BY date",
        {"u": username, **params},
    )


@_streamlit_cache(ttl=300)
def get_hourly_sales(
    username: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    extra, params = _date_clauses(start_date, end_date)
    return _query(
        f"SELECT * FROM hourly_sales WHERE username = :u{extra} ORDER BY date, hour",
        {"u": username, **params},
    )


@_streamlit_cache(ttl=300)
def get_menu_items(username: str) -> pd.DataFrame:
    return _query(
        "SELECT * FROM menu_items WHERE username = :u ORDER BY total_revenue DESC",
        {"u": username},
    )


@_streamlit_cache(ttl=300)
def get_daily_labor(
    username: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    extra, params = _date_clauses(start_date, end_date)
    return _query(
        f"SELECT * FROM daily_labor WHERE username = :u{extra} ORDER BY date",
        {"u": username, **params},
    )


@_streamlit_cache(ttl=300)
def get_weekly_payroll(
    username: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    extra, params = _date_clauses(start_date, end_date, col="week_start")
    return _query(
        f"SELECT * FROM weekly_payroll WHERE username = :u{extra} ORDER BY week_start, dept",
        {"u": username, **params},
    )


@_streamlit_cache(ttl=300)
def get_expenses(
    username: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    extra, params = _date_clauses(start_date, end_date)
    return _query(
        f"SELECT * FROM expenses WHERE username = :u{extra} ORDER BY date DESC",
        {"u": username, **params},
    )


@_streamlit_cache(ttl=300)
def get_cash_flow(
    username: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    extra, params = _date_clauses(start_date, end_date)
    return _query(
        f"SELECT * FROM cash_flow WHERE username = :u{extra} ORDER BY date",
        {"u": username, **params},
    )


@_streamlit_cache(ttl=300)
def get_kpi_today(username: str, as_of_date: str | None = None) -> dict:
    """KPIs for the most recent day on or before as_of_date (defaults to latest)."""
    extra = "AND date <= :as_of" if as_of_date else ""
    params: dict = {"u": username}
    if as_of_date:
        params["as_of"] = as_of_date
    sales = _query(
        f"SELECT * FROM daily_sales WHERE username = :u {extra} ORDER BY date DESC LIMIT 1",
        params,
    )
    if sales.empty:
        return {}
    row = sales.iloc[0]
    labor = _query(
        "SELECT SUM(labor_cost) as labor_cost, SUM(hours) as hours "
        "FROM daily_labor WHERE username = :u AND date = :d",
        {"u": username, "d": row["date"]},
    )
    labor_cost = float(labor["labor_cost"].iloc[0] or 0)
    revenue    = float(row["revenue"])
    food_cost  = float(row["food_cost"])
    labor_pct  = (labor_cost / revenue * 100) if revenue else 0
    food_pct   = float(row["food_cost_pct"])
    return {
        "date":           row["date"],
        "revenue":        revenue,
        "covers":         int(row["covers"]),
        "avg_check":      float(row["avg_check"]),
        "food_cost":      food_cost,
        "food_cost_pct":  food_pct,
        "labor_cost":     labor_cost,
        "labor_cost_pct": round(labor_pct, 2),
        "prime_cost_pct": round(food_pct + labor_pct, 2),
        "net_profit":     round(revenue - food_cost - labor_cost, 2),
    }
