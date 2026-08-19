/*
Staging model: stg_ctgov__studies

Transforms raw_ctgov__studies (one row per study per run) into a clean,
deduplicated, column-oriented view with business classification flags.

Steps:
  1. latest_runs  — deduplicate to the most recent ingestion run per nct_id
  2. flattened    — extract typed columns from raw_json using Databricks : operator
  3. classified   — add is_early_stop and is_closed boolean flags

Grain: one row per nct_id (current state as of last pipeline run)
*/

WITH latest_runs AS (

    SELECT
        nct_id,
        raw_json,
        run_ts,
        ROW_NUMBER() OVER (
            PARTITION BY nct_id
            ORDER BY run_ts DESC
        ) AS rn

    FROM {{ source('landing', 'raw_ctgov__studies') }}
    WHERE nct_id IS NOT NULL   -- guard against malformed rows

),

flattened AS (

    SELECT
        nct_id,
        run_ts                                                                              AS last_updated_run_ts,

        -- Status
        raw_json:protocolSection:statusModule:overallStatus::string                         AS overall_status,
        raw_json:protocolSection:statusModule:whyStopped::string                            AS why_stopped,

        -- Sponsor
        raw_json:protocolSection:sponsorCollaboratorsModule:leadSponsor:class::string       AS sponsor_class,
        raw_json:protocolSection:sponsorCollaboratorsModule:leadSponsor:name::string        AS sponsor_name,

        -- Design
        raw_json:protocolSection:designModule:phases::string                                AS phases_raw,
        raw_json:protocolSection:designModule:studyType::string                             AS study_type,

        -- Identification
        raw_json:protocolSection:identificationModule:briefTitle::string                    AS brief_title,
        raw_json:protocolSection:identificationModule:officialTitle::string                 AS official_title,

        -- Dates — use TRY_CAST to handle month-only values like "2015-01"
        TRY_CAST(
            raw_json:protocolSection:statusModule:startDateStruct:date::string AS DATE
        )                                                                                   AS start_date,

        TRY_CAST(
            raw_json:protocolSection:statusModule:completionDateStruct:date::string AS DATE
        )                                                                                   AS completion_date,

        TRY_CAST(
            raw_json:protocolSection:statusModule:studyFirstSubmitDate::string AS DATE
        )                                                                                   AS first_submitted_date

    FROM latest_runs
    WHERE rn = 1

),

classified AS (

    SELECT
        *,

        -- Early stop: trial closed before reaching natural completion
        CASE
            WHEN overall_status IN ('TERMINATED', 'WITHDRAWN', 'SUSPENDED') THEN TRUE
            ELSE FALSE
        END                                                                                 AS is_early_stop,

        -- Closed: trial is no longer actively running (includes completed + early stop)
        CASE
            WHEN overall_status IN ('COMPLETED', 'TERMINATED', 'WITHDRAWN', 'SUSPENDED') THEN TRUE
            ELSE FALSE
        END                                                                                 AS is_closed

    FROM flattened

)

SELECT * FROM classified
