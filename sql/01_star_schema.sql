-- =====================================================================
-- UK Airport Punctuality: star schema (DuckDB SQL)
--
-- Source: stg_punctuality, the cleaned CAA rows loaded by the pipeline.
-- Grain of the fact table: one row per
--   month x reporting airport x origin/destination x airline
--   x arrival/departure x scheduled/charter
--
--                    dim_date
--                       |
--   dim_airport --- fact_punctuality --- dim_airline
--                    /          \
--         dim_destination    dim_flight_type
-- =====================================================================

-- ---------------------------------------------------------------------
-- dim_date: one row per reporting month
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE dim_date AS
SELECT
    period                                         AS date_key,      -- YYYYMM
    month_start,
    year(month_start)                              AS year,
    month(month_start)                             AS month_number,
    strftime(month_start, '%B')                    AS month_name,
    strftime(month_start, '%b %Y')                 AS month_label,
    'Q' || quarter(month_start)                    AS quarter,
    CASE
        WHEN month(month_start) IN (12, 1, 2) THEN 'Winter'
        WHEN month(month_start) IN (3, 4, 5)  THEN 'Spring'
        WHEN month(month_start) IN (6, 7, 8)  THEN 'Summer'
        ELSE 'Autumn'
    END                                            AS season,
    month(month_start) IN (6, 7, 8)                AS is_summer_peak
FROM (
    SELECT DISTINCT
        reporting_period                                               AS period,
        make_date(reporting_period // 100, reporting_period % 100, 1)  AS month_start
    FROM stg_punctuality
)
ORDER BY date_key;

-- ---------------------------------------------------------------------
-- dim_airport: UK reporting airports
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE dim_airport AS
SELECT
    row_number() OVER (ORDER BY reporting_airport)  AS airport_key,
    reporting_airport                               AS airport_name
FROM (SELECT DISTINCT reporting_airport FROM stg_punctuality);

-- ---------------------------------------------------------------------
-- dim_destination: the other end of the route
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE dim_destination AS
SELECT
    row_number() OVER (ORDER BY origin_destination_country, origin_destination) AS destination_key,
    origin_destination                       AS destination_name,
    origin_destination_country               AS destination_country,
    origin_destination_country IN (
        'UNITED KINGDOM', 'UK', 'ENGLAND', 'SCOTLAND', 'WALES',
        'NORTHERN IRELAND', 'CHANNEL ISLANDS', 'ISLE OF MAN'
    )                                        AS is_domestic
FROM (SELECT DISTINCT origin_destination, origin_destination_country FROM stg_punctuality);

-- ---------------------------------------------------------------------
-- dim_airline
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE dim_airline AS
SELECT
    row_number() OVER (ORDER BY airline_name)  AS airline_key,
    airline_name
FROM (SELECT DISTINCT airline_name FROM stg_punctuality);

-- ---------------------------------------------------------------------
-- dim_flight_type: small "junk" dimension for the two flags
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE dim_flight_type AS
SELECT
    row_number() OVER (ORDER BY ad.code, sc.code)  AS flight_type_key,
    ad.code                                        AS arrival_departure_code,
    ad.label                                       AS arrival_departure,
    sc.code                                        AS scheduled_charter_code,
    sc.label                                       AS scheduled_charter
FROM (VALUES ('A', 'Arrival'), ('D', 'Departure')) AS ad(code, label)
CROSS JOIN (VALUES ('S', 'Scheduled'), ('C', 'Charter')) AS sc(code, label);

-- ---------------------------------------------------------------------
-- fact_punctuality
-- Percentages in the source are converted to flight counts so that every
-- measure is additive and can be re-aggregated correctly at any level
-- (averaging percentages across rows would be wrong).
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE fact_punctuality AS
WITH derived AS (
    SELECT
        s.*,
        number_flights_matched / 100.0 AS m   -- multiplier: percent -> flights
    FROM stg_punctuality AS s
)
SELECT
    d.reporting_period                                   AS date_key,
    a.airport_key,
    ds.destination_key,
    al.airline_key,
    ft.flight_type_key,

    SUM(number_flights_matched)                          AS flights_matched,
    SUM(actual_flights_unmatched)                        AS flights_unmatched,
    SUM(number_flights_cancelled)                        AS flights_cancelled,
    SUM(number_flights_matched + actual_flights_unmatched
        + number_flights_cancelled)                      AS flights_planned,

    -- CAA definition of "on time": early, or up to 15 minutes late
    SUM(m * (flights_more_than_15_minutes_early_percent
           + flights_15_minutes_early_to_1_minute_early_percent
           + flights_0_to_15_minutes_late_percent))      AS flights_on_time,
    SUM(m * (flights_between_16_and_30_minutes_late_percent
           + flights_between_31_and_60_minutes_late_percent)) AS flights_late_16_60,
    SUM(m * (flights_between_61_and_120_minutes_late_percent
           + flights_between_121_and_180_minutes_late_percent)) AS flights_late_61_180,
    SUM(m * (flights_between_181_and_360_minutes_late_percent
           + flights_more_than_360_minutes_late_percent)) AS flights_late_over_180,

    SUM(number_flights_matched * average_delay_mins)     AS total_delay_minutes,

    -- same month, previous year (as published by the CAA)
    SUM(previous_year_month_flights_matched)             AS py_flights_matched,
    SUM(previous_year_month_flights_matched / 100.0
        * coalesce(previous_year_month_early_to_15_mins_late_percent, 0)) AS py_flights_on_time,
    SUM(previous_year_month_flights_matched
        * coalesce(previous_year_month_average_delay, 0)) AS py_total_delay_minutes
FROM derived AS d
JOIN dim_airport     AS a  ON a.airport_name = d.reporting_airport
JOIN dim_destination AS ds ON ds.destination_name = d.origin_destination
                          AND ds.destination_country = d.origin_destination_country
JOIN dim_airline     AS al ON al.airline_name = d.airline_name
JOIN dim_flight_type AS ft ON ft.arrival_departure_code = d.arrival_departure
                          AND ft.scheduled_charter_code = d.scheduled_charter
GROUP BY ALL;
