package dev.tramita.core.proposal;

import dev.tramita.core.domain.Decision;
import dev.tramita.core.domain.Reason;
import dev.tramita.core.domain.RequiredDocument;
import dev.tramita.core.domain.Routing;
import dev.tramita.core.rules.Evaluation;
import dev.tramita.core.rules.FraudSignal;
import dev.tramita.core.rules.Violation;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** A proposal next to the rules' verdict on it. */
public record ProposalView(
    UUID proposalId,
    Instant createdAt,
    Decision proposedDecision,
    BigDecimal eligibleAmount,
    BigDecimal proposedAmount,
    String exclusionCode,
    List<String> citations,
    String rationale,
    Map<String, Object> modelMetadata,
    Decision decision,
    BigDecimal payableAmount,
    Routing routing,
    List<Reason> reasons,
    List<Violation> violations,
    double fraudScore,
    List<FraudSignal> fraudSignals,
    List<RequiredDocument> missingDocuments,
    List<String> requiredCitations) {

  public static ProposalView of(ProposalRecord p) {
    Evaluation e = p.getEvaluation();
    return new ProposalView(
        p.getProposalId(),
        p.getCreatedAt(),
        p.getProposedDecision(),
        p.getEligibleAmount(),
        p.getProposedAmount(),
        p.getExclusionCode(),
        p.getCitations(),
        p.getRationale(),
        p.getModelMetadata(),
        e.decision(),
        e.payableAmount(),
        e.routing(),
        e.reasons(),
        e.violations(),
        e.fraudScore(),
        e.fraudSignals(),
        e.missingDocuments(),
        e.requiredCitations());
  }
}
