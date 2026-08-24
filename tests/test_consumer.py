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
