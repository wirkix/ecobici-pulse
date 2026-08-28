# Setting up the production VM (Oracle Cloud Always Free)

This is a manual, account-gated step -- Oracle requires a credit card for
identity verification at signup (you're never charged for Always Free
resources, but the verification step itself needs a human). Claude can't
complete this on your behalf; follow this runbook yourself, or share SSH
access afterward and I can drive the rest.

## 1. Create the account and VM

1. Sign up at https://www.oracle.com/cloud/free/ if you don't already have
   an OCI account.
2. Console -> Compute -> Instances -> Create Instance.
3. Image: **Canonical Ubuntu** (22.04 or later).
4. Shape: **VM.Standard.A1.Flex** (Ampere ARM, Always Free-eligible) --
   1-2 OCPU / 6-12 GB RAM is plenty for this project. If A1 capacity is
   unavailable in your region (a known, common Always Free constraint),
   fall back to **VM.Standard.E2.1.Micro** (x86, smaller but also always
   free) -- the Docker images used here (`apache/kafka`, `timescale/timescaledb`)
   publish both `arm64` and `amd64` builds, so either works.
5. Add your SSH public key under "Add SSH keys".
6. **Networking**: leave the default VCN/subnet. Do **not** open any
   ingress rules beyond the default SSH (22) -- this project's design
   deliberately needs no other inbound ports (see README.md's "Why this
   design"). Skip creating a public load balancer or opening 80/443.
7. Create the instance, note its public IP.

## 2. Install Docker

SSH in (`ssh ubuntu@<public-ip>`) and run:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# log out and back in for the group change to apply
```

## 3. Deploy the pipeline

```bash
git clone https://github.com/wirkix/ecobici-pulse.git
cd ecobici-pulse
cp .env.example .env
nano .env   # fill in SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_DB_DSN
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

For `SUPABASE_DB_DSN`, use the dashboard's **Connect** panel -> **Session
pooler** string, not the direct connection string the dashboard shows by
default. This VM has no IPv6 egress (true of most cloud VM images), and
Supabase's direct connection is IPv6-only unless you pay for the IPv4
add-on -- using it here fails with `psycopg2.OperationalError: ...
Network is unreachable` rather than an obviously-DSN-related error. See
CLAUDE.md's "Known gotchas" for detail.

Check it's running:

```bash
docker compose ps
docker compose logs -f poller consumer
```

## 4. Keep it running across reboots

Docker Desktop isn't in play here -- this is plain `dockerd` via the
install script above, which already enables and starts the systemd
service. Combined with `restart: always` in `docker-compose.prod.yml`,
containers come back up automatically after a VM reboot without any
further systemd unit needed.

## 5. Verify

From your own machine (not the VM, since nothing here is publicly
reachable by design):

```sql
-- against the Supabase project's session-pooler connection string (see
-- above -- your own machine may or may not have working IPv6, so use the
-- same pooler string here rather than assuming the direct one will work)
select station_id, name, occupancy_pct, updated_at from station_snapshot order by updated_at desc limit 5;
```

`updated_at` should be within the last ~60-90 seconds and keep advancing
on repeated queries.

## Status

This runbook has already been followed once for this project's live
deployment -- the pipeline is up and running. Re-run it if the VM ever
needs to be recreated from scratch (e.g. after losing access, or moving
to a fresh Always Free tenancy).
