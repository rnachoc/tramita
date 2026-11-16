import json
import threading
from dataclasses import dataclass, field
from typing import Any

from tramita_agents.events.consumer import EventConsumer, Retry, dead_letter_topic
from tramita_agents.events.contracts import ClaimEvent


@dataclass
class FakeMessage:
    payload: bytes
    claim: str = "CL-1"

    def error(self) -> None:
        return None

    def key(self) -> bytes:
        return self.claim.encode()

    def value(self) -> bytes:
        return self.payload


@dataclass
class FakeConsumer:
    messages: list[FakeMessage]
    committed: list[FakeMessage] = field(default_factory=list)
    closed: bool = False

    def subscribe(self, topics: list[str]) -> None:
        self.topics = topics

    def poll(self, timeout: float) -> FakeMessage | None:
        return self.messages.pop(0) if self.messages else None

    def commit(self, message: Any, asynchronous: bool) -> None:
        self.committed.append(message)

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeProducer:
    sent: list[tuple[str, bytes | None, list[tuple[str, str]]]] = field(default_factory=list)

    def produce(
        self, topic: str, value: bytes | None, key: bytes | None, headers: list[tuple[str, str]]
    ) -> None:
        self.sent.append((topic, value, headers))

    def flush(self, timeout: float) -> int:
        return 0


def _event(event_id: str, kind: str = "DOCUMENT_RECEIVED") -> FakeMessage:
    data = {"document_id": "D-1", "document_type": "INVOICE"} if kind == "DOCUMENT_RECEIVED" else {}
    body = {
        "event_id": event_id,
        "event_type": kind,
        "schema_version": 1,
        "claim_id": "CL-1",
        "occurred_at": "2026-11-16T10:00:00Z",
        "actor_role": "AGENT",
        "data": data,
    }
    return FakeMessage(json.dumps(body).encode())


def _run(
    messages: list[FakeMessage], handler: Any
) -> tuple[FakeConsumer, FakeProducer, Any, list[float]]:
    consumer, producer = FakeConsumer(messages), FakeProducer()
    sleeps: list[float] = []
    worker = EventConsumer(
        consumer,
        producer,
        "signals",
        handler,
        retry=Retry(attempts=3, first_delay_s=0.5),
        sleep=sleeps.append,
    )
    stats = worker.run(threading.Event(), idle_timeout_s=0)
    return consumer, producer, stats, sleeps


def test_events_are_handled_in_order_and_committed_after_success() -> None:
    seen: list[str] = []
    messages = [_event("1"), _event("2")]

    consumer, producer, stats, _ = _run(list(messages), lambda e: seen.append(e.event_id))

    assert seen == ["1", "2"]
    assert consumer.committed == messages
    assert (stats.handled, producer.sent, consumer.closed) == (2, [], True)


def test_a_failing_handler_is_retried_with_backoff_then_dead_lettered() -> None:
    calls: list[ClaimEvent] = []

    def flaky(event: ClaimEvent) -> None:
        calls.append(event)
        raise RuntimeError("temporal unavailable")

    message = _event("7")
    consumer, producer, stats, sleeps = _run([message], flaky)

    assert len(calls) == 3
    assert sleeps == [0.5, 1.0]
    topic, value, headers = producer.sent[0]
    assert topic == dead_letter_topic("signals") == "tramita.claim-events.dlt.signals"
    assert value == message.payload
    assert ("error", "RuntimeError: temporal unavailable") in headers
    assert ("attempts", "3") in headers
    assert consumer.committed == [message]  # parked, so consumption moves on
    assert (stats.retried, stats.dead_lettered) == (2, 1)


def test_a_handler_that_recovers_is_not_dead_lettered() -> None:
    attempts = iter([RuntimeError("once"), None])

    def recovers(_: ClaimEvent) -> None:
        error = next(attempts)
        if error:
            raise error

    _, producer, stats, sleeps = _run([_event("8")], recovers)

    assert (stats.handled, stats.retried, producer.sent, sleeps) == (1, 1, [], [0.5])


def test_a_message_that_breaks_the_contract_goes_straight_to_the_dead_letter_topic() -> None:
    handled: list[ClaimEvent] = []
    bad = FakeMessage(b'{"event_id": "9"}')

    consumer, producer, stats, _ = _run([bad, _event("10")], handled.append)

    assert producer.sent[0][2][0][1].startswith("contract:")
    assert [e.event_id for e in handled] == ["10"]
    assert consumer.committed == [bad, consumer.committed[1]]
    assert stats.dead_lettered == 1


def test_backoff_is_capped() -> None:
    retry = Retry(attempts=10, first_delay_s=1, max_delay_s=5)

    assert [retry.delay(n) for n in range(1, 6)] == [1, 2, 4, 5, 5]
