"""Consumes StationStatusEvent messages from Kafka, joins each against the
cached station_information, computes occupancy, and fans the result out
three ways:

  1. INSERT into TimescaleDB's `station_status_history` hypertable (full
     history, for later charts/analysis).
  2. UPSERT into Supabase Postgres's `station_snapshot` table (current
     state only -- what the Next.js app's initial page load reads).
  3. POST to Supabase Realtime's broadcast REST endpoint (what already-open
     browser tabs receive live, no polling) -- only stations whose counts
     changed, batched per poll; see BroadcastBatcher.

(2) and (3) both hit Supabase for two different reasons: (2) is durable
state a fresh page load can query; (3) is an ephemeral push so open tabs
don't have to poll for it. Same payload, different purpose.
"""

from __future__ import annotations

import logging
import os
import sys

import httpx
import psycopg2
import truststore

# See poller/main.py for why -- same OS-trust-store TLS verification,
# needed for both the station_information fetch and the Supabase REST call.
truststore.inject_into_ssl()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common.kafka_client import TOPIC_STATION_STATUS_RAW, iter_json_messages, make_consumer  # noqa: E402
from common.models import StationSnapshot, StationStatusEvent, compute_occupancy_pct  # noqa: E402
from consumer.station_info_cache import StationInfoCache  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("consumer")

REALTIME_TOPIC = os.environ.get("REALTIME_TOPIC", "stations")
# Stations per Realtime message. ~250 bytes of JSON each, so 100 keeps a
# message around 25 KB -- well under Realtime's per-message payload limit.
BROADCAST_BATCH_SIZE = 100

INSERT_HISTORY_SQL = """
    INSERT INTO station_status_history
        (time, station_id, bikes_available, docks_available, occupancy_pct, is_renting, is_returning)
    VALUES (to_timestamp(%(observed_at)s), %(station_id)s, %(bikes_available)s, %(docks_available)s,
            %(occupancy_pct)s, %(is_renting)s, %(is_returning)s)
"""

UPSERT_SNAPSHOT_SQL = """
    INSERT INTO station_snapshot
        (station_id, name, lat, lon, capacity, bikes_available, docks_available,
         occupancy_pct, is_renting, is_returning, updated_at)
    VALUES (%(station_id)s, %(name)s, %(lat)s, %(lon)s, %(capacity)s, %(bikes_available)s,
            %(docks_available)s, %(occupancy_pct)s, %(is_renting)s, %(is_returning)s,
            to_timestamp(%(observed_at)s))
    ON CONFLICT (station_id) DO UPDATE SET
        bikes_available = EXCLUDED.bikes_available,
        docks_available = EXCLUDED.docks_available,
        occupancy_pct = EXCLUDED.occupancy_pct,
        is_renting = EXCLUDED.is_renting,
        is_returning = EXCLUDED.is_returning,
        updated_at = EXCLUDED.updated_at
    WHERE station_snapshot.updated_at < EXCLUDED.updated_at
"""


def build_snapshot(event: StationStatusEvent, info_cache: StationInfoCache) -> StationSnapshot | None:
    info = info_cache.get(event.station_id)
    if info is None:
        # Station not in the metadata feed yet (brand new station, or a
        # transient cache miss right after startup before the first
        # refresh completes) -- skip rather than write a row with no
        # name/location.
        log.warning("no station_information for station_id=%s, skipping", event.station_id)
        return None
    return StationSnapshot(
        station_id=event.station_id,
        name=info.name,
        lat=info.lat,
        lon=info.lon,
        capacity=info.capacity,
        bikes_available=event.num_bikes_available,
        docks_available=event.num_docks_available,
        occupancy_pct=compute_occupancy_pct(event.num_bikes_available, info.capacity),
        is_renting=event.is_renting,
        is_returning=event.is_returning,
        observed_at=event.last_reported,
    )


def connect(dsn: str) -> psycopg2.extensions.connection:
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    return conn


class ReconnectingWriter:
    """Holds a single psycopg2 connection and reconnects on a dead one.

    A long-lived connection (this consumer runs for weeks at a time) will
    eventually get dropped server-side -- an idle timeout, a pooler
    recycling it, a network blip -- and psycopg2 doesn't detect that until
    the next query on it fails with InterfaceError/OperationalError. Found
    the hard way: the previous version opened its connections once at
    startup and never reconnected, so a single dropped connection silently
    broke every write for the rest of the process's life (3+ weeks, in
    production) while the container kept reporting healthy.
    """

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._conn = connect(dsn)

    def execute(self, sql: str, params: dict) -> None:
        try:
            with self._conn.cursor() as cursor:
                cursor.execute(sql, params)
            return
        except (psycopg2.InterfaceError, psycopg2.OperationalError):
            log.warning("connection dropped, reconnecting")
            self._conn = connect(self._dsn)
            with self._conn.cursor() as cursor:
                cursor.execute(sql, params)


def broadcast_supabase(
    http_client: httpx.Client,
    snapshots: list[StationSnapshot],
    supabase_url: str,
    service_role_key: str,
) -> None:
    # Verified 2026-08-28 against the real ecobici-pulse Supabase project:
    # POST {url}/realtime/v1/api/broadcast with a "messages" array returns
    # 202 Accepted as expected.
    #
    # "private": True sends on the private channel, which is gated by RLS on
    # realtime.messages (db/supabase/schema.sql): anon may receive, nobody
    # but the service role may send. On the old public channel anyone with
    # the anon key could broadcast fake station updates to every viewer.
    #
    # Each entry in "messages" counts as one Realtime message against the
    # Supabase org's quota, so stations are packed BROADCAST_BATCH_SIZE to a
    # message rather than one message per station.
    chunks = [
        snapshots[i : i + BROADCAST_BATCH_SIZE] for i in range(0, len(snapshots), BROADCAST_BATCH_SIZE)
    ]
    resp = http_client.post(
        f"{supabase_url}/realtime/v1/api/broadcast",
        headers={
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
        },
        json={
            "messages": [
                {
                    "topic": REALTIME_TOPIC,
                    "event": "station_batch",
                    "payload": {"stations": [s.model_dump() for s in chunk]},
                    "private": True,
                }
                for chunk in chunks
            ]
        },
        timeout=5.0,
    )
    resp.raise_for_status()


def _broadcast_key(snapshot: StationSnapshot) -> tuple:
    """The fields a viewer can actually see change on the map. observed_at
    is deliberately excluded: it moves on nearly every poll even when the
    station's counts don't."""
    return (snapshot.bikes_available, snapshot.docks_available, snapshot.is_renting, snapshot.is_returning)


class BroadcastBatcher:
    """Buffers snapshots and broadcasts only stations whose visible state
    changed since their last successful broadcast, batched.

    The previous version POSTed one Realtime message per station per poll
    (~235k messages/day, 24/7, whether or not anyone had the map open),
    blowing through the Supabase org's Free-plan Realtime quota (2.2M/month)
    -- which is shared with other projects in the same org. Unchanged
    stations are skipped entirely; changed ones are flushed together once
    the poll's burst of Kafka messages goes quiet.
    """

    def __init__(self, send):
        self._send = send
        self._last_sent: dict[str, tuple] = {}
        self._pending: dict[str, StationSnapshot] = {}

    def add(self, snapshot: StationSnapshot) -> None:
        if self._last_sent.get(snapshot.station_id) == _broadcast_key(snapshot):
            self._pending.pop(snapshot.station_id, None)
            return
        self._pending[snapshot.station_id] = snapshot

    def flush(self) -> None:
        if not self._pending:
            return
        snapshots = list(self._pending.values())
        self._pending.clear()
        try:
            self._send(snapshots)
        except Exception:
            # _last_sent isn't updated, so these stations still count as
            # changed and go out again with the next poll.
            log.exception("failed to broadcast %d stations, will retry next poll", len(snapshots))
            return
        for s in snapshots:
            self._last_sent[s.station_id] = _broadcast_key(s)
        log.info("broadcast %d changed stations", len(snapshots))


def main() -> None:
    # Read required config lazily, inside main(), rather than at import
    # time -- lets tests import build_snapshot() etc. without a full
    # runtime environment configured.
    timescale_dsn = os.environ["TIMESCALE_DSN"]
    supabase_db_dsn = os.environ["SUPABASE_DB_DSN"]
    supabase_url = os.environ["SUPABASE_URL"]
    supabase_service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    info_cache = StationInfoCache()
    info_cache.start()

    timescale = ReconnectingWriter(timescale_dsn)
    supabase = ReconnectingWriter(supabase_db_dsn)

    consumer = make_consumer(group_id="ecobici-pulse-consumer", topics=[TOPIC_STATION_STATUS_RAW])

    with httpx.Client() as http_client:
        batcher = BroadcastBatcher(
            lambda snapshots: broadcast_supabase(
                http_client, snapshots, supabase_url, supabase_service_role_key
            )
        )
        # yield_idle: the poller produces a whole feed's worth of stations
        # in one burst, so the first idle poll after it means the batch is
        # complete and it's time to broadcast.
        for raw in iter_json_messages(consumer, yield_idle=True):
            if raw is None:
                batcher.flush()
                continue
            event = StationStatusEvent.model_validate(raw)
            snapshot = build_snapshot(event, info_cache)
            if snapshot is None:
                continue
            try:
                timescale.execute(INSERT_HISTORY_SQL, snapshot.model_dump())
                supabase.execute(UPSERT_SNAPSHOT_SQL, snapshot.model_dump())
            except Exception:
                log.exception("failed to process station_id=%s, continuing", event.station_id)
                continue
            batcher.add(snapshot)


if __name__ == "__main__":
    main()
