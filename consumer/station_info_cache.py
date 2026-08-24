"""In-memory cache of Ecobici's station_information.json (name/lat/lon/
capacity per station). This changes rarely -- new stations, capacity
changes after a rebalance of docks -- so we fetch it once at startup and
refresh in a background thread on a slow interval instead of joining
against a live API call per Kafka message.
"""

from __future__ import annotations

import logging
import threading
import time

import httpx

from common.models import StationInformation

log = logging.getLogger("consumer.station_info_cache")

STATION_INFORMATION_URL_DEFAULT = "https://gbfs.mex.lyftbikes.com/gbfs/en/station_information.json"
REFRESH_INTERVAL_S_DEFAULT = 3600  # station metadata changes on the order of days/weeks, not minutes


class StationInfoCache:
    def __init__(
        self,
        url: str = STATION_INFORMATION_URL_DEFAULT,
        refresh_interval_s: int = REFRESH_INTERVAL_S_DEFAULT,
    ) -> None:
        self._url = url
        self._refresh_interval_s = refresh_interval_s
        self._lock = threading.Lock()
        self._stations: dict[str, StationInformation] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def get(self, station_id: str) -> StationInformation | None:
        with self._lock:
            return self._stations.get(station_id)

    def refresh_once(self) -> None:
        with httpx.Client() as client:
            resp = client.get(self._url, timeout=10.0)
            resp.raise_for_status()
            body = resp.json()
        stations = {
            s["station_id"]: StationInformation.model_validate(s) for s in body["data"]["stations"]
        }
        with self._lock:
            self._stations = stations
        log.info("station_information cache refreshed: %d stations", len(stations))

    def start(self) -> None:
        """Fetches synchronously once (so callers can rely on the cache
        being populated immediately after start() returns), then spawns a
        background thread for periodic refreshes."""
        self.refresh_once()

        def _loop() -> None:
            while not self._stop.wait(self._refresh_interval_s):
                try:
                    self.refresh_once()
                except Exception:
                    log.exception("station_information refresh failed, keeping stale cache")

        self._thread = threading.Thread(target=_loop, daemon=True, name="station-info-refresh")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
