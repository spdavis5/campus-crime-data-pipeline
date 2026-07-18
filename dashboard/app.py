"""BYU Campus Safety dashboard — the serving layer over the dbt marts.

Reads the analytics star schema from PostgreSQL and presents incident trends over
the academic calendar, breakdowns by campus zone and category, a zone-by-category
heatmap, weekday patterns, and a searchable incident explorer. A single set of
sidebar filters drives every view. Run via the dashboard container (see
docker-compose.yml).
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

# Streamlit puts the script's own directory on sys.path, so data.py imports directly.
import data

# --- palette (validated categorical + chrome; see project docs) --------------
INK = "#0b0b0b"
SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
PRIMARY = "#2a78d6"
AQUA = "#1baf7a"
CATEGORICAL = ["#2a78d6", "#1baf7a", "#eda100", "#008300",
               "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"]
DAY_TYPE_DOMAIN = ["Regular", "Finals", "Break", "Game day"]
DAY_TYPE_RANGE = ["#2a78d6", "#e34948", "#eb6834", "#4a3aa7"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

st.set_page_config(page_title="BYU Campus Safety Analytics", layout="wide")

st.markdown(
    """
    <style>
      #MainMenu, header, footer {visibility: hidden;}
      .block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1320px;}
      h1 {font-weight: 650; letter-spacing: -0.01em; margin-bottom: 0.1rem;}
      [data-testid="stMetric"] {
          background: #ffffff; border: 1px solid #e1e0d9;
          border-radius: 10px; padding: 14px 18px;
      }
      [data-testid="stMetricLabel"] p {
          color: #52514e; font-size: 0.74rem; font-weight: 600;
          text-transform: uppercase; letter-spacing: 0.05em;
      }
      [data-testid="stMetricValue"] {color: #0b0b0b; font-weight: 650;}
      section[data-testid="stSidebar"] {border-right: 1px solid #e1e0d9;}
      button[data-baseweb="tab"] {font-size: 0.95rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def _engine():
    return data.get_engine()


@st.cache_data(ttl=300)
def _incidents() -> pd.DataFrame:
    return data.load_incidents(_engine())


@st.cache_data(ttl=300)
def _spine() -> pd.DataFrame:
    return data.load_date_spine(_engine())


def _cfg(chart: alt.Chart) -> alt.Chart:
    """Apply consistent, recessive chrome to a top-level chart."""
    return (
        chart.configure_view(strokeWidth=0)
        .configure_axis(
            gridColor=GRID, domainColor=AXIS, tickColor=AXIS,
            labelColor=SECONDARY, titleColor=SECONDARY,
            labelFontSize=11, titleFontSize=12,
        )
        .configure_legend(labelColor=SECONDARY, titleColor=SECONDARY)
    )


# --- header + guard ----------------------------------------------------------
st.title("BYU Campus Safety Analytics")
st.caption(
    "Incident patterns from BYU's public Police Beat, classified into campus zones "
    "and enriched with the academic calendar."
)

if not data.marts_exist(_engine()):
    st.warning(
        "The analytics tables aren't built yet. Run the pipeline first: "
        "`scraper` → `classifier` → `normalizer` → `dbt build`."
    )
    st.stop()

incidents = _incidents()
spine = _spine()

# --- sidebar filters (drive every view) --------------------------------------
with st.sidebar:
    st.markdown("### Filters")
    dmin = spine["date_day"].min().date()
    dmax = spine["date_day"].max().date()
    picked = st.date_input("Date range", (dmin, dmax), min_value=dmin, max_value=dmax)
    start, end = (picked if isinstance(picked, tuple) and len(picked) == 2 else (dmin, dmax))
    start, end = pd.Timestamp(start), pd.Timestamp(end)

    sem_options = sorted(s for s in incidents["semester"].dropna().unique())
    sem_sel = st.multiselect("Semester", sem_options)
    zone_sel = st.multiselect("Campus zone", sorted(incidents["zone"].dropna().unique()))
    cat_sel = st.multiselect("Category", sorted(incidents["category"].dropna().unique()))
    search = st.text_input("Search narrative", placeholder="e.g. bike, alarm, medical")
    st.caption("Filters apply to every chart and table below.")

# apply filters; keep undated incidents unless a narrower date range excludes them
f = incidents[incidents["date"].isna() | incidents["date"].between(start, end)]
if sem_sel:
    f = f[f["semester"].isin(sem_sel)]
if zone_sel:
    f = f[f["zone"].isin(zone_sel)]
if cat_sel:
    f = f[f["category"].isin(cat_sel)]
if search:
    f = f[f["narrative"].str.contains(search, case=False, na=False)]

sp = spine[spine["date_day"].between(start, end)]
if sem_sel:
    sp = sp[sp["semester"].isin(sem_sel)]

if f.empty:
    st.info("No incidents match the current filters. Try widening them in the sidebar.")
    st.stop()

# --- headline metrics --------------------------------------------------------
total = len(f)
dated = f.dropna(subset=["date"])
days_in_range = max(len(sp), 1)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Incidents", f"{total:,}")
c2.metric("Incidents / day", f"{total / days_in_range:.1f}",
          help="Average over the calendar days in the selected range.")
c3.metric("Campus zones", int(f.loc[~f["zone_unknown"], "zone"].nunique()))
c4.metric(
    "Date range",
    f"{dated['date'].min():%b %Y} – {dated['date'].max():%b %Y}" if not dated.empty else "—",
)

st.write("")
overview, patterns, explorer = st.tabs(["Overview", "Patterns", "Explorer"])

# --- Overview: trend + calendar effect ---------------------------------------
with overview:
    counts = (
        dated.assign(day=dated["date"].dt.normalize())
        .groupby("day").size().rename("incidents")
    )
    daily = sp[["date_day", "is_finals", "is_break", "is_game_day"]].copy()
    daily = daily.merge(counts, left_on="date_day", right_index=True, how="left")
    daily["incidents"] = daily["incidents"].fillna(0).astype(int)
    daily["day_type"] = "Regular"
    daily.loc[daily["is_game_day"], "day_type"] = "Game day"
    daily.loc[daily["is_break"], "day_type"] = "Break"
    daily.loc[daily["is_finals"], "day_type"] = "Finals"
    daily["rolling"] = daily["incidents"].rolling(7, min_periods=1).mean().round(2)

    st.subheader("Incidents per day")
    bars = (
        alt.Chart(daily).mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
            x=alt.X("date_day:T", title=None),
            y=alt.Y("incidents:Q", title="Incidents"),
            color=alt.Color("day_type:N", title="Day type",
                            scale=alt.Scale(domain=DAY_TYPE_DOMAIN, range=DAY_TYPE_RANGE)),
            tooltip=[alt.Tooltip("date_day:T", title="Date"),
                     alt.Tooltip("incidents:Q", title="Incidents"),
                     alt.Tooltip("day_type:N", title="Day type")],
        )
    )
    line = (
        alt.Chart(daily).mark_line(color=INK, strokeWidth=2, opacity=0.75).encode(
            x="date_day:T", y="rolling:Q",
            tooltip=[alt.Tooltip("date_day:T", title="Date"),
                     alt.Tooltip("rolling:Q", title="7-day avg")],
        )
    )
    st.altair_chart(_cfg((bars + line).properties(height=300)), use_container_width=True)
    st.caption("Bars are daily counts colored by academic-calendar day type; the line is a 7-day rolling average.")

    st.subheader("Average incidents per day, by calendar context")
    effect = (
        daily.groupby("day_type")
        .agg(avg_per_day=("incidents", "mean"), days=("incidents", "size"),
             total=("incidents", "sum"))
        .reindex([d for d in DAY_TYPE_DOMAIN if d in daily["day_type"].unique()])
        .reset_index()
    )
    effect["avg_per_day"] = effect["avg_per_day"].round(2)
    eff_chart = (
        alt.Chart(effect).mark_bar(cornerRadiusEnd=3, size=42).encode(
            x=alt.X("day_type:N", title=None, sort=DAY_TYPE_DOMAIN, axis=alt.Axis(grid=False)),
            y=alt.Y("avg_per_day:Q", title="Avg incidents / day"),
            color=alt.Color("day_type:N", scale=alt.Scale(domain=DAY_TYPE_DOMAIN, range=DAY_TYPE_RANGE), legend=None),
            tooltip=[alt.Tooltip("day_type:N", title="Day type"),
                     alt.Tooltip("avg_per_day:Q", title="Avg / day"),
                     alt.Tooltip("days:Q", title="# days"),
                     alt.Tooltip("total:Q", title="Total incidents")],
        )
    )
    labels = eff_chart.mark_text(dy=-8, color=SECONDARY, fontSize=12).encode(text="avg_per_day:Q")
    st.altair_chart(_cfg((eff_chart + labels).properties(height=280)), use_container_width=True)

# --- Patterns: zone, category, heatmap, weekday ------------------------------
with patterns:
    left, right = st.columns(2)
    with left:
        st.subheader("By campus zone")
        by_zone = (
            f[~f["zone_unknown"]].groupby("zone").size()
            .rename("incidents").reset_index()
        )
        st.altair_chart(
            _cfg(alt.Chart(by_zone).mark_bar(color=PRIMARY, cornerRadiusEnd=3).encode(
                x=alt.X("incidents:Q", title="Incidents"),
                y=alt.Y("zone:N", sort="-x", title=None, axis=alt.Axis(grid=False)),
                tooltip=["zone:N", "incidents:Q"],
            ).properties(height=340)),
            use_container_width=True,
        )
    with right:
        st.subheader("By category")
        by_cat = f.groupby("category").size().rename("incidents").reset_index()
        st.altair_chart(
            _cfg(alt.Chart(by_cat).mark_bar(color=AQUA, cornerRadiusEnd=3).encode(
                x=alt.X("incidents:Q", title="Incidents"),
                y=alt.Y("category:N", sort="-x", title=None, axis=alt.Axis(grid=False)),
                tooltip=["category:N", "incidents:Q"],
            ).properties(height=340)),
            use_container_width=True,
        )

    st.subheader("Where each category happens")
    grid = (
        f[~f["zone_unknown"]].groupby(["zone", "category"]).size()
        .rename("incidents").reset_index()
    )
    heat = (
        alt.Chart(grid).mark_rect().encode(
            x=alt.X("category:N", title=None, axis=alt.Axis(labelAngle=-40)),
            y=alt.Y("zone:N", title=None),
            color=alt.Color("incidents:Q", title="Incidents",
                            scale=alt.Scale(scheme="blues")),
            tooltip=["zone:N", "category:N", "incidents:Q"],
        ).properties(height=360)
    )
    st.altair_chart(_cfg(heat), use_container_width=True)
    st.caption("Darker cells mark zone/category combinations with more incidents.")

    st.subheader("By day of week")
    if not dated.empty:
        wk = dated.assign(weekday=dated["date"].dt.day_name()).groupby("weekday").size()
        wk = wk.reindex(WEEKDAYS, fill_value=0).rename("incidents").reset_index()
        st.altair_chart(
            _cfg(alt.Chart(wk).mark_bar(color=PRIMARY, cornerRadiusEnd=3, size=42).encode(
                x=alt.X("weekday:N", title=None, sort=WEEKDAYS, axis=alt.Axis(grid=False, labelAngle=0)),
                y=alt.Y("incidents:Q", title="Incidents"),
                tooltip=["weekday:N", "incidents:Q"],
            ).properties(height=260)),
            use_container_width=True,
        )

# --- Explorer: searchable, downloadable table --------------------------------
with explorer:
    st.subheader("Incident explorer")
    table = (
        f[["date", "zone", "category", "type", "narrative"]]
        .rename(columns=str.title)
        .sort_values("Date", ascending=False, na_position="last")
    )
    st.caption(f"{len(table):,} of {len(incidents):,} incidents match the current filters.")
    st.download_button(
        "Download filtered data (CSV)",
        table.to_csv(index=False).encode("utf-8"),
        file_name="campus_incidents.csv",
        mime="text/csv",
    )
    st.dataframe(
        table, use_container_width=True, hide_index=True,
        column_config={
            "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
            "Narrative": st.column_config.TextColumn("Narrative", width="large"),
        },
    )
