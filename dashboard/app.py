"""BYU Campus Safety dashboard — the serving layer over the dbt marts.

Reads the analytics star schema from PostgreSQL and presents incident trends over
the academic calendar, a breakdown by campus zone and category, and an incident
explorer. Run via the dashboard container (see docker-compose.yml).
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

# Streamlit puts the script's own directory on sys.path, so data.py imports directly.
import data

st.set_page_config(page_title="BYU Campus Safety Analytics", page_icon="🚓", layout="wide")


@st.cache_resource
def _engine():
    return data.get_engine()


@st.cache_data(ttl=300)
def _daily() -> pd.DataFrame:
    return data.load_daily(_engine())


@st.cache_data(ttl=300)
def _kpis() -> dict:
    return data.load_kpis(_engine())


@st.cache_data(ttl=300)
def _by_zone() -> pd.DataFrame:
    return data.load_by_zone(_engine())


@st.cache_data(ttl=300)
def _by_category() -> pd.DataFrame:
    return data.load_by_category(_engine())


@st.cache_data(ttl=300)
def _incidents() -> pd.DataFrame:
    return data.load_incidents(_engine())


st.title("🚓 BYU Campus Safety Analytics")
st.caption(
    "Incident patterns from BYU's public Police Beat, classified into campus zones "
    "and enriched with the academic calendar."
)

if not data.marts_exist(_engine()):
    st.warning(
        "The analytics tables aren't built yet. Run the pipeline first:\n\n"
        "`docker compose run --rm scraper` → `classifier` → `normalizer` → `dbt`"
    )
    st.stop()

kpis = _kpis()
daily = _daily()

# --- headline metrics --------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total incidents", f"{kpis['total_incidents']:,}")
c2.metric("Located to a zone", f"{kpis['located_pct']:.0f}%",
          help="Share with a known campus zone; the rest have no location in the report.")
c3.metric("Campus zones seen", kpis["distinct_zones"])
c4.metric("Date range", f"{kpis['first_day']} → {kpis['last_day']}")

# --- daily trend -------------------------------------------------------------
st.subheader("Incidents per day")
trend = daily.copy()
trend["day_type"] = "Regular"
trend.loc[trend["is_game_day"], "day_type"] = "Game day"
trend.loc[trend["is_finals"], "day_type"] = "Finals"
chart = (
    alt.Chart(trend)
    .mark_bar()
    .encode(
        x=alt.X("date_day:T", title="Date"),
        y=alt.Y("total_incidents:Q", title="Incidents"),
        color=alt.Color(
            "day_type:N",
            title="Day type",
            scale=alt.Scale(
                domain=["Regular", "Finals", "Game day"],
                range=["#4c78a8", "#e45756", "#f58518"],
            ),
        ),
        tooltip=["date_day:T", "total_incidents:Q", "semester:N", "day_type:N"],
    )
    .properties(height=280)
)
st.altair_chart(chart, use_container_width=True)
if not trend["is_finals"].any() and not trend["is_game_day"].any():
    st.caption(
        "⚠️ The academic-calendar seed still holds placeholder dates, so no finals "
        "or game days fall in range yet. Replace `dbt/seeds/academic_calendar.csv` "
        "with the real BYU calendar to light up those bars."
    )

# --- breakdowns --------------------------------------------------------------
left, right = st.columns(2)
with left:
    st.subheader("By campus zone")
    st.altair_chart(
        alt.Chart(_by_zone()).mark_bar(color="#4c78a8").encode(
            x=alt.X("incidents:Q", title="Incidents"),
            y=alt.Y("zone_label:N", sort="-x", title=None),
            tooltip=["zone_label:N", "incidents:Q"],
        ).properties(height=320),
        use_container_width=True,
    )
with right:
    st.subheader("By incident category")
    st.altair_chart(
        alt.Chart(_by_category()).mark_bar(color="#72b7b2").encode(
            x=alt.X("incidents:Q", title="Incidents"),
            y=alt.Y("incident_category:N", sort="-x", title=None),
            tooltip=["incident_category:N", "incidents:Q"],
        ).properties(height=320),
        use_container_width=True,
    )

# --- incident explorer -------------------------------------------------------
st.subheader("Incident explorer")
incidents = _incidents()
fcol1, fcol2 = st.columns(2)
zones = fcol1.multiselect("Zone", sorted(incidents["zone"].dropna().unique()))
categories = fcol2.multiselect("Category", sorted(incidents["category"].dropna().unique()))

filtered = incidents
if zones:
    filtered = filtered[filtered["zone"].isin(zones)]
if categories:
    filtered = filtered[filtered["category"].isin(categories)]

st.caption(f"{len(filtered):,} of {len(incidents):,} incidents")
st.dataframe(filtered, use_container_width=True, hide_index=True)
