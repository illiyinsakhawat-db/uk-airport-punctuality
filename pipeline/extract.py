"""Read the raw CAA CSV files into one clean pandas DataFrame."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ID_COLUMNS = [
    "reporting_period",
    "reporting_airport",
    "origin_destination_country",
    "origin_destination",
    "airline_name",
    "arrival_departure",
    "scheduled_charter",
]

COUNT_COLUMNS = [
    "number_flights_matched",
    "actual_flights_unmatched",
    "number_flights_cancelled",
    "previous_year_month_flights_matched",
]

# Percentages of *planned* flights (matched + unmatched + cancelled) in each delay
# band. Together with the unmatched and cancelled percentages they sum to ~100.
BAND_COLUMNS = [
    "flights_more_than_15_minutes_early_percent",
    "flights_15_minutes_early_to_1_minute_early_percent",
    "flights_0_to_15_minutes_late_percent",
    "flights_between_16_and_30_minutes_late_percent",
    "flights_between_31_and_60_minutes_late_percent",
    "flights_between_61_and_120_minutes_late_percent",
    "flights_between_121_and_180_minutes_late_percent",
    "flights_between_181_and_360_minutes_late_percent",
    "flights_more_than_360_minutes_late_percent",
]

OTHER_NUMERIC_COLUMNS = [
    "flights_unmatched_percent",
    "flights_cancelled_percent",
    "average_delay_mins",
    "previous_year_month_early_to_15_mins_late_percent",
    "previous_year_month_average_delay",
]

REQUIRED_COLUMNS = ID_COLUMNS + COUNT_COLUMNS + BAND_COLUMNS + OTHER_NUMERIC_COLUMNS

TEXT_COLUMNS = [c for c in ID_COLUMNS if c != "reporting_period"]


def read_raw_files(raw_dir: Path) -> tuple[pd.DataFrame, list[str]]:
    """Return all raw rows plus the list of files read.

    Column names are normalised (lower case, trimmed) so small header changes
    between monthly files do not break the load.
    """
    files = sorted(Path(raw_dir).glob("*.csv"))
    if not files:
        raise FileNotFoundError(
            f"No CSV files in {raw_dir}. Run `python scripts/download_data.py` first."
        )

    frames = []
    for path in files:
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        df.columns = [c.strip().lower() for c in df.columns]
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"{path.name} is missing expected columns: {missing}")
        df["source_file"] = path.name
        frames.append(df[REQUIRED_COLUMNS + ["source_file"]])

    return pd.concat(frames, ignore_index=True), [p.name for p in files]


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    """Trim text, standardise codes and convert numbers. Blank numbers become 0/NaN."""
    df = raw.copy()

    for col in TEXT_COLUMNS:
        df[col] = df[col].str.strip().str.upper().str.replace(r"\s+", " ", regex=True)

    df["reporting_period"] = pd.to_numeric(df["reporting_period"], errors="coerce").astype("Int64")

    for col in COUNT_COLUMNS:
        df[col] = pd.to_numeric(df[col].str.strip(), errors="coerce").fillna(0).astype(int)

    for col in BAND_COLUMNS + OTHER_NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col].str.strip(), errors="coerce")

    pct_cols = BAND_COLUMNS + ["flights_unmatched_percent", "flights_cancelled_percent"]
    df[pct_cols] = df[pct_cols].fillna(0.0)
    df["average_delay_mins"] = df["average_delay_mins"].fillna(0.0)
    return df
