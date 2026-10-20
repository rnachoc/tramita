package dev.tramita.core.rules;

import dev.tramita.core.domain.Decision;
import dev.tramita.core.domain.Reason;
import dev.tramita.core.domain.RequiredDocument;
import dev.tramita.core.domain.Routing;
import java.math.BigDecimal;
import java.util.List;

/**
 * The outcome of checking a proposal against the rules.
 *
 * @param decision the decision the rules allow, which overrides the proposal when they disagree
 * @param payableAmount the payment computed by the rules, zero unless approved
 * @param requiredCitations clauses that ground the decision and must be cited
 */
public record Evaluation(
    Decision decision,
    BigDecimal payableAmount,
    Routing routing,
    List<Reason> reasons,
    List<Violation> violations,
    double fraudScore,
    List<FraudSignal> fraudSignals,
    List<RequiredDocument> missingDocuments,
    List<String> requiredCitations) {

  public boolean canExecuteAutomatically() {
    return routing == Routing.AUTO;
  }
}
