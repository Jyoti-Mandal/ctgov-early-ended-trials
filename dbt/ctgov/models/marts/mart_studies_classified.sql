/*
Mart model: mart_studies_classified

Study-level detail mart for closed trials.
Enables analysts to drill into individual trials behind any aggregate number
in mart_sponsor_early_stop.

Grain: one row per nct_id (closed trials only)
*/

SELECT
    nct_id,
    brief_title,
    official_title,
    sponsor_class,
    sponsor_name,
    overall_status,
    why_stopped,
    is_early_stop,
    start_date,
    completion_date,
    first_submitted_date,
    phases_raw,
    last_updated_run_ts

FROM {{ ref('stg_ctgov__studies') }}
WHERE is_closed = TRUE
ORDER BY sponsor_class, nct_id
