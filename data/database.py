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
    with engine.begin() as conn:

        # --- users table ---
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                username              TEXT PRIMARY KEY,
                password_hash         TEXT NOT NULL,
                restaurant_name       TEXT NOT NULL DEFAULT '',
                use_simulated_data    BOOLEAN NOT NULL DEFAULT TRUE,
                toast_api_key         TEXT,
                toast_guid            TEXT,
                paychex_client_id     TEXT,
                paychex_client_secret TEXT,
                paychex_company_id    TEXT,
                qb_client_id          TEXT,
                qb_client_secret      TEXT,
                qb_realm_id           TEXT,
                qb_refresh_token      TEXT,
                created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))

        # --- business tables (create if not exist, with username column) ---
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

        # --- idempotent migration: add username column to pre-existing tables ---
        for tbl in list(_TABLE_PKS.keys()) + ["expenses"]:
            conn.execute(text(f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='{tbl}' AND column_name='username'
                    ) THEN
                        ALTER TABLE {tbl} ADD COLUMN username TEXT NOT NULL DEFAULT 'test';
                        ALTER TABLE {tbl} ALTER COLUMN username DROP DEFAULT;
                    END IF;
                END $$;
            """))

        # --- idempotent composite PKs for scoped tables ---
        for tbl, pk_cols in _TABLE_PKS.items():
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

        # expenses: index on username (no PK change — id is the PK)
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
    **api_keys,
) -> None:
    """Insert a new user. Raises ValueError if username is already taken."""
    pw_hash = hash_password(plain_password)
    engine = get_engine()
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO users (
                    username, password_hash, restaurant_name, use_simulated_data,
                    toast_api_key, toast_guid,
                    paychex_client_id, paychex_client_secret, paychex_company_id,
                    qb_client_id, qb_client_secret, qb_realm_id, qb_refresh_token
                ) VALUES (
                    :username, :password_hash, :restaurant_name, :use_simulated_data,
                    :toast_api_key, :toast_guid,
                    :paychex_client_id, :paychex_client_secret, :paychex_company_id,
                    :qb_client_id, :qb_client_secret, :qb_realm_id, :qb_refresh_token
                )
            """), {
                "username": username,
                "password_hash": pw_hash,
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


@_streamlit_cache(ttl=300)
def get_daily_sales(username: str, days: int = 90) -> pd.DataFrame:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return _query(
        "SELECT * FROM daily_sales WHERE username = :u AND date >= :cutoff ORDER BY date",
        {"u": username, "cutoff": cutoff},
    )


@_streamlit_cache(ttl=300)
def get_hourly_sales(username: str, days: int = 30) -> pd.DataFrame:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return _query(
        """
        SELECT * FROM hourly_sales
        WHERE username = :u AND date >= :cutoff
        ORDER BY date, hour
        """,
        {"u": username, "cutoff": cutoff},
    )


@_streamlit_cache(ttl=300)
def get_menu_items(username: str) -> pd.DataFrame:
    return _query(
        "SELECT * FROM menu_items WHERE username = :u ORDER BY total_revenue DESC",
        {"u": username},
    )


@_streamlit_cache(ttl=300)
def get_daily_labor(username: str, days: int = 90) -> pd.DataFrame:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return _query(
        "SELECT * FROM daily_labor WHERE username = :u AND date >= :cutoff ORDER BY date",
        {"u": username, "cutoff": cutoff},
    )


@_streamlit_cache(ttl=300)
def get_weekly_payroll(username: str, weeks: int = 12) -> pd.DataFrame:
    cutoff = (date.today() - timedelta(days=weeks * 7)).isoformat()
    return _query(
        "SELECT * FROM weekly_payroll WHERE username = :u AND week_start >= :cutoff ORDER BY week_start, dept",
        {"u": username, "cutoff": cutoff},
    )


@_streamlit_cache(ttl=300)
def get_expenses(username: str, days: int = 90) -> pd.DataFrame:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return _query(
        "SELECT * FROM expenses WHERE username = :u AND date >= :cutoff ORDER BY date DESC",
        {"u": username, "cutoff": cutoff},
    )


@_streamlit_cache(ttl=300)
def get_cash_flow(username: str, days: int = 90) -> pd.DataFrame:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return _query(
        "SELECT * FROM cash_flow WHERE username = :u AND date >= :cutoff ORDER BY date",
        {"u": username, "cutoff": cutoff},
    )


@_streamlit_cache(ttl=300)
def get_kpi_today(username: str) -> dict:
    sales = _query(
        "SELECT * FROM daily_sales WHERE username = :u ORDER BY date DESC LIMIT 1",
        {"u": username},
    )
    if sales.empty:
        return {}
    row = sales.iloc[0]
    labor = _query(
        "SELECT SUM(labor_cost) as labor_cost, SUM(hours) as hours FROM daily_labor WHERE username = :u AND date = :d",
        {"u": username, "d": row["date"]},
    )
    labor_cost = float(labor["labor_cost"].iloc[0] or 0)
    revenue = float(row["revenue"])
    food_cost = float(row["food_cost"])
    labor_pct = (labor_cost / revenue * 100) if revenue else 0
    food_pct = float(row["food_cost_pct"])
    return {
        "date": row["date"],
        "revenue": revenue,
        "covers": int(row["covers"]),
        "avg_check": float(row["avg_check"]),
        "food_cost": food_cost,
        "food_cost_pct": food_pct,
        "labor_cost": labor_cost,
        "labor_cost_pct": round(labor_pct, 2),
        "prime_cost_pct": round(food_pct + labor_pct, 2),
        "net_profit": round(revenue - food_cost - labor_cost, 2),
    }
