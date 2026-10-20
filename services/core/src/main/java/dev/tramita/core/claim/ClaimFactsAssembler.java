package dev.tramita.core.claim;

import dev.tramita.core.domain.DocumentType;
import dev.tramita.core.rules.ClaimFacts;
import dev.tramita.core.rules.RepairFacts;
import java.time.LocalDate;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import org.springframework.stereotype.Component;

/** Gathers what the rules need about a claim from the claim, its documents and earlier claims. */
@Component
public class ClaimFactsAssembler {

  private final ClaimRepository claims;
  private final ClaimDocumentRepository documents;

  public ClaimFactsAssembler(ClaimRepository claims, ClaimDocumentRepository documents) {
    this.claims = claims;
    this.documents = documents;
  }

  public ClaimFacts assemble(Claim claim) {
    List<ClaimDocument> docs = documents.findByClaimClaimIdOrderByDocumentIdAsc(claim.getClaimId());
    Set<DocumentType> types = EnumSet.noneOf(DocumentType.class);
    docs.forEach(d -> types.add(d.getDocumentType()));
    List<LocalDate> dates =
        docs.stream().map(ClaimDocument::getIssueDate).filter(Objects::nonNull).toList();
    List<LocalDate> earlier =
        claims
            .findEarlierOnPolicy(
                claim.getPolicy().getPolicyNumber(), claim.getClaimId(), claim.getReportedDate())
            .stream()
            .map(Claim::getIncidentDate)
            .toList();
    boolean seenBefore =
        docs.stream()
            .filter(d -> d.getIssuerTaxId() != null && d.getDocumentNumber() != null)
            .anyMatch(
                d ->
                    documents.existsInEarlierClaim(
                        d.getIssuerTaxId(),
                        d.getDocumentNumber(),
                        claim.getClaimId(),
                        claim.getReportedDate()));
    return new ClaimFacts(
        claim.getClaimId(),
        claim.getClaimType(),
        claim.getIncidentDate(),
        claim.getReportedDate(),
        types,
        dates,
        amounts(docs),
        earlier,
        seenBefore);
  }

  /** Amounts come from the latest invoice, or failing that the latest estimate. */
  static Optional<RepairFacts> amounts(List<ClaimDocument> docs) {
    Comparator<ClaimDocument> order = Comparator.comparing(ClaimDocument::getDocumentId);
    Optional<ClaimDocument> source =
        docs.stream()
            .filter(d -> d.getDocumentType() == DocumentType.INVOICE && d.hasAmounts())
            .max(order);
    if (source.isEmpty()) {
      source =
          docs.stream()
              .filter(d -> d.getDocumentType() == DocumentType.ESTIMATE && d.hasAmounts())
              .max(order);
    }
    return source.map(
        d ->
            new RepairFacts(
                d.getIssuerTaxId(),
                d.getDocumentNumber(),
                d.getIssueDate(),
                d.getLineAmounts(),
                d.getTaxRate(),
                d.getStatedTotal()));
  }
}
