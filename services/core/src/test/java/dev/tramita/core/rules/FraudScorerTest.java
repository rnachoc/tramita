package dev.tramita.core.rules;

import static org.assertj.core.api.Assertions.assertThat;

import dev.tramita.core.TestCatalog;
import dev.tramita.core.domain.FraudSignalType;
import java.util.List;
import org.junit.jupiter.api.Test;

class FraudScorerTest {

  private final FraudScorer scorer = new FraudScorer(TestCatalog.CATALOG.operations().fraud());

  @Test
  void combinesSignalsWithANoisyOr() {
    List<FraudSignal> signals =
        List.of(
            FraudSignal.rule(FraudSignalType.EARLY_CLAIM, "e"),
            FraudSignal.rule(FraudSignalType.ROUND_AMOUNTS, "r"),
            FraudSignal.rule(FraudSignalType.DATE_INCONSISTENCY, "d"));

    // 1 - (1 - 0.35)(1 - 0.15)(1 - 0.5) = 0.72375
    assertThat(scorer.score(signals)).isEqualTo(0.7238);
  }

  @Test
  void scalesEachWeightByTheSignalConfidence() {
    FraudSignal half =
        new FraudSignal(FraudSignalType.DUPLICATE_INVOICE, "x", 0.5, SignalSource.MODEL);

    assertThat(scorer.score(List.of(half))).isEqualTo(0.4);
  }

  @Test
  void keepsTheStrongestSignalOfEachType() {
    FraudSignal weak =
        new FraudSignal(FraudSignalType.DATE_INCONSISTENCY, "model", 0.3, SignalSource.MODEL);
    FraudSignal rule = FraudSignal.rule(FraudSignalType.DATE_INCONSISTENCY, "rule");

    List<FraudSignal> merged = scorer.merge(List.of(weak), List.of(rule));

    assertThat(merged).containsExactly(rule);
  }

  @Test
  void noSignalsMeansZero() {
    assertThat(scorer.score(List.of())).isZero();
  }
}
