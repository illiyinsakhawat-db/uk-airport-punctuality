"""Interactive dashboard for the UK airport punctuality star schema.

Run locally:   streamlit run streamlit_app.py
Data:          powerbi/data/*.csv (created by run_pipeline.py)
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from pipeline.names import title_case

DATA_DIR = Path(__file__).resolve().parent / "powerbi" / "data"

PRIMARY = "#1f5fa8"
MUTED = "#9aa5b1"
GOOD = "#2f855a"
WARN = "#d9822b"
BAD = "#c53030"
SEVERITY_COLOURS = [GOOD, "#ecc94b", WARN, BAD]

COUNT_COLS = [
    "flights_matched", "flights_cancelled", "flights_planned", "flights_on_time",
    "flights_late_16_60", "flights_late_61_180", "flights_late_over_180", "total_delay_minutes",
    "py_flights_matched", "py_flights_on_time", "py_total_delay_minutes",
]

st.set_page_config(page_title="UK Airport Punctuality", page_icon="✈️", layout="wide")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Loading CAA punctuality data…")
def load_data() -> pd.DataFrame:
    if not (DATA_DIR / "fact_punctuality.csv").exists():
        return pd.DataFrame()
    fact = pd.read_csv(DATA_DIR / "fact_punctuality.csv")
    dates = pd.read_csv(DATA_DIR / "dim_date.csv", parse_dates=["month_start"])
    airports = pd.read_csv(DATA_DIR / "dim_airport.csv")
    dests = pd.read_csv(DATA_DIR / "dim_destination.csv")
    airlines = pd.read_csv(DATA_DIR / "dim_airline.csv")
    types = pd.read_csv(DATA_DIR / "dim_flight_type.csv")

    airports["airport"] = airports["airport_name"].map(title_case)
    airlines["airline"] = airlines["airline_name"].map(title_case)
    dests["destination"] = dests["destination_name"].map(title_case)
    dests["country"] = dests["destination_country"].map(title_case)
    dests["route_type"] = dests["is_domestic"].map({True: "Domestic", False: "International"})

    df = (
        fact.merge(dates[["date_key", "month_start", "month_label", "is_summer_peak"]], on="date_key")
        .merge(airports[["airport_key", "airport"]], on="airport_key")
        .merge(dests[["destination_key", "destination", "country", "route_type"]], on="destination_key")
        .merge(airlines[["airline_key", "airline"]], on="airline_key")
        .merge(types[["flight_type_key", "arrival_departure", "scheduled_charter"]], on="flight_type_key")
    )
    df["month"] = df["month_start"].dt.strftime("%b %Y")
    return df


def summarise(df: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    """Sum the additive counts, then compute rates (never average a rate)."""
    grouped = df.groupby(by, observed=True)[COUNT_COLS].sum().reset_index() if by else df[COUNT_COLS].sum().to_frame().T
    g = grouped
    flights = g["flights_matched"].where(g["flights_matched"] > 0)
    g["on_time_pct"] = 100 * g["flights_on_time"] / flights
    g["avg_delay"] = g["total_delay_minutes"] / flights
    g["over_1hr_pct"] = 100 * (g["flights_late_61_180"] + g["flights_late_over_180"]) / flights
    g["cancel_pct"] = 100 * g["flights_cancelled"] / g["flights_planned"].where(g["flights_planned"] > 0)
    py = g["py_flights_matched"].where(g["py_flights_matched"] > 0)
    g["py_on_time_pct"] = 100 * g["py_flights_on_time"] / py
    g["py_avg_delay"] = g["py_total_delay_minutes"] / py
    return g


def style(fig: go.Figure, height: int = 380) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=40, b=10),
        plot_bgcolor="white", paper_bgcolor="white",
        font=dict(family="Inter, Segoe UI, sans-serif", size=13, color="#1f2933"),
        title_font=dict(size=16), legend_title_text="",
        hoverlabel=dict(bgcolor="white"),
    )
    fig.update_xaxes(showgrid=False, linecolor="#e4e7eb")
    fig.update_yaxes(gridcolor="#eef0f2", zeroline=False)
    return fig


data = load_data()
if data.empty:
    st.error("No data found. Run `python scripts/download_data.py` and `python run_pipeline.py` first.")
    st.stop()

months = (data[["month_start", "month"]].drop_duplicates().sort_values("month_start")["month"].tolist())

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")
    start, end = st.select_slider("Months", options=months, value=(months[0], months[-1]))
    direction = st.radio("Direction", ["All", "Arrivals", "Departures"], horizontal=True)
    service = st.multiselect("Service", ["Scheduled", "Charter"], default=["Scheduled", "Charter"])
    route_type = st.radio("Routes", ["All", "Domestic", "International"], horizontal=True)
    airport_pick = st.multiselect("UK airports", sorted(data["airport"].unique()), placeholder="All airports")
    airline_pick = st.multiselect("Airlines", sorted(data["airline"].unique()), placeholder="All airlines")
    st.caption("On time = early or up to 15 minutes late (CAA definition).")

selected_months = months[months.index(start): months.index(end) + 1]
mask = data["month"].isin(selected_months) & data["scheduled_charter"].isin(service)
if direction != "All":
    mask &= data["arrival_departure"] == direction[:-1]
if route_type != "All":
    mask &= data["route_type"] == route_type
if airport_pick:
    mask &= data["airport"].isin(airport_pick)
if airline_pick:
    mask &= data["airline"].isin(airline_pick)
df = data[mask]

period = start if start == end else f"{start} – {end}"
volume_scale = len(selected_months) / len(months)  # scale minimum-volume filters to the period

st.title("✈️ UK Airport Punctuality")
st.caption(f"Civil Aviation Authority punctuality statistics · {period}")

if df["flights_matched"].sum() == 0:
    st.warning("No flights match these filters.")
    st.stop()

# ---------------------------------------------------------------------------
# Headline KPIs
# ---------------------------------------------------------------------------
k = summarise(df).iloc[0]
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Flights", f"{k.flights_matched:,.0f}",
          f"{100 * (k.flights_matched / k.py_flights_matched - 1):+.1f}% vs last year" if k.py_flights_matched else None)
c2.metric("On time", f"{k.on_time_pct:.1f}%",
          f"{k.on_time_pct - k.py_on_time_pct:+.1f} pts vs last year" if pd.notna(k.py_on_time_pct) else None)
c3.metric("Average delay", f"{k.avg_delay:.1f} min",
          f"{k.avg_delay - k.py_avg_delay:+.1f} min vs last year" if pd.notna(k.py_avg_delay) else None,
          delta_color="inverse")
c4.metric("Over 1 hour late", f"{k.over_1hr_pct:.1f}%")
c5.metric("Cancelled", f"{k.cancel_pct:.2f}%")

overview, airports_tab, airlines_tab, routes_tab, about = st.tabs(
    ["Overview", "Airports", "Airlines", "Routes", "About the data"])

# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
with overview:
    monthly = summarise(df, ["month_start", "month"]).sort_values("month_start")
    left, right = st.columns([3, 2])
    with left:
        fig = go.Figure()
        fig.add_scatter(x=monthly["month_start"], y=monthly["on_time_pct"], name="This year",
                        mode="lines+markers", line=dict(color=PRIMARY, width=3),
                        hovertemplate="%{x|%b %Y}: %{y:.1f}% on time<extra></extra>")
        fig.add_scatter(x=monthly["month_start"], y=monthly["py_on_time_pct"], name="Same month last year",
                        mode="lines", line=dict(color=MUTED, width=2, dash="dash"),
                        hovertemplate="%{x|%b} last year: %{y:.1f}%<extra></extra>")
        fig.update_yaxes(title="Flights on time (%)", ticksuffix="%")
        fig.update_xaxes(tickformat="%b" if len(monthly) <= 12 else "%b %y", dtick="M1")
        fig.update_layout(title="On-time performance by month",
                          legend=dict(orientation="h", y=-0.15, x=0))
        st.plotly_chart(style(fig), width="stretch")
    with right:
        bands = pd.DataFrame({
            "band": ["On time (≤15 min)", "16–60 min late", "1–3 hours late", "Over 3 hours late"],
            "flights": [k.flights_on_time, k.flights_late_16_60, k.flights_late_61_180, k.flights_late_over_180],
        })
        bands["share"] = 100 * bands["flights"] / bands["flights"].sum()
        fig = px.bar(bands, x="share", y="band", orientation="h", text=bands["share"].map("{:.1f}%".format),
                     color="band", color_discrete_sequence=SEVERITY_COLOURS)
        fig.update_traces(textposition="outside", cliponaxis=False,
                          hovertemplate="%{y}: %{x:.1f}% of flights<extra></extra>")
        fig.update_layout(title="How late were flights?", showlegend=False)
        fig.update_yaxes(title="", autorange="reversed")
        fig.update_xaxes(title="Share of flights (%)", range=[0, 100])
        st.plotly_chart(style(fig), width="stretch")

    if len(monthly) > 1:
        worst, best = monthly.loc[monthly["on_time_pct"].idxmin()], monthly.loc[monthly["on_time_pct"].idxmax()]
        st.info(f"**{worst.month}** was the worst month ({worst.on_time_pct:.1f}% on time, "
                f"{worst.avg_delay:.1f} min average delay) and **{best.month}** the best "
                f"({best.on_time_pct:.1f}%), a gap of {best.on_time_pct - worst.on_time_pct:.1f} points.")

# ---------------------------------------------------------------------------
# Airports
# ---------------------------------------------------------------------------
with airports_tab:
    default_min = int(round(10000 * volume_scale, -2)) or 100
    min_flights = st.slider("Minimum flights per airport", 0, 50000, default_min, step=500,
                            help="Hides small airports so the ranking is fair.")
    by_airport = summarise(df, ["airport"])
    by_airport = by_airport[by_airport["flights_matched"] >= min_flights].sort_values("on_time_pct")
    if by_airport.empty:
        st.warning("No airports meet the minimum flights setting.")
    else:
        median = by_airport["on_time_pct"].median()
        colours = [GOOD if v >= median else WARN for v in by_airport["on_time_pct"]]
        fig = go.Figure(go.Bar(
            x=by_airport["on_time_pct"], y=by_airport["airport"], orientation="h", marker_color=colours,
            text=by_airport["on_time_pct"].map("{:.1f}%".format), textposition="outside", cliponaxis=False,
            customdata=by_airport[["flights_matched", "avg_delay"]],
            hovertemplate="%{y}<br>%{x:.1f}% on time<br>%{customdata[0]:,.0f} flights"
                          "<br>%{customdata[1]:.1f} min average delay<extra></extra>"))
        fig.add_vline(x=median, line_dash="dot", line_color=MUTED,
                      annotation_text=f"median {median:.1f}%", annotation_position="top")
        fig.update_xaxes(range=[0, 100], ticksuffix="%", title="Flights on time")
        fig.update_layout(title="On-time performance by airport")
        st.plotly_chart(style(fig, height=max(380, 26 * len(by_airport) + 120)), width="stretch")

        st.subheader("When does each airport struggle?")
        st.caption("On-time % by airport and month. Red cells are each airport's pressure points.")
        heat = summarise(df[df["airport"].isin(by_airport["airport"])], ["airport", "month_start", "month"])
        pivot = heat.pivot(index="airport", columns="month_start", values="on_time_pct")
        pivot = pivot.loc[by_airport["airport"][::-1]]
        pivot.columns = [c.strftime("%b") if len(selected_months) <= 12 else c.strftime("%b %y") for c in pivot.columns]
        fig = px.imshow(pivot, color_continuous_scale="RdYlGn", aspect="auto", text_auto=".0f",
                        labels=dict(color="On time %", x="", y=""))
        fig.update_traces(hovertemplate="%{y}, %{x}: %{z:.1f}% on time<extra></extra>")
        st.plotly_chart(style(fig, height=max(380, 26 * len(pivot) + 120)), width="stretch")

        has_summer = df["is_summer_peak"].any() and (~df["is_summer_peak"]).any()
        if has_summer:
            st.subheader("The summer peak effect")
            peak = summarise(df[df["airport"].isin(by_airport["airport"])], ["airport", "is_summer_peak"])
            peak = peak.pivot(index="airport", columns="is_summer_peak", values="on_time_pct").dropna()
            peak.columns = ["Rest of year", "Summer (Jun–Aug)"]
            peak["effect"] = peak["Summer (Jun–Aug)"] - peak["Rest of year"]
            peak = peak.sort_values("effect", ascending=False)
            fig = go.Figure()
            for airport, row in peak.iterrows():
                fig.add_scatter(x=[row["Summer (Jun–Aug)"], row["Rest of year"]], y=[airport, airport],
                                mode="lines", line=dict(color="#e4e7eb", width=4), showlegend=False,
                                hoverinfo="skip")
            fig.add_scatter(x=peak["Rest of year"], y=peak.index, mode="markers", name="Rest of year",
                            marker=dict(color=PRIMARY, size=11),
                            hovertemplate="%{y}: %{x:.1f}% rest of year<extra></extra>")
            fig.add_scatter(x=peak["Summer (Jun–Aug)"], y=peak.index, mode="markers", name="Summer (Jun–Aug)",
                            marker=dict(color=BAD, size=11),
                            customdata=peak["effect"],
                            hovertemplate="%{y}: %{x:.1f}% in summer (%{customdata:+.1f} pts)<extra></extra>")
            fig.update_xaxes(title="Flights on time", ticksuffix="%")
            fig.update_layout(legend=dict(orientation="h", y=-0.12, x=0))
            st.plotly_chart(style(fig, height=max(380, 26 * len(peak) + 140)), width="stretch")

# ---------------------------------------------------------------------------
# Airlines
# ---------------------------------------------------------------------------
with airlines_tab:
    default_min = int(round(2000 * volume_scale, -2)) or 100
    min_flights = st.slider("Minimum flights per airline", 0, 20000, default_min, step=250,
                            help="Hides airlines with very few UK flights.")
    by_airline = summarise(df, ["airline"])
    by_airline = by_airline[by_airline["flights_matched"] >= min_flights]
    if by_airline.empty:
        st.warning("No airlines meet the minimum flights setting.")
    else:
        fig = px.scatter(
            by_airline, x="flights_matched", y="on_time_pct", log_x=True, hover_name="airline",
            color="avg_delay", color_continuous_scale=["#2f855a", "#ecc94b", "#c53030"],
            labels={"flights_matched": "Flights (log scale)", "on_time_pct": "On time (%)",
                    "avg_delay": "Avg delay (min)"},
            custom_data=["avg_delay"])
        fig.update_traces(marker=dict(size=11, line=dict(width=0.5, color="white")),
                          hovertemplate="<b>%{hovertext}</b><br>%{x:,.0f} flights<br>%{y:.1f}% on time"
                                        "<br>%{customdata[0]:.1f} min average delay<extra></extra>")
        fig.update_layout(title="Are bigger airlines less punctual?")
        fig.update_yaxes(ticksuffix="%")
        st.plotly_chart(style(fig, height=440), width="stretch")

        table = by_airline.sort_values("on_time_pct", ascending=False)[
            ["airline", "flights_matched", "on_time_pct", "avg_delay", "over_1hr_pct", "cancel_pct"]]
        table.insert(0, "rank", range(1, len(table) + 1))
        st.dataframe(
            table, hide_index=True, width="stretch", height=420,
            column_config={
                "rank": st.column_config.NumberColumn("#", width="small"),
                "airline": "Airline",
                "flights_matched": st.column_config.NumberColumn("Flights", format="localized"),
                "on_time_pct": st.column_config.ProgressColumn("On time", format="%.1f%%", min_value=0, max_value=100),
                "avg_delay": st.column_config.NumberColumn("Avg delay (min)", format="%.1f"),
                "over_1hr_pct": st.column_config.NumberColumn("Over 1 hr late", format="%.1f%%"),
                "cancel_pct": st.column_config.NumberColumn("Cancelled", format="%.2f%%"),
            })

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
with routes_tab:
    left, right = st.columns([1, 2])
    with left:
        by_type = summarise(df, ["route_type"])
        fig = px.bar(by_type, x="route_type", y="on_time_pct", text=by_type["on_time_pct"].map("{:.1f}%".format),
                     color="route_type", color_discrete_sequence=[PRIMARY, "#5a8dd6"])
        fig.update_traces(textposition="outside", cliponaxis=False,
                          hovertemplate="%{x}: %{y:.1f}% on time<extra></extra>")
        fig.update_layout(title="Domestic vs international", showlegend=False)
        fig.update_yaxes(range=[0, 100], ticksuffix="%", title="On time")
        fig.update_xaxes(title="")
        st.plotly_chart(style(fig), width="stretch")
    with right:
        default_min = int(round(500 * volume_scale, -1)) or 50
        min_route = st.slider("Minimum flights per route", 0, 5000, default_min, step=50)
        routes = summarise(df, ["airport", "destination", "country"])
        routes = routes[routes["flights_matched"] >= min_route].sort_values("avg_delay", ascending=False).head(25)
        st.markdown("**Routes with the longest average delays**")
        st.dataframe(
            routes[["airport", "destination", "country", "flights_matched", "avg_delay", "on_time_pct"]],
            hide_index=True, width="stretch", height=420,
            column_config={
                "airport": "UK airport", "destination": "To / from", "country": "Country",
                "flights_matched": st.column_config.NumberColumn("Flights", format="localized"),
                "avg_delay": st.column_config.NumberColumn("Avg delay (min)", format="%.1f"),
                "on_time_pct": st.column_config.ProgressColumn("On time", format="%.1f%%", min_value=0, max_value=100),
            })

# ---------------------------------------------------------------------------
# About
# ---------------------------------------------------------------------------
with about:
    st.markdown("""
**Source:** UK Civil Aviation Authority, [punctuality statistics](https://www.caa.co.uk/data-and-analysis/uk-aviation-market/flight-punctuality/uk-flight-punctuality-statistics/2025/)
("Full Analysis Arrival Departure" monthly files).

**How the numbers are built**
- A Python pipeline validates the raw files and reconciles them to a SQL star schema
  (one fact table; date, airport, destination, airline and flight-type dimensions).
- The CAA reports delays as percentages of planned flights. These are converted to flight counts, so every
  figure here is a ratio of sums and stays correct for any combination of filters.
- **On time** = early, or up to 15 minutes late. **Average delay** = the CAA's average per matched flight,
  weighted by flights. **Last year** = the CAA's figures for the same months a year earlier.

**Limitations:** the data is monthly and aggregated (no individual flights or time of day), and it does not
record the cause of a delay. Airlines appear under the legal entity that reported to the CAA.
""")
