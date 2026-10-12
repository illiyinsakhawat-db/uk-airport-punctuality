"""Tests run on a small synthetic file in the CAA format (no download needed)."""
from __future__ import annotations

import csv
import random
from pathlib import Path

import duckdb
import pytest

from pipeline.extract import BAND_COLUMNS, REQUIRED_COLUMNS, clean, read_raw_files
from pipeline.validate import run_checks
from pipeline.warehouse import build, load_named_queries, reconcile
from run_pipeline import main

HEADER = ["run_date"] + REQUIRED_COLUMNS[:7] + [
    "number_flights_matched", "actual_flights_unmatched", "number_flights_cancelled",
    *BAND_COLUMNS,
    "flights_unmatched_percent", "flights_cancelled_percent", "average_delay_mins",
    "previous_year_month_flights_matched", "previous_year_month_early_to_15_mins_late_percent",
    "previous_year_month_average_delay",
]


def _row(period, airport, country, dest, airline, ad, sc, matched, bands, avg_delay, cancelled=0):
    """`bands` are shares of matched flights; like the CAA, the file stores them as shares of planned flights."""
    planned = matched + cancelled
    bands = [round(b * matched / planned, 6) for b in bands]
    return {
        "run_date": "01/01/2026 09:00", "reporting_period": period, "reporting_airport": airport,
        "origin_destination_country": country, "origin_destination": dest, "airline_name": airline,
        "arrival_departure": ad, "scheduled_charter": sc,
        "number_flights_matched": matched, "actual_flights_unmatched": 0, "number_flights_cancelled": cancelled,
        **dict(zip(BAND_COLUMNS, bands)),
        "flights_unmatched_percent": 0, "flights_cancelled_percent": round(100 * cancelled / planned, 6), "average_delay_mins": avg_delay,
        "previous_year_month_flights_matched": matched, "previous_year_month_early_to_15_mins_late_percent": 70,
        "previous_year_month_average_delay": 15,
    }


def make_synthetic(base: Path) -> Path:
    """Write 12 months of fake CAA-format files to base/raw and return that folder."""
    rng = random.Random(42)
    raw = base / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    airports = ["HEATHROW", "GATWICK", "MANCHESTER"]
    airlines = ["BRITISH AIRWAYS", "EASYJET", "RYANAIR"]
    dests = [("SPAIN", "MALAGA"), ("UNITED KINGDOM", "EDINBURGH"), ("FRANCE", "PARIS (CHARLES DE GAULLE)")]
    for month in range(1, 13):
        period = 202500 + month
        rows = []
        for ap in airports:
            for al in airlines:
                for country, dest in dests:
                    for ad in "AD":
                        on_time = rng.uniform(55, 90)
                        rest = 100 - on_time
                        bands = [on_time * 0.2, on_time * 0.5, on_time * 0.3,
                                 rest * 0.4, rest * 0.3, rest * 0.15, rest * 0.08, rest * 0.05, rest * 0.02]
                        rows.append(_row(period, f" {ap.lower()} ", country, dest, al, ad, "S",
                                         rng.randint(300, 900), [round(b, 6) for b in bands],
                                         round(rng.uniform(5, 30), 2), cancelled=rng.randint(0, 9)))
        with open(raw / f"{period}_test.csv", "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=HEADER)
            writer.writeheader()
            writer.writerows(rows)
    return raw


@pytest.fixture()
def raw_dir(tmp_path: Path) -> Path:
    return make_synthetic(tmp_path)


def test_clean_standardises_text(raw_dir):
    df = clean(read_raw_files(raw_dir)[0])
    assert set(df["reporting_airport"]) == {"HEATHROW", "GATWICK", "MANCHESTER"}


def test_checks_pass_on_good_data(raw_dir):
    df = clean(read_raw_files(raw_dir)[0])
    assert not [c for c in run_checks(df) if c.status == "FAIL"]


def test_checks_fail_on_bad_code(raw_dir):
    df = clean(read_raw_files(raw_dir)[0])
    df.loc[0, "arrival_departure"] = "X"
    failed = [c.name for c in run_checks(df) if c.status == "FAIL"]
    assert "Arrival/departure code is A or D" in failed


def test_fact_reconciles_and_on_time_is_weighted(raw_dir, tmp_path):
    df = clean(read_raw_files(raw_dir)[0])
    con = build(df, tmp_path / "w.duckdb")
    assert all(raw == fact for _, raw, fact in reconcile(con))

    planned = df["number_flights_matched"] + df["actual_flights_unmatched"] + df["number_flights_cancelled"]
    expected = (planned * df[BAND_COLUMNS[:3]].sum(axis=1) / 100).sum() \
        / df["number_flights_matched"].sum() * 100
    actual = con.execute(
        "SELECT 100 * SUM(flights_on_time) / SUM(flights_matched) FROM fact_punctuality").fetchone()[0]
    assert actual == pytest.approx(expected)

    domestic = con.execute(
        "SELECT is_domestic FROM dim_destination WHERE destination_name = 'EDINBURGH'").fetchone()[0]
    assert domestic is True


def test_band_counts_add_up_to_matched_flights(raw_dir, tmp_path):
    con = build(clean(read_raw_files(raw_dir)[0]), tmp_path / "w.duckdb")
    matched, banded = con.execute("""
        SELECT SUM(flights_matched),
               SUM(flights_on_time + flights_late_16_60 + flights_late_61_180 + flights_late_over_180)
        FROM fact_punctuality""").fetchone()
    assert banded == pytest.approx(matched, rel=1e-4)


def test_all_analysis_queries_run(raw_dir, tmp_path):
    df = clean(read_raw_files(raw_dir)[0])
    con = build(df, tmp_path / "w.duckdb")
    queries = load_named_queries()
    assert len(queries) == 13
    for name, sql in queries.items():
        con.execute(sql).df()  # raises if the SQL is invalid


def test_end_to_end(raw_dir, tmp_path):
    out = tmp_path / "out"
    code = main(["--raw-dir", str(raw_dir), "--db", str(out / "w.duckdb"),
                 "--powerbi-dir", str(out / "powerbi"), "--reports-dir", str(out / "reports")])
    assert code == 0
    assert (out / "reports" / "findings.md").exists()
    assert (out / "reports" / "charts" / "01_monthly_trend.png").exists()
    assert (out / "powerbi" / "fact_punctuality.csv").exists()
    con = duckdb.connect()
    n = con.execute(f"SELECT COUNT(*) FROM '{(out / 'powerbi' / 'fact_punctuality.csv').as_posix()}'").fetchone()[0]
    assert n == 12 * 3 * 3 * 3 * 2


def test_streamlit_app_runs_on_exported_data():
    """Smoke test of the dashboard; needs powerbi/data from a real pipeline run."""
    data_dir = Path(__file__).resolve().parents[1] / "powerbi" / "data"
    if not (data_dir / "fact_punctuality.csv").exists():
        pytest.skip("run the pipeline first to create powerbi/data")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(data_dir.parents[1] / "streamlit_app.py"), default_timeout=60).run()
    assert not app.exception
    assert app.metric[0].label == "Flights"
