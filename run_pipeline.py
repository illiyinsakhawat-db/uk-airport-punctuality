"""End-to-end pipeline: raw CAA CSVs -> validated -> DuckDB star schema -> Power BI extracts + report.

Usage:
    python scripts/download_data.py   # once, to fetch the data
    python run_pipeline.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipeline.extract import clean, read_raw_files
from pipeline.report import build_report
from pipeline.validate import run_checks, to_markdown
from pipeline.warehouse import build, export_for_powerbi, reconcile

ROOT = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the UK airport punctuality warehouse and report.")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "warehouse.duckdb")
    parser.add_argument("--powerbi-dir", type=Path, default=ROOT / "powerbi" / "data")
    parser.add_argument("--reports-dir", type=Path, default=ROOT / "reports")
    args = parser.parse_args(argv)

    print("1/5 Extract: reading raw CAA files")
    raw, files = read_raw_files(args.raw_dir)
    df = clean(raw)
    print(f"    {len(df):,} rows from {len(files)} file(s)")

    print("2/5 Validate: running data quality checks")
    checks = run_checks(df)
    for c in checks:
        print(f"    [{c.status}] {c.name}: {c.detail}")
    if any(c.status == "FAIL" for c in checks):
        print("Stopping: fix the failed checks above before loading.")
        return 1

    print("3/5 Load: building the DuckDB star schema")
    con = build(df, args.db)
    recon = reconcile(con)
    args.reports_dir.mkdir(parents=True, exist_ok=True)
    (args.reports_dir / "data_quality_report.md").write_text(to_markdown(checks, files, recon))
    for label, raw_total, fact_total in recon:
        print(f"    {label}: raw {raw_total:,} | fact {fact_total:,} {'OK' if raw_total == fact_total else 'MISMATCH'}")
    if any(r != f for _, r, f in recon):
        print("Stopping: fact table does not reconcile to the raw files.")
        return 1

    print("4/5 Export: writing star schema CSVs for Power BI")
    for path in export_for_powerbi(con, args.powerbi_dir):
        print(f"    {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")

    print("5/5 Analyse: running SQL analysis, charts and findings")
    build_report(con, args.reports_dir)
    con.close()
    print(f"\nDone. Read {args.reports_dir / 'findings.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
