package dev.tramita.core.rules;

/** Where a fraud signal comes from. */
public enum SignalSource {
  /** Proposed by the fraud agent, with evidence quoted from the documents. */
  MODEL,
  /** Computed by the rules from dates, amounts and claim history. */
  RULE
}
