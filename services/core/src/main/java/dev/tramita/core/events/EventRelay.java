package dev.tramita.core.events;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.tramita.core.audit.AuditEvent;
import dev.tramita.core.audit.AuditEventRepository;
import java.time.Clock;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.PageRequest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.scheduling.annotation.Scheduled;

/**
 * Publishes the audit trail to Kafka in order, at least once (ADR 0014).
 *
 * <p>Each run reads the events after the cursor, publishes the contiguous ones keyed by claim (so a
 * claim's events stay in order on one partition) and only then moves the cursor. A crash between
 * the two publishes some events again; consumers deduplicate by {@code event_id}.
 */
public class EventRelay {

  private static final Logger log = LoggerFactory.getLogger(EventRelay.class);
  private static final String RELAY = "kafka";

  private final AuditEventRepository events;
  private final JdbcTemplate jdbc;
  private final KafkaTemplate<String, String> kafka;
  private final ObjectMapper json;
  private final Clock clock;
  private final EventsProperties properties;

  public EventRelay(
      AuditEventRepository events,
      JdbcTemplate jdbc,
      KafkaTemplate<String, String> kafka,
      ObjectMapper json,
      Clock clock,
      EventsProperties properties) {
    this.events = events;
    this.jdbc = jdbc;
    this.kafka = kafka;
    this.json = json;
    this.clock = clock;
    this.properties = properties;
  }

  @Scheduled(fixedDelayString = "${tramita.events.relay-interval-ms:500}")
  public void relay() {
    try {
      while (relayBatch() > 0) {
        // keep going while there is a backlog
      }
    } catch (RuntimeException | InterruptedException | ExecutionException | TimeoutException e) {
      if (e instanceof InterruptedException) {
        Thread.currentThread().interrupt();
      }
      // The cursor did not move: the same events are retried on the next run.
      log.warn("Event relay paused: {}", e.toString());
    }
  }

  /** Publishes one batch and returns how many events it published. */
  int relayBatch() throws InterruptedException, ExecutionException, TimeoutException {
    Long cursor =
        jdbc.queryForObject(
            "SELECT last_event_id FROM core.event_relay WHERE relay = ?", Long.class, RELAY);
    List<AuditEvent> batch =
        events.findByEventIdGreaterThanOrderByEventIdAsc(
            cursor, PageRequest.of(0, properties.batchSize()));
    int count =
        ClaimEvents.publishable(
            batch.stream().map(ClaimEvents.Position::of).toList(),
            cursor,
            clock.instant(),
            properties.gapGrace());
    if (count == 0) {
      return 0;
    }
    for (AuditEvent e : batch.subList(0, count)) {
      if (e.getClaimId() == null) {
        continue; // reference data imports: not claim events
      }
      kafka
          .send(properties.topic(), e.getClaimId(), serialise(e))
          .get(properties.sendTimeout().toMillis(), TimeUnit.MILLISECONDS);
    }
    long last = batch.get(count - 1).getEventId();
    jdbc.update(
        "UPDATE core.event_relay SET last_event_id = ?, updated_at = now() WHERE relay = ?",
        last,
        RELAY);
    return count;
  }

  private String serialise(AuditEvent e) {
    try {
      return json.writeValueAsString(ClaimEvents.envelope(e));
    } catch (JsonProcessingException ex) {
      throw new IllegalStateException("Event " + e.getEventId() + " cannot be serialised", ex);
    }
  }

  /** Settings under {@code tramita.events}. */
  public record EventsProperties(
      String topic, int batchSize, Duration gapGrace, Duration sendTimeout) {}
}
