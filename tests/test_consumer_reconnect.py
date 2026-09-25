import os
import sys

import psycopg2
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from consumer.main import ReconnectingWriter  # noqa: E402


class FakeCursor:
    def __init__(self, fail: bool):
        self.fail = fail
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params):
        if self.fail:
            raise psycopg2.InterfaceError("cursor already closed")
        self.executed.append((sql, params))


class FakeConnection:
    def __init__(self, fail: bool):
        self.fail = fail
        self.cursor_obj = FakeCursor(fail)

    def cursor(self):
        return self.cursor_obj


def test_execute_succeeds_on_a_healthy_connection(monkeypatch):
    healthy = FakeConnection(fail=False)
    monkeypatch.setattr("consumer.main.connect", lambda dsn: healthy)

    writer = ReconnectingWriter("dsn")
    writer.execute("INSERT ...", {"a": 1})

    assert healthy.cursor_obj.executed == [("INSERT ...", {"a": 1})]


def test_execute_reconnects_once_after_a_dead_connection(monkeypatch):
    # First connect() call (in __init__) returns a connection whose cursor
    # always raises -- simulating the real bug's dropped connection. The
    # second connect() call (the reconnect) returns a healthy one.
    dead = FakeConnection(fail=True)
    healthy = FakeConnection(fail=False)
    connections = iter([dead, healthy])
    monkeypatch.setattr("consumer.main.connect", lambda dsn: next(connections))

    writer = ReconnectingWriter("dsn")
    writer.execute("INSERT ...", {"a": 1})

    assert healthy.cursor_obj.executed == [("INSERT ...", {"a": 1})]
    assert writer._conn is healthy


def test_execute_raises_when_the_reconnect_is_also_dead(monkeypatch):
    dead = FakeConnection(fail=True)
    still_dead = FakeConnection(fail=True)
    connections = iter([dead, still_dead])
    monkeypatch.setattr("consumer.main.connect", lambda dsn: next(connections))

    writer = ReconnectingWriter("dsn")
    with pytest.raises(psycopg2.InterfaceError):
        writer.execute("INSERT ...", {"a": 1})


def test_execute_values_reconnects_once_after_a_dead_connection(monkeypatch):
    dead = FakeConnection(fail=True)
    healthy = FakeConnection(fail=False)
    connections = iter([dead, healthy])
    monkeypatch.setattr("consumer.main.connect", lambda dsn: next(connections))

    calls = []

    def fake_execute_values(cursor, sql, rows, template, page_size):
        cursor.execute(sql, rows)
        calls.append(page_size)

    monkeypatch.setattr("consumer.main.psycopg2.extras.execute_values", fake_execute_values)

    writer = ReconnectingWriter("dsn")
    writer.execute_values("INSERT ... VALUES %s", [{"a": 1}, {"a": 2}], "(%(a)s)")

    assert healthy.cursor_obj.executed == [("INSERT ... VALUES %s", [{"a": 1}, {"a": 2}])]
    assert calls == [2]
