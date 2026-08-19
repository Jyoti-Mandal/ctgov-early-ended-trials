/*
Mart model: mart_sponsor_early_stop

Answers the business question:
  "Which sponsor class has the highest proportion of trials that ended early,
   and how does this compare to industry-sponsored trials?"

Grain: one row per sponsor_class

Denominator: closed trials only (COMPLETED + early-stop statuses).
Ongoing trials are excluded — you cannot assess early stopping on active trials.

Key columns:
  early_stop_rate       — proportion of closed trials that ended early (0–1)
  industry_early_stop_rate — the INDUSTRY rate broadcast to every row for comparison
  vs_industry_delta     — positive = higher early-stop rate than industry
  early_stop_rank       — 1 = highest early-stop proportion
*/

WITH sponsor_summary AS (

    SELECT
        sponsor_class,
        COUNT(*)                                                AS total_closed_trials,
        SUM(CASE WHEN is_early_stop THEN 1 ELSE 0 END)         AS early_stop_trials,
        SUM(CASE WHEN NOT is_early_stop THEN 1 ELSE 0 END)     AS completed_trials

    FROM {{ ref('stg_ctgov__studies') }}
    WHERE is_closed = TRUE      -- restrict denominator to closed trials only

    GROUP BY sponsor_class

),

with_rates AS (

    SELECT
        sponsor_class,
        total_closed_trials,
        early_stop_trials,
        completed_trials,

        -- Early-stop rate: NULLIF guards against zero-denominator
        ROUND(
            early_stop_trials / NULLIF(total_closed_trials, 0),
            4
        )                                                       AS early_stop_rate,

        -- Broadcast the INDUSTRY rate across all rows for comparison
        MAX(
            CASE
                WHEN sponsor_class = 'INDUSTRY'
                THEN ROUND(early_stop_trials / NULLIF(total_closed_trials, 0), 4)
            END
        ) OVER ()                                               AS industry_early_stop_rate

    FROM sponsor_summary

)

SELECT
    sponsor_class,
    total_closed_trials,
    early_stop_trials,
    completed_trials,
    early_stop_rate,
    industry_early_stop_rate,

    -- Delta vs industry: positive = worse than industry, negative = better
    ROUND(early_stop_rate - industry_early_stop_rate, 4)        AS vs_industry_delta,

    -- RANK allows ties; use DENSE_RANK if you want no gaps in ranking sequence
    RANK() OVER (ORDER BY early_stop_rate DESC)                 AS early_stop_rank

FROM with_rates
ORDER BY early_stop_rank
