# Data quality report

Source files (12): `202501_Punctuality_Statistics_Full_Analysis_Arrival_Departure.csv`, `202502_Punctuality_Statistics_Full_Analysis_Arrival_Departure.csv`, `202503_Punctuality_Statistics_Full_Analysis_Arrival_Departure.csv`, `202504_Punctuality_Statistics_Full_Analysis_Arrival_Departure.csv`, `202505_Punctuality_Statistics_Full_Analysis_Arrival_Departure.csv`, `202506_Punctuality_Statistics_Full_Analysis_Arrival_Departure.csv`, `202507_Punctuality_Statistics_Full_Analysis_Arrival_Departure.csv`, `202508_Punctuality_Statistics_Full_Analysis_Arrival_Departure.csv`, `202509_Punctuality_Statistics_Full_Analysis_Arrival_Departure.csv`, `202510_Punctuality_Statistics_Full_Analysis_Arrival_Departure.csv`, `202511_Punctuality_Statistics_Full_Analysis_Arrival_Departure.csv`, `202512_Punctuality_Statistics_Full_Analysis_Arrival_Departure.csv`

## Checks on the raw data

| Check | Result | Detail |
| --- | --- | --- |
| Row count | ✅ PASS | 77,839 rows loaded |
| Valid reporting period (YYYYMM) | ✅ PASS | all periods valid |
| No blank airport, airline or destination | ✅ PASS | no blanks |
| Arrival/departure code is A or D | ✅ PASS | all codes valid |
| Scheduled/charter code is S or C | ✅ PASS | all codes valid |
| Flight counts are not negative | ✅ PASS | no negative counts |
| Delay bands + unmatched % + cancelled % sum to 100% (±1pp) | ⚠️ WARN | 3 rows (0.00%) do not reconcile |
| Average delay is not negative | ✅ PASS | no negative averages |
| One row per period/airport/route/airline/type | ✅ PASS | grain is unique |
| Rows with no flights at all | ⚠️ WARN | 9,440 rows (kept, contribute zero) |

## Reconciliation: raw files vs warehouse fact table

| Measure | Raw files | Fact table | Match |
| --- | ---: | ---: | --- |
| Flights matched | 1,909,792 | 1,909,792 | ✅ |
| Flights unmatched | 262 | 262 | ✅ |
| Flights cancelled | 20,073 | 20,073 | ✅ |
