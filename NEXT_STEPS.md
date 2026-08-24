# Next steps

Where this project stands and what's left, in order. Everything below is
blocked on accounts Claude can't create on your behalf (phone/card/email
verification) — the code, tests, and local Docker Compose pipeline are
already built and verified against the real Ecobici feed.

## 1. Create a Supabase project

- Dashboard → New Project. Keep it separate from `professional-website`'s.
- Run [`db/supabase/schema.sql`](db/supabase/schema.sql) in its SQL editor.
- From Project Settings, collect:
  - Project URL
  - anon key
  - service role key
  - direct (non-pooled) Postgres connection string
- Fill those into `.env` (copy from `.env.example`) and `web/.env.local`
  (only needs the `NEXT_PUBLIC_*` ones there).

Full detail: [README.md § Setting up Supabase](README.md#setting-up-supabase).

## 2. Set up the Oracle Cloud VM and deploy the pipeline

Full step-by-step runbook: [`scripts/setup_oracle_vm.md`](scripts/setup_oracle_vm.md).
Short version once you have Supabase creds from step 1:

```bash
# on the new VM, after installing Docker
git clone https://github.com/wirkix/ecobici-pulse.git
cd ecobici-pulse
cp .env.example .env && nano .env   # fill in the SUPABASE_* values
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose ps   # confirm kafka, timescaledb, poller, consumer are all up
```

No inbound ports besides SSH are needed on this VM by design — see
README.md's "Why this design".

## 3. Deploy the Next.js app to Vercel

- Vercel dashboard → Add New → Project → Import `wirkix/ecobici-pulse`.
- Root directory: `web`.
- Add the two `NEXT_PUBLIC_SUPABASE_*` env vars from step 1 in the
  project's Settings → Environment Variables.
- Deploy, then open the URL and confirm the map loads with station pins
  and that occupancy numbers are actually changing minute to minute (not
  just a static first paint).

## 4. Once the live demo is confirmed working

Tell Claude — the remaining step is updating `professional-website`'s
portfolio card (Spanish copy, live `demo` link), matching the roadmap's
"one project fully finished before the next starts" pace decision, then
moving on to roadmap project #4 (Economic Pulse Lakehouse).

## Known loose end

`consumer/main.py`'s `broadcast_supabase()` — the Supabase Realtime REST
broadcast endpoint/body shape was written from documentation, not
confirmed against a real project. First time you run the consumer against
your real Supabase project, watch its logs for errors from that call
specifically; the fix (if needed) is almost certainly just adjusting the
URL path or JSON body shape to match whatever Supabase's current docs say
at that point — the surrounding logic doesn't depend on the exact shape.
