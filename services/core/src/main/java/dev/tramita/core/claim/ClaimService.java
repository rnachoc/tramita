package dev.tramita.core.claim;

import dev.tramita.core.audit.AuditService;
import dev.tramita.core.domain.ClaimStatus;
import dev.tramita.core.policy.Policy;
import dev.tramita.core.policy.PolicyRepository;
import dev.tramita.core.web.ConflictException;
import dev.tramita.core.web.NotFoundException;
import java.time.Clock;
import java.time.Instant;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ClaimService {

  /** Statuses in which documents and their extractions may still change. */
  public static final Set<ClaimStatus> OPEN_FOR_EVIDENCE =
      EnumSet.of(ClaimStatus.RECEIVED, ClaimStatus.WAITING_DOCUMENTS);

  private final ClaimRepository claims;
  private final ClaimDocumentRepository documents;
  private final PolicyRepository policies;
  private final AuditService audit;
  private final Clock clock;

  public ClaimService(
      ClaimRepository claims,
      ClaimDocumentRepository documents,
      PolicyRepository policies,
      AuditService audit,
      Clock clock) {
    this.claims = claims;
    this.documents = documents;
    this.policies = policies;
    this.audit = audit;
    this.clock = clock;
  }

  /**
   * Registers a claim. Idempotent: submitting the same claim again returns the existing one, while
   * a different claim under an existing id is rejected.
   */
  @Transactional
  public Claim register(ClaimRequests.Register r) {
    Optional<Claim> existing = claims.findById(r.claimId());
    if (existing.isPresent()) {
      Claim c = existing.get();
      boolean same =
          c.getPolicy().getPolicyNumber().equals(r.policyNumber())
              && c.getClaimType() == r.claimType()
              && c.getIncidentDate().equals(r.incidentDate())
              && c.getDescription().equals(r.description());
      if (!same) {
        throw new ConflictException(
            "Claim " + r.claimId() + " already exists with different content");
      }
      return c;
    }
    Policy policy =
        policies
            .findById(r.policyNumber())
            .orElseThrow(() -> new NotFoundException("Unknown policy " + r.policyNumber()));
    if (r.reportedDate().isBefore(r.incidentDate())) {
      throw new IllegalArgumentException("reported_date cannot be before incident_date");
    }
    Instant now = Instant.now(clock);
    Claim claim =
        claims.save(
            new Claim(
                r.claimId(),
                policy,
                r.claimType(),
                r.incidentDate(),
                r.reportedDate(),
                r.location(),
                r.description(),
                r.claimedAmount(),
                r.contactPhone(),
                r.contactEmail(),
                now));
    Map<String, Object> details = new HashMap<>();
    details.put("policy_number", policy.getPolicyNumber());
    details.put("claim_type", r.claimType().name());
    audit.record(claim.getClaimId(), "CLAIM_RECEIVED", details);
    return claim;
  }

  /** Attaches a document. Idempotent on the document id. */
  @Transactional
  public ClaimDocument addDocument(String claimId, ClaimRequests.AddDocument r) {
    Claim claim = get(claimId);
    Optional<ClaimDocument> existing = documents.findById(r.documentId());
    if (existing.isPresent()) {
      ClaimDocument d = existing.get();
      if (!d.getClaim().getClaimId().equals(claimId) || d.getDocumentType() != r.documentType()) {
        throw new ConflictException(
            "Document " + r.documentId() + " already exists with a different claim or type");
      }
      return d;
    }
    requireOpenForEvidence(claim);
    ClaimDocument doc =
        documents.save(
            new ClaimDocument(
                r.documentId(),
                claim,
                r.documentType(),
                r.filename(),
                r.storageKey(),
                Instant.now(clock)));
    audit.record(
        claimId,
        "DOCUMENT_RECEIVED",
        Map.of("document_id", r.documentId(), "document_type", r.documentType().name()));
    return doc;
  }

  @Transactional
  public ClaimDocument recordExtraction(
      String claimId, String documentId, ClaimRequests.Extraction r) {
    ClaimDocument doc =
        documents
            .findById(documentId)
            .filter(d -> d.getClaim().getClaimId().equals(claimId))
            .orElseThrow(
                () ->
                    new NotFoundException(
                        "Unknown document " + documentId + " in claim " + claimId));
    requireOpenForEvidence(doc.getClaim());
    doc.recordExtraction(
        r.fields(),
        r.issueDate(),
        r.issuerTaxId(),
        r.documentNumber(),
        r.statedTotal(),
        r.taxRate(),
        r.lineAmounts(),
        Instant.now(clock));
    Map<String, Object> details = new HashMap<>();
    details.put("document_id", documentId);
    details.put("has_amounts", doc.hasAmounts());
    audit.record(claimId, "DOCUMENT_EXTRACTED", details);
    return doc;
  }

  /**
   * Documents and extractions can only change while the agents may still assess the claim. Once a
   * proposal awaits a human, or the claim is closed, the evidence it was judged on is frozen.
   */
  private static void requireOpenForEvidence(Claim claim) {
    if (!OPEN_FOR_EVIDENCE.contains(claim.getStatus())) {
      throw new ConflictException(
          "Claim "
              + claim.getClaimId()
              + " is "
              + claim.getStatus()
              + "; documents can only change while it is "
              + OPEN_FOR_EVIDENCE);
    }
  }

  @Transactional(readOnly = true)
  public Claim get(String claimId) {
    return claims
        .findById(claimId)
        .orElseThrow(() -> new NotFoundException("Unknown claim " + claimId));
  }

  @Transactional(readOnly = true)
  public List<ClaimDocument> documents(String claimId) {
    get(claimId);
    return documents.findByClaimClaimIdOrderByDocumentIdAsc(claimId);
  }

  @Transactional(readOnly = true)
  public List<Claim> byStatus(List<ClaimStatus> statuses, int limit) {
    return claims.findByStatusInOrderByUpdatedAtAsc(
        statuses, PageRequest.of(0, Math.min(Math.max(limit, 1), 500)));
  }

  @Transactional(readOnly = true)
  public List<Claim> onPolicy(String policyNumber) {
    return claims.findByPolicyPolicyNumberOrderByReportedDateAsc(
        Objects.requireNonNull(policyNumber));
  }
}
