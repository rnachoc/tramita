package dev.tramita.core.rules;

import dev.tramita.core.domain.Decision;
import java.math.BigDecimal;
import java.util.List;

/**
 * What the agents propose for a claim. Nothing here is trusted: the rules engine checks every field
 * against the catalog, the policy and the documents before anything is executed.
 *
 * @param eligibleAmount damages the agents consider related to the incident, tax included
 * @param proposedAmount the payment the agents propose
 * @param exclusionCode the catalog exclusion the agents rely on to reject, if any
 * @param citations clause ids the agents cite
 * @param reviewRequests why the agents ask for a person to look, if they do. Agents can only make a
 *     claim safer: a request always sends it to a person, and its absence never skips one.
 */
public record Proposal(
    Decision decision,
    BigDecimal eligibleAmount,
    BigDecimal proposedAmount,
    String exclusionCode,
    List<String> citations,
    List<FraudSignal> fraudSignals,
    List<String> reviewRequests) {

  public Proposal {
    reviewRequests = reviewRequests == null ? List.of() : List.copyOf(reviewRequests);
  }

  /** A proposal that does not ask for review. */
  public Proposal(
      Decision decision,
      BigDecimal eligibleAmount,
      BigDecimal proposedAmount,
      String exclusionCode,
      List<String> citations,
      List<FraudSignal> fraudSignals) {
    this(
        decision,
        eligibleAmount,
        proposedAmount,
        exclusionCode,
        citations,
        fraudSignals,
        List.of());
  }
}
