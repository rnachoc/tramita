package dev.tramita.core.claim;

import java.time.LocalDate;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ClaimDocumentRepository extends JpaRepository<ClaimDocument, String> {

  List<ClaimDocument> findByClaimClaimIdOrderByDocumentIdAsc(String claimId);

  /**
   * Whether another claim reported earlier already submitted a document from the same issuer with
   * the same number: the duplicate-invoice signal.
   */
  @Query(
      """
      select count(d) > 0 from ClaimDocument d
      where d.issuerTaxId = :issuer
        and d.documentNumber = :number
        and d.claim.claimId <> :claimId
        and (d.claim.reportedDate < :reported
             or (d.claim.reportedDate = :reported and d.claim.claimId < :claimId))
      """)
  boolean existsInEarlierClaim(
      @Param("issuer") String issuerTaxId,
      @Param("number") String documentNumber,
      @Param("claimId") String claimId,
      @Param("reported") LocalDate reportedDate);
}
