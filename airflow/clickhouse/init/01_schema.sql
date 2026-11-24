CREATE DATABASE IF NOT EXISTS bionicpro;

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
