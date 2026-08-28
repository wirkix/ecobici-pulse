# Next steps

Where this project stands and what's left, in order.

## 1. ~~Create a Supabase project~~ -- done

Project created, schema applied, live and receiving writes.

## 2. ~~Set up the Oracle Cloud VM and deploy the pipeline~~ -- done

Docker installed, repo deployed. `docker compose ps` shows kafka,
timescaledb, poller, and consumer all up; `station_snapshot` rows are
updating every ~60-90s, confirmed against the real Supabase project. No
inbound ports besides SSH (verified from outside the VM after fixing a
`docker-compose.prod.yml` bug where `ports: []` wasn't actually clearing
the base file's published ports -- see git history / CLAUDE.md).

Along the way: `SUPABASE_DB_DSN` needed to be the Supavisor session-pooler
connection string, not the direct one -- see the "Known gotchas" entry in
CLAUDE.md if setting this up again elsewhere (e.g. redeploying the VM).

## 3. ~~Deploy the Next.js app to Vercel~~ -- done

Live at **https://ecobici-pulse-three.vercel.app/** -- map loads with
station pins, occupancy numbers advance minute to minute (confirmed via
the on-page "last update" clock, not just a static first paint).

Since the initial deploy: fixed the station popup's text being
unreadable (see CLAUDE.md's `!important` gotcha), added a legend
explaining what the pins/colors mean, and added top-10 "best station to
grab/return a bike" lists with click-to-fly-to.

## 4. Update the portfolio card

The remaining step is updating `professional-website`'s portfolio card
(Spanish copy, live `demo` link to the URL above), matching the
roadmap's "one project fully finished before the next starts" pace
decision, then moving on to roadmap project #4 (Economic Pulse
Lakehouse).

## Known loose ends

- No origin-destination / trip-history analysis -- this project only
  ever polls the live GBFS `station_status.json`/`station_information.json`
  endpoints (aggregate counts per station). Ecobici's separate historical
  trip-data downloads (if you want busiest-route/rebalancing analysis
  later) are untouched by this pipeline; that'd be a distinct effort, not
  a gap in what this project set out to do.
