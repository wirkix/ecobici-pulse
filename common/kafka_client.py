"""Thin wrappers around confluent-kafka so poller/ and consumer/ don't each
hand-roll producer/consumer setup and JSON (de)serialization.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any

from confluent_kafka import Consumer, KafkaError, KafkaException, Producer

TOPIC_STATION_STATUS_RAW = "station-status-raw"


def _bootstrap_servers() -> str:
    return os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")


def make_producer() -> Producer:
    return Producer({"bootstrap.servers": _bootstrap_servers()})


def produce_json(producer: Producer, topic: str, key: str, value: dict[str, Any]) -> None:
    producer.produce(
        topic,
        key=key.encode("utf-8"),
        value=json.dumps(value).encode("utf-8"),
    )


def make_consumer(group_id: str, topics: list[str]) -> Consumer:
    consumer = Consumer(
        {
            "bootstrap.servers": _bootstrap_servers(),
            "group.id": group_id,
            # Start from the beginning on a brand-new consumer group so a
            # freshly-deployed consumer doesn't sit idle until the next poll
            # cycle produces something new -- fine at this message volume.
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
        }
    )
    consumer.subscribe(topics)
    return consumer


def iter_json_messages(consumer: Consumer, poll_timeout: float = 1.0) -> Iterator[dict[str, Any]]:
    """Blocks polling `consumer` forever, yielding decoded JSON message
    values. Raises on any non-EOF Kafka error; EOF (no more messages at the
    partition's current end, only relevant when reading a bounded range) is
    swallowed since this is a never-ending stream in practice.
    """
    while True:
        msg = consumer.poll(poll_timeout)
        if msg is None:
            continue
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                continue
            raise KafkaException(msg.error())
        yield json.loads(msg.value().decode("utf-8"))
