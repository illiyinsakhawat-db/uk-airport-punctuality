"""Load cleaned data into DuckDB, build the star schema and export it for Power BI."""
from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pandas as pd

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"

POWERBI_TABLES = [
    "dim_date",
    "dim_airport",
    "dim_destination",
    "dim_airline",
    "dim_flight_type",
    "fact_punctuality",
]


def build(df: pd.DataFrame, db_path: Path) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    con.register("stg_df", df)
    con.execute("CREATE OR REPLACE TABLE stg_punctuality AS SELECT * FROM stg_df")
    con.unregister("stg_df")
    for name in ("01_star_schema.sql", "02_views.sql"):
        con.execute((SQL_DIR / name).read_text())
    return con


def reconcile(con: duckdb.DuckDBPyConnection) -> list[tuple[str, int, int]]:
    """Totals in the staging table must equal totals in the fact table."""
    pairs = [
        ("Flights matched", "number_flights_matched", "flights_matched"),
        ("Flights unmatched", "actual_flights_unmatched", "flights_unmatched"),
        ("Flights cancelled", "number_flights_cancelled", "flights_cancelled"),
    ]
    rows = []
    for label, stg_col, fact_col in pairs:
        raw_total = con.execute(f"SELECT COALESCE(SUM({stg_col}), 0) FROM stg_punctuality").fetchone()[0]
        fact_total = con.execute(f"SELECT COALESCE(SUM({fact_col}), 0) FROM fact_punctuality").fetchone()[0]
        rows.append((label, int(raw_total), int(fact_total)))
    return rows


def export_for_powerbi(con: duckdb.DuckDBPyConnection, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for table in POWERBI_TABLES:
        path = out_dir / f"{table}.csv"
        con.execute(f"COPY (SELECT * FROM {table}) TO '{path.as_posix()}' (HEADER, DELIMITER ',')")
        paths.append(path)
    return paths


def load_named_queries(path: Path | None = None) -> dict[str, str]:
    """Split 03_analysis_queries.sql into {name: sql} using '-- name:' markers."""
    text = (path or SQL_DIR / "03_analysis_queries.sql").read_text()
    parts = re.split(r"^-- name:\s*(\w+)\s*$", text, flags=re.MULTILINE)
    return {parts[i]: parts[i + 1].strip().rstrip(";") for i in range(1, len(parts), 2)}
