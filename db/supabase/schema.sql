-- Supabase Postgres schema: current-state snapshot only (not history --
-- that lives in TimescaleDB). This table backs the Next.js app's initial
-- page load; Realtime broadcast (not Postgres Changes) carries live
-- updates, so this table does not need to be replication-enabled.

CREATE TABLE IF NOT EXISTS station_snapshot (
    station_id      TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    lat             DOUBLE PRECISION NOT NULL,
    lon             DOUBLE PRECISION NOT NULL,
    capacity        INTEGER NOT NULL,
    bikes_available INTEGER NOT NULL,
    docks_available INTEGER NOT NULL,
    occupancy_pct   DOUBLE PRECISION NOT NULL,
    is_renting      BOOLEAN NOT NULL,
    is_returning    BOOLEAN NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL
);

ALTER TABLE station_snapshot ENABLE ROW LEVEL SECURITY;

-- Public, read-only: the map is a portfolio demo, no login. Only the
-- consumer (using the service role key, which bypasses RLS entirely)
-- ever writes to this table.
CREATE POLICY "station_snapshot is publicly readable"
    ON station_snapshot
    FOR SELECT
    TO anon
    USING (true);
