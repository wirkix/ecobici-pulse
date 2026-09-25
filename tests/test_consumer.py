import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from common.models import StationInformation, StationStatusEvent, compute_occupancy_pct  # noqa: E402
from consumer.main import build_snapshot  # noqa: E402
from consumer.station_info_cache import StationInfoCache  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _fake_info_cache() -> StationInfoCache:
    """A StationInfoCache pre-populated from the fixture, bypassing
    start()/refresh_once()'s HTTP call entirely."""
    cache = StationInfoCache()
    body = _load_fixture("station_information_sample.json")
    cache._stations = {
        s["station_id"]: StationInformation.model_validate(s) for s in body["data"]["stations"]
    }
    return cache


def _event(station_id: str, bikes_available: int, **overrides) -> StationStatusEvent:
    defaults = dict(
        station_id=station_id,
        polled_at=1787539900,
        last_reported=1787539864,
        num_bikes_available=bikes_available,
        num_bikes_disabled=0,
        num_docks_available=10,
        num_docks_disabled=0,
        is_installed=True,
        is_renting=True,
        is_returning=True,
    )
    defaults.update(overrides)
    return StationStatusEvent(**defaults)


def test_compute_occupancy_pct_normal():
    assert compute_occupancy_pct(10, 39) == pytest.approx(25.641, rel=1e-3)


def test_compute_occupancy_pct_zero_capacity_does_not_divide_by_zero():
    assert compute_occupancy_pct(5, 0) == 0.0


def test_compute_occupancy_pct_clamps_above_100():
    # Rebalancing trucks can transiently drop off more bikes than a
    # station's nominal capacity.
    assert compute_occupancy_pct(45, 39) == 100.0


def test_build_snapshot_joins_station_information():
    cache = _fake_info_cache()
    event = _event("1", bikes_available=10)

    snapshot = build_snapshot(event, cache)

    assert snapshot is not None
    assert snapshot.name == "CE-710 Molino del Rey - Glorieta de la Lealtad"
    assert snapshot.capacity == 39
    assert snapshot.occupancy_pct == pytest.approx(25.641, rel=1e-3)


def test_build_snapshot_zero_capacity_station():
    cache = _fake_info_cache()
    event = _event("2", bikes_available=0)

    snapshot = build_snapshot(event, cache)

    assert snapshot is not None
    assert snapshot.capacity == 0
    assert snapshot.occupancy_pct == 0.0


def test_build_snapshot_returns_none_when_station_info_missing():
    cache = _fake_info_cache()
    event = _event("999", bikes_available=5)

    assert build_snapshot(event, cache) is None


def _snapshot(station_id: str, bikes_available: int, **overrides):
    from common.models import StationSnapshot

    defaults = dict(
        station_id=station_id,
        name=f"Station {station_id}",
        lat=19.4,
        lon=-99.1,
        capacity=20,
        bikes_available=bikes_available,
        docks_available=20 - bikes_available,
        occupancy_pct=compute_occupancy_pct(bikes_available, 20),
        is_renting=True,
        is_returning=True,
        observed_at=1787539864,
    )
    defaults.update(overrides)
    return StationSnapshot(**defaults)


def test_batcher_sends_changed_stations_once_per_flush():
    from consumer.main import BroadcastBatcher

    sent = []
    batcher = BroadcastBatcher(sent.append)
    batcher.add(_snapshot("1", 5))
    batcher.add(_snapshot("2", 7))
    batcher.flush()

    assert len(sent) == 1
    assert [s.station_id for s in sent[0]] == ["1", "2"]


def test_batcher_skips_unchanged_stations_even_if_observed_at_moves():
    from consumer.main import BroadcastBatcher

    sent = []
    batcher = BroadcastBatcher(sent.append)
    batcher.add(_snapshot("1", 5))
    batcher.add(_snapshot("2", 7))
    batcher.flush()

    batcher.add(_snapshot("1", 5, observed_at=1787539999))
    batcher.add(_snapshot("2", 6, docks_available=14))
    batcher.flush()

    assert [s.station_id for s in sent[1]] == ["2"]


def test_batcher_flush_with_nothing_changed_sends_nothing():
    from consumer.main import BroadcastBatcher

    sent = []
    batcher = BroadcastBatcher(sent.append)
    batcher.add(_snapshot("1", 5))
    batcher.flush()
    batcher.add(_snapshot("1", 5))
    batcher.flush()
    batcher.flush()

    assert len(sent) == 1


def test_batcher_retries_stations_after_a_failed_send():
    from consumer.main import BroadcastBatcher

    calls = []

    def flaky_send(snapshots):
        calls.append(snapshots)
        if len(calls) == 1:
            raise RuntimeError("503")

    batcher = BroadcastBatcher(flaky_send)
    batcher.add(_snapshot("1", 5))
    batcher.flush()
    batcher.add(_snapshot("1", 5))
    batcher.flush()

    assert len(calls) == 2
    assert [s.station_id for s in calls[1]] == ["1"]


def test_broadcast_supabase_packs_stations_into_chunks():
    from consumer.main import BROADCAST_BATCH_SIZE, broadcast_supabase

    class FakeResponse:
        def raise_for_status(self):
            pass

    class FakeClient:
        def __init__(self):
            self.bodies = []

        def post(self, url, headers, json, timeout):
            self.bodies.append(json)
            return FakeResponse()

    client = FakeClient()
    snapshots = [_snapshot(str(i), 5) for i in range(BROADCAST_BATCH_SIZE * 2 + 1)]
    broadcast_supabase(client, snapshots, "https://x.supabase.co", "key")

    assert len(client.bodies) == 1
    messages = client.bodies[0]["messages"]
    assert [len(m["payload"]["stations"]) for m in messages] == [BROADCAST_BATCH_SIZE, BROADCAST_BATCH_SIZE, 1]
    assert all(m["event"] == "station_batch" and m["private"] for m in messages)
