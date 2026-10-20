package dev.tramita.core.audit;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.Map;
import org.hibernate.annotations.Immutable;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/** One entry of the append-only audit trail. The database rejects updates and deletes. */
@Entity
@Immutable
@Table(name = "audit_events")
public class AuditEvent {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long eventId;

  private String claimId;
  private Instant occurredAt;
  private String actor;
  private String actorRole;
  private String eventType;

  @JdbcTypeCode(SqlTypes.JSON)
  private Map<String, Object> details;

  protected AuditEvent() {}

  public AuditEvent(
      String claimId,
      Instant occurredAt,
      String actor,
      String actorRole,
      String eventType,
      Map<String, Object> details) {
    this.claimId = claimId;
    this.occurredAt = occurredAt;
    this.actor = actor;
    this.actorRole = actorRole;
    this.eventType = eventType;
    this.details = details;
  }

  public Long getEventId() {
    return eventId;
  }

  public String getClaimId() {
    return claimId;
  }

  public Instant getOccurredAt() {
    return occurredAt;
  }

  public String getActor() {
    return actor;
  }

  public String getActorRole() {
    return actorRole;
  }

  public String getEventType() {
    return eventType;
  }

  public Map<String, Object> getDetails() {
    return details;
  }
}
