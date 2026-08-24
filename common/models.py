"""Pydantic models for the Ecobici GBFS feed and the derived records we
produce/consume through Kafka.

Field names mirror the GBFS spec (https://gbfs.org) as published by
Ecobici's feed, not our own naming conventions -- keep them literal so a
diff against the raw JSON stays obvious.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class StationStatus(BaseModel):
    """One entry from `data.stations` in station_status.json."""

    station_id: str
    num_bikes_available: int
    num_bikes_disabled: int = 0
    num_docks_available: int
    num_docks_disabled: int = 0
    is_installed: bool
    is_renting: bool
    is_returning: bool
    last_reported: int  # unix seconds, set by Ecobici's backend
    # is_installed/is_renting/is_returning arrive as 0/1 ints in the GBFS
    # JSON; pydantic coerces them to bool for these fields automatically.


class StationInformation(BaseModel):
    """One entry from `data.stations` in station_information.json."""

    station_id: str
    name: str
    short_name: str | None = None
    lat: float
    lon: float
    capacity: int
    has_kiosk: bool | None = None


class StationStatusEvent(BaseModel):
    """What the poller actually produces to Kafka: a status reading tagged
    with the poll time. Station metadata is joined later by the consumer,
    not embedded here -- keeps the wire payload small and avoids baking
    slow-changing data into every 60s message."""

    station_id: str
    polled_at: int  # unix seconds, when *our* poller fetched this
    last_reported: int  # unix seconds, from Ecobici
    num_bikes_available: int
    num_bikes_disabled: int
    num_docks_available: int
    num_docks_disabled: int
    is_installed: bool
    is_renting: bool
    is_returning: bool


class StationSnapshot(BaseModel):
    """What the consumer writes downstream (TimescaleDB history row and
    Supabase snapshot row/Realtime broadcast payload) after joining a
    StationStatusEvent with StationInformation."""

    station_id: str
    name: str
    lat: float
    lon: float
    capacity: int
    bikes_available: int
    docks_available: int
    occupancy_pct: float = Field(ge=0, le=100)
    is_renting: bool
    is_returning: bool
    observed_at: int  # unix seconds == StationStatusEvent.last_reported


def compute_occupancy_pct(bikes_available: int, capacity: int) -> float:
    """% of a station's dock capacity currently occupied by a bike.

    Guards against capacity == 0 (a handful of decommissioned/kiosk-only
    stations report this) and against bikes_available briefly exceeding
    capacity (happens transiently during rebalancing trucks' drop-offs) by
    clamping to [0, 100].
    """
    if capacity <= 0:
        return 0.0
    pct = (bikes_available / capacity) * 100
    return max(0.0, min(100.0, pct))
