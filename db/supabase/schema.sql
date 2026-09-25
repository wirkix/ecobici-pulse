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

-- Explicit Data API grants. From 2026-10-30 Supabase no longer grants new
-- public tables to these roles automatically, so without these lines a
-- fresh project would leave the table unreadable by the map (permission
-- denied). Matches what the live project has: read-only for the public
-- roles, everything for the service role.
GRANT SELECT ON station_snapshot TO anon, authenticated;
GRANT ALL ON station_snapshot TO service_role;

-- Projects created before that change (this one included) gave
-- anon/authenticated full table privileges by default, relying on RLS to
-- block writes. Revoke the write privileges too, so a future policy
-- mistake (or TRUNCATE, which RLS doesn't cover) can't turn into public
-- write access. The consumer writes with the service role. Harmless on a
-- project where they were never granted.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON station_snapshot FROM anon, authenticated;

-- Live updates go over the *private* Realtime channel "stations". Anon can
-- receive broadcasts on it; there is deliberately no INSERT policy, so
-- nobody but the consumer (service role, bypasses RLS) can send. Pair this
-- with Realtime Settings -> "Allow public access" OFF, so the old public
-- channel (where anyone with the anon key could broadcast) is gone.
CREATE POLICY "anon can receive station broadcasts"
    ON realtime.messages FOR SELECT TO anon
    USING (realtime.topic() = 'stations' AND extension = 'broadcast');
