package dev.tramita.core.proposal;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProposalRepository extends JpaRepository<ProposalRecord, UUID> {

  Optional<ProposalRecord> findByIdempotencyKey(String idempotencyKey);

  List<ProposalRecord> findByClaimClaimIdOrderByCreatedAtAsc(String claimId);

  Optional<ProposalRecord> findFirstByClaimClaimIdOrderByCreatedAtDesc(String claimId);
}
