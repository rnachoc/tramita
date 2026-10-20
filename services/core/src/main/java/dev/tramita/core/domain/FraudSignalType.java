package dev.tramita.core.domain;

/** Kinds of fraud indicators. Weights live in the product catalog. */
public enum FraudSignalType {
  DUPLICATE_INVOICE,
  DATE_INCONSISTENCY,
  DESCRIPTION_MISMATCH,
  EARLY_CLAIM,
  FREQUENT_CLAIMS,
  ROUND_AMOUNTS
}
