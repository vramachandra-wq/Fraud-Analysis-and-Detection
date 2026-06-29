CREATE OR REPLACE FUNCTION curated.fn_analyze_transaction_fraud(

    -- Performance Parameter
    p_lookback_days             INT     DEFAULT 1,     -- NULL = full history

    -- Rule 1: High Value Withdrawals
    p_high_val_days             INT     DEFAULT 1,
    p_high_val_txn_count        INT     DEFAULT 3,
    p_high_val_amount_threshold NUMERIC DEFAULT 50000,

    -- Rule 2: Multiple ATM Locations
    p_atm_mult_days             INT     DEFAULT 1,
    p_atm_mult_txn_count        INT     DEFAULT 3,
    p_atm_mult_amount_threshold NUMERIC DEFAULT 50000,

    -- Rule 3: Impossible ATM Travel Velocity
    p_velocity_hours            INT     DEFAULT 24,
    p_velocity_min_txns         INT     DEFAULT 2,
    p_velocity_km_threshold     NUMERIC DEFAULT 100,
    p_velocity_kmh              NUMERIC DEFAULT 100,

    -- Rule 4: Concurrent Account Devices
    p_device_minutes_window     INT     DEFAULT 10,
    p_device_min_burst_freq     INT     DEFAULT 2

)
RETURNS TABLE (
    transaction_id      "curated"."fact_transactions".transaction_id%TYPE,
    customer_id         "curated"."dim_account".customer_id%TYPE,
    account_id          "curated"."fact_transactions".account_id%TYPE,
    transaction_type    "curated"."fact_transactions".transaction_type%TYPE,
    channel             "curated"."fact_transactions".channel%TYPE,
    amount              "curated"."fact_transactions".amount%TYPE,
    transaction_status  "curated"."fact_transactions".transaction_status%TYPE,
    transaction_date    "curated"."fact_transactions".transaction_date%TYPE,
    transaction_time    "curated"."fact_transactions".transaction_time%TYPE,
    created_at          "curated"."fact_transactions".created_at%TYPE,
    location_id         "curated"."fact_transactions".location_id%TYPE,
    device_id           "curated"."fact_transactions".device_id%TYPE,
    reference_number    "curated"."fact_transactions".reference_number%TYPE,
    fraud_flag          BOOLEAN,
    fraud_reason        TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_high_val_window   INTERVAL;
    v_atm_mult_window   INTERVAL;
    v_velocity_window   INTERVAL;
    v_device_window     INTERVAL;
BEGIN
    -- Explicitly generate clean intervals to prevent runtime evaluation bugs in window constructs
    v_high_val_window := (p_high_val_days || ' DAYS')::INTERVAL;
    v_atm_mult_window := (p_atm_mult_days || ' DAYS')::INTERVAL;
    v_velocity_window := (p_velocity_hours || ' HOURS')::INTERVAL;
    v_device_window   := (p_device_minutes_window || ' MINUTES')::INTERVAL;

    RETURN QUERY
    WITH

    max_date AS (
        SELECT MAX(t.transaction_date) AS anchor_date
        FROM "curated"."fact_transactions" t
    ),

    unique_accounts AS (
        SELECT DISTINCT ON (da.account_id)
            da.account_id,
            da.customer_id
        FROM "curated"."dim_account" da
        ORDER BY da.account_id, da.is_current DESC, da.created_at DESC
    ),

    unique_locations AS (
        SELECT DISTINCT ON (dl.location_id)
            dl.location_id,
            dl.latitude,
            dl.longitude
        FROM "curated"."dim_location" dl
        ORDER BY dl.location_id
    ),

    base_transactions AS (
        SELECT
            t.transaction_id        AS src_transaction_id,
            t.account_id            AS src_account_id,
            a.customer_id           AS src_customer_id,
            t.transaction_type      AS src_transaction_type,
            t.channel               AS src_channel,
            t.amount                AS src_amount,
            t.transaction_status    AS src_transaction_status,
            t.transaction_date      AS src_transaction_date,
            t.transaction_time      AS src_transaction_time,
            t.created_at            AS src_created_at,
            t.location_id           AS src_location_id,
            t.device_id             AS src_device_id,
            t.reference_number      AS src_reference_number,
            (t.transaction_date + t.transaction_time) AS txn_timestamp,
            loc.latitude,
            loc.longitude
        FROM "curated"."fact_transactions" t
        CROSS JOIN max_date md
        INNER JOIN unique_accounts a
            ON t.account_id = a.account_id
        LEFT JOIN unique_locations loc
            ON t.location_id = loc.location_id
        WHERE (
            p_lookback_days IS NULL
            -- Soft buffer added (+2 days) to base query so lagging identifiers are pulled for calculations
            OR t.transaction_date >= md.anchor_date - ((p_lookback_days + 2) * INTERVAL '1 DAY')
        )
    ),

    atm_distinct_locations AS (
        SELECT DISTINCT
            b.src_customer_id,
            b.src_location_id,
            CAST(b.txn_timestamp AS DATE) AS txn_date
        FROM base_transactions b
        WHERE b.src_transaction_type = 'WITHDRAWAL'
          AND LOWER(b.src_channel)   = 'atm'
          AND b.src_location_id IS NOT NULL
    ),

    atm_location_counts AS (
        SELECT
            d.src_customer_id,
            d.txn_date,
            COUNT(*) OVER (
                PARTITION BY d.src_customer_id
                ORDER BY d.txn_date
                RANGE BETWEEN v_atm_mult_window PRECEDING AND CURRENT ROW
            ) AS unique_atms_in_window
        FROM atm_distinct_locations d
    ),

    atm_location_counts_by_date AS (
        SELECT
            src_customer_id,
            txn_date,
            MAX(unique_atms_in_window) AS unique_atms_in_window
        FROM atm_location_counts
        GROUP BY src_customer_id, txn_date
    ),

    window_metrics AS (
        SELECT
            b.*,

            -- RULE 1
            COUNT(*) OVER (
                PARTITION BY b.src_customer_id, b.src_account_id
                ORDER BY b.txn_timestamp
                RANGE BETWEEN v_high_val_window PRECEDING AND CURRENT ROW
            ) AS r1_rolling_txn_count,

            SUM(CASE WHEN b.src_transaction_type = 'WITHDRAWAL'
                     THEN b.src_amount ELSE 0 END
            ) OVER (
                PARTITION BY b.src_customer_id, b.src_account_id
                ORDER BY b.txn_timestamp
                RANGE BETWEEN v_high_val_window PRECEDING AND CURRENT ROW
            ) AS r1_rolling_amount,

            -- RULE 2
            COUNT(CASE WHEN b.src_transaction_type = 'WITHDRAWAL'
                            AND LOWER(b.src_channel) = 'atm' THEN 1 END
            ) OVER (
                PARTITION BY b.src_customer_id
                ORDER BY b.txn_timestamp
                RANGE BETWEEN v_atm_mult_window PRECEDING AND CURRENT ROW
            ) AS r2_rolling_atm_count,

            SUM(CASE WHEN b.src_transaction_type = 'WITHDRAWAL'
                          AND LOWER(b.src_channel) = 'atm'
                     THEN b.src_amount ELSE 0 END
            ) OVER (
                PARTITION BY b.src_customer_id
                ORDER BY b.txn_timestamp
                RANGE BETWEEN v_atm_mult_window PRECEDING AND CURRENT ROW
            ) AS r2_rolling_atm_amount,

            -- RULE 3
            COUNT(CASE WHEN b.src_transaction_type = 'WITHDRAWAL'
                            AND LOWER(b.src_channel) = 'atm' THEN 1 END
            ) OVER (
                PARTITION BY b.src_customer_id
                ORDER BY b.txn_timestamp
                RANGE BETWEEN v_velocity_window PRECEDING AND CURRENT ROW
            ) AS r3_total_window_withdrawals,

            LAG(b.src_location_id) OVER (PARTITION BY b.src_customer_id ORDER BY b.txn_timestamp) AS prev_location_id,
            LAG(b.txn_timestamp)   OVER (PARTITION BY b.src_customer_id ORDER BY b.txn_timestamp) AS prev_txn_timestamp,
            LAG(b.latitude)        OVER (PARTITION BY b.src_customer_id ORDER BY b.txn_timestamp) AS prev_latitude,
            LAG(b.longitude)       OVER (PARTITION BY b.src_customer_id ORDER BY b.txn_timestamp) AS prev_longitude,

            -- RULE 4
            LAG(b.src_device_id)   OVER (PARTITION BY b.src_account_id ORDER BY b.txn_timestamp) AS prev_device_id,
            LAG(b.txn_timestamp)   OVER (PARTITION BY b.src_account_id ORDER BY b.txn_timestamp) AS r4_prev_txn_timestamp,

            COUNT(CASE WHEN b.src_device_id IS NOT NULL THEN 1 END
            ) OVER (
                PARTITION BY b.src_account_id
                ORDER BY b.txn_timestamp
                RANGE BETWEEN v_device_window PRECEDING AND CURRENT ROW
            ) AS r4_rapid_account_txn_count

        FROM base_transactions b
    ),

    advanced_calculations AS (
        SELECT
            w.*,
            COALESCE(alc.unique_atms_in_window, 0) AS unique_atms_visited,

            EXTRACT(EPOCH FROM (w.txn_timestamp - w.prev_txn_timestamp)) / 3600.0
                AS travel_hours_elapsed,

            CASE
                WHEN w.prev_location_id IS NOT NULL
                 AND w.prev_location_id <> w.src_location_id
                THEN 6371.0 * acos(
                        GREATEST(-1.0, LEAST(1.0,
                            cos(radians(w.latitude))     * cos(radians(w.prev_latitude))
                          * cos(radians(w.prev_longitude) - radians(w.longitude))
                          + sin(radians(w.latitude))     * sin(radians(w.prev_latitude))
                        ))
                     )
                ELSE 0.0
            END AS distance_km,

            EXTRACT(EPOCH FROM (w.txn_timestamp - w.r4_prev_txn_timestamp)) / 60.0
                AS device_minutes_elapsed

        FROM window_metrics w
        LEFT JOIN atm_location_counts_by_date alc
            ON  w.src_customer_id              = alc.src_customer_id
            AND CAST(w.txn_timestamp AS DATE)  = alc.txn_date
    ),

    flagged_pipeline AS (
        SELECT
            c.src_transaction_id,
            c.src_customer_id,
            c.src_account_id,
            c.src_transaction_type,
            c.src_channel,
            c.src_amount,
            c.src_transaction_status,
            c.src_transaction_date,
            c.src_transaction_time,
            c.src_created_at,
            c.src_location_id,
            c.src_device_id,
            c.src_reference_number,

            (
                c.src_transaction_type = 'WITHDRAWAL'
                AND c.r1_rolling_txn_count >= p_high_val_txn_count
                AND c.r1_rolling_amount    >= p_high_val_amount_threshold
            ) AS is_r1_fraud,

            (
                c.src_transaction_type  = 'WITHDRAWAL'
                AND LOWER(c.src_channel)       = 'atm'
                AND c.r2_rolling_atm_count    >= p_atm_mult_txn_count
                AND c.r2_rolling_atm_amount   >= p_atm_mult_amount_threshold
                AND c.unique_atms_visited     >= p_atm_mult_txn_count
            ) AS is_r2_fraud,

            (
                c.src_transaction_type  = 'WITHDRAWAL'
                AND LOWER(c.src_channel)              = 'atm'
                AND c.prev_location_id               IS NOT NULL
                AND c.prev_location_id               <> c.src_location_id
                AND c.r3_total_window_withdrawals      >= p_velocity_min_txns
                AND c.distance_km                    >= p_velocity_km_threshold
                AND c.travel_hours_elapsed             > 0
                AND (c.distance_km / c.travel_hours_elapsed) > p_velocity_kmh
            ) AS is_r3_fraud,

            (
                c.src_device_id              IS NOT NULL
                AND c.prev_device_id         IS NOT NULL
                AND c.src_device_id              <> c.prev_device_id
                AND c.device_minutes_elapsed    <= p_device_minutes_window
                AND c.r4_rapid_account_txn_count >= p_device_min_burst_freq
            ) AS is_r4_fraud

        FROM advanced_calculations c
    )

    SELECT
        f.src_transaction_id    AS transaction_id,
        f.src_customer_id       AS customer_id,
        f.src_account_id        AS account_id,
        f.src_transaction_type  AS transaction_type,
        f.src_channel           AS channel,
        f.src_amount            AS amount,
        f.src_transaction_status AS transaction_status,
        f.src_transaction_date  AS transaction_date,
        f.src_transaction_time  AS transaction_time,
        f.src_created_at        AS created_at,
        f.src_location_id       AS location_id,
        f.src_device_id         AS device_id,
        f.src_reference_number  AS reference_number,

        (f.is_r1_fraud OR f.is_r2_fraud OR f.is_r3_fraud OR f.is_r4_fraud) AS fraud_flag,

        CASE
            WHEN NOT (f.is_r1_fraud OR f.is_r2_fraud OR f.is_r3_fraud OR f.is_r4_fraud)
            THEN NULL
            ELSE CONCAT_WS(' | ',
                CASE WHEN f.is_r1_fraud THEN 'MULTIPLE_WITHDRAWALS_HIGH_VALUE' END,
                CASE WHEN f.is_r2_fraud THEN 'MULTIPLE_ATM_TRANSACTIONS'       END,
                CASE WHEN f.is_r3_fraud THEN 'IMPOSSIBLE_ATM_TRAVEL_VELOCITY'  END,
                CASE WHEN f.is_r4_fraud THEN 'CONCURRENT_ACCOUNT_DEVICES'      END
            )
        END AS fraud_reason
    FROM flagged_pipeline f
    CROSS JOIN max_date md
    WHERE (
        p_lookback_days IS NULL 
        OR f.src_transaction_date >= md.anchor_date - (p_lookback_days * INTERVAL '1 DAY')
    )
    ORDER BY f.src_transaction_id;

END;
$$;