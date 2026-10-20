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
 */
public record Proposal(
    Decision decision,
    BigDecimal eligibleAmount,
    BigDecimal proposedAmount,
    String exclusionCode,
    List<String> citations,
    List<FraudSignal> fraudSignals) {}
