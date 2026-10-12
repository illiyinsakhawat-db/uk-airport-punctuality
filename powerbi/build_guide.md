# Power BI build guide

This guide turns the star schema CSVs in `powerbi/data/` into a four-page Power BI report. Run `python run_pipeline.py` first so the CSVs exist.

> **On a Mac:** Power BI Desktop only runs on Windows. Use a Windows PC, a Windows virtual machine (for example Parallels), or a university or work Windows machine. Copy the `powerbi/data/` folder across.

## 1. Load the data

1. **Home → Get data → Text/CSV**, and load all six files from `powerbi/data/`.
2. In **Power Query** (Transform data), check the data types:

   | Table | Column | Type |
   | --- | --- | --- |
   | dim_date | month_start | Date |
   | dim_date | date_key, year, month_number | Whole number |
   | dim_date, dim_destination | is_summer_peak, is_domestic | True/False |
   | fact_punctuality | all `*_key` and flight count columns | Whole number |
   | fact_punctuality | flights_on_time, flights_late_*, *_delay_minutes, py_* | Decimal number |

3. **Close & Apply.**

## 2. Model the star schema

In **Model view**, create these relationships: all are one-to-many, with single cross-filter direction from the dimension to the fact.

| From (one) | To (many) |
| --- | --- |
| dim_date[date_key] | fact_punctuality[date_key] |
| dim_airport[airport_key] | fact_punctuality[airport_key] |
| dim_destination[destination_key] | fact_punctuality[destination_key] |
| dim_airline[airline_key] | fact_punctuality[airline_key] |
| dim_flight_type[flight_type_key] | fact_punctuality[flight_type_key] |

Then:
- **Hide** every `*_key` column and all raw fact columns (report users should only see the measures).
- Sort `dim_date[month_label]` by `dim_date[date_key]`, and `dim_date[month_name]` by `month_number`.
- Create an empty `_Measures` table and add every measure from [`measures.dax`](measures.dax).

## 3. Report pages

Use one consistent theme: one main colour for "this year", grey for "last year", and green/orange/red only for good/warning/bad.

### Page 1: Overview
- **Title:** a text box bound to the `Selected Period` measure, such as "UK airport punctuality · Jan 2025 – Dec 2025".
- **KPI cards:** `Flights`, `On Time %`, `Avg Delay (mins)`, `Cancellation %` and `YoY On Time Change (pp)`.
- **Line chart:** `month_label` on the x-axis; `On Time %` and `PY On Time %` as values.
- **100% stacked bar:** the delay bands (`On Time %`, `Late 16-60 %`, `Late 1-3 Hours %`, `Late Over 3 Hours %`).
- **Slicers:** month, `arrival_departure`, `scheduled_charter` and `is_domestic`.

### Page 2: Airports
- **Bar chart:** `airport_name` by `On Time %`, filtered to `Flights` ≥ 10,000 and sorted descending.
- **Matrix heatmap:** `airport_name` (rows) × `month_label` (columns) with `On Time %` values, plus conditional formatting (a red–green background). This shows **when** each airport struggles, which is the "operational bottleneck" view.
- **Table:** airport, `Flights`, `On Time %`, `Summer On Time %`, `Rest Of Year On Time %` and `Summer Effect (pp)`.

### Page 3: Airlines
- **Table:** `Airline On Time Rank`, airline, `Flights`, `On Time %`, `Avg Delay (mins)`, `Over 1 Hour Late %` and `Cancellation %`.
- **Scatter chart:** `Flights` (x) vs `On Time %` (y), with airline as details. It shows whether larger carriers are less punctual.
- **Line chart** with an airline slicer: monthly `On Time %` for the selected carriers.

### Page 4: Routes
- **Table:** airport, destination, country, `Flights` and `Avg Delay (mins)`, filtered to `Flights` ≥ 500 and sorted by delay (worst first).
- **Clustered bar:** domestic vs international `On Time %`.
- **Drill-through:** from any airport on Page 2 to this page, filtered to that airport's routes.

## 4. Check the numbers

Compare the Overview cards with `reports/tables/q01_headline_kpis.csv`. The flights, on-time %, average delay and cancellation % should match the SQL results exactly. If they don't, a relationship or data type is wrong.

## 5. Publish

- Save as `powerbi/uk_airport_punctuality.pbix`.
- Export each page as an image to `powerbi/screenshots/`, and link them in the README.
- Optional: **Publish to web** (if your account allows it) and add the link to the README and your CV.
