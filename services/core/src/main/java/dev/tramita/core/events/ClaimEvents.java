package dev.tramita.core.events;

import dev.tramita.core.audit.AuditEvent;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

/**
 * Turns audit events into the public claim events published on Kafka (ADR 0014).
 *
 * <p>The audit trail is the outbox: each state change writes its audit event in the same
 * transaction, so an event exists if and only if the change committed. Only the fields listed here
 * leave the core; who reviewed a claim and the masked account number stay in the audit trail. The
 * envelope matches {@code docs/events/claim-event.schema.json}.
 */
public final class ClaimEvents {

  public static final int SCHEMA_VERSION = 1;

  static final Map<String, Set<String>> PUBLIC_FIELDS =
      Map.of(
          "CLAIM_RECEIVED", Set.of("policy_number", "claim_type"),
          "DOCUMENT_RECEIVED", Set.of("document_id", "document_type"),
          "DOCUMENT_EXTRACTED", Set.of("document_id", "has_amounts"),
          "PROPOSAL_EVALUATED",
              Set.of(
                  "proposal_id",
                  "proposed_decision",
                  "decision",
                  "payable_amount",
                  "routing",
                  "fraud_score",
                  "violations"),
          "REVIEW_RECORDED",
              Set.of("review_id", "action", "decision", "amount", "agrees_with_proposal"),
          "PAYMENT_EXECUTED", Set.of("payment_id", "amount", "triggered_by"));

  private ClaimEvents() {}

  /** The event as published: an envelope with the public fields of its type only. */
  public static Map<String, Object> envelope(AuditEvent e) {
    Set<String> allowed = PUBLIC_FIELDS.getOrDefault(e.getEventType(), Set.of());
    Map<String, Object> data = new TreeMap<>();
    e.getDetails()
        .forEach(
            (key, value) -> {
              if (allowed.contains(key)) {
                data.put(key, value);
              }
            });
    Map<String, Object> envelope = new LinkedHashMap<>();
    envelope.put("event_id", String.valueOf(e.getEventId()));
    envelope.put("event_type", e.getEventType());
    envelope.put("schema_version", SCHEMA_VERSION);
    envelope.put("claim_id", e.getClaimId());
    envelope.put("occurred_at", e.getOccurredAt().toString());
    envelope.put("actor_role", e.getActorRole());
    envelope.put("data", data);
    return envelope;
  }

  /**
   * How many events at the head of {@code batch} can be published after {@code cursor}.
   *
   * <p>Identifiers come from a sequence and are taken before commit, so a lower id can commit after
   * a higher one. A gap before an event younger than {@code grace} may still be filled by a
   * transaction in flight: publishing stops there and is retried. A gap older than that is a rolled
   * back insert and is skipped.
   */
  public static int publishable(List<Position> batch, long cursor, Instant now, Duration grace) {
    long expected = cursor + 1;
    int count = 0;
    for (Position p : batch) {
      boolean gap = p.eventId() != expected;
      if (gap && p.occurredAt().isAfter(now.minus(grace))) {
        break;
      }
      count++;
      expected = p.eventId() + 1;
    }
    return count;
  }

  /** Where an audit event sits in the trail. */
  public record Position(long eventId, Instant occurredAt) {
    public static Position of(AuditEvent e) {
      return new Position(e.getEventId(), e.getOccurredAt());
    }
  }
}
