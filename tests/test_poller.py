import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
import respx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from poller.main import STATION_STATUS_URL, fetch_station_status, poll_once  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@respx.mock
def test_fetch_station_status_parses_all_stations():
    body = _load_fixture("station_status_sample.json")
    respx.get(STATION_STATUS_URL).mock(return_value=httpx.Response(200, json=body))

    with httpx.Client() as client:
        last_updated, stations = fetch_station_status(client)

    assert last_updated == body["last_updated"]
    assert len(stations) == 3
    assert {s.station_id for s in stations} == {"1", "2", "999"}


@respx.mock
def test_poll_once_produces_one_event_per_station_on_first_poll():
    body = _load_fixture("station_status_sample.json")
    respx.get(STATION_STATUS_URL).mock(return_value=httpx.Response(200, json=body))
    producer = MagicMock()

    with httpx.Client() as client:
        result = poll_once(client, producer, last_seen_feed_update=None)

    assert result == body["last_updated"]
    assert producer.produce.call_count == 3
    produced_keys = {call.kwargs["key"] for call in producer.produce.call_args_list}
    assert produced_keys == {b"1", b"2", b"999"}


@respx.mock
def test_poll_once_skips_produce_when_feed_unchanged():
    body = _load_fixture("station_status_sample.json")
    respx.get(STATION_STATUS_URL).mock(return_value=httpx.Response(200, json=body))
    producer = MagicMock()

    with httpx.Client() as client:
        result = poll_once(client, producer, last_seen_feed_update=body["last_updated"])

    assert result == body["last_updated"]
    producer.produce.assert_not_called()


@respx.mock
def test_fetch_station_status_raises_on_http_error():
    respx.get(STATION_STATUS_URL).mock(return_value=httpx.Response(500))

    with httpx.Client() as client:
        with pytest.raises(httpx.HTTPStatusError):
            fetch_station_status(client)
