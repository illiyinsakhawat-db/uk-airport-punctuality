-- =====================================================================
-- Reporting layer: one wide view over the star schema, plus summary views.
-- Rates are always calculated from summed counts, never by averaging rates.
-- =====================================================================

CREATE OR REPLACE VIEW vw_punctuality AS
SELECT
    dt.date_key, dt.month_start, dt.month_label, dt.month_number, dt.quarter, dt.season, dt.is_summer_peak,
    ap.airport_name,
    ds.destination_name, ds.destination_country, ds.is_domestic,
    al.airline_name,
    ft.arrival_departure, ft.scheduled_charter,
    f.*  EXCLUDE (date_key, airport_key, destination_key, airline_key, flight_type_key)
FROM fact_punctuality AS f
JOIN dim_date        AS dt USING (date_key)
JOIN dim_airport     AS ap USING (airport_key)
JOIN dim_destination AS ds USING (destination_key)
JOIN dim_airline     AS al USING (airline_key)
JOIN dim_flight_type AS ft USING (flight_type_key);

-- Monthly KPIs per airport
CREATE OR REPLACE VIEW vw_airport_month AS
SELECT
    airport_name, date_key, month_label,
    SUM(flights_matched)                                             AS flights,
    100.0 * SUM(flights_on_time)   / NULLIF(SUM(flights_matched), 0) AS on_time_pct,
    SUM(total_delay_minutes)       / NULLIF(SUM(flights_matched), 0) AS avg_delay_mins,
    100.0 * SUM(flights_cancelled) / NULLIF(SUM(flights_planned), 0) AS cancellation_pct
FROM vw_punctuality
GROUP BY ALL;

-- Monthly KPIs per airline
CREATE OR REPLACE VIEW vw_airline_month AS
SELECT
    airline_name, date_key, month_label,
    SUM(flights_matched)                                             AS flights,
    100.0 * SUM(flights_on_time)   / NULLIF(SUM(flights_matched), 0) AS on_time_pct,
    SUM(total_delay_minutes)       / NULLIF(SUM(flights_matched), 0) AS avg_delay_mins,
    100.0 * SUM(flights_cancelled) / NULLIF(SUM(flights_planned), 0) AS cancellation_pct
FROM vw_punctuality
GROUP BY ALL;
