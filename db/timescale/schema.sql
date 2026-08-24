-- TimescaleDB schema: full history of station status readings.
-- Run against the self-hosted TimescaleDB instance (local docker-compose
-- or the production VM) -- this is NOT the Supabase database.

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS station_status_history (
    time            TIMESTAMPTZ NOT NULL,
    station_id      TEXT NOT NULL,
    bikes_available INTEGER NOT NULL,
    docks_available INTEGER NOT NULL,
    occupancy_pct   DOUBLE PRECISION NOT NULL,
    is_renting      BOOLEAN NOT NULL,
    is_returning    BOOLEAN NOT NULL
);

SELECT create_hypertable('station_status_history', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_station_status_history_station_time
    ON station_status_history (station_id, time DESC);

-- Small footprint by design: this runs on a free-tier VM. Keep 14 days of
-- history -- plenty for a "last 24h" chart in the portfolio demo, cheap on
-- disk, and TimescaleDB drops whole chunks rather than doing row-by-row
-- deletes.
SELECT add_retention_policy('station_status_history', INTERVAL '14 days', if_not_exists => TRUE);
