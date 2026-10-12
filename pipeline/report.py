"""Run the analysis queries, save result tables, draw charts and write the findings."""
from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .warehouse import load_named_queries  # noqa: E402

INK = "#1f2933"
MUTED = "#7b8794"
GRID = "#e4e7eb"
PRIMARY = "#1f5fa8"
ACCENT = "#d9822b"
GOOD = "#2f855a"
BAD = "#c53030"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "axes.titlecolor": INK,
    "axes.titlelocation": "left",
    "xtick.color": MUTED,
    "ytick.color": INK,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 150,
})


def run_queries(con: duckdb.DuckDBPyConnection, tables_dir: Path) -> dict[str, pd.DataFrame]:
    tables_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, sql in load_named_queries().items():
        df = con.execute(sql).df()
        df.to_csv(tables_dir / f"{name}.csv", index=False)
        results[name] = df
    return results


KEEP_UPPER = {"UK", "TUI", "KLM", "SAS", "TAP", "LOT", "BA", "USA", "UAE", "JFK", "AG", "PLC", "LTD"}


SPECIAL_NAMES = {"EASYJET": "easyJet", "JET2.COM": "Jet2.com", "WIZZ AIR": "Wizz Air"}


def _title_case(name: str) -> str:
    """'BRITISH AIRWAYS' -> 'British Airways', keeping known acronyms upper case."""
    name = str(name)
    if name in SPECIAL_NAMES:
        return SPECIAL_NAMES[name]
    return " ".join(w if w in KEEP_UPPER else w.capitalize() for w in name.split())


def _save(fig, path: Path) -> Path:
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def chart_monthly_trend(df: pd.DataFrame, path: Path) -> Path | None:
    if df.empty:
        return None
    fig, ax = plt.subplots(figsize=(9, 4.2))
    x = range(len(df))
    ax.plot(x, df["on_time_pct"], color=PRIMARY, linewidth=2.5, marker="o", label="This year")
    if df["py_on_time_pct"].notna().any():
        ax.plot(x, df["py_on_time_pct"], color=MUTED, linewidth=1.5, linestyle="--", label="Same month last year")
    worst = df["on_time_pct"].idxmin()
    ax.annotate(f"{df.loc[worst, 'on_time_pct']:.1f}%", (worst, df.loc[worst, "on_time_pct"]),
                textcoords="offset points", xytext=(0, -16), ha="center", color=BAD, fontweight="bold")
    ax.set_xticks(list(x), [m.split()[0] for m in df["month_label"]])
    ax.set_ylabel("Flights on time (%)")
    ax.yaxis.grid(True, color=GRID)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2)
    ax.set_title("On-time performance by month, all UK reporting airports")
    return _save(fig, path)


def chart_ranked_bars(df: pd.DataFrame, label_col: str, title: str, path: Path, top_bottom: int | None = None) -> Path | None:
    if df.empty:
        return None
    data = df.sort_values("on_time_pct")
    if top_bottom and len(data) > 2 * top_bottom:
        data = pd.concat([data.head(top_bottom), data.tail(top_bottom)])
    overall = df["on_time_pct"].median()
    colours = [GOOD if v >= overall else ACCENT for v in data["on_time_pct"]]
    fig, ax = plt.subplots(figsize=(8, 0.32 * len(data) + 1.2))
    ax.barh([_title_case(n) for n in data[label_col]], data["on_time_pct"], color=colours, height=0.7)
    for i, v in enumerate(data["on_time_pct"]):
        ax.text(v + 0.4, i, f"{v:.1f}%", va="center", fontsize=8.5, color=INK)
    ax.axvline(overall, color=MUTED, linestyle=":", linewidth=1)
    ax.set_xlim(0, 100)
    ax.set_xlabel(f"Flights on time (%)   ·   dotted line = median {overall:.1f}%   ·   green = above median")
    ax.set_title(title)
    return _save(fig, path)


def chart_summer_effect(df: pd.DataFrame, path: Path) -> Path | None:
    if df.empty:
        return None
    data = df.sort_values("summer_effect_pp", ascending=False)
    fig, ax = plt.subplots(figsize=(8, 0.34 * len(data) + 1.3))
    y = range(len(data))
    ax.hlines(y, data["summer_on_time_pct"], data["rest_of_year_on_time_pct"], color=GRID, linewidth=3)
    ax.scatter(data["rest_of_year_on_time_pct"], y, color=PRIMARY, s=36, label="Rest of year", zorder=3)
    ax.scatter(data["summer_on_time_pct"], y, color=BAD, s=36, label="Summer peak (Jun–Aug)", zorder=3)
    ax.set_yticks(list(y), [_title_case(n) for n in data["airport_name"]])
    ax.set_xlabel("Flights on time (%)")
    ax.legend(frameon=False, loc="lower right", fontsize=8.5)
    ax.set_title("How much the summer peak costs each major airport")
    return _save(fig, path)


def chart_severity(df: pd.DataFrame, path: Path) -> Path | None:
    if df.empty:
        return None
    fig, ax = plt.subplots(figsize=(8, 2.8))
    colours = [GOOD, ACCENT, "#dd6b20", BAD][: len(df)]
    ax.barh(df["band"][::-1], df["share_pct"][::-1], color=colours[::-1], height=0.6)
    for i, v in enumerate(df["share_pct"][::-1]):
        ax.text(v + 0.8, i, f"{v:.1f}%", va="center", fontsize=9)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of flights (%)")
    ax.set_title("How late are UK flights?")
    return _save(fig, path)


def _fmt_int(v) -> str:
    return f"{int(round(v)):,}"


def write_findings(r: dict[str, pd.DataFrame], path: Path, period_label: str) -> None:
    k = r["q01_headline_kpis"].iloc[0]
    lines = [
        f"# Findings: UK airport punctuality, {period_label}",
        "",
        "_Generated automatically by `run_pipeline.py` from the CAA data. Numbers update when the data changes._",
        "",
        "## Headline",
        "",
        f"- **{_fmt_int(k.flights)} flights** analysed across all UK reporting airports.",
        f"- **{k.on_time_pct:.1f}% on time** (early or up to 15 minutes late)"
        + (f", compared with {k.py_on_time_pct:.1f}% in the same months a year earlier." if pd.notna(k.py_on_time_pct) else "."),
        f"- Average delay **{k.avg_delay_mins:.1f} minutes** per flight; **{k.over_1hr_late_pct:.1f}%** of flights were more than an hour late.",
        f"- **{k.cancellation_pct:.2f}%** of planned flights were cancelled.",
    ]

    m = r["q02_monthly_trend"]
    if not m.empty:
        worst, best = m.loc[m["on_time_pct"].idxmin()], m.loc[m["on_time_pct"].idxmax()]
        lines += ["", "## Through the year", "",
                  f"- Worst month: **{worst.month_label}** ({worst.on_time_pct:.1f}% on time, {worst.avg_delay_mins:.1f} min average delay).",
                  f"- Best month: **{best.month_label}** ({best.on_time_pct:.1f}% on time).",
                  f"- Gap between best and worst month: **{best.on_time_pct - worst.on_time_pct:.1f} percentage points**."]

    a = r["q03_airport_league"]
    if not a.empty:
        top, bottom = a.iloc[0], a.iloc[-1]
        lines += ["", "## Airports (10,000+ flights)", "",
                  f"- Most punctual: **{_title_case(top.airport_name)}** ({top.on_time_pct:.1f}% on time).",
                  f"- Least punctual: **{_title_case(bottom.airport_name)}** ({bottom.on_time_pct:.1f}% on time, {bottom.avg_delay_mins:.1f} min average delay)."]

    s = r["q06_summer_peak_effect"]
    if not s.empty:
        hit = s.iloc[0]
        avg_effect = s["summer_effect_pp"].mean()
        lines += [f"- The summer peak cost major airports **{abs(avg_effect):.1f} points** of on-time performance on average; "
                  f"the hardest hit was **{_title_case(hit.airport_name)}** ({hit.summer_effect_pp:+.1f} points)."]

    al = r["q04_airline_league"]
    if not al.empty:
        top, bottom = al.iloc[0], al.iloc[-1]
        lines += ["", "## Airlines (2,000+ flights)", "",
                  f"- Most punctual: **{_title_case(top.airline_name)}** ({top.on_time_pct:.1f}% on time).",
                  f"- Least punctual: **{_title_case(bottom.airline_name)}** ({bottom.on_time_pct:.1f}% on time; "
                  f"{bottom.over_1hr_late_pct:.1f}% of its flights over an hour late)."]
    c = r["q10_airline_consistency"]
    if not c.empty:
        steady, volatile = c.iloc[0], c.iloc[-1]
        lines += [f"- Most consistent month to month: **{_title_case(steady.airline_name)}** (±{steady.volatility_pp:.1f} points); "
                  f"least consistent: **{_title_case(volatile.airline_name)}** (±{volatile.volatility_pp:.1f} points)."]

    w = r["q07_worst_routes"]
    if not w.empty:
        route = w.iloc[0]
        lines += ["", "## Routes (500+ flights)", "",
                  f"- Longest average delay: **{_title_case(route.airport_name)} ↔ {_title_case(route.destination_name)}** "
                  f"({route.avg_delay_mins:.1f} minutes, {route.on_time_pct:.1f}% on time)."]

    d = r["q11_domestic_vs_international"]
    if len(d) == 2:
        dom, intl = d.set_index("route_type").loc["Domestic"], d.set_index("route_type").loc["International"]
        lines += [f"- Domestic routes ran {dom.on_time_pct:.1f}% on time vs {intl.on_time_pct:.1f}% for international routes."]

    lines += ["", "## Caveats", "",
              "- The CAA publishes monthly aggregates per airport, route and airline, not individual flights, "
              "so the analysis cannot see time of day.",
              "- Delays are measured against the published schedule; the data does not record the cause of a delay "
              "(for example air traffic control, weather or airline operations).",
              "- Average delay is the CAA's figure per matched flight, weighted here by flight volume."]
    path.write_text("\n".join(lines) + "\n")


def build_report(con: duckdb.DuckDBPyConnection, reports_dir: Path) -> dict[str, pd.DataFrame]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    charts_dir = reports_dir / "charts"
    charts_dir.mkdir(exist_ok=True)

    results = run_queries(con, reports_dir / "tables")

    months = results["q02_monthly_trend"]
    period_label = (f"{months['month_label'].iloc[0]} – {months['month_label'].iloc[-1]}"
                    if not months.empty else "no data")

    chart_monthly_trend(months, charts_dir / "01_monthly_trend.png")
    chart_ranked_bars(results["q03_airport_league"], "airport_name",
                      "On-time performance by airport (10,000+ flights)", charts_dir / "02_airport_league.png")
    chart_ranked_bars(results["q04_airline_league"], "airline_name",
                      "Most and least punctual airlines (2,000+ flights)", charts_dir / "03_airline_league.png",
                      top_bottom=10)
    chart_summer_effect(results["q06_summer_peak_effect"], charts_dir / "04_summer_peak_effect.png")
    chart_severity(results["q09_delay_severity"], charts_dir / "05_delay_severity.png")

    write_findings(results, reports_dir / "findings.md", period_label)
    return results
