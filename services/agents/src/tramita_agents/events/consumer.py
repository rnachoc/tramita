"""Consumes claim events with retries and a dead-letter topic per consumer group (ADR 0004).

- **At least once**: the offset is committed only after the handler succeeded or the message
  went to the dead-letter topic, so a crash replays it. Handlers must be idempotent (events carry
  a unique ``event_id``).
- **Retries** with exponential backoff, in place, so a claim's events keep their order.
- **Dead letters**: a message that still fails, or that does not match the contract, goes to
  ``<topic>.dlt.<group>`` with the error in its headers, and consumption moves on.
- Logs name event ids, types and claim ids only; events carry no personal data.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from confluent_kafka import Consumer as KafkaConsumer
from confluent_kafka import Producer as KafkaProducer
from confluent_kafka.admin import AdminClient, NewTopic  # type: ignore[attr-defined]
from pydantic import ValidationError

from tramita_agents.events.contracts import TOPIC, ClaimEvent

log = logging.getLogger(__name__)

Handler = Callable[[ClaimEvent], None]


class Message(Protocol):
    def error(self) -> Any: ...
    def key(self) -> bytes | None: ...
    def value(self) -> bytes | None: ...


class Consumer(Protocol):
    def subscribe(self, topics: list[str]) -> None: ...
    def poll(self, timeout: float) -> Message | None: ...
    def commit(self, message: Any, asynchronous: bool) -> Any: ...
    def close(self) -> None: ...


class Producer(Protocol):
    def produce(
        self, topic: str, value: bytes | None, key: bytes | None, headers: list[tuple[str, str]]
    ) -> None: ...
    def flush(self, timeout: float) -> int: ...


@dataclass(frozen=True)
class Retry:
    attempts: int = 5
    first_delay_s: float = 0.5
    max_delay_s: float = 30.0

    def delay(self, attempt: int) -> float:
        return float(min(self.max_delay_s, self.first_delay_s * 2 ** (attempt - 1)))


DEFAULT_RETRY = Retry()


def dead_letter_topic(group: str, topic: str = TOPIC) -> str:
    return f"{topic}.dlt.{group}"


@dataclass
class Stats:
    handled: int = 0
    retried: int = 0
    dead_lettered: int = 0


class EventConsumer:
    def __init__(
        self,
        consumer: Consumer,
        producer: Producer,
        group: str,
        handler: Handler,
        *,
        retry: Retry = DEFAULT_RETRY,
        sleep: Callable[[float], None] = time.sleep,
        topic: str = TOPIC,
    ) -> None:
        self.consumer = consumer
        self.producer = producer
        self.group = group
        self.handler = handler
        self.retry = retry
        self.sleep = sleep
        self.topic = topic
        self.stats = Stats()

    def run(self, stop: threading.Event, idle_timeout_s: float | None = None) -> Stats:
        """Consumes until ``stop`` is set, or until nothing arrives for ``idle_timeout_s``."""
        self.consumer.subscribe([self.topic])
        idle_since = time.monotonic()
        try:
            while not stop.is_set():
                message = self.consumer.poll(1.0)
                if message is None:
                    if (
                        idle_timeout_s is not None
                        and time.monotonic() - idle_since > idle_timeout_s
                    ):
                        break
                    continue
                idle_since = time.monotonic()
                if message.error():
                    log.warning("consumer error: %s", message.error())
                    continue
                self.process(message)
                self.consumer.commit(message, asynchronous=False)
        finally:
            self.consumer.close()
        return self.stats

    def process(self, message: Message) -> None:
        try:
            event = ClaimEvent.model_validate_json(message.value() or b"")
            event.payload()
        except ValidationError as error:
            self._dead_letter(message, f"contract: {error.error_count()} error(s)", 0)
            return
        last: Exception | None = None
        for attempt in range(1, self.retry.attempts + 1):
            try:
                self.handler(event)
                self.stats.handled += 1
                return
            except Exception as error:
                last = error
                if attempt < self.retry.attempts:
                    self.stats.retried += 1
                    log.warning(
                        "%s event %s (%s, %s) failed, attempt %d: %s",
                        self.group,
                        event.event_id,
                        event.event_type,
                        event.claim_id,
                        attempt,
                        type(error).__name__,
                    )
                    self.sleep(self.retry.delay(attempt))
        self._dead_letter(message, f"{type(last).__name__}: {last}"[:500], self.retry.attempts)

    def _dead_letter(self, message: Message, reason: str, attempts: int) -> None:
        self.producer.produce(
            dead_letter_topic(self.group, self.topic),
            value=message.value(),
            key=message.key(),
            headers=[("error", reason), ("group", self.group), ("attempts", str(attempts))],
        )
        self.producer.flush(10.0)
        self.stats.dead_lettered += 1
        log.error(
            "%s parked a message in %s: %s", self.group, dead_letter_topic(self.group), reason
        )


def connect(bootstrap: str, group: str) -> tuple[Consumer, Producer]:
    """Real Kafka clients, and the dead-letter topic created if missing (no auto-creation)."""
    # The local broker advertises "localhost"; IPv4 only avoids a refused ::1 attempt per connect.
    common: dict[str, Any] = {"bootstrap.servers": bootstrap, "broker.address.family": "v4"}
    admin = AdminClient(common)
    dlt = dead_letter_topic(group)
    if dlt not in admin.list_topics(timeout=10).topics:
        for future in admin.create_topics([NewTopic(dlt, 1, 1)]).values():
            try:
                future.result()
            except Exception as error:
                log.info("dead-letter topic %s: %s", dlt, error)
    consumer = KafkaConsumer(
        {
            **common,
            "group.id": group,
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
        }
    )
    producer = KafkaProducer({**common, "enable.idempotence": True})
    return consumer, producer  # type: ignore[return-value]
