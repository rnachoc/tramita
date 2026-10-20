package dev.tramita.core.rules;

import dev.tramita.core.catalog.Catalog;
import dev.tramita.core.catalog.ClauseIndex;
import dev.tramita.core.domain.Decision;
import dev.tramita.core.domain.Reason;
import dev.tramita.core.domain.RequiredDocument;
import dev.tramita.core.domain.Routing;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * Checks a proposal against the hard rules and decides what may happen next.
 *
 * <p>The model proposes, this class decides. Checks run in a fixed order: policy in force,
 * guarantee included, waiting period, grounded exclusion, required documents, amounts, notice
 * period, fraud score, citations and routing. When the proposal disagrees with a rule, the rule
 * wins and the disagreement is recorded as a violation, which always sends the claim to a human.
 *
 * <p>The class is pure: no I/O, no clock, no framework. Everything it needs arrives as arguments.
 */
public final class RulesEngine {

  private static final BigDecimal CENT = new BigDecimal("0.01");
  private static final BigDecimal TOTAL_TOLERANCE = new BigDecimal("0.05");

  private final Catalog catalog;
  private final ClauseIndex clauses;
  private final FraudScorer scorer;

  public RulesEngine(Catalog catalog, ClauseIndex clauses) {
    this.catalog = catalog;
    this.clauses = clauses;
    this.scorer = new FraudScorer(catalog.operations().fraud());
  }

  public Evaluation evaluate(PolicyFacts policy, ClaimFacts claim, Proposal proposal) {
    Assessment a = new Assessment();
    Catalog.Product product =
        catalog
            .product(policy.productCode())
            .orElseThrow(
                () -> new IllegalArgumentException("unknown product " + policy.productCode()));
    Optional<Catalog.Guarantee> guarantee = product.guarantee(claim.claimType());

    if (!policy.inForceOn(claim.incidentDate())) {
      a.forced(proposal, Decision.REJECT, Reason.POLICY_NOT_IN_FORCE, null);
    } else if (guarantee.isEmpty()) {
      a.forced(proposal, Decision.REJECT, Reason.NOT_INCLUDED, "not_included:" + claim.claimType());
    } else if (withinWaitingPeriod(policy, claim, guarantee.get())) {
      a.forced(proposal, Decision.REJECT, Reason.WAITING_PERIOD, "waiting:" + claim.claimType());
    } else if (proposal.decision() == Decision.REJECT) {
      assessRejection(claim, proposal, a);
    } else {
      assessDocumentsAndAmounts(policy, claim, proposal, guarantee.get(), a);
    }

    boolean late =
        ChronoUnit.DAYS.between(claim.incidentDate(), claim.reportedDate())
            > catalog.operations().noticeDays();
    if (late) {
      a.reasons.add(Reason.LATE_NOTICE);
    }

    List<FraudSignal> signals =
        scorer.merge(acceptedModelSignals(proposal, a), scorer.ruleSignals(policy, claim));
    double score = scorer.score(signals);
    Catalog.FraudRules fraud = catalog.operations().fraud();
    if (score >= fraud.reviewThreshold()) {
      a.reasons.add(Reason.FRAUD_SUSPECTED);
    }

    List<String> required = requiredCitations(policy.productCode(), a.groundingKey);
    checkCitations(policy.productCode(), proposal.citations(), required, a);
    if (!a.violations.isEmpty()) {
      a.reasons.add(Reason.RULE_VIOLATION);
    }

    Routing routing = route(a, late, score, fraud);
    return new Evaluation(
        a.decision,
        a.payable,
        routing,
        List.copyOf(a.reasons),
        List.copyOf(a.violations),
        score,
        signals,
        List.copyOf(a.missing),
        required);
  }

  private static boolean withinWaitingPeriod(
      PolicyFacts policy, ClaimFacts claim, Catalog.Guarantee guarantee) {
    return ChronoUnit.DAYS.between(policy.startDate(), claim.incidentDate())
        < guarantee.waitingDays();
  }

  private void assessRejection(ClaimFacts claim, Proposal proposal, Assessment a) {
    a.decision = Decision.REJECT;
    String code = proposal.exclusionCode();
    if (code != null && catalog.coverage(claim.claimType()).hasExclusion(code)) {
      a.reasons.add(Reason.EXCLUSION);
      a.groundingKey = "exclusion:" + code;
    } else {
      a.violations.add(
          new Violation(
              "UNGROUNDED_REJECTION",
              code == null
                  ? "Rejection proposed without a catalog exclusion or rule to ground it"
                  : "Exclusion " + code + " does not apply to " + claim.claimType()));
    }
  }

  private void assessDocumentsAndAmounts(
      PolicyFacts policy,
      ClaimFacts claim,
      Proposal proposal,
      Catalog.Guarantee guarantee,
      Assessment a) {
    for (RequiredDocument required : catalog.coverage(claim.claimType()).requiredDocuments()) {
      if (!required.isSatisfiedBy(claim.documentTypes())) {
        a.missing.add(required);
      }
    }
    if (!a.missing.isEmpty()) {
      a.decision = Decision.REQUEST_INFO;
      a.reasons.add(Reason.MISSING_DOCUMENTS);
      a.groundingKey = "documents:" + claim.claimType();
      if (proposal.decision() == Decision.APPROVE) {
        a.violations.add(
            new Violation(
                "APPROVAL_WITH_MISSING_DOCUMENTS", "Required documents missing: " + a.missing));
      }
      return;
    }
    if (proposal.decision() == Decision.REQUEST_INFO) {
      // The agents may ask for more than the minimum, for example when a scan is unreadable.
      a.decision = Decision.REQUEST_INFO;
      return;
    }
    if (claim.amounts().isEmpty()) {
      a.decision = Decision.REQUEST_INFO;
      a.violations.add(
          new Violation("NO_AMOUNTS", "No invoice or estimate amounts were extracted"));
      return;
    }
    assessAmounts(policy, claim.amounts().get(), proposal, guarantee, a);
    a.groundingKey = "coverage:" + claim.claimType();
  }

  private void assessAmounts(
      PolicyFacts policy,
      RepairFacts repair,
      Proposal proposal,
      Catalog.Guarantee guarantee,
      Assessment a) {
    a.decision = Decision.APPROVE;
    a.reasons.add(Reason.COVERED);
    BigDecimal documented = repair.computedTotal();
    BigDecimal eligible =
        proposal.eligibleAmount() == null ? documented : proposal.eligibleAmount();
    if (eligible.compareTo(documented.add(CENT)) > 0) {
      a.violations.add(
          new Violation(
              "ELIGIBLE_ABOVE_DOCUMENTED",
              "Eligible amount %s exceeds what the document supports (%s)"
                  .formatted(eligible, documented)));
      eligible = documented;
    }
    boolean linesRemoved = eligible.compareTo(documented.subtract(CENT)) < 0;
    boolean totalDoesNotAddUp = repair.statedTotal().compareTo(documented.add(TOTAL_TOLERANCE)) > 0;
    if (linesRemoved || totalDoesNotAddUp) {
      a.reasons.add(Reason.AMOUNT_ADJUSTED);
    }
    BigDecimal limit = guarantee.limit().resolve(policy.insuredValue());
    if (eligible.compareTo(limit) > 0) {
      a.reasons.add(Reason.LIMIT_APPLIED);
    }
    BigDecimal deductible = BigDecimal.valueOf(guarantee.deductible());
    if (guarantee.deductible() > 0) {
      a.reasons.add(Reason.DEDUCTIBLE_APPLIED);
    }
    a.payable = eligible.min(limit).subtract(deductible).max(BigDecimal.ZERO);
    a.payable = a.payable.setScale(2, RoundingMode.HALF_UP);
    BigDecimal proposed = proposal.proposedAmount();
    if (proposed != null && proposed.subtract(a.payable).abs().compareTo(CENT) > 0) {
      a.reasons.add(Reason.AMOUNT_RECALCULATED);
    }
    if (a.payable.compareTo(BigDecimal.valueOf(catalog.operations().reviewThresholdEur())) > 0) {
      a.reasons.add(Reason.ABOVE_REVIEW_THRESHOLD);
    }
  }

  /** Model signals need evidence and a confidence in [0, 1]; anything else is discarded. */
  private static List<FraudSignal> acceptedModelSignals(Proposal proposal, Assessment a) {
    List<FraudSignal> accepted = new ArrayList<>();
    for (FraudSignal signal : proposal.fraudSignals()) {
      boolean hasEvidence = signal.evidence() != null && !signal.evidence().isBlank();
      boolean validConfidence = signal.confidence() >= 0 && signal.confidence() <= 1;
      if (hasEvidence && validConfidence) {
        accepted.add(
            new FraudSignal(
                signal.type(), signal.evidence(), signal.confidence(), SignalSource.MODEL));
      } else {
        a.violations.add(
            new Violation(
                "SIGNAL_DISCARDED",
                signal.type() + " discarded: signals need evidence and a confidence in [0, 1]"));
      }
    }
    return accepted;
  }

  private List<String> requiredCitations(String productCode, String groundingKey) {
    if (groundingKey == null) {
      return List.of();
    }
    return clauses.clauseFor(productCode, groundingKey).map(List::of).orElse(List.of());
  }

  private void checkCitations(
      String productCode, List<String> cited, List<String> required, Assessment a) {
    for (String citation : cited) {
      if (!clauses.belongsTo(citation, productCode)) {
        a.violations.add(
            new Violation(
                "INVALID_CITATION",
                "Clause " + citation + " does not exist in product " + productCode));
      }
    }
    for (String clause : required) {
      if (!cited.contains(clause)) {
        a.violations.add(
            new Violation("MISSING_CITATION", "The decision must cite clause " + clause));
      }
    }
  }

  private static Routing route(Assessment a, boolean late, double score, Catalog.FraudRules fraud) {
    if (score >= fraud.investigationThreshold()) {
      return Routing.FRAUD_INVESTIGATION;
    }
    if (score >= fraud.reviewThreshold()) {
      return Routing.HUMAN_REVIEW;
    }
    if (a.decision == Decision.REQUEST_INFO) {
      // Asking for documents is low risk; the claim is assessed again when they arrive.
      return Routing.AUTO;
    }
    boolean needsHuman =
        a.decision == Decision.REJECT
            || late
            || !a.violations.isEmpty()
            || a.reasons.contains(Reason.AMOUNT_ADJUSTED)
            || a.reasons.contains(Reason.ABOVE_REVIEW_THRESHOLD);
    return needsHuman ? Routing.HUMAN_REVIEW : Routing.AUTO;
  }

  /** Mutable scratchpad for one evaluation. */
  private static final class Assessment {
    private Decision decision;
    private BigDecimal payable = BigDecimal.ZERO.setScale(2);
    private String groundingKey;
    private final List<Reason> reasons = new ArrayList<>();
    private final List<Violation> violations = new ArrayList<>();
    private final List<RequiredDocument> missing = new ArrayList<>();

    /** A rule decides regardless of the proposal; a different proposal is a violation. */
    void forced(Proposal proposal, Decision ruled, Reason reason, String key) {
      decision = ruled;
      reasons.add(reason);
      groundingKey = key;
      if (proposal.decision() != ruled) {
        violations.add(
            new Violation(
                "DECISION_OVERRIDDEN",
                "Proposed "
                    + proposal.decision()
                    + " but the rules require "
                    + ruled
                    + " ("
                    + reason
                    + ")"));
      }
    }
  }
}
