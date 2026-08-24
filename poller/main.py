"""Polls Ecobici's public GBFS station_status.json every POLL_INTERVAL_S
seconds and produces one StationStatusEvent per station to Kafka.

No auth needed -- the feed is public. We poll at 60s (the roadmap's spec)
even though the feed's own TTL is 10s: no reason to hammer a public city
API harder than a demo project needs.
"""

from __future__ import annotations

import logging
import os
import sys
import time

import httpx
import truststore

# Verify TLS against the OS's native certificate store rather than
# certifi's bundled list. Purely additive/more-correct: it's what browsers
# already do, and it's what makes this run on machines where a corporate
# proxy or antivirus's HTTPS-scanning re-signs traffic with a locally
# trusted root that certifi doesn't know about (this doesn't weaken
# verification -- it still fails closed on a genuinely bad cert).
truststore.inject_into_ssl()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common.kafka_client import TOPIC_STATION_STATUS_RAW, make_producer, produce_json  # noqa: E402
from common.models import StationStatus, StationStatusEvent  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poller")

STATION_STATUS_URL = os.environ.get(
    "STATION_STATUS_URL",
    "https://gbfs.mex.lyftbikes.com/gbfs/en/station_status.json",
)
POLL_INTERVAL_S = int(os.environ.get("POLL_INTERVAL_S", "60"))
REQUEST_TIMEOUT_S = 10.0


def fetch_station_status(client: httpx.Client) -> tuple[int, list[StationStatus]]:
    """Returns (feed_last_updated, stations). Raises on HTTP/parse errors --
    the caller decides whether to retry or crash the poll loop."""
    resp = client.get(STATION_STATUS_URL, timeout=REQUEST_TIMEOUT_S)
    resp.raise_for_status()
    body = resp.json()
    stations = [StationStatus.model_validate(s) for s in body["data"]["stations"]]
    return body["last_updated"], stations


def poll_once(client: httpx.Client, producer, last_seen_feed_update: int | None) -> int | None:
    """Fetches the feed and, if it has actually moved forward since the
    last poll, produces one event per station. Returns the feed's
    last_updated we just saw (for the caller to pass back in next time) so
    we skip producing a full duplicate batch when Ecobici's own backend
    hasn't refreshed between our polls yet."""
    feed_last_updated, stations = fetch_station_status(client)

    if feed_last_updated == last_seen_feed_update:
        log.info("feed unchanged since last poll (last_updated=%s), skipping", feed_last_updated)
        return last_seen_feed_update

    polled_at = int(time.time())
    for station in stations:
        event = StationStatusEvent(
            station_id=station.station_id,
            polled_at=polled_at,
            last_reported=station.last_reported,
            num_bikes_available=station.num_bikes_available,
            num_bikes_disabled=station.num_bikes_disabled,
            num_docks_available=station.num_docks_available,
            num_docks_disabled=station.num_docks_disabled,
            is_installed=station.is_installed,
            is_renting=station.is_renting,
            is_returning=station.is_returning,
        )
        produce_json(producer, TOPIC_STATION_STATUS_RAW, key=station.station_id, value=event.model_dump())
    producer.flush(timeout=10.0)
    log.info("produced %d station events (feed last_updated=%s)", len(stations), feed_last_updated)
    return feed_last_updated


def main() -> None:
    producer = make_producer()
    last_seen_feed_update: int | None = None
    with httpx.Client() as client:
        while True:
            try:
                last_seen_feed_update = poll_once(client, producer, last_seen_feed_update)
            except Exception:
                log.exception("poll failed, will retry next interval")
            time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    main()
