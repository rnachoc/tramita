package dev.tramita.core.audit;

import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AuditEventRepository extends JpaRepository<AuditEvent, Long> {

  List<AuditEvent> findByClaimIdOrderByEventIdAsc(String claimId);

  /** The trail after a given event, in order; the event relay reads it in pages. */
  List<AuditEvent> findByEventIdGreaterThanOrderByEventIdAsc(Long eventId, Pageable page);
}
