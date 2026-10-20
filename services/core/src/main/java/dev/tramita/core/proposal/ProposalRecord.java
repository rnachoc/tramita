package dev.tramita.core.proposal;

import dev.tramita.core.claim.Claim;
import dev.tramita.core.domain.Decision;
import dev.tramita.core.domain.Routing;
import dev.tramita.core.rules.Evaluation;
import dev.tramita.core.rules.FraudSignal;
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
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/** A proposal submitted by the agents, stored together with the rules evaluation of it. */
@Entity
@Table(name = "proposals")
public class ProposalRecord {

  @Id private UUID proposalId;

  @ManyToOne(fetch = FetchType.LAZY, optional = false)
  @JoinColumn(name = "claim_id")
  private Claim claim;

  private String idempotencyKey;
  private Instant createdAt;

  @Enumerated(EnumType.STRING)
  private Decision proposedDecision;

  private BigDecimal eligibleAmount;
  private BigDecimal proposedAmount;
  private String exclusionCode;

  @JdbcTypeCode(SqlTypes.JSON)
  private List<String> citations;

  @JdbcTypeCode(SqlTypes.JSON)
  private List<FraudSignal> fraudSignals;

  private String rationale;

  @JdbcTypeCode(SqlTypes.JSON)
  private Map<String, Object> modelMetadata;

  @Enumerated(EnumType.STRING)
  private Decision decision;

  private BigDecimal payableAmount;

  @Enumerated(EnumType.STRING)
  private Routing routing;

  private BigDecimal fraudScore;

  @JdbcTypeCode(SqlTypes.JSON)
  private Evaluation evaluation;

  protected ProposalRecord() {}

  public ProposalRecord(
      Claim claim,
      String idempotencyKey,
      Instant createdAt,
      Decision proposedDecision,
      BigDecimal eligibleAmount,
      BigDecimal proposedAmount,
      String exclusionCode,
      List<String> citations,
      List<FraudSignal> fraudSignals,
      String rationale,
      Map<String, Object> modelMetadata,
      Evaluation evaluation) {
    this.proposalId = UUID.randomUUID();
    this.claim = claim;
    this.idempotencyKey = idempotencyKey;
    this.createdAt = createdAt;
    this.proposedDecision = proposedDecision;
    this.eligibleAmount = eligibleAmount;
    this.proposedAmount = proposedAmount;
    this.exclusionCode = exclusionCode;
    this.citations = List.copyOf(citations);
    this.fraudSignals = List.copyOf(fraudSignals);
    this.rationale = rationale;
    this.modelMetadata = modelMetadata;
    this.evaluation = evaluation;
    this.decision = evaluation.decision();
    this.payableAmount = evaluation.payableAmount();
    this.routing = evaluation.routing();
    this.fraudScore = BigDecimal.valueOf(evaluation.fraudScore());
  }

  public UUID getProposalId() {
    return proposalId;
  }

  public Claim getClaim() {
    return claim;
  }

  public String getIdempotencyKey() {
    return idempotencyKey;
  }

  public Instant getCreatedAt() {
    return createdAt;
  }

  public Decision getProposedDecision() {
    return proposedDecision;
  }

  public BigDecimal getEligibleAmount() {
    return eligibleAmount;
  }

  public BigDecimal getProposedAmount() {
    return proposedAmount;
  }

  public String getExclusionCode() {
    return exclusionCode;
  }

  public List<String> getCitations() {
    return citations;
  }

  public List<FraudSignal> getFraudSignals() {
    return fraudSignals;
  }

  public String getRationale() {
    return rationale;
  }

  public Map<String, Object> getModelMetadata() {
    return modelMetadata;
  }

  public Decision getDecision() {
    return decision;
  }

  public BigDecimal getPayableAmount() {
    return payableAmount;
  }

  public Routing getRouting() {
    return routing;
  }

  public Evaluation getEvaluation() {
    return evaluation;
  }
}
