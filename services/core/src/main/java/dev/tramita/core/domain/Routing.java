package dev.tramita.core.domain;

/** Who acts on a proposal next. */
public enum Routing {
  /** The rules allow executing the proposal without a person. */
  AUTO,
  /** A claims handler must approve, correct or reject the proposal. */
  HUMAN_REVIEW,
  /** Fraud score above the investigation threshold; a specialist reviews the claim. */
  FRAUD_INVESTIGATION
}
