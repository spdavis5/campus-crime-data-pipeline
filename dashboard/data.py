"""Data access for the dashboard: reads the dbt marts from PostgreSQL.

Kept separate from the Streamlit UI so the queries are importable and testable on
their own. Every function takes a SQLAlchemy engine and returns a DataFrame, so
the app layer owns caching and layout while this layer owns SQL. All reads target
the ``analytics`` schema built by dbt; if those tables are missing the caller is
expected to prompt the user to run dbt first.
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


def load_kpis(engine: Engine) -> dict[str, object]:
    """Headline numbers: totals, located share, zone count, and date range."""
    query = """
        select
            count(*)                                                  as total_incidents,
            count(*) filter (where location_zone <> 'UNKNOWN')        as located_incidents,
            count(distinct location_zone) filter (where location_zone <> 'UNKNOWN') as distinct_zones,
            min(occurred_date)                                        as first_day,
            max(occurred_date)                                        as last_day
        from analytics.fct_incidents
    """
    row = pd.read_sql(query, engine).iloc[0]
    total = int(row["total_incidents"])
    located = int(row["located_incidents"])
    return {
        "total_incidents": total,
        "located_incidents": located,
        "located_pct": (located / total * 100) if total else 0.0,
        "distinct_zones": int(row["distinct_zones"]),
        "first_day": row["first_day"],
        "last_day": row["last_day"],
    }


def load_daily(engine: Engine) -> pd.DataFrame:
    """Per-day incident counts with academic-calendar context."""
    return pd.read_sql(
        "select * from analytics.mart_daily_summary order by date_day", engine
    )


def load_by_zone(engine: Engine) -> pd.DataFrame:
    """Incident counts per campus zone (excludes UNKNOWN)."""
    query = """
        select l.zone_label, count(*) as incidents
        from analytics.fct_incidents f
        join analytics.dim_location l using (location_zone)
        where not l.is_unknown
        group by l.zone_label
        order by incidents desc
    """
    return pd.read_sql(query, engine)


def load_by_category(engine: Engine) -> pd.DataFrame:
    """Incident counts per coarse type category."""
    query = """
        select t.incident_category, count(*) as incidents
        from analytics.fct_incidents f
        join analytics.dim_incident_type t using (incident_type)
        group by t.incident_category
        order by incidents desc
    """
    return pd.read_sql(query, engine)


def load_calendar_effect(engine: Engine) -> pd.DataFrame:
    """Average incidents per day, finals vs. regular days (needs a real calendar)."""
    query = """
        select
            case when is_finals then 'Finals' else 'Regular' end as day_kind,
            round(avg(total_incidents), 2)                       as avg_incidents_per_day,
            count(*)                                             as n_days
        from analytics.mart_daily_summary
        group by 1
        order by 1
    """
    return pd.read_sql(query, engine)


def load_incidents(engine: Engine) -> pd.DataFrame:
    """Incident-level detail for the explorer table."""
    query = """
        select
            f.occurred_date        as date,
            l.zone_label           as zone,
            t.incident_category    as category,
            f.incident_type        as type,
            f.incident_text        as narrative
        from analytics.fct_incidents f
        join analytics.dim_location l using (location_zone)
        left join analytics.dim_incident_type t using (incident_type)
        order by f.occurred_date desc nulls last
    """
    return pd.read_sql(query, engine)
