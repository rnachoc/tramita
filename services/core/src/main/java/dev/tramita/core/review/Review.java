package dev.tramita.core.review;

import dev.tramita.core.claim.Claim;
import dev.tramita.core.domain.Decision;
import dev.tramita.core.proposal.ProposalRecord;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

/** A claims handler's decision on a proposal. */
@Entity
@Table(name = "reviews")
public class Review {

  @Id private UUID reviewId;

  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(name = "claim_id")
  private Claim claim;

  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(name = "proposal_id")
  private ProposalRecord proposal;

  private String idempotencyKey;
  private String reviewer;

  @Enumerated(EnumType.STRING)
  private ReviewAction action;

  @Enumerated(EnumType.STRING)
  private Decision decision;

  private BigDecimal amount;
  private String comment;
  private Instant createdAt;

  protected Review() {}

  public Review(
      Claim claim,
      ProposalRecord proposal,
      String idempotencyKey,
      String reviewer,
      ReviewAction action,
      Decision decision,
      BigDecimal amount,
      String comment,
      Instant createdAt) {
    this.reviewId = UUID.randomUUID();
    this.claim = claim;
    this.proposal = proposal;
    this.idempotencyKey = idempotencyKey;
    this.reviewer = reviewer;
    this.action = action;
    this.decision = decision;
    this.amount = amount;
    this.comment = comment;
    this.createdAt = createdAt;
  }

  public UUID getReviewId() {
    return reviewId;
  }

  public Claim getClaim() {
    return claim;
  }

  public ProposalRecord getProposal() {
    return proposal;
  }

  public String getIdempotencyKey() {
    return idempotencyKey;
  }

  public String getReviewer() {
    return reviewer;
  }

  public ReviewAction getAction() {
    return action;
  }

  public Decision getDecision() {
    return decision;
  }

  public BigDecimal getAmount() {
    return amount;
  }

  public String getComment() {
    return comment;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }
}
