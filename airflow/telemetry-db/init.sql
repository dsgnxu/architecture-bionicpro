-- Mock telemetry from prosthesis sensors (OLTP source for ETL)
CREATE TABLE IF NOT EXISTS telemetry_events (
    id              BIGSERIAL PRIMARY KEY,
    user_id         VARCHAR(64) NOT NULL,
    username        VARCHAR(128) NOT NULL,
    event_ts        TIMESTAMPTZ NOT NULL,
    event_type      VARCHAR(64) NOT NULL,
    usage_hours     NUMERIC(10, 2) NOT NULL DEFAULT 0,
    movement_count  INTEGER NOT NULL DEFAULT 0,
    calibrations    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_telemetry_user_ts ON telemetry_events (username, event_ts);

-- Seed several days of data ending "yesterday" so Airflow can process them
INSERT INTO telemetry_events (user_id, username, event_ts, event_type, usage_hours, movement_count, calibrations) VALUES
    ('u-prothetic1', 'prothetic1', CURRENT_DATE - INTERVAL '3 days' + TIME '09:00', 'daily_usage', 4.5, 120, 1),
    ('u-prothetic1', 'prothetic1', CURRENT_DATE - INTERVAL '3 days' + TIME '18:00', 'daily_usage', 2.0, 80, 0),
    ('u-prothetic1', 'prothetic1', CURRENT_DATE - INTERVAL '2 days' + TIME '10:00', 'daily_usage', 5.2, 150, 1),
    ('u-prothetic1', 'prothetic1', CURRENT_DATE - INTERVAL '1 day' + TIME '11:00', 'daily_usage', 3.8, 95, 0),
    ('u-prothetic2', 'prothetic2', CURRENT_DATE - INTERVAL '3 days' + TIME '08:00', 'daily_usage', 3.0, 60, 1),
    ('u-prothetic2', 'prothetic2', CURRENT_DATE - INTERVAL '2 days' + TIME '12:00', 'daily_usage', 4.1, 110, 0),
    ('u-prothetic2', 'prothetic2', CURRENT_DATE - INTERVAL '1 day' + TIME '15:00', 'daily_usage', 2.5, 70, 1),
    ('u-prothetic3', 'prothetic3', CURRENT_DATE - INTERVAL '2 days' + TIME '09:30', 'daily_usage', 6.0, 200, 2),
    ('u-prothetic3', 'prothetic3', CURRENT_DATE - INTERVAL '1 day' + TIME '14:00', 'daily_usage', 1.5, 40, 0),
    ('u-john-doe', 'john.doe', CURRENT_DATE - INTERVAL '3 days' + TIME '07:00', 'daily_usage', 5.0, 140, 1),
    ('u-john-doe', 'john.doe', CURRENT_DATE - INTERVAL '2 days' + TIME '16:00', 'daily_usage', 3.2, 90, 0),
    ('u-john-doe', 'john.doe', CURRENT_DATE - INTERVAL '1 day' + TIME '10:00', 'daily_usage', 4.7, 130, 1),
    ('u-alex-johnson', 'alex.johnson', CURRENT_DATE - INTERVAL '2 days' + TIME '11:00', 'daily_usage', 2.8, 75, 0),
    ('u-alex-johnson', 'alex.johnson', CURRENT_DATE - INTERVAL '1 day' + TIME '13:00', 'daily_usage', 3.5, 100, 1);
