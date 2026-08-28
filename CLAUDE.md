# CLAUDE.md

Guidance for Claude Code (and future contributors) working in this repo.

## What this is

Project #3 of Alois Wirkes' portfolio roadmap ("CDMX Bike-Share Pulse"):
streams Mexico City's public Ecobici GBFS feed through Kafka into
TimescaleDB (history) and Supabase (live snapshot + Realtime), rendered on
a live map by a Next.js app. See [README.md](README.md) for architecture
and setup.

## Repo layout

```
common/            pydantic models + Kafka producer/consumer wrappers, shared
                    by poller/ and consumer/
poller/main.py      polls station_status.json every 60s, produces to Kafka
consumer/main.py     consumes, joins station_information, writes/broadcasts
consumer/station_info_cache.py   in-memory cache of station_information.json,
                                  refreshed hourly in a background thread
db/timescale/schema.sql    hypertable + retention policy (self-hosted DB)
db/supabase/schema.sql      station_snapshot table + RLS (Supabase project)
web/                Next.js app -- MapLibre map, Realtime subscription
docker-compose.yml            local dev: kafka + timescaledb + poller + consumer
docker-compose.prod.yml        prod overrides for the VM (no published ports)
scripts/setup_oracle_vm.md     manual runbook for the account-gated VM step
tests/               pytest unit tests, run against fixture JSON (no network)
```

## Local dev gotchas

- **This dev machine's Avast antivirus intercepts outbound HTTPS to hosts
  outside its allowlist** (pypi.org is allowlisted; gbfs.mex.lyftbikes.com,
  Supabase, etc. are not), re-signing traffic with a root CA that's in
  Windows' OS trust store but not in `certifi`'s bundled list. Symptom:
  `httpx.ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] ... unable to get
  local issuer certificate` on a host machine call that should work fine
  (confirmed the target itself is reachable and its real cert is valid).
  Fixed by calling `truststore.inject_into_ssl()` before creating any
  `httpx` client in `poller/main.py` and `consumer/main.py` -- this makes
  `ssl` verify against the OS-native trust store instead of `certifi`,
  which is strictly more correct (still fails closed on a genuinely bad
  cert) and doesn't disable verification. Don't remove this thinking it's
  dead code; it's required on this machine and harmless elsewhere. The
  production VM (no Avast) doesn't need it but isn't hurt by it either.
- Building the poller/consumer **Docker images** on this same machine can
  still fail with the identical SSL error, but from `pip install` running
  *inside* the container -- the interception apparently also breaks
  Docker Desktop's WSL2 network path for arbitrary new hosts (pypi.org
  itself is generally fine, so a bare `pip install` may work while a
  fresh, less-common package mirror wouldn't). If this happens: verify
  `common/`, `poller/`, `consumer/` logic directly via `pytest` (needs no
  Docker) and, for a real Kafka/Postgres integration check, run
  `docker compose up -d kafka timescaledb` (pre-built images, no `pip`
  involved) and run `poller/main.py`/`consumer/main.py` directly via a
  host virtualenv pointed at `localhost:9092` / `localhost:5433` instead
  of building the poller/consumer images. Do not "fix" this by adding
  `--trusted-host`/disabling TLS verification in the Dockerfiles --
  that's a real security regression for image builds anywhere else,
  `truststore` is the correct fix.
- Uses Python 3.12 (`py -3.12`), not whatever `python`/`python3` resolves
  to by default on this machine, for parity with [[wide-table-motor-analytics-build|motor-analytics]]'s
  workaround for a different, unrelated Python-3.14 packaging issue on the
  same machine -- not strictly required here, but keeps one fewer moving
  part different across the roadmap's sibling repos.
- `web/.env.local` is git-ignored; `npm run build` needs
  `NEXT_PUBLIC_SUPABASE_URL`/`NEXT_PUBLIC_SUPABASE_ANON_KEY` set to
  *something* (even placeholders) or the build fails at the Supabase
  client's module-eval time, since `StationMap` is prerendered once during
  `next build`'s static generation pass.

## Known gotchas / history

- The Ecobici GBFS feed's `station_status.json` schema uses 0/1 ints for
  `is_installed`/`is_renting`/`is_returning`; pydantic coerces these to
  `bool` automatically -- don't add manual int-to-bool conversion.
- `compute_occupancy_pct()` clamps to [0, 100] because rebalancing trucks
  can transiently push `num_bikes_available` above a station's nominal
  `capacity`, and a handful of decommissioned/kiosk-only stations report
  `capacity == 0`.
- The consumer skips (rather than errors on) a `StationStatusEvent` whose
  `station_id` isn't yet in the `StationInfoCache` -- happens for a
  brand-new station between when it starts reporting status and the
  cache's next hourly refresh, or in the first seconds after consumer
  startup before the initial synchronous fetch in `StationInfoCache.start()`
  completes. Don't change this to raise; a missing join target isn't
  fatal here.
- Supabase's REST broadcast endpoint (`consumer/main.py`'s
  `broadcast_supabase()`) is now verified against the real project --
  `POST {url}/realtime/v1/api/broadcast` with a "messages" array returns
  202 Accepted as documented.
- **`SUPABASE_DB_DSN` must be the Supavisor session-pooler connection
  string** (`postgresql://postgres.<project-ref>:<password>@aws-N-<region>.pooler.supabase.com:5432/postgres`),
  **not** the direct `db.<project-ref>.supabase.co:5432` one from the
  dashboard's default "Connect" tab. Supabase's direct connection is
  IPv6-only (unless you pay for the IPv4 add-on), and the Oracle Cloud VM
  -- like most cloud VM images -- has no IPv6 egress by default, so
  `psycopg2.connect()` fails with `OperationalError: ... Network is
  unreachable`, not a DNS or auth error. Get the pooler string from the
  dashboard's Connect panel -> "Session pooler" (not "Transaction
  pooler," which is port 6543 and doesn't support the session-level
  usage this consumer needs). The `N` in `aws-N-<region>` varies per
  project (this project's is `aws-1-us-west-2`) -- a `tenant/user ...
  not found` error means you guessed the wrong `N`, not a bad
  password. Don't "fix" the direct-connection failure by enabling IPv6
  on the VM instead; the pooler is Supabase's documented recommendation
  for exactly this case and needs no VM networking changes.
- `web/app/globals.css`'s `.maplibregl-popup-content`/`-tip`/
  `-close-button` overrides need `!important` -- don't remove it thinking
  it's redundant. MapLibre's own stylesheet (`maplibre-gl/dist/maplibre-gl.css`,
  imported inside `StationMap.tsx`) defines the same selectors at the same
  specificity, and Next.js places that chunk *after* `globals.css`'s chunk
  in the built page regardless of import order in either file -- so
  without `!important` the equal-specificity tiebreak silently goes to
  MapLibre's rule every time. Confirmed via computed styles against the
  deployed page, twice (the first attempt at this fix, without
  `!important`, shipped and did nothing).
- `StationMap.tsx`'s `focusStation()` (called when a top-10 list entry is
  clicked) explicitly closes every other open popup before opening its
  target. This looks redundant with MapLibre's default
  `Popup({closeOnClick: true})`, but isn't: that default only fires on a
  click that bubbles up as a click *on the map itself* -- which a direct
  dot click does for free, but a click inside the side-panel list never
  does. Without the explicit close, popups opened from the list pile up
  indefinitely instead of replacing each other like dot clicks do.
