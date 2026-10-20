package dev.tramita.core.review;

import dev.tramita.core.audit.AuditService;
import dev.tramita.core.catalog.Catalog;
import dev.tramita.core.claim.Claim;
import dev.tramita.core.claim.ClaimService;
import dev.tramita.core.domain.ClaimStatus;
import dev.tramita.core.domain.Decision;
import dev.tramita.core.payment.Payment;
import dev.tramita.core.payment.PaymentService;
import dev.tramita.core.proposal.ProposalRecord;
import dev.tramita.core.proposal.ProposalRepository;
import dev.tramita.core.web.ConflictException;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Records human decisions on proposals. Humans can override the agents, but not the policy: a
 * corrected payment can never exceed the limit of the guarantee.
 */
@Service
public class ReviewService {

  private final ReviewRepository reviews;
  private final ProposalRepository proposals;
  private final ClaimService claims;
  private final PaymentService payments;
  private final AuditService audit;
  private final Catalog catalog;
  private final Clock clock;

  public ReviewService(
      ReviewRepository reviews,
      ProposalRepository proposals,
      ClaimService claims,
      PaymentService payments,
      AuditService audit,
      Catalog catalog,
      Clock clock) {
    this.reviews = reviews;
    this.proposals = proposals;
    this.claims = claims;
    this.payments = payments;
    this.audit = audit;
    this.catalog = catalog;
    this.clock = clock;
  }

  public record Outcome(Review review, ClaimStatus claimStatus, Optional<Payment> payment) {}

  @Transactional
  public Outcome review(String claimId, String idempotencyKey, ReviewRequest request) {
    Optional<Review> replay = reviews.findByIdempotencyKey(idempotencyKey);
    if (replay.isPresent()) {
      Review r = replay.get();
      if (!r.getClaim().getClaimId().equals(claimId)) {
        throw new ConflictException(
            "Idempotency-Key already used for claim " + r.getClaim().getClaimId());
      }
      return new Outcome(r, r.getClaim().getStatus(), payments.forClaim(claimId));
    }
    Claim claim = claims.get(claimId);
    if (!claim.getStatus().awaitsHuman()) {
      throw new ConflictException(
          "Claim " + claimId + " is " + claim.getStatus() + " and does not await review");
    }
    ProposalRecord proposal =
        proposals
            .findFirstByClaimClaimIdOrderByCreatedAtDesc(claimId)
            .orElseThrow(
                () -> new ConflictException("Claim " + claimId + " has no proposal to review"));

    Decision decision;
    BigDecimal amount;
    switch (request.action()) {
      case APPROVE -> {
        decision = proposal.getDecision();
        amount = proposal.getPayableAmount();
      }
      case CORRECT -> {
        requireComment(request);
        if (request.decision() == null) {
          throw new IllegalArgumentException("A correction must state the corrected decision");
        }
        decision = request.decision();
        amount =
            decision == Decision.APPROVE
                ? requireAmountWithinLimit(claim, request.amount())
                : BigDecimal.ZERO;
      }
      case REJECT -> {
        requireComment(request);
        decision = Decision.REJECT;
        amount = BigDecimal.ZERO;
      }
      default -> throw new IllegalArgumentException("Unknown action " + request.action());
    }

    Instant now = Instant.now(clock);
    Review review =
        reviews.save(
            new Review(
                claim,
                proposal,
                idempotencyKey,
                request.reviewer(),
                request.action(),
                decision,
                amount,
                request.comment(),
                now));
    claim.moveTo(statusAfter(decision), now);
    Map<String, Object> details = new HashMap<>();
    details.put("review_id", review.getReviewId().toString());
    details.put("reviewer", request.reviewer());
    details.put("action", request.action().name());
    details.put("decision", decision.name());
    details.put("amount", amount);
    details.put("agrees_with_proposal", agrees(proposal, decision, amount));
    audit.record(claimId, "REVIEW_RECORDED", details);

    Optional<Payment> payment = Optional.empty();
    if (decision == Decision.APPROVE && amount.signum() > 0) {
      payment =
          Optional.of(
              payments.execute(
                  claim, amount, Payment.Trigger.REVIEW, "review:" + review.getReviewId()));
    }
    return new Outcome(review, claim.getStatus(), payment);
  }

  @Transactional(readOnly = true)
  public List<Review> forClaim(String claimId) {
    return reviews.findByClaimClaimIdOrderByCreatedAtAsc(claimId);
  }

  @Transactional(readOnly = true)
  public List<Review> corrections() {
    return reviews.findByActionOrderByCreatedAtAsc(ReviewAction.CORRECT);
  }

  private static ClaimStatus statusAfter(Decision decision) {
    return switch (decision) {
      case APPROVE -> ClaimStatus.APPROVED;
      case REJECT -> ClaimStatus.REJECTED;
      case REQUEST_INFO -> ClaimStatus.WAITING_DOCUMENTS;
    };
  }

  private static boolean agrees(ProposalRecord proposal, Decision decision, BigDecimal amount) {
    return proposal.getDecision() == decision && proposal.getPayableAmount().compareTo(amount) == 0;
  }

  private static void requireComment(ReviewRequest request) {
    if (request.comment() == null || request.comment().isBlank()) {
      throw new IllegalArgumentException(
          "A " + request.action() + " review must explain the decision in a comment");
    }
  }

  private BigDecimal requireAmountWithinLimit(Claim claim, BigDecimal amount) {
    if (amount == null || amount.signum() <= 0) {
      throw new IllegalArgumentException("An approving correction must state a positive amount");
    }
    Catalog.Guarantee guarantee =
        catalog
            .product(claim.getPolicy().getProductCode())
            .flatMap(p -> p.guarantee(claim.getClaimType()))
            .orElseThrow(
                () ->
                    new IllegalArgumentException(
                        "The policy does not include "
                            + claim.getClaimType()
                            + "; it cannot be approved"));
    BigDecimal limit = guarantee.limit().resolve(claim.getPolicy().getInsuredValue());
    if (amount.compareTo(limit) > 0) {
      throw new IllegalArgumentException(
          "Amount " + amount + " exceeds the guarantee limit of " + limit);
    }
    return amount;
  }
}
