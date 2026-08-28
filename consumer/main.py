"""Consumes StationStatusEvent messages from Kafka, joins each against the
cached station_information, computes occupancy, and fans the result out
three ways:

  1. INSERT into TimescaleDB's `station_status_history` hypertable (full
     history, for later charts/analysis).
  2. UPSERT into Supabase Postgres's `station_snapshot` table (current
     state only -- what the Next.js app's initial page load reads).
  3. POST to Supabase Realtime's broadcast REST endpoint (what already-open
     browser tabs receive live, no polling).

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


def write_timescale(cursor, snapshot: StationSnapshot) -> None:
    cursor.execute(INSERT_HISTORY_SQL, snapshot.model_dump())


def write_supabase_snapshot(cursor, snapshot: StationSnapshot) -> None:
    cursor.execute(UPSERT_SNAPSHOT_SQL, snapshot.model_dump())


def broadcast_supabase(
    http_client: httpx.Client, snapshot: StationSnapshot, supabase_url: str, service_role_key: str
) -> None:
    # Verified 2026-08-28 against the real ecobici-pulse Supabase project:
    # POST {url}/realtime/v1/api/broadcast with a "messages" array returns
    # 202 Accepted as expected.
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
                    "event": "station_update",
                    "payload": snapshot.model_dump(),
                }
            ]
        },
        timeout=5.0,
    )
    resp.raise_for_status()


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

    timescale_conn = psycopg2.connect(timescale_dsn)
    timescale_conn.autocommit = True
    supabase_conn = psycopg2.connect(supabase_db_dsn)
    supabase_conn.autocommit = True

    consumer = make_consumer(group_id="ecobici-pulse-consumer", topics=[TOPIC_STATION_STATUS_RAW])

    with httpx.Client() as http_client, timescale_conn.cursor() as ts_cur, supabase_conn.cursor() as sb_cur:
        for raw in iter_json_messages(consumer):
            event = StationStatusEvent.model_validate(raw)
            snapshot = build_snapshot(event, info_cache)
            if snapshot is None:
                continue
            try:
                write_timescale(ts_cur, snapshot)
                write_supabase_snapshot(sb_cur, snapshot)
                broadcast_supabase(http_client, snapshot, supabase_url, supabase_service_role_key)
            except Exception:
                log.exception("failed to process station_id=%s, continuing", event.station_id)


if __name__ == "__main__":
    main()
