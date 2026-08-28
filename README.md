# Ecobici Pulse

**Live demo: https://ecobici-pulse-three.vercel.app/**

A live occupancy map of Mexico City's Ecobici bike-share system: a Python
poller streams the public GBFS feed through Kafka, a consumer joins it
against station metadata and fans it out to TimescaleDB (history) and
Supabase (current snapshot + Realtime push), and a Next.js app renders it
on a live map -- station pins colored by occupancy, plus top-10 lists of
the best stations to grab or return a bike right now.

```
Ecobici GBFS (public, no auth)
  station_status.json   polled every 60s
  station_information.json   polled hourly (cached)
        |
        v
  poller (Python) --produces--> Kafka topic `station-status-raw`
                                       |
                                       v
                            consumer (Python)
                              - joins cached station_information
                              - computes occupancy_pct
                              - INSERT history row -> TimescaleDB hypertable
                              - UPSERT snapshot row -> Supabase Postgres
                              - broadcast delta -> Supabase Realtime channel
                                       |
                                       v
                           Next.js app (Vercel)
                             - initial load: station_snapshot table
                             - live updates: Realtime broadcast subscription
                             - MapLibre GL map, pins colored by occupancy %
                             - top-10 lists: best stations to grab/return a bike
```

## Why this design

The self-hosted piece (Kafka + TimescaleDB + poller + consumer, run via
Docker Compose on an always-on VM) needs **zero inbound ports open to the
internet** -- it only makes outbound writes to Supabase. Supabase (a
managed free-tier service) is the only thing browsers ever talk to
directly. No managed "free forever" Kafka exists any more (checked
2026-08-23: Upstash Kafka is discontinued, Redpanda/Confluent's free tiers
are time-limited trials) so Kafka is self-hosted -- which also matches the
project's own "Docker Compose" stack choice rather than working around it.

TimescaleDB holds full history (for a "last 24h" chart per station);
Supabase Postgres holds only the current snapshot, for a fast initial page
load, plus is the Realtime pub/sub relay for live deltas.

## Local development

Prerequisites: Docker, a Supabase project (see below -- the consumer talks
to the real Supabase project even in local dev, there's no local stand-in
for Realtime).

```bash
cp .env.example .env   # fill in SUPABASE_* values; see db/supabase/schema.sql to set the project up
docker compose up --build
```

This runs a single-node Kafka (KRaft mode, no ZooKeeper) and TimescaleDB
locally, plus the poller and consumer, all pointed at the real Ecobici
feed -- no fixture/mock needed for the happy path.

Run the Next.js app separately:

```bash
cd web
cp ../.env.example .env.local   # only need the NEXT_PUBLIC_* values here
npm install
npm run dev
```

### Tests

```bash
python -m venv .venv && .venv/Scripts/activate  # or source .venv/bin/activate on macOS/Linux
pip install -r requirements-dev.txt
pytest tests/
```

Unit tests run against fixture JSON (`tests/fixtures/`), no network or
Docker required.

## Setting up Supabase

1. Create a new Supabase project (dashboard -> New Project). Keep it
   separate from any other project you run.
2. Run [`db/supabase/schema.sql`](db/supabase/schema.sql) in the SQL
   editor.
3. From Project Settings -> API, copy the project URL, anon key, and
   service role key. From the dashboard's **Connect** panel, copy the
   **Session pooler** connection string for `SUPABASE_DB_DSN` -- **not**
   the direct connection string. The direct connection is IPv6-only
   (unless you pay for Supabase's IPv4 add-on), and most hosts running the
   consumer (this project's production VM included) have no IPv6 egress,
   so the direct string fails with a misleading `Network is unreachable`
   error rather than a DNS or auth error. See CLAUDE.md's "Known gotchas"
   for detail.
4. Fill those into `.env` (repo root, for the pipeline) and `web/.env.local`
   (Next.js app -- only needs the `NEXT_PUBLIC_*` ones).

## Production deployment

The pipeline (Kafka + TimescaleDB + poller + consumer) runs continuously
on an Oracle Cloud "Always Free" VM -- see
[`scripts/setup_oracle_vm.md`](scripts/setup_oracle_vm.md). The Next.js
app deploys to Vercel via its GitHub integration (Import Git Repository),
same as this project's sibling `professional-website`.

## Known limitations

- The Ecobici GBFS feed's own TTL is 10s; this project polls at 60s
  deliberately (see the roadmap this project came from) rather than
  matching the feed's own refresh rate.
- TimescaleDB's retention policy keeps 14 days of history -- enough for a
  short trend chart, sized to fit comfortably on a free-tier VM's disk.
- No auth/rate-limiting in front of the Supabase snapshot table beyond
  Postgres RLS (public read-only) -- acceptable for a portfolio demo at
  this traffic scale.
