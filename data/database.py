"""
PostgreSQL read/write layer via SQLAlchemy.
All pages query through this module.

Connection URL priority:
  1. st.secrets["database"]["url"]  (Streamlit Cloud)
  2. DATABASE_URL environment variable  (GitHub Actions / local dev)
"""

import os
from datetime import date, timedelta
from functools import wraps

import pandas as pd
from sqlalchemy import create_engine, text


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def _get_db_url() -> str:
    # Try every possible location in order
    try:
        import streamlit as st
        # Flat key: DATABASE_URL = "..."
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
        # Nested key: [database] / url = "..."
        if "database" in st.secrets and "url" in st.secrets["database"]:
            return st.secrets["database"]["url"]
    except Exception:
        pass
    # Environment variable (GitHub Actions, local dev)
    url = os.environ.get("DATABASE_URL", "")
    if url:
        return url
    raise RuntimeError(
        "No database URL found. Add DATABASE_URL to Streamlit Cloud secrets."
    )


def get_engine():
    url = _get_db_url()
    # Supabase / Heroku may give postgres:// — SQLAlchemy needs postgresql://
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

def init_db() -> None:
    """Create all tables if they don't exist."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS daily_sales (
                date            TEXT PRIMARY KEY,
                covers          INTEGER,
                revenue         DOUBLE PRECISION,
                avg_check       DOUBLE PRECISION,
                food_cost       DOUBLE PRECISION,
                food_cost_pct   DOUBLE PRECISION
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS hourly_sales (
                date    TEXT,
                hour    INTEGER,
                covers  INTEGER,
                revenue DOUBLE PRECISION,
                PRIMARY KEY (date, hour)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS menu_items (
                name            TEXT PRIMARY KEY,
                category        TEXT,
                price           DOUBLE PRECISION,
                cost            DOUBLE PRECISION,
                quantity_sold   INTEGER,
                total_revenue   DOUBLE PRECISION,
                total_cost      DOUBLE PRECISION,
                gross_profit    DOUBLE PRECISION,
                margin_pct      DOUBLE PRECISION
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS daily_labor (
                date        TEXT,
                dept        TEXT,
                hours       DOUBLE PRECISION,
                labor_cost  DOUBLE PRECISION,
                PRIMARY KEY (date, dept)
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
                PRIMARY KEY (week_start, employee_id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS expenses (
                id          SERIAL PRIMARY KEY,
                date        TEXT,
                category    TEXT,
                vendor      TEXT,
                amount      DOUBLE PRECISION,
                description TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS cash_flow (
                date    TEXT PRIMARY KEY,
                inflow  DOUBLE PRECISION,
                outflow DOUBLE PRECISION,
                net     DOUBLE PRECISION
            )
        """))


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def upsert_df(df: pd.DataFrame, table: str) -> int:
    """Replace table contents with DataFrame rows (full refresh)."""
    engine = get_engine()
    df.to_sql(table, engine, if_exists="replace", index=False)
    return len(df)


# ---------------------------------------------------------------------------
# Read helpers — cached for Streamlit, uncached for sync.py
# ---------------------------------------------------------------------------

def _query(sql: str, params: dict | None = None) -> pd.DataFrame:
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql_query(text(sql), conn, params=params or {})


@_streamlit_cache(ttl=300)
def get_daily_sales(days: int = 90) -> pd.DataFrame:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return _query(
        "SELECT * FROM daily_sales WHERE date >= :cutoff ORDER BY date",
        {"cutoff": cutoff},
    )


@_streamlit_cache(ttl=300)
def get_hourly_sales(days: int = 30) -> pd.DataFrame:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return _query(
        """
        SELECT h.* FROM hourly_sales h
        WHERE h.date >= :cutoff
        ORDER BY h.date, h.hour
        """,
        {"cutoff": cutoff},
    )


@_streamlit_cache(ttl=300)
def get_menu_items() -> pd.DataFrame:
    return _query("SELECT * FROM menu_items ORDER BY total_revenue DESC")


@_streamlit_cache(ttl=300)
def get_daily_labor(days: int = 90) -> pd.DataFrame:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return _query(
        "SELECT * FROM daily_labor WHERE date >= :cutoff ORDER BY date",
        {"cutoff": cutoff},
    )


@_streamlit_cache(ttl=300)
def get_weekly_payroll(weeks: int = 12) -> pd.DataFrame:
    cutoff = (date.today() - timedelta(days=weeks * 7)).isoformat()
    return _query(
        "SELECT * FROM weekly_payroll WHERE week_start >= :cutoff ORDER BY week_start, dept",
        {"cutoff": cutoff},
    )


@_streamlit_cache(ttl=300)
def get_expenses(days: int = 90) -> pd.DataFrame:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return _query(
        "SELECT * FROM expenses WHERE date >= :cutoff ORDER BY date DESC",
        {"cutoff": cutoff},
    )


@_streamlit_cache(ttl=300)
def get_cash_flow(days: int = 90) -> pd.DataFrame:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return _query(
        "SELECT * FROM cash_flow WHERE date >= :cutoff ORDER BY date",
        {"cutoff": cutoff},
    )


@_streamlit_cache(ttl=300)
def get_kpi_today() -> dict:
    sales = _query("SELECT * FROM daily_sales ORDER BY date DESC LIMIT 1")
    if sales.empty:
        return {}
    row = sales.iloc[0]
    labor = _query(
        "SELECT SUM(labor_cost) as labor_cost, SUM(hours) as hours FROM daily_labor WHERE date = :d",
        {"d": row["date"]},
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
