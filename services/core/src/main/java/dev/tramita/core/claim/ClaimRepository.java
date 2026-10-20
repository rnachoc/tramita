package dev.tramita.core.claim;

import dev.tramita.core.domain.ClaimStatus;
import java.time.LocalDate;
import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ClaimRepository extends JpaRepository<Claim, String> {

  List<Claim> findByStatusInOrderByUpdatedAtAsc(List<ClaimStatus> statuses, Pageable page);

  List<Claim> findByPolicyPolicyNumberOrderByReportedDateAsc(String policyNumber);

  /** Claims on the same policy that were reported before the given claim. */
  @Query(
      """
      select c from Claim c
      where c.policy.policyNumber = :policy
        and c.claimId <> :claimId
        and (c.reportedDate < :reported
             or (c.reportedDate = :reported and c.claimId < :claimId))
      """)
  List<Claim> findEarlierOnPolicy(
      @Param("policy") String policyNumber,
      @Param("claimId") String claimId,
      @Param("reported") LocalDate reportedDate);
}
