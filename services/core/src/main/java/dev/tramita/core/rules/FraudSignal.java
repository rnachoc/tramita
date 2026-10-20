package dev.tramita.core.rules;

import dev.tramita.core.domain.FraudSignalType;

/**
 * A fraud indicator with the evidence that supports it.
 *
 * @param confidence between 0 and 1; rule signals are always 1
 */
public record FraudSignal(
    FraudSignalType type, String evidence, double confidence, SignalSource source) {

  public static FraudSignal rule(FraudSignalType type, String evidence) {
    return new FraudSignal(type, evidence, 1.0, SignalSource.RULE);
  }
}
