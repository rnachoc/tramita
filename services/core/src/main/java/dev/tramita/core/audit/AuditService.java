package dev.tramita.core.audit;

import dev.tramita.core.security.ApiClient;
import dev.tramita.core.security.CurrentActor;
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/** Appends to the audit trail within the caller's transaction, so state and audit move together. */
@Service
public class AuditService {

  private final AuditEventRepository events;
  private final Clock clock;

  public AuditService(AuditEventRepository events, Clock clock) {
    this.events = events;
    this.clock = clock;
  }

  @Transactional(propagation = Propagation.MANDATORY)
  public void record(String claimId, String eventType, Map<String, Object> details) {
    ApiClient actor = CurrentActor.get();
    events.save(
        new AuditEvent(
            claimId, Instant.now(clock), actor.name(), actor.role().name(), eventType, details));
  }

  @Transactional(readOnly = true)
  public List<AuditEvent> trail(String claimId) {
    return events.findByClaimIdOrderByEventIdAsc(claimId);
  }
}
