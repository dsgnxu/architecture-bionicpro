CREATE DATABASE IF NOT EXISTS bionicpro;

-- Legacy mart (Assignment 2 batch ETL). Kept for reference; API uses report_mart_cdc.
CREATE TABLE IF NOT EXISTS bionicpro.report_mart
(
    user_id String,
    username String,
    report_date Date,
    usage_hours Float64,
    movement_count UInt32,
    calibrations UInt32,
    crm_status String,
    prosthesis_model String
)
ENGINE = MergeTree
ORDER BY (username, report_date);

CREATE TABLE IF NOT EXISTS bionicpro.etl_watermark
(
    pipeline String,
    processed_to DateTime
)
ENGINE = ReplacingMergeTree
ORDER BY pipeline;

-- Assignment 4: CDC CRM via KafkaEngine
-- Debezium DATE → days since epoch (Int32) with time.precision.mode=connect
CREATE TABLE IF NOT EXISTS bionicpro.crm_clients_queue
(
    user_id String,
    username String,
    full_name String,
    email Nullable(String),
    crm_status String,
    prosthesis_model String,
    registered_at Int32,
    `__deleted` String
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list = 'kafka:9092',
    kafka_topic_list = 'crm.public.clients',
    kafka_group_name = 'clickhouse_crm_clients',
    kafka_format = 'JSONEachRow',
    kafka_num_consumers = 1,
    kafka_skip_broken_messages = 100;

CREATE TABLE IF NOT EXISTS bionicpro.crm_clients
(
    user_id String,
    username String,
    full_name String,
    email String,
    crm_status String,
    prosthesis_model String,
    registered_at Date,
    updated_at DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY user_id;

CREATE MATERIALIZED VIEW IF NOT EXISTS bionicpro.crm_clients_mv
TO bionicpro.crm_clients
AS
SELECT
    user_id,
    username,
    full_name,
    ifNull(email, '') AS email,
    crm_status,
    prosthesis_model,
    toDate(registered_at) AS registered_at,
    now() AS updated_at
FROM bionicpro.crm_clients_queue
WHERE `__deleted` != 'true';

-- Telemetry facts (Airflow batch, no CRM join)
CREATE TABLE IF NOT EXISTS bionicpro.telemetry_daily
(
    user_id String,
    username String,
    report_date Date,
    usage_hours Float64,
    movement_count UInt32,
    calibrations UInt32
)
ENGINE = MergeTree
ORDER BY (username, report_date);

-- Reporting mart: telemetry INSERT → JOIN latest CRM dim from CDC
CREATE TABLE IF NOT EXISTS bionicpro.report_mart_cdc
(
    user_id String,
    username String,
    report_date Date,
    usage_hours Float64,
    movement_count UInt32,
    calibrations UInt32,
    crm_status String,
    prosthesis_model String
)
ENGINE = MergeTree
ORDER BY (username, report_date);

CREATE MATERIALIZED VIEW IF NOT EXISTS bionicpro.report_mart_cdc_mv
TO bionicpro.report_mart_cdc
AS
SELECT
    t.user_id,
    t.username,
    t.report_date,
    t.usage_hours,
    t.movement_count,
    t.calibrations,
    ifNull(c.crm_status, 'unknown') AS crm_status,
    ifNull(c.prosthesis_model, 'unknown') AS prosthesis_model
FROM bionicpro.telemetry_daily AS t
LEFT JOIN
(
    SELECT
        username,
        argMax(crm_status, updated_at) AS crm_status,
        argMax(prosthesis_model, updated_at) AS prosthesis_model
    FROM bionicpro.crm_clients
    GROUP BY username
) AS c ON t.username = c.username;
