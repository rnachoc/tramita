package dev.tramita.core.events;

import static org.assertj.core.api.Assertions.assertThat;

import dev.tramita.core.audit.AuditEvent;
import dev.tramita.core.events.ClaimEvents.Position;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

class ClaimEventsTest {

  private static final Instant NOW = Instant.parse("2026-11-16T10:00:00Z");
  private static final Duration GRACE = Duration.ofSeconds(30);

  private static AuditEvent audit(long id, String type, Map<String, Object> details) {
    AuditEvent e = new AuditEvent("CL-1", NOW, "console", "REVIEWER", type, details);
    ReflectionTestUtils.setField(e, "eventId", id);
    return e;
  }

  @Test
  void theEnvelopeCarriesOnlyThePublicFieldsOfItsType() {
    AuditEvent review =
        audit(
            7,
            "REVIEW_RECORDED",
            Map.of(
                "review_id", "r-1",
                "reviewer", "Ana Tramitadora",
                "decision", "APPROVE",
                "amount", new BigDecimal("120.00")));

    Map<String, Object> envelope = ClaimEvents.envelope(review);

    assertThat(envelope)
        .containsEntry("event_id", "7")
        .containsEntry("event_type", "REVIEW_RECORDED")
        .containsEntry("schema_version", 1)
        .containsEntry("claim_id", "CL-1")
        .containsEntry("occurred_at", "2026-11-16T10:00:00Z")
        .containsEntry("actor_role", "REVIEWER");
    assertThat(envelope.get("data"))
        .isEqualTo(
            Map.of("review_id", "r-1", "decision", "APPROVE", "amount", new BigDecimal("120.00")));
  }

  @Test
  void paymentsLeaveTheAccountNumberBehindAndUnknownTypesCarryNoData() {
    AuditEvent paid =
        audit(8, "PAYMENT_EXECUTED", Map.of("payment_id", "p-1", "iban", "ES91 **** 0001"));
    AuditEvent other = audit(9, "SOMETHING_NEW", Map.of("secret", "x"));

    assertThat(ClaimEvents.envelope(paid).get("data")).isEqualTo(Map.of("payment_id", "p-1"));
    assertThat(ClaimEvents.envelope(other).get("data")).isEqualTo(Map.of());
  }

  @Test
  void contiguousEventsArePublishedInOneGo() {
    List<Position> batch = List.of(new Position(4, NOW), new Position(5, NOW));

    assertThat(ClaimEvents.publishable(batch, 3, NOW, GRACE)).isEqualTo(2);
  }

  @Test
  void aRecentGapWaitsForTheTransactionThatMayFillIt() {
    List<Position> batch = List.of(new Position(4, NOW), new Position(6, NOW.minusSeconds(5)));

    assertThat(ClaimEvents.publishable(batch, 3, NOW, GRACE)).isEqualTo(1);
  }

  @Test
  void anOldGapIsARolledBackInsertAndIsSkipped() {
    List<Position> batch = List.of(new Position(6, NOW.minusSeconds(60)), new Position(7, NOW));

    assertThat(ClaimEvents.publishable(batch, 3, NOW, GRACE)).isEqualTo(2);
  }
}
