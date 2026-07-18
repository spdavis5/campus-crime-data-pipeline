"""Data access for the dashboard: reads the dbt marts from PostgreSQL.

Kept separate from the Streamlit UI so the queries are importable and testable on
their own. The app loads incident-level detail once (enriched with the location,
category, and academic-calendar dimensions) plus the full date spine, then derives
every chart in pandas from the user's current filter selection — so a single set
of sidebar filters drives the whole dashboard consistently. All reads target the
``analytics`` schema built by dbt.
"""

from __future__ import annotations

import os

import pandas as pd
from sqlalchemy import Engine, create_engine


def get_engine() -> Engine:
    """Build a SQLAlchemy engine from the shared POSTGRES_* environment variables."""
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "byu_police_beat")
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "postgres")
    return create_engine(f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}")


def marts_exist(engine: Engine) -> bool:
    """True if the dbt marts have been built (fct_incidents present)."""
    query = "select to_regclass('analytics.fct_incidents') is not null as ok"
    return bool(pd.read_sql(query, engine)["ok"].iloc[0])


def load_incidents(engine: Engine) -> pd.DataFrame:
    """Incident-level detail joined to every dimension, including calendar context.

    One row per incident. Calendar columns come from dim_date and are null for the
    few incidents whose date could not be parsed; boolean flags are coalesced to
    False so downstream grouping is clean.
    """
    query = """
        select
            f.occurred_date                       as date,
            l.zone_label                          as zone,
            l.is_unknown                          as zone_unknown,
            coalesce(t.incident_category, 'Uncategorized') as category,
            f.incident_type                       as type,
            f.incident_text                       as narrative,
            d.semester                            as semester,
            coalesce(d.is_finals, false)          as is_finals,
            coalesce(d.is_break, false)           as is_break,
            coalesce(d.is_game_day, false)        as is_game_day,
            coalesce(d.is_weekend, false)         as is_weekend
        from analytics.fct_incidents f
        join analytics.dim_location l using (location_zone)
        left join analytics.dim_incident_type t using (incident_type)
        left join analytics.dim_date d on d.date_day = f.occurred_date
        order by f.occurred_date desc nulls last
    """
    frame = pd.read_sql(query, engine)
    frame["date"] = pd.to_datetime(frame["date"])
    return frame


def load_date_spine(engine: Engine) -> pd.DataFrame:
    """Every calendar day in range with its academic-calendar context.

    Sourced from mart_daily_summary so days with zero incidents still appear in
    trend lines and per-day averages are computed over real calendar days.
    """
    frame = pd.read_sql(
        """
        select date_day, semester, is_finals, is_break, is_game_day, is_weekend
        from analytics.mart_daily_summary
        order by date_day
        """,
        engine,
    )
    frame["date_day"] = pd.to_datetime(frame["date_day"])
    return frame
