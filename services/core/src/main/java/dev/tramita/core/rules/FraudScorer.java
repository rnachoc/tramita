package dev.tramita.core.rules;

import dev.tramita.core.catalog.Catalog;
import dev.tramita.core.domain.FraudSignalType;
import java.math.BigDecimal;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;

/**
 * Turns fraud signals into a score with explicit, configurable weights.
 *
 * <p>Signals come from two places: the fraud agent (with evidence and a confidence) and the rules
 * themselves (dates, amounts and claim history, always with confidence 1). They are merged by type,
 * keeping the strongest, and combined with a noisy-OR: {@code score = 1 - prod(1 - weight *
 * confidence)}. Each signal "lets through" a share of the doubt; the weights and thresholds live in
 * the product catalog, not in code.
 */
public final class FraudScorer {

  private static final BigDecimal ROUND_UNIT = BigDecimal.valueOf(50);
  private static final int MIN_ROUND_LINES = 2;

  private final Catalog.FraudRules rules;

  public FraudScorer(Catalog.FraudRules rules) {
    this.rules = rules;
  }

  /** Signals the rules can establish on their own from the claim facts. */
  public List<FraudSignal> ruleSignals(PolicyFacts policy, ClaimFacts claim) {
    List<FraudSignal> signals = new ArrayList<>();
    long sinceStart = ChronoUnit.DAYS.between(policy.startDate(), claim.incidentDate());
    if (sinceStart <= rules.earlyClaimDays()) {
      signals.add(
          FraudSignal.rule(
              FraudSignalType.EARLY_CLAIM,
              "Incident %d days after the policy start (window: %d days)"
                  .formatted(sinceStart, rules.earlyClaimDays())));
    }
    long recent =
        claim.earlierIncidents().stream()
            .filter(
                d ->
                    ChronoUnit.DAYS.between(d, claim.incidentDate())
                        <= rules.frequentClaimsWindowDays())
            .count();
    if (recent + 1 >= rules.frequentClaimsMin()) {
      signals.add(
          FraudSignal.rule(
              FraudSignalType.FREQUENT_CLAIMS,
              "%d claims on this policy within %d days"
                  .formatted(recent + 1, rules.frequentClaimsWindowDays())));
    }
    if (claim.repairDocumentSeenBefore()) {
      signals.add(
          FraudSignal.rule(
              FraudSignalType.DUPLICATE_INVOICE,
              "The same invoice (issuer and number) was submitted with an earlier claim"));
    }
    claim.documentDates().stream()
        .filter(d -> d.isBefore(claim.incidentDate()))
        .findFirst()
        .ifPresent(
            d ->
                signals.add(
                    FraudSignal.rule(
                        FraudSignalType.DATE_INCONSISTENCY,
                        "A document is dated %s, before the incident on %s"
                            .formatted(d, claim.incidentDate()))));
    claim
        .amounts()
        .filter(this::allRound)
        .ifPresent(
            r ->
                signals.add(
                    FraudSignal.rule(
                        FraudSignalType.ROUND_AMOUNTS,
                        "All %d invoice lines are multiples of %s EUR"
                            .formatted(r.lineAmounts().size(), ROUND_UNIT))));
    return signals;
  }

  private boolean allRound(RepairFacts repair) {
    return repair.lineAmounts().size() >= MIN_ROUND_LINES
        && repair.lineAmounts().stream()
            .allMatch(a -> a.remainder(ROUND_UNIT).compareTo(BigDecimal.ZERO) == 0);
  }

  /** Merges signals by type, keeping the one with the highest confidence. */
  public List<FraudSignal> merge(List<FraudSignal> modelSignals, List<FraudSignal> ruleSignals) {
    Map<FraudSignalType, FraudSignal> strongest = new EnumMap<>(FraudSignalType.class);
    for (FraudSignal signal : concat(ruleSignals, modelSignals)) {
      strongest.merge(signal.type(), signal, (a, b) -> a.confidence() >= b.confidence() ? a : b);
    }
    return List.copyOf(strongest.values());
  }

  public double score(List<FraudSignal> signals) {
    double remaining = 1.0;
    for (FraudSignal signal : signals) {
      double weight = rules.weights().getOrDefault(signal.type(), 0.0);
      remaining *= 1 - weight * signal.confidence();
    }
    return Math.round((1 - remaining) * 10_000) / 10_000.0;
  }

  private static List<FraudSignal> concat(List<FraudSignal> first, List<FraudSignal> second) {
    List<FraudSignal> all = new ArrayList<>(first);
    all.addAll(second);
    return all;
  }
}
