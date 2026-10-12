-- =====================================================================
-- Business questions answered in SQL (DuckDB).
-- Each query starts with "-- name: <id>" so scripts/build_report.py can run
-- it and save the result to reports/tables/<id>.csv.
--
-- On time = early, or up to 15 minutes late (CAA definition).
-- Minimum-volume filters stop tiny operations topping the rankings.
-- =====================================================================

-- name: q01_headline_kpis
-- Q1. What does UK punctuality look like overall, and versus last year?
SELECT
    SUM(flights_matched)::BIGINT                                          AS flights,
    ROUND(100.0 * SUM(flights_on_time) / SUM(flights_matched), 1)         AS on_time_pct,
    ROUND(SUM(total_delay_minutes) / SUM(flights_matched), 1)             AS avg_delay_mins,
    ROUND(100.0 * SUM(flights_late_61_180 + flights_late_over_180)
          / SUM(flights_matched), 1)                                      AS over_1hr_late_pct,
    ROUND(100.0 * SUM(flights_cancelled) / SUM(flights_planned), 2)       AS cancellation_pct,
    ROUND(100.0 * SUM(py_flights_on_time) / NULLIF(SUM(py_flights_matched), 0), 1) AS py_on_time_pct,
    ROUND(SUM(py_total_delay_minutes) / NULLIF(SUM(py_flights_matched), 0), 1)     AS py_avg_delay_mins
FROM fact_punctuality;

-- name: q02_monthly_trend
-- Q2. How does punctuality move through the year? (LAG for month-on-month change)
WITH monthly AS (
    SELECT
        dt.date_key, dt.month_label,
        SUM(f.flights_matched)                                            AS flights,
        100.0 * SUM(f.flights_on_time) / SUM(f.flights_matched)           AS on_time_pct,
        SUM(f.total_delay_minutes) / SUM(f.flights_matched)               AS avg_delay_mins,
        100.0 * SUM(f.flights_cancelled) / SUM(f.flights_planned)         AS cancellation_pct,
        100.0 * SUM(f.py_flights_on_time) / NULLIF(SUM(f.py_flights_matched), 0) AS py_on_time_pct
    FROM fact_punctuality AS f
    JOIN dim_date AS dt USING (date_key)
    GROUP BY ALL
)
SELECT
    date_key, month_label, flights,
    ROUND(on_time_pct, 1)                                       AS on_time_pct,
    ROUND(on_time_pct - LAG(on_time_pct) OVER (ORDER BY date_key), 1) AS on_time_change_pp,
    ROUND(avg_delay_mins, 1)                                    AS avg_delay_mins,
    ROUND(cancellation_pct, 2)                                  AS cancellation_pct,
    ROUND(py_on_time_pct, 1)                                    AS py_on_time_pct,
    ROUND(on_time_pct - py_on_time_pct, 1)                      AS yoy_change_pp
FROM monthly
ORDER BY date_key;

-- name: q03_airport_league
-- Q3. Which airports are most and least punctual? (airports with 10,000+ flights)
WITH airports AS (
    SELECT
        ap.airport_name,
        SUM(f.flights_matched)                                     AS flights,
        100.0 * SUM(f.flights_on_time) / SUM(f.flights_matched)    AS on_time_pct,
        SUM(f.total_delay_minutes) / SUM(f.flights_matched)        AS avg_delay_mins,
        100.0 * SUM(f.flights_cancelled) / SUM(f.flights_planned)  AS cancellation_pct
    FROM fact_punctuality AS f
    JOIN dim_airport AS ap USING (airport_key)
    GROUP BY ALL
    HAVING SUM(f.flights_matched) >= 10000
)
SELECT
    RANK() OVER (ORDER BY on_time_pct DESC)                     AS on_time_rank,
    airport_name, flights,
    ROUND(100.0 * flights / SUM(flights) OVER (), 1)            AS share_of_flights_pct,
    ROUND(on_time_pct, 1)                                       AS on_time_pct,
    ROUND(avg_delay_mins, 1)                                    AS avg_delay_mins,
    ROUND(cancellation_pct, 2)                                  AS cancellation_pct
FROM airports
ORDER BY on_time_rank;

-- name: q04_airline_league
-- Q4. Which airlines perform best and worst? (airlines with 2,000+ flights)
WITH airlines AS (
    SELECT
        al.airline_name,
        SUM(f.flights_matched)                                     AS flights,
        COUNT(DISTINCT f.airport_key)                              AS uk_airports_served,
        100.0 * SUM(f.flights_on_time) / SUM(f.flights_matched)    AS on_time_pct,
        SUM(f.total_delay_minutes) / SUM(f.flights_matched)        AS avg_delay_mins,
        100.0 * SUM(f.flights_late_61_180 + f.flights_late_over_180)
              / SUM(f.flights_matched)                             AS over_1hr_late_pct,
        100.0 * SUM(f.flights_cancelled) / SUM(f.flights_planned)  AS cancellation_pct
    FROM fact_punctuality AS f
    JOIN dim_airline AS al USING (airline_key)
    GROUP BY ALL
    HAVING SUM(f.flights_matched) >= 2000
)
SELECT
    RANK() OVER (ORDER BY on_time_pct DESC)  AS on_time_rank,
    airline_name, flights, uk_airports_served,
    ROUND(on_time_pct, 1)        AS on_time_pct,
    ROUND(avg_delay_mins, 1)     AS avg_delay_mins,
    ROUND(over_1hr_late_pct, 1)  AS over_1hr_late_pct,
    ROUND(cancellation_pct, 2)   AS cancellation_pct
FROM airlines
ORDER BY on_time_rank;

-- name: q05_airport_peak_months
-- Q5. When is each major airport under most pressure? Worst vs best month
--     (ROW_NUMBER picks the extremes per airport).
WITH airport_month AS (
    SELECT
        ap.airport_name, dt.date_key, dt.month_label,
        SUM(f.flights_matched)                                   AS flights,
        100.0 * SUM(f.flights_on_time) / SUM(f.flights_matched)  AS on_time_pct
    FROM fact_punctuality AS f
    JOIN dim_airport AS ap USING (airport_key)
    JOIN dim_date    AS dt USING (date_key)
    GROUP BY ALL
),
major AS (
    SELECT airport_name FROM airport_month GROUP BY 1 HAVING SUM(flights) >= 10000
),
ranked AS (
    SELECT
        am.*,
        ROW_NUMBER() OVER (PARTITION BY am.airport_name ORDER BY am.on_time_pct ASC)  AS worst_n,
        ROW_NUMBER() OVER (PARTITION BY am.airport_name ORDER BY am.on_time_pct DESC) AS best_n,
        MAX(am.flights) OVER (PARTITION BY am.airport_name)                           AS busiest_month_flights
    FROM airport_month AS am
    JOIN major USING (airport_name)
)
SELECT
    w.airport_name,
    w.month_label                        AS worst_month,
    ROUND(w.on_time_pct, 1)              AS worst_on_time_pct,
    b.month_label                        AS best_month,
    ROUND(b.on_time_pct, 1)              AS best_on_time_pct,
    ROUND(b.on_time_pct - w.on_time_pct, 1) AS seasonal_gap_pp,
    w.flights = w.busiest_month_flights  AS worst_month_is_busiest
FROM ranked AS w
JOIN ranked AS b ON b.airport_name = w.airport_name AND b.best_n = 1
WHERE w.worst_n = 1
ORDER BY seasonal_gap_pp DESC;

-- name: q06_summer_peak_effect
-- Q6. How much does the June–August peak hurt punctuality at each major airport?
SELECT
    ap.airport_name,
    ROUND(100.0 * SUM(f.flights_on_time) FILTER (WHERE dt.is_summer_peak)
               / SUM(f.flights_matched) FILTER (WHERE dt.is_summer_peak), 1)      AS summer_on_time_pct,
    ROUND(100.0 * SUM(f.flights_on_time) FILTER (WHERE NOT dt.is_summer_peak)
               / SUM(f.flights_matched) FILTER (WHERE NOT dt.is_summer_peak), 1)  AS rest_of_year_on_time_pct,
    ROUND(SUM(f.total_delay_minutes) FILTER (WHERE dt.is_summer_peak)
        / SUM(f.flights_matched) FILTER (WHERE dt.is_summer_peak), 1)             AS summer_avg_delay_mins,
    ROUND(SUM(f.total_delay_minutes) FILTER (WHERE NOT dt.is_summer_peak)
        / SUM(f.flights_matched) FILTER (WHERE NOT dt.is_summer_peak), 1)         AS rest_of_year_avg_delay_mins,
    ROUND(summer_on_time_pct - rest_of_year_on_time_pct, 1)                        AS summer_effect_pp
FROM fact_punctuality AS f
JOIN dim_airport AS ap USING (airport_key)
JOIN dim_date    AS dt USING (date_key)
GROUP BY ALL
HAVING SUM(f.flights_matched) >= 10000
   AND SUM(f.flights_matched) FILTER (WHERE dt.is_summer_peak) > 0
   AND SUM(f.flights_matched) FILTER (WHERE NOT dt.is_summer_peak) > 0
ORDER BY summer_effect_pp;

-- name: q07_worst_routes
-- Q7. Which routes have the longest average delays? (routes with 500+ flights)
SELECT
    ap.airport_name,
    ds.destination_name,
    ds.destination_country,
    SUM(f.flights_matched)                                                   AS flights,
    COUNT(DISTINCT f.airline_key)                                            AS airlines,
    ROUND(SUM(f.total_delay_minutes) / SUM(f.flights_matched), 1)            AS avg_delay_mins,
    ROUND(100.0 * SUM(f.flights_on_time) / SUM(f.flights_matched), 1)        AS on_time_pct
FROM fact_punctuality AS f
JOIN dim_airport     AS ap USING (airport_key)
JOIN dim_destination AS ds USING (destination_key)
GROUP BY ALL
HAVING SUM(f.flights_matched) >= 500
ORDER BY avg_delay_mins DESC
LIMIT 15;

-- name: q08_arrival_vs_departure
-- Q8. Are arrivals or departures more punctual?
SELECT
    ft.arrival_departure,
    ft.scheduled_charter,
    SUM(f.flights_matched)                                                AS flights,
    ROUND(100.0 * SUM(f.flights_on_time) / SUM(f.flights_matched), 1)     AS on_time_pct,
    ROUND(SUM(f.total_delay_minutes) / SUM(f.flights_matched), 1)         AS avg_delay_mins,
    ROUND(100.0 * SUM(f.flights_cancelled) / SUM(f.flights_planned), 2)   AS cancellation_pct
FROM fact_punctuality AS f
JOIN dim_flight_type AS ft USING (flight_type_key)
GROUP BY ALL
ORDER BY ft.scheduled_charter DESC, ft.arrival_departure;

-- name: q09_delay_severity
-- Q9. How severe are delays? Share of flights in each band (UNPIVOT).
WITH totals AS (
    SELECT
        SUM(flights_on_time)       AS "On time (≤15 min late)",
        SUM(flights_late_16_60)    AS "16–60 min late",
        SUM(flights_late_61_180)   AS "1–3 hours late",
        SUM(flights_late_over_180) AS "Over 3 hours late",
        SUM(flights_matched)       AS all_flights
    FROM fact_punctuality
)
SELECT
    band,
    ROUND(flights)                       AS flights,
    ROUND(100.0 * flights / all_flights, 2) AS share_pct
FROM totals
UNPIVOT (flights FOR band IN (
    "On time (≤15 min late)", "16–60 min late", "1–3 hours late", "Over 3 hours late"
));

-- name: q10_airline_consistency
-- Q10. Which large airlines are most consistent month to month?
--      (standard deviation of monthly on-time %, airlines with 2,000+ flights)
WITH airline_month AS (
    SELECT
        al.airline_name, f.date_key,
        SUM(f.flights_matched)                                  AS flights,
        100.0 * SUM(f.flights_on_time) / SUM(f.flights_matched) AS on_time_pct
    FROM fact_punctuality AS f
    JOIN dim_airline AS al USING (airline_key)
    GROUP BY ALL
    HAVING SUM(f.flights_matched) > 0
)
SELECT
    airline_name,
    SUM(flights)                         AS flights,
    COUNT(*)                             AS months_operating,
    ROUND(AVG(on_time_pct), 1)           AS mean_monthly_on_time_pct,
    ROUND(MIN(on_time_pct), 1)           AS worst_month_on_time_pct,
    ROUND(STDDEV_SAMP(on_time_pct), 1)   AS volatility_pp
FROM airline_month
GROUP BY airline_name
HAVING SUM(flights) >= 2000 AND COUNT(*) >= 6
ORDER BY volatility_pp;

-- name: q11_domestic_vs_international
-- Q11. Domestic vs international punctuality
SELECT
    CASE WHEN ds.is_domestic THEN 'Domestic' ELSE 'International' END     AS route_type,
    SUM(f.flights_matched)                                                AS flights,
    ROUND(100.0 * SUM(f.flights_on_time) / SUM(f.flights_matched), 1)     AS on_time_pct,
    ROUND(SUM(f.total_delay_minutes) / SUM(f.flights_matched), 1)         AS avg_delay_mins,
    ROUND(100.0 * SUM(f.flights_cancelled) / SUM(f.flights_planned), 2)   AS cancellation_pct
FROM fact_punctuality AS f
JOIN dim_destination AS ds USING (destination_key)
GROUP BY ALL
ORDER BY route_type;

-- name: q12_airport_yoy
-- Q12. Which major airports improved or worsened on last year?
SELECT
    ap.airport_name,
    SUM(f.flights_matched)                                                           AS flights,
    ROUND(100.0 * SUM(f.flights_on_time) / SUM(f.flights_matched), 1)                AS on_time_pct,
    ROUND(100.0 * SUM(f.py_flights_on_time) / NULLIF(SUM(f.py_flights_matched), 0), 1) AS py_on_time_pct,
    ROUND(on_time_pct - py_on_time_pct, 1)                                           AS yoy_change_pp,
    ROUND(100.0 * (SUM(f.flights_matched) - SUM(f.py_flights_matched))
                / NULLIF(SUM(f.py_flights_matched), 0), 1)                           AS traffic_growth_pct
FROM fact_punctuality AS f
JOIN dim_airport AS ap USING (airport_key)
GROUP BY ALL
HAVING SUM(f.flights_matched) >= 10000 AND SUM(f.py_flights_matched) > 0
ORDER BY yoy_change_pp DESC;

-- name: q13_carriers_at_busiest_airports
-- Q13. At the five busiest airports, which carriers (1,000+ flights there)
--      are best and worst? (PARTITION BY airport)
WITH busiest AS (
    SELECT airport_key
    FROM fact_punctuality
    GROUP BY airport_key
    ORDER BY SUM(flights_matched) DESC
    LIMIT 5
),
carrier_airport AS (
    SELECT
        ap.airport_name, al.airline_name,
        SUM(f.flights_matched)                                  AS flights,
        100.0 * SUM(f.flights_on_time) / SUM(f.flights_matched) AS on_time_pct
    FROM fact_punctuality AS f
    JOIN busiest     USING (airport_key)
    JOIN dim_airport AS ap USING (airport_key)
    JOIN dim_airline AS al USING (airline_key)
    GROUP BY ALL
    HAVING SUM(f.flights_matched) >= 1000
),
ranked AS (
    SELECT *,
        RANK() OVER (PARTITION BY airport_name ORDER BY on_time_pct DESC) AS best_rank,
        RANK() OVER (PARTITION BY airport_name ORDER BY on_time_pct ASC)  AS worst_rank
    FROM carrier_airport
)
SELECT
    airport_name,
    CASE WHEN best_rank = 1 THEN 'Most punctual' ELSE 'Least punctual' END AS position,
    airline_name, flights, ROUND(on_time_pct, 1) AS on_time_pct
FROM ranked
WHERE best_rank = 1 OR worst_rank = 1
ORDER BY airport_name, position;
