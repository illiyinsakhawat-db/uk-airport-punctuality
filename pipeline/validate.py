"""Data quality checks run on the cleaned data before it is loaded."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .extract import BAND_COLUMNS, ID_COLUMNS

BAND_TOLERANCE = 1.0  # percentage points; CAA figures are rounded


@dataclass
class CheckResult:
    name: str
    status: str  # PASS, WARN or FAIL
    detail: str


def _result(name: str, bad_rows: int, total: int, fail: bool, ok_detail: str, bad_detail: str) -> CheckResult:
    if bad_rows == 0:
        return CheckResult(name, "PASS", ok_detail)
    return CheckResult(name, "FAIL" if fail else "WARN", bad_detail.format(n=bad_rows, pct=100 * bad_rows / total))


def run_checks(df: pd.DataFrame) -> list[CheckResult]:
    total = len(df)
    results = [CheckResult("Row count", "PASS" if total else "FAIL", f"{total:,} rows loaded")]

    period = df["reporting_period"]
    bad = int((period.isna() | ~(period % 100).between(1, 12)).sum())
    results.append(_result("Valid reporting period (YYYYMM)", bad, total, True,
                           "all periods valid", "{n:,} rows with an invalid period"))

    bad = int((df[["reporting_airport", "airline_name", "origin_destination"]] == "").any(axis=1).sum())
    results.append(_result("No blank airport, airline or destination", bad, total, True,
                           "no blanks", "{n:,} rows with a blank key field"))

    bad = int((~df["arrival_departure"].isin(["A", "D"])).sum())
    results.append(_result("Arrival/departure code is A or D", bad, total, True,
                           "all codes valid", "{n:,} rows with an unknown code"))

    bad = int((~df["scheduled_charter"].isin(["S", "C"])).sum())
    results.append(_result("Scheduled/charter code is S or C", bad, total, True,
                           "all codes valid", "{n:,} rows with an unknown code"))

    counts = ["number_flights_matched", "actual_flights_unmatched", "number_flights_cancelled"]
    bad = int((df[counts] < 0).any(axis=1).sum())
    results.append(_result("Flight counts are not negative", bad, total, True,
                           "no negative counts", "{n:,} rows with negative counts"))

    flown = df["number_flights_matched"] > 0
    band_sum = df[BAND_COLUMNS].sum(axis=1)
    bad = int((flown & ((band_sum - 100).abs() > BAND_TOLERANCE)).sum())
    results.append(_result(f"Delay bands sum to 100% (±{BAND_TOLERANCE:g}pp) where flights matched", bad, total, False,
                           "all rows reconcile", "{n:,} rows ({pct:.2f}%) do not reconcile"))

    bad = int((df["average_delay_mins"] < 0).sum())
    results.append(_result("Average delay is not negative", bad, total, False,
                           "no negative averages", "{n:,} rows with a negative average delay"))

    dupes = int(df.duplicated(subset=ID_COLUMNS, keep=False).sum())
    results.append(_result("One row per period/airport/route/airline/type", dupes, total, False,
                           "grain is unique",
                           "{n:,} rows share a key; they are summed in the fact table"))

    no_activity = int((df[counts].sum(axis=1) == 0).sum())
    results.append(CheckResult("Rows with no flights at all", "PASS" if no_activity == 0 else "WARN",
                               f"{no_activity:,} rows (kept, contribute zero)"))
    return results


def to_markdown(results: list[CheckResult], files: list[str], reconciliation: list[tuple[str, int, int]]) -> str:
    icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}
    lines = [
        "# Data quality report",
        "",
        f"Source files ({len(files)}): " + ", ".join(f"`{f}`" for f in files),
        "",
        "## Checks on the raw data",
        "",
        "| Check | Result | Detail |",
        "| --- | --- | --- |",
    ]
    lines += [f"| {r.name} | {icon[r.status]} {r.status} | {r.detail} |" for r in results]
    lines += [
        "",
        "## Reconciliation: raw files vs warehouse fact table",
        "",
        "| Measure | Raw files | Fact table | Match |",
        "| --- | ---: | ---: | --- |",
    ]
    for name, raw_total, fact_total in reconciliation:
        lines.append(f"| {name} | {raw_total:,} | {fact_total:,} | {'✅' if raw_total == fact_total else '❌'} |")
    return "\n".join(lines) + "\n"
