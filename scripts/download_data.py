"""Download the CAA's 2025 monthly punctuality statistics.

Source: UK Civil Aviation Authority, "Punctuality statistics 2025"
https://www.caa.co.uk/data-and-analysis/uk-aviation-market/flight-punctuality/uk-flight-punctuality-statistics/2025/

The "Full Analysis Arrival Departure" files are used because they split every
airport / route / airline row into arrivals and departures.

Usage:
    python scripts/download_data.py            # all 12 months of 2025
    python scripts/download_data.py --force    # re-download existing files
"""
from __future__ import annotations

import argparse
import sys
import time
import urllib.request
from pathlib import Path

BASE_URL = "https://www.caa.co.uk/Documents/Download/24022/3d82eddc-84f7-4692-bc12-a9ab96562d04/"

# reporting period (YYYYMM) -> CAA document id for the
# "Punctuality Statistics Full Analysis Arrival Departure" CSV
FILES_2025 = {
    "202501": 1648,
    "202502": 1659,
    "202503": 1664,
    "202504": 1668,
    "202505": 1672,
    "202506": 1679,
    "202507": 1684,
    "202508": 1689,
    "202509": 1694,
    "202510": 1699,
    "202511": 1703,
    "202512": 1710,
}

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


def download(period: str, doc_id: int, force: bool) -> Path:
    target = RAW_DIR / f"{period}_Punctuality_Statistics_Full_Analysis_Arrival_Departure.csv"
    if target.exists() and not force:
        print(f"  {period}: already downloaded")
        return target

    request = urllib.request.Request(
        BASE_URL + str(doc_id),
        headers={"User-Agent": "Mozilla/5.0 (uk-airport-punctuality portfolio project)"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        content = response.read()

    first_line = content.split(b"\n", 1)[0].decode("utf-8-sig", errors="replace")
    if "reporting_period" not in first_line:
        raise RuntimeError(f"{period}: response does not look like a CAA punctuality CSV")

    target.write_bytes(content)
    print(f"  {period}: {len(content) / 1024:,.0f} KB")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="re-download files that already exist")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading CAA punctuality files to {RAW_DIR}")
    failures = []
    for period, doc_id in FILES_2025.items():
        try:
            download(period, doc_id, args.force)
            time.sleep(0.5)  # be polite to the CAA website
        except Exception as exc:  # noqa: BLE001 - report and carry on
            print(f"  {period}: FAILED ({exc})")
            failures.append(period)

    if failures:
        print(f"\n{len(failures)} file(s) failed: {', '.join(failures)}. "
              "Download them manually from the CAA page in this script's docstring.")
        return 1
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
