# Next steps

Where this project stands and what's left, in order.

## 1. ~~Create a Supabase project~~ -- done

Project created, schema applied, live and receiving writes.

## 2. ~~Set up the Oracle Cloud VM and deploy the pipeline~~ -- done

Deployed on `163.192.133.188`. `docker compose ps` shows kafka,
timescaledb, poller, and consumer all up; `station_snapshot` rows are
updating every ~60-90s, confirmed against the real Supabase project. No
inbound ports besides SSH (verified from outside the VM after fixing a
`docker-compose.prod.yml` bug where `ports: []` wasn't actually clearing
the base file's published ports -- see git history / CLAUDE.md).

Along the way: `SUPABASE_DB_DSN` needed to be the Supavisor session-pooler
connection string, not the direct one -- see the "Known gotchas" entry in
CLAUDE.md if setting this up again elsewhere (e.g. redeploying the VM).

## 3. Deploy the Next.js app to Vercel

- Vercel dashboard → Add New → Project → Import `wirkix/ecobici-pulse`.
- Root directory: `web`.
- Add the two `NEXT_PUBLIC_SUPABASE_*` env vars (from `web/.env.local` on
  this machine, or Supabase dashboard → Project Settings → API) in the
  project's Settings → Environment Variables.
- Deploy, then open the URL and confirm the map loads with station pins
  and that occupancy numbers are actually changing minute to minute (not
  just a static first paint).

## 4. Once the live demo is confirmed working

Tell Claude — the remaining step is updating `professional-website`'s
portfolio card (Spanish copy, live `demo` link), matching the roadmap's
"one project fully finished before the next starts" pace decision, then
moving on to roadmap project #4 (Economic Pulse Lakehouse).
