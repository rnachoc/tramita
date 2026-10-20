package dev.tramita.core.web;

import dev.tramita.core.audit.AuditEvent;
import dev.tramita.core.claim.Claim;
import dev.tramita.core.claim.ClaimDocument;
import dev.tramita.core.domain.ClaimStatus;
import dev.tramita.core.domain.CoverageCode;
import dev.tramita.core.domain.Decision;
import dev.tramita.core.domain.DocumentType;
import dev.tramita.core.payment.Payment;
import dev.tramita.core.policy.PolicyView;
import dev.tramita.core.proposal.ProposalView;
import dev.tramita.core.review.Review;
import dev.tramita.core.review.ReviewAction;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Response bodies of the claims API. */
public final class Views {

  private Views() {}

  public record ClaimSummary(
      String claimId,
      String policyNumber,
      CoverageCode claimType,
      LocalDate incidentDate,
      LocalDate reportedDate,
      ClaimStatus status,
      Instant updatedAt) {

    public static ClaimSummary of(Claim c) {
      return new ClaimSummary(
          c.getClaimId(),
          c.getPolicy().getPolicyNumber(),
          c.getClaimType(),
          c.getIncidentDate(),
          c.getReportedDate(),
          c.getStatus(),
          c.getUpdatedAt());
    }
  }

  public record DocumentView(
      String documentId,
      DocumentType documentType,
      String filename,
      String storageKey,
      Instant receivedAt,
      Instant extractedAt,
      Map<String, Object> extraction) {

    public static DocumentView of(ClaimDocument d) {
      return new DocumentView(
          d.getDocumentId(),
          d.getDocumentType(),
          d.getFilename(),
          d.getStorageKey(),
          d.getReceivedAt(),
          d.getExtractedAt(),
          d.getExtraction());
    }
  }

  public record ReviewView(
      UUID reviewId,
      UUID proposalId,
      String reviewer,
      ReviewAction action,
      Decision decision,
      BigDecimal amount,
      String comment,
      Instant createdAt) {

    public static ReviewView of(Review r) {
      return new ReviewView(
          r.getReviewId(),
          r.getProposal().getProposalId(),
          r.getReviewer(),
          r.getAction(),
          r.getDecision(),
          r.getAmount(),
          r.getComment(),
          r.getCreatedAt());
    }
  }

  public record PaymentView(
      UUID paymentId,
      BigDecimal amount,
      String ibanMasked,
      String reference,
      Payment.Trigger triggeredBy,
      Instant executedAt) {

    public static PaymentView of(Payment p) {
      return new PaymentView(
          p.getPaymentId(),
          p.getAmount(),
          p.getIbanMasked(),
          p.getReference(),
          p.getTriggeredBy(),
          p.getExecutedAt());
    }
  }

  public record ClaimView(
      String claimId,
      ClaimStatus status,
      CoverageCode claimType,
      LocalDate incidentDate,
      LocalDate reportedDate,
      String location,
      String description,
      BigDecimal claimedAmount,
      PolicyView policy,
      List<DocumentView> documents,
      List<ProposalView> proposals,
      List<ReviewView> reviews,
      PaymentView payment) {}

  public record ProposalSubmitted(
      ProposalView proposal, ClaimStatus claimStatus, PaymentView payment) {}

  public record ReviewRecorded(ReviewView review, ClaimStatus claimStatus, PaymentView payment) {}

  public record AuditView(
      long eventId,
      Instant occurredAt,
      String actor,
      String actorRole,
      String eventType,
      Map<String, Object> details) {

    public static AuditView of(AuditEvent e) {
      return new AuditView(
          e.getEventId(),
          e.getOccurredAt(),
          e.getActor(),
          e.getActorRole(),
          e.getEventType(),
          e.getDetails());
    }
  }
}
